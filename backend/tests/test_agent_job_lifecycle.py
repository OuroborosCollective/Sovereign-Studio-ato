from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.contracts import SovereignAgentEvent  # noqa: E402
from agent_runtime.git_workspace import GitWorkspaceResult  # noqa: E402
from agent_runtime.job_lifecycle import create_sovereign_agent_job  # noqa: E402
from agent_runtime.job_store import create_agent_job_record, list_agent_jobs, read_agent_job  # noqa: E402
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
                "allowed_paths": params[8],
                "forbidden_paths": params[9],
                "memory_hints": params[10],
                "changed_files": [],
                "events": params[11],
                "blocker": params[12],
            }
        elif normalized.startswith("INSERT INTO SOVEREIGN_AGENT_EVENTS"):
            self.conn.events.append(params)
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS") and "SET EVENTS" in normalized:
            job_id = params[1]
            # events come as JSON string, need to parse and extend
            import json
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

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def valid_payload(**overrides):
    payload = {
        "repoUrl": "https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        "branch": "main",
        "mission": "Update README and prepare a Draft PR.",
        "executor": "sovereign-local-runner",
        "draftPrOnly": True,
        "allowAutoMerge": False,
    }
    payload.update(overrides)
    return payload


def test_create_agent_job_queues_without_workspace(tmp_path: Path):
    conn = FakeConnection()

    lifecycle = create_sovereign_agent_job(
        conn,
        user_id="user-1",
        payload=valid_payload(),
        workspace_root=tmp_path,
        provision_workspace=False,
        job_id="agent-test-1",
    )

    assert lifecycle.job_id == "agent-test-1"
    assert lifecycle.result.status == "queued"
    assert conn.jobs["agent-test-1"]["status"] == "queued"
    assert not (tmp_path / "agent-test-1").exists()
    assert conn.commits >= 1


def test_invalid_request_is_persisted_as_blocked_without_workspace(tmp_path: Path):
    conn = FakeConnection()

    lifecycle = create_sovereign_agent_job(
        conn,
        user_id="user-1",
        payload=valid_payload(repoUrl="https://evil.example/repo"),
        workspace_root=tmp_path,
        provision_workspace=True,
        job_id="agent-bad-1",
    )

    assert lifecycle.result.status == "blocked"
    assert "valid HTTPS GitHub" in (lifecycle.result.blocker or "")
    assert conn.jobs["agent-bad-1"]["status"] == "blocked"
    assert not (tmp_path / "agent-bad-1").exists()


def test_valid_request_provisions_workspace_and_updates_state(tmp_path: Path):
    conn = FakeConnection()

    lifecycle = create_sovereign_agent_job(
        conn,
        user_id="user-1",
        payload=valid_payload(),
        workspace_root=tmp_path,
        provision_workspace=True,
        clone_repo=False,
        job_id="agent-workspace-1",
    )

    assert lifecycle.result.status == "provisioning"
    assert lifecycle.result.workspace_id == "agent-workspace-1"
    assert (tmp_path / "agent-workspace-1" / "repo").exists()
    assert conn.jobs["agent-workspace-1"]["status"] == "provisioning"
    assert conn.jobs["agent-workspace-1"]["workspace_id"] == "agent-workspace-1"


def test_clone_success_moves_job_to_running(monkeypatch, tmp_path: Path):
    conn = FakeConnection()

    def fake_clone(workspace_id, repo_url, branch, workspace_root, token=None):
        assert workspace_id == "agent-clone-1"
        assert repo_url.startswith("https://github.com/")
        assert branch == "main"
        assert repo_dir_for_workspace(workspace_id, workspace_root).exists()
        return GitWorkspaceResult(
            status="done",
            events=(SovereignAgentEvent(stage="repo_clone_completed", level="success", message="Repository snapshot ready."),),
            exit_code=0,
        )

    monkeypatch.setattr("agent_runtime.job_lifecycle.clone_repo_into_workspace", fake_clone)

    lifecycle = create_sovereign_agent_job(
        conn,
        user_id="user-1",
        payload=valid_payload(),
        workspace_root=tmp_path,
        provision_workspace=True,
        clone_repo=True,
        job_id="agent-clone-1",
    )

    assert lifecycle.result.status == "running"
    assert conn.jobs["agent-clone-1"]["status"] == "running"
    assert conn.jobs["agent-clone-1"]["workspace_id"] == "agent-clone-1"
    assert any(event.stage == "repo_clone_completed" for event in lifecycle.events)


