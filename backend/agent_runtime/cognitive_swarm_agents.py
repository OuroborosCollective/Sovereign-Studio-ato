"""OpenAI Agents SDK orchestration for the Sovereign cognitive swarm.

The model layer plans and reviews. Repository, database, deployment and merge
mutations remain in the existing bounded runtime tools and approval gates.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.metadata
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, Field, PrivateAttr

from .cognitive_swarm_manifest import (
    AGENTS,
    SPECIALIST_ROLES,
    WORKER_ROLES,
    manifest_payload,
    max_active_specialists,
)
from .cognitive_llm_transport import (
    RouteRunConfig,
    RouteRuntimeError,
    build_route_run_config,
)
from .cognitive_output_budget import assess_output_budget_evidence
from .cognitive_usage_billing import AgentStageBilling
from .fleet_supervisor import FleetContractError, FleetPlan
from .llm_contract import (
    LlmOutputContract,
    build_request_envelope,
    compile_contract_prompt,
    verify_llm_response,
)


DEFAULT_MODEL: Final[str] = ""
ALLOWED_LITELLM_MODEL_ALIASES: Final[frozenset[str]] = frozenset()
_DIRECT_ROUTE_REQUIRED_TRANSPORT: Final[str] = "unresolved"
_AGENT_OUTPUT_TOKEN_LIMIT: Final[int] = 2_048
_AGENT_WORKER_MAX_TURNS: Final[int] = 4
_AGENT_FREE_WORKSPACE_MAX_TURNS: Final[int] = 12
_AGENT_SINGLE_STAGE_MAX_TURNS: Final[int] = 1
SKILL_PATH: Final[Path] = Path(__file__).parent / "skills" / "sovereign-cognitive-architecture" / "SKILL.md"
RELEASE_HUNT_SKILL_PATH: Final[Path] = (
    Path(__file__).parent
    / "skills"
    / "sovereign-release-ready-error-family-hunt"
    / "SKILL.md"
)

_AGENT_CLASS: Any | None = None
_RUNNER_CLASS: Any | None = None
_AGENTS_SDK_ERROR = ""

StageObserver = Callable[[dict[str, object]], None]
RepositoryToolFactory = Callable[[str], list[Any]]
FleetLaneGuard = Callable[[str, tuple[str, ...]], Any]
FleetHeadReadback = Callable[[], str]


def _emit_stage(
    observer: StageObserver | None,
    *,
    agent_id: str,
    event_type: str,
    status: str,
    summary: str,
    next_action: str,
    loop: int | None = None,
    fleet_plan_hash: str | None = None,
    fleet_lane_id: str | None = None,
    fleet_task_id: str | None = None,
    assignment_hash: str | None = None,
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
    if fleet_plan_hash:
        payload["fleetPlanHash"] = fleet_plan_hash
    if fleet_lane_id:
        payload["fleetLaneId"] = fleet_lane_id
    if fleet_task_id:
        payload["fleetTaskId"] = fleet_task_id
    if assignment_hash:
        payload["assignmentHash"] = assignment_hash
    observer(payload)


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
        output_budget_evidence: dict[str, object] | None = None,
    ) -> None:
        super().__init__(family)
        self.stage = stage[:160]
        self.family = family[:160]
        self.error_type = error_type[:160]
        self.next_action = next_action[:240]
        self.retryable = bool(retryable)
        self.http_status = http_status
        self.request_id = (request_id or "")[:200] or None
        self.output_budget_evidence = dict(output_budget_evidence or {})

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "failureStage": self.stage,
            "failureFamily": self.family,
            "errorType": self.error_type,
            "nextAction": self.next_action,
            "retryable": self.retryable,
            "httpStatus": self.http_status,
            "requestId": self.request_id,
            "rawErrorPersisted": False,
        }
        if self.output_budget_evidence:
            payload["outputBudgetEvidence"] = dict(self.output_budget_evidence)
        return payload


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


def _output_budget_failure(value: Any, *, stage: str) -> SwarmExecutionError | None:
    evidence = assess_output_budget_evidence(
        value,
        output_token_limit=_AGENT_OUTPUT_TOKEN_LIMIT,
    )
    if evidence.get("budgetExhausted") is not True:
        return None
    return SwarmExecutionError(
        stage=stage,
        family="AGENTS_OUTPUT_BUDGET_EXHAUSTED",
        error_type="OutputBudgetEvidence",
        next_action="RETRY_WITH_BOUNDED_OUTPUT_BUDGET_INCREASE",
        retryable=True,
        output_budget_evidence=evidence,
    )


def classify_swarm_exception(
    exc: Exception,
    *,
    stage: str,
    transport: str = _DIRECT_ROUTE_REQUIRED_TRANSPORT,
) -> SwarmExecutionError:
    error_type = type(exc).__name__
    lowered = error_type.casefold()
    status = _exception_status(exc)
    budget_failure = _output_budget_failure(exc, stage=stage)
    normalized_transport = str(transport or _DIRECT_ROUTE_REQUIRED_TRANSPORT).strip().lower()
    provider_name = (
        "OPENROUTER"
        if normalized_transport == "openrouter"
        else "FREELLM"
        if normalized_transport == "freellm"
        else "ROUTE"
    )
    if isinstance(exc, FileNotFoundError):
        family, next_action, retryable = "AGENTS_RUNTIME_ASSET_MISSING", "VERIFY_PRODUCTION_RUNTIME_ASSETS", False
    elif status == 401 or "authentication" in lowered:
        family, next_action, retryable = (
            f"{provider_name}_AUTHENTICATION_FAILED",
            f"VERIFY_{provider_name}_PROTECTED_KEY",
            False,
        )
    elif status == 403 or "permission" in lowered:
        family, next_action, retryable = (
            f"{provider_name}_PERMISSION_DENIED",
            f"VERIFY_{provider_name}_MODEL_ACCESS",
            False,
        )
    elif status == 404 or "notfound" in lowered or "not_found" in lowered:
        family, next_action, retryable = (
            f"{provider_name}_MODEL_OR_ENDPOINT_NOT_FOUND",
            f"VERIFY_{provider_name}_MODEL_AND_ENDPOINT",
            False,
        )
    elif status == 429 or "ratelimit" in lowered or "rate_limit" in lowered:
        family, next_action, retryable = (
            f"{provider_name}_RATE_LIMITED",
            "RETRY_AFTER_PROVIDER_BACKOFF",
            True,
        )
    elif status in {408, 504} or "timeout" in lowered:
        family, next_action, retryable = (
            f"{provider_name}_TIMEOUT",
            "RETRY_FROM_PERSISTED_RUN_STATE",
            True,
        )
    elif status is not None and status >= 500:
        family, next_action, retryable = (
            f"{provider_name}_UNAVAILABLE",
            "RETRY_FROM_PERSISTED_RUN_STATE",
            True,
        )
    elif status == 400 or "badrequest" in lowered or "bad_request" in lowered:
        family, next_action, retryable = (
            f"{provider_name}_REQUEST_REJECTED",
            "REVIEW_MODEL_AND_STRUCTURED_OUTPUT_CONTRACT",
            False,
        )
    elif budget_failure is not None:
        return budget_failure
    elif any(marker in lowered for marker in ("modelbehavior", "output", "validation")):
        family, next_action, retryable = "AGENTS_STRUCTURED_OUTPUT_INVALID", "RETRY_WITH_BOUNDED_SCHEMA_DIAGNOSTICS", True
    elif "maxturn" in lowered or "max_turn" in lowered:
        family, next_action, retryable = "AGENTS_TURN_LIMIT_EXHAUSTED", "REVIEW_AGENT_TURN_BUDGET", False
    elif "connection" in lowered or "network" in lowered:
        family, next_action, retryable = (
            f"{provider_name}_CONNECTION_FAILED",
            "RETRY_FROM_PERSISTED_RUN_STATE",
            True,
        )
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


def _stage_max_turns(stage: str) -> int:
    normalized = str(stage or "").casefold()
    if "free-single-agent" in normalized:
        return _AGENT_FREE_WORKSPACE_MAX_TURNS
    if ":worker:" in normalized:
        return _AGENT_WORKER_MAX_TURNS
    return _AGENT_SINGLE_STAGE_MAX_TURNS


async def _run_stage(
    runner_class: Any,
    agent: Any,
    prompt: str,
    *,
    stage: str,
    stage_billing: AgentStageBilling | None = None,
    run_config: Any | None = None,
    transport: str = _DIRECT_ROUTE_REQUIRED_TRANSPORT,
) -> Any:
    reservation = (
        stage_billing.reserve(stage=stage, prompt=prompt)
        if stage_billing is not None
        else None
    )
    try:
        effective_run_config = run_config
        if effective_run_config is None:
            raise SwarmExecutionError(
                stage=stage,
                family="AGENTS_DIRECT_ROUTE_REQUIRED",
                error_type="RuntimeConfigurationError",
                next_action="RESOLVE_DATABASE_OPENROUTER_OR_FREELLM_ROUTE",
                retryable=False,
            )
        result = await runner_class.run(
            agent,
            prompt,
            run_config=effective_run_config,
            max_turns=_stage_max_turns(stage),
        )
    except SwarmExecutionError as exc:
        if reservation is not None:
            if exc.http_status in {400, 401, 403, 404, 429}:
                stage_billing.refund_failed_before_usage(
                    reservation,
                    family=exc.family,
                )
            else:
                stage_billing.mark_reconciliation_required(
                    reservation,
                    family=exc.family,
                )
        raise
    except Exception as exc:
        classified = classify_swarm_exception(
            exc,
            stage=stage,
            transport=transport,
        )
        if reservation is not None:
            if classified.http_status in {400, 401, 403, 404, 429}:
                stage_billing.refund_failed_before_usage(
                    reservation,
                    family=classified.family,
                )
            else:
                stage_billing.mark_reconciliation_required(
                    reservation,
                    family=classified.family,
                )
        raise classified from exc
    if reservation is not None:
        stage_billing.settle(reservation, result)
    return result


async def _run_billed_stage(
    runner_class: Any,
    agent: Any,
    prompt: str,
    *,
    stage: str,
    stage_billing: AgentStageBilling | None,
    run_config: Any | None = None,
    transport: str = _DIRECT_ROUTE_REQUIRED_TRANSPORT,
) -> Any:
    kwargs: dict[str, Any] = {"stage": stage}
    if run_config is not None:
        kwargs["run_config"] = run_config
    kwargs["transport"] = transport
    if stage_billing is not None:
        kwargs["stage_billing"] = stage_billing
    return await _run_stage(runner_class, agent, prompt, **kwargs)


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


MISSION_INTENT_OUTPUT_CONTRACT: Final[LlmOutputContract] = LlmOutputContract(
    contract_id="mission.intent",
    version=1,
    json_schema={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["conversation", "read_only_analysis", "repository_execution"],
            },
            "normalizedGoal": {"type": "string", "minLength": 1, "maxLength": 2000},
            "requiresOnlineTools": {"type": "boolean"},
            "requiresRepositoryWorkspace": {"type": "boolean"},
            "learningScope": {
                "type": "array",
                "maxItems": 12,
                "items": {"type": "string", "maxLength": 160},
            },
        },
        "required": [
            "mode",
            "normalizedGoal",
            "requiresOnlineTools",
            "requiresRepositoryWorkspace",
            "learningScope",
        ],
        "additionalProperties": False,
    },
)


class MissionIntent(BaseModel):
    mode: Literal["conversation", "read_only_analysis", "repository_execution"]
    normalized_goal: str = Field(min_length=1, max_length=2000)
    requires_online_tools: bool
    requires_repository_workspace: bool
    learning_scope: list[str] = Field(default_factory=list, max_length=12)
    confidence: float = Field(ge=0.0, le=1.0)
    _contract_receipt: dict[str, Any] = PrivateAttr(default_factory=dict)

    def contract_receipt(self) -> dict[str, Any]:
        return dict(self._contract_receipt)


def _mission_intent_contract_payload(intent: MissionIntent) -> dict[str, Any]:
    return {
        "mode": intent.mode,
        "normalizedGoal": intent.normalized_goal,
        "requiresOnlineTools": intent.requires_online_tools,
        "requiresRepositoryWorkspace": intent.requires_repository_workspace,
        "learningScope": list(intent.learning_scope),
    }


_FREELLM_INTENT_MODES: Final[frozenset[str]] = frozenset({
    "conversation",
    "read_only_analysis",
    "repository_execution",
})


def _invalid_freellm_intent(error_type: str) -> SwarmExecutionError:
    return SwarmExecutionError(
        stage="intent-router-output",
        family="AGENTS_INTENT_TEXT_INVALID",
        error_type=error_type,
        next_action="RETRY_WITH_PLAIN_TEXT_INTENT_CONTRACT",
        retryable=True,
    )


def _parse_freellm_intent_text(raw_output: object, fallback_goal: str) -> MissionIntent:
    """Normalize explicit FreeLLM intent fields without interpreting user language."""

    if not isinstance(raw_output, str) or not raw_output.strip():
        raise _invalid_freellm_intent(type(raw_output).__name__)
    text = raw_output.strip()
    fenced = re.fullmatch(r"```(?:text|json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    mode_value = ""
    goal_value = ""
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise _invalid_freellm_intent("InvalidIntentJson") from exc
        if not isinstance(payload, dict):
            raise _invalid_freellm_intent("IntentJsonNotObject")
        mode_value = str(payload.get("mode") or payload.get("intent") or "")
        goal_value = str(
            payload.get("normalized_goal")
            or payload.get("normalizedGoal")
            or payload.get("goal")
            or ""
        )
    else:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        mode_index = -1
        for index, line in enumerate(lines[:4]):
            cleaned = line.strip("`*_#- ")
            match = re.fullmatch(
                r"(?:mode|intent)\s*[:=]\s*([A-Za-z _-]+)",
                cleaned,
                flags=re.IGNORECASE,
            )
            candidate = match.group(1) if match else cleaned
            normalized_candidate = candidate.strip().casefold().replace("-", "_").replace(" ", "_")
            if normalized_candidate in _FREELLM_INTENT_MODES:
                mode_value = normalized_candidate
                mode_index = index
                break
        if mode_index < 0:
            raise _invalid_freellm_intent("UnsupportedIntentMode")
        goal_lines = lines[mode_index + 1 :]
        if goal_lines:
            goal_lines[0] = re.sub(
                r"^(?:goal|normalized_goal|normalizedGoal)\s*[:=]\s*",
                "",
                goal_lines[0],
                flags=re.IGNORECASE,
            ).strip()
        goal_value = " ".join(goal_lines).strip()
    normalized_mode = mode_value.strip().casefold().replace("-", "_").replace(" ", "_")
    if normalized_mode not in _FREELLM_INTENT_MODES:
        raise _invalid_freellm_intent("UnsupportedIntentMode")
    normalized_goal = (goal_value.strip() or fallback_goal.strip())[:2000]
    if not normalized_goal:
        raise _invalid_freellm_intent("EmptyNormalizedGoal")
    return MissionIntent(
        mode=normalized_mode,
        normalized_goal=normalized_goal,
        requires_online_tools=normalized_mode != "conversation",
        requires_repository_workspace=normalized_mode == "repository_execution",
        learning_scope=[],
        confidence=0.0,
    )


async def classify_mission_intent(
    mission: str,
    *,
    model: str | None = None,
    route: dict[str, Any] | None = None,
    stage_billing: AgentStageBilling | None = None,
) -> MissionIntent:
    """Let the routed LLM understand user language; runtime only validates the bounded action contract."""

    normalized_mission = mission.strip()
    if not normalized_mission:
        raise ValueError("mission is required")
    if route is None:
        raise SwarmExecutionError(
            stage="intent-router",
            family="AGENTS_DIRECT_ROUTE_REQUIRED",
            error_type="RuntimeConfigurationError",
            next_action="RESOLVE_DATABASE_OPENROUTER_OR_FREELLM_ROUTE",
            retryable=False,
        )
    try:
        route_runtime = build_route_run_config(
            route,
            output_token_limit=_AGENT_OUTPUT_TOKEN_LIMIT,
        )
    except RouteRuntimeError as exc:
        raise SwarmExecutionError(
            stage="intent-router",
            family=exc.family,
            error_type=type(exc).__name__,
            next_action=exc.next_action,
            retryable=False,
        ) from exc
    selected_model = route_runtime.model
    agent_class, runner_class = _require_agents_sdk()
    freellm_text_contract = bool(
        route_runtime is not None and route_runtime.transport == "freellm"
    )
    router_kwargs: dict[str, Any] = {
        "name": "Sovereign Intent Router",
        "model": selected_model,
        "instructions": (
            "Understand the user's natural language, including typos, slang, incomplete grammar and mixed technical language. "
            "Choose repository_execution when the user asks the system to change, fix, implement, rerun, test, build, deploy, "
            "or otherwise act on the configured repository/runtime. Choose read_only_analysis when tools may inspect evidence "
            "but no mutation is requested. Choose conversation for explanation or discussion without online tools. "
            "Do not infer success, permissions, secrets or completed actions. "
            + (
                "Return plain text with MODE=<conversation|read_only_analysis|repository_execution> on one line and GOAL=<normalized user goal> on the next line. A JSON object with only mode and normalized_goal is also accepted. Do not add commentary."
                if freellm_text_contract
                else "Return only the structured intent. learning_scope may name reusable observations that should be learned only after real tool evidence exists."
            )
        ),
    }
    if not freellm_text_contract:
        router_kwargs["output_type"] = MissionIntent
    router = agent_class(**router_kwargs)
    raw_prompt = f"User mission:\n{normalized_mission}"
    try:
        request_envelope = build_request_envelope(
            operation_identity="intent.router",
            route_binding=route_runtime.route_binding,
            prompt=raw_prompt,
            contract=MISSION_INTENT_OUTPUT_CONTRACT,
            context={"stage": "intent-router"},
        )
        routed_prompt = compile_contract_prompt(
            envelope=request_envelope,
            contract=MISSION_INTENT_OUTPUT_CONTRACT,
            prompt=raw_prompt,
        )
    except ValueError as exc:
        raise SwarmExecutionError(
            stage="intent-router-contract",
            family="LLM_REQUEST_CONTRACT_REJECTED",
            error_type=type(exc).__name__,
            next_action="VERIFY_ROUTE_REVISION_AND_OUTPUT_CONTRACT",
            retryable=False,
        ) from exc
    result = await _run_billed_stage(
        runner_class,
        router,
        routed_prompt,
        stage="intent-router",
        stage_billing=stage_billing,
        run_config=route_runtime.run_config,
        transport=route_runtime.transport,
    )
    if freellm_text_contract:
        try:
            intent = _parse_freellm_intent_text(result.final_output, normalized_mission)
        except SwarmExecutionError as exc:
            budget_failure = _output_budget_failure(result, stage="intent-router-output")
            if budget_failure is not None:
                raise budget_failure from exc
            raise
    else:
        intent = result.final_output
    if not isinstance(intent, MissionIntent):
        budget_failure = _output_budget_failure(result, stage="intent-router-output")
        if budget_failure is not None:
            raise budget_failure
        raise SwarmExecutionError(
            stage="intent-router-output",
            family="AGENTS_STRUCTURED_OUTPUT_INVALID",
            error_type=type(intent).__name__,
            next_action="RETRY_WITH_BOUNDED_SCHEMA_DIAGNOSTICS",
            retryable=True,
        )
    if intent.mode == "repository_execution":
        intent.requires_online_tools = True
        intent.requires_repository_workspace = True
    elif intent.mode == "conversation":
        intent.requires_online_tools = False
        intent.requires_repository_workspace = False
    verification = verify_llm_response(
        envelope=request_envelope,
        contract=MISSION_INTENT_OUTPUT_CONTRACT,
        response=_mission_intent_contract_payload(intent),
    )
    if not verification.accepted:
        raise SwarmExecutionError(
            stage="intent-router-output-contract",
            family="LLM_OUTPUT_CONTRACT_REJECTED",
            error_type="LlmContractVerification",
            next_action="RETRY_WITH_REVISION_BOUND_JSON_SCHEMA_CONTRACT",
            retryable=True,
        )
    intent._contract_receipt = verification.receipt.to_dict()
    return intent


class FreeSingleAgentResult(BaseModel):
    mode: Literal["conversation", "read_only_analysis", "repository_execution"]
    assistant_text: str = Field(min_length=1, max_length=8000)
    findings: list[str] = Field(default_factory=list, max_length=20)
    blockers: list[str] = Field(default_factory=list, max_length=20)
    upgrade_required: bool = False
    repository_execution_performed: bool = False
    response_truncated: bool = False


async def run_free_single_agent(
    mission: str,
    *,
    evidence: str = "",
    model: str,
    intent: MissionIntent,
    route: dict[str, Any] | None = None,
    stage_observer: StageObserver | None = None,
    repository_tool_factory: RepositoryToolFactory | None = None,
) -> dict[str, Any]:
    """Run exactly one foreground agent on one DB-resolved direct FreeLLM route."""
    normalized_mission = str(mission or "").strip()
    selected_model = str(model or "").strip()
    if not normalized_mission:
        raise ValueError("mission is required")
    if not isinstance(intent, MissionIntent):
        raise ValueError("A validated mission intent is required for the free profile.")
    if route is None:
        raise SwarmExecutionError(
            stage="free-single-agent",
            family="AGENTS_DIRECT_ROUTE_REQUIRED",
            error_type="RuntimeConfigurationError",
            next_action="RESOLVE_DATABASE_FREELLM_ROUTE",
            retryable=False,
        )
    try:
        route_runtime = build_route_run_config(
            route,
            output_token_limit=_AGENT_OUTPUT_TOKEN_LIMIT,
        )
    except RouteRuntimeError as exc:
        raise SwarmExecutionError(
            stage="free-single-agent",
            family=exc.family,
            error_type=type(exc).__name__,
            next_action=exc.next_action,
            retryable=False,
        ) from exc
    if route_runtime.transport != "freellm":
        raise ValueError("The free profile requires a direct FreeLLM route.")
    selected_model = route_runtime.model
    agent_class, runner_class = _require_agents_sdk()
    repository_tools = (
        list(repository_tool_factory("free_single_agent"))
        if repository_tool_factory is not None
        else []
    )
    single_agent = agent_class(
        name="Sovereign Free Single Agent",
        model=selected_model,
        instructions=(
            "You are the single-agent free execution profile. Understand the user's language and complete one bounded task without spawning or delegating to another agent. "
            "When repository tools are present, you may read, create, replace and exactly patch code only inside the isolated Code-Server Agent Job workspace. Read before writing; after every mutation inspect Git status and diff and run at least one relevant allowlisted test. "
            "You must never merge, auto-merge, deploy to production, mutate the host, read secrets, or claim success without tool evidence. "
            "When repository execution is requested but no repository tools are present, explain that the workspace tools are unavailable. "
            "For conversation or read-only analysis, answer directly. Return one useful plain-text answer; do not emit JSON or a schema wrapper."
        ),
        tools=repository_tools,
    )
    _emit_stage(
        stage_observer,
        agent_id="free_single_agent",
        event_type="agent_started",
        status="RUNNING",
        summary="The database-resolved free single agent started.",
        next_action="WAIT_FOR_FREE_SINGLE_AGENT",
    )
    result = await _run_stage(
        runner_class,
        single_agent,
        (
            f"Validated mission mode: {intent.mode}\n"
            f"Normalized goal: {intent.normalized_goal}\n\n"
            f"User mission:\n{normalized_mission}\n\n"
            f"Supplied read-only evidence:\n{evidence or '[no evidence supplied]'}"
        ),
        stage="free-single-agent",
        stage_billing=None,
        run_config=route_runtime.run_config,
        transport=route_runtime.transport,
    )
    raw_output = result.final_output
    output_budget_evidence = assess_output_budget_evidence(
        result,
        output_token_limit=_AGENT_OUTPUT_TOKEN_LIMIT,
    )
    if not isinstance(raw_output, str) or not raw_output.strip():
        budget_failure = _output_budget_failure(result, stage="free-single-agent-output")
        if budget_failure is not None:
            raise budget_failure
        raise SwarmExecutionError(
            stage="free-single-agent-output",
            family="AGENTS_TEXT_OUTPUT_INVALID",
            error_type=type(raw_output).__name__,
            next_action="RETRY_WITH_PLAIN_TEXT_OUTPUT",
            retryable=True,
        )
    normalized_output = raw_output.strip()
    assistant_text = normalized_output[:8000]
    output = FreeSingleAgentResult(
        mode=intent.mode,
        assistant_text=assistant_text,
        response_truncated=(
            len(normalized_output) > len(assistant_text)
            or output_budget_evidence.get("budgetExhausted") is True
        ),
    )
    repository_requested = intent.mode == "repository_execution"
    workspace_tools_available = bool(repository_tools)
    if repository_requested and not workspace_tools_available:
        output.upgrade_required = True
        output.repository_execution_performed = False
        if "WORKSPACE_TOOLS_REQUIRED" not in output.blockers:
            output.blockers.append("WORKSPACE_TOOLS_REQUIRED")
    else:
        output.upgrade_required = False
        output.repository_execution_performed = False
    blocked = repository_requested and not workspace_tools_available
    _emit_stage(
        stage_observer,
        agent_id="free_single_agent",
        event_type="agent_completed",
        status="BLOCKED" if blocked else "COMPLETED",
        summary=(
            "The free single agent could not access an isolated workspace."
            if blocked
            else "The free single agent completed its bounded foreground execution."
        ),
        next_action=(
            "PROVISION_ISOLATED_CODE_SERVER_WORKSPACE"
            if blocked
            else "VERIFY_SINGLE_AGENT_WORKSPACE_EVIDENCE"
            if repository_requested
            else "NO_FURTHER_ACTION_REQUIRED"
        ),
    )
    return {
        "ok": not blocked,
        "status": "BLOCKED" if blocked else "COMPLETED",
        "executionProfile": "free_single_agent",
        "maxForegroundAgents": 1,
        "maxBackgroundAgents": 0,
        "repositoryExecutionAllowed": True,
        "repositoryExecutionPerformed": False,
        "result": output.model_dump(),
        "activeSpecialists": 0,
        "autoMerge": False,
    }


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
    mission_complete: bool = False
    human_approval_required: bool = True
    hunt_outcome: str = ""
    error_family: str = ""
    next_error_family: str = ""
    nullfind_confirmed: bool = False


def _parse_text_contract_output(
    raw_output: object,
    model_type: type[BaseModel],
    *,
    stage: str,
    result: Any | None = None,
) -> BaseModel:
    """Parse one FreeLLM JSON text contract without treating prose as structured truth."""
    if not isinstance(raw_output, str) or not raw_output.strip():
        budget_failure = _output_budget_failure(result, stage=f"{stage}-output") if result is not None else None
        if budget_failure is not None:
            raise budget_failure
        raise SwarmExecutionError(
            stage=f"{stage}-output",
            family="AGENTS_TEXT_CONTRACT_INVALID",
            error_type=type(raw_output).__name__,
            next_action="RETRY_WITH_STRICT_JSON_TEXT_CONTRACT",
            retryable=True,
        )
    text = raw_output.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return model_type.model_validate_json(text)
    except Exception as exc:
        budget_failure = _output_budget_failure(result, stage=f"{stage}-output") if result is not None else None
        if budget_failure is not None:
            raise budget_failure from exc
        raise SwarmExecutionError(
            stage=f"{stage}-output",
            family="AGENTS_TEXT_CONTRACT_INVALID",
            error_type=type(exc).__name__,
            next_action="RETRY_WITH_STRICT_JSON_TEXT_CONTRACT",
            retryable=True,
        ) from exc


def _resolved_swarm_status(final_verdict: JudgeVerdict) -> tuple[bool, str]:
    ready_for_draft_pr = final_verdict.draft_pr_ready and not final_verdict.blockers
    read_only_complete = final_verdict.mission_complete and not final_verdict.blockers
    if ready_for_draft_pr:
        return True, "READY_FOR_DRAFT_PR"
    if read_only_complete:
        return True, "COMPLETED"
    return False, "BLOCKED"


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
    bundles: list[str] = []
    for path, label in (
        (SKILL_PATH, "Sovereign cognitive"),
        (RELEASE_HUNT_SKILL_PATH, "Sovereign release-hunt"),
    ):
        content = path.read_text("utf-8").strip()
        if not content.startswith("---"):
            raise RuntimeError(f"{label} skill front matter is missing.")
        bundles.append(content)
    return "\n\n--- bundled-skill-boundary ---\n\n".join(bundles)


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


def build_cognitive_swarm(
    model: str | None = None,
    *,
    main_model: str | None = None,
    agent_model: str | None = None,
    worker_models: dict[str, str] | None = None,
    repository_tool_factory: RepositoryToolFactory | None = None,
    run_config: Any | None = None,
    main_run_config: Any | None = None,
    agent_run_config: Any | None = None,
    text_contract: bool = False,
) -> CognitiveSwarm:
    selected_main_model = str(main_model or model or "").strip()
    selected_agent_model = str(agent_model or selected_main_model).strip()
    if not selected_main_model or not selected_agent_model:
        raise ValueError("Main and six-agent model identifiers are required.")
    resolved_main_config = main_run_config if main_run_config is not None else run_config
    resolved_agent_config = (
        agent_run_config if agent_run_config is not None else resolved_main_config
    )
    if resolved_main_config is None or resolved_agent_config is None:
        raise ValueError(
            "Database-resolved direct route RunConfig values are required for the swarm."
        )
    selected_worker_models = {
        role: str((worker_models or {}).get(role) or selected_agent_model).strip()
        for role in WORKER_ROLES
    }
    if any(not value for value in selected_worker_models.values()):
        raise ValueError("Each fixed worker requires one database-resolved model identifier.")
    agent_class, _ = _require_agents_sdk()

    skill = _load_skill_instructions()
    base = _base_instructions(skill)

    specialists: list[Any] = []
    specialist_tools: list[Any] = []
    for role in SPECIALIST_ROLES[:max_active_specialists()]:
        specialist_kwargs: dict[str, Any] = {
            "name": f"Sovereign {role.replace('_', ' ').title()} Specialist",
            "model": selected_agent_model,
            "instructions": (
                f"{base}\n\n"
                f"You are the bounded {role} specialist. Work on exactly one assigned package. "
                "Never spawn agents, merge, deploy, read secrets, change global state, or write outside assigned files. "
                "Return evidence-backed findings and required actions only."
                + (" Return exactly one JSON object matching WorkerReport fields, with no prose or markdown." if text_contract else "")
            ),
        }
        if not text_contract:
            specialist_kwargs["output_type"] = WorkerReport
        specialist = agent_class(**specialist_kwargs)
        specialists.append(specialist)
        specialist_tools.append(
            specialist.as_tool(
                tool_name=f"specialist_{role}",
                tool_description=f"Analyze one bounded {role} work package and return evidence-backed findings.",
                run_config=resolved_agent_config,
                max_turns=2,
            )
        )

    dispatcher_kwargs: dict[str, Any] = {
        "name": AGENTS[0].name,
        "model": selected_main_model,
        "instructions": (
            f"{base}\n\n"
            "Create one ordered six-item plan, one item for each fixed core worker role in manifest order. "
            "Do not perform worker tasks yourself. Identify required evidence, initial blockers, and specialists needed."
            + (" Return exactly one JSON object with mission, ordered_work, required_evidence and initial_blockers; no prose or markdown." if text_contract else "")
        ),
    }
    if not text_contract:
        dispatcher_kwargs["output_type"] = DispatchPlan
    dispatcher = agent_class(**dispatcher_kwargs)

    workers: list[Any] = []
    for contract in AGENTS[1:7]:
        worker_tools = list(specialist_tools) if contract.role == "chat_cognitive" else []
        if repository_tool_factory is not None:
            worker_tools.extend(repository_tool_factory(contract.role))
        repository_instruction = (
            "Repository tools are connected to a real isolated Agent Job workspace. "
            "Use at least one supplied repository tool before making repository claims. "
            "Read or scan before writing. Writes must use exact SHA-bound replacement tools, "
            "and completion requires independent status, diff and test evidence. "
            if repository_tool_factory is not None
            else ""
        )
        worker_kwargs: dict[str, Any] = {
            "name": contract.name,
            "model": selected_worker_models[contract.role],
            "instructions": (
                f"{base}\n\n"
                f"Your fixed role is {contract.role}. Responsibility: {contract.responsibility} "
                f"Allowed zones: {', '.join(contract.allowed_zones)}. "
                "Analyze only your bounded domain. Return a WorkerReport. "
                "Use a specialist tool only for a clearly bounded package and keep orchestration ownership. "
                "Set blocked=true whenever evidence needed for a claim is absent. "
                f"{repository_instruction}"
                "You may recommend exact changes, but you may claim an action was applied only when a tool result confirms it."
                + (" Return exactly one JSON object with role, loop, status, findings, required_actions, evidence_observed, evidence_missing and blocked; no prose or markdown." if text_contract else "")
            ),
            "tools": worker_tools,
        }
        if not text_contract:
            worker_kwargs["output_type"] = WorkerReport
        workers.append(agent_class(**worker_kwargs))

    judge_kwargs: dict[str, Any] = {
        "name": AGENTS[-1].name,
        "model": selected_main_model,
        "instructions": (
            f"{base}\n\n"
            "You are the final evidence controller. You never edit files and never perform a release. "
            "Reject unsupported worker claims. draft_pr_ready may be true only when all required evidence "
            "is supplied, all checks are green, no blocker remains, and the result is explicitly Draft-PR-only. "
            "For a read-only mission, mission_complete may be true when the requested analysis is satisfied, "
            "no blocker remains, and no repository change is required. Do not block on evidence for your own "
            "current response; the host records that stage afterward. The first-loop verdict can never end the "
            "workflow; a second refinement loop is mandatory. For release-hunt missions, populate hunt_outcome, "
            "error_family, next_error_family and nullfind_confirmed exactly as the bundled release-hunt skill requires."
            + (" Return exactly one JSON object matching JudgeVerdict fields, with no prose or markdown." if text_contract else "")
        ),
    }
    if not text_contract:
        judge_kwargs["output_type"] = JudgeVerdict
    judge = agent_class(**judge_kwargs)

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
    fleet_plan_hash: str = "",
    fleet_lane_id: str = "",
    fleet_task_id: str = "",
    assignment_hash: str = "",
) -> str:
    previous = prior_verdict.model_dump_json() if prior_verdict else "none"
    fleet_binding = (
        "No repository Fleet binding applies to this analysis-only worker."
        if not fleet_plan_hash
        else (
            "Repository Fleet binding (immutable for this pass):\n"
            f"planHash={fleet_plan_hash}\n"
            f"laneId={fleet_lane_id}\n"
            f"taskId={fleet_task_id}\n"
            f"assignmentHash={assignment_hash}\n"
        )
    )
    return (
        f"Mission:\n{mission}\n\n"
        f"Fixed worker role: {role}\n"
        f"Double-loop pass: {loop}\n\n"
        f"Dispatcher plan:\n{plan.model_dump_json()}\n\n"
        f"{fleet_binding}\n\n"
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


def _resolve_repository_fleet_execution(
    *,
    repository_tool_factory: RepositoryToolFactory | None,
    fleet_plan: FleetPlan | dict[str, Any] | None,
    fleet_task_ids_by_role: dict[str, str] | None,
    fleet_assignments_by_role: dict[str, Any] | None,
    fleet_lane_guard: FleetLaneGuard | None,
) -> tuple[FleetPlan | None, dict[str, str], dict[str, str], FleetLaneGuard | None]:
    """Validate the only scheduler authority for repository-backed workers.

    Non-repository analysis keeps its existing read-only worker topology.  Once
    repository tools are supplied, a hash-valid FleetPlan, exact role/task mapping,
    exact assignment hashes and a lane admission guard are mandatory before the
    dispatcher can call a model.
    """

    if repository_tool_factory is None:
        return None, {}, {}, None
    if (
        fleet_plan is None
        or fleet_task_ids_by_role is None
        or fleet_assignments_by_role is None
        or fleet_lane_guard is None
    ):
        raise SwarmExecutionError(
            stage="fleet-plan",
            family="FLEET_PLAN_REQUIRED_FOR_REPOSITORY_WORKERS",
            error_type="FleetPlanRequired",
            next_action="BUILD_AND_PERSIST_A_HASH_BOUND_FLEET_PLAN",
            retryable=False,
        )
    try:
        plan = fleet_plan if isinstance(fleet_plan, FleetPlan) else FleetPlan.from_dict(fleet_plan)
        task_ids_by_role = {
            role: str(fleet_task_ids_by_role.get(role) or "").strip()
            for role in WORKER_ROLES
        }
        if any(not task_id for task_id in task_ids_by_role.values()):
            raise FleetContractError("Fleet role/task binding is incomplete")
        if len(set(task_ids_by_role.values())) != len(task_ids_by_role):
            raise FleetContractError("Fleet role/task binding contains duplicates")
        if set(task_ids_by_role.values()) != {task.task_id for task in plan.tasks}:
            raise FleetContractError("FleetPlan tasks do not match persisted worker tasks")
        if any(task.expected_base_revision != plan.base_revision for task in plan.tasks):
            raise FleetContractError("FleetPlan task base revision drifted")
        lane_tasks = tuple(task_id for lane in plan.lanes for task_id in lane.task_ids)
        if set(lane_tasks) != set(task_ids_by_role.values()) or len(lane_tasks) != len(set(lane_tasks)):
            raise FleetContractError("FleetPlan lanes do not cover every worker exactly once")
        sequences = tuple(lane.sequence for lane in plan.lanes)
        if sequences != tuple(sorted(sequences)) or len(set(sequences)) != len(sequences):
            raise FleetContractError("FleetPlan lane ordering is invalid")
        assignment_hashes: dict[str, str] = {}
        for role, task_id in task_ids_by_role.items():
            assignment = fleet_assignments_by_role.get(role)
            assignment_task_id = str(
                getattr(assignment, "task_id", "")
                or (assignment.get("taskId") if isinstance(assignment, dict) else "")
                or (assignment.get("task_id") if isinstance(assignment, dict) else "")
                or ""
            ).strip()
            assignment_plan_hash = str(
                getattr(assignment, "plan_hash", "")
                or (assignment.get("planHash") if isinstance(assignment, dict) else "")
                or (assignment.get("plan_hash") if isinstance(assignment, dict) else "")
                or ""
            ).strip()
            assignment_hash = str(
                getattr(assignment, "assignment_hash", "")
                or (assignment.get("assignmentHash") if isinstance(assignment, dict) else "")
                or (assignment.get("assignment_hash") if isinstance(assignment, dict) else "")
                or ""
            ).strip()
            if assignment_task_id != task_id or assignment_plan_hash != plan.plan_hash or len(assignment_hash) != 64:
                raise FleetContractError("Fleet worker assignment does not match the plan")
            assignment_hashes[role] = assignment_hash
    except FleetContractError as exc:
        raise SwarmExecutionError(
            stage="fleet-plan",
            family="FLEET_PLAN_BINDING_INVALID",
            error_type=type(exc).__name__,
            next_action="REBUILD_FLEET_PLAN_FROM_CURRENT_PERSISTED_WORKER_BINDINGS",
            retryable=False,
        ) from exc
    return plan, task_ids_by_role, assignment_hashes, fleet_lane_guard


async def run_cognitive_swarm(
    mission: str,
    *,
    evidence: str = "",
    model: str | None = None,
    route: dict[str, Any] | None = None,
    main_route: dict[str, Any] | None = None,
    agent_route: dict[str, Any] | None = None,
    worker_routes: dict[str, dict[str, Any]] | None = None,
    stage_observer: StageObserver | None = None,
    repository_tool_factory: RepositoryToolFactory | None = None,
    fleet_plan: FleetPlan | dict[str, Any] | None = None,
    fleet_task_ids_by_role: dict[str, str] | None = None,
    fleet_assignments_by_role: dict[str, Any] | None = None,
    fleet_lane_guard: FleetLaneGuard | None = None,
    fleet_head_readback: FleetHeadReadback | None = None,
    stage_billing: AgentStageBilling | None = None,
) -> dict[str, Any]:
    normalized_mission = mission.strip()
    if not normalized_mission:
        raise ValueError("mission is required")
    resolved_main_route = main_route or route
    resolved_agent_route = agent_route or resolved_main_route
    if resolved_main_route is None or resolved_agent_route is None:
        raise SwarmExecutionError(
            stage="swarm-build",
            family="AGENTS_DIRECT_OPENROUTER_ROUTE_REQUIRED",
            error_type="RuntimeConfigurationError",
            next_action="RESOLVE_DATABASE_OPENROUTER_ROUTE",
            retryable=False,
        )
    resolved_fleet_plan, resolved_fleet_task_ids, assignment_hashes, resolved_lane_guard = _resolve_repository_fleet_execution(
        repository_tool_factory=repository_tool_factory,
        fleet_plan=fleet_plan,
        fleet_task_ids_by_role=fleet_task_ids_by_role,
        fleet_assignments_by_role=fleet_assignments_by_role,
        fleet_lane_guard=fleet_lane_guard,
    )
    if repository_tool_factory is not None and fleet_head_readback is None:
        raise SwarmExecutionError(
            stage="fleet-plan",
            family="FLEET_WORKSPACE_READBACK_REQUIRED",
            error_type="FleetWorkspaceReadbackRequired",
            next_action="READ_CURRENT_WORKSPACE_HEAD_BEFORE_EACH_FLEET_PASS",
            retryable=False,
        )
    try:
        main_runtime = build_route_run_config(
            resolved_main_route,
            output_token_limit=_AGENT_OUTPUT_TOKEN_LIMIT,
        )
        agent_runtime = (
            main_runtime
            if resolved_agent_route is resolved_main_route
            or str(resolved_agent_route.get("id") or "")
            == str(resolved_main_route.get("id") or "")
            else build_route_run_config(
                resolved_agent_route,
                output_token_limit=_AGENT_OUTPUT_TOKEN_LIMIT,
            )
        )
        resolved_worker_routes = {
            role: dict((worker_routes or {}).get(role) or resolved_agent_route)
            for role in WORKER_ROLES
        }
        worker_runtimes = {
            role: (
                agent_runtime
                if str(selected.get("id") or "") == str(resolved_agent_route.get("id") or "")
                else build_route_run_config(selected, output_token_limit=_AGENT_OUTPUT_TOKEN_LIMIT)
            )
            for role, selected in resolved_worker_routes.items()
        }
    except RouteRuntimeError as exc:
        raise SwarmExecutionError(
            stage="swarm-build",
            family=exc.family,
            error_type=type(exc).__name__,
            next_action=exc.next_action,
            retryable=False,
        ) from exc
    transports = {main_runtime.transport, agent_runtime.transport, *(runtime.transport for runtime in worker_runtimes.values())}
    if transports not in ({"openrouter"}, {"freellm"}):
        raise ValueError("A swarm requires one consistent direct transport across control and worker routes.")
    text_contract = transports == {"freellm"}
    selected_main_model = main_runtime.model
    selected_agent_model = agent_runtime.model
    selected_worker_models = {role: runtime.model for role, runtime in worker_runtimes.items()}

    try:
        _, runner_class = _require_agents_sdk()
        build_kwargs: dict[str, Any] = {
            "main_model": selected_main_model,
            "agent_model": selected_agent_model,
            "worker_models": selected_worker_models,
            "main_run_config": main_runtime.run_config,
            "agent_run_config": agent_runtime.run_config,
            "text_contract": text_contract,
        }
        if repository_tool_factory is not None:
            build_kwargs["repository_tool_factory"] = repository_tool_factory
        swarm = build_cognitive_swarm(**build_kwargs)
    except SwarmExecutionError:
        raise
    except Exception as exc:
        raise classify_swarm_exception(
            exc,
            stage="swarm-build",
            transport=main_runtime.transport,
        ) from exc

    _emit_stage(
        stage_observer,
        agent_id="dispatcher",
        event_type="agent_started",
        status="RUNNING",
        summary="Dispatcher started the evidence-bounded planning model call.",
        next_action="WAIT_FOR_DISPATCH_PLAN",
    )
    plan_result = await _run_billed_stage(
        runner_class,
        swarm.dispatcher,
        f"Mission:\n{normalized_mission}\n\nRuntime evidence:\n{evidence or '[no evidence supplied]'}",
        stage="dispatcher",
        stage_billing=stage_billing,
        run_config=main_runtime.run_config,
        transport=main_runtime.transport,
    )
    plan = (
        _parse_text_contract_output(plan_result.final_output, DispatchPlan, stage="dispatcher", result=plan_result)
        if text_contract
        else plan_result.final_output
    )
    if not isinstance(plan, DispatchPlan):
        budget_failure = _output_budget_failure(plan_result, stage="dispatcher-output")
        if budget_failure is not None:
            raise budget_failure
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
    workers_by_role = dict(zip(WORKER_ROLES, swarm.workers, strict=True))
    task_to_role = {
        task_id: role
        for role, task_id in resolved_fleet_task_ids.items()
    }

    for loop in (1, 2):
        if resolved_fleet_plan is not None:
            try:
                observed_head = str(fleet_head_readback() if fleet_head_readback else "").strip().lower()
            except Exception as exc:
                raise SwarmExecutionError(
                    stage=f"loop-{loop}:fleet-workspace-readback",
                    family="FLEET_WORKSPACE_READBACK_FAILED",
                    error_type=type(exc).__name__,
                    next_action="READ_CURRENT_WORKSPACE_HEAD_AND_REBUILD_FLEET_PLAN",
                    retryable=False,
                ) from exc
            if observed_head != resolved_fleet_plan.base_revision:
                raise SwarmExecutionError(
                    stage=f"loop-{loop}:fleet-workspace-readback",
                    family="FLEET_PLAN_BASE_REVISION_STALE",
                    error_type="FleetWorkspaceHeadDrift",
                    next_action="REBUILD_FLEET_PLAN_FROM_FRESH_WORKSPACE_READBACK",
                    retryable=False,
                )

        async def execute_worker(
            role: str,
            worker: Any,
            *,
            fleet_lane_id: str = "",
            fleet_task_id: str = "",
        ) -> WorkerReport:
            assignment_hash = assignment_hashes.get(role, "")
            _emit_stage(
                stage_observer,
                agent_id=role,
                event_type="agent_started",
                status="RUNNING",
                summary=(
                    f"{role} started Fleet lane {fleet_lane_id} evidence analysis for double-loop pass {loop}."
                    if fleet_lane_id
                    else f"{role} started evidence analysis for double-loop pass {loop}."
                ),
                next_action="WAIT_FOR_AGENT_REPORT",
                loop=loop,
                fleet_plan_hash=resolved_fleet_plan.plan_hash if resolved_fleet_plan else None,
                fleet_lane_id=fleet_lane_id or None,
                fleet_task_id=fleet_task_id or None,
                assignment_hash=assignment_hash or None,
            )
            result = await _run_billed_stage(
                runner_class,
                worker,
                _worker_input(
                    mission=normalized_mission,
                    evidence=evidence,
                    plan=plan,
                    loop=loop,
                    role=role,
                    prior_verdict=prior_verdict,
                    fleet_plan_hash=resolved_fleet_plan.plan_hash if resolved_fleet_plan else "",
                    fleet_lane_id=fleet_lane_id,
                    fleet_task_id=fleet_task_id,
                    assignment_hash=assignment_hash,
                ),
                stage=f"loop-{loop}:worker:{role}",
                stage_billing=stage_billing,
                run_config=worker_runtimes[role].run_config,
                transport=worker_runtimes[role].transport,
            )
            report = (
                _parse_text_contract_output(result.final_output, WorkerReport, stage=f"loop-{loop}:worker:{role}", result=result)
                if text_contract
                else result.final_output
            )
            if not isinstance(report, WorkerReport):
                budget_failure = _output_budget_failure(result, stage=f"loop-{loop}:worker-output:{role}")
                if budget_failure is not None:
                    raise budget_failure
                raise SwarmExecutionError(
                    stage=f"loop-{loop}:worker-output:{role}",
                    family="AGENTS_STRUCTURED_OUTPUT_INVALID",
                    error_type=type(report).__name__,
                    next_action="RETRY_WITH_BOUNDED_SCHEMA_DIAGNOSTICS",
                    retryable=True,
                )
            report.role = role
            report.loop = loop
            _emit_stage(
                stage_observer,
                agent_id=role,
                event_type="agent_completed",
                status="BLOCKED" if report.blocked else "COMPLETED",
                summary=(
                    f"{role} produced a blocked Fleet lane evidence report for double-loop pass {loop}."
                    if report.blocked
                    else f"{role} produced a validated Fleet lane evidence report for double-loop pass {loop}."
                ),
                next_action="WAIT_FOR_FLEET_LANE_COMPLETION",
                loop=loop,
                fleet_plan_hash=resolved_fleet_plan.plan_hash if resolved_fleet_plan else None,
                fleet_lane_id=fleet_lane_id or None,
                fleet_task_id=fleet_task_id or None,
                assignment_hash=assignment_hash or None,
            )
            return report

        if resolved_fleet_plan is None:
            reports = list(await asyncio.gather(*(
                execute_worker(role, worker)
                for role, worker in workers_by_role.items()
            )))
        else:
            reports_by_role: dict[str, WorkerReport] = {}
            for lane in sorted(resolved_fleet_plan.lanes, key=lambda item: item.sequence):
                lane_roles = tuple(task_to_role[task_id] for task_id in lane.task_ids)
                with resolved_lane_guard(lane.lane_id, lane_roles):
                    # Persist RUNNING only after the controller admitted this exact
                    # lane.  A guard failure must not manufacture a reconnectable
                    # live lane from a pre-admission observability event.
                    _emit_stage(
                        stage_observer,
                        agent_id="dispatcher",
                        event_type="fleet_lane_started",
                        status="RUNNING",
                        summary=f"Fleet lane {lane.lane_id} started for double-loop pass {loop}.",
                        next_action="WAIT_FOR_FLEET_LANE_COMPLETION",
                        loop=loop,
                        fleet_plan_hash=resolved_fleet_plan.plan_hash,
                        fleet_lane_id=lane.lane_id,
                    )
                    if lane.parallel_safe and len(lane_roles) > 1:
                        lane_reports = list(await asyncio.gather(*(
                            execute_worker(
                                role,
                                workers_by_role[role],
                                fleet_lane_id=lane.lane_id,
                                fleet_task_id=resolved_fleet_task_ids[role],
                            )
                            for role in lane_roles
                        )))
                    else:
                        lane_reports = []
                        for role in lane_roles:
                            lane_reports.append(await execute_worker(
                                role,
                                workers_by_role[role],
                                fleet_lane_id=lane.lane_id,
                                fleet_task_id=resolved_fleet_task_ids[role],
                            ))
                    reports_by_role.update({report.role: report for report in lane_reports})
                    # Keep the durable terminal event within the controller's lane
                    # admission.  Releasing the guard first would leave a window
                    # where persisted evidence still says RUNNING after the worker
                    # lane has already been released.
                    _emit_stage(
                        stage_observer,
                        agent_id="dispatcher",
                        event_type="fleet_lane_completed",
                        status="COMPLETED",
                        summary=f"Fleet lane {lane.lane_id} reached terminal worker reports for double-loop pass {loop}.",
                        next_action="START_NEXT_FLEET_LANE",
                        loop=loop,
                        fleet_plan_hash=resolved_fleet_plan.plan_hash,
                        fleet_lane_id=lane.lane_id,
                    )
            reports = [reports_by_role[role] for role in WORKER_ROLES]

        _emit_stage(
            stage_observer,
            agent_id="judge",
            event_type="agent_started",
            status="VERIFYING",
            summary=f"Judge started evidence verification for double-loop checkpoint {loop}.",
            next_action="WAIT_FOR_JUDGE_VERDICT",
            loop=loop,
        )
        judge_result = await _run_billed_stage(
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
            stage_billing=stage_billing,
            run_config=main_runtime.run_config,
            transport=main_runtime.transport,
        )
        verdict = (
            _parse_text_contract_output(judge_result.final_output, JudgeVerdict, stage=f"loop-{loop}:judge", result=judge_result)
            if text_contract
            else judge_result.final_output
        )
        if not isinstance(verdict, JudgeVerdict):
            budget_failure = _output_budget_failure(judge_result, stage=f"loop-{loop}:judge-output")
            if budget_failure is not None:
                raise budget_failure
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
            verdict.mission_complete = False
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

    ok, final_status = _resolved_swarm_status(final_verdict)

    return {
        "ok": ok,
        "status": final_status,
        "manifest": manifest_payload(),
        "plan": plan.model_dump(),
        "loops": loop_payloads,
        "finalVerdict": final_verdict.model_dump(),
        "activeSpecialists": len(swarm.specialists),
        "mainModel": selected_main_model,
        "agentModel": selected_agent_model,
        "workerModels": selected_worker_models,
        "sixAgentModelShared": len(set(selected_worker_models.values())) == 1,
        "swarmTransport": main_runtime.transport,
        "repositoryToolMode": repository_tool_factory is not None,
        "fleetPlan": resolved_fleet_plan.to_dict() if resolved_fleet_plan else None,
        "fleetPlanHash": resolved_fleet_plan.plan_hash if resolved_fleet_plan else None,
        "fleetTaskIdsByRole": resolved_fleet_task_ids if resolved_fleet_plan else {},
        "approvalRequired": final_status == "READY_FOR_DRAFT_PR" and final_verdict.human_approval_required,
        "autoMerge": False,
    }
