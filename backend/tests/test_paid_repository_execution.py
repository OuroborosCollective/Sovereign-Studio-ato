"""Real submit and SDK stage contracts; external DB/provider adapters are isolated."""
import asyncio
from types import SimpleNamespace

import pytest

from backend.agent_runtime import cognitive_swarm_agents as agents
from backend.agent_runtime.cognitive_output_budget import SINGLE_AGENT_REQUEST_LIMIT
from backend.agent_runtime.cognitive_usage_billing import AgentBillingError, AgentStageBilling
from backend.agent_runtime import repository_execution as execution
from backend.tests.test_repository_execution import pending_execution


@pytest.mark.parametrize("mode", ["free", "paid"])
def test_owner_selection_is_bound_to_permission_and_reaches_only_its_transport(pending_execution, monkeypatch, mode):
    state = pending_execution
    selected = []
    billing = []
    conn = SimpleNamespace(close=lambda: None)
    execution._bind_repository_execution_permission(conn, job=state.job, expected_head_sha="1"*40, execution_mode=mode)
    assert execution.read_repository_execution_mode(conn, job=state.job) == mode
    assert execution._require_repository_effect_authority(conn, job=state.job)
    monkeypatch.setattr(execution, "read_agent_task_ids", lambda *_args, **_kw: {f"{mode}_single_agent": "task-real"})
    def resolve(*_args, **kwargs):
        selected.append(kwargs["requested_mode"])
        return SimpleNamespace(profile_id=execution.PAID_SWARM_PROFILE if mode == "paid" else execution.FREE_SINGLE_AGENT_PROFILE,
            repository_execution_allowed=True, primary_route={"id": "route-real"})
    monkeypatch.setattr(execution, "load_execution_resolution", resolve)
    monkeypatch.setattr(execution, "AgentStageBilling", lambda **kwargs: billing.append(kwargs) or object())
    async def paid(*_args, **kwargs):
        assert "stage_billing" in kwargs
        state.model_calls += 1
        return {"status": "BLOCKED", "reason": "Stopped at the isolated provider adapter."}
    monkeypatch.setattr(execution, "run_paid_single_agent", paid)
    result = state.submit()
    assert result.status == "blocked"
    assert selected == [mode]
    assert state.model_calls == 1
    assert len(billing) == (1 if mode == "paid" else 0)
    if billing:
        assert billing[0]["requested_mode"] == "paid"
        assert state.receipts[-1].normalized_parameters["execution_mode"] == "paid"
    state.submit()
    assert state.model_calls == 1


def test_free_selection_never_accepts_a_paid_resolution_or_starts_billing(pending_execution, monkeypatch):
    state = pending_execution
    monkeypatch.setattr(execution, "load_execution_resolution", lambda *_a, **_k: SimpleNamespace(
        profile_id=execution.PAID_SWARM_PROFILE, repository_execution_allowed=True, primary_route={}))
    def forbidden(**kwargs):
        pytest.fail("A Free permission must never reach Paid billing")
    monkeypatch.setattr(execution, "AgentStageBilling", forbidden)
    result = state.submit()
    assert result.status == "blocked"
    assert "NO_VERIFIED_FREE_SINGLE_AGENT_ROUTE" in result.blocker
    assert state.model_calls == 0


def test_free_swarm_capable_catalog_still_runs_exactly_one_free_agent(pending_execution, monkeypatch):
    monkeypatch.setattr(execution, "load_execution_resolution", lambda *_a, **_k: SimpleNamespace(
        profile_id=execution.FREE_SWARM_PROFILE, repository_execution_allowed=True, primary_route={}))
    monkeypatch.setattr(execution, "AgentStageBilling", lambda **_kw: pytest.fail("Free single agent reached billing"))
    pending_execution.submit()
    assert pending_execution.model_calls == 1


def test_paid_selection_never_falls_back_to_free(pending_execution, monkeypatch):
    state = pending_execution
    execution._bind_repository_execution_permission(SimpleNamespace(), job=state.job, expected_head_sha="1"*40, execution_mode="paid")
    monkeypatch.setattr(execution, "read_agent_task_ids", lambda *_a, **_k: {"paid_single_agent": "task-real"})
    result = state.submit()  # The fixture resolves only Free.
    assert result.status == "blocked"
    assert "NO_VERIFIED_PAID_SINGLE_AGENT_ROUTE" in result.blocker
    assert state.model_calls == 0


