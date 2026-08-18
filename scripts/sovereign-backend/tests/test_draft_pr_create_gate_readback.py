"""Regression tests for the real Draft-PR publication readback boundary."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_runtime import draft_pr_create_gate as gate


REPO_URL = "https://github.com/OuroborosCollective/Sovereign-Studio-ato"
PR_URL = "https://github.com/OuroborosCollective/Sovereign-Studio-ato/pull/42"
HEAD_BRANCH = "sovereign/test-draft-flow"
BASE_BRANCH = "main"
HEAD_SHA = "a" * 40


def _request() -> gate.DraftPrCreateRequest:
    return gate.DraftPrCreateRequest(
        job_id="job-1",
        repo_url=REPO_URL,
        head_branch=HEAD_BRANCH,
        base_branch=BASE_BRANCH,
        title="test: verified Draft PR",
        body="Evidence-bound Draft PR test.",
        pr_state="ready",
        changed_files=("README.md",),
        diff_summary="README.md changed",
        test_summary="tests passed",
        workspace_id="ws-1",
    )


def _pr_payload(*, draft: bool = True, head_sha: str = HEAD_SHA) -> dict:
    return {
        "html_url": PR_URL,
        "draft": draft,
        "state": "open",
        "head": {
            "ref": HEAD_BRANCH,
            "sha": head_sha,
            "repo": {"full_name": "OuroborosCollective/Sovereign-Studio-ato"},
        },
        "base": {
            "ref": BASE_BRANCH,
            "repo": {"full_name": "OuroborosCollective/Sovereign-Studio-ato"},
        },
    }


def _github_readback(url: str, _token: str, **_kwargs):
    if url.endswith("/pulls/42"):
        return _pr_payload()
    if "/check-runs?" in url:
        return {
            "total_count": 1,
            "check_runs": [{"status": "in_progress", "conclusion": None}],
        }
    if url.endswith(f"/commits/{HEAD_SHA}/status?per_page=100"):
        return {"state": "pending", "total_count": 0, "statuses": []}
    raise AssertionError(f"unexpected GitHub URL: {url}")


def test_readback_requires_open_draft_matching_head_and_reads_ci(monkeypatch):
    monkeypatch.setattr(gate, "_github_json", _github_readback)
    creator = gate.GitHubApiDraftPrCreator()

    evidence = creator._readback_evidence(
        _request(),
        "test-token",
        "OuroborosCollective",
        "Sovereign-Studio-ato",
        pr_url=PR_URL,
        pr_number=42,
        expected_head_sha=HEAD_SHA,
    )

    assert evidence.readback_verified is True
    assert evidence.checks_readback_verified is True
    assert evidence.draft_verified is True
    assert evidence.state == "open"
    assert evidence.published_head_sha == HEAD_SHA
    assert evidence.readback_head_sha == HEAD_SHA
    assert evidence.ci_state == "pending"
    assert evidence.check_run_count == 1
    assert evidence.checks_pending_count == 1
    assert evidence.checks_failure_count == 0


def test_readback_rejects_non_draft_pull_request(monkeypatch):
    def fake_github(url: str, _token: str, **_kwargs):
        if url.endswith("/pulls/42"):
            return _pr_payload(draft=False)
        raise AssertionError(f"unexpected GitHub URL after identity failure: {url}")

    monkeypatch.setattr(gate, "_github_json", fake_github)
    creator = gate.GitHubApiDraftPrCreator()

    with pytest.raises(gate.DraftPrPublicationError, match="identity readback mismatch"):
        creator._readback_evidence(
            _request(),
            "test-token",
            "OuroborosCollective",
            "Sovereign-Studio-ato",
            pr_url=PR_URL,
            pr_number=42,
            expected_head_sha=HEAD_SHA,
        )


def test_readback_rejects_workspace_and_pull_request_sha_drift(monkeypatch):
    drift_sha = "b" * 40

    def fake_github(url: str, _token: str, **_kwargs):
        if url.endswith("/pulls/42"):
            return _pr_payload(head_sha=drift_sha)
        raise AssertionError(f"unexpected GitHub URL after SHA failure: {url}")

    monkeypatch.setattr(gate, "_github_json", fake_github)
    creator = gate.GitHubApiDraftPrCreator()

    with pytest.raises(gate.DraftPrPublicationError, match="does not match"):
        creator._readback_evidence(
            _request(),
            "test-token",
            "OuroborosCollective",
            "Sovereign-Studio-ato",
            pr_url=PR_URL,
            pr_number=42,
            expected_head_sha=HEAD_SHA,
        )
