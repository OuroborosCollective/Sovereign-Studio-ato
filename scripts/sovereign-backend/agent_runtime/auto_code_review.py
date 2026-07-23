"""Transport-neutral automatic code review for a real Sovereign workspace diff.

The review uses the account's persisted execution resolution. Paid users run on
an active OpenRouter route with the existing credit settlement path. Free users
run on the direct FreeLLM revolver and may advance across independent quota
scopes. A missing route, provider failure, invalid model output, or empty diff is
always a blocker; it is never converted into synthetic success.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from llm_execution_resolver import ExecutionResolutionError, load_execution_resolution
from llm_transport import OPENROUTER_TRANSPORT, route_provider_model, route_transport

from .cognitive_llm_transport import RouteRuntimeError, build_route_run_config
from .cognitive_swarm_agents import _require_agents_sdk, _run_billed_stage
from .cognitive_usage_billing import AgentBillingError, AgentStageBilling

ConnectionFactory = Callable[[], Any]
ReviewSeverity = Literal["HIGH", "MEDIUM", "LOW"]
ReviewCategory = Literal["security", "breaking_change", "quality", "style"]
ReviewDecision = Literal["passed", "blocked_high", "blocked_unavailable"]


@dataclass(frozen=True)
class AutoCodeReviewInput:
    diff_text: str
    changed_files: tuple[str, ...] = field(default_factory=tuple)
    job_id: str = ""
    mission: str = ""
    max_diff_chars: int = 12_000


@dataclass(frozen=True)
class AutoCodeReviewFinding:
    severity: ReviewSeverity
    category: ReviewCategory
    file: str
    line_hint: str
    description: str


@dataclass(frozen=True)
class AutoCodeReviewResult:
    decision: ReviewDecision
    passed: bool
    summary: str
    findings: tuple[AutoCodeReviewFinding, ...]
    high_count: int
    medium_count: int
    low_count: int
    model_used: str
    resolved_transport: str = ""
    route_id: str = ""
    fallback_used: bool = False
    attempted_route_count: int = 0
    error: str = ""


_REVIEW_SYSTEM_PROMPT = """You are a strict code reviewer. Review only the supplied real git diff.
Return ONLY one JSON array. Each item must contain exactly: severity (HIGH|MEDIUM|LOW), category (security|breaking_change|quality|style), file, line_hint, description.
HIGH is reserved for exploitable security flaws, data loss, secret exposure, authorization bypass, unsafe command execution, or a clear release-breaking defect.
MEDIUM is a probable functional defect or breaking public contract. LOW is a bounded maintainability or style issue.
If no supported finding exists, return []. Never claim that tests ran and never invent files or lines."""

_SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"sk-(?:or-v1-|proj-|ant-)?[A-Za-z0-9_-]{16,}", re.IGNORECASE),
    re.compile(r"Authorization:\s*Bearer\s+[^\s]+", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
    re.compile(r"(?:token|password|secret|api[_-]?key)\s*[=:]\s*[^\s]+", re.IGNORECASE),
)


def _redact_secret_shaped_text(value: str) -> str:
    redacted = str(value or "")
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def _truncate_diff(diff_text: str, max_chars: int) -> str:
    bounded = max(256, int(max_chars))
    if len(diff_text) <= bounded:
        return diff_text
    half = bounded // 2
    return diff_text[:half] + "\n\n[... diff truncated for review ...]\n\n" + diff_text[-half:]


def _build_review_prompt(input_value: AutoCodeReviewInput) -> str:
    diff = _redact_secret_shaped_text(
        _truncate_diff(input_value.diff_text, input_value.max_diff_chars)
    )
    files_note = (
        f"Changed files: {_redact_secret_shaped_text(', '.join(input_value.changed_files[:40]))}\n"
        if input_value.changed_files
        else "Changed files: derived from the diff.\n"
    )
    mission_note = (
        f"Mission context: {_redact_secret_shaped_text(input_value.mission[:500])}\n"
        if input_value.mission
        else ""
    )
    return f"{files_note}{mission_note}Actual git diff:\n```diff\n{diff}\n```"


def _extract_findings_payload(raw_text: str) -> tuple[list[Any] | None, bool]:
    clean = str(raw_text or "").strip()
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", clean, re.DOTALL)
        if not match:
            return None, False
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None, False
    return (parsed, True) if isinstance(parsed, list) else (None, False)


def _parse_findings(raw_json: str) -> tuple[AutoCodeReviewFinding, ...]:
    items, valid = _extract_findings_payload(raw_json)
    if not valid or items is None:
        return ()
    findings: list[AutoCodeReviewFinding] = []
    for item in items[:50]:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "LOW")).upper()
        if severity not in ("HIGH", "MEDIUM", "LOW"):
            severity = "LOW"
        category = str(item.get("category", "quality")).lower()
        if category not in ("security", "breaking_change", "quality", "style"):
            category = "quality"
        description = _redact_secret_shaped_text(
            str(item.get("description", "")).strip()
        )[:500]
        if not description:
            continue
        findings.append(AutoCodeReviewFinding(
            severity=severity,
            category=category,
            file=_redact_secret_shaped_text(
                str(item.get("file", "general")).strip()
            )[:200] or "general",
            line_hint=_redact_secret_shaped_text(
                str(item.get("line_hint", "")).strip()
            )[:200],
            description=description,
        ))
    return tuple(findings)


def _count_by_severity(findings: tuple[AutoCodeReviewFinding, ...]) -> tuple[int, int, int]:
    return (
        sum(1 for finding in findings if finding.severity == "HIGH"),
        sum(1 for finding in findings if finding.severity == "MEDIUM"),
        sum(1 for finding in findings if finding.severity == "LOW"),
    )


def _route_id(route: dict[str, Any]) -> str:
    return str(route.get("id") or "").strip()


def _candidate_routes(resolution: Any) -> tuple[dict[str, Any], ...]:
    """Use one paid primary, then every verified free revolver candidate."""
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    primary = dict(resolution.primary_route)
    for route in (primary, *resolution.candidate_routes):
        candidate = dict(route)
        identifier = _route_id(candidate)
        if not identifier or identifier in seen:
            continue
        transport = route_transport(candidate)
        if transport == OPENROUTER_TRANSPORT and ordered:
            continue
        seen.add(identifier)
        ordered.append(candidate)
    return tuple(ordered)


def _safe_failure(exc: BaseException) -> str:
    family = str(getattr(exc, "family", "") or "").strip()
    return (family or type(exc).__name__)[:160]


async def _run_review_route(
    *,
    route: dict[str, Any],
    prompt: str,
    stage_billing: AgentStageBilling | None,
) -> str:
    runtime = build_route_run_config(route, output_token_limit=2_048)
    agent_class, runner_class = _require_agents_sdk()
    reviewer = agent_class(
        name="Sovereign Auto Code Reviewer",
        model=runtime.model,
        instructions=_REVIEW_SYSTEM_PROMPT,
    )
    result = await _run_billed_stage(
        runner_class,
        reviewer,
        prompt,
        stage="auto-code-review",
        stage_billing=stage_billing,
        run_config=runtime.run_config,
        transport=runtime.transport,
    )
    return str(getattr(result, "final_output", "") or "")


def auto_code_review(
    input_value: AutoCodeReviewInput,
    *,
    get_connection: ConnectionFactory,
    user_id: str,
    requested_mode: str = "auto",
) -> AutoCodeReviewResult:
    """Review the actual diff over the user's resolved OpenRouter/FreeLLM path."""
    if not input_value.diff_text.strip():
        return AutoCodeReviewResult(
            decision="blocked_unavailable",
            passed=False,
            summary="Auto code review blocked: no real git diff was available.",
            findings=(),
            high_count=0,
            medium_count=0,
            low_count=0,
            model_used="",
            error="diff_text is empty",
        )
    if not str(user_id or "").strip():
        return AutoCodeReviewResult(
            decision="blocked_unavailable",
            passed=False,
            summary="Auto code review blocked: authenticated user identity is missing.",
            findings=(),
            high_count=0,
            medium_count=0,
            low_count=0,
            model_used="",
            error="authenticated user id is required",
        )

    try:
        resolution = load_execution_resolution(
            get_connection,
            user_id=user_id,
            requested_mode=requested_mode,
        )
    except (ExecutionResolutionError, LookupError) as exc:
        return AutoCodeReviewResult(
            decision="blocked_unavailable",
            passed=False,
            summary="Auto code review blocked: no eligible model route could be resolved.",
            findings=(),
            high_count=0,
            medium_count=0,
            low_count=0,
            model_used="",
            error=_safe_failure(exc),
        )
    except Exception as exc:
        return AutoCodeReviewResult(
            decision="blocked_unavailable",
            passed=False,
            summary="Auto code review route resolution is unavailable.",
            findings=(),
            high_count=0,
            medium_count=0,
            low_count=0,
            model_used="",
            error=_safe_failure(exc),
        )

    if resolution is None:
        return AutoCodeReviewResult(
            decision="blocked_unavailable",
            passed=False,
            summary="Auto code review blocked: neither OpenRouter nor a direct FreeLLM route is ready.",
            findings=(),
            high_count=0,
            medium_count=0,
            low_count=0,
            model_used="",
            error="NO_VERIFIED_REVIEW_ROUTE_READY",
        )

    prompt = _build_review_prompt(input_value)
    failures: list[str] = []
    candidates = _candidate_routes(resolution)
    for attempt, route in enumerate(candidates, start=1):
        transport = route_transport(route)
        model = route_provider_model(route)
        billing: AgentStageBilling | None = None
        try:
            if transport == OPENROUTER_TRANSPORT:
                billing = AgentStageBilling(
                    get_connection=get_connection,
                    user_id=user_id,
                    run_id=f"review-{input_value.job_id or uuid.uuid4().hex}",
                    trace_id=f"review-{uuid.uuid4().hex}",
                    main_route=route,
                    agent_route=route,
                    requested_mode=resolution.requested_mode,
                )
            raw_output = asyncio.run(_run_review_route(
                route=route,
                prompt=prompt,
                stage_billing=billing,
            ))
        except (AgentBillingError, RouteRuntimeError, RuntimeError, ValueError) as exc:
            failures.append(f"{transport}:{_safe_failure(exc)}")
            continue
        except Exception as exc:
            failures.append(f"{transport}:{_safe_failure(exc)}")
            continue

        payload, valid_payload = _extract_findings_payload(raw_output)
        if not valid_payload or payload is None:
            failures.append(f"{transport}:INVALID_REVIEW_OUTPUT")
            continue
        findings = _parse_findings(raw_output)
        high, medium, low = _count_by_severity(findings)
        if high:
            decision: ReviewDecision = "blocked_high"
            passed = False
            summary = f"Code review blocked: {high} HIGH-severity finding(s) must be resolved before Draft PR preparation."
        else:
            decision = "passed"
            passed = True
            summary = (
                f"Code review passed with {medium} MEDIUM and {low} LOW finding(s); no HIGH finding was returned."
                if findings
                else "Code review passed: the resolved model returned no supported finding for the real diff."
            )
        return AutoCodeReviewResult(
            decision=decision,
            passed=passed,
            summary=summary,
            findings=findings,
            high_count=high,
            medium_count=medium,
            low_count=low,
            model_used=model,
            resolved_transport=transport,
            route_id=_route_id(route),
            fallback_used=attempt > 1,
            attempted_route_count=attempt,
        )

    return AutoCodeReviewResult(
        decision="blocked_unavailable",
        passed=False,
        summary="Auto code review blocked: every eligible OpenRouter/FreeLLM review route failed or returned invalid evidence.",
        findings=(),
        high_count=0,
        medium_count=0,
        low_count=0,
        model_used="",
        attempted_route_count=len(candidates),
        error="; ".join(failures)[:800] or "REVIEW_ROUTE_EXHAUSTED",
    )


def auto_code_review_signal(result: AutoCodeReviewResult) -> dict[str, Any]:
    return {
        "runtime": "auto-code-review",
        "decision": result.decision,
        "passed": result.passed,
        "summary": result.summary,
        "highCount": result.high_count,
        "mediumCount": result.medium_count,
        "lowCount": result.low_count,
        "modelUsed": result.model_used,
        "resolvedTransport": result.resolved_transport,
        "routeId": result.route_id,
        "fallbackUsed": result.fallback_used,
        "attemptedRouteCount": result.attempted_route_count,
        "error": result.error,
        "findings": [
            {
                "severity": finding.severity,
                "category": finding.category,
                "file": finding.file,
                "lineHint": finding.line_hint,
                "description": finding.description,
            }
            for finding in result.findings
        ],
        "secretValuesReturned": False,
    }
