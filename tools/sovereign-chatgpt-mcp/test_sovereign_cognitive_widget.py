from pathlib import Path
import sys

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

MCP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MCP_ROOT))

from sovereign_cognitive_widget import (
    STRICT_CSP,
    WIDGET_HTML,
    WIDGET_MANIFEST,
    WIDGET_URI,
    register_sovereign_cognitive_widget,
)


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def _status():
    return {
        "ok": True,
        "status": "RUNTIME_READY",
        "summary": "Evidence loaded.",
        "controlPlane": {"status": "BROKER_READY"},
        "agentsSdkState": "backend_endpoint_configured",
        "draftPr": {"ready": False},
    }


def test_widget_contract_is_strict_and_evidence_only() -> None:
    assert STRICT_CSP == {
        "connectDomains": [],
        "resourceDomains": [],
        "frameDomains": [],
    }
    assert WIDGET_MANIFEST["agentCount"] == 8
    assert WIDGET_MANIFEST["releaseMode"] == "draft_pr_only"
    assert WIDGET_MANIFEST["autoMerge"] is False
    assert "https://" not in WIDGET_HTML
    assert "http://" not in WIDGET_HTML
    assert "aria-live=\"polite\"" in WIDGET_HTML
    assert "sendFollowUpMessage" in WIDGET_HTML
    assert "repository_pr_status" in WIDGET_HTML


def test_widget_registers_one_resource_and_status_tool() -> None:
    mcp = FastMCP("widget-test")
    register_sovereign_cognitive_widget(
        mcp,
        read_only_annotations=READ_ONLY,
        status_provider=_status,
    )
    tools = mcp._tool_manager.list_tools()
    resources = mcp._resource_manager.list_resources()
    assert [tool.name for tool in tools] == ["sovereign_cognitive_architecture_status"]
    assert [str(resource.uri) for resource in resources] == [WIDGET_URI]
    assert tools[0].meta["ui"]["resourceUri"] == WIDGET_URI
    assert resources[0].meta["ui"]["csp"] == STRICT_CSP
