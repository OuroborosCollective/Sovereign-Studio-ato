from __future__ import annotations

import pytest

from aurion_admin_mcp_lane import (
    ALL_AURION_ADMIN_TOOLS,
    AURION_TOOL_HANDLER_MAP,
    AURION_ADMIN_MCP_DEFAULT_RESOURCE_URL,
    AURION_ADMIN_MCP_PATH,
    AURION_MAX_GLB_BASE64_CHARS,
    AURION_SOURCE_FILE_SHA256,
    AUTHORING_WRITE_SCOPE,
    ASSET_WRITE_SCOPE,
    CONTRACTS,
    READ_SCOPE,
    AurionAdminMcpRuntime,
    exposed_tool_names,
    required_scope_for_tool,
    tool_mode,
)


EXPECTED_TOOLS = (
    "aurion_admin_get_capabilities",
    "aurion_admin_get_world_overview",
    "aurion_admin_wolfram_status",
    "aurion_admin_wolfram_compute",
    "aurion_admin_wolfram_hints",
    "aurion_admin_wolfram_alpha_results",
    "aurion_admin_wolfram_alpha_context",
    "aurion_admin_wolfram_canary",
    "aurion_admin_os3a_source",
    "aurion_admin_os3a_search",
    "aurion_admin_os3a_gap_scan",
    "aurion_admin_glb_plan",
    "aurion_admin_glb_import",
    "aurion_admin_glb_catalog",
    "aurion_admin_glb_assign",
    "aurion_admin_os3a_plan",
    "aurion_admin_os3a_apply",
    "aurion_admin_os3a_gap_reconcile",
    "aurion_admin_gds_status",
    "aurion_admin_gds_plan",
    "aurion_admin_gds_apply",
    "aurion_admin_named_npc_visual_plan",
    "aurion_admin_named_npc_visual_apply",
    "aurion_admin_world_design_read",
    "aurion_admin_world_design_plan",
    "aurion_admin_world_design_apply",
    "aurion_admin_dungeon_design_read",
    "aurion_admin_dungeon_design_plan",
    "aurion_admin_dungeon_design_apply",
    "aurion_quest_status",
    "aurion_quest_template_list",
    "aurion_quest_template_get",
    "aurion_quest_validate",
    "aurion_quest_instance_explain",
    "aurion_quest_replay",
    "aurion_quest_draft_propose",
    "aurion_quest_publish_plan",
    "aurion_quest_publish",
    "aurion_context_inspect_capsule",
    "aurion_context_replay_capsule",
    "aurion_context_expand_sources",
    "aurion_context_get_episode",
    "aurion_context_eval_summary",
    "aurion_causality_status",
    "aurion_assurance_status",
    "aurion_tick_receipt_get",
    "aurion_tick_explain",
    "aurion_tick_replay",
    "aurion_replay_range",
    "aurion_runtime_identity",
    "aurion_recovery_plan",
    "aurion_donor_ledger",
    "aurion_donor_capability_explain",
)

WRITE_TOOLS = {
    "aurion_admin_glb_import",
    "aurion_admin_glb_assign",
    "aurion_admin_os3a_apply",
    "aurion_admin_os3a_gap_reconcile",
    "aurion_admin_gds_apply",
    "aurion_admin_named_npc_visual_apply",
    "aurion_admin_world_design_apply",
    "aurion_admin_dungeon_design_apply",
    "aurion_quest_draft_propose",
    "aurion_quest_publish",
}


def test_exact_aurion_tool_contract_inventory() -> None:
    assert ALL_AURION_ADMIN_TOOLS == EXPECTED_TOOLS
    assert len(EXPECTED_TOOLS) == 53
    assert set(CONTRACTS) == set(EXPECTED_TOOLS)


def test_every_registered_tool_has_an_authoritative_handler_mapping() -> None:
    allowed_sources = {
        "server/adminMcp.ts",
        "server/aurionAuthoringPersistence.ts",
        "server/chatgptCausalityBridge.ts",
        "server/gameDevelopmentStudioProduction.ts",
        "server/gameDevelopmentStudioRuntime.ts",
        "server/glbImportPlan.ts",
        "server/glbImportStore.ts",
        "server/namedNpcVisualAssignment.ts",
        "server/openSource3dFallback.ts",
        "server/automaticGlbFallback.ts",
        "server/questCompiler/adminService.ts",
        "server/questCompiler/validator.ts",
        "server/wolframCag.ts",
        "server/worldContext/service.ts",
    }
    assert set(AURION_TOOL_HANDLER_MAP) == set(EXPECTED_TOOLS)
    assert all(value.split("::", 1)[0] in allowed_sources for value in AURION_TOOL_HANDLER_MAP.values())


