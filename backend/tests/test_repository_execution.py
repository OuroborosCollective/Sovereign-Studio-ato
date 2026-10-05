from __future__ import annotations

from pathlib import Path
from dataclasses import replace
import asyncio
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/sovereign-backend"))
sys.path.insert(0, str(ROOT))

from backend.agent_runtime import repository_execution as execution
from backend.agent_runtime import cognitive_run_store as runtime_store
from backend.agent_runtime.job_store import StoredSovereignAgentJob
from backend.agent_runtime.revocation_closure import create_revocation_transition, PermissionAuthorityHead


@pytest.fixture
def pending_execution(monkeypatch, tmp_path):
    """Exercise the real claim, permission gate and submit path; replace I/O only."""
    job = StoredSovereignAgentJob(
        job_id="agent-regression", user_id="owner-regression", executor="sovereign-local-runner",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato", branch="main",
        mission="Create Testgb with 1987a26 and prepare a Draft PR.", status="running",
        workspace_id="agent-regression", external_ref=execution._pending_submit_ref("agent-regression"),
    )
    state = SimpleNamespace(job=job, receipts=[], binding=None, model_calls=0)
    conn = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(execution, "persist_workflow_run", lambda *_: None)
    monkeypatch.setattr(execution, "append_permission_receipt", lambda _, **kw: state.receipts.append(kw["receipt"]))
    def bind(_, **kw):
        receipt = kw["approved_receipt"]
        state.binding = {"job_id": kw["job_id"], "workflow_run_id": receipt.binding.workflow_run_id,
                         "permission_id": receipt.permission_id, "approved_receipt_hash": receipt.receipt_hash}
    monkeypatch.setattr(execution, "bind_repository_job_permission", bind)
    monkeypatch.setattr(execution, "read_repository_job_permission_binding", lambda _, **kw: state.binding, raising=False)
    monkeypatch.setattr(execution, "read_latest_permission_receipt", lambda _, **kw: (state.receipts[-1], len(state.receipts)-1))
    def head(_, **kw):
        receipt = state.receipts[-1]
        material = {"permission_id": receipt.permission_id, "workflow_run_id": receipt.binding.workflow_run_id,
                    "receipt_hash": receipt.receipt_hash, "receipt_sequence": len(state.receipts)-1,
                    "decision": receipt.decision.value}
        return PermissionAuthorityHead(**(material | {"decision": receipt.decision}),
                                       readback_hash=execution.canonical_sha256(material))
    monkeypatch.setattr(execution, "read_permission_authority_head", head)
    monkeypatch.setattr(execution, "read_agent_job", lambda _, **kw: state.job)
    def update(_, **kw):
        fields = {key: value for key, value in kw.items() if key in {"status", "workspace_id", "blocker"}}
        if kw.get("clear_blocker"): fields["blocker"] = None
        state.job = replace(state.job, **fields)
    monkeypatch.setattr(execution, "update_agent_job_state", update)
    def event(_, job_id, value):
        state.job = replace(state.job, events=(*state.job.events, {"stage": value.stage, "level": value.level,
                                                                 "message": value.message, "at": value.at}))
    monkeypatch.setattr(execution, "append_agent_event", event)
    def cas(_, **kw):
        if state.job.external_ref != kw["expected_ref"]: return False
        state.job = replace(state.job, external_ref=kw["new_ref"])
        return True
    monkeypatch.setattr(execution, "compare_and_swap_agent_job_external_ref", cas)
    monkeypatch.setattr(execution, "read_agent_run", lambda _, **kw: SimpleNamespace(evidence_id="evidence-regression", trace_id="trace-regression"))
    monkeypatch.setattr(execution, "read_agent_task_ids", lambda _, **kw: {"free_single_agent": "task-regression"})
    monkeypatch.setattr(execution, "transition_agent_run", lambda *args, **kw: None)
    monkeypatch.setattr(execution, "append_repository_executor_heartbeat", lambda *args, **kw: True)
    resolution = SimpleNamespace(profile_id=execution.FREE_SINGLE_AGENT_PROFILE, repository_execution_allowed=True,
                                 primary_route=SimpleNamespace())
    monkeypatch.setattr(execution, "load_execution_resolution", lambda *args, **kw: resolution)
    monkeypatch.setattr(execution, "route_provider_model", lambda _: "test-provider-boundary")
    async def model(*args, **kw):
        state.model_calls += 1
        return {"status": "BLOCKED", "reason": "Provider boundary stopped by regression test."}
    monkeypatch.setattr(execution, "run_free_single_agent", model)
    (tmp_path / job.workspace_id / "repo" / ".git").mkdir(parents=True)
    execution._bind_repository_execution_permission(conn, job=job, expected_head_sha="1"*40)
    state.submit = lambda: execution._submit_pending_repository_job(conn, job=state.job,
                              workspace_root=tmp_path, get_connection=lambda: conn)
    return state


