"""Host-worker-only lifecycle for one isolated desktop container.

The public broker never receives a host path, scope value, or Docker argument.
It receives only an opaque activation id.  A controller-side issuer must place
a mode-0600, non-symlink activation document in the host-only activation root.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_ACTIVATION_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ATTEMPT_RE = re.compile(r"^attempt-[0-9a-f]{24}$")
_WORKSPACE_RE = re.compile(r"^job-[a-z0-9-]{6,63}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_RE = re.compile(r"^[A-Za-z0-9./_-]+@sha256:[0-9a-f]{64}$")
_CONTAINER_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")
_MAX_CPU_MILLIS = 4_000
_MAX_MEMORY_BYTES = 8 * 1024 * 1024 * 1024
_MAX_PIDS = 256


class DesktopWorkerError(ValueError):
    pass


def _text(value: object, field: str, maximum: int = 256) -> str:
    result = str(value or "").strip()
    if not result or len(result) > maximum:
        raise DesktopWorkerError(f"{field} is invalid")
    return result


def _hash(value: object, field: str) -> str:
    result = _text(value, field, 64).lower()
    if not _HASH_RE.fullmatch(result):
        raise DesktopWorkerError(f"{field} must be an exact SHA-256 value")
    return result


def _bounded_int(value: object, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise DesktopWorkerError(f"{field} is outside its bounded range")
    return value


@dataclass(frozen=True)
class DesktopActivation:
    activation_id: str
    session_binding_hash: str
    attempt_id: str
    workspace_id: str
    worktree_identity_hash: str
    workspace_path: Path
    workspace_path_hash: str
    image_reference: str
    runtime_identity_hash: str
    source_revision: str
    expected_base_revision: str
    observed_head_revision: str
    view_scope_path: Path
    view_scope_hash: str
    input_scope_path: Path
    input_scope_hash: str
    cpu_millis: int
    memory_bytes: int
    pids_limit: int
    wall_time_seconds: int
    idle_timeout_seconds: int

    @property
    def container_name(self) -> str:
        return f"sovereign-desktop-{self.session_binding_hash[:20]}"


class DesktopWorkerRuntime:
    """Start/read/remove only exact, pre-issued controller activations."""

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        activation_root: str | None = None,
        workspace_root: str | None = None,
        network: str = "sovereign-desktop",
    ) -> None:
        self._runner = runner or subprocess.run
        self.activation_root = Path(activation_root or os.getenv("SOVEREIGN_DESKTOP_ACTIVATION_ROOT", "/opt/sovereign-desktop-activations"))
        self.workspace_root = Path(workspace_root or os.getenv("SOVEREIGN_DESKTOP_WORKSPACE_ROOT", "/opt/sovereign-agent-workspaces"))
        self.network = _text(network, "network", 80)
        if self.network != "sovereign-desktop":
            raise DesktopWorkerError("desktop worker network must be sovereign-desktop")

    def _under(self, candidate: Path, root: Path, field: str) -> Path:
        root = root.resolve()
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise DesktopWorkerError(f"{field} is unavailable") from exc
        if resolved == root or root not in resolved.parents:
            raise DesktopWorkerError(f"{field} leaves its approved root")
        return resolved

    def _load_json_file(self, path: Path) -> dict[str, Any]:
        if path.is_symlink():
            raise DesktopWorkerError("activation document may not be a symlink")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
                raise DesktopWorkerError("activation document mode is unsafe")
            handle = os.fdopen(descriptor, "r", encoding="utf-8")
            descriptor = -1
            with handle:
                value = json.load(handle)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if not isinstance(value, dict):
            raise DesktopWorkerError("activation document is invalid")
        return value

    def _load_activation(self, activation_id: str) -> DesktopActivation:
        selected_id = _hash(activation_id, "activation_id")
        if not _ACTIVATION_ID_RE.fullmatch(selected_id):
            raise DesktopWorkerError("activation id is invalid")
        document = self.activation_root / f"{selected_id}.json"
        raw = self._load_json_file(self._under(document, self.activation_root, "activation document"))
        if _hash(raw.get("activationId") or raw.get("activation_id"), "activation_id") != selected_id:
            raise DesktopWorkerError("activation id does not bind document")
        workspace_id = _text(raw.get("workspaceId") or raw.get("workspace_id"), "workspace_id", 80)
        if not _WORKSPACE_RE.fullmatch(workspace_id):
            raise DesktopWorkerError("workspace id is invalid")
        attempt_id = _text(raw.get("attemptId") or raw.get("attempt_id"), "attempt_id", 40).lower()
        if not _ATTEMPT_RE.fullmatch(attempt_id):
            raise DesktopWorkerError("attempt id is invalid")
        relative_workspace = Path(_text(raw.get("workspaceRelativePath") or raw.get("workspace_relative_path"), "workspace_relative_path", 500))
        if relative_workspace.is_absolute() or not relative_workspace.parts or ".." in relative_workspace.parts:
            raise DesktopWorkerError("workspace relative path is invalid")
        workspace_path = self._under(self.workspace_root / relative_workspace, self.workspace_root, "workspace path")
        view_scope_name = Path(_text(raw.get("viewScopeFile") or raw.get("view_scope_file"), "view_scope_file", 160))
        input_scope_name = Path(_text(raw.get("inputScopeFile") or raw.get("input_scope_file"), "input_scope_file", 160))
        if view_scope_name.is_absolute() or input_scope_name.is_absolute() or len(view_scope_name.parts) != 1 or len(input_scope_name.parts) != 1:
            raise DesktopWorkerError("desktop scope filenames are invalid")
        view_scope_path = self._under(self.activation_root / view_scope_name, self.activation_root, "view scope")
        input_scope_path = self._under(self.activation_root / input_scope_name, self.activation_root, "input scope")
        if view_scope_path == input_scope_path or view_scope_path.is_symlink() or input_scope_path.is_symlink():
            raise DesktopWorkerError("desktop scopes must be separate regular files")
        for path in (view_scope_path, input_scope_path):
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode) or mode & 0o077 or path.stat().st_size > 256:
                raise DesktopWorkerError("desktop scope material is unsafe")
        image_reference = _text(raw.get("imageReference") or raw.get("image_reference"), "image_reference", 360)
        if not _IMAGE_RE.fullmatch(image_reference) or ":latest" in image_reference.lower():
            raise DesktopWorkerError("desktop image must be immutable and digest-bound")
        source_revision = _text(raw.get("sourceRevision") or raw.get("source_revision"), "source_revision", 40).lower()
        expected_base_revision = _text(raw.get("expectedBaseRevision") or raw.get("expected_base_revision"), "expected_base_revision", 40).lower()
        observed_head_revision = _text(raw.get("observedHeadRevision") or raw.get("observed_head_revision"), "observed_head_revision", 40).lower()
        if not all(_REVISION_RE.fullmatch(value) for value in (source_revision, expected_base_revision, observed_head_revision)):
            raise DesktopWorkerError("desktop revisions must be exact")
        workspace_path_hash = _hash(raw.get("workspacePathHash") or raw.get("workspace_path_hash"), "workspace_path_hash")
        view_scope_hash = _hash(raw.get("viewScopeHash") or raw.get("view_scope_hash"), "view_scope_hash")
        input_scope_hash = _hash(raw.get("inputScopeHash") or raw.get("input_scope_hash"), "input_scope_hash")
        if view_scope_hash == input_scope_hash:
            raise DesktopWorkerError("desktop view and input scope hashes must differ")
        if view_scope_hash != hashlib.sha256(view_scope_path.read_bytes()).hexdigest() or input_scope_hash != hashlib.sha256(input_scope_path.read_bytes()).hexdigest():
            raise DesktopWorkerError("desktop scope content does not match activation hash")
        return DesktopActivation(
            activation_id=selected_id,
            session_binding_hash=_hash(raw.get("sessionBindingHash") or raw.get("session_binding_hash"), "session_binding_hash"),
            attempt_id=attempt_id,
            workspace_id=workspace_id,
            worktree_identity_hash=_hash(raw.get("worktreeIdentityHash") or raw.get("worktree_identity_hash"), "worktree_identity_hash"),
            workspace_path=workspace_path,
            workspace_path_hash=workspace_path_hash,
            image_reference=image_reference,
            runtime_identity_hash=_hash(raw.get("runtimeIdentityHash") or raw.get("runtime_identity_hash"), "runtime_identity_hash"),
            source_revision=source_revision,
            expected_base_revision=expected_base_revision,
            observed_head_revision=observed_head_revision,
            view_scope_path=view_scope_path,
            view_scope_hash=view_scope_hash,
            input_scope_path=input_scope_path,
            input_scope_hash=input_scope_hash,
            cpu_millis=_bounded_int(raw.get("cpuMillis") if "cpuMillis" in raw else raw.get("cpu_millis"), "cpu_millis", 100, _MAX_CPU_MILLIS),
            memory_bytes=_bounded_int(raw.get("memoryBytes") if "memoryBytes" in raw else raw.get("memory_bytes"), "memory_bytes", 268_435_456, _MAX_MEMORY_BYTES),
            pids_limit=_bounded_int(raw.get("pidsLimit") if "pidsLimit" in raw else raw.get("pids_limit"), "pids_limit", 16, _MAX_PIDS),
            wall_time_seconds=_bounded_int(raw.get("wallTimeSeconds") if "wallTimeSeconds" in raw else raw.get("wall_time_seconds"), "wall_time_seconds", 60, 86_400),
            idle_timeout_seconds=_bounded_int(raw.get("idleTimeoutSeconds") if "idleTimeoutSeconds" in raw else raw.get("idle_timeout_seconds"), "idle_timeout_seconds", 60, 14_400),
        )

    def _run(self, argv: list[str], timeout: int = 60) -> dict[str, Any]:
        completed = self._runner(argv, capture_output=True, text=True, timeout=timeout, check=False)
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-24_000:],
            "stderr": completed.stderr[-24_000:],
        }

    @staticmethod
    def _public_plan(activation: DesktopActivation) -> dict[str, Any]:
        return {
            "activationId": activation.activation_id,
            "containerName": activation.container_name,
            "sessionBindingHash": activation.session_binding_hash,
            "attemptId": activation.attempt_id,
            "workspaceId": activation.workspace_id,
            "worktreeIdentityHash": activation.worktree_identity_hash,
            "imageReference": activation.image_reference,
            "runtimeIdentityHash": activation.runtime_identity_hash,
            "sourceRevision": activation.source_revision,
            "expectedBaseRevision": activation.expected_base_revision,
            "observedHeadRevision": activation.observed_head_revision,
            "network": "sovereign-desktop",
            "publishedPorts": [],
            "authoritative": False,
            "verificationAuthority": False,
        }

    def _docker_run_argv(self, activation: DesktopActivation) -> list[str]:
        image_digest = activation.image_reference.rsplit("@", 1)[1]
        return [
            "docker", "run", "--detach", "--init",
            "--name", activation.container_name,
            "--label", "sovereign.component=desktop-worker",
            "--label", f"sovereign.activation-id={activation.activation_id}",
            "--label", f"sovereign.session-binding-hash={activation.session_binding_hash}",
            "--label", f"sovereign.attempt-id={activation.attempt_id}",
            "--label", f"sovereign.workspace-id={activation.workspace_id}",
            "--label", f"sovereign.worktree-identity-hash={activation.worktree_identity_hash}",
            "--label", f"sovereign.runtime-identity-hash={activation.runtime_identity_hash}",
            "--label", f"sovereign.source-revision={activation.source_revision}",
            "--label", f"sovereign.expected-base-revision={activation.expected_base_revision}",
            "--label", f"sovereign.observed-head-revision={activation.observed_head_revision}",
            "--label", f"sovereign.image-digest={image_digest}",
            "--user", "10001:10001",
            "--read-only",
            "--security-opt", "no-new-privileges:true",
            "--cap-drop", "ALL",
            "--pids-limit", str(activation.pids_limit),
            "--memory", str(activation.memory_bytes),
            "--cpus", f"{activation.cpu_millis / 1000:.3f}",
            "--network", self.network,
            "--mount", f"type=bind,src={activation.workspace_path},dst=/workspace",
            "--mount", f"type=bind,src={activation.view_scope_path},dst=/opt/desktop-scopes/view,readonly",
            "--mount", f"type=bind,src={activation.input_scope_path},dst=/opt/desktop-scopes/input,readonly",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=128m",
            "--tmpfs", "/run:rw,noexec,nosuid,size=16m,uid=10001,gid=10001,mode=0700",
            "--tmpfs", "/home/desktop:rw,noexec,nosuid,size=128m,uid=10001,gid=10001,mode=0700",
            "--env", "DESKTOP_VIEW_SCOPE_FILE=/opt/desktop-scopes/view",
            "--env", "DESKTOP_INPUT_SCOPE_FILE=/opt/desktop-scopes/input",
            "--env", f"DESKTOP_RUNTIME_IDENTITY_HASH={activation.runtime_identity_hash}",
            "--env", f"DESKTOP_WALL_TIME_SECONDS={activation.wall_time_seconds}",
            "--env", f"DESKTOP_IDLE_TIMEOUT_SECONDS={activation.idle_timeout_seconds}",
            activation.image_reference,
        ]

    def plan(self, *, activation_id: str) -> dict[str, Any]:
        return {"ok": True, "status": "PLANNED", **self._public_plan(self._load_activation(activation_id))}

    @staticmethod
    def _prepare_scope_mounts(activation: DesktopActivation) -> None:
        for path in (activation.view_scope_path, activation.input_scope_path):
            if path.is_symlink() or not path.is_file():
                raise DesktopWorkerError("desktop scope material is unavailable")
            os.chown(path, 10001, 10001)
            os.chmod(path, 0o400)
            metadata = path.stat()
            if metadata.st_uid != 10001 or metadata.st_mode & 0o077:
                raise DesktopWorkerError("desktop scope material cannot be mounted safely")

    def start(self, *, activation_id: str) -> dict[str, Any]:
        activation = self._load_activation(activation_id)
        try:
            self._prepare_scope_mounts(activation)
        except (DesktopWorkerError, OSError):
            return {"ok": False, "status": "BLOCKED", "failure_family": "DESKTOP_SCOPE_MOUNT_PREPARATION_FAILED", **self._public_plan(activation)}
        existing = self._run(["docker", "container", "inspect", activation.container_name], timeout=20)
        if existing["ok"]:
            return {"ok": False, "status": "BLOCKED", "failure_family": "DESKTOP_ALREADY_EXISTS", **self._public_plan(activation)}
        result = self._run(self._docker_run_argv(activation), timeout=120)
        if not result["ok"]:
            return {"ok": False, "status": "FAILED", "failure_family": "DESKTOP_START_FAILED", **self._public_plan(activation)}
        return {"ok": True, "status": "STARTED", **self._public_plan(activation)}

    def _inspect_container(self, activation: DesktopActivation) -> dict[str, Any] | None:
        result = self._run(["docker", "container", "inspect", "--format", "{{json .}}", activation.container_name], timeout=30)
        if not result["ok"]:
            return None
        try:
            value = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def readback(self, *, activation_id: str) -> dict[str, Any]:
        activation = self._load_activation(activation_id)
        record = self._inspect_container(activation)
        if record is None:
            return {"ok": False, "status": "UNKNOWN", "failure_family": "DESKTOP_INSPECT_UNAVAILABLE", **self._public_plan(activation)}
        host = record.get("HostConfig") if isinstance(record.get("HostConfig"), dict) else {}
        config = record.get("Config") if isinstance(record.get("Config"), dict) else {}
        state = record.get("State") if isinstance(record.get("State"), dict) else {}
        network_settings = record.get("NetworkSettings") if isinstance(record.get("NetworkSettings"), dict) else {}
        networks = network_settings.get("Networks") if isinstance(network_settings.get("Networks"), dict) else {}
        labels = config.get("Labels") if isinstance(config.get("Labels"), dict) else {}
        mounts = record.get("Mounts") if isinstance(record.get("Mounts"), list) else []
        expected_labels = {
            "sovereign.component": "desktop-worker",
            "sovereign.activation-id": activation.activation_id,
            "sovereign.session-binding-hash": activation.session_binding_hash,
            "sovereign.attempt-id": activation.attempt_id,
            "sovereign.workspace-id": activation.workspace_id,
            "sovereign.worktree-identity-hash": activation.worktree_identity_hash,
            "sovereign.runtime-identity-hash": activation.runtime_identity_hash,
            "sovereign.source-revision": activation.source_revision,
            "sovereign.expected-base-revision": activation.expected_base_revision,
            "sovereign.observed-head-revision": activation.observed_head_revision,
            "sovereign.image-digest": activation.image_reference.rsplit("@", 1)[1],
        }
        violations: list[str] = []
        if not bool(state.get("Running")):
            violations.append("NOT_RUNNING")
        health = state.get("Health") if isinstance(state.get("Health"), dict) else {}
        if health.get("Status") != "healthy":
            violations.append("HEALTH_NOT_READY")
        if bool(host.get("Privileged")) or not bool(host.get("ReadonlyRootfs")):
            violations.append("HOST_AUTHORITY_OR_WRITABLE_ROOT")
        security = host.get("SecurityOpt") if isinstance(host.get("SecurityOpt"), list) else []
        if "no-new-privileges:true" not in security:
            violations.append("NO_NEW_PRIVILEGES_MISSING")
        cap_drop = host.get("CapDrop") if isinstance(host.get("CapDrop"), list) else []
        if "ALL" not in cap_drop:
            violations.append("CAP_DROP_MISSING")
        if host.get("NetworkMode") != self.network or tuple(sorted(networks)) != (self.network,):
            violations.append("NETWORK_TOPOLOGY_MISMATCH")
        ports = network_settings.get("Ports") if isinstance(network_settings.get("Ports"), dict) else {}
        if any(value for value in ports.values()):
            violations.append("PUBLISHED_PORT_PRESENT")
        if any(str(mount.get("Source") or "").endswith("docker.sock") for mount in mounts if isinstance(mount, dict)):
            violations.append("DOCKER_SOCKET_PRESENT")
        expected_mounts = {
            "/workspace": (str(activation.workspace_path), True),
            "/opt/desktop-scopes/view": (str(activation.view_scope_path), False),
            "/opt/desktop-scopes/input": (str(activation.input_scope_path), False),
        }
        actual_mounts = {
            str(mount.get("Destination") or ""): (str(mount.get("Source") or ""), bool(mount.get("RW")))
            for mount in mounts
            if isinstance(mount, dict)
        }
        if actual_mounts != expected_mounts:
            violations.append("MOUNT_TOPOLOGY_MISMATCH")
        if any(labels.get(key) != value for key, value in expected_labels.items()):
            violations.append("BINDING_LABEL_MISMATCH")
        if config.get("Image") != activation.image_reference:
            violations.append("IMAGE_REFERENCE_MISMATCH")
        image = self._run(["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", activation.image_reference], timeout=30)
        try:
            repo_digests = json.loads(image["stdout"]) if image["ok"] else []
        except json.JSONDecodeError:
            repo_digests = []
        if not isinstance(repo_digests, list) or activation.image_reference not in repo_digests:
            violations.append("IMAGE_DIGEST_UNVERIFIED")
        public = {
            **self._public_plan(activation),
            "containerId": str(record.get("Id") or "")[:64],
            "imageDigest": activation.image_reference.rsplit("@", 1)[1],
            "runtimeSecurity": {
                "privileged": bool(host.get("Privileged")),
                "readOnlyRootFilesystem": bool(host.get("ReadonlyRootfs")),
                "noNewPrivileges": "no-new-privileges:true" in security,
                "capabilitiesDropped": "ALL" in cap_drop,
                "networks": sorted(networks),
                "publishedPorts": [],
            },
            "workspaceMount": {
                "destination": "/workspace",
                "workspaceId": activation.workspace_id,
                "attemptId": activation.attempt_id,
                "worktreeIdentityHash": activation.worktree_identity_hash,
                "hostPathHash": activation.workspace_path_hash,
                "readWrite": True,
            },
            "health": str(health.get("Status") or "unknown"),
            "workerClaim": "OBSERVED",
        }
        if violations:
            return {"ok": False, "status": "CONTRADICTED", "failure_family": "DESKTOP_RUNTIME_CONTRADICTION", "violations": sorted(violations), **public}
        return {"ok": True, "status": "OBSERVED", "violations": [], **public}

    def canary(self, *, activation_id: str) -> dict[str, Any]:
        activation = self._load_activation(activation_id)
        readback = self.readback(activation_id=activation_id)
        if not readback.get("ok"):
            return {"ok": False, "status": "BLOCKED", "failure_family": "DESKTOP_CANARY_PRECONDITION_FAILED", **self._public_plan(activation)}
        script = (
            "from pathlib import Path; from urllib.request import Request, urlopen; "
            "scope=Path('/opt/desktop-scopes/view').read_text('utf-8').strip(); "
            "request=Request('http://127.0.0.1:8765/frame',headers={'X-Sovereign-Desktop-Scope':scope}); "
            "response=urlopen(request,timeout=8); body=response.read(64); "
            "assert response.status==200 and response.headers.get('Content-Type')=='image/png' and body.startswith(bytes([137,80,78,71]))"
        )
        result = self._run(["docker", "exec", activation.container_name, "python3", "-c", script], timeout=20)
        return {
            "ok": result["ok"],
            "status": "OBSERVED" if result["ok"] else "UNKNOWN",
            "failure_family": None if result["ok"] else "DESKTOP_CANARY_FAILED",
            **self._public_plan(activation),
            "authoritative": False,
            "targetEffectVerified": False,
        }

    @staticmethod
    def _controller_input_payload(arguments: dict[str, Any]) -> dict[str, Any]:
        action_id = _text(arguments.get("action_id"), "action_id", 120)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", action_id):
            raise DesktopWorkerError("controller input action id is invalid")
        action = _text(arguments.get("action"), "action", 40).lower()
        if action not in {"pointer_move", "click", "type", "keypress", "scroll", "window_focus"}:
            raise DesktopWorkerError("controller input action is forbidden")
        payload: dict[str, Any] = {"actionId": action_id, "action": action}
        if action in {"pointer_move", "click"}:
            payload["x"] = _bounded_int(arguments.get("x"), "x", 0, 7680)
            payload["y"] = _bounded_int(arguments.get("y"), "y", 0, 7680)
            if action == "click":
                button = _text(arguments.get("button") or "left", "button", 12).lower()
                if button not in {"left", "middle", "right"}:
                    raise DesktopWorkerError("controller click button is forbidden")
                payload["button"] = button
        elif action == "type":
            text = arguments.get("text")
            if not isinstance(text, str) or not text or len(text.encode("utf-8")) > 2_048:
                raise DesktopWorkerError("controller type text is outside bounded range")
            payload["text"] = text
        elif action == "keypress":
            key = _text(arguments.get("key"), "key", 80)
            if not re.fullmatch(r"[A-Za-z0-9_+.-]{1,80}", key):
                raise DesktopWorkerError("controller keypress is forbidden")
            payload["key"] = key
        elif action == "scroll":
            amount = _bounded_int(arguments.get("amount"), "amount", -20, 20)
            if amount == 0:
                raise DesktopWorkerError("controller scroll amount may not be zero")
            payload["amount"] = amount
        else:
            window_id = _text(arguments.get("window_id"), "window_id", 12)
            if not re.fullmatch(r"[0-9]{1,12}", window_id):
                raise DesktopWorkerError("controller window id is forbidden")
            payload["windowId"] = window_id
        return payload

    @contextmanager
    def _control_lock(self, activation: DesktopActivation):
        """Use the same per-activation lock as the backend handoff gateway."""
        lock_path = self.activation_root / f"{activation.activation_id}.control.lock"
        try:
            descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        except OSError as exc:
            raise DesktopWorkerError("desktop control lock is unavailable") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
                raise DesktopWorkerError("desktop control lock is unsafe")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _assert_agent_input_control(self, activation: DesktopActivation) -> None:
        """Allow controller GUI input only when no human lease or a rebound exists."""
        path = self.activation_root / f"{activation.activation_id}.control.json"
        if not path.exists():
            return
        raw = self._load_json_file(self._under(path, self.activation_root, "desktop control record"))
        if raw.get("schemaVersion") != "sovereign.desktop-control.v1":
            raise DesktopWorkerError("desktop control record is invalid")
        payload = {
            "schemaVersion": raw.get("schemaVersion"),
            "leaseId": raw.get("leaseId"),
            "sessionBindingHash": raw.get("sessionBindingHash"),
            "ownerSubjectHash": raw.get("ownerSubjectHash"),
            "runId": raw.get("runId"),
            "attemptId": raw.get("attemptId"),
            "workspaceId": raw.get("workspaceId"),
            "worktreeIdentityHash": raw.get("worktreeIdentityHash"),
            "inputScopeHash": raw.get("inputScopeHash"),
            "state": raw.get("state"),
            "issuedReadbackHash": raw.get("issuedReadbackHash"),
            "reconciledReadbackHash": raw.get("reconciledReadbackHash"),
            "issuedAt": raw.get("issuedAt"),
            "expiresAt": raw.get("expiresAt"),
        }
        expected_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if (
            not isinstance(raw.get("recordHash"), str)
            or raw["recordHash"] != expected_hash
            or raw.get("sessionBindingHash") != activation.session_binding_hash
            or raw.get("attemptId") != activation.attempt_id
            or raw.get("workspaceId") != activation.workspace_id
            or raw.get("worktreeIdentityHash") != activation.worktree_identity_hash
            or raw.get("state") != "AGENT_CONTROLLED_REBOUND"
        ):
            raise DesktopWorkerError("desktop input lease is unavailable")

    def controller_input(self, *, activation_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        activation = self._load_activation(activation_id)
        try:
            with self._control_lock(activation):
                self._assert_agent_input_control(activation)
                readback = self.readback(activation_id=activation_id)
                if not readback.get("ok"):
                    return {"ok": False, "status": "BLOCKED", "failure_family": "DESKTOP_INPUT_PRECONDITION_FAILED", **self._public_plan(activation)}
                try:
                    payload = self._controller_input_payload(arguments)
                except DesktopWorkerError:
                    return {"ok": False, "status": "BLOCKED", "failure_family": "DESKTOP_INPUT_ARGUMENT_INVALID", **self._public_plan(activation)}
                script = (
                    "import json,sys; from pathlib import Path; from urllib.request import Request,urlopen; "
                    "scope=Path('/opt/desktop-scopes/input').read_text('utf-8').strip(); body=sys.stdin.buffer.read(); "
                    "request=Request('http://127.0.0.1:8765/input',data=body,headers={'Content-Type':'application/json','X-Sovereign-Desktop-Scope':scope},method='POST'); "
                    "response=urlopen(request,timeout=8); print(response.read().decode('utf-8'))"
                )
                encoded = json.dumps(payload, separators=(",", ":"))
                completed = self._runner(
                    ["docker", "exec", "-i", activation.container_name, "python3", "-c", script],
                    input=encoded,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
        except DesktopWorkerError:
            return {"ok": False, "status": "BLOCKED", "failure_family": "DESKTOP_INPUT_LEASE_UNAVAILABLE", **self._public_plan(activation)}
        try:
            response = json.loads(completed.stdout)
        except json.JSONDecodeError:
            response = {}
        if completed.returncode != 0 or not isinstance(response, dict) or response.get("status") not in {"SENT", "OBSERVED"}:
            return {"ok": False, "status": "UNKNOWN", "failure_family": "DESKTOP_INPUT_DELIVERY_FAILED", **self._public_plan(activation)}
        return {
            "ok": True,
            "status": str(response["status"]),
            "actionId": payload["actionId"],
            "inputKind": str(response.get("inputKind") or payload["action"]).upper(),
            "requestHash": str(response.get("requestHash") or ""),
            "runtimeIdentityHash": activation.runtime_identity_hash,
            "targetEffectVerified": False,
            "authoritative": False,
        }

    def remove(self, *, activation_id: str) -> dict[str, Any]:
        activation = self._load_activation(activation_id)
        inspect = self._run(["docker", "container", "inspect", "--format", "{{json .Config.Labels}}", activation.container_name], timeout=20)
        if not inspect["ok"]:
            return {"ok": False, "status": "BLOCKED", "failure_family": "DESKTOP_NOT_FOUND", **self._public_plan(activation)}
        try:
            labels = json.loads(inspect["stdout"])
        except json.JSONDecodeError:
            labels = {}
        if not isinstance(labels, dict) or labels.get("sovereign.activation-id") != activation.activation_id:
            return {"ok": False, "status": "BLOCKED", "failure_family": "DESKTOP_OWNERSHIP_MISMATCH", **self._public_plan(activation)}
        result = self._run(["docker", "rm", "--force", activation.container_name], timeout=60)
        return {
            "ok": result["ok"],
            "status": "REMOVED" if result["ok"] else "FAILED",
            "failure_family": None if result["ok"] else "DESKTOP_REMOVE_FAILED",
            **self._public_plan(activation),
        }
