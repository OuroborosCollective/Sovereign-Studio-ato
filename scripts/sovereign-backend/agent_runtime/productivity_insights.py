"""Evidence-bound mission, diff and changelog insights.

Language tasks reuse the persisted OpenRouter/FreeLLM resolution used by the
code reviewer. Deterministic fallbacks are labelled and never become execution,
test, merge, deployment or runtime evidence.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from llm_execution_resolver import ExecutionResolutionError, load_execution_resolution
from llm_transport import OPENROUTER_TRANSPORT, route_provider_model, route_transport

from .auto_code_review import _candidate_routes, _redact_secret_shaped_text, _route_id, _safe_failure
from .cognitive_llm_transport import RouteRuntimeError, build_route_run_config
from .cognitive_swarm_agents import _require_agents_sdk, _run_billed_stage
from .cognitive_usage_billing import AgentBillingError, AgentStageBilling

ConnectionFactory = Callable[[], Any]


@dataclass(frozen=True)
class MissionValidationResult:
    score: int
    specific_enough: bool
    questions: tuple[str, ...]
    evidence: tuple[str, ...]
    status: str
    model_used: str = ""
    resolved_transport: str = ""
    route_id: str = ""
    fallback_used: bool = False
    attempted_route_count: int = 0
    error: str = ""


@dataclass(frozen=True)
class DiffNarrationResult:
    status: str
    narratives: tuple[tuple[str, str], ...]
    diff_text: str
    model_used: str = ""
    resolved_transport: str = ""
    route_id: str = ""
    fallback_used: bool = False
    attempted_route_count: int = 0
    error: str = ""


@dataclass(frozen=True)
class ChangelogResult:
    status: str
    markdown: str
    commit_count: int
    source: str
    model_used: str = ""
    resolved_transport: str = ""
    route_id: str = ""
    fallback_used: bool = False
    attempted_route_count: int = 0
    error: str = ""


@dataclass(frozen=True)
class _ModelOutput:
    ok: bool
    text: str = ""
    model_used: str = ""
    resolved_transport: str = ""
    route_id: str = ""
    fallback_used: bool = False
    attempted_route_count: int = 0
    error: str = ""


_ACTION = re.compile(r"\b(add|build|change|create|delete|fix|implement|integrate|migrate|refactor|remove|repair|replace|test|update|analysiere|baue|behebe|ändere|erstelle|füge|implementiere|integriere|lösche|migriere|prüfe|repariere|teste)\b", re.I)
_TARGET = re.compile(r"(?:\b(?:api|backend|branch|button|component|database|datei|endpoint|feature|frontend|funktion|modul|page|repository|route|runtime|screen|service|test|ui|workflow)\b|[\w.-]+/[\w./-]+|[\w.-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|kt|sql|yml|yaml))", re.I)
_OUTCOME = re.compile(r"\b(acceptance|akzeptanz|block|build|ci|evidence|ergebnis|erwartet|fail|gate|grün|output|pass|result|test|validier|verifizier|wenn)\b", re.I)
_CONSTRAINT = re.compile(r"\b(authoritative|deterministic|draft|fail[- ]?closed|kein|keine|must|nicht|only|ohne|shall|soll|truth|wahrheit)\b", re.I)
_BROAD = re.compile(r"\b(all|alles|entire|ganze[nmrs]?|komplett|whole)\b", re.I)


async def _run_route(route: dict[str, Any], system: str, prompt: str, stage: str, billing: AgentStageBilling | None, token_limit: int) -> str:
    runtime = build_route_run_config(route, output_token_limit=token_limit)
    agent_class, runner_class = _require_agents_sdk()
    agent = agent_class(name=f"Sovereign {stage}", model=runtime.model, instructions=system)
    result = await _run_billed_stage(
        runner_class,
        agent,
        prompt,
        stage=stage,
        stage_billing=billing,
        run_config=runtime.run_config,
        transport=runtime.transport,
    )
    return str(getattr(result, "final_output", "") or "")


def _model_output(*, get_connection: ConnectionFactory, user_id: str, system: str, prompt: str, stage: str, job_id: str, token_limit: int) -> _ModelOutput:
    if not str(user_id or "").strip():
        return _ModelOutput(ok=False, error="AUTHENTICATED_USER_REQUIRED")
    try:
        resolution = load_execution_resolution(get_connection, user_id=user_id, requested_mode="auto")
    except (ExecutionResolutionError, LookupError) as exc:
        return _ModelOutput(ok=False, error=_safe_failure(exc))
    except Exception as exc:
        return _ModelOutput(ok=False, error=_safe_failure(exc))
    if resolution is None:
        return _ModelOutput(ok=False, error="NO_VERIFIED_INSIGHT_ROUTE_READY")

    failures: list[str] = []
    candidates = _candidate_routes(resolution)
    for attempt, route in enumerate(candidates, start=1):
        transport = route_transport(route)
        model = route_provider_model(route)
        billing = None
        try:
            if transport == OPENROUTER_TRANSPORT:
                billing = AgentStageBilling(
                    get_connection=get_connection,
                    user_id=user_id,
                    run_id=f"{stage}-{job_id or uuid.uuid4().hex}",
                    trace_id=f"{stage}-{uuid.uuid4().hex}",
                    main_route=route,
                    agent_route=route,
                    requested_mode=resolution.requested_mode,
                )
            text = asyncio.run(_run_route(route, system, prompt, stage, billing, token_limit))
        except (AgentBillingError, RouteRuntimeError, RuntimeError, ValueError) as exc:
            failures.append(f"{transport}:{_safe_failure(exc)}")
            continue
        except Exception as exc:
            failures.append(f"{transport}:{_safe_failure(exc)}")
            continue
        if text.strip():
            return _ModelOutput(
                ok=True,
                text=text,
                model_used=model,
                resolved_transport=transport,
                route_id=_route_id(route),
                fallback_used=attempt > 1,
                attempted_route_count=attempt,
            )
        failures.append(f"{transport}:EMPTY_OUTPUT")
    return _ModelOutput(
        ok=False,
        attempted_route_count=len(candidates),
        error="; ".join(failures)[:800] or "INSIGHT_ROUTE_EXHAUSTED",
    )


def _json(value: str) -> Any | None:
    clean = str(value or "").strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        for pattern in (r"\{.*\}", r"\[.*\]"):
            match = re.search(pattern, clean, re.S)
            if not match:
                continue
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return None


def deterministic_mission_validation(mission: str) -> MissionValidationResult:
    clean = re.sub(r"\s+", " ", str(mission or "")).strip()
    score = 0
    evidence: list[str] = []
    questions: list[str] = []
    if len(clean) >= 24:
        score += 20; evidence.append("minimum_detail")
    else:
        questions.append("Was soll konkret geändert werden?")
    if _ACTION.search(clean):
        score += 25; evidence.append("action")
    else:
        questions.append("Welche konkrete Aktion soll laufen?")
    if _TARGET.search(clean):
        score += 25; evidence.append("target")
    else:
        questions.append("Welche Datei oder Systemfläche ist betroffen?")
    if _OUTCOME.search(clean):
        score += 20; evidence.append("verification")
    else:
        questions.append("Woran ist der Erfolg belegbar?")
    if _CONSTRAINT.search(clean):
        score += 10; evidence.append("constraint")
    if _BROAD.search(clean) and len(clean) < 120:
        score -= 20; evidence.append("broad_scope_penalty")
    score = max(0, min(100, score))
    return MissionValidationResult(score, score >= 40, tuple(questions[:3]), tuple(evidence), "deterministic_fallback")


def validate_mission(mission: str, *, get_connection: ConnectionFactory, user_id: str) -> MissionValidationResult:
    baseline = deterministic_mission_validation(mission)
    clean = _redact_secret_shaped_text(str(mission or "").strip())[:4000]
    if not clean:
        return baseline
    output = _model_output(
        get_connection=get_connection,
        user_id=user_id,
        system=("You are a mission pre-flight linter, not an executor. Return ONLY JSON with score (0-100), questions (up to three strings), and evidence (strings). Judge concrete action, target, verifiable outcome and constraints. Broad unbounded requests score below 40. Never claim execution or success."),
        prompt=f"Mission:\n{clean}",
        stage="mission-preflight",
        job_id="mission",
        token_limit=384,
    )
    parsed = _json(output.text) if output.ok else None
    if not isinstance(parsed, dict):
        return MissionValidationResult(
            baseline.score, baseline.specific_enough, baseline.questions, baseline.evidence,
            "deterministic_fallback", attempted_route_count=output.attempted_route_count,
            error=output.error or "INVALID_MISSION_VALIDATION_OUTPUT",
        )
    try:
        score = max(0, min(100, int(parsed.get("score"))))
    except (TypeError, ValueError):
        score = baseline.score
    raw_questions = parsed.get("questions") if isinstance(parsed.get("questions"), list) else list(baseline.questions)
    raw_evidence = parsed.get("evidence") if isinstance(parsed.get("evidence"), list) else list(baseline.evidence)
    questions = tuple(_redact_secret_shaped_text(str(item)).strip()[:240] for item in raw_questions[:3] if str(item).strip())
    evidence = tuple(_redact_secret_shaped_text(str(item)).strip()[:160] for item in raw_evidence[:8] if str(item).strip())
    return MissionValidationResult(
        score, score >= 40, questions, evidence, "ready", output.model_used,
        output.resolved_transport, output.route_id, output.fallback_used,
        output.attempted_route_count,
    )


def narrate_diff(diff_text: str, changed_files: tuple[str, ...], *, get_connection: ConnectionFactory, user_id: str, job_id: str) -> DiffNarrationResult:
    clean_diff = str(diff_text or "").strip()
    files = tuple(dict.fromkeys(path.strip() for path in changed_files if path.strip()))
    if not clean_diff or not files:
        return DiffNarrationResult("blocked_unavailable", (), clean_diff, error="REAL_DIFF_AND_CHANGED_FILES_REQUIRED")
    prompt = (
        "Changed files:\n" + _redact_secret_shaped_text("\n".join(f"- {path}" for path in files[:80]))
        + "\n\nReal git diff:\n```diff\n" + _redact_secret_shaped_text(clean_diff[:16000]) + "\n```"
    )
    output = _model_output(
        get_connection=get_connection,
        user_id=user_id,
        system=("Translate the supplied real git diff into business-readable one-sentence file narratives. Return ONLY a JSON array with path and narration. Include every changed file exactly once. Never claim tests, deployment, merge or runtime success."),
        prompt=prompt,
        stage="semantic-diff-narrator",
        job_id=job_id,
        token_limit=2048,
    )
    parsed = _json(output.text) if output.ok else None
    if not isinstance(parsed, list):
        return DiffNarrationResult(
            "blocked_unavailable", (), clean_diff, attempted_route_count=output.attempted_route_count,
            error=output.error or "INVALID_DIFF_NARRATION_OUTPUT",
        )
    allowed = set(files)
    by_path: dict[str, str] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        narration = _redact_secret_shaped_text(str(item.get("narration") or "")).strip()[:500]
        if path in allowed and narration:
            by_path[path] = narration
    missing = [path for path in files if path not in by_path]
    status = "ready" if not missing else "blocked_unavailable"
    return DiffNarrationResult(
        status, tuple((path, by_path[path]) for path in files if path in by_path), clean_diff,
        output.model_used, output.resolved_transport, output.route_id, output.fallback_used,
        output.attempted_route_count,
        "" if not missing else f"MISSING_NARRATION_FOR_{len(missing)}_FILES",
    )


def _subjects(log_text: str) -> list[str]:
    result: list[str] = []
    for line in str(log_text or "").splitlines():
        clean = line.strip()
        if not clean:
            continue
        parts = clean.split(maxsplit=1)
        result.append(parts[1] if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{7,40}", parts[0]) else clean)
    return result


def _deterministic_changelog(log_text: str, diff_text: str) -> tuple[str, int]:
    groups: dict[str, list[str]] = {"Added": [], "Changed": [], "Fixed": [], "Removed": []}
    subjects = _subjects(log_text)
    for subject in subjects:
        lower = subject.lower()
        clean = re.sub(r"^(feat|fix|chore|refactor|docs|test|build|ci|perf)(\([^)]*\))?!?:\s*", "", subject, flags=re.I).strip()
        if not clean:
            continue
        group = "Added" if lower.startswith(("feat", "add", "create")) else "Fixed" if lower.startswith(("fix", "repair", "bug")) else "Removed" if lower.startswith(("remove", "delete", "drop")) else "Changed"
        if clean not in groups[group]:
            groups[group].append(clean)
    if not subjects and str(diff_text or "").strip():
        groups["Changed"].append("Workspace changes represented by the current real git diff")
    lines = ["## [Unreleased]", ""]
    for group in ("Added", "Changed", "Fixed", "Removed"):
        if groups[group]:
            lines.extend([f"### {group}", *[f"- {item}" for item in groups[group]], ""])
    return "\n".join(lines).rstrip() + "\n", len(subjects)


def generate_changelog(log_text: str, diff_text: str, *, get_connection: ConnectionFactory, user_id: str, job_id: str) -> ChangelogResult:
    deterministic, commit_count = _deterministic_changelog(log_text, diff_text)
    evidence = _redact_secret_shaped_text(f"Real git log:\n{str(log_text or '')[:8000]}\n\nReal git diff:\n{str(diff_text or '')[:8000]}")
    if not evidence.strip():
        return ChangelogResult("blocked_unavailable", "", 0, "none", error="GIT_HISTORY_AND_DIFF_UNAVAILABLE")
    output = _model_output(
        get_connection=get_connection,
        user_id=user_id,
        system=("Group real commit subjects and diff evidence into Keep a Changelog categories. Return ONLY JSON with arrays Added, Changed, Fixed, Removed. Preserve supported facts only. Never claim deployment, publication, tests or runtime success."),
        prompt=evidence,
        stage="changelog-generator",
        job_id=job_id,
        token_limit=1536,
    )
    parsed = _json(output.text) if output.ok else None
    if not isinstance(parsed, dict):
        return ChangelogResult(
            "deterministic_fallback", deterministic, commit_count, "real_git_deterministic",
            attempted_route_count=output.attempted_route_count,
            error=output.error or "INVALID_CHANGELOG_OUTPUT",
        )
    lines = ["## [Unreleased]", ""]
    accepted = 0
    for group in ("Added", "Changed", "Fixed", "Removed"):
        values = parsed.get(group)
        if not isinstance(values, list):
            continue
        bullets = [_redact_secret_shaped_text(str(value)).strip()[:500] for value in values[:30] if str(value).strip()]
        if bullets:
            accepted += len(bullets)
            lines.extend([f"### {group}", *[f"- {value}" for value in bullets], ""])
    if not accepted:
        return ChangelogResult("deterministic_fallback", deterministic, commit_count, "real_git_deterministic", attempted_route_count=output.attempted_route_count, error="EMPTY_CHANGELOG_GROUPS")
    return ChangelogResult(
        "ready", "\n".join(lines).rstrip() + "\n", commit_count, "real_git_model_grouped",
        output.model_used, output.resolved_transport, output.route_id, output.fallback_used,
        output.attempted_route_count,
    )


def mission_validation_signal(result: MissionValidationResult) -> dict[str, Any]:
    return {
        "runtime": "mission-preflight", "status": result.status, "score": result.score,
        "specificEnough": result.specific_enough, "questions": list(result.questions),
        "evidence": list(result.evidence), "modelUsed": result.model_used,
        "resolvedTransport": result.resolved_transport, "routeId": result.route_id,
        "fallbackUsed": result.fallback_used, "attemptedRouteCount": result.attempted_route_count,
        "error": result.error, "secretValuesReturned": False,
    }


def diff_narration_signal(result: DiffNarrationResult) -> dict[str, Any]:
    return {
        "runtime": "semantic-diff-narrator", "status": result.status,
        "diffText": result.diff_text,
        "narratives": [{"path": path, "narration": narration} for path, narration in result.narratives],
        "modelUsed": result.model_used, "resolvedTransport": result.resolved_transport,
        "routeId": result.route_id, "fallbackUsed": result.fallback_used,
        "attemptedRouteCount": result.attempted_route_count, "error": result.error,
        "secretValuesReturned": False,
    }


def changelog_signal(result: ChangelogResult) -> dict[str, Any]:
    return {
        "runtime": "changelog-generator", "status": result.status,
        "markdown": result.markdown, "commitCount": result.commit_count,
        "source": result.source, "modelUsed": result.model_used,
        "resolvedTransport": result.resolved_transport, "routeId": result.route_id,
        "fallbackUsed": result.fallback_used, "attemptedRouteCount": result.attempted_route_count,
        "error": result.error, "secretValuesReturned": False,
    }
