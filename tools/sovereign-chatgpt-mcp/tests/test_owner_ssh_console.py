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
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "f" * 40)
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

def shell_grant(instance, session_id, command, timeout_seconds=30, ttl=300):
    digest = instance.validate_shell_command(command, timeout_seconds)
    return instance.owner_action(owner_action(instance, "grant", sessionId=session_id,
        operations=["shell"], ttl=ttl, commandSha256=digest, timeoutSeconds=timeout_seconds))


def full_owner_session(console):
    instance, profile, calls = console
    profile.update(host="46.202.154.25", username="root", expiresInSeconds=0)
    instance._write("ssh_console_profile.json", profile)
    result = instance.owner_action(owner_action(instance, "connect"))
    return instance, result["sessionId"], calls


def test_designated_owner_vps_gets_one_persistent_full_session(console):
    instance, session_id, calls = full_owner_session(console)
    status = instance.status(session_id)
    assert status["fullAccess"] is True and status["assistantGrantActive"] is True
    assert status["expiresAt"] is None
    assert {"shell", "workspace", *OPERATIONS} <= set(status["allowedOperations"])
    assert any("ControlPersist=yes" in argv for argv in calls)


def test_full_session_runs_different_commands_and_returns_paginated_output(console, monkeypatch):
    instance, session_id, calls = full_owner_session(console)
    monkeypatch.delenv("SOVEREIGN_SOURCE_REVISION", raising=False)
    observed = []
    body = (b"owner-secret-example\n" * 5000) + bytes([255])

    def transport(argv, *, timeout_seconds, guard, output_streams):
        guard()
        observed.append((argv, timeout_seconds))
        output_streams[1].write(body)
        output_streams[2].write(b"diagnostic\n")
        return SimpleNamespace(returncode=0, stdout_bytes=len(body), stderr_bytes=11)

    instance.shell_runner = transport
    first = instance.assistant_shell(session_id, "printf x # " + "x" * 9000, timeout_seconds=None)
    second = instance.assistant_shell(session_id, "id", timeout_seconds=None)
    assert first["ok"] and second["ok"] and len(observed) == 2
    assert all(timeout is None and "systemd-run" not in argv[-1] for argv, timeout in observed)
    assert first["stdoutBytes"] == len(body) and first["stdout"]["eof"] is False
    assert first["stderr"]["text"] == "diagnostic\n"
    chunks = [base64.b64decode(first["stdout"]["base64"])]
    offset = first["stdout"]["nextOffset"]
    while True:
        page = instance.assistant_shell_output(session_id, first["executionId"], "stdout", offset)
        chunks.append(base64.b64decode(page["base64"]))
        offset = page["nextOffset"]
        if page["eof"]:
            break
    assert b"".join(chunks) == body
    assert "owner-secret-example" not in json.dumps(instance._state())
    assert instance.status(session_id)["assistantGrantActive"] is True
    with pytest.raises(ValueError, match="identity"):
        instance.assistant_shell_output("a" * 32, first["executionId"], "stdout")


def test_full_shell_transport_captures_binary_output_without_a_deadline(tmp_path):
    from owner_ssh_console import _shell_transport
    out = tmp_path / "out"
    err = tmp_path / "err"
    code = "import sys;sys.stdout.buffer.write(bytes([255])*110000);sys.stderr.write('ok')"
    with out.open("wb") as stdout, err.open("wb") as stderr:
        result = _shell_transport([sys.executable, "-c", code], timeout_seconds=None,
                                  guard=lambda: None, output_streams={1: stdout, 2: stderr})
    assert result.returncode == 0 and result.stdout_bytes == 110000 and result.stderr_bytes == 2
    assert out.read_bytes() == bytes([255]) * 110000 and err.read_bytes() == b"ok"

def test_owner_connection_checks_host_and_keeps_material_out_of_arguments(console):
    instance, session_id, calls = connected(console)
    serialized = json.dumps(calls)
    assert "synthetic-unusable-ssh-material" not in serialized
    assert any("StrictHostKeyChecking=yes" in argv for argv in calls)
    assert any("IdentityAgent=none" in argv for argv in calls)
    assert instance.status(session_id)["status"] == "connected"
    assert "privateKey" not in json.dumps(instance.status(session_id))
    assert (instance.root / ("ssh-" + session_id) / "identity").stat().st_mode & 0o777 == 0o600

