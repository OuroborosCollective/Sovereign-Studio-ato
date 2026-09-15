from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
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
    list_reconcilable_repository_jobs,
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
        job = state["job"]
        event_row = {
            "stage": event.stage,
            "level": event.level,
            "message": event.message,
            "at": event.at,
        }
        state["job"] = replace(job, events=job.events + (event_row,))

    monkeypatch.setattr(repository_execution, "read_agent_job", read_agent_job)
    monkeypatch.setattr(repository_execution, "compare_and_swap_agent_job_external_ref", cas)
    monkeypatch.setattr(repository_execution, "update_agent_job_state", update)
    monkeypatch.setattr(repository_execution, "append_agent_event", append)
    return state


def test_original_task_lost_does_not_resubmit_and_transient_404_can_recover(monkeypatch):
    state = _patch_job_store(monkeypatch, _job())
    monkeypatch.setattr(
        repository_execution,
        "run_agent_job_tool",
        lambda *_args, **_kwargs: _done_tool(changed_files=()),
    )

    class Client:
        submit_count = 0
        reads = 0

        def get_task(self, task_id):
            assert task_id == "task-original"
            self.reads += 1
            if self.reads == 1:
                raise AgentZeroA2ATaskLost(
                    "AGENT_ZERO_A2A_TASK_LOST",
                    "RECONCILE_STABLE_WORKSPACE_WITHOUT_RESUBMIT",
                    http_status=404,
                )
            return AgentZeroA2ATask(task_id=task_id, state="working")

        def submit_repository_task(self, **_kwargs):
            self.submit_count += 1
            raise AssertionError("lost-task readback must never trigger an automatic resubmit")

    client = Client()
    first = repository_execution.reconcile_repository_execution(
        object(), user_id="owner-test", job_id="agent-test",
        a2a_client_factory=lambda: client,
    )
    assert first is not None
    assert first.status == "running"
    assert first.external_ref == "agent-zero-a2a:task-original"
    assert client.submit_count == 0
    assert any(event.stage == "agent_zero_a2a_task_readback_lost" for event in state["events"])

    second = repository_execution.reconcile_repository_execution(
        object(), user_id="owner-test", job_id="agent-test",
        a2a_client_factory=lambda: client,
    )
    assert second is not None
    assert second.status == "running"
    assert second.external_ref == "agent-zero-a2a:task-original"
    assert client.submit_count == 0
    assert any(event.stage == "agent_zero_a2a_task_readback_restored" for event in state["events"])
    assert repository_execution._lost_epoch_is_active(second) is False


def test_restored_task_makes_a_later_loss_start_a_fresh_epoch(monkeypatch):
    state = _patch_job_store(monkeypatch, _job())
    old_at = int((repository_execution.time.time() - 4000.0) * 1000)
    state["job"] = replace(state["job"], events=(
        {"stage": "agent_zero_a2a_task_readback_lost", "level": "warning", "message": "old", "at": old_at},
        {"stage": "agent_zero_a2a_task_readback_restored", "level": "info", "message": "restored", "at": old_at + 1000},
    ))
    monkeypatch.setattr(repository_execution, "run_agent_job_tool", lambda *_a, **_k: _done_tool(changed_files=()))

    class Client:
        def get_task(self, task_id):
            raise AgentZeroA2ATaskLost("AGENT_ZERO_A2A_TASK_LOST", "RECONCILE_STABLE_WORKSPACE_WITHOUT_RESUBMIT", http_status=404)
        def submit_repository_task(self, **_kwargs):
            raise AssertionError("fresh lost epoch must never resubmit")

    result = repository_execution.reconcile_repository_execution(
        object(), user_id="owner-test", job_id="agent-test", a2a_client_factory=Client,
    )
    assert result is not None
    assert result.status == "running"
    assert repository_execution._lost_epoch_is_active(result) is True
    lost_events = [event for event in state["events"] if event.stage == "agent_zero_a2a_task_readback_lost"]
    assert len(lost_events) == 1
    assert lost_events[0].at > old_at + 1000


def test_original_task_lost_closes_stable_workspace_effect_without_resubmit(monkeypatch):
    state = _patch_job_store(monkeypatch, _job())

    class Client:
        submit_count = 0

        def get_task(self, task_id):
            assert task_id == "task-original"
            raise AgentZeroA2ATaskLost(
                "AGENT_ZERO_A2A_TASK_LOST",
                "RECONCILE_STABLE_WORKSPACE_WITHOUT_RESUBMIT",
                http_status=404,
            )

        def submit_repository_task(self, **_kwargs):
            self.submit_count += 1
            raise AssertionError("workspace recovery must not submit a second Agent Zero task")

    client = Client()
    monkeypatch.setattr(
        repository_execution,
        "run_agent_job_tool",
        lambda *_args, **_kwargs: _done_tool(changed_files=("README.md",)),
    )
    monkeypatch.setattr(
        repository_execution,
        "git_diff_full",
        lambda *_args, **_kwargs: (
            b"diff --git a/README.md b/README.md\n+stable marker\n",
            SimpleNamespace(status="done", blocker=None),
        ),
    )
    monkeypatch.setattr(repository_execution, "_lost_workspace_stable_seconds", lambda: 0.0)
    closeouts: list[tuple[str, str]] = []

    def closeout(_conn, *, job, claim_ref, bound_ref, workspace_root):
        closeouts.append((claim_ref, bound_ref))
        state["job"] = replace(
            state["job"],
            status="validating",
            external_ref=bound_ref,
            changed_files=("README.md",),
            pr_state="ready",
        )
        return state["job"]

    monkeypatch.setattr(repository_execution, "_closeout_repository_job", closeout)

    # First miss records task-store loss; second observes the diff; third confirms the
    # same diff is stable and enters closeout. None may call message/send.
    for _ in range(3):
        result = repository_execution.reconcile_repository_execution(
            object(), user_id="owner-test", job_id="agent-test",
            a2a_client_factory=lambda: client,
        )

    assert result is not None
    assert result.pr_state == "ready"
    assert result.changed_files == ("README.md",)
    assert result.external_ref == "agent-zero-a2a:task-original"
    assert client.submit_count == 0
    assert len(closeouts) == 1
    assert closeouts[0][0].startswith("agent-zero-a2a:claim:closeout-lost:")
    assert closeouts[0][1] == "agent-zero-a2a:task-original"
    assert any(event.stage == "agent_zero_a2a_task_lost_workspace_observed" for event in state["events"])
    assert any(event.stage == "agent_zero_a2a_task_lost_workspace_closeout" for event in state["events"])