def test_pending_submit_reaches_model_once_with_real_live_permission(pending_execution):
    result = pending_execution.submit()
    assert pending_execution.model_calls == 1, result.blocker
    assert any(event["stage"] == "sovereign_executor_started" for event in result.events)
    pending_execution.submit()
    assert pending_execution.model_calls == 1


def test_missing_permission_is_persisted_as_blocked(pending_execution):
    pending_execution.binding = None
    result = pending_execution.submit()
    assert result.status == "blocked"
    assert result.events[-1]["stage"] == "repository_permission_unbound"
    assert pending_execution.model_calls == 0


def test_revoked_permission_never_starts_executor(pending_execution):
    revoked, _ = create_revocation_transition(pending_execution.receipts[-1], revocation_sequence=2,
        revocation_epoch_ms=2000, reason_code="OWNER_REVOKED", revoker_identity="owner-regression")
    pending_execution.receipts.append(revoked)
    result = pending_execution.submit()
    assert result.status == "blocked"
    assert result.events[-1]["stage"] == "repository_revocation_blocked"
    assert pending_execution.model_calls == 0


@pytest.mark.parametrize("field,value", [("job_id", "agent-other"), ("repo_url", "https://github.com/other/repo"),
                                         ("user_id", "other-owner"), ("workspace_id", "other-workspace"),
                                         ("mission", "A different instruction")])
def test_permission_for_another_scope_never_starts_executor(pending_execution, field, value):
    pending_execution.job = replace(pending_execution.job, **{field: value})
    result = pending_execution.submit()
    assert result.status == "blocked"
    assert pending_execution.model_calls == 0


def test_unexpected_preflight_error_is_visible_and_does_not_leave_running_claim(pending_execution, monkeypatch):
    def unreadable(*args, **kw):
        raise RuntimeError("private-provider-password must not enter evidence")
    monkeypatch.setattr(execution, "read_latest_permission_receipt", unreadable)
    result = pending_execution.submit()
    assert result.status == "blocked"
    assert result.events[-1]["stage"] == "sovereign_executor_submit_failed"
    assert "RuntimeError" in result.blocker
    assert "private-provider-password" not in result.blocker
    assert pending_execution.model_calls == 0


@pytest.fixture
def runtime_readback():
    payload = {"jobId": "agent-regression", "loop": 1, "rawModelOutputPersisted": False}
    row = {"event_id": "event-real", "run_id": "repo-agent-regression", "agent_id": "free_single_agent",
           "type": "single_agent_started", "status": "RUNNING", "source": "agents-sdk",
           "summary": "Persisted agent phase.", "next_action": "WAIT_FOR_AGENT",
           "created_at": "2026-10-02T21:10:26Z", "evidence_id": "evidence-real",
           "sha256": runtime_store._digest_text(runtime_store._json(payload)), "payload": payload,
           "user_id": "owner-regression", "job_id": "agent-regression",
           "evidence_run_id": "repo-agent-regression", "evidence_agent_id": "free_single_agent"}
    state = SimpleNamespace(rows=[row], queries=[])
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, params): state.queries.append((sql, params))
        def fetchall(self): return state.rows
    conn = SimpleNamespace(cursor=lambda: Cursor())
    state.read = lambda: runtime_store.read_job_runtime_evidence(conn, user_id="owner-regression", job_id="agent-regression")
    return state


