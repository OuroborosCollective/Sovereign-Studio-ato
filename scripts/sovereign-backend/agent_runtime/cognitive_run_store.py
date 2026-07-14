"""Persistent PostgreSQL truth for Sovereign OpenAI Agents SDK runs.

The store accepts a DB-API compatible connection. It never persists raw tool
arguments, credentials or full evidence text. Callers provide bounded summaries;
large or sensitive inputs are represented only by SHA-256 digests.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Final, Mapping, Sequence
import uuid

from .contracts import sanitize_agent_text


RUN_STATUSES: Final[frozenset[str]] = frozenset({
    "RECEIVED",
    "SCOPING",
    "PLANNED",
    "QUEUED",
    "ASSIGNED",
    "RUNNING",
    "WAITING_FOR_TOOL",
    "WAITING_FOR_AGENT",
    "WAITING_FOR_OWNER",
    "VERIFYING",
    "BLOCKED",
    "FAILED_RECOVERABLE",
    "FAILED_FINAL",
    "READY_FOR_DRAFT_PR",
    "DRAFT_PR_CREATED",
    "COMPLETED",
})

EVIDENCE_SOURCES: Final[frozenset[str]] = frozenset({
    "agents-sdk",
    "mcp",
    "broker",
    "github",
    "browserless",
    "tika",
    "gotenberg",
    "database",
})

TERMINAL_RUN_STATUSES: Final[frozenset[str]] = frozenset({
    "FAILED_FINAL",
    "DRAFT_PR_CREATED",
    "COMPLETED",
})

NON_RESUMABLE_RUN_STATUSES: Final[frozenset[str]] = frozenset({
    *TERMINAL_RUN_STATUSES,
    "READY_FOR_DRAFT_PR",
})

_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")


@dataclass(frozen=True, slots=True)
class StoredAgentRun:
    run_id: str
    user_id: str
    session_key: str
    status: str
    source: str
    evidence_id: str
    trace_id: str
    reason: str
    next_action: str
    mission_summary: str
    mission_digest: str
    max_active_specialists: int
    max_iterations: int
    iteration_count: int
    lease_active: bool
    resume_task_id: str | None


@dataclass(frozen=True, slots=True)
class AgentRunResumeClaim:
    run: StoredAgentRun
    task_id: str
    work_package: str
    evidence_id: str
    trace_id: str
    lease_token: str
    lease_seconds: int


class AgentRunResumeConflict(RuntimeError):
    """Another live worker currently owns the resume lease."""


class AgentRunNotResumable(ValueError):
    """The persisted run is terminal or has no valid next action."""


class AgentRunIterationLimit(RuntimeError):
    """The persisted run exhausted its bounded iteration budget."""

    def __init__(self, message: str, resume_task_id: str | None = None) -> None:
        super().__init__(message)
        self.resume_task_id = resume_task_id


def _bounded(value: object, limit: int) -> str:
    return sanitize_agent_text(str(value or ""), limit).strip()


def _digest_text(value: object) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _validated_id(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not _ID_PATTERN.fullmatch(normalized):
        raise ValueError(f"{label} is invalid")
    return normalized


def _validated_status(status: str) -> str:
    normalized = str(status or "").strip().upper()
    if normalized not in RUN_STATUSES:
        raise ValueError("unsupported Agents SDK run status")
    return normalized


def _validated_source(source: str) -> str:
    normalized = str(source or "").strip().lower()
    if normalized not in EVIDENCE_SOURCES:
        raise ValueError("unsupported runtime evidence source")
    return normalized


def _validated_limits(max_active_specialists: int, max_iterations: int) -> tuple[int, int]:
    active = int(max_active_specialists)
    iterations = int(max_iterations)
    if not 1 <= active <= 8:
        raise ValueError("max_active_specialists must be between 1 and 8")
    if not 1 <= iterations <= 100:
        raise ValueError("max_iterations must be between 1 and 100")
    return active, iterations


def _event_payload(
    *,
    event_id: str,
    run_id: str,
    task_id: str | None,
    agent_id: str,
    event_type: str,
    status: str,
    source: str,
    summary: str,
    evidence_id: str,
    trace_id: str,
    next_action: str,
) -> tuple[object, ...]:
    return (
        event_id,
        run_id,
        task_id,
        _bounded(agent_id, 160),
        _bounded(event_type, 120),
        status,
        source,
        _bounded(summary, 2000),
        evidence_id,
        trace_id,
        _bounded(next_action, 1000),
    )


def create_agent_run(
    conn: Any,
    *,
    user_id: str,
    run_id: str,
    session_key: str,
    mission: str,
    supplied_evidence: str,
    trace_id: str,
    max_active_specialists: int = 4,
    max_iterations: int = 12,
    job_id: str | None = None,
) -> dict[str, str]:
    """Create one RECEIVED run plus its input evidence and event atomically."""

    normalized_run_id = _validated_id(run_id, "run_id")
    normalized_session_key = _validated_id(session_key, "session_key")
    normalized_trace_id = _validated_id(trace_id, "trace_id")
    active_limit, iteration_limit = _validated_limits(max_active_specialists, max_iterations)
    mission_summary = _bounded(mission, 2000)
    if not mission_summary:
        raise ValueError("mission is required")
    mission_digest = _digest_text(mission)
    supplied_evidence_digest = _digest_text(supplied_evidence)
    evidence_id = _new_id("evidence")
    event_id = _new_id("event")
    reason = "Authenticated user mission was accepted and persisted before model execution."
    next_action = "SCOPING"
    context_snapshot = {
        "missionDigest": mission_digest,
        "suppliedEvidenceDigest": supplied_evidence_digest,
        "rawSecretsPersisted": False,
    }

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_runs (
                    run_id, user_id, job_id, session_key, mission_summary, mission_digest,
                    status, source, evidence_id, trace_id, reason, next_action,
                    context_snapshot, max_active_specialists, max_iterations
                ) VALUES (
                    %s, %s::uuid, %s, %s, %s, %s,
                    'RECEIVED', 'agents-sdk', %s, %s, %s, %s,
                    %s::jsonb, %s, %s
                )
                """,
                (
                    normalized_run_id,
                    str(user_id),
                    job_id,
                    normalized_session_key,
                    mission_summary,
                    mission_digest,
                    evidence_id,
                    normalized_trace_id,
                    reason,
                    next_action,
                    _json(context_snapshot),
                    active_limit,
                    iteration_limit,
                ),
            )
            cur.execute(
                """
                INSERT INTO agent_evidence (
                    evidence_id, run_id, task_id, agent_id, source, kind,
                    summary, sha256, payload
                ) VALUES (%s, %s, NULL, 'orchestrator', 'agents-sdk', 'input', %s, %s, %s::jsonb)
                """,
                (
                    evidence_id,
                    normalized_run_id,
                    "Mission and supplied evidence digests persisted before model execution.",
                    _digest_text(_json(context_snapshot)),
                    _json(context_snapshot),
                ),
            )
            cur.execute(
                """
                INSERT INTO agent_events (
                    event_id, run_id, task_id, agent_id, type, status, source,
                    summary, evidence_id, trace_id, next_action
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                _event_payload(
                    event_id=event_id,
                    run_id=normalized_run_id,
                    task_id=None,
                    agent_id="orchestrator",
                    event_type="run_received",
                    status="RECEIVED",
                    source="agents-sdk",
                    summary=reason,
                    evidence_id=evidence_id,
                    trace_id=normalized_trace_id,
                    next_action=next_action,
                ),
            )
        conn.commit()
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        raise

    return {
        "runId": normalized_run_id,
        "sessionKey": normalized_session_key,
        "traceId": normalized_trace_id,
        "evidenceId": evidence_id,
        "status": "RECEIVED",
        "source": "agents-sdk",
        "reason": reason,
        "nextAction": next_action,
    }


def transition_agent_run(
    conn: Any,
    *,
    user_id: str,
    run_id: str,
    status: str,
    source: str,
    trace_id: str,
    reason: str,
    next_action: str,
    evidence_kind: str,
    evidence_summary: str,
    evidence_payload: Mapping[str, object],
    agent_id: str = "orchestrator",
    task_id: str | None = None,
    expected_lease_token: str | None = None,
) -> dict[str, str]:
    """Persist evidence, state and event in one transaction."""

    normalized_run_id = _validated_id(run_id, "run_id")
    normalized_status = _validated_status(status)
    normalized_source = _validated_source(source)
    normalized_trace_id = _validated_id(trace_id, "trace_id")
    normalized_reason = _bounded(reason, 2000)
    normalized_next_action = _bounded(next_action, 1000)
    normalized_summary = _bounded(evidence_summary, 2000)
    normalized_kind = _bounded(evidence_kind, 120)
    if not all((normalized_reason, normalized_next_action, normalized_summary, normalized_kind)):
        raise ValueError("state transition requires reason, next_action and evidence")

    safe_payload = dict(evidence_payload)
    payload_json = _json(safe_payload)
    evidence_id = _new_id("evidence")
    event_id = _new_id("event")
    if expected_lease_token:
        lease_clause = "AND lease_token = %s AND lease_expires_at > NOW()"
        lease_params: tuple[object, ...] = (_digest_text(expected_lease_token),)
    else:
        lease_clause = "AND (lease_token IS NULL OR lease_expires_at <= NOW())"
        lease_params = ()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_evidence (
                    evidence_id, run_id, task_id, agent_id, source, kind,
                    summary, sha256, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    evidence_id,
                    normalized_run_id,
                    task_id,
                    _bounded(agent_id, 160),
                    normalized_source,
                    normalized_kind,
                    normalized_summary,
                    _digest_text(payload_json),
                    payload_json,
                ),
            )
            cur.execute(
                f"""
                UPDATE agent_runs
                SET status = %s,
                    source = %s,
                    evidence_id = %s,
                    trace_id = %s,
                    reason = %s,
                    next_action = %s,
                    iteration_count = LEAST(iteration_count + 1, max_iterations),
                    resumed_at = CASE WHEN %s IN ('RUNNING', 'VERIFYING') THEN NOW() ELSE resumed_at END,
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    resume_task_id = NULL
                WHERE run_id = %s AND user_id = %s::uuid
                  {lease_clause}
                RETURNING run_id
                """,
                (
                    normalized_status,
                    normalized_source,
                    evidence_id,
                    normalized_trace_id,
                    normalized_reason,
                    normalized_next_action,
                    normalized_status,
                    normalized_run_id,
                    str(user_id),
                    *lease_params,
                ),
            )
            if not cur.fetchone():
                raise LookupError("agent run not found or active resume lease is not held")
            if task_id:
                cur.execute(
                    """
                    UPDATE agent_tasks
                    SET status = %s,
                        source = %s,
                        evidence_id = %s,
                        reason = %s,
                        next_action = %s,
                        completed_at = CASE
                            WHEN %s IN ('COMPLETED', 'FAILED_FINAL', 'DRAFT_PR_CREATED') THEN NOW()
                            ELSE completed_at
                        END
                    WHERE task_id = %s AND run_id = %s
                    """,
                    (
                        normalized_status,
                        normalized_source,
                        evidence_id,
                        normalized_reason,
                        normalized_next_action,
                        normalized_status,
                        task_id,
                        normalized_run_id,
                    ),
                )
            cur.execute(
                """
                INSERT INTO agent_events (
                    event_id, run_id, task_id, agent_id, type, status, source,
                    summary, evidence_id, trace_id, next_action
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                _event_payload(
                    event_id=event_id,
                    run_id=normalized_run_id,
                    task_id=task_id,
                    agent_id=agent_id,
                    event_type="run_state_changed",
                    status=normalized_status,
                    source=normalized_source,
                    summary=normalized_summary,
                    evidence_id=evidence_id,
                    trace_id=normalized_trace_id,
                    next_action=normalized_next_action,
                ),
            )
        conn.commit()
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        raise

    return {
        "runId": normalized_run_id,
        "status": normalized_status,
        "source": normalized_source,
        "evidenceId": evidence_id,
        "traceId": normalized_trace_id,
        "reason": normalized_reason,
        "nextAction": normalized_next_action,
    }


def claim_agent_run_for_resume(
    conn: Any,
    *,
    user_id: str,
    run_id: str,
    supplied_evidence: str,
    trace_id: str,
    lease_seconds: int = 900,
) -> AgentRunResumeClaim:
    """Atomically claim one resumable run and reconstruct its bounded next task."""

    normalized_run_id = _validated_id(run_id, "run_id")
    normalized_trace_id = _validated_id(trace_id, "trace_id")
    bounded_lease_seconds = max(30, min(int(lease_seconds), 3600))
    raw_lease_token = uuid.uuid4().hex
    lease_digest = _digest_text(raw_lease_token)
    evidence_id = _new_id("evidence")
    task_id = _new_id("task-resume")
    event_id = _new_id("event")

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *,
                       (lease_token IS NOT NULL AND lease_expires_at > NOW()) AS lease_active
                FROM agent_runs
                WHERE run_id = %s AND user_id = %s::uuid
                LIMIT 1
                FOR UPDATE
                """,
                (normalized_run_id, str(user_id)),
            )
            row = cur.fetchone()
            if not row:
                raise LookupError("agent run not found for authenticated user")
            run = stored_run_from_row(row)
            if run.status in NON_RESUMABLE_RUN_STATUSES:
                raise AgentRunNotResumable("agent run is not eligible for resume execution")
            if run.lease_active:
                raise AgentRunResumeConflict("agent run already has an active resume lease")
            if run.iteration_count >= run.max_iterations:
                raise AgentRunIterationLimit(
                    "agent run iteration limit is exhausted",
                    run.resume_task_id,
                )
            work_package = _bounded(run.next_action, 1000)
            if not work_package:
                raise AgentRunNotResumable("agent run has no persisted next action")

            resume_payload = {
                "previousStatus": run.status,
                "previousEvidenceId": run.evidence_id,
                "previousNextAction": work_package,
                "suppliedEvidenceDigest": _digest_text(supplied_evidence),
                "rawSecretsPersisted": False,
                "leaseSeconds": bounded_lease_seconds,
            }
            payload_json = _json(resume_payload)
            reason = "Persisted run was atomically claimed for one bounded resume attempt."

            if run.resume_task_id:
                cur.execute(
                    """
                    UPDATE agent_tasks
                    SET status = 'FAILED_RECOVERABLE',
                        source = 'agents-sdk',
                        reason = 'Previous resume lease expired before a validated final state was persisted.',
                        next_action = %s,
                        retry_count = LEAST(retry_count + 1, max_retries),
                        completed_at = NULL
                    WHERE task_id = %s AND run_id = %s AND status = 'RUNNING'
                    """,
                    (work_package, run.resume_task_id, normalized_run_id),
                )

            cur.execute(
                """
                INSERT INTO agent_tasks (
                    task_id, run_id, agent_id, specialist_role, work_package,
                    status, source, evidence_id, reason, next_action,
                    allowed_files, allowed_tools, acceptance_criteria, forbidden_actions,
                    timeout_seconds, max_tool_calls, max_retries
                ) VALUES (
                    %s, %s, 'orchestrator', 'recovery', %s,
                    'RUNNING', 'agents-sdk', %s, %s, %s,
                    '[]'::jsonb, '[]'::jsonb, %s::jsonb, %s::jsonb,
                    %s, 20, 2
                )
                """,
                (
                    task_id,
                    normalized_run_id,
                    work_package,
                    evidence_id,
                    reason,
                    work_package,
                    _json([
                        "Produce a new evidence-backed run state.",
                        "Preserve Draft-PR-only and no-auto-merge policy.",
                    ]),
                    _json([
                        "read or persist secrets",
                        "merge a pull request",
                        "deploy to production",
                        "claim success without runtime evidence",
                    ]),
                    bounded_lease_seconds,
                ),
            )
            cur.execute(
                """
                INSERT INTO agent_evidence (
                    evidence_id, run_id, task_id, agent_id, source, kind,
                    summary, sha256, payload
                ) VALUES (%s, %s, %s, 'orchestrator', 'agents-sdk', 'resume_claim', %s, %s, %s::jsonb)
                """,
                (
                    evidence_id,
                    normalized_run_id,
                    task_id,
                    reason,
                    _digest_text(payload_json),
                    payload_json,
                ),
            )
            cur.execute(
                """
                UPDATE agent_runs
                SET status = 'RUNNING',
                    source = 'agents-sdk',
                    evidence_id = %s,
                    trace_id = %s,
                    reason = %s,
                    next_action = %s,
                    resumed_at = NOW(),
                    lease_token = %s,
                    lease_expires_at = NOW() + (%s * INTERVAL '1 second'),
                    resume_task_id = %s
                WHERE run_id = %s AND user_id = %s::uuid
                  AND (lease_token IS NULL OR lease_expires_at <= NOW())
                RETURNING run_id
                """,
                (
                    evidence_id,
                    normalized_trace_id,
                    reason,
                    work_package,
                    lease_digest,
                    bounded_lease_seconds,
                    task_id,
                    normalized_run_id,
                    str(user_id),
                ),
            )
            if not cur.fetchone():
                raise AgentRunResumeConflict("agent run was claimed by another worker")
            cur.execute(
                """
                INSERT INTO agent_events (
                    event_id, run_id, task_id, agent_id, type, status, source,
                    summary, evidence_id, trace_id, next_action
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                _event_payload(
                    event_id=event_id,
                    run_id=normalized_run_id,
                    task_id=task_id,
                    agent_id="orchestrator",
                    event_type="run_resumed",
                    status="RUNNING",
                    source="agents-sdk",
                    summary=reason,
                    evidence_id=evidence_id,
                    trace_id=normalized_trace_id,
                    next_action=work_package,
                ),
            )
        conn.commit()
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        raise

    return AgentRunResumeClaim(
        run=run,
        task_id=task_id,
        work_package=work_package,
        evidence_id=evidence_id,
        trace_id=normalized_trace_id,
        lease_token=raw_lease_token,
        lease_seconds=bounded_lease_seconds,
    )


def create_agent_task(
    conn: Any,
    *,
    run_id: str,
    task_id: str,
    agent_id: str,
    work_package: str,
    evidence_id: str,
    source: str = "agents-sdk",
    status: str = "QUEUED",
    reason: str = "Bounded work package was queued by the orchestrator.",
    next_action: str = "ASSIGNED",
    specialist_role: str | None = None,
    allowed_files: Sequence[str] = (),
    allowed_tools: Sequence[str] = (),
    acceptance_criteria: Sequence[str] = (),
    forbidden_actions: Sequence[str] = (),
    timeout_seconds: int = 900,
    max_tool_calls: int = 20,
    max_retries: int = 2,
) -> None:
    normalized_status = _validated_status(status)
    normalized_source = _validated_source(source)
    normalized_run_id = _validated_id(run_id, "run_id")
    normalized_task_id = _validated_id(task_id, "task_id")
    if timeout_seconds < 1 or max_tool_calls < 0 or max_retries < 0:
        raise ValueError("task limits are invalid")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_tasks (
                    task_id, run_id, agent_id, specialist_role, work_package,
                    status, source, evidence_id, reason, next_action,
                    allowed_files, allowed_tools, acceptance_criteria, forbidden_actions,
                    timeout_seconds, max_tool_calls, max_retries
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                    %s, %s, %s
                )
                """,
                (
                    normalized_task_id,
                    normalized_run_id,
                    _bounded(agent_id, 160),
                    _bounded(specialist_role, 120) or None,
                    _bounded(work_package, 2000),
                    normalized_status,
                    normalized_source,
                    _validated_id(evidence_id, "evidence_id"),
                    _bounded(reason, 2000),
                    _bounded(next_action, 1000),
                    _json([_bounded(item, 500) for item in allowed_files]),
                    _json([_bounded(item, 160) for item in allowed_tools]),
                    _json([_bounded(item, 1000) for item in acceptance_criteria]),
                    _json([_bounded(item, 500) for item in forbidden_actions]),
                    int(timeout_seconds),
                    int(max_tool_calls),
                    int(max_retries),
                ),
            )
        conn.commit()
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        raise


def record_agent_failure(
    conn: Any,
    *,
    run_id: str,
    agent_id: str,
    family: str,
    summary: str,
    evidence_id: str,
    recoverable: bool,
    task_id: str | None = None,
) -> str:
    failure_id = _new_id("failure")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_failures (
                    failure_id, run_id, task_id, agent_id, family,
                    recoverable, summary, evidence_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    failure_id,
                    _validated_id(run_id, "run_id"),
                    task_id,
                    _bounded(agent_id, 160),
                    _bounded(family, 160),
                    bool(recoverable),
                    _bounded(summary, 2000),
                    _validated_id(evidence_id, "evidence_id"),
                ),
            )
        conn.commit()
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        raise
    return failure_id


def stored_run_from_row(row: Mapping[str, Any]) -> StoredAgentRun:
    return StoredAgentRun(
        run_id=str(row.get("run_id") or ""),
        user_id=str(row.get("user_id") or ""),
        session_key=str(row.get("session_key") or ""),
        status=str(row.get("status") or ""),
        source=str(row.get("source") or ""),
        evidence_id=str(row.get("evidence_id") or ""),
        trace_id=str(row.get("trace_id") or ""),
        reason=str(row.get("reason") or ""),
        next_action=str(row.get("next_action") or ""),
        mission_summary=str(row.get("mission_summary") or ""),
        mission_digest=str(row.get("mission_digest") or ""),
        max_active_specialists=int(row.get("max_active_specialists") or 0),
        max_iterations=int(row.get("max_iterations") or 0),
        iteration_count=int(row.get("iteration_count") or 0),
        lease_active=bool(row.get("lease_active")),
        resume_task_id=str(row.get("resume_task_id") or "") or None,
    )


def read_agent_run(conn: Any, *, user_id: str, run_id: str) -> StoredAgentRun | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT *,
                   (lease_token IS NOT NULL AND lease_expires_at > NOW()) AS lease_active
            FROM agent_runs
            WHERE user_id = %s::uuid AND run_id = %s
            LIMIT 1
            """,
            (str(user_id), _validated_id(run_id, "run_id")),
        )
        row = cur.fetchone()
    return stored_run_from_row(row) if row else None


def list_resumable_agent_runs(
    conn: Any,
    *,
    user_id: str | None = None,
    limit: int = 50,
) -> tuple[StoredAgentRun, ...]:
    safe_limit = max(1, min(int(limit), 100))
    terminal = tuple(sorted(NON_RESUMABLE_RUN_STATUSES))
    with conn.cursor() as cur:
        if user_id:
            cur.execute(
                """
                SELECT *, false AS lease_active FROM agent_runs
                WHERE user_id = %s::uuid AND status <> ALL(%s)
                  AND (lease_token IS NULL OR lease_expires_at <= NOW())
                ORDER BY updated_at ASC
                LIMIT %s
                """,
                (str(user_id), list(terminal), safe_limit),
            )
        else:
            cur.execute(
                """
                SELECT *, false AS lease_active FROM agent_runs
                WHERE status <> ALL(%s)
                  AND (lease_token IS NULL OR lease_expires_at <= NOW())
                ORDER BY updated_at ASC
                LIMIT %s
                """,
                (list(terminal), safe_limit),
            )
        rows = cur.fetchall()
    return tuple(stored_run_from_row(row) for row in rows)
