from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/sovereign-chatgpt-mcp"))
from owner_ssh_console import OwnerSSHConsole, OPERATIONS

@pytest.fixture
def console(tmp_path, monkeypatch):
    # Only the external filesystem ownership adapter is mocked on non-root CI.
    # Modes, symlink refusal, persisted state and all production logic are real.
    original = os.fstat
    if os.geteuid() != 0:
        def root_owned(fd):
            info = original(fd)
            fields = list(info)
            fields[4] = 0
            return os.stat_result(fields)
        monkeypatch.setattr(os, "fstat", root_owned)
    calls = []
    environments = []
    alive = [False]
    def runner(argv, **kwargs):
        calls.append(argv)
        environments.append(kwargs.get("env", {}))
        if "-fN" in argv:
            alive[0] = True
        if "exit" in argv:
            alive[0] = False
        code = 255 if "check" in argv and not alive[0] else 0
        return SimpleNamespace(returncode=code, stdout="synthetic-inspection-output", stderr="")
    instance = OwnerSSHConsole(root=tmp_path, runner=runner)
    instance.test_environments = environments
    profile = {"host": str(__import__("ipaddress").ip_address(int("08080808", 16))), "port": 22,
               "username": "operator", "knownHostKey": "ssh-ed25519 " + base64.b64encode(
                    b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(32)).decode(),
               "privateKey": "synthetic-unusable-ssh-material", "expiresInSeconds": 60}
    instance._write("ssh_console_profile.json", profile)
    return instance, profile, calls

def owner_action(instance, action, **values):
    identifier = __import__("uuid").uuid4().hex
    payload = {"operationId": identifier, "action": action, "expiresAt": time.time() + 30, **values}
    if action == "connect":
        payload["profileSha256"] = hashlib.sha256(instance._read("ssh_console_profile.json")).hexdigest()
    instance._write("ssh_console_action.json", payload)
    return identifier

def connected(console):
    instance, profile, calls = console
    result = instance.owner_action(owner_action(instance, "connect"))
    assert result["ok"]
    return instance, result["sessionId"], calls

def test_owner_connection_checks_host_and_keeps_material_out_of_arguments(console):
    instance, session_id, calls = connected(console)
    serialized = json.dumps(calls)
    assert "synthetic-unusable-ssh-material" not in serialized
    assert any("StrictHostKeyChecking=yes" in argv for argv in calls)
    assert any("IdentityAgent=none" in argv for argv in calls)
    assert instance.status(session_id)["status"] == "connected"
    assert "privateKey" not in json.dumps(instance.status(session_id))
    assert (instance.root / ("ssh-" + session_id) / "identity").stat().st_mode & 0o777 == 0o600

def test_default_delegation_denied_and_cross_session_denied(console):
    instance, session_id, calls = connected(console)
    with pytest.raises(ValueError, match="delegation"):
        instance.assistant_inspect(session_id, "disk")
    with pytest.raises(ValueError, match="identity"):
        instance.assistant_inspect("f" * 32, "disk")

def test_scoped_delegation_same_transport_and_revocation(console):
    instance, session_id, calls = connected(console)
    instance.owner_action(owner_action(instance, "grant", sessionId=session_id, operations=["disk"], ttl=30))
    with pytest.raises(ValueError, match="delegation"):
        instance.assistant_inspect(session_id, "system")
    result = instance.assistant_inspect(session_id, "disk")
    assert result["operation"] == "disk"
    inspections = [argv for argv in calls if "df -h" in argv]
    assert len(inspections) == 1
    assert "ProxyCommand=false" in inspections[0]
    assert "ControlMaster=no" in inspections[0]
    assert instance._state()["lastActivity"]["actor"] == "assistant"
    instance.owner_action(owner_action(instance, "revoke", sessionId=session_id))
    with pytest.raises(ValueError, match="delegation"):
        instance.assistant_inspect(session_id, "disk")

