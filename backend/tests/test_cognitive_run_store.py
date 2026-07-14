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
    create_agent_run,
    list_resumable_agent_runs,
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


def test_resumable_query_excludes_only_terminal_runs() -> None:
    conn = FakeConnection()
    conn.fetchall_rows = [{
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
    }]

    runs = list_resumable_agent_runs(conn, user_id=USER_ID)

    assert len(runs) == 1
    assert runs[0].status == "FAILED_RECOVERABLE"
    sql, params = conn.calls[0]
    assert "status <> ALL" in sql
    assert set(params[1]) == {"COMPLETED", "DRAFT_PR_CREATED", "FAILED_FINAL"}


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


def test_canonical_and_deployment_agents_sdk_runtime_are_identical() -> None:
    for relative in (
        "cognitive_run_store.py",
        "cognitive_swarm_routes.py",
        "cognitive_swarm_agents.py",
    ):
        canonical = (ROOT / "backend/agent_runtime" / relative).read_text("utf-8")
        deployed = (ROOT / "scripts/sovereign-backend/agent_runtime" / relative).read_text("utf-8")
        assert canonical == deployed, relative
