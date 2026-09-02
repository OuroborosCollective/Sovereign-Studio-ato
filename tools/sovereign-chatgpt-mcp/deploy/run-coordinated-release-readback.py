#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
IMAGE_REPOSITORY_RE = re.compile(r"^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+$")
NAMESPACE = "sovereign-runtime-receipt"
TOKEN_DIR = Path("/run/sovereign-release-reconciler")
TOKEN_FILE = TOKEN_DIR / "github-token"
DOCKER_CONFIG_DIR = TOKEN_DIR / "docker-config"
RECEIPT_FILE = TOKEN_DIR / "receipt.json"
ATTESTATION_KEY = Path("/etc/ssh/ssh_host_ed25519_key")
RECONCILER = Path("/opt/sovereign-chatgpt-tools/bin/reconcile-main-release")
STATUS_FILE = Path("/var/lib/sovereign-release-reconciler/status.json")
CONTROL_PLANE_ENV = Path(
    os.getenv(
        "SOVEREIGN_RELEASE_CONTROL_PLANE_ENV_FILE",
        "/opt/sovereign-chatgpt-tools/runtime.env",
    )
)
ALLOWED_BACKEND_ENV_FILES = frozenset(
    {
        Path("/run/secrets/sovereign-backend.env"),
        Path("/opt/sovereign-backend/.env"),
    }
)
REPOSITORY = os.getenv(
    "SOVEREIGN_MCP_REPOSITORY",
    "OuroborosCollective/Sovereign-Studio-ato",
).strip()
BACKEND_IMAGE_REPOSITORY = os.getenv(
    "SOVEREIGN_BACKEND_IMAGE_REPOSITORY",
    "ghcr.io/ouroboroscollective/sovereign-backend",
).strip()


class ReadbackError(RuntimeError):
    pass


def _registry_username() -> str:
    if not REPOSITORY_RE.fullmatch(REPOSITORY):
        raise ReadbackError("repository identity is invalid")
    owner = REPOSITORY.split("/", 1)[0]
    if owner.startswith("-") or len(owner) > 255:
        raise ReadbackError("registry username is invalid")
    return owner


def _validate_registry_username(raw: bytes) -> str:
    try:
        username = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ReadbackError("registry username is invalid") from exc
    if (
        not username
        or len(username) > 255
        or "\n" in username
        or "\r" in username
        or username.startswith("-")
    ):
        raise ReadbackError("registry username is invalid")
    return username


def _read_input() -> tuple[dict[str, Any], str, str]:
    # Wire-compatibility rule: scope + token are the stable mandatory framing.
    # A third registry-username line is optional so the forced command accepts
    # both the legacy two-line client and the current three-line Actions client.
    scope_line = sys.stdin.buffer.readline(4097)
    token_line = sys.stdin.buffer.readline(4097)
    if not scope_line or not token_line:
        raise ReadbackError("input framing is invalid")
    registry_username_line = sys.stdin.buffer.readline(257)
    if sys.stdin.buffer.read(1):
        raise ReadbackError("input framing is invalid")
    try:
        scope = json.loads(scope_line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReadbackError("scope is not valid JSON") from exc
    if not isinstance(scope, dict) or set(scope) != {
        "revision",
        "releaseGateRunId",
        "backendDigest",
        "mcpDigest",
        "manifestEvidenceSha256",
    }:
        raise ReadbackError("scope shape is invalid")
    if not SHA_RE.fullmatch(str(scope["revision"]).lower()):
        raise ReadbackError("scope revision is invalid")
    if not isinstance(scope["releaseGateRunId"], int) or scope["releaseGateRunId"] <= 0:
        raise ReadbackError("scope release gate run id is invalid")
    if not DIGEST_RE.fullmatch(str(scope["backendDigest"]).lower()):
        raise ReadbackError("scope backend digest is invalid")
    if not DIGEST_RE.fullmatch(str(scope["mcpDigest"]).lower()):
        raise ReadbackError("scope MCP digest is invalid")
    if not HEX_64_RE.fullmatch(str(scope["manifestEvidenceSha256"]).lower()):
        raise ReadbackError("scope manifest evidence hash is invalid")
    token = token_line.decode("utf-8").strip()
    if len(token) < 20 or len(token) > 4096 or "\n" in token or "\r" in token:
        raise ReadbackError("ephemeral credential is invalid")
    registry_username = (
        _validate_registry_username(registry_username_line)
        if registry_username_line
        else _registry_username()
    )
    return {
        "revision": str(scope["revision"]).lower(),
        "releaseGateRunId": scope["releaseGateRunId"],
        "backendDigest": str(scope["backendDigest"]).lower(),
        "mcpDigest": str(scope["mcpDigest"]).lower(),
        "manifestEvidenceSha256": str(scope["manifestEvidenceSha256"]).lower(),
    }, token, registry_username


def _assert_root_private(path: Path, *, regular: bool) -> None:
    metadata = path.lstat()
    if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) not in {0o600, 0o700}:
        raise ReadbackError("privileged file metadata is unsafe")
    if regular and not stat.S_ISREG(metadata.st_mode):
        raise ReadbackError("privileged file type is invalid")