def _fake_git_clone_with_readme(workspace_id, repo_url, branch, workspace_root, token=None):
    repo_path = repo_dir_for_workspace(workspace_id, workspace_root)
    subprocess.run(["git", "init", "-b", branch], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runtime"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo_path, check=True)
    (repo_path / "README.md").write_text("# Original\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", repo_url], cwd=repo_path, check=True)
    return GitWorkspaceResult(
        status="done",
        events=(SovereignAgentEvent(stage="repo_clone_completed", level="success", message="Repository snapshot ready."),),
        exit_code=0,
    )


def test_confirmed_document_change_creates_real_workspace_evidence(monkeypatch, tmp_path: Path):
    conn = FakeConnection()
    monkeypatch.setattr("agent_runtime.job_lifecycle.clone_repo_into_workspace", _fake_git_clone_with_readme)

    lifecycle = create_sovereign_agent_job(
        conn,
        user_id="user-1",
        payload=valid_payload(stagedFiles=[{
            "path": "README.md",
            "baseContent": "# Original\n",
            "content": "# Updated\n\nRuntime truth.\n",
        }]),
        workspace_root=tmp_path,
        provision_workspace=True,
        clone_repo=False,
        job_id="agent-staged-doc",
    )

    assert lifecycle.result.status == "running"
    assert lifecycle.result.changed_files == ("README.md",)
    assert "README.md" in (lifecycle.result.diff_summary or "")
    assert lifecycle.result.test_summary == "git diff --check passed for documentation-only staged changes."
    assert (repo_dir_for_workspace("agent-staged-doc", tmp_path) / "README.md").read_text() == "# Updated\n\nRuntime truth.\n"


def test_existing_staged_file_requires_base_content(monkeypatch, tmp_path: Path):
    conn = FakeConnection()
    monkeypatch.setattr("agent_runtime.job_lifecycle.clone_repo_into_workspace", _fake_git_clone_with_readme)

    lifecycle = create_sovereign_agent_job(
        conn,
        user_id="user-1",
        payload=valid_payload(stagedFiles=[{
            "path": "README.md",
            "content": "# Overwrite without base evidence\n",
        }]),
        workspace_root=tmp_path,
        provision_workspace=True,
        job_id="agent-staged-no-base",
    )

    assert lifecycle.result.status == "blocked"
    assert lifecycle.result.blocker == "baseContent is required for existing staged file: README.md"
    assert (repo_dir_for_workspace("agent-staged-no-base", tmp_path) / "README.md").read_text() == "# Original\n"


def test_staged_change_blocks_when_base_content_drifted(monkeypatch, tmp_path: Path):
    conn = FakeConnection()
    monkeypatch.setattr("agent_runtime.job_lifecycle.clone_repo_into_workspace", _fake_git_clone_with_readme)

    lifecycle = create_sovereign_agent_job(
        conn,
        user_id="user-1",
        payload=valid_payload(stagedFiles=[{
            "path": "README.md",
            "baseContent": "# Stale base\n",
            "content": "# Unsafe overwrite\n",
        }]),
        workspace_root=tmp_path,
        provision_workspace=True,
        job_id="agent-staged-drift",
    )

    assert lifecycle.result.status == "blocked"
    assert lifecycle.result.blocker == "staged base content drift detected: README.md"
    assert (repo_dir_for_workspace("agent-staged-drift", tmp_path) / "README.md").read_text() == "# Original\n"


