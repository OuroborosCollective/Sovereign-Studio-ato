"""Authenticated Flask routes for the Sovereign cognitive swarm."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any, Callable
import uuid

from flask import jsonify, request

from .a2a_routes import register_a2a_routes
from .cognitive_run_store import (
    AgentRunIterationLimit,
    AgentRunNotResumable,
    AgentRunResumeConflict,
    NON_RESUMABLE_RUN_STATUSES,
    claim_agent_run_for_resume,
    create_agent_run,
    link_agent_run_job,
    list_resumable_agent_runs,
    read_agent_run,
    read_agent_task_ids,
    record_agent_failure,
    record_agent_stage_event,
    request_agent_approval,
    transition_agent_run,
)
from .cognitive_swarm_agents import (
    ALLOWED_LITELLM_MODEL_ALIASES,
    DEFAULT_MODEL,
    MissionIntent,
    RepositoryToolFactory,
    SwarmExecutionError,
    classify_mission_intent,
    classify_swarm_exception,
    run_cognitive_swarm,
    run_free_single_agent,
)
from .cognitive_repository_tools import (
    BoundRepositoryToolset,
    create_repository_single_agent_task,
    create_repository_swarm_tasks,
)
from .cognitive_swarm_manifest import WORKER_ROLES, manifest_payload
from .cognitive_usage_billing import AgentBillingError, AgentStageBilling
from .evidence_gate import EvidenceGateInput, evaluate_agent_evidence
from .job_lifecycle import create_sovereign_agent_job
from .job_store import read_agent_job
from .pattern_gateway import (
    evaluate_pattern_learning,
    pattern_input_from_job,
    persist_pattern_learning_candidate_once,
)
from .pattern_vector_memory import persist_pattern_vector
from llm_execution_resolver import (
    FREE_SINGLE_AGENT_PROFILE,
    PAID_SWARM_PROFILE,
    ExecutionResolution,
    ExecutionResolutionError,
    advance_free_revolver_resolution,
    free_fallback_resolution,
    load_execution_resolution,
)
from llm_revolver import route_quota_scope
from llm_transport import route_provider_model, route_transport


ConnectionFactory = Callable[[], Any]
_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_INTENT_MODES = frozenset({"auto", "conversation", "read_only_analysis", "repository_execution"})


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


def _normalize_intent_mode(value: str, *, free_profile: bool) -> str:
    selected = str(value or "auto").strip().casefold().replace("-", "_").replace(" ", "_")
    if selected not in _INTENT_MODES:
        raise ValueError("intentMode must be auto, conversation, read_only_analysis or repository_execution")
    if free_profile and selected == "auto":
        return "conversation"
    return selected


def _explicit_mission_intent(intent_mode: str, mission: str) -> MissionIntent | None:
    if intent_mode == "auto":
        return None
    return MissionIntent(
        mode=intent_mode,
        normalized_goal=str(mission or "").strip()[:2000],
        requires_online_tools=intent_mode != "conversation",
        requires_repository_workspace=intent_mode == "repository_execution",
        learning_scope=[],
        confidence=1.0,
    )


def _allowed_models() -> frozenset[str]:
    """Keep the legacy alias allowlist fail-closed for old test/operator callers.

    Product execution ignores environment-provided model lists and resolves
    direct OpenRouter or FreeLLM routes from PostgreSQL instead.
    """

    return frozenset({DEFAULT_MODEL}) & ALLOWED_LITELLM_MODEL_ALIASES


def _current_session_user_id() -> str:
    return str(getattr(request, "session_user_id", None) or "")


def _close_connection(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def _service_owner_user_id(get_connection: ConnectionFactory) -> str | None:
    """Resolve only the configured owner when the existing internal key matches."""

    expected = os.getenv("SOVEREIGN_OWNER_REQUEST_KEY", "").strip()
    supplied = str(request.headers.get("X-Sovereign-Owner-Request-Key") or "").strip()
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        return None
    expected_id = os.getenv("SOVEREIGN_OWNER_ADMIN_ID", "").strip()
    expected_email = os.getenv("SOVEREIGN_OWNER_ADMIN_EMAIL", "").strip().lower()
    if not expected_id and not expected_email:
        raise RuntimeError("Sovereign owner identity is not configured")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if expected_id:
                cur.execute(
                    "SELECT id::text FROM admin_users WHERE id=%s::uuid LIMIT 1",
                    (expected_id,),
                )
            else:
                cur.execute(
                    "SELECT id::text FROM admin_users WHERE lower(email)=lower(%s) LIMIT 1",
                    (expected_email,),
                )
            row = cur.fetchone()
    finally:
        _close_connection(conn)
    if not row:
        raise LookupError("Configured Sovereign owner was not found")
    return str(row["id"])


def _workspace_root() -> Path | None:
    configured = os.getenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", "").strip()
    return Path(configured) if configured else None


def _configured_repository() -> str:
    value = os.getenv(
        "SOVEREIGN_CONTROLLER_REPOSITORY",
        "OuroborosCollective/Sovereign-Studio-ato",
    ).strip()
    if not _REPOSITORY_PATTERN.fullmatch(value):
        raise RuntimeError("SOVEREIGN_CONTROLLER_REPOSITORY is invalid")
    return value


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
        "jobId": run.job_id,
        "sessionKey": run.session_key,
        "a2aContextId": run.a2a_context_id,
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


def _billing_blocker_contract(exc: AgentBillingError) -> tuple[str, str]:
    """Return a bounded reason/action pair without exposing provider details."""

    contracts = {
        "OPENROUTER_PAID_ROUTE_NOT_READY": (
            "The selected direct OpenRouter route is not active and ready.",
            "ACTIVATE_VERIFIED_OPENROUTER_ROUTE",
        ),
        "OPENROUTER_PAID_ROUTE_REJECTED": (
            "The selected route failed the direct OpenRouter policy contract.",
            "REPAIR_OPENROUTER_ROUTE_POLICY",
        ),
        "OPENROUTER_ROUTE_CHANGED_BEFORE_RESERVATION": (
            "The selected OpenRouter route or price changed before reservation.",
            "REFRESH_OPENROUTER_MODELS_AND_RETRY",
        ),
        "AGENTS_OPENROUTER_ROUTE_REQUIRED": (
            "Paid agent execution requires a direct OpenRouter route.",
            "ACTIVATE_VERIFIED_OPENROUTER_ROUTE",
        ),
        "AGENTS_LITELLM_ALIAS_NOT_READY": (
            "The Agents SDK LiteLLM alias is not active and ready for paid execution.",
            "ACTIVATE_PRICE_VERIFIED_LITELLM_ROUTE",
        ),
        "AGENTS_ROUTE_PRICING_UNVERIFIED": (
            "The Agents SDK route has no verified provider pricing contract.",
            "VERIFY_OPENROUTER_ROUTE_PRICING",
        ),
        "AGENTS_PROVIDER_MODEL_MISMATCH": (
            "The Agents SDK route does not target the required provider model.",
            "ATTACH_EXPECTED_LITELLM_PROVIDER_MODEL",
        ),
        "AGENTS_STANDARD_ROUTE_REQUIRED": (
            "The Agents SDK route does not satisfy the standard cost-policy floor.",
            "CONFIGURE_STANDARD_OPENROUTER_ROUTE",
        ),
        "AGENT_INPUT_COST_BOUND_EXCEEDED": (
            "The Agents SDK input exceeds the bounded cost envelope.",
            "REDUCE_AGENT_INPUT_OR_SPLIT_STAGE",
        ),
        "AGENT_BILLING_USER_NOT_FOUND": (
            "The authenticated owner has no billable account state.",
            "RESTORE_AGENT_BILLING_ACCOUNT",
        ),
        "CREDIT_STATE_VERIFICATION_FAILED": (
            "The cached credit balance does not match the verified ledger balance.",
            "RECONCILE_CREDIT_LEDGER_AND_CACHE",
        ),
        "PAID_CREDIT_PURCHASE_REQUIRED": (
            "The Agents SDK route requires credits backed by a verified purchase.",
            "PURCHASE_PAID_CREDITS",
        ),
        "INSUFFICIENT_PROVIDER_FUNDED_CREDITS": (
            "The Agents SDK cost reservation is not backed by enough provider-funded credits.",
            "PURCHASE_OR_REPLENISH_PROVIDER_FUNDED_CREDITS",
        ),
        "AGENT_ACTUAL_COST_EXCEEDED_RESERVATION": (
            "The verified provider cost exceeded the reserved provider-funded credits.",
            "PURCHASE_OR_REPLENISH_PROVIDER_FUNDED_CREDITS",
        ),
    }
    return contracts.get(
        exc.family,
        (
            "The Agents SDK billing contract blocked model execution.",
            "REVIEW_AGENT_BILLING_CONFIGURATION",
        ),
    )


def _persist_billing_blocker(
    *,
    get_connection: ConnectionFactory,
    user_id: str,
    run_id: str,
    trace_id: str,
    exc: AgentBillingError,
    task_id: str | None = None,
    expected_lease_token: str | None = None,
) -> dict[str, str]:
    reason, next_action = _billing_blocker_contract(exc)
    provider_execution_prevented = exc.family != "AGENT_ACTUAL_COST_EXCEEDED_RESERVATION"
    evidence_summary = (
        "The model call was blocked before provider execution."
        if provider_execution_prevented
        else "The completed provider call requires billing reconciliation before the run may continue."
    )
    conn = get_connection()
    try:
        return transition_agent_run(
            conn,
            user_id=user_id,
            run_id=run_id,
            status="BLOCKED",
            source="agents-sdk",
            trace_id=trace_id,
            reason=reason,
            next_action=next_action,
            evidence_kind="agent_billing_blocker",
            evidence_summary=evidence_summary,
            evidence_payload={
                **exc.safe_payload(),
                "providerExecutionPrevented": provider_execution_prevented,
            },
            agent_id="billing",
            task_id=task_id,
            expected_lease_token=expected_lease_token,
        )
    finally:
        _close_connection(conn)


def execute_persisted_swarm(
    *,
    get_connection: ConnectionFactory,
    user_id: str,
    run_id: str,
    trace_id: str,
    mission: str,
    evidence: str,
    model: str | None,
    route: dict[str, Any],
    agent_route: dict[str, Any] | None = None,
    task_id: str | None = None,
    lease_token: str | None = None,
    response_context: dict[str, object] | None = None,
    repository_tool_factory: RepositoryToolFactory | None = None,
    repository_tool_summary: Callable[[], dict[str, Any]] | None = None,
    job_id: str | None = None,
    task_ids_by_agent: dict[str, str] | None = None,
    stage_billing: AgentStageBilling | None = None,
) -> tuple[dict[str, object], int]:
    manifest = manifest_payload()

    def persist_stage_event(stage: dict[str, object]) -> None:
        agent_id = str(stage.get("agentId") or "orchestrator").strip()
        event_type = str(stage.get("eventType") or "agent_stage").strip()
        status = str(stage.get("status") or "RUNNING").strip()
        summary = str(stage.get("summary") or "Agent stage changed.").strip()
        next_action = str(stage.get("nextAction") or "WAIT_FOR_AGENT").strip()
        loop_value = stage.get("loop")
        stage_task_id = (task_ids_by_agent or {}).get(agent_id) or task_id
        safe_payload: dict[str, object] = {
            "agentId": agent_id,
            "eventType": event_type,
            "status": status,
            "rawModelOutputPersisted": False,
        }
        if isinstance(loop_value, int):
            safe_payload["loop"] = loop_value
        conn = get_connection()
        try:
            record_agent_stage_event(
                conn,
                user_id=user_id,
                run_id=run_id,
                trace_id=trace_id,
                agent_id=agent_id,
                event_type=event_type,
                status=status,
                summary=summary,
                next_action=next_action,
                evidence_payload=safe_payload,
                task_id=stage_task_id,
                expected_lease_token=lease_token,
            )
        finally:
            _close_connection(conn)

    try:
        result = asyncio.run(
            run_cognitive_swarm(
                mission,
                evidence=evidence,
                model=model,
                main_route=route,
                agent_route=agent_route or route,
                stage_observer=persist_stage_event,
                repository_tool_factory=repository_tool_factory,
                stage_billing=stage_billing,
            )
        )
        repository_summary = repository_tool_summary() if callable(repository_tool_summary) else {}
        job_evidence: dict[str, object] = {}
        learning_evidence: dict[str, object] = {
            "state": "NOT_REQUESTED" if not job_id else "PENDING_EVIDENCE",
            "candidateId": None,
            "candidateCreated": False,
            "vectorStored": False,
        }
        execution_gate = None
        if job_id:
            conn = get_connection()
            try:
                stored_job = read_agent_job(conn, user_id=user_id, job_id=job_id)
            finally:
                _close_connection(conn)
            if not stored_job:
                raise RuntimeError("linked Sovereign Agent Job disappeared during swarm execution")
            execution_gate = evaluate_agent_evidence(EvidenceGateInput(
                job_id=stored_job.job_id,
                changed_files=stored_job.changed_files,
                diff_summary=stored_job.diff_summary,
                test_summary=stored_job.test_summary,
                blocker=stored_job.blocker,
                tool_status=stored_job.status,
            ))
            job_evidence = {
                "jobId": stored_job.job_id,
                "workspaceId": stored_job.workspace_id,
                "status": stored_job.status,
                "changedFiles": list(stored_job.changed_files),
                "hasDiff": bool(stored_job.diff_summary),
                "hasTests": bool(stored_job.test_summary),
                "blocker": stored_job.blocker,
                "gatePassed": execution_gate.passed,
                "gateReason": execution_gate.reason,
                "canLearnPattern": execution_gate.can_learn_pattern,
            }
            pattern_result = evaluate_pattern_learning(
                pattern_input_from_job(stored_job, source="agents-sdk-swarm")
            )
            learning_evidence.update({
                "decision": pattern_result.decision,
                "kind": pattern_result.kind,
                "signal": pattern_result.predictive_signal,
                "blockers": list(pattern_result.blockers),
                "remoteMemoryAllowed": pattern_result.remote_memory_allowed,
            })
            if pattern_result.allowed:
                conn = get_connection()
                try:
                    candidate_id, candidate_created = persist_pattern_learning_candidate_once(
                        conn,
                        user_id=user_id,
                        result=pattern_result,
                    )
                    vector_result = (
                        persist_pattern_vector(
                            conn,
                            candidate_id=candidate_id,
                            user_id=user_id,
                            result=pattern_result,
                        )
                        if candidate_id
                        else {"stored": False, "reason": "candidate_not_persisted"}
                    )
                finally:
                    _close_connection(conn)
                learning_evidence.update({
                    "state": "STORED" if vector_result.get("stored") else "CANDIDATE_ONLY",
                    "candidateId": candidate_id,
                    "candidateCreated": candidate_created,
                    "vectorStored": bool(vector_result.get("stored")),
                    "vectorStorage": vector_result.get("storage"),
                    "vectorReason": vector_result.get("reason"),
                })
        final_status = str(result.get("status") or "BLOCKED")
        roles_with_calls = set(repository_summary.get("rolesWithCalls") or [])
        missing_tool_roles = sorted(set(WORKER_ROLES) - roles_with_calls) if repository_tool_factory else []
        if final_status in {"READY_FOR_DRAFT_PR", "COMPLETED"} and missing_tool_roles:
            final_status = "BLOCKED"
            result["ok"] = False
            result["status"] = final_status
            result["blocker"] = f"Repository tool evidence is missing for roles: {', '.join(missing_tool_roles)}"
        if final_status in {"READY_FOR_DRAFT_PR", "COMPLETED"} and job_id and not (execution_gate and execution_gate.passed):
            final_status = "BLOCKED"
            result["ok"] = False
            result["status"] = final_status
            result["blocker"] = execution_gate.reason if execution_gate else "Repository execution evidence is unavailable."
        result["repositoryTools"] = repository_summary
        result["jobEvidence"] = job_evidence
        result["learningEvidence"] = learning_evidence
        result["missingRepositoryToolRoles"] = missing_tool_roles
        if final_status not in {"BLOCKED", "READY_FOR_DRAFT_PR", "COMPLETED"}:
            final_status = "BLOCKED"
        ready = final_status == "READY_FOR_DRAFT_PR" and bool(result.get("ok"))
        completed = final_status == "COMPLETED" and bool(result.get("ok"))
        accepted = ready or completed
        reason = (
            "Judge accepted the supplied evidence for Draft PR readiness."
            if ready
            else "Judge completed the evidence-only mission without repository changes."
            if completed
            else str(result.get("blocker") or "Required runtime evidence or protected configuration is missing.")
        )
        next_action = (
            "CREATE_DRAFT_PR_AFTER_OWNER_APPROVAL"
            if ready
            else "NO_FURTHER_ACTION_REQUIRED"
            if completed
            else "PROVIDE_MISSING_EVIDENCE_OR_PROTECTED_CONFIGURATION"
        )
        final_verdict = result.get("finalVerdict") if isinstance(result.get("finalVerdict"), dict) else {}
        approval_required = ready and bool(final_verdict.get("human_approval_required", True))
        hunt_outcome = str(final_verdict.get("hunt_outcome") or "").strip().upper()
        if hunt_outcome not in {"FINDING", "NULLFIND", "BLOCKED"}:
            hunt_outcome = ""
        error_family = str(final_verdict.get("error_family") or "").strip()[:160]
        next_error_family = str(final_verdict.get("next_error_family") or "").strip()[:160]
        nullfind_confirmed = (
            hunt_outcome == "NULLFIND"
            and bool(final_verdict.get("nullfind_confirmed"))
            and completed
        )
        release_hunt = {
            "outcome": hunt_outcome,
            "errorFamily": error_family,
            "nextErrorFamily": next_error_family if nullfind_confirmed else "",
            "nullfindConfirmed": nullfind_confirmed,
        }
        evidence_payload = {
            "resultStatus": final_status,
            "ok": accepted,
            "missionCompleted": completed,
            "activeSpecialists": int(result.get("activeSpecialists") or 0),
            "manifestSchema": int((result.get("manifest") or manifest).get("schema") or 0),
            "finalVerdictDigest": _digest_json(final_verdict),
            "releaseHunt": release_hunt,
            "repositoryTools": repository_summary,
            "jobEvidence": job_evidence,
            "learningEvidence": learning_evidence,
            "learningState": str(learning_evidence.get("state") or "PENDING_EVIDENCE"),
            "autoMerge": False,
        }
        conn = get_connection()
        try:
            if approval_required:
                final_state = request_agent_approval(
                    conn,
                    user_id=user_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    kind="draft_pr_readiness",
                    requested_by_agent="judge",
                    reason="Judge accepted the evidence; active user approval is required before Draft-PR readiness.",
                    next_action="OWNER_APPROVAL_REQUIRED_FOR_DRAFT_PR",
                    evidence_payload={
                        **evidence_payload,
                        "judgeReady": True,
                        "ownerApprovalRequired": True,
                    },
                    task_id=task_id,
                    expected_lease_token=lease_token,
                )
            else:
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
        billing_failure = isinstance(exc, AgentBillingError)
        if billing_failure:
            billing_reason, billing_next_action = _billing_blocker_contract(exc)
            failure = exc.safe_payload()
            failure.update({
                "failureStage": "billing",
                "errorType": type(exc).__name__,
                "nextAction": billing_next_action,
                "retryable": False,
                "httpStatus": exc.status_code,
                "requestId": None,
            })
        elif isinstance(exc, SwarmExecutionError):
            failure = exc.safe_payload()
        else:
            failure = {
                "failureStage": "unknown",
                "failureFamily": "AGENTS_SDK_EXECUTION_FAILED",
                "errorType": type(exc).__name__,
                "nextAction": "INSPECT_BOUNDED_SDK_FAILURE_EVIDENCE",
                "retryable": True,
                "httpStatus": None,
                "requestId": None,
                "rawErrorPersisted": False,
            }
        failure_family = str(failure["failureFamily"])
        failure_stage = str(failure["failureStage"])
        failure_next_action = str(failure["nextAction"])
        failure_retryable = bool(failure["retryable"])
        failure_status = (
            "BLOCKED"
            if billing_failure or not failure_retryable
            else "FAILED_RECOVERABLE"
        )
        failure_reason = (
            billing_reason
            if billing_failure
            else f"Agents SDK execution failed at {failure_stage} ({failure_family})."
        )
        try:
            conn = get_connection()
            try:
                failed_state = transition_agent_run(
                    conn,
                    user_id=user_id,
                    run_id=run_id,
                    status=failure_status,
                    source="agents-sdk",
                    trace_id=trace_id,
                    reason=failure_reason,
                    next_action=failure_next_action,
                    evidence_kind="runtime_failure",
                    evidence_summary=failure_reason,
                    evidence_payload=failure,
                    task_id=task_id,
                    expected_lease_token=lease_token,
                )
                record_agent_failure(
                    conn,
                    run_id=run_id,
                    agent_id="orchestrator",
                    family=failure_family,
                    summary=failure_reason,
                    evidence_id=failed_state["evidenceId"],
                    recoverable=failure_retryable,
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
                "error": str(failure["errorType"]),
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
            "blocker": failure_family,
            "failureStage": failure_stage,
            "retryable": failure_retryable,
            "httpStatus": failure["httpStatus"],
            "requestId": failure["requestId"],
            "error": str(failure["errorType"]),
            **(response_context or {}),
        }, exc.status_code if billing_failure else (502 if failure_retryable else 503))

    status_code = (
        202 if final_state["status"] == "WAITING_FOR_OWNER"
        else 200 if final_state["status"] in {"READY_FOR_DRAFT_PR", "COMPLETED"}
        else 503
    )
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
        "approvalId": final_state.get("approvalId"),
        "approvalKind": final_state.get("approvalKind"),
        **(response_context or {}),
    }, status_code)


def _persist_execution_resolution_blocker(
    get_connection: ConnectionFactory,
    *,
    user_id: str,
    run_id: str,
    trace_id: str,
    status: str,
    blocker: str,
    reason: str,
    next_action: str,
    error_type: str = "",
    task_id: str | None = None,
    expected_lease_token: str | None = None,
) -> dict[str, str]:
    """Persist one route-resolution blocker after the run truth already exists."""
    conn = get_connection()
    try:
        return transition_agent_run(
            conn,
            user_id=user_id,
            run_id=run_id,
            status=status,
            source="agents-sdk",
            trace_id=trace_id,
            reason=reason,
            next_action=next_action,
            evidence_kind="llm_execution_resolution_blocker",
            evidence_summary=reason,
            evidence_payload={
                "blocker": str(blocker)[:160],
                "errorType": str(error_type)[:160] or None,
                "providerExecutionPrevented": True,
                "backgroundAgentsStarted": 0,
                "rawErrorPersisted": False,
            },
            agent_id="execution_resolver",
            task_id=task_id,
            expected_lease_token=expected_lease_token,
        )
    finally:
        _close_connection(conn)


def _record_route_cooldown(
    get_connection: ConnectionFactory,
    *,
    execution_resolution: Any,
    failure: SwarmExecutionError,
) -> None:
    """Persist a bounded cooldown so later runs skip one unavailable quota scope."""
    try:
        failed_stage = str(getattr(failure, "stage", "") or "").casefold()
        selected = (
            execution_resolution.agent_route
            if ":worker:" in failed_stage
            else execution_resolution.primary_route
        )
        route = dict(selected)
        scope = route_quota_scope(route)
    except (AttributeError, TypeError, ValueError):
        return
    family = str(getattr(failure, "family", "") or "").casefold()
    cooldown_seconds = (
        3600
        if "quota" in family
        else 60
        if getattr(failure, "http_status", None) == 429
        else 300
    )
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO llm_route_revolver_state
                       (quota_scope, status, consecutive_failures, cooldown_until,
                        quota_remaining, quota_reset_at,
                        last_route_id, last_http_status, last_blocker,
                        last_attempt_at, updated_at)
                   VALUES (%s, 'cooldown', 1,
                           NOW() + (%s * INTERVAL '1 second'),
                           0, NOW() + (%s * INTERVAL '1 second'),
                           %s, %s, %s, NOW(), NOW())
                   ON CONFLICT (quota_scope) DO UPDATE SET
                       status='cooldown',
                       consecutive_failures=llm_route_revolver_state.consecutive_failures + 1,
                       cooldown_until=EXCLUDED.cooldown_until,
                       quota_remaining=0,
                       quota_reset_at=EXCLUDED.quota_reset_at,
                       last_route_id=EXCLUDED.last_route_id,
                       last_http_status=EXCLUDED.last_http_status,
                       last_blocker=EXCLUDED.last_blocker,
                       last_attempt_at=NOW(),
                       updated_at=NOW()""",
                (
                    scope,
                    cooldown_seconds,
                    cooldown_seconds,
                    str(route.get("id") or "")[:240],
                    failure.http_status,
                    failure.family[:240],
                ),
            )
        conn.commit()
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
    finally:
        _close_connection(conn)


