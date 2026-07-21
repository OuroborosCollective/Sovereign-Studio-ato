from __future__ import annotations

from typing import Any

import launcher
import toolchain_composition as chains


def _desired_output() -> chains.SemanticType:
    return chains.SemanticType(
        category="evidence",
        data_type="VerifiedRepositoryEvidence",
        schema_ref="sovereign://tests/repository-evidence/v1",
    )


def _compile_read_chain() -> chains.ToolChainProposalResult:
    return chains.mcp_toolchain_compile(
        mission_summary="Inspect the current repository and CI evidence before proposing a safe repair.",
        required_capabilities=["repository", "ci"],
        desired_end_state=_desired_output(),
        allowed_effects=["read"],
        required_evidence=["exact_revision", "ci"],
        max_nodes=5,
    )


def _required_context_keys(chain: chains.McpToolChain, node_id: str) -> list[str]:
    node = chain.nodes[node_id]
    return sorted(
        mapping.context_key
        for mapping in node.input_mappings.values()
        if isinstance(mapping, chains.RuntimeContextMapping)
    )


def test_toolchain_tools_are_registered_with_strict_output_schemas() -> None:
    registered = {tool.name: tool for tool in launcher.mcp._tool_manager.list_tools()}
    expected = {
        "mcp_toolchain_contract_inventory",
        "mcp_toolchain_compile",
        "mcp_toolchain_validate",
        "mcp_toolchain_next_step",
        "mcp_diagnostic_chain_plan",
    }

    assert expected.issubset(registered)
    for name in expected:
        tool = registered[name]
        assert tool.output_schema["type"] == "object"
        assert tool.output_schema["required"]
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False


def test_compile_creates_non_executing_hash_bound_valid_chain() -> None:
    result = _compile_read_chain()
    chain = result.proposal.initial_pipeline
    validation = chains.mcp_toolchain_validate(chain)

    assert result.status in {"MCP_TOOLCHAIN_PROPOSED", "MCP_TOOLCHAIN_PROPOSAL_INCOMPLETE"}
    assert chain.auto_execute is False
    assert chain.allowed_effects == ["read"]
    assert chain.nodes
    assert all(node.effect == "read" for node in chain.nodes.values())
    assert all(node.contract_sha256 for node in chain.nodes.values())
    assert all(node.output_semantic_type.schema_ref.startswith("mcp://tool/") for node in chain.nodes.values())
    assert validation.ok is True, validation.findings
    assert validation.status == "MCP_TOOLCHAIN_VALID"
    assert validation.chainSha256 == chain.chain_sha256
    assert validation.executionOrder[0] == chain.entry_node_id


def test_contract_drift_and_chain_tampering_fail_closed() -> None:
    chain = _compile_read_chain().proposal.initial_pipeline
    payload = chain.model_dump(mode="json")
    first_node_id = payload["entry_node_id"]
    payload["nodes"][first_node_id]["contract_sha256"] = "0" * 64
    tampered = chains.McpToolChain.model_validate(payload)

    validation = chains.mcp_toolchain_validate(tampered)
    families = {item["family"] for item in validation.findings}

    assert validation.ok is False
    assert "TOOLCHAIN_TOOL_CONTRACT_DRIFT" in families
    assert "TOOLCHAIN_HASH_MISMATCH" in families


def test_next_step_requires_explicit_bindings_before_returning_ready_node() -> None:
    chain = _compile_read_chain().proposal.initial_pipeline
    entry = chain.entry_node_id
    required_keys = _required_context_keys(chain, entry)

    blocked = chains.mcp_toolchain_next_step(chain=chain)
    ready = chains.mcp_toolchain_next_step(
        chain=chain,
        available_runtime_context_keys=required_keys,
    )

    if required_keys:
        assert blocked.ok is False
        assert blocked.status == "MCP_TOOLCHAIN_WAITING_FOR_BINDINGS"
        assert blocked.missingRuntimeContextKeys == required_keys
    assert ready.ok is True
    assert ready.status == "MCP_TOOLCHAIN_NODE_READY"
    assert ready.nextNode is not None
    assert ready.nextNode["nodeId"] == entry
    assert ready.nextNode["executeAutomatically"] is False


def test_external_write_chain_requires_owner_approval_and_never_executes() -> None:
    result = chains.mcp_toolchain_compile(
        mission_summary="Prepare the already reviewed pull request merge as an explicitly owner-governed step.",
        required_capabilities=["repository", "release", "ownership"],
        desired_end_state=chains.SemanticType(
            category="deployment",
            data_type="MergeEvidence",
            schema_ref="sovereign://tests/merge-evidence/v1",
        ),
        allowed_effects=["external-write"],
        required_evidence=["exact_revision", "green_checks", "owner_approval"],
        preferred_tools=["repository_merge_pr"],
        max_nodes=1,
    )
    chain = result.proposal.initial_pipeline
    entry = chain.entry_node_id
    node = chain.nodes[entry]
    required_keys = _required_context_keys(chain, entry)

    waiting = chains.mcp_toolchain_next_step(
        chain=chain,
        available_runtime_context_keys=required_keys,
    )
    approved = chains.mcp_toolchain_next_step(
        chain=chain,
        available_runtime_context_keys=required_keys,
        approved_node_ids=[entry],
    )

    assert node.effect == "external-write"
    assert node.requires_owner_approval is True
    assert waiting.ok is False
    assert waiting.status == "MCP_TOOLCHAIN_WAITING_FOR_OWNER"
    assert waiting.ownerApprovalRequired is True
    assert approved.ok is True
    assert approved.status == "MCP_TOOLCHAIN_NODE_READY"
    assert approved.nextNode is not None
    assert approved.nextNode["executeAutomatically"] is False


def test_failure_stops_chain_and_requires_new_evidence_replan() -> None:
    chain = _compile_read_chain().proposal.initial_pipeline
    result = chains.mcp_toolchain_next_step(
        chain=chain,
        failed_node_id=chain.entry_node_id,
        failure_family="CI_CONTRACT_MISMATCH",
    )

    assert result.ok is False
    assert result.status == "MCP_TOOLCHAIN_REPLAN_REQUIRED"
    assert result.nextNode is None
    assert any(item["family"] == "CI_CONTRACT_MISMATCH" for item in result.findings)
    assert "compile or validate a revised chain; do not retry automatically" in result.nextActions


def test_diagnostic_plan_carries_bounded_are_style_stop_policy() -> None:
    result = chains.mcp_diagnostic_chain_plan(
        failure_family="MCP_TOOL_OUTPUT_SCHEMA_VIOLATION",
        capabilities=["mcp", "repository", "ci"],
        evidence_summary="A registered tool returned an output that did not satisfy its published schema.",
        allowed_effects=["read"],
        max_nodes=6,
    )
    metadata: dict[str, Any] = result.proposal.initial_pipeline.expected_output.metadata

    assert result.proposal.initial_pipeline.auto_execute is False
    assert metadata["stopOnFailureFamilyChange"] is True
    assert metadata["requireNewEvidenceForRetry"] is True
    assert metadata["allowAutomaticFix"] is False
    assert metadata["maxRepeatedFailureCount"] == 2
