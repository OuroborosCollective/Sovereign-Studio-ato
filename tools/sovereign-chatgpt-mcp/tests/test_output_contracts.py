from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from output_contracts import (
    ExternalWriteOutput,
    ToolOutputEnvelope,
    install_output_contracts,
)


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
EXTERNAL_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)


@dataclass(frozen=True)
class StrictResult:
    ok: bool
    status: str
    count: int


def _tool(mcp: FastMCP, name: str):
    return next(tool for tool in mcp._tool_manager.list_tools() if tool.name == name)


def test_legacy_read_tool_receives_compatible_output_contract() -> None:
    mcp = FastMCP("output-contract-read-test")

    @mcp.tool(annotations=READ_ONLY)
    def legacy_read() -> dict[str, Any]:
        return {"status": "VERIFIED", "value": 7}

    result = install_output_contracts(mcp)
    tool = _tool(mcp, "legacy_read")
    payload = tool.fn()
    converted = asyncio.run(tool.run({}, convert_result=True))

    assert result["missingOutputSchemaCount"] == 0
    assert tool.fn_metadata.output_model is ToolOutputEnvelope
    assert tool.output_schema["type"] == "object"
    assert set(ToolOutputEnvelope.model_fields) <= set(tool.output_schema["required"])
    assert payload["value"] == 7
    assert payload["ok"] is True
    assert payload["status"] == "VERIFIED"
    assert payload["mutationPerformed"] is False
    assert payload["secretValuesReturned"] is False
    assert isinstance(converted, tuple)
    assert converted[1]["value"] == 7
    assert converted[1]["schemaVersion"] == "sovereign.tool-output-envelope.v1"


def test_external_write_tool_receives_stricter_effect_and_readback_contract() -> None:
    mcp = FastMCP("output-contract-write-test")

    @mcp.tool(annotations=EXTERNAL_WRITE)
    async def merge_pr() -> dict[str, Any]:
        return {
            "status": "MERGED",
            "pr_number": 901,
            "owner_approved": True,
            "expected_head_sha": "a" * 40,
            "merge_commit_sha": "b" * 40,
        }

    install_output_contracts(mcp)
    tool = _tool(mcp, "merge_pr")
    payload = asyncio.run(tool.fn())
    converted = asyncio.run(tool.run({}, convert_result=True))

    assert tool.fn_metadata.output_model is ExternalWriteOutput
    assert set(ExternalWriteOutput.model_fields) <= set(tool.output_schema["required"])
    assert payload["operationId"] == "901"
    assert payload["requestedEffect"] == "external-write"
    assert payload["observedEffect"] == "external-write"
    assert payload["mutationPerformed"] is True
    assert payload["ownerApproved"] is True
    assert payload["expectedRevision"] == "a" * 40
    assert payload["actualRevision"] == "b" * 40
    assert payload["readbackVerified"] is False
    assert isinstance(converted, tuple)
    assert converted[1]["operationId"] == "901"
    assert converted[1]["observedEffect"] == "external-write"


def test_widget_result_keeps_content_and_receives_structured_contract() -> None:
    mcp = FastMCP("output-contract-widget-test")

    @mcp.tool(annotations=EXTERNAL_WRITE, structured_output=True)
    def owner_widget() -> types.CallToolResult:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="Owner request created")],
            structuredContent={"status": "REQUEST_CREATED", "request_id": "request-1"},
            _meta={"widget": "owner-input"},
        )

    install_output_contracts(mcp)
    tool = _tool(mcp, "owner_widget")
    result = tool.fn()
    converted = asyncio.run(tool.run({}, convert_result=True))

    assert isinstance(result, types.CallToolResult)
    assert result.content[0].text == "Owner request created"
    assert result.meta == {"widget": "owner-input"}
    assert result.structuredContent is not None
    assert result.structuredContent["operationId"] == "request-1"
    assert result.structuredContent["requestedEffect"] == "external-write"
    assert result.structuredContent["secretValuesReturned"] is False
    assert isinstance(converted, types.CallToolResult)
    assert converted.structuredContent is not None
    assert converted.structuredContent["operationId"] == "request-1"


def test_existing_strict_output_schema_is_preserved_and_install_is_idempotent() -> None:
    mcp = FastMCP("output-contract-strict-test")

    @mcp.tool(annotations=READ_ONLY)
    def strict_tool() -> StrictResult:
        return StrictResult(ok=True, status="READY", count=1)

    tool = _tool(mcp, "strict_tool")
    original_fn = tool.fn
    original_schema = dict(tool.output_schema)

    first = install_output_contracts(mcp)
    second = install_output_contracts(mcp)

    assert first["strictToolCount"] == 1
    assert second["strictToolCount"] == 1
    assert tool.fn is original_fn
    assert tool.output_schema == original_schema


def test_full_launcher_registry_has_no_missing_output_schema() -> None:
    import launcher

    tools = list(launcher.mcp._tool_manager.list_tools())
    report = launcher.OUTPUT_CONTRACT_INSTALLATION
    missing = [tool.name for tool in tools if not getattr(tool, "output_schema", None)]
    weak = [
        tool.name
        for tool in tools
        if not isinstance(tool.output_schema.get("required"), list)
        or not tool.output_schema["required"]
    ]

    assert tools
    assert report["ok"] is True
    assert report["toolCount"] == len(tools)
    assert report["missingOutputSchemaCount"] == 0
    assert missing == []
    assert weak == []
