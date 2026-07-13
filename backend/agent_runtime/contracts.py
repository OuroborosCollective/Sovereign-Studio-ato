"""Sovereign Agent Job runtime contract.

The UI never creates agent truth. This module defines the backend truth contract
for agent jobs and validates every state before a live path can use it.

The internal sovereign-local-runner is the only live executor and truth producer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import time
from typing import Literal, Sequence, Any
from urllib.parse import urlparse

AgentStatus = Literal[
    "queued",
    "provisioning",
    "running",
    "waiting-for-user",
    "validating",
    "completed",
    "failed",
    "blocked",
    "cleaned",
]

AgentExecutor = Literal["sovereign-local-runner"]

AgentEventLevel = Literal["info", "warning", "error", "success"]

AGENT_STATUSES: tuple[AgentStatus, ...] = (
    "queued",
    "provisioning",
    "running",
    "waiting-for-user",
    "validating",
    "completed",
    "failed",
    "blocked",
    "cleaned",
)

AGENT_TERMINAL_STATUSES: tuple[AgentStatus, ...] = (
    "completed",
    "failed",
    "blocked",
    "cleaned",
)

AGENT_EXECUTORS: tuple[AgentExecutor, ...] = ("sovereign-local-runner",)

_SAFE_BRANCH = re.compile(r"^[\w./-]{1,160}$")
_SAFE_RELATIVE_PATH = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))(?!.*\0)[\w .@/+~=-]+$")
_GITHUB_REPO_HOSTS = {"github.com"}
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # GitHub (classic, fine-grained, app, etc.)
    re.compile(r"((?:gh[pousr])_)[a-zA-Z0-9_]{8,100}", re.IGNORECASE),
    re.compile(r"(github_pat_)[a-zA-Z0-9_]{20,200}", re.IGNORECASE),
    # Google Cloud / Gemini API keys
    re.compile(r"(AIza)[a-zA-Z0-9_-]{26,60}", re.IGNORECASE),
    # AI provider style keys
    re.compile(r"(sk-or-v1-)[a-zA-Z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"(sk-proj-)[a-zA-Z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"(sk-ant-)[a-zA-Z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"(sk-)[a-zA-Z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"(gsk_)[a-zA-Z0-9_-]{20,}", re.IGNORECASE),
    # HuggingFace, Together AI and Pollinations AI
    re.compile(r"(hf_)[a-zA-Z0-9]{8,100}", re.IGNORECASE),
    re.compile(r"(together_)[a-zA-Z0-9]{8,100}", re.IGNORECASE),
    re.compile(r"(pollinations_)[a-zA-Z0-9]{8,100}", re.IGNORECASE),
    # Authorization header / Bearer tokens (with optional Authorization: label)
    re.compile(r"((?:Authorization:\s*)?Bearer\s+)[a-zA-Z0-9._~+/-]+=*", re.IGNORECASE),
    # Label-based credentials (supports optional quotes and common delimiters)
    re.compile(
        r'((["\']?)(?:password|passwd|token|secret|api[_-]?key|access[_-]?token|private[_-]?key)\2\s*[:=]\s*["\']?)[a-zA-Z0-9_@#$%^&*.\-~+/=]+["\']?',
        re.IGNORECASE,
    ),
)

_PLAN_ONLY_FILES = {
    "docs/sovereign_plan.md",
    "docs/agent_plan.md",
    "sovereign_plan.md",
}

_ALLOWED_EVIDENCE_PREFIXES = (
    "src/",
    "tests/",
    "backend/",
    "scripts/",
    "android/",
    "docs/",
    ".github/workflows/",
)

_ALLOWED_EVIDENCE_FILES = {
    "README.md",
    "package.json",
    "pnpm-lock.yaml",
    "tsconfig.json",
    "vite.config.ts",
}

_ALLOWED_TRANSITIONS: dict[AgentStatus, tuple[AgentStatus, ...]] = {
    "queued": ("provisioning", "running", "blocked", "failed", "cleaned"),
    "provisioning": ("running", "blocked", "failed", "cleaned"),
    "running": ("waiting-for-user", "validating", "completed", "blocked", "failed", "cleaned"),
    "waiting-for-user": ("running", "validating", "blocked", "failed", "cleaned"),
    "validating": ("completed", "blocked", "failed", "cleaned"),
    "completed": ("cleaned",),
    "failed": ("cleaned",),
    "blocked": ("cleaned",),
    "cleaned": (),
}


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _trim(value: str, max_length: int) -> str:
    text = value.strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1]}…"


def sanitize_agent_text(value: str, max_length: int = 4000) -> str:
    """Mask secret-like values and cap text before storing events/results."""
    if not value:
        return ""
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        # Preserve the primary prefix/label captured in Group 1
        text = pattern.sub(
            lambda m: (m.group(1) or "") + "[redacted]" if m.groups() else "[redacted]",
            text,
        )
    return _trim(text, max_length)


def normalize_agent_path(path: str) -> str | None:
    clean = path.strip().replace("\\", "/").removeprefix("./")
    while "//" in clean:
        clean = clean.replace("//", "/")
    if not clean or not _SAFE_RELATIVE_PATH.fullmatch(clean):
        return None
    return clean


def normalize_agent_paths(paths: Sequence[str] | None) -> tuple[str, ...]:
    normalized = [normalize_agent_path(path) for path in (paths or ())]
    return _unique([path for path in normalized if path])


def is_valid_github_repo_url(repo_url: str) -> bool:
    parsed = urlparse(repo_url.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() not in _GITHUB_REPO_HOSTS:
        return False
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return False
    owner, repo = parts[0], parts[1]
    return bool(owner and repo and re.fullmatch(r"[\w.-]+", owner) and re.fullmatch(r"[\w.-]+(?:\.git)?", repo))


def is_plan_only_file(path: str) -> bool:
    lower = path.strip().replace("\\", "/").removeprefix("./").lower()
    return lower in _PLAN_ONLY_FILES


def is_actionable_evidence_file(path: str) -> bool:
    normalized = normalize_agent_path(path)
    if not normalized:
        return False
    if is_plan_only_file(normalized):
        return False
    return normalized in _ALLOWED_EVIDENCE_FILES or normalized.startswith(_ALLOWED_EVIDENCE_PREFIXES)


@dataclass(frozen=True)
class SovereignAgentEvent:
    stage: str
    level: AgentEventLevel
    message: str
    at: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass(frozen=True)
class SovereignAgentJobRequest:
    repo_url: str
    mission: str
    executor: AgentExecutor = "sovereign-local-runner"
    branch: str = "main"
    draft_pr_only: bool = True
    allow_auto_merge: bool = False
    allowed_paths: tuple[str, ...] = ()
    forbidden_paths: tuple[str, ...] = ()
    memory_hints: tuple[str, ...] = ()
    max_runtime_ms: int | None = None
    max_workspace_bytes: int | None = None


@dataclass(frozen=True)
class SovereignAgentJobResult:
    job_id: str
    status: AgentStatus
    executor: AgentExecutor = "sovereign-local-runner"
    events: tuple[SovereignAgentEvent, ...] = ()
    changed_files: tuple[str, ...] = ()
    diff_summary: str | None = None
    test_summary: str | None = None
    draft_pr_url: str | None = None
    blocker: str | None = None
    workspace_id: str | None = None
    external_ref: str | None = None
    # Migration 004: Draft PR Preparation fields
    draft_pr_preparation: dict[str, Any] | None = None
    branch_name: str | None = None
    target_branch: str | None = None
    commit_message: str | None = None
    pr_url: str | None = None
    pr_state: str | None = None


@dataclass(frozen=True)
class SovereignAgentValidationResult:
    allowed: bool
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def normalize_agent_event(event: SovereignAgentEvent) -> SovereignAgentEvent:
    level: AgentEventLevel = event.level if event.level in ("info", "warning", "error", "success") else "warning"  # type: ignore[assignment]
    return SovereignAgentEvent(
        stage=sanitize_agent_text(event.stage, 80) or "agent",
        level=level,
        message=sanitize_agent_text(event.message, 1200) or "Agent event.",
        at=event.at if isinstance(event.at, int) and event.at > 0 else int(time.time() * 1000),
    )


def build_sovereign_agent_job_request(input_value: dict) -> SovereignAgentJobRequest:
    """Create a normalized request from an API payload without trusting the payload."""

    return SovereignAgentJobRequest(
        repo_url=str(input_value.get("repoUrl") or input_value.get("repo_url") or "").strip(),
        mission=sanitize_agent_text(str(input_value.get("mission") or input_value.get("task") or ""), 8000),
        executor=str(input_value.get("executor") or "sovereign-local-runner").strip() or "sovereign-local-runner",  # type: ignore[arg-type]
        branch=str(input_value.get("branch") or "main").strip() or "main",
        draft_pr_only=bool(input_value.get("draftPrOnly", input_value.get("draft_pr_only", True))),
        allow_auto_merge=bool(input_value.get("allowAutoMerge", input_value.get("allow_auto_merge", False))),
        allowed_paths=normalize_agent_paths(input_value.get("allowedPaths") or input_value.get("allowed_paths") or ()),
        forbidden_paths=normalize_agent_paths(input_value.get("forbiddenPaths") or input_value.get("forbidden_paths") or ()),
        memory_hints=tuple(
            sanitize_agent_text(str(hint), 1000)
            for hint in (input_value.get("memoryHints") or input_value.get("memory_hints") or ())
            if str(hint).strip()
        ),
        max_runtime_ms=input_value.get("maxRuntimeMs") or input_value.get("max_runtime_ms"),
        max_workspace_bytes=input_value.get("maxWorkspaceBytes") or input_value.get("max_workspace_bytes"),
    )


def validate_agent_job_request(request: SovereignAgentJobRequest) -> SovereignAgentValidationResult:
    blockers: list[str] = []
    warnings: list[str] = []

    if not is_valid_github_repo_url(request.repo_url):
        blockers.append("agent job requires a valid HTTPS GitHub repository URL")

    if not request.mission.strip():
        blockers.append("agent job mission is required")

    if request.mission != sanitize_agent_text(request.mission, 8000):
        blockers.append("agent job mission contains a secret-like value")

    if request.executor not in AGENT_EXECUTORS:
        blockers.append("agent executor is not supported")

    if not _SAFE_BRANCH.fullmatch(request.branch):
        blockers.append("agent job branch contains unsafe characters")

    if request.draft_pr_only is not True:
        blockers.append("agent jobs must run in Draft-PR-only mode")

    if request.allow_auto_merge:
        blockers.append("agent jobs may not auto-merge")

    if request.max_runtime_ms is not None and (not isinstance(request.max_runtime_ms, int) or request.max_runtime_ms < 30_000):
        blockers.append("agent max_runtime_ms must be at least 30000 when provided")

    if request.max_workspace_bytes is not None and (
        not isinstance(request.max_workspace_bytes, int) or request.max_workspace_bytes < 50_000_000
    ):
        blockers.append("agent max_workspace_bytes must be at least 50000000 when provided")

    if any(path is None for path in [normalize_agent_path(path) for path in request.allowed_paths]):
        blockers.append("agent allowed_paths contains an unsafe path")

    if any(path is None for path in [normalize_agent_path(path) for path in request.forbidden_paths]):
        blockers.append("agent forbidden_paths contains an unsafe path")

    return SovereignAgentValidationResult(
        allowed=not blockers,
        blockers=_unique(blockers),
        warnings=_unique(warnings),
    )


def can_transition_agent_status(current: AgentStatus, target: AgentStatus) -> bool:
    return target in _ALLOWED_TRANSITIONS.get(current, ())


def result_has_evidence(result: SovereignAgentJobResult) -> bool:
    if result.blocker and result.blocker.strip():
        return True
    if result.draft_pr_url and result.draft_pr_url.startswith("https://github.com/"):
        return True
    if result.diff_summary and result.diff_summary.strip():
        return True
    if result.test_summary and result.test_summary.strip():
        return True
    return any(is_actionable_evidence_file(path) for path in result.changed_files)


def validate_agent_job_result(result: SovereignAgentJobResult) -> SovereignAgentValidationResult:
    blockers: list[str] = []

    if not result.job_id.strip():
        blockers.append("agent result requires a job id")

    if result.status not in AGENT_STATUSES:
        blockers.append("agent result status is not supported")

    if result.executor not in AGENT_EXECUTORS:
        blockers.append("agent result executor is not supported")

    if result.status == "completed" and not result_has_evidence(result):
        blockers.append("completed agent result requires runtime evidence")

    if result.status == "completed" and result.changed_files and all(is_plan_only_file(path) for path in result.changed_files):
        blockers.append("plan-only agent result may not complete")

    if result.status in ("failed", "blocked") and not (result.blocker and result.blocker.strip()):
        blockers.append("failed or blocked agent result requires a blocker reason")

    if result.draft_pr_url and not result.draft_pr_url.startswith("https://github.com/"):
        blockers.append("draft PR URL must be a GitHub URL")

    return SovereignAgentValidationResult(allowed=not blockers, blockers=_unique(blockers), warnings=())


def normalize_agent_job_result(result: SovereignAgentJobResult) -> SovereignAgentJobResult:
    normalized = SovereignAgentJobResult(
        job_id=sanitize_agent_text(result.job_id, 120) or "agent-job-unknown",
        status=result.status if result.status in AGENT_STATUSES else "blocked",  # type: ignore[arg-type]
        executor=result.executor if result.executor in AGENT_EXECUTORS else "sovereign-local-runner",  # type: ignore[arg-type]
        events=tuple(normalize_agent_event(event) for event in result.events[-200:]),
        changed_files=normalize_agent_paths(result.changed_files),
        diff_summary=sanitize_agent_text(result.diff_summary, 2000) if result.diff_summary else None,
        test_summary=sanitize_agent_text(result.test_summary, 2000) if result.test_summary else None,
        draft_pr_url=result.draft_pr_url.strip() if result.draft_pr_url and result.draft_pr_url.startswith("https://github.com/") else None,
        blocker=sanitize_agent_text(result.blocker, 1200) if result.blocker else None,
        workspace_id=sanitize_agent_text(result.workspace_id, 120) if result.workspace_id else None,
        external_ref=sanitize_agent_text(result.external_ref, 120) if result.external_ref else None,
    )

    validation = validate_agent_job_result(normalized)
    if validation.allowed:
        return normalized

    return SovereignAgentJobResult(
        job_id=normalized.job_id,
        status="blocked",
        executor=normalized.executor,
        events=normalized.events,
        changed_files=normalized.changed_files,
        diff_summary=normalized.diff_summary,
        test_summary=normalized.test_summary,
        draft_pr_url=normalized.draft_pr_url,
        blocker="; ".join(validation.blockers),
        workspace_id=normalized.workspace_id,
        external_ref=normalized.external_ref,
    )


def build_blocked_agent_result(job_id: str, blocker: str, executor: AgentExecutor = "sovereign-local-runner") -> SovereignAgentJobResult:
    return normalize_agent_job_result(
        SovereignAgentJobResult(
            job_id=job_id,
            status="blocked",
            executor=executor,
            events=(
                SovereignAgentEvent(
                    stage="agent_blocked",
                    level="warning",
                    message=blocker,
                ),
            ),
            blocker=blocker,
        )
    )
