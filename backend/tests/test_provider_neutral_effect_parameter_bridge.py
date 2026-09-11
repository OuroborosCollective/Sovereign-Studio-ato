"""Regression for canonical provider-neutral parameters crossing into real tools."""

from __future__ import annotations

from agent_runtime.provider_neutral_runtime import (
    PolicyRule,
    ProviderNeutralRuntimeKernel,
    RuntimeContext,
    descriptor_from_registry,
)
from agent_runtime.tools.base import ToolRegistry
from agent_runtime.tools.janitor_tool import DynamicJanitorTool


REVISION = "a" * 40


def test_provider_neutral_janitor_receives_json_native_array_parameters(tmp_path) -> None:
    """Frozen evidence arrays must become lists again before the effect adapter."""
    (tmp_path / "README.md").write_text("# Provider-neutral bridge\n", encoding="utf-8")

    registry = ToolRegistry()
    registry.register(
        DynamicJanitorTool(),
        effect="workspace-write",
        capabilities=("repository", "test"),
    )
    kernel = ProviderNeutralRuntimeKernel(
        policy_rules=(
            PolicyRule(
                "allow-janitor-scan",
                "ALLOW",
                "bounded regression scan",
                tool_name="janitor",
            ),
        )
    )

    execution = kernel.execute_registered_tool(
        context=RuntimeContext(
            run_id="run-provider-neutral-array-regression",
            owner_id="test-owner",
            revision=REVISION,
            tick=0,
            epoch_ms=0,
            call_id="call-janitor-array",
        ),
        tool=descriptor_from_registry(registry, "janitor"),
        parameters={
            "mode": "scan",
            "family": "provider neutral parameter bridge",
            "paths": ["README.md"],
            "maxFindings": 10,
            "maxFiles": 10,
            "includeDocs": True,
            "explainWithLocalModel": False,
        },
        registry=registry,
        workspace_path=str(tmp_path),
    )

    assert execution.status == "done"
    assert execution.result["status"] == "done"
    assert execution.result["metadata"]["scannedFiles"] == 1
