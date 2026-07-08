from __future__ import annotations

import os
import sys

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.draft_pr_create_gate import (  # noqa: E402
    DraftPrCreateRequest,
    create_draft_pr_for_job,
    draft_pr_create_request_from_job,
    draft_pr_create_signal,
    validate_draft_pr_create_request,
)
from agent_runtime.job_store import StoredSovereignAgentJob  # noqa: E402


class FakeDraftPrCreator:
    def __init__(self, url="https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/123"):
        self.url = url
        self.calls = []

    def create_draft_pr(self, request, token):
        self.calls.append((request, token))
        return self.url


def ready_job(**overrides):
    values = dict(
        job_id="agent-1",
        user_id="user-1",
        executor="sovereign-local-runner",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        branch="main",
        mission="Update README wording",
        status="validating",
        changed_files=("README.md",),
        diff_summary="README.md | 2 ++",
        test_summary="12 passed, 0 failed",
        draft_pr_preparation={"body": "Prepared body"},
        branch_name="sovereign/agent-agent-1-update-readme",
        target_branch="main",
        commit_message="Draft: Update README wording",
        pr_state="ready",
    )
    values.update(overrides)
    return StoredSovereignAgentJob(**values)


def test_draft_pr_create_request_from_job_maps_ready_state():
    request = draft_pr_create_request_from_job(ready_job())

    assert request.job_id == "agent-1"
    assert request.head_branch == "sovereign/agent-agent-1-update-readme"
    assert request.base_branch == "main"
    assert request.title == "Draft: Update README wording"
    assert request.body == "Prepared body"
    assert request.pr_state == "ready"


def test_validate_blocks_without_ready_state():
    request = draft_pr_create_request_from_job(ready_job(pr_state=None))

    blockers = validate_draft_pr_create_request(request)

    assert "Draft PR create requires pr_state=ready" in blockers


def test_validate_blocks_missing_evidence():
    request = DraftPrCreateRequest(
        job_id="agent-1",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        head_branch="sovereign/agent-1",
        base_branch="main",
        title="Draft: Update README",
        body="Body",
        pr_state="ready",
    )

    blockers = validate_draft_pr_create_request(request)

    assert "Draft PR create requires changed file evidence" in blockers
    assert "Draft PR create requires diff summary evidence" in blockers
    assert "Draft PR create requires test summary evidence" in blockers


def test_validate_blocks_unsafe_branch():
    request = draft_pr_create_request_from_job(ready_job(branch_name="main;rm-rf"))

    blockers = validate_draft_pr_create_request(request)

    assert "head branch is unsafe or missing" in blockers


def test_validate_blocks_secret_like_payload():
    request = draft_pr_create_request_from_job(ready_job(diff_summary="token=ghp_1234567890SECRETSECRETSECRET"))

    blockers = validate_draft_pr_create_request(request)

    assert "Draft PR create payload contains secret-like material" in blockers


def test_create_blocks_without_server_token(monkeypatch):
    monkeypatch.delenv("SOVEREIGN_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    result = create_draft_pr_for_job(ready_job())

    assert result.allowed is False
    assert result.status == "blocked"
    assert result.pr_url is None
    assert result.blocker == "server GitHub credentials missing for Draft PR create"
    assert result.predictive_signal == "agent_draft_pr_create_credentials_missing"


def test_create_uses_injected_creator_and_requires_valid_url(monkeypatch):
    monkeypatch.delenv("SOVEREIGN_GITHUB_TOKEN", raising=False)
    creator = FakeDraftPrCreator()

    result = create_draft_pr_for_job(ready_job(), creator=creator, token="test-token")

    assert result.allowed is True
    assert result.status == "created"
    assert result.pr_url == "https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/123"
    assert result.predictive_signal == "agent_draft_pr_created"
    assert creator.calls[0][1] == "test-token"


def test_create_blocks_invalid_creator_url():
    creator = FakeDraftPrCreator(url="https://example.com/not-a-github-pr")

    result = create_draft_pr_for_job(ready_job(), creator=creator, token="test-token")

    assert result.allowed is False
    assert result.status == "blocked"
    assert result.blocker == "GitHub did not return a valid pull request URL"


def test_existing_created_pr_is_idempotent():
    result = create_draft_pr_for_job(ready_job(
        pr_state="created",
        pr_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/321",
    ))

    assert result.allowed is True
    assert result.status == "created"
    assert result.pr_url.endswith("/pull/321")


def test_draft_pr_create_signal_is_serializable():
    result = create_draft_pr_for_job(ready_job(
        pr_state="created",
        pr_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/321",
    ))

    signal = draft_pr_create_signal(result)

    assert signal["allowed"] is True
    assert signal["status"] == "created"
    assert signal["prUrl"].endswith("/pull/321")
    assert signal["signal"] == "agent_draft_pr_created"
