from __future__ import annotations

import os
import sys

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request  # noqa: E402

from agent_runtime.contracts import SovereignAgentEvent, SovereignAgentJobRequest  # noqa: E402
from agent_runtime.job_store import create_agent_job_record, update_agent_job_state  # noqa: E402
from agent_runtime.routes import register_sovereign_agent_routes  # noqa: E402


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.last_result = None

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        normalized = " ".join(sql.upper().split())
        if normalized.startswith("INSERT INTO SOVEREIGN_AGENT_JOBS"):
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
                # Migration 004: Draft PR fields (VPS schema)
                "draft_pr_preparation": None,
                "branch_name": None,
                "target_branch": None,
                "commit_message": None,
                "pr_url": None,
                "pr_state": None,
            }
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS") and "PR_STATE = 'ready'" in normalized:
            job_id = params[-1]
            self.conn.jobs[job_id]["status"] = "validating"
            self.conn.jobs[job_id]["pr_state"] = "ready"
            self.conn.jobs[job_id]["branch_name"] = params[0]
            self.conn.jobs[job_id]["target_branch"] = params[1]
            self.conn.jobs[job_id]["commit_message"] = params[2]
            self.conn.jobs[job_id]["blocker"] = None
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS") and "pr_state = 'ready'" in normalized.lower():
            job_id = params[-1]
            self.conn.jobs[job_id]["status"] = "validating"
            self.conn.jobs[job_id]["pr_state"] = "ready"
            self.conn.jobs[job_id]["branch_name"] = params[0]
            self.conn.jobs[job_id]["target_branch"] = params[1]
            self.conn.jobs[job_id]["commit_message"] = params[2]
            self.conn.jobs[job_id]["blocker"] = None
        elif normalized.startswith("INSERT INTO SOVEREIGN_AGENT_EVENTS"):
            self.conn.events.append(params)
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS") and "SET EVENTS" in normalized:
            job_id = params[1]
            self.conn.jobs[job_id]["events"].append(params[0])
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
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

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


def seed_job(conn: FakeConnection, *, user_id="user-1", job_id="agent-1"):
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
        diff_summary="README.md | 2 +-",
        test_summary="12 passed, 0 failed",
    )


def test_draft_pr_prepare_requires_session():
    conn = FakeConnection()
    app = create_test_app(conn)

    response = app.test_client().post("/api/user/agent/jobs/agent-1/draft-pr/prepare")

    assert response.status_code == 401


def test_draft_pr_prepare_is_user_scoped():
    conn = FakeConnection()
    seed_job(conn, user_id="user-1", job_id="agent-1")
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/draft-pr/prepare",
        headers={"X-Test-User": "user-2"},
        json={},
    )

    assert response.status_code == 404
    assert conn.jobs["agent-1"]["pr_state"] is None


def test_draft_pr_prepare_persists_ready_state():
    conn = FakeConnection()
    seed_job(conn, user_id="user-1", job_id="agent-1")
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/draft-pr/prepare",
        headers={"X-Test-User": "user-1"},
        json={},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["draftPrPreparation"]["canCreateDraftPr"] is True
    assert payload["draftPrPreparation"]["nextAction"] == "create_draft_pr"
    assert payload["draftPrPreparation"]["signal"] == "agent_draft_pr_ready"
    assert conn.jobs["agent-1"]["status"] == "validating"
    assert conn.jobs["agent-1"]["pr_state"] == "ready"
    assert conn.jobs["agent-1"]["branch_name"].startswith("sovereign/agent-")
    assert conn.jobs["agent-1"]["commit_message"] == "Draft: Update README wording"


def test_draft_pr_prepare_blocks_without_tests():
    conn = FakeConnection()
    seed_job(conn, user_id="user-1", job_id="agent-1")
    update_agent_job_state(
        conn,
        job_id="agent-1",
        status="running",
        changed_files=("README.md",),
        diff_summary="README.md | 2 +-",
        test_summary="",
    )
    conn.jobs["agent-1"]["test_summary"] = None
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/draft-pr/prepare",
        headers={"X-Test-User": "user-1"},
        json={},
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["draftPrPreparation"]["canCreateDraftPr"] is False
    assert "evidence gate does not allow Draft PR preparation" in payload["draftPrPreparation"]["blockers"]
    assert conn.jobs["agent-1"]["pr_state"] is None


def test_draft_pr_prepare_blocks_unsafe_head_branch():
    conn = FakeConnection()
    seed_job(conn, user_id="user-1", job_id="agent-1")
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/draft-pr/prepare",
        headers={"X-Test-User": "user-1"},
        json={"headBranch": "main;rm-rf"},
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["ok"] is False
    assert "head branch is unsafe" in payload["draftPrPreparation"]["blockers"]
    assert conn.jobs["agent-1"]["pr_state"] is None
