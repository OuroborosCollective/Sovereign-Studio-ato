from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Any

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from agent_runtime.cognitive_run_store import (
    AgentRunIterationLimit,
    AgentRunNotResumable,
    AgentRunResumeConflict,
    claim_agent_run_for_resume,
    create_agent_run,
    list_agent_runs,
    list_resumable_agent_runs,
    read_agent_events,
    record_agent_stage_event,
    record_external_action_event,
    stored_run_from_row,
    request_agent_approval,
    transition_agent_run,
)


USER_ID = "00000000-0000-0000-0000-000000000001"


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.last_sql = ""

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self.last_sql = " ".join(sql.split())
        self.connection.calls.append((self.last_sql, params))

    def fetchone(self):
        if "RETURNING run_id" in self.last_sql:
            return {"run_id": "run-test"}
        if self.connection.fetchone_rows:
            return self.connection.fetchone_rows.pop(0)
        return None

    def fetchall(self):
        return list(self.connection.fetchall_rows)


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.fetchone_rows: list[dict[str, Any]] = []
        self.fetchall_rows: list[dict[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def test_create_run_persists_received_state_event_and_digest_only_evidence() -> None:
    conn = FakeConnection()
    supplied_evidence = "private browser trace body that must not be persisted"

    state = create_agent_run(
        conn,
        user_id=USER_ID,
        run_id="run-test",
        session_key="session-test",
        mission="Implement the persistent Agents SDK run contract.",
        supplied_evidence=supplied_evidence,
        trace_id="trace-test",
        max_active_specialists=4,
        max_iterations=12,
    )

    assert state["status"] == "RECEIVED"
    assert state["source"] == "agents-sdk"
    assert state["evidenceId"].startswith("evidence-")
    assert state["reason"]
    assert state["nextAction"] == "SCOPING"
    assert conn.commits == 1
    assert conn.rollbacks == 0
    assert len(conn.calls) == 3
    assert "INSERT INTO agent_runs" in conn.calls[0][0]
    assert "INSERT INTO agent_evidence" in conn.calls[1][0]
    assert "INSERT INTO agent_events" in conn.calls[2][0]

    persisted_parameters = repr(conn.calls)
    assert supplied_evidence not in persisted_parameters
    assert hashlib.sha256(supplied_evidence.encode("utf-8")).hexdigest() in persisted_parameters


def test_create_run_preserves_a2a_context_separately_from_unique_session_identity() -> None:
    conn = FakeConnection()

    create_agent_run(
        conn,
        user_id=USER_ID,
        run_id="run-a2a-context",
        session_key="session-unique-a2a-context",
        mission="Preserve the A2A conversation context.",
        supplied_evidence="",
        trace_id="trace-a2a-context",
        a2a_context_id="shared-a2a-conversation",
    )

    persisted_parameters = repr(conn.calls[0][1])
    assert "session-unique-a2a-context" in persisted_parameters
    assert "shared-a2a-conversation" in persisted_parameters
    restored = stored_run_from_row({
        **_stored_run_row(),
        "context_snapshot": {"a2aContextId": "shared-a2a-conversation"},
    })
    assert restored.session_key == "session-resumable"
    assert restored.a2a_context_id == "shared-a2a-conversation"


def _stored_run_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "run_id": "run-resumable",
        "user_id": USER_ID,
        "session_key": "session-resumable",
        "status": "FAILED_RECOVERABLE",
        "source": "agents-sdk",
        "evidence_id": "evidence-resumable",
        "trace_id": "trace-resumable",
        "reason": "Tool was temporarily unavailable.",
        "next_action": "RETRY_FROM_PERSISTED_RUN_STATE",
        "mission_summary": "Resume the bounded work package.",
        "mission_digest": "b" * 64,
        "max_active_specialists": 4,
        "max_iterations": 12,
        "iteration_count": 3,
        "lease_active": False,
        "resume_task_id": None,
    }
    row.update(overrides)
    return row


def test_stage_event_persists_agent_activity_without_advancing_iteration_budget() -> None:
    conn = FakeConnection()
    lease_token = "bounded-resume-lease"

    state = record_agent_stage_event(
        conn,
        user_id=USER_ID,
        run_id="run-test",
        trace_id="trace-test",
        agent_id="data_storage",
        event_type="agent_started",
        status="RUNNING",
        summary="Data and Storage started bounded evidence analysis.",
        next_action="WAIT_FOR_AGENT_REPORT",
        evidence_payload={
            "agentId": "data_storage",
            "eventType": "agent_started",
            "loop": 1,
            "rawModelOutputPersisted": False,
        },
        expected_lease_token=lease_token,
    )

    assert state["agentId"] == "data_storage"
    assert state["eventType"] == "agent_started"
    assert state["status"] == "RUNNING"
    assert conn.commits == 1
    assert conn.rollbacks == 0
    assert [call[0].split()[0] for call in conn.calls] == ["INSERT", "UPDATE", "INSERT"]
    update_sql, update_params = conn.calls[1]
    assert "iteration_count" not in update_sql
    assert "lease_token = %s" in update_sql
    assert hashlib.sha256(lease_token.encode("utf-8")).hexdigest() in update_params
    assert lease_token not in repr(conn.calls)
    assert "INSERT INTO agent_events" in conn.calls[2][0]


def _external_run_row() -> dict[str, Any]:
    return {
        "run_id": "run-test",
        "status": "BLOCKED",
        "trace_id": "trace-test",
        "next_action": "FIX_CURRENT_BLOCKER",
    }


def test_external_action_event_is_owner_scoped_idempotent_and_state_neutral() -> None:
    conn = FakeConnection()
    conn.fetchone_rows = [
        _external_run_row(),
        {"evidence_id": "created"},
        {"event_id": "created"},
    ]
    raw_secret = "sk-proj-" + "x" * 30

    state = record_external_action_event(
        conn,
        user_id=USER_ID,
        run_id="run-test",
        source="github",
        external_identity="workflow:29648652001",
        event_type="workflow_completed",
        summary="Exact-head GitHub workflow completed.",
        payload={
            "headSha": "a" * 40,
            "conclusion": "success",
            "nested": {"credential": raw_secret},
        },
    )

    assert state["created"] is True
    assert state["duplicate"] is False
    assert state["runStatus"] == "BLOCKED"
    assert state["runStateChanged"] is False
    assert state["taskStateChanged"] is False
    assert state["activeBlockerChanged"] is False
    assert state["rawSecretsPersisted"] is False
    assert conn.commits == 1
    assert conn.rollbacks == 0
    assert [call[0].split()[0] for call in conn.calls] == ["SELECT", "INSERT", "INSERT"]
    assert "user_id = %s::uuid" in conn.calls[0][0]
    assert "FOR SHARE" in conn.calls[0][0]
    assert not any(call[0].startswith("UPDATE") for call in conn.calls)
    persisted = repr(conn.calls)
    assert raw_secret not in persisted
    assert "[redacted]" in persisted
    assert "ON CONFLICT (evidence_id) DO NOTHING" in conn.calls[1][0]
    assert "ON CONFLICT (event_id) DO NOTHING" in conn.calls[2][0]

    duplicate = FakeConnection()
    duplicate.fetchone_rows = [_external_run_row(), None, None]  # type: ignore[list-item]
    repeated = record_external_action_event(
        duplicate,
        user_id=USER_ID,
        run_id="run-test",
        source="github",
        external_identity="workflow:29648652001",
        event_type="workflow_completed",
        summary="Exact-head GitHub workflow completed.",
        payload={"conclusion": "success"},
    )
    assert repeated["eventId"] == state["eventId"]
    assert repeated["evidenceId"] == state["evidenceId"]
    assert repeated["created"] is False
    assert repeated["duplicate"] is True
    assert not any(call[0].startswith("UPDATE") for call in duplicate.calls)


def test_external_action_event_rejects_non_external_source_before_database_access() -> None:
    conn = FakeConnection()

    with pytest.raises(ValueError, match="not allowed for external action events"):
        record_external_action_event(
            conn,
            user_id=USER_ID,
            run_id="run-test",
            source="agents-sdk",
            external_identity="agent:self-report",
            event_type="invalid_external_event",
            summary="Agents SDK may not impersonate an external producer.",
            payload={},
        )

    assert conn.calls == []
    assert conn.commits == 0


def test_transition_persists_evidence_before_state_and_event() -> None:
    conn = FakeConnection()

    state = transition_agent_run(
        conn,
        user_id=USER_ID,
        run_id="run-test",
        status="VERIFYING",
        source="github",
        trace_id="trace-test",
        reason="Named GitHub checks are being verified.",
        next_action="WAIT_FOR_CHECKS",
        evidence_kind="workflow_checks",
        evidence_summary="GitHub checks were requested for the exact head SHA.",
        evidence_payload={"headSha": "a" * 40, "pending": ["Agent Runtime Tests"]},
        agent_id="validation_evidence",
    )

    assert state["status"] == "VERIFYING"
    assert state["source"] == "github"
    assert state["evidenceId"].startswith("evidence-")
    assert conn.commits == 1
    assert conn.rollbacks == 0
    assert [call[0].split()[0] for call in conn.calls] == ["INSERT", "UPDATE", "INSERT"]
    assert "RETURNING run_id" in conn.calls[1][0]


def test_lease_owned_transition_updates_recovery_task_and_hides_raw_token() -> None:
    conn = FakeConnection()
    raw_lease_token = "resume-lease-token"

    state = transition_agent_run(
        conn,
        user_id=USER_ID,
        run_id="run-test",
        status="BLOCKED",
        source="agents-sdk",
        trace_id="trace-test",
        reason="More runtime evidence is required.",
        next_action="PROVIDE_RUNTIME_EVIDENCE",
        evidence_kind="judge_verdict",
        evidence_summary="The resumed run remained blocked.",
        evidence_payload={"ok": False},
        task_id="task-resume-test",
        expected_lease_token=raw_lease_token,
    )

    assert state["status"] == "BLOCKED"
    assert conn.commits == 1
    assert [call[0].split()[0] for call in conn.calls] == [
        "INSERT",
        "UPDATE",
        "UPDATE",
        "UPDATE",
        "INSERT",
    ]
    update_sql, update_params = conn.calls[1]
    assert "lease_token = %s" in update_sql
    assert "lease_token = NULL" in update_sql
    assert hashlib.sha256(raw_lease_token.encode("utf-8")).hexdigest() in update_params
    assert raw_lease_token not in repr(conn.calls)
    assert "UPDATE agent_tasks" in conn.calls[2][0]
    assert "UPDATE agent_failures" in conn.calls[3][0]
    assert "recoverable = TRUE" in conn.calls[3][0]
    assert "resolved_at IS NULL" in conn.calls[3][0]
    assert conn.calls[3][1] == ("run-test",)


def test_failed_recovery_transition_keeps_prior_failure_unresolved() -> None:
    conn = FakeConnection()

    transition_agent_run(
        conn,
        user_id=USER_ID,
        run_id="run-test",
        status="FAILED_RECOVERABLE",
        source="agents-sdk",
        trace_id="trace-test",
        reason="The retry failed again.",
        next_action="RETRY_WITH_NEW_EVIDENCE",
        evidence_kind="runtime_failure",
        evidence_summary="The recoverable failure remains active.",
        evidence_payload={"retryable": True},
    )

    assert [call[0].split()[0] for call in conn.calls] == ["INSERT", "UPDATE", "INSERT"]
    assert not any("UPDATE agent_failures" in sql for sql, _ in conn.calls)


def test_owner_approval_state_resolves_recoverable_failures_without_deleting_history() -> None:
    conn = FakeConnection()

    state = request_agent_approval(
        conn,
        user_id=USER_ID,
        run_id="run-test",
        trace_id="trace-test",
        kind="draft_pr_readiness",
        requested_by_agent="judge",
        reason="Owner approval is required after validated recovery.",
        next_action="OWNER_APPROVAL_REQUIRED_FOR_DRAFT_PR",
        evidence_payload={"judgeReady": True},
    )

    assert state["status"] == "WAITING_FOR_OWNER"
    assert [call[0].split()[0] for call in conn.calls] == [
        "INSERT",
        "UPDATE",
        "UPDATE",
        "INSERT",
        "INSERT",
    ]
    resolution_sql, resolution_params = conn.calls[2]
    assert "UPDATE agent_failures" in resolution_sql
    assert "resolved_at = COALESCE(resolved_at, NOW())" in resolution_sql
    assert "DELETE" not in resolution_sql
    assert resolution_params == ("run-test",)


def test_claim_resume_is_atomic_and_reconstructs_one_bounded_task() -> None:
    conn = FakeConnection()
    conn.fetchone_rows = [_stored_run_row()]
    supplied_evidence = "fresh runtime evidence that must remain request-local"

    claim = claim_agent_run_for_resume(
        conn,
        user_id=USER_ID,
        run_id="run-resumable",
        supplied_evidence=supplied_evidence,
        trace_id="trace-resume",
        lease_seconds=120,
    )

    assert claim.run.status == "FAILED_RECOVERABLE"
    assert claim.work_package == "RETRY_FROM_PERSISTED_RUN_STATE"
    assert claim.task_id.startswith("task-resume-")
    assert claim.evidence_id.startswith("evidence-")
    assert claim.lease_seconds == 120
    assert conn.commits == 1
    assert conn.rollbacks == 0
    assert [call[0].split()[0] for call in conn.calls] == ["SELECT", "INSERT", "INSERT", "UPDATE", "INSERT"]
    assert "INSERT INTO agent_tasks" in conn.calls[1][0]
    assert "INSERT INTO agent_evidence" in conn.calls[2][0]
    assert "FOR UPDATE" in conn.calls[0][0]
    assert "lease_expires_at" in conn.calls[3][0]

    persisted_parameters = repr(conn.calls)
    assert supplied_evidence not in persisted_parameters
    assert hashlib.sha256(supplied_evidence.encode("utf-8")).hexdigest() in persisted_parameters
    assert claim.lease_token not in persisted_parameters
    assert hashlib.sha256(claim.lease_token.encode("utf-8")).hexdigest() in persisted_parameters


def test_claim_resume_blocks_active_lease_terminal_run_and_exhausted_budget() -> None:
    active = FakeConnection()
    active.fetchone_rows = [_stored_run_row(status="RUNNING", lease_active=True, resume_task_id="task-active")]
    with pytest.raises(AgentRunResumeConflict):
        claim_agent_run_for_resume(
            active,
            user_id=USER_ID,
            run_id="run-resumable",
            supplied_evidence="",
            trace_id="trace-resume",
        )
    assert active.rollbacks == 1

    terminal = FakeConnection()
    terminal.fetchone_rows = [_stored_run_row(status="COMPLETED")]
    with pytest.raises(AgentRunNotResumable):
        claim_agent_run_for_resume(
            terminal,
            user_id=USER_ID,
            run_id="run-resumable",
            supplied_evidence="",
            trace_id="trace-resume",
        )

    exhausted = FakeConnection()
    exhausted.fetchone_rows = [_stored_run_row(iteration_count=12, max_iterations=12)]
    with pytest.raises(AgentRunIterationLimit):
        claim_agent_run_for_resume(
            exhausted,
            user_id=USER_ID,
            run_id="run-resumable",
            supplied_evidence="",
            trace_id="trace-resume",
        )


def test_expired_resume_task_is_marked_recoverable_before_new_claim() -> None:
    conn = FakeConnection()
    conn.fetchone_rows = [_stored_run_row(
        status="RUNNING",
        lease_active=False,
        resume_task_id="task-expired",
    )]

    claim_agent_run_for_resume(
        conn,
        user_id=USER_ID,
        run_id="run-resumable",
        supplied_evidence="new evidence",
        trace_id="trace-resume",
    )

    assert "UPDATE agent_tasks" in conn.calls[1][0]
    assert "FAILED_RECOVERABLE" in conn.calls[1][0]
    assert conn.calls[1][1][1] == "task-expired"
    assert "INSERT INTO agent_tasks" in conn.calls[2][0]


def test_invalid_status_and_source_fail_closed() -> None:
    conn = FakeConnection()

    with pytest.raises(ValueError, match="unsupported Agents SDK run status"):
        transition_agent_run(
            conn,
            user_id=USER_ID,
            run_id="run-test",
            status="FAKE_PROGRESS_75_PERCENT",
            source="agents-sdk",
            trace_id="trace-test",
            reason="Invalid status must be rejected.",
            next_action="BLOCK",
            evidence_kind="contract",
            evidence_summary="Invalid state contract.",
            evidence_payload={},
        )

    with pytest.raises(ValueError, match="unsupported runtime evidence source"):
        transition_agent_run(
            conn,
            user_id=USER_ID,
            run_id="run-test",
            status="BLOCKED",
            source="ui",
            trace_id="trace-test",
            reason="UI cannot create runtime truth.",
            next_action="COLLECT_RUNTIME_EVIDENCE",
            evidence_kind="contract",
            evidence_summary="UI source was rejected.",
            evidence_payload={},
        )

    assert conn.calls == []
    assert conn.commits == 0


def test_a2a_run_and_event_queries_remain_owner_scoped() -> None:
    conn = FakeConnection()
    conn.fetchall_rows = [_stored_run_row(context_snapshot={"a2aContextId": "context-a2a"})]

    runs = list_agent_runs(conn, user_id=USER_ID, limit=25)
    assert len(runs) == 1
    assert runs[0].a2a_context_id == "context-a2a"
    assert "WHERE user_id = %s::uuid" in conn.calls[0][0]

    conn.calls.clear()
    conn.fetchall_rows = [{
        "event_id": "event-a2a",
        "run_id": "run-resumable",
        "task_id": None,
        "agent_id": "judge",
        "type": "run_state_changed",
        "status": "COMPLETED",
        "source": "agents-sdk",
        "summary": "Persisted completion.",
        "evidence_id": "evidence-a2a",
        "trace_id": "trace-a2a",
        "created_at": "2026-07-17T18:00:00Z",
        "next_action": "NO_FURTHER_ACTION_REQUIRED",
    }]
    events = read_agent_events(conn, user_id=USER_ID, run_id="run-resumable")
    assert events[0]["event_id"] == "event-a2a"
    sql, params = conn.calls[0]
    assert "JOIN agent_runs AS run" in sql
    assert "run.user_id = %s::uuid" in sql
    assert params[0] == USER_ID


def test_resumable_query_excludes_terminal_and_draft_ready_runs() -> None:
    conn = FakeConnection()
    conn.fetchall_rows = [_stored_run_row()]

    runs = list_resumable_agent_runs(conn, user_id=USER_ID)

    assert len(runs) == 1
    assert runs[0].status == "FAILED_RECOVERABLE"
    sql, params = conn.calls[0]
    assert "status <> ALL" in sql
    assert "lease_expires_at <= NOW()" in sql
    assert set(params[1]) == {
        "COMPLETED",
        "DRAFT_PR_CREATED",
        "FAILED_FINAL",
        "READY_FOR_DRAFT_PR",
        "WAITING_FOR_OWNER",
    }


def test_migration_creates_all_required_runtime_truth_tables() -> None:
    migration = (ROOT / "scripts/sovereign-backend/migrations/018_agents_sdk_runtime_state.sql").read_text("utf-8")

    for table in (
        "agent_runs",
        "agent_tasks",
        "agent_handoffs",
        "agent_events",
        "agent_tool_calls",
        "agent_evidence",
        "agent_artifacts",
        "agent_approvals",
        "agent_failures",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration

    for status in (
        "RECEIVED",
        "WAITING_FOR_TOOL",
        "WAITING_FOR_OWNER",
        "FAILED_RECOVERABLE",
        "READY_FOR_DRAFT_PR",
        "DRAFT_PR_CREATED",
        "COMPLETED",
    ):
        assert f"'{status}'" in migration

    assert "arguments_digest CHAR(64) NOT NULL" in migration
    assert "result_digest CHAR(64)" in migration
    assert "raw_arguments" not in migration
    assert "evidence_id <> '' AND reason <> '' AND next_action <> ''" in migration

    resume_migration = (ROOT / "scripts/sovereign-backend/migrations/019_agents_sdk_resume_lease.sql").read_text("utf-8")
    assert "ADD COLUMN IF NOT EXISTS lease_token CHAR(64)" in resume_migration
    assert "ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ" in resume_migration
    assert "ADD COLUMN IF NOT EXISTS resume_task_id TEXT" in resume_migration
    assert "lease_token ~ '^[0-9a-f]{64}$'" in resume_migration
    assert "raw token is process-local only" in resume_migration


def test_canonical_and_deployment_agents_sdk_runtime_are_identical() -> None:
    for relative in (
        "cognitive_run_store.py",
        "cognitive_swarm_routes.py",
        "cognitive_swarm_agents.py",
    ):
        canonical = (ROOT / "backend/agent_runtime" / relative).read_text("utf-8")
        deployed = (ROOT / "scripts/sovereign-backend/agent_runtime" / relative).read_text("utf-8")
        assert canonical == deployed, relative