def test_staged_change_rejects_path_escape_before_workspace(tmp_path: Path):
    conn = FakeConnection()

    lifecycle = create_sovereign_agent_job(
        conn,
        user_id="user-1",
        payload=valid_payload(stagedFiles=[{
            "path": "../outside.md",
            "content": "unsafe",
        }]),
        workspace_root=tmp_path,
        provision_workspace=True,
        job_id="agent-staged-escape",
    )

    assert lifecycle.result.status == "blocked"
    assert "unsafe staged file path" in (lifecycle.result.blocker or "")
    assert not (tmp_path / "agent-staged-escape").exists()


def test_ephemeral_github_token_reaches_clone_but_is_not_persisted(monkeypatch, tmp_path: Path):
    conn = FakeConnection()
    observed = {}
    token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"

    def fake_clone(workspace_id, repo_url, branch, workspace_root, token=None):
        observed["token"] = token
        return GitWorkspaceResult(
            status="done",
            events=(SovereignAgentEvent(stage="repo_clone_completed", level="success", message="Repository snapshot ready."),),
            exit_code=0,
        )

    monkeypatch.setattr("agent_runtime.job_lifecycle.clone_repo_into_workspace", fake_clone)
    lifecycle = create_sovereign_agent_job(
        conn,
        user_id="user-1",
        payload=valid_payload(githubAccessToken=token),
        workspace_root=tmp_path,
        provision_workspace=True,
        clone_repo=True,
        job_id="agent-token-ephemeral",
    )

    assert lifecycle.result.status == "running"
    assert observed["token"] == token
    assert token not in repr(conn.jobs)
    assert token not in repr(conn.events)


def test_invalid_ephemeral_github_token_blocks_before_workspace(tmp_path: Path):
    conn = FakeConnection()
    lifecycle = create_sovereign_agent_job(
        conn,
        user_id="user-1",
        payload=valid_payload(githubAccessToken="not-a-token"),
        workspace_root=tmp_path,
        provision_workspace=True,
        clone_repo=True,
        job_id="agent-token-invalid",
    )

    assert lifecycle.result.status == "blocked"
    assert lifecycle.result.blocker == "githubAccessToken has an invalid format"
    assert not (tmp_path / "agent-token-invalid").exists()


def test_clone_blocker_moves_job_to_blocked(monkeypatch, tmp_path: Path):
    conn = FakeConnection()

    def fake_clone(workspace_id, repo_url, branch, workspace_root, token=None):
        return GitWorkspaceResult(
            status="blocked",
            events=(SovereignAgentEvent(stage="repo_clone_blocked", level="warning", message="Repo directory is not empty."),),
            blocker="Repo directory is not empty.",
        )

    monkeypatch.setattr("agent_runtime.job_lifecycle.clone_repo_into_workspace", fake_clone)

    lifecycle = create_sovereign_agent_job(
        conn,
        user_id="user-1",
        payload=valid_payload(),
        workspace_root=tmp_path,
        provision_workspace=True,
        clone_repo=True,
        job_id="agent-clone-blocked",
    )

    assert lifecycle.result.status == "blocked"
    assert lifecycle.result.blocker == "Repo directory is not empty."
    assert conn.jobs["agent-clone-blocked"]["status"] == "blocked"
    assert conn.jobs["agent-clone-blocked"]["blocker"] == "Repo directory is not empty."


def test_job_store_read_and_list_are_user_scoped():
    conn = FakeConnection()
    create_agent_job_record(
        conn,
        user_id="user-1",
        job_id="agent-1",
        request=valid_payload_request(),
    )
    create_agent_job_record(
        conn,
        user_id="user-2",
        job_id="agent-2",
        request=valid_payload_request(),
    )

    assert read_agent_job(conn, user_id="user-1", job_id="agent-1") is not None
    assert read_agent_job(conn, user_id="user-1", job_id="agent-2") is None
    jobs = list_agent_jobs(conn, user_id="user-1")
    assert len(jobs) == 1
    assert jobs[0].job_id == "agent-1"


def valid_payload_request():
    from agent_runtime.contracts import build_sovereign_agent_job_request

    return build_sovereign_agent_job_request(valid_payload())
