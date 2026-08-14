#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
IMAGE_REPOSITORY_RE = re.compile(r"^ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+$")

REPOSITORY = os.getenv(
    "SOVEREIGN_MCP_REPOSITORY",
    "OuroborosCollective/Sovereign-Studio-ato",
).strip()
GITHUB_TOKEN_FILE_VALUE = os.getenv("SOVEREIGN_RELEASE_GITHUB_TOKEN_FILE", "").strip()
GITHUB_TOKEN_FILE = Path(GITHUB_TOKEN_FILE_VALUE) if GITHUB_TOKEN_FILE_VALUE else None
EXPECTED_REVISION = os.getenv("SOVEREIGN_EXPECTED_REVISION", "").strip().lower()
EXPECTED_RELEASE_GATE_RUN_ID = os.getenv("SOVEREIGN_EXPECTED_RELEASE_GATE_RUN_ID", "").strip()
EXPECTED_BACKEND_DIGEST = os.getenv("SOVEREIGN_EXPECTED_BACKEND_DIGEST", "").strip().lower()
EXPECTED_MCP_DIGEST = os.getenv("SOVEREIGN_EXPECTED_MCP_DIGEST", "").strip().lower()
EXPECTED_MANIFEST_EVIDENCE_SHA256 = os.getenv("SOVEREIGN_EXPECTED_MANIFEST_EVIDENCE_SHA256", "").strip().lower()
BACKEND_REPOSITORY = os.getenv(
    "SOVEREIGN_BACKEND_IMAGE_REPOSITORY",
    "ghcr.io/ouroboroscollective/sovereign-backend",
).strip()
MCP_REPOSITORY = os.getenv(
    "SOVEREIGN_MCP_IMAGE_REPOSITORY",
    "ghcr.io/ouroboroscollective/sovereign-chatgpt-mcp",
).strip()
WORKFLOW = os.getenv(
    "SOVEREIGN_COORDINATED_RELEASE_WORKFLOW",
    "sovereign-coordinated-release.yml",
).strip()
STATE_DIR = Path(
    os.getenv(
        "SOVEREIGN_RELEASE_RECONCILER_STATE_DIR",
        "/var/lib/sovereign-release-reconciler",
    )
)
STATUS_FILE = STATE_DIR / "status.json"
LOCK_FILE = STATE_DIR / "reconcile.lock"
BACKEND_DEPLOY = os.getenv(
    "SOVEREIGN_MCP_DEPLOY_SCRIPT",
    "/opt/sovereign-chatgpt-tools/bin/deploy-sovereign-backend",
)
BACKEND_ROLLBACK = os.getenv(
    "SOVEREIGN_MCP_ROLLBACK_SCRIPT",
    "/opt/sovereign-chatgpt-tools/bin/rollback-sovereign-backend",
)
MCP_INSTALLER = os.getenv(
    "SOVEREIGN_MCP_INSTALLER",
    "/opt/sovereign-operator-source/tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh",
)
OPERATOR_SOURCE = Path(
    os.getenv("SOVEREIGN_MCP_SOURCE_DIR", "/opt/sovereign-operator-source")
)
OPERATOR_SOURCE_CHECKOUTS = Path(
    os.getenv(
        "SOVEREIGN_MCP_SOURCE_CHECKOUTS_DIR",
        "/var/lib/sovereign-release-reconciler/operator-source-checkouts",
    )
)
BROKER_SOCKET = Path(
    os.getenv(
        "SOVEREIGN_MCP_BROKER_SOCKET",
        "/run/sovereign-chatgpt-broker/operator.sock",
    )
)
# The installer owns Backend env discovery and persists only the selected
# path as SOVEREIGN_BACKEND_ENV_FILE in the root-managed control-plane env.
# Resolve that pointer here; never copy or serialize Backend secret values.
CONTROL_PLANE_ENV = Path(
    os.getenv(
        "SOVEREIGN_RELEASE_CONTROL_PLANE_ENV_FILE",
        "/opt/sovereign-chatgpt-tools/runtime.env",
    )
)
BACKEND_MANAGED_ENV_FILE = Path(
    os.getenv(
        "SOVEREIGN_BACKEND_MANAGED_ENV_FILE",
        "/opt/sovereign-chatgpt-tools/backend-runtime.env",
    )
)
ALLOWED_BACKEND_ENV_FILES = frozenset(
    {
        Path("/run/secrets/sovereign-backend.env"),
        Path("/opt/sovereign-backend/.env"),
    }
)


