from functools import wraps
from pathlib import Path
import sys
from typing import Any

from flask import Flask, request

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from agent_runtime.cognitive_swarm_routes import register_cognitive_swarm_routes


USER_ID = "00000000-0000-0000-0000-000000000001"


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
        if "RETURNING run_id" in self.last_sql:
            return {"run_id": "run-persisted"}
        return None

    def fetchall(self):
        return []


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
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, Any]] = []
        self.connections: list[FakeConnection] = []
        self.commits = 0
        self.rollbacks = 0

    def __call__(self) -> FakeConnection:
        if self.fail:
            raise RuntimeError("database unavailable")
        connection = FakeConnection(self)
        self.connections.append(connection)
        return connection


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
    assert payload["nextAction"] == "PROVIDE_MISSING_EVIDENCE_OR_PROTECTED_CONFIGURATION"
    assert "OPENAI_API_KEY" in payload["blocker"]
    assert factory.commits == 2
    assert any("INSERT INTO agent_runs" in sql for sql, _ in factory.calls)
    assert any("UPDATE agent_runs" in sql for sql, _ in factory.calls)


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
