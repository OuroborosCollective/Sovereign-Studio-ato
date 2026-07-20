"""Flask routes for neutral Sovereign Agent Jobs.

The route module is intentionally injectable: app.py provides the Flask app,
require_session decorator and DB connection factory. This keeps the huge app file
thin and keeps the internal Sovereign Agent routes as the only job truth source.
"""

from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
from typing import Any, Callable

from flask import jsonify, request

from .contracts import SovereignAgentEvent, normalize_agent_job_result
from .draft_pr_create_gate import create_draft_pr_for_job, draft_pr_create_signal
from .draft_pr_gate import draft_pr_preparation_signal, prepare_draft_pr, draft_pr_input_from_job
from .evidence_gate import EvidenceGateResult, evidence_gate_signal
from .git_workspace import normalize_ephemeral_github_token
from .job_lifecycle import create_sovereign_agent_job
from .job_store import append_agent_event, list_agent_jobs, mark_draft_pr_created, mark_draft_pr_prepared, read_agent_job, update_agent_job_state
from .pattern_gateway import (
    evaluate_pattern_learning,
    pattern_input_from_job,
    pattern_learning_signal,
    persist_pattern_learning_candidate_once,
)
from .pattern_vector_memory import persist_pattern_vector, search_pattern_vectors
from .reusable_memory import search_reusable_memory
from .tool_events import append_tool_result_to_job, predictive_tool_signal
from .tool_runner import run_agent_job_tool
from .tools.base import ToolResult
from .universal_toolchain import (
    build_agent_handoff_context,
    persist_toolchain_handoff,
    persist_toolchain_incident,
    runtime_failure_diagnose,
    toolchain_manifest,
    validate_migration_for_rollback_preview,
)
from .workspace import cleanup_agent_workspace
from .workspace_editor import WorkspaceEditorAccessError, build_workspace_editor_descriptor


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
        "draftPrPreparation": getattr(job, "draft_pr_preparation", None),
        "branchName": getattr(job, "branch_name", None),
        "targetBranch": getattr(job, "target_branch", None),
        "commitMessage": getattr(job, "commit_message", None),
        "prUrl": getattr(job, "pr_url", None),
        "prState": getattr(job, "pr_state", None),
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


def _merge_job_evidence(job, result: ToolResult) -> ToolResult:
    return ToolResult(
        tool=result.tool,
        allowed=result.allowed,
        status=result.status,
        stdout=result.stdout,
        stderr=result.stderr,
        output=result.output,
        error=result.error,
        metadata=result.metadata,
        changed_files=result.changed_files or job.changed_files,
        diff_summary=result.diff_summary or job.diff_summary,
        test_summary=result.test_summary or job.test_summary,
        blocker=result.blocker,
        exit_code=result.exit_code,
        events=result.events,
        predictive_signal=result.predictive_signal,
    )


def _tool_result_to_api(result: ToolResult, gate: EvidenceGateResult | None = None) -> dict[str, Any]:
    return {
        "tool": result.tool,
        "allowed": result.allowed,
        "status": result.status,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "metadata": result.metadata,
        "changedFiles": list(result.changed_files),
        "diffSummary": result.diff_summary,
        "testSummary": result.test_summary,
        "blocker": result.blocker,
        "exitCode": result.exit_code,
        "events": [asdict(event) for event in result.events],
        "predictiveSignal": predictive_tool_signal(result, gate),
        "evidenceGate": evidence_gate_signal(gate) if gate else None,
    }


def _pattern_learning_response_state(pattern_result: Any, vector_memory: dict[str, Any]) -> tuple[bool, int, str | None]:
    """Derive API truth only from both candidate and pgvector persistence outcomes."""
    if not getattr(pattern_result, "allowed", False):
        return False, 400, "pattern_not_accepted"
    if not bool(vector_memory.get("stored")):
        blocker = str(vector_memory.get("reason") or "pattern_vector_not_stored")[:120]
        return False, 503, blocker
    return True, 200, None


