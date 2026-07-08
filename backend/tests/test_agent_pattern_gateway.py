from __future__ import annotations

import os
import sys

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.job_store import StoredSovereignAgentJob  # noqa: E402
from agent_runtime.pattern_gateway import (  # noqa: E402
    PatternLearningInput,
    evaluate_pattern_learning,
    pattern_input_from_job,
    pattern_learning_signal,
)


def test_solution_pattern_requires_validated_evidence():
    result = evaluate_pattern_learning(PatternLearningInput(
        job_id="agent-1",
        source="test",
        mission="Improve README and tests",
        changed_files=("README.md",),
        diff_summary="README.md | 12 ++++++++++++",
        test_summary="12 passed, 0 failed",
        evidence_passed=True,
        can_learn_pattern=True,
        draft_pr_ready=True,
    ))

    assert result.allowed is True
    assert result.kind == "solution"
    assert result.remote_memory_allowed is True
    assert result.predictive_signal == "agent_pattern_solution_ready"
    assert result.payload["changedFiles"] == ["README.md"]


def test_blocker_pattern_can_be_learned_without_solution_evidence():
    result = evaluate_pattern_learning(PatternLearningInput(
        job_id="agent-2",
        source="test",
        mission="Run backend tests",
        blocker="pytest unavailable in workspace image",
    ))

    assert result.allowed is True
    assert result.kind == "blocker"
    assert result.remote_memory_allowed is True
    assert result.payload["blocker"] == "pytest unavailable in workspace image"


def test_secret_like_pattern_payload_blocks_remote_memory():
    result = evaluate_pattern_learning(PatternLearningInput(
        job_id="agent-3",
        source="test",
        mission="Update config",
        changed_files=("README.md",),
        diff_summary="token=ghp_1234567890SECRETSECRET",
        test_summary="1 passed",
        evidence_passed=True,
        can_learn_pattern=True,
    ))

    assert result.allowed is False
    assert result.remote_memory_allowed is False
    assert "pattern payload contains secret-like material" in result.blockers


def test_no_evidence_blocks_pattern_learning():
    result = evaluate_pattern_learning(PatternLearningInput(
        job_id="agent-4",
        source="test",
        mission="Think about a plan",
    ))

    assert result.allowed is False
    assert result.kind is None
    assert result.remote_memory_allowed is False
    assert "no validated solution or blocker evidence for pattern learning" in result.blockers


def test_pattern_input_from_job_uses_evidence_gate():
    job = StoredSovereignAgentJob(
        job_id="agent-5",
        user_id="user-1",
        executor="sovereign-local-runner",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        branch="main",
        mission="Improve README and tests",
        status="validating",
        changed_files=("README.md",),
        diff_summary="README.md | 12 ++++++++++++",
        test_summary="12 passed, 0 failed",
        pr_state="ready",
    )

    input_value = pattern_input_from_job(job)
    result = evaluate_pattern_learning(input_value)

    assert input_value.evidence_passed is True
    assert input_value.can_learn_pattern is True
    assert input_value.draft_pr_ready is True
    assert result.allowed is True


def test_pattern_learning_signal_is_serializable():
    result = evaluate_pattern_learning(PatternLearningInput(
        job_id="agent-6",
        source="test",
        mission="Fix runtime route",
        blocker="route returned incompatible ToolResult shape",
    ))

    signal = pattern_learning_signal(result)

    assert signal["allowed"] is True
    assert signal["kind"] == "blocker"
    assert signal["remoteMemoryAllowed"] is True
    assert signal["signal"] == "agent_pattern_blocker_ready"
