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
    try:
        child_state = status.read_text().split()[2]
    except (FileNotFoundError, ProcessLookupError):
        child_state = 'gone'
    assert child_state in {'gone', 'Z'}


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


def test_closed_lease_pipe_does_not_hide_a_successful_remote_exit(monkeypatch):
    original = subprocess.Popen
    class ClosingPipe:
        def __init__(self, pipe): self.pipe = pipe
        def __getattr__(self, name): return getattr(self.pipe, name)
        def close(self):
            self.pipe.close()
            raise BrokenPipeError('remote side already closed')
    class Process:
        def __init__(self, actual):
            self.actual = actual
            self.stdin = ClosingPipe(actual.stdin)
        def __getattr__(self, name): return getattr(self.actual, name)
        def __enter__(self): return self
        def __exit__(self, *args): return self.actual.__exit__(*args)
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: Process(original(*args, **kwargs)))
    result = _workspace_transport([sys.executable, '-c', 'print("done")'], deadline=time.time()+2, guard=lambda:None)
    assert result.returncode == 0 and result.stdout == 'done\n'


@pytest.fixture
def target_workspace(tmp_path, monkeypatch):
    import owner_ssh_workspace as helper
    # Only host identity/provisioning and the external systemd adapter are
    # substituted. Real control directories, lock and target_action are used.
    monkeypatch.setattr(helper.os, "geteuid", lambda: 0)
    monkeypatch.setattr(helper, "UID", 0)
    original_fstat, original_lstat = os.fstat, Path.lstat
    class HostStat:
        st_uid = 0
        def __init__(self, value): self.value = value
        def __getattr__(self, name): return getattr(self.value, name)
    monkeypatch.setattr(os, "fstat", lambda fd: HostStat(original_fstat(fd)))
    monkeypatch.setattr(Path, "lstat", lambda path: HostStat(original_lstat(path)))
    monkeypatch.setattr(os, "chown", lambda *_: None)
    original_isfile, original_access = os.path.isfile, os.access
    monkeypatch.setattr(os.path, "isfile", lambda path: True if path == "/usr/bin/bwrap" else original_isfile(path))
    monkeypatch.setattr(os, "access", lambda path, mode: True if path == "/usr/bin/bwrap" else original_access(path, mode))
    root = tmp_path / "capsules"
    request = {"sessionId": "a"*32, "grantId": "b"*32,
               "sourceRevision": "c"*40, "deadline": time.time()+60,
               "action": "init"}
    helper.target_action(request, "reviewed-source", root=root)
    return helper, root, {**request, "action": "run", "argv": ["python3", "-c", "print(1)"],
                          "timeout_seconds": 1}


def test_controller_timeout_still_stops_and_reads_back_unit(target_workspace, monkeypatch):
    helper, root, request = target_workspace
    calls = []
    def run(argv, **kwargs):
        calls.append(argv[:])
        if argv[0] == "/usr/bin/systemd-run":
            raise subprocess.TimeoutExpired(argv, 1)
        return subprocess.CompletedProcess(argv, 0, "inactive\n" if "show" in argv else "", "")
    monkeypatch.setattr(helper.subprocess, "run", run)
    try:
        helper.target_action(request, "reviewed-source", root=root)
    except (subprocess.TimeoutExpired, ValueError):
        pass
    assert any("stop" in argv for argv in calls)
    assert any("show" in argv for argv in calls)


def test_unavailable_unit_wrapper_never_becomes_success(target_workspace, monkeypatch):
    helper, root, request = target_workspace
    def run(argv, **kwargs):
        if argv[0] == "/usr/bin/systemd-run":
            return subprocess.CompletedProcess(argv, 1, json.dumps({
                "ok": False, "status": "SSH_WORKSPACE_BLOCKED",
                "failureFamily": "WORKSPACE_DEPENDENCY_MISSING"}), "")
        return subprocess.CompletedProcess(argv, 0, "inactive\n" if "show" in argv else "", "")
    monkeypatch.setattr(helper.subprocess, "run", run)
    result = helper.target_action(request, "reviewed-source", root=root)
    assert result["ok"] is False
    assert result.get("exitCode") == 255
    assert result.get("stopReason") == "SANDBOX_UNAVAILABLE"
    assert result["unitStopped"] is True


@pytest.mark.parametrize("failure", [
    ValueError("synthetic-private-detail"),
    FileNotFoundError("synthetic-private-path"),
    PermissionError("synthetic-private-detail"),
    subprocess.TimeoutExpired(["synthetic-private-command"], 1),
])
def test_failure_receipt_never_includes_exception_detail(failure):
    from owner_ssh_workspace import blocked_result, FAILURE_FAMILIES
    result = blocked_result(failure)
    assert result["ok"] is False and result["failureFamily"] in FAILURE_FAMILIES
    assert "synthetic-private" not in json.dumps(result)


@pytest.mark.parametrize("state,code", [("active", 0), ("inactive", 1), ("", 0)])
def test_unconfirmed_unit_stop_always_blocks(target_workspace, monkeypatch, state, code):
    helper, root, request = target_workspace
    def run(argv, **kwargs):
        if argv[0] == "/usr/bin/systemd-run":
            return subprocess.CompletedProcess(argv, 0, json.dumps({
                "exitCode": 0, "stopReason": None, "output": "done", "stderr": ""}), "")
        return subprocess.CompletedProcess(argv, code, state if "show" in argv else "", "")
    monkeypatch.setattr(helper.subprocess, "run", run)
    with pytest.raises(helper.WorkspaceFailure) as caught:
        helper.target_action(request, "reviewed-source", root=root)
    assert caught.value.family == "WORKSPACE_CGROUP_STOP_UNVERIFIED"


def test_validated_receipt_preserves_real_command_failure(target_workspace, monkeypatch):
    helper, root, request = target_workspace
    def run(argv, **kwargs):
        if argv[0] == "/usr/bin/systemd-run":
            return subprocess.CompletedProcess(argv, 0, json.dumps({
                "exitCode": 7, "stopReason": None, "output": "", "stderr": "test failed"}), "")
        return subprocess.CompletedProcess(argv, 0, "inactive\n" if "show" in argv else "", "")
    monkeypatch.setattr(helper.subprocess, "run", run)
    result = helper.target_action(request, "reviewed-source", root=root)
    assert result["ok"] is False and result["exitCode"] == 7 and result["unitStopped"] is True


def test_missing_bwrap_blocks_before_unit_admission(target_workspace, monkeypatch):
    helper, root, request = target_workspace
    monkeypatch.setattr(os, "access", lambda *_: False)
    monkeypatch.setattr(helper.subprocess, "run", lambda *_a, **_k: pytest.fail("Missing sandbox reached unit admission"))
    with pytest.raises(helper.WorkspaceFailure) as caught:
        helper.target_action(request, "reviewed-source", root=root)
    assert caught.value.family == "WORKSPACE_BWRAP_UNAVAILABLE"
