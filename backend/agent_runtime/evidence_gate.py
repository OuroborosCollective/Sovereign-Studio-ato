"""Evidence and result gate for Sovereign Agent tool results.

Tool output is not product truth by itself. This gate decides which next runtime
state is allowed from changedFiles, diffSummary, testSummary and blockers.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal, Sequence

from .contracts import (
    is_actionable_evidence_file,
    is_plan_only_file,
    normalize_agent_paths,
    sanitize_agent_text,
)
from .tools.base import ToolResult

EvidenceDecision = Literal[
    "continue",
    "block",
    "collect_diff",
    "run_tests",
    "prepare_draft_pr",
    "allow_pattern_learning",
]

EvidenceGateCode = Literal[
    "tool_blocked",
    "tool_failed",
    "no_runtime_evidence",
    "secret_like_evidence",
    "plan_only_result",
    "non_actionable_changed_files",
    "diff_required",
    "tests_required",
    "tests_failed",
    "draft_pr_ready",
    "pattern_learning_ready",
]

_SECRET_EVIDENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"Authorization:\s*(?:Bearer\s+)?[^\s\n]+", re.IGNORECASE),
    re.compile(r"(?:token|password|secret|api[_-]?key)\s*[=:]\s*[^\s\n]+", re.IGNORECASE),
)

_FAILED_TEST_TOKENS = (
    " failed",
    "failed=",
    " failures",
    "failure",
    "error:",
    "errors=",
    "exit code 1",
    "traceback",
    "assertionerror",
)

_PASSED_TEST_TOKENS = (
    " passed",
    "passed=",
    "0 failed",
    "success",
    "completed",
    "ok",
)


@dataclass(frozen=True)
class EvidenceGateInput:
    changed_files: tuple[str, ...] = ()
    diff_summary: str | None = None
    test_summary: str | None = None
    blocker: str | None = None
    tool_status: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True)
class EvidenceGateResult:
    allowed: bool
    decision: EvidenceDecision
    codes: tuple[EvidenceGateCode, ...]
    summary: str
    changed_files: tuple[str, ...] = ()
    next_action: str | None = None
    can_prepare_draft_pr: bool = False
    can_learn_pattern: bool = False
    predictive_signal: str = "agent_evidence_gate_blocked"


def evidence_input_from_tool_result(result: ToolResult) -> EvidenceGateInput:
    return EvidenceGateInput(
        changed_files=result.changed_files,
        diff_summary=result.diff_summary,
        test_summary=result.test_summary,
        blocker=result.blocker,
        tool_status=result.status,
        tool_name=result.tool,
    )


def _has_secret_like_text(*values: str | None) -> bool:
    joined = "\n".join(value or "" for value in values)
    return any(pattern.search(joined) for pattern in _SECRET_EVIDENCE_PATTERNS)


def _tests_failed(summary: str | None) -> bool:
    lower = (summary or "").lower()
    return bool(lower and any(token in lower for token in _FAILED_TEST_TOKENS) and "0 failed" not in lower)


def _tests_present(summary: str | None) -> bool:
    lower = (summary or "").lower()
    return bool(lower and (any(token in lower for token in _PASSED_TEST_TOKENS) or any(token in lower for token in _FAILED_TEST_TOKENS)))


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def evaluate_agent_evidence(input_value: EvidenceGateInput) -> EvidenceGateResult:
    changed_files = normalize_agent_paths(input_value.changed_files)
    actionable_files = tuple(path for path in changed_files if is_actionable_evidence_file(path))
    plan_only_files = tuple(path for path in changed_files if is_plan_only_file(path))
    diff_summary = sanitize_agent_text(input_value.diff_summary, 4000) if input_value.diff_summary else None
    test_summary = sanitize_agent_text(input_value.test_summary, 4000) if input_value.test_summary else None
    blocker = sanitize_agent_text(input_value.blocker, 1200) if input_value.blocker else None

    if _has_secret_like_text("\n".join(changed_files), input_value.diff_summary, input_value.test_summary, input_value.blocker):
        return EvidenceGateResult(
            allowed=False,
            decision="block",
            codes=("secret_like_evidence",),
            summary="Evidence contains secret-like material and was blocked.",
            changed_files=changed_files,
            next_action="redact_and_review",
            predictive_signal="agent_evidence_secret_blocked",
        )

    if input_value.tool_status == "blocked":
        return EvidenceGateResult(
            allowed=False,
            decision="block",
            codes=("tool_blocked",),
            summary=blocker or "Tool result was blocked by runtime policy.",
            changed_files=changed_files,
            next_action="show_blocker",
            can_learn_pattern=bool(blocker),
            predictive_signal="agent_tool_blocked",
        )

    if input_value.tool_status == "failed":
        return EvidenceGateResult(
            allowed=False,
            decision="block",
            codes=("tool_failed",),
            summary=blocker or "Tool result failed.",
            changed_files=changed_files,
            next_action="show_blocker",
            can_learn_pattern=bool(blocker),
            predictive_signal="agent_tool_failed",
        )

    if changed_files and not actionable_files:
        return EvidenceGateResult(
            allowed=False,
            decision="block",
            codes=("plan_only_result",) if plan_only_files else ("non_actionable_changed_files",),
            summary="Changed files are not acceptable runtime evidence.",
            changed_files=changed_files,
            next_action="show_blocker",
            predictive_signal="agent_evidence_non_actionable_blocked",
        )

    has_changes = bool(actionable_files)
    has_diff = bool(diff_summary and diff_summary.strip())
    has_tests = _tests_present(test_summary)

    if _tests_failed(test_summary):
        return EvidenceGateResult(
            allowed=False,
            decision="block",
            codes=("tests_failed",),
            summary="Tests or validation gate reported a failure.",
            changed_files=actionable_files,
            next_action="show_blocker",
            can_learn_pattern=True,
            predictive_signal="agent_tests_failed",
        )

    if has_changes and not has_diff:
        return EvidenceGateResult(
            allowed=True,
            decision="collect_diff",
            codes=("diff_required",),
            summary="Changed files detected; collect a diff before Draft PR preparation.",
            changed_files=actionable_files,
            next_action="collect_diff",
            predictive_signal="agent_evidence_needs_diff",
        )

    if has_changes and has_diff and not has_tests:
        return EvidenceGateResult(
            allowed=True,
            decision="run_tests",
            codes=("tests_required",),
            summary="Diff is ready; run validation tests before Draft PR preparation.",
            changed_files=actionable_files,
            next_action="run_tests",
            can_learn_pattern=True,
            predictive_signal="agent_evidence_needs_tests",
        )

    if has_changes and has_diff and has_tests:
        return EvidenceGateResult(
            allowed=True,
            decision="prepare_draft_pr",
            codes=("draft_pr_ready", "pattern_learning_ready"),
            summary="Changes, diff and tests are present; Draft PR preparation is allowed.",
            changed_files=actionable_files,
            next_action="prepare_draft_pr",
            can_prepare_draft_pr=True,
            can_learn_pattern=True,
            predictive_signal="agent_evidence_draft_pr_ready",
        )

    if has_diff and has_tests:
        return EvidenceGateResult(
            allowed=True,
            decision="allow_pattern_learning",
            codes=("pattern_learning_ready",),
            summary="Diff and tests are present; pattern learning is allowed, but Draft PR needs changed file evidence.",
            changed_files=actionable_files,
            next_action="collect_changed_files",
            can_learn_pattern=True,
            predictive_signal="agent_evidence_learning_ready",
        )

    return EvidenceGateResult(
        allowed=False,
        decision="block",
        codes=("no_runtime_evidence",),
        summary="No runtime evidence was produced by the tool result.",
        changed_files=changed_files,
        next_action="show_blocker",
        predictive_signal="agent_evidence_missing_blocked",
    )


def evaluate_tool_result_evidence(result: ToolResult) -> EvidenceGateResult:
    return evaluate_agent_evidence(evidence_input_from_tool_result(result))


def evidence_gate_signal(gate: EvidenceGateResult) -> dict:
    return {
        "allowed": gate.allowed,
        "decision": gate.decision,
        "codes": list(gate.codes),
        "summary": gate.summary,
        "changedFiles": list(gate.changed_files),
        "nextAction": gate.next_action,
        "canPrepareDraftPr": gate.can_prepare_draft_pr,
        "canLearnPattern": gate.can_learn_pattern,
        "signal": gate.predictive_signal,
    }
