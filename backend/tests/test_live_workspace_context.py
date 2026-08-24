from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.cognitive_repository_tools import build_repository_fleet_bindings
from agent_runtime.cognitive_run_store import StoredAgentRun
from agent_runtime.cognitive_swarm_manifest import WORKER_ROLES
from agent_runtime.fleet_attempts import create_worker_attempt
from agent_runtime.fleet_attempt_worktrees import provision_attempt_worktree
from agent_runtime.fleet_supervisor import FleetContractError, FleetPlan, stable_hash
from agent_runtime.live_workspace import WorkspaceReadbackV1
from agent_runtime.live_workspace_context import _safe_changed_paths, build_live_workspace_context_resolver


REPOSITORY_URL = "https://github.com/OuroborosCollective/Sovereign-Studio-ato"
REPOSITORY = "OuroborosCollective/Sovereign-Studio-ato"
USER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"
RUN_ID = "run-live-context"
JOB_ID = "job-live-context"


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=path, check=True, text=True, capture_output=True,
    )
    return completed.stdout.strip()


def _run(*, user_id: str = USER_ID, job_id: str = JOB_ID, status: str = "RUNNING") -> StoredAgentRun:
    return StoredAgentRun(
        run_id=RUN_ID,
        user_id=user_id,
        job_id=job_id,
        session_key="session-live-context",
        a2a_context_id=None,
        status=status,
        source="agents-sdk",
        evidence_id="evidence-initial",
        trace_id="trace-live-context",
        reason="running",
        next_action="WAIT_FOR_FLEET_LANE_COMPLETION",
        mission_summary="test live workspace context",
        mission_digest="a" * 64,
        max_active_specialists=6,
        max_iterations=2,
        iteration_count=0,
        lease_active=False,
        resume_task_id=None,
        updated_at="2026-01-01T00:00:00+00:00",
    )


def _record(*, event_type: str, status: str, payload: dict) -> dict[str, object]:
    full = {
        "agentId": "dispatcher",
        "eventType": event_type,
        "status": status,
        "rawModelOutputPersisted": False,
        **payload,
    }
    return {
        "eventId": f"event-{event_type}",
        "runId": RUN_ID,
        "jobId": JOB_ID,
        "evidenceRunId": RUN_ID,
        "eventAgentId": "dispatcher",
        "evidenceAgentId": "dispatcher",
        "eventSource": "agents-sdk",
        "evidenceSource": "agents-sdk",
        "eventType": event_type,
        "status": status,
        "evidenceSha256": stable_hash(full),
        "payload": full,
    }


def _fixture(tmp_path: Path):
    root = tmp_path / "workspaces"
    repo = root / JOB_ID / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "live-context@example.invalid")
    _git(repo, "config", "user.name", "Live Context Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")
    _git(repo, "remote", "add", "origin", REPOSITORY_URL)
    base_revision = _git(repo, "rev-parse", "HEAD")
    task_ids = {role: f"task-{index:02d}" for index, role in enumerate(WORKER_ROLES, start=1)}
    bindings = build_repository_fleet_bindings(
        run_id=RUN_ID,
        repository=REPOSITORY,
        workspace_id=JOB_ID,
        workspace_branch="main",
        base_revision=base_revision,
        task_ids_by_agent=task_ids,
    )
    attempts = {
        role: create_worker_attempt(assignment, attempt_sequence=1)
        for role, assignment in bindings.assignments_by_role.items()
    }
    workspaces = {
        role: provision_attempt_worktree(
            assignment=assignment,
            attempt=attempts[role],
            active_attempt=attempts[role],
            repository_url=REPOSITORY_URL,
            root=root,
        )
        for role, assignment in bindings.assignments_by_role.items()
    }
    job = SimpleNamespace(
        user_id=USER_ID,
        job_id=JOB_ID,
        workspace_id=JOB_ID,
        repo_url=REPOSITORY_URL,
        branch="main",
        status="running",
    )
    snapshot = {
        "fleetPlanHash": bindings.plan.plan_hash,
        "fleetPlan": bindings.plan.to_dict(),
        "fleetTaskIdsByRole": dict(bindings.task_ids_by_role),
        "fleetAssignmentsByRole": {
            role: assignment.to_dict()
            for role, assignment in bindings.assignments_by_role.items()
        },
        "fleetAttemptsByRole": {
            role: workspace.receipt_binding()
            for role, workspace in workspaces.items()
        },
    }
    lane = bindings.plan.lanes[0]
    records = (
        _record(event_type="fleet_plan_persisted", status="RUNNING", payload=snapshot),
        _record(
            event_type="fleet_lane_started",
            status="RUNNING",
            payload={"fleetPlanHash": bindings.plan.plan_hash, "fleetLaneId": lane.lane_id},
        ),
    )
    return root, repo, bindings, attempts, workspaces, job, snapshot, lane, records


