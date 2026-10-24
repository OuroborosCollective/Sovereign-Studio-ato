"""Fixed Aurion native-auth repair contracts; never an arbitrary env editor.

All secret-bearing objects stay inside the host adapter. Public plans carry
only identity, file fingerprints and validity predicates.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import time
import threading
from functools import wraps
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

TARGET = "echoes-of-aurion/aurion"
ENV_FILE = "/opt/echoes-of-aurion/.env.production"
RUNTIME_FILE = "/etc/aurion-traefik-runtime.env"
RELEASE = "NATIVE_AUTH_RELEASE_ENABLED"
SEAL = "NATIVE_AUTH_STATE_SEAL_KEY"
SHA = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
OPERATION = re.compile(r"[0-9a-f]{32}")


class RepairBlocked(ValueError):
    """Fixed failure code only: never include input, stderr or file contents."""


def redacted_boundary(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except RepairBlocked:
            raise
        except Exception:
            raise RepairBlocked("NATIVE_AUTH_OPERATION_UNAVAILABLE") from None
    return guarded


def fingerprint(value):
    return hashlib.sha256(value).hexdigest()


def canonical_hash(value):
    return fingerprint(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def valid_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
        return False
    try:
        raw = base64.b64decode(value + "=", altchars=b"-_", validate=True)
    except ValueError:
        return False
    return len(raw) == 32 and base64.urlsafe_b64encode(raw).decode().rstrip("=") == value


def parse_env(raw):
    """Deliberately strict dotenv subset. Ambiguity blocks instead of guessing.

    Preserve original bytes for unrelated entries. Never evaluate expansion or
    shell syntax, and reject duplicate names even when values agree.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise RepairBlocked("ENV_ENCODING") from None
    if "\x00" in text or "\r" in text:
        raise RepairBlocked("ENV_FORMAT")
    values = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if not match:
            raise RepairBlocked("ENV_FORMAT")
        name, value = match.groups()
        if name in values:
            raise RepairBlocked("ENV_DUPLICATE")
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0] or value[0] in value[1:-1]:
                raise RepairBlocked("ENV_FORMAT")
            value = value[1:-1]
        elif any(c.isspace() for c in value) or "#" in value:
            raise RepairBlocked("ENV_FORMAT")
        if any(c in value for c in ("$", "`", "\\")):
            raise RepairBlocked("ENV_EXPANSION")
        values[name] = value
    return values


def configuration(raw):
    values = parse_env(raw)
    key = values.get(SEAL, "")
    return {"releaseEnabled": values.get(RELEASE) == "true",
            "stateSealKeyPresent": bool(key), "stateSealKeyValid": valid_key(key)}


def repaired_env(raw, *, generate_key):
    values = parse_env(raw)
    key = values.get(SEAL, "")
    # Existing malformed keys are never silently replaced or rotated.
    if key and not valid_key(key):
        raise RepairBlocked("EXISTING_KEY_INVALID")
    if not key:
        if generate_key is not True:
            raise RepairBlocked("KEY_GENERATION_NOT_APPROVED")
        key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    elif generate_key is not False:
        raise RepairBlocked("KEY_GENERATION_PLAN_DRIFT")
    lines = [line for line in raw.decode().splitlines(keepends=True)
             if not line.startswith((RELEASE + "=", SEAL + "="))]
    preserved = "".join(lines)
    if preserved and not preserved.endswith("\n"):
        preserved += "\n"
    return (preserved + RELEASE + "=true\n" + SEAL + "=" + key + "\n").encode()


@dataclass(frozen=True, repr=False)
class ProtectedSnapshot:
    raw: bytes
    device: int
    inode: int
    uid: int
    gid: int
    mode: int
    mtime_ns: int
    ctime_ns: int

    def identity(self):
        return {"sha256": fingerprint(self.raw), "device": self.device,
                "inode": self.inode, "uid": self.uid, "gid": self.gid,
                "mode": self.mode, "mtimeNs": self.mtime_ns, "ctimeNs": self.ctime_ns}