class ReconcileError(RuntimeError):
    def __init__(self, stage: str, detail: str) -> None:
        super().__init__(detail)
        self.stage = stage
        self.detail = detail[:1000]


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_status(status: str, *, ok: bool, revision: str = "", **evidence: Any) -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o750)
    payload: dict[str, Any] = {
        "schemaVersion": "sovereign.coordinated-release-reconciler-status.v1",
        "ok": bool(ok),
        "status": status,
        "revision": revision,
        "updatedAtEpoch": int(time.time()),
        "secretValuesReturned": False,
        **evidence,
    }
    evidence_payload = {key: value for key, value in payload.items() if key != "evidenceSha256"}
    payload["evidenceSha256"] = _canonical_sha256(evidence_payload)
    temporary = STATUS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", "utf-8")
    os.chmod(temporary, 0o640)
    temporary.replace(STATUS_FILE)
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return payload


def _github_token() -> str:
    if GITHUB_TOKEN_FILE is None:
        raise ReconcileError("github_auth", "ephemeral token file is not configured")
    try:
        metadata = GITHUB_TOKEN_FILE.lstat()
    except OSError as exc:
        raise ReconcileError("github_auth", "ephemeral token file is unreadable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size < 20
        or metadata.st_size > 4096
    ):
        raise ReconcileError("github_auth", "ephemeral token file metadata is invalid")
    try:
        token = GITHUB_TOKEN_FILE.read_text("utf-8").strip()
    except OSError as exc:
        raise ReconcileError("github_auth", "ephemeral token file read failed") from exc
    if not token or "\n" in token or "\r" in token:
        raise ReconcileError("github_auth", "ephemeral token value is invalid")
    return token


def _assert_root_private(path: Path, *, regular: bool) -> None:
    metadata = path.lstat()
    if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) not in {0o600, 0o700}:
        raise ReconcileError("backend_env", "privileged file metadata is unsafe")
    if regular and not stat.S_ISREG(metadata.st_mode):
        raise ReconcileError("backend_env", "privileged file type is invalid")


