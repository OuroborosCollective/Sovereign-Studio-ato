from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import zipfile

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify  # noqa: E402

from agent_runtime.contracts import (  # noqa: E402
    SovereignAgentEvent,
    SovereignAgentJobRequest,
    SovereignAgentJobResult,
)
from agent_runtime.job_store import create_agent_job_record, update_agent_job_state  # noqa: E402
import agent_runtime.routes as routes_module  # noqa: E402
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
                self.conn.jobs[job_id]["blocker"] = None
            elif params[8]:
                self.conn.jobs[job_id]["blocker"] = params[8]
        elif normalized.startswith("SELECT * FROM SOVEREIGN_RESCUE_REPAIRS") and "REPAIR_ID" in normalized:
            repair_id, user_id = params[:2]
            row = self.conn.rescues.get(repair_id)
            self.last_result = row if row and row.get("user_id") == user_id else None
        elif normalized.startswith("SELECT * FROM SOVEREIGN_RESCUE_REPAIRS"):
            user_id = params[0]
            self.last_result = [row for row in self.conn.rescues.values() if row.get("user_id") == user_id]
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
        self.rescues = {}
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


def test_github_access_validation_requires_sovereign_session():
    conn = FakeConnection()
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/github-access/validate",
        json={
            "owner": "OuroborosCollective",
            "repo": "Wasd",
            "githubAccessToken": "ghp_" + "a" * 40,
        },
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "Nicht eingeloggt"


def test_github_access_validation_is_server_job_scoped_and_never_echoes_token(monkeypatch):
    conn = FakeConnection()
    seed_job(conn, "user-1", "agent-github-access")
    captured = {}
    token = "ghp_" + "a" * 40

    def fake_validate(raw_token, *, owner, repo):
        captured.update(token=raw_token, owner=owner, repo=repo)
        return SimpleNamespace(
            ok=True,
            can_write=True,
            code="ready",
            message="GitHub-Zugang wurde serverseitig bestätigt.",
        )

    monkeypatch.setattr(routes_module, "validate_github_access_for_repo", fake_validate)
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/github-access/validate",
        headers={"X-Test-User": "user-1"},
        json={
            "jobId": "agent-github-access",
            "owner": "attacker-controlled-owner",
            "repo": "attacker-controlled-repo",
            "githubAccessToken": token,
        },
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload == {"ok": True, "canWrite": True, "code": "ready", "error": None}
    assert captured == {"token": token, "owner": "OuroborosCollective", "repo": "Sovereign-Studio-ato"}
    assert token not in response.get_data(as_text=True)


def test_github_access_validation_rejects_unowned_server_scope_before_external_validation():
    conn = FakeConnection()
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/github-access/validate",
        headers={"X-Test-User": "user-1"},
        json={
            "jobId": "agent-not-owned-by-session",
            "githubAccessToken": "ghp_" + "a" * 40,
        },
    )

    payload = response.get_json()
    assert response.status_code == 422
    assert payload["ok"] is False
    assert payload["canWrite"] is False
    assert payload["code"] == "server_scope_unverified"


def test_github_access_validation_preserves_typed_github_rejection_without_session_logout(monkeypatch):
    conn = FakeConnection()
    seed_job(conn, "user-1", "agent-github-access")
    token = "github_pat_" + "b" * 32
    monkeypatch.setattr(
        routes_module,
        "validate_github_access_for_repo",
        lambda raw_token, *, owner, repo: SimpleNamespace(
            ok=False,
            can_write=False,
            code="credential_rejected",
            message="GitHub hat diesen Zugang nicht authentifiziert.",
        ),
    )
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/github-access/validate",
        headers={"X-Test-User": "user-1"},
        json={
            "jobId": "agent-github-access",
            "githubAccessToken": token,
        },
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is False
    assert payload["canWrite"] is False
    assert payload["code"] == "credential_rejected"
    assert "nicht authentifiziert" in payload["error"]
    assert token not in response.get_data(as_text=True)


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
    assert conn.jobs["agent-1"]["blocker"] is None
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


