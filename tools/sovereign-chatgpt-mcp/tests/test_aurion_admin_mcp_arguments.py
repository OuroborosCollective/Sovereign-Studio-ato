"""Exercise the actual registered FastMCP call path; only the host broker is isolated."""
from __future__ import annotations

import asyncio
import copy
import importlib
import sys

import pytest

from aurion_admin_mcp_lane import (
    ALL_AURION_ADMIN_TOOLS,
    ASSET_WRITE_SCOPE,
    AUTHORING_WRITE_SCOPE,
    CONTRACTS,
    READ_SCOPE,
)


@pytest.fixture
def registered_server(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_AURION_ADMIN_MCP", "1")
    monkeypatch.setenv("AURION_ADMIN_MCP_SCOPES", " ".join((READ_SCOPE, ASSET_WRITE_SCOPE, AUTHORING_WRITE_SCOPE)))
    monkeypatch.setenv("AURION_ADMIN_MCP_WOLFRAM_ENABLED", "1")
    original = sys.modules.pop("server", None)
    try:
        yield importlib.import_module("server")
    finally:
        sys.modules.pop("server", None)
        if original is not None:
            sys.modules["server"] = original


@pytest.mark.parametrize("name,arguments,action,timeout", [
    ("aurion_admin_get_capabilities", {}, "aurion_admin_mcp_read", 120),
    ("aurion_runtime_identity", {}, "aurion_admin_mcp_read", 120),
    ("aurion_causality_status", {}, "aurion_admin_mcp_read", 120),
    ("aurion_causality_status", {"zoneId": "fixture-zone"}, "aurion_admin_mcp_read", 120),
    ("aurion_quest_template_get", {"templateId": "fixture-quest"}, "aurion_admin_mcp_read", 120),
    ("aurion_tick_receipt_get", {"zoneId": "fixture-zone", "tick": 0}, "aurion_admin_mcp_read", 120),
    ("aurion_tick_receipt_get", {"zoneId": "fixture-zone", "tick": 9007199254740993}, "aurion_admin_mcp_read", 120),
    ("aurion_quest_validate", {"templateJson": '[1, "Grüße"]'}, "aurion_admin_mcp_read", 120),
    ("aurion_context_expand_sources", {
        "capsuleId": "fixture-capsule",
        "requestedSourceIds": ["source-a", "source-b"],
        "expectedCapsuleHash": "fixture-hash",
    }, "aurion_admin_mcp_read", 120),
    ("aurion_quest_publish", {
        "proposalId": "fixture-proposal",
        "expectedPlanHash": "a" * 64,
        "confirmation": "PUBLISH_QUEST_TEMPLATE",
    }, "aurion_admin_mcp_write", 240),
])
def test_registered_calls_forward_flat_arguments_without_coercion(
    registered_server, monkeypatch: pytest.MonkeyPatch, name, arguments, action, timeout,
) -> None:
    calls = []
    original = copy.deepcopy(arguments)
    response = {"ok": False, "status": "TEST_ADAPTER_BOUNDARY_ONLY"}

    def broker_call(selected_action, payload, *, timeout):
        calls.append((selected_action, payload, timeout))
        return response

    monkeypatch.setattr(registered_server.broker, "call", broker_call)
    result = asyncio.run(registered_server.mcp._tool_manager.call_tool(name, arguments))
    assert result == response
    assert calls == [(action, {"tool_name": name, "arguments": original}, timeout)]
    assert arguments == original


def test_all_published_aurion_contracts_remain_flat(registered_server) -> None:
    manager = registered_server.mcp._tool_manager
    for name in ALL_AURION_ADMIN_TOOLS:
        tool = manager.get_tool(name)
        assert tool is not None
        assert tool.parameters == CONTRACTS[name]
        assert "kwargs" not in tool.parameters.get("properties", {})


@pytest.mark.parametrize("family", [
    "AURION_SCOPE_NOT_ENABLED_LOCALLY",
    "SOVEREIGN_OWNER_MODE_REQUIRED",
    "AURION_ADMIN_OAUTH_REJECTED",
    "AURION_ADMIN_REMOTE_ERROR",
])
def test_registered_call_preserves_authority_denials(
    registered_server, monkeypatch: pytest.MonkeyPatch, family,
) -> None:
    rejection = {"ok": False, "failureFamily": family, "mutationPerformed": False}
    monkeypatch.setattr(registered_server.broker, "call", lambda *args, **kwargs: rejection)
    result = asyncio.run(registered_server.mcp._tool_manager.call_tool("aurion_runtime_identity", {}))
    assert result == rejection


def test_mcp_protocol_lists_flat_schema_and_calls_existing_broker(
    registered_server, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    from mcp.shared.memory import create_connected_server_and_client_session

    calls = []
    rejection = {"ok": False, "failureFamily": "AURION_ADMIN_OAUTH_REJECTED", "mutationPerformed": False}

    def broker_call(action, payload, *, timeout):
        calls.append((action, payload, timeout))
        return rejection

    monkeypatch.setattr(registered_server.broker, "call", broker_call)

    async def exchange():
        async with create_connected_server_and_client_session(registered_server.mcp) as session:
            published = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert published["aurion_runtime_identity"].inputSchema == CONTRACTS["aurion_runtime_identity"]
            empty = await session.call_tool("aurion_runtime_identity", {})
            assert empty.isError is False  # Transport worked; authority remains denied in the payload.
            assert json.loads(empty.content[0].text) == rejection
            flat = await session.call_tool("aurion_tick_receipt_get", {"zoneId": "fixture-zone", "tick": 0})
            assert flat.isError is False
            assert json.loads(flat.content[0].text) == rejection

    asyncio.run(exchange())
    assert calls == [
        ("aurion_admin_mcp_read", {"tool_name": "aurion_runtime_identity", "arguments": {}}, 120),
        ("aurion_admin_mcp_read", {"tool_name": "aurion_tick_receipt_get", "arguments": {"zoneId": "fixture-zone", "tick": 0}}, 120),
    ]