def test_runtime_readback_exposes_real_evidence_identity_without_raw_payload(runtime_readback):
    events = runtime_readback.read()
    assert events[0]["eventId"] == "event-real"
    assert events[0]["evidenceId"] == "evidence-real"
    assert events[0]["evidenceSha256"] == runtime_readback.rows[0]["sha256"]
    assert events[0]["at"] == "2026-10-02T21:10:26Z"
    assert "payload" not in events[0]
    sql, params = runtime_readback.queries[0]
    assert "run.user_id = %s::uuid AND run.job_id = %s" in sql
    assert params == ("owner-regression", "agent-regression", 100)


@pytest.mark.parametrize("field,value", [("user_id", "other-owner"), ("job_id", "agent-other"),
    ("evidence_run_id", "repo-other"), ("evidence_agent_id", "other-agent"), ("sha256", "0"*64),
    ("created_at", None)])
def test_runtime_evidence_contradictions_fail_closed(runtime_readback, field, value):
    runtime_readback.rows[0][field] = value
    with pytest.raises(ValueError): runtime_readback.read()


def test_empty_runtime_evidence_does_not_manufacture_status_messages(runtime_readback):
    runtime_readback.rows = []
    assert runtime_readback.read() == ()


def test_real_executor_heartbeat_lifetime_and_claim_binding(pending_execution, monkeypatch):
    observed = []
    monkeypatch.setattr(execution, "_executor_heartbeat_seconds", lambda: 0.01)
    async def scenario():
        second = asyncio.Event()
        def persist(conn, **kw):
            observed.append(kw)
            if len(observed) == 2: second.set()
            return True
        monkeypatch.setattr(execution, "append_repository_executor_heartbeat", persist)
        async def model():
            await asyncio.wait_for(second.wait(), timeout=1)
            return "real-coroutine-return"
        result = await execution._run_with_executor_heartbeat(model, get_connection=lambda: SimpleNamespace(close=lambda: None),
            job=pending_execution.job, run_id="repo-agent-regression", claim_ref="claim-exact")
        assert result == "real-coroutine-return"
        assert len(observed) == 2
        await asyncio.sleep(0.03)
        assert len(observed) == 2  # observer is cancelled before closeout
    asyncio.run(scenario())
    assert all(row["job_id"] == "agent-regression" and row["claim_ref"] == "claim-exact" for row in observed)


def test_lost_heartbeat_claim_blocks_model_invocation(pending_execution, monkeypatch):
    monkeypatch.setattr(execution, "append_repository_executor_heartbeat", lambda *args, **kw: False)
    result = pending_execution.submit()
    assert result.status == "blocked"
    assert pending_execution.model_calls == 0
    assert "EXECUTOR_HEARTBEAT_CLAIM_NOT_CURRENT" in result.blocker


@pytest.mark.parametrize("current", [True, False])
def test_heartbeat_persistence_is_owner_claim_bound_and_never_updates_progress(current):
    queries, commits, rollbacks = [], [], []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, params): queries.append((sql, params))
        def fetchone(self): return {"trace_id": "trace-real"} if current else None
    conn = SimpleNamespace(cursor=lambda: Cursor(), commit=lambda: commits.append(True), rollback=lambda: rollbacks.append(True))
    claim = "sovereign-local-runner:claim:submit:exact-test"
    result = runtime_store.append_repository_executor_heartbeat(conn, user_id="owner-regression", job_id="agent-regression",
        run_id="repo-agent-regression", claim_ref=claim)
    assert result is current
    sql, params = queries[0]
    assert "job.status = 'running' AND job.external_ref = %s" in sql
    assert "run.user_id = %s::uuid AND job.user_id = %s::uuid" in sql
    assert params == ("owner-regression", "owner-regression", "repo-agent-regression", "agent-regression", claim)
    assert not any("UPDATE " in sql.upper() for sql, _ in queries)
    assert len(queries) == (3 if current else 1)
    assert len(commits) == int(current)
    assert len(rollbacks) == int(not current)


