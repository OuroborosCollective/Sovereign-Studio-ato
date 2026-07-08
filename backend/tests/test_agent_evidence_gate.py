from __future__ import annotations

import os
import sys

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.evidence_gate import (  # noqa: E402
    EvidenceGateInput,
    evaluate_agent_evidence,
    evaluate_tool_result_evidence,
    evidence_gate_signal,
)
from agent_runtime.tools.base import blocked_tool_result, done_tool_result, failed_tool_result  # noqa: E402


def test_changed_files_require_diff_before_draft_pr():
    gate = evaluate_agent_evidence(EvidenceGateInput(
        changed_files=("README.md",),
        tool_status="done",
        tool_name="file",
    ))

    assert gate.allowed is True
    assert gate.decision == "collect_diff"
    assert gate.next_action == "collect_diff"
    assert gate.can_prepare_draft_pr is False
    assert gate.can_learn_pattern is False
    assert gate.predictive_signal == "agent_evidence_needs_diff"


def test_changed_files_and_diff_require_tests():
    gate = evaluate_agent_evidence(EvidenceGateInput(
        changed_files=("README.md",),
        diff_summary="README.md | 2 +-",
    ))

    assert gate.allowed is True
    assert gate.decision == "run_tests"
    assert gate.next_action == "run_tests"
    assert gate.can_prepare_draft_pr is False
    assert gate.can_learn_pattern is True
    assert gate.predictive_signal == "agent_evidence_needs_tests"


def test_changes_diff_and_tests_allow_draft_pr_and_pattern_learning():
    gate = evaluate_agent_evidence(EvidenceGateInput(
        changed_files=("src/features/product/runtime/example.ts",),
        diff_summary="src/features/product/runtime/example.ts | 4 +++-",
        test_summary="12 passed, 0 failed",
    ))

    assert gate.allowed is True
    assert gate.decision == "prepare_draft_pr"
    assert gate.next_action == "prepare_draft_pr"
    assert gate.can_prepare_draft_pr is True
    assert gate.can_learn_pattern is True
    assert gate.codes == ("draft_pr_ready", "pattern_learning_ready")
    assert gate.predictive_signal == "agent_evidence_draft_pr_ready"


def test_tests_failure_blocks_draft_pr_preparation():
    gate = evaluate_agent_evidence(EvidenceGateInput(
        changed_files=("README.md",),
        diff_summary="README.md | 2 +-",
        test_summary="1 failed, 4 passed",
    ))

    assert gate.allowed is False
    assert gate.decision == "block"
    assert gate.next_action == "show_blocker"
    assert gate.can_prepare_draft_pr is False
    assert "tests_failed" in gate.codes
    assert gate.predictive_signal == "agent_tests_failed"


def test_plan_only_changed_file_blocks_result():
    gate = evaluate_agent_evidence(EvidenceGateInput(
        changed_files=("docs/SOVEREIGN_PLAN.md",),
        diff_summary="docs/SOVEREIGN_PLAN.md | 10 ++++++++++",
        test_summary="1 passed",
    ))

    assert gate.allowed is False
    assert gate.decision == "block"
    assert "plan_only_result" in gate.codes
    assert gate.predictive_signal == "agent_evidence_non_actionable_blocked"


def test_secret_like_evidence_blocks_before_learning():
    gate = evaluate_agent_evidence(EvidenceGateInput(
        changed_files=("README.md",),
        diff_summary="token=ghp_1234567890SECRETSECRET",
        test_summary="1 passed",
    ))

    assert gate.allowed is False
    assert gate.decision == "block"
    assert gate.codes == ("secret_like_evidence",)
    assert gate.can_learn_pattern is False
    assert gate.predictive_signal == "agent_evidence_secret_blocked"


def test_blocked_tool_result_becomes_blocker_with_learning_signal():
    result = blocked_tool_result("file", "Secret-like path is blocked: .env", predictive_signal="agent_file_write_blocked")
    gate = evaluate_tool_result_evidence(result)

    assert gate.allowed is False
    assert gate.decision == "block"
    assert gate.can_learn_pattern is True
    assert "tool_blocked" in gate.codes
    assert gate.predictive_signal == "agent_tool_blocked"


def test_failed_tool_result_blocks():
    result = failed_tool_result("shell", "Command failed.", exit_code=1)
    gate = evaluate_tool_result_evidence(result)

    assert gate.allowed is False
    assert gate.decision == "block"
    assert "tool_failed" in gate.codes
    assert gate.next_action == "show_blocker"


def test_empty_done_tool_result_blocks_fake_success():
    result = done_tool_result("shell", stdout="nothing changed")
    gate = evaluate_tool_result_evidence(result)

    assert gate.allowed is False
    assert gate.decision == "block"
    assert "no_runtime_evidence" in gate.codes
    assert gate.predictive_signal == "agent_evidence_missing_blocked"


def test_evidence_gate_signal_is_serializable():
    gate = evaluate_agent_evidence(EvidenceGateInput(
        changed_files=("README.md",),
        diff_summary="README.md | 1 +",
    ))

    signal = evidence_gate_signal(gate)

    assert signal["allowed"] is True
    assert signal["decision"] == "run_tests"
    assert signal["nextAction"] == "run_tests"
    assert signal["changedFiles"] == ["README.md"]
    assert signal["signal"] == "agent_evidence_needs_tests"
