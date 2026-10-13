"""Exercise production path operations and real subprocess/lease supervision."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/sovereign-chatgpt-mcp"))
from owner_ssh_workspace import validate_request, file_action, sandbox_argv, unit_argv, supervise, storage_guard
from owner_ssh_console import _workspace_transport


@pytest.fixture
def worktree(tmp_path, monkeypatch):
    # Ownership provisioning is an external host adapter, including root in a
    # user namespace without a mapping for nobody. Dirfd/write/readback stays real.
    monkeypatch.setattr(os, "fchown", lambda *_: None)
    return tmp_path


def test_repeated_revision_bound_writes_and_independent_readback(worktree):
    first = file_action(worktree, validate_request("write", "src/test.py", "print(1)\n", "absent"))
    readback = file_action(worktree, validate_request("read", "src/test.py"))
    assert readback["content"] == "print(1)\n" and readback["sha256"] == first["sha256"]
    second = file_action(worktree, validate_request("write", "src/test.py", "print(2)\n", first["sha256"]))
    assert second["sha256"] == hashlib.sha256(b"print(2)\n").hexdigest()
    with pytest.raises(ValueError, match="revision changed"):
        file_action(worktree, validate_request("write", "src/test.py", "stale", first["sha256"]))
    assert file_action(worktree, validate_request("read", "src/test.py"))["sha256"] == second["sha256"]


@pytest.mark.parametrize("path", ["../outside", "/etc/passwd", "a/../../outside", "a//b", "a/./b", ".git/config", "a\\b", "a/", "a\x00b"])
def test_path_escape_rejected_before_any_effect(path):
    with pytest.raises(ValueError):
        validate_request("write", path, "data", "absent")


def test_symlink_and_hardlink_cannot_read_or_modify_outside(worktree):
    outside = worktree.parent / (worktree.name + "-outside")
    outside.mkdir()
    original = outside / "source"
    original.write_text("preserved")
    (worktree / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        file_action(worktree, validate_request("write", "link/source", "changed", "absent"))
    (worktree / "filelink").symlink_to(original)
    with pytest.raises(OSError):
        file_action(worktree, validate_request("read", "filelink"))
    os.link(original, worktree / "hardlink")
    with pytest.raises(ValueError, match="link count"):
        file_action(worktree, validate_request("read", "hardlink"))
    assert original.read_text() == "preserved"


def test_fifo_is_rejected_without_blocking(worktree):
    os.mkfifo(worktree / "fifo")
    with pytest.raises(ValueError, match="file type"):
        file_action(worktree, validate_request("read", "fifo"))


@pytest.mark.parametrize("kwargs", [
    {"action": "run", "argv": ["sudo", "id"]}, {"action": "run", "argv": "python3"},
    {"action": "run", "argv": ["python3", "\x00"]}, {"action": "run", "argv": ["python3"], "timeout_seconds": True},
    {"action": "run", "argv": ["python3"], "timeout_seconds": 301},
    {"action": "write", "path": "x", "content": "x" * 32769, "expected_sha256": "absent"},
    {"action": "write", "path": "x", "content": "x"}, {"action": "read", "path": "x", "argv": ["cat"]},
])
def test_invalid_command_and_write_contract(kwargs):
    with pytest.raises(ValueError):
        validate_request(**kwargs)


def test_namespace_and_cgroup_contract_excludes_live_mounts(tmp_path):
    command = sandbox_argv(tmp_path, ["python3", "-c", "print(1)"])
    assert "--unshare-all" in command and "--clearenv" in command and "--die-with-parent" in command
    assert command[command.index("--uid") + 1] == "65534"
    for private in ("/etc", "/opt", "/root", "/home", "/run", "/var", "/"):
        assert not any(command[i+1] == private for i, v in enumerate(command[:-1]) if v in {"--bind", "--ro-bind"})
    unit = unit_argv(tmp_path, {"timeout_seconds": 30, "deadline": time.time()+900, "argv": ["node", "test.js"]}, "sovereign-ssh-"+"a"*32+".service", "reviewed-source")
    assert all(v in unit for v in ("User=65534", "MemoryMax=2G", "MemorySwapMax=0", "CPUQuota=200%", "TasksMax=128", "KillMode=control-group"))


def run_with_lease(argv, *, duration=1, timeout=2, output_limit=65536):
    read, write = os.pipe()
    def heartbeat():
        until = time.monotonic()+duration
        try:
            while time.monotonic() < until:
                os.write(write, b".\n")
                time.sleep(0.03)
        except BrokenPipeError:
            pass
        finally:
            os.close(write)
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        return supervise(argv, deadline=time.time()+timeout, lease_fd=read, output_limit=output_limit)
    finally:
        os.close(read)
        thread.join(timeout=3)


def test_real_python_process_can_run_twice():
    for number in (1, 2):
        result = run_with_lease([sys.executable, "-c", "print("+str(number)+")"], duration=0.2)
        assert result["exitCode"] == 0 and result["output"] == str(number)+"\n"


def test_real_output_flood_stops_and_remains_bounded():
    result = run_with_lease([sys.executable, "-c", "import sys;sys.stdout.write('x'*1000000)"], output_limit=1024, duration=0.2)
    assert result["exitCode"] == 255 and result["stopReason"] == "OUTPUT_LIMIT"
    assert len(result["output"].encode()) <= 1024


def test_real_timeout_stops_process():
    start = time.monotonic()
    result = run_with_lease([sys.executable, "-c", "import time;time.sleep(30)"], timeout=0.2, duration=0.4)
    assert result["stopReason"] == "TIMEOUT" and time.monotonic()-start < 2


def test_real_host_abort_kills_parent_and_child_process():
    source = "import subprocess,sys,time;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);print(p.pid,flush=True);time.sleep(30)"
    result = run_with_lease([sys.executable, "-c", source], duration=0.3)
    assert result["stopReason"] == "HOST_ABORTED" and result["exitCode"] == 255
    child = int(result["output"].strip())
    status = Path('/proc') / str(child) / 'stat'
    assert not status.exists() or status.read_text().split()[2] == 'Z'


def test_transport_revocation_stops_a_real_inflight_process(tmp_path):
    pidfile = tmp_path / "pid"
    source = "import os,time;open("+repr(str(pidfile))+",'w').write(str(os.getpid()));time.sleep(30)"
    def guard():
        if pidfile.exists():
            raise ValueError("revoked")
    with pytest.raises(ValueError, match="revoked"):
        _workspace_transport([sys.executable, "-c", source], deadline=time.time()+2, guard=guard)
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_workspace_helper_and_console_are_byte_equal_shipping_mirrors():
    for name in ("owner_ssh_console.py", "owner_ssh_workspace.py", "command_contract.py"):
        assert (ROOT / "tools/sovereign-chatgpt-mcp" / name).read_bytes() == (ROOT / "scripts/sovereign-backend" / name).read_bytes()


def test_expired_authority_never_starts_a_process(tmp_path):
    read, write = os.pipe()
    output = tmp_path / 'should-not-exist'
    try:
        with pytest.raises(ValueError, match='before process admission'):
            supervise([sys.executable,'-c','open('+repr(str(output))+',"w").write("bad")'],
                      deadline=time.time()-1, lease_fd=read)
        assert not output.exists()
    finally:
        os.close(read);os.close(write)


def test_storage_monitor_rejects_oversized_sparse_file(tmp_path):
    with (tmp_path/'sparse').open('wb') as stream:
        stream.truncate(1073741825)
    with pytest.raises(ValueError, match='storage exceeded'):
        storage_guard(tmp_path)