def _private_regular_file(path: Path, *, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ReadbackError(f"{label} is unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ReadbackError(f"{label} is not a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ReadbackError(f"{label} mode is unsafe")


def _backend_env_file() -> Path:
    # The installer already owns Backend env discovery and stores only its
    # selected path in the root-managed MCP runtime environment. Keep that
    # source of truth; never copy or serialize Backend secret values here.
    _assert_root_private(CONTROL_PLANE_ENV, regular=True)
    matches: list[str] = []
    try:
        for raw_line in CONTROL_PLANE_ENV.read_text("utf-8").splitlines():
            if raw_line.startswith("SOVEREIGN_BACKEND_ENV_FILE="):
                matches.append(raw_line.split("=", 1)[1].strip())
    except (OSError, UnicodeDecodeError) as exc:
        raise ReadbackError("control-plane environment is unreadable") from exc
    if len(matches) != 1:
        raise ReadbackError("backend env pointer is missing or ambiguous")
    selected = Path(matches[0])
    if selected not in ALLOWED_BACKEND_ENV_FILES:
        raise ReadbackError("backend env pointer is outside the canonical allowlist")
    _private_regular_file(selected, label="backend env file")
    return selected


def _write_token(token: str) -> None:
    TOKEN_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(TOKEN_DIR, 0o700)
    _assert_root_private(TOKEN_DIR, regular=False)
    temporary = TOKEN_FILE.with_suffix(".tmp")
    temporary.write_text(token, encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(TOKEN_FILE)
    _assert_root_private(TOKEN_FILE, regular=True)


def _classify_registry_error(output: str) -> str:
    lowered = output.lower()
    if "unauthorized" in lowered or "authentication required" in lowered:
        return "UNAUTHORIZED"
    if "forbidden" in lowered or "denied" in lowered or "permission_denied" in lowered:
        return "FORBIDDEN"
    if "not found" in lowered or "manifest unknown" in lowered or "name unknown" in lowered:
        return "NOT_FOUND"
    if any(marker in lowered for marker in ("timeout", "connection refused", "temporary failure", "network")):
        return "NETWORK"
    return "OTHER"


def _prepare_registry_auth(token: str, username: str) -> None:
    if DOCKER_CONFIG_DIR.is_symlink():
        raise ReadbackError("registry credential directory is unsafe")
    if DOCKER_CONFIG_DIR.exists():
        if not DOCKER_CONFIG_DIR.is_dir():
            raise ReadbackError("registry credential path is unsafe")
        shutil.rmtree(DOCKER_CONFIG_DIR)
    DOCKER_CONFIG_DIR.mkdir(mode=0o700, parents=True)
    os.chmod(DOCKER_CONFIG_DIR, 0o700)
    _assert_root_private(DOCKER_CONFIG_DIR, regular=False)
    completed = subprocess.run(
        [
            "docker",
            "--config",
            str(DOCKER_CONFIG_DIR),
            "login",
            "ghcr.io",
            "--username",
            username,
            "--password-stdin",
        ],
        input=token + "\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        error_class = _classify_registry_error(completed.stdout + completed.stderr)
        raise ReadbackError(f"registry authentication failed:{error_class}")
    config = DOCKER_CONFIG_DIR / "config.json"
    if not config.is_file() or config.is_symlink():
        raise ReadbackError("registry authentication produced no private Docker config")
    os.chmod(config, 0o600)
    _assert_root_private(config, regular=True)


def _cleanup_registry_auth() -> None:
    if DOCKER_CONFIG_DIR.is_dir() and not DOCKER_CONFIG_DIR.is_symlink():
        subprocess.run(
            ["docker", "--config", str(DOCKER_CONFIG_DIR), "logout", "ghcr.io"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        shutil.rmtree(DOCKER_CONFIG_DIR, ignore_errors=True)


def _assert_root_runtime_status(path: Path) -> None:
    metadata = path.lstat()
    if (
        metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) not in {0o600, 0o640}
        or not stat.S_ISREG(metadata.st_mode)
    ):
        raise ReadbackError("runtime receipt metadata is unsafe")


def _read_status() -> bytes:
    _assert_root_runtime_status(STATUS_FILE)
    receipt = STATUS_FILE.read_bytes()
    if len(receipt) < 32 or len(receipt) > 1_000_000:
        raise ReadbackError("runtime receipt size is invalid")
    try:
        parsed = json.loads(receipt.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReadbackError("runtime receipt is invalid JSON") from exc
    if not isinstance(parsed, dict) or parsed.get("secretValuesReturned") is not False:
        raise ReadbackError("runtime receipt has an unsafe contract")
    return receipt


def _sign(receipt: bytes) -> bytes:
    _assert_root_private(ATTESTATION_KEY, regular=True)
    RECEIPT_FILE.write_bytes(receipt)
    os.chmod(RECEIPT_FILE, 0o600)
    signature_file = RECEIPT_FILE.with_suffix(".json.sig")
    result = subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(ATTESTATION_KEY), "-n", NAMESPACE, str(RECEIPT_FILE)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not signature_file.is_file():
        raise ReadbackError("runtime receipt signing failed")
    signature = signature_file.read_bytes()
    if not signature.startswith(b"-----BEGIN SSH SIGNATURE-----"):
        raise ReadbackError("runtime receipt signature format is invalid")
    return signature


def _emit(scope: dict[str, Any], receipt: bytes, signature: bytes) -> None:
    envelope = {
        "schemaVersion": "sovereign.independent-target-runtime-receipt.v1",
        "scope": scope,
        "receiptSha256": hashlib.sha256(receipt).hexdigest(),
        "receiptBase64": base64.b64encode(receipt).decode("ascii"),
        "signature": {
            "format": "sshsig",
            "namespace": NAMESPACE,
            "valueBase64": base64.b64encode(signature).decode("ascii"),
        },
        "secretValuesReturned": False,
    }
    print(json.dumps(envelope, sort_keys=True, separators=(",", ":")))


def main() -> int:
    if os.geteuid() != 0:
        raise ReadbackError("root execution is required")
    scope: dict[str, Any] | None = None
    try:
        scope, token, registry_username = _read_input()
        if not IMAGE_REPOSITORY_RE.fullmatch(BACKEND_IMAGE_REPOSITORY):
            raise ReadbackError("backend image repository is invalid")
        backend_env_file = _backend_env_file()
        _write_token(token)
        _prepare_registry_auth(token, registry_username)
        environment = os.environ.copy()
        environment.update(
            {
                "SOVEREIGN_RELEASE_GITHUB_TOKEN_FILE": str(TOKEN_FILE),
                "SOVEREIGN_EXPECTED_REVISION": scope["revision"],
                "SOVEREIGN_EXPECTED_RELEASE_GATE_RUN_ID": str(scope["releaseGateRunId"]),
                "SOVEREIGN_EXPECTED_BACKEND_DIGEST": scope["backendDigest"],
                "SOVEREIGN_EXPECTED_MCP_DIGEST": scope["mcpDigest"],
                "SOVEREIGN_EXPECTED_MANIFEST_EVIDENCE_SHA256": scope["manifestEvidenceSha256"],
                "SOVEREIGN_BACKEND_IMAGE_REPOSITORY": BACKEND_IMAGE_REPOSITORY,
                "SOVEREIGN_BACKEND_ENV_FILE": str(backend_env_file),
                "DOCKER_CONFIG": str(DOCKER_CONFIG_DIR),
            }
        )
        completed = subprocess.run(
            [str(RECONCILER)],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        receipt = _read_status()
        signature = _sign(receipt)
        _emit(scope, receipt, signature)
        # SSH is the signed-evidence transport boundary, not the deployment
        # verdict boundary. Once a target-system receipt was read, signed and
        # emitted, transport succeeded even if reconciliation itself failed.
        # The GitHub-side receipt verifier remains authoritative for success.
        return 0
    except ReadbackError as exc:
        print(json.dumps({
            "schemaVersion": "sovereign.independent-target-runtime-receipt-error.v1",
            "ok": False,
            "failureSha256": hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),
            "secretValuesReturned": False,
        }, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 2
    finally:
        _cleanup_registry_auth()
        for path in (TOKEN_FILE, TOKEN_FILE.with_suffix(".tmp"), RECEIPT_FILE, RECEIPT_FILE.with_suffix(".json.sig")):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
