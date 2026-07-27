from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import tool_extensions


def test_stitch_endpoint_defaults_to_official_google_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOVEREIGN_STITCH_MCP_URL", raising=False)
    monkeypatch.delenv("SOVEREIGN_STITCH_ALLOW_CUSTOM_ENDPOINT", raising=False)
    assert tool_extensions._stitch_endpoint() == "https://stitch.googleapis.com/mcp"


def test_stitch_endpoint_rejects_custom_endpoint_without_explicit_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOVEREIGN_STITCH_MCP_URL", "https://example.test/mcp")
    monkeypatch.delenv("SOVEREIGN_STITCH_ALLOW_CUSTOM_ENDPOINT", raising=False)
    with pytest.raises(RuntimeError, match="Custom Stitch MCP endpoints"):
        tool_extensions._stitch_endpoint()


def test_stitch_auth_uses_secret_file_without_returning_value(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret = tmp_path / "stitch.key"
    secret.write_text("very-secret-key\n", "utf-8")
    monkeypatch.setenv("SOVEREIGN_STITCH_API_KEY_FILE", str(secret))
    monkeypatch.delenv("SOVEREIGN_STITCH_BEARER_TOKEN_FILE", raising=False)
    headers, mode = tool_extensions._stitch_auth_headers(required=True)
    assert headers == {"X-Goog-Api-Key": "very-secret-key"}
    assert mode == "api_key_file"


def test_stitch_arguments_reject_secret_shaped_keys() -> None:
    with pytest.raises(ValueError, match="Secret-shaped"):
        tool_extensions._bounded_arguments({"access_token": "must-not-pass"})


def test_stitch_catalog_exposes_live_actions_without_hardcoding(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_remote_tools(*, include_schemas: bool, require_auth: bool):
        assert include_schemas is True
        assert require_auth is False
        return ([{
            "name": "list_projects",
            "title": "List projects",
            "description": "Read projects",
            "annotations": {"readOnlyHint": True},
            "inputSchema": {"type": "object"},
            "outputSchema": {"type": "object"},
            "contractSha256": "a" * 64,
        }], "none")

    monkeypatch.setattr(tool_extensions, "_stitch_remote_tools", fake_remote_tools)
    result = asyncio.run(tool_extensions.stitch_mcp_catalog())
    assert result["status"] == "STITCH_MCP_CATALOG_READY"
    assert result["tools"][0]["name"] == "list_projects"
    assert result["mutationPerformed"] is False
    assert result["secretValuesReturned"] is False


def test_stitch_read_rejects_action_without_remote_read_only_annotation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_remote_tools(*, include_schemas: bool, require_auth: bool):
        return ([{
            "name": "create_project",
            "annotations": {"readOnlyHint": False},
            "contractSha256": "b" * 64,
        }], "api_key_file")

    monkeypatch.setattr(tool_extensions, "_stitch_remote_tools", fake_remote_tools)
    with pytest.raises(PermissionError, match="not explicitly marked read-only"):
        asyncio.run(tool_extensions.stitch_mcp_call_read("create_project", {}))


def test_stitch_write_requires_server_gate_and_exact_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOVEREIGN_STITCH_ENABLE_WRITES", raising=False)
    with pytest.raises(PermissionError, match="writes are disabled"):
        asyncio.run(tool_extensions.stitch_mcp_call_write("create_project", {}, "STITCH_WRITE_APPROVED"))

    monkeypatch.setenv("SOVEREIGN_STITCH_ENABLE_WRITES", "1")
    with pytest.raises(PermissionError, match="confirmation must equal"):
        asyncio.run(tool_extensions.stitch_mcp_call_write("create_project", {}, "yes"))
