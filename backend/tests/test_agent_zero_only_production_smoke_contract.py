from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(relative: str) -> str:
    return (ROOT / relative).read_text("utf-8")


def test_agent_zero_only_production_smoke_has_no_github_or_publication_authority() -> None:
    workflow = source(".github/workflows/agent-zero-only-production-smoke.yml")
    script = source("scripts/run-agent-zero-only-production-smoke.mjs")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "github.token" not in workflow
    assert "GITHUB_TOKEN" not in workflow
    assert "SOVEREIGN_E2E_GITHUB_TOKEN" not in workflow
    assert "No Draft-PR publication step exists" in workflow
    assert "createDraftPr" not in workflow
    assert "publishDraft" not in workflow

    assert "/api/user/agent/repository/run" in script
    assert "githubAccessTokenPresent" in script
    assert "GITHUB_CREDENTIAL_PRESENT_ON_EXECUTION_REQUEST" in script
    assert "SWARM_EXECUTION_ROUTE_USED" in script
    assert "GENERIC_JOB_EXECUTION_ROUTE_USED" in script
    assert "BILLING_OR_CREDITS_EXECUTION_ROUTE_USED" in script
    assert "TOOLCHAIN_HANDOFF_EXECUTION_ROUTE_USED" in script
    assert "GITHUB_CODING_AGENT_ROUTE_USED" in script
    assert "DRAFT_PR_PUBLICATION_ROUTE_USED" in script
    assert "DIRECT_GITHUB_MUTATION_USED" in script


def test_agent_zero_only_production_smoke_requires_single_a2a_and_exact_testfile_readback() -> None:
    script = source("scripts/run-agent-zero-only-production-smoke.mjs")

    assert "agent_zero_repository_access_delegated" in script
    assert "agent_zero_a2a_submit_queued" in script
    assert "agent_zero_a2a_submitted" in script
    assert "agent_zero_a2a_retry_submitted" in script
    assert "AGENT_ZERO_A2A_SUBMISSION_COUNT_NOT_EXACTLY_ONE" in script
    assert "AGENT_ZERO_A2A_RETRY_PRESENT" in script
    assert "/tools/file" in script
    assert "/tools/git-status" in script
    assert "TESTFILE_NOT_EMPTY" in script
    assert "TESTFILE_EMPTY_SHA256_MISMATCH" in script
    assert "GIT_STATUS_NOT_EXACTLY_TESTFILE" in script
    assert "TESTFILE_NOT_UNTRACKED_WORKTREE_EVIDENCE" in script
    assert "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" in script


def test_agent_zero_only_production_smoke_uses_exact_owner_mission_and_runtime_identity() -> None:
    script = source("scripts/run-agent-zero-only-production-smoke.mjs")

    assert (
        "Erstelle im Root des bereitgestellten Repository-Workspaces genau eine leere reguläre Datei testfile. "
        "Verändere keine andere Datei. Erzeuge keinen Commit und keinen Pull Request. "
        "Melde nach Fertigstellung den Abschluss des Auftrages."
    ) in script
    assert "/health" in script
    assert "BACKEND_REVISION_MISMATCH" in script
    assert "BACKEND_IMAGE_DIGEST_MISMATCH" in script
    assert "DEPLOYED_UI_AUTH_ACCOUNT_MISMATCH" in script
    assert "REPOSITORY_JOB_MISSION_IDENTITY_DRIFT" in script
    assert "DRAFT_PR_PUBLICATION_ALREADY_OCCURRED" in script
