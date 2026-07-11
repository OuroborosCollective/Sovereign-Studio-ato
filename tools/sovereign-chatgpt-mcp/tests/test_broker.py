from __future__ import annotations

from pathlib import Path

from broker import BrokerRuntime
from broker_client import HostBrokerClient


def test_missing_broker_socket_is_a_real_blocker(tmp_path: Path) -> None:
    client = HostBrokerClient(str(tmp_path / "missing.sock"))
    result = client.call("container_status", {"container": "sovereign-backend"})
    assert result["status"] == "BLOCKED"
    assert "Socket fehlt" in result["blocker"]


def test_unknown_broker_action_is_blocked() -> None:
    runtime = BrokerRuntime()
    result = runtime.dispatch("shell", {"command": "rm -rf /"})
    assert result["status"] == "BLOCKED"
    assert "nicht freigegeben" in result["blocker"]


def test_non_allowlisted_container_is_blocked() -> None:
    runtime = BrokerRuntime()
    result = runtime.dispatch("container_status", {"container": "unrelated-root-container"})
    assert result["status"] == "BLOCKED"
    assert "nicht freigegeben" in result["blocker"]


def test_deploy_action_remains_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_DEPLOY", raising=False)
    runtime = BrokerRuntime()
    result = runtime.dispatch(
        "deploy_verified_release",
        {
            "image_digest": "sha256:" + "a" * 64,
            "expected_revision": "b" * 40,
            "confirmation_revision": "b" * 40,
        },
    )
    assert result["status"] == "BLOCKED"
