"""OpenAI Agents SDK orchestration for the Sovereign cognitive swarm.

The model layer plans and reviews. Repository, database, deployment and merge
mutations remain in the existing bounded runtime tools and approval gates.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.metadata
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, Literal

from pydantic import BaseModel, Field

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
from .cognitive_usage_billing import AgentStageBilling
from llm_cost_policy import AGENTS_LITELLM_ALIAS, AGENTS_PROVIDER_MODEL
from llm_transport import LEGACY_LITELLM_TRANSPORT


DEFAULT_MODEL: Final[str] = AGENTS_LITELLM_ALIAS
ALLOWED_LITELLM_MODEL_ALIASES: Final[frozenset[str]] = frozenset({AGENTS_LITELLM_ALIAS})
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
_RUN_CONFIG: Any | None = None
_RUN_CONFIG_MODEL = ""
_RUN_CONFIG_ERROR = ""
_AGENTS_SDK_ERROR = ""
_LITELLM_SERVICE_KEY_FILENAME: Final[str] = "litellm_master_key.txt"
_LITELLM_SERVICE_KEY_MAX_BYTES: Final[int] = 8192
_DEFAULT_LITELLM_BASE_URL: Final[str] = "http://litellm:4000"
_SAFE_LITELLM_ALIAS: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,199}$"
)

StageObserver = Callable[[dict[str, object]], None]
RepositoryToolFactory = Callable[[str], list[Any]]


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


def _ensure_litellm_runtime_key(model: str | None = None) -> bool:
    """Build the isolated Legacy-LiteLLM compatibility RunConfig.

    Persisted product runs must supply a database-resolved direct OpenRouter or
    FreeLLM route and therefore do not enter this no-route compatibility path.
    """

    global _RUN_CONFIG, _RUN_CONFIG_MODEL, _RUN_CONFIG_ERROR
    _RUN_CONFIG = None
    _RUN_CONFIG_MODEL = ""
    _RUN_CONFIG_ERROR = ""
    selected_model = str(model or DEFAULT_MODEL).strip()
    if not _SAFE_LITELLM_ALIAS.fullmatch(selected_model):
        _RUN_CONFIG_ERROR = "LITELLM_ALIAS_INVALID"
        return False
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("OPENAI_BASE_URL", None)
    base_url = os.getenv("LITELLM_BASE_URL", _DEFAULT_LITELLM_BASE_URL).strip().rstrip("/")
    if base_url != _DEFAULT_LITELLM_BASE_URL:
        return False
    expected_root = Path(
        os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", "/opt/sovereign-owner-managed")
    ).resolve()
    configured_key_file = os.getenv(
        "LITELLM_MASTER_KEY_FILE",
        str(expected_root / _LITELLM_SERVICE_KEY_FILENAME),
    ).strip()
    candidate_path = Path(configured_key_file)
    if candidate_path.is_symlink():
        return False
    candidate = candidate_path.resolve()
    if candidate.parent != expected_root or candidate.name != _LITELLM_SERVICE_KEY_FILENAME or not candidate.is_file():
        return False
    try:
        if candidate.stat().st_mode & 0o077:
            return False
        raw = candidate.read_bytes()
    except OSError:
        return False
    if not raw or len(raw) > _LITELLM_SERVICE_KEY_MAX_BYTES:
        return False
    try:
        value = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return False
    if len(value) < 16 or "\x00" in value or "\n" in value or "\r" in value:
        return False
    try:
        provider_module = importlib.import_module("agents.models.openai_provider")
        provider_class = getattr(provider_module, "OpenAIProvider")
    except (AttributeError, ImportError):
        _RUN_CONFIG_ERROR = "SDK_OPENAI_PROVIDER_API_UNAVAILABLE"
        return False
    try:
        run_config_module = importlib.import_module("agents.run_config")
        run_config_class = getattr(run_config_module, "RunConfig")
    except (AttributeError, ImportError):
        _RUN_CONFIG_ERROR = "SDK_RUN_CONFIG_API_UNAVAILABLE"
        return False
    try:
        provider = provider_class(
            api_key=value,
            base_url=f"{base_url}/v1",
            use_responses=False,
        )
    except (TypeError, ValueError):
        _RUN_CONFIG_ERROR = "SDK_PROVIDER_CONFIGURATION_REJECTED"
        return False
    try:
        model_settings_module = importlib.import_module("agents.model_settings")
        model_settings_class = getattr(model_settings_module, "ModelSettings")
        model_settings = model_settings_class(
            max_tokens=_AGENT_OUTPUT_TOKEN_LIMIT,
            include_usage=True,
        )
    except (AttributeError, ImportError, TypeError, ValueError):
        _RUN_CONFIG_ERROR = "SDK_MODEL_SETTINGS_API_UNAVAILABLE"
        return False
    try:
        _RUN_CONFIG = run_config_class(
            model=selected_model,
            model_provider=provider,
            model_settings=model_settings,
            tracing_disabled=True,
            trace_include_sensitive_data=False,
        )
    except (TypeError, ValueError):
        _RUN_CONFIG = None
        _RUN_CONFIG_ERROR = "SDK_RUN_CONFIG_REJECTED"
        return False
    _RUN_CONFIG_MODEL = selected_model
    return True


def ensure_openai_runtime_key() -> bool:
    """Build the bounded Legacy-LiteLLM test/operator compatibility provider."""
    return _ensure_litellm_runtime_key(DEFAULT_MODEL)


def _require_litellm_run_config(model: str | None = None) -> Any:
    selected_model = str(model or DEFAULT_MODEL).strip()
    if _RUN_CONFIG is None or _RUN_CONFIG_MODEL != selected_model:
        if not _ensure_litellm_runtime_key(selected_model):
            raise RuntimeError("The Legacy-LiteLLM compatibility RunConfig is unavailable.")
    return _RUN_CONFIG


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


def classify_swarm_exception(
    exc: Exception,
    *,
    stage: str,
    transport: str = LEGACY_LITELLM_TRANSPORT,
) -> SwarmExecutionError:
    error_type = type(exc).__name__
    lowered = error_type.casefold()
    status = _exception_status(exc)
    normalized_transport = str(transport or LEGACY_LITELLM_TRANSPORT).strip().lower()
    provider_name = (
        "OPENROUTER"
        if normalized_transport == "openrouter"
        else "FREELLM"
        if normalized_transport == "freellm"
        else "LITELLM"
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
    transport: str = LEGACY_LITELLM_TRANSPORT,
) -> Any:
    reservation = (
        stage_billing.reserve(stage=stage, prompt=prompt)
        if stage_billing is not None
        else None
    )
    try:
        selected_agent_model = str(getattr(agent, "model", "") or DEFAULT_MODEL)
        effective_run_config = run_config
        if effective_run_config is None:
            effective_run_config = _require_litellm_run_config(
                None if selected_agent_model == DEFAULT_MODEL else selected_agent_model
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
    transport: str = LEGACY_LITELLM_TRANSPORT,
) -> Any:
    kwargs: dict[str, Any] = {"stage": stage}
    if run_config is not None:
        kwargs["run_config"] = run_config
    if transport != LEGACY_LITELLM_TRANSPORT:
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


class MissionIntent(BaseModel):
    mode: Literal["conversation", "read_only_analysis", "repository_execution"]
    normalized_goal: str = Field(min_length=1, max_length=2000)
    requires_online_tools: bool
    requires_repository_workspace: bool
    learning_scope: list[str] = Field(default_factory=list, max_length=12)
    confidence: float = Field(ge=0.0, le=1.0)


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
    selected_model = (model or DEFAULT_MODEL).strip()
    route_runtime: RouteRunConfig | None = None
    if route is not None:
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
    else:
        if not _SAFE_LITELLM_ALIAS.fullmatch(selected_model):
            raise ValueError("A valid Legacy-LiteLLM compatibility alias is required.")
        if stage_billing is not None and selected_model not in ALLOWED_LITELLM_MODEL_ALIASES:
            raise ValueError("A paid Legacy-LiteLLM compatibility alias is required.")
        if not _ensure_litellm_runtime_key(selected_model):
            raise SwarmExecutionError(
                stage="intent-router",
                family="LITELLM_RUNTIME_CONFIGURATION_MISSING",
                error_type="RuntimeConfigurationError",
                next_action="VERIFY_LITELLM_SERVICE_KEY",
                retryable=False,
            )
    agent_class, runner_class = _require_agents_sdk()
    router = agent_class(
        name="Sovereign Intent Router",
        model=selected_model,
        instructions=(
            "Understand the user's natural language, including typos, slang, incomplete grammar and mixed technical language. "
            "Choose repository_execution when the user asks the system to change, fix, implement, rerun, test, build, deploy, "
            "or otherwise act on the configured repository/runtime. Choose read_only_analysis when tools may inspect evidence "
            "but no mutation is requested. Choose conversation for explanation or discussion without online tools. "
            "Do not infer success, permissions, secrets or completed actions. Return only the structured intent. "
            "learning_scope may name reusable observations that should be learned only after real tool evidence exists."
        ),
        output_type=MissionIntent,
    )
    result = await _run_billed_stage(
        runner_class,
        router,
        f"User mission:\n{normalized_mission}",
        stage="intent-router",
        stage_billing=stage_billing,
        run_config=route_runtime.run_config if route_runtime else None,
        transport=route_runtime.transport if route_runtime else LEGACY_LITELLM_TRANSPORT,
    )
    intent = result.final_output
    if not isinstance(intent, MissionIntent):
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
    return intent


class FreeSingleAgentResult(BaseModel):
    mode: Literal["conversation", "read_only_analysis", "repository_execution"]
    assistant_text: str = Field(min_length=1, max_length=8000)
    findings: list[str] = Field(default_factory=list, max_length=20)
    blockers: list[str] = Field(default_factory=list, max_length=20)
    upgrade_required: bool = False
    repository_execution_performed: bool = False


async def run_free_single_agent(
    mission: str,
    *,
    evidence: str = "",
    model: str,
    route: dict[str, Any] | None = None,
    stage_observer: StageObserver | None = None,
    repository_tool_factory: RepositoryToolFactory | None = None,
) -> dict[str, Any]:
    """Run exactly one foreground agent on one DB-resolved direct FreeLLM route."""
    normalized_mission = str(mission or "").strip()
    selected_model = str(model or "").strip()
    if not normalized_mission:
        raise ValueError("mission is required")
    route_runtime: RouteRunConfig | None = None
    if route is not None:
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
    else:
        if not _SAFE_LITELLM_ALIAS.fullmatch(selected_model):
            raise ValueError("A valid Legacy-LiteLLM compatibility alias is required.")
        if not _ensure_litellm_runtime_key(selected_model):
            raise SwarmExecutionError(
                stage="free-single-agent",
                family="LITELLM_RUNTIME_CONFIGURATION_MISSING",
                error_type="RuntimeConfigurationError",
                next_action="VERIFY_LITELLM_SERVICE_KEY",
                retryable=False,
            )
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
            "When repository execution is requested but no repository tools are present, set upgrade_required=true and include WORKSPACE_TOOLS_REQUIRED. "
            "For conversation or read-only analysis, answer directly. Return only the structured result."
        ),
        tools=repository_tools,
        output_type=FreeSingleAgentResult,
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
            f"User mission:\n{normalized_mission}\n\n"
            f"Supplied read-only evidence:\n{evidence or '[no evidence supplied]'}"
        ),
        stage="free-single-agent",
        stage_billing=None,
        run_config=route_runtime.run_config if route_runtime else None,
        transport=route_runtime.transport if route_runtime else LEGACY_LITELLM_TRANSPORT,
    )
    output = result.final_output
    if not isinstance(output, FreeSingleAgentResult):
        raise SwarmExecutionError(
            stage="free-single-agent-output",
            family="AGENTS_STRUCTURED_OUTPUT_INVALID",
            error_type=type(output).__name__,
            next_action="RETRY_WITH_BOUNDED_SCHEMA_DIAGNOSTICS",
            retryable=True,
        )
    repository_requested = output.mode == "repository_execution"
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
    repository_tool_factory: RepositoryToolFactory | None = None,
    run_config: Any | None = None,
    main_run_config: Any | None = None,
    agent_run_config: Any | None = None,
) -> CognitiveSwarm:
    selected_main_model = (main_model or model or DEFAULT_MODEL).strip()
    selected_agent_model = (agent_model or selected_main_model).strip()
    if not selected_main_model or not selected_agent_model:
        raise ValueError("Main and six-agent model identifiers are required.")
    resolved_main_config = main_run_config if main_run_config is not None else run_config
    resolved_agent_config = (
        agent_run_config if agent_run_config is not None else resolved_main_config
    )
    if resolved_main_config is None and selected_main_model not in ALLOWED_LITELLM_MODEL_ALIASES:
        raise ValueError("A Sovereign LiteLLM model alias is required for the legacy main model.")
    if resolved_agent_config is None and selected_agent_model not in ALLOWED_LITELLM_MODEL_ALIASES:
        raise ValueError("A Sovereign LiteLLM model alias is required for the legacy six-agent model.")
    agent_class, _ = _require_agents_sdk()

    skill = _load_skill_instructions()
    base = _base_instructions(skill)

    specialists: list[Any] = []
    specialist_tools: list[Any] = []
    for role in SPECIALIST_ROLES[:max_active_specialists()]:
        specialist = agent_class(
            name=f"Sovereign {role.replace('_', ' ').title()} Specialist",
            model=selected_agent_model,
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
                run_config=(
                    resolved_agent_config
                    if resolved_agent_config is not None
                    else _require_litellm_run_config(selected_agent_model)
                ),
                max_turns=2,
            )
        )

    dispatcher = agent_class(
        name=AGENTS[0].name,
        model=selected_main_model,
        instructions=(
            f"{base}\n\n"
            "Create one ordered six-item plan, one item for each fixed core worker role in manifest order. "
            "Do not perform worker tasks yourself. Identify required evidence, initial blockers, and specialists needed."
        ),
        output_type=DispatchPlan,
    )

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
        workers.append(agent_class(
            name=contract.name,
            model=selected_agent_model,
            instructions=(
                f"{base}\n\n"
                f"Your fixed role is {contract.role}. Responsibility: {contract.responsibility} "
                f"Allowed zones: {', '.join(contract.allowed_zones)}. "
                "Analyze only your bounded domain. Return a WorkerReport. "
                "Use a specialist tool only for a clearly bounded package and keep orchestration ownership. "
                "Set blocked=true whenever evidence needed for a claim is absent. "
                f"{repository_instruction}"
                "You may recommend exact changes, but you may claim an action was applied only when a tool result confirms it."
            ),
            tools=worker_tools,
            output_type=WorkerReport,
        ))

    judge = agent_class(
        name=AGENTS[-1].name,
        model=selected_main_model,
        instructions=(
            f"{base}\n\n"
            "You are the final evidence controller. You never edit files and never perform a release. "
            "Reject unsupported worker claims. draft_pr_ready may be true only when all required evidence "
            "is supplied, all checks are green, no blocker remains, and the result is explicitly Draft-PR-only. "
            "For a read-only mission, mission_complete may be true when the requested analysis is satisfied, "
            "no blocker remains, and no repository change is required. Do not block on evidence for your own "
            "current response; the host records that stage afterward. The first-loop verdict can never end the "
            "workflow; a second refinement loop is mandatory. For release-hunt missions, populate hunt_outcome, "
            "error_family, next_error_family and nullfind_confirmed exactly as the bundled release-hunt skill requires."
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
    route: dict[str, Any] | None = None,
    main_route: dict[str, Any] | None = None,
    agent_route: dict[str, Any] | None = None,
    stage_observer: StageObserver | None = None,
    repository_tool_factory: RepositoryToolFactory | None = None,
    stage_billing: AgentStageBilling | None = None,
) -> dict[str, Any]:
    normalized_mission = mission.strip()
    if not normalized_mission:
        raise ValueError("mission is required")
    selected_main_model = str(model or DEFAULT_MODEL).strip()
    selected_agent_model = selected_main_model
    resolved_main_route = main_route or route
    resolved_agent_route = agent_route or resolved_main_route
    main_runtime: RouteRunConfig | None = None
    agent_runtime: RouteRunConfig | None = None
    if resolved_main_route is not None:
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
        except RouteRuntimeError as exc:
            raise SwarmExecutionError(
                stage="swarm-build",
                family=exc.family,
                error_type=type(exc).__name__,
                next_action=exc.next_action,
                retryable=False,
            ) from exc
        if main_runtime.transport != "openrouter" or agent_runtime.transport != "openrouter":
            raise ValueError("The paid swarm requires direct OpenRouter model routes.")
        selected_main_model = main_runtime.model
        selected_agent_model = agent_runtime.model
    else:
        if (
            selected_main_model not in ALLOWED_LITELLM_MODEL_ALIASES
            or selected_agent_model not in ALLOWED_LITELLM_MODEL_ALIASES
        ):
            raise ValueError("A paid Sovereign LiteLLM model alias is required for legacy no-route execution.")
        if selected_main_model == DEFAULT_MODEL:
            if not ensure_openai_runtime_key():
                return {
                    "ok": False,
                    "status": "BLOCKED",
                    "blocker": "Legacy-LiteLLM compatibility key or internal base URL is not configured.",
                    "manifest": manifest_payload(),
                }
        elif not _ensure_litellm_runtime_key(selected_main_model):
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Legacy-LiteLLM compatibility key or internal base URL is not configured.",
                "manifest": manifest_payload(),
            }

    try:
        _, runner_class = _require_agents_sdk()
        if main_runtime is None and agent_runtime is None:
            # Preserve the bounded legacy test/operator entrypoint while every
            # resolved paid execution uses the explicit direct-OpenRouter pair.
            build_kwargs: dict[str, Any] = {"model": selected_main_model}
        else:
            build_kwargs = {
                "main_model": selected_main_model,
                "agent_model": selected_agent_model,
                "main_run_config": main_runtime.run_config if main_runtime else None,
                "agent_run_config": agent_runtime.run_config if agent_runtime else None,
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
            transport=main_runtime.transport if main_runtime else LEGACY_LITELLM_TRANSPORT,
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
        run_config=main_runtime.run_config if main_runtime else None,
        transport=(
            main_runtime.transport
            if main_runtime
            else LEGACY_LITELLM_TRANSPORT
        ),
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
        async def execute_worker(role: str, worker: Any) -> WorkerReport:
            _emit_stage(
                stage_observer,
                agent_id=role,
                event_type="agent_started",
                status="RUNNING",
                summary=f"{role} started evidence analysis for parallel double-loop pass {loop}.",
                next_action="WAIT_FOR_AGENT_REPORT",
                loop=loop,
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
                ),
                stage=f"loop-{loop}:worker:{role}",
                stage_billing=stage_billing,
                run_config=agent_runtime.run_config if agent_runtime else None,
                transport=(
                    agent_runtime.transport
                    if agent_runtime
                    else LEGACY_LITELLM_TRANSPORT
                ),
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
            _emit_stage(
                stage_observer,
                agent_id=role,
                event_type="agent_completed",
                status="BLOCKED" if report.blocked else "COMPLETED",
                summary=(
                    f"{role} produced a blocked evidence report for parallel double-loop pass {loop}."
                    if report.blocked
                    else f"{role} produced a validated evidence report for parallel double-loop pass {loop}."
                ),
                next_action="WAIT_FOR_PARALLEL_WORKER_PASS",
                loop=loop,
            )
            return report

        reports = list(await asyncio.gather(*(
            execute_worker(role, worker)
            for role, worker in zip(WORKER_ROLES, swarm.workers, strict=True)
        )))

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
            run_config=main_runtime.run_config if main_runtime else None,
            transport=(
                main_runtime.transport
                if main_runtime
                else LEGACY_LITELLM_TRANSPORT
            ),
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
        "sixAgentModelShared": True,
        "repositoryToolMode": repository_tool_factory is not None,
        "approvalRequired": final_status == "READY_FOR_DRAFT_PR" and final_verdict.human_approval_required,
        "autoMerge": False,
    }
