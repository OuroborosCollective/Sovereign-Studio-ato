"""Real SDK HTTP transport contracts for the installer readback client."""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
import socket
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from deployment_registry_probe import DOMAIN, WIDGET_URI, _pages, readback

NAMES = {"probe_ping", "mcp_control_plane_status", "mcp_tool_contract_registry"}
SERVER = '''
import hashlib, json, os
from pathlib import Path
from typing import Any
from mcp.server.fastmcp import FastMCP
settings = Path(os.environ["PROBE_SETTINGS"])
mcp = FastMCP("Deployment protocol contract fixture", host="127.0.0.1", port=int(os.environ["PROBE_PORT"]), stateless_http=True, json_response=True)
def flags(): return json.loads(settings.read_text())
@mcp.tool()
def probe_ping() -> dict[str, Any]: return {"ok":True}
@mcp.tool()
def mcp_control_plane_status() -> dict[str, Any]:
    names = sorted(tool.name for tool in mcp._tool_manager.list_tools())
    return {"ok":True,"status":"BROKER_READY" if not flags().get("broker") else "FAILED", "registry_runtime_verified":True,"registry_tool_count":len(names),"registry_tool_names_sha256":"0"*64 if flags().get("hash") else hashlib.sha256(json.dumps(names,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()}
@mcp.tool()
def mcp_tool_contract_registry(include_schemas: bool=True, max_tools: int=1000) -> dict[str, Any]:
    names = sorted(tool.name for tool in mcp._tool_manager.list_tools())
    contracts = [{"name":name,"parameters":{},"outputSchema":{},"contractSha256":"1"*64} for name in names]
    return {"ok":True,"status":"MCP_TOOL_REGISTRY_READY","runtimeVerified":True,"truncated":bool(flags().get("truncated")),"toolCount":len(names),"registrySnapshotSha256":"1"*64,"tools":contracts[:-1] if flags().get("contracts") else contracts}
@mcp.resource("ui://sovereign/dev_dashboard.v2.html", meta={"ui":{"domain":"https://sovereign-backend.arelorian.de"},"openai/widgetDomain":"https://sovereign-backend.arelorian.de"})
def widget() -> str: return "<html>Deployment protocol contract fixture</html>"
if os.environ.get("PROBE_BAD_DOMAIN") == "1":
    for resource in mcp._resource_manager.list_resources():
        resource.meta = {"ui":{"domain":"https://invalid.example"},"openai/widgetDomain":"https://invalid.example"}
mcp.run(transport="streamable-http")
'''


@pytest.fixture
def endpoint(tmp_path, request):
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps(getattr(request, "param", {})))
    script = tmp_path / "sdk_server.py"
    script.write_text(SERVER)
    env = {**os.environ, "PROBE_SETTINGS": str(settings), "PROBE_PORT": str(port),
           "PROBE_BAD_DOMAIN": "1" if getattr(request, "param", {}).get("domain") else "0"}
    with subprocess.Popen([sys.executable, str(script)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) as process:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(process.stderr.read().decode())
            with socket.socket() as ready:
                if ready.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.05)
        else:
            process.kill()
            pytest.fail("Actual SDK HTTP server did not start")
        try:
            yield f"http://127.0.0.1:{port}/mcp"
        finally:
            process.terminate()
            process.wait(timeout=10)


def verify(mode, endpoint, count=3, required=NAMES):
    return asyncio.run(readback(mode, count, url=endpoint, required_tools=required))


def test_live_surface_and_complete_contract_snapshot(endpoint):
    surface = verify("surface", endpoint)
    assert surface["toolCount"] == 3 and surface["widgetUri"] == WIDGET_URI
    assert surface["widgetDomain"] == DOMAIN and surface["captureProvenance"] == "live-mcp-http-v1"
    snapshot = verify("snapshot", endpoint)
    assert snapshot["toolCount"] == 3
    assert {item["name"] for item in snapshot["tools"]} == NAMES


@pytest.mark.parametrize("endpoint,mode,error", [
    ({"hash": True}, "surface", "identity"),
    ({"broker": True}, "surface", "identity"),
    ({"domain": True}, "surface", "domain"),
    ({"truncated": True}, "snapshot", "incomplete"),
    ({"contracts": True}, "snapshot", "incomplete"),
], indirect=["endpoint"])
def test_live_readback_rejects_unverified_or_partial_evidence(endpoint, mode, error):
    with pytest.raises(ValueError, match=error):
        verify(mode, endpoint)


def test_more_tools_than_the_declared_minimum_are_accepted(endpoint):
    assert verify("surface", endpoint, count=2)["toolCount"] == 3
    assert verify("snapshot", endpoint, count=2)["toolCount"] == 3


def test_registry_readback_follows_more_than_twenty_pages_and_one_thousand_items():
    async def page(*, cursor):
        index = int(cursor or 0)
        start = index * 50
        return SimpleNamespace(tools=list(range(start, start + 50)),
                               nextCursor=str(index + 1) if index < 21 else None)

    observed = asyncio.run(_pages(None, page, "tools"))
    assert observed == list(range(1100))


def test_declared_count_and_required_names_are_never_learned_from_live_registry(endpoint):
    with pytest.raises(ValueError, match="count"):
        verify("surface", endpoint, count=4)
    with pytest.raises(ValueError, match="missing required"):
        verify("surface", endpoint, required=NAMES | {"absent_required_tool"})


def test_loopback_readback_ignores_proxy_environment(endpoint, monkeypatch):
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(key, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    assert verify("surface", endpoint)["toolCount"] == 3


def test_client_does_not_load_a_second_server_or_exceed_128_mib(endpoint):
    code = "import asyncio,json,sys;from pathlib import Path;from deployment_registry_probe import readback;r=asyncio.run(readback('surface',3,url=sys.argv[1],required_tools={'probe_ping','mcp_control_plane_status','mcp_tool_contract_registry'}));assert 'launcher' not in sys.modules and 'server' not in sys.modules;print(json.dumps({'count':r['toolCount'],'rssKiB':int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmHWM:')))}))"
    # An exec must not inherit the parent image's high-water RSS. Keep the
    # same 128 MiB bound on this fresh client's actual mm, even after a large parent.
    parent = "import os,sys;allocation=bytearray(160*1024*1024);os.execv(sys.executable,[sys.executable,'-c',sys.argv[1],sys.argv[2]])"
    result = subprocess.run([sys.executable, "-c", parent, code, endpoint], cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["count"] == 3 and observed["rssKiB"] < 128 * 1024
    print("Actual client peak RSS (KiB):", observed["rssKiB"])


@pytest.mark.parametrize("url", ["https://127.0.0.1/mcp", "http://external.example/mcp", "http://127.0.0.1/other", "http://user:secret@127.0.0.1/mcp", "http://127.0.0.1/mcp?x=1"])
def test_probe_cannot_leave_the_loopback_mcp_endpoint(url):
    with pytest.raises(ValueError, match="loopback"):
        verify("surface", url)