@pytest.mark.parametrize("port", [22, 2222])
def test_known_host_entry_matches_actual_openssh_lookup(console, port):
    if not shutil.which("ssh-keygen"):
        pytest.skip("OpenSSH key lookup unavailable in this isolated environment")
    instance, profile, calls = console
    profile["port"] = port
    instance._write("ssh_console_profile.json", profile)
    result = instance.owner_action(owner_action(instance, "connect"))
    lookup = profile["host"] if port == 22 else "[" + profile["host"] + "]:" + str(port)
    known = instance.root / ("ssh-" + result["sessionId"]) / "known_hosts"
    observed = subprocess.run(["ssh-keygen", "-F", lookup, "-f", str(known)], capture_output=True, text=True)
    assert observed.returncode == 0, observed.stderr
    assert profile["knownHostKey"] in observed.stdout


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



def test_shell_requires_specific_command_bound_owner_approval(console):
    instance, session_id, calls = connected(console)
    with pytest.raises(ValueError, match="delegation"):
        instance.assistant_shell(session_id, "uname -a")
    instance.owner_action(owner_action(instance, "grant", sessionId=session_id, operations=["disk"], ttl=300))
    with pytest.raises(ValueError, match="delegation"):
        instance.assistant_shell(session_id, "uname -a")
    with pytest.raises(ValueError, match="Command-bound"):
        instance.owner_action(owner_action(instance, "grant", sessionId=session_id, operations=["shell"], ttl=300))
    with pytest.raises(ValueError, match="delegation"):
        instance.assistant_shell(session_id, "uname -a")
    shell_grant(instance, session_id, "uname -a")
    with pytest.raises(ValueError, match="Owner approval does not match"):
        instance.assistant_shell(session_id, "id")
    assert not any("/bin/sh -c" in " ".join(map(str, argv)) for argv in calls)


def test_shell_executes_once_and_returns_only_a_revision_bound_receipt(console):
    instance, session_id, calls = connected(console)
    command = "printf 'one;two;three' | cut -d ';' -f 3"
    shell_grant(instance, session_id, command, timeout_seconds=25)
    observed = []
    def transport(argv, *, timeout_seconds, guard):
        guard()
        observed.append(argv)
        guard()
        return SimpleNamespace(returncode=0, stdout="sensitive output", stderr="sensitive error",
                               stdout_bytes=6, stderr_bytes=8)
    instance.shell_runner = transport
    result = instance.assistant_shell(session_id, command, timeout_seconds=25)
    assert result["status"] == "SSH_SHELL_EXECUTED" and result["exitCode"] == 0
    assert result["stdoutBytes"] == 6 and result["stderrBytes"] == 8
    assert result["outputReturned"] is False and "output" not in result
    assert result["commandSha256"] == hashlib.sha256(command.encode()).hexdigest()
    assert result["profileSha256"] == instance._state()["profileSha256"]
    assert result["sourceRevision"] == "f" * 40
    assert result["targetStateVerified"] is False
    assert "sensitive" not in json.dumps(result) and "sensitive" not in json.dumps(instance._state())
    assert len(observed) == 1
    assert "ProxyCommand=false" in observed[0] and "ControlMaster=no" in observed[0]
    assert "/bin/sh -c" in observed[0][-1]
    assert "systemd-run --user --scope" in observed[0][-1]
    assert "sovott-ssh-shell-" in observed[0][-1]
    assert any("systemctl --user show --property=ActiveState" in argv[-1] for argv in calls)
    assert "command" not in instance._state()["lastActivity"]
    assert instance._state()["lastActivity"]["commandSha256"] == result["commandSha256"]
    with pytest.raises(ValueError, match="approval"):
        instance.assistant_shell(session_id, command, timeout_seconds=25)


def test_shell_fails_closed_on_revocation_or_expired_grant(console):
    instance, session_id, calls = connected(console)
    shell_grant(instance, session_id, "whoami", ttl=60)
    instance.owner_action(owner_action(instance, "revoke", sessionId=session_id))
    with pytest.raises(ValueError, match="delegation"):
        instance.assistant_shell(session_id, "whoami")
    shell_grant(instance, session_id, "whoami", ttl=60)
    state = instance._state()
    state["grantUntil"] = time.time() - 1
    instance._write("ssh_console_state.json", state)
    with pytest.raises(ValueError, match="delegation"):
        instance.assistant_shell(session_id, "whoami")


