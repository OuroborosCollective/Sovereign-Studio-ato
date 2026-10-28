"""Read the running MCP over loopback; never instantiate a second server."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from urllib.parse import urlparse

from mcp import ClientSession
import httpx
from mcp.client.streamable_http import streamable_http_client

DEFAULT_URL = "http://127.0.0.1:8090/mcp"
DOMAIN = "https://sovereign-backend.arelorian.de"
WIDGET_URI = "ui://sovereign/dev_dashboard.v2.html"
REQUIRED_TOOLS = frozenset({
    "agent_zero_backend_diagnostics", "agent_zero_a2a_canary", "backend_architecture_assess",
    "deterministic_architecture_inventory", "mcp_tool_contract_registry", "neuro_event_commit",
    "neuro_event_route_preview", "neuro_runtime_contract_status", "operational_assurance_skill_inventory",
    "patchmon_tool_inventory", "repository_architecture_drift_report", "repository_architecture_snapshot",
    "aurion_account_role_readback", "aurion_account_role_plan", "aurion_account_role_apply",
    "teaching_lesson_simulate", "teaching_package_assess", "wolfram_source_intelligence", "vps_ssh_workspace",
})


def _endpoint(url):
    target = urlparse(url)
    if (target.scheme != "http" or target.hostname not in {"127.0.0.1", "localhost", "::1"}
            or target.path != "/mcp" or target.username or target.password or target.query or target.fragment):
        raise ValueError("Deployment readback requires the loopback /mcp endpoint")
    return url


def _structured(result):
    if result.isError or not isinstance(result.structuredContent, dict):
        raise ValueError("Running MCP did not return a successful structured readback")
    return result.structuredContent


async def _pages(session, method, field):
    items, cursor, seen = [], None, set()
    while True:
        page = await method(cursor=cursor)
        items.extend(getattr(page, field))
        cursor = page.nextCursor
        if cursor is None:
            return items
        if cursor in seen:
            raise ValueError("Running MCP returned a repeated registry cursor")
        seen.add(cursor)


async def _readback(mode, expected_count, *, url=DEFAULT_URL, required_tools=REQUIRED_TOOLS):
    if type(expected_count) is not int or expected_count < 1:
        raise ValueError("Declared MCP tool count is invalid")
    _endpoint(url)
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=httpx.Timeout(30)) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                initialized = await session.initialize()
                if initialized.capabilities.tools is None:
                    raise ValueError("Running MCP does not advertise tools")
                tools = await _pages(session, session.list_tools, "tools")
                names = sorted(tool.name for tool in tools)
                if len(names) < expected_count or names != sorted(set(names)):
                    raise ValueError("Running MCP tool count is below the declared minimum or names are not unique")
                missing = sorted(set(required_tools) - set(names))
                if missing:
                    raise ValueError("Running MCP is missing required tools: " + ",".join(missing))
                if mode == "surface":
                    registry = _structured(await session.call_tool("mcp_control_plane_status", {}))
                    digest = hashlib.sha256(json.dumps(names, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
                    if (registry.get("status") != "BROKER_READY" or registry.get("ok") is not True
                            or registry.get("registry_runtime_verified") is not True
                            or registry.get("registry_tool_count") != len(names)
                            or registry.get("registry_tool_names_sha256") != digest):
                        raise ValueError("Running MCP broker/registry identity is not independently confirmed")
                    resources = await _pages(session, session.list_resources, "resources")
                    widget = next((item for item in resources if str(item.uri) == WIDGET_URI), None)
                    meta = widget.model_dump(by_alias=True).get("_meta", {}) if widget else {}
                    if (meta.get("ui", {}).get("domain") != DOMAIN or meta.get("openai/widgetDomain") != DOMAIN):
                        raise ValueError("Running MCP widget domain differs from the declared owner domain")
                    return {"toolCount": len(names), "registrySha256": digest, "widgetDomain": DOMAIN,
                            "widgetUri": WIDGET_URI, "captureProvenance": "live-mcp-http-v1"}
                if mode != "snapshot":
                    raise ValueError("Invalid deployment readback mode")
                registry = _structured(await session.call_tool("mcp_tool_contract_registry", {"include_schemas": True, "max_tools": len(names)}))
                contracts = registry.get("tools")
                if (registry.get("ok") is not True or registry.get("status") != "MCP_TOOL_REGISTRY_READY"
                        or registry.get("runtimeVerified") is not True or registry.get("truncated") is not False
                        or registry.get("toolCount") != len(names) or not isinstance(contracts, list)
                        or [item.get("name") for item in contracts] != names
                        or not re.fullmatch(r"[0-9a-f]{64}", str(registry.get("registrySnapshotSha256") or ""))):
                    raise ValueError("Running MCP returned an incomplete contract snapshot")
                return {"schemaVersion": "sovereign.mcp-deployment-contract-surface.v1",
                        "registrySnapshotSha256": registry["registrySnapshotSha256"], "toolCount": len(names),
                        "tools": contracts, "captureProvenance": "live-mcp-http-contract-registry-v1"}

async def readback(mode, expected_count, *, url=DEFAULT_URL, required_tools=REQUIRED_TOOLS):
    async with asyncio.timeout(45):
        try:
            return await _readback(mode, expected_count, url=url, required_tools=required_tools)
        except BaseExceptionGroup as group:
            def leaves(error):
                if isinstance(error, BaseExceptionGroup):
                    return [leaf for child in error.exceptions for leaf in leaves(child)]
                return [error]
            errors = leaves(group)
            if errors and all(isinstance(error, ValueError) for error in errors):
                raise errors[0] from group
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("surface", "snapshot"))
    parser.add_argument("expected_count", type=int)
    args = parser.parse_args()
    required = set(REQUIRED_TOOLS)
    if os.getenv("SOVEREIGN_MCP_ENABLE_AURION_ADMIN_MCP", "0").strip() == "1":
        from aurion_admin_mcp_lane import AurionAdminMcpRuntime, exposed_tool_names
        required.update(exposed_tool_names(AurionAdminMcpRuntime()._local_allowed_scopes(),
                        wolfram_enabled=os.getenv("AURION_ADMIN_MCP_WOLFRAM_ENABLED", "0").strip() == "1"))
    result = asyncio.run(readback(args.mode, args.expected_count, required_tools=required))
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
