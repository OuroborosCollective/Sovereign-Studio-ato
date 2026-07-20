from __future__ import annotations

from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[3]
    / ".github"
    / "workflows"
    / "close-redundant-pr.yml"
).read_text("utf-8")


def test_exact_pr_close_workflow_is_owner_and_revision_bound() -> None:
    assert "workflow_dispatch:" in WORKFLOW
    assert "pull-requests: write" in WORKFLOW
    assert "contents: read" in WORKFLOW
    assert "actions/github-script@v7" in WORKFLOW
    assert "PR_NUMBER: ${{ inputs.pr_number }}" in WORKFLOW
    assert "EXPECTED_HEAD_SHA: ${{ inputs.expected_head_sha }}" in WORKFLOW
    assert "CLOSURE_REASON: ${{ inputs.closure_reason }}" in WORKFLOW
    assert "OWNER_APPROVED: ${{ inputs.owner_approved }}" in WORKFLOW
    assert "process.env.PR_NUMBER" in WORKFLOW
    assert "process.env.EXPECTED_HEAD_SHA" in WORKFLOW
    assert "process.env.CLOSURE_REASON" in WORKFLOW
    assert "process.env.OWNER_APPROVED" in WORKFLOW
    assert "core.getInput(" not in WORKFLOW
    assert "expected_head_sha" in WORKFLOW
    assert "/^[0-9a-f]{40}$/" in WORKFLOW
    assert "ownerApproved !== 'true'" in WORKFLOW
    assert "['redundant', 'superseded']" in WORKFLOW
    assert "actualBase !== 'main'" in WORKFLOW
    assert "actualHead !== expectedHead" in WORKFLOW


def test_exact_pr_close_workflow_requires_non_merge_readback() -> None:
    assert "github.rest.pulls.get" in WORKFLOW
    assert "github.rest.pulls.update" in WORKFLOW
    assert "state: 'closed'" in WORKFLOW
    assert "Boolean(after.merged_at)" in WORKFLOW
    assert "merge_performed', 'false'" in WORKFLOW
    assert "github.rest.pulls.merge" not in WORKFLOW
    assert "git push" not in WORKFLOW
    assert "secrets." not in WORKFLOW
    assert "run: |" not in WORKFLOW