def test_heartbeat_payload_hash_is_verified_and_old_claim_cannot_look_current(runtime_readback):
    row = runtime_readback.rows[0]
    row["type"] = "sovereign_executor_heartbeat"
    row["payload"] = {"jobId": "agent-regression", "progressImplied": False, "claimSha256": "0"*64}
    row["sha256"] = runtime_store._digest_text(runtime_store._json(row["payload"]))
    assert runtime_readback.read()[0]["heartbeatCurrent"] is False
    row["payload"]["progressImplied"] = True
    row["sha256"] = runtime_store._digest_text(runtime_store._json(row["payload"]))
    with pytest.raises(ValueError): runtime_readback.read()


def source(relative: str) -> str:
    return (ROOT / relative).read_text("utf-8")


def section(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]


def test_active_repository_executor_is_sovereign_local_only() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    assert "AgentZeroA2AClient" not in runtime
    assert "AgentZeroA2AError" not in runtime
    assert "agent-zero-a2a:" not in runtime
    assert '_EXECUTOR_PREFIX: Final[str] = "sovereign-local-runner:"' in runtime
    assert '_EXECUTOR_PENDING_PREFIX: Final[str] = "sovereign-local-runner:pending:submit:"' in runtime
    assert '_EXECUTOR_CLAIM_PREFIX: Final[str] = "sovereign-local-runner:claim:"' in runtime


def test_repository_start_clones_into_the_isolated_workspace() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    start = section(
        runtime,
        "def start_repository_execution(",
        "def _submit_pending_repository_job(",
    )
    assert "provision_workspace=True" in start
    assert "clone_repo=True" in start
    assert "clone_repo=False" not in start
    assert "sovereign_repository_checked_out" in start
    assert "sovereign_local_execution_queued" in start


def test_single_agent_run_is_persisted_before_model_execution() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    submit = section(runtime, "def _ensure_local_single_agent_run(", "def _submit_after_claim(")
    assert "create_agent_run(" in submit
    assert "read_agent_run(" in submit
    assert "read_agent_task_ids(" in submit
    assert "create_repository_single_agent_task(" in submit
    assert '"free_single_agent"' in submit and '"paid_single_agent"' in submit
    assert 'status="RUNNING"' in submit
    assert 'source="agents-sdk"' in submit


def test_local_executor_binds_real_repository_toolset_and_free_route() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    submit = section(runtime, "def _submit_after_claim(", "def _safe_regression_commands(")
    assert "BoundRepositoryToolset(" in submit
    assert "write_confirmed=True" in submit
    assert "run_free_single_agent(" in submit
    assert "repository_tool_factory=repository_toolset.tools_for_role" in submit
    assert "capability_tool_factory=None" in submit
    assert 'requested_mode=execution_mode' in submit
    assert 'read_repository_execution_mode(conn, job=job)' in submit
    assert 'requested_mode="paid"' in submit
    assert "FREE_SINGLE_AGENT_PROFILE" in submit
    assert "route_provider_model" in submit


def test_local_executor_uses_the_isolated_repository_directory_as_tool_root() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    assert "repo_dir_for_workspace(workspace_id, workspace_root)" in runtime
    assert "workspace_root=repo_path.parent.parent" in runtime


