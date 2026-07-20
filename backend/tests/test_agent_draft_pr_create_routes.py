from __future__ import annotations

import os
import sys

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request  # noqa: E402

from agent_runtime.contracts import SovereignAgentEvent, SovereignAgentJobRequest  # noqa: E402
from agent_runtime.draft_pr_create_gate import DraftPrCreateResult  # noqa: E402
from agent_runtime.job_store import create_agent_job_record, mark_draft_pr_prepared, update_agent_job_state  # noqa: E402
from agent_runtime.routes import register_sovereign_agent_routes  # noqa: E402


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.last_result = None

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        self.last_result = None
        normalized = " ".join(sql.upper().split())
        if normalized.startswith("SELECT PG_ADVISORY_XACT_LOCK"):
            self.last_result = {"locked": True}
        elif normalized.startswith("SELECT CREDITS, ROLE FROM ADMIN_USERS"):
            user_id = params[0]
            self.last_result = self.conn.users.get(user_id)
        elif normalized.startswith("UPDATE ADMIN_USERS") and "RETURNING CREDITS" in normalized:
            amount, user_id, minimum = params
            user = self.conn.users.get(user_id)
            if user and int(user.get("credits") or 0) >= int(minimum):
                user["credits"] = int(user["credits"]) - int(amount)
                self.last_result = {"credits": user["credits"]}
        elif normalized.startswith("INSERT INTO CREDIT_LEDGER"):
            self.conn.credit_ledger.append(params)
        elif normalized.startswith("INSERT INTO SOVEREIGN_AGENT_JOBS"):
            self.conn.jobs[params[1]] = {
                "user_id": params[0],
                "job_id": params[1],
                "executor": params[2],
                "repo_url": params[3],
                "branch": params[4],
                "mission": params[5],
                "status": params[6],
                "workspace_id": params[7],
                "external_ref": None,
                "draft_pr_url": None,
                "changed_files": [],
                "diff_summary": None,
                "test_summary": None,
                "events": [],
                "blocker": params[12],
                "draft_pr_preparation": None,
                "branch_name": None,
                "target_branch": None,
                "commit_message": None,
                "pr_url": None,
                "pr_state": None,
            }
        elif normalized.startswith("INSERT INTO SOVEREIGN_AGENT_EVENTS"):
            self.conn.events.append(params)
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS") and "SET EVENTS" in normalized:
            pass
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS") and "PR_STATE = 'READY'" in normalized:
            job_id = params[-1]
            self.conn.jobs[job_id]["status"] = "validating"
            self.conn.jobs[job_id]["pr_state"] = "ready"
            self.conn.jobs[job_id]["branch_name"] = params[0]
            self.conn.jobs[job_id]["target_branch"] = params[1]
            self.conn.jobs[job_id]["commit_message"] = params[2]
            self.conn.jobs[job_id]["draft_pr_preparation"] = {"body": "Prepared body"}
            self.conn.jobs[job_id]["blocker"] = None
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS") and "PR_STATE = 'CREATED'" in normalized:
            job_id = params[-1]
            self.conn.jobs[job_id]["status"] = "completed"
            self.conn.jobs[job_id]["pr_state"] = "created"
            self.conn.jobs[job_id]["pr_url"] = params[0]
            self.conn.jobs[job_id]["draft_pr_url"] = params[1]
            self.conn.jobs[job_id]["blocker"] = None
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS"):
            job_id = params[-1]
            self.conn.jobs[job_id]["status"] = params[0]
            if params[1]:
                self.conn.jobs[job_id]["workspace_id"] = params[1]
            if params[3]:
                self.conn.jobs[job_id]["changed_files"] = params[3]
            if params[4]:
                self.conn.jobs[job_id]["diff_summary"] = params[4]
            if params[5]:
                self.conn.jobs[job_id]["test_summary"] = params[5]
            if params[6]:
                self.conn.jobs[job_id]["draft_pr_url"] = params[6]
            if params[7]:
                self.conn.jobs[job_id]["blocker"] = None
            elif params[8]:
                self.conn.jobs[job_id]["blocker"] = params[8]
        elif normalized.startswith("SELECT * FROM SOVEREIGN_AGENT_JOBS") and "AND JOB_ID" in normalized:
            user_id, job_id = params
            row = self.conn.jobs.get(job_id)
            self.last_result = row if row and row["user_id"] == user_id else None
        elif normalized.startswith("SELECT * FROM SOVEREIGN_AGENT_JOBS"):
            user_id = params[0]
            self.last_result = [row for row in self.conn.jobs.values() if row["user_id"] == user_id]

    def fetchone(self):
        return self.last_result if isinstance(self.last_result, dict) else None

    def fetchall(self):
        return self.last_result if isinstance(self.last_result, list) else []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.jobs = {}
        self.events = []
        self.users = {
            "user-1": {"credits": 100, "role": "admin"},
            "user-2": {"credits": 100, "role": "admin"},
        }
        self.credit_ledger = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def request_contract():
    return SovereignAgentJobRequest(
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        branch="main",
        mission="Update README wording",
        executor="sovereign-local-runner",
    )


