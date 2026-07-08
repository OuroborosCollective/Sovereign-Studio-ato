"""Flask routes for neutral Sovereign Agent Jobs.

The route module is intentionally injectable: app.py provides the Flask app,
require_session decorator and DB connection factory. This keeps the huge app file
thin and prevents OpenHands-specific routes from becoming the truth source.
"""

from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
from typing import Any, Callable

from flask import jsonify, request

from .contracts import normalize_agent_job_result
from .job_lifecycle import create_sovereign_agent_job
from .job_store import list_agent_jobs, read_agent_job, result_from_stored_job, update_agent_job_state
from .tool_events import append_tool_result_to_job, predictive_tool_signal
from .tool_runner import run_agent_job_tool
from .tools.base import ToolResult
from .workspace import cleanup_agent_workspace


ConnectionFactory = Callable[[], Any]


def _current_session_user_id() -> str:
    uid = getattr(request, "session_user_id", None)
    return str(uid or "")


def _job_to_api(job) -> dict[str, Any]:
    return {
        "jobId": job.job_id,
        "executor": job.executor,
        "repoUrl": job.repo_url,
        "branch": job.branch,
        "mission": job.mission,
        "status": job.status,
        "workspaceId": job.workspace_id,
        "externalRef": job.external_ref,
        "draftPrUrl": job.draft_pr_url,
        "changedFiles": list(job.changed_files),
        "diffSummary": job.diff_summary,
        "testSummary": job.test_summary,
        "blocker": job.blocker,
        "events": list(job.events),
    }


def _result_to_api(result) -> dict[str, Any]:
    normalized = normalize_agent_job_result(result)
    return {
        "jobId": normalized.job_id,
        "executor": normalized.executor,
        "status": normalized.status,
        "workspaceId": normalized.workspace_id,
        "externalRef": normalized.external_ref,
        "draftPrUrl": normalized.draft_pr_url,
        "changedFiles": list(normalized.changed_files),
        "diffSummary": normalized.diff_summary,
        "testSummary": normalized.test_summary,
        "blocker": normalized.blocker,
        "events": [asdict(event) for event in normalized.events],
    }


def _tool_result_to_api(result: ToolResult) -> dict[str, Any]:
    return {
        "tool": result.tool,
        "allowed": result.allowed,
        "status": result.status,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "changedFiles": list(result.changed_files),
        "diffSummary": result.diff_summary,
        "testSummary": result.test_summary,
        "blocker": result.blocker,
        "exitCode": result.exit_code,
        "events": [asdict(event) for event in result.events],
        "predictiveSignal": predictive_tool_signal(result),
    }


def _workspace_root() -> Path | None:
    configured = os.getenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", "").strip()
    return Path(configured) if configured else None