def test_pending_reconcile_forwards_a_fresh_database_connection_and_workspace() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    pending = section(runtime, "def _submit_pending_repository_job(", "def _safe_regression_commands(")
    reconcile = section(runtime, "def reconcile_repository_jobs_once(", "def start_repository_reconciler(")
    assert "get_connection: ConnectionFactory | None = None" in pending
    assert "workspace_root=workspace_root" in pending
    assert "get_connection=get_connection" in pending
    assert "workspace_root=workspace_root" in reconcile
    assert "get_connection=get_connection" in reconcile


def test_local_executor_closeout_requires_real_git_diff_and_regression() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    closeout = section(runtime, "def _closeout_repository_job(", "def reconcile_repository_execution(")
    assert 'run_agent_job_tool(job, "git-status"' in closeout
    assert 'run_agent_job_tool(job, "diff"' in closeout
    assert "git_diff_full(" in closeout
    assert "git_diff_check(" in closeout
    assert "repository_regression_started" in closeout
    assert 'run_agent_job_tool(' in closeout
    assert '"test"' in closeout
    assert "evaluate_agent_evidence(" in closeout
    assert "prepare_draft_pr(" in closeout


def test_local_executor_never_auto_merges_or_deploys() -> None:
    tools = source("backend/agent_runtime/cognitive_repository_tools.py")
    task = section(tools, "def create_repository_single_agent_task(", "def _require_function_tool(")
    assert "No background agent, production deploy, merge or auto-merge is started." in task
    assert "start background agents" in task
    assert "merge a pull request" in task
    assert "deploy to production" in task
    assert "claim success without tool, diff and test evidence" in task


def test_cancellation_is_local_only() -> None:
    runtime = source("backend/agent_runtime/repository_execution.py")
    cancel = section(runtime, "def cancel_repository_execution(", "def _block_job(")
    assert 'status="blocked"' in cancel
    assert "sovereign_executor_cancelled" in cancel
    assert "external executor cancellation" in cancel
    assert "AgentZeroA2AClient" not in cancel
    assert "submit_repository_task" not in cancel


def test_frontend_repository_surface_matches_local_executor_contract() -> None:
    chat = source("src/features/control-surface-vnext/components/ChatSurface/ChatSurface.tsx")
    adapter = source("src/features/control-surface-vnext/adapter/repository-bound-adapter.ts")
    client = source("src/features/product/runtime/sovereignAgentClient.ts")
    assert "Sovereign · Free" in chat
    assert "Paid · direct OpenRouter" in chat
    assert "Free · direct FreeLLM. No credit deduction" in chat
    assert "Agent Zero" not in chat
    assert "executor === 'sovereign-local-runner'" in adapter
    assert "agent-zero-a2a:" not in adapter
    assert "Agent Zero A2A" not in client
    assert "Sovereign-local-runner route" in client


def test_unified_frontend_backend_boundary_has_no_external_repository_executor() -> None:
    runtime = source("src/features/product/runtime/sovereignAgentRuntime.ts")
    boundary = source("src/features/product/runtime/sovereignEngineBoundary.ts")
    bridge = source("src/features/product/runtime/devChatWorkerBridge.ts")
    assert "readSameOriginBackendUrl()" in runtime
    assert "await transport.startRepositoryExecution(command.payload.input)" in boundary
    assert "await transport.listJobs()" in boundary
    assert "agent-zero-a2a:" not in runtime
    assert "agent-zero-a2a:" not in bridge


def test_canonical_and_shipping_repository_execution_mirrors_are_equal() -> None:
    canonical = ROOT / "backend/agent_runtime/repository_execution.py"
    shipping = ROOT / "scripts/sovereign-backend/agent_runtime/repository_execution.py"
    assert shipping.read_bytes() == canonical.read_bytes()

