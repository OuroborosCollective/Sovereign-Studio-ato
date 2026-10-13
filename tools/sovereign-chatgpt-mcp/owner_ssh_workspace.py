"""Fixed SSH workspace capsule. No credentials, shell evaluation or live mounts.

The existing console transmits this reviewed helper over its pinned transport.
Root performs only dirfd-based file operations and fixed systemd supervision;
workspace code runs as nobody in a bubblewrap namespace and bounded cgroup.
Missing kernel, bubblewrap or systemd support fails closed without a fallback.
"""
from __future__ import annotations
import base64
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
import uuid

ROOT = Path("/var/lib/sovereign-ssh-workspaces")
ID = re.compile(r"^[0-9a-f]{32}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")
ACTIONS = frozenset(("init", "write", "read", "run"))
EXECUTABLES = frozenset(("python3", "node", "pnpm", "npm", "git", "rg", "ls", "pwd", "cat"))
MAX_FILE_BYTES = 32768
MAX_OUTPUT_BYTES = 65536
MAX_ARG_BYTES = 8192
UID = 65534
ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8"}


FAILURE_FAMILIES = frozenset((
    "WORKSPACE_TARGET_FAILED", "WORKSPACE_BWRAP_UNAVAILABLE",
    "WORKSPACE_CONTROLLER_TIMEOUT", "WORKSPACE_DEPENDENCY_MISSING",
    "WORKSPACE_PERMISSION_DENIED", "WORKSPACE_CGROUP_STOP_UNVERIFIED",
    "WORKSPACE_SANDBOX_START_FAILED", "WORKSPACE_SANDBOX_RECEIPT_INVALID",
))


class WorkspaceFailure(ValueError):
    def __init__(self, family):
        self.family = family if family in FAILURE_FAMILIES else "WORKSPACE_TARGET_FAILED"
        super().__init__(self.family)


def blocked_result(error):
    # Never return exception text, command arguments, host paths or environment.
    family = "WORKSPACE_TARGET_FAILED"
    if isinstance(error, WorkspaceFailure):
        family = error.family
    elif isinstance(error, subprocess.TimeoutExpired):
        family = "WORKSPACE_CONTROLLER_TIMEOUT"
    elif isinstance(error, FileNotFoundError):
        family = "WORKSPACE_DEPENDENCY_MISSING"
    elif isinstance(error, PermissionError):
        family = "WORKSPACE_PERMISSION_DENIED"
    return {"ok": False, "status": "SSH_WORKSPACE_BLOCKED",
            "blocker": "Workspace effect or readback not confirmed", "failureFamily": family}


def validate_request(action, path="", content="", expected_sha256="", argv=None, timeout_seconds=30):
    if action not in ACTIONS:
        raise ValueError("Invalid workspace action")
    if not isinstance(path, str) or not isinstance(content, str) or not isinstance(expected_sha256, str):
        raise ValueError("Workspace fields must be text")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
        raise ValueError("Workspace timeout must be 1–300 seconds")
    argv = [] if argv is None else argv
    if not isinstance(argv, list) or len(argv) > 64 or any(not isinstance(a, str) or "\x00" in a for a in argv):
        raise ValueError("Invalid workspace argument vector")
    if sum(len(a.encode()) for a in argv) > MAX_ARG_BYTES:
        raise ValueError("Workspace argument vector too large")
    if action in {"read", "write"}:
        parts = PurePosixPath(path).parts
        if (not path or path.startswith("/") or "\\" in path or "\x00" in path or len(path.encode()) > 512
                or any(p in {"", ".", "..", ".git"} for p in path.split("/")) or len(parts) > 16):
            raise ValueError("Workspace path escape or invalid path")
    elif path or content or expected_sha256:
        raise ValueError("Unexpected workspace file fields")
    if action == "write":
        if expected_sha256 != "absent" and not SHA.fullmatch(expected_sha256):
            raise ValueError("Expected file SHA256 or absent is required")
        if len(content.encode()) > MAX_FILE_BYTES:
            raise ValueError("Workspace file exceeds size limit")
    elif content or expected_sha256:
        raise ValueError("Unexpected workspace write fields")
    if action == "run":
        if not argv or argv[0] not in EXECUTABLES:
            raise ValueError("Workspace executable is not allowlisted")
    elif argv:
        raise ValueError("Unexpected workspace command fields")
    return {"action": action, "path": path, "content": content, "expected_sha256": expected_sha256,
            "argv": argv, "timeout_seconds": timeout_seconds}


