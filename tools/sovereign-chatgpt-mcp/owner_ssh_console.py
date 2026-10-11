"""Owner-bound OpenSSH transport for the existing host command worker.

Credentials are read from the protected owner-managed file, never from tool
arguments. No arbitrary shell command surface is exposed.
"""
from __future__ import annotations
import base64
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import shutil
import stat
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

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
ID = re.compile(r"^[0-9a-f]{32}$")

class OwnerSSHConsole:
    def __init__(self, root=None, runner=None):
        self.root = Path(root or os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", "/opt/sovereign-owner-managed"))
        self.runner = runner or subprocess.run
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
    def validate_profile(profile):
        if not isinstance(profile, dict):
            raise ValueError("SSH profile must be an object")
        if set(profile) - {"host", "port", "username", "knownHostKey", "privateKey", "password", "expiresInSeconds"}:
            raise ValueError("Unsupported SSH profile field")
        # Literal public IPs prevent DNS rebinding and access to internal services.
        host = str(profile.get("host") or "")
        ip = ipaddress.ip_address(host)
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            raise ValueError("SSH target must be a public IP address")
        user = str(profile.get("username") or "")
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user):
            raise ValueError("Invalid SSH username")
        port = profile.get("port", 22)
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Invalid SSH port")
        key = str(profile.get("knownHostKey") or "").strip()
        parts = key.split()
        if len(parts) != 2 or parts[0] != "ssh-ed25519":
            raise ValueError("An independently verified ed25519 host public key is required")
        try:
            decoded = base64.b64decode(parts[1], validate=True)
        except Exception as exc:
            raise ValueError("Invalid SSH host public key") from exc
        if len(decoded) != 51 or decoded[:19] != b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20":
            raise ValueError("Invalid SSH host public key")
        if not isinstance(profile.get("privateKey", ""), str) or not isinstance(profile.get("password", ""), str):
            raise ValueError("SSH authentication material must be text")
        private = str(profile.get("privateKey") or "")
        password = str(profile.get("password") or "")
        if bool(private) == bool(password) or len(private.encode()) > 16000 or len(password.encode()) > 1024:
            raise ValueError("Choose exactly one SSH key or password")
        if any(character in password for character in ("\n", "\r", "\x00")):
            raise ValueError("Invalid SSH password transport format")
        ttl = profile.get("expiresInSeconds", 900)
        if type(ttl) is not int or not 60 <= ttl <= 3600:
            raise ValueError("Invalid SSH session lifetime")
        return host, port, user, key, private, ttl, password

    def _run(self, argv, timeout=15, askpass=None):
        env = {"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": "/nonexistent"}
        if askpass:
            env.update(SSH_ASKPASS=str(askpass), SSH_ASKPASS_REQUIRE="force")
        return self.runner(argv, capture_output=True, text=True, timeout=timeout, check=False,
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

    def _close(self, state, preserve_profile=False):
        state.update(status="close_unverified", grantUntil=0, allowedOperations=[])
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
        if time.time() >= state["expiresAt"] or digest != state["profileSha256"]:
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
        observed = state["status"]
        if observed == "connected":
            digest = hashlib.sha256(self._read("ssh_console_profile.json")).hexdigest()
            if time.time() >= state["expiresAt"] or digest != state["profileSha256"]:
                observed = "expired"
            elif self._run(self._base(state)[:-1] + ["-O", "check", state["host"]], 5).returncode:
                observed = "disconnected"
        return {"ok": True, "status": observed, "sessionId": state["sessionId"],
                "host": state["host"], "username": state["username"], "expiresAt": state["expiresAt"],
                "hostFingerprint": state["hostFingerprint"],
                "assistantGrantActive": observed == "connected" and time.time() < state.get("grantUntil", 0),
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
        state = {"sessionId": identifier, "host": host, "port": port, "username": user, "authMode": "password" if password else "key",
                 "hostFingerprint": fingerprint, "profileSha256": hashlib.sha256(raw).hexdigest(),
                 "expiresAt": time.time() + ttl, "status": "connecting", "grantUntil": 0, "allowedOperations": []}
        self._write("ssh_console_state.json", state)
        try:
            result = self._run(self._base(state)[:-1] +
                               ["-o", "ControlMaster=yes", "-o", "ControlPersist=" + str(ttl), "-fN", host], 20,
                               askpass=directory / "askpass" if password else None)
            if result.returncode:
                raise ValueError("SSH authentication or trusted-host verification failed")
            state["status"] = "connected"
            self._write("ssh_console_state.json", state)
            self._ready(state)
        except Exception:
            self._close(state)
            raise
        return {"ok": True, "status": "SSH_CONNECTED", "sessionId": identifier,
                "hostFingerprint": fingerprint, "protectedValuesReturned": False}

    def _delegation_ready(self, state, operation):
        if time.time() >= state.get("grantUntil", 0) or operation not in state.get("allowedOperations", []):
            raise ValueError("Owner SSH delegation missing, revoked or expired")
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
            if state["status"] in {"connected", "close_unverified"} and time.time() >= state["expiresAt"]:
                self._close(state)

    def assistant_inspect(self, session_id, operation):
        with self._lock():
            state = self._state()
            if session_id != state["sessionId"]:
                raise ValueError("SSH session identity mismatch")
            self._ready(state)
            self._delegation_ready(state, operation)
            return self._inspect(state, operation, actor="assistant")

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
            state = self._state()
            if action.get("sessionId") != state["sessionId"]:
                raise ValueError("SSH session identity mismatch")
            selected = action.get("action")
            if selected == "close":
                self._close(state)
                return {"ok": True, "status": "SSH_CLOSED", "sessionId": state["sessionId"]}
            if selected == "revoke":
                state.update(grantUntil=0, allowedOperations=[])
                self._write("ssh_console_state.json", state)
                return {"ok": True, "status": "SSH_DELEGATION_REVOKED"}
            self._ready(state)
            if selected == "grant":
                ops = action.get("operations")
                if not isinstance(ops, list) or not ops or any(op not in OPERATIONS for op in ops):
                    raise ValueError("Invalid owner SSH delegation scope")
                ttl = action.get("ttl", 300)
                if type(ttl) is not int or not 30 <= ttl <= 900:
                    raise ValueError("Invalid owner SSH delegation lifetime")
                state.update(grantUntil=min(time.time() + ttl, state["expiresAt"]), allowedOperations=sorted(set(ops)))
                self._write("ssh_console_state.json", state)
                return {"ok": True, "status": "SSH_DELEGATION_GRANTED", "sessionId": state["sessionId"],
                        "allowedOperations": state["allowedOperations"], "expiresAt": state["grantUntil"]}
            if selected == "inspect":
                return self._inspect(state, str(action.get("operation") or ""))
            raise ValueError("Owner SSH action is not allowlisted")
