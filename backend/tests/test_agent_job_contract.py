from __future__ import annotations

import os
import sys

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.contracts import (  # noqa: E402
    SovereignAgentEvent,
    SovereignAgentJobRequest,
    SovereignAgentJobResult,
    build_blocked_agent_result,
    build_sovereign_agent_job_request,
    can_transition_agent_status,
    normalize_agent_job_result,
    sanitize_agent_text,
    validate_agent_job_request,
    validate_agent_job_result,
)


def valid_request(**overrides):
    payload = {
        "repo_url": "https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        "mission": "Fix the README wording and prepare a Draft PR.",
        "executor": "sovereign-local-runner",
        "branch": "main",
        "draft_pr_only": True,
        "allow_auto_merge": False,
    }
    payload.update(overrides)
    return SovereignAgentJobRequest(**payload)


def test_valid_sovereign_agent_request_is_allowed():
    result = validate_agent_job_request(valid_request())

    assert result.allowed is True
    assert result.blockers == ()


def test_invalid_repo_url_blocks():
    result = validate_agent_job_request(valid_request(repo_url="https://evil.example/repo"))

    assert result.allowed is False
    assert "agent job requires a valid HTTPS GitHub repository URL" in result.blockers


def test_empty_mission_blocks():
    result = validate_agent_job_request(valid_request(mission="   "))

    assert result.allowed is False
    assert "agent job mission is required" in result.blockers


def test_auto_merge_and_non_draft_pr_mode_block():
    result = validate_agent_job_request(valid_request(draft_pr_only=False, allow_auto_merge=True))

    assert result.allowed is False
    assert "agent jobs must run in Draft-PR-only mode" in result.blockers
    assert "agent jobs may not auto-merge" in result.blockers


def test_secret_like_mission_blocks_before_runtime_dispatch():
    result = validate_agent_job_request(valid_request(mission="Use github_pat_1234567890SECRETSECRET to push."))

    assert result.allowed is False
    assert "agent job mission contains a secret-like value" in result.blockers


def test_unsupported_executor_blocks():
    result = validate_agent_job_request(valid_request(executor="docker-root-agent"))

    assert result.allowed is False
    assert "agent executor is not supported" in result.blockers


def test_unsafe_branch_blocks():
    result = validate_agent_job_request(valid_request(branch="main; rm -rf /"))

    assert result.allowed is False
    assert "agent job branch contains unsafe characters" in result.blockers


def test_build_request_normalizes_payload_and_masks_memory_hints():
    request = build_sovereign_agent_job_request({
        "repoUrl": " https://github.com/OuroborosCollective/Sovereign-Studio-ato ",
        "mission": "Update docs",
        "allowedPaths": ["src/App.tsx", "../escape"],
        "memoryHints": ["token=ghp_1234567890SECRETSECRET"],
    })

    assert request.repo_url == "https://github.com/OuroborosCollective/Sovereign-Studio-ato"
    assert request.allowed_paths == ("src/App.tsx",)
    assert "[redacted]" in request.memory_hints[0]
    assert "ghp_" not in request.memory_hints[0]


def test_status_transitions_are_explicit():
    assert can_transition_agent_status("queued", "provisioning") is True
    assert can_transition_agent_status("running", "completed") is True
    assert can_transition_agent_status("completed", "running") is False
    assert can_transition_agent_status("cleaned", "running") is False


def test_completed_without_evidence_blocks():
    result = validate_agent_job_result(SovereignAgentJobResult(
        job_id="job-1",
        status="completed",
        changed_files=(),
    ))

    assert result.allowed is False
    assert "completed agent result requires runtime evidence" in result.blockers


def test_completed_with_real_changed_file_is_allowed():
    result = validate_agent_job_result(SovereignAgentJobResult(
        job_id="job-1",
        status="completed",
        changed_files=("src/features/product/runtime/example.ts",),
    ))

    assert result.allowed is True


def test_completed_with_plan_only_file_blocks():
    result = validate_agent_job_result(SovereignAgentJobResult(
        job_id="job-1",
        status="completed",
        changed_files=("docs/SOVEREIGN_PLAN.md",),
    ))

    assert result.allowed is False
    assert "plan-only agent result may not complete" in result.blockers


def test_failed_and_blocked_require_reason():
    failed = validate_agent_job_result(SovereignAgentJobResult(job_id="job-1", status="failed"))
    blocked = validate_agent_job_result(SovereignAgentJobResult(job_id="job-2", status="blocked"))

    assert failed.allowed is False
    assert blocked.allowed is False
    assert "failed or blocked agent result requires a blocker reason" in failed.blockers
    assert "failed or blocked agent result requires a blocker reason" in blocked.blockers


def test_normalize_result_converts_invalid_completed_to_blocked_state():
    normalized = normalize_agent_job_result(SovereignAgentJobResult(
        job_id="job-1",
        status="completed",
        changed_files=(),
    ))

    assert normalized.status == "blocked"
    assert normalized.blocker
    assert "completed agent result requires runtime evidence" in normalized.blocker


def test_result_sanitizes_events_and_secret_text():
    normalized = normalize_agent_job_result(SovereignAgentJobResult(
        job_id="job-1",
        status="blocked",
        blocker="token=github_pat_1234567890SECRETSECRET",
        events=(SovereignAgentEvent(stage="log", level="info", message="Authorization: Bearer ghp_1234567890SECRETSECRET"),),
    ))

    serialized = f"{normalized.blocker} {normalized.events[0].message}"
    assert "github_pat_" not in serialized
    assert "ghp_" not in serialized
    assert "[redacted]" in serialized


def test_build_blocked_agent_result_creates_valid_blocker_state():
    result = build_blocked_agent_result("job-1", "Workspace policy blocked.")
    validation = validate_agent_job_result(result)

    assert result.status == "blocked"
    assert result.blocker == "Workspace policy blocked."
    assert validation.allowed is True


def test_sanitize_agent_text_masks_secret_like_values():
    text = sanitize_agent_text("password=super-secret token=ghp_1234567890SECRETSECRET")

    assert "super-secret" not in text
    assert "ghp_" not in text
    assert "[redacted]" in text