def test_shell_revocation_during_transport_blocks_result_and_keeps_safe_receipt(console):
    instance, session_id, calls = connected(console)
    shell_grant(instance, session_id, "uptime")
    def transport(argv, *, timeout_seconds, guard):
        guard()
        instance._write("ssh_console_revocation.json", {"sessionId": session_id, "at": time.time()})
        guard()
        return subprocess.CompletedProcess(argv, 0, "should-not-return", "")
    instance.shell_runner = transport
    with pytest.raises(ValueError, match="revocation"):
        instance.assistant_shell(session_id, "uptime")
    activity = instance._state()["lastActivity"]
    assert activity["status"] == "SSH_SHELL_INTERRUPTED_OUTCOME_UNKNOWN"
    assert "output" not in activity and "command" not in activity


def test_shell_failure_and_secret_output_are_withheld(console):
    instance, profile, calls = console
    profile.pop("privateKey")
    profile["password"] = "synthetic-password-not-real"
    instance._write("ssh_console_profile.json", profile)
    result = instance.owner_action(owner_action(instance, "connect"))
    session_id = result["sessionId"]
    shell_grant(instance, session_id, "false")
    def transport(argv, *, timeout_seconds, guard):
        guard()
        return SimpleNamespace(returncode=7, stdout="password=secret-value\\n" + profile["password"],
                               stderr="database://credential", stdout_bytes=50, stderr_bytes=29)
    instance.shell_runner = transport
    result = instance.assistant_shell(session_id, "false")
    assert result["ok"] is False and result["exitCode"] == 7
    assert result["targetStateVerified"] is False
    assert result["outputReturned"] is False and "output" not in result
    assert "secret-value" not in json.dumps(result)
    assert profile["password"] not in json.dumps(result)
    assert profile["password"] not in json.dumps(instance._state())
    assert "database://credential" not in json.dumps(instance._state())


def test_shell_approval_is_bound_to_runtime_source_revision(console):
    instance, session_id, calls = connected(console)
    shell_grant(instance, session_id, "uptime")
    state = instance._state()
    state["shellApproval"]["sourceRevision"] = "e" * 40
    instance._write("ssh_console_state.json", state)
    instance.shell_runner = lambda *_args, **_kwargs: pytest.fail("stale revision reached transport")
    with pytest.raises(ValueError, match="approval"):
        instance.assistant_shell(session_id, "uptime")


def test_shell_runtime_revision_change_interrupts_inflight_execution(console, monkeypatch):
    instance, session_id, calls = connected(console)
    shell_grant(instance, session_id, "uptime")
    def transport(argv, *, timeout_seconds, guard):
        monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "e" * 40)
        guard()
    instance.shell_runner = transport
    with pytest.raises(ValueError, match="source revision changed"):
        instance.assistant_shell(session_id, "uptime")
    assert instance._state()["lastActivity"]["status"] == "SSH_SHELL_INTERRUPTED_OUTCOME_UNKNOWN"


def test_shell_profile_replacement_interrupts_inflight_execution(console):
    instance, session_id, calls = connected(console)
    shell_grant(instance, session_id, "uptime")
    def transport(argv, *, timeout_seconds, guard):
        profile = instance._json("ssh_console_profile.json")
        profile["username"] = "changed"
        instance._write("ssh_console_profile.json", profile)
        guard()
    instance.shell_runner = transport
    with pytest.raises(ValueError, match="profile changed"):
        instance.assistant_shell(session_id, "uptime")
    activity = instance._state()["lastActivity"]
    assert activity["status"] == "SSH_SHELL_INTERRUPTED_OUTCOME_UNKNOWN"
    assert instance._state().get("shellApproval") is None
    assert "output" not in activity


def test_shell_transport_discards_binary_streams_and_never_sends_stdin():
    from owner_ssh_console import _shell_transport
    code = "import sys;sys.stdout.buffer.write(bytes([255]));sys.stderr.buffer.write(bytes([254]));sys.exit(0 if sys.stdin.buffer.read()==b'' else 2)"
    completed = _shell_transport([sys.executable, "-c", code], timeout_seconds=3, guard=lambda: None)
    assert completed.returncode == 0
    assert completed.stdout == "" and completed.stderr == ""
    assert completed.stdout_bytes == 1 and completed.stderr_bytes == 1


