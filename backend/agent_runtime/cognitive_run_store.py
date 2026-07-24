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

from .agent_run_receipts import build_agent_run_receipt, canonical_sha256
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
    "WAITING_FOR_OWNER",
})

RECOVERY_RESOLUTION_STATUSES: Final[frozenset[str]] = frozenset({
    "BLOCKED",
    "WAITING_FOR_OWNER",
    "READY_FOR_DRAFT_PR",
    "DRAFT_PR_CREATED",
    "COMPLETED",
})

_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")


@dataclass(frozen=True, slots=True)
class StoredAgentRun:
    run_id: str
    user_id: str
    job_id: str | None
    session_key: str
    a2a_context_id: str | None
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
    updated_at: str


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


def _timestamp_text(value: object) -> str:
    if value is None:
        return ""
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value or "").strip()


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


def _resolve_recoverable_failures(cur: Any, *, run_id: str, status: str) -> None:
    """Close prior recoverable failures only after a successful persisted execution state."""

    if status not in RECOVERY_RESOLUTION_STATUSES:
        return
    cur.execute(
        """
        UPDATE agent_failures
        SET resolved_at = COALESCE(resolved_at, NOW())
        WHERE run_id = %s
          AND recoverable = TRUE
          AND resolved_at IS NULL
        """,
        (run_id,),
    )


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
    a2a_context_id: str | None = None,
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
    normalized_a2a_context = _bounded(a2a_context_id, 500)
    if normalized_a2a_context:
        context_snapshot["a2aContextId"] = normalized_a2a_context

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