def test_historical_retry_task_lost_blocks_without_another_resubmit(monkeypatch):
    state = _patch_job_store(monkeypatch, _job(external_ref="agent-zero-a2a:retry:task-retry"))

    class Client:
        submit_count = 0

        def get_task(self, task_id):
            assert task_id == "task-retry"
            raise AgentZeroA2ATaskLost(
                "AGENT_ZERO_A2A_TASK_LOST",
                "RECONCILE_STABLE_WORKSPACE_WITHOUT_RESUBMIT",
                http_status=404,
            )

        def submit_repository_task(self, **_kwargs):
            self.submit_count += 1
            raise AssertionError("historical retry loss must fail closed without another submit")

    client = Client()
    terminal = repository_execution.reconcile_repository_execution(
        object(), user_id="owner-test", job_id="agent-test",
        a2a_client_factory=lambda: client,
    )
    assert terminal is not None
    assert terminal.status == "blocked"
    assert "no further resubmit" in (terminal.blocker or "")
    assert client.submit_count == 0

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

def test_active_task_stalls_fail_closed_after_bounded_window(monkeypatch):
    stale = replace(
        _job(),
        updated_at=datetime.now(timezone.utc) - timedelta(seconds=601),
    )
    state = _patch_job_store(monkeypatch, stale)
    monkeypatch.setenv("SOVEREIGN_REPOSITORY_STALL_SECONDS", "300")

    class Client:
        def get_task(self, task_id):
            assert task_id == "task-original"
            return AgentZeroA2ATask(task_id=task_id, state="working")

    result = repository_execution.reconcile_repository_execution(
        object(),
        user_id="owner-test",
        job_id="agent-test",
        a2a_client_factory=Client,
    )

    assert result is not None
    assert result.status == "blocked"
    assert "AGENT_ZERO_A2A_STALLED" in (result.blocker or "")
    assert any(event.stage == "agent_zero_a2a_task_stalled" for event in state["events"])


def test_fresh_active_task_remains_running(monkeypatch):
    fresh = replace(_job(), updated_at=datetime.now(timezone.utc))
    _patch_job_store(monkeypatch, fresh)
    monkeypatch.setenv("SOVEREIGN_REPOSITORY_STALL_SECONDS", "300")

    class Client:
        def get_task(self, task_id):
            return AgentZeroA2ATask(task_id=task_id, state="working")

    result = repository_execution.reconcile_repository_execution(
        object(),
        user_id="owner-test",
        job_id="agent-test",
        a2a_client_factory=Client,
    )

    assert result is not None
    assert result.status == "running"


def test_server_reconciler_processes_bound_job_without_client_polling(monkeypatch):
    candidate = _job()
    connections = []
    observed = []

    class Conn:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    def factory():
        conn = Conn()
        connections.append(conn)
        return conn

    monkeypatch.setattr(
        repository_execution,
        "list_reconcilable_repository_jobs",
        lambda _conn, *, limit=50: (candidate,),
    )

    def reconcile(_conn, *, user_id, job_id, workspace_root=None, a2a_client_factory=None):
        observed.append((user_id, job_id, workspace_root))
        return candidate

    monkeypatch.setattr(repository_execution, "reconcile_repository_execution", reconcile)

    summary = repository_execution.reconcile_repository_jobs_once(
        get_connection=factory,
        workspace_root=Path("/tmp/server-owned-reconcile"),
    )

    assert summary == {
        "scanned": 1,
        "reconciled": 1,
        "transientFailures": 0,
        "unexpectedFailures": 0,
    }
    assert observed == [("owner-test", "agent-test", Path("/tmp/server-owned-reconcile"))]
    assert len(connections) == 2
    assert all(conn.closed for conn in connections)


class _PyformatCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        rendered = sql % tuple(params)
        assert "LIKE 'agent-zero-a2a:%'" in rendered
        assert "NOT LIKE 'agent-zero-a2a:claim:%'" in rendered

    def fetchall(self):
        return []


class _PyformatConnection:
    def cursor(self):
        return _PyformatCursor()


def test_reconcilable_job_query_escapes_like_wildcards_for_pyformat_driver():
    assert list_reconcilable_repository_jobs(_PyformatConnection()) == ()
