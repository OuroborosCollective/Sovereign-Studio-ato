"""Real broker/queue-client and registry boundaries; run in existing MCP CI."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

from broker import BrokerRuntime
from broker_client import HostBrokerClient
from command_contract import MUTATING_ACTIONS


def test_native_apply_keeps_host_worker_boundary(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_AURION_OPERATOR", "1")
    runtime = BrokerRuntime()
    runtime.aurion_native_auth = Mock()
    operation = "a" * 32
    assert runtime.dispatch("aurion_native_auth_apply", {"operation_id": operation})["failure_family"] == "INBOUND_MUTATION_FORBIDDEN"
    runtime.aurion_native_auth.apply.assert_not_called()
    runtime.dispatch("aurion_native_auth_apply", {"operation_id": operation}, execution_origin="host_worker")
    runtime.aurion_native_auth.apply.assert_called_once_with(operation)


def test_only_one_native_mutating_action_and_queue_metadata(monkeypatch):
    assert {name for name in MUTATING_ACTIONS if name.startswith("aurion_native_auth_")} == {"aurion_native_auth_apply"}
    client = HostBrokerClient()
    client.command_queue = Mock()
    client.call("aurion_native_auth_apply", {"operation_id": "a" * 32}, timeout=1)
    client.command_queue.submit.assert_called_once_with("aurion_native_auth_apply", {"operation_id": "a" * 32}, timeout=1.0)


def test_native_paths_reject_nonprivate_and_extra_arguments(monkeypatch):
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_AURION_OPERATOR", "1")
    runtime = BrokerRuntime()
    runtime.aurion_native_auth = Mock()
    assert runtime.dispatch("aurion_native_auth_plan", {"expected_revision": "a" * 40})["ok"] is False
    runtime.private_owner_mode = True
    result = runtime.dispatch("aurion_native_auth_apply", {"operation_id": "a" * 32, "owner_approved": True}, execution_origin="host_worker")
    assert result["blocker"] == "NATIVE_AUTH_ARGUMENTS_INVALID"
    runtime.aurion_native_auth.apply.assert_not_called()


def test_real_registered_native_tools_have_closed_bounded_inputs(tmp_path):
    root = Path(__file__).resolve().parents[1]
    program = '''
import json
import launcher
import server
from pydantic import ValidationError
assert launcher.mcp is server.mcp
for suffix, key, value in (("plan", "expected_revision", "a"*40), ("apply", "operation_id", "b"*32), ("readback", "operation_id", "b"*32)):
    tool=launcher.mcp._tool_manager.get_tool("aurion_native_auth_"+suffix)
    assert tool is not None
    assert set(tool.parameters["properties"]) == {key}
    tool.fn_metadata.arg_model.model_validate({key:value})
    for invalid in ({key:"../escape"}, {key:value,"owner_approved":True}):
        try: tool.fn_metadata.arg_model.model_validate(invalid)
        except ValidationError: pass
        else: raise AssertionError("unbounded input accepted")
print("native registry contracts passed")
'''
    env = {**os.environ, "PYTHONPATH": str(root), "SOVEREIGN_MCP_PRIVATE_OWNER_MODE": "1",
        "SOVEREIGN_MCP_ENABLE_AURION_OPERATOR": "1", "SOVEREIGN_MCP_WORKSPACE_ROOT": str(tmp_path / "workspaces"),
        "SOVEREIGN_TOOL_RANKING_STATE_ROOT": str(tmp_path / "ranking"),
        "SOVEREIGN_NEURO_RUNTIME_STATE_ROOT": str(tmp_path / "neuro"), "SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED": "0"}
    completed = subprocess.run([sys.executable, "-c", program], cwd=root, env=env, capture_output=True, text=True, timeout=60)
    assert completed.returncode == 0, completed.stderr
    assert "native registry contracts passed" in completed.stdout
