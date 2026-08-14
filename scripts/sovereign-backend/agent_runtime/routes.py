"""Flask routes for neutral Sovereign Agent Jobs.

The route module is intentionally injectable: app.py provides the Flask app,
require_session decorator and DB connection factory. This keeps the huge app file
thin and keeps the internal Sovereign Agent routes as the only job truth source.
"""

from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
import uuid

from flask import Response, jsonify, request

from .auto_code_review import AutoCodeReviewInput, auto_code_review, auto_code_review_signal
from .productivity_insights import (
    changelog_signal,
    diff_narration_signal,
    generate_changelog,
    mission_validation_signal,
    narrate_diff,
    validate_mission,
)
from .contracts import SovereignAgentEvent, normalize_agent_job_result
from .cognitive_run_store import read_agent_run_receipts
from .cognitive_swarm_routes import start_cognitive_swarm_run
from .draft_pr_create_gate import create_draft_pr_for_job, draft_pr_create_signal
from .draft_pr_gate import draft_pr_preparation_signal, prepare_draft_pr, draft_pr_input_from_job
from .evidence_gate import EvidenceGateResult, evidence_gate_signal
from .git_workspace import git_diff_full, normalize_ephemeral_github_token
from .github_access import (
    issue_github_access_scope,
    validate_github_access_for_repo,
    verify_github_access_scope,
)
from .job_lifecycle import create_sovereign_agent_job, generate_agent_job_id
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
from .repair_capsule import (
    MAX_REPAIR_CAPSULE_PATCH_BYTES,
    build_repair_capsule,
    build_repair_capsule_archive,
)
from .rescue import (
    MAX_REPAIR_CHANGED_FILES,
    REPAIR_PACK_CREDITS,
    RESCUE_CSRF_TTL_SECONDS,
    build_free_diagnosis,
    build_proof_pack,
    entitlement_payload,
    evaluate_rescue_pre_mutation_gate,
    issue_rescue_csrf_token,
    normalize_head_sha,
    normalize_repair_changed_files,
    normalize_rescue_origin,
    public_repair_row,
    read_github_pr_evidence,
    redact_secret_text,
    repair_changed_file_limit_blocker,
    reserve_repair_pack,
    resolve_account_entitlement,
    resolve_github_head,
    update_repair_execution,
    verify_proof_pack,
    verify_rescue_csrf_token,
)
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
    - POST /api/user/agent/validate-mission
    - POST /api/user/agent/jobs/<job_id>/review
    - POST /api/user/agent/jobs/<job_id>/diff-narration
    - POST /api/user/agent/jobs/<job_id>/changelog
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

    def _github_target_for_owned_job(conn, user_id: str, job_id: str) -> tuple[str, str] | None:
        job = _read_owned_job(conn, user_id, job_id)
        if job is None:
            return None
        parsed = urlparse(str(job.repo_url or "").strip())
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
            return None
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) != 2:
            return None
        owner, repo = parts
        repo = repo.removesuffix(".git")
        return (owner, repo) if owner and repo else None

    def _github_access_scope_secret() -> str:
        return str(
            os.getenv("SOVEREIGN_GITHUB_ACCESS_SCOPE_SECRET")
            or os.getenv("JWT_SECRET")
            or ""
        )

    def _real_job_diff(job: Any) -> str:
        diff_result = run_agent_job_tool(job, "diff", {}, _workspace_root())
        if diff_result.status != "done":
            return ""
        diff_text = str(diff_result.output or diff_result.stdout or "")
        return "" if diff_text.strip() == "No changes" else diff_text

    def _review_job_diff(job: Any, user_id: str):
        return auto_code_review(
            AutoCodeReviewInput(
                diff_text=_real_job_diff(job),
                changed_files=tuple(job.changed_files),
                job_id=job.job_id,
                mission=job.mission,
            ),
            get_connection=_connection,
            user_id=user_id,
            requested_mode="auto",
        )

    def _run_tool_route(job_id: str, action: str):
        user_id = _current_session_user_id()
        body = request.get_json(silent=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
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

    def _rescue_account(conn, user_id: str) -> dict[str, Any] | None:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT account.id::text AS id, account.email, account.role,
                          account.credits::integer AS credits,
                          EXISTS(
                            SELECT 1
                            FROM transactions AS tx
                            JOIN credit_receipts AS receipt
                              ON receipt.user_id = tx.user_id
                             AND receipt.provider = tx.provider
                             AND receipt.provider_tx_id = tx.provider_tx_id
                            WHERE tx.user_id = account.id
                              AND tx.type = 'credit_purchase'
                              AND tx.status = 'completed'
                          ) AS paid_purchase_verified
                   FROM admin_users AS account
                   WHERE account.id = %s::uuid
                   LIMIT 1""",
                (user_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        account = dict(row)
        account["configured_owner_id"] = os.getenv("SOVEREIGN_OWNER_ADMIN_ID", "")
        account["configured_owner_email"] = os.getenv("SOVEREIGN_OWNER_ADMIN_EMAIL", "")
        return account

    def _ephemeral_github_access_token(body: dict[str, Any]) -> tuple[str | None, tuple[Any, int] | None]:
        raw_token = body.get("githubAccessToken")
        token = normalize_ephemeral_github_token(raw_token)
        if raw_token is not None and token is None:
            return None, (jsonify({"error": "githubAccessToken has an invalid format"}), 400)
        return token, None

    def _rescue_request_origin() -> str | None:
        declared = str(request.headers.get("X-Sovereign-Rescue-Origin") or "").strip()
        actual = str(request.headers.get("Origin") or "").strip()
        try:
            normalized_declared = normalize_rescue_origin(declared) if declared else None
            normalized_actual = normalize_rescue_origin(actual) if actual else None
        except ValueError:
            return None
        if normalized_actual and normalized_declared and normalized_actual != normalized_declared:
            return None
        return normalized_actual or normalized_declared

    def _rescue_csrf_secret() -> str:
        return str(
            os.getenv("SOVEREIGN_RESCUE_CSRF_SECRET")
            or os.getenv("JWT_SECRET")
            or ""
        )

    def _issue_rescue_csrf(user_id: str) -> tuple[str | None, tuple[Any, int] | None]:
        origin = _rescue_request_origin()
        if not origin:
            return None, (
                jsonify({"error": "rescue_origin_required", "blocker": "csrf_origin_unverified"}),
                403,
            )
        try:
            token = issue_rescue_csrf_token(
                user_id=user_id,
                origin=origin,
                secret=_rescue_csrf_secret(),
            )
        except RuntimeError as exc:
            return None, (
                jsonify({"error": str(exc), "blocker": "csrf_runtime_unavailable"}),
                503,
            )
        return token, None

    def _rescue_csrf_request_error(user_id: str) -> tuple[Any, int] | None:
        if not request.is_json:
            return (
                jsonify({
                    "error": "application/json is required",
                    "blocker": "rescue_json_content_type_required",
                }),
                415,
            )
        origin = _rescue_request_origin()
        if not origin:
            return (
                jsonify({"error": "rescue_origin_required", "blocker": "csrf_origin_unverified"}),
                403,
            )
        supplied = request.headers.get("X-Sovereign-Rescue-CSRF")
        if not verify_rescue_csrf_token(
            supplied,
            user_id=user_id,
            origin=origin,
            secret=_rescue_csrf_secret(),
        ):
            return (
                jsonify({"error": "rescue_csrf_invalid", "blocker": "csrf_verification_failed"}),
                403,
            )
        return None

    def _read_owned_rescue(conn, user_id: str, repair_id: str) -> dict[str, Any] | None:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT * FROM sovereign_rescue_repairs
                   WHERE repair_id = %s::uuid AND user_id = %s::uuid
                   LIMIT 1""",
                (repair_id, user_id),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def _bind_rescue_published_head(
        conn: Any,
        *,
        reservation: Mapping[str, Any] | None,
        user_id: str,
        job_id: str,
        observed_head_sha: str | None,
    ) -> str | None:
        if not reservation:
            return None
        stored_raw = str(reservation.get("published_head_sha") or "").strip()
        observed_raw = str(observed_head_sha or "").strip()
        try:
            stored = normalize_head_sha(stored_raw) if stored_raw else None
            observed = normalize_head_sha(observed_raw) if observed_raw else None
        except ValueError:
            return None
        if stored and observed and stored != observed:
            return None
        bound = stored or observed
        if not bound:
            return None
        if not stored:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE sovereign_rescue_repairs
                       SET published_head_sha = %s, updated_at = NOW()
                       WHERE job_id = %s AND user_id = %s::uuid""",
                    (bound, job_id, user_id),
                )
        return bound

    @app.route("/api/user/agent/rescue/entitlement", methods=["GET"])
    @require_session
    def user_get_rescue_entitlement():
        user_id = _current_session_user_id()
        csrf_token, csrf_error = _issue_rescue_csrf(user_id)
        if csrf_error:
            return csrf_error
        conn = _connection()
        try:
            account = _rescue_account(conn, user_id)
            if not account:
                return jsonify({"error": "Authenticated account not found"}), 404
            entitlement = resolve_account_entitlement(account)
            return jsonify({
                "ok": True,
                "runtime": "sovereign-rescue",
                "csrfToken": csrf_token,
                "csrfExpiresInSeconds": RESCUE_CSRF_TTL_SECONDS,
                "entitlement": entitlement_payload(account, entitlement),
            })
        finally:
            _close(conn)

    @app.route("/api/user/agent/rescue/diagnose", methods=["POST"])
    @require_session
    def user_diagnose_sovereign_rescue():
        body = request.get_json(force=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
        token, token_error = _ephemeral_github_access_token(body)
        if token_error:
            return token_error
        try:
            revision = resolve_github_head(
                body.get("repository") or body.get("repoUrl"),
                body.get("baseBranch") or body.get("branch") or "main",
                token=token,
            )
            diagnosis = build_free_diagnosis(
                repository=revision["repository"],
                base_branch=revision["baseBranch"],
                base_sha=revision["baseSha"],
                evidence_text=body.get("evidenceText") or body.get("logText") or "",
                requested_family=str(body.get("failureFamily") or ""),
            )
        except (ValueError, HTTPError, URLError, TimeoutError) as exc:
            return jsonify({
                "ok": False,
                "runtime": "sovereign-rescue",
                "mutationPerformed": False,
                "blocker": "github_revision_unverified",
                "error": redact_secret_text(exc, 400),
            }), 422
        return jsonify({
            "ok": bool(diagnosis.get("ok")),
            "runtime": "sovereign-rescue",
            "diagnosis": diagnosis,
        }), 200 if diagnosis.get("ok") else 422

    @app.route("/api/user/agent/rescue/repair", methods=["POST"])
    @require_session
    def user_start_sovereign_rescue_repair():
        user_id = _current_session_user_id()
        csrf_error = _rescue_csrf_request_error(user_id)
        if csrf_error:
            return csrf_error
        parsed_body = request.get_json(silent=True)
        if not isinstance(parsed_body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
        body: dict[str, Any] = parsed_body
        token, token_error = _ephemeral_github_access_token(body)
        if token_error:
            return token_error
        try:
            idempotency_key = str(uuid.UUID(str(
                request.headers.get("Idempotency-Key")
                or ""
            )))
            expected_base_sha = normalize_head_sha(body.get("expectedBaseSha"))
            revision = resolve_github_head(
                body.get("repository") or body.get("repoUrl"),
                body.get("baseBranch") or body.get("branch") or "main",
                token=token,
            )
            if revision["baseSha"] != expected_base_sha:
                return jsonify({
                    "ok": False,
                    "runtime": "sovereign-rescue",
                    "blocker": "repository_head_changed",
                    "expectedBaseSha": expected_base_sha,
                    "actualBaseSha": revision["baseSha"],
                    "nextAction": "Run a new free diagnosis on the current revision.",
                }), 409
            diagnosis = build_free_diagnosis(
                repository=revision["repository"],
                base_branch=revision["baseBranch"],
                base_sha=revision["baseSha"],
                evidence_text=body.get("evidenceText") or body.get("logText") or "",
                requested_family=str(body.get("failureFamily") or ""),
            )
            if not diagnosis.get("ok"):
                return jsonify({
                    "ok": False,
                    "runtime": "sovereign-rescue",
                    "blocker": diagnosis.get("blocker"),
                    "diagnosis": diagnosis,
                }), 422
            contract = diagnosis["outcomeContract"]
            repair_id = str(uuid.uuid4())
            implementation_job_id = generate_agent_job_id()
        except (ValueError, HTTPError, URLError, TimeoutError) as exc:
            return jsonify({
                "ok": False,
                "runtime": "sovereign-rescue",
                "blocker": "repair_request_invalid",
                "error": redact_secret_text(exc, 400),
            }), 400

        conn = _connection()
        try:
            try:
                reservation = reserve_repair_pack(
                    conn,
                    user_id=user_id,
                    repair_id=repair_id,
                    job_id=implementation_job_id,
                    idempotency_key=idempotency_key,
                    repository=revision["repository"],
                    base_branch=revision["baseBranch"],
                    base_sha=revision["baseSha"],
                    failure_family=str(diagnosis["failureFamily"]),
                    outcome_contract_sha256=str(contract["contractSha256"]),
                    configured_owner_id=os.getenv("SOVEREIGN_OWNER_ADMIN_ID", ""),
                    configured_owner_email=os.getenv("SOVEREIGN_OWNER_ADMIN_EMAIL", ""),
                )
            except PermissionError as exc:
                blocker = str(exc)
                return jsonify({
                    "ok": False,
                    "runtime": "sovereign-rescue",
                    "blocker": blocker,
                    "requiredCredits": REPAIR_PACK_CREDITS,
                    "checkout": {"surface": "existing-paywall-modal", "external": True},
                }), 402
            except RuntimeError as exc:
                status = 409 if "conflict" in str(exc) or "race" in str(exc) else 500
                return jsonify({
                    "ok": False,
                    "runtime": "sovereign-rescue",
                    "blocker": redact_secret_text(exc, 400),
                }), status
            if reservation.get("duplicate"):
                existing_job = _read_owned_job(
                    conn,
                    user_id,
                    str(reservation.get("jobId") or ""),
                )
                existing_state = str(reservation.get("state") or "")
                if existing_job:
                    job_state = str(getattr(existing_job, "status", "") or "")
                    if job_state == "completed" or existing_state in {"draft_pr_ready", "completed"}:
                        update_repair_execution(
                            conn,
                            user_id=user_id,
                            repair_id=str(reservation["repairId"]),
                            run_id=str(reservation.get("runId") or "") or None,
                            job_id=existing_job.job_id,
                            state="draft_pr_ready",
                        )
                        return jsonify({
                            "ok": True,
                            "runtime": "sovereign-rescue",
                            "duplicate": True,
                            "repair": {**reservation, "state": "draft_pr_ready"},
                        }), 200
                    if job_state in {
                        "queued",
                        "provisioning",
                        "running",
                        "waiting-for-user",
                        "validating",
                    }:
                        update_repair_execution(
                            conn,
                            user_id=user_id,
                            repair_id=str(reservation["repairId"]),
                            run_id=str(reservation.get("runId") or "") or None,
                            job_id=existing_job.job_id,
                            state="running",
                        )
                        return jsonify({
                            "ok": True,
                            "runtime": "sovereign-rescue",
                            "duplicate": True,
                            "repair": {**reservation, "state": "running"},
                        }), 202
                    return jsonify({
                        "ok": False,
                        "runtime": "sovereign-rescue",
                        "duplicate": True,
                        "blocker": "rescue_existing_job_recovery_required",
                        "repair": reservation,
                        "jobState": job_state or "unknown",
                        "nextAction": "Inspect the persisted job evidence before retrying publication.",
                    }), 409
                if existing_state not in {"reserved", "blocked"}:
                    return jsonify({
                        "ok": False,
                        "runtime": "sovereign-rescue",
                        "duplicate": True,
                        "blocker": "rescue_reservation_state_inconsistent",
                        "repair": reservation,
                    }), 409
                implementation_job_id = str(reservation.get("jobId") or "")
        finally:
            _close(conn)

        pre_mutation_gate = evaluate_rescue_pre_mutation_gate(
            reservation=reservation,
            diagnosis=diagnosis,
            outcome_contract=contract,
            resolved_base_sha=revision["baseSha"],
        )
        if not pre_mutation_gate["allowed"]:
            conn = _connection()
            try:
                update_repair_execution(
                    conn,
                    user_id=user_id,
                    repair_id=str(reservation.get("repairId") or repair_id),
                    run_id=str(reservation.get("runId") or "") or None,
                    job_id=str(reservation.get("jobId") or implementation_job_id) or None,
                    state="blocked",
                    blocker=",".join(pre_mutation_gate["blockers"]),
                )
            finally:
                _close(conn)
            return jsonify({
                "ok": False,
                "runtime": "sovereign-rescue",
                "blocker": "rescue_pre_mutation_evidence_unverified",
                "preMutationGate": pre_mutation_gate,
                "mutationPerformed": False,
            }), 409

        mission = (
            "Sovereign Rescue Repair Pack. "
            f"Repair only failure family {diagnosis['failureFamily']} at exact base "
            f"{revision['baseSha']}. Follow Outcome Contract {contract['contractSha256']}. "
            "Keep the change bounded, run the required targeted checks, create no "
            "production side effect, and stop at Draft-PR-ready evidence."
        )
        execution, status_code = start_cognitive_swarm_run(
            get_connection=_connection,
            user_id=user_id,
            mission=mission,
            evidence=redact_secret_text(
                body.get("evidenceText") or body.get("logText") or ""
            ),
            mode="free",
            intent_mode="repository_execution",
            repository_url=revision["repository"],
            repository_branch=revision["baseBranch"],
            expected_head_sha=revision["baseSha"],
            github_access_token=token,
            implementation_job_id=implementation_job_id,
        )
        run_id = str(execution.get("runId") or "") or None
        job_id = str(execution.get("jobId") or implementation_job_id)
        completed = status_code == 200 and execution.get("status") == "COMPLETED"
        conn = _connection()
        try:
            update_repair_execution(
                conn,
                user_id=user_id,
                repair_id=str(reservation["repairId"]),
                run_id=run_id,
                job_id=job_id,
                state="draft_pr_ready" if completed else "blocked",
                blocker="" if completed else str(execution.get("blocker") or execution.get("reason") or ""),
            )
        finally:
            _close(conn)
        return jsonify({
            "ok": completed,
            "runtime": "sovereign-rescue",
            "diagnosis": diagnosis,
            "outcomeContract": contract,
            "repair": {
                **reservation,
                "runId": run_id,
                "jobId": job_id,
                "state": "draft_pr_ready" if completed else "blocked",
            },
            "execution": execution,
        }), 202 if completed else status_code

    @app.route("/api/user/agent/rescue/repairs/<repair_id>", methods=["GET"])
    @require_session
    def user_get_sovereign_rescue_repair(repair_id: str):
        user_id = _current_session_user_id()
        try:
            repair_uuid = str(uuid.UUID(repair_id))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid repair id"}), 400
        conn = _connection()
        try:
            repair = _read_owned_rescue(conn, user_id, repair_uuid)
            if not repair:
                return jsonify({"error": "Repair not found"}), 404
            job = _read_owned_job(conn, user_id, str(repair.get("job_id") or ""))
            return jsonify({
                "ok": True,
                "runtime": "sovereign-rescue",
                "repair": public_repair_row(repair),
                "job": _job_to_api(job) if job else None,
            })
        finally:
            _close(conn)

    @app.route(
        "/api/user/agent/rescue/repairs/<repair_id>/proof-pack",
        methods=["POST"],
    )
    @require_session
    def user_get_sovereign_rescue_proof_pack(repair_id: str):
        user_id = _current_session_user_id()
        csrf_error = _rescue_csrf_request_error(user_id)
        if csrf_error:
            return csrf_error
        parsed_body = request.get_json(silent=True)
        if not isinstance(parsed_body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
        body: dict[str, Any] = parsed_body
        token, token_error = _ephemeral_github_access_token(body)
        if token_error:
            return token_error
        try:
            repair_uuid = str(uuid.UUID(repair_id))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid repair id"}), 400
        conn = _connection()
        try:
            repair = _read_owned_rescue(conn, user_id, repair_uuid)
            if not repair:
                return jsonify({"error": "Repair not found"}), 404
            job = _read_owned_job(conn, user_id, str(repair.get("job_id") or ""))
            if not job:
                return jsonify({"error": "Repair job not found"}), 404
            agent_receipts: tuple[dict[str, object], ...] = ()
            repair_run_id = str(repair.get("run_id") or "")
            if repair_run_id:
                try:
                    agent_receipts = read_agent_run_receipts(conn, run_id=repair_run_id)
                except (LookupError, ValueError, TypeError) as exc:
                    agent_receipts = ()
                    pr_evidence_error = redact_secret_text(exc, 400)
                else:
                    pr_evidence_error = ""
            else:
                pr_evidence_error = "agent_run_receipts_unavailable"
            pr_evidence: dict[str, Any] = {}
            if job.draft_pr_url:
                try:
                    pr_evidence = read_github_pr_evidence(job.draft_pr_url, token=token)
                except (ValueError, HTTPError, URLError, TimeoutError) as exc:
                    pr_evidence = {
                        "url": job.draft_pr_url,
                        "error": redact_secret_text(exc, 400),
                    }
            pack = build_proof_pack(
                repair=repair,
                job={
                    "changed_files": list(job.changed_files),
                    "test_summary": job.test_summary,
                    "draft_pr_url": job.draft_pr_url,
                },
                pr_evidence={**pr_evidence, "agentReceiptReadbackError": pr_evidence_error or None},
                agent_receipts=agent_receipts,
            )
            if pack["ready"]:
                update_repair_execution(
                    conn,
                    user_id=user_id,
                    repair_id=repair_uuid,
                    run_id=str(repair.get("run_id") or "") or None,
                    job_id=str(repair.get("job_id") or "") or None,
                    state="completed",
                )
            return jsonify({
                "ok": bool(pack["ready"]),
                "runtime": "sovereign-rescue",
                "proofPack": pack,
                "verified": verify_proof_pack(pack),
            }), 200 if pack["ready"] else 409
        finally:
            _close(conn)

    @app.route(
        "/api/user/agent/rescue/repairs/<repair_id>/capsule",
        methods=["POST"],
    )
    @require_session
    def user_get_sovereign_rescue_capsule(repair_id: str):
        """Return a bounded, zero-write Capsule built from current workspace evidence."""

        user_id = _current_session_user_id()
        csrf_error = _rescue_csrf_request_error(user_id)
        if csrf_error:
            return csrf_error
        parsed_body = request.get_json(silent=True)
        if not isinstance(parsed_body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
        if parsed_body:
            return jsonify({
                "error": "Capsule delivery accepts no request fields",
                "blocker": "capsule_request_fields_forbidden",
            }), 400
        try:
            repair_uuid = str(uuid.UUID(repair_id))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid repair id"}), 400

        conn = _connection()
        try:
            repair = _read_owned_rescue(conn, user_id, repair_uuid)
            if not repair:
                return jsonify({"error": "Repair not found"}), 404
            job = _read_owned_job(conn, user_id, str(repair.get("job_id") or ""))
            if not job:
                return jsonify({"error": "Repair job not found"}), 404
            workspace_id = str(job.workspace_id or "").strip()
            if not workspace_id:
                return jsonify({
                    "error": "Repair workspace is unavailable",
                    "blocker": "capsule_workspace_missing",
                }), 409

            patch, diff_result = git_diff_full(
                workspace_id,
                _workspace_root(),
                max_bytes=MAX_REPAIR_CAPSULE_PATCH_BYTES,
                max_files=MAX_REPAIR_CHANGED_FILES,
            )
            if diff_result.status != "done":
                return jsonify({
                    "ok": False,
                    "runtime": "sovereign-rescue",
                    "blocker": diff_result.blocker or "capsule_workspace_diff_failed",
                    "mutationPerformed": False,
                }), 409 if diff_result.status == "blocked" else 422
            try:
                base_sha = normalize_head_sha(repair.get("base_sha"))
            except ValueError:
                return jsonify({
                    "error": "Repair base revision is invalid",
                    "blocker": "capsule_base_sha_invalid",
                }), 409
            if diff_result.commit_sha != base_sha:
                return jsonify({
                    "error": "Workspace base revision changed",
                    "blocker": "capsule_workspace_base_stale",
                    "expectedBaseSha": base_sha,
                    "observedBaseSha": diff_result.commit_sha,
                    "mutationPerformed": False,
                }), 409

            # Issue #1122: bind the Capsule to the real targeted test evidence
            # persisted as append-only Agent-Run receipts. No caller can satisfy
            # this path with a supplied digest or Boolean assertion.
            agent_receipts: tuple[dict[str, object], ...] = ()
            repair_run_id = str(repair.get("run_id") or "")
            if repair_run_id:
                try:
                    agent_receipts = read_agent_run_receipts(conn, run_id=repair_run_id)
                except (LookupError, ValueError, TypeError):
                    agent_receipts = ()

            capsule = build_repair_capsule(
                repair=repair,
                job={
                    "changed_files": list(job.changed_files),
                    "test_summary": job.test_summary,
                },
                patch_value=patch,
                agent_receipts=agent_receipts,
            )
            manifest = capsule.get("manifest", {})
            if capsule.get("ready") is not True:
                return jsonify({
                    "ok": False,
                    "runtime": "sovereign-rescue",
                    "capsule": manifest,
                    "blocker": "capsule_evidence_incomplete",
                    "mutationPerformed": False,
                }), 409
            try:
                archive = build_repair_capsule_archive(capsule)
            except ValueError as exc:
                return jsonify({
                    "ok": False,
                    "runtime": "sovereign-rescue",
                    "blocker": str(exc),
                    "mutationPerformed": False,
                }), 409

            response = Response(archive, status=200, mimetype="application/zip")
            response.headers["Content-Disposition"] = (
                f'attachment; filename="sovereign-repair-capsule-{repair_uuid}.zip"'
            )
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Sovereign-Capsule-Sha256"] = str(manifest["capsuleSha256"])
            response.headers["X-Sovereign-Capsule-Base-Sha"] = base_sha
            response.headers["X-Sovereign-Mutation-Performed"] = "false"
            return response
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
        body = request.get_json(force=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
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
        body = request.get_json(force=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
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
        body = request.get_json(force=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
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

    @app.route("/api/user/agent/github-access/scope", methods=["POST"])
    @require_session
    def user_issue_github_access_scope():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
        user_id = _current_session_user_id()
        github_token, token_error = _ephemeral_github_access_token(body)
        if token_error is not None:
            return token_error
        try:
            expected_revision = normalize_head_sha(body.get("expectedBaseSha"))
            revision = resolve_github_head(
                body.get("repository") or body.get("repoUrl"),
                body.get("baseBranch") or body.get("branch") or "main",
                token=github_token,
            )
            if revision["baseSha"] != expected_revision:
                return jsonify({
                    "ok": False,
                    "code": "repository_head_changed",
                    "error": "Die serverbestätigte Repository-Revision hat sich geändert.",
                }), 409
            scope = issue_github_access_scope(
                user_id=user_id,
                repository=revision["repository"],
                branch=revision["baseBranch"],
                revision=revision["baseSha"],
                secret=_github_access_scope_secret(),
            )
        except RuntimeError as exc:
            return jsonify({
                "ok": False,
                "code": "server_scope_unavailable",
                "error": redact_secret_text(exc, 240),
            }), 503
        except (ValueError, HTTPError, URLError, TimeoutError) as exc:
            return jsonify({
                "ok": False,
                "code": "server_scope_unverified",
                "error": redact_secret_text(exc, 240),
            }), 422
        return jsonify({
            "ok": True,
            "scope": scope,
            "repository": revision["repository"],
            "baseBranch": revision["baseBranch"],
            "baseSha": revision["baseSha"],
        }), 200

    @app.route("/api/user/agent/github-access/validate", methods=["POST"])
    @require_session
    def user_validate_github_access():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
        user_id = _current_session_user_id()
        scope = verify_github_access_scope(
            body.get("scope"),
            user_id=user_id,
            secret=_github_access_scope_secret(),
        )
        target = (scope.owner, scope.repo) if scope else None
        if target is None:
            job_id = str(body.get("jobId") or "").strip()
            if job_id:
                conn = _connection()
                try:
                    target = _github_target_for_owned_job(conn, user_id, job_id)
                finally:
                    _close(conn)
        if target is None:
            return jsonify({
                "ok": False,
                "canWrite": False,
                "code": "server_scope_unverified",
                "error": "Der servergebundene Repository-Scope konnte nicht bestätigt werden.",
            }), 422
        owner, repo = target
        result = validate_github_access_for_repo(
            body.get("githubAccessToken"),
            owner=owner,
            repo=repo,
        )
        # This is a nested external-credential verdict, not a failure of the
        # authenticated Sovereign session. Keep expected GitHub rejections in a
        # typed 200 envelope so the frontend cannot confuse them with logout.
        return jsonify({
            "ok": result.ok and result.can_write,
            "canWrite": result.can_write,
            "code": result.code,
            "error": None if result.ok and result.can_write else result.message,
        }), 200

    @app.route("/api/user/agent/validate-mission", methods=["POST"])
    @require_session
    def user_validate_agent_mission():
        user_id = _current_session_user_id()
        body = request.get_json(force=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
        mission = str(body.get("mission") or "").strip()
        if not mission:
            return jsonify({"error": "mission is required"}), 400
        result = validate_mission(mission, get_connection=_connection, user_id=user_id)
        return jsonify(mission_validation_signal(result)), 200

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
        body = request.get_json(force=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
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
        body = request.get_json(silent=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
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

    @app.route("/api/user/agent/jobs/<job_id>/review", methods=["POST"])
    @require_session
    def user_review_agent_job(job_id: str):
        user_id = _current_session_user_id()
        conn = _connection()
        try:
            job = _read_owned_job(conn, user_id, job_id)
            if not job:
                return jsonify({"error": "Job nicht gefunden"}), 404
            review = _review_job_diff(job, user_id)
            signal = auto_code_review_signal(review)
            append_agent_event(conn, job_id, SovereignAgentEvent(
                stage="auto_code_review_completed" if review.passed else "auto_code_review_blocked",
                level="success" if review.passed else "warning",
                message=review.summary[:1200],
            ))
            status_code = 503 if review.decision == "blocked_unavailable" else 200
            return jsonify(signal), status_code
        finally:
            _close(conn)

    @app.route("/api/user/agent/jobs/<job_id>/diff-narration", methods=["POST"])
    @require_session
    def user_narrate_agent_job_diff(job_id: str):
        user_id = _current_session_user_id()
        conn = _connection()
        try:
            job = _read_owned_job(conn, user_id, job_id)
            if not job:
                return jsonify({"error": "Job nicht gefunden"}), 404
            result = narrate_diff(
                _real_job_diff(job), tuple(job.changed_files),
                get_connection=_connection, user_id=user_id, job_id=job_id,
            )
            append_agent_event(conn, job_id, SovereignAgentEvent(
                stage="semantic_diff_narration_ready" if result.status == "ready" else "semantic_diff_narration_blocked",
                level="success" if result.status == "ready" else "warning",
                message=(f"Semantic narration: {len(result.narratives)} file(s)." if result.status == "ready" else f"Semantic narration unavailable: {result.error}")[:1200],
            ))
            return jsonify(diff_narration_signal(result)), 200 if result.status == "ready" else 503
        finally:
            _close(conn)

    @app.route("/api/user/agent/jobs/<job_id>/changelog", methods=["POST"])
    @require_session
    def user_generate_agent_job_changelog(job_id: str):
        user_id = _current_session_user_id()
        body = request.get_json(silent=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
        try:
            max_count = max(1, min(int(body.get("maxCount", 30)), 100))
        except (TypeError, ValueError):
            max_count = 30
        conn = _connection()
        try:
            job = _read_owned_job(conn, user_id, job_id)
            if not job:
                return jsonify({"error": "Job nicht gefunden"}), 404
            log_result = run_agent_job_tool(job, "git_log", {"max_count": max_count, "oneline": True}, _workspace_root())
            log_text = str(log_result.output or log_result.stdout or "") if log_result.status == "done" else ""
            result = generate_changelog(
                log_text, _real_job_diff(job),
                get_connection=_connection, user_id=user_id, job_id=job_id,
            )
            append_agent_event(conn, job_id, SovereignAgentEvent(
                stage="changelog_generated" if result.markdown else "changelog_blocked",
                level="success" if result.markdown else "warning",
                message=(f"Changelog generated from {result.commit_count} real commit(s) via {result.source}." if result.markdown else f"Changelog unavailable: {result.error}")[:1200],
            ))
            return jsonify(changelog_signal(result)), 200 if result.markdown else 503
        finally:
            _close(conn)

    @app.route("/api/user/agent/jobs/<job_id>/draft-pr/prepare", methods=["POST"])
    @require_session
    def user_prepare_agent_draft_pr(job_id: str):
        user_id = _current_session_user_id()
        body = request.get_json(silent=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
        conn = _connection()
        try:
            job = _read_owned_job(conn, user_id, job_id)
            if not job:
                return jsonify({"error": "Job nicht gefunden"}), 404
            review = _review_job_diff(job, user_id)
            review_signal = auto_code_review_signal(review)
            if not review.passed:
                append_agent_event(conn, job_id, SovereignAgentEvent(
                    stage="draft_pr_blocked_by_auto_code_review",
                    level="warning",
                    message=review.summary[:1200],
                ))
                return jsonify({
                    "ok": False,
                    "runtime": "sovereign-agent",
                    "jobId": job_id,
                    "autoCodeReview": review_signal,
                    "blocker": review.decision,
                }), 409 if review.decision == "blocked_high" else 503
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
                "autoCodeReview": review_signal,
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
        body = request.get_json(silent=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
        raw_github_token = body.get("githubAccessToken")
        github_token = normalize_ephemeral_github_token(raw_github_token)
        if raw_github_token is not None and github_token is None:
            return jsonify({"error": "githubAccessToken has an invalid format"}), 400

        conn = _connection()
        try:
            # One job can cross the GitHub side-effect boundary only once at a time.
            # Holding the transaction-scoped lock lets a retry recover an existing
            # Draft PR before one atomic job-state + credit settlement commit.
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (f"agent-draft-pr:{job_id}",),
                )

            job = _read_owned_job(conn, user_id, job_id)
            if not job:
                conn.rollback()
                return jsonify({"error": "Job nicht gefunden"}), 404

            with conn.cursor() as cur:
                cur.execute(
                    """SELECT repair_id::text, entitlement_source, charged_credits,
                              published_head_sha, state
                       FROM sovereign_rescue_repairs
                       WHERE job_id = %s AND user_id = %s::uuid
                         AND state IN (
                             'reserved', 'running', 'blocked',
                             'draft_pr_ready', 'completed'
                         )
                       LIMIT 1""",
                    (job_id, user_id),
                )
                rescue_reservation = cur.fetchone()
            changed_file_blocker = repair_changed_file_limit_blocker(job.changed_files)
            if rescue_reservation and changed_file_blocker:
                conn.rollback()
                return jsonify({
                    "ok": False,
                    "runtime": "sovereign-agent",
                    "jobId": job_id,
                    "blocker": changed_file_blocker,
                    "changedFileCount": len(normalize_repair_changed_files(job.changed_files)),
                    "creditSettlement": {"chargedCredits": 0, "duplicate": False},
                }), 409
            credit_cost = 0 if rescue_reservation else 10

            if job.pr_state == "created" and (job.pr_url or job.draft_pr_url):
                result = create_draft_pr_for_job(job, token=github_token)
                published_head_sha = _bind_rescue_published_head(
                    conn,
                    reservation=rescue_reservation,
                    user_id=user_id,
                    job_id=job_id,
                    observed_head_sha=result.head_sha,
                )
                if rescue_reservation and not published_head_sha:
                    conn.rollback()
                    return jsonify({
                        "ok": False,
                        "runtime": "sovereign-agent",
                        "jobId": job_id,
                        "blocker": "rescue_published_head_sha_missing",
                    }), 409
                if rescue_reservation:
                    conn.commit()
                else:
                    conn.rollback()
                return jsonify({
                    "ok": result.allowed,
                    "runtime": "sovereign-agent",
                    "jobId": job_id,
                    "draftPrCreate": draft_pr_create_signal(result),
                    "creditSettlement": {
                        "chargedCredits": 0,
                        "duplicate": True,
                    },
                }), 200 if result.allowed else 400

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT credits, role FROM admin_users WHERE id = %s::uuid FOR UPDATE",
                    (user_id,),
                )
                user_row = cur.fetchone()
            if not user_row:
                conn.rollback()
                return jsonify({"error": "User nicht gefunden"}), 404

            is_admin = str(user_row.get("role") or "") in ("admin", "superadmin")
            available_credits = int(user_row.get("credits") or 0)
            if not is_admin and available_credits < credit_cost:
                conn.rollback()
                return jsonify({
                    "error": f"Nicht genügend Credits ({credit_cost} erforderlich)",
                    "availableCredits": available_credits,
                }), 402

            result = create_draft_pr_for_job(job, token=github_token)
            if not result.allowed or not result.pr_url:
                conn.rollback()
                return jsonify({
                    "ok": False,
                    "runtime": "sovereign-agent",
                    "jobId": job_id,
                    "draftPrCreate": draft_pr_create_signal(result),
                    "creditSettlement": {
                        "chargedCredits": 0,
                        "duplicate": False,
                    },
                }), 400

            published_head_sha = _bind_rescue_published_head(
                conn,
                reservation=rescue_reservation,
                user_id=user_id,
                job_id=job_id,
                observed_head_sha=result.head_sha,
            )
            if rescue_reservation and not published_head_sha:
                conn.rollback()
                return jsonify({
                    "ok": False,
                    "runtime": "sovereign-agent",
                    "jobId": job_id,
                    "blocker": "rescue_published_head_sha_missing",
                    "creditSettlement": {"chargedCredits": 0, "duplicate": False},
                }), 409

            remaining_credits: int | None = None
            charged_credits = 0
            if not is_admin and credit_cost > 0:
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE admin_users
                           SET credits = credits - %s
                           WHERE id = %s::uuid AND credits >= %s
                           RETURNING credits""",
                        (credit_cost, user_id, credit_cost),
                    )
                    updated_user = cur.fetchone()
                    if not updated_user:
                        conn.rollback()
                        return jsonify({
                            "error": "Credit-Stand änderte sich während der Draft-PR-Erstellung",
                            "blocker": "credit_settlement_race",
                        }), 409
                    remaining_credits = int(updated_user.get("credits") or 0)
                    cur.execute(
                        """INSERT INTO credit_ledger
                               (user_id, type, amount, reason, provider, provider_tx_id)
                           VALUES (%s::uuid, 'usage', %s, %s, 'sovereign-agent', %s)""",
                        (
                            user_id,
                            -credit_cost,
                            f"Agent Draft PR: {job_id}",
                            f"agent-pr:{job_id}",
                        ),
                    )
                charged_credits = credit_cost
            elif not is_admin:
                remaining_credits = available_credits

            mark_draft_pr_created(
                conn,
                job_id=job_id,
                pr_url=result.pr_url,
                commit=False,
            )
            if rescue_reservation:
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE sovereign_rescue_repairs
                           SET state = 'draft_pr_ready', updated_at = NOW()
                           WHERE job_id = %s AND user_id = %s::uuid""",
                        (job_id, user_id),
                    )
            conn.commit()
            return jsonify({
                "ok": True,
                "runtime": "sovereign-agent",
                "jobId": job_id,
                "draftPrCreate": draft_pr_create_signal(result),
                "creditSettlement": {
                    "chargedCredits": charged_credits,
                    "remainingCredits": remaining_credits,
                    "duplicate": False,
                },
            }), 200
        except Exception:
            conn.rollback()
            raise
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
        body = request.get_json(force=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
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
        body = request.get_json(force=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return jsonify({"error": "A JSON object is required"}), 400
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
