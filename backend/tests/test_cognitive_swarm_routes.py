from functools import wraps
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

from flask import Flask, request
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from agent_runtime import cognitive_swarm_routes as routes_runtime
from agent_runtime.cognitive_swarm_agents import MissionIntent, SwarmExecutionError
from agent_runtime.cognitive_swarm_routes import register_cognitive_swarm_routes


USER_ID = "00000000-0000-0000-0000-000000000001"


async def _read_only_intent(
    mission: str,
    *,
    model: str | None = None,
    stage_billing: Any = None,
) -> MissionIntent:
    return MissionIntent(
        mode="read_only_analysis",
        normalized_goal=mission.strip(),
        requires_online_tools=True,
        requires_repository_workspace=False,
        learning_scope=[],
        confidence=1.0,
    )


@pytest.fixture(autouse=True)
def isolate_internal_litellm_configuration(monkeypatch, tmp_path: Path) -> None:
    owner_root = tmp_path / "missing-owner-secrets"
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(owner_root))
    monkeypatch.setenv(
        "LITELLM_MASTER_KEY_FILE",
        str(owner_root / "litellm_master_key.txt"),
    )
    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm:4000")


class FakeCursor:
    def __init__(self, factory: "FakeConnectionFactory") -> None:
        self.factory = factory
        self.last_sql = ""

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self.last_sql = " ".join(sql.split())
        self.factory.calls.append((self.last_sql, params))

    def fetchone(self):
        if "FROM llm_routes" in self.last_sql:
            if not self.factory.route_ready:
                return None
            return {
                "model_id": "sovereign-fast",
                "config": {
                    "providerModel": "gpt-5.4-mini",
                    "billingCategory": "standard",
                    "markupMultiplier": 4,
                    "inputUsdPerMillion": "0.25",
                    "cachedInputUsdPerMillion": "0.025",
                    "outputUsdPerMillion": "2.00",
                    "pricingVerified": True,
                    "pricingSource": "test-fixture",
                },
            }
        if self.factory.fetchone_rows:
            return self.factory.fetchone_rows.pop(0)
        if "RETURNING run_id" in self.last_sql:
            return {"run_id": "run-persisted"}
        return None

    def fetchall(self):
        return list(self.factory.fetchall_rows)