def test_shell_transport_kills_descendants_after_timeout(tmp_path):
    from owner_ssh_console import _shell_transport
    marker = tmp_path / "child-finished"
    child_code = f"import time; time.sleep(0.25); open({str(marker)!r}, 'w').write('done')"
    parent_code = "import subprocess,sys; subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "]); sys.exit(0)"
    with pytest.raises(subprocess.TimeoutExpired):
        _shell_transport([sys.executable, "-c", parent_code], timeout_seconds=0.05, guard=lambda: None)
    time.sleep(0.4)
    assert not marker.exists()


def orphaned_execution(instance, execution_id):
    state = instance._state()
    state.update(shellExecutionId=execution_id,
                 lastActivity={"operation": "shell", "status": "SSH_SHELL_STARTED",
                               "executionId": execution_id})
    instance._write("ssh_console_state.json", state)


def test_status_projects_orphan_without_remote_mutation_or_state_write(console):
    instance, session_id, calls = connected(console)
    orphaned_execution(instance, "a" * 32)
    before = (instance.root / "ssh_console_state.json").read_bytes()
    calls_before = len(calls)
    observed = instance.status(session_id)
    assert observed["status"] == "SSH_SHELL_RECOVERY_REQUIRED"
    assert observed["shellRecoveryRequired"] is True
    assert observed["assistantGrantActive"] is False
    assert (instance.root / "ssh_console_state.json").read_bytes() == before
    assert len(calls) == calls_before