def test_submit_persists_real_paid_billing_blocker_before_provider_io(pending_execution, monkeypatch):
    state = pending_execution
    execution._bind_repository_execution_permission(SimpleNamespace(), job=state.job, expected_head_sha="1"*40, execution_mode="paid")
    monkeypatch.setattr(execution, "read_agent_task_ids", lambda *_a, **_k: {"paid_single_agent": "task-real"})
    monkeypatch.setattr(execution, "load_execution_resolution", lambda *_a, **_k: SimpleNamespace(
        profile_id=execution.PAID_SWARM_PROFILE, repository_execution_allowed=True, primary_route={}))
    def unavailable(**kwargs):
        raise AgentBillingError("INSUFFICIENT_PROVIDER_FUNDED_CREDITS", required_credits=25, available_credits=2)
    monkeypatch.setattr(execution, "AgentStageBilling", unavailable)
    result = state.submit()
    assert result.status == "blocked"
    assert result.events[-1]["stage"] == "sovereign_executor_billing_blocked"
    assert "requiredCredits=25" in result.blocker and "availableProviderFundedCredits=2" in result.blocker
    assert state.model_calls == 0


def test_paid_permission_is_revocation_checked_before_billing(pending_execution, monkeypatch):
    state = pending_execution
    execution._bind_repository_execution_permission(SimpleNamespace(), job=state.job, expected_head_sha="1"*40, execution_mode="paid")
    from backend.agent_runtime.revocation_closure import create_revocation_transition
    receipt, _ = create_revocation_transition(state.receipts[-1], revocation_sequence=2,
        revocation_epoch_ms=2000, reason_code="OWNER_REVOKED", revoker_identity="owner-regression")
    state.receipts.append(receipt)
    monkeypatch.setattr(execution, "AgentStageBilling", lambda **_kw: pytest.fail("Revoked permission reached billing"))
    assert state.submit().status == "blocked"
    assert state.model_calls == 0


@pytest.mark.parametrize("outcome", ["success", "reservation-fails", "settlement-fails", "provider-fails", "wrong-transport"])
def test_paid_sdk_stage_reserves_before_io_and_settles_before_completion(monkeypatch, outcome):
    sequence = []
    result = SimpleNamespace(final_output="Actual provider adapter result")
    class BillingAdapter:
        def reserve(self, **kwargs):
            assert kwargs["stage"] == "paid-single-agent"
            sequence.append("reserve")
            if outcome == "reservation-fails":
                raise AgentBillingError("INSUFFICIENT_PROVIDER_FUNDED_CREDITS")
            return object()
        def settle(self, reservation, actual_result):
            assert actual_result is result
            sequence.append("settle")
            if outcome == "settlement-fails":
                raise AgentBillingError("AGENT_ACTUAL_COST_EXCEEDED_RESERVATION")
        def mark_reconciliation_required(self, reservation, **kwargs):
            sequence.append("reconcile")
        def refund_failed_before_usage(self, reservation, **kwargs):
            sequence.append("refund")
    class ProviderAdapter:
        @staticmethod
        async def run(agent, prompt, **kwargs):
            assert kwargs["max_turns"] == AgentStageBilling.request_upper_bound("paid-single-agent") == SINGLE_AGENT_REQUEST_LIMIT
            sequence.append("provider")
            if outcome == "provider-fails":
                raise RuntimeError("isolated provider failure")
            return result
    monkeypatch.setattr(agents, "_require_agents_sdk", lambda: (lambda **kwargs: SimpleNamespace(**kwargs), ProviderAdapter))
    monkeypatch.setattr(agents, "build_route_run_config", lambda *_a, **_k: SimpleNamespace(
        transport="freellm" if outcome == "wrong-transport" else "openrouter", model="model-real", run_config=object()))
    intent = agents.MissionIntent(mode="repository_execution", normalized_goal="Create Testgb",
        requires_online_tools=True, requires_repository_workspace=True, learning_scope=[], confidence=1)
    stages = []
    async def invoke():
        return await agents.run_paid_single_agent("Create Testgb", model="model-real", route={"id": "paid-real"},
            intent=intent, stage_billing=BillingAdapter(), repository_tool_factory=lambda role: [object()] if role == "paid_single_agent" else [],
            stage_observer=lambda stage: stages.append(stage))
    if outcome == "success":
        actual = asyncio.run(invoke())
        assert actual["executionProfile"] == "paid_single_agent"
        assert actual["maxBackgroundAgents"] == 0
        assert sequence == ["reserve", "provider", "settle"]
        assert stages[-1]["eventType"] == "agent_completed"
    else:
        with pytest.raises((AgentBillingError, ValueError, agents.SwarmExecutionError)):
            asyncio.run(invoke())
        assert not any(stage["eventType"] == "agent_completed" for stage in stages)
        if outcome in {"reservation-fails", "wrong-transport"}:
            assert "provider" not in sequence
        if outcome == "provider-fails":
            assert sequence[-1] == "reconcile"