def link_agent_run_job(
    conn: Any,
    *,
    user_id: str,
    run_id: str,
    job_id: str,
    trace_id: str,
    workspace_id: str | None,
) -> dict[str, str]:
    """Link one persisted RECEIVED run to a real Agent Job with bounded handoff evidence."""

    normalized_run_id = _validated_id(run_id, "run_id")
    normalized_job_id = _validated_id(job_id, "job_id")
    normalized_trace_id = _validated_id(trace_id, "trace_id")
    normalized_workspace = _bounded(workspace_id, 240) or None
    evidence_id = _new_id("evidence")
    event_id = _new_id("event")
    reason = "The routed LLM selected repository execution and the run was linked to a real Agent Job."
    next_action = "CREATE_SIX_AGENT_TASKS"
    payload = {
        "jobId": normalized_job_id,
        "workspaceId": normalized_workspace,
        "draftPrOnly": True,
        "autoMerge": False,
    }
    payload_json = _json(payload)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_evidence (
                    evidence_id, run_id, task_id, agent_id, source, kind,
                    summary, sha256, payload
                ) VALUES (%s, %s, NULL, 'orchestrator', 'agents-sdk',
                          'implementation_handoff', %s, %s, %s::jsonb)
                """,
                (
                    evidence_id,
                    normalized_run_id,
                    reason,
                    _digest_text(payload_json),
                    payload_json,
                ),
            )
            cur.execute(
                """
                UPDATE agent_runs
                SET job_id = %s,
                    status = 'PLANNED',
                    source = 'agents-sdk',
                    evidence_id = %s,
                    trace_id = %s,
                    reason = %s,
                    next_action = %s
                WHERE run_id = %s AND user_id = %s::uuid
                  AND (job_id IS NULL OR job_id = %s)
                RETURNING run_id
                """,
                (
                    normalized_job_id,
                    evidence_id,
                    normalized_trace_id,
                    reason,
                    next_action,
                    normalized_run_id,
                    str(user_id),
                    normalized_job_id,
                ),
            )
            if not cur.fetchone():
                raise LookupError("agent run could not be linked to the implementation job")
            cur.execute(
                """
                INSERT INTO agent_events (
                    event_id, run_id, task_id, agent_id, type, status, source,
                    summary, evidence_id, trace_id, next_action
                ) VALUES (%s, %s, NULL, 'orchestrator', 'implementation_job_linked',
                          'PLANNED', 'agents-sdk', %s, %s, %s, %s)
                """,
                (
                    event_id,
                    normalized_run_id,
                    reason,
                    evidence_id,
                    normalized_trace_id,
                    next_action,
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
        "jobId": normalized_job_id,
        "status": "PLANNED",
        "source": "agents-sdk",
        "evidenceId": evidence_id,
        "traceId": normalized_trace_id,
        "reason": reason,
        "nextAction": next_action,
    }


def record_agent_stage_event(
    conn: Any,
    *,
    user_id: str,
    run_id: str,
    trace_id: str,
    agent_id: str,
    event_type: str,
    status: str,
    summary: str,
    next_action: str,
    evidence_payload: Mapping[str, object],
    task_id: str | None = None,
    expected_lease_token: str | None = None,
) -> dict[str, str]:
    """Persist one bounded agent lifecycle event without inventing run completion."""

    normalized_run_id = _validated_id(run_id, "run_id")
    normalized_trace_id = _validated_id(trace_id, "trace_id")
    normalized_status = _validated_status(status)
    normalized_agent = _bounded(agent_id, 160)
    normalized_event_type = _bounded(event_type, 120)
    normalized_summary = _bounded(summary, 2000)
    normalized_next_action = _bounded(next_action, 1000)
    if not all((normalized_agent, normalized_event_type, normalized_summary, normalized_next_action)):
        raise ValueError("agent stage event requires agent, type, summary and next action")

    payload_json = _json(dict(evidence_payload))
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
                ) VALUES (%s, %s, %s, %s, 'agents-sdk', 'agent_stage', %s, %s, %s::jsonb)
                """,
                (
                    evidence_id,
                    normalized_run_id,
                    task_id,
                    normalized_agent,
                    normalized_summary,
                    _digest_text(payload_json),
                    payload_json,
                ),
            )
            cur.execute(
                f"""
                UPDATE agent_runs
                SET status = CASE
                        WHEN %s IN ('RUNNING', 'VERIFYING', 'WAITING_FOR_AGENT', 'WAITING_FOR_TOOL') THEN %s
                        ELSE status
                    END,
                    source = 'agents-sdk',
                    evidence_id = %s,
                    trace_id = %s,
                    reason = %s,
                    next_action = %s
                WHERE run_id = %s AND user_id = %s::uuid
                  {lease_clause}
                RETURNING run_id
                """,
                (
                    normalized_status,
                    normalized_status,
                    evidence_id,
                    normalized_trace_id,
                    normalized_summary,
                    normalized_next_action,
                    normalized_run_id,
                    str(user_id),
                    *lease_params,
                ),
            )
            if not cur.fetchone():
                raise LookupError("agent run not found or active resume lease is not held")
            cur.execute(
                """
                INSERT INTO agent_events (
                    event_id, run_id, task_id, agent_id, type, status, source,
                    summary, evidence_id, trace_id, next_action
                ) VALUES (%s, %s, %s, %s, %s, %s, 'agents-sdk', %s, %s, %s, %s)
                """,
                (
                    event_id,
                    normalized_run_id,
                    task_id,
                    normalized_agent,
                    normalized_event_type,
                    normalized_status,
                    normalized_summary,
                    evidence_id,
                    normalized_trace_id,
                    normalized_next_action,
                ),
            )
            if task_id:
                cur.execute(
                    """
                    UPDATE agent_tasks
                    SET status = %s,
                        source = 'agents-sdk',
                        evidence_id = %s,
                        reason = %s,
                        next_action = %s,
                        completed_at = CASE
                            WHEN %s IN ('COMPLETED', 'FAILED_FINAL', 'DRAFT_PR_CREATED') THEN NOW()
                            WHEN %s IN ('RUNNING', 'VERIFYING', 'WAITING_FOR_AGENT', 'WAITING_FOR_TOOL') THEN NULL
                            ELSE completed_at
                        END
                    WHERE task_id = %s AND run_id = %s
                    """,
                    (
                        normalized_status,
                        evidence_id,
                        normalized_summary,
                        normalized_next_action,
                        normalized_status,
                        normalized_status,
                        task_id,
                        normalized_run_id,
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
        "source": "agents-sdk",
        "evidenceId": evidence_id,
        "traceId": normalized_trace_id,
        "agentId": normalized_agent,
        "eventType": normalized_event_type,
        "summary": normalized_summary,
        "nextAction": normalized_next_action,
    }


EXTERNAL_ACTION_SOURCES: Final[frozenset[str]] = frozenset({
    "mcp",
    "broker",
    "github",
    "browserless",
    "tika",
    "gotenberg",
    "database",
})


def _sanitize_external_payload(value: object, *, depth: int = 0) -> object:
    """Return bounded JSON-safe external evidence without raw secret-shaped text."""

    if depth > 5:
        return "[depth-limit]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Mapping):
        output: dict[str, object] = {}
        for index, (key, item) in enumerate(sorted(value.items(), key=lambda pair: str(pair[0]))):
            if index >= 60:
                output["_truncated"] = True
                break
            safe_key = _bounded(key, 120)
            if safe_key:
                output[safe_key] = _sanitize_external_payload(item, depth=depth + 1)
        return output
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _sanitize_external_payload(item, depth=depth + 1)
            for item in list(value)[:100]
        ]
    return sanitize_agent_text(str(value), 1200)


