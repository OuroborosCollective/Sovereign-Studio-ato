from __future__ import annotations

import json
import os
import sys

# Füge Backend zum Python Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime import draft_pr_create_gate  # noqa: E402
from agent_runtime.draft_pr_create_gate import (  # noqa: E402
    DraftPrCreateRequest,
    GitHubApiDraftPrCreator,
    create_draft_pr_for_job,
    draft_pr_create_request_from_job,
    draft_pr_create_signal,
    validate_draft_pr_create_request,
)
from agent_runtime.job_store import StoredSovereignAgentJob  # noqa: E402


class FakeDraftPrCreator:
    def __init__(
        self,
        url="https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/123",
        head_sha=None,
    ):
        self.url = url
        self.head_sha = head_sha
        self.calls = []

    def create_draft_pr(self, request, token):
        self.calls.append((request, token))
        return (self.url, self.head_sha) if self.head_sha else self.url


def fake_github_token() -> str:
    return "ghp_" + "1234567890SECRETSECRETSECRET"


class _FakeGitHubResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def _github_readback_urlopen(*, existing_prs, pr_number, head_sha, head_branch, base_branch="main"):
    """URL-routing urlopen fake for the production readback evidence flow."""
    owner_repo = "OuroborosCollective/Sovereign-Studio-ato"

    def handler(request, timeout=30):
        url = request.full_url
        if "/pulls?" in url:
            return _FakeGitHubResponse(existing_prs)
        if url.rstrip("/").endswith(f"/pulls/{pr_number}"):
            return _FakeGitHubResponse({
                "html_url": f"https://github.com/{owner_repo}/pull/{pr_number}",
                "state": "open",
                "draft": True,
                "head": {"ref": head_branch, "sha": head_sha, "repo": {"full_name": owner_repo}},
                "base": {"ref": base_branch, "repo": {"full_name": owner_repo}},
            })
        if "/check-runs?" in url:
            return _FakeGitHubResponse({"total_count": 0, "check_runs": []})
        if "/status?per_page=100" in url:
            return _FakeGitHubResponse({"state": "success", "statuses": [], "total_count": 0})
        raise AssertionError(f"Unexpected GitHub URL: {url}")

    return handler