def test_scope_and_mutation_split_matches_aurion_contract() -> None:
    assert all(required_scope_for_tool(name) == READ_SCOPE for name in EXPECTED_TOOLS if name not in {
        "aurion_admin_wolfram_compute",
        "aurion_admin_wolfram_hints",
        "aurion_admin_wolfram_alpha_results",
        "aurion_admin_wolfram_alpha_context",
        "aurion_admin_wolfram_canary",
        "aurion_admin_glb_plan",
        "aurion_admin_glb_import",
        "aurion_admin_glb_catalog",
        "aurion_admin_glb_assign",
        "aurion_admin_os3a_plan",
        "aurion_admin_os3a_apply",
        "aurion_admin_os3a_gap_reconcile",
        "aurion_admin_gds_status",
        "aurion_admin_gds_plan",
        "aurion_admin_gds_apply",
        "aurion_admin_named_npc_visual_plan",
        "aurion_admin_named_npc_visual_apply",
        "aurion_admin_world_design_plan",
        "aurion_admin_world_design_apply",
        "aurion_admin_dungeon_design_plan",
        "aurion_admin_dungeon_design_apply",
        "aurion_quest_draft_propose",
        "aurion_quest_publish_plan",
        "aurion_quest_publish",
    })
    assert all(required_scope_for_tool(name) == ASSET_WRITE_SCOPE for name in {
        "aurion_admin_glb_plan",
        "aurion_admin_glb_import",
        "aurion_admin_glb_catalog",
        "aurion_admin_glb_assign",
        "aurion_admin_os3a_plan",
        "aurion_admin_os3a_apply",
        "aurion_admin_os3a_gap_reconcile",
        "aurion_admin_gds_status",
        "aurion_admin_gds_plan",
        "aurion_admin_gds_apply",
        "aurion_admin_named_npc_visual_plan",
        "aurion_admin_named_npc_visual_apply",
    })
    assert all(required_scope_for_tool(name) == AUTHORING_WRITE_SCOPE for name in {
        "aurion_admin_world_design_plan",
        "aurion_admin_world_design_apply",
        "aurion_admin_dungeon_design_plan",
        "aurion_admin_dungeon_design_apply",
        "aurion_quest_draft_propose",
        "aurion_quest_publish",
    })
    assert all(tool_mode(name) == "write" for name in WRITE_TOOLS)
    assert all(tool_mode(name) == "read" for name in set(EXPECTED_TOOLS) - WRITE_TOOLS)


def test_wolfram_is_read_only_but_runtime_conditioned() -> None:
    wolfram = {
        "aurion_admin_wolfram_compute",
        "aurion_admin_wolfram_hints",
        "aurion_admin_wolfram_alpha_results",
        "aurion_admin_wolfram_alpha_context",
        "aurion_admin_wolfram_canary",
    }
    assert all(required_scope_for_tool(name) == READ_SCOPE for name in wolfram)
    assert all(tool_mode(name) == "read" for name in wolfram)
    assert len(exposed_tool_names(frozenset({READ_SCOPE}), wolfram_enabled=False)) == 30
    assert len(exposed_tool_names(frozenset({READ_SCOPE}), wolfram_enabled=True)) == 35
    assert len(exposed_tool_names(frozenset({READ_SCOPE, ASSET_WRITE_SCOPE}), wolfram_enabled=False)) == 42
    assert len(exposed_tool_names(frozenset({READ_SCOPE, AUTHORING_WRITE_SCOPE}), wolfram_enabled=False)) == 36
    assert len(exposed_tool_names(frozenset({READ_SCOPE, ASSET_WRITE_SCOPE, AUTHORING_WRITE_SCOPE}), wolfram_enabled=True)) == 53


