"""Bounded, non-authoritative admission contracts for isolated desktop workers.

The desktop worker is an effect and projection surface only.  It never owns a
Fleet attempt, source of truth, model/provider configuration, permissions, or
verification verdicts.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

from .fleet_supervisor import FleetContractError, stable_hash
from .live_workspace import DesktopRuntimeContractV1, LiveWorkspaceSessionV1

DESKTOP_WORKER_ADMISSION_SCHEMA_VERSION = "sovereign.desktop-worker-admission.v1"
DESKTOP_COMPUTER_USE_SCHEMA_VERSION = "sovereign.desktop-computer-use.v1"
DESKTOP_INPUT_RECEIPT_SCHEMA_VERSION = "sovereign.desktop-input-receipt.v1"

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ATTEMPT_RE = re.compile(r"^attempt-[0-9a-f]{24}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_CONTAINER_RE = re.compile(r"^[0-9a-f]{12,64}$")
_SCOPE_KINDS = frozenset({"VIEW", "CONTROLLER_INPUT"})
_OBSERVATION_STATUSES = frozenset({"SENT", "OBSERVED", "BLOCKED", "UNKNOWN"})
_COMPUTER_USE_KINDS = frozenset(
    {
        "SCREENSHOT",
        "POINTER_MOVE",
        "CLICK",
        "TYPE",
        "KEYPRESS",
        "SCROLL",
        "WINDOW_FOCUS",
        "WINDOW_LIST",
        "VIEWPORT_READBACK",
    }
)


def _text(value: object, field: str, maximum: int = 256) -> str:
    result = str(value or "").strip()
    if not result or len(result) > maximum:
        raise FleetContractError(f"{field} is invalid")
    return result


def _hash(value: object, field: str) -> str:
    result = _text(value, field, 64).lower()
    if not _HASH_RE.fullmatch(result):
        raise FleetContractError(f"{field} must be an exact SHA-256 value")
    return result


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise FleetContractError(f"{field} must be a boolean")
    return value


def _int(value: object, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise FleetContractError(f"{field} is outside its bounded range")
    return value


def _strings(value: object, field: str, *, maximum: int = 12) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise FleetContractError(f"{field} must be an array")
    result = tuple(_text(item, field, 120) for item in value)
    if len(result) > maximum or len(set(result)) != len(result):
        raise FleetContractError(f"{field} is invalid")
    return result


@dataclass(frozen=True)
class DesktopWorkerAdmissionV1:
    """A Docker readback that may admit a projection worker, never verify work."""

    runtime_identity_hash: str
    session_binding_hash: str
    attempt_id: str
    workspace_id: str
    worktree_identity_hash: str
    image_digest: str
    image_reference: str
    source_revision: str
    container_id: str
    privileged: bool
    docker_socket_mounted: bool
    host_namespaces: bool
    no_new_privileges: bool
    capabilities_dropped: bool
    read_only_root_filesystem: bool
    networks: tuple[str, ...]
    published_ports: tuple[str, ...]
    workspace_mount: Mapping[str, str]
    view_scope_hash: str
    input_scope_hash: str
    cpu_millis: int
    memory_bytes: int
    pids_limit: int
    wall_time_seconds: int
    idle_timeout_seconds: int
    worker_claim: str
    admission_hash: str

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        session: LiveWorkspaceSessionV1 | None = None,
    ) -> "DesktopWorkerAdmissionV1":
        if not isinstance(value, Mapping):
            raise FleetContractError("desktop worker admission must be an object")
        image_digest = _text(value.get("imageDigest") or value.get("image_digest"), "image_digest", 80).lower()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest):
            raise FleetContractError("desktop worker image digest must be immutable")
        image_reference = _text(value.get("imageReference") or value.get("image_reference"), "image_reference", 360)
        if not image_reference.endswith("@" + image_digest) or ":latest" in image_reference.lower():
            raise FleetContractError("desktop worker image reference is not digest-bound")
        attempt_id = _text(value.get("attemptId") or value.get("attempt_id"), "attempt_id", 40).lower()
        if not _ATTEMPT_RE.fullmatch(attempt_id):
            raise FleetContractError("desktop worker attempt id is invalid")
        source_revision = _text(value.get("sourceRevision") or value.get("source_revision"), "source_revision", 40).lower()
        if not _REVISION_RE.fullmatch(source_revision):
            raise FleetContractError("desktop worker source revision must be exact")
        container_id = _text(value.get("containerId") or value.get("container_id"), "container_id", 64).lower()
        if not _CONTAINER_RE.fullmatch(container_id):
            raise FleetContractError("desktop worker container id is invalid")
        worker_claim = _text(value.get("workerClaim") or value.get("worker_claim") or "OBSERVED", "worker_claim", 32).upper()
        if worker_claim not in {"OBSERVED", "ADMITTED", "BLOCKED", "UNKNOWN"}:
            raise FleetContractError("desktop worker may not claim verification or success")
        workspace_mount = value.get("workspaceMount") or value.get("workspace_mount")
        if not isinstance(workspace_mount, Mapping):
            raise FleetContractError("desktop worker requires one workspace mount readback")
        result = cls(
            runtime_identity_hash=_hash(value.get("runtimeIdentityHash") or value.get("runtime_identity_hash"), "runtime_identity_hash"),
            session_binding_hash=_hash(value.get("sessionBindingHash") or value.get("session_binding_hash"), "session_binding_hash"),
            attempt_id=attempt_id,
            workspace_id=_text(value.get("workspaceId") or value.get("workspace_id"), "workspace_id", 160),
            worktree_identity_hash=_hash(value.get("worktreeIdentityHash") or value.get("worktree_identity_hash"), "worktree_identity_hash"),
            image_digest=image_digest,
            image_reference=image_reference,
            source_revision=source_revision,
            container_id=container_id,
            privileged=_bool(value.get("privileged"), "privileged"),
            docker_socket_mounted=_bool(value.get("dockerSocketMounted") if "dockerSocketMounted" in value else value.get("docker_socket_mounted"), "docker_socket_mounted"),
            host_namespaces=_bool(value.get("hostNamespaces") if "hostNamespaces" in value else value.get("host_namespaces"), "host_namespaces"),
            no_new_privileges=_bool(value.get("noNewPrivileges") if "noNewPrivileges" in value else value.get("no_new_privileges"), "no_new_privileges"),
            capabilities_dropped=_bool(value.get("capabilitiesDropped") if "capabilitiesDropped" in value else value.get("capabilities_dropped"), "capabilities_dropped"),
            read_only_root_filesystem=_bool(value.get("readOnlyRootFilesystem") if "readOnlyRootFilesystem" in value else value.get("read_only_root_filesystem"), "read_only_root_filesystem"),
            networks=_strings(value.get("networks"), "networks", maximum=2),
            published_ports=_strings(value.get("publishedPorts") if "publishedPorts" in value else value.get("published_ports") or (), "published_ports", maximum=1),
            workspace_mount={
                "destination": _text(workspace_mount.get("destination"), "workspace_mount.destination", 120),
                "workspaceId": _text(workspace_mount.get("workspaceId") or workspace_mount.get("workspace_id"), "workspace_mount.workspace_id", 160),
                "attemptId": _text(workspace_mount.get("attemptId") or workspace_mount.get("attempt_id"), "workspace_mount.attempt_id", 40).lower(),
                "worktreeIdentityHash": _hash(workspace_mount.get("worktreeIdentityHash") or workspace_mount.get("worktree_identity_hash"), "workspace_mount.worktree_identity_hash"),
                "hostPathHash": _hash(workspace_mount.get("hostPathHash") or workspace_mount.get("host_path_hash"), "workspace_mount.host_path_hash"),
                "readWrite": str(_bool(workspace_mount.get("readWrite") if "readWrite" in workspace_mount else workspace_mount.get("read_write"), "workspace_mount.read_write")).lower(),
            },
            view_scope_hash=_hash(value.get("viewScopeHash") or value.get("view_scope_hash"), "view_scope_hash"),
            input_scope_hash=_hash(value.get("inputScopeHash") or value.get("input_scope_hash"), "input_scope_hash"),
            cpu_millis=_int(value.get("cpuMillis") if "cpuMillis" in value else value.get("cpu_millis"), "cpu_millis", minimum=100, maximum=4000),
            memory_bytes=_int(value.get("memoryBytes") if "memoryBytes" in value else value.get("memory_bytes"), "memory_bytes", minimum=268_435_456, maximum=8_589_934_592),
            pids_limit=_int(value.get("pidsLimit") if "pidsLimit" in value else value.get("pids_limit"), "pids_limit", minimum=16, maximum=256),
            wall_time_seconds=_int(value.get("wallTimeSeconds") if "wallTimeSeconds" in value else value.get("wall_time_seconds"), "wall_time_seconds", minimum=60, maximum=86_400),
            idle_timeout_seconds=_int(value.get("idleTimeoutSeconds") if "idleTimeoutSeconds" in value else value.get("idle_timeout_seconds"), "idle_timeout_seconds", minimum=60, maximum=14_400),
            worker_claim=worker_claim,
            admission_hash="",
        )
        if result.privileged or result.docker_socket_mounted or result.host_namespaces:
            raise FleetContractError("desktop worker host authority is forbidden")
        if not result.no_new_privileges or not result.capabilities_dropped or not result.read_only_root_filesystem:
            raise FleetContractError("desktop worker hardening is incomplete")
        if result.networks != ("sovereign-desktop",):
            raise FleetContractError("desktop worker network topology is not private and exact")
        if result.published_ports:
            raise FleetContractError("desktop worker may not publish host ports")
        mount = result.workspace_mount
        if (
            mount["destination"] != "/workspace"
            or mount["workspaceId"] != result.workspace_id
            or mount["attemptId"] != result.attempt_id
            or mount["worktreeIdentityHash"] != result.worktree_identity_hash
            or mount["readWrite"] != "true"
        ):
            raise FleetContractError("desktop worker workspace mount is not bound to the active attempt")
        if result.view_scope_hash == result.input_scope_hash:
            raise FleetContractError("desktop view and controller input scopes must be distinct")
        if result.idle_timeout_seconds > result.wall_time_seconds:
            raise FleetContractError("desktop worker idle timeout may not exceed wall time")
        if session is not None:
            if (
                session.session_binding_hash != result.session_binding_hash
                or session.attempt_id != result.attempt_id
                or session.workspace_id != result.workspace_id
                or session.worktree_identity_hash != result.worktree_identity_hash
            ):
                raise FleetContractError("desktop worker admission is not bound to the live workspace session")
        payload = result._payload()
        return cls(**{**result.__dict__, "admission_hash": stable_hash(payload)})

    def _payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": DESKTOP_WORKER_ADMISSION_SCHEMA_VERSION,
            "runtimeIdentityHash": self.runtime_identity_hash,
            "sessionBindingHash": self.session_binding_hash,
            "attemptId": self.attempt_id,
            "workspaceId": self.workspace_id,
            "worktreeIdentityHash": self.worktree_identity_hash,
            "imageDigest": self.image_digest,
            "imageReference": self.image_reference,
            "sourceRevision": self.source_revision,
            "containerId": self.container_id,
            "privileged": self.privileged,
            "dockerSocketMounted": self.docker_socket_mounted,
            "hostNamespaces": self.host_namespaces,
            "noNewPrivileges": self.no_new_privileges,
            "capabilitiesDropped": self.capabilities_dropped,
            "readOnlyRootFilesystem": self.read_only_root_filesystem,
            "networks": list(self.networks),
            "publishedPorts": list(self.published_ports),
            "workspaceMount": dict(self.workspace_mount),
            "viewScopeHash": self.view_scope_hash,
            "inputScopeHash": self.input_scope_hash,
            "cpuMillis": self.cpu_millis,
            "memoryBytes": self.memory_bytes,
            "pidsLimit": self.pids_limit,
            "wallTimeSeconds": self.wall_time_seconds,
            "idleTimeoutSeconds": self.idle_timeout_seconds,
            "workerClaim": self.worker_claim,
        }

    def to_runtime_contract(self) -> DesktopRuntimeContractV1:
        return DesktopRuntimeContractV1.from_dict(
            {
                "runtimeIdentityHash": self.runtime_identity_hash,
                "imageDigest": self.image_digest,
                "privileged": self.privileged,
                "dockerSocketMounted": self.docker_socket_mounted,
                "hostNamespaces": self.host_namespaces,
                "noNewPrivileges": self.no_new_privileges,
                "capabilitiesDropped": self.capabilities_dropped,
                "readOnlyRootFilesystem": self.read_only_root_filesystem,
                "workspaceId": self.workspace_id,
                "inputScopeHash": self.input_scope_hash,
                "viewScopeHash": self.view_scope_hash,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._payload(),
            "admissionHash": self.admission_hash,
            "authoritative": False,
            "verificationAuthority": False,
        }


@dataclass(frozen=True)
class DesktopComputerUseRequestV1:
    session_binding_hash: str
    attempt_id: str
    action_id: str
    input_kind: str
    scope_kind: str
    request_hash: str

    @classmethod
    def create(
        cls,
        *,
        admission: DesktopWorkerAdmissionV1,
        action_id: str,
        input_kind: str,
        scope_kind: str,
        normalized_arguments: Mapping[str, Any] | None = None,
    ) -> "DesktopComputerUseRequestV1":
        kind = _text(input_kind, "input_kind", 80).upper()
        if kind not in _COMPUTER_USE_KINDS:
            raise FleetContractError("desktop computer-use action is forbidden")
        scope = _text(scope_kind, "scope_kind", 80).upper()
        if scope not in _SCOPE_KINDS:
            raise FleetContractError("desktop computer-use scope is forbidden")
        if kind in {"CLICK", "TYPE", "KEYPRESS", "SCROLL", "POINTER_MOVE", "WINDOW_FOCUS"} and scope != "CONTROLLER_INPUT":
            raise FleetContractError("desktop input requires controller input scope")
        if kind in {"SCREENSHOT", "WINDOW_LIST", "VIEWPORT_READBACK"} and scope != "VIEW":
            raise FleetContractError("desktop observation requires view scope")
        action = _text(action_id, "action_id", 120)
        arguments = dict(normalized_arguments or {})
        encoded = {
            "schemaVersion": DESKTOP_COMPUTER_USE_SCHEMA_VERSION,
            "sessionBindingHash": admission.session_binding_hash,
            "attemptId": admission.attempt_id,
            "actionId": action,
            "inputKind": kind,
            "scopeKind": scope,
            "normalizedArguments": arguments,
        }
        return cls(
            session_binding_hash=admission.session_binding_hash,
            attempt_id=admission.attempt_id,
            action_id=action,
            input_kind=kind,
            scope_kind=scope,
            request_hash=stable_hash(encoded),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": DESKTOP_COMPUTER_USE_SCHEMA_VERSION,
            "sessionBindingHash": self.session_binding_hash,
            "attemptId": self.attempt_id,
            "actionId": self.action_id,
            "inputKind": self.input_kind,
            "scopeKind": self.scope_kind,
            "requestHash": self.request_hash,
            "authoritative": False,
        }


@dataclass(frozen=True)
class DesktopInputObservationReceiptV1:
    session_binding_hash: str
    attempt_id: str
    action_id: str
    input_kind: str
    request_hash: str
    runtime_identity_hash: str
    status: str
    receipt_hash: str

    @classmethod
    def create(
        cls,
        *,
        admission: DesktopWorkerAdmissionV1,
        request: DesktopComputerUseRequestV1,
        status: str,
    ) -> "DesktopInputObservationReceiptV1":
        selected_status = _text(status, "status", 32).upper()
        if selected_status not in _OBSERVATION_STATUSES:
            raise FleetContractError("desktop input receipt status is forbidden")
        if (
            request.session_binding_hash != admission.session_binding_hash
            or request.attempt_id != admission.attempt_id
        ):
            raise FleetContractError("desktop input request is not bound to admission")
        payload = {
            "schemaVersion": DESKTOP_INPUT_RECEIPT_SCHEMA_VERSION,
            "sessionBindingHash": admission.session_binding_hash,
            "attemptId": admission.attempt_id,
            "actionId": request.action_id,
            "inputKind": request.input_kind,
            "requestHash": request.request_hash,
            "runtimeIdentityHash": admission.runtime_identity_hash,
            "status": selected_status,
        }
        return cls(
            session_binding_hash=admission.session_binding_hash,
            attempt_id=admission.attempt_id,
            action_id=request.action_id,
            input_kind=request.input_kind,
            request_hash=request.request_hash,
            runtime_identity_hash=admission.runtime_identity_hash,
            status=selected_status,
            receipt_hash=stable_hash(payload),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": DESKTOP_INPUT_RECEIPT_SCHEMA_VERSION,
            "sessionBindingHash": self.session_binding_hash,
            "attemptId": self.attempt_id,
            "actionId": self.action_id,
            "inputKind": self.input_kind,
            "requestHash": self.request_hash,
            "runtimeIdentityHash": self.runtime_identity_hash,
            "status": self.status,
            "receiptHash": self.receipt_hash,
            "targetEffectVerified": False,
            "authoritative": False,
        }


__all__ = [
    "DESKTOP_COMPUTER_USE_SCHEMA_VERSION",
    "DESKTOP_INPUT_RECEIPT_SCHEMA_VERSION",
    "DESKTOP_WORKER_ADMISSION_SCHEMA_VERSION",
    "DesktopComputerUseRequestV1",
    "DesktopInputObservationReceiptV1",
    "DesktopWorkerAdmissionV1",
]