def _regular(fd, limit=MAX_FILE_BYTES):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
        raise ValueError("Workspace file type, link count or size invalid")
    data = bytearray()
    while len(data) <= limit:
        chunk = os.read(fd, min(8192, limit + 1 - len(data)))
        if not chunk:
            return bytes(data)
        data.extend(chunk)
    raise ValueError("Workspace file exceeds size limit")


def file_action(worktree, request):
    """Walk only opened directories; reject links and never follow replacements."""
    parts = request["path"].split("/")
    directory = os.open(worktree, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = None
    try:
        for part in parts[:-1]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            except FileNotFoundError:
                if request["action"] != "write":
                    raise
                os.mkdir(part, 0o755, dir_fd=directory)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.fchown(child, UID, UID)
            os.close(directory)
            directory = child
        try:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            old = None
        else:
            try:
                old = _regular(fd)
            finally:
                os.close(fd)
        if request["action"] == "read":
            if old is None:
                raise FileNotFoundError("Workspace file does not exist")
            return {"content": old.decode("utf-8"), "sha256": hashlib.sha256(old).hexdigest(), "bytes": len(old)}
        actual = "absent" if old is None else hashlib.sha256(old).hexdigest()
        if actual != request["expected_sha256"]:
            raise ValueError("Workspace file revision changed")
        data = request["content"].encode()
        temporary = ".write-" + uuid.uuid4().hex
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=directory)
        try:
            os.fchown(fd, UID, UID)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, parts[-1], src_dir_fd=directory, dst_dir_fd=directory)
            temporary = None
            os.fsync(directory)
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                readback = _regular(fd)
            finally:
                os.close(fd)
            if readback != data:
                raise ValueError("Workspace write readback mismatch")
            return {"sha256": hashlib.sha256(readback).hexdigest(), "bytes": len(readback)}
        finally:
            if temporary:
                os.unlink(temporary, dir_fd=directory)
    finally:
        os.close(directory)


def sandbox_argv(worktree, argv):
    # No host /etc, /opt, /home, /root, /run, /var, DB/socket or network mount.
    command = ["/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
               "--uid", str(UID), "--gid", str(UID), "--clearenv", "--dir", "/usr"]
    for path in ("/usr/bin", "/usr/lib", "/usr/lib64", "/usr/share", "/bin", "/lib", "/lib64"):
        if os.path.exists(path):
            command.extend(("--ro-bind", path, path))
    command.extend(("--dir", "/etc", "--tmpfs", "/tmp", "--proc", "/proc", "--dev", "/dev",
                    "--bind", str(worktree), "/workspace", "--chdir", "/workspace"))
    for key, value in ENV.items():
        command.extend(("--setenv", key, value))
    return command + ["--", *argv]