def _resolver(
    *,
    root: Path,
    run: StoredAgentRun,
    records: tuple[dict[str, object], ...],
    job: SimpleNamespace,
):
    return build_live_workspace_context_resolver(
        workspace_root=root,
        active_run_reader=lambda _conn, **_kwargs: run,
        stage_evidence_reader=lambda _conn, **_kwargs: records,
        job_reader=lambda _conn, **_kwargs: job,
    )


def test_live_workspace_resolver_uses_existing_exact_attempt_and_never_provisions(tmp_path: Path) -> None:
    root, repo, _bindings, _attempts, workspaces, job, _snapshot, _lane, records = _fixture(tmp_path)
    before = _git(repo, "worktree", "list", "--porcelain")
    resolver = _resolver(root=root, run=_run(), records=records, job=job)

    first = resolver(None, job)
    second = resolver(None, job)

    assert first is not None and second is not None
    assert first.reconciliation.projection_state == "LIVE"
    assert first.attempt_workspace.attempt_id == workspaces[WORKER_ROLES[0]].attempt_id
    assert first.session.session_binding_hash == second.session.session_binding_hash
    assert _git(repo, "worktree", "list", "--porcelain") == before
    public = first.to_public_dict()
    assert "worktreePath" not in public["attempt"]
    assert "baseRepositoryPath" not in public["attempt"]
    assert str(first.attempt_workspace.worktree_path) not in str(public)
    assert str(first.attempt_workspace.base_repository_path) not in str(public)


def test_repository_fleet_plan_round_trips_through_persisted_contract(tmp_path: Path) -> None:
    _root, _repo, bindings, _attempts, _workspaces, _job, _snapshot, _lane, _records = _fixture(tmp_path)

    assert FleetPlan.from_dict(bindings.plan.to_dict()).to_dict() == bindings.plan.to_dict()


@pytest.mark.parametrize("kind", ("missing", "cross_user", "terminal"))
def test_live_workspace_resolver_blocks_non_live_or_unowned_run(tmp_path: Path, kind: str) -> None:
    root, _repo, _bindings, _attempts, _workspaces, job, _snapshot, _lane, records = _fixture(tmp_path)
    run = _run()
    if kind == "missing":
        active_reader = lambda _conn, **_kwargs: None
    elif kind == "cross_user":
        active_reader = lambda _conn, **_kwargs: _run(user_id=OTHER_USER_ID)
    else:
        active_reader = lambda _conn, **_kwargs: _run(status="COMPLETED")
    resolver = build_live_workspace_context_resolver(
        workspace_root=root,
        active_run_reader=active_reader,
        stage_evidence_reader=lambda _conn, **_kwargs: records,
    )

    assert resolver(None, job) is None


def test_live_workspace_resolver_blocks_no_active_or_ambiguous_lane(tmp_path: Path) -> None:
    root, _repo, bindings, _attempts, _workspaces, job, _snapshot, lane, records = _fixture(tmp_path)
    complete = _record(
        event_type="fleet_lane_completed",
        status="COMPLETED",
        payload={"fleetPlanHash": bindings.plan.plan_hash, "fleetLaneId": lane.lane_id},
    )
    resolver = _resolver(root=root, run=_run(), records=records + (complete,), job=job)
    assert resolver(None, job) is None

    ambiguous = records + (
        _record(
            event_type="fleet_lane_started",
            status="RUNNING",
            payload={"fleetPlanHash": bindings.plan.plan_hash, "fleetLaneId": bindings.plan.lanes[1].lane_id},
        ),
    )
    assert _resolver(root=root, run=_run(), records=ambiguous, job=job)(None, job) is None


