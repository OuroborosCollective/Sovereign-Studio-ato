"""OpenAI Agents SDK orchestration for the Sovereign cognitive swarm.

The model layer plans and reviews. Repository, database, deployment and merge
mutations remain in the existing bounded runtime tools and approval gates.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, Field

from .cognitive_swarm_manifest import (
    AGENTS,
    SPECIALIST_ROLES,
    WORKER_ROLES,
    manifest_payload,
    max_active_specialists,
)


DEFAULT_MODEL: Final[str] = "gpt-5.4-mini"
SKILL_PATH: Final[Path] = Path(__file__).parent / "skills" / "sovereign-cognitive-architecture" / "SKILL.md"

_AGENT_CLASS: Any | None = None
_RUNNER_CLASS: Any | None = None
_AGENTS_SDK_ERROR = ""
_OPENAI_KEY_FILENAME: Final[str] = "openai_api_key.txt"
_OPENAI_KEY_MAX_BYTES: Final[int] = 8192

StageObserver = Callable[[dict[str, object]], None]


def _emit_stage(
    observer: StageObserver | None,
    *,
    agent_id: str,
    event_type: str,
    status: str,
    summary: str,
    next_action: str,
    loop: int | None = None,
) -> None:
    if observer is None:
        return
    payload: dict[str, object] = {
        "agentId": agent_id,
        "eventType": event_type,
        "status": status,
        "summary": summary,
        "nextAction": next_action,
    }
    if loop is not None:
        payload["loop"] = loop
    observer(payload)


def ensure_openai_runtime_key() -> bool:
    """Load the owner-managed OpenAI key into this backend process without logging it."""

    if os.getenv("OPENAI_API_KEY", "").strip():
        return True
    root = Path(os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", "/opt/sovereign-owner-managed")).resolve()
    candidate_path = root / _OPENAI_KEY_FILENAME
    if candidate_path.is_symlink():
        return False
    candidate = candidate_path.resolve()
    if candidate.parent != root or not candidate.is_file():
        return False
    try:
        if candidate.stat().st_mode & 0o077:
            return False
        raw = candidate.read_bytes()
    except OSError:
        return False
    if not raw or len(raw) > _OPENAI_KEY_MAX_BYTES:
        return False
    try:
        value = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return False
    if not value:
        return False
    os.environ["OPENAI_API_KEY"] = value
    return True


class SwarmExecutionError(RuntimeError):
    """Bounded provider/runtime failure without raw exception or credential text."""

    def __init__(
        self,
        *,
        stage: str,
        family: str,
        error_type: str,
        next_action: str,
        retryable: bool,
        http_status: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(family)
        self.stage = stage[:160]
        self.family = family[:160]
        self.error_type = error_type[:160]
        self.next_action = next_action[:240]
        self.retryable = bool(retryable)
        self.http_status = http_status
        self.request_id = (request_id or "")[:200] or None

    def safe_payload(self) -> dict[str, object]:
        return {
            "failureStage": self.stage,
            "failureFamily": self.family,
            "errorType": self.error_type,
            "nextAction": self.next_action,
            "retryable": self.retryable,
            "httpStatus": self.http_status,
            "requestId": self.request_id,
            "rawErrorPersisted": False,
        }


def _exception_status(exc: Exception) -> int | None:
    direct = getattr(exc, "status_code", None)
    if isinstance(direct, int):
        return direct
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _exception_request_id(exc: Exception) -> str | None:
    direct = getattr(exc, "request_id", None) or getattr(exc, "requestId", None)
    if direct:
        return str(direct)
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers:
        value = headers.get("x-request-id") or headers.get("X-Request-Id")
        if value:
            return str(value)
    return None


def classify_swarm_exception(exc: Exception, *, stage: str) -> SwarmExecutionError:
    error_type = type(exc).__name__
    lowered = error_type.casefold()
    status = _exception_status(exc)
    if isinstance(exc, FileNotFoundError):
        family, next_action, retryable = "AGENTS_RUNTIME_ASSET_MISSING", "VERIFY_PRODUCTION_RUNTIME_ASSETS", False
    elif status == 401 or "authentication" in lowered:
        family, next_action, retryable = "OPENAI_AUTHENTICATION_FAILED", "VERIFY_OPENAI_PROJECT_KEY", False
    elif status == 403 or "permission" in lowered:
        family, next_action, retryable = "OPENAI_PERMISSION_DENIED", "VERIFY_OPENAI_PROJECT_AND_MODEL_ACCESS", False
    elif status == 404 or "notfound" in lowered or "not_found" in lowered:
        family, next_action, retryable = "OPENAI_MODEL_OR_ENDPOINT_NOT_FOUND", "VERIFY_ALLOWLISTED_MODEL_ACCESS", False
    elif status == 429 or "ratelimit" in lowered or "rate_limit" in lowered:
        family, next_action, retryable = "OPENAI_RATE_LIMITED", "RETRY_AFTER_PROVIDER_BACKOFF", True
    elif status in {408, 504} or "timeout" in lowered:
        family, next_action, retryable = "OPENAI_TIMEOUT", "RETRY_FROM_PERSISTED_RUN_STATE", True
    elif status is not None and status >= 500:
        family, next_action, retryable = "OPENAI_PROVIDER_UNAVAILABLE", "RETRY_FROM_PERSISTED_RUN_STATE", True
    elif status == 400 or "badrequest" in lowered or "bad_request" in lowered:
        family, next_action, retryable = "OPENAI_REQUEST_REJECTED", "REVIEW_MODEL_AND_STRUCTURED_OUTPUT_CONTRACT", False
    elif any(marker in lowered for marker in ("modelbehavior", "output", "validation")):
        family, next_action, retryable = "AGENTS_STRUCTURED_OUTPUT_INVALID", "RETRY_WITH_BOUNDED_SCHEMA_DIAGNOSTICS", True
    elif "maxturn" in lowered or "max_turn" in lowered:
        family, next_action, retryable = "AGENTS_TURN_LIMIT_EXHAUSTED", "REVIEW_AGENT_TURN_BUDGET", False
    elif "connection" in lowered or "network" in lowered:
        family, next_action, retryable = "OPENAI_CONNECTION_FAILED", "RETRY_FROM_PERSISTED_RUN_STATE", True
    else:
        family, next_action, retryable = "AGENTS_SDK_EXECUTION_FAILED", "INSPECT_BOUNDED_SDK_FAILURE_EVIDENCE", True
    return SwarmExecutionError(
        stage=stage,
        family=family,
        error_type=error_type,
        next_action=next_action,
        retryable=retryable,
        http_status=status,
        request_id=_exception_request_id(exc),
    )


async def _run_stage(runner_class: Any, agent: Any, prompt: str, *, stage: str) -> Any:
    try:
        return await runner_class.run(agent, prompt)
    except SwarmExecutionError:
        raise
    except Exception as exc:
        raise classify_swarm_exception(exc, stage=stage) from exc


try:
    _AGENTS_SDK_VERSION = importlib.metadata.version("openai-agents")
    _agents_module = importlib.import_module("agents")
    _agent_candidate = getattr(_agents_module, "Agent", None)
    _runner_candidate = getattr(_agents_module, "Runner", None)
    if not callable(_agent_candidate) or _runner_candidate is None or not callable(getattr(_runner_candidate, "run", None)):
        raise ImportError("the imported agents module is not the OpenAI Agents SDK")
    _AGENT_CLASS = _agent_candidate
    _RUNNER_CLASS = _runner_candidate
except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
    _AGENTS_SDK_VERSION = ""
    _AGENTS_SDK_ERROR = f"{type(exc).__name__}: {exc}"


def agents_sdk_status() -> dict[str, object]:
    available = _AGENT_CLASS is not None and _RUNNER_CLASS is not None
    return {
        "available": available,
        "distribution": "openai-agents",
        "version": _AGENTS_SDK_VERSION or None,
        "error": None if available else _AGENTS_SDK_ERROR or "OpenAI Agents SDK is unavailable.",
    }


def _require_agents_sdk() -> tuple[Any, Any]:
    if _AGENT_CLASS is None or _RUNNER_CLASS is None:
        raise RuntimeError(
            "openai-agents is unavailable or shadowed by a different 'agents' module; "
            "install the pinned backend dependency before running the swarm"
        )
    return _AGENT_CLASS, _RUNNER_CLASS


class DispatchPlan(BaseModel):
    mission: str
    ordered_work: list[str] = Field(min_length=6, max_length=6)
    required_evidence: list[str]
    initial_blockers: list[str]


class WorkerReport(BaseModel):
    role: str
    loop: int
    status: str
    findings: list[str]
    required_actions: list[str]
    evidence_observed: list[str]
    evidence_missing: list[str]
    blocked: bool


class JudgeVerdict(BaseModel):
    loop: int
    verdict: str
    blockers: list[str]
    accepted_evidence: list[str]
    rejected_claims: list[str]
    required_next_actions: list[str]
    draft_pr_ready: bool
    human_approval_required: bool = True


_CONFIRMED_NULLFUND_VERDICTS: Final[frozenset[str]] = frozenset({
    "healthy_nullfind",
    "healthy_nullfund",
    "nullfund_confirmed",
})


def _is_confirmed_nullfund(verdict: JudgeVerdict) -> bool:
    normalized = verdict.verdict.strip().casefold().replace("-", "_").replace(" ", "_")
    return normalized in _CONFIRMED_NULLFUND_VERDICTS


class CognitiveSwarm:
    def __init__(
        self,
        *,
        dispatcher: Any,
        workers: tuple[Any, ...],
        specialists: tuple[Any, ...],
        judge: Any,
    ) -> None:
        if len(workers) != 6:
            raise ValueError("The Sovereign orchestrator requires exactly six bounded core worker agents.")
        if len(specialists) > max_active_specialists():
            raise ValueError("Active specialist agents exceed SOVEREIGN_MAX_ACTIVE_AGENTS.")
        self.dispatcher = dispatcher
        self.workers = workers
        self.specialists = specialists
        self.judge = judge

    @property
    def agent_count(self) -> int:
        return 2 + len(self.workers) + len(self.specialists)


def _load_skill_instructions() -> str:
    content = SKILL_PATH.read_text("utf-8").strip()
    if not content.startswith("---"):
        raise RuntimeError("Sovereign cognitive skill front matter is missing.")
    return content


def _base_instructions(skill: str) -> str:
    return (
        "You are part of the Sovereign cognitive architecture. "
        "Treat the supplied runtime evidence as the only source of truth. "
        "Never invent file changes, tests, screenshots, traces, deployments, database writes or PR states. "
        "Missing evidence is a blocker. Never request or reveal secrets. "
        "Interpret lease_active=false on a terminal or blocked persisted run as evidence that the lease is released, not as evidence that lease release is missing. "
        "An absent open PR is informational unless the mission explicitly requires an existing PR; never invent a PR continuation blocker. "
        "Do not authorize merge or production deployment.\n\n"
        f"Repository skill contract:\n{skill}"
    )


def build_cognitive_swarm(model: str | None = None) -> CognitiveSwarm:
    agent_class, _ = _require_agents_sdk()
    selected_model = (model or os.getenv("SOVEREIGN_AGENTS_MODEL") or DEFAULT_MODEL).strip()
    if not selected_model:
        raise ValueError("A model identifier is required.")

    skill = _load_skill_instructions()
    base = _base_instructions(skill)

    specialists: list[Any] = []
    specialist_tools: list[Any] = []
    for role in SPECIALIST_ROLES[:max_active_specialists()]:
        specialist = agent_class(
            name=f"Sovereign {role.replace('_', ' ').title()} Specialist",
            model=selected_model,
            instructions=(
                f"{base}\n\n"
                f"You are the bounded {role} specialist. Work on exactly one assigned package. "
                "Never spawn agents, merge, deploy, read secrets, change global state, or write outside assigned files. "
                "Return evidence-backed findings and required actions only."
            ),
            output_type=WorkerReport,
        )
        specialists.append(specialist)
        specialist_tools.append(
            specialist.as_tool(
                tool_name=f"specialist_{role}",
                tool_description=f"Analyze one bounded {role} work package and return evidence-backed findings.",
                max_turns=6,
            )
        )

    dispatcher = agent_class(
        name=AGENTS[0].name,
        model=selected_model,
        instructions=(
            f"{base}\n\n"
            "Create one ordered six-item plan, one item for each fixed core worker role in manifest order. "
            "Do not perform worker tasks yourself. Identify required evidence, initial blockers, and specialists needed."
        ),
        output_type=DispatchPlan,
    )

    workers: list[Any] = []
    for contract in AGENTS[1:7]:
        worker_tools = specialist_tools if contract.role == "chat_cognitive" else []
        workers.append(agent_class(
            name=contract.name,
            model=selected_model,
            instructions=(
                f"{base}\n\n"
                f"Your fixed role is {contract.role}. Responsibility: {contract.responsibility} "
                f"Allowed zones: {', '.join(contract.allowed_zones)}. "
                "Analyze only your bounded domain. Return a WorkerReport. "
                "Use a specialist tool only for a clearly bounded package and keep orchestration ownership. "
                "Set blocked=true whenever evidence needed for a claim is absent. "
                "You may recommend exact changes, but you may not claim they were applied."
            ),
            tools=worker_tools,
            output_type=WorkerReport,
        ))

    judge = agent_class(
        name=AGENTS[-1].name,
        model=selected_model,
        instructions=(
            f"{base}\n\n"
            "You are the final evidence controller. You never edit files and never perform a release. "
            "Reject unsupported worker claims. draft_pr_ready may be true only when all required evidence "
            "is supplied, all checks are green, no blocker remains, and the result is explicitly Draft-PR-only. "
            "The first-loop verdict can never end the workflow; a second refinement loop is mandatory."
        ),
        output_type=JudgeVerdict,
    )

    swarm = CognitiveSwarm(
        dispatcher=dispatcher,
        workers=tuple(workers),
        specialists=tuple(specialists),
        judge=judge,
    )
    if swarm.agent_count < 8:
        raise RuntimeError("Sovereign core topology dropped below eight agents.")
    return swarm


def _worker_input(
    *,
    mission: str,
    evidence: str,
    plan: DispatchPlan,
    loop: int,
    role: str,
    prior_verdict: JudgeVerdict | None,
) -> str:
    previous = prior_verdict.model_dump_json() if prior_verdict else "none"
    return (
        f"Mission:\n{mission}\n\n"
        f"Fixed worker role: {role}\n"
        f"Double-loop pass: {loop}\n\n"
        f"Dispatcher plan:\n{plan.model_dump_json()}\n\n"
        f"Supplied runtime evidence:\n{evidence or '[no evidence supplied]'}\n\n"
        f"Prior judge verdict:\n{previous}\n"
    )


def _judge_input(
    *,
    mission: str,
    evidence: str,
    plan: DispatchPlan,
    loop: int,
    reports: list[WorkerReport],
) -> str:
    return (
        f"Mission:\n{mission}\n\n"
        f"Double-loop checkpoint: {loop}\n"
        f"Dispatcher plan:\n{plan.model_dump_json()}\n\n"
        f"Worker reports:\n{[report.model_dump() for report in reports]}\n\n"
        f"Independent supplied runtime evidence:\n{evidence or '[no evidence supplied]'}\n"
    )


async def run_cognitive_swarm(
    mission: str,
    *,
    evidence: str = "",
    model: str | None = None,
    stage_observer: StageObserver | None = None,
) -> dict[str, Any]:
    normalized_mission = mission.strip()
    if not normalized_mission:
        raise ValueError("mission is required")
    if not ensure_openai_runtime_key():
        return {
            "ok": False,
            "status": "BLOCKED",
            "blocker": "OPENAI_API_KEY is not configured in the protected backend environment.",
            "manifest": manifest_payload(),
        }

    try:
        _, runner_class = _require_agents_sdk()
        swarm = build_cognitive_swarm(model=model)
    except SwarmExecutionError:
        raise
    except Exception as exc:
        raise classify_swarm_exception(exc, stage="swarm-build") from exc
    _emit_stage(
        stage_observer,
        agent_id="dispatcher",
        event_type="agent_started",
        status="RUNNING",
        summary="Dispatcher started the evidence-bounded planning model call.",
        next_action="WAIT_FOR_DISPATCH_PLAN",
    )
    plan_result = await _run_stage(
        runner_class,
        swarm.dispatcher,
        f"Mission:\n{normalized_mission}\n\nRuntime evidence:\n{evidence or '[no evidence supplied]'}",
        stage="dispatcher",
    )
    plan = plan_result.final_output
    if not isinstance(plan, DispatchPlan):
        raise SwarmExecutionError(
            stage="dispatcher-output",
            family="AGENTS_STRUCTURED_OUTPUT_INVALID",
            error_type=type(plan).__name__,
            next_action="RETRY_WITH_BOUNDED_SCHEMA_DIAGNOSTICS",
            retryable=True,
        )
    _emit_stage(
        stage_observer,
        agent_id="dispatcher",
        event_type="agent_completed",
        status="COMPLETED",
        summary="Dispatcher produced a validated six-role work plan.",
        next_action="START_WORKER_PASS_ONE",
    )

    loop_payloads: list[dict[str, Any]] = []
    prior_verdict: JudgeVerdict | None = None

    for loop in (1, 2):
        reports: list[WorkerReport] = []
        for role, worker in zip(WORKER_ROLES, swarm.workers, strict=True):
            _emit_stage(
                stage_observer,
                agent_id=role,
                event_type="agent_started",
                status="RUNNING",
                summary=f"{role} started evidence analysis for double-loop pass {loop}.",
                next_action="WAIT_FOR_AGENT_REPORT",
                loop=loop,
            )
            result = await _run_stage(
                runner_class,
                worker,
                _worker_input(
                    mission=normalized_mission,
                    evidence=evidence,
                    plan=plan,
                    loop=loop,
                    role=role,
                    prior_verdict=prior_verdict,
                ),
                stage=f"loop-{loop}:worker:{role}",
            )
            report = result.final_output
            if not isinstance(report, WorkerReport):
                raise SwarmExecutionError(
                    stage=f"loop-{loop}:worker-output:{role}",
                    family="AGENTS_STRUCTURED_OUTPUT_INVALID",
                    error_type=type(report).__name__,
                    next_action="RETRY_WITH_BOUNDED_SCHEMA_DIAGNOSTICS",
                    retryable=True,
                )
            report.role = role
            report.loop = loop
            reports.append(report)
            _emit_stage(
                stage_observer,
                agent_id=role,
                event_type="agent_completed",
                status="COMPLETED",
                summary=f"{role} produced a validated evidence report for double-loop pass {loop}.",
                next_action="CONTINUE_WORKER_PASS" if role != WORKER_ROLES[-1] else "START_JUDGE_CHECKPOINT",
                loop=loop,
            )

        _emit_stage(
            stage_observer,
            agent_id="judge",
            event_type="agent_started",
            status="VERIFYING",
            summary=f"Judge started evidence verification for double-loop checkpoint {loop}.",
            next_action="WAIT_FOR_JUDGE_VERDICT",
            loop=loop,
        )
        judge_result = await _run_stage(
            runner_class,
            swarm.judge,
            _judge_input(
                mission=normalized_mission,
                evidence=evidence,
                plan=plan,
                loop=loop,
                reports=reports,
            ),
            stage=f"loop-{loop}:judge",
        )
        verdict = judge_result.final_output
        if not isinstance(verdict, JudgeVerdict):
            raise SwarmExecutionError(
                stage=f"loop-{loop}:judge-output",
                family="AGENTS_STRUCTURED_OUTPUT_INVALID",
                error_type=type(verdict).__name__,
                next_action="RETRY_WITH_BOUNDED_SCHEMA_DIAGNOSTICS",
                retryable=True,
            )
        verdict.loop = loop
        if loop == 1:
            verdict.draft_pr_ready = False
            if "mandatory_second_loop" not in verdict.required_next_actions:
                verdict.required_next_actions.append("mandatory_second_loop")
        _emit_stage(
            stage_observer,
            agent_id="judge",
            event_type="agent_completed",
            status="COMPLETED",
            summary=f"Judge produced a validated verdict for double-loop checkpoint {loop}.",
            next_action="START_WORKER_REFINEMENT_PASS_TWO" if loop == 1 else "FINALIZE_PERSISTED_RUN",
            loop=loop,
        )

        loop_payloads.append({
            "loop": loop,
            "workers": [report.model_dump() for report in reports],
            "judge": verdict.model_dump(),
        })
        prior_verdict = verdict

    final_verdict = prior_verdict
    if final_verdict is None:
        raise RuntimeError("The mandatory double loop did not produce a verdict.")

    draft_pr_ready = final_verdict.draft_pr_ready and not final_verdict.blockers
    nullfund_confirmed = _is_confirmed_nullfund(final_verdict)
    final_status = (
        "READY_FOR_DRAFT_PR"
        if draft_pr_ready
        else "COMPLETED"
        if nullfund_confirmed
        else "BLOCKED"
    )

    return {
        "ok": final_status in {"READY_FOR_DRAFT_PR", "COMPLETED"},
        "status": final_status,
        "manifest": manifest_payload(),
        "plan": plan.model_dump(),
        "loops": loop_payloads,
        "finalVerdict": final_verdict.model_dump(),
        "activeSpecialists": len(swarm.specialists),
        "approvalRequired": draft_pr_ready and final_verdict.human_approval_required,
        "autoMerge": False,
    }
