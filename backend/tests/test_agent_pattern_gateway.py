from __future__ import annotations

import hashlib
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
    assert len(result.payload["missionSha256"]) == 64


def test_wrapped_agent_mission_hashes_the_original_user_prompt():
    prompt = "Fix the runtime route and prove it with tests"
    wrapped = "\n".join((
        "Ideenfabrik Auftrag:",
        prompt,
        "",
        "Repository-Kontext:",
        "Repo-Snapshot ist geladen.",
        "",
        "Umsetzung:",
        "- Draft PR only.",
    ))
    result = evaluate_pattern_learning(PatternLearningInput(
        job_id="agent-wrapped",
        source="test",
        mission=wrapped,
        changed_files=("src/runtime.ts",),
        diff_summary="src/runtime.ts | 10 ++++++++++",
        test_summary="4 passed, 0 failed",
        evidence_passed=True,
        can_learn_pattern=True,
        draft_pr_ready=True,
    ))

    assert result.payload["missionSha256"] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def test_blocker_pattern_requires_terminal_runtime_evidence():
    result = evaluate_pattern_learning(PatternLearningInput(
        job_id="agent-2",
        source="test",
        mission="Run backend tests",
        blocker="pytest unavailable in workspace image",
        blocker_evidence_passed=True,
    ))

    assert result.allowed is True
    assert result.kind == "blocker"
    assert result.remote_memory_allowed is True
    assert result.payload["blocker"] == "pytest unavailable in workspace image"
    assert result.payload["blockerEvidencePassed"] is True


def test_unverified_blocker_text_never_becomes_remote_memory():
    result = evaluate_pattern_learning(PatternLearningInput(
        job_id="agent-unverified-blocker",
        source="test",
        mission="Run backend tests",
        blocker="pytest unavailable in workspace image",
    ))

    assert result.allowed is False
    assert result.kind is None
    assert result.remote_memory_allowed is False
    assert "no validated solution or blocker evidence for pattern learning" in result.blockers


def test_solution_without_draft_pr_evidence_is_blocked():
    result = evaluate_pattern_learning(PatternLearningInput(
        job_id="agent-no-draft",
        source="test",
        mission="Improve README and tests",
        changed_files=("README.md",),
        diff_summary="README.md | 12 ++++++++++++",
        test_summary="12 passed, 0 failed",
        evidence_passed=True,
        can_learn_pattern=True,
        draft_pr_ready=False,
    ))

    assert result.allowed is False
    assert result.remote_memory_allowed is False


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


def test_pattern_input_from_job_requires_terminal_error_event_for_blocker_learning():
    without_event = StoredSovereignAgentJob(
        job_id="agent-blocked-plain",
        user_id="user-1",
        executor="sovereign-local-runner",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        branch="main",
        mission="Run backend tests",
        status="blocked",
        blocker="pytest unavailable in workspace image",
        events=(),
    )
    with_event = StoredSovereignAgentJob(
        job_id="agent-blocked-evidence",
        user_id="user-1",
        executor="sovereign-local-runner",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        branch="main",
        mission="Run backend tests",
        status="failed",
        blocker="pytest unavailable in workspace image",
        events=({"level": "error", "message": "pytest executable missing from runtime image"},),
    )

    assert pattern_input_from_job(without_event).blocker_evidence_passed is False
    assert pattern_input_from_job(with_event).blocker_evidence_passed is True


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
        blocker_evidence_passed=True,
    ))

    signal = pattern_learning_signal(result)

    assert signal["allowed"] is True
    assert signal["kind"] == "blocker"
    assert signal["remoteMemoryAllowed"] is True
    assert signal["signal"] == "agent_pattern_blocker_ready"
