"""Draft PR preparation gate for Sovereign Agent Runtime.

This module does not create pull requests. It prepares a verified Draft-PR-ready
runtime state only after evidence gates allow it. Auto-merge remains forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from .contracts import normalize_agent_paths, sanitize_agent_text
from .evidence_gate import EvidenceGateInput, EvidenceGateResult, evaluate_agent_evidence
from .job_store import StoredSovereignAgentJob

DraftPrDecision = Literal["ready", "blocked"]

_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]{0,119}$")
_SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"Authorization:\s*(?:Bearer\s+)?[^\s\n]+", re.IGNORECASE),
    re.compile(r"(?:token|password|secret|api[_-]?key)\s*[=:]\s*[^\s\n]+", re.IGNORECASE),
)


@dataclass(frozen=True)
class DraftPrPreparationInput:
    job_id: str
    repo_url: str
    base_branch: str
    mission: str
    changed_files: tuple[str, ...]
    diff_summary: str | None
    test_summary: str | None
    evidence_gate: EvidenceGateResult
    head_branch: str | None = None
    title: str | None = None
    body: str | None = None
    draft: bool = True
    allow_auto_merge: bool = False


@dataclass(frozen=True)
class DraftPrPreparationResult:
    allowed: bool
    decision: DraftPrDecision
    summary: str
    head_branch: str | None = None
    base_branch: str | None = None
    title: str | None = None
    body: str | None = None
    changed_files: tuple[str, ...] = ()
    next_action: str | None = None
    can_create_draft_pr: bool = False
    can_learn_pattern: bool = False
    blockers: tuple[str, ...] = ()
    predictive_signal: str = "agent_draft_pr_prepare_blocked"


def draft_pr_input_from_job(job: StoredSovereignAgentJob, *, head_branch: str | None = None) -> DraftPrPreparationInput:
    evidence = evaluate_agent_evidence(EvidenceGateInput(
        changed_files=job.changed_files,
        diff_summary=job.diff_summary,
        test_summary=job.test_summary,
        blocker=job.blocker,
        tool_status="done" if job.status in ("running", "validating") else job.status,
    ))
    return DraftPrPreparationInput(
        job_id=job.job_id,
        repo_url=job.repo_url,
        base_branch=job.branch or "main",
        mission=job.mission,
        changed_files=job.changed_files,
        diff_summary=job.diff_summary,
        test_summary=job.test_summary,
        evidence_gate=evidence,
        head_branch=head_branch,
    )


def _slug(value: str, fallback: str = "agent") -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip().lower()).strip("-")
    return (slug or fallback)[:48]


def _default_head_branch(job_id: str, mission: str) -> str:
    return f"sovereign/agent-{_slug(job_id, 'job')}-{_slug(mission, 'change')[:24]}"


def _safe_branch(value: str) -> bool:
    return bool(_SAFE_BRANCH.fullmatch(value)) and ".." not in value and not value.endswith("/") and "//" not in value


def _contains_secret(*values: str | None) -> bool:
    text = "\n".join(value or "" for value in values)
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def _default_title(mission: str) -> str:
    clean = sanitize_agent_text(mission, 120).strip().rstrip(".")
    return f"Draft: {clean or 'Sovereign agent changes'}"


def _default_body(input_value: DraftPrPreparationInput) -> str:
    files = "\n".join(f"- `{path}`" for path in input_value.changed_files) or "- No changed file evidence"
    return sanitize_agent_text(
        "\n".join(
            [
                "## Sovereign Draft PR Preparation",
                "",
                "This is a prepared Draft PR state. The PR has not been created by this gate.",
                "",
                "### Runtime rules",
                "- Draft PR only",
                "- Auto-merge forbidden",
                "- Created only after evidence gate allows preparation",
                "- UI may display this state, but does not create truth",
                "",
                "### Mission",
                input_value.mission or "No mission provided.",
                "",
                "### Changed files",
                files,
                "",
                "### Diff summary",
                input_value.diff_summary or "No diff summary provided.",
                "",
                "### Test summary",
                input_value.test_summary or "No test summary provided.",
            ]
        ),
        8000,
    )


def prepare_draft_pr(input_value: DraftPrPreparationInput) -> DraftPrPreparationResult:
    blockers: list[str] = []

    if not input_value.evidence_gate.can_prepare_draft_pr:
        blockers.append("evidence gate does not allow Draft PR preparation")
    if input_value.draft is not True:
        blockers.append("Draft PR preparation must stay draft-only")
    if input_value.allow_auto_merge:
        blockers.append("auto-merge is forbidden")

    changed_files = normalize_agent_paths(input_value.changed_files)
    if not changed_files:
        blockers.append("Draft PR preparation requires changed file evidence")

    base_branch = input_value.base_branch.strip() or "main"
    head_branch = (input_value.head_branch or _default_head_branch(input_value.job_id, input_value.mission)).strip()
    if not _safe_branch(base_branch):
        blockers.append("base branch is unsafe")
    if not _safe_branch(head_branch):
        blockers.append("head branch is unsafe")
    if head_branch == base_branch:
        blockers.append("head branch must differ from base branch")

    title = sanitize_agent_text(input_value.title or _default_title(input_value.mission), 160)
    body = sanitize_agent_text(input_value.body or _default_body(input_value), 8000)
    if _contains_secret(title, body, input_value.diff_summary, input_value.test_summary, "\n".join(changed_files)):
        blockers.append("Draft PR preparation contains secret-like material")

    if blockers:
        return DraftPrPreparationResult(
            allowed=False,
            decision="blocked",
            summary="Draft PR preparation blocked.",
            head_branch=head_branch,
            base_branch=base_branch,
            title=title,
            body=body,
            changed_files=changed_files,
            next_action="show_blocker",
            blockers=tuple(dict.fromkeys(blockers)),
            predictive_signal="agent_draft_pr_prepare_blocked",
        )

    return DraftPrPreparationResult(
        allowed=True,
        decision="ready",
        summary="Draft PR preparation is ready. Creating the Draft PR is the next explicit action.",
        head_branch=head_branch,
        base_branch=base_branch,
        title=title,
        body=body,
        changed_files=changed_files,
        next_action="create_draft_pr",
        can_create_draft_pr=True,
        can_learn_pattern=input_value.evidence_gate.can_learn_pattern,
        predictive_signal="agent_draft_pr_ready",
    )


def draft_pr_preparation_signal(result: DraftPrPreparationResult) -> dict:
    return {
        "allowed": result.allowed,
        "decision": result.decision,
        "summary": result.summary,
        "headBranch": result.head_branch,
        "baseBranch": result.base_branch,
        "title": result.title,
        "body": result.body,
        "changedFiles": list(result.changed_files),
        "nextAction": result.next_action,
        "canCreateDraftPr": result.can_create_draft_pr,
        "canLearnPattern": result.can_learn_pattern,
        "blockers": list(result.blockers),
        "signal": result.predictive_signal,
    }