def supervise(argv, *, deadline, lease_fd, output_limit=MAX_OUTPUT_BYTES, guard=None):
    """Live stdin lease: EOF, missing heartbeat, timeout or output flood kills all children."""
    output = {1: bytearray(), 2: bytearray()}
    size, reason = 0, ""
    stopping_at = None
    last_lease = time.monotonic()
    if time.time() >= deadline:
        raise ValueError("Workspace authority expired before process admission")
    with subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=ENV, start_new_session=True) as process:
        def terminate(*_args):
            nonlocal reason
            reason = reason or "HOST_ABORTED"
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        previous = {}
        if __import__("threading").current_thread() is __import__("threading").main_thread():
            for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
                previous[sig] = signal.signal(sig, terminate)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(lease_fd, selectors.EVENT_READ, 0)
                selector.register(process.stdout, selectors.EVENT_READ, 1)
                selector.register(process.stderr, selectors.EVENT_READ, 2)
                while process.poll() is None or any(k.data != 0 for k in selector.get_map().values()):
                    if reason:
                        stopping_at = stopping_at or time.monotonic()
                        if time.monotonic() - stopping_at > 1:
                            break
                    if not reason and guard:
                        try:
                            guard()
                        except (OSError, ValueError):
                            reason = "WORKSPACE_STORAGE_LIMIT"
                            terminate()
                    if not reason and (time.time() >= deadline or time.monotonic() - last_lease > 2):
                        reason = "TIMEOUT" if time.time() >= deadline else "HOST_LEASE_EXPIRED"
                        terminate()
                    for key, _ in selector.select(0.1):
                        chunk = os.read(key.fd, 8192)
                        if key.data == 0:
                            if not chunk:
                                selector.unregister(key.fileobj)
                                reason = reason or "HOST_ABORTED"
                                terminate()
                            elif chunk != b".\n" and set(chunk) - {46, 10}:
                                reason = "INVALID_HOST_LEASE"
                                terminate()
                            else:
                                last_lease = time.monotonic()
                        elif not chunk:
                            selector.unregister(key.fileobj)
                        else:
                            allowed = max(0, output_limit - size)
                            output[key.data].extend(chunk[:allowed])
                            size += min(allowed, len(chunk))
                            if len(chunk) > allowed:
                                reason = "OUTPUT_LIMIT"
                                terminate()
                code = process.wait()
            return {"exitCode": code if not reason else 255, "stopReason": reason or None,
                    "output": bytes(output[1]).decode("utf-8", "replace"),
                    "stderr": bytes(output[2]).decode("utf-8", "replace")}
        finally:
            if process.poll() is None:
                terminate()
            process.wait()
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def storage_guard(worktree):
    total = count = 0
    for _path, directories, files, directory in os.fwalk(worktree, follow_symlinks=False):
        count += len(directories) + len(files)
        if count > 10000:
            raise ValueError("Workspace file count exceeded")
        for name in files:
            try:
                info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                continue
            total += info.st_size
            if total > 1073741824:
                raise ValueError("Workspace storage exceeded")


def unit_argv(worktree, request, unit, helper_source):
    timeout = max(1, math.ceil(min(request["timeout_seconds"], request["deadline"] - time.time())))
    # All namespace processes share a cgroup. Limits survive loss of the SSH helper.
    command = ["/usr/bin/systemd-run", "--quiet", "--pipe", "--wait", "--collect", "--service-type=exec",
               "--unit=" + unit]
    for setting in ("User=65534", "Group=65534", "NoNewPrivileges=yes", "KillMode=control-group",
                    "TimeoutStopSec=2", "MemoryMax=2G", "MemorySwapMax=0", "CPUQuota=200%", "TasksMax=128",
                    "LimitNOFILE=256", "LimitCORE=0", "LimitFSIZE=1073741824", "UMask=0077",
                    "RuntimeMaxSec=" + str(timeout)):
        command.extend(("--property", setting))
    payload = base64.b64encode(json.dumps({"worktree": str(worktree), "argv": request["argv"],
                                         "deadline": min(request["deadline"], time.time() + timeout)},
                                        separators=(",", ":")).encode()).decode()
    return command + ["/usr/bin/python3", "-I", "-c", helper_source, "unit", payload]


def _secure_dir(path, mode):
    try:
        path.mkdir(mode=mode)
    except FileExistsError:
        pass
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != mode:
        raise ValueError("Workspace control directory ownership invalid")


