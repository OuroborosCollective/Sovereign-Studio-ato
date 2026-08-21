"""Fail-closed, rebuildable Live Workspace contracts for issues #1616–#1622.

The monitor is an observation surface only.  This module is intentionally pure: it
never creates a worktree, starts a container, writes a database, executes a command,
or upgrades a verification verdict.  Callers must provide fresh canonical assignment,
attempt, worktree, Git and runtime readbacks for every bind or reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    event_id: str
    event_type: str
    session_id: str
    session_binding_hash: str
    attempt_id: str
    action_id: str
    observation_hash: str

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
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": VISUAL_PROJECTION_SCHEMA_VERSION,
            "eventId": self.event_id,
            "eventType": self.event_type,
            "sessionId": self.session_id,
            "sessionBindingHash": self.session_binding_hash,
            "attemptId": self.attempt_id,
            "actionId": self.action_id,
            "observationHash": self.observation_hash,
            "authoritative": False,
            "claim": "OBSERVED",
        }


@dataclass(frozen=True)
class WorkspaceEvidenceAnchorV1:
    claim_type: str
    verdict: str
    session_binding_hash: str
    attempt_id: str
    source_revision: str
    source_receipt_hashes: tuple[str, ...]
    observation_event_id: str | None
    requires_patchmon: bool
    anchor_hash: str

    @classmethod
    def create(
        cls,
        *,
        session: LiveWorkspaceSessionV1,
        claim_type: str,
        verdict: str,
        source_receipt_hashes: Sequence[str],
        source_revision: str,
        observation_event: VisualProjectionEventV1 | None = None,
        requires_patchmon: bool = False,
    ) -> "WorkspaceEvidenceAnchorV1":
        normalized_verdict = _text(verdict, "verdict", 32).upper()
        if normalized_verdict not in EVIDENCE_VERDICTS:
            raise FleetContractError("evidence verdict is invalid")
        receipts = _bounded_hashes(source_receipt_hashes, "source_receipt_hashes")
        if not receipts:
            raise FleetContractError("canonical evidence receipts are required")
        if observation_event and observation_event.session_binding_hash != session.session_binding_hash:
            raise FleetContractError("observation event is bound to another session")
        normalized_claim = _text(claim_type, "claim_type", 120).upper()
        if normalized_verdict == "VERIFIED" and observation_event and not receipts:
            raise FleetContractError("screen observation cannot verify a claim")
        payload = {
            "schemaVersion": EVIDENCE_ANCHOR_SCHEMA_VERSION,
            "claimType": normalized_claim,
            "verdict": normalized_verdict,
            "sessionBindingHash": session.session_binding_hash,
            "attemptId": session.attempt_id,
            "sourceRevision": _revision(source_revision, "source_revision"),
            "sourceReceiptHashes": list(receipts),
            "observationEventId": observation_event.event_id if observation_event else None,
            "requiresPatchMon": bool(requires_patchmon),
        }
        return cls(
            claim_type=payload["claimType"],
            verdict=payload["verdict"],
            session_binding_hash=session.session_binding_hash,
            attempt_id=session.attempt_id,
            source_revision=payload["sourceRevision"],
            source_receipt_hashes=receipts,
            observation_event_id=payload["observationEventId"],
            requires_patchmon=payload["requiresPatchMon"],
            anchor_hash=stable_hash(payload),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": EVIDENCE_ANCHOR_SCHEMA_VERSION,
            "claimType": self.claim_type,
            "verdict": self.verdict,
            "sessionBindingHash": self.session_binding_hash,
            "attemptId": self.attempt_id,
            "sourceRevision": self.source_revision,
            "sourceReceiptHashes": list(self.source_receipt_hashes),
            "observationEventId": self.observation_event_id,
            "requiresPatchMon": self.requires_patchmon,
            "anchorHash": self.anchor_hash,
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
        forbidden = ("chain-of-thought", "reasoning:", "system prompt", "tool schema")
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
    """Parse a signed assignment without trusting client-provided convenience fields."""
    raw = _mapping(value, "assignment")
    required = (
        "assignmentId", "planHash", "laneId", "taskId", "controllerRunId", "workspaceId",
        "workspaceBranch", "expectedBaseRevision", "runEnvelopeHash", "capabilityManifestHash", "assignmentHash",
    )
    if any(name not in raw for name in required):
        raise FleetContractError("assignment lacks canonical signed fields")
    return FleetWorkerAssignment(
        assignment_id=_text(raw["assignmentId"], "assignment_id", 160),
        plan_hash=_hash(raw["planHash"], "plan_hash"),
        lane_id=_text(raw["laneId"], "lane_id", 120),
        task_id=_text(raw["taskId"], "task_id", 120),
        controller_run_id=_text(raw["controllerRunId"], "controller_run_id", 160),
        workspace_id=_text(raw["workspaceId"], "workspace_id", 160),
        workspace_branch=_text(raw["workspaceBranch"], "workspace_branch", 200),
        expected_base_revision=_revision(raw["expectedBaseRevision"], "expected_base_revision"),
        expected_head_revision=str(raw.get("expectedHeadRevision") or "").strip().lower(),
        run_envelope_hash=_hash(raw["runEnvelopeHash"], "run_envelope_hash"),
        capability_manifest_hash=_hash(raw["capabilityManifestHash"], "capability_manifest_hash"),
        permission_receipt_hashes=_bounded_hashes(raw.get("permissionReceiptHashes", []), "permission_receipt_hashes"),
        allowed_effects=tuple(str(item) for item in raw.get("allowedEffects", [])),
        assignment_hash=_hash(raw["assignmentHash"], "assignment_hash"),
    )


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