def test_owner_revoke_stops_orphan_before_clearing_execution_id(console):
    instance, session_id, calls = connected(console)
    execution_id = "b" * 32
    orphaned_execution(instance, execution_id)
    instance.owner_action(owner_action(instance, "revoke", sessionId=session_id))
    state = instance._state()
    assert not state["shellExecutionId"]
    assert state["lastActivity"]["status"] == "SSH_SHELL_INTERRUPTED_OUTCOME_UNKNOWN"
    assert state["grantUntil"] == 0 and state["allowedOperations"] == []
    stop_command = next(argv[-1] for argv in calls if "systemctl --user show --property=LoadState" in argv[-1])
    syntax = subprocess.run(["/bin/sh", "-n", "-c", stop_command], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr


def test_failed_orphan_stop_blocks_revoke_and_grant_overwrite(console):
    instance, session_id, _calls = connected(console)
    for action in ("revoke", "grant"):
        execution_id = ("c" if action == "revoke" else "d") * 32
        orphaned_execution(instance, execution_id)
        instance.runner = lambda *args, **kwargs: SimpleNamespace(returncode=255, stdout="", stderr="")
        with pytest.raises(ValueError, match="Orphaned remote SSH shell"):
            if action == "revoke":
                instance.owner_action(owner_action(instance, action, sessionId=session_id))
            else:
                command = "uname"
                digest = instance.validate_shell_command(command, 30)
                instance.owner_action(owner_action(instance, action, sessionId=session_id, operations=["shell"],
                                                   ttl=300, commandSha256=digest, timeoutSeconds=30))
        state = instance._state()
        assert state["shellExecutionId"] == execution_id
        assert state["lastActivity"]["status"] == "SSH_SHELL_INTERRUPTED_OUTCOME_UNKNOWN"
        assert state["grantUntil"] == 0 and state["allowedOperations"] == []


def test_shell_timeout_returns_ambiguous_receipt_and_consumes_approval(console):
    instance, session_id, calls = connected(console)
    shell_grant(instance, session_id, "long-op", timeout_seconds=2)
    def transport(argv, *, timeout_seconds, guard):
        guard()
        raise subprocess.TimeoutExpired(argv, timeout_seconds)
    instance.shell_runner = transport
    result = instance.assistant_shell(session_id, "long-op", timeout_seconds=2)
    assert result["status"] == "SSH_SHELL_OUTCOME_UNKNOWN" and result["exitCode"] is None
    assert result["outputReturned"] is False
    with pytest.raises(ValueError, match="approval"):
        instance.assistant_shell(session_id, "long-op", timeout_seconds=2)


@pytest.mark.parametrize("command,timeout", [("", 30), ("a" * 9000, 30), ("printf " + chr(0), 30),
                                                  ("echo " + chr(0x202e) + "danger", 30),
                                                  ("echo " + chr(0x200b) + "hidden", 30),
                                                  ("echo " + chr(1), 30), ("uname", 0), ("uname", 301)])
def test_shell_invalid_command_or_timeout_rejected_before_transport(console, command, timeout):
    instance, session_id, calls = connected(console)
    with pytest.raises(ValueError):
        instance.assistant_shell(session_id, command, timeout_seconds=timeout)


@pytest.mark.parametrize("ops,ttl", [(["shell"], 30), (["shell"], 901), (["shell", "workspace"], 900), (["shell", "disk"], 300)])
def test_shell_grant_rejects_wrong_lifetime_or_mixed_scope(console, ops, ttl):
    instance, session_id, calls = connected(console)
    with pytest.raises(ValueError, match="scope|lifetime"):
        instance.owner_action(owner_action(instance, "grant", sessionId=session_id, operations=ops, ttl=ttl))

def test_canonical_backend_mirrors_and_queue_route():
    for name in ("owner_ssh_console.py", "command_queue.py", "command_contract.py"):
        assert (ROOT / "tools/sovereign-chatgpt-mcp" / name).read_bytes() == (ROOT / "scripts/sovereign-backend" / name).read_bytes()
    from command_contract import is_mutating_action
    assert is_mutating_action("ssh_console_owner_action")
    assert is_mutating_action("ssh_console_assistant_inspect")
    assert not is_mutating_action("ssh_console_status")

import asyncio

def test_broker_routes_output_read_and_keeps_shell_on_host_queue():
    from types import SimpleNamespace
    from broker import BrokerRuntime

    runtime = BrokerRuntime.__new__(BrokerRuntime)
    runtime.private_owner_mode = True
    calls = []
    runtime.owner_ssh = SimpleNamespace(
        assistant_shell_output=lambda *args: calls.append(args) or {"ok": True, "status": "TEST_OUTPUT"},
        assistant_shell=lambda *args: calls.append(args) or {"ok": True, "status": "TEST_SHELL"},
    )
    session_id, execution_id = "a" * 32, "b" * 32
    result = runtime.dispatch("ssh_console_assistant_output", {
        "session_id": session_id, "execution_id": execution_id,
        "stream": "stdout", "offset": 16384, "limit": 65536,
    })
    assert result["status"] == "TEST_OUTPUT"
    assert calls == [(session_id, execution_id, "stdout", 16384, 65536)]
    args = {"session_id": session_id, "command": "true", "timeout_seconds": None}
    assert runtime.dispatch("ssh_console_assistant_shell", args)["status"] == "BLOCKED"
    assert runtime.dispatch("ssh_console_assistant_shell", args, execution_origin="host_worker")["status"] == "TEST_SHELL"
    assert calls[-1] == (session_id, "true", None)


def test_shell_mcp_accepts_long_commands_and_exposes_output_pages(monkeypatch):
    import server
    calls = []
    def queue_enqueue(action, arguments):
        calls.append((action, arguments))
        return {"ok": True, "status": "QUEUED", "request_id": "c" * 32}
    def broker_call(action, arguments, *, timeout=None):
        calls.append((action, arguments, timeout))
        return {"ok": True, "status": "TEST_BOUNDARY"}
    monkeypatch.setattr(server.broker.command_queue, "enqueue", queue_enqueue)
    monkeypatch.setattr(server.broker, "call", broker_call)
    command = "printf x # " + "x" * 9000
    asyncio.run(server.mcp._tool_manager.call_tool(
        "vps_ssh_shell", {"session_id": "a" * 32, "command": command}, convert_result=False
    ))
    asyncio.run(server.mcp._tool_manager.call_tool(
        "vps_ssh_shell_output", {"session_id": "a" * 32, "execution_id": "b" * 32,
                                 "stream": "stdout", "offset": 16384}, convert_result=False
    ))
    assert calls[0][0] == "ssh_console_assistant_shell"
    assert calls[0][1]["command"] == command and calls[0][1]["timeout_seconds"] is None
    assert calls[1][0] == "ssh_console_assistant_output" and calls[1][1]["offset"] == 16384


def test_shell_queue_admission_remains_queued_without_a_claimant(tmp_path, monkeypatch):
    import server
    from command_queue import HostCommandQueueClient

    queue = HostCommandQueueClient(str(tmp_path / "queue"))
    monkeypatch.setattr(server.broker, "command_queue", queue)
    queued = server.vps_ssh_shell("a" * 32, "true")
    assert queued["status"] == "QUEUED"
    assert queue.status(queued["request_id"])["status"] == "QUEUED"


def test_native_resource_and_tool_argument_boundaries(monkeypatch):
    import server
    from owner_ssh_widget import URI
    tools = asyncio.run(server.mcp.list_tools())
    by_name = {tool.name: tool for tool in tools}
    status = by_name["vps_ssh_session_status"]
    shell = by_name["vps_ssh_shell"]
    assert "command" in shell.inputSchema["properties"]
    assert "session_id" in shell.inputSchema["properties"]
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

def test_actual_process_capture_is_bounded_and_times_out(tmp_path):
    instance = OwnerSSHConsole(root=tmp_path)
    result = instance._run(["python3", "-c", "import sys;sys.stdout.write(chr(120)*1000000)"], timeout=2)
    assert result.returncode != 0
    assert len(result.stdout.encode()) <= 65536
    with pytest.raises(subprocess.TimeoutExpired):
        instance._run(["python3", "-c", "import time;time.sleep(5)"], timeout=0.1)


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
    assert 'id="shellTimeout"' in page and 'value="300"' in page
    assert "Number($('shellTimeout').value)" in page
    assert "displayControl" in page and "control.test(ch)" in page

def test_server_host_key_comment_normalized_without_touching_login_method(console):
    instance, profile, calls = console
    original = profile["knownHostKey"]
    profile["knownHostKey"] += " server.example"
    observed = instance.validate_profile(profile)
    assert observed[3] == original
    assert observed[-1] == ""
    assert calls == []


def test_password_first_host_key_probe_is_public_and_needs_no_login_material(console):
    instance, profile, calls = console
    profile.pop("privateKey")
    profile["password"] = "synthetic-not-a-real-password"
    commands = []
    def keyscan(argv, **kwargs):
        commands.append(argv)
        return SimpleNamespace(returncode=0, stdout=profile["host"] + " " + profile["knownHostKey"] + "\n", stderr="")
    instance.runner = keyscan
    result = instance.owner_action(owner_action(instance, "probe", host=profile["host"], port=22))
    assert result["ok"] is True
    assert result["status"] == "SSH_HOST_KEY_DISCOVERED"
    assert result["knownHostKey"] == profile["knownHostKey"]
    assert result["hostFingerprint"].startswith("SHA256:")
    assert commands[0][:2] == ["ssh-keyscan", "-T"]
    assert "synthetic-not-a-real-password" not in json.dumps(commands)
    assert not (instance.root / "ssh_console_state.json").exists()


def test_ssh_probe_rejects_untrusted_or_internal_target(console):
    instance, profile, calls = console
    observed_calls = []
    def wrong_server(argv, **kwargs):
        observed_calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="9.9.9.9 " + profile["knownHostKey"] + "\n", stderr="")
    instance.runner = wrong_server
    with pytest.raises(ValueError, match="unavailable or ambiguous"):
        instance._probe_host_key(profile["host"], 22)
    with pytest.raises(ValueError, match="public IP"):
        instance._probe_host_key("127.0.0.1", 22)
    assert len(observed_calls) == 1


