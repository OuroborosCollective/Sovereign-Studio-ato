from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.agent_zero_a2a import (  # noqa: E402
    AgentZeroA2ASubmitOutcomeUnknown,
    AgentZeroA2ATask,
    AgentZeroA2ATaskLost,
)
from agent_runtime.job_store import (  # noqa: E402
    StoredSovereignAgentJob,
    compare_and_swap_agent_job_external_ref,
)
import agent_runtime.repository_execution as repository_execution  # noqa: E402


class _CasCursor:
    def __init__(self, conn):
        self.conn = conn
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        assert "external_ref IS NOT DISTINCT FROM %s" in sql
        assert "RETURNING job_id" in sql
        new_ref, job_id, expected_ref = params
        if job_id == self.conn.job_id and self.conn.external_ref == expected_ref:
            self.conn.external_ref = new_ref
            self.row = {"job_id": job_id}
        else:
            self.row = None

    def fetchone(self):
        return self.row


class _CasConnection:
    def __init__(self, external_ref=None):
        self.job_id = "agent-cas"
        self.external_ref = external_ref
        self.commits = 0

    def cursor(self):
        return _CasCursor(self)

    def commit(self):
        self.commits += 1


def _job(*, external_ref: str | None = "agent-zero-a2a:task-original", status: str = "running"):
    return StoredSovereignAgentJob(
        job_id="agent-test",
        user_id="owner-test",
        executor="sovereign-local-runner",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        branch="main",
        mission="Implement one bounded repository change.",
        status=status,
        workspace_id="agent-test",
        external_ref=external_ref,
    )


def test_initial_submit_claim_wins_once():
    conn = _CasConnection()
    first = "agent-zero-a2a:claim:submit:a:first"
    second = "agent-zero-a2a:claim:submit:b:second"

    assert compare_and_swap_agent_job_external_ref(
        conn, job_id=conn.job_id, expected_ref=None, new_ref=first,
    ) is True
    assert compare_and_swap_agent_job_external_ref(
        conn, job_id=conn.job_id, expected_ref=None, new_ref=second,
    ) is False
    assert conn.external_ref == first


def test_closeout_claim_wins_once():
    original = "agent-zero-a2a:task-1"
    conn = _CasConnection(original)
    first = "agent-zero-a2a:claim:closeout:a:first"
    second = "agent-zero-a2a:claim:closeout:b:second"

    assert compare_and_swap_agent_job_external_ref(
        conn, job_id=conn.job_id, expected_ref=original, new_ref=first,
    ) is True
    assert compare_and_swap_agent_job_external_ref(
        conn, job_id=conn.job_id, expected_ref=original, new_ref=second,
    ) is False
    assert conn.external_ref == first


def test_restart_recovery_claim_wins_once():
    original = "agent-zero-a2a:task-1"
    conn = _CasConnection(original)
    first = "agent-zero-a2a:claim:retry:a:first"
    second = "agent-zero-a2a:claim:retry:b:second"

    assert compare_and_swap_agent_job_external_ref(
        conn, job_id=conn.job_id, expected_ref=original, new_ref=first,
    ) is True
    assert compare_and_swap_agent_job_external_ref(
        conn, job_id=conn.job_id, expected_ref=original, new_ref=second,
    ) is False
    assert conn.external_ref == first


def _patch_job_store(monkeypatch, initial: StoredSovereignAgentJob):
    state = {"job": initial, "events": []}

    def read_agent_job(_conn, *, user_id, job_id):
        job = state["job"]
        return job if job.user_id == user_id and job.job_id == job_id else None

    def cas(_conn, *, job_id, expected_ref, new_ref):
        job = state["job"]
        if job.job_id != job_id or job.external_ref != expected_ref:
            return False
        state["job"] = replace(job, external_ref=new_ref)
        return True

    def update(_conn, *, job_id, status, workspace_id=None, external_ref=None,
               changed_files=None, diff_summary=None, test_summary=None,
               draft_pr_url=None, blocker=None, clear_blocker=False):
        job = state["job"]
        assert job.job_id == job_id
        state["job"] = replace(
            job,
            status=status,
            workspace_id=workspace_id or job.workspace_id,
            external_ref=external_ref or job.external_ref,
            changed_files=tuple(changed_files) if changed_files is not None else job.changed_files,
            diff_summary=diff_summary if diff_summary is not None else job.diff_summary,
            test_summary=test_summary if test_summary is not None else job.test_summary,
            draft_pr_url=draft_pr_url or job.draft_pr_url,
            blocker=None if clear_blocker else (blocker or job.blocker),
        )

    def append(_conn, job_id, event):
        assert job_id == state["job"].job_id
        state["events"].append(event)

    monkeypatch.setattr(repository_execution, "read_agent_job", read_agent_job)
    monkeypatch.setattr(repository_execution, "compare_and_swap_agent_job_external_ref", cas)
    monkeypatch.setattr(repository_execution, "update_agent_job_state", update)
    monkeypatch.setattr(repository_execution, "append_agent_event", append)
    return state


