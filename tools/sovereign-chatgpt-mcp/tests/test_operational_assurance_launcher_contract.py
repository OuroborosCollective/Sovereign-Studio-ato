from __future__ import annotations

import importlib
import os


def test_launcher_registers_combined_governance_and_assurance_registry(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_WORKSPACE_ROOT", str(tmp_path / "workspaces"))
    monkeypatch.setenv("SOVEREIGN_MCP_REPOSITORY", "OuroborosCollective/Sovereign-Studio-ato")
    monkeypatch.setenv("SOVEREIGN_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("SOVEREIGN_MCP_PORT", "8090")
    monkeypatch.setenv("SOVEREIGN_KAPPA_POS", "1000000")
    os.environ.pop("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", None)

    launcher = importlib.import_module("launcher")
    server = importlib.import_module("server")
    governance = importlib.import_module("operational_governance_tools")
    assurance = importlib.import_module("operational_assurance_tools")

    assert launcher.mcp is server.mcp
    names = {tool.name for tool in server.mcp._tool_manager.list_tools()}
    required = {
        "operational_skill_inventory",
        "mcp_tool_contract_registry",
        "tool_recommend_for_mission",
        "mcp_toolchain_contract_inventory",
        "mcp_toolchain_compile",
        "mcp_toolchain_validate",
        "mcp_toolchain_next_step",
        "mcp_diagnostic_chain_plan",
        "operational_assurance_skill_inventory",
        "vps_capacity_resource_pressure_assess",
        "runtime_dependency_health_matrix",
        "outbox_queue_liveness_assess",
        "scheduled_maintenance_coordinate",
        "runtime_topology_change_audit",
        "postgres_query_index_performance_assess",
        "data_integrity_invariant_audit",
        "data_repair_plan_build",
        "vector_memory_consistency_assess",
        "memory_poisoning_provenance_guard",
        "learning_pattern_lifecycle_preview",
        "data_retention_privacy_audit",
        "multi_tenant_isolation_verify",
        "mcp_schema_compatibility_audit",
        "mcp_protocol_conformance_fuzz_plan",
        "tool_permission_minimize",
        "dynamic_execution_containment_audit",
        "skill_capability_coverage_map",
        "skill_lifecycle_deprecation_preview",
        "skill_regression_benchmark",
        "tool_idempotency_verify",
        "owner_approval_policy_evaluate",
        "secret_lifecycle_rotation_assess",
        "secret_literal_triage",
        "sbom_provenance_image_signing_verify",
        "dependency_vulnerability_remediation_plan",
        "authentication_chaos_negative_test_assess",
    }
    assert required.issubset(names), sorted(required - names)

    inventory = governance.operational_skill_inventory()
    assert inventory.skillCount == 43
    assert inventory.toolCount == 48
    assurance_inventory = assurance.operational_assurance_skill_inventory()
    assert assurance_inventory.evidence["newTools"] == 27
    assert assurance_inventory.evidence["existingReusedTools"] == ["mcp_tool_contract_registry"]

    registry = governance.mcp_tool_contract_registry(include_schemas=True)
    assert registry.status == "MCP_TOOL_REGISTRY_READY"
    assert registry.toolCount == len(names)
    assert len(registry.registrySnapshotSha256) == 64