def create_test_app(conn: FakeConnection):
    app = Flask(__name__)

    def require_session(fn):
        def wrapped(*args, **kwargs):
            uid = request.headers.get("X-Test-User")
            if not uid:
                return jsonify({"error": "Nicht eingeloggt"}), 401
            request.session_user_id = uid
            return fn(*args, **kwargs)

        wrapped.__name__ = fn.__name__
        return wrapped

    register_sovereign_agent_routes(app, require_session=require_session, get_connection=lambda: conn)
    return app


def seed_ready_job(conn: FakeConnection, *, user_id="user-1", job_id="agent-1"):
    create_agent_job_record(
        conn,
        user_id=user_id,
        job_id=job_id,
        request=request_contract(),
        status="running",
        workspace_id=job_id,
        events=(SovereignAgentEvent(stage="seed", level="info", message="Seeded job."),),
    )
    update_agent_job_state(
        conn,
        job_id=job_id,
        status="validating",
        changed_files=("README.md",),
        diff_summary="README.md | 2 ++",
        test_summary="12 passed, 0 failed",
    )
    mark_draft_pr_prepared(
        conn,
        job_id=job_id,
        head_branch="sovereign/agent-agent-1-update-readme",
        base_branch="main",
        title="Draft: Update README wording",
        body="Prepared body",
    )


def test_draft_pr_create_requires_session():
    conn = FakeConnection()
    app = create_test_app(conn)

    response = app.test_client().post("/api/user/agent/jobs/agent-1/draft-pr/create")

    assert response.status_code == 401


def test_draft_pr_create_is_user_scoped():
    conn = FakeConnection()
    seed_ready_job(conn, user_id="user-1", job_id="agent-1")
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/draft-pr/create",
        headers={"X-Test-User": "user-2"},
        json={},
    )

    assert response.status_code == 404
    assert conn.jobs["agent-1"]["pr_state"] == "ready"
    assert conn.jobs["agent-1"]["pr_url"] is None


