"""Android-first controller board backed only by real Sovereign runtime evidence."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import time
import uuid
from typing import Any, Callable

import requests
from flask import jsonify, make_response, request

from agent_runtime.cognitive_run_store import (
    AgentRunIterationLimit,
    AgentRunNotResumable,
    AgentRunResumeConflict,
    claim_agent_run_for_resume,
    create_agent_run,
    create_agent_task,
    transition_agent_run,
)
from agent_runtime.cognitive_swarm_manifest import manifest_payload
from agent_runtime.cognitive_swarm_routes import execute_persisted_swarm
from agent_runtime.job_lifecycle import create_sovereign_agent_job
from security_oauth import _decrypt_token


ConnectionFactory = Callable[[], Any]
_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_IMPLEMENTATION_ACTION_PATTERN = re.compile(
    r"\b(?:fix(?:e|en)?|beheb(?:e|en)?|reparier(?:e|en)?|implement(?:iere|ieren)?|patch(?:e|en)?|"
    r"änder(?:e|n)?|schreib(?:e|en)?|erstell(?:e|en)?|refactor(?:e|en)?|migrier(?:e|en)?)\b",
    re.IGNORECASE,
)
_IMPLEMENTATION_TARGET_PATTERN = re.compile(
    r"\b(?:code|datei(?:en)?|repository|repo|backend|frontend|endpoint|route|test(?:s)?|workflow|"
    r"workspace|draft[- ]?pr|pull request|bug|fehler)\b",
    re.IGNORECASE,
)
_OPERATOR_SECRET_MARKERS = (
    "sk-proj-",
    "github_pat_",
    "ghp_",
    "authorization: bearer",
    "begin openssh private key",
    "begin rsa private key",
)


def _service_authorized() -> bool:
    expected = os.getenv("SOVEREIGN_OWNER_REQUEST_KEY", "").strip()
    supplied = request.headers.get("X-Sovereign-Owner-Request-Key", "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _operator_contains_secret(value: str) -> bool:
    normalized = str(value or "").casefold()
    return any(marker in normalized for marker in _OPERATOR_SECRET_MARKERS)


def _operator_owner_user_id(conn: Any) -> str:
    expected_id = os.getenv("SOVEREIGN_OWNER_ADMIN_ID", "").strip()
    expected_email = os.getenv("SOVEREIGN_OWNER_ADMIN_EMAIL", "").strip().lower()
    with conn.cursor() as cur:
        if expected_id:
            cur.execute("SELECT id::text FROM admin_users WHERE id=%s::uuid LIMIT 1", (expected_id,))
        elif expected_email:
            cur.execute("SELECT id::text FROM admin_users WHERE lower(email)=lower(%s) LIMIT 1", (expected_email,))
        else:
            raise RuntimeError("Sovereign owner identity is not configured")
        row = cur.fetchone()
    if not row:
        raise LookupError("Configured Sovereign owner was not found")
    return str(row["id"])


def _operator_resume_lease_seconds() -> int:
    try:
        configured = int(os.getenv("SOVEREIGN_AGENTS_RESUME_LEASE_SECONDS", "900"))
    except ValueError:
        configured = 900
    return max(30, min(configured, 3600))


def _operator_max_iterations() -> int:
    try:
        configured = int(os.getenv("SOVEREIGN_AGENTS_MAX_ITERATIONS", "12"))
    except ValueError:
        configured = 12
    return max(1, min(configured, 100))


def _operator_json(payload: dict[str, Any], status: int = 200):
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response, status


def _close(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def _mission_requires_repository_execution(mission: str) -> bool:
    normalized = str(mission or "").strip()
    return bool(
        normalized
        and _IMPLEMENTATION_ACTION_PATTERN.search(normalized)
        and _IMPLEMENTATION_TARGET_PATTERN.search(normalized)
    )


def _controller_workspace_root() -> Path | None:
    configured = os.getenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", "").strip()
    return Path(configured) if configured else None


def _controller_repository() -> str:
    value = os.getenv(
        "SOVEREIGN_CONTROLLER_REPOSITORY",
        "OuroborosCollective/Sovereign-Studio-ato",
    ).strip()
    if not _REPOSITORY_PATTERN.fullmatch(value):
        raise RuntimeError("SOVEREIGN_CONTROLLER_REPOSITORY is invalid")
    return value


def _github_headers(session_token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "sovereign-controller-board/1.0",
    }
    token = (
        os.getenv("TOOLCHAIN_GITHUB_TOKEN", "").strip()
        or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "").strip()
        or str(session_token or "").strip()
    )
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_get(path: str, *, token: str | None = None) -> Any:
    response = requests.get(
        f"https://api.github.com{path}",
        headers=_github_headers(token),
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def _iso(value: object) -> str:
    return str(value or "")


_FAILURE_DIAGNOSTIC_KEYS = (
    "failureStage",
    "failureFamily",
    "errorType",
    "nextAction",
    "retryable",
    "httpStatus",
    "requestId",
    "rawErrorPersisted",
)


def _bounded_failure_diagnostics(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}
    return {
        key: payload.get(key)
        for key in _FAILURE_DIAGNOSTIC_KEYS
        if key in payload
    }


def _json_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


_TERMINAL_RUN_STATUSES = frozenset({
    "FAILED_FINAL",
    "READY_FOR_DRAFT_PR",
    "DRAFT_PR_CREATED",
    "COMPLETED",
})
_TERMINAL_TASK_STATUSES = frozenset({"COMPLETED", "FAILED_FINAL", "DRAFT_PR_CREATED"})
_BLOCKING_TASK_STATUSES = frozenset({"BLOCKED", "FAILED_RECOVERABLE", "FAILED_FINAL"})


def _current_task_id(run: dict[str, Any], tasks: list[dict[str, Any]]) -> str | None:
    persisted = str(run.get("resume_task_id") or "").strip()
    if persisted:
        return persisted
    if not tasks:
        return None
    return str(tasks[-1].get("task_id") or "").strip() or None


def _task_runtime_view(
    task: dict[str, Any],
    *,
    run_status: str,
    current_task_id: str | None,
) -> dict[str, Any]:
    task_id = str(task.get("task_id") or "")
    status = str(task.get("status") or "")
    is_current = bool(current_task_id and task_id == current_task_id)
    run_terminal = run_status in _TERMINAL_RUN_STATUSES
    return {
        **task,
        "taskLifecycle": "current" if is_current else "historical",
        "isCurrentTask": is_current,
        "isActiveTask": is_current and not run_terminal and status not in _TERMINAL_TASK_STATUSES,
        "isActiveBlocker": is_current and not run_terminal and status in _BLOCKING_TASK_STATUSES,
        "resolvedByTaskId": current_task_id if not is_current else None,
    }


def _release_hunt_payload(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    outcome = str(value.get("outcome") or "").strip().upper()
    if outcome not in {"FINDING", "NULLFIND", "BLOCKED"}:
        return {}
    return {
        "outcome": outcome,
        "errorFamily": str(value.get("errorFamily") or "")[:160],
        "nextErrorFamily": str(value.get("nextErrorFamily") or "")[:160],
        "nullfindConfirmed": bool(value.get("nullfindConfirmed")),
    }


def register_controller_board_routes(
    app: Any,
    *,
    require_session: Callable,
    get_connection: ConnectionFactory,
) -> None:
    @app.route("/controller")
    @app.route("/controller/")
    def sovereign_controller_board():
        response = make_response(_CONTROLLER_HTML)
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'; connect-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
        )
        return response

    @app.route("/api/internal/controller/runs", methods=["GET"])
    def operator_controller_runs():
        if not _service_authorized():
            return _operator_json({"error": "not authorized"}, 401)
        try:
            limit = max(1, min(int(request.args.get("limit") or 20), 100))
        except ValueError:
            return _operator_json({"error": "limit is invalid"}, 400)
        conn = get_connection()
        try:
            owner_id = _operator_owner_user_id(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT run_id, session_key, status, source, evidence_id, trace_id,
                              reason, next_action, mission_summary, iteration_count,
                              max_iterations, created_at, updated_at,
                              (lease_token IS NOT NULL AND lease_expires_at > NOW()) AS lease_active
                       FROM agent_runs WHERE user_id=%s::uuid
                       ORDER BY updated_at DESC LIMIT %s""",
                    (owner_id, limit),
                )
                rows = [dict(row) for row in cur.fetchall()]
            return _operator_json({
                "ok": True,
                "ownerUserId": owner_id,
                "runs": [
                    {key: _iso(value) if key.endswith("_at") else value for key, value in row.items()}
                    for row in rows
                ],
            })
        finally:
            _close(conn)

    @app.route("/api/internal/controller/runs", methods=["POST"])
    def operator_controller_run_start():
        if not _service_authorized():
            return _operator_json({"error": "not authorized"}, 401)
        body = request.get_json(force=True) or {}
        mission = str(body.get("mission") or "").strip()
        evidence = str(body.get("evidence") or "").strip()
        if not mission:
            return _operator_json({"error": "mission is required"}, 400)
        if len(mission) > 20_000:
            return _operator_json({"error": "mission exceeds the bounded input limit"}, 400)
        if len(evidence) > 250_000:
            return _operator_json({"error": "evidence exceeds the bounded input limit"}, 400)
        if _operator_contains_secret(mission) or _operator_contains_secret(evidence):
            return _operator_json({"error": "secret-shaped material is forbidden in operator input"}, 400)

        manifest = manifest_payload()
        run_id = f"run-{uuid.uuid4().hex}"
        session_key = f"session-{uuid.uuid4().hex}"
        trace_id = f"trace-{uuid.uuid4().hex}"
        conn = get_connection()
        try:
            owner_id = _operator_owner_user_id(conn)
            implementation_job = None
            if _mission_requires_repository_execution(mission):
                repository = _controller_repository()
                implementation_job = create_sovereign_agent_job(
                    conn,
                    user_id=owner_id,
                    payload={
                        "repoUrl": f"https://github.com/{repository}",
                        "branch": "main",
                        "mission": mission,
                        "executor": "sovereign-local-runner",
                        "draftPrOnly": True,
                        "allowAutoMerge": False,
                    },
                    workspace_root=_controller_workspace_root(),
                    provision_workspace=True,
                    clone_repo=True,
                )
                if implementation_job.result.status in {"blocked", "failed"}:
                    return _operator_json({
                        "ok": False,
                        "runtime": "sovereign-agent",
                        "status": "BLOCKED",
                        "jobId": implementation_job.job_id,
                        "workspaceId": implementation_job.result.workspace_id,
                        "blocker": implementation_job.result.blocker or "IMPLEMENTATION_JOB_PROVISIONING_FAILED",
                        "reason": "The real repository workspace could not be provisioned.",
                        "nextAction": "FIX_WORKSPACE_PROVISIONING_AND_RERUN",
                        "protectedValuesReturned": False,
                    }, 503)

            received_state = create_agent_run(
                conn,
                user_id=owner_id,
                run_id=run_id,
                session_key=session_key,
                mission=mission,
                supplied_evidence=evidence,
                trace_id=trace_id,
                max_active_specialists=int(manifest["maxActiveSpecialists"]),
                max_iterations=_operator_max_iterations(),
                job_id=implementation_job.job_id if implementation_job else None,
            )
            if implementation_job:
                task_id = _new_id("task-implementation")
                create_agent_task(
                    conn,
                    run_id=run_id,
                    task_id=task_id,
                    agent_id="implementation_coordinator",
                    specialist_role="repository_execution",
                    work_package=(
                        "Execute the authenticated code mission in the linked real repository workspace; "
                        "produce file, diff, test and Draft-PR-only evidence."
                    ),
                    evidence_id=received_state["evidenceId"],
                    status="WAITING_FOR_TOOL",
                    reason="A code mission was routed to the real Sovereign Agent Job runtime.",
                    next_action="EXECUTE_BOUNDED_REPOSITORY_TOOLS",
                    allowed_tools=("file", "git-status", "diff", "test", "draft-pr-prepare", "draft-pr-create"),
                    acceptance_criteria=(
                        "At least one actionable changed file is persisted.",
                        "Git diff evidence is non-empty and git diff --check passes.",
                        "Relevant tests or build checks pass.",
                        "At most one Draft PR is created and auto-merge remains disabled.",
                    ),
                    forbidden_actions=(
                        "persist or reveal secrets",
                        "merge a pull request",
                        "claim completion without diff and test evidence",
                    ),
                )
                routed_state = transition_agent_run(
                    conn,
                    user_id=owner_id,
                    run_id=run_id,
                    status="WAITING_FOR_TOOL",
                    source="agents-sdk",
                    trace_id=trace_id,
                    reason="Code mission is linked to a real repository workspace and awaits bounded tool execution.",
                    next_action="EXECUTE_BOUNDED_REPOSITORY_TOOLS",
                    evidence_kind="implementation_handoff",
                    evidence_summary="The controller materialized a real Agent Job, workspace and implementation task.",
                    evidence_payload={
                        "jobId": implementation_job.job_id,
                        "workspaceId": implementation_job.result.workspace_id,
                        "jobStatus": implementation_job.result.status,
                        "taskId": task_id,
                        "draftPrOnly": True,
                        "autoMerge": False,
                    },
                    agent_id="orchestrator",
                    task_id=task_id,
                )
                return _operator_json({
                    "ok": True,
                    "runtime": "sovereign-agent",
                    "runId": run_id,
                    "sessionKey": session_key,
                    "traceId": trace_id,
                    "status": routed_state["status"],
                    "source": routed_state["source"],
                    "evidenceId": routed_state["evidenceId"],
                    "reason": routed_state["reason"],
                    "nextAction": routed_state["nextAction"],
                    "jobId": implementation_job.job_id,
                    "workspaceId": implementation_job.result.workspace_id,
                    "taskId": task_id,
                    "jobStatus": implementation_job.result.status,
                    "changedFiles": list(implementation_job.result.changed_files),
                    "protectedValuesReturned": False,
                    "autoMerge": False,
                }, 202)
        except Exception as exc:
            return _operator_json({
                "ok": False,
                "runtime": "openai-agents-sdk",
                "error": "agent run persistence unavailable",
                "blocker": "AGENT_RUN_PERSISTENCE_UNAVAILABLE",
                "errorType": type(exc).__name__,
            }, 503)
        finally:
            _close(conn)

        payload, status_code = execute_persisted_swarm(
            get_connection=get_connection,
            user_id=owner_id,
            run_id=run_id,
            trace_id=trace_id,
            mission=mission,
            evidence=evidence,
            model=None,
            response_context={
                "sessionKey": session_key,
                "resumed": False,
                "operatorBridge": True,
                "receivedEvidenceId": received_state["evidenceId"],
                "protectedValuesReturned": False,
            },
        )
        return _operator_json(payload, status_code)

    @app.route("/api/internal/controller/runs/<run_id>", methods=["GET"])
    def operator_controller_run_status(run_id: str):
        if not _service_authorized():
            return _operator_json({"error": "not authorized"}, 401)
        conn = get_connection()
        try:
            owner_id = _operator_owner_user_id(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT * FROM agent_runs
                       WHERE run_id=%s AND user_id=%s::uuid LIMIT 1""",
                    (run_id, owner_id),
                )
                run = cur.fetchone()
                if not run:
                    return _operator_json({"error": "run not found"}, 404)
                cur.execute(
                    """SELECT event_id, task_id, agent_id, type, status, source,
                              summary, evidence_id, trace_id, next_action, created_at
                       FROM agent_events WHERE run_id=%s ORDER BY created_at ASC LIMIT 500""",
                    (run_id,),
                )
                events = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """SELECT task_id, agent_id, specialist_role, work_package, status,
                              source, reason, next_action, tool_call_count, max_tool_calls,
                              retry_count, max_retries, created_at, updated_at
                       FROM agent_tasks WHERE run_id=%s ORDER BY created_at ASC LIMIT 200""",
                    (run_id,),
                )
                tasks = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """SELECT f.failure_id, f.task_id, f.agent_id, f.family, f.recoverable,
                              f.summary, f.evidence_id, f.retry_after, f.created_at, f.resolved_at,
                              e.payload AS evidence_payload
                       FROM agent_failures f
                       LEFT JOIN agent_evidence e ON e.evidence_id=f.evidence_id
                       WHERE f.run_id=%s ORDER BY f.created_at ASC LIMIT 200""",
                    (run_id,),
                )
                failures = [dict(row) for row in cur.fetchall()]
                for failure in failures:
                    failure["diagnostics"] = _bounded_failure_diagnostics(
                        failure.pop("evidence_payload", None)
                    )
                cur.execute(
                    """SELECT approval_id, task_id, kind, status, requested_by_agent,
                              evidence_id, reason, created_at, decided_at
                       FROM agent_approvals WHERE run_id=%s ORDER BY created_at ASC LIMIT 100""",
                    (run_id,),
                )
                approvals = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """SELECT payload->'releaseHunt' AS release_hunt
                       FROM agent_evidence
                       WHERE run_id=%s AND kind='judge_verdict'
                       ORDER BY created_at DESC LIMIT 1""",
                    (run_id,),
                )
                hunt_row = cur.fetchone()
            run_dict = dict(run)
            current_task_id = _current_task_id(run_dict, tasks)
            tasks = [
                _task_runtime_view(
                    task,
                    run_status=str(run_dict.get("status") or ""),
                    current_task_id=current_task_id,
                )
                for task in tasks
            ]
            release_hunt = _release_hunt_payload((hunt_row or {}).get("release_hunt"))
            normalize = lambda row: {
                key: _iso(value) if key.endswith("_at") else value
                for key, value in row.items()
            }
            return _operator_json({
                "ok": True,
                "run": normalize(run_dict),
                "releaseHunt": release_hunt,
                "events": [normalize(row) for row in events],
                "tasks": [normalize(row) for row in tasks],
                "failures": [normalize(row) for row in failures],
                "approvals": [normalize(row) for row in approvals],
                "protectedValuesReturned": False,
            })
        finally:
            _close(conn)

    @app.route("/api/internal/controller/runs/<run_id>/resume", methods=["POST"])
    def operator_controller_run_resume(run_id: str):
        if not _service_authorized():
            return _operator_json({"error": "not authorized"}, 401)
        body = request.get_json(force=True) or {}
        evidence = str(body.get("evidence") or "").strip()
        if len(evidence) > 250_000:
            return _operator_json({"error": "evidence exceeds the bounded input limit"}, 400)
        if _operator_contains_secret(evidence):
            return _operator_json({"error": "secret-shaped material is forbidden in operator evidence"}, 400)
        trace_id = f"trace-{uuid.uuid4().hex}"
        conn = get_connection()
        try:
            owner_id = _operator_owner_user_id(conn)
            claim = claim_agent_run_for_resume(
                conn,
                user_id=owner_id,
                run_id=run_id,
                supplied_evidence=evidence,
                trace_id=trace_id,
                lease_seconds=_operator_resume_lease_seconds(),
            )
        except LookupError:
            return _operator_json({"error": "run not found"}, 404)
        except AgentRunResumeConflict as exc:
            return _operator_json({
                "ok": False,
                "runId": run_id,
                "status": "RUNNING",
                "blocker": "RUN_ALREADY_CLAIMED",
                "reason": str(exc),
            }, 409)
        except AgentRunIterationLimit as exc:
            return _operator_json({
                "ok": False,
                "runId": run_id,
                "blocker": "RUN_ITERATION_LIMIT_EXHAUSTED",
                "reason": str(exc),
            }, 409)
        except AgentRunNotResumable as exc:
            return _operator_json({
                "ok": False,
                "runId": run_id,
                "blocker": "RUN_NOT_RESUMABLE",
                "reason": str(exc),
            }, 409)
        finally:
            _close(conn)

        resume_context = {
            "persistedRunId": claim.run.run_id,
            "persistedMissionDigest": claim.run.mission_digest,
            "previousStatus": claim.run.status,
            "previousEvidenceId": claim.run.evidence_id,
            "recoveryTaskId": claim.task_id,
            "recoveryWorkPackage": claim.work_package,
            "operatorBridge": True,
            "protectedValuesReturned": False,
        }
        execution_evidence = (
            "Persisted operator resume context:\n"
            f"{json.dumps(resume_context, ensure_ascii=False, sort_keys=True)}\n\n"
            "New bounded operator evidence:\n"
            f"{evidence or '[no new evidence supplied]'}"
        )
        payload, status_code = execute_persisted_swarm(
            get_connection=get_connection,
            user_id=owner_id,
            run_id=claim.run.run_id,
            trace_id=trace_id,
            mission=claim.run.mission_summary,
            evidence=execution_evidence,
            model=None,
            task_id=claim.task_id,
            lease_token=claim.lease_token,
            response_context={
                "sessionKey": claim.run.session_key,
                "resumed": True,
                "operatorBridge": True,
                "resumeClaimEvidenceId": claim.evidence_id,
                "recoveryTask": {
                    "taskId": claim.task_id,
                    "workPackage": claim.work_package,
                    "leaseSeconds": claim.lease_seconds,
                },
            },
        )
        return _operator_json(payload, status_code)

    @app.route("/api/controller/overview", methods=["GET"])
    @require_session
    def controller_overview():
        user_id = str(request.session_user_id)
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT status, COUNT(*)::integer AS count
                       FROM agent_runs WHERE user_id=%s::uuid GROUP BY status""",
                    (user_id,),
                )
                status_counts = {str(row["status"]): int(row["count"]) for row in cur.fetchall()}
                cur.execute(
                    """SELECT run_id, session_key, status, source, evidence_id, trace_id,
                              reason, next_action, mission_summary, iteration_count,
                              max_iterations, updated_at, created_at,
                              (lease_token IS NOT NULL AND lease_expires_at > NOW()) AS lease_active
                       FROM agent_runs WHERE user_id=%s::uuid
                       ORDER BY updated_at DESC LIMIT 20""",
                    (user_id,),
                )
                runs = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """SELECT t.agent_id, t.specialist_role, t.status, t.source,
                              t.reason, t.next_action, t.updated_at, t.run_id, t.task_id,
                              r.status AS run_status
                       FROM agent_runs r
                       JOIN LATERAL (
                           SELECT task_id, agent_id, specialist_role, status, source,
                                  reason, next_action, updated_at, run_id
                           FROM agent_tasks
                           WHERE run_id=r.run_id
                           ORDER BY created_at DESC LIMIT 1
                       ) t ON TRUE
                       WHERE r.user_id=%s::uuid
                         AND r.status NOT IN ('COMPLETED','FAILED_FINAL','DRAFT_PR_CREATED')
                         AND t.status NOT IN ('COMPLETED','FAILED_FINAL','DRAFT_PR_CREATED')
                       ORDER BY t.updated_at DESC LIMIT 50""",
                    (user_id,),
                )
                active_tasks = []
                for row in cur.fetchall():
                    task = dict(row)
                    run_status = str(task.pop("run_status", "") or "")
                    active_tasks.append(
                        _task_runtime_view(
                            task,
                            run_status=run_status,
                            current_task_id=str(task.get("task_id") or "") or None,
                        )
                    )
                cur.execute(
                    """SELECT
                         (SELECT COUNT(*) FROM agent_evidence e JOIN agent_runs r ON r.run_id=e.run_id WHERE r.user_id=%s::uuid)::integer AS evidence_count,
                         (SELECT COUNT(*) FROM agent_tool_calls t JOIN agent_runs r ON r.run_id=t.run_id WHERE r.user_id=%s::uuid)::integer AS tool_call_count,
                         (SELECT COUNT(*) FROM agent_failures f JOIN agent_runs r ON r.run_id=f.run_id WHERE r.user_id=%s::uuid AND f.resolved_at IS NULL)::integer AS unresolved_failures,
                         (SELECT COUNT(*) FROM agent_approvals a JOIN agent_runs r ON r.run_id=a.run_id WHERE r.user_id=%s::uuid AND a.status='WAITING_FOR_OWNER')::integer AS pending_approvals""",
                    (user_id, user_id, user_id, user_id),
                )
                totals = dict(cur.fetchone() or {})
            return jsonify({
                "ok": True,
                "runtime": "openai-agents-sdk",
                "statusCounts": status_counts,
                "runs": [
                    {
                        **row,
                        "created_at": _iso(row.get("created_at")),
                        "updated_at": _iso(row.get("updated_at")),
                    }
                    for row in runs
                ],
                "activeTasks": [
                    {**row, "updated_at": _iso(row.get("updated_at"))}
                    for row in active_tasks
                ],
                "totals": totals,
                "refreshedAt": int(time.time()),
            })
        finally:
            _close(conn)

    @app.route("/api/controller/runs/<run_id>", methods=["GET"])
    @require_session
    def controller_run_detail(run_id: str):
        user_id = str(request.session_user_id)
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT * FROM agent_runs
                       WHERE run_id=%s AND user_id=%s::uuid LIMIT 1""",
                    (run_id, user_id),
                )
                run = cur.fetchone()
                if not run:
                    return jsonify({"error": "run not found"}), 404
                cur.execute(
                    """SELECT event_id, task_id, agent_id, type, status, source,
                              summary, evidence_id, trace_id, next_action, created_at
                       FROM agent_events WHERE run_id=%s ORDER BY created_at ASC LIMIT 250""",
                    (run_id,),
                )
                events = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """SELECT task_id, agent_id, specialist_role, work_package, status,
                              source, reason, next_action, tool_call_count, max_tool_calls,
                              retry_count, max_retries, updated_at
                       FROM agent_tasks WHERE run_id=%s ORDER BY created_at ASC LIMIT 100""",
                    (run_id,),
                )
                tasks = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """SELECT f.failure_id, f.task_id, f.agent_id, f.family, f.recoverable,
                              f.summary, f.evidence_id, f.retry_after, f.created_at, f.resolved_at,
                              e.payload AS evidence_payload
                       FROM agent_failures f
                       LEFT JOIN agent_evidence e ON e.evidence_id=f.evidence_id
                       WHERE f.run_id=%s ORDER BY f.created_at ASC LIMIT 100""",
                    (run_id,),
                )
                failures = [dict(row) for row in cur.fetchall()]
                for failure in failures:
                    failure["diagnostics"] = _bounded_failure_diagnostics(
                        failure.pop("evidence_payload", None)
                    )
                cur.execute(
                    """SELECT payload->'releaseHunt' AS release_hunt
                       FROM agent_evidence
                       WHERE run_id=%s AND kind='judge_verdict'
                       ORDER BY created_at DESC LIMIT 1""",
                    (run_id,),
                )
                hunt_row = cur.fetchone()
            run_dict = dict(run)
            current_task_id = _current_task_id(run_dict, tasks)
            tasks = [
                _task_runtime_view(
                    task,
                    run_status=str(run_dict.get("status") or ""),
                    current_task_id=current_task_id,
                )
                for task in tasks
            ]
            return jsonify({
                "run": {key: _iso(value) if key.endswith("_at") else value for key, value in run_dict.items()},
                "releaseHunt": _release_hunt_payload((hunt_row or {}).get("release_hunt")),
                "events": [{key: _iso(value) if key.endswith("_at") else value for key, value in row.items()} for row in events],
                "tasks": [{key: _iso(value) if key.endswith("_at") else value for key, value in row.items()} for row in tasks],
                "failures": [{key: _iso(value) if key.endswith("_at") else value for key, value in row.items()} for row in failures],
            })
        finally:
            _close(conn)

    @app.route("/api/controller/approvals", methods=["GET"])
    @require_session
    def controller_approvals():
        user_id = str(request.session_user_id)
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.approval_id, a.run_id, a.task_id, a.kind, a.status,
                              a.protected_input_ref, a.requested_by_agent, a.evidence_id,
                              a.reason, a.created_at, r.mission_summary, r.next_action
                       FROM agent_approvals a
                       JOIN agent_runs r ON r.run_id=a.run_id
                       WHERE r.user_id=%s::uuid AND a.status='WAITING_FOR_OWNER'
                       ORDER BY a.created_at ASC LIMIT 50""",
                    (user_id,),
                )
                rows = [dict(row) for row in cur.fetchall()]
            return jsonify({
                "approvals": [
                    {
                        **row,
                        "created_at": _iso(row.get("created_at")),
                        "requiresProtectedOwnerInput": bool(row.get("protected_input_ref")),
                    }
                    for row in rows
                ]
            })
        finally:
            _close(conn)

    @app.route("/api/controller/approvals/<approval_id>/decision", methods=["POST"])
    @require_session
    def controller_approval_decision(approval_id: str):
        user_id = str(request.session_user_id)
        body = request.get_json(force=True) or {}
        decision = str(body.get("decision") or "").strip().lower()
        if decision not in {"approve", "reject"}:
            return jsonify({"error": "decision must be approve or reject"}), 400
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.*, r.trace_id, r.status AS run_status
                       FROM agent_approvals a
                       JOIN agent_runs r ON r.run_id=a.run_id
                       WHERE a.approval_id=%s AND r.user_id=%s::uuid
                       LIMIT 1 FOR UPDATE""",
                    (approval_id, user_id),
                )
                approval = cur.fetchone()
                if not approval:
                    return jsonify({"error": "approval not found"}), 404
                if approval["status"] != "WAITING_FOR_OWNER":
                    return jsonify({"error": "approval already decided"}), 409
                if approval.get("protected_input_ref"):
                    return jsonify({
                        "error": "protected owner input must be completed in the owner approval surface",
                        "blocker": "PROTECTED_OWNER_INPUT_REQUIRED",
                        "ownerUrl": "/owner-approvals",
                    }), 409

                approved = decision == "approve"
                approval_status = "APPROVED" if approved else "REJECTED"
                approval_kind = str(approval.get("kind") or "")
                draft_pr_approval = approved and approval_kind == "draft_pr_readiness"
                run_status = (
                    "READY_FOR_DRAFT_PR"
                    if draft_pr_approval
                    else "QUEUED" if approved
                    else "BLOCKED"
                )
                next_action = (
                    "CREATE_DRAFT_PR_AFTER_OWNER_APPROVAL"
                    if draft_pr_approval
                    else f"RESUME_FROM_OWNER_APPROVAL:{approval_id}"
                    if approved
                    else "OWNER_REJECTED_REVIEW_OR_NEW_MISSION"
                )
                reason = (
                    "Authenticated active user approved the pending agent request."
                    if approved
                    else "Authenticated active user rejected the pending agent request."
                )
                evidence_payload = {
                    "approvalId": approval_id,
                    "decision": decision,
                    "activeUserConfirmed": True,
                    "protectedValueReturned": False,
                }
                evidence_id = _new_id("evidence")
                event_id = _new_id("event")
                trace_id = str(approval.get("trace_id") or f"trace-{uuid.uuid4().hex}")
                payload_json = json.dumps(evidence_payload, sort_keys=True, separators=(",", ":"))
                cur.execute(
                    """INSERT INTO agent_evidence
                       (evidence_id, run_id, task_id, agent_id, source, kind, summary, sha256, payload)
                       VALUES (%s,%s,%s,'owner','agents-sdk','owner_decision',%s,%s,%s::jsonb)""",
                    (
                        evidence_id,
                        approval["run_id"],
                        approval.get("task_id"),
                        reason,
                        _json_digest(evidence_payload),
                        payload_json,
                    ),
                )
                cur.execute(
                    """UPDATE agent_approvals
                       SET status=%s, decided_by_user=%s::uuid, decided_at=NOW()
                       WHERE approval_id=%s AND status='WAITING_FOR_OWNER'""",
                    (approval_status, user_id, approval_id),
                )
                cur.execute(
                    """UPDATE agent_runs
                       SET status=%s, source='agents-sdk', evidence_id=%s,
                           reason=%s, next_action=%s, lease_token=NULL,
                           lease_expires_at=NULL, resume_task_id=NULL
                       WHERE run_id=%s AND user_id=%s::uuid AND status='WAITING_FOR_OWNER'
                       RETURNING run_id""",
                    (run_status, evidence_id, reason, next_action, approval["run_id"], user_id),
                )
                if not cur.fetchone():
                    raise ValueError("agent run is no longer waiting for owner decision")
                if approval.get("task_id"):
                    cur.execute(
                        """UPDATE agent_tasks
                           SET status=%s, source='agents-sdk', evidence_id=%s,
                               reason=%s, next_action=%s
                           WHERE task_id=%s AND run_id=%s AND status='WAITING_FOR_OWNER'""",
                        (
                            run_status,
                            evidence_id,
                            reason,
                            next_action,
                            approval["task_id"],
                            approval["run_id"],
                        ),
                    )
                cur.execute(
                    """INSERT INTO agent_events
                       (event_id, run_id, task_id, agent_id, type, status, source,
                        summary, evidence_id, trace_id, next_action)
                       VALUES (%s,%s,%s,'owner','owner_decision',%s,'agents-sdk',%s,%s,%s,%s)""",
                    (
                        event_id,
                        approval["run_id"],
                        approval.get("task_id"),
                        run_status,
                        reason,
                        evidence_id,
                        trace_id,
                        next_action,
                    ),
                )
            conn.commit()
            return jsonify({
                "ok": True,
                "approvalId": approval_id,
                "runId": approval["run_id"],
                "status": run_status,
                "resumeRequired": approved and not draft_pr_approval,
                "resumeEvidence": (
                    f"Authenticated active user approved approval {approval_id}. "
                    "No protected value was included."
                    if approved
                    else ""
                ),
                "nextAction": next_action,
            })
        except Exception:
            rollback = getattr(conn, "rollback", None)
            if callable(rollback):
                rollback()
            raise
        finally:
            _close(conn)

    @app.route("/api/controller/github", methods=["GET"])
    @require_session
    def controller_github_monitor():
        repository = _controller_repository()
        encoded_repo = "/".join(part for part in repository.split("/"))
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT github_access_token FROM admin_users WHERE id=%s::uuid LIMIT 1",
                    (str(request.session_user_id),),
                )
                token_row = cur.fetchone()
        finally:
            _close(conn)
        encrypted_token = str((token_row or {}).get("github_access_token") or "")
        session_token = _decrypt_token(encrypted_token) if encrypted_token else None
        try:
            commits = _github_get(
                f"/repos/{encoded_repo}/commits?sha=main&per_page=15",
                token=session_token,
            )
            latest_sha = str((commits or [{}])[0].get("sha") or "")
            latest = (
                _github_get(f"/repos/{encoded_repo}/commits/{latest_sha}", token=session_token)
                if latest_sha else {}
            )
            runs_payload = _github_get(
                f"/repos/{encoded_repo}/actions/runs?branch=main&per_page=50",
                token=session_token,
            )
        except requests.RequestException as exc:
            status = int(getattr(exc.response, "status_code", 502) or 502)
            return jsonify({
                "error": "GitHub runtime evidence unavailable",
                "status": status,
                "repository": repository,
            }), 502

        workflow_runs = list((runs_payload or {}).get("workflow_runs") or [])
        playwright_runs = [
            run for run in workflow_runs
            if any(
                marker in f"{run.get('name', '')} {run.get('display_title', '')}".lower()
                for marker in ("playwright", "e2e", "browser", "visual", "smoke")
            )
        ]
        def commit_api(item: dict[str, Any]) -> dict[str, object]:
            commit = item.get("commit") or {}
            author = commit.get("author") or {}
            return {
                "sha": str(item.get("sha") or ""),
                "message": str(commit.get("message") or "").splitlines()[0][:240],
                "author": str(author.get("name") or ""),
                "date": str(author.get("date") or ""),
                "url": str(item.get("html_url") or ""),
            }
        def run_api(item: dict[str, Any]) -> dict[str, object]:
            return {
                "id": int(item.get("id") or 0),
                "name": str(item.get("name") or ""),
                "title": str(item.get("display_title") or ""),
                "status": str(item.get("status") or ""),
                "conclusion": str(item.get("conclusion") or ""),
                "event": str(item.get("event") or ""),
                "headSha": str(item.get("head_sha") or ""),
                "createdAt": str(item.get("created_at") or ""),
                "updatedAt": str(item.get("updated_at") or ""),
                "url": str(item.get("html_url") or ""),
            }
        completed_playwright = [run for run in playwright_runs if run.get("status") == "completed"]
        successful_playwright = [run for run in completed_playwright if run.get("conclusion") == "success"]
        failed_playwright = [
            run for run in completed_playwright
            if run.get("conclusion") not in {"success", "neutral", "skipped"}
        ]
        running_playwright = [run for run in playwright_runs if run.get("status") != "completed"]
        success_rate = (
            round((len(successful_playwright) / len(completed_playwright)) * 100, 1)
            if completed_playwright else None
        )
        return jsonify({
            "repository": repository,
            "branch": "main",
            "commits": [commit_api(item) for item in (commits or [])[:15]],
            "latestCommit": {
                "sha": latest_sha,
                "message": str(((latest.get("commit") or {}).get("message") or "")).splitlines()[0][:240],
                "stats": dict(latest.get("stats") or {}),
                "files": [
                    {
                        "filename": str(item.get("filename") or ""),
                        "status": str(item.get("status") or ""),
                        "additions": int(item.get("additions") or 0),
                        "deletions": int(item.get("deletions") or 0),
                        "changes": int(item.get("changes") or 0),
                    }
                    for item in (latest.get("files") or [])[:100]
                ],
            },
            "workflowRuns": [run_api(item) for item in workflow_runs[:25]],
            "playwrightRuns": [run_api(item) for item in playwright_runs[:15]],
            "playwrightStats": {
                "total": len(playwright_runs),
                "completed": len(completed_playwright),
                "successful": len(successful_playwright),
                "failed": len(failed_playwright),
                "running": len(running_playwright),
                "successRate": success_rate,
            },
            "refreshedAt": int(time.time()),
        })


_CONTROLLER_HTML = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Sovereign Controller</title>
<style>
:root{color-scheme:dark;--bg:#080b10;--panel:#121821;--panel2:#19212c;--line:#2b3542;--text:#edf3f8;--muted:#91a0af;--ok:#52d273;--warn:#f1b84b;--bad:#ff6b6b;--accent:#69a7ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;min-height:100vh}button,input,textarea{font:inherit}button{min-height:48px;border:0;border-radius:12px;padding:.7rem 1rem;font-weight:700;cursor:pointer}.primary{background:var(--accent);color:#07111f}.ghost{background:var(--panel2);color:var(--text);border:1px solid var(--line)}.danger{background:#632b32;color:#fff}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.muted{color:var(--muted)}input,textarea{width:100%;min-height:48px;background:#0b1017;color:var(--text);border:1px solid var(--line);border-radius:12px;padding:.8rem}textarea{min-height:110px;resize:vertical}.shell{width:min(100%,1100px);margin:auto;padding:max(12px,env(safe-area-inset-top)) 12px max(20px,env(safe-area-inset-bottom))}.top{position:sticky;top:0;z-index:5;background:rgba(8,11,16,.94);backdrop-filter:blur(12px);padding:8px 0 12px}.head{display:flex;align-items:center;gap:10px}.head h1{font-size:1.05rem;margin:0}.head .state{margin-left:auto;font-size:.78rem}.tabs{display:flex;gap:8px;overflow:auto;padding-top:10px}.tabs button{white-space:nowrap;background:var(--panel);color:var(--muted);border:1px solid var(--line)}.tabs button.active{color:var(--text);border-color:var(--accent)}.view{display:none}.view.active{display:block}.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:14px;margin:10px 0}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.metric{background:var(--panel2);border-radius:13px;padding:12px}.metric strong{display:block;font-size:1.45rem}.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.between{justify-content:space-between}.badge{display:inline-flex;align-items:center;min-height:26px;padding:3px 9px;border-radius:999px;background:var(--panel2);font-size:.72rem;border:1px solid var(--line)}.list{display:grid;gap:8px}.item{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:11px;overflow-wrap:anywhere}.item h3{font-size:.92rem;margin:0 0 5px}.item p{font-size:.8rem;margin:4px 0;color:var(--muted)}.auth{width:min(100%,440px);margin:10vh auto}.hidden{display:none!important}.code{font-family:ui-monospace,monospace;font-size:.72rem;white-space:pre-wrap;overflow-wrap:anywhere}.timeline{border-left:2px solid var(--line);padding-left:12px}.timeline .item{margin:8px 0}.split{display:grid;gap:10px}.link{color:var(--accent);text-decoration:none}.notice{border-left:4px solid var(--warn)}@media(min-width:720px){.grid{grid-template-columns:repeat(4,minmax(0,1fr))}.split{grid-template-columns:1fr 1fr}.shell{padding-inline:20px}}@media(max-width:420px){.head h1{font-size:.95rem}.card{padding:12px}.tabs button{padding:.65rem .8rem}}
</style></head><body><main class="shell">
<section id="login" class="auth card"><h1>Sovereign Controller</h1><p class="muted">Diese Anmeldung erzeugt die echte Sovereign-Benutzersitzung für Agents-SDK-Läufe.</p><input id="email" type="email" placeholder="E-Mail" autocomplete="username"><input id="password" type="password" placeholder="Passwort" autocomplete="current-password" style="margin-top:8px"><button class="primary" style="width:100%;margin-top:10px" onclick="login()">Anmelden</button><p id="loginMsg" class="bad"></p></section>
<section id="app" class="hidden"><div class="top"><div class="head"><h1>Sovereign Controller Board</h1><span id="sessionState" class="state badge">Sitzung wird geprüft</span><button class="ghost" onclick="logout()">Abmelden</button></div><div class="tabs"><button class="active" data-view="overview">Monitor</button><button data-view="agents">Agenten</button><button data-view="code">Code</button><button data-view="playwright">Playwright</button><button data-view="approvals">Bestätigungen</button><button data-view="admin">Admin</button></div></div>
<section id="overview" class="view active"><div id="metrics" class="grid"></div><div class="split"><div class="card"><div class="row between"><h2>Aktive Agenten</h2><button class="ghost" onclick="refreshAll()">Aktualisieren</button></div><div id="activeAgents" class="list"></div></div><div class="card"><h2>Letzte Runs</h2><div id="recentRuns" class="list"></div></div></div></section>
<section id="agents" class="view"><div class="card"><h2>Neue Agents-SDK-Mission</h2><textarea id="mission" placeholder="Mission ohne Secrets"></textarea><textarea id="evidence" placeholder="Optionale Runtime-Evidence ohne Zugangsdaten" style="margin-top:8px"></textarea><div class="row" style="margin-top:10px"><button class="primary" onclick="startMission()">Mission starten</button><span id="missionMsg" class="muted"></span></div></div><div class="card"><h2>Run-Status</h2><div id="runs" class="list"></div></div><div id="runDetail" class="card hidden"></div></section>
<section id="code" class="view"><div class="card"><div class="row between"><h2>Commits & Änderungen</h2><button class="ghost" onclick="loadGithub()">Neu laden</button></div><div id="latestCommit"></div><div id="commits" class="list"></div></div></section>
<section id="playwright" class="view"><div id="playwrightMetrics" class="grid"></div><div class="card"><h2>Playwright / E2E Evidence</h2><p class="muted">Nur echte GitHub-Actions-Läufe; keine simulierten Browserzustände.</p><div id="playwrightRuns" class="list"></div></div><div class="card"><h2>Weitere Workflows</h2><div id="workflowRuns" class="list"></div></div></section>
<section id="approvals" class="view"><div class="card notice"><h2>Bestätigungen des aktiven Nutzers</h2><p class="muted">Zustimmung speichert Evidence und startet anschließend den echten Resume-Pfad. Geschützte Eingaben bleiben im Owner-Panel.</p><div id="approvalList" class="list"></div></div></section>
<section id="admin" class="view"><div class="card"><h2>Admin-Unlock</h2><p class="muted">Der Admin-Key bleibt nur im Arbeitsspeicher dieser Seite und wird nicht gespeichert.</p><input id="adminKey" type="password" placeholder="Admin API Key" autocomplete="off"><div class="row" style="margin-top:10px"><button class="primary" onclick="unlockAdmin()">Admin prüfen</button><button class="ghost" onclick="lockAdmin()">Sperren</button></div><p id="adminMsg" class="muted"></p></div><div class="card"><h2>Owner-Anfragen</h2><div id="ownerRequests" class="list"><p class="muted">Admin-Unlock erforderlich.</p></div></div></section>
</section></main><script>
let state={user:null,overview:null,github:null,adminKey:'',timer:null};const $=id=>document.getElementById(id);const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,opt={}){const r=await fetch(path,{credentials:'include',...opt,headers:{'Content-Type':'application/json',...(opt.headers||{})}});const t=await r.text();let d={};try{d=t?JSON.parse(t):{}}catch{d={error:t}}if(!r.ok)throw Object.assign(new Error(d.error||('HTTP '+r.status)),{status:r.status,data:d});return d}
async function login(){const password=$('password');try{await api('/api/auth/login',{method:'POST',body:JSON.stringify({email:$('email').value.trim(),password:password.value})});password.value='';await boot()}catch(e){password.value='';$('loginMsg').textContent=e.message}}
async function logout(){if(state.timer)clearInterval(state.timer);state.timer=null;state.adminKey='';try{await api('/api/auth/logout',{method:'POST',body:'{}'})}finally{location.reload()}}
async function boot(){try{state.user=await api('/api/auth/me');$('login').classList.add('hidden');$('app').classList.remove('hidden');$('sessionState').textContent=state.user.email+' · '+state.user.role;await refreshAll();if(state.timer)clearInterval(state.timer);state.timer=setInterval(refreshAll,15000)}catch(e){$('app').classList.add('hidden');$('login').classList.remove('hidden')}}
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));b.classList.add('active');$(b.dataset.view).classList.add('active')});
function badge(s){const c=['COMPLETED','READY_FOR_DRAFT_PR','success'].includes(s)?'ok':['FAILED_FINAL','failure','BLOCKED'].includes(s)?'bad':['WAITING_FOR_OWNER','queued','in_progress'].includes(s)?'warn':'muted';return `<span class="badge ${c}">${esc(s||'unknown')}</span>`}
async function refreshAll(){await Promise.allSettled([loadOverview(),loadApprovals(),loadGithub()]);if(state.adminKey)loadOwnerRequests()}
async function loadOverview(){const d=await api('/api/controller/overview');state.overview=d;const c=d.statusCounts||{},t=d.totals||{};$('metrics').innerHTML=[['Laufend',(c.RUNNING||0)+(c.VERIFYING||0)],['Warten',c.WAITING_FOR_OWNER||0],['Evidence',t.evidence_count||0],['Tool Calls',t.tool_call_count||0],['Fehler',t.unresolved_failures||0],['Bestätigungen',t.pending_approvals||0]].map(x=>`<div class="metric"><span class="muted">${x[0]}</span><strong>${x[1]}</strong></div>`).join('');$('activeAgents').innerHTML=(d.activeTasks||[]).map(x=>`<div class="item"><div class="row between"><h3>${esc(x.agent_id)} ${x.specialist_role?'· '+esc(x.specialist_role):''}</h3>${badge(x.status)}</div><p>${esc(x.reason)}</p><p>Nächster Schritt: ${esc(x.next_action)}</p></div>`).join('')||'<p class="muted">Keine aktiven Tasks.</p>';const runs=d.runs||[];$('recentRuns').innerHTML=runs.slice(0,6).map(runCard).join('')||'<p class="muted">Noch keine Runs.</p>';$('runs').innerHTML=runs.map(runCard).join('')||'<p class="muted">Noch keine Runs.</p>'}
function runCard(r){return `<div class="item"><div class="row between"><h3>${esc(r.mission_summary)}</h3>${badge(r.status)}</div><p class="code">${esc(r.run_id)}</p><p>${esc(r.reason)}</p><div class="row"><button class="ghost" onclick="runDetail('${esc(r.run_id)}')">Details</button>${!['COMPLETED','FAILED_FINAL','DRAFT_PR_CREATED','READY_FOR_DRAFT_PR','WAITING_FOR_OWNER'].includes(r.status)&&!r.lease_active?`<button class="primary" onclick="resumeRun('${esc(r.run_id)}','Manueller Resume aus Controller Board; keine Secrets.')">Resume</button>`:''}</div></div>`}
async function startMission(){const m=$('mission').value.trim();if(!m)return;$('missionMsg').textContent='Runtime läuft…';try{const d=await api('/api/user/agent/swarm/run',{method:'POST',body:JSON.stringify({mission:m,evidence:$('evidence').value.trim()})});$('missionMsg').textContent=(d.status||'')+' · '+(d.reason||'');await loadOverview();if(d.runId)runDetail(d.runId)}catch(e){$('missionMsg').textContent=(e.data?.status||'Fehler')+' · '+(e.data?.reason||e.message);await loadOverview()}}
async function resumeRun(id,evidence){try{const d=await api('/api/user/agent/swarm/runs/'+encodeURIComponent(id)+'/resume',{method:'POST',body:JSON.stringify({evidence})});await loadOverview();await runDetail(id);return d}catch(e){await loadOverview();alert(e.data?.reason||e.message)}}
async function runDetail(id){const d=await api('/api/controller/runs/'+encodeURIComponent(id));const r=d.run,h=d.releaseHunt||{};$('runDetail').classList.remove('hidden');$('runDetail').innerHTML=`<div class="row between"><h2>${esc(r.mission_summary)}</h2>${badge(r.status)}</div><p>${esc(r.reason)}</p>${h.outcome?`<div class="item"><div class="row between"><b>Release-Jagd · ${esc(h.errorFamily||'unbekannte Familie')}</b>${badge(h.outcome)}</div><p>Nullfund bestätigt: ${h.nullfindConfirmed?'ja':'nein'}</p>${h.nextErrorFamily?`<p>Nächste Familie: ${esc(h.nextErrorFamily)}</p>`:''}</div>`:''}<p class="code">Evidence: ${esc(r.evidence_id)}<br>Trace: ${esc(r.trace_id)}<br>Next: ${esc(r.next_action)}</p><h3>Tasks</h3><div class="list">${(d.tasks||[]).map(x=>`<div class="item"><div class="row between"><b>${esc(x.agent_id)}</b><span>${badge(x.status)} ${badge(x.taskLifecycle||'historical')}</span></div><p>${esc(x.work_package)}</p>${x.isActiveBlocker?'<p class="bad">Aktiver Blocker</p>':x.taskLifecycle==='historical'?'<p class="muted">Historische Evidence, kein aktiver Blocker.</p>':''}</div>`).join('')||'<p class="muted">Keine Tasks.</p>'}</div><h3>Failures</h3><div class="list">${(d.failures||[]).map(x=>{const q=x.diagnostics||{};return `<div class="item"><div class="row between"><b>${esc(x.family)}</b>${badge(x.recoverable?'FAILED_RECOVERABLE':'FAILED_FINAL')}</div><p>${esc(x.summary)}</p><p class="code">Stage: ${esc(q.failureStage||'unknown')}<br>Error: ${esc(q.errorType||'unknown')}<br>HTTP: ${esc(q.httpStatus??'–')}<br>Request: ${esc(q.requestId||'–')}<br>Next: ${esc(q.nextAction||'–')}</p></div>`}).join('')||'<p class="muted">Keine Failure-Evidence.</p>'}</div><h3>Events</h3><div class="timeline">${(d.events||[]).map(x=>`<div class="item"><b>${esc(x.agent_id)} · ${esc(x.type)}</b> ${badge(x.status)}<p>${esc(x.summary)}</p></div>`).join('')}</div>`;$('runDetail').scrollIntoView({behavior:'smooth'})}
async function loadApprovals(){const d=await api('/api/controller/approvals');$('approvalList').innerHTML=(d.approvals||[]).map(a=>`<div class="item"><div class="row between"><h3>${esc(a.kind)} · ${esc(a.requested_by_agent)}</h3>${badge(a.status)}</div><p>${esc(a.reason)}</p><p class="code">Run: ${esc(a.run_id)}</p>${a.requiresProtectedOwnerInput?`<a class="link" href="/owner-approvals" target="_blank">Geschützte Eingabe im Owner-Panel öffnen</a>`:`<div class="row"><button class="primary" onclick="decide('${esc(a.approval_id)}','approve')">Bestätigen</button><button class="danger" onclick="decide('${esc(a.approval_id)}','reject')">Ablehnen</button></div>`}</div>`).join('')||'<p class="muted">Keine offenen Bestätigungen.</p>'}
async function decide(id,decision){const d=await api('/api/controller/approvals/'+encodeURIComponent(id)+'/decision',{method:'POST',body:JSON.stringify({decision})});if(d.resumeRequired)await resumeRun(d.runId,d.resumeEvidence);await refreshAll()}
async function loadGithub(){try{const d=await api('/api/controller/github');state.github=d;const l=d.latestCommit||{},s=d.playwrightStats||{};$('latestCommit').innerHTML=`<div class="item"><div class="row between"><h3>${esc(l.message||'Kein Commit')}</h3><span class="badge">${esc((l.sha||'').slice(0,10))}</span></div><p>+${l.stats?.additions||0} / -${l.stats?.deletions||0} · ${l.stats?.total||0} Änderungen</p><div class="code">${(l.files||[]).slice(0,30).map(f=>esc(f.status)+' '+esc(f.filename)+' (+'+f.additions+' -'+f.deletions+')').join('\n')}</div></div>`;$('commits').innerHTML=(d.commits||[]).map(c=>`<div class="item"><div class="row between"><h3>${esc(c.message)}</h3><span class="badge">${esc(c.sha.slice(0,8))}</span></div><p>${esc(c.author)} · ${esc(c.date)}</p></div>`).join('');$('playwrightMetrics').innerHTML=[['Erfolg',s.successful||0],['Fehler',s.failed||0],['Laufend',s.running||0],['Quote',s.successRate===null||s.successRate===undefined?'–':s.successRate+'%']].map(x=>`<div class="metric"><span class="muted">${x[0]}</span><strong>${x[1]}</strong></div>`).join('');$('playwrightRuns').innerHTML=runList(d.playwrightRuns);$('workflowRuns').innerHTML=runList(d.workflowRuns)}catch(e){$('latestCommit').innerHTML='<p class="bad">'+esc(e.message)+'</p>';if(!$('playwrightRuns').innerHTML)$('playwrightRuns').innerHTML='<p class="muted">Noch keine Evidence.</p>'}}
function runList(items){return (items||[]).map(r=>`<div class="item"><div class="row between"><h3>${esc(r.name||r.title)}</h3>${badge(r.conclusion||r.status)}</div><p>${esc(r.title)} · ${esc(r.event)}</p><p class="code">${esc(r.headSha.slice(0,12))}</p>${r.url?`<a class="link" href="${esc(r.url)}" target="_blank" rel="noreferrer">GitHub Evidence öffnen</a>`:''}</div>`).join('')||'<p class="muted">Keine passenden Läufe gefunden.</p>'}
async function unlockAdmin(){const k=$('adminKey').value.trim();if(!k)return;try{const d=await api('/api/admin/ping',{headers:{Authorization:'Bearer '+k}});state.adminKey=k;$('adminKey').value='';$('adminMsg').textContent='Admin aktiv: '+d.email;await loadOwnerRequests()}catch(e){state.adminKey='';$('adminMsg').textContent='Admin nicht bestätigt: '+e.message}}
function lockAdmin(){state.adminKey='';$('adminKey').value='';$('adminMsg').textContent='Admin gesperrt.';$('ownerRequests').innerHTML='<p class="muted">Admin-Unlock erforderlich.</p>'}
async function loadOwnerRequests(){if(!state.adminKey)return;try{const d=await api('/api/admin/owner-input/requests',{headers:{Authorization:'Bearer '+state.adminKey}});$('ownerRequests').innerHTML=(d.requests||[]).map(r=>`<div class="item"><h3>${esc(r.title)}</h3><p>${esc(r.reason)}</p><a class="link" href="/owner-approvals" target="_blank">Sicher entscheiden</a></div>`).join('')||'<p class="muted">Keine offenen Owner-Anfragen.</p>'}catch(e){$('ownerRequests').innerHTML='<p class="bad">'+esc(e.message)+'</p>'}}
boot();
</script></body></html>"""
