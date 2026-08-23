"""Fail-closed server-side reconnect resolution for one Fleet attempt workspace.

This module deliberately consumes only persisted, owner-scoped Fleet stage evidence
and a fresh readback of an already registered #1524 ``AttemptWorkspace``.  It never
provisions a worktree, picks a role from request input, or exposes filesystem paths.
Generic ``/tools/*`` routes use the outer Agent Job clone and therefore must not call
this resolver or turn their results into attempt-labelled projections.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from .agent_run_receipts import canonical_sha256
from .cognitive_run_store import (
    LIVE_WORKSPACE_RUN_STATUSES,
    StoredAgentRun,
    read_active_agent_run_for_job,
    read_live_workspace_stage_evidence,
)
from .cognitive_swarm_manifest import WORKER_ROLES, manifest_payload
from .fleet_attempts import FleetWorkerAttempt, create_worker_attempt
from .fleet_attempt_worktrees import (
    ATTEMPT_WORKTREE_SCHEMA_VERSION,
    AttemptWorkspace,
    read_active_attempt_worktree,
)
from .fleet_supervisor import (
    FleetContractError,
    FleetPlan,
    FleetWorkerAssignment,
    create_worker_assignment,
    stable_hash,
)
from .job_store import read_agent_job
from .live_workspace import LiveWorkspaceSessionV1, SessionReconciliationV1, WorkspaceReadbackV1
from .workspace_policy import WorkspacePolicyError, validate_repo_url_for_workspace


LIVE_WORKSPACE_CONTEXT_SCHEMA_VERSION = "sovereign.live-workspace-context.v1"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\\\/]")
_TERMINAL_JOB_STATUSES = frozenset({
    "blocked", "cancelled", "canceled", "cleaned", "completed", "failed",
    "draft_pr_created", "terminal",
})
_ATTEMPT_RECEIPT_KEYS = frozenset({
    "schemaVersion", "workspaceId", "runId", "taskId", "assignmentHash",
    "attemptId", "attemptSequence", "attemptHash", "branchName", "baseRevision",
    "headRevision", "worktreePathSha256", "worktreeReadbackSha256",
    "worktreeBindingHash", "changedPaths",
})
_STATIC_ATTEMPT_RECEIPT_KEYS = (
    "schemaVersion", "workspaceId", "runId", "taskId", "assignmentHash",
    "attemptId", "attemptSequence", "attemptHash", "branchName", "baseRevision",
    "worktreePathSha256", "worktreeBindingHash",
)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FleetContractError(f"{field} must be an object")
    return value


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


def _text(value: object, field: str, *, maximum: int = 240) -> str:
    result = str(value or "").strip()
    if not result or len(result) > maximum:
        raise FleetContractError(f"{field} is invalid")
    return result


def _workspace_id_for_job(job: Any) -> str:
    return _text(getattr(job, "workspace_id", None) or getattr(job, "job_id", None), "workspace_id", maximum=160)


def _repository_for_job(job: Any, plan: FleetPlan) -> str:
    """Verify that the owned job URL is exactly the FleetPlan repository."""

    safe_url = validate_repo_url_for_workspace(_text(getattr(job, "repo_url", None), "repository_url", maximum=500))
    parsed = urlparse(safe_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or parsed.query or parsed.fragment:
        raise FleetContractError("job repository URL is not a canonical GitHub repository")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        raise FleetContractError("job repository URL is not a repository root")
    repository = f"{parts[0]}/{parts[1].removesuffix('.git')}"
    if repository != plan.repository:
        raise FleetContractError("job repository does not match the persisted FleetPlan")
    return repository


@dataclass(frozen=True)
class _PersistedSnapshot:
    plan: FleetPlan
    assignments_by_role: dict[str, FleetWorkerAssignment]
    attempts_by_role: dict[str, FleetWorkerAttempt]
    receipts_by_role: dict[str, dict[str, Any]]
    evidence_sha256: str
    record_index: int
    source_event_type: str


@dataclass(frozen=True)
class _ActiveLane:
    lane_id: str
    evidence_sha256: str
    started_index: int
    snapshot: _PersistedSnapshot


@dataclass(frozen=True)
class LiveWorkspaceContextV1:
    """Internal exact-attempt context with a path-free public representation."""

    session: LiveWorkspaceSessionV1
    reconciliation: SessionReconciliationV1
    attempt_workspace: AttemptWorkspace
    role: str
    run_id: str
    fleet_snapshot_evidence_sha256: str
    active_lane_evidence_sha256: str

    def to_public_dict(self) -> dict[str, Any]:
        """Return reconnect state without filesystem paths or controller authority."""

        return {
            "schemaVersion": LIVE_WORKSPACE_CONTEXT_SCHEMA_VERSION,
            "projectionState": self.reconciliation.projection_state,
            "role": self.role,
            "runId": self.run_id,
            "session": self.session.to_dict(),
            "reconciliation": self.reconciliation.to_dict(),
            "attempt": {
                "attemptId": self.attempt_workspace.attempt_id,
                "attemptSequence": self.attempt_workspace.attempt_sequence,
                "attemptHash": self.attempt_workspace.attempt_hash,
                "assignmentHash": self.attempt_workspace.assignment_hash,
                "taskId": self.attempt_workspace.task_id,
                "branchName": self.attempt_workspace.branch_name,
                "baseRevision": self.attempt_workspace.base_revision,
                "headRevision": self.attempt_workspace.head_revision,
                "worktreePathSha256": self.attempt_workspace.receipt_binding()["worktreePathSha256"],
                "worktreeReadbackSha256": self.attempt_workspace.worktree_readback_sha256,
                "worktreeBindingHash": self.attempt_workspace.binding_hash,
                "changedPaths": list(self.attempt_workspace.changed_paths),
                "authoritative": False,
            },
            "reconnectEvidence": {
                "fleetSnapshotSha256": self.fleet_snapshot_evidence_sha256,
                "activeLaneSha256": self.active_lane_evidence_sha256,
                "authoritative": False,
            },
        }


def _verified_stage_record(
    record: Mapping[str, object],
    *,
    run_id: str,
    job_id: str,
) -> tuple[str, Mapping[str, Any], str]:
    """Verify provenance and the exact canonical hash of one persisted event."""

    if (
        str(record.get("runId") or "") != run_id
        or str(record.get("evidenceRunId") or "") != run_id
        or str(record.get("jobId") or "") != job_id
        or str(record.get("eventSource") or "") != "agents-sdk"
        or str(record.get("evidenceSource") or "") != "agents-sdk"
        or str(record.get("eventAgentId") or "") != "dispatcher"
        or str(record.get("evidenceAgentId") or "") != "dispatcher"
    ):
        raise FleetContractError("Fleet stage evidence scope is inconsistent")
    event_type = _text(record.get("eventType"), "event_type", maximum=120)
    if event_type not in {
        "fleet_plan_persisted", "fleet_attempt_rebound", "fleet_lane_started", "fleet_lane_completed",
    }:
        raise FleetContractError("Fleet stage evidence type is not reconnect-admissible")
    payload = _mapping(record.get("payload"), "Fleet stage evidence payload")
    evidence_sha = _hash(record.get("evidenceSha256"), "Fleet stage evidence SHA")
    if stable_hash(dict(payload)) != evidence_sha:
        raise FleetContractError("Fleet stage evidence hash does not bind its payload")
    if (
        payload.get("eventType") != event_type
        or payload.get("status") != record.get("status")
        or payload.get("rawModelOutputPersisted") is not False
    ):
        raise FleetContractError("Fleet stage evidence payload is not controller-canonical")
    return event_type, payload, evidence_sha


def _task_ids_by_role(payload: Mapping[str, Any], plan: FleetPlan) -> dict[str, str]:
    raw = _mapping(payload.get("fleetTaskIdsByRole"), "fleetTaskIdsByRole")
    if set(raw) != set(WORKER_ROLES):
        raise FleetContractError("Fleet task role map is incomplete")
    result = {role: _text(raw.get(role), "fleet task id", maximum=120) for role in WORKER_ROLES}
    if len(set(result.values())) != len(result):
        raise FleetContractError("Fleet task role map has duplicate task ids")
    tasks = {task.task_id: task for task in plan.tasks}
    if set(tasks) != set(result.values()):
        raise FleetContractError("Fleet task role map does not cover the exact plan")
    for role, task_id in result.items():
        task = tasks[task_id]
        if task.source_type != "integration_step" or task.source_id != role:
            raise FleetContractError("Fleet task role map does not match the plan task source")
    return result


def _expected_assignments(
    *,
    payload: Mapping[str, Any],
    plan: FleetPlan,
    run: StoredAgentRun,
    job: Any,
    task_ids_by_role: Mapping[str, str],
) -> dict[str, FleetWorkerAssignment]:
    raw_assignments = _mapping(payload.get("fleetAssignmentsByRole"), "fleetAssignmentsByRole")
    if set(raw_assignments) != set(WORKER_ROLES):
        raise FleetContractError("Fleet assignment role map is incomplete")
    workspace_id = _workspace_id_for_job(job)
    workspace_branch = _text(getattr(job, "branch", None) or "main", "workspace_branch", maximum=200)
    run_envelope_hash = canonical_sha256({
        "schemaVersion": "sovereign.repository-fleet-envelope.v1",
        "runId": run.run_id,
        "repository": plan.repository,
        "workspaceId": workspace_id,
        "workspaceBranch": workspace_branch,
        "baseRevision": plan.base_revision,
        "fleetPlanHash": plan.plan_hash,
    })
    capability_manifest_hash = canonical_sha256(manifest_payload())
    lane_by_task = {
        task_id: lane.lane_id
        for lane in plan.lanes
        for task_id in lane.task_ids
    }
    if set(lane_by_task) != set(task_ids_by_role.values()):
        raise FleetContractError("Fleet plan lanes do not cover the exact task map")
    assignments: dict[str, FleetWorkerAssignment] = {}
    for role in WORKER_ROLES:
        expected = create_worker_assignment(
            plan,
            lane_id=lane_by_task[task_ids_by_role[role]],
            task_id=task_ids_by_role[role],
            controller_run_id=run.run_id,
            workspace_id=workspace_id,
            workspace_branch=workspace_branch,
            run_envelope_hash=run_envelope_hash,
            capability_manifest_hash=capability_manifest_hash,
        )
        raw = _mapping(raw_assignments.get(role), "Fleet assignment")
        parsed = FleetWorkerAssignment.from_dict(raw)
        if parsed != expected or dict(raw) != expected.to_dict():
            raise FleetContractError("persisted Fleet assignment is not the exact controller derivation")
        assignments[role] = expected
    return assignments


def _attempts_from_receipts(
    *,
    payload: Mapping[str, Any],
    assignments_by_role: Mapping[str, FleetWorkerAssignment],
) -> tuple[dict[str, FleetWorkerAttempt], dict[str, dict[str, Any]]]:
    raw_receipts = _mapping(payload.get("fleetAttemptsByRole"), "fleetAttemptsByRole")
    if set(raw_receipts) != set(WORKER_ROLES):
        raise FleetContractError("Fleet attempt role map is incomplete")
    attempts: dict[str, FleetWorkerAttempt] = {}
    receipts: dict[str, dict[str, Any]] = {}
    for role in WORKER_ROLES:
        raw = _mapping(raw_receipts.get(role), "Fleet attempt receipt")
        if set(raw) != _ATTEMPT_RECEIPT_KEYS:
            raise FleetContractError("Fleet attempt receipt fields are not canonical")
        sequence = raw.get("attemptSequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise FleetContractError("Fleet attempt sequence is invalid")
        assignment = assignments_by_role[role]
        attempt = create_worker_attempt(assignment, attempt_sequence=sequence)
        if (
            raw.get("schemaVersion") != ATTEMPT_WORKTREE_SCHEMA_VERSION
            or raw.get("workspaceId") != assignment.workspace_id
            or raw.get("runId") != assignment.controller_run_id
            or raw.get("taskId") != assignment.task_id
            or raw.get("assignmentHash") != assignment.assignment_hash
            or raw.get("attemptId") != attempt.attempt_id
            or raw.get("attemptSequence") != attempt.attempt_sequence
            or raw.get("attemptHash") != attempt.attempt_hash
            or raw.get("baseRevision") != assignment.expected_base_revision
        ):
            raise FleetContractError("Fleet attempt receipt is not bound to its assignment")
        _text(raw.get("branchName"), "Fleet attempt branch", maximum=240)
        _revision(raw.get("headRevision"), "Fleet attempt receipt head")
        _hash(raw.get("worktreePathSha256"), "Fleet attempt worktree path hash")
        _hash(raw.get("worktreeReadbackSha256"), "Fleet attempt worktree readback hash")
        _hash(raw.get("worktreeBindingHash"), "Fleet attempt worktree binding hash")
        changed_paths = raw.get("changedPaths")
        if not isinstance(changed_paths, list) or any(not isinstance(path, str) or len(path) > 500 for path in changed_paths):
            raise FleetContractError("Fleet attempt changed paths are invalid")
        attempts[role] = attempt
        receipts[role] = dict(raw)
    return attempts, receipts


def _snapshot_from_payload(
    *,
    payload: Mapping[str, Any],
    evidence_sha256: str,
    record_index: int,
    source_event_type: str,
    run: StoredAgentRun,
    job: Any,
) -> _PersistedSnapshot:
    raw_plan = _mapping(payload.get("fleetPlan"), "fleetPlan")
    plan = FleetPlan.from_dict(raw_plan)
    if (
        dict(raw_plan) != plan.to_dict()
        or payload.get("fleetPlanHash") != plan.plan_hash
        or plan.integration_id != run.run_id
        or plan.base_revision != _revision(plan.base_revision, "FleetPlan base revision")
    ):
        raise FleetContractError("FleetPlan snapshot is not canonical")
    _repository_for_job(job, plan)
    task_ids_by_role = _task_ids_by_role(payload, plan)
    assignments = _expected_assignments(
        payload=payload,
        plan=plan,
        run=run,
        job=job,
        task_ids_by_role=task_ids_by_role,
    )
    attempts, receipts = _attempts_from_receipts(payload=payload, assignments_by_role=assignments)
    return _PersistedSnapshot(
        plan=plan,
        assignments_by_role=assignments,
        attempts_by_role=attempts,
        receipts_by_role=receipts,
        evidence_sha256=evidence_sha256,
        record_index=record_index,
        source_event_type=source_event_type,
    )


def _same_plan(left: FleetPlan, right: FleetPlan) -> bool:
    return left.plan_hash == right.plan_hash and left.to_dict() == right.to_dict()


def _resolve_active_lane(
    *,
    records: tuple[dict[str, object], ...],
    run: StoredAgentRun,
    job: Any,
) -> tuple[_PersistedSnapshot, _ActiveLane, str]:
    snapshot: _PersistedSnapshot | None = None
    active_lane: _ActiveLane | None = None
    initial_plan_seen = False
    for index, raw_record in enumerate(records):
        record = _mapping(raw_record, "Fleet stage record")
        event_type, payload, evidence_sha = _verified_stage_record(
            record,
            run_id=run.run_id,
            job_id=str(getattr(job, "job_id", "")),
        )
        if event_type in {"fleet_plan_persisted", "fleet_attempt_rebound"}:
            next_snapshot = _snapshot_from_payload(
                payload=payload,
                evidence_sha256=evidence_sha,
                record_index=index,
                source_event_type=event_type,
                run=run,
                job=job,
            )
            if event_type == "fleet_plan_persisted":
                if initial_plan_seen or snapshot is not None or active_lane is not None:
                    raise FleetContractError("FleetPlan persistence is ambiguous")
                if any(attempt.attempt_sequence != 1 for attempt in next_snapshot.attempts_by_role.values()):
                    raise FleetContractError("initial FleetPlan snapshot may bind only first attempts")
                initial_plan_seen = True
            else:
                if not initial_plan_seen or snapshot is None or active_lane is not None:
                    raise FleetContractError("Fleet retry snapshot has no inactive prior plan")
                if not _same_plan(next_snapshot.plan, snapshot.plan):
                    raise FleetContractError("Fleet retry snapshot changed the persisted plan")
                advanced_roles = tuple(
                    role
                    for role in WORKER_ROLES
                    if next_snapshot.attempts_by_role[role].attempt_sequence
                    > snapshot.attempts_by_role[role].attempt_sequence
                )
                if any(
                    next_snapshot.attempts_by_role[role].attempt_sequence
                    < snapshot.attempts_by_role[role].attempt_sequence
                    for role in WORKER_ROLES
                ) or len(advanced_roles) != 1:
                    raise FleetContractError("Fleet retry snapshot must advance exactly one active attempt")
            snapshot = next_snapshot
            continue
        if snapshot is None:
            raise FleetContractError("Fleet lane evidence appeared before a persisted plan")
        if payload.get("fleetPlanHash") != snapshot.plan.plan_hash:
            raise FleetContractError("Fleet lane evidence references another plan")
        lane_id = _text(payload.get("fleetLaneId"), "Fleet lane id", maximum=120)
        lane = next((item for item in snapshot.plan.lanes if item.lane_id == lane_id), None)
        if lane is None:
            raise FleetContractError("Fleet lane evidence is not in the persisted plan")
        if event_type == "fleet_lane_started":
            if record.get("status") != "RUNNING" or active_lane is not None:
                raise FleetContractError("Fleet lane start is invalid or parallel")
            active_lane = _ActiveLane(
                lane_id=lane_id,
                evidence_sha256=evidence_sha,
                started_index=index,
                snapshot=snapshot,
            )
            continue
        if event_type == "fleet_lane_completed":
            if (
                record.get("status") != "COMPLETED"
                or active_lane is None
                or active_lane.lane_id != lane_id
            ):
                raise FleetContractError("Fleet lane completion is not paired with the active lane")
            active_lane = None
            continue
        raise FleetContractError("Fleet stage evidence transition is unsupported")
    if snapshot is None or active_lane is None:
        raise FleetContractError("no active Fleet lane is available for live reconnect")
    if snapshot.record_index > active_lane.started_index:
        raise FleetContractError("Fleet active lane predates the selected attempt snapshot")
    lane = next((item for item in snapshot.plan.lanes if item.lane_id == active_lane.lane_id), None)
    if lane is None or lane.parallel_safe or len(lane.task_ids) != 1:
        raise FleetContractError("live reconnect requires one active serialized Fleet lane")
    task_id = lane.task_ids[0]
    roles = [role for role, assignment in snapshot.assignments_by_role.items() if assignment.task_id == task_id]
    if len(roles) != 1:
        raise FleetContractError("active Fleet lane does not resolve to exactly one worker role")
    return snapshot, active_lane, roles[0]


def _verify_static_attempt_receipt(
    *,
    persisted: Mapping[str, Any],
    current: AttemptWorkspace,
) -> None:
    current_receipt = current.receipt_binding()
    if any(persisted.get(key) != current_receipt.get(key) for key in _STATIC_ATTEMPT_RECEIPT_KEYS):
        raise FleetContractError("persisted Fleet attempt receipt does not bind the current deterministic worktree")


def _safe_changed_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    if len(paths) > 256:
        raise FleetContractError("attempt worktree changed paths exceed the reconnect bound")
    safe: list[str] = []
    for value in paths:
        path = str(value or "")
        if (
            not path
            or len(path) > 500
            or path.startswith(("/", "\\", "//", "\\\\"))
            or _WINDOWS_ABSOLUTE_PATH_RE.match(path)
            or ".." in path.replace("\\", "/").split("/")
        ):
            raise FleetContractError("attempt worktree changed path is unsafe")
        safe.append(path)
    return tuple(safe)


ActiveRunReader = Callable[..., StoredAgentRun | None]
StageEvidenceReader = Callable[..., tuple[dict[str, object], ...]]
AttemptWorkspaceReader = Callable[..., AttemptWorkspace]
JobReader = Callable[..., Any | None]


@dataclass(frozen=True)
class _CurrentReconnectState:
    run: StoredAgentRun
    snapshot: _PersistedSnapshot
    active_lane: _ActiveLane
    role: str


def _read_current_reconnect_state(
    *,
    conn: Any,
    job: Any,
    user_id: str,
    job_id: str,
    active_run_reader: ActiveRunReader,
    stage_evidence_reader: StageEvidenceReader,
) -> _CurrentReconnectState:
    run = active_run_reader(conn, user_id=user_id, job_id=job_id)
    if (
        run is None
        or run.run_id == ""
        or run.user_id != user_id
        or run.job_id != job_id
        or str(run.status or "").upper() not in LIVE_WORKSPACE_RUN_STATUSES
    ):
        raise FleetContractError("there is no unique owned live controller run")
    records = stage_evidence_reader(
        conn,
        user_id=user_id,
        run_id=run.run_id,
        job_id=job_id,
    )
    if not isinstance(records, tuple) or not records:
        raise FleetContractError("there is no current Fleet stage evidence timeline")
    snapshot, active_lane, role = _resolve_active_lane(records=records, run=run, job=job)
    return _CurrentReconnectState(
        run=run,
        snapshot=snapshot,
        active_lane=active_lane,
        role=role,
    )


def _controller_state_ref(
    *,
    state: _CurrentReconnectState,
    job_id: str,
    attempt: FleetWorkerAttempt,
) -> str:
    return stable_hash({
        "schemaVersion": LIVE_WORKSPACE_CONTEXT_SCHEMA_VERSION,
        "runId": state.run.run_id,
        "jobId": job_id,
        "controllerStatus": str(state.run.status).upper(),
        "fleetPlanHash": state.snapshot.plan.plan_hash,
        "fleetSnapshotEvidenceSha256": state.snapshot.evidence_sha256,
        "fleetLaneEvidenceSha256": state.active_lane.evidence_sha256,
        "fleetLaneId": state.active_lane.lane_id,
        "role": state.role,
        "attemptId": attempt.attempt_id,
        "attemptHash": attempt.attempt_hash,
    })


def _workspace_readback(
    *,
    state: _CurrentReconnectState,
    assignment: FleetWorkerAssignment,
    attempt: FleetWorkerAttempt,
    workspace: AttemptWorkspace,
    job_id: str,
) -> WorkspaceReadbackV1:
    return WorkspaceReadbackV1.from_dict({
        "repository": state.snapshot.plan.repository,
        "workspaceId": assignment.workspace_id,
        "worktreeIdentityHash": workspace.worktree_readback_sha256,
        "observedHeadRevision": workspace.head_revision,
        "fleetPlanHash": state.snapshot.plan.plan_hash,
        "controllerStateRef": _controller_state_ref(state=state, job_id=job_id, attempt=attempt),
        "controllerState": str(state.run.status).upper(),
        "workspacePathOwner": assignment.workspace_id,
    })


def _read_current_owned_job(
    *,
    conn: Any,
    initial_job: Any,
    user_id: str,
    job_id: str,
    job_reader: JobReader,
) -> Any:
    current = job_reader(conn, user_id=user_id, job_id=job_id)
    if current is None:
        raise FleetContractError("owned Agent Job is no longer readable")
    if (
        _text(getattr(current, "user_id", None), "current job user id", maximum=160) != user_id
        or _text(getattr(current, "job_id", None), "current job id", maximum=160) != job_id
        or str(getattr(current, "status", "")).strip().lower() in _TERMINAL_JOB_STATUSES
    ):
        raise FleetContractError("owned Agent Job is no longer reconnectable")
    # The route-owned job is the authorization object.  A concurrent update must
    # not retarget an already-bound session to another repository/workspace.
    for field in ("repo_url", "branch"):
        if _text(getattr(current, field, None), f"current job {field}", maximum=500) != _text(
            getattr(initial_job, field, None), f"initial job {field}", maximum=500
        ):
            raise FleetContractError("owned Agent Job immutable binding changed during reconnect")
    if _workspace_id_for_job(current) != _workspace_id_for_job(initial_job):
        raise FleetContractError("owned Agent Job immutable binding changed during reconnect")
    return current


@dataclass(frozen=True)
class LiveWorkspaceContextResolver:
    """Server-only resolver dependency injected into the GET reconnect route."""

    workspace_root: Path | None = None
    active_run_reader: ActiveRunReader = read_active_agent_run_for_job
    stage_evidence_reader: StageEvidenceReader = read_live_workspace_stage_evidence
    attempt_workspace_reader: AttemptWorkspaceReader = read_active_attempt_worktree
    job_reader: JobReader = read_agent_job

    def __call__(self, conn: Any, job: Any) -> LiveWorkspaceContextV1 | None:
        try:
            user_id = _text(getattr(job, "user_id", None), "job user id", maximum=160)
            job_id = _text(getattr(job, "job_id", None), "job id", maximum=160)
            if str(getattr(job, "status", "")).strip().lower() in _TERMINAL_JOB_STATUSES:
                return None
            initial = _read_current_reconnect_state(
                conn=conn,
                job=job,
                user_id=user_id,
                job_id=job_id,
                active_run_reader=self.active_run_reader,
                stage_evidence_reader=self.stage_evidence_reader,
            )
            assignment = initial.snapshot.assignments_by_role[initial.role]
            attempt = initial.snapshot.attempts_by_role[initial.role]
            current = self.attempt_workspace_reader(
                assignment=assignment,
                attempt=attempt,
                active_attempt=attempt,
                repository_url=str(getattr(job, "repo_url", "")),
                root=self.workspace_root,
            )
            _verify_static_attempt_receipt(persisted=initial.snapshot.receipts_by_role[initial.role], current=current)
            readback = _workspace_readback(
                state=initial,
                assignment=assignment,
                attempt=attempt,
                workspace=current,
                job_id=job_id,
            )
            session = LiveWorkspaceSessionV1.bind(
                assignment=assignment,
                attempt=attempt,
                active_attempt=attempt,
                workspace_readback=readback,
                projection_source_hashes=(
                    initial.snapshot.evidence_sha256,
                    initial.active_lane.evidence_sha256,
                    current.worktree_readback_sha256,
                    readback.controller_state_ref,
                ),
            )
            # Re-read all controller and worktree state after binding.  Binding and
            # reconciling against the same objects would otherwise race a retry or
            # a completed lane into a false LIVE projection.
            fresh_job = _read_current_owned_job(
                conn=conn,
                initial_job=job,
                user_id=user_id,
                job_id=job_id,
                job_reader=self.job_reader,
            )
            fresh = _read_current_reconnect_state(
                conn=conn,
                job=fresh_job,
                user_id=user_id,
                job_id=job_id,
                active_run_reader=self.active_run_reader,
                stage_evidence_reader=self.stage_evidence_reader,
            )
            fresh_assignment = fresh.snapshot.assignments_by_role[fresh.role]
            fresh_attempt = fresh.snapshot.attempts_by_role[fresh.role]
            if (
                fresh.run.run_id != initial.run.run_id
                or str(fresh.run.status).upper() != str(initial.run.status).upper()
                or fresh.role != initial.role
                or fresh.snapshot.evidence_sha256 != initial.snapshot.evidence_sha256
                or fresh.active_lane.evidence_sha256 != initial.active_lane.evidence_sha256
                or fresh_assignment != assignment
                or fresh_attempt != attempt
            ):
                return None
            fresh_workspace = self.attempt_workspace_reader(
                assignment=fresh_assignment,
                attempt=fresh_attempt,
                active_attempt=fresh_attempt,
                repository_url=str(getattr(fresh_job, "repo_url", "")),
                root=self.workspace_root,
            )
            _verify_static_attempt_receipt(
                persisted=fresh.snapshot.receipts_by_role[fresh.role],
                current=fresh_workspace,
            )
            current_changed_paths = _safe_changed_paths(fresh_workspace.changed_paths)
            fresh_readback = _workspace_readback(
                state=fresh,
                assignment=fresh_assignment,
                attempt=fresh_attempt,
                workspace=fresh_workspace,
                job_id=job_id,
            )
            reconciliation = session.reconcile(active_attempt=fresh_attempt, workspace_readback=fresh_readback)
            if reconciliation.projection_state != "LIVE":
                return None
            # Ensure public data stays path-free even if a future worktree reader
            # returns a path-shaped changed-path value.
            if current_changed_paths != fresh_workspace.changed_paths:
                return None
            return LiveWorkspaceContextV1(
                session=session,
                reconciliation=reconciliation,
                attempt_workspace=fresh_workspace,
                role=fresh.role,
                run_id=fresh.run.run_id,
                fleet_snapshot_evidence_sha256=fresh.snapshot.evidence_sha256,
                active_lane_evidence_sha256=fresh.active_lane.evidence_sha256,
            )
        except (FleetContractError, WorkspacePolicyError, OSError, TypeError, ValueError, KeyError, AttributeError):
            return None


def build_live_workspace_context_resolver(
    *,
    workspace_root: Path | None = None,
    active_run_reader: ActiveRunReader = read_active_agent_run_for_job,
    stage_evidence_reader: StageEvidenceReader = read_live_workspace_stage_evidence,
    attempt_workspace_reader: AttemptWorkspaceReader = read_active_attempt_worktree,
    job_reader: JobReader = read_agent_job,
) -> LiveWorkspaceContextResolver:
    """Create the sole safe GET/reconnect resolver; no generic tool route uses it."""

    return LiveWorkspaceContextResolver(
        workspace_root=workspace_root,
        active_run_reader=active_run_reader,
        stage_evidence_reader=stage_evidence_reader,
        attempt_workspace_reader=attempt_workspace_reader,
        job_reader=job_reader,
    )


__all__ = [
    "LIVE_WORKSPACE_CONTEXT_SCHEMA_VERSION",
    "LiveWorkspaceContextResolver",
    "LiveWorkspaceContextV1",
    "build_live_workspace_context_resolver",
]