def record_external_action_event(
    conn: Any,
    *,
    user_id: str,
    run_id: str,
    source: str,
    external_identity: str,
    event_type: str,
    summary: str,
    payload: Mapping[str, object],
) -> dict[str, object]:
    """Append one idempotent external action event without changing run/task state."""

    normalized_run_id = _validated_id(run_id, "run_id")
    normalized_source = _validated_source(source)
    if normalized_source not in EXTERNAL_ACTION_SOURCES:
        raise ValueError("source is not allowed for external action events")
    normalized_identity = _validated_id(external_identity, "external_identity")
    normalized_type = _bounded(event_type, 120)
    normalized_summary = _bounded(summary, 2000)
    if not normalized_type or not normalized_summary:
        raise ValueError("external action event requires type and summary")

    safe_payload = _sanitize_external_payload(dict(payload))
    if not isinstance(safe_payload, dict):
        raise ValueError("external action payload must be an object")
    evidence_payload = {
        "externalIdentity": normalized_identity,
        "eventType": normalized_type,
        "data": safe_payload,
        "rawSecretsPersisted": False,
        "runStateMutationAllowed": False,
    }
    payload_json = _json(evidence_payload)
    identity_digest = hashlib.sha256(
        f"{normalized_run_id}|{normalized_source}|{normalized_identity}".encode("utf-8")
    ).hexdigest()
    evidence_id = f"evidence-external-{identity_digest[:32]}"
    event_id = f"event-external-{identity_digest[:32]}"
    evidence_digest = _digest_text(payload_json)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id, status, trace_id, next_action
                FROM agent_runs
                WHERE run_id = %s AND user_id = %s::uuid
                LIMIT 1
                FOR SHARE
                """,
                (normalized_run_id, str(user_id)),
            )
            run = cur.fetchone()
            if not run:
                raise LookupError("agent run not found for authenticated user")
            run_status = _validated_status(str(run.get("status") or ""))
            trace_id = _validated_id(str(run.get("trace_id") or ""), "trace_id")
            next_action = _bounded(run.get("next_action"), 1000) or "NO_RUN_STATE_CHANGE"

            cur.execute(
                """
                INSERT INTO agent_evidence (
                    evidence_id, run_id, task_id, agent_id, source, kind,
                    summary, sha256, payload
                ) VALUES (
                    %s, %s, NULL, %s, %s, 'external_action',
                    %s, %s, %s::jsonb
                )
                ON CONFLICT (evidence_id) DO NOTHING
                RETURNING evidence_id
                """,
                (
                    evidence_id,
                    normalized_run_id,
                    f"external:{normalized_source}",
                    normalized_source,
                    normalized_summary,
                    evidence_digest,
                    payload_json,
                ),
            )
            evidence_created = bool(cur.fetchone())
            cur.execute(
                """
                INSERT INTO agent_events (
                    event_id, run_id, task_id, agent_id, type, status, source,
                    summary, evidence_id, trace_id, next_action
                ) VALUES (
                    %s, %s, NULL, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (event_id) DO NOTHING
                RETURNING event_id
                """,
                (
                    event_id,
                    normalized_run_id,
                    f"external:{normalized_source}",
                    normalized_type,
                    run_status,
                    normalized_source,
                    normalized_summary,
                    evidence_id,
                    trace_id,
                    next_action,
                ),
            )
            event_created = bool(cur.fetchone())
        conn.commit()
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        raise

    return {
        "runId": normalized_run_id,
        "source": normalized_source,
        "externalIdentity": normalized_identity,
        "eventType": normalized_type,
        "eventId": event_id,
        "evidenceId": evidence_id,
        "created": event_created,
        "duplicate": not event_created,
        "evidenceCreated": evidence_created,
        "runStatus": run_status,
        "runStateChanged": False,
        "taskStateChanged": False,
        "activeBlockerChanged": False,
        "rawSecretsPersisted": False,
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
            _resolve_recoverable_failures(
                cur,
                run_id=normalized_run_id,
                status=normalized_status,
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


def request_agent_approval(
    conn: Any,
    *,
    user_id: str,
    run_id: str,
    trace_id: str,
    kind: str,
    requested_by_agent: str,
    reason: str,
    next_action: str,
    evidence_payload: Mapping[str, object],
    task_id: str | None = None,
    protected_input_ref: str | None = None,
    expected_lease_token: str | None = None,
) -> dict[str, str]:
    """Persist one owner approval request and WAITING_FOR_OWNER state atomically."""

    normalized_run_id = _validated_id(run_id, "run_id")
    normalized_trace_id = _validated_id(trace_id, "trace_id")
    normalized_kind = _bounded(kind, 120)
    normalized_agent = _bounded(requested_by_agent, 160)
    normalized_reason = _bounded(reason, 2000)
    normalized_next_action = _bounded(next_action, 1000)
    normalized_protected_ref = _bounded(protected_input_ref, 500) or None
    if not all((normalized_kind, normalized_agent, normalized_reason, normalized_next_action)):
        raise ValueError("approval request requires kind, agent, reason and next action")

    safe_payload = dict(evidence_payload)
    payload_json = _json(safe_payload)
    evidence_id = _new_id("evidence")
    approval_id = _new_id("approval")
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
                ) VALUES (%s, %s, %s, %s, 'agents-sdk', 'owner_approval_request', %s, %s, %s::jsonb)
                """,
                (
                    evidence_id,
                    normalized_run_id,
                    task_id,
                    normalized_agent,
                    normalized_reason,
                    _digest_text(payload_json),
                    payload_json,
                ),
            )
            cur.execute(
                f"""
                UPDATE agent_runs
                SET status = 'WAITING_FOR_OWNER',
                    source = 'agents-sdk',
                    evidence_id = %s,
                    trace_id = %s,
                    reason = %s,
                    next_action = %s,
                    iteration_count = LEAST(iteration_count + 1, max_iterations),
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    resume_task_id = NULL
                WHERE run_id = %s AND user_id = %s::uuid
                  {lease_clause}
                RETURNING run_id
                """,
                (
                    evidence_id,
                    normalized_trace_id,
                    normalized_reason,
                    normalized_next_action,
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
                    SET status = 'WAITING_FOR_OWNER',
                        source = 'agents-sdk',
                        evidence_id = %s,
                        reason = %s,
                        next_action = %s
                    WHERE task_id = %s AND run_id = %s
                    """,
                    (
                        evidence_id,
                        normalized_reason,
                        normalized_next_action,
                        task_id,
                        normalized_run_id,
                    ),
                )
            _resolve_recoverable_failures(
                cur,
                run_id=normalized_run_id,
                status="WAITING_FOR_OWNER",
            )
            cur.execute(
                """
                INSERT INTO agent_approvals (
                    approval_id, run_id, task_id, kind, status,
                    protected_input_ref, requested_by_agent, evidence_id, reason
                ) VALUES (%s, %s, %s, %s, 'WAITING_FOR_OWNER', %s, %s, %s, %s)
                """,
                (
                    approval_id,
                    normalized_run_id,
                    task_id,
                    normalized_kind,
                    normalized_protected_ref,
                    normalized_agent,
                    evidence_id,
                    normalized_reason,
                ),
            )
            cur.execute(
                """
                INSERT INTO agent_events (
                    event_id, run_id, task_id, agent_id, type, status, source,
                    summary, evidence_id, trace_id, next_action
                ) VALUES (%s, %s, %s, %s, 'owner_approval_requested',
                          'WAITING_FOR_OWNER', 'agents-sdk', %s, %s, %s, %s)
                """,
                (
                    event_id,
                    normalized_run_id,
                    task_id,
                    normalized_agent,
                    normalized_reason,
                    evidence_id,
                    normalized_trace_id,
                    normalized_next_action,
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
        "status": "WAITING_FOR_OWNER",
        "source": "agents-sdk",
        "evidenceId": evidence_id,
        "traceId": normalized_trace_id,
        "reason": normalized_reason,
        "nextAction": normalized_next_action,
        "approvalId": approval_id,
        "approvalKind": normalized_kind,
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
    commit: bool = True,
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
        if commit:
            conn.commit()
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        raise


def start_agent_tool_call(
    conn: Any,
    *,
    run_id: str,
    task_id: str,
    agent_id: str,
    tool_name: str,
    arguments: Mapping[str, object],
    mutating: bool,
) -> str:
    """Reserve one bounded task tool call and persist only its argument digest."""

    normalized_run_id = _validated_id(run_id, "run_id")
    normalized_task_id = _validated_id(task_id, "task_id")
    normalized_agent = _bounded(agent_id, 160)
    normalized_tool = _bounded(tool_name, 160)
    if not normalized_agent or not normalized_tool:
        raise ValueError("agent tool call requires agent and tool names")
    tool_call_id = _new_id("tool-call")
    arguments_digest = canonical_sha256(dict(arguments))
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_tasks
                SET tool_call_count = tool_call_count + 1,
                    status = 'RUNNING',
                    reason = %s,
                    next_action = 'WAIT_FOR_TOOL_RESULT'
                WHERE task_id = %s AND run_id = %s
                  AND tool_call_count < max_tool_calls
                RETURNING task_id
                """,
                (
                    f"Agent started bounded tool {normalized_tool}.",
                    normalized_task_id,
                    normalized_run_id,
                ),
            )
            if not cur.fetchone():
                raise RuntimeError("agent task tool-call budget is exhausted or task is missing")
            cur.execute(
                """
                INSERT INTO agent_tool_calls (
                    tool_call_id, run_id, task_id, agent_id, tool_name,
                    arguments_digest, status, mutating
                ) VALUES (%s, %s, %s, %s, %s, %s, 'RUNNING', %s)
                """,
                (
                    tool_call_id,
                    normalized_run_id,
                    normalized_task_id,
                    normalized_agent,
                    normalized_tool,
                    arguments_digest,
                    bool(mutating),
                ),
            )
        conn.commit()
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        raise
    return tool_call_id


def finish_agent_tool_call(
    conn: Any,
    *,
    tool_call_id: str,
    status: str,
    result_summary: Mapping[str, object],
    repository: str,
    base_commit_sha: str,
    mcp_revision: str,
    mcp_image_digest: str,
    mcp_revision_verified: bool,
    operation_identity: str,
    diff_sha256: str,
    test_evidence_sha256: str,
    evidence_gate_result: str,
    mutation_performed: bool,
    observed_effect: str,
    authoritative_readback_sha256: str,
    failure_family: str | None = None,
) -> dict[str, object]:
    """Atomically finish one tool call and append its canonical receipt."""

    normalized_id = _validated_id(tool_call_id, "tool_call_id")
    normalized_status = str(status or "").strip().upper()
    if normalized_status not in {"COMPLETED", "BLOCKED", "FAILED_RECOVERABLE", "FAILED_FINAL"}:
        raise ValueError("unsupported agent tool-call result status")
    result_digest = canonical_sha256(dict(result_summary))
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tool_call_id, run_id, task_id, tool_name, arguments_digest, mutating
                FROM agent_tool_calls
                WHERE tool_call_id = %s AND status = 'RUNNING'
                LIMIT 1
                FOR UPDATE
                """,
                (normalized_id,),
            )
            tool_call = cur.fetchone()
            if not tool_call:
                raise LookupError("running agent tool call was not found")
            run_id = _validated_id(str(tool_call["run_id"]), "run_id")
            cur.execute(
                """
                SELECT sequence, receipt_sha256
                FROM agent_run_receipts
                WHERE agent_run_id = %s
                ORDER BY sequence DESC
                LIMIT 1
                FOR UPDATE
                """,
                (run_id,),
            )
            previous_row = cur.fetchone()
            sequence = int(previous_row["sequence"]) + 1 if previous_row else 0
            previous_hash = str(previous_row["receipt_sha256"]) if previous_row else "0" * 64
            receipt = build_agent_run_receipt(
                sequence=sequence,
                repository=repository,
                base_commit_sha=base_commit_sha,
                mcp_revision=mcp_revision,
                mcp_image_digest=mcp_image_digest,
                mcp_revision_verified=mcp_revision_verified,
                agent_run_id=run_id,
                tool_name=str(tool_call["tool_name"]),
                call_id=normalized_id,
                operation_identity=operation_identity,
                input_sha256=str(tool_call["arguments_digest"]),
                output_sha256=result_digest,
                diff_sha256=diff_sha256,
                test_evidence_sha256=test_evidence_sha256,
                evidence_gate_result=evidence_gate_result,
                mutation_performed=mutation_performed,
                observed_effect=observed_effect,
                authoritative_readback_sha256=authoritative_readback_sha256,
                previous_receipt_sha256=previous_hash,
            )
            body = dict(receipt["body"])
            cur.execute(
                """
                INSERT INTO agent_run_receipts (
                    receipt_sha256, schema_version, sequence, repository,
                    base_commit_sha, mcp_revision, mcp_image_digest,
                    mcp_revision_verified, agent_run_id, tool_name, call_id,
                    operation_identity, input_sha256, output_sha256, diff_sha256,
                    test_evidence_sha256, evidence_gate_result, mutation_performed,
                    observed_effect, authoritative_readback_sha256,
                    previous_receipt_sha256, canonical_body
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s::jsonb
                )
                """,
                (
                    body["receipt_sha256"], body["schema_version"], body["sequence"], body["repository"],
                    body["base_commit_sha"], body["mcp_revision"], body["mcp_image_digest"],
                    body["mcp_revision_verified"], body["agent_run_id"], body["tool_name"], body["call_id"],
                    body["operation_identity"], body["input_sha256"], body["output_sha256"], body["diff_sha256"],
                    body["test_evidence_sha256"], body["evidence_gate_result"], body["mutation_performed"],
                    body["observed_effect"], body["authoritative_readback_sha256"],
                    body["previous_receipt_sha256"], _json(body),
                ),
            )
            cur.execute(
                """
                UPDATE agent_tool_calls
                SET status = %s,
                    result_digest = %s,
                    failure_family = %s,
                    finished_at = NOW()
                WHERE tool_call_id = %s AND status = 'RUNNING'
                RETURNING task_id
                """,
                (
                    normalized_status,
                    result_digest,
                    _bounded(failure_family, 160) or None,
                    normalized_id,
                ),
            )
            row = cur.fetchone()
            if not row:
                raise LookupError("running agent tool call changed before receipt persistence")
            if normalized_status in {"BLOCKED", "FAILED_RECOVERABLE", "FAILED_FINAL"}:
                cur.execute(
                    """
                    UPDATE agent_tasks
                    SET status = %s,
                        reason = %s,
                        next_action = 'REVIEW_TOOL_FAILURE_EVIDENCE'
                    WHERE task_id = %s
                    """,
                    (
                        normalized_status,
                        f"Bounded tool call ended with {normalized_status}.",
                        row["task_id"],
                    ),
                )
        conn.commit()
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        raise
    return receipt


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
    raw_context = row.get("context_snapshot") or {}
    if isinstance(raw_context, str):
        try:
            raw_context = json.loads(raw_context)
        except json.JSONDecodeError:
            raw_context = {}
    context_snapshot = raw_context if isinstance(raw_context, Mapping) else {}
    return StoredAgentRun(
        run_id=str(row.get("run_id") or ""),
        user_id=str(row.get("user_id") or ""),
        job_id=str(row.get("job_id") or "") or None,
        session_key=str(row.get("session_key") or ""),
        a2a_context_id=str(context_snapshot.get("a2aContextId") or "") or None,
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
        updated_at=_timestamp_text(row.get("updated_at")),
    )


def read_agent_task_ids(conn: Any, *, run_id: str) -> dict[str, str]:
    """Return the latest persisted task id for each agent in one run."""

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (agent_id) agent_id, task_id
            FROM agent_tasks
            WHERE run_id = %s
            ORDER BY agent_id, created_at DESC
            """,
            (_validated_id(run_id, "run_id"),),
        )
        rows = cur.fetchall()
    return {
        str(row["agent_id"]): str(row["task_id"])
        for row in rows
        if row.get("agent_id") and row.get("task_id")
    }


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


