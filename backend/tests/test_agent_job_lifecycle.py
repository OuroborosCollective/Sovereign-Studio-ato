from __future__ import annotations

import os
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
                "changed_files": [],
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

    def fake_clone(workspace_id, repo_url, branch, workspace_root):
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


def test_clone_blocker_moves_job_to_blocked(monkeypatch, tmp_path: Path):
    conn = FakeConnection()

    def fake_clone(workspace_id, repo_url, branch, workspace_root):
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