def test_free_request_rejection_rotates_to_next_verified_route_before_mutation(
    pending_execution, monkeypatch
):
    route_a = {"id": "free-a", "model_id": "model-a"}
    route_b = {"id": "free-b", "model_id": "model-b"}
    resolution_a = SimpleNamespace(
        profile_id=execution.FREE_SINGLE_AGENT_PROFILE,
        repository_execution_allowed=True,
        primary_route=route_a,
        candidate_routes=(route_a, route_b),
        agent_route=route_a,
    )
    resolution_b = SimpleNamespace(
        profile_id=execution.FREE_SINGLE_AGENT_PROFILE,
        repository_execution_allowed=True,
        primary_route=route_b,
        candidate_routes=(route_b,),
        agent_route=route_b,
    )

    class Toolset:
        def tools_for_role(self, _role):
            return []

        def summary(self):
            return {"rolesWithMutations": []}

    monkeypatch.setattr(execution, "BoundRepositoryToolset", lambda **_kwargs: Toolset())
    monkeypatch.setattr(execution, "load_execution_resolution", lambda *args, **kwargs: resolution_a)
    monkeypatch.setattr(execution, "route_provider_model", lambda route: route["model_id"])

    attempted_routes = []

    async def model(*args, route, **kwargs):
        attempted_routes.append(route["id"])
        if route["id"] == "free-a":
            raise execution.SwarmExecutionError(
                stage="free-single-agent",
                family="FREELLM_REQUEST_REJECTED",
                error_type="BadRequestError",
                next_action="ADVANCE_FREE_REVOLVER_ROUTE",
                retryable=True,
                http_status=400,
            )
        return {"status": "BLOCKED", "reason": "second verified route reached"}

    monkeypatch.setattr(execution, "run_free_single_agent", model)
    monkeypatch.setattr(
        execution,
        "advance_free_revolver_resolution",
        lambda resolution, *, failed_route_id, reason: (
            resolution_b if failed_route_id == "free-a" else None
        ),
    )
    cooled = []
    monkeypatch.setattr(
        execution,
        "_record_repository_free_route_cooldown",
        lambda _get_connection, *, resolution, failure: cooled.append(
            resolution.primary_route["id"]
        ),
    )

    result = pending_execution.submit()

    assert attempted_routes == ["free-a", "free-b"]
    assert cooled == ["free-a"]
    assert result.status == "blocked"
    assert any(event["stage"] == "sovereign_free_route_rotated" for event in result.events)


def test_free_request_rejection_does_not_replay_after_repository_mutation(
    pending_execution, monkeypatch
):
    route_a = {"id": "free-a", "model_id": "model-a"}
    resolution_a = SimpleNamespace(
        profile_id=execution.FREE_SINGLE_AGENT_PROFILE,
        repository_execution_allowed=True,
        primary_route=route_a,
        candidate_routes=(route_a,),
        agent_route=route_a,
    )

    class MutatedToolset:
        def tools_for_role(self, _role):
            return []

        def summary(self):
            return {"rolesWithMutations": ["free_single_agent"]}

    monkeypatch.setattr(execution, "BoundRepositoryToolset", lambda **_kwargs: MutatedToolset())
    monkeypatch.setattr(execution, "load_execution_resolution", lambda *args, **kwargs: resolution_a)
    monkeypatch.setattr(execution, "route_provider_model", lambda route: route["model_id"])

    attempts = []

    async def model(*args, **kwargs):
        attempts.append("free-a")
        raise execution.SwarmExecutionError(
            stage="free-single-agent",
            family="FREELLM_REQUEST_REJECTED",
            error_type="BadRequestError",
            next_action="ADVANCE_FREE_REVOLVER_ROUTE",
            retryable=True,
            http_status=400,
        )

    monkeypatch.setattr(execution, "run_free_single_agent", model)
    advanced = []
    monkeypatch.setattr(
        execution,
        "advance_free_revolver_resolution",
        lambda *args, **kwargs: advanced.append(True),
    )

    result = pending_execution.submit()

    assert attempts == ["free-a"]
    assert advanced == []
    assert result.status == "blocked"
    assert result.events[-1]["stage"] == "sovereign_executor_execution_failed"
