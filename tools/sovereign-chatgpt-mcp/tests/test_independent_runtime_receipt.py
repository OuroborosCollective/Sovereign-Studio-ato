from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]
VALIDATOR = REPOSITORY_ROOT / "scripts/verify_sovereign_runtime_receipt.py"


def _sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _write_signed_fixture(directory: Path) -> tuple[Path, Path, Path, int]:
    revision = "a" * 40
    backend_digest = "sha256:" + "b" * 64
    mcp_digest = "sha256:" + "c" * 64
    run_id = 777001
    manifest = {
        "schemaVersion": "sovereign.coordinated-release-manifest.v1",
        "revision": revision,
        "authoritativeMainRevision": revision,
        "backend": {"repository": "ghcr.io/ouroboroscollective/sovereign-backend", "digest": backend_digest},
        "mcp": {"repository": "ghcr.io/ouroboroscollective/sovereign-chatgpt-mcp", "digest": mcp_digest},
        "workflows": {},
        "deploymentPerformed": False,
        "runtimePromotionStatus": "BLOCKED_PENDING_INDEPENDENT_TARGET_SYSTEM_READBACK",
        "secretValuesReturned": False,
    }
    manifest["evidenceSha256"] = _sha256(manifest)
    scope = {
        "revision": revision,
        "releaseGateRunId": run_id,
        "backendDigest": backend_digest,
        "mcpDigest": mcp_digest,
        "manifestEvidenceSha256": manifest["evidenceSha256"],
    }
    receipt = {
        "schemaVersion": "sovereign.coordinated-release-reconciler-status.v1",
        "ok": True,
        "status": "COORDINATED_RELEASE_DEPLOYED",
        "revision": revision,
        "expectedScope": scope,
        "updatedAtEpoch": 1,
        "secretValuesReturned": False,
        "backendImage": {"digest": backend_digest},
        "mcpImage": {"digest": mcp_digest},
        "runtime": {
            "backend": {"running": True, "revision": revision, "digest": backend_digest},
            "mcp": {"running": True, "health": "healthy", "revision": revision, "digest": mcp_digest},
            "broker": {"status": "BROKER_READY"},
            "patchmon": {"status": "VERIFIED", "evidenceSha256": "d" * 64},
        },
    }
    receipt["evidenceSha256"] = _sha256(receipt)
    manifest_path = directory / "manifest.json"
    receipt_path = directory / "receipt.json"
    key_path = directory / "target_ed25519"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", "utf-8")
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n", "utf-8")
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key_path)], check=True)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(key_path), "-n", "sovereign-runtime-receipt", str(receipt_path)],
        check=True,
        capture_output=True,
    )
    allowed_signers = directory / "allowed-signers"
    allowed_signers.write_text("sovereign-runtime-receipt " + key_path.with_suffix(".pub").read_text("utf-8"), "utf-8")
    receipt_bytes = receipt_path.read_bytes()
    envelope = {
        "schemaVersion": "sovereign.independent-target-runtime-receipt.v1",
        "scope": scope,
        "receiptSha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "receiptBase64": base64.b64encode(receipt_bytes).decode("ascii"),
        "signature": {
            "format": "sshsig",
            "namespace": "sovereign-runtime-receipt",
            "valueBase64": base64.b64encode(receipt_path.with_suffix(".json.sig").read_bytes()).decode("ascii"),
        },
        "secretValuesReturned": False,
    }
    envelope_path = directory / "envelope.json"
    envelope_path.write_text(json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n", "utf-8")
    return manifest_path, envelope_path, allowed_signers, run_id


def test_runtime_receipt_validator_accepts_real_signed_matching_evidence(tmp_path: Path) -> None:
    manifest, envelope, allowed_signers, run_id = _write_signed_fixture(tmp_path)
    report = tmp_path / "report.json"
    completed = subprocess.run(
        [sys.executable, str(VALIDATOR), str(manifest), str(envelope), str(allowed_signers), str(report), str(run_id)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(report.read_text("utf-8"))["status"] == "VERIFIED"


def test_runtime_receipt_validator_blocks_a_real_signed_receipt_with_wrong_gate_scope(tmp_path: Path) -> None:
    manifest, envelope, allowed_signers, run_id = _write_signed_fixture(tmp_path)
    report = tmp_path / "report.json"
    completed = subprocess.run(
        [sys.executable, str(VALIDATOR), str(manifest), str(envelope), str(allowed_signers), str(report), str(run_id + 1)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert json.loads(report.read_text("utf-8"))["status"] == "BLOCKED_BY_MISSING_OR_CONTRADICTED_EVIDENCE"


def test_runtime_readback_contract_does_not_persist_api_tokens_or_accept_unscoped_timer_runs() -> None:
    reconciler = (ROOT / "deploy/reconcile-main-release.py").read_text("utf-8")
    installer = (ROOT / "deploy/install-on-vps.sh").read_text("utf-8")
    entrypoint = (ROOT / "deploy/run-coordinated-release-readback.py").read_text("utf-8")
    workflow = (REPOSITORY_ROOT / ".github/workflows/sovereign-coordinated-release.yml").read_text("utf-8")
    assert 'GITHUB_TOKEN = os.getenv' not in reconciler
    assert 'SOVEREIGN_RELEASE_GITHUB_TOKEN_FILE' in reconciler
    assert 'WAITING_FOR_CI_RUNTIME_READBACK_SCOPE' in reconciler
    assert 'remove_value "$MANAGED_ENV" GITHUB_TOKEN' in installer
    assert "printf 'GITHUB_TOKEN=%s\\n'" not in installer
    assert 'command="/opt/sovereign-chatgpt-tools/bin/run-coordinated-release-readback",restrict' in installer
    assert 'SOVEREIGN_RELEASE_GITHUB_TOKEN_FILE' in entrypoint
    assert 'actions/create-github-app-token@' in workflow
    assert 'StrictHostKeyChecking=yes' in workflow
    assert 'verify_sovereign_runtime_receipt.py' in workflow
    assert 'Publish verified production deployment verdict' in workflow
