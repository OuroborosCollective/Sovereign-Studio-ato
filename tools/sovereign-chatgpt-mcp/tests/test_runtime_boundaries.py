from __future__ import annotations

from server import mcp_runtime_boundaries


def test_runtime_boundaries_report_enforced_execution_model(monkeypatch) -> None:
    for name in (
        "SOVEREIGN_MCP_PRIVATE_OWNER_MODE",
        "SOVEREIGN_MCP_ENABLE_DB_WRITES",
        "SOVEREIGN_MCP_ENABLE_DEPLOY",
        "SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS",
        "SOVEREIGN_MCP_ENABLE_ADMIN_SQL",
        "SOVEREIGN_MCP_ENABLE_MAIN_PUSH",
        "SOVEREIGN_MCP_ENABLE_PR_MERGE",
        "SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL",
        "SOVEREIGN_MCP_ENABLE_SELF_UPDATE",
        "SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE",
        "SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE",
    ):
        monkeypatch.setenv(name, "1")

    result = mcp_runtime_boundaries()

    assert result["ok"] is True
    assert result["status"] == "RUNTIME_BOUNDARIES_VERIFIED"
    assert result["node_build_execution"] == "github_actions_only"
    assert result["local_node_dependency_install_allowed"] is False
    assert result["host_mutation_execution"] == "host_command_queue_only"
    assert result["direct_broker_socket_mutation_allowed"] is False
    assert result["generic_shell_available"] is False
    assert result["workspace_changes_end_at_draft_pr"] is True
    assert result["owner_protected_input_execution"] == "authenticated_owner_ui_only"
    assert result["llm_can_receive_protected_values"] is False
    assert result["raw_payment_card_input_allowed"] is False
    assert result["private_owner_mode_enabled"] is True
    assert set(result["active_private_admin_capabilities"]) == {
        "private_owner_mode",
        "postgres_write",
        "backend_deploy",
        "data_backfill",
        "postgres_admin_sql",
        "repository_push_main",
        "repository_merge_pr",
        "repository_workflow_dispatch",
        "repository_rerun_failed_workflows",
        "mcp_self_update",
        "managed_compose_write",
        "patchmon_patch_write",
    }
