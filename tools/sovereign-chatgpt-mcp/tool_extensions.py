from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import ToolAnnotations

_BROKER: Any = None
_REGISTERED = False

NETWORK_READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
EXTERNAL_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)

_STITCH_DEFAULT_ENDPOINT = "https://stitch.googleapis.com/mcp"
_STITCH_WRITE_CONFIRMATION = "STITCH_WRITE_APPROVED"
_STITCH_ACTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_SECRET_KEY_RE = re.compile(r"(?:secret|password|passwd|token|authorization|api[_-]?key|credential)", re.IGNORECASE)


def repository_dispatch_workflow(
    workflow: str,
    ref: str = "main",
    inputs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Dispatch one allowlisted GitHub Actions workflow without accepting secret-shaped inputs."""
    if _BROKER is None:
        raise RuntimeError("Workflow tools are not registered")
    return _BROKER.call(
        "github_workflow_dispatch",
        {"workflow": workflow, "ref": ref, "inputs": inputs or {}},
        timeout=60,
    )


def repository_workflow_run_status(run_id: int) -> dict[str, Any]:
    """Read workflow, job and failed-step evidence for one GitHub Actions run."""
    if _BROKER is None:
        raise RuntimeError("Workflow tools are not registered")
    return _BROKER.call("github_workflow_run_status", {"run_id": run_id}, timeout=60)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _stitch_endpoint() -> str:
    endpoint = os.getenv("SOVEREIGN_STITCH_MCP_URL", _STITCH_DEFAULT_ENDPOINT).strip()
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError("Stitch MCP endpoint must be a credential-free HTTPS URL")
    if parsed.query or parsed.fragment or parsed.params:
        raise RuntimeError("Stitch MCP endpoint must not contain query, fragment or params")
    if endpoint != _STITCH_DEFAULT_ENDPOINT and os.getenv("SOVEREIGN_STITCH_ALLOW_CUSTOM_ENDPOINT", "0").strip() != "1":
        raise RuntimeError("Custom Stitch MCP endpoints require SOVEREIGN_STITCH_ALLOW_CUSTOM_ENDPOINT=1")
    if endpoint == _STITCH_DEFAULT_ENDPOINT and (parsed.hostname != "stitch.googleapis.com" or parsed.path != "/mcp"):
        raise RuntimeError("Official Stitch MCP endpoint must be exactly https://stitch.googleapis.com/mcp")
    return endpoint


def _read_secret_file(env_name: str, *, max_bytes: int = 16_384) -> str:
    configured = os.getenv(env_name, "").strip()
    if not configured:
        return ""
    path = Path(configured)
    if not path.is_absolute():
        raise RuntimeError(f"{env_name} must point to an absolute file path")
    if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > max_bytes:
        raise RuntimeError(f"{env_name} does not point to a bounded readable secret file")
    value = path.read_text("utf-8").strip()
    if not value or "\n" in value or "\r" in value:
        raise RuntimeError(f"{env_name} must contain exactly one non-empty line")
    return value


def _stitch_auth_headers(*, required: bool) -> tuple[dict[str, str], str]:
    api_key = _read_secret_file("SOVEREIGN_STITCH_API_KEY_FILE")
    bearer = _read_secret_file("SOVEREIGN_STITCH_BEARER_TOKEN_FILE")
    if api_key and bearer:
        raise RuntimeError("Configure only one Stitch authentication mode")
    headers: dict[str, str] = {}
    mode = "none"
    if api_key:
        headers["X-Goog-Api-Key"] = api_key
        mode = "api_key_file"
    elif bearer:
        headers["Authorization"] = f"Bearer {bearer}"
        mode = "oauth_bearer_file"
    project = os.getenv("SOVEREIGN_STITCH_GOOGLE_PROJECT", "").strip()
    if project:
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,62}", project):
            raise RuntimeError("SOVEREIGN_STITCH_GOOGLE_PROJECT is invalid")
        headers["X-Goog-User-Project"] = project
    if required and mode == "none":
        raise RuntimeError(
            "Stitch authentication is not configured; set SOVEREIGN_STITCH_API_KEY_FILE "
            "or SOVEREIGN_STITCH_BEARER_TOKEN_FILE"
        )
    return headers, mode


def _reject_secret_shaped_values(value: Any, path: str = "arguments") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            if _SECRET_KEY_RE.search(key_text):
                raise ValueError(f"Secret-shaped Stitch argument key is forbidden: {path}.{key_text}")
            _reject_secret_shaped_values(nested, f"{path}.{key_text}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_secret_shaped_values(nested, f"{path}[{index}]")


def _bounded_arguments(arguments: dict[str, Any] | None) -> dict[str, Any]:
    payload = arguments or {}
    if not isinstance(payload, dict):
        raise ValueError("arguments must be a JSON object")
    _reject_secret_shaped_values(payload)
    encoded = _canonical(payload).encode("utf-8")
    if len(encoded) > 200_000:
        raise ValueError("Stitch arguments exceed the 200 KB safety bound")
    return payload


def _tool_dict(tool: Any, *, include_schemas: bool) -> dict[str, Any]:
    raw = tool.model_dump(mode="json", by_alias=True) if hasattr(tool, "model_dump") else dict(tool)
    annotations = raw.get("annotations") if isinstance(raw.get("annotations"), dict) else {}
    item: dict[str, Any] = {
        "name": str(raw.get("name") or "")[:160],
        "title": str(raw.get("title") or "")[:240],
        "description": str(raw.get("description") or "")[:4_000],
        "annotations": annotations,
    }
    if include_schemas:
        item["inputSchema"] = raw.get("inputSchema") or {}
        item["outputSchema"] = raw.get("outputSchema") or {}
    item["contractSha256"] = _sha256(item)
    return item


def _result_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    content: list[dict[str, Any]] = []
    for entry in list(getattr(result, "content", None) or [])[:64]:
        if hasattr(entry, "model_dump"):
            raw = entry.model_dump(mode="json", by_alias=True)
        elif isinstance(entry, dict):
            raw = dict(entry)
        else:
            raw = {"type": type(entry).__name__, "text": str(entry)}
        if isinstance(raw.get("text"), str):
            raw["text"] = raw["text"][:50_000]
        content.append(raw)
    payload = {
        "isError": bool(getattr(result, "isError", getattr(result, "is_error", False))),
        "structuredContent": structured,
        "content": content,
    }
    encoded = _canonical(payload).encode("utf-8")
    if len(encoded) > 1_000_000:
        payload = {
            "isError": payload["isError"],
            "structuredContent": None,
            "content": content[:8],
            "truncated": True,
        }
    payload["responseSha256"] = _sha256(payload)
    return payload


async def _stitch_remote_tools(*, include_schemas: bool, require_auth: bool) -> tuple[list[dict[str, Any]], str]:
    endpoint = _stitch_endpoint()
    headers, auth_mode = _stitch_auth_headers(required=require_auth)
    async with streamable_http_client(endpoint, headers=headers or None) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
    tools = [_tool_dict(tool, include_schemas=include_schemas) for tool in result.tools]
    return tools, auth_mode


async def _stitch_remote_call(action: str, arguments: dict[str, Any]) -> dict[str, Any]:
    endpoint = _stitch_endpoint()
    headers, _ = _stitch_auth_headers(required=True)
    async with streamable_http_client(endpoint, headers=headers) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(action, arguments=arguments)
    return _result_payload(result)


def _find_tool(tools: list[dict[str, Any]], action: str) -> dict[str, Any]:
    for tool in tools:
        if tool.get("name") == action:
            return tool
    raise ValueError(f"Stitch action is not present in the live remote catalog: {action}")


def _is_read_only(tool: dict[str, Any]) -> bool:
    annotations = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    return annotations.get("readOnlyHint") is True or annotations.get("read_only_hint") is True


async def stitch_mcp_status() -> dict[str, Any]:
    """Verify the official Google Stitch remote MCP catalog without returning credentials."""
    endpoint = _stitch_endpoint()
    headers, configured_mode = _stitch_auth_headers(required=False)
    try:
        tools, observed_mode = await _stitch_remote_tools(include_schemas=False, require_auth=False)
    except Exception as exc:
        return {
            "ok": False,
            "status": "STITCH_MCP_UNAVAILABLE",
            "endpointSha256": hashlib.sha256(endpoint.encode("utf-8")).hexdigest(),
            "authConfigured": configured_mode != "none",
            "authMode": configured_mode,
            "writeEnabled": os.getenv("SOVEREIGN_STITCH_ENABLE_WRITES", "0").strip() == "1",
            "errorType": type(exc).__name__,
            "errorSha256": hashlib.sha256(str(exc).encode("utf-8", errors="replace")).hexdigest(),
            "secretValuesReturned": False,
        }
    return {
        "ok": True,
        "status": "STITCH_MCP_CATALOG_VERIFIED",
        "endpointSha256": hashlib.sha256(endpoint.encode("utf-8")).hexdigest(),
        "toolCount": len(tools),
        "toolNames": [tool["name"] for tool in tools],
        "catalogSha256": _sha256(tools),
        "authConfigured": bool(headers),
        "authMode": observed_mode,
        "writeEnabled": os.getenv("SOVEREIGN_STITCH_ENABLE_WRITES", "0").strip() == "1",
        "secretValuesReturned": False,
    }


async def stitch_mcp_catalog(include_schemas: bool = True, max_tools: int = 100) -> dict[str, Any]:
    """List the live Stitch MCP tool catalog so new Google actions are discovered without hard-coded names."""
    bounded_max = max(1, min(int(max_tools), 100))
    tools, auth_mode = await _stitch_remote_tools(include_schemas=include_schemas, require_auth=False)
    selected = tools[:bounded_max]
    return {
        "ok": True,
        "status": "STITCH_MCP_CATALOG_READY",
        "tools": selected,
        "toolCount": len(tools),
        "returnedToolCount": len(selected),
        "catalogSha256": _sha256(tools),
        "authMode": auth_mode,
        "mutationPerformed": False,
        "secretValuesReturned": False,
    }


async def stitch_mcp_call_read(action: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call one live Stitch action only when Google marks it explicitly read-only."""
    action_name = str(action or "").strip()
    if not _STITCH_ACTION_RE.fullmatch(action_name):
        raise ValueError("action is invalid")
    payload = _bounded_arguments(arguments)
    tools, auth_mode = await _stitch_remote_tools(include_schemas=True, require_auth=True)
    tool = _find_tool(tools, action_name)
    if not _is_read_only(tool):
        raise PermissionError("Stitch action is not explicitly marked read-only; use the guarded write tool")
    result = await _stitch_remote_call(action_name, payload)
    return {
        "ok": not result.get("isError", False),
        "status": "STITCH_READ_ACTION_COMPLETED" if not result.get("isError", False) else "STITCH_READ_ACTION_FAILED",
        "action": action_name,
        "remoteContractSha256": tool["contractSha256"],
        "authMode": auth_mode,
        "result": result,
        "mutationPerformed": False,
        "secretValuesReturned": False,
    }


async def stitch_mcp_call_write(
    action: str,
    arguments: dict[str, Any] | None = None,
    confirmation: str = "",
) -> dict[str, Any]:
    """Call one non-read-only Stitch action after the server write gate and exact confirmation are present."""
    if os.getenv("SOVEREIGN_STITCH_ENABLE_WRITES", "0").strip() != "1":
        raise PermissionError("Stitch writes are disabled; set SOVEREIGN_STITCH_ENABLE_WRITES=1 on the server")
    if str(confirmation or "").strip() != _STITCH_WRITE_CONFIRMATION:
        raise PermissionError(f"confirmation must equal {_STITCH_WRITE_CONFIRMATION}")
    action_name = str(action or "").strip()
    if not _STITCH_ACTION_RE.fullmatch(action_name):
        raise ValueError("action is invalid")
    payload = _bounded_arguments(arguments)
    tools, auth_mode = await _stitch_remote_tools(include_schemas=True, require_auth=True)
    tool = _find_tool(tools, action_name)
    if _is_read_only(tool):
        raise PermissionError("Read-only Stitch actions must use stitch_mcp_call_read")
    result = await _stitch_remote_call(action_name, payload)
    return {
        "ok": not result.get("isError", False),
        "status": "STITCH_WRITE_ACTION_COMPLETED" if not result.get("isError", False) else "STITCH_WRITE_ACTION_FAILED",
        "action": action_name,
        "remoteContractSha256": tool["contractSha256"],
        "authMode": auth_mode,
        "result": result,
        "mutationPerformed": True,
        "secretValuesReturned": False,
    }


def register(mcp: Any, broker: Any) -> None:
    global _BROKER, _REGISTERED
    _BROKER = broker
    if _REGISTERED:
        return
    mcp.tool(annotations=EXTERNAL_WRITE)(repository_dispatch_workflow)
    mcp.tool(annotations=NETWORK_READ)(repository_workflow_run_status)
    for tool in (
        stitch_mcp_status,
        stitch_mcp_catalog,
        stitch_mcp_call_read,
    ):
        mcp.tool(annotations=NETWORK_READ)(tool)
    mcp.tool(annotations=EXTERNAL_WRITE)(stitch_mcp_call_write)
    _REGISTERED = True
