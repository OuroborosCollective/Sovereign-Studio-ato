"""QuickNode/Core adapter regressions; provider doubles are not live evidence."""
from __future__ import annotations

import importlib.util
import io
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sqlite3
import sys
import threading
import traceback
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest
import yaml

from agent_runtime.retrieval.bitcoin_rpc import BitcoinCoreRpcClient, BitcoinCoreRpcConfig, BitcoinCoreRpcError

ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_MARKER = "SYNTHETIC_NOT_A_CREDENTIAL"
ENDPOINT = "https://fixture.btc.quiknode.pro/" + SYNTHETIC_MARKER + "/"


@pytest.fixture
def cli():
    spec = importlib.util.spec_from_file_location(
        "bitcoin_full_chain_ingest_test_target", ROOT / "scripts/sovereign-backend/bitcoin_full_chain_ingest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def client_with_response(result, *, auth_mode="quicknode", envelope=None):
    client = BitcoinCoreRpcClient(BitcoinCoreRpcConfig(
        ENDPOINT if auth_mode == "quicknode" else "http://127.0.0.1:8332", auth_mode=auth_mode
    ))
    response = io.BytesIO(json.dumps(
        envelope if envelope is not None else {"id": "sovereign-bitcoin", "result": result, "error": None}
    ).encode())
    client._opener.open = Mock(return_value=response)
    return client


def test_quicknode_sends_json_rpc_2_without_basic_credentials(monkeypatch):
    monkeypatch.delenv("BITCOIN_RPC_USER", raising=False)
    monkeypatch.delenv("BITCOIN_RPC_PASSWORD", raising=False)
    client = client_with_response(123)
    assert client.get_block_count() == 123
    req = client._opener.open.call_args.args[0]
    assert req.full_url == ENDPOINT
    assert req.get_header("Authorization") is None
    assert json.loads(req.data) == {
        "jsonrpc": "2.0", "id": "sovereign-bitcoin", "method": "getblockcount", "params": []
    }


def test_basic_auth_remains_the_default(monkeypatch):
    monkeypatch.setenv("BITCOIN_RPC_USER", "synthetic-user")
    monkeypatch.setenv("BITCOIN_RPC_PASSWORD", SYNTHETIC_MARKER)
    client = client_with_response(123, auth_mode="basic")
    assert client.get_block_count() == 123
    req = client._opener.open.call_args.args[0]
    assert req.get_header("Authorization").startswith("Basic ")
    assert json.loads(req.data)["jsonrpc"] == "1.0"


def test_basic_auth_missing_credentials_never_falls_back_to_url(monkeypatch):
    monkeypatch.delenv("BITCOIN_RPC_USER", raising=False)
    monkeypatch.delenv("BITCOIN_RPC_PASSWORD", raising=False)
    client = client_with_response(123, auth_mode="basic")
    with pytest.raises(BitcoinCoreRpcError, match="credentials"):
        client.get_block_count()
    client._opener.open.assert_not_called()


@pytest.mark.parametrize("endpoint", [
    "http://fixture.btc.quiknode.pro/" + SYNTHETIC_MARKER,
    "https://fixture.btc.quiknode.pro:8443/" + SYNTHETIC_MARKER,
    "https://fixture.btc.quiknode.pro/",
    "https://fixture.btc.quiknode.pro.evil.invalid/" + SYNTHETIC_MARKER,
    "https://evilquiknode.pro/" + SYNTHETIC_MARKER,
    "https://fixture.btc.quiknode.pro/" + SYNTHETIC_MARKER + "?token=synthetic",
    "https://fixture.btc.quiknode.pro/" + SYNTHETIC_MARKER + "#fragment",
    "https://synthetic@fixture.btc.quiknode.pro/" + SYNTHETIC_MARKER,
    "https://fixture.btc.quiknode.pro/extra/" + SYNTHETIC_MARKER,
])
def test_quicknode_rejects_unprotected_or_out_of_scope_endpoints(endpoint):
    with pytest.raises(BitcoinCoreRpcError):
        BitcoinCoreRpcConfig(endpoint, auth_mode="quicknode")


def test_config_repr_omits_endpoint():
    config = BitcoinCoreRpcConfig(ENDPOINT, auth_mode="quicknode")
    assert SYNTHETIC_MARKER not in repr(config)
    assert "quiknode.pro" not in repr(config)


def test_unknown_auth_mode_fails_closed():
    with pytest.raises(BitcoinCoreRpcError, match="auth_mode"):
        BitcoinCoreRpcConfig(ENDPOINT, auth_mode="anonymous")


@pytest.mark.parametrize("method", ["sendrawtransaction", "sendtoaddress", "stop", "eth_getBalance", ""])
def test_mutating_or_cross_chain_methods_are_rejected_before_transport(method):
    client = client_with_response(None)
    with pytest.raises(BitcoinCoreRpcError, match="read-only"):
        client.call(method)
    client._opener.open.assert_not_called()


@pytest.mark.parametrize("payload", [
    {"id": "stale-call", "result": 123},
    {"result": 123},
    {"id": "sovereign-bitcoin"},
    [],
])
def test_invalid_or_mismatched_envelope_fails_closed(payload):
    client = client_with_response(None, envelope=payload)
    with pytest.raises(BitcoinCoreRpcError, match="envelope"):
        client.get_block_count()


def test_provider_error_cannot_echo_endpoint_credentials():
    client = client_with_response(None, envelope={
        "id": "sovereign-bitcoin", "error": {"code": -32601, "message": ENDPOINT}
    })
    with pytest.raises(BitcoinCoreRpcError, match=r"\(-32601\)") as caught:
        client.get_block_count()
    assert SYNTHETIC_MARKER not in "".join(traceback.format_exception(caught.value))


def test_http_error_cannot_echo_endpoint_credentials():
    client = client_with_response(None)
    client._opener.open.side_effect = HTTPError(ENDPOINT, 403, ENDPOINT, {}, None)
    with pytest.raises(BitcoinCoreRpcError, match="transport") as caught:
        client.get_block_count()
    assert SYNTHETIC_MARKER not in "".join(traceback.format_exception(caught.value))


def test_redirect_is_rejected_without_contacting_second_origin():
    client = client_with_response(None)
    handler = next(h for h in client._opener.handlers if hasattr(h, "redirect_request"))
    with pytest.raises(BitcoinCoreRpcError, match="redirects"):
        handler.redirect_request(None, None, 302, "redirect", {}, "https://other.invalid/")


def test_non_hex_block_hash_is_rejected():
    client = client_with_response("z" * 64)
    with pytest.raises(BitcoinCoreRpcError, match="hash"):
        client.get_block_hash(0)


def mainnet_client(cli, *, chain="main", genesis_hash=None, tx=None):
    client = BitcoinCoreRpcClient(BitcoinCoreRpcConfig(ENDPOINT, auth_mode="quicknode"))
    block_hash = genesis_hash or cli.MAINNET_GENESIS_HASH
    def respond(req, **kwargs):
        method = json.loads(req.data)["method"]
        result = {
            "getblockchaininfo": {"chain": chain},
            "getblockcount": 123,
            "getblockhash": block_hash,
            "getblock": {"height": 0, "hash": block_hash, "tx": [{"txid": "a" * 64}] if tx is None else tx},
        }[method]
        return io.BytesIO(json.dumps({"id": "sovereign-bitcoin", "result": result}).encode())
    client._opener.open = Mock(side_effect=respond)
    return client


def test_read_only_preflight_checks_mainnet_and_full_blocks(cli):
    client = mainnet_client(cli)
    assert cli.check_mainnet(client) == 123
    calls = [json.loads(c.args[0].data) for c in client._opener.open.call_args_list]
    assert [c["method"] for c in calls] == ["getblockchaininfo", "getblockcount", "getblockhash", "getblock"]
    assert calls[-1]["params"] == [cli.MAINNET_GENESIS_HASH, 2]


@pytest.mark.parametrize("chain,block_hash,tx", [
    ("test", None, None),
    ("main", "a" * 64, None),
    ("main", None, ["a" * 64]),
    ("main", None, []),
])
def test_wrong_network_or_incomplete_full_block_fails_preflight(cli, chain, block_hash, tx):
    with pytest.raises(BitcoinCoreRpcError):
        cli.check_mainnet(mainnet_client(cli, chain=chain, genesis_hash=block_hash, tx=tx))


def test_check_rpc_does_not_create_or_modify_store(cli, monkeypatch, tmp_path, capsys):
    store = tmp_path / "not-created" / "canonical.sqlite"
    monkeypatch.setenv("BITCOIN_RPC_URL", ENDPOINT)
    monkeypatch.setenv("BITCOIN_RPC_AUTH_MODE", "quicknode")
    monkeypatch.setattr(sys, "argv", ["ingest", "--check-rpc", "--store", str(store)])
    client = mainnet_client(cli)
    monkeypatch.setattr(cli, "BitcoinCoreRpcClient", lambda config: client)
    assert cli.main() == 0
    assert not store.parent.exists()
    assert "BITCOIN_RPC_PREFLIGHT=PASS" in capsys.readouterr().out


def test_ingest_rejects_wrong_network_before_store_creation(cli, monkeypatch, tmp_path):
    store = tmp_path / "not-created" / "canonical.sqlite"
    monkeypatch.setenv("BITCOIN_RPC_URL", ENDPOINT)
    monkeypatch.setenv("BITCOIN_RPC_AUTH_MODE", "quicknode")
    monkeypatch.setattr(sys, "argv", ["ingest", "--store", str(store)])
    monkeypatch.setattr(cli, "BitcoinCoreRpcClient", lambda config: mainnet_client(cli, chain="test"))
    with pytest.raises(BitcoinCoreRpcError, match="mainnet"):
        cli.main()
    assert not store.parent.exists()


def test_rpc_mirror_is_byte_identical():
    assert (ROOT / "backend/agent_runtime/retrieval/bitcoin_rpc.py").read_bytes() == (
        ROOT / "scripts/sovereign-backend/agent_runtime/retrieval/bitcoin_rpc.py"
    ).read_bytes()


def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/bitcoin-full-chain-index.yml").read_text())


@pytest.mark.parametrize("mode,username,password,relative_store,expected", [
    ("basic", "", "", False, False),
    ("basic", "synthetic-user", SYNTHETIC_MARKER, False, True),
    ("quicknode", "", "", False, True),
    ("anonymous", "", "", False, False),
    ("quicknode", "", "", True, False),
])
def test_actual_workflow_credential_gate(mode, username, password, relative_store, expected, tmp_path):
    step = next(s for s in workflow()["jobs"]["bitcoin-full-chain"]["steps"] if s["name"].startswith("Require authorized"))
    env = dict(os.environ, BITCOIN_RPC_URL=ENDPOINT, BITCOIN_RPC_AUTH_MODE=mode,
               BITCOIN_RPC_USER=username, BITCOIN_RPC_PASSWORD=password,
               BITCOIN_CANONICAL_STORE="data/bitcoin.sqlite" if relative_store else str(tmp_path / "persistent.sqlite"),
               GITHUB_WORKSPACE=str(tmp_path / "checkout"))
    result = subprocess.run(["bash", "-c", step["run"]], env=env, capture_output=True, text=True)
    assert (result.returncode == 0) is expected
    assert SYNTHETIC_MARKER not in result.stdout + result.stderr


def test_workflow_preflight_precedes_ingest_and_inputs_are_not_shell_code():
    steps = workflow()["jobs"]["bitcoin-full-chain"]["steps"]
    preflight = next(i for i, s in enumerate(steps) if "--check-rpc" in s.get("run", ""))
    ingest = next(i for i, s in enumerate(steps) if s["name"] == "Run canonical full-chain ingest")
    assert preflight < ingest
    assert "${{ inputs." not in "\n".join(s.get("run", "") for s in steps)
    assert workflow()["jobs"]["bitcoin-full-chain"]["runs-on"] == ["self-hosted", "linux", "x64", "bitcoin-indexer"]


def test_real_http_adapter_ingest_persists_and_resumes_sqlite(cli, monkeypatch, tmp_path, capsys):
    """Real local HTTP/SQLite round trip; the source is an explicit test fixture."""
    block_hash = cli.MAINNET_GENESIS_HASH
    fixture_block = {
        "height": 0, "hash": block_hash, "time": 0, "nonce": 0, "bits": "1d00ffff",
        "tx": [{"txid": "a" * 64, "version": 1, "locktime": 0,
                "vin": [{"coinbase": "0101", "sequence": 0}],
                "vout": [{"value": "50.00000000", "n": 0, "scriptPubKey": {"type": "p2pk"}}]}],
    }
    requests = []
    class FixtureRpc(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            assert self.headers["Authorization"].startswith("Basic ")
            results = {"getblockchaininfo": {"chain": "main"}, "getblockcount": 0,
                       "getblockhash": block_hash, "getblock": fixture_block}
            payload = json.dumps({"id": body["id"], "result": results[body["method"]], "error": None}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureRpc)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store = tmp_path / "persistent" / "canonical.sqlite"
    monkeypatch.setenv("BITCOIN_RPC_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("BITCOIN_RPC_AUTH_MODE", "basic")
    monkeypatch.setenv("BITCOIN_RPC_USER", "synthetic-user")
    monkeypatch.setenv("BITCOIN_RPC_PASSWORD", SYNTHETIC_MARKER)
    monkeypatch.setattr(sys, "argv", ["ingest", "--store", str(store), "--end-height", "0"])
    try:
        assert cli.main() == 0
        assert "BLOCKS_INGESTED=1" in capsys.readouterr().out
        with sqlite3.connect(store) as connection:
            assert connection.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 1
            assert connection.execute("SELECT value_sat FROM outputs").fetchone()[0] == 5_000_000_000
        assert cli.main() == 0
        assert "BLOCKS_INGESTED=0" in capsys.readouterr().out
        with sqlite3.connect(store) as connection:
            assert connection.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert {r["method"] for r in requests} <= {"getblockchaininfo", "getblockcount", "getblockhash", "getblock"}


def test_ci_runs_quicknode_regressions_and_only_probes_source():
    ci = yaml.safe_load((ROOT / ".github/workflows/sovereign-agent-backend.yml").read_text())
    steps = ci["jobs"]["bitcoin-retrieval-contracts"]["steps"]
    regression = next(s for s in steps if s["name"] == "Run Bitcoin retrieval contract tests")
    assert "backend/tests/test_bitcoin_rpc_quicknode.py" in regression["run"]
    probe = next(s for s in steps if s["name"] == "Probe authorized Bitcoin mainnet RPC (read-only)")
    assert "--check-rpc" in probe["run"]
    assert "--depth" not in probe["run"]
