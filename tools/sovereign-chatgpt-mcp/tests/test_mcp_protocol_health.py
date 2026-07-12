from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import mcp_protocol_health


class _Response:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, limit: int) -> bytes:
        assert limit == 1_000_000
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "Sovereign ChatGPT Operator", "version": "1"},
                },
            }
        ).encode("utf-8")


def test_probe_requires_real_initialize_contract() -> None:
    with patch("urllib.request.urlopen", return_value=_Response()):
        result = mcp_protocol_health.probe()

    assert result["ok"] is True
    assert result["status"] == "MCP_PROTOCOL_READY"
    assert result["tools_capability"] is True


def test_probe_rejects_tcp_like_response_without_server_info() -> None:
    response = _Response()
    response.read = lambda limit: b'{"jsonrpc":"2.0","id":1,"result":{"capabilities":{"tools":{}}}}'

    with patch("urllib.request.urlopen", return_value=response):
        with pytest.raises(RuntimeError, match="serverInfo.name"):
            mcp_protocol_health.probe()


def test_probe_rejects_non_loopback_and_wrong_path() -> None:
    with pytest.raises(ValueError, match="loopback"):
        mcp_protocol_health.probe("https://example.com/mcp")
    with pytest.raises(ValueError, match="exact /mcp"):
        mcp_protocol_health.probe("http://127.0.0.1:8090/")