def test_draft_pr_create_blocks_without_ready_state(monkeypatch):
    monkeypatch.delenv("SOVEREIGN_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    conn = FakeConnection()
    create_agent_job_record(
        conn,
        user_id="user-1",
        job_id="agent-1",
        request=request_contract(),
        status="running",
        workspace_id="agent-1",
    )
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/draft-pr/create",
        headers={"X-Test-User": "user-1"},
        json={},
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["draftPrCreate"]["status"] == "blocked"
    assert "pr_state=ready" in payload["draftPrCreate"]["blocker"]


def test_draft_pr_create_blocks_without_server_credentials(monkeypatch):
    monkeypatch.delenv("SOVEREIGN_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    conn = FakeConnection()
    seed_ready_job(conn, user_id="user-1", job_id="agent-1")
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/draft-pr/create",
        headers={"X-Test-User": "user-1"},
        json={},
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["draftPrCreate"]["blocker"] == "server GitHub credentials missing for Draft PR create"
    assert conn.jobs["agent-1"]["pr_state"] == "ready"
    assert conn.jobs["agent-1"]["pr_url"] is None


def test_draft_pr_create_persists_created_state(monkeypatch):
    import agent_runtime.routes as routes

    observed = {}

    def fake_create_draft_pr_for_job(job, token=None):
        observed["token"] = token
        return DraftPrCreateResult(
            allowed=True,
            status="created",
            pr_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/123",
            summary="GitHub Draft PR created.",
            predictive_signal="agent_draft_pr_created",
        )

    monkeypatch.setattr(routes, "create_draft_pr_for_job", fake_create_draft_pr_for_job)
    conn = FakeConnection()
    seed_ready_job(conn, user_id="user-1", job_id="agent-1")
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/draft-pr/create",
        headers={"X-Test-User": "user-1"},
        json={"githubAccessToken": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert observed["token"] == "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
    assert payload["ok"] is True
    assert payload["draftPrCreate"]["prUrl"].endswith("/pull/123")
    assert payload["draftPrCreate"]["signal"] == "agent_draft_pr_created"
    assert conn.jobs["agent-1"]["status"] == "completed"
    assert conn.jobs["agent-1"]["pr_state"] == "created"
    assert conn.jobs["agent-1"]["pr_url"].endswith("/pull/123")
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456" not in repr(conn.jobs)
    assert payload["creditSettlement"]["chargedCredits"] == 0
    assert payload["creditSettlement"]["duplicate"] is False


def test_non_admin_is_not_charged_when_github_creation_fails(monkeypatch):
    import agent_runtime.routes as routes

    monkeypatch.setattr(
        routes,
        "create_draft_pr_for_job",
        lambda *_args, **_kwargs: DraftPrCreateResult(
            allowed=False,
            status="blocked",
            blocker="GitHub unavailable",
            summary="Draft PR create blocked.",
            predictive_signal="agent_draft_pr_create_blocked",
        ),
    )
    conn = FakeConnection()
    conn.users["user-1"] = {"credits": 20, "role": "user"}
    seed_ready_job(conn, user_id="user-1", job_id="agent-1")
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/draft-pr/create",
        headers={"X-Test-User": "user-1"},
        json={"githubAccessToken": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"},
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["creditSettlement"]["chargedCredits"] == 0
    assert conn.users["user-1"]["credits"] == 20
    assert conn.credit_ledger == []
    assert conn.jobs["agent-1"]["pr_state"] == "ready"
    assert conn.rollbacks >= 1


def test_non_admin_success_charges_once_and_uses_real_ledger_columns(monkeypatch):
    import agent_runtime.routes as routes

    monkeypatch.setattr(
        routes,
        "create_draft_pr_for_job",
        lambda *_args, **_kwargs: DraftPrCreateResult(
            allowed=True,
            status="created",
            pr_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/124",
            summary="GitHub Draft PR created.",
            predictive_signal="agent_draft_pr_created",
        ),
    )
    conn = FakeConnection()
    conn.users["user-1"] = {"credits": 20, "role": "user"}
    seed_ready_job(conn, user_id="user-1", job_id="agent-1")
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/draft-pr/create",
        headers={"X-Test-User": "user-1"},
        json={"githubAccessToken": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["creditSettlement"] == {
        "chargedCredits": 10,
        "remainingCredits": 10,
        "duplicate": False,
    }
    assert conn.users["user-1"]["credits"] == 10
    assert conn.credit_ledger == [
        ("user-1", -10, "Agent Draft PR: agent-1", "agent-pr:agent-1")
    ]
    ledger_sql = next(sql for sql, _params in conn.executed if "INSERT INTO credit_ledger" in sql)
    assert "reason" in ledger_sql
    assert "provider" in ledger_sql
    assert "provider_tx_id" in ledger_sql
    assert "description" not in ledger_sql
    assert "reference_id" not in ledger_sql

    repeated = app.test_client().post(
        "/api/user/agent/jobs/agent-1/draft-pr/create",
        headers={"X-Test-User": "user-1"},
        json={"githubAccessToken": "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"},
    )
    assert repeated.status_code == 200
    assert repeated.get_json()["creditSettlement"] == {
        "chargedCredits": 0,
        "duplicate": True,
    }
    assert conn.users["user-1"]["credits"] == 10
    assert len(conn.credit_ledger) == 1


def test_draft_pr_create_rejects_invalid_ephemeral_token_before_creator(monkeypatch):
    import agent_runtime.routes as routes

    creator = monkeypatch.setattr(routes, "create_draft_pr_for_job", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("creator must not run")))
    assert creator is None
    conn = FakeConnection()
    seed_ready_job(conn, user_id="user-1", job_id="agent-1")
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/draft-pr/create",
        headers={"X-Test-User": "user-1"},
        json={"githubAccessToken": "invalid"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "githubAccessToken has an invalid format"
    assert conn.jobs["agent-1"]["pr_state"] == "ready"
