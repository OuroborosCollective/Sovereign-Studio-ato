from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_absent_ato_implementation_is_a_clean_noop() -> None:
    workflow = _read(".github/workflows/autonomous-cycle.yml")

    assert "Detect ATO implementation" in workflow
    assert "echo 'present=false' >> \"$GITHUB_OUTPUT\"" in workflow
    assert "pnpm/action-setup@v4" in workflow
    assert "version: 9.12.2" in workflow
    assert "node-version: 22" in workflow
    assert "pnpm install --frozen-lockfile" in workflow
    assert "pnpm exec tsx scripts/ato/autonomous-pipeline.ts" in workflow
    assert workflow.count("if: steps.ato.outputs.present == 'true'") >= 6
    assert "if: steps.ato.outputs.present != 'true'" in workflow
    assert "no dependency install, QA, mutation, or Draft PR publication was attempted" in workflow
    assert "if-no-files-found: ignore" in workflow
    assert "node-version: 20" not in workflow
    assert "npm ci" not in workflow


def test_supplemental_dispatcher_treats_closed_exact_head_pr_as_terminal_noop() -> None:
    workflow = _read(".github/workflows/supplemental-check-coordinator.yml")

    assert "const matchingPulls = associatedPulls.data.filter" in workflow
    assert "const pull = matchingPulls.find((candidate) => candidate.state === 'open');" in workflow
    assert "if (matchingPulls.length > 0)" in workflow
    assert "Exact-head main PR is already closed or merged; supplemental dispatch is no longer required." in workflow
    # No associated PR is still a provenance failure; only a known closed/merged PR is a no-op.
    assert "core.setFailed('MAIN_PULL_REQUEST_FOR_HEAD_NOT_FOUND');" in workflow
    assert "OPEN_MAIN_PULL_REQUEST_FOR_HEAD_NOT_FOUND" not in workflow