def _private_regular_file(path: Path, *, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ReconcileError("backend_env", f"{label} is unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ReconcileError("backend_env", f"{label} is not a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ReconcileError("backend_env", f"{label} mode is unsafe")


def _backend_env_file() -> Path:
    # Resolve only the installer-selected Backend base env *path* from the
    # root-managed control-plane env. Reject symlinks, arbitrary/relative
    # pointers and anything outside the sanctioned allowlist. Never read or
    # return the secret contents of the selected file.
    _assert_root_private(CONTROL_PLANE_ENV, regular=True)
    matches: list[str] = []
    try:
        for raw_line in CONTROL_PLANE_ENV.read_text("utf-8").splitlines():
            if raw_line.startswith("SOVEREIGN_BACKEND_ENV_FILE="):
                matches.append(raw_line.split("=", 1)[1].strip())
    except (OSError, UnicodeDecodeError) as exc:
        raise ReconcileError("backend_env", "control-plane env is unreadable") from exc
    if len(matches) != 1:
        raise ReconcileError("backend_env", "backend env pointer is missing or ambiguous")
    selected = Path(matches[0])
    if selected not in ALLOWED_BACKEND_ENV_FILES:
        raise ReconcileError("backend_env", "backend env pointer is outside the canonical allowlist")
    _private_regular_file(selected, label="backend env file")
    return selected


def _backend_deploy_environment() -> dict[str, str]:
    # Export only the resolved Backend env *path* plus the canonical Backend
    # image repository and the shared managed env file pointer into the
    # ephemeral deploy/rollback subprocess environment. Do not copy the
    # ambient reconciler environment or any secret values.
    backend_env_file = _backend_env_file()
    environment: dict[str, str] = {
        "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
        "SOVEREIGN_BACKEND_ENV_FILE": str(backend_env_file),
        "SOVEREIGN_BACKEND_MANAGED_ENV_FILE": str(BACKEND_MANAGED_ENV_FILE),
        "SOVEREIGN_BACKEND_IMAGE_REPOSITORY": BACKEND_REPOSITORY,
    }
    return environment


def _expected_scope() -> dict[str, Any]:
    if not SHA_RE.fullmatch(EXPECTED_REVISION):
        raise ReconcileError("scope", "expected revision is invalid")
    if not EXPECTED_RELEASE_GATE_RUN_ID.isdigit() or int(EXPECTED_RELEASE_GATE_RUN_ID) <= 0:
        raise ReconcileError("scope", "expected release gate run id is invalid")
    if not DIGEST_RE.fullmatch(EXPECTED_BACKEND_DIGEST):
        raise ReconcileError("scope", "expected backend digest is invalid")
    if not DIGEST_RE.fullmatch(EXPECTED_MCP_DIGEST):
        raise ReconcileError("scope", "expected MCP digest is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", EXPECTED_MANIFEST_EVIDENCE_SHA256):
        raise ReconcileError("scope", "expected manifest evidence hash is invalid")
    return {
        "revision": EXPECTED_REVISION,
        "releaseGateRunId": int(EXPECTED_RELEASE_GATE_RUN_ID),
        "backendDigest": EXPECTED_BACKEND_DIGEST,
        "mcpDigest": EXPECTED_MCP_DIGEST,
        "manifestEvidenceSha256": EXPECTED_MANIFEST_EVIDENCE_SHA256,
    }


def _github_json(path: str) -> Any:
    token = _github_token()
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "sovereign-coordinated-release-reconciler",
            "X-GitHub-Api-Version": "2026-03-10",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise ReconcileError("github_api", f"GitHub API returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ReconcileError("github_api", type(exc).__name__) from exc


def _main_revision() -> str:
    payload = _github_json(f"/repos/{REPOSITORY}/git/ref/heads/main")
    revision = str(((payload.get("object") or {}) if isinstance(payload, dict) else {}).get("sha") or "").lower()
    if not SHA_RE.fullmatch(revision):
        raise ReconcileError("main_revision", "GitHub returned no full main revision")
    return revision


def _release_gate(revision: str, *, expected_runtime_readback_run_id: int | None = None) -> dict[str, Any]:
    workflow = urllib.parse.quote(WORKFLOW, safe="")
    payload = _github_json(
        f"/repos/{REPOSITORY}/actions/workflows/{workflow}/runs"
        f"?branch=main&event=push&per_page=50"
    )
    runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
    exact = [
        item
        for item in runs
        if isinstance(item, dict) and str(item.get("head_sha") or "").lower() == revision
    ]
    exact.sort(key=lambda item: (int(item.get("run_attempt") or 0), int(item.get("id") or 0)), reverse=True)
    if not exact:
        return {"ready": False, "status": "WAITING_FOR_RELEASE_GATE", "runId": None}
    run = exact[0]
    run_status = str(run.get("status") or "")
    conclusion = str(run.get("conclusion") or "")
    evidence = {
        "runId": int(run.get("id") or 0),
        "runAttempt": int(run.get("run_attempt") or 0),
        "runStatus": run_status,
        "conclusion": conclusion or None,
        "url": str(run.get("html_url") or ""),
        "headSha": str(run.get("head_sha") or "").lower(),
    }
    if run_status != "completed":
        if expected_runtime_readback_run_id is not None and evidence["runId"] == expected_runtime_readback_run_id:
            return {
                "ready": True,
                "status": "RELEASE_GATE_SELF_RUNTIME_READBACK_ACTIVE",
                "selfRuntimeReadback": True,
                **evidence,
            }
        return {"ready": False, "status": "WAITING_FOR_RELEASE_GATE", **evidence}
    if conclusion != "success":
        return {"ready": False, "status": "RELEASE_GATE_FAILED", **evidence}
    return {"ready": True, "status": "RELEASE_GATE_VERIFIED", **evidence}


def _run(
    argv: list[str], *, timeout: int, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=environment if environment is not None else os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        raise ReconcileError("host_command", f"timeout:{Path(argv[0]).name}") from exc


def _refresh_operator_source(scope: dict[str, Any]) -> dict[str, Any]:
    git_directory = OPERATOR_SOURCE / ".git"
    if not git_directory.is_dir() or git_directory.is_symlink():
        raise ReconcileError("operator_source", "operator source repository is unavailable")
    token = _github_token()
    with tempfile.TemporaryDirectory(prefix="sovereign-git-askpass-") as directory:
        askpass = Path(directory) / "askpass.sh"
        askpass.write_text(
            "#!/bin/sh\ncase \"$1\" in *Username*) printf %s x-access-token ;; *Password*) printf %s \"$GITHUB_TOKEN\" ;; esac\n",
            encoding="utf-8",
        )
        os.chmod(askpass, 0o700)
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_ASKPASS": str(askpass),
                "GIT_TERMINAL_PROMPT": "0",
                "GITHUB_TOKEN": token,
            }
        )
        fetch = _run(
            ["git", "-C", str(OPERATOR_SOURCE), "fetch", "--no-tags", "origin", "main"],
            timeout=600,
            environment=environment,
        )
    combined = fetch.stdout + fetch.stderr
    output_sha = hashlib.sha256(combined.encode("utf-8", errors="replace")).hexdigest()
    if fetch.returncode != 0:
        raise ReconcileError("operator_source", f"fetch-failed;outputSha256={output_sha}")
    remote = _run(
        ["git", "-C", str(OPERATOR_SOURCE), "rev-parse", "origin/main"], timeout=60
    )
    remote_revision = remote.stdout.strip().lower()
    if remote.returncode != 0 or remote_revision != scope["revision"]:
        raise ReconcileError("operator_source", "origin/main differs from CI scope revision")

    revision = str(scope["revision"])
    checkout = OPERATOR_SOURCE_CHECKOUTS / revision
    OPERATOR_SOURCE_CHECKOUTS.mkdir(parents=True, exist_ok=True)
    os.chmod(OPERATOR_SOURCE_CHECKOUTS, 0o700)
    if checkout.exists():
        checkout_git = checkout / ".git"
        if not checkout_git.exists() or checkout_git.is_symlink():
            raise ReconcileError("operator_source", "scoped operator worktree is invalid")
        status = _run(["git", "-C", str(checkout), "status", "--porcelain"], timeout=60)
        if status.returncode != 0 or status.stdout.strip():
            raise ReconcileError("operator_source", "scoped operator worktree is not clean")
    else:
        created = _run(
            ["git", "-C", str(OPERATOR_SOURCE), "worktree", "add", "--detach", str(checkout), revision],
            timeout=180,
        )
        if created.returncode != 0:
            raise ReconcileError("operator_source", "scoped operator worktree creation failed")
    head = _run(["git", "-C", str(checkout), "rev-parse", "HEAD"], timeout=60)
    checked_out_revision = head.stdout.strip().lower()
    if head.returncode != 0 or checked_out_revision != revision:
        raise ReconcileError("operator_source", "scoped operator worktree revision differs from CI scope")
    installer = checkout / "tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh"
    if not installer.is_file() or installer.is_symlink():
        raise ReconcileError("operator_source", "scoped operator installer is unavailable")
    return {
        "path": str(checkout),
        "installer": str(installer),
        "revision": checked_out_revision,
        "fetchOutputSha256": output_sha,
    }


def _image_evidence(repository: str, revision: str) -> dict[str, str]:
    if not IMAGE_REPOSITORY_RE.fullmatch(repository):
        raise ReconcileError("image_contract", "image repository is invalid")
    tag = f"{repository}:{revision}"
    pull = _run(["docker", "pull", tag], timeout=600)
    if pull.returncode != 0:
        raise ReconcileError(
            "image_pull",
            f"{repository}:sha256={hashlib.sha256((pull.stdout + pull.stderr).encode()).hexdigest()}",
        )
    inspect = _run(["docker", "image", "inspect", tag], timeout=60)
    if inspect.returncode != 0:
        raise ReconcileError("image_inspect", repository)
    try:
        rows = json.loads(inspect.stdout)
        image = rows[0]
    except (json.JSONDecodeError, IndexError, TypeError) as exc:
        raise ReconcileError("image_inspect", "invalid Docker image metadata") from exc
    labels = ((image.get("Config") or {}).get("Labels") or {}) if isinstance(image, dict) else {}
    image_revision = str(labels.get("org.opencontainers.image.revision") or "").lower()
    if image_revision != revision:
        raise ReconcileError("image_revision", f"{repository}:revision-label-mismatch")
    prefix = repository + "@"
    immutable = next(
        (
            value
            for value in (image.get("RepoDigests") or [])
            if isinstance(value, str) and value.startswith(prefix)
        ),
        "",
    )
    digest = immutable.split("@", 1)[1] if "@" in immutable else ""
    if not DIGEST_RE.fullmatch(digest):
        raise ReconcileError("image_digest", f"{repository}:immutable-digest-missing")
    return {
        "repository": repository,
        "tag": tag,
        "immutableReference": immutable,
        "digest": digest,
        "revision": image_revision,
        "imageId": str(image.get("Id") or ""),
    }


def _container_identity(container: str, repository: str) -> dict[str, Any]:
    inspect = _run(["docker", "inspect", container], timeout=30)
    if inspect.returncode != 0:
        return {"present": False, "container": container}
    try:
        row = json.loads(inspect.stdout)[0]
    except (json.JSONDecodeError, IndexError, TypeError):
        return {"present": True, "container": container, "valid": False}
    image_id = str(row.get("Image") or "")
    image_inspect = _run(["docker", "image", "inspect", image_id], timeout=30)
    if image_inspect.returncode != 0:
        return {"present": True, "container": container, "valid": False}
    try:
        image = json.loads(image_inspect.stdout)[0]
    except (json.JSONDecodeError, IndexError, TypeError):
        return {"present": True, "container": container, "valid": False}
    labels = ((image.get("Config") or {}).get("Labels") or {}) if isinstance(image, dict) else {}
    prefix = repository + "@"
    immutable = next(
        (
            value
            for value in (image.get("RepoDigests") or [])
            if isinstance(value, str) and value.startswith(prefix)
        ),
        "",
    )
    state = row.get("State") if isinstance(row.get("State"), dict) else {}
    health = state.get("Health") if isinstance(state.get("Health"), dict) else {}
    return {
        "present": True,
        "valid": bool(immutable),
        "container": container,
        "running": bool(state.get("Running")),
        "health": str(health.get("Status") or "no-health"),
        "restartCount": int(row.get("RestartCount") or 0),
        "revision": str(labels.get("org.opencontainers.image.revision") or "").lower(),
        "immutableReference": immutable,
        "digest": immutable.split("@", 1)[1] if "@" in immutable else "",
        "imageId": image_id,
    }


def _command_json(
    argv: list[str], *, timeout: int, stage: str, environment: dict[str, str] | None = None
) -> dict[str, Any]:
    completed = _run(argv, timeout=timeout, environment=environment)
    combined = completed.stdout + completed.stderr
    output_sha = hashlib.sha256(combined.encode("utf-8", errors="replace")).hexdigest()
    if completed.returncode != 0:
        raise ReconcileError(stage, f"exit={completed.returncode};outputSha256={output_sha}")
    parsed: dict[str, Any] | None = None
    for line in reversed(completed.stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            parsed = candidate
            break
    if parsed is None or parsed.get("ok") is not True:
        raise ReconcileError(stage, f"missing-success-receipt;outputSha256={output_sha}")
    return {"receipt": parsed, "outputSha256": output_sha}


def _broker_call(action: str, arguments: dict[str, Any], *, timeout: int = 30) -> dict[str, Any]:
    request_id = hashlib.sha256(f"{action}:{time.time_ns()}".encode()).hexdigest()[:24]
    payload = json.dumps(
        {"request_id": request_id, "action": action, "arguments": arguments},
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    if not BROKER_SOCKET.is_socket():
        raise ReconcileError("broker", "broker socket is missing")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(BROKER_SOCKET))
        client.sendall(payload)
        chunks = bytearray()
        while b"\n" not in chunks and len(chunks) < 1_000_000:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.extend(chunk)
    try:
        response = json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReconcileError("broker", "invalid broker response") from exc
    result = response.get("result") if isinstance(response, dict) else None
    if not isinstance(result, dict):
        raise ReconcileError("broker", "broker returned no result")
    return result


def _deploy_mcp_from_ci_scope(
    revision: str, mcp: dict[str, str], operator_source: dict[str, Any]
) -> dict[str, Any]:
    if str(operator_source.get("revision") or "").lower() != revision:
        raise ReconcileError("operator_source", "installer source revision is not CI-scoped")
    installer = Path(str(operator_source.get("installer") or ""))
    expected_installer = Path(str(operator_source.get("path") or "")) / "tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh"
    if installer != expected_installer or not installer.is_file() or installer.is_symlink():
        raise ReconcileError("operator_source", "installer path is not CI-scoped")
    environment = os.environ.copy()
    environment.update(
        {
            "SOVEREIGN_MCP_EXPECTED_REVISION": revision,
            "SOVEREIGN_MCP_EXPECTED_DIGEST": mcp["digest"],
        }
    )
    result = _command_json(
        [str(installer)],
        timeout=1800,
        stage="mcp_deploy",
        environment=environment,
    )
    receipt = result["receipt"]
    expected_reference = f"{MCP_REPOSITORY}@{mcp['digest']}"
    if (
        str(receipt.get("mcp_revision") or "").lower() != revision
        or str(receipt.get("mcp_image") or "") != expected_reference
        or receipt.get("host_command_worker_active") is not True
        or receipt.get("broker") != "active"
        or receipt.get("broker_rpc_ready") is not True
        or receipt.get("broker_socket_host_visible") is not True
        or receipt.get("broker_socket_container_visible") is not True
        or receipt.get("mcp_protocol_ready") is not True
        or receipt.get("self_update_available") is not False
        or receipt.get("pr_lifecycle_available") is not False
        or receipt.get("workflow_dispatch_available") is not False
    ):
        raise ReconcileError("mcp_deploy", "installer receipt violates CI scope or capability truth")
    return {
        "status": "DEPLOYED",
        "revision": revision,
        "digest": mcp["digest"],
        "operatorSource": operator_source,
        **result,
    }


def _runtime_readback(revision: str, backend: dict[str, str], mcp: dict[str, str]) -> dict[str, Any]:
    backend_runtime = _container_identity("sovereign-backend", BACKEND_REPOSITORY)
    mcp_runtime = _container_identity("sovereign-chatgpt-mcp", MCP_REPOSITORY)
    if not (
        backend_runtime.get("running") is True
        and backend_runtime.get("revision") == revision
        and backend_runtime.get("digest") == backend["digest"]
    ):
        raise ReconcileError("runtime_readback", "backend revision or digest parity failed")
    if not (
        mcp_runtime.get("running") is True
        and mcp_runtime.get("health") == "healthy"
        and mcp_runtime.get("revision") == revision
        and mcp_runtime.get("digest") == mcp["digest"]
    ):
        raise ReconcileError("runtime_readback", "MCP revision, digest or health parity failed")
    broker = _broker_call("broker_health", {})
    if broker.get("status") != "BROKER_READY":
        raise ReconcileError("runtime_readback", "broker is not ready")
    patchmon = _broker_call(
        "patchmon_runtime_inventory",
        {"include_fleet": True, "max_fleet_containers": 100},
        timeout=90,
    )
    if patchmon.get("ok") is not True:
        raise ReconcileError("runtime_readback", "PatchMon inventory is not verified")
    return {
        "backend": backend_runtime,
        "mcp": mcp_runtime,
        "broker": {
            "status": broker.get("status"),
            "pid": broker.get("pid"),
        },
        "patchmon": {
            "status": patchmon.get("status"),
            "evidenceSha256": _canonical_sha256(patchmon),
        },
    }


def _assert_expected_scope(
    scope: dict[str, Any],
    revision: str,
    gate: dict[str, Any],
    backend: dict[str, str] | None = None,
    mcp: dict[str, str] | None = None,
) -> None:
    if revision != scope["revision"]:
        raise ReconcileError("scope", "authoritative main revision differs from expected revision")
    if gate.get("ready") is not True or int(gate.get("runId") or 0) != scope["releaseGateRunId"]:
        raise ReconcileError("scope", "release gate differs from expected gate")
    if backend is not None and backend.get("digest") != scope["backendDigest"]:
        raise ReconcileError("scope", "backend digest differs from expected manifest digest")
    if mcp is not None and mcp.get("digest") != scope["mcpDigest"]:
        raise ReconcileError("scope", "MCP digest differs from expected manifest digest")


def reconcile() -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", REPOSITORY):
        raise ReconcileError("configuration", "repository is invalid")
    for repository in (BACKEND_REPOSITORY, MCP_REPOSITORY):
        if not IMAGE_REPOSITORY_RE.fullmatch(repository):
            raise ReconcileError("configuration", "image repository is invalid")

    scope = _expected_scope()
    revision = _main_revision()
    gate = _release_gate(
        revision,
        expected_runtime_readback_run_id=scope["releaseGateRunId"],
    )
    if not gate.get("ready"):
        return _write_status(
            str(gate.get("status") or "WAITING_FOR_RELEASE_GATE"),
            ok=False,
            revision=revision,
            releaseGate=gate,
            mutationPerformed=False,
            retryable=True,
        )

    _assert_expected_scope(scope, revision, gate)
    operator_source = _refresh_operator_source(scope)
    backend_image = _image_evidence(BACKEND_REPOSITORY, revision)
    mcp_image = _image_evidence(MCP_REPOSITORY, revision)
    _assert_expected_scope(scope, revision, gate, backend_image, mcp_image)
    previous_backend = _container_identity("sovereign-backend", BACKEND_REPOSITORY)
    current_mcp = _container_identity("sovereign-chatgpt-mcp", MCP_REPOSITORY)
    backend_changed = not (
        previous_backend.get("running") is True
        and previous_backend.get("revision") == revision
        and previous_backend.get("digest") == backend_image["digest"]
    )
    mcp_changed = not (
        current_mcp.get("running") is True
        and current_mcp.get("health") == "healthy"
        and current_mcp.get("revision") == revision
        and current_mcp.get("digest") == mcp_image["digest"]
    )

    backend_deploy: dict[str, Any] = {"status": "ALREADY_CURRENT", "mutationPerformed": False}
    if backend_changed:
        deploy_environment = _backend_deploy_environment()
        backend_deploy = {
            "status": "DEPLOYED",
            "mutationPerformed": True,
            **_command_json(
                [BACKEND_DEPLOY, backend_image["digest"], revision],
                timeout=1800,
                stage="backend_deploy",
                environment=deploy_environment,
            ),
        }

    mcp_update: dict[str, Any] = {"status": "ALREADY_CURRENT", "mutationPerformed": False}
    try:
        if mcp_changed:
            mcp_update = {
                **_deploy_mcp_from_ci_scope(revision, mcp_image, operator_source),
                "mutationPerformed": True,
            }
    except ReconcileError as exc:
        rollback: dict[str, Any] = {"attempted": False}
        previous_digest = str(previous_backend.get("digest") or "")
        if backend_changed and DIGEST_RE.fullmatch(previous_digest):
            try:
                rollback_result = _command_json(
                    [BACKEND_ROLLBACK, previous_digest],
                    timeout=900,
                    stage="backend_rollback_after_mcp_failure",
                    environment=deploy_environment,
                )
                rollback = {"attempted": True, "ok": True, **rollback_result}
            except ReconcileError as rollback_exc:
                rollback = {
                    "attempted": True,
                    "ok": False,
                    "failureStage": rollback_exc.stage,
                    "failureSha256": hashlib.sha256(rollback_exc.detail.encode()).hexdigest(),
                }
        return _write_status(
            "MCP_UPDATE_FAILED_BACKEND_ROLLBACK_ATTEMPTED",
            ok=False,
            revision=revision,
            releaseGate=gate,
            backendImage=backend_image,
            mcpImage=mcp_image,
            backendDeploy=backend_deploy,
            mcpUpdate={
                "status": "FAILED",
                "failureStage": exc.stage,
                "failureSha256": hashlib.sha256(exc.detail.encode()).hexdigest(),
            },
            rollback=rollback,
            mutationPerformed=bool(backend_changed or mcp_changed),
            retryable=True,
        )

    runtime = _runtime_readback(revision, backend_image, mcp_image)
    return _write_status(
        "COORDINATED_RELEASE_DEPLOYED",
        ok=True,
        revision=revision,
        releaseGate=gate,
        backendImage=backend_image,
        mcpImage=mcp_image,
        backendDeploy=backend_deploy,
        mcpUpdate=mcp_update,
        runtime=runtime,
        mutationPerformed=bool(backend_changed or mcp_changed),
        retryable=False,
        expectedScope=scope,
        operatorSource=operator_source,
    )


def main() -> int:
    scope_values = (
        EXPECTED_REVISION,
        EXPECTED_RELEASE_GATE_RUN_ID,
        EXPECTED_BACKEND_DIGEST,
        EXPECTED_MCP_DIGEST,
        EXPECTED_MANIFEST_EVIDENCE_SHA256,
    )
    if not any(scope_values) and GITHUB_TOKEN_FILE is None:
        _write_status(
            "WAITING_FOR_CI_RUNTIME_READBACK_SCOPE",
            ok=False,
            mutationPerformed=False,
            retryable=False,
        )
        return 0
    if not all(scope_values) or GITHUB_TOKEN_FILE is None:
        _write_status(
            "RECONCILIATION_BLOCKED",
            ok=False,
            failureStage="scope",
            failureSha256=hashlib.sha256(b"partial-or-missing-ci-runtime-readback-scope").hexdigest(),
            mutationPerformed=False,
            retryable=False,
        )
        return 1
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o750)
    with LOCK_FILE.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _write_status(
                "ALREADY_RUNNING",
                ok=False,
                mutationPerformed=False,
                retryable=True,
            )
            return 0
        try:
            reconcile()
            return 0
        except ReconcileError as exc:
            _write_status(
                "RECONCILIATION_BLOCKED",
                ok=False,
                failureStage=exc.stage,
                failureSha256=hashlib.sha256(exc.detail.encode()).hexdigest(),
                mutationPerformed=False,
                retryable=True,
            )
            return 1
        except Exception as exc:  # fail closed without returning raw values
            _write_status(
                "RECONCILIATION_FAILED",
                ok=False,
                failureStage="unexpected",
                failureFamily=type(exc).__name__,
                mutationPerformed=False,
                retryable=True,
            )
            return 1


if __name__ == "__main__":
    sys.exit(main())
