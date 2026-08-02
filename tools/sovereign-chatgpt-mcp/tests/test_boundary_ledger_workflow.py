from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DRIFT_WORKFLOW = ROOT / ".github" / "workflows" / "boundary-ledger-drift.yml"
MCP_WORKFLOW = ROOT / ".github" / "workflows" / "sovereign-chatgpt-mcp.yml"


def test_boundary_workflow_emits_evidence_before_failing_closed() -> None:
    workflow = DRIFT_WORKFLOW.read_text("utf-8")

    assert "workflow_call:" in workflow
    assert "Discover candidates and compare the review ledger" in workflow
    assert "Upload bounded drift evidence" in workflow
    assert workflow.index("Upload bounded drift evidence") < workflow.index("Fail closed before the MCP full suite")
    assert "--expected-head" in workflow
    assert "--append-continuity" in workflow
    assert "onlyNewStructuredCandidates" in workflow
    assert "exclusively new deterministic STRUCTURED_POLICY candidates" in workflow
    assert "git push origin \"HEAD:${TARGET_REF}\"" in workflow
    assert "--force" not in workflow
    assert 'test "${TARGET_REF}" != main' in workflow


def test_mcp_full_suite_requires_boundary_preflight() -> None:
    workflow = MCP_WORKFLOW.read_text("utf-8")

    assert "boundary-ledger-drift:" in workflow
    assert "uses: ./.github/workflows/boundary-ledger-drift.yml" in workflow
    validate = workflow.index("  validate:")
    pytest = workflow.index("python -m pytest -q", validate)
    needs = workflow.index("needs: boundary-ledger-drift", validate)
    assert validate < needs < pytest