def target_action(request, helper_source, root=ROOT):
    if os.geteuid() != 0:
        raise ValueError("Workspace controller requires the authenticated host worker")
    for key in ("sessionId", "grantId"):
        if not ID.fullmatch(str(request.get(key) or "")):
            raise ValueError("Invalid workspace control identity")
    if not REVISION.fullmatch(str(request.get("sourceRevision") or "")):
        raise ValueError("Invalid workspace source revision")
    deadline = request.get("deadline")
    if type(deadline) not in (int, float) or not math.isfinite(deadline) or not time.time() < deadline <= time.time() + 3600:
        raise ValueError("Workspace authority expired or invalid")
    validated = validate_request(request.get("action"), request.get("path", ""), request.get("content", ""),
                                 request.get("expected_sha256", ""), request.get("argv"), request.get("timeout_seconds", 30))
    request = {**request, **validated}
    _secure_dir(root, 0o711)
    control = root / request["sessionId"]
    _secure_dir(control, 0o711)
    control = control / request["grantId"]
    _secure_dir(control, 0o711)
    lock = os.open(control / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1:
            raise ValueError("Invalid workspace lock")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        worktree = control / "files"
        metadata = control / "identity.json"
        if request["action"] == "init":
            try:
                worktree.mkdir(mode=0o700)
            except FileExistsError:
                pass
            else:
                os.chown(worktree, UID, UID)
            expected = {"sessionId": request["sessionId"], "grantId": request["grantId"],
                        "sourceRevision": request["sourceRevision"]}
            try:
                fd = os.open(metadata, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, "w") as stream:
                    json.dump(expected, stream)
        fd = os.open(metadata, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if os.fstat(fd).st_uid != 0 or stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
                raise ValueError("Invalid workspace identity ownership")
            identity = json.loads(_regular(fd))
        finally:
            os.close(fd)
        if identity != {k: request[k] for k in ("sessionId", "grantId", "sourceRevision")}:
            raise ValueError("Workspace source revision or grant changed")
        info = worktree.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != UID or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("Workspace files ownership invalid")
        if time.time() >= deadline:
            raise ValueError("Workspace authority expired")
        if request["action"] in {"read", "write"}:
            result = file_action(worktree, request)
        elif request["action"] == "run":
            unit = "sovereign-ssh-" + request["grantId"] + ".service"
            command = unit_argv(worktree, request, unit, helper_source)
            # Cleanup and independent readback also run when admission/wait raises.
            try:
                completed = subprocess.run(command, stdin=sys.stdin, capture_output=True, text=True,
                                           timeout=request["timeout_seconds"] + 10, env=ENV)
                # The unit wrapper bounds user output before it crosses this pipe.
                try:
                    result = json.loads(completed.stdout)
                    if (not isinstance(result, dict) or type(result.get("exitCode")) is not int
                            or not isinstance(result.get("output"), str)
                            or not isinstance(result.get("stderr"), str)):
                        raise ValueError("Invalid unit receipt")
                    if completed.returncode != 0:
                        raise ValueError("Unit wrapper failed")
                    result = {key: result[key] for key in ("exitCode", "output", "stderr")} | {
                        "stopReason": result.get("stopReason")}
                except (ValueError, TypeError):
                    family = "WORKSPACE_SANDBOX_START_FAILED"
                    try:
                        candidate = json.loads(completed.stdout)
                        if isinstance(candidate, dict) and candidate.get("failureFamily") in FAILURE_FAMILIES:
                            family = candidate["failureFamily"]
                    except (ValueError, TypeError):
                        pass
                    result = {"exitCode": 255, "stopReason": "SANDBOX_UNAVAILABLE",
                              "failureFamily": family, "output": "", "stderr": "",
                              "controllerExitCode": completed.returncode}
            finally:
                try:
                    subprocess.run(["/usr/bin/systemctl", "stop", unit], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, env=ENV)
                except (OSError, subprocess.TimeoutExpired):
                    pass  # The independent state readback below remains mandatory.
                try:
                    observed = subprocess.run(
                        ["/usr/bin/systemctl", "show", unit, "--property=ActiveState", "--value"],
                        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5, env=ENV)
                except (OSError, subprocess.TimeoutExpired):
                    raise WorkspaceFailure("WORKSPACE_CGROUP_STOP_UNVERIFIED") from None
                if observed.returncode != 0 or observed.stdout.strip() not in {"inactive", "failed"}:
                    raise WorkspaceFailure("WORKSPACE_CGROUP_STOP_UNVERIFIED")
            result["unitStopped"] = True
        else:
            result = {"initialized": True}
        return {"ok": result.get("exitCode", 0) == 0, "status": "SSH_WORKSPACE_COMPLETE",
                **identity, "action": request["action"], **result}
    finally:
        os.close(lock)


def main():
    payload = json.loads(base64.b64decode(sys.argv[2], validate=True))
    if sys.argv[1] == "unit":
        if os.geteuid() != UID:
            raise ValueError("Workspace test identity must be non-root")
        if not os.path.isfile("/usr/bin/bwrap") or not os.access("/usr/bin/bwrap", os.X_OK):
            raise WorkspaceFailure("WORKSPACE_BWRAP_UNAVAILABLE")
        result = supervise(sandbox_argv(payload["worktree"], payload["argv"]), deadline=payload["deadline"], lease_fd=0,
                           guard=lambda: storage_guard(payload["worktree"]))
    else:
        # The caller supplies only this exact module's reviewed source, not workspace code.
        result = target_action(payload, sys.argv[3])
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps(blocked_result(error)))
        sys.exit(1)