def workspace_granted(console):
    instance, session_id, calls = connected(console)
    state = instance._state()
    state['expiresAt'] = time.time() + 3600
    instance._write('ssh_console_state.json', state)
    instance.owner_action(owner_action(instance, 'grant', sessionId=session_id, operations=['workspace'], ttl=900, createdAt=time.time()))
    return instance, session_id, calls


def test_workspace_requires_its_own_owner_grant(console):
    instance, session_id, calls = connected(console)
    instance.owner_action(owner_action(instance, 'grant', sessionId=session_id, operations=['disk'], ttl=30))
    with pytest.raises(ValueError, match='delegation'):
        instance.assistant_workspace(session_id, 'a'*40, 'init')
    with pytest.raises(ValueError):
        instance.validate_grant(['workspace'], 899)
    with pytest.raises(ValueError):
        instance.validate_grant(['workspace'], 3601)


def test_workspace_grant_repeated_actions_and_target_hash_readback(console):
    instance, session_id, calls = workspace_granted(console)
    received = []
    def runner(argv, *, guard, deadline):
        import shlex
        request = json.loads(base64.b64decode(shlex.split(argv[-1])[-2]))
        received.append(request)
        guard()
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            'ok': True, 'status': 'SSH_WORKSPACE_COMPLETE', **{k: request[k] for k in ('sessionId','grantId','sourceRevision','action')},
            'sha256': hashlib.sha256(request['content'].encode()).hexdigest(), 'bytes': len(request['content']),
        }), stderr='')
    instance.workspace_runner = runner
    for value in ("print(1)\n", "print(2)\n"):
        result = instance.assistant_workspace(session_id, 'a'*40, 'write', 'test.py', value, 'absent')
        assert result['ok'] is True and result['sha256'] == hashlib.sha256(value.encode()).hexdigest()
    assert len(received) == 2 and received[0]['grantId'] == received[1]['grantId']
    assert received[0]['sourceRevision'] == 'a'*40