def _agent_run_filters(
    *,
    user_id: str,
    context_id: str | None = None,
    statuses: Sequence[str] = (),
    status_after: str | None = None,
) -> tuple[list[str], list[object]]:
    clauses = ["user_id = %s::uuid"]
    params: list[object] = [str(user_id)]
    normalized_context = _bounded(context_id, 500)
    if normalized_context:
        clauses.append("context_snapshot ->> 'a2aContextId' = %s")
        params.append(normalized_context)
    normalized_statuses = tuple(
        _validated_status(status)
        for status in statuses
        if str(status or "").strip()
    )
    if normalized_statuses:
        clauses.append("status = ANY(%s)")
        params.append(list(normalized_statuses))
    normalized_after = _bounded(status_after, 100)
    if normalized_after:
        clauses.append("updated_at >= %s::timestamptz")
        params.append(normalized_after)
    return clauses, params


def count_agent_runs(
    conn: Any,
    *,
    user_id: str,
    context_id: str | None = None,
    statuses: Sequence[str] = (),
    status_after: str | None = None,
) -> int:
    """Count one authenticated, filtered A2A task view."""

    clauses, params = _agent_run_filters(
        user_id=user_id,
        context_id=context_id,
        statuses=statuses,
        status_after=status_after,
    )
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) AS total FROM agent_runs WHERE {' AND '.join(clauses)}",
            tuple(params),
        )
        row = cur.fetchone()
    return int((row or {}).get("total") or 0)


