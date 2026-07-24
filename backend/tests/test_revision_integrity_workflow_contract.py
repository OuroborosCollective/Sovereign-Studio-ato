from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_release_gate_runs_for_every_pr_and_draft_pr() -> None:
    workflow = (ROOT / ".github/workflows/release-verification.yml").read_text("utf-8")

    pull_request_block = workflow.split("  pull_request:\n", 1)[1].split("  workflow_dispatch:", 1)[0]
    assert "branches: [main]" in pull_request_block
    assert "types: [opened, synchronize, reopened, ready_for_review, converted_to_draft]" in pull_request_block
    assert "paths:" not in pull_request_block


def test_release_gate_binds_checkout_and_tests_to_pr_head_revision() -> None:
    workflow = (ROOT / ".github/workflows/release-verification.yml").read_text("utf-8")

    assert "SOVEREIGN_REVISION: ${{ github.event.pull_request.head.sha || github.sha }}" in workflow
    assert "name: Checkout exact authoritative revision" in workflow
    assert "ref: ${{ env.SOVEREIGN_REVISION }}" in workflow
    assert "name: Revision Integrity Gate" in workflow
    assert 'ACTUAL_HEAD="$(git rev-parse HEAD)"' in workflow
    assert '[[ "$ACTUAL_HEAD" == "$SOVEREIGN_REVISION" ]]' in workflow
    assert '[[ "$EVENT_PR_HEAD_SHA" == "$SOVEREIGN_REVISION" ]]' in workflow
    assert "| Revision Integrity | ${{ steps.revision_integrity.outcome }} |" in workflow


def test_backend_image_uses_the_same_authoritative_revision() -> None:
    workflow = (ROOT / ".github/workflows/sovereign-backend-image.yml").read_text("utf-8")

    assert "SOVEREIGN_REVISION: ${{ github.event.pull_request.head.sha || github.sha }}" in workflow
    assert "ref: ${{ env.SOVEREIGN_REVISION }}" in workflow
    assert "VITE_SOVEREIGN_SOURCE_REVISION: ${{ env.SOVEREIGN_REVISION }}" in workflow
    assert "SOVEREIGN_SOURCE_REVISION=${{ env.SOVEREIGN_REVISION }}" in workflow
    assert "org.opencontainers.image.revision=${{ env.SOVEREIGN_REVISION }}" in workflow
    assert "${{ env.IMAGE_NAME }}:${{ env.SOVEREIGN_REVISION }}" in workflow
