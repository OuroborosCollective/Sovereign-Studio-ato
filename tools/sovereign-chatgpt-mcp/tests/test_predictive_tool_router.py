from __future__ import annotations

from predictive_tool_router import perceive_mission, predict_tool_route


def _tool(name: str, description: str, capabilities: list[str], effect: str) -> dict:
    return {
        "name": name,
        "description": description,
        "capabilities": capabilities,
        "effect": effect,
        "annotations": {"readOnlyHint": effect == "read", "destructiveHint": False, "idempotentHint": True},
        "parameters": {"properties": {}},
        "contractSha256": (name + "0" * 64)[:64],
    }


def _catalog() -> list[dict]:
    return [
        _tool("repository_revision_resolve", "Resolve exact repository and CI revision identity.", ["repository", "ci"], "read"),
        _tool("repository_read_file", "Read one repository file and return SHA-256.", ["repository"], "read"),
        _tool("repository_apply_search_replace", "Patch an exact file with stale-SHA protection.", ["repository", "configuration"], "workspace-write"),
        _tool("repository_hash_bound_replace", "Replace exact blob content with revision binding.", ["repository", "security"], "workspace-write"),
        _tool("repository_mirror_diff_report", "Verify canonical and runtime mirror parity.", ["repository", "compliance"], "read"),
        _tool("repository_run_check", "Run continuity and repository validation checks.", ["repository", "ci"], "workspace-write"),
        _tool("repository_create_draft_pr", "Commit, push and create a Draft PR.", ["repository", "ci"], "external-write"),
        _tool("mcp_schema_compatibility_audit", "Compare MCP schema surfaces.", ["repository", "configuration", "compliance"], "read"),
    ]


def test_ledger_publication_perceives_required_functional_stages() -> None:
    perception = perceive_mission(
        "Append a checkpoint to byte-identical JSONL ledgers, validate and publish a Draft PR.",
        ["file SHA", "mirror parity", "continuity check", "Draft PR head"],
    )
    assert set(perception.stages) >= {
        "revision-identity",
        "file-read",
        "ledger-write",
        "mirror-verification",
        "validation",
        "publication",
    }


def test_ledger_route_uses_exact_tools_not_generic_schema_audit() -> None:
    result = predict_tool_route(
        catalog=_catalog(),
        mission_summary="Read both ledgers, append exactly once, verify mirrors, run checks and publish the Draft PR.",
        required_capabilities={"repository", "configuration", "compliance", "ci"},
        allowed_effects={"read", "workspace-write", "external-write"},
        required_evidence=["file SHA", "mirror parity", "continuity validator", "Draft PR head"],
        excluded_tools=set(),
        max_tools=8,
        historical_bonuses={},
    )
    names = [item["name"] for item in result["selectedTools"]]
    assert result["routeComplete"] is True
    for required in (
        "repository_revision_resolve",
        "repository_read_file",
        "repository_mirror_diff_report",
        "repository_run_check",
        "repository_create_draft_pr",
    ):
        assert required in names
    assert any(name in names for name in ("repository_apply_search_replace", "repository_hash_bound_replace"))
    assert "mcp_schema_compatibility_audit" not in names


def test_history_only_reorders_functionally_eligible_candidates() -> None:
    result = predict_tool_route(
        catalog=_catalog(),
        mission_summary="Patch the exact repository file using a revision-bound replacement.",
        required_capabilities={"repository"},
        allowed_effects={"workspace-write", "read"},
        required_evidence=["exact blob SHA"],
        excluded_tools=set(),
        max_tools=4,
        historical_bonuses={
            "repository_apply_search_replace": 5,
            "repository_hash_bound_replace": 80,
            "mcp_schema_compatibility_audit": 80,
        },
    )
    names = [item["name"] for item in result["selectedTools"]]
    writes = [name for name in names if name in {"repository_hash_bound_replace", "repository_apply_search_replace"}]
    assert writes[0] == "repository_hash_bound_replace"
    assert "mcp_schema_compatibility_audit" not in names