def test_live_workspace_resolver_blocks_cross_role_or_attempt_receipt_mismatch(tmp_path: Path) -> None:
    root, _repo, bindings, _attempts, _workspaces, job, snapshot, lane, _records = _fixture(tmp_path)
    role = WORKER_ROLES[0]
    other = WORKER_ROLES[1]
    broken_assignment = dict(snapshot)
    broken_assignment["fleetAssignmentsByRole"] = dict(snapshot["fleetAssignmentsByRole"])
    broken_assignment["fleetAssignmentsByRole"][role] = snapshot["fleetAssignmentsByRole"][other]
    cross_role_records = (
        _record(event_type="fleet_plan_persisted", status="RUNNING", payload=broken_assignment),
        _record(event_type="fleet_lane_started", status="RUNNING", payload={"fleetPlanHash": bindings.plan.plan_hash, "fleetLaneId": lane.lane_id}),
    )
    assert _resolver(root=root, run=_run(), records=cross_role_records, job=job)(None, job) is None

    broken_attempt = dict(snapshot)
    broken_attempt["fleetAttemptsByRole"] = {
        item: dict(receipt) for item, receipt in snapshot["fleetAttemptsByRole"].items()
    }
    broken_attempt["fleetAttemptsByRole"][role]["attemptId"] = "attempt-000000000000000000000000"
    mismatch_records = (
        _record(event_type="fleet_plan_persisted", status="RUNNING", payload=broken_attempt),
        _record(event_type="fleet_lane_started", status="RUNNING", payload={"fleetPlanHash": bindings.plan.plan_hash, "fleetLaneId": lane.lane_id}),
    )
    assert _resolver(root=root, run=_run(), records=mismatch_records, job=job)(None, job) is None


def test_live_workspace_resolver_uses_rebound_attempt_and_stales_old_binding(tmp_path: Path) -> None:
    root, _repo, bindings, attempts, workspaces, job, snapshot, lane, records = _fixture(tmp_path)
    role = WORKER_ROLES[0]
    initial = _resolver(root=root, run=_run(), records=records, job=job)(None, job)
    assert initial is not None
    completed = _record(
        event_type="fleet_lane_completed",
        status="COMPLETED",
        payload={"fleetPlanHash": bindings.plan.plan_hash, "fleetLaneId": lane.lane_id},
    )
    retry_attempt = create_worker_attempt(bindings.assignments_by_role[role], attempt_sequence=2)
    retry_workspace = provision_attempt_worktree(
        assignment=bindings.assignments_by_role[role],
        attempt=retry_attempt,
        active_attempt=retry_attempt,
        repository_url=REPOSITORY_URL,
        root=root,
    )
    rebound = dict(snapshot)
    rebound["fleetAttemptsByRole"] = {
        item: workspace.receipt_binding()
        for item, workspace in workspaces.items()
    }
    rebound["fleetAttemptsByRole"][role] = retry_workspace.receipt_binding()
    retry_records = records + (
        completed,
        _record(event_type="fleet_attempt_rebound", status="RUNNING", payload=rebound),
        _record(event_type="fleet_lane_started", status="RUNNING", payload={"fleetPlanHash": bindings.plan.plan_hash, "fleetLaneId": lane.lane_id}),
    )
    current = _resolver(root=root, run=_run(), records=retry_records, job=job)(None, job)

    assert current is not None
    assert current.attempt_workspace.attempt_id == retry_attempt.attempt_id
    assert current.session.attempt_id != initial.session.attempt_id
    readback = WorkspaceReadbackV1.from_dict({
        "repository": current.session.repository,
        "workspaceId": current.session.workspace_id,
        "worktreeIdentityHash": current.session.worktree_identity_hash,
        "observedHeadRevision": current.session.observed_head_revision,
        "fleetPlanHash": current.session.fleet_plan_hash,
        "controllerStateRef": current.session.controller_state_ref,
        "controllerState": "RUNNING",
        "workspacePathOwner": current.session.workspace_id,
    })
    stale = initial.session.reconcile(active_attempt=retry_attempt, workspace_readback=readback)
    assert stale.projection_state == "STALE"
    assert "ACTIVE_ATTEMPT_CHANGED" in stale.blockers


def test_live_workspace_resolver_blocks_timeline_rebound_during_reconnect(tmp_path: Path) -> None:
    root, _repo, bindings, _attempts, workspaces, job, snapshot, lane, records = _fixture(tmp_path)
    rebound_role = WORKER_ROLES[1]
    retry_attempt = create_worker_attempt(bindings.assignments_by_role[rebound_role], attempt_sequence=2)
    retry_workspace = provision_attempt_worktree(
        assignment=bindings.assignments_by_role[rebound_role],
        attempt=retry_attempt,
        active_attempt=retry_attempt,
        repository_url=REPOSITORY_URL,
        root=root,
    )
    rebound = dict(snapshot)
    rebound["fleetAttemptsByRole"] = {
        role: workspace.receipt_binding() for role, workspace in workspaces.items()
    }
    rebound["fleetAttemptsByRole"][rebound_role] = retry_workspace.receipt_binding()
    completed = _record(
        event_type="fleet_lane_completed",
        status="COMPLETED",
        payload={"fleetPlanHash": bindings.plan.plan_hash, "fleetLaneId": lane.lane_id},
    )
    rebound_timeline = records + (
        completed,
        _record(event_type="fleet_attempt_rebound", status="RUNNING", payload=rebound),
        _record(
            event_type="fleet_lane_started",
            status="RUNNING",
            payload={"fleetPlanHash": bindings.plan.plan_hash, "fleetLaneId": lane.lane_id},
        ),
    )
    reads = [records, rebound_timeline]
    resolver = build_live_workspace_context_resolver(
        workspace_root=root,
        active_run_reader=lambda _conn, **_kwargs: _run(),
        stage_evidence_reader=lambda _conn, **_kwargs: reads.pop(0),
        job_reader=lambda _conn, **_kwargs: job,
    )

    assert resolver(None, job) is None
    assert reads == []


