from __future__ import annotations

import os
import sys

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify  # noqa: E402

from agent_runtime.contracts import (  # noqa: E402
    SovereignAgentEvent,
    SovereignAgentJobRequest,
    SovereignAgentJobResult,
)
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
                "allowed_paths": params[8],
                "forbidden_paths": params[9],
                "memory_hints": params[10],
                "external_ref": None,
                "draft_pr_url": None,
                "changed_files": [],
                "diff_summary": None,
                "test_summary": None,
                "events": params[11],
                "blocker": params[12],
            }
        elif normalized.startswith("INSERT INTO SOVEREIGN_AGENT_EVENTS"):
            self.conn.events.append(params)
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS") and "SET EVENTS" in normalized:
            import json
            job_id = params[1]
            new_events = json.loads(params[0])
            current = self.conn.jobs[job_id].get("events", [])
            if isinstance(current, str):
                current = json.loads(current)
            self.conn.jobs[job_id]["events"] = current + new_events
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS"):
            job_id = params[-1]
            self.conn.jobs[job_id]["status"] = params[0]
            if params[1]:
                self.conn.jobs[job_id]["workspace_id"] = params[1]
            if params[2]:
                self.conn.jobs[job_id]["external_ref"] = params[2]
            if params[3]:
                self.conn.jobs[job_id]["changed_files"] = params[3]
            if params[4]:
                self.conn.jobs[job_id]["diff_summary"] = params[4]
            if params[5]:
                self.conn.jobs[job_id]["test_summary"] = params[5]
            if params[6]:
                self.conn.jobs[job_id]["draft_pr_url"] = params[6]
            if params[7]:
                self.conn.jobs[job_id]["blocker"] = params[7]
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
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def valid_request():
    return SovereignAgentJobRequest(
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        branch="main",
        mission="Update README and prepare a Draft PR.",
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


def seed_job(conn: FakeConnection, user_id: str, job_id: str, status: str = "queued"):
    create_agent_job_record(
        conn,
        user_id=user_id,
        job_id=job_id,
        request=valid_request(),
        status=status,
        workspace_id=job_id if status != "queued" else None,
        events=(SovereignAgentEvent(stage="seed", level="info", message="Seeded job."),),
        blocker="Seed blocker." if status in ("blocked", "failed") else None,
    )


def test_routes_require_session():
    conn = FakeConnection()
    app = create_test_app(conn)

    response = app.test_client().get("/api/user/agent/jobs")

    assert response.status_code == 401
    assert response.get_json()["error"] == "Nicht eingeloggt"


def test_list_jobs_is_user_scoped():
    conn = FakeConnection()
    seed_job(conn, "user-1", "agent-1")
    seed_job(conn, "user-2", "agent-2")
    app = create_test_app(conn)

    response = app.test_client().get("/api/user/agent/jobs", headers={"X-Test-User": "user-1"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["runtime"] == "sovereign-agent"
    assert payload["total"] == 1
    assert payload["jobs"][0]["jobId"] == "agent-1"


def test_create_job_runs_lifecycle_and_returns_runtime_state(tmp_path, monkeypatch):
    conn = FakeConnection()
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs",
        headers={"X-Test-User": "user-1"},
        json={
            "repoUrl": "https://github.com/OuroborosCollective/Sovereign-Studio-ato",
            "branch": "main",
            "mission": "Update README and prepare a Draft PR.",
            "provisionWorkspace": True,
            "cloneRepo": False,
        },
    )

    payload = response.get_json()
    assert response.status_code == 201
    assert payload["ok"] is True
    assert payload["runtime"] == "sovereign-agent"
    assert payload["job"]["status"] == "provisioning"
    assert payload["job"]["workspaceId"].startswith("agent-")


def test_create_invalid_job_returns_blocked_without_fake_success(tmp_path, monkeypatch):
    conn = FakeConnection()
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs",
        headers={"X-Test-User": "user-1"},
        json={
            "repoUrl": "https://evil.example/repo",
            "mission": "Do unsafe work.",
        },
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["job"]["status"] == "blocked"
    assert "valid HTTPS GitHub" in payload["job"]["blocker"]


def test_get_job_is_user_scoped():
    conn = FakeConnection()
    seed_job(conn, "user-1", "agent-1")
    app = create_test_app(conn)

    owned = app.test_client().get("/api/user/agent/jobs/agent-1", headers={"X-Test-User": "user-1"})
    other = app.test_client().get("/api/user/agent/jobs/agent-1", headers={"X-Test-User": "user-2"})

    assert owned.status_code == 200
    assert owned.get_json()["job"]["jobId"] == "agent-1"
    assert other.status_code == 404


def test_cancel_non_terminal_job_sets_blocked():
    conn = FakeConnection()
    seed_job(conn, "user-1", "agent-1", status="running")
    app = create_test_app(conn)

    response = app.test_client().post("/api/user/agent/jobs/agent-1/cancel", headers={"X-Test-User": "user-1"})

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert conn.jobs["agent-1"]["status"] == "blocked"
    assert conn.jobs["agent-1"]["blocker"] == "Cancelled by user."


def test_cancel_terminal_job_is_blocked():
    conn = FakeConnection()
    seed_job(conn, "user-1", "agent-1", status="blocked")
    app = create_test_app(conn)

    response = app.test_client().post("/api/user/agent/jobs/agent-1/cancel", headers={"X-Test-User": "user-1"})

    assert response.status_code == 400
    assert response.get_json()["error"] == "Job ist bereits terminal"


def test_cleanup_requires_terminal_state():
    conn = FakeConnection()
    seed_job(conn, "user-1", "agent-1", status="running")
    app = create_test_app(conn)

    response = app.test_client().post("/api/user/agent/jobs/agent-1/cleanup", headers={"X-Test-User": "user-1"})

    assert response.status_code == 400
    assert response.get_json()["error"] == "Cleanup erst nach terminalem State erlaubt"


def test_cleanup_terminal_job_sets_cleaned(tmp_path, monkeypatch):
    conn = FakeConnection()
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    seed_job(conn, "user-1", "agent-1", status="blocked")
    (tmp_path / "agent-1" / "repo").mkdir(parents=True)
    app = create_test_app(conn)

    response = app.test_client().post("/api/user/agent/jobs/agent-1/cleanup", headers={"X-Test-User": "user-1"})

    assert response.status_code == 200
    assert response.get_json()["status"] == "cleaned"
    assert conn.jobs["agent-1"]["status"] == "cleaned"
    assert not (tmp_path / "agent-1").exists()


def test_janitor_scan_is_user_scoped_read_only_and_keeps_job_running(tmp_path, monkeypatch):
    conn = FakeConnection()
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    seed_job(conn, "user-1", "agent-janitor", status="running")
    repo = tmp_path / "agent-janitor" / "repo"
    repo.mkdir(parents=True)
    source = "import subprocess\nsubprocess.run('echo unsafe', shell=True)\n"
    target = repo / "worker.py"
    target.write_text(source, encoding="utf-8")
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-janitor/tools/janitor",
        headers={"X-Test-User": "user-1"},
        json={"mode": "scan", "maxFindings": 10},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["tool"]["metadata"]["mode"] == "scan"
    assert any(item["ruleId"] == "PY-UNSAFE-SHELL" for item in payload["tool"]["metadata"]["findings"])
    assert payload["tool"]["changedFiles"] == []
    assert conn.jobs["agent-janitor"]["status"] == "running"
    assert target.read_text(encoding="utf-8") == source

    other_user = app.test_client().post(
        "/api/user/agent/jobs/agent-janitor/tools/janitor",
        headers={"X-Test-User": "user-2"},
        json={"mode": "scan"},
    )
    assert other_user.status_code == 404