def test_workspace_editor_open_is_backend_owned_and_user_scoped(tmp_path, monkeypatch):
    conn = FakeConnection()
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("SOVEREIGN_OWNER_ADMIN_ID", "user-1")
    monkeypatch.setenv("SOVEREIGN_CODE_SERVER_PUBLIC_URL", "https://code.arelorian.de")
    seed_job(conn, "user-1", "agent-editor", status="running")
    (tmp_path / "agent-editor" / "repo" / ".git").mkdir(parents=True)
    app = create_test_app(conn)

    opened = app.test_client().post(
        "/api/user/agent/jobs/agent-editor/editor/open",
        headers={"X-Test-User": "user-1"},
        json={},
    )
    other = app.test_client().post(
        "/api/user/agent/jobs/agent-editor/editor/open",
        headers={"X-Test-User": "user-2"},
        json={},
    )

    assert opened.status_code == 200
    payload = opened.get_json()
    assert payload["editor"]["workspaceAuthority"] == "sovereign-backend"
    assert payload["editor"]["mcpWorkspaceAuthority"] is False
    assert payload["editor"]["editorFolder"] == "/config/sovereign-agent-workspaces/agent-editor/repo"
    assert other.status_code == 404


def test_workspace_editor_shared_runtime_blocks_non_owner(tmp_path, monkeypatch):
    conn = FakeConnection()
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("SOVEREIGN_OWNER_ADMIN_ID", "owner-1")
    monkeypatch.setenv("SOVEREIGN_CODE_SERVER_PUBLIC_URL", "https://code.arelorian.de")
    seed_job(conn, "user-2", "agent-editor-user", status="running")
    (tmp_path / "agent-editor-user" / "repo" / ".git").mkdir(parents=True)
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/jobs/agent-editor-user/editor/open",
        headers={"X-Test-User": "user-2"},
        json={},
    )

    assert response.status_code == 403
    assert response.get_json()["workspaceAuthority"] == "sovereign-backend"
    assert "owner-only" in response.get_json()["error"]


def test_rescue_free_diagnosis_is_revision_bound_and_read_only(monkeypatch):
    conn = FakeConnection()
    base_sha = "a" * 40
    monkeypatch.setattr(
        routes_module,
        "resolve_github_head",
        lambda repository, branch, token=None: {
            "repository": "https://github.com/example/broken-app",
            "baseBranch": "main",
            "baseSha": base_sha,
        },
    )
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/rescue/diagnose",
        headers={"X-Test-User": "11111111-1111-4111-8111-111111111111"},
        json={
            "repository": "https://github.com/example/broken-app",
            "baseBranch": "main",
            "failureFamily": "github_actions_ci",
            "evidenceText": "GitHub Actions workflow failed in .github/workflows/ci.yml",
        },
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["diagnosis"]["baseSha"] == base_sha
    assert payload["diagnosis"]["failureFamily"] == "github_actions_ci"
    assert payload["diagnosis"]["mutationPerformed"] is False
    assert conn.jobs == {}


def test_rescue_paid_repair_reuses_free_executor_at_exact_head(monkeypatch):
    conn = FakeConnection()
    base_sha = "b" * 40
    repair_id = "22222222-2222-4222-8222-222222222222"
    job_id = "agent-rescue-test"
    captured = {}

    monkeypatch.setattr(
        routes_module,
        "resolve_github_head",
        lambda repository, branch, token=None: {
            "repository": "https://github.com/example/broken-app",
            "baseBranch": "main",
            "baseSha": base_sha,
        },
    )
    monkeypatch.setattr(
        routes_module,
        "reserve_repair_pack",
        lambda connection, **kwargs: {
            "repairId": repair_id,
            "jobId": job_id,
            "state": "reserved",
            "chargedCredits": 10,
            "duplicate": False,
        },
    )

    def fake_start(**kwargs):
        captured["start"] = kwargs
        return {"status": "COMPLETED", "runId": "run-rescue-test", "jobId": job_id}, 200

    def fake_update(connection, **kwargs):
        captured["update"] = kwargs
        return {"repairId": repair_id, **kwargs}

    monkeypatch.setattr(routes_module, "start_cognitive_swarm_run", fake_start)
    monkeypatch.setattr(routes_module, "update_repair_execution", fake_update)
    monkeypatch.setattr(routes_module, "generate_agent_job_id", lambda: job_id)
    monkeypatch.setattr(routes_module, "verify_rescue_csrf_token", lambda *args, **kwargs: True)
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/rescue/repair",
        headers={
            "X-Test-User": "11111111-1111-4111-8111-111111111111",
            "Idempotency-Key": "33333333-3333-4333-8333-333333333333",
            "Origin": "https://studio.example.test",
            "X-Sovereign-Rescue-Origin": "https://studio.example.test",
            "X-Sovereign-Rescue-CSRF": "bound-test-token",
        },
        json={
            "repository": "https://github.com/example/broken-app",
            "baseBranch": "main",
            "expectedBaseSha": base_sha,
            "failureFamily": "github_actions_ci",
            "evidenceText": "GitHub Actions workflow failed in .github/workflows/ci.yml",
        },
    )

    payload = response.get_json()
    assert response.status_code == 202
    assert payload["ok"] is True
    assert captured["start"]["mode"] == "free"
    assert captured["start"]["intent_mode"] == "repository_execution"
    assert captured["start"]["repository_url"] == "https://github.com/example/broken-app"
    assert captured["start"]["repository_branch"] == "main"
    assert captured["start"]["expected_head_sha"] == base_sha
    assert captured["start"]["implementation_job_id"] == job_id
    assert captured["update"]["state"] == "draft_pr_ready"