def start_cognitive_swarm_run(
    *,
    get_connection: ConnectionFactory,
    user_id: str,
    mission: str,
    evidence: str = "",
    model: str | None = None,
    main_model: str | None = None,
    agent_model: str | None = None,
    mode: str = "auto",
    intent_mode: str = "auto",
    run_id: str | None = None,
    session_key: str | None = None,
    a2a_context_id: str | None = None,
    trace_id: str | None = None,
    _reuse_received_state: dict[str, str] | None = None,
    _force_free_profile: bool = False,
    _fallback_reason: str = "",
    _free_resolution_override: ExecutionResolution | None = None,
    _free_retry_count: int = 0,
    _free_implementation_job: Any | None = None,
    _free_repository_toolset: Any | None = None,
    _free_task_id: str | None = None,
    _free_mission_intent: Any | None = None,
) -> tuple[dict[str, object], int]:
    """Execute the single persisted Agents SDK start path for REST and A2A."""

    normalized_mission = str(mission or "").strip()
    normalized_evidence = str(evidence or "").strip()
    normalized_model = str(model or "").strip() or None
    normalized_main_model = str(main_model or normalized_model or "").strip() or None
    normalized_agent_model = str(
        agent_model or normalized_model or normalized_main_model or ""
    ).strip() or None
    normalized_mode = str(mode or "auto").strip().lower()
    try:
        normalized_intent_mode = _normalize_intent_mode(
            intent_mode,
            free_profile=normalized_mode == "free" or _force_free_profile,
        )
    except ValueError as exc:
        return {"error": str(exc)}, 400
    if not normalized_mission:
        return {"error": "mission is required"}, 400
    if len(normalized_mission) > 20_000:
        return {"error": "mission exceeds the bounded input limit"}, 400
    if len(normalized_evidence) > 250_000:
        return {"error": "evidence exceeds the bounded input limit"}, 400
    if _contains_secret_shaped_text(normalized_mission) or _contains_secret_shaped_text(normalized_evidence):
        return {"error": "secret-shaped material is forbidden in swarm input"}, 400
    if any(
        selected and len(selected) > 240
        for selected in (normalized_model, normalized_main_model, normalized_agent_model)
    ):
        return {"error": "model identifier exceeds the bounded limit"}, 400
    if not user_id:
        return {"error": "authenticated user id is required"}, 401

    resolved_run_id = str(run_id or f"run-{uuid.uuid4().hex}").strip()
    resolved_session_key = str(session_key or f"session-{uuid.uuid4().hex}").strip()
    resolved_trace_id = str(trace_id or f"trace-{uuid.uuid4().hex}").strip()
    manifest = manifest_payload()
    if _reuse_received_state is not None:
        received_state = dict(_reuse_received_state)
    else:
        try:
            conn = get_connection()
            try:
                received_state = create_agent_run(
                    conn,
                    user_id=user_id,
                    run_id=resolved_run_id,
                    session_key=resolved_session_key,
                    mission=normalized_mission,
                    supplied_evidence=normalized_evidence,
                    trace_id=resolved_trace_id,
                    max_active_specialists=int(manifest["maxActiveSpecialists"]),
                    max_iterations=_max_iterations(),
                    job_id=None,
                    a2a_context_id=a2a_context_id,
                )
            finally:
                _close_connection(conn)
        except Exception as exc:
            return {
                "ok": False,
                "runtime": "openai-agents-sdk",
                "error": "agent run persistence unavailable",
                "blocker": "AGENT_RUN_PERSISTENCE_UNAVAILABLE",
                "errorType": type(exc).__name__,
            }, 503

    resolver_mode = "free" if _force_free_profile else normalized_mode
    try:
        execution_resolution = (
            _free_resolution_override
            if _free_resolution_override is not None
            else load_execution_resolution(
                get_connection,
                user_id=user_id,
                requested_model="" if _force_free_profile else normalized_model or "",
                requested_main_model=(
                    "" if _force_free_profile else normalized_main_model or ""
                ),
                requested_agent_model=(
                    "" if _force_free_profile else normalized_agent_model or ""
                ),
                requested_mode=resolver_mode,
            )
        )
    except ExecutionResolutionError as exc:
        state = _persist_execution_resolution_blocker(
            get_connection,
            user_id=user_id,
            run_id=resolved_run_id,
            trace_id=resolved_trace_id,
            status="BLOCKED",
            blocker=exc.failure_family,
            reason=str(exc),
            next_action=(
                "PURCHASE_CREDITS"
                if exc.failure_family == "paid_purchase_required"
                else "ADD_PROVIDER_FUNDED_CREDITS"
                if exc.failure_family == "paid_credits_required"
                else "ACTIVATE_VERIFIED_OPENROUTER_ROUTE"
            ),
            error_type=type(exc).__name__,
        )
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": resolved_run_id,
            "traceId": resolved_trace_id,
            "status": state["status"],
            "source": state["source"],
            "evidenceId": state["evidenceId"],
            "receivedEvidenceId": received_state["evidenceId"],
            "blocker": exc.failure_family,
            "reason": state["reason"],
            "nextAction": state["nextAction"],
            "requestedMode": normalized_mode,
            "secretValuesReturned": False,
        }, exc.status_code
    except LookupError as exc:
        state = _persist_execution_resolution_blocker(
            get_connection,
            user_id=user_id,
            run_id=resolved_run_id,
            trace_id=resolved_trace_id,
            status="BLOCKED",
            blocker="AGENT_BILLING_USER_NOT_FOUND",
            reason="The authenticated user has no persisted account state for route resolution.",
            next_action="RESTORE_AGENT_BILLING_ACCOUNT",
            error_type=type(exc).__name__,
        )
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": resolved_run_id,
            "traceId": resolved_trace_id,
            "status": state["status"],
            "source": state["source"],
            "evidenceId": state["evidenceId"],
            "receivedEvidenceId": received_state["evidenceId"],
            "blocker": "AGENT_BILLING_USER_NOT_FOUND",
            "reason": state["reason"],
            "nextAction": state["nextAction"],
        }, 404
    except Exception as exc:
        state = _persist_execution_resolution_blocker(
            get_connection,
            user_id=user_id,
            run_id=resolved_run_id,
            trace_id=resolved_trace_id,
            status="FAILED_RECOVERABLE",
            blocker="LLM_EXECUTION_RESOLVER_UNAVAILABLE",
            reason="The persisted run could not resolve an active LLM execution profile.",
            next_action="RETRY_LLM_EXECUTION_RESOLUTION",
            error_type=type(exc).__name__,
        )
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": resolved_run_id,
            "traceId": resolved_trace_id,
            "status": state["status"],
            "source": state["source"],
            "evidenceId": state["evidenceId"],
            "receivedEvidenceId": received_state["evidenceId"],
            "blocker": "LLM_EXECUTION_RESOLVER_UNAVAILABLE",
            "reason": state["reason"],
            "nextAction": state["nextAction"],
            "errorType": type(exc).__name__,
        }, 503
    if execution_resolution is None:
        state = _persist_execution_resolution_blocker(
            get_connection,
            user_id=user_id,
            run_id=resolved_run_id,
            trace_id=resolved_trace_id,
            status="BLOCKED",
            blocker="NO_VERIFIED_EXECUTION_ROUTE_READY",
            reason="No active OpenRouter paid route or direct FreeLLM route is ready.",
            next_action="ACTIVATE_OPENROUTER_OR_FREELLM_ROUTE_WITH_CANARY_EVIDENCE",
        )
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": resolved_run_id,
            "traceId": resolved_trace_id,
            "status": state["status"],
            "source": state["source"],
            "evidenceId": state["evidenceId"],
            "receivedEvidenceId": received_state["evidenceId"],
            "blocker": "NO_VERIFIED_EXECUTION_ROUTE_READY",
            "reason": state["reason"],
            "nextAction": state["nextAction"],
        }, 503
    if _force_free_profile:
        execution_resolution = free_fallback_resolution(
            execution_resolution,
            reason=(
                _fallback_reason
                or "paid_provider_failure_resolved_to_free_revolver"
            ),
        )
        if execution_resolution is None:
            state = _persist_execution_resolution_blocker(
                get_connection,
                user_id=user_id,
                run_id=resolved_run_id,
                trace_id=resolved_trace_id,
                status="BLOCKED",
                blocker="FREE_REVOLVER_ROUTE_NOT_READY",
                reason="The paid route failed and no verified free fallback route is ready.",
                next_action="ACTIVATE_FREE_PROVIDER_ROUTE_WITH_CANARY_EVIDENCE",
            )
            return {
                "ok": False,
                "runtime": "openai-agents-sdk",
                "runId": resolved_run_id,
                "traceId": resolved_trace_id,
                "status": state["status"],
                "source": state["source"],
                "evidenceId": state["evidenceId"],
                "receivedEvidenceId": received_state["evidenceId"],
                "blocker": "FREE_REVOLVER_ROUTE_NOT_READY",
                "reason": state["reason"],
                "nextAction": state["nextAction"],
            }, 503
    resolved_model = route_provider_model(execution_resolution.primary_route)
    resolved_agent_model = route_provider_model(execution_resolution.agent_route)
    if not resolved_model or not resolved_agent_model:
        state = _persist_execution_resolution_blocker(
            get_connection,
            user_id=user_id,
            run_id=resolved_run_id,
            trace_id=resolved_trace_id,
            status="BLOCKED",
            blocker="RESOLVED_PROVIDER_MODEL_MISSING",
            reason="The selected execution route has no bounded provider model.",
            next_action="REPAIR_EXECUTION_ROUTE_PROVIDER_MODEL",
        )
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": resolved_run_id,
            "traceId": resolved_trace_id,
            "status": state["status"],
            "source": state["source"],
            "evidenceId": state["evidenceId"],
            "receivedEvidenceId": received_state["evidenceId"],
            "blocker": "RESOLVED_PROVIDER_MODEL_MISSING",
            "reason": state["reason"],
            "nextAction": state["nextAction"],
        }, 503

    if execution_resolution.profile_id == FREE_SINGLE_AGENT_PROFILE:
        implementation_job = _free_implementation_job
        repository_toolset = _free_repository_toolset
        free_task_id: str | None = _free_task_id
        mission_intent = _free_mission_intent
        try:
            if mission_intent is None:
                mission_intent = _explicit_mission_intent(
                    _normalize_intent_mode(normalized_intent_mode, free_profile=True),
                    normalized_mission,
                )
            if mission_intent is None:
                raise RuntimeError("Free execution requires a deterministic intent mode.")
            if (
                mission_intent.mode == "repository_execution"
                and implementation_job is None
            ):
                conn = get_connection()
                try:
                    repository = _configured_repository()
                    implementation_job = create_sovereign_agent_job(
                        conn,
                        user_id=user_id,
                        payload={
                            "repoUrl": f"https://github.com/{repository}",
                            "branch": "main",
                            "mission": mission_intent.normalized_goal,
                            "executor": "sovereign-local-runner",
                            "draftPrOnly": True,
                            "allowAutoMerge": False,
                        },
                        workspace_root=_workspace_root(),
                        provision_workspace=True,
                        clone_repo=True,
                    )
                    linked_state = link_agent_run_job(
                        conn,
                        user_id=user_id,
                        run_id=resolved_run_id,
                        job_id=implementation_job.job_id,
                        trace_id=resolved_trace_id,
                        workspace_id=implementation_job.result.workspace_id,
                    )
                    if implementation_job.result.status in {"blocked", "failed"}:
                        raise RuntimeError(
                            implementation_job.result.blocker
                            or "FREE_AGENT_WORKSPACE_PROVISIONING_FAILED"
                        )
                    free_task_id = create_repository_single_agent_task(
                        conn,
                        run_id=resolved_run_id,
                        evidence_id=linked_state["evidenceId"],
                        write_confirmed=True,
                    )
                finally:
                    _close_connection(conn)
                repository_toolset = BoundRepositoryToolset(
                    get_connection=get_connection,
                    user_id=user_id,
                    run_id=resolved_run_id,
                    job_id=implementation_job.job_id,
                    task_ids_by_agent={"free_single_agent": free_task_id},
                    workspace_root=_workspace_root(),
                    write_confirmed=True,
                )

            single_result = asyncio.run(run_free_single_agent(
                normalized_mission,
                evidence=normalized_evidence,
                model=resolved_model,
                intent=mission_intent,
                route=execution_resolution.primary_route,
                repository_tool_factory=(
                    repository_toolset.tools_for_role if repository_toolset else None
                ),
            ))
            single_payload = (
                single_result.get("result")
                if isinstance(single_result.get("result"), dict)
                else {}
            )
            repository_summary = repository_toolset.summary() if repository_toolset else {}
            job_evidence: dict[str, object] = {}
            execution_gate = None
            if implementation_job is not None:
                conn = get_connection()
                try:
                    stored_job = read_agent_job(
                        conn,
                        user_id=user_id,
                        job_id=implementation_job.job_id,
                    )
                finally:
                    _close_connection(conn)
                if not stored_job:
                    raise RuntimeError("The free-agent workspace job disappeared during execution.")
                execution_gate = evaluate_agent_evidence(EvidenceGateInput(
                    job_id=stored_job.job_id,
                    changed_files=stored_job.changed_files,
                    diff_summary=stored_job.diff_summary,
                    test_summary=stored_job.test_summary,
                    blocker=stored_job.blocker,
                    tool_status=stored_job.status,
                ))
                job_evidence = {
                    "jobId": stored_job.job_id,
                    "workspaceId": stored_job.workspace_id,
                    "codeServerWorkspace": (
                        "/config/sovereign-agent-workspaces/"
                        + stored_job.workspace_id
                        + "/repo"
                    ),
                    "status": stored_job.status,
                    "changedFiles": list(stored_job.changed_files),
                    "hasDiff": bool(stored_job.diff_summary),
                    "hasTests": bool(stored_job.test_summary),
                    "blocker": stored_job.blocker,
                    "gatePassed": execution_gate.passed,
                    "gateReason": execution_gate.reason,
                    "canPrepareDraftPr": execution_gate.can_prepare_draft_pr,
                }

            repository_requested = bool(
                mission_intent and mission_intent.mode == "repository_execution"
            )
            roles_with_calls = set(repository_summary.get("rolesWithCalls") or [])
            workspace_evidence_ready = (
                not repository_requested
                or (
                    execution_gate is not None
                    and execution_gate.passed
                    and "free_single_agent" in roles_with_calls
                )
            )
            single_blocked = (
                str(single_result.get("status") or "BLOCKED") != "COMPLETED"
                or not workspace_evidence_ready
            )
            reason = (
                "The free single agent completed one isolated Code-Server workspace mission with diff and test evidence."
                if repository_requested and not single_blocked
                else "The free single agent completed without background agents."
                if not single_blocked
                else "The free single-agent workspace execution lacks required tool, diff or test evidence."
            )
            next_action = (
                "REVIEW_WORKSPACE_AND_OPTIONALLY_CREATE_DRAFT_PR"
                if repository_requested and not single_blocked
                else "NO_FURTHER_ACTION_REQUIRED"
                if not single_blocked
                else "COMPLETE_SINGLE_AGENT_WORKSPACE_EVIDENCE"
            )
            conn = get_connection()
            try:
                final_state = transition_agent_run(
                    conn,
                    user_id=user_id,
                    run_id=resolved_run_id,
                    status="COMPLETED" if not single_blocked else "BLOCKED",
                    source="agents-sdk",
                    trace_id=resolved_trace_id,
                    reason=reason,
                    next_action=next_action,
                    evidence_kind="free_single_agent_result",
                    evidence_summary=reason,
                    evidence_payload={
                        "executionResolution": execution_resolution.safe_payload(),
                        "intent": mission_intent.model_dump() if mission_intent else {},
                        "resultMode": str(single_payload.get("mode") or ""),
                        "repositoryExecutionPerformed": bool(
                            repository_requested and workspace_evidence_ready
                        ),
                        "backgroundAgentsStarted": 0,
                        "repositoryTools": repository_summary,
                        "jobEvidence": job_evidence,
                        "rawModelOutputPersisted": False,
                    },
                    agent_id="free_single_agent",
                    task_id=free_task_id,
                )
            finally:
                _close_connection(conn)
            return {
                "runtime": "openai-agents-sdk",
                **single_result,
                "runId": resolved_run_id,
                "traceId": resolved_trace_id,
                "status": final_state["status"],
                "source": final_state["source"],
                "evidenceId": final_state["evidenceId"],
                "reason": final_state["reason"],
                "nextAction": final_state["nextAction"],
                "receivedEvidenceId": received_state["evidenceId"],
                "executionResolution": execution_resolution.safe_payload(),
                "intent": mission_intent.model_dump() if mission_intent else {},
                "resolvedModelId": resolved_model,
                "jobId": implementation_job.job_id if implementation_job else None,
                "workspaceId": (
                    implementation_job.result.workspace_id if implementation_job else None
                ),
                "codeServerWorkspace": job_evidence.get("codeServerWorkspace"),
                "repositoryTools": repository_summary,
                "jobEvidence": job_evidence,
                "repositoryExecutionPerformed": bool(
                    repository_requested and workspace_evidence_ready
                ),
                "maxBackgroundAgents": 0,
                "freeRouteFailoverCount": _free_retry_count,
                "autoMerge": False,
            }, 200 if not single_blocked else 503
        except Exception as raw_exc:
            exc = (
                raw_exc
                if isinstance(raw_exc, SwarmExecutionError)
                else classify_swarm_exception(
                    raw_exc,
                    stage="free-single-agent",
                    transport=route_transport(execution_resolution.primary_route),
                )
            )
            if isinstance(exc, SwarmExecutionError) and exc.retryable:
                _record_route_cooldown(
                    get_connection,
                    execution_resolution=execution_resolution,
                    failure=exc,
                )
                repository_summary = (
                    repository_toolset.summary()
                    if repository_toolset is not None
                    else {}
                )
                mutations = list(repository_summary.get("rolesWithMutations") or [])
                next_resolution = advance_free_revolver_resolution(
                    execution_resolution,
                    failed_route_id=str(
                        execution_resolution.primary_route.get("id") or ""
                    ),
                    reason="free_route_failed_advanced_to_next_quota_scope",
                )
                if next_resolution is not None and not mutations:
                    next_model = route_provider_model(next_resolution.primary_route)
                    return start_cognitive_swarm_run(
                        get_connection=get_connection,
                        user_id=user_id,
                        mission=normalized_mission,
                        evidence=normalized_evidence,
                        model=next_model,
                        mode=normalized_mode,
                        intent_mode=normalized_intent_mode,
                        run_id=resolved_run_id,
                        session_key=resolved_session_key,
                        a2a_context_id=a2a_context_id,
                        trace_id=resolved_trace_id,
                        _reuse_received_state=received_state,
                        _free_resolution_override=next_resolution,
                        _free_retry_count=_free_retry_count + 1,
                        _free_implementation_job=implementation_job,
                        _free_repository_toolset=repository_toolset,
                        _free_task_id=free_task_id,
                        _free_mission_intent=mission_intent,
                    )
            conn = get_connection()
            try:
                failed_state = transition_agent_run(
                    conn,
                    user_id=user_id,
                    run_id=resolved_run_id,
                    status="FAILED_RECOVERABLE" if exc.retryable else "BLOCKED",
                    source="agents-sdk",
                    trace_id=resolved_trace_id,
                    reason="The free single-agent route or workspace could not produce validated evidence.",
                    next_action=exc.next_action,
                    evidence_kind="free_single_agent_failure",
                    evidence_summary="The free single-agent path failed without starting background agents.",
                    evidence_payload={
                        **exc.safe_payload(),
                        "executionResolution": execution_resolution.safe_payload(),
                        "jobId": implementation_job.job_id if implementation_job else None,
                        "workspaceId": (
                            implementation_job.result.workspace_id
                            if implementation_job
                            else None
                        ),
                        "backgroundAgentsStarted": 0,
                    },
                    agent_id="free_single_agent",
                    task_id=free_task_id,
                )
            finally:
                _close_connection(conn)
            return {
                "ok": False,
                "runtime": "openai-agents-sdk",
                "runId": resolved_run_id,
                "traceId": resolved_trace_id,
                "status": failed_state["status"],
                "source": failed_state["source"],
                "evidenceId": failed_state["evidenceId"],
                "receivedEvidenceId": received_state["evidenceId"],
                "blocker": exc.family,
                "reason": failed_state["reason"],
                "nextAction": failed_state["nextAction"],
                "executionResolution": execution_resolution.safe_payload(),
                "resolvedModelId": resolved_model,
                "jobId": implementation_job.job_id if implementation_job else None,
                "workspaceId": (
                    implementation_job.result.workspace_id if implementation_job else None
                ),
                "maxBackgroundAgents": 0,
                "freeRouteFailoverCount": _free_retry_count,
            }, 502 if exc.retryable else 503

    if execution_resolution.profile_id != PAID_SWARM_PROFILE:
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "blocker": "EXECUTION_PROFILE_UNSUPPORTED",
        }, 503
    try:
        stage_billing = AgentStageBilling(
            get_connection=get_connection,
            user_id=user_id,
            run_id=resolved_run_id,
            trace_id=resolved_trace_id,
            main_route=execution_resolution.primary_route,
            agent_route=execution_resolution.agent_route,
            requested_mode=execution_resolution.requested_mode,
        )
        mission_intent = _explicit_mission_intent(
            normalized_intent_mode,
            normalized_mission,
        )
        if mission_intent is None:
            mission_intent = asyncio.run(classify_mission_intent(
                normalized_mission,
                model=resolved_model,
                route=execution_resolution.primary_route,
                stage_billing=stage_billing,
            ))
    except AgentBillingError as exc:
        if exc.family in {
            "INSUFFICIENT_PROVIDER_FUNDED_CREDITS",
            "PAID_CREDIT_PURCHASE_REQUIRED",
        }:
            fallback_resolution = free_fallback_resolution(
                execution_resolution,
                reason="paid_credit_capacity_resolved_to_free_revolver",
            )
            if fallback_resolution is not None:
                fallback_model = str(
                    fallback_resolution.primary_route.get("model_id")
                    or fallback_resolution.primary_route.get("modelId")
                    or ""
                ).strip()
                return start_cognitive_swarm_run(
                    get_connection=get_connection,
                    user_id=user_id,
                    mission=normalized_mission,
                    evidence=normalized_evidence,
                    model=fallback_model,
                    mode=execution_resolution.requested_mode,
                    intent_mode=normalized_intent_mode,
                    run_id=resolved_run_id,
                    session_key=resolved_session_key,
                    a2a_context_id=a2a_context_id,
                    trace_id=resolved_trace_id,
                    _reuse_received_state=received_state,
                    _force_free_profile=True,
                    _fallback_reason="paid_credit_capacity_resolved_to_free_revolver",
                )
        try:
            intent_state = _persist_billing_blocker(
                get_connection=get_connection,
                user_id=user_id,
                run_id=resolved_run_id,
                trace_id=resolved_trace_id,
                exc=exc,
            )
        except Exception as persistence_exc:
            return {
                "ok": False,
                "runtime": "openai-agents-sdk",
                "runId": resolved_run_id,
                "traceId": resolved_trace_id,
                "receivedEvidenceId": received_state["evidenceId"],
                "blocker": "AGENT_BILLING_BLOCKER_PERSISTENCE_UNAVAILABLE",
                "errorType": type(persistence_exc).__name__,
            }, 503
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": resolved_run_id,
            "traceId": resolved_trace_id,
            "status": intent_state["status"],
            "source": intent_state["source"],
            "evidenceId": intent_state["evidenceId"],
            "receivedEvidenceId": received_state["evidenceId"],
            "blocker": exc.family,
            "reason": intent_state["reason"],
            "nextAction": intent_state["nextAction"],
            "requiredCredits": exc.required_credits,
            "availableProviderFundedCredits": exc.available_credits,
        }, exc.status_code
    except Exception as raw_exc:
        exc = (
            raw_exc
            if isinstance(raw_exc, SwarmExecutionError)
            else classify_swarm_exception(
                raw_exc,
                stage="intent-router",
                transport=route_transport(execution_resolution.primary_route),
            )
        )
        if isinstance(exc, SwarmExecutionError) and exc.http_status == 429:
            fallback_resolution = free_fallback_resolution(
                execution_resolution,
                reason="paid_provider_429_resolved_to_free_revolver",
            )
            if fallback_resolution is not None:
                _record_route_cooldown(
                    get_connection,
                    execution_resolution=execution_resolution,
                    failure=exc,
                )
                fallback_model = str(
                    fallback_resolution.primary_route.get("model_id")
                    or fallback_resolution.primary_route.get("modelId")
                    or ""
                ).strip()
                return start_cognitive_swarm_run(
                    get_connection=get_connection,
                    user_id=user_id,
                    mission=normalized_mission,
                    evidence=normalized_evidence,
                    model=fallback_model,
                    mode=execution_resolution.requested_mode,
                    intent_mode=normalized_intent_mode,
                    run_id=resolved_run_id,
                    session_key=resolved_session_key,
                    a2a_context_id=a2a_context_id,
                    trace_id=resolved_trace_id,
                    _reuse_received_state=received_state,
                    _force_free_profile=True,
                    _fallback_reason="paid_provider_429_resolved_to_free_revolver",
                )
        conn = get_connection()
        try:
            intent_state = transition_agent_run(
                conn,
                user_id=user_id,
                run_id=resolved_run_id,
                status="FAILED_RECOVERABLE" if exc.retryable else "BLOCKED",
                source="agents-sdk",
                trace_id=resolved_trace_id,
                reason="The routed LLM could not produce a validated mission intent.",
                next_action=exc.next_action,
                evidence_kind="intent_classification_failure",
                evidence_summary="Mission intent classification failed before any action was authorized.",
                evidence_payload=exc.safe_payload(),
                agent_id="intent_router",
            )
        finally:
            _close_connection(conn)
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": resolved_run_id,
            "traceId": resolved_trace_id,
            "status": intent_state["status"],
            "source": intent_state["source"],
            "evidenceId": intent_state["evidenceId"],
            "receivedEvidenceId": received_state["evidenceId"],
            "blocker": exc.family,
            "reason": intent_state["reason"],
            "nextAction": intent_state["nextAction"],
        }, 502 if exc.retryable else 503

    implementation_job = None
    task_ids_by_agent: dict[str, str] = {}
    repository_toolset = None
    try:
        if mission_intent.mode == "repository_execution":
            conn = get_connection()
            try:
                repository = _configured_repository()
                implementation_job = create_sovereign_agent_job(
                    conn,
                    user_id=user_id,
                    payload={
                        "repoUrl": f"https://github.com/{repository}",
                        "branch": "main",
                        "mission": mission_intent.normalized_goal,
                        "executor": "sovereign-local-runner",
                        "draftPrOnly": True,
                        "allowAutoMerge": False,
                    },
                    workspace_root=_workspace_root(),
                    provision_workspace=True,
                    clone_repo=True,
                )
                linked_state = link_agent_run_job(
                    conn,
                    user_id=user_id,
                    run_id=resolved_run_id,
                    job_id=implementation_job.job_id,
                    trace_id=resolved_trace_id,
                    workspace_id=implementation_job.result.workspace_id,
                )
                if implementation_job.result.status in {"blocked", "failed"}:
                    blocked_state = transition_agent_run(
                        conn,
                        user_id=user_id,
                        run_id=resolved_run_id,
                        status="BLOCKED",
                        source="agents-sdk",
                        trace_id=resolved_trace_id,
                        reason="The real repository workspace could not be provisioned.",
                        next_action="FIX_WORKSPACE_PROVISIONING_AND_RERUN",
                        evidence_kind="workspace_provisioning_failure",
                        evidence_summary="Repository execution was selected but workspace provisioning failed.",
                        evidence_payload={
                            "jobId": implementation_job.job_id,
                            "workspaceId": implementation_job.result.workspace_id,
                            "blocker": implementation_job.result.blocker or "IMPLEMENTATION_JOB_PROVISIONING_FAILED",
                            "autoMerge": False,
                        },
                        agent_id="orchestrator",
                    )
                    return {
                        "ok": False,
                        "runtime": "sovereign-agent",
                        "runId": resolved_run_id,
                        "status": blocked_state["status"],
                        "source": blocked_state["source"],
                        "evidenceId": blocked_state["evidenceId"],
                        "receivedEvidenceId": received_state["evidenceId"],
                        "jobId": implementation_job.job_id,
                        "workspaceId": implementation_job.result.workspace_id,
                        "blocker": implementation_job.result.blocker or "IMPLEMENTATION_JOB_PROVISIONING_FAILED",
                        "reason": blocked_state["reason"],
                        "nextAction": blocked_state["nextAction"],
                    }, 503
                task_ids_by_agent = create_repository_swarm_tasks(
                    conn,
                    run_id=resolved_run_id,
                    evidence_id=linked_state["evidenceId"],
                    write_confirmed=True,
                )
            finally:
                _close_connection(conn)
            repository_toolset = BoundRepositoryToolset(
                get_connection=get_connection,
                user_id=user_id,
                run_id=resolved_run_id,
                job_id=implementation_job.job_id,
                task_ids_by_agent=task_ids_by_agent,
                workspace_root=_workspace_root(),
                write_confirmed=True,
            )
    except Exception as exc:
        conn = get_connection()
        try:
            handoff_state = transition_agent_run(
                conn,
                user_id=user_id,
                run_id=resolved_run_id,
                status="FAILED_RECOVERABLE",
                source="agents-sdk",
                trace_id=resolved_trace_id,
                reason="Repository execution handoff failed after intent classification.",
                next_action="RETRY_REPOSITORY_EXECUTION_HANDOFF",
                evidence_kind="implementation_handoff_failure",
                evidence_summary="The implementation job or six-agent task graph could not be materialized.",
                evidence_payload={"errorType": type(exc).__name__, "rawErrorPersisted": False},
                agent_id="orchestrator",
            )
        finally:
            _close_connection(conn)
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": resolved_run_id,
            "status": handoff_state["status"],
            "source": handoff_state["source"],
            "evidenceId": handoff_state["evidenceId"],
            "receivedEvidenceId": received_state["evidenceId"],
            "blocker": "AGENT_REPOSITORY_HANDOFF_FAILED",
            "reason": handoff_state["reason"],
            "nextAction": handoff_state["nextAction"],
        }, 503

    return execute_persisted_swarm(
        get_connection=get_connection,
        user_id=user_id,
        run_id=resolved_run_id,
        trace_id=resolved_trace_id,
        mission=normalized_mission,
        evidence=normalized_evidence,
        model=resolved_model,
        route=execution_resolution.primary_route,
        agent_route=execution_resolution.agent_route,
        repository_tool_factory=(repository_toolset.tools_for_role if repository_toolset else None),
        repository_tool_summary=(repository_toolset.summary if repository_toolset else None),
        job_id=implementation_job.job_id if implementation_job else None,
        task_id=task_ids_by_agent.get("judge"),
        task_ids_by_agent=task_ids_by_agent,
        stage_billing=stage_billing,
        response_context={
            "sessionKey": resolved_session_key,
            "a2aContextId": str(a2a_context_id or "") or None,
            "resumed": False,
            "receivedEvidenceId": received_state["evidenceId"],
            "intent": mission_intent.model_dump(),
            "jobId": implementation_job.job_id if implementation_job else None,
            "workspaceId": implementation_job.result.workspace_id if implementation_job else None,
            "learningState": "PENDING_EVIDENCE" if implementation_job else "NOT_REQUESTED",
            "executionResolution": execution_resolution.safe_payload(),
            "resolvedModelId": resolved_model,
            "resolvedMainModelId": resolved_model,
            "resolvedAgentModelId": resolved_agent_model,
            "sixAgentModelShared": True,
            "maxBackgroundAgents": execution_resolution.max_background_agents,
            "autoMerge": False,
        },
    )


