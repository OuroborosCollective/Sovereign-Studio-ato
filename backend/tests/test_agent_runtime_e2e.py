from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.draft_pr_gate import DraftPrPreparationInput, prepare_draft_pr  # noqa: E402
from agent_runtime.evidence_gate import EvidenceGateInput, evaluate_agent_evidence  # noqa: E402
from agent_runtime.job_lifecycle import create_sovereign_agent_job  # noqa: E402
from agent_runtime.job_store import mark_draft_pr_prepared, read_agent_job  # noqa: E402
from agent_runtime.pattern_gateway import (  # noqa: E402
    PatternLearningInput,
    evaluate_pattern_learning,
    persist_pattern_learning_candidate,
)
from agent_runtime.tool_runner import run_agent_job_tool  # noqa: E402


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
                "events": params[11],
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
        elif normalized.startswith("INSERT INTO SOVEREIGN_AGENT_PATTERN_CANDIDATES"):
            self.conn.pattern_candidates.append({
                "candidate_id": params[0],
                "user_id": params[1],
                "job_id": params[2],
                "decision": params[3],
                "kind": params[4],
                "summary": params[5],
                "payload": json.loads(params[6]),
                "remote_memory_allowed": params[7],
                "predictive_signal": params[8],
            })
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS") and "SET EVENTS" in normalized:
            job_id = params[1]
            self.conn.jobs[job_id]["events"] = self.conn.jobs[job_id].get("events", []) + json.loads(params[0])
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS") and "PR_STATE = 'READY'" in normalized:
            job_id = params[-1]
            self.conn.jobs[job_id]["status"] = "validating"
            self.conn.jobs[job_id]["pr_state"] = "ready"
            self.conn.jobs[job_id]["branch_name"] = params[0]
            self.conn.jobs[job_id]["target_branch"] = params[1]
            self.conn.jobs[job_id]["commit_message"] = params[2]
            self.conn.jobs[job_id]["draft_pr_preparation"] = {
                "branchName": params[0],
                "targetBranch": params[1],
                "commitMessage": params[2],
            }
            self.conn.jobs[job_id]["blocker"] = None
        elif normalized.startswith("UPDATE SOVEREIGN_AGENT_JOBS"):
            job_id = params[-1]
            self.conn.jobs[job_id]["status"] = params[0]
            if params[1]:
                self.conn.jobs[job_id]["workspace_id"] = params[1]
            if params[3]:
                self.conn.jobs[job_id]["changed_files"] = json.loads(params[3])
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
        self.pattern_candidates = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


def _run_git(repo_dir: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True, text=True)


def _seed_git_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    _run_git(repo_dir, "init")
    _run_git(repo_dir, "config", "user.email", "sovereign@example.invalid")
    _run_git(repo_dir, "config", "user.name", "Sovereign Runtime Test")
    (repo_dir / "README.md").write_text("# Sovereign Studio\n\nInitial runtime proof.\n", encoding="utf-8")
    _run_git(repo_dir, "add", "README.md")
    _run_git(repo_dir, "commit", "-m", "Initial README")


def test_sovereign_agent_runtime_full_e2e_without_openhands(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("OPENHANDS_API_URL", raising=False)
    monkeypatch.setenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", str(tmp_path))
    conn = FakeConnection()

    lifecycle = create_sovereign_agent_job(
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
        job_id="agent-e2e-1",
    )
    assert lifecycle.result.executor == "sovereign-local-runner"
    assert lifecycle.result.status == "provisioning"

    repo_dir = tmp_path / "agent-e2e-1" / "repo"
    _seed_git_repo(repo_dir)

    file_result = run_agent_job_tool(lifecycle.result, "file", {
        "mode": "write",
        "path": "README.md",
        "content": "# Sovereign Studio\n\nRuntime E2E proof generated real evidence.\n",
    }, tmp_path)
    assert file_result.status == "done"
    assert file_result.changed_files == ("README.md",)

    status_result = run_agent_job_tool(lifecycle.result, "git-status", {}, tmp_path)
    assert status_result.status == "done"
    assert "README.md" in status_result.changed_files

    diff_result = run_agent_job_tool(lifecycle.result, "diff", {}, tmp_path)
    assert diff_result.status == "done"
    assert "Runtime E2E proof" in (diff_result.diff_summary or "")

    test_result = run_agent_job_tool(lifecycle.result, "test", {
        "command": "python -c \"print('1 passed, 0 failed')\"",
        "timeout": 20,
    }, tmp_path)
    assert test_result.status == "done"
    assert "1 passed" in (test_result.test_summary or "")

    evidence = evaluate_agent_evidence(EvidenceGateInput(
        job_id="agent-e2e-1",
        changed_files=status_result.changed_files,
        diff_summary=diff_result.diff_summary,
        test_summary=test_result.test_summary,
    ))
    assert evidence.passed is True
    assert evidence.can_prepare_draft_pr is True
    assert evidence.can_learn_pattern is True

    draft = prepare_draft_pr(DraftPrPreparationInput(
        job_id="agent-e2e-1",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        base_branch="main",
        mission="README smoke change in draft-pr-only mode",
        changed_files=status_result.changed_files,
        diff_summary=diff_result.diff_summary,
        test_summary=test_result.test_summary,
        evidence_gate=evidence,
    ))
    assert draft.allowed is True
    assert draft.can_create_draft_pr is True
    assert draft.next_action == "create_draft_pr"

    mark_draft_pr_prepared(
        conn,
        job_id="agent-e2e-1",
        head_branch=draft.head_branch or "sovereign/agent-e2e-1-readme",
        base_branch=draft.base_branch or "main",
        title=draft.title or "Draft: README smoke change",
        body=draft.body or "",
    )

    stored = read_agent_job(conn, user_id="user-1", job_id="agent-e2e-1")
    assert stored is not None
    assert stored.pr_state == "ready"
    assert stored.branch_name is not None

    pattern = evaluate_pattern_learning(PatternLearningInput(
        job_id="agent-e2e-1",
        source="agent-runtime-e2e",
        mission="README smoke change in draft-pr-only mode",
        changed_files=status_result.changed_files,
        diff_summary=diff_result.diff_summary,
        test_summary=test_result.test_summary,
        evidence_passed=evidence.passed,
        can_learn_pattern=evidence.can_learn_pattern,
        draft_pr_ready=True,
    ))
    assert pattern.allowed is True
    assert pattern.kind == "solution"
    assert pattern.remote_memory_allowed is True

    persist_pattern_learning_candidate(conn, user_id="user-1", result=pattern)
    assert conn.pattern_candidates
    assert conn.pattern_candidates[0]["remote_memory_allowed"] is True

    assert "OPENHANDS_API_URL" not in os.environ
    assert all("completed" != job["status"] or job.get("changed_files") or job.get("diff_summary") or job.get("test_summary") or job.get("blocker") for job in conn.jobs.values())
