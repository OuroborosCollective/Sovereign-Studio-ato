from __future__ import annotations

from pathlib import Path


def test_continuity_is_advisory_in_mcp_validation_workflow() -> None:
    repo = Path(__file__).resolve().parents[3]
    workflow = (repo / ".github/workflows/sovereign-chatgpt-mcp.yml").read_text(encoding="utf-8")
    assert "assert continuity_read.status == 'CONTINUITY_CONTEXT_BOUND'" not in workflow
    assert "Continuity provenance is advisory" in workflow
