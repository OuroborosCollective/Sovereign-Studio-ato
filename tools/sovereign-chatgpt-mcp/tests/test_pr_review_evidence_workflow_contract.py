from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "sovereign-pr-review-evidence.yml"


def test_review_evidence_workflow_is_head_bound_and_read_first() -> None:
    workflow = WORKFLOW.read_text("utf-8")

    assert "workflow_dispatch:" in workflow
    assert "pr_number:" in workflow
    assert "expected_head_sha:" in workflow
    assert "confirm_resolve:" in workflow
    assert "pull-requests: write" in workflow
    assert "reviewThreads(first:100,after:$cursor)" in workflow
    assert "PR_HEAD_IDENTITY_MISMATCH" in workflow
    assert "threadIdSha256" in workflow
    assert "bodySha256" in workflow
    assert "slice(0, 3000)" in workflow
    assert "resolutionPerformed: resolved" in workflow
    assert "secretValuesReturned: false" in workflow


def test_review_resolution_requires_exact_thread_comment_path_and_author() -> None:
    workflow = WORKFLOW.read_text("utf-8")

    assert "expected_thread_id_sha256:" in workflow
    assert "expected_comment_body_sha256:" in workflow
    assert "expected_path:" in workflow
    assert "expected_author:" in workflow
    assert "RESOLUTION_CONFIRMATION_INCOMPLETE" in workflow
    assert "REVIEW_THREAD_EVIDENCE_MISMATCH" in workflow
    assert "resolveReviewThread(input:{threadId:$threadId})" in workflow
    assert "THREAD_ALREADY_RESOLVED" in workflow
    assert "git push" not in workflow
    assert "curl " not in workflow
