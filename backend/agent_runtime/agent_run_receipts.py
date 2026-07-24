"""Canonical, revision-bound receipts for real Sovereign agent tool calls.

The module contains no UI or telemetry truth. It canonicalizes bounded metadata,
reads the installed MCP identity through the existing host broker, derives a real
Git workspace diff identity, and builds tamper-evident receipt bodies. Raw prompts,
file contents, database rows and secret-shaped fields are never returned.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
import unicodedata
import uuid
from typing import Any, Final, Mapping, Sequence


_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_DIGEST: Final[re.Pattern[str]] = re.compile(r"^sha256:[0-9a-f]{64}$")
_ZERO_SHA256: Final[str] = "0" * 64
_CANONICALIZATION: Final[str] = "utf8-nfc-json-sorted-no-floats-v1"
_SECRET_KEY_MARKERS: Final[tuple[str, ...]] = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "client_secret",
    "cookie",
    "raw_prompt",
    "prompt_text",
    "file_content",
    "database_row",
)
_SECRET_SAFE_BOOLEAN_KEYS: Final[frozenset[str]] = frozenset({
    "secretvaluesreturned",
    "secret_values_returned",
    "rawsecretspersisted",
    "raw_secrets_persisted",
    "mcp_revision_verified",
})
_MAX_BROKER_RESPONSE_BYTES: Final[int] = 1_000_000


class ReceiptContractError(ValueError):
    """A receipt input violated a deterministic or secret-safety invariant."""


class ReceiptIdentityBlocked(RuntimeError):
    """The authoritative MCP or Git identity could not be verified."""

    def __init__(self, failure_family: str, detail: str) -> None:
        super().__init__(detail)
        self.failure_family = failure_family
        self.detail = detail


@dataclass(frozen=True, slots=True)
class McpRuntimeIdentity:
    revision: str
    image_digest: str
    revision_verified: bool
    image_digest_verified: bool
    protocol_ready: bool
    broker_ready: bool


@dataclass(frozen=True, slots=True)
class GitWorkspaceIdentity:
    repository: str
    base_commit_sha: str
    diff_sha256: str
    authoritative_readback_sha256: str
    changed_paths: tuple[str, ...]


def _normalize_string(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def canonical_value(value: Any, *, path: str = "$") -> Any:
    """Return the exact JSON-safe canonical value or fail closed."""

    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ReceiptContractError(f"floating-point value is forbidden at {path}")
    if isinstance(value, str):
        return _normalize_string(value)
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise ReceiptContractError(f"non-string object key is forbidden at {path}")
            key = _normalize_string(raw_key)
            folded = key.casefold()
            if any(marker in folded for marker in _SECRET_KEY_MARKERS):
                if folded not in _SECRET_SAFE_BOOLEAN_KEYS or not isinstance(item, bool):
                    raise ReceiptContractError(f"secret-shaped field is forbidden at {path}.{key}")
            output[key] = canonical_value(item, path=f"{path}.{key}")
        return output
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [canonical_value(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    raise ReceiptContractError(f"unsupported canonical type {type(value).__name__} at {path}")


def canonical_bytes(value: Any) -> bytes:
    normalized = canonical_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _broker_call(action: str, arguments: Mapping[str, Any] | None = None, *, timeout: float = 8.0) -> dict[str, Any]:
    socket_path = Path(
        os.getenv("SOVEREIGN_MCP_BROKER_SOCKET", "/run/sovereign-chatgpt-broker/operator.sock")
    )
    if not socket_path.exists() or not socket_path.is_socket():
        raise ReceiptIdentityBlocked("BROKER_SOCKET_UNAVAILABLE", "authoritative MCP broker socket is unavailable")
    request_id = uuid.uuid4().hex
    payload = json.dumps(
        {"request_id": request_id, "action": action, "arguments": dict(arguments or {})},
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    chunks: list[bytes] = []
    size = 0
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(socket_path))
            client.sendall(payload)
            while True:
                chunk = client.recv(8192)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > _MAX_BROKER_RESPONSE_BYTES:
                    raise ReceiptIdentityBlocked("BROKER_RESPONSE_TOO_LARGE", "authoritative broker response exceeded the bounded limit")
                if b"\n" in chunk:
                    break
    except ReceiptIdentityBlocked:
        raise
    except PermissionError as exc:
        raise ReceiptIdentityBlocked("BROKER_SOCKET_PERMISSION_DENIED", "backend cannot read the authoritative MCP broker socket") from exc
    except socket.timeout as exc:
        raise ReceiptIdentityBlocked("BROKER_RPC_TIMEOUT", "authoritative MCP revision readback timed out") from exc
    except OSError as exc:
        raise ReceiptIdentityBlocked("BROKER_RPC_UNAVAILABLE", f"authoritative MCP revision readback failed: {type(exc).__name__}") from exc
    raw = b"".join(chunks).split(b"\n", 1)[0]
    try:
        response = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptIdentityBlocked("BROKER_RPC_INVALID_RESPONSE", "authoritative MCP broker returned invalid JSON") from exc
    if response.get("request_id") != request_id or not isinstance(response.get("result"), dict):
        raise ReceiptIdentityBlocked("BROKER_RPC_CONTRACT_MISMATCH", "authoritative MCP broker response identity did not match")
    return dict(response["result"])


def read_mcp_runtime_identity(*, expected_revision: str | None = None) -> McpRuntimeIdentity:
    """Read and verify the installed MCP revision and immutable image digest."""

    result = _broker_call("mcp_self_update_status", {})
    revision = str(result.get("revision") or "").strip().lower()
    image_digest = str(result.get("image_digest") or result.get("imageDigest") or "").strip().lower()
    verified = bool(result.get("ok") and result.get("revision_verified") and _SHA40.fullmatch(revision))
    digest_verified = bool(result.get("image_digest_verified") and _IMAGE_DIGEST.fullmatch(image_digest))
    protocol_ready = bool(result.get("mcp_protocol_ready"))
    broker_ready = bool(result.get("broker_rpc_ready"))
    if not verified:
        raise ReceiptIdentityBlocked("MCP_REVISION_UNVERIFIED", "installed MCP revision is not authoritatively verified")
    if not digest_verified:
        raise ReceiptIdentityBlocked("MCP_IMAGE_DIGEST_UNVERIFIED", "installed MCP image digest is not authoritatively verified")
    if not protocol_ready or not broker_ready:
        raise ReceiptIdentityBlocked("MCP_CONTROL_PLANE_NOT_READY", "MCP protocol or broker readback is not ready")
    expected = str(expected_revision or os.getenv("SOVEREIGN_SOURCE_REVISION", "")).strip().lower()
    if expected:
        if not _SHA40.fullmatch(expected):
            raise ReceiptIdentityBlocked("EXPECTED_REVISION_INVALID", "configured backend source revision is not a full Git SHA")
        if revision != expected:
            raise ReceiptIdentityBlocked("MCP_RUNTIME_REVISION_MISMATCH", "installed MCP revision differs from the backend source revision")
    return McpRuntimeIdentity(
        revision=revision,
        image_digest=image_digest,
        revision_verified=True,
        image_digest_verified=True,
        protocol_ready=True,
        broker_ready=True,
    )


def _git_bytes(workspace_root: Path, *args: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", "-C", str(workspace_root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReceiptIdentityBlocked("GIT_READBACK_FAILED", f"authoritative Git readback failed for {' '.join(args)}") from exc
    return completed.stdout


def read_git_workspace_identity(workspace_root: Path, *, repository: str) -> GitWorkspaceIdentity:
    """Hash real HEAD, staged/unstaged diffs, status and untracked file identities."""

    root = workspace_root.resolve()
    base_commit_sha = _git_bytes(root, "rev-parse", "HEAD").decode("ascii", "strict").strip().lower()
    if not _SHA40.fullmatch(base_commit_sha):
        raise ReceiptIdentityBlocked("GIT_HEAD_UNVERIFIED", "workspace HEAD is not a full Git SHA")
    status = _git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    unstaged = _git_bytes(root, "diff", "--no-ext-diff", "--binary", "--full-index")
    staged = _git_bytes(root, "diff", "--cached", "--no-ext-diff", "--binary", "--full-index")
    changed_paths: list[str] = []
    untracked: list[dict[str, Any]] = []
    entries = [entry for entry in status.split(b"\0") if entry]
    for entry in entries:
        decoded = entry.decode("utf-8", "surrogateescape")
        path_text = decoded[3:] if len(decoded) >= 3 else ""
        if not path_text:
            continue
        path = PurePosixPath(path_text.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or ".git" in path.parts:
            raise ReceiptIdentityBlocked("GIT_STATUS_PATH_UNSAFE", "Git status returned an unsafe path")
        normalized_path = path.as_posix()
        changed_paths.append(normalized_path)
        if decoded.startswith("?? "):
            candidate = (root / normalized_path).resolve()
            try:
                candidate.relative_to(root)
            except ValueError as exc:
                raise ReceiptIdentityBlocked("GIT_UNTRACKED_PATH_ESCAPE", "untracked path escaped the workspace") from exc
            if candidate.is_file() and not candidate.is_symlink():
                data = candidate.read_bytes()
                untracked.append({
                    "path": normalized_path,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                })
    diff_identity_payload = {
        "status_sha256": hashlib.sha256(status).hexdigest(),
        "unstaged_diff_sha256": hashlib.sha256(unstaged).hexdigest(),
        "staged_diff_sha256": hashlib.sha256(staged).hexdigest(),
        "untracked": sorted(untracked, key=lambda item: item["path"]),
    }
    diff_sha256 = canonical_sha256(diff_identity_payload)
    readback_sha256 = canonical_sha256({
        "base_commit_sha": base_commit_sha,
        "changed_paths": sorted(set(changed_paths)),
        "diff_sha256": diff_sha256,
        "repository": _normalize_string(str(repository or "").strip()),
    })
    return GitWorkspaceIdentity(
        repository=_normalize_string(str(repository or "").strip()),
        base_commit_sha=base_commit_sha,
        diff_sha256=diff_sha256,
        authoritative_readback_sha256=readback_sha256,
        changed_paths=tuple(sorted(set(changed_paths))),
    )


def build_agent_run_receipt(
    *,
    sequence: int,
    repository: str,
    base_commit_sha: str,
    mcp_revision: str,
    mcp_image_digest: str,
    mcp_revision_verified: bool,
    agent_run_id: str,
    tool_name: str,
    call_id: str,
    operation_identity: str,
    input_sha256: str,
    output_sha256: str,
    diff_sha256: str,
    test_evidence_sha256: str,
    evidence_gate_result: str,
    mutation_performed: bool,
    observed_effect: str,
    authoritative_readback_sha256: str,
    previous_receipt_sha256: str,
) -> dict[str, Any]:
    """Build one canonical receipt. Timestamp observations remain outside the hash."""

    gate = str(evidence_gate_result or "").strip().upper()
    if gate not in {"PASS", "FAIL", "BLOCKED"}:
        raise ReceiptContractError("unsupported evidence gate result")
    effect = str(observed_effect or "").strip().lower()
    if effect not in {"read", "workspace-write", "external-write", "none"}:
        raise ReceiptContractError("unsupported observed effect")
    previous = str(previous_receipt_sha256 or "").strip().lower() or _ZERO_SHA256
    digests = {
        "input_sha256": input_sha256,
        "output_sha256": output_sha256,
        "diff_sha256": diff_sha256,
        "test_evidence_sha256": test_evidence_sha256,
        "authoritative_readback_sha256": authoritative_readback_sha256,
        "previous_receipt_sha256": previous,
    }
    for label, digest in digests.items():
        if not _SHA64.fullmatch(str(digest or "").strip().lower()):
            raise ReceiptContractError(f"{label} must be a lowercase SHA-256")
    base_sha = str(base_commit_sha or "").strip().lower()
    mcp_sha = str(mcp_revision or "").strip().lower()
    image_digest = str(mcp_image_digest or "").strip().lower()
    if gate == "PASS":
        if not _SHA40.fullmatch(base_sha):
            raise ReceiptContractError("positive receipt requires an exact repository base commit")
        if not mcp_revision_verified or not _SHA40.fullmatch(mcp_sha):
            raise ReceiptContractError("positive receipt requires a verified installed MCP revision")
        if not _IMAGE_DIGEST.fullmatch(image_digest):
            raise ReceiptContractError("positive receipt requires a verified immutable MCP image digest")
        if mutation_performed and effect not in {"workspace-write", "external-write"}:
            raise ReceiptContractError("positive mutation receipt requires an observed write effect")
    body: dict[str, Any] = {
        "schema_version": "sovereign.agent-run-receipt.v1",
        "sequence": int(sequence),
        "repository": _normalize_string(str(repository or "").strip()),
        "base_commit_sha": base_sha,
        "mcp_revision": mcp_sha,
        "mcp_image_digest": image_digest,
        "mcp_revision_verified": bool(mcp_revision_verified),
        "agent_run_id": _normalize_string(str(agent_run_id or "").strip()),
        "tool_name": _normalize_string(str(tool_name or "").strip()),
        "call_id": _normalize_string(str(call_id or "").strip()),
        "operation_identity": _normalize_string(str(operation_identity or "").strip()),
        "input_sha256": str(input_sha256).lower(),
        "output_sha256": str(output_sha256).lower(),
        "diff_sha256": str(diff_sha256).lower(),
        "test_evidence_sha256": str(test_evidence_sha256).lower(),
        "evidence_gate_result": gate,
        "mutation_performed": bool(mutation_performed),
        "observed_effect": effect,
        "authoritative_readback_sha256": str(authoritative_readback_sha256).lower(),
        "previous_receipt_sha256": previous,
    }
    if sequence < 0:
        raise ReceiptContractError("receipt sequence must be non-negative")
    if sequence == 0 and previous != _ZERO_SHA256:
        raise ReceiptContractError("sequence zero requires the genesis anchor")
    if sequence > 0 and previous == _ZERO_SHA256:
        raise ReceiptContractError("non-genesis receipt requires the previous receipt hash")
    receipt_sha256 = canonical_sha256(body)
    return {
        "header": {
            "algorithm": "sha256",
            "canonicalization": _CANONICALIZATION,
            "hash": receipt_sha256,
        },
        "body": {**body, "receipt_sha256": receipt_sha256},
    }


def verify_agent_run_receipt_chain(
    receipts: Sequence[Mapping[str, Any]],
    *,
    expected_repository: str = "",
    expected_base_commit_sha: str = "",
    expected_mcp_revision: str = "",
    expected_start_sequence: int = 0,
    anchor_previous_receipt_sha256: str = _ZERO_SHA256,
) -> dict[str, Any]:
    """Verify every causal field through the canonical body hash and chain links."""

    if not receipts:
        raise ReceiptContractError("at least one receipt is required")
    findings: list[dict[str, Any]] = []
    previous = str(anchor_previous_receipt_sha256).strip().lower()
    for index, receipt in enumerate(receipts):
        header = dict(receipt.get("header") or {})
        body = dict(receipt.get("body") or {})
        stored_hash = str(header.get("hash") or "").strip().lower()
        body_hash = str(body.pop("receipt_sha256", "") or "").strip().lower()
        computed = canonical_sha256(body)
        expected_sequence = expected_start_sequence + index
        if body.get("sequence") != expected_sequence:
            findings.append({"index": index, "family": "SEQUENCE_MISMATCH"})
        if body.get("previous_receipt_sha256") != previous:
            findings.append({"index": index, "family": "PREVIOUS_HASH_MISMATCH"})
        if stored_hash != computed or body_hash != computed:
            findings.append({"index": index, "family": "RECEIPT_HASH_MISMATCH"})
        if expected_repository and body.get("repository") != expected_repository:
            findings.append({"index": index, "family": "REPOSITORY_MISMATCH"})
        if expected_base_commit_sha and body.get("base_commit_sha") != expected_base_commit_sha:
            findings.append({"index": index, "family": "BASE_REVISION_MISMATCH"})
        if expected_mcp_revision and body.get("mcp_revision") != expected_mcp_revision:
            findings.append({"index": index, "family": "MCP_REVISION_MISMATCH"})
        previous = stored_hash
    return {
        "ok": not findings,
        "verified_count": len(receipts) - len({item["index"] for item in findings}),
        "receipt_count": len(receipts),
        "chain_head_sha256": previous,
        "findings": findings,
    }
