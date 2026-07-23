import asyncio
from pathlib import Path
import sys

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

MCP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(MCP_ROOT))

from sovereign_cognitive_widget import (
    STRICT_CSP,
    WIDGET_DOMAIN,
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
        "agentsSdkState": "RUNNING",
        "controllerRuns": {
            "ok": True,
            "status": "CONTROLLER_EVIDENCE_READY",
            "runs": [
                {
                    "runId": "run-0123456789abcdef0123456789abcdef",
                    "status": "RUNNING",
                    "nextAction": "WAIT_FOR_AGENT",
                }
            ],
            "latestRun": {
                "run": {
                    "runId": "run-0123456789abcdef0123456789abcdef",
                    "status": "RUNNING",
                    "nextAction": "WAIT_FOR_AGENT",
                },
                "tasks": [],
                "events": [
                    {
                        "agentId": "dispatcher",
                        "status": "RUNNING",
                        "summary": "Dispatcher erstellt den belegten Arbeitsplan.",
                    }
                ],
                "failures": [],
                "approvals": [],
            },
        },
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
    assert 'id="run-events"' in WIDGET_HTML
    assert 'id="recent-runs"' in WIDGET_HTML
    assert 'id="refresh-runs"' in WIDGET_HTML
    assert "sovereign_cognitive_architecture_status erneut" in WIDGET_HTML
    assert WIDGET_URI == "ui://sovereign/dev_dashboard.v2.html"
    assert WIDGET_DOMAIN == "https://sovereign-backend.arelorian.de"


def test_widget_registers_one_resource_and_status_tool() -> None:
    mcp = FastMCP("widget-test")
    register_sovereign_cognitive_widget(
        mcp,
        read_only_annotations=READ_ONLY,
        status_provider=_status,
    )
    tools = mcp._tool_manager.list_tools()
    resources = mcp._resource_manager.list_resources()
    listed_tools = asyncio.run(mcp.list_tools())
    listed_resources = asyncio.run(mcp.list_resources())
    read_contents = list(asyncio.run(mcp.read_resource(WIDGET_URI)))

    assert [tool.name for tool in tools] == ["sovereign_cognitive_architecture_status"]
    assert [str(resource.uri) for resource in resources] == [WIDGET_URI]
    assert tools[0].meta["ui"]["resourceUri"] == WIDGET_URI
    assert tools[0].output_schema is not None
    assert tools[0].output_schema["type"] == "object"
    assert "manifest" in tools[0].output_schema["properties"]
    assert listed_tools[0].outputSchema == tools[0].output_schema

    assert resources[0].meta["ui"]["csp"] == STRICT_CSP
    assert resources[0].meta["ui"]["domain"] == WIDGET_DOMAIN
    assert resources[0].meta["openai/widgetDomain"] == WIDGET_DOMAIN
    assert listed_resources[0].meta["ui"]["domain"] == WIDGET_DOMAIN
    assert listed_resources[0].meta["openai/widgetDomain"] == WIDGET_DOMAIN
    serialized_resource = listed_resources[0].model_dump(by_alias=True)
    assert serialized_resource["_meta"]["ui"]["domain"] == WIDGET_DOMAIN
    assert serialized_resource["_meta"]["openai/widgetDomain"] == WIDGET_DOMAIN
    assert read_contents[0].meta["ui"]["domain"] == WIDGET_DOMAIN
    assert read_contents[0].meta["openai/widgetDomain"] == WIDGET_DOMAIN
