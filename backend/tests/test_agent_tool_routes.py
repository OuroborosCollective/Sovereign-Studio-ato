from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, request  # noqa: E402

from agent_runtime.contracts import SovereignAgentEvent, SovereignAgentJobRequest  # noqa: E402
from agent_runtime.job_store import create_agent_job_record  # noqa: E402
from agent_runtime.routes import register_sovereign_agent_routes  # noqa: E402
from agent_runtime.workspace import create_agent_workspace  # noqa: E402
from agent_runtime.workspace_policy import repo_dir_for_workspace  # noqa: E402


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
                "blocker": params[13],
            }
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


def request_contract():
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


def seed_job(conn: FakeConnection, user_id: str, job_id: str, *, status: str = "running", workspace: bool = True):
    create_agent_job_record(
        conn,
        user_id=user_id,
        job_id=job_id,
        request=request_contract(),
        status=status,
        workspace_id=job_id if workspace else None,
        events=(SovereignAgentEvent(stage="seed", level="info", message="Seeded job."),),
        blocker="Seed blocker." if status in ("blocked", "failed") else None,
    )


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Sovereign Test"], cwd=path, check=True, capture_output=True, text=True)
    (path / "README.md").write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True, text=True)


def test_tool_routes_require_session():
    conn = FakeConnection()
    app = create_test_app(conn)

    response = app.test_client().post("/api/user/agent/jobs/agent-1/tools/git-status")

    assert response.status_code == 401


def test_file_tool_route_is_user_scoped(tmp_path: Path, monkeypatch):
    conn = FakeConnection()
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    seed_job(conn, "user-1", "agent-1")
    create_agent_workspace("agent-1", tmp_path)
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/tools/file",
        headers={"X-Test-User": "user-2"},
        json={"mode": "write", "path": "README.md", "content": "hello\n"},
    )

    assert response.status_code == 404
    assert not (tmp_path / "agent-1" / "repo" / "README.md").exists()


def test_file_write_route_updates_job_evidence(tmp_path: Path, monkeypatch):
    conn = FakeConnection()
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    seed_job(conn, "user-1", "agent-1")
    create_agent_workspace("agent-1", tmp_path)
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/tools/file",
        headers={"X-Test-User": "user-1"},
        json={"mode": "write", "path": "README.md", "content": "hello\n"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["tool"]["status"] == "done"
    assert payload["tool"]["changedFiles"] == ["README.md"]
    assert payload["tool"]["predictiveSignal"]["signal"] == "agent_file_changed"
    assert conn.jobs["agent-1"]["status"] == "running"
    assert "README.md" in conn.jobs["agent-1"]["changed_files"]


def test_file_tool_route_blocks_secret_path_and_terminalizes_job(tmp_path: Path, monkeypatch):
    conn = FakeConnection()
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    seed_job(conn, "user-1", "agent-1")
    create_agent_workspace("agent-1", tmp_path)
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/tools/file",
        headers={"X-Test-User": "user-1"},
        json={"mode": "write", "path": ".env", "content": "SECRET=value"},
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["tool"]["status"] == "blocked"
    assert payload["tool"]["predictiveSignal"]["signal"] == "agent_file_write_blocked"
    assert conn.jobs["agent-1"]["status"] == "blocked"
    assert "Secret-like path" in conn.jobs["agent-1"]["blocker"]


def test_git_status_and_diff_routes_collect_evidence(tmp_path: Path, monkeypatch):
    conn = FakeConnection()
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    seed_job(conn, "user-1", "agent-1")
    create_agent_workspace("agent-1", tmp_path)
    repo = repo_dir_for_workspace("agent-1", tmp_path)
    _init_git_repo(repo)
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    app = create_test_app(conn)

    status_response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/tools/git-status",
        headers={"X-Test-User": "user-1"},
        json={},
    )
    diff_response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/tools/diff",
        headers={"X-Test-User": "user-1"},
        json={},
    )

    status = status_response.get_json()
    diff = diff_response.get_json()
    assert status_response.status_code == 200
    assert status["tool"]["changedFiles"] == ["README.md"]
    assert status["tool"]["predictiveSignal"]["signal"] == "agent_git_status_completed"
    assert diff_response.status_code == 200
    assert "README.md" in diff["tool"]["diffSummary"]
    assert diff["tool"]["predictiveSignal"]["signal"] == "agent_diff_ready"
    assert conn.jobs["agent-1"]["diff_summary"] is not None


def test_test_tool_route_blocks_non_test_command(tmp_path: Path, monkeypatch):
    conn = FakeConnection()
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    seed_job(conn, "user-1", "agent-1")
    create_agent_workspace("agent-1", tmp_path)
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/tools/test",
        headers={"X-Test-User": "user-1"},
        json={"argv": ["git", "status"]},
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["tool"]["status"] == "blocked"
    assert payload["tool"]["predictiveSignal"]["signal"] == "agent_test_command_blocked"


def test_terminal_job_cannot_run_tools(tmp_path: Path, monkeypatch):
    conn = FakeConnection()
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    seed_job(conn, "user-1", "agent-1", status="blocked")
    create_agent_workspace("agent-1", tmp_path)
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-1/tools/git-status",
        headers={"X-Test-User": "user-1"},
        json={},
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["tool"]["status"] == "blocked"
    assert payload["tool"]["predictiveSignal"]["signal"] == "agent_tool_terminal_blocked"