def list_agent_runs(
    conn: Any,
    *,
    user_id: str,
    limit: int = 50,
    context_id: str | None = None,
    statuses: Sequence[str] = (),
    status_after: str | None = None,
    cursor_updated_at: str | None = None,
    cursor_run_id: str | None = None,
) -> tuple[StoredAgentRun, ...]:
    """Return one authenticated, cursor-bounded page ordered by last update."""

    safe_limit = max(1, min(int(limit), 101))
    clauses, params = _agent_run_filters(
        user_id=user_id,
        context_id=context_id,
        statuses=statuses,
        status_after=status_after,
    )
    normalized_cursor_time = _bounded(cursor_updated_at, 100)
    normalized_cursor_run = _bounded(cursor_run_id, 160)
    if normalized_cursor_time or normalized_cursor_run:
        if not normalized_cursor_time or not normalized_cursor_run:
            raise ValueError("A2A task cursor requires updated_at and run_id")
        _validated_id(normalized_cursor_run, "cursor_run_id")
        clauses.append("(updated_at, run_id) < (%s::timestamptz, %s)")
        params.extend((normalized_cursor_time, normalized_cursor_run))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT *,
                   (lease_token IS NOT NULL AND lease_expires_at > NOW()) AS lease_active
            FROM agent_runs
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC, run_id DESC
            LIMIT %s
            """,
            (*params, safe_limit),
        )
        rows = cur.fetchall()
    return tuple(stored_run_from_row(row) for row in rows)


def read_agent_events(
    conn: Any,
    *,
    user_id: str,
    run_id: str,
    limit: int = 500,
) -> tuple[dict[str, object], ...]:
    """Return bounded ordered event evidence for one authenticated user's run."""

    safe_limit = max(1, min(int(limit), 1000))
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT event.event_id, event.run_id, event.task_id, event.agent_id,
                   event.type, event.status, event.source, event.summary,
                   event.evidence_id, event.trace_id, event.created_at,
                   event.next_action
            FROM agent_events AS event
            JOIN agent_runs AS run ON run.run_id = event.run_id
            WHERE run.user_id = %s::uuid AND event.run_id = %s
            ORDER BY event.created_at ASC, event.event_id ASC
            LIMIT %s
            """,
            (str(user_id), _validated_id(run_id, "run_id"), safe_limit),
        )
        rows = cur.fetchall()
    return tuple(dict(row) for row in rows)


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
