"""Exercise authenticated control-surface projections; DB is the adapter boundary."""
from functools import wraps
from types import SimpleNamespace

import pytest
from flask import Flask, jsonify, request

from backend.agent_runtime import routes


OWNER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


class Database:
    def __init__(self, *, credits=1250, ledger=1250, funded=1100):
        self.account = {"id": OWNER, "email": "owner@example.test", "role": "user",
                        "credits": credits, "ledger_balance": ledger,
                        "provider_funded_credits": funded, "purchase_verified": True}
        self.sql = []
        self.rows = []
        self.closed = False

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=None):
        self.sql.append((statement, params))
        if "control-surface:credits" in statement:
            self.rows = [self.account] if params == (OWNER,) else []
        elif "control-surface:agents" in statement:
            self.rows = [{"agent_id": "free_single_agent", "task_id": "task-real",
                          "run_id": "repo-agent-real", "status": "RUNNING", "source": "agents-sdk",
                          "created_at": "2026-10-02T21:00:00+00:00", "updated_at": "2026-10-02T21:02:00+00:00"}]
        else:
            raise AssertionError("Unexpected DB adapter query")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def app_for(monkeypatch, database):
    app = Flask(__name__)

    def require_session(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = request.headers.get("X-Test-User")
            if not user:
                return jsonify({"error": "session required"}), 401
            request.session_user_id = user
            return view(*args, **kwargs)
        return wrapped

    app.extensions["sovereign_enterprise_platform"] = SimpleNamespace(integrations=lambda: [{
        "id": "postgresql", "label": "PostgreSQL", "status": "verified",
        "checkedAt": "2026-10-02T21:01:00+00:00", "boundary": "canonical persistence",
        "evidence": {"credential": "not-returned"}, "secret": "not-returned",
    }])
    job = SimpleNamespace(job_id="agent-real", user_id=OWNER, executor="sovereign-local-runner",
                          status="running", external_ref="sovereign-local-runner:pending:submit:agent-real")
    monkeypatch.setattr(routes, "read_agent_job", lambda _conn, user_id, job_id: job if user_id == OWNER and job_id == job.job_id else None)
    import backend.agent_runtime.control_surface_readback as projection
    monkeypatch.setattr(projection, "load_execution_resolution", lambda *_args, **_kwargs: None)
    routes.register_sovereign_agent_routes(app, require_session=require_session, get_connection=lambda: database)
    return app.test_client()


def test_authentication_and_exact_owned_job_are_required(monkeypatch):
    db = Database()
    client = app_for(monkeypatch, db)
    assert client.get("/api/user/agent/control-surface").status_code == 401
    response = client.get("/api/user/agent/control-surface?jobId=agent-real", headers={"X-Test-User": OTHER})
    assert response.status_code == 404
    assert db.sql == []


def test_persisted_agents_verified_credit_ledger_and_allowlisted_integrations(monkeypatch):
    db = Database()
    response = app_for(monkeypatch, db).get("/api/user/agent/control-surface?jobId=agent-real", headers={"X-Test-User": OWNER})
    assert response.status_code == 200
    body = response.json
    assert body["jobId"] == "agent-real"
    assert body["credits"]["credits"] == 1250
    assert body["credits"]["providerFundedCredits"] == 1100
    assert body["credits"]["creditStateVerified"] is True
    assert body["agents"][1]["taskId"] == "task-real"
    assert body["agents"][0]["status"] == "QUEUED"
    assert body["integrations"][0]["status"] == "verified"
    assert "not-returned" not in response.get_data(as_text=True)
    agents_sql, params = next(item for item in db.sql if "control-surface:agents" in item[0])
    assert "run.user_id = job.user_id" in agents_sql
    assert "job.user_id = %s::uuid" in agents_sql
    assert params == (OWNER, "agent-real")
    assert all("UPDATE " not in statement and "INSERT " not in statement for statement, _ in db.sql)
    assert db.closed


@pytest.mark.parametrize("credits,ledger,funded", [(1250,1200,1100), (1250,1250,1300), (-1,-1,0)])
def test_contradicted_balance_is_not_replaced_by_zero(monkeypatch, credits, ledger, funded):
    body = app_for(monkeypatch, Database(credits=credits, ledger=ledger, funded=funded)).get(
        "/api/user/agent/control-surface", headers={"X-Test-User": OWNER}).json
    assert body["credits"]["readbackState"] == "unavailable"
    assert "credits" not in body["credits"]
    assert body["credits"]["blocker"] == "credit_state_verification_failed"
    assert body["routing"]["modes"][1]["available"] is False


def test_provider_ready_paid_route_is_available_with_verified_funded_credits(monkeypatch):
    db = Database()
    client = app_for(monkeypatch, db)
    import backend.agent_runtime.control_surface_readback as projection
    monkeypatch.setattr(projection, "load_execution_resolution", lambda *_args, **kwargs: SimpleNamespace(
        profile_id=projection.PAID_SWARM_PROFILE if kwargs["requested_mode"] == "paid" else "free_single_agent",
        primary_route={"id": "route-real", "model_id": "model-real"}, repository_execution_allowed=True))
    body = client.get("/api/user/agent/control-surface", headers={"X-Test-User": OWNER}).json
    paid = body["routing"]["modes"][1]
    assert paid["providerAvailable"] is True
    assert paid["available"] is True
    assert "blocker" not in paid
    assert body["agents"][0]["source"] == "repository-execution-manifest"
    assert body["agents"][0]["status"] == "DECLARED"
