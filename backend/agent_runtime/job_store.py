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
    # Migration 004: Draft PR fields (matching VPS schema)
    draft_pr_preparation: dict[str, Any] | None = None
    branch_name: str | None = None
    target_branch: str | None = None
    commit_message: str | None = None
    pr_url: str | None = None
    pr_state: str | None = None


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
    # Parse draft_pr_preparation JSONB
    draft_pr_prep = row.get("draft_pr_preparation")
    if isinstance(draft_pr_prep, str):
        try:
            draft_pr_prep = json.loads(draft_pr_prep)
        except json.JSONDecodeError:
            draft_pr_prep = None

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
        # Migration 004: Draft PR fields (matching VPS schema)
        draft_pr_preparation=draft_pr_prep,
        branch_name=row.get("branch_name"),
        target_branch=row.get("target_branch"),
        commit_message=row.get("commit_message"),
        pr_url=row.get("pr_url"),
        pr_state=row.get("pr_state"),
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
    clear_blocker: bool = False,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE sovereign_agent_jobs
            SET status = input.status,
                workspace_id = COALESCE(input.workspace_id, sovereign_agent_jobs.workspace_id),
                external_ref = COALESCE(input.external_ref, sovereign_agent_jobs.external_ref),
                changed_files = CASE
                    WHEN input.changed_files IS NULL THEN sovereign_agent_jobs.changed_files
                    ELSE (
                        SELECT COALESCE(jsonb_agg(item ORDER BY item), '[]'::jsonb)
                        FROM (
                            SELECT DISTINCT jsonb_array_elements_text(
                                COALESCE(sovereign_agent_jobs.changed_files, '[]'::jsonb) || input.changed_files
                            ) AS item
                        ) merged_files
                    )
                END,
                diff_summary = CASE
                    WHEN input.diff_summary IS NULL THEN sovereign_agent_jobs.diff_summary
                    WHEN sovereign_agent_jobs.diff_summary IS NULL OR sovereign_agent_jobs.diff_summary = '' THEN input.diff_summary
                    ELSE LEFT(sovereign_agent_jobs.diff_summary || E'\n---\n' || input.diff_summary, 12000)
                END,
                test_summary = CASE
                    WHEN input.test_summary IS NULL THEN sovereign_agent_jobs.test_summary
                    WHEN sovereign_agent_jobs.test_summary IS NULL OR sovereign_agent_jobs.test_summary = '' THEN input.test_summary
                    ELSE LEFT(sovereign_agent_jobs.test_summary || E'\n---\n' || input.test_summary, 12000)
                END,
                draft_pr_url = COALESCE(input.draft_pr_url, sovereign_agent_jobs.draft_pr_url),
                blocker = CASE
                    WHEN input.clear_blocker THEN NULL
                    ELSE COALESCE(input.blocker, sovereign_agent_jobs.blocker)
                END
            FROM (
                SELECT %s::text AS status,
                       %s::text AS workspace_id,
                       %s::text AS external_ref,
                       %s::jsonb AS changed_files,
                       %s::text AS diff_summary,
                       %s::text AS test_summary,
                       %s::text AS draft_pr_url,
                       %s::boolean AS clear_blocker,
                       %s::text AS blocker,
                       %s::text AS job_id
            ) AS input
            WHERE sovereign_agent_jobs.job_id = input.job_id
            """,
            (
                status,
                workspace_id,
                external_ref,
                _json(list(changed_files)) if changed_files is not None else None,
                sanitize_agent_text(diff_summary, 4000) if diff_summary else None,
                sanitize_agent_text(test_summary, 4000) if test_summary else None,
                draft_pr_url if draft_pr_url and draft_pr_url.startswith("https://github.com/") else None,
                bool(clear_blocker),
                sanitize_agent_text(blocker, 1200) if blocker else None,
                job_id,
            ),
        )
    conn.commit()


def mark_draft_pr_prepared(
    conn: Any,
    *,
    job_id: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
) -> None:
    preparation = {
        "headBranch": sanitize_agent_text(head_branch, 160),
        "baseBranch": sanitize_agent_text(base_branch, 160),
        "title": sanitize_agent_text(title, 200),
        "body": sanitize_agent_text(body, 8000),
    }
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE sovereign_agent_jobs
            SET status = 'validating',
                pr_state = 'ready',
                branch_name = %s,
                target_branch = %s,
                commit_message = %s,
                draft_pr_preparation = %s::jsonb,
                blocker = NULL
            WHERE job_id = %s
            """,
            (
                preparation["headBranch"],
                preparation["baseBranch"],
                preparation["title"],
                _json(preparation),
                job_id,
            ),
        )
    conn.commit()


def mark_draft_pr_created(
    conn: Any,
    *,
    job_id: str,
    pr_url: str,
    commit: bool = True,
) -> None:
    safe_pr_url = pr_url.strip() if pr_url.startswith("https://github.com/") and "/pull/" in pr_url else ""
    if not safe_pr_url:
        raise ValueError("valid GitHub pull request URL required")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE sovereign_agent_jobs
            SET status = 'completed',
                pr_state = 'created',
                pr_url = %s,
                draft_pr_url = %s,
                blocker = NULL
            WHERE job_id = %s
            """,
            (safe_pr_url, safe_pr_url, job_id),
        )
    if commit:
        conn.commit()


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
    return stored_job_from_row(row) if row else None


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
    return tuple(stored_job_from_row(row) for row in rows)


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
        # Migration 004: Draft PR fields
        draft_pr_preparation=job.draft_pr_preparation,
        branch_name=job.branch_name,
        target_branch=job.target_branch,
        commit_message=job.commit_message,
        pr_url=job.pr_url,
        pr_state=job.pr_state,
    )
