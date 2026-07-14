"""Authenticated Flask routes for the Sovereign cognitive swarm."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from typing import Any, Callable
import uuid

from flask import jsonify, request

from .cognitive_run_store import (
    AgentRunIterationLimit,
    AgentRunNotResumable,
    AgentRunResumeConflict,
    NON_RESUMABLE_RUN_STATUSES,
    claim_agent_run_for_resume,
    create_agent_run,
    list_resumable_agent_runs,
    read_agent_run,
    record_agent_failure,
    transition_agent_run,
)
from .cognitive_swarm_agents import run_cognitive_swarm
from .cognitive_swarm_manifest import manifest_payload


ConnectionFactory = Callable[[], Any]


_SECRET_MARKERS = (
    "sk-proj-",
    "github_pat_",
    "ghp_",
    "authorization: bearer",
    "begin openssh private key",
    "begin rsa private key",
)


def _contains_secret_shaped_text(value: str) -> bool:
    normalized = value.casefold()
    return any(marker in normalized for marker in _SECRET_MARKERS)


def _allowed_models() -> frozenset[str]:
    configured = os.getenv("SOVEREIGN_AGENTS_ALLOWED_MODELS", "gpt-5.6")
    values = frozenset(item.strip() for item in configured.split(",") if item.strip())
    return values or frozenset({"gpt-5.6"})


def _current_session_user_id() -> str:
    return str(getattr(request, "session_user_id", None) or "")


def _close_connection(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def _max_iterations() -> int:
    try:
        configured = int(os.getenv("SOVEREIGN_AGENTS_MAX_ITERATIONS", "12"))
    except ValueError:
        configured = 12
    return max(1, min(configured, 100))


def _resume_lease_seconds() -> int:
    try:
        configured = int(os.getenv("SOVEREIGN_AGENTS_RESUME_LEASE_SECONDS", "900"))
    except ValueError:
        configured = 900
    return max(30, min(configured, 3600))


def _digest_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stored_run_to_api(run: Any) -> dict[str, object]:
    return {
        "runId": run.run_id,
        "sessionKey": run.session_key,
        "status": run.status,
        "source": run.source,
        "evidenceId": run.evidence_id,
        "traceId": run.trace_id,
        "reason": run.reason,
        "nextAction": run.next_action,
        "missionSummary": run.mission_summary,
        "missionDigest": run.mission_digest,
        "maxActiveSpecialists": run.max_active_specialists,
        "maxIterations": run.max_iterations,
        "iterationCount": run.iteration_count,
        "leaseActive": run.lease_active,
        "resumeTaskId": run.resume_task_id,
        "resumeAvailable": (
            not run.lease_active
            and run.status not in NON_RESUMABLE_RUN_STATUSES
            and run.iteration_count < run.max_iterations
        ),
    }


def _execute_persisted_swarm(
    *,
    get_connection: ConnectionFactory,
    user_id: str,
    run_id: str,
    trace_id: str,
    mission: str,
    evidence: str,
    model: str | None,
    task_id: str | None = None,
    lease_token: str | None = None,
    response_context: dict[str, object] | None = None,
) -> tuple[dict[str, object], int]:
    manifest = manifest_payload()
    try:
        result = asyncio.run(
            run_cognitive_swarm(
                mission,
                evidence=evidence,
                model=model,
            )
        )
        final_status = str(result.get("status") or "BLOCKED")
        if final_status not in {"BLOCKED", "READY_FOR_DRAFT_PR"}:
            final_status = "BLOCKED"
        ready = final_status == "READY_FOR_DRAFT_PR" and bool(result.get("ok"))
        reason = (
            "Judge accepted the supplied evidence for Draft PR readiness."
            if ready
            else str(result.get("blocker") or "Required runtime evidence or protected configuration is missing.")
        )
        next_action = (
            "CREATE_DRAFT_PR_AFTER_OWNER_APPROVAL"
            if ready
            else "PROVIDE_MISSING_EVIDENCE_OR_PROTECTED_CONFIGURATION"
        )
        final_verdict = result.get("finalVerdict") if isinstance(result.get("finalVerdict"), dict) else {}
        evidence_payload = {
            "resultStatus": final_status,
            "ok": ready,
            "activeSpecialists": int(result.get("activeSpecialists") or 0),
            "manifestSchema": int((result.get("manifest") or manifest).get("schema") or 0),
            "finalVerdictDigest": _digest_json(final_verdict),
            "autoMerge": False,
        }
        conn = get_connection()
        try:
            final_state = transition_agent_run(
                conn,
                user_id=user_id,
                run_id=run_id,
                status=final_status,
                source="agents-sdk",
                trace_id=trace_id,
                reason=reason,
                next_action=next_action,
                evidence_kind="judge_verdict",
                evidence_summary=reason,
                evidence_payload=evidence_payload,
                agent_id="judge",
                task_id=task_id,
                expected_lease_token=lease_token,
            )
        finally:
            _close_connection(conn)
    except Exception as exc:
        try:
            conn = get_connection()
            try:
                failed_state = transition_agent_run(
                    conn,
                    user_id=user_id,
                    run_id=run_id,
                    status="FAILED_RECOVERABLE",
                    source="agents-sdk",
                    trace_id=trace_id,
                    reason="Agents SDK execution failed without a validated final verdict.",
                    next_action="RETRY_FROM_PERSISTED_RUN_STATE",
                    evidence_kind="runtime_failure",
                    evidence_summary="Agents SDK execution raised a bounded runtime failure.",
                    evidence_payload={"errorType": type(exc).__name__},
                    task_id=task_id,
                    expected_lease_token=lease_token,
                )
                record_agent_failure(
                    conn,
                    run_id=run_id,
                    agent_id="orchestrator",
                    family="AGENTS_SDK_EXECUTION_FAILED",
                    summary="Agents SDK execution failed; the persisted run remains resumable.",
                    evidence_id=failed_state["evidenceId"],
                    recoverable=True,
                    task_id=task_id,
                )
            finally:
                _close_connection(conn)
        except Exception as persistence_exc:
            return ({
                "ok": False,
                "runtime": "openai-agents-sdk",
                "runId": run_id,
                "traceId": trace_id,
                "error": type(exc).__name__,
                "blocker": "AGENT_RUN_FAILURE_PERSISTENCE_UNAVAILABLE",
                "persistenceErrorType": type(persistence_exc).__name__,
                **(response_context or {}),
            }, 502)
        return ({
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": run_id,
            "traceId": trace_id,
            "status": failed_state["status"],
            "source": failed_state["source"],
            "evidenceId": failed_state["evidenceId"],
            "reason": failed_state["reason"],
            "nextAction": failed_state["nextAction"],
            "error": type(exc).__name__,
            **(response_context or {}),
        }, 502)

    status_code = 200 if final_state["status"] == "READY_FOR_DRAFT_PR" else 503
    return ({
        "runtime": "openai-agents-sdk",
        **result,
        "runId": run_id,
        "traceId": trace_id,
        "status": final_state["status"],
        "source": final_state["source"],
        "evidenceId": final_state["evidenceId"],
        "reason": final_state["reason"],
        "nextAction": final_state["nextAction"],
        **(response_context or {}),
    }, status_code)


def register_cognitive_swarm_routes(
    app,
    *,
    require_session,
    get_connection: ConnectionFactory,
) -> None:
    @app.route("/api/user/agent/swarm/manifest", methods=["GET"])
    @require_session
    def user_get_cognitive_swarm_manifest():
        return jsonify({
            "ok": True,
            "runtime": "openai-agents-sdk",
            "configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
            "allowedModels": sorted(_allowed_models()),
            "manifest": manifest_payload(),
        })

    @app.route("/api/user/agent/swarm/runs/resumable", methods=["GET"])
    @require_session
    def user_list_resumable_cognitive_runs():
        user_id = _current_session_user_id()
        conn = get_connection()
        try:
            runs = list_resumable_agent_runs(conn, user_id=user_id, limit=50)
            return jsonify({
                "runtime": "openai-agents-sdk",
                "runs": [_stored_run_to_api(run) for run in runs],
                "total": len(runs),
            })
        finally:
            _close_connection(conn)

    @app.route("/api/user/agent/swarm/runs/<run_id>", methods=["GET"])
    @require_session
    def user_get_cognitive_run(run_id: str):
        user_id = _current_session_user_id()
        conn = get_connection()
        try:
            run = read_agent_run(conn, user_id=user_id, run_id=run_id)
            if not run:
                return jsonify({"error": "run not found"}), 404
            return jsonify({
                "runtime": "openai-agents-sdk",
                "run": _stored_run_to_api(run),
            })
        finally:
            _close_connection(conn)

    @app.route("/api/user/agent/swarm/runs/<run_id>/resume", methods=["POST"])
    @require_session
    def user_resume_cognitive_run(run_id: str):
        body: dict[str, Any] = request.get_json(force=True) or {}
        evidence = str(body.get("evidence") or body.get("evidenceText") or "").strip()
        model = str(body.get("model") or "").strip() or None

        if len(evidence) > 250_000:
            return jsonify({"error": "evidence exceeds the bounded input limit"}), 400
        if _contains_secret_shaped_text(evidence):
            return jsonify({"error": "secret-shaped material is forbidden in swarm input"}), 400
        if model and model not in _allowed_models():
            return jsonify({"error": "model is not allowlisted"}), 400

        user_id = _current_session_user_id()
        if not user_id:
            return jsonify({"error": "authenticated user id is required"}), 401
        trace_id = f"trace-{uuid.uuid4().hex}"

        try:
            conn = get_connection()
            try:
                claim = claim_agent_run_for_resume(
                    conn,
                    user_id=user_id,
                    run_id=run_id,
                    supplied_evidence=evidence,
                    trace_id=trace_id,
                    lease_seconds=_resume_lease_seconds(),
                )
            finally:
                _close_connection(conn)
        except LookupError:
            return jsonify({"error": "run not found"}), 404
        except AgentRunResumeConflict as exc:
            return jsonify({
                "ok": False,
                "runtime": "openai-agents-sdk",
                "runId": run_id,
                "status": "RUNNING",
                "blocker": "RUN_ALREADY_CLAIMED",
                "reason": str(exc),
                "nextAction": "WAIT_FOR_ACTIVE_RESUME_LEASE_OR_RETRY_AFTER_EXPIRY",
            }), 409
        except AgentRunIterationLimit as exc:
            reason = str(exc)
            try:
                conn = get_connection()
                try:
                    final_state = transition_agent_run(
                        conn,
                        user_id=user_id,
                        run_id=run_id,
                        status="FAILED_FINAL",
                        source="agents-sdk",
                        trace_id=trace_id,
                        reason=reason,
                        next_action="OWNER_REVIEW_REQUIRED",
                        evidence_kind="iteration_limit",
                        evidence_summary="The persisted run exhausted its bounded iteration budget.",
                        evidence_payload={"blocker": "RUN_ITERATION_LIMIT_EXHAUSTED"},
                        task_id=exc.resume_task_id,
                    )
                finally:
                    _close_connection(conn)
            except Exception as persistence_exc:
                return jsonify({
                    "ok": False,
                    "runtime": "openai-agents-sdk",
                    "runId": run_id,
                    "blocker": "RUN_ITERATION_LIMIT_PERSISTENCE_UNAVAILABLE",
                    "reason": reason,
                    "errorType": type(persistence_exc).__name__,
                }), 503
            return jsonify({
                "ok": False,
                "runtime": "openai-agents-sdk",
                "runId": run_id,
                "status": final_state["status"],
                "source": final_state["source"],
                "evidenceId": final_state["evidenceId"],
                "blocker": "RUN_ITERATION_LIMIT_EXHAUSTED",
                "reason": final_state["reason"],
                "nextAction": final_state["nextAction"],
            }), 409
        except AgentRunNotResumable as exc:
            return jsonify({
                "ok": False,
                "runtime": "openai-agents-sdk",
                "runId": run_id,
                "blocker": "RUN_NOT_RESUMABLE",
                "reason": str(exc),
                "nextAction": "READ_PERSISTED_RUN_STATE",
            }), 409
        except Exception as exc:
            return jsonify({
                "ok": False,
                "runtime": "openai-agents-sdk",
                "runId": run_id,
                "blocker": "RUN_RESUME_PERSISTENCE_UNAVAILABLE",
                "errorType": type(exc).__name__,
            }), 503

        resume_context = {
            "persistedRunId": claim.run.run_id,
            "persistedMissionDigest": claim.run.mission_digest,
            "previousStatus": claim.run.status,
            "previousEvidenceId": claim.run.evidence_id,
            "recoveryTaskId": claim.task_id,
            "recoveryWorkPackage": claim.work_package,
            "missionWasBoundedSummary": True,
        }
        execution_evidence = (
            "Persisted resume context:\n"
            f"{json.dumps(resume_context, ensure_ascii=False, sort_keys=True)}\n\n"
            "New runtime evidence:\n"
            f"{evidence or '[no new evidence supplied]'}"
        )
        payload, status_code = _execute_persisted_swarm(
            get_connection=get_connection,
            user_id=user_id,
            run_id=claim.run.run_id,
            trace_id=trace_id,
            mission=claim.run.mission_summary,
            evidence=execution_evidence,
            model=model,
            task_id=claim.task_id,
            lease_token=claim.lease_token,
            response_context={
                "sessionKey": claim.run.session_key,
                "resumed": True,
                "resumeClaimEvidenceId": claim.evidence_id,
                "recoveryTask": {
                    "taskId": claim.task_id,
                    "workPackage": claim.work_package,
                    "leaseSeconds": claim.lease_seconds,
                },
            },
        )
        return jsonify(payload), status_code

    @app.route("/api/user/agent/swarm/run", methods=["POST"])
    @require_session
    def user_run_cognitive_swarm():
        body: dict[str, Any] = request.get_json(force=True) or {}
        mission = str(body.get("mission") or "").strip()
        evidence = str(body.get("evidence") or body.get("evidenceText") or "").strip()
        model = str(body.get("model") or "").strip() or None

        if not mission:
            return jsonify({"error": "mission is required"}), 400
        if len(mission) > 20_000:
            return jsonify({"error": "mission exceeds the bounded input limit"}), 400
        if len(evidence) > 250_000:
            return jsonify({"error": "evidence exceeds the bounded input limit"}), 400
        if _contains_secret_shaped_text(mission) or _contains_secret_shaped_text(evidence):
            return jsonify({"error": "secret-shaped material is forbidden in swarm input"}), 400
        if model and model not in _allowed_models():
            return jsonify({"error": "model is not allowlisted"}), 400

        user_id = _current_session_user_id()
        if not user_id:
            return jsonify({"error": "authenticated user id is required"}), 401

        manifest = manifest_payload()
        run_id = f"run-{uuid.uuid4().hex}"
        session_key = f"session-{uuid.uuid4().hex}"
        trace_id = f"trace-{uuid.uuid4().hex}"

        try:
            conn = get_connection()
            try:
                received_state = create_agent_run(
                    conn,
                    user_id=user_id,
                    run_id=run_id,
                    session_key=session_key,
                    mission=mission,
                    supplied_evidence=evidence,
                    trace_id=trace_id,
                    max_active_specialists=int(manifest["maxActiveSpecialists"]),
                    max_iterations=_max_iterations(),
                )
            finally:
                _close_connection(conn)
        except Exception as exc:
            return jsonify({
                "ok": False,
                "runtime": "openai-agents-sdk",
                "error": "agent run persistence unavailable",
                "blocker": "AGENT_RUN_PERSISTENCE_UNAVAILABLE",
                "errorType": type(exc).__name__,
            }), 503

        payload, status_code = _execute_persisted_swarm(
            get_connection=get_connection,
            user_id=user_id,
            run_id=run_id,
            trace_id=trace_id,
            mission=mission,
            evidence=evidence,
            model=model,
            response_context={
                "sessionKey": session_key,
                "resumed": False,
                "receivedEvidenceId": received_state["evidenceId"],
            },
        )
        return jsonify(payload), status_code