def test_original_task_lost_resubmits_exactly_once_then_retry_lost_fails_closed(monkeypatch):
    state = _patch_job_store(monkeypatch, _job())

    class Client:
        submit_count = 0

        def get_task(self, task_id):
            raise AgentZeroA2ATaskLost(
                "AGENT_ZERO_A2A_TASK_LOST",
                "USE_SINGLE_ATOMIC_RESTART_RECOVERY",
                http_status=404,
            )

        def submit_repository_task(self, *, workspace_id, mission):
            assert workspace_id == "agent-test"
            assert mission == state["job"].mission
            self.submit_count += 1
            return AgentZeroA2ATask(task_id="task-retry", state="submitted")

    client = Client()
    recovered = repository_execution.reconcile_repository_execution(
        object(),
        user_id="owner-test",
        job_id="agent-test",
        a2a_client_factory=lambda: client,
    )

    assert recovered is not None
    assert recovered.external_ref == "agent-zero-a2a:retry:task-retry"
    assert client.submit_count == 1

    terminal = repository_execution.reconcile_repository_execution(
        object(),
        user_id="owner-test",
        job_id="agent-test",
        a2a_client_factory=lambda: client,
    )

    assert terminal is not None
    assert terminal.status == "blocked"
    assert "no further resubmit" in (terminal.blocker or "")
    assert client.submit_count == 1


def test_ambiguous_submit_outcome_blocks_without_any_automatic_second_submit(monkeypatch):
    claim = "agent-zero-a2a:claim:submit:a:test"
    state = _patch_job_store(monkeypatch, _job(external_ref=claim))

    class Client:
        submit_count = 0

        def submit_repository_task(self, **_kwargs):
            self.submit_count += 1
            raise AgentZeroA2ASubmitOutcomeUnknown(
                "AGENT_ZERO_A2A_SUBMIT_OUTCOME_UNKNOWN",
                "DO_NOT_RESUBMIT_UNTIL_TASK_ACCEPTANCE_CAN_BE_PROVEN",
            )

    client = Client()
    blocked = repository_execution._submit_after_claim(
        object(),
        job=state["job"],
        claim_ref=claim,
        retry=False,
        a2a_client_factory=lambda: client,
    )

    assert blocked.status == "blocked"
    assert client.submit_count == 1
    assert state["job"].external_ref == claim
    assert "automatic resubmit is forbidden" in (blocked.blocker or "")


def _done_tool(*, changed_files=(), output="ok", metadata=None):
    return SimpleNamespace(
        status="done",
        changed_files=tuple(changed_files),
        blocker=None,
        error=None,
        output=output,
        metadata=metadata or {},
    )


def _failed_tool(reason="failed"):
    return SimpleNamespace(
        status="error",
        changed_files=(),
        blocker=None,
        error=reason,
        output="",
        metadata={},
    )


def _patch_closeout_baseline(monkeypatch, *, janitor_metadata=None, test_result=None, gate=None):
    state = _patch_job_store(
        monkeypatch,
        _job(external_ref="agent-zero-a2a:claim:closeout:a:test"),
    )
    changed = ("backend/agent_runtime/example.py",)

    def tool(_job_value, action, _params, _root):
        if action == "git-status":
            return _done_tool(changed_files=changed)
        if action == "diff":
            return _done_tool(output="diff --git a/example b/example\n+real change")
        if action == "janitor":
            return _done_tool(metadata=janitor_metadata or {
                "severityCounts": {},
                "recommendedTestCommand": "pytest backend/tests/test_example.py",
            })
        if action == "test":
            return test_result or _done_tool(output="1 passed")
        raise AssertionError(action)

    monkeypatch.setattr(repository_execution, "run_agent_job_tool", tool)
    monkeypatch.setattr(
        repository_execution,
        "git_diff_full",
        lambda *_args, **_kwargs: (
            b"diff --git a/example b/example\n+real implementation\n",
            SimpleNamespace(status="done", blocker=None),
        ),
    )
    monkeypatch.setattr(
        repository_execution,
        "git_diff_check",
        lambda *_args, **_kwargs: SimpleNamespace(status="done", blocker=None),
    )
    monkeypatch.setattr(
        repository_execution,
        "evaluate_agent_evidence",
        lambda _input: gate or SimpleNamespace(
            passed=True,
            can_prepare_draft_pr=True,
            reason="all evidence passed",
        ),
    )
    return state, changed


def _run_closeout(state):
    return repository_execution._closeout_repository_job(
        object(),
        job=state["job"],
        claim_ref="agent-zero-a2a:claim:closeout:a:test",
        bound_ref="agent-zero-a2a:task-original",
        workspace_root=Path("/tmp/not-used-by-mocked-tools"),
    )