def test_expired_delegation_does_not_execute(console):
    instance, session_id, calls = connected(console)
    state = instance._state()
    state.update(grantUntil=time.time() - 1, allowedOperations=["disk"])
    instance._write("ssh_console_state.json", state)
    with pytest.raises(ValueError, match="delegation"):
        instance.assistant_inspect(session_id, "disk")
    assert not any("df -h" in argv for argv in calls)

def test_owner_request_is_one_use_and_revision_bound(console):
    instance, profile, calls = console
    action = owner_action(instance, "connect")
    profile["username"] = "changed"
    instance._write("ssh_console_profile.json", profile)
    with pytest.raises(ValueError, match="changed"):
        instance.owner_action(action)
    assert not calls
    with pytest.raises(FileNotFoundError):
        instance.owner_action(action)

def test_closed_session_removes_identity_and_cannot_be_reused(console):
    instance, session_id, calls = connected(console)
    instance.owner_action(owner_action(instance, "close", sessionId=session_id))
    assert not (instance.root / ("ssh-" + session_id)).exists()
    assert instance.status(session_id)["status"] == "closed"
    with pytest.raises(ValueError):
        instance.assistant_inspect(session_id, "disk")

def test_expiry_cleanup_runs_without_owner_browser(console):
    instance, session_id, calls = connected(console)
    state = instance._state()
    state["expiresAt"] = time.time() - 1
    instance._write("ssh_console_state.json", state)
    before = (instance.root / "ssh_console_state.json").read_bytes()
    assert instance.status(session_id)["status"] == "expired"
    assert (instance.root / "ssh_console_state.json").read_bytes() == before
    instance.cleanup_expired()
    assert instance._state()["status"] == "closed"
    assert not (instance.root / ("ssh-" + session_id)).exists()

@pytest.mark.parametrize("patch", [
    {"host": "127.0.0.1"}, {"host": "localhost"}, {"host": "169.254.169.254"},
    {"username": "-oProxyCommand=bad"}, {"port": True}, {"port": 65536},
    {"knownHostKey": "unknown"}, {"expiresInSeconds": 10000}, {"password": "synthetic"},
])
def test_invalid_and_internal_targets_fail_closed(console, patch):
    instance, profile, calls = console
    with pytest.raises(ValueError):
        instance.validate_profile({**profile, **patch})
    assert not calls

def test_protected_symlinks_and_readable_profiles_denied(console):
    instance, profile, calls = console
    source = instance.root / "ssh_console_profile.json"
    source.chmod(0o644)
    with pytest.raises(ValueError, match="ownership"):
        instance._read(source.name)
    source.unlink()
    source.symlink_to(instance.root / "different")
    with pytest.raises(OSError):
        instance._read(source.name)

def test_password_askpass_is_private_and_not_an_argument(console):
    instance, profile, calls = console
    profile.pop("privateKey")
    profile["password"] = "synthetic-not-a-real-login"
    instance._write("ssh_console_profile.json", profile)
    result = instance.owner_action(owner_action(instance, "connect"))
    directory = instance.root / ("ssh-" + result["sessionId"])
    assert (directory / "password").stat().st_mode & 0o777 == 0o600
    assert (directory / "askpass").stat().st_mode & 0o777 == 0o700
    assert "synthetic-not-a-real-login" not in json.dumps(calls + instance.test_environments)
    assert any(env.get("SSH_ASKPASS_REQUIRE") == "force" for env in instance.test_environments)
    completed = subprocess.run([sys.executable, str(directory / "askpass")], capture_output=True, text=True)
    assert completed.returncode == 0
    assert completed.stdout == "synthetic-not-a-real-login\n"
    instance.owner_action(owner_action(instance, "close", sessionId=result["sessionId"]))
    assert not directory.exists() and not (instance.root / "ssh_console_profile.json").exists()


def test_canonical_backend_mirrors_and_queue_route():
    for name in ("owner_ssh_console.py", "command_queue.py", "command_contract.py"):
        assert (ROOT / "tools/sovereign-chatgpt-mcp" / name).read_bytes() == (ROOT / "scripts/sovereign-backend" / name).read_bytes()
    from command_contract import is_mutating_action
    assert is_mutating_action("ssh_console_owner_action")
    assert is_mutating_action("ssh_console_assistant_inspect")
    assert not is_mutating_action("ssh_console_status")

