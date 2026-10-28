"""Owner-bound OpenSSH transport for the existing host command worker.

Credentials are read from the owner-managed file. The owner's designated VPS
uses one standing session grant for shell and workspace operations.
"""
from __future__ import annotations
import base64
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import selectors
import shlex
import shutil
import signal
import stat
import subprocess
import time
import unicodedata
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path
from owner_ssh_workspace import validate_request, FAILURE_FAMILIES, ACTIONS as WORKSPACE_ACTIONS, EXECUTABLES as WORKSPACE_EXECUTABLES

ASKPASS_SCRIPT = """#!/usr/bin/python3
from pathlib import Path
import sys
sys.stdout.write(Path(__file__).with_name("password").read_text() + chr(10))
"""

OPERATIONS = {
    "system": "uname -a; uptime; id",
    "disk": "df -h",
    "memory": "free -m",
    "containers": "docker ps --format '{{.Names}} {{.Status}}'",
    "services": "systemctl --no-pager --plain --type=service --state=running",
}
# Workspace scope: repeated non-root workspace tasks, isolated from live data.
WORKSPACE_SCOPE = "workspace"
SHELL_SCOPE = "shell"
GRANT_OPERATIONS = frozenset((*OPERATIONS, WORKSPACE_SCOPE, SHELL_SCOPE))
ID = re.compile(r"^[0-9a-f]{32}$")
OWNER_FULL_ACCESS_HOST = "46.202.154.25"

MAX_CAPTURE_BYTES = 65536


def _expired(deadline):
    """None denotes a session or grant with no time-based expiration."""
    return deadline is not None and time.time() >= deadline