def test_live_workspace_resolver_blocks_rebound_that_advances_multiple_roles(tmp_path: Path) -> None:
    root, _repo, bindings, _attempts, workspaces, job, snapshot, lane, records = _fixture(tmp_path)
    rebound = dict(snapshot)
    rebound["fleetAttemptsByRole"] = {
        role: workspace.receipt_binding() for role, workspace in workspaces.items()
    }
    for role in WORKER_ROLES[1:3]:
        retry_attempt = create_worker_attempt(bindings.assignments_by_role[role], attempt_sequence=2)
        retry_workspace = provision_attempt_worktree(
            assignment=bindings.assignments_by_role[role],
            attempt=retry_attempt,
            active_attempt=retry_attempt,
            repository_url=REPOSITORY_URL,
            root=root,
        )
        rebound["fleetAttemptsByRole"][role] = retry_workspace.receipt_binding()
    timeline = records + (
        _record(
            event_type="fleet_lane_completed",
            status="COMPLETED",
            payload={"fleetPlanHash": bindings.plan.plan_hash, "fleetLaneId": lane.lane_id},
        ),
        _record(event_type="fleet_attempt_rebound", status="RUNNING", payload=rebound),
        _record(
            event_type="fleet_lane_started",
            status="RUNNING",
            payload={"fleetPlanHash": bindings.plan.plan_hash, "fleetLaneId": lane.lane_id},
        ),
    )

    assert _resolver(root=root, run=_run(), records=timeline, job=job)(None, job) is None


def test_live_workspace_resolver_blocks_job_state_change_during_reconnect(tmp_path: Path) -> None:
    root, _repo, _bindings, _attempts, _workspaces, job, _snapshot, _lane, records = _fixture(tmp_path)
    blocked_job = SimpleNamespace(**{**vars(job), "status": "blocked"})
    resolver = build_live_workspace_context_resolver(
        workspace_root=root,
        active_run_reader=lambda _conn, **_kwargs: _run(),
        stage_evidence_reader=lambda _conn, **_kwargs: records,
        job_reader=lambda _conn, **_kwargs: blocked_job,
    )

    assert resolver(None, job) is None


def test_live_workspace_resolver_accepts_equivalent_workspace_id_fallback(tmp_path: Path) -> None:
    root, _repo, _bindings, _attempts, _workspaces, job, _snapshot, _lane, records = _fixture(tmp_path)
    fresh_job = SimpleNamespace(**{**vars(job), "workspace_id": None})
    resolver = build_live_workspace_context_resolver(
        workspace_root=root,
        active_run_reader=lambda _conn, **_kwargs: _run(),
        stage_evidence_reader=lambda _conn, **_kwargs: records,
        job_reader=lambda _conn, **_kwargs: fresh_job,
    )

    assert resolver(None, job) is not None


@pytest.mark.parametrize(
    "paths",
    [
        ("C:\\attempt\\secret.py",),
        ("//server/share/secret.py",),
        ("\\\\server\\share\\secret.py",),
        tuple(f"src/{index}.py" for index in range(257)),
    ],
)
def test_live_workspace_changed_paths_reject_absolute_and_unbounded_values(paths: tuple[str, ...]) -> None:
    with pytest.raises(FleetContractError):
        _safe_changed_paths(paths)


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "backend").is_dir() and (candidate / "scripts/sovereign-backend").is_dir():
            return candidate
    raise AssertionError("repository root not found")


def test_live_workspace_context_module_is_byte_identical_in_deployment_mirror() -> None:
    root = _repo_root()
    assert (
        root / "backend/agent_runtime/live_workspace_context.py"
    ).read_bytes() == (
        root / "scripts/sovereign-backend/agent_runtime/live_workspace_context.py"
    ).read_bytes()
