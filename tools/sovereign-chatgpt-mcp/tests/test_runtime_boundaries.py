from __future__ import annotations

from server import mcp_runtime_boundaries


def test_runtime_boundaries_report_enforced_execution_model() -> None:
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
    assert isinstance(result["active_private_admin_capabilities"], list)