def _workspace_transport(argv, *, deadline, guard):
    """Feed a revocable lease on the existing SSH channel; never reconnect."""
    output = {1: bytearray(), 2: bytearray()}
    size = 0
    last_heartbeat = 0.0
    with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env={"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": "/nonexistent"},
                          start_new_session=True) as process:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, 1)
                selector.register(process.stderr, selectors.EVENT_READ, 2)
                while selector.get_map():
                    if time.time() >= deadline:
                        raise ValueError("Workspace authority or command timeout expired")
                    guard()
                    if process.poll() is None and time.monotonic() - last_heartbeat >= 0.4:
                        try:
                            process.stdin.write(b".\n")
                            process.stdin.flush()
                        except BrokenPipeError:
                            pass
                        last_heartbeat = time.monotonic()
                    for key, _ in selector.select(0.1):
                        chunk = os.read(key.fd, 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        if size + len(chunk) > 450000:
                            raise ValueError("Workspace transport output exceeded limit")
                        output[key.data].extend(chunk)
                        size += len(chunk)
            code = process.wait(timeout=1)
            guard()
            return subprocess.CompletedProcess(argv, code, bytes(output[1]).decode("utf-8", errors="replace"),
                                               bytes(output[2]).decode("utf-8", errors="replace"))
        finally:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()

def _runtime_source_revision():
    revision = os.getenv("SOVEREIGN_SOURCE_REVISION", "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Exact MCP source revision is unavailable")
    return revision


def _shell_transport(argv, *, timeout_seconds, guard, output_streams=None):
    """Run a shell command; optionally persist both streams without a size cap."""
    counts = {1: 0, 2: 0}
    deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
    with subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          env={"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": "/nonexistent"},
                          start_new_session=True) as process:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, 1)
                selector.register(process.stderr, selectors.EVENT_READ, 2)
                while selector.get_map():
                    remaining = None if deadline is None else deadline - time.monotonic()
                    if remaining is not None and remaining <= 0:
                        raise subprocess.TimeoutExpired(argv, timeout_seconds)
                    guard()
                    for key, _ in selector.select(0.1 if remaining is None else min(remaining, 0.1)):
                        chunk = os.read(key.fileobj.fileno(), 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                            continue
                        counts[key.data] += len(chunk)
                        if output_streams is not None:
                            output_streams[key.data].write(chunk)
            while process.poll() is None:
                guard()
                if deadline is not None and time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(argv, timeout_seconds)
                time.sleep(0.1)
            code = process.returncode
            guard()
            result = subprocess.CompletedProcess(argv, code, "", "")
            result.stdout_bytes = counts[1]
            result.stderr_bytes = counts[2]
            return result
        finally:
            # A shell command can leave descendants holding inherited pipes even
            # after its leader exits. Always reap its process group on completion
            # or interruption so a timeout cannot orphan a remote command tree.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.poll() is None:
                process.wait()

def _bounded_run(argv, *, capture_output, text, timeout, check, stdin, env):
    if not capture_output:
        return subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=timeout, check=check, stdin=stdin, env=env, text=text)
    output = {1: bytearray(), 2: bytearray()}
    size = 0
    exceeded = False
    deadline = time.monotonic() + timeout
    with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=stdin, env=env) as process:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, 1)
            selector.register(process.stderr, selectors.EVENT_READ, 2)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    process.kill()
                    process.wait()
                    raise subprocess.TimeoutExpired(argv, timeout)
                for key, _ in selector.select(min(remaining, 0.25)):
                    chunk = os.read(key.fileobj.fileno(), 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    allowed = max(0, MAX_CAPTURE_BYTES - size)
                    output[key.data].extend(chunk[:allowed])
                    size += min(allowed, len(chunk))
                    if len(chunk) > allowed and not exceeded:
                        exceeded = True
                        process.kill()
            code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
    return subprocess.CompletedProcess(argv, code if not exceeded else 255,
            bytes(output[1]).decode("utf-8", errors="replace"), bytes(output[2]).decode("utf-8", errors="replace"))

class OwnerSSHConsole:
    def __init__(self, root=None, runner=None, workspace_runner=None):
        self.root = Path(root or os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", "/opt/sovereign-owner-managed"))
        self.runner = runner or _bounded_run
        self.workspace_runner = workspace_runner or _workspace_transport
        self.shell_runner = _shell_transport
        self._next_cleanup = 0.0

    def _read(self, name, limit=65536):
        path = self.root / name
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > limit:
                raise ValueError("SSH protected-file ownership or size contract failed")
            raw = os.read(fd, limit + 1)
            if len(raw) > limit:
                raise ValueError("SSH protected-file size contract failed")
            return raw
        finally:
            os.close(fd)

    def _json(self, name):
        value = json.loads(self._read(name))
        if not isinstance(value, dict):
            raise ValueError("SSH protected record must be an object")
        return value

    def _write(self, name, value):
        path = self.root / name
        tmp = self.root / ("." + uuid.uuid4().hex)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    @staticmethod
    def _has_full_access(state):
        return state.get("host") == OWNER_FULL_ACCESS_HOST and state.get("fullAccess") is True

    def _shell_output_chunk(self, state, execution_id, stream, offset=0, limit=65536):
        if not ID.fullmatch(str(execution_id or "")) or stream not in {"stdout", "stderr"}:
            raise ValueError("Invalid SSH output identity or stream")
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 65536:
            raise ValueError("Invalid SSH output range")
        directory = self.root / ("ssh-" + state["sessionId"])
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("SSH session output directory is unavailable")
        path = directory / ("output-" + execution_id + "." + stream)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("SSH output is not a regular file")
            chunk = os.pread(fd, limit, offset)
        finally:
            os.close(fd)
        next_offset = offset + len(chunk)
        complete = state.get("shellExecutionId") != execution_id
        return {"ok": True, "status": "SSH_OUTPUT_READ", "sessionId": state["sessionId"],
                "executionId": execution_id, "stream": stream, "offset": offset,
                "nextOffset": next_offset, "bytes": len(chunk),
                "text": chunk.decode("utf-8", errors="replace"),
                "base64": base64.b64encode(chunk).decode("ascii"),
                "eof": complete and next_offset >= info.st_size,
                "protectedValuesReturned": bool(chunk),
                "secretValuesReturned": bool(chunk), "secretPresenceDetermined": False}

    def assistant_shell_output(self, session_id, execution_id, stream, offset=0, limit=65536):
        state = self._state()
        if state["sessionId"] != session_id or not self._has_full_access(state):
            raise ValueError("Full-access SSH session identity mismatch")
        self._ready(state)
        self._delegation_ready(state, SHELL_SCOPE)
        return self._shell_output_chunk(state, execution_id, stream, offset, limit)

    @contextmanager
    def _lock(self):
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError("Protected SSH root unavailable")
        fd = os.open(self.root / ".ssh-console.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    @staticmethod
    def validate_target(host, port):
        # Literal globally routable addresses prevent DNS rebinding and SSRF
        # into internal networks. No SSH credentials are sent by a probe.
        if not isinstance(host, str):
            raise ValueError("SSH target must be a public IP address")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("SSH target must be a public IP address") from exc
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            raise ValueError("SSH target must be a public IP address")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Invalid SSH port")
        return str(ip), port

    @staticmethod
    def normalize_host_key(key):
        parts = str(key or "").strip().split()
        # Accept one optional OpenSSH comment; options from authorized_keys
        # are not valid as host identity.
        if len(parts) not in (2, 3) or parts[0] != "ssh-ed25519":
            raise ValueError("An independently verified ed25519 server host public key is required")
        try:
            decoded = base64.b64decode(parts[1], validate=True)
        except Exception as exc:
            raise ValueError("Invalid SSH host public key") from exc
        if len(decoded) != 51 or decoded[:19] != b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20":
            raise ValueError("Invalid SSH host public key")
        return " ".join(parts[:2])

    @staticmethod
    def validate_profile(profile):
        if not isinstance(profile, dict):
            raise ValueError("SSH profile must be an object")
        if set(profile) - {"host", "port", "username", "knownHostKey", "privateKey", "password", "expiresInSeconds"}:
            raise ValueError("Unsupported SSH profile field")
        host, port = OwnerSSHConsole.validate_target(profile.get("host"), profile.get("port", 22))
        user = str(profile.get("username") or "")
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user):
            raise ValueError("Invalid SSH username")
        key = OwnerSSHConsole.normalize_host_key(profile.get("knownHostKey"))
        if not isinstance(profile.get("privateKey", ""), str) or not isinstance(profile.get("password", ""), str):
            raise ValueError("SSH authentication material must be text")
        private = str(profile.get("privateKey") or "")
        password = str(profile.get("password") or "")
        if bool(private) == bool(password) or len(private.encode()) > 16000 or len(password.encode()) > 1024:
            raise ValueError("Choose exactly one SSH key or password")
        if any(character in password for character in ("\n", "\r", "\x00")):
            raise ValueError("Invalid SSH password transport format")
        ttl = profile.get("expiresInSeconds", 900)
        if type(ttl) is not int or not (60 <= ttl <= 3600 or (host == OWNER_FULL_ACCESS_HOST and ttl == 0)):
            raise ValueError("Invalid SSH session lifetime")
        return host, port, user, key, private, ttl, password

    def _probe_host_key(self, host, port):
        # ssh-keyscan never authenticates. This is only a candidate; owner
        # MUST verify its fingerprint in the independent VPS/provider console
        # before a password is allowed to be submitted over SSH.
        host, port = self.validate_target(host, port)
        lookup = host if port == 22 else "[" + host + "]:" + str(port)
        scanned = self._run(["ssh-keyscan", "-T", "7", "-p", str(port), "-t", "ed25519", host], timeout=12)
        if scanned.returncode:
            raise ValueError("SSH server host key lookup failed")
        keys = set()
        for line in (scanned.stdout or "").splitlines():
            fields = line.strip().split()
            if len(fields) != 3 or fields[0] != lookup or fields[1] != "ssh-ed25519":
                continue
            known = " ".join(fields[1:])
            try:
                normalized = self.normalize_host_key(known)
            except ValueError:
                continue
            keys.add(normalized)
        if len(keys) != 1:
            raise ValueError("SSH server host identity unavailable or ambiguous")
        known = next(iter(keys))
        fingerprint = "SHA256:" + base64.b64encode(
            hashlib.sha256(base64.b64decode(known.split()[1])).digest()
        ).decode().rstrip("=")
        return {"ok": True, "status": "SSH_HOST_KEY_DISCOVERED",
                "host": host, "port": port, "knownHostKey": known,
                "hostFingerprint": fingerprint, "protectedValuesReturned": False}

    def _run(self, argv, timeout=15, askpass=None, capture=True):
        env = {"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": "/nonexistent"}
        if askpass:
            env.update(SSH_ASKPASS=str(askpass), SSH_ASKPASS_REQUIRE="force")
        return self.runner(argv, capture_output=capture, text=True, timeout=timeout, check=False,
                           stdin=subprocess.DEVNULL, env=env)

    def _base(self, state):
        directory = self.root / ("ssh-" + state["sessionId"])
        password_mode = state.get("authMode") == "password"
        identity = [] if password_mode else ["-i", str(directory / "identity")]
        return ["ssh", "-F", "/dev/null", "-o", "StrictHostKeyChecking=yes",
                "-o", "UserKnownHostsFile=" + str(directory / "known_hosts"),
                "-o", "GlobalKnownHostsFile=/dev/null", "-o", "BatchMode=" + ("no" if password_mode else "yes"),
                "-o", "PreferredAuthentications=" + ("password" if password_mode else "publickey"),
                "-o", "NumberOfPasswordPrompts=1",
                "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
                "-o", "ForwardAgent=no", "-o", "ClearAllForwardings=yes",
                "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15",
                "-o", "ServerAliveCountMax=2", "-S", str(directory / "socket"),
                "-p", str(state["port"]), *identity,
                "-l", state["username"], state["host"]]

    def _state(self):
        state = self._json("ssh_console_state.json")
        if not ID.fullmatch(str(state.get("sessionId") or "")):
            raise ValueError("Invalid SSH session identity")
        return state

    @staticmethod
    def _shell_unit(execution_id):
        if not ID.fullmatch(str(execution_id or "")):
            raise ValueError("Invalid SSH shell execution identity")
        return "sovott-ssh-shell-" + execution_id + ".scope"

    def _stop_shell_scope(self, state, execution_id):
        """Stop and verify the remote systemd cgroup; fail closed if unavailable."""
        unit = self._shell_unit(execution_id)
        remote = ("command -v systemctl >/dev/null 2>&1 || exit 1; "
                  "load=$(systemctl --user show --property=LoadState --value " + shlex.quote(unit) + ") || exit 1; "
                  "case \"$load\" in not-found) exit 0 ;; loaded) "
                  "state=$(systemctl --user show --property=ActiveState --value " + shlex.quote(unit) + ") || exit 1; "
                  "case \"$state\" in inactive|failed) exit 0 ;; "
                  "active|activating|deactivating) systemctl --user kill --kill-who=all --signal=SIGKILL "
                  + shlex.quote(unit) + " && systemctl --user stop " + shlex.quote(unit)
                  + " && load=$(systemctl --user show --property=LoadState --value " + shlex.quote(unit)
                  + ") && state=$(systemctl --user show --property=ActiveState --value " + shlex.quote(unit)
                  + ") && { [ \"$load\" = not-found ] || [ \"$state\" = inactive ] || [ \"$state\" = failed ]; } ;; "
                  "*) exit 1 ;; esac ;; *) exit 1 ;; esac")
        argv = self._base(state)[:-1] + ["-o", "BatchMode=yes", "-o", "ControlMaster=no",
                                         "-o", "ProxyCommand=false", state["host"], remote]
        try:
            result = self._run(argv, timeout=12, capture=False)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0

    def _execution_lock_held(self):
        """Read-only probe: true only while another worker owns the command lock."""
        try:
            fd = os.open(self.root / ".ssh-console.lock", os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            return False
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        except OSError:
            return False
        finally:
            os.close(fd)

    def _recover_orphaned_shell(self, state):
        execution_id = state.get("shellExecutionId")
        if not execution_id:
            return state
        if self._has_full_access(state):
            activity = dict(state.get("lastActivity") or {})
            activity.update(status="SSH_SHELL_INTERRUPTED_OUTCOME_UNKNOWN", exitCode=None, at=time.time())
            state.update(lastActivity=activity, shellExecutionId="")
            self._write("ssh_console_state.json", state)
            return state
        # Callers hold the exclusive SSH-console lock. Therefore no active
        # shell invocation can still own the execution lease here.
        stopped = self._stop_shell_scope(state, execution_id)
        state = self._state()
        if state.get("shellExecutionId") != execution_id:
            return state
        activity = dict(state.get("lastActivity") or {})
        activity.update(status="SSH_SHELL_INTERRUPTED_OUTCOME_UNKNOWN", exitCode=None,
                        stdoutBytes=None, stderrBytes=None, at=time.time())
        state["lastActivity"] = activity
        state.update(grantUntil=0, allowedOperations=[], shellApproval=None)
        if stopped:
            state["shellExecutionId"] = ""
        self._write("ssh_console_state.json", state)
        if not stopped:
            raise ValueError("Orphaned remote SSH shell could not be stopped and verified")
        return state

    def _close(self, state, preserve_profile=False):
        if (state.get("shellExecutionId") and not self._has_full_access(state)
                and not self._stop_shell_scope(state, state["shellExecutionId"])):
            raise ValueError("Remote SSH shell scope could not be stopped before closing")
        state.update(status="close_unverified", grantUntil=0, allowedOperations=[], shellApproval=None, shellExecutionId="")
        self._write("ssh_console_state.json", state)
        try:
            self._run(self._base(state)[:-1] + ["-O", "exit", state["host"]], 5)
            check = self._run(self._base(state)[:-1] + ["-O", "check", state["host"]], 5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("SSH close could not be independently confirmed") from exc
        if check.returncode == 0:
            raise ValueError("SSH transport remained active after close; delegation revoked")
        directory = self.root / ("ssh-" + state["sessionId"])
        try:
            shutil.rmtree(directory)
        except FileNotFoundError:
            pass
        if not preserve_profile:
            try:
                if hashlib.sha256(self._read("ssh_console_profile.json")).hexdigest() == state["profileSha256"]:
                    (self.root / "ssh_console_profile.json").unlink()
            except FileNotFoundError:
                pass
        state.update(status="closed", grantUntil=0, allowedOperations=[])
        self._write("ssh_console_state.json", state)

    def _ready(self, state):
        if state.get("status") != "connected":
            raise ValueError("SSH session is closed or unverified")
        digest = hashlib.sha256(self._read("ssh_console_profile.json")).hexdigest()
        if _expired(state["expiresAt"]) or digest != state["profileSha256"]:
            self._close(state)
            raise ValueError("SSH session expired, changed or closed")
        result = self._run(self._base(state)[:-1] + ["-O", "check", state["host"]], 5)
        if result.returncode:
            self._close(state)
            raise ValueError("SSH transport is no longer active")

    def status(self, session_id=""):
        try:
            state = self._state()
        except FileNotFoundError:
            return {"ok": True, "status": "SSH_NOT_CONNECTED", "operations": list(OPERATIONS)}
        if session_id and session_id != state["sessionId"]:
            raise ValueError("SSH session identity mismatch")
        recovery_required = bool(state.get("shellExecutionId") and not self._execution_lock_held())
        observed = "SSH_SHELL_RECOVERY_REQUIRED" if recovery_required else state["status"]
        if observed == "connected":
            digest = hashlib.sha256(self._read("ssh_console_profile.json")).hexdigest()
            if _expired(state["expiresAt"]) or digest != state["profileSha256"]:
                observed = "expired"
            elif self._run(self._base(state)[:-1] + ["-O", "check", state["host"]], 5).returncode:
                observed = "disconnected"
        grant_active = (observed == "connected" and not _expired(state.get("grantUntil", 0))
                        and not state.get("shellExecutionId"))
        if grant_active:
            try:
                self._delegation_ready(state, next(iter(state.get("allowedOperations", [])), ""))
            except ValueError:
                grant_active = False
        return {"ok": True, "status": observed, "sessionId": state["sessionId"],
                "host": state["host"], "username": state["username"], "expiresAt": state["expiresAt"],
                "hostFingerprint": state["hostFingerprint"],
                "fullAccess": self._has_full_access(state),
                "assistantGrantActive": grant_active, "shellRecoveryRequired": recovery_required,
                "allowedOperations": state.get("allowedOperations", []), "operations": list(OPERATIONS),
                "protectedValuesReturned": False}

    def _connect(self, expected_profile_sha256):
        raw = self._read("ssh_console_profile.json")
        if hashlib.sha256(raw).hexdigest() != expected_profile_sha256:
            raise ValueError("Owner SSH profile changed before connection")
        profile = json.loads(raw)
        host, port, user, known, private, ttl, password = self.validate_profile(profile)
        try:
            old = self._state()
        except FileNotFoundError:
            old = None
        if old and old.get("status") != "closed":
            self._close(old, preserve_profile=True)
        identifier = uuid.uuid4().hex
        directory = self.root / ("ssh-" + identifier)
        directory.mkdir(mode=0o700)
        host_token = host if port == 22 else "[" + host + "]:" + str(port)
        files = [("known_hosts", host_token + " " + known + "\n")]
        files.append(("password", password) if password else ("identity", private + "\n"))
        if password:
            files.append(("askpass", ASKPASS_SCRIPT))
        for name, value in files:
            fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(value)
        if password:
            os.chmod(directory / "askpass", 0o700)
        fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(base64.b64decode(known.split()[1])).digest()).decode().rstrip("=")
        full_access = host == OWNER_FULL_ACCESS_HOST
        expires_at = None if ttl == 0 else time.time() + ttl
        state = {"sessionId": identifier, "host": host, "port": port, "username": user, "authMode": "password" if password else "key",
                 "hostFingerprint": fingerprint, "profileSha256": hashlib.sha256(raw).hexdigest(),
                 "expiresAt": expires_at, "status": "connecting", "grantUntil": 0, "allowedOperations": [],
                 "fullAccess": full_access}
        self._write("ssh_console_state.json", state)
        try:
            result = self._run(self._base(state)[:-1] +
                               ["-o", "ControlMaster=yes", "-o", "ControlPersist=" + ("yes" if ttl == 0 else str(ttl)), "-fN", host], 20,
                               askpass=directory / "askpass" if password else None, capture=False)
            if result.returncode:
                raise ValueError("SSH authentication or trusted-host verification failed")
            state["status"] = "connected"
            if full_access:
                state.update(grantUntil=expires_at, allowedOperations=sorted(GRANT_OPERATIONS),
                             workspaceGrantId=uuid.uuid4().hex, shellGrantId=uuid.uuid4().hex)
            self._write("ssh_console_state.json", state)
            self._ready(state)
        except Exception:
            self._close(state)
            raise
        return {"ok": True, "status": "SSH_CONNECTED", "sessionId": identifier,
                "hostFingerprint": fingerprint, "protectedValuesReturned": False}

    def _delegation_ready(self, state, operation):
        if _expired(state.get("grantUntil", 0)) or operation not in state.get("allowedOperations", []):
            raise ValueError("Owner SSH delegation missing, revoked or expired")
        if operation == SHELL_SCOPE and not self._has_full_access(state) and not state.get("shellExecutionId"):
            approval = state.get("shellApproval")
            if (not isinstance(approval, dict) or approval.get("sourceRevision") != _runtime_source_revision()
                    or approval.get("profileSha256") != state.get("profileSha256")):
                raise ValueError("Command-bound owner approval missing or stale")
        try:
            revoked = self._json("ssh_console_revocation.json")
        except FileNotFoundError:
            revoked = {}
        if revoked.get("sessionId") == state["sessionId"]:
            raise ValueError("Owner SSH revocation or closure is pending")
        try:
            pending = self._json("ssh_console_action.json")
        except FileNotFoundError:
            pending = {}
        if (pending.get("sessionId") == state["sessionId"] and pending.get("action") in {"revoke", "close"}
                and time.time() < pending.get("expiresAt", 0)):
            raise ValueError("Owner SSH revocation or closure is pending")

    def _inspect(self, state, operation, actor="owner"):
        if operation not in OPERATIONS:
            raise ValueError("SSH operation is not allowlisted")
        self._ready(state)
        # ControlMaster=no and ProxyCommand=false prohibit reconnecting with credentials
        # if the existing transport vanishes between check and execution.
        argv = self._base(state)[:-1] + ["-o", "ControlMaster=no", "-o", "ProxyCommand=false",
                                       state["host"], OPERATIONS[operation]]
        if actor == "assistant":
            self._delegation_ready(state, operation)
        result = self._run(argv, 20)
        self._ready(state)
        if actor == "assistant":
            self._delegation_ready(state, operation)
        # Fixed inspection commands intentionally exclude files, env and logs.
        text = (result.stdout or "")[-24000:]
        profile = self._json("ssh_console_profile.json")
        for field in ("password", "privateKey"):
            protected = str(profile.get(field) or "")
            if protected:
                text = text.replace(protected, "[REDACTED]")
                for line in protected.splitlines():
                    if len(line) > 16:
                        text = text.replace(line, "[REDACTED]")
        text = re.sub(r"(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_./+=-]+", "[REDACTED]", text)
        state["lastActivity"] = {"actor": actor, "operation": operation, "command": OPERATIONS[operation],
                                 "output": text, "exitCode": result.returncode, "at": time.time()}
        self._write("ssh_console_state.json", state)
        return {"ok": result.returncode == 0, "status": "SSH_INSPECTION_COMPLETE" if result.returncode == 0 else "SSH_INSPECTION_FAILED",
                "sessionId": state["sessionId"], "operation": operation, "command": OPERATIONS[operation],
                "output": text, "exitCode": result.returncode, "protectedValuesReturned": False}

    def cleanup_expired(self):
        if time.monotonic() < self._next_cleanup:
            return
        self._next_cleanup = time.monotonic() + 5
        if not self.root.is_dir():
            return
        with self._lock():
            try:
                state = self._state()
            except FileNotFoundError:
                return
            if state["status"] in {"connected", "close_unverified"} and _expired(state["expiresAt"]):
                self._close(state)

    def assistant_inspect(self, session_id, operation):
        with self._lock():
            state = self._state()
            if session_id != state["sessionId"]:
                raise ValueError("SSH session identity mismatch")
            self._ready(state)
            self._delegation_ready(state, operation)
            return self._inspect(state, operation, actor="assistant")

    @staticmethod
    def validate_grant(ops, ttl):
        if not isinstance(ops, list) or not ops or any(not isinstance(op, str) or op not in GRANT_OPERATIONS for op in ops):
            raise ValueError("Invalid owner SSH delegation scope")
        if SHELL_SCOPE in ops and len(ops) != 1:
            raise ValueError("SSH shell scope must be separate")
        low, high = (60, 900) if SHELL_SCOPE in ops else ((900, 3600) if WORKSPACE_SCOPE in ops else (30, 900))
        if type(ttl) is not int or not low <= ttl <= high:
            raise ValueError("Invalid owner SSH delegation lifetime")

    @staticmethod
    def validate_shell_command(command, timeout_seconds):
        if not isinstance(command, str) or not command.strip() or "\x00" in command:
            raise ValueError("Invalid SSH shell command")
        try:
            encoded = command.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise ValueError("Invalid SSH shell command encoding") from exc
        if len(encoded) > 8192:
            raise ValueError("Invalid SSH shell command")
        if any(unicodedata.category(ch) in {"Cf", "Cs", "Cn", "Zl", "Zp"}
               or (unicodedata.category(ch) == "Cc" and ch not in "\n\t") for ch in command):
            raise ValueError("SSH shell command contains hidden display controls")
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
            raise ValueError("Invalid SSH shell timeout")
        return hashlib.sha256(encoded).hexdigest()

    def _assistant_full_shell(self, session_id, command, timeout_seconds=None):
        if not isinstance(command, str) or not command.strip() or "\x00" in command:
            raise ValueError("Invalid SSH shell command")
        if timeout_seconds is not None and (type(timeout_seconds) is not int or timeout_seconds < 1):
            raise ValueError("Invalid SSH shell timeout")
        try:
            digest = hashlib.sha256(command.encode("utf-8", errors="strict")).hexdigest()
        except UnicodeError as exc:
            raise ValueError("Invalid SSH shell command encoding") from exc

        with self._lock():
            state = self._recover_orphaned_shell(self._state())
            if state["sessionId"] != session_id or not self._has_full_access(state):
                raise ValueError("Full-access SSH session identity mismatch")
            self._ready(state)
            self._delegation_ready(state, SHELL_SCOPE)
            execution_id = uuid.uuid4().hex
            grant_id = str(state.get("shellGrantId") or "")
            if not ID.fullmatch(grant_id):
                raise ValueError("Full-access SSH session grant missing")
            source_revision = os.getenv("SOVEREIGN_SOURCE_REVISION", "").strip().lower() or None
            directory = self.root / ("ssh-" + session_id)
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("SSH session output directory is unavailable")
            state["shellExecutionId"] = execution_id
            state["lastActivity"] = {
                "actor": "assistant", "operation": SHELL_SCOPE, "status": "SSH_SHELL_STARTED",
                "sessionId": session_id, "grantId": grant_id, "executionId": execution_id,
                "commandSha256": digest, "sourceRevision": source_revision,
                "timeoutSeconds": timeout_seconds, "at": time.time(),
            }
            self._write("ssh_console_state.json", state)

            def guard():
                current = self._state()
                if (current["sessionId"] != session_id or current.get("shellExecutionId") != execution_id
                        or current.get("status") != "connected" or _expired(current["expiresAt"])
                        or not self._has_full_access(current)):
                    raise ValueError("SSH session expired or changed")
                if hashlib.sha256(self._read("ssh_console_profile.json")).hexdigest() != current["profileSha256"]:
                    raise ValueError("SSH profile changed during shell execution")
                self._delegation_ready(current, SHELL_SCOPE)

            remote = "exec /bin/sh -c " + shlex.quote(command)
            argv = self._base(state)[:-1] + ["-o", "BatchMode=yes", "-o", "ControlMaster=no",
                                              "-o", "ProxyCommand=false", state["host"], remote]
            try:
                with ExitStack() as stack:
                    streams = {}
                    for number, stream in ((1, "stdout"), (2, "stderr")):
                        path = directory / ("output-" + execution_id + "." + stream)
                        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                        streams[number] = stack.enter_context(os.fdopen(fd, "wb", buffering=0))
                    completed = self.shell_runner(argv, timeout_seconds=timeout_seconds, guard=guard,
                                                  output_streams=streams)
                guard()
                self._ready(state)
                guard()
                stdout_bytes = max(0, int(getattr(completed, "stdout_bytes", 0)))
                stderr_bytes = max(0, int(getattr(completed, "stderr_bytes", 0)))
                status = "SSH_SHELL_EXECUTED" if completed.returncode == 0 else "SSH_SHELL_FAILED"
                state["lastActivity"] = {**state["lastActivity"], "status": status,
                    "exitCode": completed.returncode, "stdoutBytes": stdout_bytes,
                    "stderrBytes": stderr_bytes, "at": time.time()}
                state["shellExecutionId"] = ""
                self._write("ssh_console_state.json", state)
                stdout = self._shell_output_chunk(state, execution_id, "stdout", limit=16384)
                stderr = self._shell_output_chunk(state, execution_id, "stderr", limit=16384)
                return {"ok": completed.returncode == 0, "status": status, "sessionId": session_id,
                        "grantId": grant_id, "executionId": execution_id, "commandSha256": digest,
                        "sourceRevision": source_revision, "exitCode": completed.returncode,
                        "stdoutBytes": stdout_bytes, "stderrBytes": stderr_bytes,
                        "stdout": stdout, "stderr": stderr, "outputReturned": True,
                        "targetStateVerified": False, "mutationPerformed": True,
                        "protectedValuesReturned": bool(stdout_bytes or stderr_bytes),
                        "secretValuesReturned": bool(stdout_bytes or stderr_bytes),
                        "secretPresenceDetermined": False}
            except subprocess.TimeoutExpired:
                current = self._state()
                current["lastActivity"] = {**current.get("lastActivity", {}),
                    "status": "SSH_SHELL_OUTCOME_UNKNOWN", "exitCode": None, "at": time.time()}
                current["shellExecutionId"] = ""
                self._write("ssh_console_state.json", current)
                return {"ok": False, "status": "SSH_SHELL_OUTCOME_UNKNOWN", "sessionId": session_id,
                        "grantId": grant_id, "executionId": execution_id, "commandSha256": digest,
                        "sourceRevision": source_revision, "exitCode": None, "outputReturned": False,
                        "targetStateVerified": False, "protectedValuesReturned": False}
            except Exception:
                current = self._state()
                current["lastActivity"] = {**current.get("lastActivity", {}),
                    "status": "SSH_SHELL_INTERRUPTED_OUTCOME_UNKNOWN", "exitCode": None, "at": time.time()}
                current["shellExecutionId"] = ""
                self._write("ssh_console_state.json", current)
                raise

    def assistant_shell(self, session_id, command, timeout_seconds=30):
        if self._has_full_access(self._state()):
            return self._assistant_full_shell(session_id, command, timeout_seconds)
        if timeout_seconds is None:
            timeout_seconds = 30
        digest = self.validate_shell_command(command, timeout_seconds)
        source_revision = _runtime_source_revision()
        with self._lock():
            state = self._state()
            state = self._recover_orphaned_shell(state)
            if state["sessionId"] != session_id:
                raise ValueError("SSH session identity mismatch")
            self._ready(state)
            self._delegation_ready(state, SHELL_SCOPE)
            approval = state.get("shellApproval")
            if (not isinstance(approval, dict) or approval.get("commandSha256") != digest
                    or approval.get("timeoutSeconds") != timeout_seconds
                    or approval.get("profileSha256") != state.get("profileSha256")
                    or approval.get("sourceRevision") != source_revision):
                raise ValueError("Owner approval does not match this command")
            approval_id = str(approval.get("approvalId") or "")
            if not ID.fullmatch(approval_id):
                raise ValueError("Owner shell approval identity is invalid")
            execution_id = uuid.uuid4().hex
            state["shellApproval"] = None
            state["shellExecutionId"] = execution_id
            state["lastActivity"] = {
                "actor": "assistant", "operation": SHELL_SCOPE, "status": "SSH_SHELL_STARTED",
                "sessionId": session_id, "approvalId": approval_id, "executionId": execution_id,
                "commandSha256": digest, "profileSha256": state["profileSha256"],
                "sourceRevision": source_revision, "timeoutSeconds": timeout_seconds, "at": time.time(),
            }
            self._write("ssh_console_state.json", state)

            def guard():
                current = self._state()
                if (current["sessionId"] != session_id or current.get("shellExecutionId") != execution_id
                        or current.get("status") != "connected" or time.time() >= current["expiresAt"]):
                    raise ValueError("SSH session expired or changed")
                profile_sha = hashlib.sha256(self._read("ssh_console_profile.json")).hexdigest()
                if profile_sha != current.get("profileSha256"):
                    raise ValueError("SSH profile changed during shell execution")
                if _runtime_source_revision() != source_revision:
                    raise ValueError("MCP source revision changed during shell execution")
                self._delegation_ready(current, SHELL_SCOPE)

            unit = self._shell_unit(execution_id)
            remote = ("exec systemd-run --user --scope --unit=" + shlex.quote(unit) + " --quiet -- "
                      "/bin/sh -c " + shlex.quote(command))
            argv = self._base(state)[:-1] + ["-o", "BatchMode=yes", "-o", "ControlMaster=no",
                                              "-o", "ProxyCommand=false", state["host"], remote]
            try:
                completed = self.shell_runner(argv, timeout_seconds=timeout_seconds, guard=guard)
                guard()
                self._ready(state)
                guard()
                stdout_bytes = max(0, int(getattr(completed, "stdout_bytes", 0)))
                stderr_bytes = max(0, int(getattr(completed, "stderr_bytes", 0)))
                status = "SSH_SHELL_EXECUTED" if completed.returncode == 0 else "SSH_SHELL_FAILED"
                receipt = {**state["lastActivity"], "status": status, "exitCode": completed.returncode,
                           "stdoutBytes": stdout_bytes, "stderrBytes": stderr_bytes, "at": time.time()}
                state["lastActivity"] = receipt
                self._write("ssh_console_state.json", state)
                return {"ok": completed.returncode == 0, "status": status, "sessionId": session_id,
                        "approvalId": approval_id, "executionId": execution_id, "commandSha256": digest,
                        "profileSha256": state["profileSha256"], "sourceRevision": source_revision,
                        "exitCode": completed.returncode, "stdoutBytes": stdout_bytes, "stderrBytes": stderr_bytes,
                        "outputReturned": False, "targetStateVerified": False, "protectedValuesReturned": False}
            except subprocess.TimeoutExpired:
                current = self._state()
                current["lastActivity"] = {**current.get("lastActivity", {}), "status": "SSH_SHELL_OUTCOME_UNKNOWN",
                                            "exitCode": None, "stdoutBytes": None, "stderrBytes": None, "at": time.time()}
                self._write("ssh_console_state.json", current)
                return {"ok": False, "status": "SSH_SHELL_OUTCOME_UNKNOWN", "sessionId": session_id,
                        "approvalId": approval_id, "executionId": execution_id, "commandSha256": digest,
                        "profileSha256": state["profileSha256"], "sourceRevision": source_revision,
                        "exitCode": None, "outputReturned": False,
                        "targetStateVerified": False, "protectedValuesReturned": False}
            except Exception:
                current = self._state()
                current["lastActivity"] = {**current.get("lastActivity", {}), "status": "SSH_SHELL_INTERRUPTED_OUTCOME_UNKNOWN",
                                            "exitCode": None, "stdoutBytes": None, "stderrBytes": None, "at": time.time()}
                self._write("ssh_console_state.json", current)
                raise
            finally:
                stopped = self._stop_shell_scope(state, execution_id)
                current = self._state()
                if current.get("shellExecutionId") == execution_id:
                    if stopped:
                        current["shellExecutionId"] = ""
                    else:
                        current["lastActivity"] = {**current.get("lastActivity", {}),
                            "status": "SSH_SHELL_INTERRUPTED_OUTCOME_UNKNOWN", "exitCode": None,
                            "stdoutBytes": None, "stderrBytes": None, "at": time.time()}
                        current.update(grantUntil=0, allowedOperations=[], shellApproval=None)
                    self._write("ssh_console_state.json", current)
                if not stopped:
                    raise ValueError("Remote SSH shell scope termination is unverified")

    def assistant_workspace(self, session_id, source_revision, action, path="", content="",
                            expected_sha256="", argv=None, timeout_seconds=30):
        request = validate_request(action, path, content, expected_sha256, argv, timeout_seconds)
        if not re.fullmatch(r"[0-9a-f]{40}", str(source_revision)):
            raise ValueError("Exact workspace source revision is required")
        with self._lock():
            state = self._state()
            if state["sessionId"] != session_id:
                raise ValueError("SSH session identity mismatch")
            self._ready(state)
            self._delegation_ready(state, WORKSPACE_SCOPE)
            grant_id = state.get("workspaceGrantId", "")
            if not ID.fullmatch(grant_id):
                raise ValueError("Workspace session grant missing")
            def guard():
                current = self._state()
                if (current["sessionId"] != session_id or current.get("workspaceGrantId") != grant_id
                        or current.get("status") != "connected" or _expired(current["expiresAt"])
                        or hashlib.sha256(self._read("ssh_console_profile.json")).hexdigest() != current["profileSha256"]):
                    raise ValueError("Workspace session expired or changed")
                self._delegation_ready(current, WORKSPACE_SCOPE)
            deadlines = [value for value in (state["grantUntil"], state["expiresAt"]) if value is not None]
            request.update(sessionId=session_id, grantId=grant_id, sourceRevision=source_revision,
                           deadline=min([time.time() + 3590, *deadlines]))
            helper = Path(__file__).with_name("owner_ssh_workspace.py").read_text("utf-8")
            payload = base64.b64encode(json.dumps(request, separators=(",", ":"), ensure_ascii=False).encode()).decode()
            # OpenSSH joins remote arguments through a shell. Quote every fixed helper/data word;
            # argv from the model is parsed only by the unprivileged sandbox, never this shell.
            command = "exec /usr/bin/python3 -I -c " + shlex.quote(helper) + " effect " + shlex.quote(payload) + " " + shlex.quote(helper)
            command_argv = self._base(state)[:-1] + ["-o", "BatchMode=yes", "-o", "ControlMaster=no",
                                                   "-o", "ProxyCommand=false", state["host"], command]
            completed = self.workspace_runner(command_argv, deadline=min(request["deadline"], time.time() + timeout_seconds + 15), guard=guard)
            guard()
            self._ready(state)
            result = json.loads(completed.stdout)
            if completed.returncode or not isinstance(result, dict) or result.get("status") != "SSH_WORKSPACE_COMPLETE":
                family = result.get("failureFamily") if isinstance(result, dict) else None
                return {"ok": False, "status": "SSH_WORKSPACE_BLOCKED", "sessionId": session_id,
                        "failureFamily": family if isinstance(family, str) and family in FAILURE_FAMILIES else "WORKSPACE_TARGET_FAILED",
                        "blocker": "Workspace effect or readback not confirmed", "protectedValuesReturned": False}
            if any(result.get(key) != request[key] for key in ("sessionId", "grantId", "sourceRevision", "action")):
                raise ValueError("Workspace target readback identity mismatch")
            if action == "write" and result.get("sha256") != hashlib.sha256(content.encode()).hexdigest():
                raise ValueError("Workspace target write readback mismatch")
            if action == "read" and result.get("sha256") != hashlib.sha256(str(result.get("content", "")).encode()).hexdigest():
                raise ValueError("Workspace target file readback mismatch")
            if action == "run" and result.get("unitStopped") is not True:
                raise ValueError("Workspace target process readback missing")
            state["lastActivity"] = {"actor": "assistant", "operation": WORKSPACE_SCOPE, "command": action,
                                     "output": str(result.get("output", ""))[:24000],
                                     "exitCode": result.get("exitCode", 0), "at": time.time()}
            self._write("ssh_console_state.json", state)
            return {**result, "protectedValuesReturned": False}

    def owner_action(self, operation_id):
        if not ID.fullmatch(operation_id):
            raise ValueError("Invalid owner SSH operation identity")
        with self._lock():
            action = self._json("ssh_console_action.json")
            if action.get("operationId") != operation_id or time.time() >= action.get("expiresAt", 0):
                raise ValueError("Owner SSH action is stale or mismatched")
            # Consume before effects; replay cannot authorize a second execution.
            (self.root / "ssh_console_action.json").unlink()
            if action.get("action") == "connect":
                return self._connect(str(action.get("profileSha256") or ""))
            if action.get("action") == "probe":
                return self._probe_host_key(action.get("host"), action.get("port"))
            state = self._state()
            if action.get("sessionId") != state["sessionId"]:
                raise ValueError("SSH session identity mismatch")
            selected = action.get("action")
            if selected == "close":
                self._close(state)
                return {"ok": True, "status": "SSH_CLOSED", "sessionId": state["sessionId"]}
            if selected in {"grant", "revoke"}:
                state = self._recover_orphaned_shell(state)
                if state.get("shellExecutionId"):
                    raise ValueError("SSH shell scope termination must be confirmed before changing delegation")
            if selected == "revoke":
                state.update(grantUntil=0, allowedOperations=[], shellApproval=None)
                self._write("ssh_console_state.json", state)
                return {"ok": True, "status": "SSH_DELEGATION_REVOKED"}
            self._ready(state)
            if selected == "grant":
                ops = action.get("operations")
                ttl = action.get("ttl", 300)
                self.validate_grant(ops, ttl)
                try:
                    marker = self._json("ssh_console_revocation.json")
                except FileNotFoundError:
                    marker = {}
                if marker.get("sessionId") == state["sessionId"]:
                    if marker.get("at", 0) >= action.get("createdAt", 0):
                        raise ValueError("Newer SSH revocation blocks this grant")
                    (self.root / "ssh_console_revocation.json").unlink()
                if self._has_full_access(state):
                    state.update(grantUntil=state["expiresAt"], allowedOperations=sorted(GRANT_OPERATIONS),
                                 workspaceGrantId=uuid.uuid4().hex, shellGrantId=uuid.uuid4().hex,
                                 shellApproval=None, shellExecutionId="")
                    self._write("ssh_console_state.json", state)
                    return {"ok": True, "status": "SSH_DELEGATION_GRANTED", "sessionId": state["sessionId"],
                            "allowedOperations": state["allowedOperations"], "expiresAt": state["grantUntil"],
                            "grantId": state["shellGrantId"], "protectedValuesReturned": False}
                shell_approval = None
                if SHELL_SCOPE in ops:
                    digest = str(action.get("commandSha256") or "")
                    timeout_seconds = action.get("timeoutSeconds")
                    if not re.fullmatch(r"[0-9a-f]{64}", digest) or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
                        raise ValueError("Command-bound owner approval is required for shell scope")
                    shell_approval = {"approvalId": uuid.uuid4().hex, "commandSha256": digest,
                                      "timeoutSeconds": timeout_seconds, "profileSha256": state["profileSha256"],
                                      "sourceRevision": _runtime_source_revision()}
                state["workspaceGrantId"] = uuid.uuid4().hex if WORKSPACE_SCOPE in ops else ""
                state.update(grantUntil=min(time.time() + ttl, state["expiresAt"]),
                             allowedOperations=sorted(set(ops)), shellApproval=shell_approval, shellExecutionId="")
                self._write("ssh_console_state.json", state)
                return {"ok": True, "status": "SSH_DELEGATION_GRANTED", "sessionId": state["sessionId"],
                        "allowedOperations": state["allowedOperations"], "expiresAt": state["grantUntil"],
                        "approvalId": shell_approval["approvalId"] if shell_approval else None,
                        "commandSha256": shell_approval["commandSha256"] if shell_approval else None,
                        "timeoutSeconds": shell_approval["timeoutSeconds"] if shell_approval else None,
                        "sourceRevision": shell_approval["sourceRevision"] if shell_approval else None}
            if selected == "inspect":
                return self._inspect(state, str(action.get("operation") or ""))
            raise ValueError("Owner SSH action is not allowlisted")