def test_contract_structural_guards_match_aurion_source() -> None:
    assert CONTRACTS["aurion_admin_glb_plan"]["properties"]["contentBase64"]["maxLength"] == AURION_MAX_GLB_BASE64_CHARS
    assert CONTRACTS["aurion_admin_glb_import"]["properties"]["contentBase64"]["maxLength"] == AURION_MAX_GLB_BASE64_CHARS
    assert CONTRACTS["aurion_admin_world_design_plan"]["properties"]["placements"]["maxItems"] == 256
    assert CONTRACTS["aurion_admin_dungeon_design_plan"]["properties"]["rooms"]["minItems"] == 4
    assert CONTRACTS["aurion_admin_dungeon_design_plan"]["properties"]["rooms"]["maxItems"] == 9
    assert CONTRACTS["aurion_admin_os3a_search"]["properties"]["tier"]["enum"] == ["phone", "tablet", "desktop"]
    assert CONTRACTS["aurion_admin_os3a_apply"]["properties"]["confirmation"]["const"] == "ADMIT_OS3A_FALLBACK"
    assert CONTRACTS["aurion_admin_gds_apply"]["properties"]["confirmation"]["const"] == "APPLY_TO_LIVE_AURION"
    assert CONTRACTS["aurion_admin_world_design_apply"]["properties"]["confirmation"]["const"] == "APPLY_WORLD_DESIGN"
    assert CONTRACTS["aurion_admin_dungeon_design_apply"]["properties"]["confirmation"]["const"] == "PUBLISH_DUNGEON"
    assert CONTRACTS["aurion_quest_publish"]["properties"]["confirmation"]["const"] == "PUBLISH_QUEST_TEMPLATE"


def test_source_fingerprints_are_pinned_to_uploaded_aurion_snapshot() -> None:
    assert AURION_SOURCE_FILE_SHA256 == {
        "AURION_ADMIN_MCP_CONTRACT.md": "183b55385593b3e17753f14a74fec6265916840b774e53b7003a9e6e80fcece4",
        "server/adminMcp.ts": "e818fa21b60b1cd6211c13f9275003e457d451dba0e14472c7585ce0995edcad",
        "server/adminMcpProtocol.ts": "173610cbc1705e3d1ad6f1e390df4a38a1c1202e0652e7d0027274c3beba4d5c",
        "shared/aurionAuthoringContract.ts": "eebcb79b0eaca0daaefaf7fa6205121ba545c9b9afaad2edfe1a3ca95c5ae432",
    }


def test_server_registers_the_existing_aurion_tool_surface_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib
    import sys

    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_AURION_ADMIN_MCP", "1")
    monkeypatch.setenv("AURION_ADMIN_MCP_SCOPES", READ_SCOPE)
    monkeypatch.setenv("AURION_ADMIN_MCP_WOLFRAM_ENABLED", "0")
    sys.modules.pop("server", None)
    server = importlib.import_module("server")
    registered = {tool.name for tool in server.mcp._tool_manager.list_tools()}
    expected = set(exposed_tool_names(frozenset({READ_SCOPE}), wolfram_enabled=False))
    assert expected <= registered
    assert "aurion_admin_glb_import" not in registered


def test_resource_url_is_hard_bound_to_existing_aurion_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = AurionAdminMcpRuntime()
    assert runtime._resource_url() == AURION_ADMIN_MCP_DEFAULT_RESOURCE_URL
    monkeypatch.setenv("AURION_ADMIN_MCP_RESOURCE_URL", "https://example.invalid/admin-mcp")
    with pytest.raises(RuntimeError, match="exactly"):
        runtime._resource_url()
    monkeypatch.setenv("AURION_ADMIN_MCP_RESOURCE_URL", "https://arelogic.space/mcp")
    with pytest.raises(RuntimeError, match="exactly"):
        runtime._resource_url()
    assert AURION_ADMIN_MCP_PATH == "/admin-mcp"


def test_missing_token_fails_closed_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AURION_ADMIN_MCP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("AURION_ADMIN_MCP_ACCESS_TOKEN_FILE", raising=False)
    runtime = AurionAdminMcpRuntime()
    result = runtime.call(
        tool_name="aurion_runtime_identity",
        arguments={},
        require_write=False,
    )
    assert result["ok"] is False
    assert result["blocker"] == "AURION_ADMIN_ACCESS_TOKEN_MISSING"
    assert result["secretValuesReturned"] is False


def test_write_lane_requires_private_owner_mode_before_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", raising=False)
    monkeypatch.setenv("AURION_ADMIN_MCP_SCOPES", f"{READ_SCOPE} {ASSET_WRITE_SCOPE}")
    runtime = AurionAdminMcpRuntime()
    result = runtime.call(
        tool_name="aurion_admin_gds_apply",
        arguments={},
        require_write=True,
    )
    assert result["ok"] is False
    assert result["blocker"] == "SOVEREIGN_OWNER_MODE_REQUIRED"


def test_broker_mode_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    runtime = AurionAdminMcpRuntime()
    result = runtime.call(
        tool_name="aurion_runtime_identity",
        arguments={},
        require_write=True,
    )
    assert result["ok"] is False
    assert result["blocker"] == "AURION_BROKER_PATH_MISMATCH"