def test_closeout_blocks_when_no_changes_exist(monkeypatch):
    state = _patch_job_store(monkeypatch, _job(external_ref="agent-zero-a2a:claim:closeout:a:test"))
    monkeypatch.setattr(
        repository_execution,
        "run_agent_job_tool",
        lambda *_args, **_kwargs: _done_tool(changed_files=()),
    )

    result = _run_closeout(state)

    assert result.status == "blocked"
    assert "without workspace changes" in (result.blocker or "")


def test_closeout_blocks_when_full_diff_is_missing(monkeypatch):
    state, _changed = _patch_closeout_baseline(monkeypatch)
    monkeypatch.setattr(
        repository_execution,
        "git_diff_full",
        lambda *_args, **_kwargs: (b"", SimpleNamespace(status="done", blocker=None)),
    )

    result = _run_closeout(state)

    assert result.status == "blocked"
    assert "diff is missing" in (result.blocker or "")


def test_closeout_blocks_when_git_diff_check_fails(monkeypatch):
    state, _changed = _patch_closeout_baseline(monkeypatch)
    monkeypatch.setattr(
        repository_execution,
        "git_diff_check",
        lambda *_args, **_kwargs: SimpleNamespace(status="failed", blocker="trailing whitespace"),
    )

    result = _run_closeout(state)

    assert result.status == "blocked"
    assert result.blocker == "trailing whitespace"


def test_closeout_blocks_on_critical_janitor_finding(monkeypatch):
    state, _changed = _patch_closeout_baseline(
        monkeypatch,
        janitor_metadata={"severityCounts": {"critical": 1}, "recommendedTestCommand": "pytest"},
    )

    result = _run_closeout(state)

    assert result.status == "blocked"
    assert "critical repository defect" in (result.blocker or "")


def test_closeout_splits_janitor_shell_combination_and_never_executes_control_token(monkeypatch):
    state, _changed = _patch_closeout_baseline(
        monkeypatch,
        janitor_metadata={
            "severityCounts": {},
            "recommendedTestCommand": "pnpm run type-check && pnpm test",
        },
    )
    observed_commands: list[str] = []
    original_tool = repository_execution.run_agent_job_tool

    def tool(job_value, action, params, root):
        if action == "test":
            observed_commands.append(str(params.get("command") or ""))
            return _done_tool(output="tests passed")
        return original_tool(job_value, action, params, root)

    monkeypatch.setattr(repository_execution, "run_agent_job_tool", tool)
    monkeypatch.setattr(
        repository_execution,
        "prepare_draft_pr",
        lambda _input: SimpleNamespace(
            allowed=True,
            blockers=(),
            summary="ready",
            head_branch="sovereign/agent-test",
            base_branch="main",
            title="Draft: test",
            body="evidence",
        ),
    )
    monkeypatch.setattr(repository_execution, "draft_pr_input_from_job", lambda job: job)
    monkeypatch.setattr(repository_execution, "mark_draft_pr_prepared", lambda *_args, **_kwargs: None)

    result = _run_closeout(state)

    assert result.status == "running"
    assert observed_commands == ["pnpm test"]
    assert all("&&" not in command for command in observed_commands)


def test_closeout_blocks_when_regression_fails(monkeypatch):
    state, _changed = _patch_closeout_baseline(monkeypatch, test_result=_failed_tool("regression red"))

    result = _run_closeout(state)

    assert result.status == "blocked"
    assert result.blocker == "regression red"


def test_closeout_blocks_when_evidence_gate_rejects(monkeypatch):
    state, _changed = _patch_closeout_baseline(
        monkeypatch,
        gate=SimpleNamespace(
            passed=False,
            can_prepare_draft_pr=False,
            reason="evidence gate red",
        ),
    )

    result = _run_closeout(state)

    assert result.status == "blocked"
    assert result.blocker == "evidence gate red"


def test_all_closeout_evidence_allows_prepare_but_never_creates_pr(monkeypatch):
    state, changed = _patch_closeout_baseline(monkeypatch)
    prepared_calls: list[dict] = []

    monkeypatch.setattr(repository_execution, "draft_pr_input_from_job", lambda job: job)
    monkeypatch.setattr(
        repository_execution,
        "prepare_draft_pr",
        lambda _input: SimpleNamespace(
            allowed=True,
            blockers=(),
            summary="ready",
            head_branch="sovereign/agent-test",
            base_branch="main",
            title="Draft: test",
            body="verified evidence",
        ),
    )

    def mark(_conn, **kwargs):
        prepared_calls.append(kwargs)
        job = state["job"]
        state["job"] = replace(job, status="validating", pr_state="ready")

    monkeypatch.setattr(repository_execution, "mark_draft_pr_prepared", mark)

    result = _run_closeout(state)

    assert prepared_calls and prepared_calls[0]["job_id"] == "agent-test"
    assert result.status == "validating"
    assert result.pr_state == "ready"
    assert result.external_ref == "agent-zero-a2a:task-original"
    assert result.changed_files == changed
    assert result.draft_pr_url is None
    assert result.pr_url is None
