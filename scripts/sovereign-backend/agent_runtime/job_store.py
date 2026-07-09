"""Database store helpers for Sovereign Agent Jobs.

This module owns the SQL boundary for the neutral `sovereign_agent_jobs` tables.
It accepts a DB-API compatible connection and never creates UI truth.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping, Sequence

from .contracts import (
    SovereignAgentEvent,
    SovereignAgentJobRequest,
    SovereignAgentJobResult,
    sanitize_agent_text,
)


@dataclass(frozen=True)
class StoredSovereignAgentJob:
    job_id: str
    user_id: str
    executor: str
    repo_url: str
    branch: str
    mission: str
    status: str
    workspace_id: str | None = None
    external_ref: str | None = None
    draft_pr_url: str | None = None
    changed_files: tuple[str, ...] = ()
    diff_summary: str | None = None
    test_summary: str | None = None
    blocker: str | None = None
    events: tuple[dict[str, Any], ...] = ()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _event_to_dict(event: SovereignAgentEvent) -> dict[str, Any]:
    return {
        "stage": sanitize_agent_text(event.stage, 80),
        "level": event.level if event.level in ("info", "warning", "error", "success") else "warning",
        "message": sanitize_agent_text(event.message, 1200),
        "at": event.at,
    }


def _coerce_json_array(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return ()
        return tuple(parsed) if isinstance(parsed, list) else ()
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, tuple):
        return value
    return ()


def stored_job_from_row(row: Mapping[str, Any]) -> StoredSovereignAgentJob:
    return StoredSovereignAgentJob(
        job_id=str(row.get("job_id") or ""),
        user_id=str(row.get("user_id") or ""),
        executor=str(row.get("executor") or "sovereign-local-runner"),
        repo_url=str(row.get("repo_url") or ""),
        branch=str(row.get("branch") or "main"),
        mission=str(row.get("mission") or ""),
        status=str(row.get("status") or "blocked"),
        workspace_id=row.get("workspace_id"),
        external_ref=row.get("external_ref"),
        draft_pr_url=row.get("draft_pr_url"),
        changed_files=tuple(str(path) for path in _coerce_json_array(row.get("changed_files"))),
        diff_summary=row.get("diff_summary"),
        test_summary=row.get("test_summary"),
        blocker=row.get("blocker"),
        events=tuple(event for event in _coerce_json_array(row.get("events")) if isinstance(event, dict)),
    )


def create_agent_job_record(
    conn: Any,
    *,
    user_id: str,
    job_id: str,
    request: SovereignAgentJobRequest,
    status: str = "queued",
    workspace_id: str | None = None,
    events: Sequence[SovereignAgentEvent] = (),
    blocker: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sovereign_agent_jobs (
                user_id,
                job_id,
                executor,
                repo_url,
                branch,
                mission,
                status,
                workspace_id,
                allowed_paths,
                forbidden_paths,
                memory_hints,
                changed_files,
                events,
                blocker,
                draft_pr_only,
                allow_auto_merge
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb,
                '[]'::jsonb, %s::jsonb, %s, TRUE, FALSE
            )
            """,
            (
                user_id,
                job_id,
                request.executor,
                request.repo_url,
                request.branch,
                request.mission,
                status,
                workspace_id,
                _json(list(request.allowed_paths)),
                _json(list(request.forbidden_paths)),
                _json(list(request.memory_hints)),
                _json([_event_to_dict(event) for event in events]),
                sanitize_agent_text(blocker, 1200) if blocker else None,
            ),
        )
    conn.commit()


def append_agent_event(conn: Any, job_id: str, event: SovereignAgentEvent) -> None:
    event_payload = _event_to_dict(event)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sovereign_agent_events (job_id, stage, level, message, payload)
            VALUES (%s, %s, %s, %s, '{}'::jsonb)
            """,
            (job_id, event_payload["stage"], event_payload["level"], event_payload["message"]),
        )
        cur.execute(
            """
            UPDATE sovereign_agent_jobs
            SET events = COALESCE(events, '[]'::jsonb) || %s::jsonb
            WHERE job_id = %s
            """,
            (_json([event_payload]), job_id),
        )
    conn.commit()


def update_agent_job_state(
    conn: Any,
    *,
    job_id: str,
    status: str,
    workspace_id: str | None = None,
    external_ref: str | None = None,
    changed_files: Sequence[str] | None = None,
    diff_summary: str | None = None,
    test_summary: str | None = None,
    draft_pr_url: str | None = None,
    blocker: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE sovereign_agent_jobs
            SET status = %s,
                workspace_id = COALESCE(%s, workspace_id),
                external_ref = COALESCE(%s, external_ref),
                changed_files = COALESCE(%s::jsonb, changed_files),
                diff_summary = COALESCE(%s, diff_summary),
                test_summary = COALESCE(%s, test_summary),
                draft_pr_url = COALESCE(%s, draft_pr_url),
                blocker = COALESCE(%s, blocker)
            WHERE job_id = %s
            """,
            (
                status,
                workspace_id,
                external_ref,
                _json(list(changed_files)) if changed_files is not None else None,
                sanitize_agent_text(diff_summary, 2000) if diff_summary else None,
                sanitize_agent_text(test_summary, 2000) if test_summary else None,
                draft_pr_url if draft_pr_url and draft_pr_url.startswith("https://github.com/") else None,
                sanitize_agent_text(blocker, 1200) if blocker else None,
                job_id,
            ),
        )
    conn.commit()



def _row_to_dict(row: tuple, columns: tuple) -> dict:
    """Convert a tuple row to a dictionary using column names."""
    if row is None:
        return {}
    return dict(zip(columns, row))


def read_agent_job(conn: Any, *, user_id: str, job_id: str) -> StoredSovereignAgentJob | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM sovereign_agent_jobs
            WHERE user_id = %s AND job_id = %s
            LIMIT 1
            """,
            (user_id, job_id),
        )
        row = cur.fetchone()
        columns = tuple(d[0] for d in cur.description) if cur.description else ()
    return stored_job_from_row(_row_to_dict(row, columns)) if row else None


def list_agent_jobs(conn: Any, *, user_id: str, limit: int = 20) -> tuple[StoredSovereignAgentJob, ...]:
    safe_limit = max(1, min(int(limit), 100))
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM sovereign_agent_jobs
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, safe_limit),
        )
        rows = cur.fetchall()
        columns = tuple(d[0] for d in cur.description) if cur.description else ()
    return tuple(stored_job_from_row(_row_to_dict(row, columns)) for row in rows)



def mark_draft_pr_prepared(conn: Any, *, job_id: str, draft_pr_url: str) -> None:
    """Mark a job as having draft PR prepared."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE sovereign_agent_jobs
            SET draft_pr_url = %s,
                draft_pr_only = FALSE
            WHERE job_id = %s
            """,
            (draft_pr_url, job_id),
        )
    conn.commit()


def result_from_stored_job(job: StoredSovereignAgentJob) -> SovereignAgentJobResult:
    return SovereignAgentJobResult(
        job_id=job.job_id,
        status=job.status,  # type: ignore[arg-type]
        executor=job.executor,  # type: ignore[arg-type]
        changed_files=job.changed_files,
        diff_summary=job.diff_summary,
        test_summary=job.test_summary,
        draft_pr_url=job.draft_pr_url,
        blocker=job.blocker,
        workspace_id=job.workspace_id,
        external_ref=job.external_ref,
    )