def register_sovereign_agent_routes(app, *, require_session, get_connection: ConnectionFactory) -> None:
    """Register neutral user-facing Sovereign Agent job routes.

    Routes:
    - GET  /api/user/agent/jobs
    - POST /api/user/agent/jobs
    - GET  /api/user/agent/jobs/<job_id>
    - POST /api/user/agent/jobs/<job_id>/cancel
    - POST /api/user/agent/jobs/<job_id>/cleanup
    - POST /api/user/agent/jobs/<job_id>/tools/file
    - POST /api/user/agent/jobs/<job_id>/tools/git-status
    - POST /api/user/agent/jobs/<job_id>/tools/diff
    - POST /api/user/agent/jobs/<job_id>/tools/test
    """

    def _connection():
        return get_connection()

    def _close(conn) -> None:
        close = getattr(conn, "close", None)
        if callable(close):
            close()

    def _read_owned_job(conn, user_id: str, job_id: str):
        return read_agent_job(conn, user_id=user_id, job_id=job_id)

    def _run_tool_route(job_id: str, action: str):
        user_id = _current_session_user_id()
        body = request.get_json(silent=True) or {}
        conn = _connection()
        try:
            job = _read_owned_job(conn, user_id, job_id)
            if not job:
                return jsonify({"error": "Job nicht gefunden"}), 404
            result = run_agent_job_tool(job, action, body, _workspace_root())
            append_tool_result_to_job(conn, job_id, result)
            return jsonify({
                "ok": result.status == "done",
                "runtime": "sovereign-agent",
                "jobId": job_id,
                "tool": _tool_result_to_api(result),
            }), 200 if result.status == "done" else 400
        finally:
            _close(conn)

    @app.route("/api/user/agent/jobs", methods=["GET"])
    @require_session
    def user_list_sovereign_agent_jobs():
        user_id = _current_session_user_id()
        try:
            limit = max(1, min(int(request.args.get("limit", 20)), 100))
        except (TypeError, ValueError):
            limit = 20
        conn = _connection()
        try:
            jobs = list_agent_jobs(conn, user_id=user_id, limit=limit)
            return jsonify({
                "jobs": [_job_to_api(job) for job in jobs],
                "total": len(jobs),
                "limit": limit,
                "runtime": "sovereign-agent",
            })
        finally:
            _close(conn)

    @app.route("/api/user/agent/jobs", methods=["POST"])
    @require_session
    def user_create_sovereign_agent_job():
        user_id = _current_session_user_id()
        body = request.get_json(force=True) or {}
        provision_workspace = bool(body.get("provisionWorkspace", True))
        clone_repo = bool(body.get("cloneRepo", False))
        conn = _connection()
        try:
            lifecycle = create_sovereign_agent_job(
                conn,
                user_id=user_id,
                payload=body,
                workspace_root=_workspace_root(),
                provision_workspace=provision_workspace,
                clone_repo=clone_repo,
            )
            status_code = 201 if lifecycle.result.status not in ("blocked", "failed") else 400
            return jsonify({
                "ok": lifecycle.result.status not in ("blocked", "failed"),
                "runtime": "sovereign-agent",
                "job": _result_to_api(lifecycle.result),
            }), status_code
        finally:
            _close(conn)

    @app.route("/api/user/agent/jobs/<job_id>", methods=["GET"])
    @require_session
    def user_get_sovereign_agent_job(job_id: str):
        user_id = _current_session_user_id()
        conn = _connection()
        try:
            job = _read_owned_job(conn, user_id, job_id)
            if not job:
                return jsonify({"error": "Job nicht gefunden"}), 404
            return jsonify({"runtime": "sovereign-agent", "job": _job_to_api(job)})
        finally:
            _close(conn)

    @app.route("/api/user/agent/jobs/<job_id>/cancel", methods=["POST"])
    @require_session
    def user_cancel_sovereign_agent_job(job_id: str):
        user_id = _current_session_user_id()
        conn = _connection()
        try:
            job = _read_owned_job(conn, user_id, job_id)
            if not job:
                return jsonify({"error": "Job nicht gefunden"}), 404
            if job.status in ("completed", "failed", "blocked", "cleaned"):
                return jsonify({"error": "Job ist bereits terminal", "status": job.status}), 400
            update_agent_job_state(
                conn,
                job_id=job_id,
                status="blocked",
                blocker="Cancelled by user.",
            )
            return jsonify({
                "ok": True,
                "runtime": "sovereign-agent",
                "jobId": job_id,
                "status": "blocked",
                "blocker": "Cancelled by user.",
            })
        finally:
            _close(conn)

    @app.route("/api/user/agent/jobs/<job_id>/cleanup", methods=["POST"])
    @require_session
    def user_cleanup_sovereign_agent_job(job_id: str):
        user_id = _current_session_user_id()
        conn = _connection()
        try:
            job = _read_owned_job(conn, user_id, job_id)
            if not job:
                return jsonify({"error": "Job nicht gefunden"}), 404
            if job.status not in ("completed", "failed", "blocked", "cleaned"):
                return jsonify({"error": "Cleanup erst nach terminalem State erlaubt", "status": job.status}), 400
            cleanup = cleanup_agent_workspace(job.workspace_id or job.job_id, _workspace_root())
            if cleanup.status == "blocked":
                return jsonify({
                    "ok": False,
                    "runtime": "sovereign-agent",
                    "jobId": job_id,
                    "status": "blocked",
                    "blocker": cleanup.blocker,
                    "events": [asdict(event) for event in cleanup.events],
                }), 400
            update_agent_job_state(conn, job_id=job_id, status="cleaned")
            return jsonify({
                "ok": True,
                "runtime": "sovereign-agent",
                "jobId": job_id,
                "status": "cleaned",
                "events": [asdict(event) for event in cleanup.events],
            })
        finally:
            _close(conn)

    @app.route("/api/user/agent/jobs/<job_id>/tools/file", methods=["POST"])
    @require_session
    def user_run_agent_file_tool(job_id: str):
        return _run_tool_route(job_id, "file")

    @app.route("/api/user/agent/jobs/<job_id>/tools/git-status", methods=["POST"])
    @require_session
    def user_run_agent_git_status_tool(job_id: str):
        return _run_tool_route(job_id, "git-status")

    @app.route("/api/user/agent/jobs/<job_id>/tools/diff", methods=["POST"])
    @require_session
    def user_run_agent_diff_tool(job_id: str):
        return _run_tool_route(job_id, "diff")

    @app.route("/api/user/agent/jobs/<job_id>/tools/test", methods=["POST"])
    @require_session
    def user_run_agent_test_tool(job_id: str):
        return _run_tool_route(job_id, "test")