def resume_cognitive_swarm_run(
    *,
    get_connection: ConnectionFactory,
    user_id: str,
    run_id: str,
    evidence: str = "",
    model: str | None = None,
    main_model: str | None = None,
    agent_model: str | None = None,
    mode: str = "auto",
    trace_id: str | None = None,
) -> tuple[dict[str, object], int]:
    """Resume one owner-scoped persisted run through its existing bounded lease path."""

    normalized_run_id = str(run_id or "").strip()
    normalized_evidence = str(evidence or "").strip()
    normalized_model = str(model or "").strip() or None
    normalized_main_model = str(main_model or normalized_model or "").strip() or None
    normalized_agent_model = str(
        agent_model or normalized_model or normalized_main_model or ""
    ).strip() or None
    normalized_mode = str(mode or "auto").strip().lower()
    if not normalized_run_id:
        return {"error": "run id is required"}, 400
    if len(normalized_evidence) > 250_000:
        return {"error": "evidence exceeds the bounded input limit"}, 400
    if _contains_secret_shaped_text(normalized_evidence):
        return {"error": "secret-shaped material is forbidden in swarm input"}, 400
    if any(
        selected and len(selected) > 240
        for selected in (normalized_model, normalized_main_model, normalized_agent_model)
    ):
        return {"error": "model identifier exceeds the bounded limit"}, 400
    if not user_id:
        return {"error": "authenticated user id is required"}, 401

    resolved_trace_id = str(trace_id or f"trace-{uuid.uuid4().hex}").strip()
    try:
        conn = get_connection()
        try:
            claim = claim_agent_run_for_resume(
                conn,
                user_id=user_id,
                run_id=normalized_run_id,
                supplied_evidence=normalized_evidence,
                trace_id=resolved_trace_id,
                lease_seconds=_resume_lease_seconds(),
            )
        finally:
            _close_connection(conn)
    except LookupError:
        return {"error": "run not found"}, 404
    except AgentRunResumeConflict as exc:
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": normalized_run_id,
            "status": "RUNNING",
            "blocker": "RUN_ALREADY_CLAIMED",
            "reason": str(exc),
            "nextAction": "WAIT_FOR_ACTIVE_RESUME_LEASE_OR_RETRY_AFTER_EXPIRY",
        }, 409
    except AgentRunIterationLimit as exc:
        reason = str(exc)
        try:
            conn = get_connection()
            try:
                final_state = transition_agent_run(
                    conn,
                    user_id=user_id,
                    run_id=normalized_run_id,
                    status="FAILED_FINAL",
                    source="agents-sdk",
                    trace_id=resolved_trace_id,
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
            return {
                "ok": False,
                "runtime": "openai-agents-sdk",
                "runId": normalized_run_id,
                "blocker": "RUN_ITERATION_LIMIT_PERSISTENCE_UNAVAILABLE",
                "reason": reason,
                "errorType": type(persistence_exc).__name__,
            }, 503
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": normalized_run_id,
            "status": final_state["status"],
            "source": final_state["source"],
            "evidenceId": final_state["evidenceId"],
            "blocker": "RUN_ITERATION_LIMIT_EXHAUSTED",
            "reason": final_state["reason"],
            "nextAction": final_state["nextAction"],
        }, 409
    except AgentRunNotResumable as exc:
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": normalized_run_id,
            "blocker": "RUN_NOT_RESUMABLE",
            "reason": str(exc),
            "nextAction": "READ_PERSISTED_RUN_STATE",
        }, 409
    except Exception as exc:
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": normalized_run_id,
            "blocker": "RUN_RESUME_PERSISTENCE_UNAVAILABLE",
            "errorType": type(exc).__name__,
        }, 503

    task_ids_by_agent: dict[str, str] = {}
    repository_toolset = None
    try:
        if claim.run.job_id:
            conn = get_connection()
            try:
                task_ids_by_agent = read_agent_task_ids(conn, run_id=claim.run.run_id)
                if not set(WORKER_ROLES).issubset(task_ids_by_agent):
                    task_ids_by_agent.update(create_repository_swarm_tasks(
                        conn,
                        run_id=claim.run.run_id,
                        evidence_id=claim.evidence_id,
                        write_confirmed=True,
                    ))
            finally:
                _close_connection(conn)
            repository_toolset = BoundRepositoryToolset(
                get_connection=get_connection,
                user_id=user_id,
                run_id=claim.run.run_id,
                job_id=claim.run.job_id,
                task_ids_by_agent=task_ids_by_agent,
                workspace_root=_workspace_root(),
                write_confirmed=True,
            )
    except Exception as exc:
        failure_reason = "Repository execution resume handoff failed after the run lease was claimed."
        try:
            conn = get_connection()
            try:
                failed_state = transition_agent_run(
                    conn,
                    user_id=user_id,
                    run_id=claim.run.run_id,
                    status="FAILED_RECOVERABLE",
                    source="agents-sdk",
                    trace_id=resolved_trace_id,
                    reason=failure_reason,
                    next_action="RETRY_REPOSITORY_EXECUTION_HANDOFF",
                    evidence_kind="resume_implementation_handoff_failure",
                    evidence_summary=failure_reason,
                    evidence_payload={
                        "errorType": type(exc).__name__,
                        "rawErrorPersisted": False,
                    },
                    task_id=claim.task_id,
                    expected_lease_token=claim.lease_token,
                )
            finally:
                _close_connection(conn)
        except Exception as persistence_exc:
            return {
                "ok": False,
                "runtime": "openai-agents-sdk",
                "runId": claim.run.run_id,
                "blocker": "RUN_RESUME_FAILURE_PERSISTENCE_UNAVAILABLE",
                "errorType": type(persistence_exc).__name__,
            }, 503
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": claim.run.run_id,
            "status": failed_state["status"],
            "source": failed_state["source"],
            "evidenceId": failed_state["evidenceId"],
            "blocker": "AGENT_REPOSITORY_RESUME_HANDOFF_FAILED",
            "reason": failed_state["reason"],
            "nextAction": failed_state["nextAction"],
            "resumed": True,
        }, 503

    resume_context = {
        "persistedRunId": claim.run.run_id,
        "persistedJobId": claim.run.job_id,
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
        f"{normalized_evidence or '[no new evidence supplied]'}"
    )
    try:
        execution_resolution = load_execution_resolution(
            get_connection,
            user_id=user_id,
            requested_model=normalized_model or "",
            requested_main_model=normalized_main_model or "",
            requested_agent_model=normalized_agent_model or "",
            requested_mode=normalized_mode,
        )
    except (ExecutionResolutionError, LookupError) as exc:
        failure_family = (
            exc.failure_family
            if isinstance(exc, ExecutionResolutionError)
            else "AGENT_BILLING_USER_NOT_FOUND"
        )
        status_code = (
            exc.status_code
            if isinstance(exc, ExecutionResolutionError)
            else 404
        )
        blocked_state = _persist_execution_resolution_blocker(
            get_connection,
            user_id=user_id,
            run_id=claim.run.run_id,
            trace_id=resolved_trace_id,
            status="BLOCKED",
            blocker=failure_family,
            reason=str(exc),
            next_action="START_NEW_RUN_OR_REPAIR_REQUESTED_ROUTE",
            error_type=type(exc).__name__,
            task_id=claim.task_id,
            expected_lease_token=claim.lease_token,
        )
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": claim.run.run_id,
            "traceId": resolved_trace_id,
            "status": blocked_state["status"],
            "source": blocked_state["source"],
            "evidenceId": blocked_state["evidenceId"],
            "resumeClaimEvidenceId": claim.evidence_id,
            "resumed": True,
            "blocker": failure_family,
            "reason": blocked_state["reason"],
            "nextAction": blocked_state["nextAction"],
            "requestedMode": normalized_mode,
        }, status_code
    if execution_resolution is None:
        blocked_state = _persist_execution_resolution_blocker(
            get_connection,
            user_id=user_id,
            run_id=claim.run.run_id,
            trace_id=resolved_trace_id,
            status="BLOCKED",
            blocker="NO_VERIFIED_EXECUTION_ROUTE_READY",
            reason="No verified execution route is ready for the resume boundary.",
            next_action="START_NEW_RUN_OR_ACTIVATE_VERIFIED_ROUTE",
            task_id=claim.task_id,
            expected_lease_token=claim.lease_token,
        )
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": claim.run.run_id,
            "traceId": resolved_trace_id,
            "status": blocked_state["status"],
            "source": blocked_state["source"],
            "evidenceId": blocked_state["evidenceId"],
            "resumeClaimEvidenceId": claim.evidence_id,
            "resumed": True,
            "blocker": "NO_VERIFIED_EXECUTION_ROUTE_READY",
            "reason": blocked_state["reason"],
            "nextAction": blocked_state["nextAction"],
            "requestedMode": normalized_mode,
        }, 503
    if execution_resolution.profile_id != PAID_SWARM_PROFILE:
        blocked_state = _persist_execution_resolution_blocker(
            get_connection,
            user_id=user_id,
            run_id=claim.run.run_id,
            trace_id=resolved_trace_id,
            status="BLOCKED",
            blocker="FREE_MODE_REQUIRES_NEW_SINGLE_AGENT_RUN",
            reason="A paid swarm resume cannot change transport mid-run.",
            next_action="START_NEW_FREE_SINGLE_AGENT_RUN",
            task_id=claim.task_id,
            expected_lease_token=claim.lease_token,
        )
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": claim.run.run_id,
            "status": blocked_state["status"],
            "blocker": "FREE_MODE_REQUIRES_NEW_SINGLE_AGENT_RUN",
            "reason": blocked_state["reason"],
            "nextAction": blocked_state["nextAction"],
            "requestedMode": normalized_mode,
        }, 409
    resolved_model = route_provider_model(execution_resolution.primary_route)
    resolved_agent_model = route_provider_model(execution_resolution.agent_route)
    try:
        stage_billing = AgentStageBilling(
            get_connection=get_connection,
            user_id=user_id,
            run_id=claim.run.run_id,
            trace_id=resolved_trace_id,
            main_route=execution_resolution.primary_route,
            agent_route=execution_resolution.agent_route,
            requested_mode=execution_resolution.requested_mode,
        )
    except AgentBillingError as exc:
        try:
            blocked_state = _persist_billing_blocker(
                get_connection=get_connection,
                user_id=user_id,
                run_id=claim.run.run_id,
                trace_id=resolved_trace_id,
                exc=exc,
                task_id=claim.task_id,
                expected_lease_token=claim.lease_token,
            )
        except Exception as persistence_exc:
            return {
                "ok": False,
                "runtime": "openai-agents-sdk",
                "runId": claim.run.run_id,
                "traceId": resolved_trace_id,
                "resumeClaimEvidenceId": claim.evidence_id,
                "resumed": True,
                "blocker": "AGENT_BILLING_BLOCKER_PERSISTENCE_UNAVAILABLE",
                "errorType": type(persistence_exc).__name__,
            }, 503
        return {
            "ok": False,
            "runtime": "openai-agents-sdk",
            "runId": claim.run.run_id,
            "traceId": resolved_trace_id,
            "status": blocked_state["status"],
            "source": blocked_state["source"],
            "evidenceId": blocked_state["evidenceId"],
            "resumeClaimEvidenceId": claim.evidence_id,
            "resumed": True,
            "blocker": exc.family,
            "reason": blocked_state["reason"],
            "nextAction": blocked_state["nextAction"],
            "requiredCredits": exc.required_credits,
            "availableProviderFundedCredits": exc.available_credits,
        }, exc.status_code
    return execute_persisted_swarm(
        get_connection=get_connection,
        user_id=user_id,
        run_id=claim.run.run_id,
        trace_id=resolved_trace_id,
        mission=claim.run.mission_summary,
        evidence=execution_evidence,
        model=resolved_model,
        route=execution_resolution.primary_route,
        agent_route=execution_resolution.agent_route,
        task_id=claim.task_id,
        lease_token=claim.lease_token,
        repository_tool_factory=(repository_toolset.tools_for_role if repository_toolset else None),
        repository_tool_summary=(repository_toolset.summary if repository_toolset else None),
        job_id=claim.run.job_id,
        task_ids_by_agent=task_ids_by_agent,
        stage_billing=stage_billing,
        response_context={
            "sessionKey": claim.run.session_key,
            "a2aContextId": claim.run.a2a_context_id,
            "resumed": True,
            "resumeClaimEvidenceId": claim.evidence_id,
            "executionResolution": execution_resolution.safe_payload(),
            "resolvedModelId": resolved_model,
            "resolvedMainModelId": resolved_model,
            "resolvedAgentModelId": resolved_agent_model,
            "sixAgentModelShared": True,
            "recoveryTask": {
                "taskId": claim.task_id,
                "workPackage": claim.work_package,
                "leaseSeconds": claim.lease_seconds,
            },
        },
    )


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
            "configured": None,
            "configurationResolution": "request-time-persisted-route",
            "executionModes": ["auto", "paid", "free"],
            "allowedModels": [],
            "modelsResolvedFromDatabase": True,
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
        payload, status_code = resume_cognitive_swarm_run(
            get_connection=get_connection,
            user_id=_current_session_user_id(),
            run_id=run_id,
            evidence=str(body.get("evidence") or body.get("evidenceText") or ""),
            model=str(body.get("model") or "") or None,
            main_model=str(body.get("mainModel") or "") or None,
            agent_model=str(body.get("agentModel") or "") or None,
            mode=str(body.get("mode") or "auto"),
        )
        return jsonify(payload), status_code

    @app.route("/api/user/agent/swarm/run", methods=["POST"])
    @require_session
    def user_run_cognitive_swarm():
        body: dict[str, Any] = request.get_json(force=True) or {}
        payload, status_code = start_cognitive_swarm_run(
            get_connection=get_connection,
            user_id=_current_session_user_id(),
            mission=str(body.get("mission") or ""),
            evidence=str(body.get("evidence") or body.get("evidenceText") or ""),
            model=str(body.get("model") or "") or None,
            main_model=str(body.get("mainModel") or "") or None,
            agent_model=str(body.get("agentModel") or "") or None,
            mode=str(body.get("mode") or "auto"),
            intent_mode=str(body.get("intentMode") or "auto"),
        )
        return jsonify(payload), status_code

    register_a2a_routes(
        app,
        require_session=require_session,
        get_connection=get_connection,
        start_run=start_cognitive_swarm_run,
        resume_run=resume_cognitive_swarm_run,
        service_user_resolver=lambda: _service_owner_user_id(get_connection),
    )
