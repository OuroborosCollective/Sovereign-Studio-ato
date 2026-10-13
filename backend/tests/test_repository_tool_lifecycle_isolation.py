"""Regression for repository tool receipts versus the local executor heartbeat.

These tests import the actual receipt and job-store code. Only the database
adapter is replaced; the live SQL and evidence-gate contracts remain intact.
"""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/sovereign-backend"))
sys.path.insert(0, str(ROOT))

from backend.agent_runtime import job_store, tool_events


class RecordingCursor:
    def __init__(self, statements):
        self.statements = statements

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, args):
        self.statements.append((sql, args))


@pytest.mark.parametrize("tool_status", ["done", "blocked", "error"])
def test_foreground_tool_receipt_does_not_terminate_running_executor(
    monkeypatch, tool_status
):
    """Tool failures and pending evidence cannot revoke the submit claim."""
    statements = []
    events = []
    commits = []
    conn = SimpleNamespace(
        cursor=lambda: RecordingCursor(statements),
        commit=lambda: commits.append(True),
    )
    monkeypatch.setattr(
        job_store, "append_agent_event",
        lambda _conn, _job_id, event: events.append(event),
    )
    tool_result = SimpleNamespace(
        status=tool_status,
        tool="run-test",
        output="Intermediate tool result, not the repository closeout.",
        error="Tool invocation rejected" if tool_status == "error" else None,
        blocker="Test command not allowlisted" if tool_status == "blocked" else None,
        changed_files=(),
        diff_summary=None,
        test_summary=None,
    )
    gate = tool_events.append_tool_result_to_job(
        conn, "agent-exact", tool_result, preserve_job_state=True,
    )
    assert gate is not None
    assert len(events) == 2
    assert events[0].stage == f"agent_tool_{tool_status}"
    assert len(statements) == 1
    sql, params = statements[0]
    assert "CASE WHEN input.preserve_job_state THEN sovereign_agent_jobs.status" in sql
    assert "WHEN input.preserve_job_state THEN sovereign_agent_jobs.blocker" in sql
    assert "%s::boolean AS preserve_job_state" in sql
    assert params[7] is True
    assert params[-1] == "agent-exact"
    assert commits == [True]


def test_generic_tool_receipt_keeps_existing_terminal_transition(monkeypatch):
    """The non-foreground API continues to use the established status gate."""
    statements = []
    conn = SimpleNamespace(
        cursor=lambda: RecordingCursor(statements),
        commit=lambda: None,
    )
    monkeypatch.setattr(job_store, "append_agent_event", lambda *_args: None)
    tool_events.append_tool_result_to_job(
        conn, "agent-generic",
        SimpleNamespace(status="blocked", tool="test", output="Rejected",
                        blocker="Invalid input", changed_files=()),
    )
    sql, params = statements[0]
    assert "ELSE input.status END" in sql
    assert params[7] is False
    assert params[0] == "blocked"


def test_heartbeat_still_requires_running_job_and_exact_submit_claim():
    """Liveness fencing remains strict; no relaxation of the heartbeat SQL."""
    from backend.agent_runtime import cognitive_run_store

    recorded = []

    class HeartbeatCursor(RecordingCursor):
        def fetchone(self):
            return None

    conn = SimpleNamespace(
        cursor=lambda: HeartbeatCursor(recorded),
        rollback=lambda: None,
    )
    current = cognitive_run_store.append_repository_executor_heartbeat(
        conn,
        user_id="00000000-0000-0000-0000-000000000000",
        job_id="agent-exact",
        run_id="repo-agent-exact",
        claim_ref="sovereign-local-runner:claim:submit:exact",
    )
    assert current is False
    query, args = recorded[0]
    assert "job.status = 'running' AND job.external_ref = %s" in query
    assert args[-1] == "sovereign-local-runner:claim:submit:exact"