def read_protected(directory_fd, name, *, limit=1048576, modes=(0o600,)):
    if "/" in name or name in ("", ".", ".."):
        raise RepairBlocked("FILE_NAME")
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_gid != 0
                    or stat.S_IMODE(before.st_mode) not in modes or before.st_nlink != 1
                    or before.st_size > limit):
                raise RepairBlocked("FILE_PROTECTION")
            chunks = []
            count = 0
            while True:
                chunk = os.read(fd, min(65536, limit + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
                if count > limit:
                    raise RepairBlocked("FILE_SIZE")
            after = os.fstat(fd)
            if (before.st_ino, before.st_mtime_ns, before.st_ctime_ns, before.st_size) != (
                    after.st_ino, after.st_mtime_ns, after.st_ctime_ns, after.st_size):
                raise RepairBlocked("FILE_DRIFT")
            return ProtectedSnapshot(b"".join(chunks), before.st_dev, before.st_ino,
                                     before.st_uid, before.st_gid, stat.S_IMODE(before.st_mode),
                                     before.st_mtime_ns, before.st_ctime_ns)
        finally:
            os.close(fd)
    except OSError:
        raise RepairBlocked("FILE_UNAVAILABLE") from None


def atomic_replace(directory_fd, name, before, content):
    """Caller holds the target operation lock in a root-owned private directory.

    Recheck both content and inode immediately before rename. Privileged writers
    outside this lane must honor the same lock; no filesystem CAS is claimed.
    """
    temporary = ".native-auth-" + secrets.token_hex(16)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory_fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchown(stream.fileno(), 0, 0)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if read_protected(directory_fd, name).identity() != before.identity():
            raise RepairBlocked("FILE_DRIFT")
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
        result = read_protected(directory_fd, name)
        if result.raw != content:
            raise RepairBlocked("FILE_READBACK")
        return result
    finally:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


class NativeAuthRepair:
    """One fixed operation on the existing owner-managed storage/worker boundary.

    The host adapter owns all Docker, HTTP and secret-bearing file I/O. Neither
    callers nor approval records can supply commands, paths, SQL or key values.
    ``issue`` is called only from the authenticated owner HTTP route, never MCP.
    """

    def __init__(self, adapter, state, *, clock=time.time):
        self.adapter, self.state, self.clock = adapter, state, clock

    def _adapter(self, method, *args):
        try:
            return getattr(self.adapter, method)(*args)
        except Exception:
            raise RepairBlocked("HOST_ADAPTER_FAILED") from None

    @redacted_boundary
    def plan(self, expected_revision, *, target=TARGET):
        if target != TARGET or not isinstance(expected_revision, str) or not REVISION.fullmatch(expected_revision):
            raise RepairBlocked("TARGET_OR_REVISION_INVALID")
        snapshot = self._adapter("snapshot", expected_revision)
        required = {"target", "revision", "containerId", "imageId", "metadataFingerprint",
                    "configurationFingerprint", "schemaVerified", "healthy", "configuration"}
        if set(snapshot) != required:
            raise RepairBlocked("SNAPSHOT_CONTRACT")
        if snapshot["target"] != TARGET or snapshot["revision"] != expected_revision:
            raise RepairBlocked("TARGET_OR_REVISION_DRIFT")
        if (not SHA.fullmatch(snapshot["containerId"])
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", snapshot["imageId"])
                or not all(SHA.fullmatch(snapshot[k]) for k in ("metadataFingerprint", "configurationFingerprint"))):
            raise RepairBlocked("IDENTITY_UNRESOLVED")
        if snapshot["schemaVerified"] is not True:
            raise RepairBlocked("SCHEMA_MISMATCH")
        if snapshot["healthy"] is not True:
            raise RepairBlocked("BASELINE_UNHEALTHY")
        config = snapshot["configuration"]
        if (set(config) != {"releaseEnabled", "stateSealKeyPresent", "stateSealKeyValid"}
                or any(type(value) is not bool for value in config.values())):
            raise RepairBlocked("CONFIGURATION_CONTRACT")
        if config["stateSealKeyPresent"] and not config["stateSealKeyValid"]:
            raise RepairBlocked("EXISTING_KEY_INVALID")
        if config["stateSealKeyValid"] and not config["stateSealKeyPresent"]:
            raise RepairBlocked("CONFIGURATION_CONTRACT")
        body = {"version": 1, "snapshot": snapshot,
                "generateKey": not config["stateSealKeyPresent"],
                "alreadySatisfied": config["releaseEnabled"] and config["stateSealKeyValid"],
                "effects": ["Set only NATIVE_AUTH_RELEASE_ENABLED=true and NATIVE_AUTH_STATE_SEAL_KEY",
                            "Generate 32 local random bytes only if generateKey=true; otherwise reuse key",
                            "Recreate only echoes-of-aurion/aurion with the identical immutable image",
                            "Brief service interruption; root-protected backup and controlled rollback",
                            "One valid start probe creates one expiring auth transaction through the application API"],
                "deviceFlow": "UNVERIFIED"}
        return {**body, "planHash": canonical_hash(body)}

    @redacted_boundary
    def issue(self, plan_hash, expected_revision):
        """Authenticated owner-route entrypoint; caller supplies no attestation."""
        with self.state.lock():
            plan = self.plan(expected_revision)
            if not isinstance(plan_hash, str) or plan_hash != plan["planHash"]:
                raise RepairBlocked("PLAN_DRIFT")
            if plan["alreadySatisfied"]:
                raise RepairBlocked("ALREADY_SATISFIED")
            # Only a new authenticated owner action may retire a provably
            # pre-effect interrupted preparation; retain a terminal receipt.
            self.state.recover_preparation_only()
            self.state.require_no_uncertain_operation()
            operation_id = secrets.token_hex(16)
            record = {"operationId": operation_id, "target": TARGET, "plan": plan,
                      "expiresAt": self.clock() + 300}
            self.state.create("approval", operation_id, record)
            return {"operationId": operation_id, "expiresAt": record["expiresAt"],
                    "planHash": plan_hash, "target": TARGET}

    @redacted_boundary
    def readback(self, operation_id):
        if not isinstance(operation_id, str) or not OPERATION.fullmatch(operation_id):
            raise RepairBlocked("OPERATION_INVALID")
        receipt = self.state.read("receipt", operation_id)
        if receipt is not None and receipt.get("phase") in {"NO_EFFECT_PREPARATION_INCOMPLETE", "EXPIRED_WITHOUT_EFFECT"}:
            return {"operationId": operation_id, "phase": receipt["phase"], "noTargetEffects": True,
                    "mutationRetried": False, "deviceFlow": "UNVERIFIED"}
        if receipt is None:
            receipt = self.state.preparation_only(operation_id)
            if receipt is None:
                approval = self.state.read("approval", operation_id)
                if approval is not None:
                    return {"operationId": operation_id, "phase": "APPROVAL_PENDING" if self.clock() < approval.get("expiresAt", 0) else "APPROVAL_EXPIRED",
                            "mutationRetried": False, "deviceFlow": "UNVERIFIED"}
                raise RepairBlocked("OPERATION_UNKNOWN")
            return {"operationId": operation_id, "phase": "NO_EFFECT_PREPARATION_INCOMPLETE",
                    "noTargetEffects": True, "mutationRetried": False, "deviceFlow": "UNVERIFIED",
                    "nextAction": "new_authenticated_owner_plan_approval"}
        observed = self._adapter("readback", receipt["plan"], operation_id)
        return {"operationId": operation_id, "phase": receipt["phase"], "ok": all(self._public_readback(observed).values()),
                "readback": self._public_readback(observed), "deviceFlow": "UNVERIFIED",
                "mutationRetried": False}

    @staticmethod
    def _public_readback(observed):
        # Do not propagate arbitrary adapter output, response bodies or exceptions.
        keys = ("sameImage", "sameRevision", "healthy", "releaseEnabled",
                "stateSealKeyPresent", "stateSealKeyValid", "configurationBound", "validStart200", "invalidBody400")
        return {key: observed.get(key) is True for key in keys}

    @redacted_boundary
    def apply(self, operation_id):
        if not isinstance(operation_id, str) or not OPERATION.fullmatch(operation_id):
            raise RepairBlocked("OPERATION_INVALID")
        with self.state.lock():
            if (self.state.read("receipt", operation_id) is not None
                    or self.state.preparation_only(operation_id) is not None):
                # A restart, timeout or duplicate delivery may only observe.
                return {**self.readback(operation_id), "replayRejected": True}
            self.state.require_no_uncertain_operation()
            approval = self.state.read("approval", operation_id)
            if (not approval or approval.get("operationId") != operation_id
                    or approval.get("target") != TARGET or self.clock() >= approval.get("expiresAt", 0)):
                raise RepairBlocked("APPROVAL_EXPIRED_OR_INVALID")
            plan = approval["plan"]
            current = self.plan(plan["snapshot"]["revision"])
            if current != plan:
                raise RepairBlocked("PLAN_DRIFT")
            # Durable intent + active lock precede consumption and all target effects.
            receipt = {"operationId": operation_id, "plan": plan, "phase": "PREPARED"}
            self.state.begin(operation_id, receipt)
            self.state.consume(operation_id)
            if self.clock() >= approval["expiresAt"]:
                receipt["phase"] = "EXPIRED_WITHOUT_EFFECT"
                self.state.complete(operation_id, receipt)
                raise RepairBlocked("APPROVAL_EXPIRED_OR_INVALID")
            # Exceptions/crashes after PREPARED deliberately leave the durable
            # operation uncertain. A retry cannot generate keys or recreate again.
            backup = self._adapter("backup", plan, operation_id)
            if not isinstance(backup, str) or not SHA.fullmatch(backup):
                raise RepairBlocked("BACKUP_IDENTITY_INVALID")
            receipt.update(phase="BACKUP_VERIFIED", backupIdentity=backup)
            self.state.update(operation_id, receipt)
            self._adapter("apply_configuration", plan, operation_id)
            receipt["phase"] = "CONFIGURATION_WRITTEN"
            self.state.update(operation_id, receipt)
            probes_completed = False
            try:
                self._adapter("recreate_same_image", plan, operation_id)
                self._adapter("verify_after_recreate", plan, operation_id)
                probes_completed = True
            except RepairBlocked:
                # First read the target after a command/probe failure. Never
                # repeat the recreation or POST after an uncertain return.
                pass
            observed = self._public_readback(self._adapter("readback", plan, operation_id))
            if not probes_completed:
                observed.update(validStart200=False, invalidBody400=False)
            if all(observed.values()):
                receipt.update(phase="VERIFIED", readback=observed)
                self.state.complete(operation_id, receipt)
            elif not observed["healthy"] and observed["sameImage"] and observed["sameRevision"]:
                # An identity mismatch or merely failed auth probe is not evidence
                # permitting a blind restore over a different deployment.
                receipt["phase"] = "ROLLBACK_STARTED"
                self.state.update(operation_id, receipt)
                self._adapter("rollback", plan, operation_id, backup)
                rollback = self._adapter("rollback_readback", plan, operation_id, backup)
                verified = all(rollback.get(k) is True for k in (
                    "sameImage", "sameRevision", "healthy", "configurationRestored"))
                receipt["phase"] = "ROLLED_BACK" if verified else "ROLLBACK_UNVERIFIED"
                if verified:
                    self.state.complete(operation_id, receipt)
                else:
                    self.state.update(operation_id, receipt)
            else:
                receipt.update(phase="APPLIED_UNVERIFIED", readback=observed)
                self.state.update(operation_id, receipt)
            return self.readback(operation_id)


class NativeAuthState:
    """Dedicated records in the existing protected owner-input directory.

    This does not accept SSH grants, credential widgets or caller-supplied owner
    assertions. Only the authenticated backend may issue approval records.
    """

    TERMINAL = frozenset({"VERIFIED", "ROLLED_BACK", "EXPIRED_WITHOUT_EFFECT", "NO_EFFECT_PREPARATION_INCOMPLETE"})

    def __init__(self, root=None):
        self.root = Path(root or os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", "/opt/sovereign-owner-managed"))
        self._local = threading.local()

    @contextmanager
    def directory(self):
        pinned = getattr(self._local, "fd", None)
        if pinned is not None:
            yield pinned
            return
        # Traverse with no-follow dirfds, not Path.resolve() followed by open().
        if not self.root.is_absolute() or ".." in self.root.parts:
            raise RepairBlocked("STATE_ROOT_INVALID")
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                for component in self.root.parts[1:]:
                    new_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd)
                    fd = new_fd
                    ancestor = os.fstat(fd)
                    if ancestor.st_uid != 0 or ancestor.st_gid != 0 or ancestor.st_mode & 0o022:
                        raise RepairBlocked("STATE_ANCESTOR_PROTECTION")
            except OSError:
                raise RepairBlocked("STATE_UNAVAILABLE") from None
            info = os.fstat(fd)
            if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
                raise RepairBlocked("STATE_ROOT_PROTECTION")
            yield fd
        finally:
            os.close(fd)

    @contextmanager
    def lock(self):
        with self.directory() as directory_fd:
            try:
                fd = os.open(".aurion-native-auth.lock", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory_fd)
                try:
                    os.fchown(fd, 0, 0)
                except Exception:
                    os.close(fd)
                    raise
            except FileExistsError:
                fd = os.open(".aurion-native-auth.lock", os.O_RDWR | os.O_NOFOLLOW, dir_fd=directory_fd)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                    raise RepairBlocked("STATE_LOCK_PROTECTION")
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RepairBlocked("CONCURRENT_OPERATION") from None
                self._local.fd = directory_fd
                try:
                    yield
                finally:
                    del self._local.fd
            finally:
                os.close(fd)

    @staticmethod
    def name(kind, operation_id):
        if kind not in {"approval", "receipt", "active"} or not OPERATION.fullmatch(operation_id):
            raise RepairBlocked("STATE_IDENTITY_INVALID")
        return "aurion-native-auth-" + ("active" if kind == "active" else kind + "-" + operation_id) + ".json"

    def read(self, kind, operation_id):
        name = self.name(kind, operation_id)
        with self.directory() as fd:
            try:
                os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                return None
            try:
                value = json.loads(read_protected(fd, name).raw)
            except (ValueError, UnicodeError):
                raise RepairBlocked("STATE_RECORD_INVALID") from None
            if not isinstance(value, dict):
                raise RepairBlocked("STATE_RECORD_INVALID")
            return value

    def create(self, kind, operation_id, record):
        # All writers hold lock(). Publish complete JSON by rename; a crash
        # during serialization must not leave an unreadable active marker.
        name = self.name(kind, operation_id)
        with self.directory() as directory_fd:
            temporary = ".native-auth-state-" + secrets.token_hex(16)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory_fd)
            try:
                with os.fdopen(fd, "w") as stream:
                    os.fchown(stream.fileno(), 0, 0)
                    json.dump(record, stream, separators=(",", ":"), sort_keys=True)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise RepairBlocked("STATE_RECORD_EXISTS")
                os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
                os.fsync(directory_fd)
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory_fd)
                except FileNotFoundError:
                    pass

    def update(self, operation_id, receipt):
        name = self.name("receipt", operation_id)
        with self.directory() as fd:
            before = read_protected(fd, name)
            atomic_replace(fd, name, before,
                           json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode())

    def remove(self, kind, operation_id):
        with self.directory() as fd:
            os.unlink(self.name(kind, operation_id), dir_fd=fd)
            os.fsync(fd)

    def require_no_uncertain_operation(self):
        active = self.read("active", "0" * 32)
        if active is not None:
            operation_id = active.get("operationId", "")
            receipt = self.read("receipt", operation_id)
            if receipt is None or receipt.get("phase") not in self.TERMINAL:
                raise RepairBlocked("PREVIOUS_OUTCOME_UNCERTAIN_READBACK_REQUIRED")
            self.remove("active", operation_id)

    def begin(self, operation_id, receipt):
        self.create("active", operation_id, {**receipt, "phase": "INTENT_ONLY"})
        self.create("receipt", operation_id, receipt)

    def preparation_only(self, operation_id):
        active = self.read("active", operation_id)
        if active is None or active.get("operationId") != operation_id:
            return None
        if self.read("receipt", operation_id) is not None:
            return None
        approval = self.read("approval", operation_id)
        if (active.get("phase") != "INTENT_ONLY" or not approval
                or active.get("plan") != approval.get("plan")):
            raise RepairBlocked("PREPARATION_IDENTITY_UNCERTAIN")
        return active

    def recover_preparation_only(self):
        active = self.read("active", "0" * 32)
        if active is None:
            return
        operation_id = active.get("operationId", "")
        intent = self.preparation_only(operation_id)
        if intent is not None:
            self.create("receipt", operation_id, {**intent, "phase": "NO_EFFECT_PREPARATION_INCOMPLETE"})
            self.consume(operation_id)
            self.remove("active", operation_id)

    def consume(self, operation_id):
        self.remove("approval", operation_id)

    def complete(self, operation_id, receipt):
        if receipt.get("phase") not in self.TERMINAL:
            raise RepairBlocked("NONTERMINAL_OPERATION")
        self.update(operation_id, receipt)
        self.remove("active", operation_id)
