from __future__ import annotations

import os
import sys

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.draft_pr_gate import (  # noqa: E402
    DraftPrPreparationInput,
    draft_pr_input_from_job,
    draft_pr_preparation_signal,
    prepare_draft_pr,
)
from agent_runtime.evidence_gate import EvidenceGateInput, evaluate_agent_evidence  # noqa: E402
from agent_runtime.job_store import StoredSovereignAgentJob  # noqa: E402


def ready_input(**overrides):
    evidence = evaluate_agent_evidence(EvidenceGateInput(
        changed_files=("README.md",),
        diff_summary="README.md | 2 +-",
        test_summary="12 passed, 0 failed",
    ))
    payload = {
        "job_id": "agent-test-123",
        "repo_url": "https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        "base_branch": "main",
        "mission": "Update README wording",
        "changed_files": ("README.md",),
        "diff_summary": "README.md | 2 +-",
        "test_summary": "12 passed, 0 failed",
        "evidence_gate": evidence,
    }
    payload.update(overrides)
    return DraftPrPreparationInput(**payload)


def test_ready_evidence_prepares_draft_pr_state():
    result = prepare_draft_pr(ready_input())

    assert result.allowed is True
    assert result.decision == "ready"
    assert result.can_create_draft_pr is True
    assert result.can_learn_pattern is True
    assert result.next_action == "create_draft_pr"
    assert result.head_branch is not None
    assert result.head_branch.startswith("sovereign/agent-")
    assert result.base_branch == "main"
    assert result.title == "Draft: Update README wording"
    assert "Auto-merge forbidden" in (result.body or "")
    assert result.predictive_signal == "agent_draft_pr_ready"


def test_not_ready_evidence_blocks_preparation():
    evidence = evaluate_agent_evidence(EvidenceGateInput(
        changed_files=("README.md",),
        diff_summary="README.md | 2 +-",
    ))
    result = prepare_draft_pr(ready_input(evidence_gate=evidence, test_summary=None))

    assert result.allowed is False
    assert result.decision == "blocked"
    assert "evidence gate does not allow Draft PR preparation" in result.blockers
    assert result.can_create_draft_pr is False


def test_auto_merge_and_non_draft_mode_block():
    result = prepare_draft_pr(ready_input(allow_auto_merge=True, draft=False))

    assert result.allowed is False
    assert "auto-merge is forbidden" in result.blockers
    assert "Draft PR preparation must stay draft-only" in result.blockers


def test_unsafe_head_branch_blocks():
    result = prepare_draft_pr(ready_input(head_branch="main;rm-rf"))

    assert result.allowed is False
    assert "head branch is unsafe" in result.blockers


def test_head_branch_must_differ_from_base():
    result = prepare_draft_pr(ready_input(head_branch="main"))

    assert result.allowed is False
    assert "head branch must differ from base branch" in result.blockers


def test_secret_like_body_blocks_preparation():
    result = prepare_draft_pr(ready_input(body="token=ghp_1234567890SECRETSECRET"))

    assert result.allowed is False
    assert "Draft PR preparation contains secret-like material" in result.blockers


def test_draft_pr_signal_is_serializable():
    result = prepare_draft_pr(ready_input())
    signal = draft_pr_preparation_signal(result)

    assert signal["allowed"] is True
    assert signal["decision"] == "ready"
    assert signal["nextAction"] == "create_draft_pr"
    assert signal["canCreateDraftPr"] is True
    assert signal["canLearnPattern"] is True
    assert signal["signal"] == "agent_draft_pr_ready"


def test_input_from_job_uses_stored_evidence():
    job = StoredSovereignAgentJob(
        job_id="agent-1",
        user_id="user-1",
        executor="sovereign-local-runner",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        branch="main",
        mission="Update README wording",
        status="validating",
        changed_files=("README.md",),
        diff_summary="README.md | 2 +-",
        test_summary="12 passed, 0 failed",
    )

    prepared = prepare_draft_pr(draft_pr_input_from_job(job))

    assert prepared.allowed is True
    assert prepared.can_create_draft_pr is True
    assert prepared.base_branch == "main"
