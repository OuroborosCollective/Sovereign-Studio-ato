from __future__ import annotations

import os
import sys
from pathlib import Path

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.job_lifecycle import create_sovereign_agent_job  # noqa: E402


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
                "events": params[11],
                "blocker": params[12],
            }
        elif normalized.startswith("INSERT INTO SOVEREIGN_AGENT_EVENTS"):
            self.conn.events.append(params)
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS") and "SET EVENTS" in normalized:
            pass
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS"):
            job_id = params[-1]
            self.conn.jobs[job_id]["status"] = params[0]
            if params[1]:
                self.conn.jobs[job_id]["workspace_id"] = params[1]
            if params[7]:
                self.conn.jobs[job_id]["blocker"] = None
            elif params[8]:
                self.conn.jobs[job_id]["blocker"] = params[8]

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


def test_sovereign_agent_runtime_does_not_require_openhands(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("OPENHANDS_API_URL", raising=False)
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    conn = FakeConnection()

    result = create_sovereign_agent_job(
        conn,
        user_id="user-1",
        payload={
            "repoUrl": "https://github.com/OuroborosCollective/Sovereign-Studio-ato",
            "branch": "main",
            "mission": "README smoke change in draft-pr-only mode",
            "executor": "sovereign-local-runner",
            "draftPrOnly": True,
            "allowAutoMerge": False,
        },
        workspace_root=tmp_path,
        provision_workspace=True,
        clone_repo=False,
        job_id="agent-no-openhands",
    )

    assert result.result.status in ("queued", "provisioning", "running", "completed", "blocked")
    assert result.result.executor == "sovereign-local-runner"
    assert conn.jobs["agent-no-openhands"]["executor"] == "sovereign-local-runner"
    assert all("openhands" not in str(query).lower() for query, _params in conn.executed)
    assert (tmp_path / "agent-no-openhands" / "repo").exists()
    assert result.result.status != "completed" or result.result.changed_files or result.result.diff_summary or result.result.test_summary or result.result.draft_pr_url or result.result.blocker