def _persist_accepted_pattern_memory(
    conn: Any,
    *,
    user_id: str,
    job: Any,
) -> tuple[Any, str | None, bool, dict[str, Any]]:
    """Store only accepted evidence-backed patterns; reruns reuse the first candidate."""

    pattern_result = evaluate_pattern_learning(pattern_input_from_job(job))
    candidate_id, candidate_created = persist_pattern_learning_candidate_once(
        conn,
        user_id=user_id,
        result=pattern_result,
    )
    vector_memory = (
        persist_pattern_vector(
            conn,
            candidate_id=candidate_id,
            user_id=user_id,
            result=pattern_result,
        )
        if candidate_id
        else {
            "stored": False,
            "storage": "postgres-pgvector",
            "reason": "pattern_not_accepted",
        }
    )
    return pattern_result, candidate_id, candidate_created, vector_memory


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
    - POST /api/user/agent/jobs/<job_id>/editor/open
    - POST /api/user/agent/jobs/<job_id>/tools/file
    - POST /api/user/agent/jobs/<job_id>/tools/git-status
    - POST /api/user/agent/jobs/<job_id>/tools/diff
    - POST /api/user/agent/jobs/<job_id>/tools/test
    - POST /api/user/agent/jobs/<job_id>/tools/janitor
    - POST /api/user/agent/jobs/<job_id>/draft-pr/prepare
    - POST /api/user/agent/jobs/<job_id>/draft-pr/create
    - POST /api/user/agent/jobs/<job_id>/patterns/learn
    - POST /api/user/agent/patterns/predict
    - POST /api/user/agent/memory/search
    - GET  /api/user/agent/toolchain/manifest
    - POST /api/user/agent/toolchain/diagnose
    - POST /api/user/agent/toolchain/handoff
    - POST /api/user/agent/toolchain/rollback-preview
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
            is_janitor_scan = (
                action == "janitor"
                and result.status == "done"
                and result.metadata.get("mode") == "scan"
            )
            if is_janitor_scan:
                append_agent_event(conn, job_id, SovereignAgentEvent(
                    stage="agent_janitor_scan_completed",
                    level="success",
                    message=str(result.output or "Janitor scan completed.")[:1200],
                ))
                return jsonify({
                    "ok": True,
                    "runtime": "sovereign-agent",
                    "jobId": job_id,
                    "tool": _tool_result_to_api(result),
                }), 200

            evidence_result = result if action == "janitor" else _merge_job_evidence(job, result)
            gate = append_tool_result_to_job(conn, job_id, evidence_result)
            tool_ok = result.status == "done"
            response_ok = tool_ok and (action == "janitor" or getattr(gate, "allowed", gate.passed))
            return jsonify({
                "ok": response_ok,
                "runtime": "sovereign-agent",
                "jobId": job_id,
                "tool": _tool_result_to_api(evidence_result, gate),
            }), 200 if response_ok else 400
        finally:
            _close(conn)

    @app.route("/api/user/agent/toolchain/manifest", methods=["GET"])
    @require_session
    def user_get_embedded_toolchain_manifest():
        return jsonify({"ok": True, **toolchain_manifest()})

    @app.route("/api/user/agent/toolchain/diagnose", methods=["POST"])
    @require_session
    def user_diagnose_with_embedded_toolchain():
        user_id = _current_session_user_id()
        body = request.get_json(force=True) or {}
        mission = str(body.get("mission") or "").strip()
        evidence_text = str(body.get("evidenceText") or body.get("logText") or "")
        diagnosis = runtime_failure_diagnose(evidence_text, mission=mission)
        conn = _connection()
        try:
            incident_id = persist_toolchain_incident(
                conn,
                user_id=user_id,
                mission=mission,
                diagnosis=diagnosis,
            )
            return jsonify({
                "ok": True,
                "runtime": "sovereign-universal-toolchain",
                "incidentId": incident_id,
                "diagnosis": diagnosis,
            })
        finally:
            _close(conn)

    @app.route("/api/user/agent/toolchain/rollback-preview", methods=["POST"])
    @require_session
    def user_preview_toolchain_migration_rollback():
        body = request.get_json(force=True) or {}
        migration_sql = str(body.get("migrationSql") or "")
        if not migration_sql:
            return jsonify({"error": "migrationSql is required"}), 400
        try:
            repair_attempt = int(body.get("repairAttempt") or 0)
        except (TypeError, ValueError):
            return jsonify({"error": "repairAttempt must be an integer"}), 400
        result = validate_migration_for_rollback_preview(
            migration_sql,
            expected_sha256=str(body.get("expectedSha256") or "") or None,
            repair_attempt=repair_attempt,
        )
        return jsonify(result), 200 if result.get("ok") else 400

    @app.route("/api/user/agent/toolchain/handoff", methods=["POST"])
    @require_session
    def user_create_toolchain_agent_handoff():
        user_id = _current_session_user_id()
        body = request.get_json(force=True) or {}
        mission = str(body.get("mission") or "").strip()
        if not mission:
            return jsonify({"error": "mission is required"}), 400
        evidence_text = str(body.get("evidenceText") or body.get("logText") or "")
        try:
            handoff = build_agent_handoff_context(mission, evidence_text)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        payload = {
            **body,
            "mission": handoff["mission"],
        }
        payload.pop("evidenceText", None)
        payload.pop("logText", None)
        provision_workspace = bool(payload.get("provisionWorkspace", True))
        clone_repo = bool(payload.get("cloneRepo", False))
        conn = _connection()
        try:
            incident_id = persist_toolchain_incident(
                conn,
                user_id=user_id,
                mission=mission,
                diagnosis=handoff["diagnosis"],
            )
            lifecycle = create_sovereign_agent_job(
                conn,
                user_id=user_id,
                payload=payload,
                workspace_root=_workspace_root(),
                provision_workspace=provision_workspace,
                clone_repo=clone_repo,
            )
            job_id = lifecycle.result.job_id
            append_agent_event(conn, job_id, SovereignAgentEvent(
                stage="toolchain_diagnosis_completed",
                level="success",
                message=(
                    f"Universal Toolchain diagnosed {len(handoff['diagnosis']['failureFamilies'])} "
                    f"failure families and exactly {len(handoff['diagnosis']['nextLogicalFailures'])} "
                    "logical neighbouring runtime risks."
                ),
            ))
            append_agent_event(conn, job_id, SovereignAgentEvent(
                stage="toolchain_predictive_handoff",
                level="info",
                message=f"Predictive evidence hash: {handoff['diagnosis']['evidenceHash']}",
            ))
            persist_toolchain_handoff(
                conn,
                incident_id=incident_id,
                user_id=user_id,
                job_id=job_id,
                repo_url=str(body.get("repoUrl") or ""),
                branch=str(body.get("branch") or "main"),
            )
            status_code = 201 if lifecycle.result.status not in ("blocked", "failed") else 400
            return jsonify({
                "ok": lifecycle.result.status not in ("blocked", "failed"),
                "runtime": "sovereign-agent",
                "incidentId": incident_id,
                "toolchain": handoff["diagnosis"],
                "job": _result_to_api(lifecycle.result),
            }), status_code
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

    @app.route("/api/user/agent/jobs/<job_id>/editor/open", methods=["POST"])
    @require_session
    def user_open_sovereign_agent_workspace_editor(job_id: str):
        user_id = _current_session_user_id()
        body = request.get_json(silent=True) or {}
        conn = _connection()
        try:
            job = _read_owned_job(conn, user_id, job_id)
            if not job:
                return jsonify({"error": "Job nicht gefunden"}), 404
            try:
                descriptor = build_workspace_editor_descriptor(
                    user_id=user_id,
                    workspace_id=job.workspace_id or job.job_id,
                    workspace_root=_workspace_root(),
                    sdcard_enabled=bool(body.get("sdcardEnabled", False)),
                    sdcard_marker_sha256=str(body.get("sdcardMarkerSha256") or ""),
                )
            except WorkspaceEditorAccessError as exc:
                reason = str(exc)
                status_code = 403 if "owner-only" in reason else 409
                return jsonify({
                    "ok": False,
                    "runtime": "sovereign-agent",
                    "workspaceAuthority": "sovereign-backend",
                    "error": reason,
                }), status_code
            return jsonify({
                "ok": True,
                "runtime": "sovereign-agent",
                "editor": descriptor,
            })
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
            update_agent_job_state(
                conn,
                job_id=job_id,
                status="cleaned",
                clear_blocker=True,
            )
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

    @app.route("/api/user/agent/jobs/<job_id>/tools/janitor", methods=["POST"])
    @require_session
    def user_run_agent_janitor_tool(job_id: str):
        return _run_tool_route(job_id, "janitor")

    @app.route("/api/user/agent/jobs/<job_id>/draft-pr/prepare", methods=["POST"])
    @require_session
    def user_prepare_agent_draft_pr(job_id: str):
        user_id = _current_session_user_id()
        body = request.get_json(silent=True) or {}
        conn = _connection()
        try:
            job = _read_owned_job(conn, user_id, job_id)
            if not job:
                return jsonify({"error": "Job nicht gefunden"}), 404
            preparation = prepare_draft_pr(draft_pr_input_from_job(job, head_branch=body.get("headBranch")))
            pattern_result = None
            candidate_id = None
            candidate_created = False
            vector_memory: dict[str, Any] = {
                "stored": False,
                "storage": "postgres-pgvector",
                "reason": "draft_pr_not_prepared",
            }
            if preparation.allowed:
                mark_draft_pr_prepared(
                    conn,
                    job_id=job_id,
                    head_branch=preparation.head_branch or "",
                    base_branch=preparation.base_branch or "main",
                    title=preparation.title or "Draft: Sovereign agent changes",
                    body=preparation.body or "",
                )
                prepared_job = _read_owned_job(conn, user_id, job_id)
                if prepared_job:
                    pattern_result, candidate_id, candidate_created, vector_memory = _persist_accepted_pattern_memory(
                        conn,
                        user_id=user_id,
                        job=prepared_job,
                    )
            return jsonify({
                "ok": preparation.allowed,
                "runtime": "sovereign-agent",
                "jobId": job_id,
                "draftPrPreparation": draft_pr_preparation_signal(preparation),
                "candidateId": candidate_id,
                "candidateCreated": candidate_created,
                "patternLearning": pattern_learning_signal(pattern_result) if pattern_result else None,
                "vectorMemory": vector_memory,
            }), 200 if preparation.allowed else 400
        finally:
            _close(conn)

    @app.route("/api/user/agent/jobs/<job_id>/draft-pr/create", methods=["POST"])
    @require_session
    def user_create_agent_draft_pr(job_id: str):
        user_id = _current_session_user_id()
        body = request.get_json(silent=True) or {}
        raw_github_token = body.get("githubAccessToken")
        github_token = normalize_ephemeral_github_token(raw_github_token)
        if raw_github_token is not None and github_token is None:
            return jsonify({"error": "githubAccessToken has an invalid format"}), 400
        conn = _connection()
        try:
            # Manifest: credits = permission. Every write action costs 10 credits.
            with conn.cursor() as cur:
                cur.execute("SELECT credits, role FROM admin_users WHERE id = %s::uuid LIMIT 1", (user_id,))
                user_row = cur.fetchone()
                if not user_row:
                    return jsonify({"error": "User nicht gefunden"}), 404
                
                is_admin = user_row.get("role") in ("admin", "superadmin")
                if not is_admin:
                    if int(user_row.get("credits") or 0) < 10:
                        return jsonify({"error": "Nicht genügend Credits (10 erforderlich)"}), 402
                    # Deduct credits
                    cur.execute("UPDATE admin_users SET credits = credits - 10 WHERE id = %s::uuid", (user_id,))
                    cur.execute("""INSERT INTO credit_ledger (user_id, amount, description, type, reference_id) 
                                   VALUES (%s::uuid, %s, %s, 'usage', %s)""", 
                                (user_id, -10, f"Agent PR: {job_id}", "usage", f"agent-pr:{job_id}"))
                    conn.commit()

            job = _read_owned_job(conn, user_id, job_id)
            if not job:
                return jsonify({"error": "Job nicht gefunden"}), 404
            result = create_draft_pr_for_job(job, token=github_token)
            if result.allowed and result.pr_url:
                mark_draft_pr_created(conn, job_id=job_id, pr_url=result.pr_url)
                conn.commit()
            return jsonify({
                "ok": result.allowed,
                "runtime": "sovereign-agent",
                "jobId": job_id,
                "draftPrCreate": draft_pr_create_signal(result),
            }), 200 if result.allowed else 400
        finally:
            _close(conn)

    @app.route("/api/user/agent/jobs/<job_id>/patterns/learn", methods=["POST"])
    @require_session
    def user_learn_agent_pattern(job_id: str):
        user_id = _current_session_user_id()
        conn = _connection()
        try:
            job = _read_owned_job(conn, user_id, job_id)
            if not job:
                return jsonify({"error": "Job nicht gefunden"}), 404
            pattern_result, candidate_id, candidate_created, vector_memory = _persist_accepted_pattern_memory(
                conn,
                user_id=user_id,
                job=job,
            )
            response_ok, status_code, blocker = _pattern_learning_response_state(
                pattern_result,
                vector_memory,
            )
            return jsonify({
                "ok": response_ok,
                "runtime": "sovereign-agent",
                "jobId": job_id,
                "candidateId": candidate_id,
                "candidateCreated": candidate_created,
                "patternLearning": pattern_learning_signal(pattern_result),
                "vectorMemory": vector_memory,
                "blocker": blocker,
            }), status_code
        finally:
            _close(conn)

    @app.route("/api/user/agent/patterns/predict", methods=["POST"])
    @require_session
    def user_predict_agent_patterns():
        user_id = _current_session_user_id()
        body = request.get_json(force=True) or {}
        query_text = str(body.get("query") or "").strip()
        if not query_text:
            return jsonify({"error": "query is required"}), 400
        try:
            limit = max(1, min(int(body.get("limit", 8)), 20))
        except (TypeError, ValueError):
            limit = 8
        conn = _connection()
        try:
            result = search_pattern_vectors(
                conn,
                user_id=user_id,
                query_text=query_text,
                limit=limit,
            )
            return jsonify({"runtime": "sovereign-agent", **result}), 200 if result.get("ok") else 503
        finally:
            _close(conn)

    @app.route("/api/user/agent/memory/search", methods=["POST"])
    @require_session
    def user_search_reusable_memory():
        user_id = _current_session_user_id()
        body = request.get_json(force=True) or {}
        query_text = str(body.get("query") or "").strip()
        if not query_text:
            return jsonify({"error": "query is required"}), 400
        try:
            limit = max(1, min(int(body.get("limit", 8)), 20))
        except (TypeError, ValueError):
            limit = 8
        conn = _connection()
        try:
            result = search_reusable_memory(
                conn,
                user_id=user_id,
                query_text=query_text,
                limit=limit,
            )
            return jsonify({"runtime": "sovereign-agent", **result}), 200 if result.get("ok") else 503
        finally:
            _close(conn)
