from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sovereign_rescue_widget import (
    OFFER,
    RESOURCE_META,
    TOOL_META,
    WIDGET_HTML,
    WIDGET_URI,
    register_sovereign_rescue_widget,
)


def test_rescue_widget_keeps_auth_checkout_and_secrets_external() -> None:
    assert "openExternal" in WIDGET_HTML
    assert "type=\"password\"" not in WIDGET_HTML
    assert "github_pat_" not in WIDGET_HTML
    assert RESOURCE_META["ui"]["csp"]["connectDomains"] == []
    assert RESOURCE_META["openai/widgetCSP"]["redirect_domains"] == [
        "https://chat.arelorian.de"
    ]
    assert TOOL_META["ui"]["resourceUri"] == WIDGET_URI


def test_rescue_offer_is_read_only_and_never_grants_entitlement() -> None:
    assert OFFER["mutationPerformed"] is False
    assert OFFER["entitlementGranted"] is False
    assert OFFER["secretValuesReturned"] is False
    assert OFFER["paid"]["serverSideEntitlementRequired"] is True
    assert OFFER["paid"]["autoMerge"] is False
    assert len(OFFER["supportedFailureFamilies"]) == 3


def test_rescue_tool_registers_current_apps_sdk_metadata() -> None:
    mcp = FastMCP("rescue-widget-test")
    register_sovereign_rescue_widget(
        mcp,
        read_only_annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    tools = asyncio.run(mcp.list_tools())
    assert [tool.name for tool in tools] == ["sovereign_rescue_offer"]
    assert tools[0].meta["ui"]["resourceUri"] == WIDGET_URI
    assert tools[0].annotations.readOnlyHint is True
