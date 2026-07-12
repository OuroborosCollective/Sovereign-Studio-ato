from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_URL = "http://127.0.0.1:8090/mcp"
DEFAULT_PROTOCOL_VERSION = "2025-06-18"


def _parse_body(content_type: str, body: bytes) -> dict[str, Any]:
    text = body.decode("utf-8", errors="replace").strip()
    if "text/event-stream" in content_type.lower():
        payloads = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        if not payloads:
            raise RuntimeError("MCP endpoint returned an empty event stream")
        text = payloads[-1]
    if not text:
        raise RuntimeError("MCP endpoint returned an empty response")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise RuntimeError("MCP response is not a JSON object")
    return parsed


def probe(
    url: str = DEFAULT_URL,
    *,
    timeout_seconds: float = 5.0,
    protocol_version: str = DEFAULT_PROTOCOL_VERSION,
) -> dict[str, Any]:
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme != "http" or parsed_url.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("MCP health probe only permits a loopback HTTP endpoint")
    if parsed_url.path != "/mcp":
        raise ValueError("MCP health probe requires the exact /mcp path")

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "sovereign-mcp-health", "version": "1.0"},
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": protocol_version,
            "User-Agent": "sovereign-mcp-health/1.0",
        },
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = int(response.status)
            content_type = str(response.headers.get("Content-Type") or "")
            body = response.read(1_000_000)
    except urllib.error.HTTPError as error:
        detail = error.read(4000).decode("utf-8", errors="replace")
        raise RuntimeError(f"MCP initialize returned HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"MCP initialize connection failed: {error.reason}") from error

    if status != 200:
        raise RuntimeError(f"MCP initialize returned unexpected HTTP {status}")
    message = _parse_body(content_type, body)
    if message.get("jsonrpc") != "2.0" or message.get("id") != 1:
        raise RuntimeError("MCP initialize returned an invalid JSON-RPC envelope")
    if message.get("error"):
        raise RuntimeError(f"MCP initialize returned a protocol error: {message['error']}")
    result = message.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("MCP initialize response has no result object")
    server_info = result.get("serverInfo")
    if not isinstance(server_info, dict) or not str(server_info.get("name") or "").strip():
        raise RuntimeError("MCP initialize response has no serverInfo.name")
    capabilities = result.get("capabilities")
    if not isinstance(capabilities, dict) or "tools" not in capabilities:
        raise RuntimeError("MCP initialize response does not advertise tool capability")

    return {
        "ok": True,
        "status": "MCP_PROTOCOL_READY",
        "url": url,
        "protocol_version": str(result.get("protocolVersion") or protocol_version),
        "server": str(server_info.get("name")),
        "server_version": str(server_info.get("version") or ""),
        "tools_capability": True,
        "latency_ms": round((time.monotonic() - started) * 1000),
    }


def wait_until_ready(
    url: str,
    *,
    wait_seconds: float,
    timeout_seconds: float,
    protocol_version: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(0.0, wait_seconds)
    last_error = "not attempted"
    while True:
        try:
            return probe(url, timeout_seconds=timeout_seconds, protocol_version=protocol_version)
        except Exception as error:
            last_error = str(error)
        if time.monotonic() >= deadline:
            raise RuntimeError(last_error)
        time.sleep(1.0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the local Sovereign MCP initialize handshake")
    parser.add_argument("--url", default=os.getenv("TUNNEL_MCP_SERVER_URL", DEFAULT_URL))
    parser.add_argument("--wait-seconds", type=float, default=0.0)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument(
        "--protocol-version",
        default=os.getenv("SOVEREIGN_MCP_PROTOCOL_VERSION", DEFAULT_PROTOCOL_VERSION),
    )
    arguments = parser.parse_args()
    try:
        result = wait_until_ready(
            arguments.url,
            wait_seconds=arguments.wait_seconds,
            timeout_seconds=arguments.timeout_seconds,
            protocol_version=arguments.protocol_version,
        )
    except Exception as error:
        print(
            json.dumps(
                {"ok": False, "status": "MCP_PROTOCOL_UNAVAILABLE", "error": str(error)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
