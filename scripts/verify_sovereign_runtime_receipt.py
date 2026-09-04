#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class ValidationError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"JSON root is not an object: {path.name}")
    return value


def _canonical_sha256(value: dict[str, Any], *, omit: str) -> str:
    projected = {key: item for key, item in value.items() if key != omit}
    return hashlib.sha256(json.dumps(projected, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise ValidationError(detail)


def _scope_from_manifest(manifest: dict[str, Any], run_id: int) -> dict[str, Any]:
    revision = str(manifest.get("revision") or "").lower()
    backend = manifest.get("backend") if isinstance(manifest.get("backend"), dict) else {}
    mcp = manifest.get("mcp") if isinstance(manifest.get("mcp"), dict) else {}
    evidence = str(manifest.get("evidenceSha256") or "").lower()
    _require(manifest.get("schemaVersion") == "sovereign.coordinated-release-manifest.v1", "manifest schema mismatch")
    _require(manifest.get("authoritativeMainRevision") == revision, "manifest main revision mismatch")
    _require(manifest.get("runtimePromotionStatus") == "BLOCKED_PENDING_INDEPENDENT_TARGET_SYSTEM_READBACK", "manifest promotion state is invalid")
    _require(manifest.get("deploymentPerformed") is False, "manifest must not self-attest deployment")
    _require(manifest.get("secretValuesReturned") is False, "manifest secret contract is unsafe")
    _require(len(revision) == 40 and all(char in "0123456789abcdef" for char in revision), "manifest revision is invalid")
    _require(len(evidence) == 64 and all(char in "0123456789abcdef" for char in evidence), "manifest evidence hash is invalid")
    _require(_canonical_sha256(manifest, omit="evidenceSha256") == evidence, "manifest evidence hash mismatch")
    for name, component in (("backend", backend), ("mcp", mcp)):
        digest = str(component.get("digest") or "").lower()
        _require(digest.startswith("sha256:") and len(digest) == 71, f"manifest {name} digest is invalid")
    _require(run_id > 0, "coordinated release run id is invalid")
    return {
        "revision": revision,
        "releaseGateRunId": run_id,
        "backendDigest": str(backend["digest"]).lower(),
        "mcpDigest": str(mcp["digest"]).lower(),
        "manifestEvidenceSha256": evidence,
    }


def _validate_signature(receipt: bytes, signature: bytes, allowed_signers: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="sovereign-runtime-receipt-") as directory:
        root = Path(directory)
        receipt_path = root / "receipt.json"
        signature_path = root / "receipt.json.sig"
        receipt_path.write_bytes(receipt)
        signature_path.write_bytes(signature)
        verification = subprocess.run(
            [
                "ssh-keygen", "-Y", "verify", "-f", str(allowed_signers), "-I", "sovereign-runtime-receipt",
                "-n", "sovereign-runtime-receipt", "-s", str(signature_path),
            ],
            input=receipt,
            capture_output=True,
            check=False,
        )
    _require(verification.returncode == 0, f"target-system receipt signature is invalid: {verification.stderr.decode('utf-8', errors='replace')}")


def _validate_runtime(receipt: dict[str, Any], scope: dict[str, Any]) -> None:
    _require(receipt.get("schemaVersion") == "sovereign.coordinated-release-reconciler-status.v1", "receipt schema mismatch")
    _require(receipt.get("ok") is True and receipt.get("status") == "COORDINATED_RELEASE_DEPLOYED", f"receipt is not a successful coordinated runtime deployment: status={receipt.get('status')}, ok={receipt.get('ok')}")
    _require(receipt.get("secretValuesReturned") is False, "receipt secret contract is unsafe")
    _require(receipt.get("revision") == scope["revision"], f"receipt revision mismatch: expected={scope['revision']}, got={receipt.get('revision')}")
    _require(receipt.get("expectedScope") == scope, f"receipt expected scope mismatch: expected={scope}, got={receipt.get('expectedScope')}")
    _require(receipt.get("evidenceSha256") == _canonical_sha256(receipt, omit="evidenceSha256"), "receipt evidence hash mismatch")
    backend_image = receipt.get("backendImage") if isinstance(receipt.get("backendImage"), dict) else {}
    mcp_image = receipt.get("mcpImage") if isinstance(receipt.get("mcpImage"), dict) else {}
    runtime = receipt.get("runtime") if isinstance(receipt.get("runtime"), dict) else {}
    backend_runtime = runtime.get("backend") if isinstance(runtime.get("backend"), dict) else {}
    mcp_runtime = runtime.get("mcp") if isinstance(runtime.get("mcp"), dict) else {}
    broker = runtime.get("broker") if isinstance(runtime.get("broker"), dict) else {}
    patchmon = runtime.get("patchmon") if isinstance(runtime.get("patchmon"), dict) else {}
    _require(backend_image.get("digest") == scope["backendDigest"], f"backend image digest mismatch: expected={scope['backendDigest']}, got={backend_image.get('digest')}")
    _require(mcp_image.get("digest") == scope["mcpDigest"], f"MCP image digest mismatch: expected={scope['mcpDigest']}, got={mcp_image.get('digest')}")
    _require(backend_runtime.get("running") is True and backend_runtime.get("revision") == scope["revision"] and backend_runtime.get("digest") == scope["backendDigest"], f"backend runtime parity failed: running={backend_runtime.get('running')}, revision={backend_runtime.get('revision')}, digest={backend_runtime.get('digest')}")
    _require(mcp_runtime.get("running") is True and mcp_runtime.get("health") == "healthy" and mcp_runtime.get("revision") == scope["revision"] and mcp_runtime.get("digest") == scope["mcpDigest"], f"mcp runtime parity failed: running={mcp_runtime.get('running')}, health={mcp_runtime.get('health')}, revision={mcp_runtime.get('revision')}, digest={mcp_runtime.get('digest')}")
    _require(broker.get("status") == "BROKER_READY", f"broker readiness failed: status={broker.get('status')}")
    _require(isinstance(patchmon.get("evidenceSha256"), str) and len(patchmon["evidenceSha256"]) == 64, f"PatchMon evidence is missing: {patchmon}")


def main() -> int:
    if len(sys.argv) != 6:
        raise SystemExit("usage: verify_sovereign_runtime_receipt.py MANIFEST ENVELOPE ALLOWED_SIGNERS REPORT RELEASE_GATE_RUN_ID")
    manifest_path, envelope_path, allowed_path, report_path = map(Path, sys.argv[1:5])
    release_gate_run_id = int(sys.argv[5])
    try:
        manifest = _load_json(manifest_path)
        envelope = _load_json(envelope_path)
        scope = _scope_from_manifest(manifest, release_gate_run_id)
        _require(envelope.get("schemaVersion") == "sovereign.independent-target-runtime-receipt.v1", "envelope schema mismatch")
        _require(envelope.get("secretValuesReturned") is False, "envelope secret contract is unsafe")
        _require(envelope.get("scope") == scope, f"envelope scope does not bind manifest: expected={scope}, got={envelope.get('scope')}")
        receipt = base64.b64decode(str(envelope.get("receiptBase64") or ""), validate=True)
        signature = base64.b64decode(str(((envelope.get("signature") or {}) if isinstance(envelope.get("signature"), dict) else {}).get("valueBase64") or ""), validate=True)
        _require(hashlib.sha256(receipt).hexdigest() == envelope.get("receiptSha256"), "envelope receipt hash mismatch")
        _require(((envelope.get("signature") or {}) if isinstance(envelope.get("signature"), dict) else {}).get("namespace") == "sovereign-runtime-receipt", "signature namespace mismatch")
        _validate_signature(receipt, signature, allowed_path)
        parsed_receipt = json.loads(receipt.decode("utf-8"))
        _require(isinstance(parsed_receipt, dict), "receipt root is not an object")
        _validate_runtime(parsed_receipt, scope)
        report = {
            "schemaVersion": "sovereign.runtime-receipt-verdict.v1",
            "status": "VERIFIED",
            "revision": scope["revision"],
            "releaseGateRunId": scope["releaseGateRunId"],
            "backendDigest": scope["backendDigest"],
            "mcpDigest": scope["mcpDigest"],
            "manifestEvidenceSha256": scope["manifestEvidenceSha256"],
            "receiptSha256": envelope["receiptSha256"],
            "secretValuesReturned": False,
        }
        exit_code = 0
    except (ValidationError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        report = {
            "schemaVersion": "sovereign.runtime-receipt-verdict.v1",
            "status": "BLOCKED_BY_MISSING_OR_CONTRADICTED_EVIDENCE",
            "failureSha256": hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),
            "failureDetail": str(exc),
            "secretValuesReturned": False,
        }
        exit_code = 2
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", "utf-8")
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