def ready_job(**overrides):
    values = dict(
        job_id="agent-1",
        user_id="user-1",
        executor="sovereign-local-runner",
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        branch="main",
        mission="Update README wording",
        status="validating",
        workspace_id="agent-1",
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

    assert "Draft PR create requires workspace evidence" in blockers
    assert "Draft PR create requires changed file evidence" in blockers
    assert "Draft PR create requires diff summary evidence" in blockers
    assert "Draft PR create requires test summary evidence" in blockers


def test_validate_blocks_unsafe_branch():
    request = draft_pr_create_request_from_job(ready_job(branch_name="main;rm-rf"))

    blockers = validate_draft_pr_create_request(request)

    assert "head branch is unsafe or missing" in blockers


def test_validate_blocks_secret_like_payload():
    request = draft_pr_create_request_from_job(ready_job(diff_summary="token=" + fake_github_token()))

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
    creator = FakeDraftPrCreator(head_sha="b" * 40)

    result = create_draft_pr_for_job(ready_job(), creator=creator, token="test-token")

    assert result.allowed is True
    assert result.status == "created"
    assert result.pr_url == "https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/123"
    assert result.head_sha == "b" * 40
    # Contract drift (production truth): the predictive_signal event for the
    # legacy injected-creator path without live readback was renamed from
    # "agent_draft_pr_created" to "agent_draft_pr_created_unverified_test_creator".
    # The production GitHubApiDraftPrCreator still emits "agent_draft_pr_created"
    # after verified readback.
    assert result.predictive_signal == "agent_draft_pr_created_unverified_test_creator"
    assert creator.calls[0][1] == "test-token"
    assert draft_pr_create_signal(result)["headSha"] == "b" * 40


def test_create_blocks_invalid_creator_url():
    creator = FakeDraftPrCreator(url="https://example.com/not-a-github-pr")

    result = create_draft_pr_for_job(ready_job(), creator=creator, token="test-token")

    assert result.allowed is False
    assert result.status == "blocked"
    assert result.blocker == "GitHub did not return a valid pull request URL"


def test_existing_created_pr_is_idempotent():
    # Contract drift (production truth): the default GitHubApiDraftPrCreator
    # re-verifies existing Draft PRs via live readback (verify_existing_draft_pr).
    # The network-free idempotent shortcut now only applies to injected
    # unit-test creators without a verifier.
    result = create_draft_pr_for_job(
        ready_job(
            pr_state="created",
            pr_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/321",
        ),
        creator=FakeDraftPrCreator(),
        token="test-token",
    )

    assert result.allowed is True
    assert result.status == "created"
    assert result.pr_url.endswith("/pull/321")
    assert result.predictive_signal == "agent_draft_pr_created_unverified_test_creator"


def test_github_creator_reuses_existing_draft_pr(monkeypatch):
    request = draft_pr_create_request_from_job(ready_job())
    head_sha = "a" * 40
    monkeypatch.setattr(
        draft_pr_create_gate,
        "publish_workspace_branch",
        lambda *args, **kwargs: type("Publication", (), {"status": "done", "commit_sha": head_sha, "blocker": None})(),
    )
    # Contract drift (production truth): the creator now returns verified
    # readback evidence (DraftPrPublicationEvidence) instead of the legacy
    # (url, head_sha) tuple, so the fake must serve the full readback flow
    # (open-PR lookup, PR readback, check-runs, combined status).
    monkeypatch.setattr(
        draft_pr_create_gate,
        "urlopen",
        _github_readback_urlopen(
            existing_prs=[{
                "html_url": "https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/444",
                "draft": True,
                "number": 444,
            }],
            pr_number=444,
            head_sha=head_sha,
            head_branch=request.head_branch,
        ),
    )

    evidence = GitHubApiDraftPrCreator().create_draft_pr(request, "test-token")

    assert evidence.pr_url.endswith("/pull/444")
    assert evidence.pr_number == 444
    assert evidence.published_head_sha == head_sha
    assert evidence.readback_head_sha == head_sha
    assert evidence.readback_verified is True
    assert evidence.checks_readback_verified is True
    assert evidence.draft_verified is True


def test_github_creator_blocks_existing_non_draft_pr(monkeypatch):
    request = draft_pr_create_request_from_job(ready_job())
    monkeypatch.setattr(
        draft_pr_create_gate,
        "publish_workspace_branch",
        lambda *args, **kwargs: type("Publication", (), {"status": "done", "commit_sha": "a" * 40, "blocker": None})(),
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            # Production readback contract: entries require a valid positive
            # "number" so the non-draft guard can identify the blocking PR.
            return b'[{"html_url":"https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/445","draft":false,"number":445}]'

    monkeypatch.setattr(draft_pr_create_gate, "urlopen", lambda request, timeout=30: FakeResponse())

    result = create_draft_pr_for_job(ready_job(), creator=GitHubApiDraftPrCreator(), token="test-token")

    assert result.allowed is False
    assert result.status == "blocked"
    assert result.blocker == "An open non-draft pull request already exists for the prepared branch"


def test_draft_pr_create_signal_is_serializable():
    # Injected creator: network-free idempotent path (see idempotency test).
    result = create_draft_pr_for_job(
        ready_job(
            pr_state="created",
            pr_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/321",
        ),
        creator=FakeDraftPrCreator(),
        token="test-token",
    )

    signal = draft_pr_create_signal(result)

    assert signal["allowed"] is True
    assert signal["status"] == "created"
    assert signal["prUrl"].endswith("/pull/321")
    # Renamed event for the unverified injected-creator path (see drift note
    # in test_create_uses_injected_creator_and_requires_valid_url).
    assert signal["signal"] == "agent_draft_pr_created_unverified_test_creator"
    json.dumps(signal)  # signal payload must stay JSON-serializable
