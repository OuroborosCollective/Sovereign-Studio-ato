"""Fail-closed, rebuildable Live Workspace contracts for issues #1616–#1622.

The monitor is an observation surface only.  This module is intentionally pure: it
never creates a worktree, starts a container, writes a database, executes a command,
or upgrades a verification verdict.  Callers must provide fresh canonical assignment,
attempt, worktree, Git and runtime readbacks for every bind or reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence

from .fleet_attempts import FleetWorkerAttempt, require_active_attempt
from .fleet_supervisor import FleetContractError, FleetWorkerAssignment, stable_hash


LIVE_WORKSPACE_SCHEMA_VERSION = "sovereign.live-workspace-session.v1"
VISUAL_PROJECTION_SCHEMA_VERSION = "sovereign.visual-projection-event.v1"
EVIDENCE_ANCHOR_SCHEMA_VERSION = "sovereign.workspace-evidence-anchor.v1"
CONTROL_LEASE_SCHEMA_VERSION = "sovereign.live-workspace-control-lease.v1"
CHAT_BUBBLE_SCHEMA_VERSION = "sovereign.live-workspace-chat-bubble.v1"
DESKTOP_RUNTIME_SCHEMA_VERSION = "sovereign.desktop-runtime-contract.v1"

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SESSION_ID_RE = re.compile(r"^livews-[0-9a-f]{24}$")
_LEASE_ID_RE = re.compile(r"^livelease-[0-9a-f]{24}$")
_SECRET_MARKERS = (
    "sk-proj-",
    "github_pat_",
    "ghp_",
    "authorization: bearer",
    "begin openssh private key",
    "begin rsa private key",
    "begin private key",
)

PROJECTION_STATES = frozenset({"CONNECTING", "LIVE", "STALE", "DISCONNECTED", "BLOCKED"})
VISUAL_PROJECTION_SOURCE_KINDS = frozenset({"MCP", "REPOSITORY", "GIT", "PROCESS", "PLAYWRIGHT", "RUNTIME", "GUI"})
VISUAL_PROJECTION_KINDS = frozenset({"IDE_FILE", "IDE_DIFF", "TERMINAL", "BROWSER", "WINDOW_FOCUS"})
VISUAL_PROJECTION_STATES = frozenset({"REQUESTED", "VISIBLE", "UNAVAILABLE", "STALE"})
OBSERVATION_EVENT_TYPES = frozenset({
    "WORKSPACE_STREAM_CONNECTED",
    "WINDOW_FOCUSED",
    "FILE_VIEW_PROJECTED",
    "TERMINAL_VIEW_PROJECTED",
    "BROWSER_VIEW_PROJECTED",
    "FRAME_OBSERVED",
    "USER_TAKEOVER_STARTED",
    "USER_TAKEOVER_ENDED",
    "STREAM_DISCONNECTED",
    "NO_VISUAL_PROJECTION_AVAILABLE",
})
CONTROL_STATES = frozenset({
    "WATCH_AGENT_CONTROLLED",
    "TAKEOVER_REQUESTED",
    "USER_CONTROLLED",
    "GIVE_BACK_REQUESTED",
    "READBACK_REQUIRED",
    "AGENT_CONTROLLED_REBOUND",
    "BLOCKED_STALE_STATE",
    "SESSION_TERMINAL",
})
EVIDENCE_VERDICTS = frozenset({"OBSERVED", "UNVERIFIED", "VERIFIED", "BLOCKED", "CONTRADICTED", "STALE"})
EVIDENCE_SOURCE_KINDS = frozenset({
    "AGENT_RUN_RECEIPT",
    "GITHUB_READBACK",
    "PATCHMON_READBACK",
    "DATABASE_READBACK",
    "TARGET_READBACK",
    "FRAME_OBSERVATION",
})
_FORBIDDEN_EVIDENCE_CLAIMS = frozenset({"EVERYTHING_WORKS", "READY", "DONE", "GREEN", "ALL_GREEN"})
CHAT_BUBBLE_KINDS = frozenset({
    "MISSION_INPUT",
    "REQUIRED_QUESTION",
    "OWNER_CONSENT_REQUEST",
    "MATERIAL_BLOCKER",
    "FINAL_RESULT",
})


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _text(value: object, field: str, maximum: int = 320, *, allow_empty: bool = False) -> str:
    normalized = str(value or "").strip()
    if (not normalized and not allow_empty) or len(normalized) > maximum:
        raise FleetContractError(f"{field} is invalid")
    if any(marker in normalized.casefold() for marker in _SECRET_MARKERS):
        raise FleetContractError(f"{field} contains secret-shaped material")
    return normalized


def _hash(value: object, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _HASH_RE.fullmatch(normalized):
        raise FleetContractError(f"{field} must be an exact SHA-256 value")
    return normalized


def _revision(value: object, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _REVISION_RE.fullmatch(normalized):
        raise FleetContractError(f"{field} must be an exact 40-character revision")
    return normalized


def _bounded_hashes(value: object, field: str, *, maximum: int = 32) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise FleetContractError(f"{field} must be a list")
    if len(value) > maximum:
        raise FleetContractError(f"{field} exceeds its bounded item limit")
    return tuple(sorted(dict.fromkeys(_hash(item, field) for item in value)))


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FleetContractError(f"{field} must be an object")
    return value


def _field(value: Mapping[str, Any], snake: str, camel: str, default: object = None) -> object:
    return value[snake] if snake in value else value.get(camel, default)


@dataclass(frozen=True)
class WorkspaceReadbackV1:
    """Fresh server-side readback of an existing attempt workspace, never client input."""

    repository: str
    workspace_id: str
    worktree_identity_hash: str
    observed_head_revision: str
    fleet_plan_hash: str
    controller_state_ref: str
    controller_state: str
    workspace_path_owner: str
    desktop_runtime_identity_hash: str | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkspaceReadbackV1":
        raw = _mapping(value, "workspace_readback")
        repository = _text(raw.get("repository"), "repository", 160)
        if not _REPOSITORY_RE.fullmatch(repository):
            raise FleetContractError("repository is invalid")
        runtime_identity = str(
            _field(raw, "desktop_runtime_identity_hash", "desktopRuntimeIdentityHash", "") or ""
        ).strip().lower()
        if runtime_identity:
            runtime_identity = _hash(runtime_identity, "desktop_runtime_identity_hash")
        state = _text(_field(raw, "controller_state", "controllerState"), "controller_state", 80).upper()
        return cls(
            repository=repository,
            workspace_id=_text(_field(raw, "workspace_id", "workspaceId"), "workspace_id", 160),
            worktree_identity_hash=_hash(_field(raw, "worktree_identity_hash", "worktreeIdentityHash"), "worktree_identity_hash"),
            observed_head_revision=_revision(_field(raw, "observed_head_revision", "observedHeadRevision"), "observed_head_revision"),
            fleet_plan_hash=_hash(_field(raw, "fleet_plan_hash", "fleetPlanHash"), "fleet_plan_hash"),
            controller_state_ref=_hash(_field(raw, "controller_state_ref", "controllerStateRef"), "controller_state_ref"),
            controller_state=state,
            workspace_path_owner=_text(_field(raw, "workspace_path_owner", "workspacePathOwner"), "workspace_path_owner", 160),
            desktop_runtime_identity_hash=runtime_identity or None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "workspaceId": self.workspace_id,
            "worktreeIdentityHash": self.worktree_identity_hash,
            "observedHeadRevision": self.observed_head_revision,
            "fleetPlanHash": self.fleet_plan_hash,
            "controllerStateRef": self.controller_state_ref,
            "controllerState": self.controller_state,
            "workspacePathOwner": self.workspace_path_owner,
            "desktopRuntimeIdentityHash": self.desktop_runtime_identity_hash,
        }


@dataclass(frozen=True)
class DesktopRuntimeContractV1:
    """Admission contract for an optional desktop worker; it grants no success authority."""

    runtime_identity_hash: str
    image_digest: str
    privileged: bool
    docker_socket_mounted: bool
    host_namespaces: bool
    no_new_privileges: bool
    capabilities_dropped: bool
    read_only_root_filesystem: bool
    workspace_id: str
    input_scope_hash: str
    view_scope_hash: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DesktopRuntimeContractV1":
        raw = _mapping(value, "desktop_runtime_contract")
        image_digest = _text(_field(raw, "image_digest", "imageDigest"), "image_digest", 80)
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest.lower()):
            raise FleetContractError("image_digest must be immutable")
        result = cls(
            runtime_identity_hash=_hash(_field(raw, "runtime_identity_hash", "runtimeIdentityHash"), "runtime_identity_hash"),
            image_digest=image_digest.lower(),
            privileged=bool(raw.get("privileged")),
            docker_socket_mounted=bool(_field(raw, "docker_socket_mounted", "dockerSocketMounted")),
            host_namespaces=bool(_field(raw, "host_namespaces", "hostNamespaces")),
            no_new_privileges=bool(_field(raw, "no_new_privileges", "noNewPrivileges")),
            capabilities_dropped=bool(_field(raw, "capabilities_dropped", "capabilitiesDropped")),
            read_only_root_filesystem=bool(_field(raw, "read_only_root_filesystem", "readOnlyRootFilesystem")),
            workspace_id=_text(_field(raw, "workspace_id", "workspaceId"), "workspace_id", 160),
            input_scope_hash=_hash(_field(raw, "input_scope_hash", "inputScopeHash"), "input_scope_hash"),
            view_scope_hash=_hash(_field(raw, "view_scope_hash", "viewScopeHash"), "view_scope_hash"),
        )
        if result.privileged or result.docker_socket_mounted or result.host_namespaces:
            raise FleetContractError("desktop runtime host authority is forbidden")
        if not result.no_new_privileges or not result.capabilities_dropped or not result.read_only_root_filesystem:
            raise FleetContractError("desktop runtime hardening is incomplete")
        if result.input_scope_hash == result.view_scope_hash:
            raise FleetContractError("desktop view and input scopes must be distinct")
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": DESKTOP_RUNTIME_SCHEMA_VERSION,
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
            "authoritative": False,
        }


@dataclass(frozen=True)
class LiveWorkspaceSessionV1:
    """A deterministic projection binding; not an execution, repository or evidence owner."""

    session_id: str
    repository: str
    run_id: str
    task_id: str
    assignment_hash: str
    attempt_id: str
    attempt_sequence: int
    attempt_hash: str
    workspace_id: str
    worktree_identity_hash: str
    expected_base_revision: str
    observed_head_revision: str
    fleet_plan_hash: str
    capability_manifest_hash: str
    controller_state_ref: str
    desktop_runtime_identity_hash: str | None
    projection_source_hashes: tuple[str, ...]
    projection_state: str
    session_binding_hash: str

    def _payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": LIVE_WORKSPACE_SCHEMA_VERSION,
            "repository": self.repository,
            "runId": self.run_id,
            "taskId": self.task_id,
            "assignmentHash": self.assignment_hash,
            "attemptId": self.attempt_id,
            "attemptSequence": self.attempt_sequence,
            "attemptHash": self.attempt_hash,
            "workspaceId": self.workspace_id,
            "worktreeIdentityHash": self.worktree_identity_hash,
            "expectedBaseRevision": self.expected_base_revision,
            "observedHeadRevision": self.observed_head_revision,
            "fleetPlanHash": self.fleet_plan_hash,
            "capabilityManifestHash": self.capability_manifest_hash,
            "controllerStateRef": self.controller_state_ref,
            "desktopRuntimeIdentityHash": self.desktop_runtime_identity_hash,
            "projectionSourceHashes": list(self.projection_source_hashes),
        }

    @classmethod
    def bind(
        cls,
        *,
        assignment: FleetWorkerAssignment | Mapping[str, Any],
        attempt: FleetWorkerAttempt | Mapping[str, Any],
        active_attempt: FleetWorkerAttempt | Mapping[str, Any],
        workspace_readback: WorkspaceReadbackV1 | Mapping[str, Any],
        projection_source_hashes: Sequence[str],
        desktop_runtime: DesktopRuntimeContractV1 | Mapping[str, Any] | None = None,
    ) -> "LiveWorkspaceSessionV1":
        selected_assignment = assignment if isinstance(assignment, FleetWorkerAssignment) else _assignment_from_dict(assignment)
        selected_attempt = require_active_attempt(attempt, active_attempt, selected_assignment)
        readback = workspace_readback if isinstance(workspace_readback, WorkspaceReadbackV1) else WorkspaceReadbackV1.from_dict(workspace_readback)
        expected_head = selected_assignment.expected_head_revision or selected_assignment.expected_base_revision
        if readback.workspace_id != selected_assignment.workspace_id:
            raise FleetContractError("workspace readback is not bound to assignment workspace")
        if readback.fleet_plan_hash != selected_assignment.plan_hash:
            raise FleetContractError("workspace readback is not bound to fleet plan")
        if readback.observed_head_revision != expected_head:
            raise FleetContractError("workspace readback head does not match the active attempt")
        if readback.controller_state not in {"RUNNING", "VERIFYING"}:
            raise FleetContractError("controller state is not live-bindable")
        if readback.workspace_path_owner != selected_assignment.workspace_id:
            raise FleetContractError("workspace path owner is not the bound assignment workspace")
        runtime: DesktopRuntimeContractV1 | None = None
        if desktop_runtime is not None:
            runtime = desktop_runtime if isinstance(desktop_runtime, DesktopRuntimeContractV1) else DesktopRuntimeContractV1.from_dict(desktop_runtime)
            if runtime.workspace_id != selected_assignment.workspace_id:
                raise FleetContractError("desktop runtime workspace does not match assignment")
            if readback.desktop_runtime_identity_hash != runtime.runtime_identity_hash:
                raise FleetContractError("desktop runtime identity readback does not match admitted runtime")
        elif readback.desktop_runtime_identity_hash:
            raise FleetContractError("desktop runtime identity requires an admitted desktop runtime contract")
        source_hashes = _bounded_hashes(projection_source_hashes, "projection_source_hashes")
        if not source_hashes:
            raise FleetContractError("projection source receipts are required")
        payload = {
            "schemaVersion": LIVE_WORKSPACE_SCHEMA_VERSION,
            "repository": readback.repository,
            "runId": selected_assignment.controller_run_id,
            "taskId": selected_assignment.task_id,
            "assignmentHash": selected_assignment.assignment_hash,
            "attemptId": selected_attempt.attempt_id,
            "attemptSequence": selected_attempt.attempt_sequence,
            "attemptHash": selected_attempt.attempt_hash,
            "workspaceId": selected_assignment.workspace_id,
            "worktreeIdentityHash": readback.worktree_identity_hash,
            "expectedBaseRevision": selected_assignment.expected_base_revision,
            "observedHeadRevision": readback.observed_head_revision,
            "fleetPlanHash": selected_assignment.plan_hash,
            "capabilityManifestHash": selected_assignment.capability_manifest_hash,
            "controllerStateRef": readback.controller_state_ref,
            "desktopRuntimeIdentityHash": readback.desktop_runtime_identity_hash,
            "projectionSourceHashes": list(source_hashes),
        }
        binding_hash = stable_hash(payload)
        return cls(
            session_id=f"livews-{binding_hash[:24]}",
            repository=payload["repository"],
            run_id=payload["runId"],
            task_id=payload["taskId"],
            assignment_hash=payload["assignmentHash"],
            attempt_id=payload["attemptId"],
            attempt_sequence=payload["attemptSequence"],
            attempt_hash=payload["attemptHash"],
            workspace_id=payload["workspaceId"],
            worktree_identity_hash=payload["worktreeIdentityHash"],
            expected_base_revision=payload["expectedBaseRevision"],
            observed_head_revision=payload["observedHeadRevision"],
            fleet_plan_hash=payload["fleetPlanHash"],
            capability_manifest_hash=payload["capabilityManifestHash"],
            controller_state_ref=payload["controllerStateRef"],
            desktop_runtime_identity_hash=payload["desktopRuntimeIdentityHash"],
            projection_source_hashes=source_hashes,
            projection_state="LIVE",
            session_binding_hash=binding_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._payload(),
            "sessionId": self.session_id,
            "projectionState": self.projection_state,
            "sessionBindingHash": self.session_binding_hash,
            "authoritative": False,
            "rebuildable": True,
        }

    def reconcile(
        self,
        *,
        active_attempt: FleetWorkerAttempt | Mapping[str, Any],
        workspace_readback: WorkspaceReadbackV1 | Mapping[str, Any],
    ) -> "SessionReconciliationV1":
        current_attempt = active_attempt if isinstance(active_attempt, FleetWorkerAttempt) else FleetWorkerAttempt.from_dict(active_attempt)
        current = workspace_readback if isinstance(workspace_readback, WorkspaceReadbackV1) else WorkspaceReadbackV1.from_dict(workspace_readback)
        mismatches: list[str] = []
        if current_attempt.attempt_id != self.attempt_id or current_attempt.attempt_hash != self.attempt_hash:
            mismatches.append("ACTIVE_ATTEMPT_CHANGED")
        if current_attempt.assignment_hash != self.assignment_hash:
            mismatches.append("ASSIGNMENT_CHANGED")
        if current.workspace_id != self.workspace_id or current.workspace_path_owner != self.workspace_id:
            mismatches.append("WORKSPACE_CHANGED")
        if current.worktree_identity_hash != self.worktree_identity_hash:
            mismatches.append("WORKTREE_CHANGED")
        if current.observed_head_revision != self.observed_head_revision:
            mismatches.append("GIT_HEAD_CHANGED")
        if current.fleet_plan_hash != self.fleet_plan_hash:
            mismatches.append("FLEET_PLAN_CHANGED")
        if current.controller_state_ref != self.controller_state_ref or current.controller_state not in {"RUNNING", "VERIFYING"}:
            mismatches.append("CONTROLLER_STATE_CHANGED")
        if current.desktop_runtime_identity_hash != self.desktop_runtime_identity_hash:
            mismatches.append("DESKTOP_RUNTIME_CHANGED")
        return SessionReconciliationV1(
            session_id=self.session_id,
            session_binding_hash=self.session_binding_hash,
            projection_state="LIVE" if not mismatches else "STALE",
            blockers=tuple(sorted(mismatches)),
            fresh_readback_hash=stable_hash(current.to_dict()),
        )


@dataclass(frozen=True)
class SessionReconciliationV1:
    session_id: str
    session_binding_hash: str
    projection_state: str
    blockers: tuple[str, ...]
    fresh_readback_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": LIVE_WORKSPACE_SCHEMA_VERSION,
            "sessionId": self.session_id,
            "sessionBindingHash": self.session_binding_hash,
            "projectionState": self.projection_state,
            "blockers": list(self.blockers),
            "freshReadbackHash": self.fresh_readback_hash,
            "authoritative": False,
        }


@dataclass(frozen=True)
class VisualProjectionEventV1:
    """Canonical non-authoritative visual observation bound to one LiveWorkspaceSession.

    Rich IDE/terminal/browser correlation fields are additive to the original
    observation contract. They never create execution or evidence authority.
    """

    event_id: str
    event_type: str
    session_id: str
    session_binding_hash: str
    attempt_id: str
    action_id: str
    observation_hash: str
    run_id: str = ""
    task_id: str = ""
    workspace_id: str = ""
    source_kind: str = ""
    projection_kind: str = ""
    projection_state: str = ""
    repository_head: str | None = None
    source_receipt_ref: str = ""
    source_identity_hash: str = ""
    projection_hash: str = ""
    payload: Mapping[str, Any] | None = None

    @classmethod
    def create(
        cls,
        *,
        session: LiveWorkspaceSessionV1,
        event_type: str,
        action_id: str,
        observation_hash: str,
    ) -> "VisualProjectionEventV1":
        normalized_type = _text(event_type, "event_type", 120).upper()
        if normalized_type not in OBSERVATION_EVENT_TYPES:
            raise FleetContractError("unknown visual projection event")
        payload = {
            "schemaVersion": VISUAL_PROJECTION_SCHEMA_VERSION,
            "eventType": normalized_type,
            "sessionId": session.session_id,
            "sessionBindingHash": session.session_binding_hash,
            "attemptId": session.attempt_id,
            "actionId": _text(action_id, "action_id", 160),
            "observationHash": _hash(observation_hash, "observation_hash"),
            "authoritative": False,
        }
        event_hash = stable_hash(payload)
        return cls(
            event_id=f"visual-{event_hash[:24]}",
            event_type=payload["eventType"],
            session_id=session.session_id,
            session_binding_hash=session.session_binding_hash,
            attempt_id=session.attempt_id,
            action_id=payload["actionId"],
            observation_hash=payload["observationHash"],
            run_id=session.run_id,
            task_id=session.task_id,
            workspace_id=session.workspace_id,
        )

    @classmethod
    def create_correlated(
        cls,
        *,
        session: LiveWorkspaceSessionV1,
        reconciliation: "SessionReconciliationV1",
        event_type: str,
        action_id: str,
        source_kind: str,
        projection_kind: str,
        projection_state: str,
        source_receipt_ref: str,
        repository_head: str | None,
        payload: Mapping[str, Any],
    ) -> "VisualProjectionEventV1":
        if reconciliation.session_binding_hash != session.session_binding_hash:
            raise FleetContractError("visual projection reconciliation belongs to another session")
        if reconciliation.projection_state != "LIVE":
            raise FleetContractError("visual projection requires a fresh LIVE session reconciliation")
        normalized_source = _text(source_kind, "source_kind", 40).upper()
        normalized_kind = _text(projection_kind, "projection_kind", 40).upper()
        normalized_state = _text(projection_state, "projection_state", 40).upper()
        if normalized_source not in VISUAL_PROJECTION_SOURCE_KINDS:
            raise FleetContractError("visual projection source kind is unsupported")
        if normalized_kind not in VISUAL_PROJECTION_KINDS:
            raise FleetContractError("visual projection kind is unsupported")
        if normalized_state not in VISUAL_PROJECTION_STATES:
            raise FleetContractError("visual projection state is unsupported")
        receipt_ref = _hash(source_receipt_ref, "source_receipt_ref")
        head = None if repository_head is None else _revision(repository_head, "repository_head")
        safe_payload = dict(_mapping(payload, "projection_payload"))
        normalized_action = _text(action_id, "action_id", 160)
        source_identity_hash = stable_hash({
            "sessionBindingHash": session.session_binding_hash,
            "attemptId": session.attempt_id,
            "actionId": normalized_action,
            "sourceReceiptRef": receipt_ref,
            "repositoryHead": head,
        })
        observation_hash = stable_hash({
            "sourceIdentityHash": source_identity_hash,
            "projectionKind": normalized_kind,
            "projectionState": normalized_state,
            "payload": safe_payload,
        })
        base = cls.create(
            session=session,
            event_type=event_type,
            action_id=normalized_action,
            observation_hash=observation_hash,
        )
        projection_hash = stable_hash({
            **base.to_dict(),
            "sourceKind": normalized_source,
            "projectionKind": normalized_kind,
            "projectionState": normalized_state,
            "repositoryHead": head,
            "sourceReceiptRef": receipt_ref,
            "sourceIdentityHash": source_identity_hash,
            "payload": safe_payload,
        })
        return cls(
            event_id=base.event_id,
            event_type=base.event_type,
            session_id=base.session_id,
            session_binding_hash=base.session_binding_hash,
            attempt_id=base.attempt_id,
            action_id=base.action_id,
            observation_hash=base.observation_hash,
            run_id=session.run_id,
            task_id=session.task_id,
            workspace_id=session.workspace_id,
            source_kind=normalized_source,
            projection_kind=normalized_kind,
            projection_state=normalized_state,
            repository_head=head,
            source_receipt_ref=receipt_ref,
            source_identity_hash=source_identity_hash,
            projection_hash=projection_hash,
            payload=safe_payload,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schemaVersion": VISUAL_PROJECTION_SCHEMA_VERSION,
            "eventId": self.event_id,
            "eventType": self.event_type,
            "sessionId": self.session_id,
            "sessionBindingHash": self.session_binding_hash,
            "attemptId": self.attempt_id,
            "actionId": self.action_id,
            "observationHash": self.observation_hash,
            "runId": self.run_id or None,
            "taskId": self.task_id or None,
            "workspaceId": self.workspace_id or None,
            "authoritative": False,
            "claim": "OBSERVED",
        }
        if self.source_kind:
            result.update({
                "projectionId": self.event_id,
                "sourceKind": self.source_kind,
                "projectionKind": self.projection_kind,
                "projectionState": self.projection_state,
                "repositoryHead": self.repository_head,
                "sourceReceiptRef": self.source_receipt_ref,
                "sourceIdentityHash": self.source_identity_hash,
                "projectionHash": self.projection_hash,
                "payload": dict(self.payload or {}),
            })
        return result


@dataclass(frozen=True)
class WorkspaceEvidenceAnchorV1:
    anchor_id: str
    claim_kind: str
    verdict: str
    session_binding_hash: str
    run_id: str
    task_id: str
    attempt_id: str
    action_id: str
    scope: str
    source_kind: str
    source_refs: tuple[str, ...]
    repository_revision: str
    target_revision: str | None
    image_digest: str | None
    runtime_identity_hash: str | None
    frame_observation_id: str | None
    observed_at: str
    requires_patchmon: bool
    evidence_hash: str

    @property
    def claim_type(self) -> str:
        return self.claim_kind

    @property
    def source_revision(self) -> str:
        return self.repository_revision

    @property
    def source_receipt_hashes(self) -> tuple[str, ...]:
        return self.source_refs

    @property
    def observation_event_id(self) -> str | None:
        return self.frame_observation_id

    @property
    def anchor_hash(self) -> str:
        return self.evidence_hash

    @staticmethod
    def _observed_at(value: object) -> str:
        raw = _text(value, "observed_at", 64)
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise FleetContractError("observed_at must be an ISO-8601 timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise FleetContractError("observed_at must include a timezone")
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _image_digest(value: object | None) -> str | None:
        if value in (None, ""):
            return None
        normalized = _text(value, "image_digest", 80).lower()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", normalized):
            raise FleetContractError("image_digest must be immutable")
        return normalized

    @classmethod
    def create(
        cls,
        *,
        session: LiveWorkspaceSessionV1,
        claim_kind: str | None = None,
        claim_type: str | None = None,
        verdict: str,
        scope: str,
        source_kind: str,
        source_refs: Sequence[str] | None = None,
        source_receipt_hashes: Sequence[str] | None = None,
        repository_revision: str | None = None,
        source_revision: str | None = None,
        action_id: str | None = None,
        observed_at: str,
        observation_event: VisualProjectionEventV1 | None = None,
        target_revision: str | None = None,
        image_digest: str | None = None,
        runtime_identity_hash: str | None = None,
        requires_patchmon: bool = False,
    ) -> "WorkspaceEvidenceAnchorV1":
        normalized_verdict = _text(verdict, "verdict", 32).upper()
        if normalized_verdict not in EVIDENCE_VERDICTS:
            raise FleetContractError("evidence verdict is invalid")
        normalized_source_kind = _text(source_kind, "source_kind", 80).upper()
        if normalized_source_kind not in EVIDENCE_SOURCE_KINDS:
            raise FleetContractError("evidence source kind is not canonical")
        refs = _bounded_hashes(
            source_refs if source_refs is not None else source_receipt_hashes or (),
            "source_refs",
        )
        if observation_event and observation_event.session_binding_hash != session.session_binding_hash:
            raise FleetContractError("observation event is bound to another session")
        if observation_event and observation_event.attempt_id != session.attempt_id:
            raise FleetContractError("observation event is bound to another attempt")
        normalized_claim = _text(claim_kind or claim_type, "claim_kind", 120).upper()
        if normalized_claim in _FORBIDDEN_EVIDENCE_CLAIMS or normalized_claim.startswith(("EVERYTHING_", "ALL_")):
            raise FleetContractError("evidence claim must be granular")
        normalized_scope = _text(scope, "scope", 500)
        if not refs:
            raise FleetContractError("canonical evidence references are required")
        if normalized_verdict == "VERIFIED" and normalized_source_kind == "FRAME_OBSERVATION":
            raise FleetContractError("screen observation cannot verify a claim")
        repository_head = _revision(
            repository_revision or source_revision,
            "repository_revision",
        )
        target_head = _revision(target_revision, "target_revision") if target_revision else None
        runtime_hash = _hash(runtime_identity_hash, "runtime_identity_hash") if runtime_identity_hash else None
        digest = cls._image_digest(image_digest)
        if requires_patchmon and normalized_verdict == "VERIFIED":
            if normalized_source_kind != "PATCHMON_READBACK" or not target_head or not digest or not runtime_hash:
                raise FleetContractError("verified runtime claim requires PatchMon revision, digest and runtime identity")
        selected_action_id = _text(
            action_id or (observation_event.action_id if observation_event else None),
            "action_id",
            160,
        )
        observed = cls._observed_at(observed_at)
        payload = {
            "schemaVersion": EVIDENCE_ANCHOR_SCHEMA_VERSION,
            "claimKind": normalized_claim,
            "verdict": normalized_verdict,
            "sessionBindingHash": session.session_binding_hash,
            "runId": session.run_id,
            "taskId": session.task_id,
            "attemptId": session.attempt_id,
            "actionId": selected_action_id,
            "scope": normalized_scope,
            "sourceKind": normalized_source_kind,
            "sourceRefs": list(refs),
            "repositoryRevision": repository_head,
            "targetRevision": target_head,
            "imageDigest": digest,
            "runtimeIdentityHash": runtime_hash,
            "frameObservationId": observation_event.event_id if observation_event else None,
            "observedAt": observed,
            "requiresPatchMon": bool(requires_patchmon),
        }
        evidence_hash = stable_hash(payload)
        return cls(
            anchor_id=f"evidence-{evidence_hash[:24]}",
            claim_kind=payload["claimKind"],
            verdict=payload["verdict"],
            session_binding_hash=session.session_binding_hash,
            run_id=session.run_id,
            task_id=session.task_id,
            attempt_id=session.attempt_id,
            action_id=payload["actionId"],
            scope=payload["scope"],
            source_kind=payload["sourceKind"],
            source_refs=refs,
            repository_revision=payload["repositoryRevision"],
            target_revision=payload["targetRevision"],
            image_digest=payload["imageDigest"],
            runtime_identity_hash=payload["runtimeIdentityHash"],
            frame_observation_id=payload["frameObservationId"],
            observed_at=payload["observedAt"],
            requires_patchmon=payload["requiresPatchMon"],
            evidence_hash=evidence_hash,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkspaceEvidenceAnchorV1":
        raw = _mapping(value, "workspace_evidence_anchor")
        if raw.get("schemaVersion") != EVIDENCE_ANCHOR_SCHEMA_VERSION:
            raise FleetContractError("evidence anchor schema is invalid")
        canonical = {
            "schemaVersion": EVIDENCE_ANCHOR_SCHEMA_VERSION,
            "claimKind": _text(raw.get("claimKind"), "claim_kind", 120).upper(),
            "verdict": _text(raw.get("verdict"), "verdict", 32).upper(),
            "sessionBindingHash": _hash(raw.get("sessionBindingHash"), "session_binding_hash"),
            "runId": _text(raw.get("runId"), "run_id", 160),
            "taskId": _text(raw.get("taskId"), "task_id", 160),
            "attemptId": _text(raw.get("attemptId"), "attempt_id", 160),
            "actionId": _text(raw.get("actionId"), "action_id", 160),
            "scope": _text(raw.get("scope"), "scope", 500),
            "sourceKind": _text(raw.get("sourceKind"), "source_kind", 80).upper(),
            "sourceRefs": list(_bounded_hashes(raw.get("sourceRefs"), "source_refs")),
            "repositoryRevision": _revision(raw.get("repositoryRevision"), "repository_revision"),
            "targetRevision": _revision(raw.get("targetRevision"), "target_revision") if raw.get("targetRevision") else None,
            "imageDigest": cls._image_digest(raw.get("imageDigest")),
            "runtimeIdentityHash": _hash(raw.get("runtimeIdentityHash"), "runtime_identity_hash") if raw.get("runtimeIdentityHash") else None,
            "frameObservationId": _text(raw.get("frameObservationId"), "frame_observation_id", 160) if raw.get("frameObservationId") else None,
            "observedAt": cls._observed_at(raw.get("observedAt")),
            "requiresPatchMon": raw.get("requiresPatchMon") is True,
        }
        if canonical["claimKind"] in _FORBIDDEN_EVIDENCE_CLAIMS:
            raise FleetContractError("evidence claim must be granular")
        if canonical["verdict"] not in EVIDENCE_VERDICTS or canonical["sourceKind"] not in EVIDENCE_SOURCE_KINDS:
            raise FleetContractError("evidence anchor verdict or source is invalid")
        if canonical["verdict"] == "VERIFIED" and canonical["sourceKind"] == "FRAME_OBSERVATION":
            raise FleetContractError("screen observation cannot verify a claim")
        if canonical["requiresPatchMon"] and canonical["verdict"] == "VERIFIED" and (
            canonical["sourceKind"] != "PATCHMON_READBACK"
            or not canonical["targetRevision"]
            or not canonical["imageDigest"]
            or not canonical["runtimeIdentityHash"]
        ):
            raise FleetContractError("verified runtime claim requires PatchMon revision, digest and runtime identity")
        evidence_hash = stable_hash(canonical)
        if raw.get("evidenceHash") != evidence_hash or raw.get("anchorId") != f"evidence-{evidence_hash[:24]}":
            raise FleetContractError("evidence anchor hash is invalid")
        return cls(
            anchor_id=str(raw["anchorId"]),
            claim_kind=str(canonical["claimKind"]),
            verdict=str(canonical["verdict"]),
            session_binding_hash=str(canonical["sessionBindingHash"]),
            run_id=str(canonical["runId"]),
            task_id=str(canonical["taskId"]),
            attempt_id=str(canonical["attemptId"]),
            action_id=str(canonical["actionId"]),
            scope=str(canonical["scope"]),
            source_kind=str(canonical["sourceKind"]),
            source_refs=tuple(canonical["sourceRefs"]),
            repository_revision=str(canonical["repositoryRevision"]),
            target_revision=canonical["targetRevision"],
            image_digest=canonical["imageDigest"],
            runtime_identity_hash=canonical["runtimeIdentityHash"],
            frame_observation_id=canonical["frameObservationId"],
            observed_at=str(canonical["observedAt"]),
            requires_patchmon=bool(canonical["requiresPatchMon"]),
            evidence_hash=evidence_hash,
        )

    @classmethod
    def from_agent_run_receipt(
        cls,
        *,
        session: LiveWorkspaceSessionV1,
        receipt: Mapping[str, Any],
        observation_event: VisualProjectionEventV1 | None,
        observed_at: str,
    ) -> "WorkspaceEvidenceAnchorV1":
        """Reference one already-persisted canonical Agent Run receipt.

        The receipt remains the truth owner. The anchor only binds a claim-sized
        monitor projection to its hash and exact Attempt/revision identity.
        """

        from .agent_run_receipts import canonical_sha256

        raw = _mapping(receipt, "agent_run_receipt")
        header = _mapping(raw.get("header"), "agent_run_receipt.header")
        body = dict(_mapping(raw.get("body"), "agent_run_receipt.body"))
        stored_hash = _hash(header.get("hash"), "agent_run_receipt.hash")
        body_hash = _hash(body.pop("receipt_sha256", None), "agent_run_receipt.body_hash")
        if stored_hash != body_hash or canonical_sha256(body) != stored_hash:
            raise FleetContractError("agent run receipt hash is invalid")
        if body.get("schema_version") != "sovereign.agent-run-receipt.v1":
            raise FleetContractError("agent run receipt schema is invalid")
        if _text(body.get("agent_run_id"), "agent_run_id", 160) != session.run_id:
            raise FleetContractError("agent run receipt belongs to another run")
        operation = _text(body.get("operation_identity"), "operation_identity", 500)
        if (
            f":attempt:{session.attempt_id}:" not in operation
            or f":assignment:{session.assignment_hash}:" not in operation
        ):
            raise FleetContractError("agent run receipt belongs to another attempt")
        action_id = _text(body.get("call_id"), "call_id", 160)
        if observation_event and observation_event.action_id != action_id:
            raise FleetContractError("observation event does not match the canonical action receipt")
        gate = _text(body.get("evidence_gate_result"), "evidence_gate_result", 32).upper()
        test_kind = _text(body.get("test_execution_kind"), "test_execution_kind", 40).lower()
        tool_name = _text(body.get("tool_name"), "tool_name", 160).lower()
        if gate == "PASS" and test_kind != "nonqualifying-test":
            verdict = "VERIFIED"
        elif gate == "FAIL":
            verdict = "CONTRADICTED"
        elif gate == "BLOCKED":
            verdict = "BLOCKED"
        else:
            verdict = "UNVERIFIED"
        claim_kind = (
            "TEST_EXECUTION_RECEIPT_MATCH"
            if test_kind == "qualifying-test"
            else "WORKTREE_READBACK_RECEIPT_MATCH"
        )
        refs = [
            stored_hash,
            _hash(body.get("authoritative_readback_sha256"), "authoritative_readback_sha256"),
        ]
        if test_kind == "qualifying-test":
            refs.append(_hash(body.get("test_evidence_sha256"), "test_evidence_sha256"))
        return cls.create(
            session=session,
            claim_kind=claim_kind,
            verdict=verdict,
            scope=(
                f"tool={tool_name};input={_hash(body.get('input_sha256'), 'input_sha256')};"
                f"effect={_text(body.get('observed_effect'), 'observed_effect', 40).lower()}"
            ),
            source_kind="AGENT_RUN_RECEIPT",
            source_refs=refs,
            repository_revision=_revision(body.get("base_commit_sha"), "base_commit_sha"),
            action_id=action_id,
            observed_at=observed_at,
            observation_event=observation_event,
        )

    @classmethod
    def from_github_draft_pr_readback(
        cls,
        *,
        binding_anchor: "WorkspaceEvidenceAnchorV1",
        readback: Mapping[str, Any],
        source_ref: str,
        observed_at: str,
    ) -> "WorkspaceEvidenceAnchorV1":
        """Bind a verified Draft-PR claim to the exact GitHub readback source."""

        raw = _mapping(readback, "github_draft_pr_readback")
        pr_number = raw.get("prNumber")
        pr_url = _text(raw.get("prUrl"), "pr_url", 500)
        head = _revision(raw.get("headSha"), "head_sha")
        if (
            isinstance(pr_number, bool)
            or not isinstance(pr_number, int)
            or pr_number < 1
            or not re.fullmatch(r"https://github\.com/[^/]+/[^/]+/pull/[1-9][0-9]*", pr_url)
            or _revision(raw.get("publishedHeadSha"), "published_head_sha") != head
            or _revision(raw.get("readbackHeadSha"), "readback_head_sha") != head
            or raw.get("draftVerified") is not True
            or raw.get("prStateVerified") != "open"
            or raw.get("readbackVerified") is not True
            or raw.get("checksReadbackVerified") is not True
        ):
            raise FleetContractError("GitHub Draft PR readback is incomplete or contradictory")
        observed = cls._observed_at(observed_at)
        canonical = {
            "schemaVersion": EVIDENCE_ANCHOR_SCHEMA_VERSION,
            "claimKind": "DRAFT_PR_EXISTS_AT_EXACT_HEAD",
            "verdict": "VERIFIED",
            "sessionBindingHash": binding_anchor.session_binding_hash,
            "runId": binding_anchor.run_id,
            "taskId": binding_anchor.task_id,
            "attemptId": binding_anchor.attempt_id,
            "actionId": f"github-draft-pr-readback-{pr_number}",
            "scope": f"pr={pr_number};draft=true;state=open;head={head}",
            "sourceKind": "GITHUB_READBACK",
            "sourceRefs": list(_bounded_hashes([source_ref], "source_refs")),
            "repositoryRevision": head,
            "targetRevision": None,
            "imageDigest": None,
            "runtimeIdentityHash": None,
            "frameObservationId": None,
            "observedAt": observed,
            "requiresPatchMon": False,
        }
        evidence_hash = stable_hash(canonical)
        return cls(
            anchor_id=f"evidence-{evidence_hash[:24]}",
            claim_kind="DRAFT_PR_EXISTS_AT_EXACT_HEAD",
            verdict="VERIFIED",
            session_binding_hash=binding_anchor.session_binding_hash,
            run_id=binding_anchor.run_id,
            task_id=binding_anchor.task_id,
            attempt_id=binding_anchor.attempt_id,
            action_id=f"github-draft-pr-readback-{pr_number}",
            scope=str(canonical["scope"]),
            source_kind="GITHUB_READBACK",
            source_refs=tuple(canonical["sourceRefs"]),
            repository_revision=head,
            target_revision=None,
            image_digest=None,
            runtime_identity_hash=None,
            frame_observation_id=None,
            observed_at=observed,
            requires_patchmon=False,
            evidence_hash=evidence_hash,
        )

    def current_verdict(
        self,
        *,
        session: LiveWorkspaceSessionV1,
        repository_revision: str,
        target_revision: str | None = None,
        image_digest: str | None = None,
        runtime_identity_hash: str | None = None,
    ) -> tuple[str, tuple[str, ...]]:
        """Project freshness without changing the immutable source anchor."""

        if self.session_binding_hash != session.session_binding_hash or self.attempt_id != session.attempt_id:
            raise FleetContractError("evidence anchor belongs to another attempt")
        reasons: list[str] = []
        if _revision(repository_revision, "repository_revision") != self.repository_revision:
            reasons.append("REPOSITORY_REVISION_CHANGED")
        if self.target_revision and target_revision and _revision(target_revision, "target_revision") != self.target_revision:
            reasons.append("TARGET_REVISION_CONTRADICTED")
        if self.image_digest and image_digest and self._image_digest(image_digest) != self.image_digest:
            reasons.append("IMAGE_DIGEST_CONTRADICTED")
        if self.runtime_identity_hash and runtime_identity_hash and _hash(runtime_identity_hash, "runtime_identity_hash") != self.runtime_identity_hash:
            reasons.append("RUNTIME_IDENTITY_CONTRADICTED")
        if any(reason.endswith("CONTRADICTED") for reason in reasons):
            return "CONTRADICTED", tuple(reasons)
        if reasons:
            return "STALE", tuple(reasons)
        if self.requires_patchmon and (not target_revision or not image_digest or not runtime_identity_hash):
            return "UNVERIFIED", ("PATCHMON_READBACK_UNAVAILABLE",)
        return self.verdict, ()

    def to_read_model(self, *, verdict: str | None = None, freshness_reasons: Sequence[str] = ()) -> dict[str, Any]:
        payload = self.to_dict()
        payload["sourceVerdict"] = self.verdict
        payload["verdict"] = verdict or self.verdict
        payload["freshnessReasons"] = list(freshness_reasons)
        payload["authoritative"] = False
        return payload

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": EVIDENCE_ANCHOR_SCHEMA_VERSION,
            "anchorId": self.anchor_id,
            "claimKind": self.claim_kind,
            "verdict": self.verdict,
            "sessionBindingHash": self.session_binding_hash,
            "runId": self.run_id,
            "taskId": self.task_id,
            "attemptId": self.attempt_id,
            "actionId": self.action_id,
            "scope": self.scope,
            "sourceKind": self.source_kind,
            "sourceRefs": list(self.source_refs),
            "repositoryRevision": self.repository_revision,
            "targetRevision": self.target_revision,
            "imageDigest": self.image_digest,
            "runtimeIdentityHash": self.runtime_identity_hash,
            "frameObservationId": self.frame_observation_id,
            "observedAt": self.observed_at,
            "requiresPatchMon": self.requires_patchmon,
            "evidenceHash": self.evidence_hash,
            "authoritative": False,
        }


@dataclass(frozen=True)
class LiveWorkspaceControlLeaseV1:
    lease_id: str
    session_binding_hash: str
    owner_subject_hash: str
    input_scope_hash: str
    state: str
    issued_readback_hash: str

    @classmethod
    def issue_takeover(
        cls,
        *,
        session: LiveWorkspaceSessionV1,
        owner_subject_hash: str,
        input_scope_hash: str,
        reconciliation: SessionReconciliationV1,
    ) -> "LiveWorkspaceControlLeaseV1":
        if reconciliation.session_binding_hash != session.session_binding_hash or reconciliation.projection_state != "LIVE":
            raise FleetContractError("takeover requires a fresh authoritative workspace readback")
        payload = {
            "schemaVersion": CONTROL_LEASE_SCHEMA_VERSION,
            "sessionBindingHash": session.session_binding_hash,
            "ownerSubjectHash": _hash(owner_subject_hash, "owner_subject_hash"),
            "inputScopeHash": _hash(input_scope_hash, "input_scope_hash"),
            "state": "USER_CONTROLLED",
            "issuedReadbackHash": _hash(reconciliation.fresh_readback_hash, "fresh_readback_hash"),
        }
        lease_hash = stable_hash(payload)
        return cls(
            lease_id=f"livelease-{lease_hash[:24]}",
            session_binding_hash=session.session_binding_hash,
            owner_subject_hash=payload["ownerSubjectHash"],
            input_scope_hash=payload["inputScopeHash"],
            state="USER_CONTROLLED",
            issued_readback_hash=payload["issuedReadbackHash"],
        )

    def give_back(self, reconciliation: SessionReconciliationV1) -> "LiveWorkspaceControlLeaseV1":
        if reconciliation.session_binding_hash != self.session_binding_hash:
            raise FleetContractError("give back readback belongs to another session")
        next_state = "AGENT_CONTROLLED_REBOUND" if reconciliation.projection_state == "LIVE" else "BLOCKED_STALE_STATE"
        return LiveWorkspaceControlLeaseV1(
            lease_id=self.lease_id,
            session_binding_hash=self.session_binding_hash,
            owner_subject_hash=self.owner_subject_hash,
            input_scope_hash=self.input_scope_hash,
            state=next_state,
            issued_readback_hash=reconciliation.fresh_readback_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": CONTROL_LEASE_SCHEMA_VERSION,
            "leaseId": self.lease_id,
            "sessionBindingHash": self.session_binding_hash,
            "ownerSubjectHash": self.owner_subject_hash,
            "inputScopeHash": self.input_scope_hash,
            "state": self.state,
            "issuedReadbackHash": self.issued_readback_hash,
            "authoritative": False,
        }


@dataclass(frozen=True)
class ChatBubbleV1:
    bubble_kind: str
    text: str
    canonical_reference_hashes: tuple[str, ...]
    bubble_hash: str

    @classmethod
    def create(cls, *, bubble_kind: str, text: str, canonical_reference_hashes: Sequence[str]) -> "ChatBubbleV1":
        kind = _text(bubble_kind, "bubble_kind", 80).upper()
        if kind not in CHAT_BUBBLE_KINDS:
            raise FleetContractError("chat bubble kind is forbidden")
        body = _text(text, "bubble_text", 2000)
        # Structural bubble kind/source/binding validation is the primary gate.
        # These markers are defense in depth for already-typed committed segments.
        forbidden = (
            "here's a thinking process",
            "chain-of-thought",
            "reasoning:",
            "system prompt",
            "tool schema",
            "runtime_flags",
            "provider_request_id",
            '"role":"system"',
            "<|system|>",
        )
        if any(marker in body.casefold() for marker in forbidden):
            raise FleetContractError("chat bubble contains internal reasoning or schema")
        refs = _bounded_hashes(canonical_reference_hashes, "canonical_reference_hashes")
        if kind in {"MATERIAL_BLOCKER", "FINAL_RESULT", "OWNER_CONSENT_REQUEST"} and not refs:
            raise FleetContractError("material chat bubble requires canonical references")
        payload = {"schemaVersion": CHAT_BUBBLE_SCHEMA_VERSION, "bubbleKind": kind, "text": body, "canonicalReferenceHashes": list(refs)}
        return cls(kind, body, refs, stable_hash(payload))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": CHAT_BUBBLE_SCHEMA_VERSION,
            "bubbleKind": self.bubble_kind,
            "text": self.text,
            "canonicalReferenceHashes": list(self.canonical_reference_hashes),
            "bubbleHash": self.bubble_hash,
            "authoritative": False,
        }


def _assignment_from_dict(value: Mapping[str, Any]) -> FleetWorkerAssignment:
    """Parse a signed assignment without trusting convenience fields."""
    return FleetWorkerAssignment.from_dict(_mapping(value, "assignment"))


__all__ = [
    "CHAT_BUBBLE_KINDS",
    "CONTROL_STATES",
    "EVIDENCE_VERDICTS",
    "LIVE_WORKSPACE_SCHEMA_VERSION",
    "OBSERVATION_EVENT_TYPES",
    "ChatBubbleV1",
    "DesktopRuntimeContractV1",
    "LiveWorkspaceControlLeaseV1",
    "LiveWorkspaceSessionV1",
    "SessionReconciliationV1",
    "VisualProjectionEventV1",
    "WorkspaceEvidenceAnchorV1",
    "WorkspaceReadbackV1",
]