class FakeConnection:
    def __init__(self, factory: "FakeConnectionFactory") -> None:
        self.factory = factory
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.factory)

    def commit(self) -> None:
        self.factory.commits += 1

    def rollback(self) -> None:
        self.factory.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class FakeConnectionFactory:
    def __init__(self, *, fail: bool = False, route_ready: bool = True) -> None:
        self.fail = fail
        self.route_ready = route_ready
        self.calls: list[tuple[str, Any]] = []
        self.connections: list[FakeConnection] = []
        self.fetchone_rows: list[dict[str, Any]] = []
        self.fetchall_rows: list[dict[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0

    def __call__(self) -> FakeConnection:
        if self.fail:
            raise RuntimeError("database unavailable")
        connection = FakeConnection(self)
        self.connections.append(connection)
        return connection


def _stored_run_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "run_id": "run-resumable",
        "user_id": USER_ID,
        "job_id": None,
        "session_key": "session-resumable",
        "status": "FAILED_RECOVERABLE",
        "source": "agents-sdk",
        "evidence_id": "evidence-resumable",
        "trace_id": "trace-resumable",
        "reason": "Previous SDK execution failed recoverably.",
        "next_action": "RETRY_FROM_PERSISTED_RUN_STATE",
        "mission_summary": "Resume the persisted SDK run from its next action.",
        "mission_digest": "b" * 64,
        "max_active_specialists": 4,
        "max_iterations": 12,
        "iteration_count": 3,
        "lease_active": False,
        "resume_task_id": None,
    }
    row.update(overrides)
    return row


def _require_session(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        request.session_user_id = USER_ID
        return handler(*args, **kwargs)
    return wrapped


def _app(factory: FakeConnectionFactory | None = None) -> Flask:
    app = Flask(__name__)
    register_cognitive_swarm_routes(
        app,
        require_session=_require_session,
        get_connection=factory or FakeConnectionFactory(),
    )
    return app


def test_swarm_manifest_route_reports_exact_topology(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SOVEREIGN_AGENTS_ALLOWED_MODELS", raising=False)
    client = _app().test_client()
    response = client.get("/api/user/agent/swarm/manifest")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["runtime"] == "openai-agents-sdk"
    assert payload["configured"] is False
    assert payload["manifest"]["agentCount"] == 20
    assert payload["manifest"]["coreAgentCount"] == 8
    assert payload["manifest"]["maxActiveSpecialists"] == 4
    assert payload["manifest"]["autoMerge"] is False
    assert payload["allowedModels"] == ["sovereign-fast"]


def test_allowed_models_drop_direct_provider_identifiers(monkeypatch) -> None:
    monkeypatch.setenv(
        "SOVEREIGN_AGENTS_ALLOWED_MODELS",
        "direct-provider-model,sovereign-fast",
    )
    assert routes_runtime._allowed_models() == frozenset({"sovereign-fast"})


def test_swarm_run_fails_closed_without_protected_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    factory = FakeConnectionFactory()
    client = _app(factory).test_client()
    response = client.post(
        "/api/user/agent/swarm/run",
        json={"mission": "Inspect supplied evidence.", "evidence": "No runtime evidence supplied."},
    )
    payload = response.get_json()
    assert response.status_code == 503
    assert payload["status"] == "BLOCKED"
    assert payload["source"] == "agents-sdk"
    assert payload["evidenceId"].startswith("evidence-")
    assert payload["receivedEvidenceId"].startswith("evidence-")
    assert payload["reason"]
    assert payload["nextAction"] == "VERIFY_LITELLM_SERVICE_KEY"
    assert payload["blocker"] == "LITELLM_RUNTIME_CONFIGURATION_MISSING"
    assert payload["receivedEvidenceId"].startswith("evidence-")
    assert factory.commits == 2
    assert any("INSERT INTO agent_runs" in sql for sql, _ in factory.calls)
    assert any("UPDATE agent_runs" in sql for sql, _ in factory.calls)


def test_swarm_start_persists_route_blocker_before_provider_execution(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    factory = FakeConnectionFactory(route_ready=False)
    client = _app(factory).test_client()

    response = client.post(
        "/api/user/agent/swarm/run",
        json={"mission": "Inspect the configured Agents SDK route."},
    )
    payload = response.get_json()

    assert response.status_code == 503
    assert payload["status"] == "BLOCKED"
    assert payload["blocker"] == "AGENTS_LITELLM_ALIAS_NOT_READY"
    assert payload["nextAction"] == "ACTIVATE_PRICE_VERIFIED_LITELLM_ROUTE"
    assert payload["receivedEvidenceId"].startswith("evidence-")
    assert payload["evidenceId"].startswith("evidence-")
    assert factory.commits == 2
    assert any("FROM llm_routes" in sql for sql, _ in factory.calls)
    assert any("UPDATE agent_runs" in sql for sql, _ in factory.calls)
    assert not any("INSERT INTO llm_usage_settlements" in sql for sql, _ in factory.calls)


def test_swarm_persists_core_agent_stage_events_for_chat_widget(monkeypatch) -> None:
    monkeypatch.setattr(routes_runtime, "classify_mission_intent", _read_only_intent)
    async def bounded_swarm(*args, stage_observer=None, **kwargs):
        assert stage_observer is not None
        stage_observer({
            "agentId": "dispatcher",
            "eventType": "agent_started",
            "status": "RUNNING",
            "summary": "Dispatcher started the bounded planning call.",
            "nextAction": "WAIT_FOR_DISPATCH_PLAN",
        })
        return {
            "ok": False,
            "status": "BLOCKED",
            "blocker": "Required runtime evidence is missing.",
            "manifest": {"schema": 2},
            "activeSpecialists": 0,
            "finalVerdict": {
                "draft_pr_ready": False,
                "human_approval_required": False,
            },
        }

    monkeypatch.setattr(routes_runtime, "run_cognitive_swarm", bounded_swarm)
    factory = FakeConnectionFactory()
    client = _app(factory).test_client()

    response = client.post(
        "/api/user/agent/swarm/run",
        json={"mission": "Persist the real core-agent lifecycle for the chat widget."},
    )
    payload = response.get_json()

    assert response.status_code == 503
    assert payload["status"] == "BLOCKED"
    assert sum("INSERT INTO agent_events" in sql for sql, _ in factory.calls) == 3
    persisted = repr(factory.calls)
    assert "agent_started" in persisted
    assert "dispatcher" in persisted
    assert "rawModelOutputPersisted" in persisted
    assert "WAIT_FOR_DISPATCH_PLAN" in persisted


def test_swarm_persists_confirmed_nullfund_as_completed(monkeypatch) -> None:
    monkeypatch.setattr(routes_runtime, "classify_mission_intent", _read_only_intent)
    async def completed_swarm(*args, **kwargs):
        return {
            "ok": True,
            "status": "COMPLETED",
            "manifest": {"schema": 2},
            "activeSpecialists": 0,
            "finalVerdict": {
                "verdict": "nullfund_confirmed",
                "draft_pr_ready": False,
                "human_approval_required": False,
            },
        }

    monkeypatch.setattr(routes_runtime, "run_cognitive_swarm", completed_swarm)
    factory = FakeConnectionFactory()
    client = _app(factory).test_client()

    response = client.post(
        "/api/user/agent/swarm/run",
        json={"mission": "Persist the evidence-backed nullfund as terminal completion."},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["status"] == "COMPLETED"
    assert payload["nextAction"] == "NO_FURTHER_ACTION_REQUIRED"
    assert "evidence-only mission" in payload["reason"]
    assert payload["approvalId"] is None
    assert payload["approvalKind"] is None
    persisted = repr(factory.calls)
    assert "COMPLETED" in persisted
    assert "NO_FURTHER_ACTION_REQUIRED" in persisted


def test_swarm_persists_bounded_failure_family_without_raw_provider_message(monkeypatch) -> None:
    monkeypatch.setattr(routes_runtime, "classify_mission_intent", _read_only_intent)
    async def fail_swarm(*args, **kwargs):
        raise SwarmExecutionError(
            stage="dispatcher",
            family="LITELLM_OR_PROVIDER_PERMISSION_DENIED",
            error_type="PermissionDeniedError",
            next_action="VERIFY_LITELLM_ALIAS_AND_PROVIDER_ACCESS",
            retryable=False,
            http_status=403,
            request_id="req-safe-456",
        )

    monkeypatch.setattr(routes_runtime, "run_cognitive_swarm", fail_swarm)
    factory = FakeConnectionFactory()
    client = _app(factory).test_client()
    response = client.post(
        "/api/user/agent/swarm/run",
        json={"mission": "Inspect the bounded runtime state."},
    )
    payload = response.get_json()

    assert response.status_code == 502
    assert payload["status"] == "FAILED_RECOVERABLE"
    assert payload["blocker"] == "LITELLM_OR_PROVIDER_PERMISSION_DENIED"
    assert payload["failureStage"] == "dispatcher"
    assert payload["httpStatus"] == 403
    assert payload["requestId"] == "req-safe-456"
    assert payload["nextAction"] == "VERIFY_LITELLM_ALIAS_AND_PROVIDER_ACCESS"
    assert payload["retryable"] is False
    assert "provider message" not in str(payload)
    assert any("INSERT INTO agent_failures" in sql for sql, _ in factory.calls)


def test_swarm_rejects_secret_shaped_input() -> None:
    factory = FakeConnectionFactory()
    client = _app(factory).test_client()
    response = client.post(
        "/api/user/agent/swarm/run",
        json={"mission": "Use github_pat_example in the workflow."},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "secret-shaped material is forbidden in swarm input"
    assert factory.calls == []


def test_swarm_resume_claims_run_reconstructs_task_and_finishes_with_same_lease(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    factory = FakeConnectionFactory()
    factory.fetchone_rows = [_stored_run_row()]
    client = _app(factory).test_client()

    response = client.post(
        "/api/user/agent/swarm/runs/run-resumable/resume",
        json={"evidence": "Fresh runtime evidence for the persisted next action."},
    )
    payload = response.get_json()

    assert response.status_code == 503
    assert payload["status"] == "BLOCKED"
    assert payload["resumed"] is True
    assert payload["sessionKey"] == "session-resumable"
    assert payload["resumeClaimEvidenceId"].startswith("evidence-")
    assert payload["recoveryTask"]["taskId"].startswith("task-resume-")
    assert payload["recoveryTask"]["workPackage"] == "RETRY_FROM_PERSISTED_RUN_STATE"
    assert payload["recoveryTask"]["leaseSeconds"] == 900
    assert factory.commits == 2
    assert sum("UPDATE agent_runs" in sql for sql, _ in factory.calls) == 2
    assert any("UPDATE agent_tasks" in sql for sql, _ in factory.calls)
    assert any("lease_token = %s" in sql for sql, _ in factory.calls)


def test_swarm_resume_persists_route_blocker_with_claimed_lease(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    factory = FakeConnectionFactory(route_ready=False)
    factory.fetchone_rows = [_stored_run_row()]
    client = _app(factory).test_client()

    response = client.post(
        "/api/user/agent/swarm/runs/run-resumable/resume",
        json={"evidence": "Resume only if the paid route is ready."},
    )
    payload = response.get_json()

    assert response.status_code == 503
    assert payload["status"] == "BLOCKED"
    assert payload["resumed"] is True
    assert payload["blocker"] == "AGENTS_LITELLM_ALIAS_NOT_READY"
    assert payload["nextAction"] == "ACTIVATE_PRICE_VERIFIED_LITELLM_ROUTE"
    assert payload["resumeClaimEvidenceId"].startswith("evidence-")
    assert factory.commits == 2
    assert any("lease_token = %s" in sql for sql, _ in factory.calls)
    assert not any("INSERT INTO llm_usage_settlements" in sql for sql, _ in factory.calls)


def test_resume_repository_handoff_failure_persists_recoverable_state_with_same_lease(monkeypatch) -> None:
    claim = SimpleNamespace(
        run=SimpleNamespace(
            run_id="run-resume-handoff",
            job_id="job-resume-handoff",
            mission_summary="Resume the repository task.",
            mission_digest="a" * 64,
            status="FAILED_RECOVERABLE",
            evidence_id="evidence-previous",
            session_key="session-resume-handoff",
            a2a_context_id="context-resume-handoff",
        ),
        task_id="task-resume-handoff",
        evidence_id="evidence-resume-claim",
        work_package="RETRY_REPOSITORY_EXECUTION_HANDOFF",
        lease_token="lease-resume-handoff",
        lease_seconds=900,
    )
    captured: dict[str, Any] = {}
    monkeypatch.setattr(routes_runtime, "claim_agent_run_for_resume", lambda *args, **kwargs: claim)
    monkeypatch.setattr(
        routes_runtime,
        "read_agent_task_ids",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("task store unavailable")),
    )

    def persist_failure(*args, **kwargs):
        captured.update(kwargs)
        return {
            "status": "FAILED_RECOVERABLE",
            "source": "agents-sdk",
            "evidenceId": "evidence-resume-failed",
            "reason": kwargs["reason"],
            "nextAction": kwargs["next_action"],
        }

    monkeypatch.setattr(routes_runtime, "transition_agent_run", persist_failure)
    payload, status_code = routes_runtime.resume_cognitive_swarm_run(
        get_connection=FakeConnectionFactory(),
        user_id=USER_ID,
        run_id=claim.run.run_id,
        evidence="Fresh runtime evidence.",
    )

    assert status_code == 503
    assert payload["status"] == "FAILED_RECOVERABLE"
    assert payload["blocker"] == "AGENT_REPOSITORY_RESUME_HANDOFF_FAILED"
    assert payload["resumed"] is True
    assert captured["expected_lease_token"] == claim.lease_token
    assert captured["task_id"] == claim.task_id
    assert captured["evidence_kind"] == "resume_implementation_handoff_failure"


def test_swarm_resume_rejects_active_lease_without_starting_second_run(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    factory = FakeConnectionFactory()
    factory.fetchone_rows = [_stored_run_row(status="RUNNING", lease_active=True, resume_task_id="task-active")]
    client = _app(factory).test_client()

    response = client.post(
        "/api/user/agent/swarm/runs/run-resumable/resume",
        json={"evidence": "Evidence must not start a duplicate run."},
    )
    payload = response.get_json()

    assert response.status_code == 409
    assert payload["status"] == "RUNNING"
    assert payload["blocker"] == "RUN_ALREADY_CLAIMED"
    assert factory.commits == 0
    assert factory.rollbacks == 1
    assert len(factory.calls) == 1
    assert "FOR UPDATE" in factory.calls[0][0]


def test_swarm_resume_rejects_secret_shaped_evidence_before_database_access() -> None:
    factory = FakeConnectionFactory()
    client = _app(factory).test_client()

    response = client.post(
        "/api/user/agent/swarm/runs/run-resumable/resume",
        json={"evidence": "github_pat_example"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "secret-shaped material is forbidden in swarm input"
    assert factory.calls == []


def test_swarm_does_not_start_model_when_persistence_is_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _app(FakeConnectionFactory(fail=True)).test_client()
    response = client.post(
        "/api/user/agent/swarm/run",
        json={"mission": "Start only after persistent run truth exists."},
    )
    payload = response.get_json()
    assert response.status_code == 503
    assert payload["blocker"] == "AGENT_RUN_PERSISTENCE_UNAVAILABLE"
    assert "status" not in payload
    assert "evidenceId" not in payload