def test_rescue_paid_repair_rejects_simple_content_type_before_reservation(monkeypatch):
    conn = FakeConnection()
    reserve_calls = []
    monkeypatch.setattr(
        routes_module,
        "reserve_repair_pack",
        lambda *args, **kwargs: reserve_calls.append((args, kwargs)),
    )
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/rescue/repair",
        headers={
            "X-Test-User": "11111111-1111-4111-8111-111111111111",
            "Origin": "https://evil.example.test",
            "X-Sovereign-Rescue-Origin": "https://evil.example.test",
        },
        data='{"idempotencyKey":"body-only-must-not-charge"}',
        content_type="text/plain",
    )

    assert response.status_code == 415
    assert response.get_json()["blocker"] == "rescue_json_content_type_required"
    assert reserve_calls == []


def test_rescue_duplicate_repair_returns_persisted_running_job_without_second_execution(monkeypatch):
    conn = FakeConnection()
    user_id = "11111111-1111-4111-8111-111111111111"
    base_sha = "c" * 40
    repair_id = "44444444-4444-4444-8444-444444444444"
    job_id = "agent-rescue-persisted"
    seed_job(conn, user_id, job_id, status="running")
    captured = {}

    monkeypatch.setattr(
        routes_module,
        "resolve_github_head",
        lambda repository, branch, token=None: {
            "repository": "https://github.com/example/broken-app",
            "baseBranch": "main",
            "baseSha": base_sha,
        },
    )
    monkeypatch.setattr(
        routes_module,
        "reserve_repair_pack",
        lambda connection, **kwargs: {
            "repairId": repair_id,
            "jobId": job_id,
            "runId": "run-persisted",
            "state": "running",
            "chargedCredits": 10,
            "duplicate": True,
        },
    )
    monkeypatch.setattr(
        routes_module,
        "start_cognitive_swarm_run",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("duplicate execution must not start")),
    )
    monkeypatch.setattr(
        routes_module,
        "update_repair_execution",
        lambda connection, **kwargs: captured.update(kwargs) or {"repairId": repair_id, **kwargs},
    )
    monkeypatch.setattr(routes_module, "verify_rescue_csrf_token", lambda *args, **kwargs: True)
    app = create_test_app(conn)

    response = app.test_client().post(
        "/api/user/agent/rescue/repair",
        headers={
            "X-Test-User": user_id,
            "Idempotency-Key": "55555555-5555-4555-8555-555555555555",
            "Origin": "https://studio.example.test",
            "X-Sovereign-Rescue-Origin": "https://studio.example.test",
            "X-Sovereign-Rescue-CSRF": "bound-test-token",
        },
        json={
            "repository": "https://github.com/example/broken-app",
            "baseBranch": "main",
            "expectedBaseSha": base_sha,
            "failureFamily": "github_actions_ci",
            "evidenceText": "GitHub Actions workflow failed in .github/workflows/ci.yml",
        },
    )

    payload = response.get_json()
    assert response.status_code == 202
    assert payload["duplicate"] is True
    assert payload["repair"]["jobId"] == job_id
    assert payload["repair"]["state"] == "running"
    assert captured["state"] == "running"
    assert captured["job_id"] == job_id


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def seed_capsule_evidence(
    conn: FakeConnection,
    tmp_path: Path,
    *,
    user_id: str = "11111111-1111-4111-8111-111111111111",
    repair_id: str = "66666666-6666-4666-8666-666666666666",
    job_id: str = "agent-capsule-test",
) -> tuple[str, str, str]:
    seed_job(conn, user_id, job_id, status="running")
    repo = tmp_path / job_id / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Capsule Route Test")
    _git(repo, "config", "user.email", "capsule-route@example.invalid")
    (repo / "README.md").write_text("before\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "baseline")
    base_sha = _git(repo, "rev-parse", "HEAD")
    (repo / "README.md").write_text("after\n", encoding="utf-8")
    conn.jobs[job_id]["workspace_id"] = job_id
    conn.jobs[job_id]["changed_files"] = ["README.md"]
    conn.jobs[job_id]["test_summary"] = "targeted capsule route tests passed"
    conn.rescues[repair_id] = {
        "user_id": user_id,
        "repair_id": repair_id,
        "job_id": job_id,
        "state": "draft_pr_ready",
        "failure_family": "github_actions_ci",
        "base_sha": base_sha,
        "repository": "https://github.com/example/broken-app",
        "outcome_contract_sha256": "c" * 64,
    }
    return user_id, repair_id, base_sha


def _capsule_headers(user_id: str) -> dict[str, str]:
    return {
        "X-Test-User": user_id,
        "X-Sovereign-Rescue-CSRF": "bound-test-token",
        "Origin": "https://studio.example.test",
        "X-Sovereign-Rescue-Origin": "https://studio.example.test",
    }


def test_rescue_capsule_returns_deterministic_zero_write_attachment(monkeypatch, tmp_path: Path):
    conn = FakeConnection()
    user_id, repair_id, base_sha = seed_capsule_evidence(conn, tmp_path)
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(routes_module, "verify_rescue_csrf_token", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        routes_module,
        "read_github_pr_evidence",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Capsule must not call GitHub")),
    )
    app = create_test_app(conn)
    conn.executed.clear()
    conn.commits = 0

    first = app.test_client().post(
        f"/api/user/agent/rescue/repairs/{repair_id}/capsule",
        headers=_capsule_headers(user_id),
        json={},
    )
    second = app.test_client().post(
        f"/api/user/agent/rescue/repairs/{repair_id}/capsule",
        headers=_capsule_headers(user_id),
        json={},
    )

    assert first.status_code == 200
    assert first.content_type == "application/zip"
    assert first.headers["X-Sovereign-Capsule-Base-Sha"] == base_sha
    assert first.headers["X-Sovereign-Mutation-Performed"] == "false"
    assert len(first.headers["X-Sovereign-Capsule-Sha256"]) == 64
    assert first.data == second.data
    assert first.headers["X-Sovereign-Capsule-Sha256"] == second.headers["X-Sovereign-Capsule-Sha256"]
    with zipfile.ZipFile(io.BytesIO(first.data)) as archive:
        assert archive.namelist() == ["README.md", "manifest.json", "repair.patch", "verify.py"]
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["baseSha"] == base_sha
        assert manifest["productionMutationIncluded"] is False
        assert manifest["secretValuesReturned"] is False
        assert manifest["changedFiles"] == ["README.md"]
    assert conn.commits == 0
    assert all("SELECT" in " ".join(sql.upper().split()) for sql, _ in conn.executed)


def test_rescue_capsule_rejects_request_fields_and_cross_tenant_access(monkeypatch, tmp_path: Path):
    conn = FakeConnection()
    user_id, repair_id, _ = seed_capsule_evidence(conn, tmp_path)
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(routes_module, "verify_rescue_csrf_token", lambda *args, **kwargs: True)
    app = create_test_app(conn)

    forbidden = app.test_client().post(
        f"/api/user/agent/rescue/repairs/{repair_id}/capsule",
        headers=_capsule_headers(user_id),
        json={"githubAccessToken": "not-accepted"},
    )
    cross_tenant = app.test_client().post(
        f"/api/user/agent/rescue/repairs/{repair_id}/capsule",
        headers=_capsule_headers("22222222-2222-4222-8222-222222222222"),
        json={},
    )

    assert forbidden.status_code == 400
    assert forbidden.get_json()["blocker"] == "capsule_request_fields_forbidden"
    assert cross_tenant.status_code == 404
    assert cross_tenant.content_type.startswith("application/json")


def test_rescue_capsule_blocks_stale_workspace_base(monkeypatch, tmp_path: Path):
    conn = FakeConnection()
    user_id, repair_id, _ = seed_capsule_evidence(conn, tmp_path)
    conn.rescues[repair_id]["base_sha"] = "b" * 40
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(routes_module, "verify_rescue_csrf_token", lambda *args, **kwargs: True)
    app = create_test_app(conn)

    response = app.test_client().post(
        f"/api/user/agent/rescue/repairs/{repair_id}/capsule",
        headers=_capsule_headers(user_id),
        json={},
    )

    assert response.status_code == 409
    assert response.get_json()["blocker"] == "capsule_workspace_base_stale"
    assert response.get_json()["mutationPerformed"] is False
