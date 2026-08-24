"""Fail-closed contracts for the isolated native desktop worker (Issue #1617).

This module is deliberately a contract and admission layer.  It does not create a
container, worktree, run, agent or success verdict.  A trusted host-side operator
must perform the bounded effect and return a fresh Docker/PatchMon readback.  The
worker's stream and GUI observations remain non-authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Mapping, Sequence

from .fleet_supervisor import FleetContractError, stable_hash
from .live_workspace import (
    DesktopRuntimeContractV1,
    LiveWorkspaceControlLeaseV1,
    LiveWorkspaceSessionV1,
    SessionReconciliationV1,
)


DESKTOP_WORKER_READBACK_SCHEMA_VERSION = "sovereign.desktop-worker-readback.v1"
DESKTOP_WORKER_SENSOR_RECEIPT_SCHEMA_VERSION = "sovereign.desktop-worker-sensor-receipt.v1"
DESKTOP_WORKER_ADMISSION_SCHEMA_VERSION = "sovereign.desktop-worker-admission.v1"
DESKTOP_VIEW_GRANT_SCHEMA_VERSION = "sovereign.desktop-view-grant.v1"
DESKTOP_INPUT_GRANT_SCHEMA_VERSION = "sovereign.desktop-input-grant.v1"
COMPUTER_USE_REQUEST_SCHEMA_VERSION = "sovereign.computer-use-request.v2"
COMPUTER_USE_RECEIPT_SCHEMA_VERSION = "sovereign.computer-use-observation-receipt.v2"
MAX_DESKTOP_READBACK_AGE_SECONDS = 300

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_ATTEMPT_RE = re.compile(r"^attempt-[0-9a-f]{24}$")
_ADMISSION_RE = re.compile(r"^desktop-admission-[0-9a-f]{24}$")
_WINDOW_RE = re.compile(r"^[0-9a-f]{1,16}$")
_KEYPRESS_RE = re.compile(r"^[A-Za-z0-9+_.-]{1,80}$")
_PATH_RE = re.compile(r"^/[A-Za-z0-9._/-]{1,160}$")

_VIEW_INPUT_KINDS = frozenset({"SCREENSHOT", "WINDOW_LIST", "VIEWPORT_READBACK"})
_EFFECT_INPUT_KINDS = frozenset(
    {"POINTER_MOVE", "CLICK", "TYPE", "KEYPRESS", "SCROLL", "WINDOW_FOCUS"}
)
COMPUTER_USE_INPUT_KINDS = _VIEW_INPUT_KINDS | _EFFECT_INPUT_KINDS
_WORKER_RECEIPT_STATUSES = frozenset({"SENT", "OBSERVED", "BLOCKED", "UNKNOWN"})
_ALLOWED_TMPFS_TARGETS = frozenset({"/tmp", "/run", "/home/desktop"})
_SECRET_MARKERS = (
    "sk-proj-",
    "github_pat_",
    "ghp_",
    "authorization: bearer",
    "begin openssh private key",
    "begin rsa private key",
    "begin private key",
)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FleetContractError(f"{field} must be an object")
    return value


def _field(value: Mapping[str, Any], snake: str, camel: str, default: object = None) -> object:
    return value[snake] if snake in value else value.get(camel, default)


def _text(value: object, field: str, *, maximum: int = 320, allow_empty: bool = False) -> str:
    result = str(value or "").strip()
    if (not result and not allow_empty) or len(result) > maximum:
        raise FleetContractError(f"{field} is invalid")
    if any(marker in result.casefold() for marker in _SECRET_MARKERS):
        raise FleetContractError(f"{field} contains secret-shaped material")
    return result


def _hash(value: object, field: str) -> str:
    result = str(value or "").strip().lower()
    if not _HASH_RE.fullmatch(result):
        raise FleetContractError(f"{field} must be an exact SHA-256 value")
    return result


def _revision(value: object, field: str) -> str:
    result = str(value or "").strip().lower()
    if not _REVISION_RE.fullmatch(result):
        raise FleetContractError(f"{field} must be an exact Git revision")
    return result


def _image_digest(value: object, field: str) -> str:
    result = str(value or "").strip().lower()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", result):
        raise FleetContractError(f"{field} must be an immutable image digest")
    return result


def _strict_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise FleetContractError(f"{field} must be a boolean")
    return bool(value)


def _epoch(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise FleetContractError(f"{field} is invalid")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise FleetContractError(f"{field} is invalid") from exc
    if result < 1 or result > 99_999_999_999:
        raise FleetContractError(f"{field} is invalid")
    return result


def _bounded_int(value: object, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise FleetContractError(f"{field} is invalid")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise FleetContractError(f"{field} is invalid") from exc
    if result < minimum or result > maximum:
        raise FleetContractError(f"{field} is out of bounds")
    return result


def _normalised_float(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise FleetContractError(f"{field} is invalid")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise FleetContractError(f"{field} is invalid") from exc
    if not math.isfinite(result) or result < 0.0 or result > 1.0:
        raise FleetContractError(f"{field} must be a finite normalised value between zero and one")
    return round(result, 6)


def _safe_target(value: object, field: str) -> str:
    result = _text(value, field, maximum=160)
    if not _PATH_RE.fullmatch(result) or result == "/" or "//" in result or ".." in result.split("/"):
        raise FleetContractError(f"{field} is not a safe container path")
    return result


def _unique_hashes(value: object, field: str, *, maximum: int = 16) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise FleetContractError(f"{field} must be a list")
    if len(value) > maximum:
        raise FleetContractError(f"{field} exceeds its bounded item limit")
    return tuple(sorted(dict.fromkeys(_hash(item, field) for item in value)))


@dataclass(frozen=True)
class DesktopWorkerMountV1:
    """Path-free mount observation from the host-side Docker sensor."""

    kind: str
    target: str
    source_identity_hash: str | None
    writable: bool

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DesktopWorkerMountV1":
        raw = _mapping(value, "desktop_worker_mount")
        kind = _text(raw.get("kind"), "mount.kind", maximum=40).upper()
        if kind not in {"ATTEMPT_WORKSPACE", "TMPFS"}:
            raise FleetContractError("desktop worker mount kind is forbidden")
        target = _safe_target(raw.get("target"), "mount.target")
        writable = _strict_bool(raw.get("writable"), "mount.writable")
        raw_source = str(_field(raw, "source_identity_hash", "sourceIdentityHash", "") or "").strip()
        if kind == "ATTEMPT_WORKSPACE":
            source = _hash(raw_source, "mount.source_identity_hash")
        else:
            if raw_source:
                raise FleetContractError("tmpfs mount must not disclose a source identity")
            source = None
        return cls(kind=kind, target=target, source_identity_hash=source, writable=writable)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "target": self.target,
            "sourceIdentityHash": self.source_identity_hash,
            "writable": self.writable,
        }


@dataclass(frozen=True)
class DesktopWorkerReadbackV1:
    """Independent runtime/Docker observation; never a worker self-claim."""

    runtime_identity_hash: str
    container_identity_hash: str
    image_digest: str
    runtime_source_revision: str
    session_binding_hash: str
    attempt_id: str
    attempt_hash: str
    workspace_id: str
    worktree_identity_hash: str
    observed_head_revision: str
    input_scope_hash: str
    view_scope_hash: str
    network_identity_hash: str
    egress_policy_hash: str
    mounts: tuple[DesktopWorkerMountV1, ...]
    privileged: bool
    docker_socket_mounted: bool
    host_namespaces: bool
    no_new_privileges: bool
    capabilities_dropped: bool
    read_only_root_filesystem: bool
    public_port_count: int
    egress_default_deny: bool
    llm_routing_present: bool
    production_credentials_present: bool
    lifecycle_state: str
    stream_ready: bool
    input_service_ready: bool
    restart_count: int
    observed_at_epoch: int

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DesktopWorkerReadbackV1":
        raw = _mapping(value, "desktop_worker_readback")
        mounts_raw = raw.get("mounts")
        if not isinstance(mounts_raw, Sequence) or isinstance(mounts_raw, (str, bytes, bytearray)):
            raise FleetContractError("desktop worker mounts must be a list")
        if not mounts_raw or len(mounts_raw) > 8:
            raise FleetContractError("desktop worker mount count is invalid")
        mounts = tuple(DesktopWorkerMountV1.from_dict(_mapping(item, "desktop worker mount")) for item in mounts_raw)
        targets = [item.target for item in mounts]
        if len(targets) != len(set(targets)):
            raise FleetContractError("desktop worker mounts may not share a target")
        lifecycle_state = _text(_field(raw, "lifecycle_state", "lifecycleState"), "lifecycle_state", maximum=40).upper()
        if lifecycle_state != "RUNNING":
            raise FleetContractError("desktop worker must be observed running")
        attempt_id = _text(_field(raw, "attempt_id", "attemptId"), "attempt_id", maximum=80)
        if not _ATTEMPT_RE.fullmatch(attempt_id):
            raise FleetContractError("attempt_id is invalid")
        return cls(
            runtime_identity_hash=_hash(_field(raw, "runtime_identity_hash", "runtimeIdentityHash"), "runtime_identity_hash"),
            container_identity_hash=_hash(_field(raw, "container_identity_hash", "containerIdentityHash"), "container_identity_hash"),
            image_digest=_image_digest(_field(raw, "image_digest", "imageDigest"), "image_digest"),
            runtime_source_revision=_revision(_field(raw, "runtime_source_revision", "runtimeSourceRevision"), "runtime_source_revision"),
            session_binding_hash=_hash(_field(raw, "session_binding_hash", "sessionBindingHash"), "session_binding_hash"),
            attempt_id=attempt_id,
            attempt_hash=_hash(_field(raw, "attempt_hash", "attemptHash"), "attempt_hash"),
            workspace_id=_text(_field(raw, "workspace_id", "workspaceId"), "workspace_id", maximum=160),
            worktree_identity_hash=_hash(_field(raw, "worktree_identity_hash", "worktreeIdentityHash"), "worktree_identity_hash"),
            observed_head_revision=_revision(_field(raw, "observed_head_revision", "observedHeadRevision"), "observed_head_revision"),
            input_scope_hash=_hash(_field(raw, "input_scope_hash", "inputScopeHash"), "input_scope_hash"),
            view_scope_hash=_hash(_field(raw, "view_scope_hash", "viewScopeHash"), "view_scope_hash"),
            network_identity_hash=_hash(_field(raw, "network_identity_hash", "networkIdentityHash"), "network_identity_hash"),
            egress_policy_hash=_hash(_field(raw, "egress_policy_hash", "egressPolicyHash"), "egress_policy_hash"),
            mounts=mounts,
            privileged=_strict_bool(raw.get("privileged"), "privileged"),
            docker_socket_mounted=_strict_bool(_field(raw, "docker_socket_mounted", "dockerSocketMounted"), "docker_socket_mounted"),
            host_namespaces=_strict_bool(_field(raw, "host_namespaces", "hostNamespaces"), "host_namespaces"),
            no_new_privileges=_strict_bool(_field(raw, "no_new_privileges", "noNewPrivileges"), "no_new_privileges"),
            capabilities_dropped=_strict_bool(_field(raw, "capabilities_dropped", "capabilitiesDropped"), "capabilities_dropped"),
            read_only_root_filesystem=_strict_bool(_field(raw, "read_only_root_filesystem", "readOnlyRootFilesystem"), "read_only_root_filesystem"),
            public_port_count=_bounded_int(_field(raw, "public_port_count", "publicPortCount", 0), "public_port_count", minimum=0, maximum=64),
            egress_default_deny=_strict_bool(_field(raw, "egress_default_deny", "egressDefaultDeny"), "egress_default_deny"),
            llm_routing_present=_strict_bool(_field(raw, "llm_routing_present", "llmRoutingPresent"), "llm_routing_present"),
            production_credentials_present=_strict_bool(_field(raw, "production_credentials_present", "productionCredentialsPresent"), "production_credentials_present"),
            lifecycle_state=lifecycle_state,
            stream_ready=_strict_bool(_field(raw, "stream_ready", "streamReady"), "stream_ready"),
            input_service_ready=_strict_bool(_field(raw, "input_service_ready", "inputServiceReady"), "input_service_ready"),
            restart_count=_bounded_int(_field(raw, "restart_count", "restartCount", 0), "restart_count", minimum=0, maximum=1_000_000),
            observed_at_epoch=_epoch(_field(raw, "observed_at_epoch", "observedAtEpoch"), "observed_at_epoch"),
        )

    def topology_hash(self) -> str:
        return stable_hash(
            {
                "imageDigest": self.image_digest,
                "runtimeSourceRevision": self.runtime_source_revision,
                "containerIdentityHash": self.container_identity_hash,
                "networkIdentityHash": self.network_identity_hash,
                "egressPolicyHash": self.egress_policy_hash,
                "mounts": [item.to_dict() for item in self.mounts],
                "privileged": self.privileged,
                "dockerSocketMounted": self.docker_socket_mounted,
                "hostNamespaces": self.host_namespaces,
                "noNewPrivileges": self.no_new_privileges,
                "capabilitiesDropped": self.capabilities_dropped,
                "readOnlyRootFilesystem": self.read_only_root_filesystem,
                "publicPortCount": self.public_port_count,
                "egressDefaultDeny": self.egress_default_deny,
                "llmRoutingPresent": self.llm_routing_present,
                "productionCredentialsPresent": self.production_credentials_present,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": DESKTOP_WORKER_READBACK_SCHEMA_VERSION,
            "runtimeIdentityHash": self.runtime_identity_hash,
            "containerIdentityHash": self.container_identity_hash,
            "imageDigest": self.image_digest,
            "runtimeSourceRevision": self.runtime_source_revision,
            "sessionBindingHash": self.session_binding_hash,
            "attemptId": self.attempt_id,
            "attemptHash": self.attempt_hash,
            "workspaceId": self.workspace_id,
            "worktreeIdentityHash": self.worktree_identity_hash,
            "observedHeadRevision": self.observed_head_revision,
            "inputScopeHash": self.input_scope_hash,
            "viewScopeHash": self.view_scope_hash,
            "networkIdentityHash": self.network_identity_hash,
            "egressPolicyHash": self.egress_policy_hash,
            "mounts": [item.to_dict() for item in self.mounts],
            "privileged": self.privileged,
            "dockerSocketMounted": self.docker_socket_mounted,
            "hostNamespaces": self.host_namespaces,
            "noNewPrivileges": self.no_new_privileges,
            "capabilitiesDropped": self.capabilities_dropped,
            "readOnlyRootFilesystem": self.read_only_root_filesystem,
            "publicPortCount": self.public_port_count,
            "egressDefaultDeny": self.egress_default_deny,
            "llmRoutingPresent": self.llm_routing_present,
            "productionCredentialsPresent": self.production_credentials_present,
            "lifecycleState": self.lifecycle_state,
            "streamReady": self.stream_ready,
            "inputServiceReady": self.input_service_ready,
            "restartCount": self.restart_count,
            "observedAtEpoch": self.observed_at_epoch,
            "topologyHash": self.topology_hash(),
            "authoritative": False,
        }


@dataclass(frozen=True)
class DesktopWorkerSensorReceiptV1:
    """Path-free host-sensor receipt for one readback and one live session.

    This is an integrity contract, not a substitute for the existing host-side
    PatchMon/Docker/OTBA verifier.  The production adapter must create this
    receipt only after that verifier has authenticated its source receipt.
    """

    source_kind: str
    source_receipt_hash: str
    readback_hash: str
    session_id: str
    session_binding_hash: str
    reconciliation_readback_hash: str
    source_revision: str
    observed_at_epoch: int
    sensor_receipt_hash: str

    @classmethod
    def from_verified_patchmon_docker(
        cls,
        *,
        session: LiveWorkspaceSessionV1,
        readback: DesktopWorkerReadbackV1,
        reconciliation: SessionReconciliationV1,
        source_receipt_hash: str,
        source_revision: str,
    ) -> "DesktopWorkerSensorReceiptV1":
        if (
            reconciliation.session_id != session.session_id
            or reconciliation.session_binding_hash != session.session_binding_hash
            or reconciliation.projection_state != "LIVE"
            or readback.session_binding_hash != session.session_binding_hash
        ):
            raise FleetContractError("desktop worker sensor receipt requires a fresh LIVE session reconciliation")
        revision = _revision(source_revision, "source_revision")
        if (
            revision != session.observed_head_revision
            or revision != readback.observed_head_revision
            or revision != readback.runtime_source_revision
        ):
            raise FleetContractError("desktop worker sensor source revision contradicts the observed runtime")
        payload = {
            "schemaVersion": DESKTOP_WORKER_SENSOR_RECEIPT_SCHEMA_VERSION,
            "sourceKind": "PATCHMON_DOCKER_OTBA",
            "sourceReceiptHash": _hash(source_receipt_hash, "source_receipt_hash"),
            "readbackHash": stable_hash(readback.to_dict()),
            "sessionId": _text(session.session_id, "session_id", maximum=160),
            "sessionBindingHash": readback.session_binding_hash,
            "reconciliationReadbackHash": _hash(reconciliation.fresh_readback_hash, "reconciliation.fresh_readback_hash"),
            "sourceRevision": revision,
            "observedAtEpoch": readback.observed_at_epoch,
        }
        receipt_hash = stable_hash(payload)
        return cls(
            source_kind=payload["sourceKind"],
            source_receipt_hash=payload["sourceReceiptHash"],
            readback_hash=payload["readbackHash"],
            session_id=payload["sessionId"],
            session_binding_hash=payload["sessionBindingHash"],
            reconciliation_readback_hash=payload["reconciliationReadbackHash"],
            source_revision=payload["sourceRevision"],
            observed_at_epoch=payload["observedAtEpoch"],
            sensor_receipt_hash=receipt_hash,
        )

    def _canonical_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": DESKTOP_WORKER_SENSOR_RECEIPT_SCHEMA_VERSION,
            "sourceKind": self.source_kind,
            "sourceReceiptHash": self.source_receipt_hash,
            "readbackHash": self.readback_hash,
            "sessionId": self.session_id,
            "sessionBindingHash": self.session_binding_hash,
            "reconciliationReadbackHash": self.reconciliation_readback_hash,
            "sourceRevision": self.source_revision,
            "observedAtEpoch": self.observed_at_epoch,
        }

    def is_self_consistent(self) -> bool:
        try:
            payload = {
                "schemaVersion": DESKTOP_WORKER_SENSOR_RECEIPT_SCHEMA_VERSION,
                "sourceKind": "PATCHMON_DOCKER_OTBA",
                "sourceReceiptHash": _hash(self.source_receipt_hash, "sensor.source_receipt_hash"),
                "readbackHash": _hash(self.readback_hash, "sensor.readback_hash"),
                "sessionId": _text(self.session_id, "sensor.session_id", maximum=160),
                "sessionBindingHash": _hash(self.session_binding_hash, "sensor.session_binding_hash"),
                "reconciliationReadbackHash": _hash(
                    self.reconciliation_readback_hash,
                    "sensor.reconciliation_readback_hash",
                ),
                "sourceRevision": _revision(self.source_revision, "sensor.source_revision"),
                "observedAtEpoch": _epoch(self.observed_at_epoch, "sensor.observed_at_epoch"),
            }
            return self.source_kind == "PATCHMON_DOCKER_OTBA" and self.sensor_receipt_hash == stable_hash(payload)
        except FleetContractError:
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._canonical_payload(),
            "sensorReceiptHash": self.sensor_receipt_hash,
            "authoritative": False,
        }


@dataclass(frozen=True)
class DesktopWorkerAdmissionV1:
    """A current, path-free admission for one exact bound desktop worker."""

    admission_id: str
    session_id: str
    session_binding_hash: str
    runtime_identity_hash: str
    container_identity_hash: str
    image_digest: str
    runtime_source_revision: str
    topology_hash: str
    network_identity_hash: str
    egress_policy_hash: str
    input_scope_hash: str
    view_scope_hash: str
    attempt_id: str
    attempt_hash: str
    workspace_id: str
    worktree_identity_hash: str
    observed_head_revision: str
    sensor_receipt_hash: str
    admitted_at_epoch: int

    @classmethod
    def admit(
        cls,
        *,
        session: LiveWorkspaceSessionV1,
        reconciliation: SessionReconciliationV1,
        runtime_contract: DesktopRuntimeContractV1 | Mapping[str, Any],
        readback: DesktopWorkerReadbackV1,
        sensor_receipt: DesktopWorkerSensorReceiptV1,
        expected_network_identity_hash: str,
        expected_egress_policy_hash: str,
        trusted_now_epoch: int,
    ) -> "DesktopWorkerAdmissionV1":
        contract = (
            runtime_contract
            if isinstance(runtime_contract, DesktopRuntimeContractV1)
            else DesktopRuntimeContractV1.from_dict(_mapping(runtime_contract, "desktop_runtime_contract"))
        )
        if not isinstance(readback, DesktopWorkerReadbackV1):
            raise FleetContractError("desktop worker admission requires a trusted typed Docker/PatchMon readback")
        if not isinstance(sensor_receipt, DesktopWorkerSensorReceiptV1):
            raise FleetContractError("desktop worker admission requires a trusted PatchMon/Docker sensor receipt")
        now = _epoch(trusted_now_epoch, "trusted_now_epoch")
        observed = readback
        if (
            reconciliation.session_id != session.session_id
            or reconciliation.session_binding_hash != session.session_binding_hash
            or reconciliation.projection_state != "LIVE"
        ):
            raise FleetContractError("desktop worker admission requires a fresh LIVE session reconciliation")
        if not sensor_receipt.is_self_consistent():
            raise FleetContractError("desktop worker PatchMon/Docker sensor receipt integrity is invalid")
        if (
            sensor_receipt.session_id != session.session_id
            or sensor_receipt.session_binding_hash != session.session_binding_hash
            or sensor_receipt.reconciliation_readback_hash != reconciliation.fresh_readback_hash
            or sensor_receipt.readback_hash != stable_hash(observed.to_dict())
            or sensor_receipt.source_revision != session.observed_head_revision
            or sensor_receipt.observed_at_epoch != observed.observed_at_epoch
        ):
            raise FleetContractError("desktop worker PatchMon/Docker sensor receipt is stale or contradictory")
        if observed.observed_at_epoch > now + 5 or now - observed.observed_at_epoch > MAX_DESKTOP_READBACK_AGE_SECONDS:
            raise FleetContractError("desktop worker readback is outside the trusted freshness window")
        if observed.restart_count != 0:
            raise FleetContractError("desktop worker restart requires a new isolated admission")
        if contract.input_scope_hash == contract.view_scope_hash or observed.input_scope_hash == observed.view_scope_hash:
            raise FleetContractError("desktop worker view and input scopes must remain distinct")
        if session.desktop_runtime_identity_hash != contract.runtime_identity_hash:
            raise FleetContractError("session runtime identity is not bound to the admitted desktop contract")
        if (
            observed.runtime_identity_hash != contract.runtime_identity_hash
            or observed.image_digest != contract.image_digest
            or observed.runtime_source_revision != session.observed_head_revision
            or observed.input_scope_hash != contract.input_scope_hash
            or observed.view_scope_hash != contract.view_scope_hash
        ):
            raise FleetContractError("desktop worker runtime readback contradicts its admitted contract")
        if (
            observed.session_binding_hash != session.session_binding_hash
            or observed.attempt_id != session.attempt_id
            or observed.attempt_hash != session.attempt_hash
            or observed.workspace_id != session.workspace_id
            or observed.worktree_identity_hash != session.worktree_identity_hash
            or observed.observed_head_revision != session.observed_head_revision
        ):
            raise FleetContractError("desktop worker readback is not bound to the active workspace session")
        if (
            observed.privileged
            or observed.docker_socket_mounted
            or observed.host_namespaces
            or not observed.no_new_privileges
            or not observed.capabilities_dropped
            or not observed.read_only_root_filesystem
        ):
            raise FleetContractError("desktop worker security readback is not hardened")
        if observed.public_port_count != 0 or not observed.egress_default_deny:
            raise FleetContractError("desktop worker network exposure is forbidden")
        if observed.llm_routing_present or observed.production_credentials_present:
            raise FleetContractError("desktop worker may not own LLM routing or production credentials")
        if not observed.stream_ready or not observed.input_service_ready:
            raise FleetContractError("desktop worker stream or bounded input service is unavailable")
        expected_network = _hash(expected_network_identity_hash, "expected_network_identity_hash")
        expected_egress = _hash(expected_egress_policy_hash, "expected_egress_policy_hash")
        if observed.network_identity_hash != expected_network or observed.egress_policy_hash != expected_egress:
            raise FleetContractError("desktop worker network or egress policy drifted")
        workspace_mounts = [item for item in observed.mounts if item.kind == "ATTEMPT_WORKSPACE"]
        tmpfs_mounts = [item for item in observed.mounts if item.kind == "TMPFS"]
        if len(workspace_mounts) != 1:
            raise FleetContractError("desktop worker requires exactly one attempt workspace mount")
        workspace_mount = workspace_mounts[0]
        if (
            workspace_mount.target != "/workspace"
            or workspace_mount.source_identity_hash != session.worktree_identity_hash
            or not workspace_mount.writable
        ):
            raise FleetContractError("desktop worker attempt workspace mount is invalid")
        if any(item.target not in _ALLOWED_TMPFS_TARGETS or not item.writable for item in tmpfs_mounts):
            raise FleetContractError("desktop worker tmpfs mount is invalid")
        if len(workspace_mounts) + len(tmpfs_mounts) != len(observed.mounts):
            raise FleetContractError("desktop worker has an unexpected mount")
        payload = {
            "schemaVersion": DESKTOP_WORKER_ADMISSION_SCHEMA_VERSION,
            "sessionId": session.session_id,
            "sessionBindingHash": session.session_binding_hash,
            "runtimeIdentityHash": observed.runtime_identity_hash,
            "containerIdentityHash": observed.container_identity_hash,
            "imageDigest": observed.image_digest,
            "runtimeSourceRevision": observed.runtime_source_revision,
            "topologyHash": observed.topology_hash(),
            "networkIdentityHash": observed.network_identity_hash,
            "egressPolicyHash": observed.egress_policy_hash,
            "inputScopeHash": observed.input_scope_hash,
            "viewScopeHash": observed.view_scope_hash,
            "attemptId": observed.attempt_id,
            "attemptHash": observed.attempt_hash,
            "workspaceId": observed.workspace_id,
            "worktreeIdentityHash": observed.worktree_identity_hash,
            "observedHeadRevision": observed.observed_head_revision,
            "sensorReceiptHash": sensor_receipt.sensor_receipt_hash,
            "admittedAtEpoch": observed.observed_at_epoch,
        }
        admission_hash = stable_hash(payload)
        return cls(
            admission_id=f"desktop-admission-{admission_hash[:24]}",
            session_id=payload["sessionId"],
            session_binding_hash=payload["sessionBindingHash"],
            runtime_identity_hash=payload["runtimeIdentityHash"],
            container_identity_hash=payload["containerIdentityHash"],
            image_digest=payload["imageDigest"],
            runtime_source_revision=payload["runtimeSourceRevision"],
            topology_hash=payload["topologyHash"],
            network_identity_hash=payload["networkIdentityHash"],
            egress_policy_hash=payload["egressPolicyHash"],
            input_scope_hash=payload["inputScopeHash"],
            view_scope_hash=payload["viewScopeHash"],
            attempt_id=payload["attemptId"],
            attempt_hash=payload["attemptHash"],
            workspace_id=payload["workspaceId"],
            worktree_identity_hash=payload["worktreeIdentityHash"],
            observed_head_revision=payload["observedHeadRevision"],
            sensor_receipt_hash=payload["sensorReceiptHash"],
            admitted_at_epoch=payload["admittedAtEpoch"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": DESKTOP_WORKER_ADMISSION_SCHEMA_VERSION,
            "admissionId": self.admission_id,
            "sessionId": self.session_id,
            "sessionBindingHash": self.session_binding_hash,
            "runtimeIdentityHash": self.runtime_identity_hash,
            "containerIdentityHash": self.container_identity_hash,
            "imageDigest": self.image_digest,
            "runtimeSourceRevision": self.runtime_source_revision,
            "topologyHash": self.topology_hash,
            "networkIdentityHash": self.network_identity_hash,
            "egressPolicyHash": self.egress_policy_hash,
            "inputScopeHash": self.input_scope_hash,
            "viewScopeHash": self.view_scope_hash,
            "attemptId": self.attempt_id,
            "attemptHash": self.attempt_hash,
            "workspaceId": self.workspace_id,
            "worktreeIdentityHash": self.worktree_identity_hash,
            "observedHeadRevision": self.observed_head_revision,
            "sensorReceiptHash": self.sensor_receipt_hash,
            "admittedAtEpoch": self.admitted_at_epoch,
            "authoritative": False,
            "status": "ADMITTED",
        }


def _valid_grant_window(*, issued_at_epoch: int, expires_at_epoch: int) -> None:
    if expires_at_epoch <= issued_at_epoch:
        raise FleetContractError("desktop grant expiration must follow issuance")
    if expires_at_epoch - issued_at_epoch < 30 or expires_at_epoch - issued_at_epoch > 900:
        raise FleetContractError("desktop grant lifetime must be between 30 and 900 seconds")


@dataclass(frozen=True)
class DesktopViewGatewayReadbackV1:
    """Independent, path-free readback for the authenticated view gateway."""

    gateway_runtime_identity_hash: str
    gateway_container_identity_hash: str
    image_digest: str
    session_id: str
    session_binding_hash: str
    admission_id: str
    runtime_identity_hash: str
    worker_container_identity_hash: str
    view_scope_hash: str
    attempt_id: str
    attempt_hash: str
    worktree_identity_hash: str
    observed_head_revision: str
    network_identity_hashes: tuple[str, ...]
    worker_backplane_network_identity_hash: str
    view_client_network_identity_hash: str
    egress_default_deny: bool
    networks_internal_only: bool
    privileged: bool
    docker_socket_mounted: bool
    host_namespaces: bool
    no_new_privileges: bool
    capabilities_dropped: bool
    read_only_root_filesystem: bool
    public_port_count: int
    workspace_mounted: bool
    control_socket_mounted: bool
    authenticated_stream_mode: bool
    lifecycle_state: str
    restart_count: int
    observed_at_epoch: int

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DesktopViewGatewayReadbackV1":
        raw = _mapping(value, "desktop_view_gateway_readback")
        networks = raw.get("networkIdentityHashes")
        if not isinstance(networks, Sequence) or isinstance(networks, (str, bytes, bytearray)):
            raise FleetContractError("desktop view gateway networks must be a list")
        network_hashes = tuple(sorted(dict.fromkeys(_hash(item, "gateway.networkIdentityHashes") for item in networks)))
        if len(network_hashes) != 2:
            raise FleetContractError("desktop view gateway requires exactly two private networks")
        worker_backplane_network_identity_hash = _hash(
            _field(raw, "worker_backplane_network_identity_hash", "workerBackplaneNetworkIdentityHash"),
            "gateway.worker_backplane_network_identity_hash",
        )
        view_client_network_identity_hash = _hash(
            _field(raw, "view_client_network_identity_hash", "viewClientNetworkIdentityHash"),
            "gateway.view_client_network_identity_hash",
        )
        if worker_backplane_network_identity_hash == view_client_network_identity_hash:
            raise FleetContractError("desktop view gateway requires separate private networks")
        if network_hashes != tuple(sorted({worker_backplane_network_identity_hash, view_client_network_identity_hash})):
            raise FleetContractError("desktop view gateway network identity readback is inconsistent")
        lifecycle_state = _text(_field(raw, "lifecycle_state", "lifecycleState"), "gateway.lifecycle_state", maximum=40).upper()
        if lifecycle_state != "RUNNING":
            raise FleetContractError("desktop view gateway must be observed running")
        admission_id = _text(_field(raw, "admission_id", "admissionId"), "gateway.admission_id", maximum=80)
        if not _ADMISSION_RE.fullmatch(admission_id):
            raise FleetContractError("desktop view gateway admission id is invalid")
        attempt_id = _text(_field(raw, "attempt_id", "attemptId"), "gateway.attempt_id", maximum=80)
        if not _ATTEMPT_RE.fullmatch(attempt_id):
            raise FleetContractError("desktop view gateway attempt id is invalid")
        return cls(
            gateway_runtime_identity_hash=_hash(_field(raw, "gateway_runtime_identity_hash", "gatewayRuntimeIdentityHash"), "gateway_runtime_identity_hash"),
            gateway_container_identity_hash=_hash(_field(raw, "gateway_container_identity_hash", "gatewayContainerIdentityHash"), "gateway_container_identity_hash"),
            image_digest=_image_digest(_field(raw, "image_digest", "imageDigest"), "gateway.image_digest"),
            session_id=_text(_field(raw, "session_id", "sessionId"), "gateway.session_id", maximum=160),
            session_binding_hash=_hash(_field(raw, "session_binding_hash", "sessionBindingHash"), "gateway.session_binding_hash"),
            admission_id=admission_id,
            runtime_identity_hash=_hash(_field(raw, "runtime_identity_hash", "runtimeIdentityHash"), "gateway.runtime_identity_hash"),
            worker_container_identity_hash=_hash(_field(raw, "worker_container_identity_hash", "workerContainerIdentityHash"), "gateway.worker_container_identity_hash"),
            view_scope_hash=_hash(_field(raw, "view_scope_hash", "viewScopeHash"), "gateway.view_scope_hash"),
            attempt_id=attempt_id,
            attempt_hash=_hash(_field(raw, "attempt_hash", "attemptHash"), "gateway.attempt_hash"),
            worktree_identity_hash=_hash(_field(raw, "worktree_identity_hash", "worktreeIdentityHash"), "gateway.worktree_identity_hash"),
            observed_head_revision=_revision(_field(raw, "observed_head_revision", "observedHeadRevision"), "gateway.observed_head_revision"),
            network_identity_hashes=network_hashes,
            worker_backplane_network_identity_hash=worker_backplane_network_identity_hash,
            view_client_network_identity_hash=view_client_network_identity_hash,
            egress_default_deny=_strict_bool(_field(raw, "egress_default_deny", "egressDefaultDeny"), "gateway.egress_default_deny"),
            networks_internal_only=_strict_bool(_field(raw, "networks_internal_only", "networksInternalOnly"), "gateway.networks_internal_only"),
            privileged=_strict_bool(raw.get("privileged"), "gateway.privileged"),
            docker_socket_mounted=_strict_bool(_field(raw, "docker_socket_mounted", "dockerSocketMounted"), "gateway.docker_socket_mounted"),
            host_namespaces=_strict_bool(_field(raw, "host_namespaces", "hostNamespaces"), "gateway.host_namespaces"),
            no_new_privileges=_strict_bool(_field(raw, "no_new_privileges", "noNewPrivileges"), "gateway.no_new_privileges"),
            capabilities_dropped=_strict_bool(_field(raw, "capabilities_dropped", "capabilitiesDropped"), "gateway.capabilities_dropped"),
            read_only_root_filesystem=_strict_bool(_field(raw, "read_only_root_filesystem", "readOnlyRootFilesystem"), "gateway.read_only_root_filesystem"),
            public_port_count=_bounded_int(_field(raw, "public_port_count", "publicPortCount", 0), "gateway.public_port_count", minimum=0, maximum=64),
            workspace_mounted=_strict_bool(_field(raw, "workspace_mounted", "workspaceMounted"), "gateway.workspace_mounted"),
            control_socket_mounted=_strict_bool(_field(raw, "control_socket_mounted", "controlSocketMounted"), "gateway.control_socket_mounted"),
            authenticated_stream_mode=_strict_bool(_field(raw, "authenticated_stream_mode", "authenticatedStreamMode"), "gateway.authenticated_stream_mode"),
            lifecycle_state=lifecycle_state,
            restart_count=_bounded_int(_field(raw, "restart_count", "restartCount", 0), "gateway.restart_count", minimum=0, maximum=1_000_000),
            observed_at_epoch=_epoch(_field(raw, "observed_at_epoch", "observedAtEpoch"), "gateway.observed_at_epoch"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "gatewayRuntimeIdentityHash": self.gateway_runtime_identity_hash,
            "gatewayContainerIdentityHash": self.gateway_container_identity_hash,
            "imageDigest": self.image_digest,
            "sessionId": self.session_id,
            "sessionBindingHash": self.session_binding_hash,
            "admissionId": self.admission_id,
            "runtimeIdentityHash": self.runtime_identity_hash,
            "workerContainerIdentityHash": self.worker_container_identity_hash,
            "viewScopeHash": self.view_scope_hash,
            "attemptId": self.attempt_id,
            "attemptHash": self.attempt_hash,
            "worktreeIdentityHash": self.worktree_identity_hash,
            "observedHeadRevision": self.observed_head_revision,
            "networkIdentityHashes": list(self.network_identity_hashes),
            "workerBackplaneNetworkIdentityHash": self.worker_backplane_network_identity_hash,
            "viewClientNetworkIdentityHash": self.view_client_network_identity_hash,
            "egressDefaultDeny": self.egress_default_deny,
            "networksInternalOnly": self.networks_internal_only,
            "privileged": self.privileged,
            "dockerSocketMounted": self.docker_socket_mounted,
            "hostNamespaces": self.host_namespaces,
            "noNewPrivileges": self.no_new_privileges,
            "capabilitiesDropped": self.capabilities_dropped,
            "readOnlyRootFilesystem": self.read_only_root_filesystem,
            "publicPortCount": self.public_port_count,
            "workspaceMounted": self.workspace_mounted,
            "controlSocketMounted": self.control_socket_mounted,
            "authenticatedStreamMode": self.authenticated_stream_mode,
            "lifecycleState": self.lifecycle_state,
            "restartCount": self.restart_count,
            "observedAtEpoch": self.observed_at_epoch,
            "authoritative": False,
        }


@dataclass(frozen=True)
class DesktopViewGrantV1:
    """Short-lived, gateway-bound view authority. No raw bearer token is serialised."""

    grant_id: str
    session_id: str
    session_binding_hash: str
    subject_hash: str
    view_scope_hash: str
    admission_id: str
    gateway_runtime_identity_hash: str
    gateway_container_identity_hash: str
    gateway_image_digest: str
    worker_backplane_network_identity_hash: str
    view_client_network_identity_hash: str
    issued_at_epoch: int
    expires_at_epoch: int

    @classmethod
    def issue(
        cls,
        *,
        session: LiveWorkspaceSessionV1,
        admission: DesktopWorkerAdmissionV1,
        gateway_readback: DesktopViewGatewayReadbackV1,
        expected_worker_backplane_network_identity_hash: str,
        expected_view_client_network_identity_hash: str,
        subject_hash: str,
        issued_at_epoch: int,
        expires_at_epoch: int,
        trusted_now_epoch: int,
    ) -> "DesktopViewGrantV1":
        issued = _epoch(issued_at_epoch, "issued_at_epoch")
        expires = _epoch(expires_at_epoch, "expires_at_epoch")
        now = _epoch(trusted_now_epoch, "trusted_now_epoch")
        _valid_grant_window(issued_at_epoch=issued, expires_at_epoch=expires)
        if not isinstance(gateway_readback, DesktopViewGatewayReadbackV1):
            raise FleetContractError("desktop view grant requires a typed authenticated gateway readback")
        expected_worker_backplane_network = _hash(
            expected_worker_backplane_network_identity_hash,
            "expected_worker_backplane_network_identity_hash",
        )
        expected_view_client_network = _hash(
            expected_view_client_network_identity_hash,
            "expected_view_client_network_identity_hash",
        )
        if expected_worker_backplane_network == expected_view_client_network:
            raise FleetContractError("desktop view grant requires separate expected private networks")
        if (
            admission.session_id != session.session_id
            or admission.session_binding_hash != session.session_binding_hash
            or gateway_readback.session_id != session.session_id
            or gateway_readback.session_binding_hash != session.session_binding_hash
            or gateway_readback.admission_id != admission.admission_id
            or gateway_readback.runtime_identity_hash != admission.runtime_identity_hash
            or gateway_readback.worker_container_identity_hash != admission.container_identity_hash
            or gateway_readback.image_digest != admission.image_digest
            or gateway_readback.view_scope_hash != admission.view_scope_hash
            or gateway_readback.attempt_id != admission.attempt_id
            or gateway_readback.attempt_hash != admission.attempt_hash
            or gateway_readback.worktree_identity_hash != admission.worktree_identity_hash
            or gateway_readback.observed_head_revision != admission.observed_head_revision
            or gateway_readback.worker_backplane_network_identity_hash != expected_worker_backplane_network
            or gateway_readback.view_client_network_identity_hash != expected_view_client_network
        ):
            raise FleetContractError("desktop view gateway is not bound to the current admission or expected private networks")
        if (
            gateway_readback.privileged
            or gateway_readback.docker_socket_mounted
            or gateway_readback.host_namespaces
            or not gateway_readback.no_new_privileges
            or not gateway_readback.capabilities_dropped
            or not gateway_readback.read_only_root_filesystem
            or gateway_readback.public_port_count != 0
            or not gateway_readback.egress_default_deny
            or not gateway_readback.networks_internal_only
            or gateway_readback.workspace_mounted
            or gateway_readback.control_socket_mounted
            or not gateway_readback.authenticated_stream_mode
            or gateway_readback.restart_count != 0
        ):
            raise FleetContractError("desktop view gateway security readback is not hardened")
        if (
            gateway_readback.observed_at_epoch > now + 5
            or now - gateway_readback.observed_at_epoch > MAX_DESKTOP_READBACK_AGE_SECONDS
        ):
            raise FleetContractError("desktop view gateway readback is outside the trusted freshness window")
        payload = {
            "schemaVersion": DESKTOP_VIEW_GRANT_SCHEMA_VERSION,
            "sessionId": session.session_id,
            "sessionBindingHash": session.session_binding_hash,
            "subjectHash": _hash(subject_hash, "subject_hash"),
            "viewScopeHash": admission.view_scope_hash,
            "admissionId": admission.admission_id,
            "gatewayRuntimeIdentityHash": gateway_readback.gateway_runtime_identity_hash,
            "gatewayContainerIdentityHash": gateway_readback.gateway_container_identity_hash,
            "gatewayImageDigest": gateway_readback.image_digest,
            "workerBackplaneNetworkIdentityHash": expected_worker_backplane_network,
            "viewClientNetworkIdentityHash": expected_view_client_network,
            "issuedAtEpoch": issued,
            "expiresAtEpoch": expires,
        }
        grant_hash = stable_hash(payload)
        return cls(
            grant_id=f"desktop-view-{grant_hash[:24]}",
            session_id=payload["sessionId"],
            session_binding_hash=payload["sessionBindingHash"],
            subject_hash=payload["subjectHash"],
            view_scope_hash=payload["viewScopeHash"],
            admission_id=payload["admissionId"],
            gateway_runtime_identity_hash=payload["gatewayRuntimeIdentityHash"],
            gateway_container_identity_hash=payload["gatewayContainerIdentityHash"],
            gateway_image_digest=payload["gatewayImageDigest"],
            worker_backplane_network_identity_hash=payload["workerBackplaneNetworkIdentityHash"],
            view_client_network_identity_hash=payload["viewClientNetworkIdentityHash"],
            issued_at_epoch=issued,
            expires_at_epoch=expires,
        )

    def is_valid_at(self, epoch: int) -> bool:
        current = _epoch(epoch, "grant_check_epoch")
        return self.issued_at_epoch <= current < self.expires_at_epoch

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": DESKTOP_VIEW_GRANT_SCHEMA_VERSION,
            "grantId": self.grant_id,
            "sessionId": self.session_id,
            "sessionBindingHash": self.session_binding_hash,
            "subjectHash": self.subject_hash,
            "viewScopeHash": self.view_scope_hash,
            "admissionId": self.admission_id,
            "gatewayRuntimeIdentityHash": self.gateway_runtime_identity_hash,
            "gatewayContainerIdentityHash": self.gateway_container_identity_hash,
            "gatewayImageDigest": self.gateway_image_digest,
            "workerBackplaneNetworkIdentityHash": self.worker_backplane_network_identity_hash,
            "viewClientNetworkIdentityHash": self.view_client_network_identity_hash,
            "issuedAtEpoch": self.issued_at_epoch,
            "expiresAtEpoch": self.expires_at_epoch,
            "access": "VIEW_ONLY",
            "authoritative": False,
            "rawTokenReturned": False,
        }


@dataclass(frozen=True)
class DesktopInputGrantV1:
    """Short-lived owner input authority tied to a fresh user-control lease."""

    grant_id: str
    session_binding_hash: str
    subject_hash: str
    input_scope_hash: str
    admission_id: str
    control_lease_id: str
    control_lease_readback_hash: str
    issued_at_epoch: int
    expires_at_epoch: int

    @classmethod
    def issue(
        cls,
        *,
        session: LiveWorkspaceSessionV1,
        admission: DesktopWorkerAdmissionV1,
        control_lease: LiveWorkspaceControlLeaseV1,
        issued_at_epoch: int,
        expires_at_epoch: int,
    ) -> "DesktopInputGrantV1":
        issued = _epoch(issued_at_epoch, "issued_at_epoch")
        expires = _epoch(expires_at_epoch, "expires_at_epoch")
        _valid_grant_window(issued_at_epoch=issued, expires_at_epoch=expires)
        if (
            admission.session_binding_hash != session.session_binding_hash
            or control_lease.session_binding_hash != session.session_binding_hash
            or control_lease.input_scope_hash != admission.input_scope_hash
            or control_lease.state != "USER_CONTROLLED"
        ):
            raise FleetContractError("desktop input grant requires the current user-control lease")
        payload = {
            "schemaVersion": DESKTOP_INPUT_GRANT_SCHEMA_VERSION,
            "sessionBindingHash": session.session_binding_hash,
            "subjectHash": control_lease.owner_subject_hash,
            "inputScopeHash": admission.input_scope_hash,
            "admissionId": admission.admission_id,
            "controlLeaseId": control_lease.lease_id,
            "controlLeaseReadbackHash": _hash(control_lease.issued_readback_hash, "control_lease.issued_readback_hash"),
            "issuedAtEpoch": issued,
            "expiresAtEpoch": expires,
        }
        grant_hash = stable_hash(payload)
        return cls(
            grant_id=f"desktop-input-{grant_hash[:24]}",
            session_binding_hash=payload["sessionBindingHash"],
            subject_hash=payload["subjectHash"],
            input_scope_hash=payload["inputScopeHash"],
            admission_id=payload["admissionId"],
            control_lease_id=payload["controlLeaseId"],
            control_lease_readback_hash=payload["controlLeaseReadbackHash"],
            issued_at_epoch=issued,
            expires_at_epoch=expires,
        )

    def is_valid_at(self, epoch: int) -> bool:
        current = _epoch(epoch, "grant_check_epoch")
        return self.issued_at_epoch <= current < self.expires_at_epoch

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": DESKTOP_INPUT_GRANT_SCHEMA_VERSION,
            "grantId": self.grant_id,
            "sessionBindingHash": self.session_binding_hash,
            "subjectHash": self.subject_hash,
            "inputScopeHash": self.input_scope_hash,
            "admissionId": self.admission_id,
            "controlLeaseId": self.control_lease_id,
            "controlLeaseReadbackHash": self.control_lease_readback_hash,
            "issuedAtEpoch": self.issued_at_epoch,
            "expiresAtEpoch": self.expires_at_epoch,
            "access": "BOUNDED_INPUT",
            "authoritative": False,
            "rawTokenReturned": False,
        }


def _only_keys(payload: Mapping[str, Any], allowed: set[str], field: str) -> None:
    if set(payload) - allowed:
        raise FleetContractError(f"{field} contains unsupported fields")


def _normalise_computer_payload(input_kind: str, value: Mapping[str, Any]) -> dict[str, Any]:
    if input_kind in _VIEW_INPUT_KINDS:
        _only_keys(value, set(), "computer use payload")
        return {}
    if input_kind == "POINTER_MOVE":
        _only_keys(value, {"x", "y"}, "computer use payload")
        return {"x": _normalised_float(value.get("x"), "x"), "y": _normalised_float(value.get("y"), "y")}
    if input_kind == "CLICK":
        _only_keys(value, {"x", "y", "button"}, "computer use payload")
        return {
            "x": _normalised_float(value.get("x"), "x"),
            "y": _normalised_float(value.get("y"), "y"),
            "button": _bounded_int(value.get("button", 1), "button", minimum=1, maximum=3),
        }
    if input_kind == "TYPE":
        _only_keys(value, {"text"}, "computer use payload")
        text = _text(value.get("text"), "text", maximum=2000)
        return {"text": text}
    if input_kind == "KEYPRESS":
        _only_keys(value, {"key"}, "computer use payload")
        key = _text(value.get("key"), "key", maximum=80)
        if not _KEYPRESS_RE.fullmatch(key):
            raise FleetContractError("keypress key is invalid")
        return {"key": key}
    if input_kind == "SCROLL":
        _only_keys(value, {"deltaX", "deltaY"}, "computer use payload")
        return {
            "deltaX": _bounded_int(value.get("deltaX", 0), "deltaX", minimum=-20, maximum=20),
            "deltaY": _bounded_int(value.get("deltaY", 0), "deltaY", minimum=-20, maximum=20),
        }
    if input_kind == "WINDOW_FOCUS":
        _only_keys(value, {"windowId"}, "computer use payload")
        window_id = _text(value.get("windowId"), "window_id", maximum=16).lower()
        if not _WINDOW_RE.fullmatch(window_id):
            raise FleetContractError("window_id is invalid")
        return {"windowId": window_id}
    raise FleetContractError("computer use input kind is forbidden")


@dataclass(frozen=True)
class ComputerUseRequestV1:
    """One bounded request created from authenticated server-side session data.

    Public serialisation intentionally omits the raw payload.  Delivery requires
    a second live reconciliation so a request created before GIVE BACK cannot be
    replayed as an input effect afterwards.
    """

    request_id: str
    session_id: str
    session_binding_hash: str
    admission_id: str
    grant_id: str
    subject_hash: str
    scope_hash: str
    runtime_identity_hash: str
    container_identity_hash: str
    image_digest: str
    attempt_id: str
    attempt_hash: str
    worktree_identity_hash: str
    observed_head_revision: str
    control_lease_id: str | None
    control_lease_readback_hash: str | None
    grant_expires_at_epoch: int
    action_id: str
    input_kind: str
    payload: Mapping[str, Any]
    payload_hash: str
    request_hash: str
    requested_at_epoch: int

    @classmethod
    def create(
        cls,
        *,
        session: LiveWorkspaceSessionV1,
        admission: DesktopWorkerAdmissionV1,
        grant: DesktopViewGrantV1 | DesktopInputGrantV1,
        subject_hash: str,
        reconciliation: SessionReconciliationV1 | None = None,
        control_lease: LiveWorkspaceControlLeaseV1 | None = None,
        action_id: str,
        input_kind: str,
        payload: Mapping[str, Any],
        requested_at_epoch: int,
    ) -> "ComputerUseRequestV1":
        requested = _epoch(requested_at_epoch, "requested_at_epoch")
        kind = _text(input_kind, "input_kind", maximum=80).upper()
        if kind not in COMPUTER_USE_INPUT_KINDS:
            raise FleetContractError("computer use input kind is unsupported")
        if not grant.is_valid_at(requested):
            raise FleetContractError("desktop grant is expired or not yet valid")
        caller_subject_hash = _hash(subject_hash, "subject_hash")
        if (
            admission.session_id != session.session_id
            or admission.session_binding_hash != session.session_binding_hash
            or grant.session_binding_hash != session.session_binding_hash
            or grant.admission_id != admission.admission_id
            or grant.subject_hash != caller_subject_hash
        ):
            raise FleetContractError("desktop grant is bound to another session, admission, or principal")
        control_lease_id: str | None = None
        control_lease_readback_hash: str | None = None
        if kind in _VIEW_INPUT_KINDS:
            if not isinstance(grant, DesktopViewGrantV1) or grant.view_scope_hash != admission.view_scope_hash:
                raise FleetContractError("view operations require the current view-only grant")
            scope_hash = grant.view_scope_hash
        else:
            if not isinstance(grant, DesktopInputGrantV1) or grant.input_scope_hash != admission.input_scope_hash:
                raise FleetContractError("input operations require the current bounded input grant")
            if (
                control_lease is None
                or reconciliation is None
                or reconciliation.session_id != session.session_id
                or reconciliation.session_binding_hash != session.session_binding_hash
                or reconciliation.projection_state != "LIVE"
                or control_lease.lease_id != grant.control_lease_id
                or control_lease.session_binding_hash != session.session_binding_hash
                or control_lease.owner_subject_hash != caller_subject_hash
                or control_lease.input_scope_hash != grant.input_scope_hash
                or control_lease.state != "USER_CONTROLLED"
                or control_lease.issued_readback_hash != grant.control_lease_readback_hash
                or reconciliation.fresh_readback_hash != control_lease.issued_readback_hash
            ):
                raise FleetContractError("input operations require the current live user-control lease and reconciliation")
            scope_hash = grant.input_scope_hash
            control_lease_id = grant.control_lease_id
            control_lease_readback_hash = grant.control_lease_readback_hash
        safe_payload = _normalise_computer_payload(kind, _mapping(payload, "computer_use_payload"))
        payload_hash = stable_hash({"inputKind": kind, "payload": safe_payload})
        raw_action_id = _text(action_id, "action_id", maximum=160)
        request_payload = {
            "schemaVersion": COMPUTER_USE_REQUEST_SCHEMA_VERSION,
            "sessionId": session.session_id,
            "sessionBindingHash": session.session_binding_hash,
            "admissionId": admission.admission_id,
            "grantId": grant.grant_id,
            "subjectHash": caller_subject_hash,
            "scopeHash": scope_hash,
            "runtimeIdentityHash": admission.runtime_identity_hash,
            "containerIdentityHash": admission.container_identity_hash,
            "imageDigest": admission.image_digest,
            "attemptId": session.attempt_id,
            "attemptHash": session.attempt_hash,
            "worktreeIdentityHash": session.worktree_identity_hash,
            "observedHeadRevision": session.observed_head_revision,
            "controlLeaseId": control_lease_id,
            "controlLeaseReadbackHash": control_lease_readback_hash,
            "grantExpiresAtEpoch": grant.expires_at_epoch,
            "actionId": raw_action_id,
            "inputKind": kind,
            "payloadHash": payload_hash,
            "requestedAtEpoch": requested,
        }
        request_hash = stable_hash(request_payload)
        return cls(
            request_id=f"computer-use-{request_hash[:24]}",
            session_id=request_payload["sessionId"],
            session_binding_hash=request_payload["sessionBindingHash"],
            admission_id=request_payload["admissionId"],
            grant_id=request_payload["grantId"],
            subject_hash=request_payload["subjectHash"],
            scope_hash=request_payload["scopeHash"],
            runtime_identity_hash=request_payload["runtimeIdentityHash"],
            container_identity_hash=request_payload["containerIdentityHash"],
            image_digest=request_payload["imageDigest"],
            attempt_id=request_payload["attemptId"],
            attempt_hash=request_payload["attemptHash"],
            worktree_identity_hash=request_payload["worktreeIdentityHash"],
            observed_head_revision=request_payload["observedHeadRevision"],
            control_lease_id=request_payload["controlLeaseId"],
            control_lease_readback_hash=request_payload["controlLeaseReadbackHash"],
            grant_expires_at_epoch=request_payload["grantExpiresAtEpoch"],
            action_id=request_payload["actionId"],
            input_kind=request_payload["inputKind"],
            payload=safe_payload,
            payload_hash=payload_hash,
            request_hash=request_hash,
            requested_at_epoch=requested,
        )

    def worker_payload(
        self,
        *,
        admission: DesktopWorkerAdmissionV1,
        reconciliation: SessionReconciliationV1,
        control_lease: LiveWorkspaceControlLeaseV1 | None = None,
        trusted_now_epoch: int,
    ) -> dict[str, Any]:
        """Internal, delivery-time payload; never return this to browser/UI code."""

        now = _epoch(trusted_now_epoch, "trusted_now_epoch")
        if (
            self.admission_id != admission.admission_id
            or self.session_id != admission.session_id
            or self.session_binding_hash != admission.session_binding_hash
            or self.runtime_identity_hash != admission.runtime_identity_hash
            or self.container_identity_hash != admission.container_identity_hash
            or self.image_digest != admission.image_digest
            or self.attempt_id != admission.attempt_id
            or self.attempt_hash != admission.attempt_hash
            or self.worktree_identity_hash != admission.worktree_identity_hash
            or self.observed_head_revision != admission.observed_head_revision
        ):
            raise FleetContractError("computer use request is not bound to the current admitted container")
        if (
            reconciliation.session_id != self.session_id
            or reconciliation.session_binding_hash != self.session_binding_hash
            or reconciliation.projection_state != "LIVE"
            or now < self.requested_at_epoch
            or now >= self.grant_expires_at_epoch
        ):
            raise FleetContractError("computer use delivery requires a fresh live reconciliation and unexpired grant")
        if self.input_kind in _EFFECT_INPUT_KINDS:
            if (
                control_lease is None
                or self.control_lease_id is None
                or self.control_lease_readback_hash is None
                or control_lease.lease_id != self.control_lease_id
                or control_lease.session_binding_hash != self.session_binding_hash
                or control_lease.owner_subject_hash != self.subject_hash
                or control_lease.input_scope_hash != self.scope_hash
                or control_lease.state != "USER_CONTROLLED"
                or control_lease.issued_readback_hash != self.control_lease_readback_hash
                or reconciliation.fresh_readback_hash != control_lease.issued_readback_hash
            ):
                raise FleetContractError("computer use input delivery requires the current user-control lease")
        elif self.control_lease_id is not None or self.control_lease_readback_hash is not None:
            raise FleetContractError("computer use view delivery may not carry input lease authority")
        return {
            "schemaVersion": COMPUTER_USE_REQUEST_SCHEMA_VERSION,
            "sessionId": self.session_id,
            "sessionBindingHash": self.session_binding_hash,
            "admissionId": self.admission_id,
            "grantId": self.grant_id,
            "subjectHash": self.subject_hash,
            "scopeHash": self.scope_hash,
            "requestHash": self.request_hash,
            "runtimeIdentityHash": self.runtime_identity_hash,
            "containerIdentityHash": self.container_identity_hash,
            "imageDigest": self.image_digest,
            "attemptId": self.attempt_id,
            "attemptHash": self.attempt_hash,
            "worktreeIdentityHash": self.worktree_identity_hash,
            "observedHeadRevision": self.observed_head_revision,
            "controlLeaseId": self.control_lease_id,
            "controlLeaseReadbackHash": self.control_lease_readback_hash,
            "grantExpiresAtEpoch": self.grant_expires_at_epoch,
            "actionId": self.action_id,
            "inputKind": self.input_kind,
            "payloadHash": self.payload_hash,
            "payload": dict(self.payload),
            "requestedAtEpoch": self.requested_at_epoch,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": COMPUTER_USE_REQUEST_SCHEMA_VERSION,
            "requestId": self.request_id,
            "sessionId": self.session_id,
            "sessionBindingHash": self.session_binding_hash,
            "admissionId": self.admission_id,
            "grantId": self.grant_id,
            "subjectHash": self.subject_hash,
            "scopeHash": self.scope_hash,
            "runtimeIdentityHash": self.runtime_identity_hash,
            "containerIdentityHash": self.container_identity_hash,
            "imageDigest": self.image_digest,
            "attemptId": self.attempt_id,
            "attemptHash": self.attempt_hash,
            "worktreeIdentityHash": self.worktree_identity_hash,
            "observedHeadRevision": self.observed_head_revision,
            "controlLeaseId": self.control_lease_id,
            "controlLeaseReadbackHash": self.control_lease_readback_hash,
            "grantExpiresAtEpoch": self.grant_expires_at_epoch,
            "actionId": self.action_id,
            "inputKind": self.input_kind,
            "payloadHash": self.payload_hash,
            "requestHash": self.request_hash,
            "requestedAtEpoch": self.requested_at_epoch,
            "rawPayloadReturned": False,
            "authoritative": False,
        }


@dataclass(frozen=True)
class ComputerUseObservationReceiptV1:
    """Bounded worker observation.  It can never claim target-effect verification."""

    receipt_id: str
    request_hash: str
    session_id: str
    session_binding_hash: str
    admission_id: str
    grant_id: str
    subject_hash: str
    scope_hash: str
    runtime_identity_hash: str
    container_identity_hash: str
    image_digest: str
    attempt_id: str
    attempt_hash: str
    worktree_identity_hash: str
    observed_head_revision: str
    input_kind: str
    status: str
    observation_hash: str | None
    observed_at_epoch: int
    receipt_hash: str

    @classmethod
    def from_worker(
        cls,
        *,
        request: ComputerUseRequestV1,
        admission: DesktopWorkerAdmissionV1,
        worker_response: Mapping[str, Any],
    ) -> "ComputerUseObservationReceiptV1":
        if (
            request.session_id != admission.session_id
            or request.session_binding_hash != admission.session_binding_hash
            or request.admission_id != admission.admission_id
            or request.runtime_identity_hash != admission.runtime_identity_hash
            or request.container_identity_hash != admission.container_identity_hash
            or request.image_digest != admission.image_digest
            or request.attempt_id != admission.attempt_id
            or request.attempt_hash != admission.attempt_hash
            or request.worktree_identity_hash != admission.worktree_identity_hash
            or request.observed_head_revision != admission.observed_head_revision
        ):
            raise FleetContractError("computer use request is not bound to the receipt admission")
        raw = _mapping(worker_response, "desktop worker response")
        status = _text(raw.get("status"), "desktop worker receipt status", maximum=32).upper()
        if status == "VERIFIED" or status not in _WORKER_RECEIPT_STATUSES:
            raise FleetContractError("desktop worker may not claim verification")
        if request.input_kind in _VIEW_INPUT_KINDS:
            allowed_statuses = {"OBSERVED", "BLOCKED", "UNKNOWN"}
        else:
            allowed_statuses = {"SENT", "BLOCKED", "UNKNOWN"}
        if status not in allowed_statuses:
            raise FleetContractError("desktop worker receipt status contradicts its bounded input kind")
        expected_text = {
            "session_id": (("session_id", "sessionId"), request.session_id),
            "admission_id": (("admission_id", "admissionId"), request.admission_id),
            "grant_id": (("grant_id", "grantId"), request.grant_id),
            "subject_hash": (("subject_hash", "subjectHash"), request.subject_hash),
            "scope_hash": (("scope_hash", "scopeHash"), request.scope_hash),
            "image_digest": (("image_digest", "imageDigest"), request.image_digest),
            "attempt_id": (("attempt_id", "attemptId"), request.attempt_id),
            "observed_head_revision": (("observed_head_revision", "observedHeadRevision"), request.observed_head_revision),
        }
        for field, ((snake, camel), expected) in expected_text.items():
            if _text(_field(raw, snake, camel), field, maximum=320) != expected:
                raise FleetContractError("desktop worker response binding is inconsistent")
        expected_hash = {
            "request_hash": (("request_hash", "requestHash"), request.request_hash),
            "session_binding_hash": (("session_binding_hash", "sessionBindingHash"), request.session_binding_hash),
            "runtime_identity_hash": (("runtime_identity_hash", "runtimeIdentityHash"), request.runtime_identity_hash),
            "container_identity_hash": (("container_identity_hash", "containerIdentityHash"), request.container_identity_hash),
            "attempt_hash": (("attempt_hash", "attemptHash"), request.attempt_hash),
            "worktree_identity_hash": (("worktree_identity_hash", "worktreeIdentityHash"), request.worktree_identity_hash),
        }
        for field, ((snake, camel), expected) in expected_hash.items():
            if _hash(_field(raw, snake, camel), field) != expected:
                raise FleetContractError("desktop worker response binding is inconsistent")
        if _text(_field(raw, "input_kind", "inputKind"), "input_kind", maximum=80).upper() != request.input_kind:
            raise FleetContractError("desktop worker response input kind is inconsistent")
        raw_observation = str(_field(raw, "observation_hash", "observationHash", "") or "").strip()
        observation_hash = _hash(raw_observation, "observation_hash") if raw_observation else None
        observed_at = _epoch(_field(raw, "observed_at_epoch", "observedAtEpoch"), "observed_at_epoch")
        if observed_at < request.requested_at_epoch or observed_at >= request.grant_expires_at_epoch:
            raise FleetContractError("desktop worker response time is outside the request grant window")
        payload = {
            "schemaVersion": COMPUTER_USE_RECEIPT_SCHEMA_VERSION,
            "requestHash": request.request_hash,
            "sessionId": request.session_id,
            "sessionBindingHash": request.session_binding_hash,
            "admissionId": request.admission_id,
            "grantId": request.grant_id,
            "subjectHash": request.subject_hash,
            "scopeHash": request.scope_hash,
            "runtimeIdentityHash": request.runtime_identity_hash,
            "containerIdentityHash": request.container_identity_hash,
            "imageDigest": request.image_digest,
            "attemptId": request.attempt_id,
            "attemptHash": request.attempt_hash,
            "worktreeIdentityHash": request.worktree_identity_hash,
            "observedHeadRevision": request.observed_head_revision,
            "inputKind": request.input_kind,
            "status": status,
            "observationHash": observation_hash,
            "observedAtEpoch": observed_at,
        }
        receipt_hash = stable_hash(payload)
        return cls(
            receipt_id=f"computer-observation-{receipt_hash[:24]}",
            request_hash=payload["requestHash"],
            session_id=payload["sessionId"],
            session_binding_hash=payload["sessionBindingHash"],
            admission_id=payload["admissionId"],
            grant_id=payload["grantId"],
            subject_hash=payload["subjectHash"],
            scope_hash=payload["scopeHash"],
            runtime_identity_hash=payload["runtimeIdentityHash"],
            container_identity_hash=payload["containerIdentityHash"],
            image_digest=payload["imageDigest"],
            attempt_id=payload["attemptId"],
            attempt_hash=payload["attemptHash"],
            worktree_identity_hash=payload["worktreeIdentityHash"],
            observed_head_revision=payload["observedHeadRevision"],
            input_kind=payload["inputKind"],
            status=payload["status"],
            observation_hash=payload["observationHash"],
            observed_at_epoch=payload["observedAtEpoch"],
            receipt_hash=receipt_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": COMPUTER_USE_RECEIPT_SCHEMA_VERSION,
            "receiptId": self.receipt_id,
            "requestHash": self.request_hash,
            "sessionId": self.session_id,
            "sessionBindingHash": self.session_binding_hash,
            "admissionId": self.admission_id,
            "grantId": self.grant_id,
            "subjectHash": self.subject_hash,
            "scopeHash": self.scope_hash,
            "runtimeIdentityHash": self.runtime_identity_hash,
            "containerIdentityHash": self.container_identity_hash,
            "imageDigest": self.image_digest,
            "attemptId": self.attempt_id,
            "attemptHash": self.attempt_hash,
            "worktreeIdentityHash": self.worktree_identity_hash,
            "observedHeadRevision": self.observed_head_revision,
            "inputKind": self.input_kind,
            "status": self.status,
            "observationHash": self.observation_hash,
            "observedAtEpoch": self.observed_at_epoch,
            "receiptHash": self.receipt_hash,
            "authoritative": False,
            "targetEffectVerified": False,
        }


__all__ = [
    "COMPUTER_USE_INPUT_KINDS",
    "COMPUTER_USE_RECEIPT_SCHEMA_VERSION",
    "COMPUTER_USE_REQUEST_SCHEMA_VERSION",
    "DESKTOP_INPUT_GRANT_SCHEMA_VERSION",
    "DESKTOP_VIEW_GRANT_SCHEMA_VERSION",
    "DESKTOP_WORKER_ADMISSION_SCHEMA_VERSION",
    "DESKTOP_WORKER_READBACK_SCHEMA_VERSION",
    "DESKTOP_WORKER_SENSOR_RECEIPT_SCHEMA_VERSION",
    "MAX_DESKTOP_READBACK_AGE_SECONDS",
    "ComputerUseObservationReceiptV1",
    "ComputerUseRequestV1",
    "DesktopInputGrantV1",
    "DesktopViewGatewayReadbackV1",
    "DesktopViewGrantV1",
    "DesktopWorkerAdmissionV1",
    "DesktopWorkerMountV1",
    "DesktopWorkerReadbackV1",
    "DesktopWorkerSensorReceiptV1",
]