@pytest.mark.parametrize("mode", ["free", "paid"])
def test_single_agent_configuration_failure_keeps_the_actual_execution_mode(mode):
    intent = agents.MissionIntent(mode="repository_execution", normalized_goal="Create Testgb",
        requires_online_tools=True, requires_repository_workspace=True, learning_scope=[], confidence=1)
    if mode == "paid":
        invocation = agents.run_paid_single_agent("Create Testgb", model="model-real", route=None,
            intent=intent, stage_billing=object())
    else:
        invocation = agents.run_free_single_agent("Create Testgb", model="model-real", route=None, intent=intent)
    with pytest.raises(agents.SwarmExecutionError) as error:
        asyncio.run(invocation)
    assert error.value.stage == f"{mode}-single-agent"
    assert error.value.next_action == f"RESOLVE_DATABASE_{'OPENROUTER' if mode == 'paid' else 'FREELLM'}_ROUTE"


@pytest.mark.parametrize("capacity", ["funded", "premium", "insufficient", "contradicted", "changed-route"])
def test_real_billing_owner_reserves_and_settles_actual_provider_usage(capacity):
    from backend.tests.test_cognitive_usage_billing_openrouter import _route
    route = _route("route-real", "provider/test-model", input_price=0.75, output_price=4.5)
    if capacity == "premium":
        route["config"].update({"billingCategory": "premium", "billingClass": "premium", "markupMultiplier": 8})
    writes = []
    account = {"id": "11111111-1111-4111-8111-111111111111", "email": "user@example.test", "role": "user",
               "credits": 100000, "provider_funded_credits": 100000 if capacity != "insufficient" else 0}
    class DatabaseAdapter:
        def __init__(self):
            self.result = None
        def cursor(self): return self
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def close(self): pass
        def commit(self): pass
        def rollback(self): pass
        def execute(self, statement, params=None):
            if "FROM llm_routes" in statement:
                self.result = {**route, "config": {**route["config"], "outputUsdPerMillion": 9}} if capacity == "changed-route" else route
            elif "FROM admin_users" in statement:
                self.result = account.copy()
            elif "SUM(amount)" in statement:
                self.result = {"balance": account["credits"] - (1 if capacity == "contradicted" else 0)}
            elif "AS purchased" in statement:
                self.result = {"purchased": True}
            elif "INSERT" in statement or "UPDATE" in statement:
                writes.append((statement, params))
                if "UPDATE admin_users" in statement:
                    direction = 1 if "credits=credits+" in statement else -1
                    account["credits"] += direction * params[0]
                    account["provider_funded_credits"] += direction * params[1]
            else:
                raise AssertionError(statement)
        def fetchone(self): return self.result
    database = DatabaseAdapter()
    if capacity not in {"funded", "premium"}:
        with pytest.raises(AgentBillingError):
            billing = AgentStageBilling(get_connection=lambda: database, user_id=account["id"], run_id="repo-real",
                trace_id="trace-real", route=route, requested_mode="paid")
            billing.reserve(stage="paid-single-agent", prompt="Create Testgb")
        assert writes == []
        return
    billing = AgentStageBilling(get_connection=lambda: database, user_id=account["id"], run_id="repo-real",
        trace_id="trace-real", route=route, requested_mode="paid", allow_premium=True)
    reservation = billing.reserve(stage="paid-single-agent", prompt="Create Testgb")
    assert reservation.request_upper_bound == SINGLE_AGENT_REQUEST_LIMIT
    assert account["credits"] == 100000 - reservation.reserved_credits
    result = SimpleNamespace(context_wrapper=SimpleNamespace(usage={"input_tokens": 100, "output_tokens": 50,
        "requests": 2, "cost": 0.001}), raw_responses=[])
    settlement = billing.settle(reservation, result)
    assert settlement["billedCredits"] > 0
    assert account["credits"] == account["provider_funded_credits"] == 100000 - settlement["billedCredits"]
    ledger = [params[1] for statement, params in writes if "INSERT INTO credit_ledger" in statement]
    assert sum(ledger) == -settlement["billedCredits"]
    assert any("status='settled_usage'" in statement for statement, _ in writes)