def test_expired_or_revoked_workspace_cannot_execute(console):
    instance, session_id, calls = workspace_granted(console)
    instance.workspace_runner = lambda *_args, **_kw: pytest.fail('Expired work reached transport')
    state = instance._state()
    state['grantUntil'] = time.time() - 1
    instance._write('ssh_console_state.json', state)
    with pytest.raises(ValueError, match='delegation'):
        instance.assistant_workspace(session_id, 'a'*40, 'init')
    state['grantUntil'] = time.time() + 900
    instance._write('ssh_console_state.json', state)
    instance._write('ssh_console_revocation.json', {'sessionId':session_id, 'at':time.time()-60})
    with pytest.raises(ValueError, match='pending'):
        instance.assistant_workspace(session_id, 'a'*40, 'init')
    assert instance.status(session_id)['assistantGrantActive'] is False


def test_workspace_mutation_routes_through_the_host_queue():
    from command_contract import is_mutating_action
    assert is_mutating_action('ssh_console_assistant_workspace')


def test_workspace_is_a_real_mcp_tool_with_no_kwargs_permission_bypass(monkeypatch):
    import server
    calls=[]
    monkeypatch.setattr(server.broker,'call',lambda action, arguments, **kwargs: calls.append((action,arguments)) or {'ok':True})
    tools=asyncio.run(server.mcp.list_tools())
    tool=next(t for t in tools if t.name=='vps_ssh_workspace')
    assert 'kwargs' not in tool.inputSchema['properties']
    assert 'owner_approved' not in tool.inputSchema['properties']
    assert tool.inputSchema['properties']['action']['enum']==['init','write','read','run']
    assert tool.annotations.readOnlyHint is False
    with pytest.raises(Exception):
        asyncio.run(server.mcp.call_tool('vps_ssh_workspace',{'session_id':'a'*32,'source_revision':'a'*40,'action':'run','argv':['sudo','id']}))
    assert calls==[]
    asyncio.run(server.mcp.call_tool('vps_ssh_workspace',{'session_id':'a'*32,'source_revision':'a'*40,'action':'run','argv':['python3','test.py']}))
    assert calls[0][0]=='ssh_console_assistant_workspace'


def test_target_response_cannot_forge_workspace_identity(console):
    instance, session_id, calls = workspace_granted(console)
    instance.workspace_runner = lambda *_args, **_kw: SimpleNamespace(returncode=0, stdout=json.dumps({
        'ok':True,'status':'SSH_WORKSPACE_COMPLETE','sessionId':'b'*32,'grantId':'b'*32,'sourceRevision':'a'*40,'action':'init'}))
    with pytest.raises(ValueError, match='identity mismatch'):
        instance.assistant_workspace(session_id, 'a'*40, 'init')


@pytest.mark.parametrize("family,expected", [
    ("WORKSPACE_BWRAP_UNAVAILABLE", "WORKSPACE_BWRAP_UNAVAILABLE"),
    ("synthetic-private-detail", "WORKSPACE_TARGET_FAILED"),
    (["synthetic-private-detail"], "WORKSPACE_TARGET_FAILED"),
])
def test_workspace_failure_propagates_only_allowlisted_family(console, family, expected):
    instance, session_id, calls = workspace_granted(console)
    instance.workspace_runner = lambda *_args, **_kw: SimpleNamespace(returncode=1, stdout=json.dumps({
        "ok": False, "status": "SSH_WORKSPACE_BLOCKED", "failureFamily": family,
        "blocker": "synthetic-private-detail"}), stderr="synthetic-private-detail")
    result = instance.assistant_workspace(session_id, "a"*40, "run", argv=["python3", "-V"])
    assert result["ok"] is False and result["failureFamily"] == expected
    assert "synthetic-private" not in json.dumps(result)