import asyncio

def test_native_resource_and_tool_argument_boundaries(monkeypatch):
    import server
    from owner_ssh_widget import URI
    tools = asyncio.run(server.mcp.list_tools())
    by_name = {tool.name: tool for tool in tools}
    status = by_name["vps_ssh_session_status"]
    assert status.meta["ui"]["resourceUri"] == URI
    assert status.meta["openai/ui"]["entrypoints"] == [{"type": "global"}, {"type": "thread"}]
    content = asyncio.run(server.mcp.read_resource(URI))
    assert "VPS-Konsole" in content[0].content
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("Invalid input reached broker")
    monkeypatch.setattr(server.broker, "call", forbidden)
    with pytest.raises(Exception):
        asyncio.run(server.mcp.call_tool("vps_ssh_inspect", {"session_id": "invalid", "operation": "disk"}))
    with pytest.raises(Exception):
        asyncio.run(server.mcp.call_tool("vps_ssh_inspect", {"session_id": "a" * 32, "operation": "shell"}))
    assert calls == []

def test_pending_owner_revocation_blocks_queued_inspection(console):
    instance, session_id, calls = connected(console)
    instance.owner_action(owner_action(instance, "grant", sessionId=session_id, operations=["disk"], ttl=30))
    owner_action(instance, "revoke", sessionId=session_id)
    with pytest.raises(ValueError, match="pending"):
        instance.assistant_inspect(session_id, "disk")
    assert not any("df -h" in argv for argv in calls)


def test_revocation_during_inspection_withholds_result(console):
    instance, session_id, calls = connected(console)
    instance.owner_action(owner_action(instance, "grant", sessionId=session_id, operations=["disk"], ttl=30))
    original = instance.runner
    def runner(argv, **kwargs):
        result = original(argv, **kwargs)
        if "df -h" in argv:
            owner_action(instance, "revoke", sessionId=session_id)
        return result
    instance.runner = runner
    with pytest.raises(ValueError, match="pending"):
        instance.assistant_inspect(session_id, "disk")
    assert instance._state().get("lastActivity") is None


def test_unconfirmed_close_never_reports_closed(console):
    instance, session_id, calls = connected(console)
    instance.runner = lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr="")
    with pytest.raises(ValueError, match="remained active"):
        instance.owner_action(owner_action(instance, "close", sessionId=session_id))
    state = instance._state()
    assert state["status"] == "close_unverified" and state["grantUntil"] == 0
    assert (instance.root / ("ssh-" + session_id) / "identity").exists()

def test_output_redacts_current_protected_value(console):
    instance, profile, calls = console
    profile.pop("privateKey")
    profile["password"] = "synthetic-not-a-real-login"
    instance._write("ssh_console_profile.json", profile)
    result = instance.owner_action(owner_action(instance, "connect"))
    instance.owner_action(owner_action(instance, "grant", sessionId=result["sessionId"], operations=["disk"], ttl=30))
    def runner(argv, **kwargs):
        return SimpleNamespace(returncode=0, stdout=profile["password"], stderr="")
    instance.runner = runner
    observed = instance.assistant_inspect(result["sessionId"], "disk")
    assert observed["output"] == "[REDACTED]"
    assert profile["password"] not in json.dumps(instance._state())


def test_actual_page_scripts_parse_without_external_resources(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node unavailable; actual script syntax is verified in MCP CI")
    import ast
    from owner_ssh_widget import HTML
    source = (ROOT / "scripts/sovereign-backend/owner_ssh_routes.py").read_text()
    tree = ast.parse(source)
    page = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "PAGE" for target in node.targets))
    for index, html in enumerate((page, HTML)):
        script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        path = tmp_path / ("script-" + str(index) + ".cjs")
        path.write_text(script)
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    assert "localStorage" not in page and "sessionStorage" not in page
    assert "textContent" in page and "innerHTML" not in page
