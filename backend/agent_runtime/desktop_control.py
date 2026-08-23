"""Attempt-bound human desktop-control gateway for Live Workspace.

The gateway holds only opaque, hashed control metadata in a private activation
sidecar. It never exposes an input scope or host path and it does not infer
effects from desktop frames. The agent-side broker reads the same sidecar before
each GUI input, so USER_CONTROLLED blocks agent input at the actual host-worker
boundary rather than only in a browser projection.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from .desktop_activation import DesktopActivationHandleV1, DesktopActivationIssuerV1
from .fleet_supervisor import FleetContractError, stable_hash

_ACTIVATION_RE = re.compile(r"^[0-9a-f]{64}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SCOPE_NAME_RE = re.compile(r"^[0-9a-f]{64}\.input\.scope$")
_ACTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
_CONTROL_STATES = frozenset({"USER_CONTROLLED", "AGENT_CONTROLLED_REBOUND", "BLOCKED_STALE_STATE"})
_CONTROL_SCHEMA = "sovereign.desktop-control.v1"
_MAX_INPUT_BYTES = 2_048


def _text(value: object, field: str, maximum: int = 360) -> str:
    result = str(value or "").strip()
    if not result or len(result) > maximum:
        raise FleetContractError(f"{field} is invalid")
    return result


def _hash(value: object, field: str) -> str:
    result = _text(value, field, 64).lower()
    if not _HASH_RE.fullmatch(result):
        raise FleetContractError(f"{field} must be an exact SHA-256 value")
    return result


def _epoch(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise FleetContractError(f"{field} is invalid")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise FleetContractError(f"{field} is invalid") from exc
    if result < 0 or result > 4_102_444_800:
        raise FleetContractError(f"{field} is invalid")
    return result


@dataclass(frozen=True)
class DesktopControlRecordV1:
    lease_id: str
    session_binding_hash: str
    owner_subject_hash: str
    run_id: str
    attempt_id: str
    workspace_id: str
    worktree_identity_hash: str
    input_scope_hash: str
    state: str
    issued_readback_hash: str
    reconciled_readback_hash: str | None
    issued_at: int
    expires_at: int
    record_hash: str

    @classmethod
    def issue(
        cls,
        *,
        context: Any,
        handle: DesktopActivationHandleV1,
        owner_subject: str,
        now: int,
        ttl_seconds: int,
    ) -> "DesktopControlRecordV1":
        session = getattr(context, "session", None)
        reconciliation = getattr(context, "reconciliation", None)
        if session is None or reconciliation is None:
            raise FleetContractError("live workspace control requires a resolved context")
        if getattr(reconciliation, "session_binding_hash", None) != handle.session_binding_hash or getattr(reconciliation, "projection_state", None) != "LIVE":
            raise FleetContractError("takeover requires a fresh LIVE workspace readback")
        owner_hash = hashlib.sha256(("sovereign.user-input.v1|" + _text(owner_subject, "owner subject", 256)).encode("utf-8")).hexdigest()
        input_scope_hash = stable_hash({
            "schemaVersion": _CONTROL_SCHEMA,
            "capability": "USER_INPUT",
            "sessionBindingHash": handle.session_binding_hash,
            "attemptId": handle.attempt_id,
            "ownerSubjectHash": owner_hash,
        })
        issued_at = _epoch(now, "issued_at")
        if not 60 <= ttl_seconds <= 3_600:
            raise FleetContractError("desktop control lease ttl is invalid")
        payload = {
            "schemaVersion": _CONTROL_SCHEMA,
            "sessionBindingHash": handle.session_binding_hash,
            "ownerSubjectHash": owner_hash,
            "runId": _text(getattr(session, "run_id", None), "run id", 120),
            "attemptId": handle.attempt_id,
            "workspaceId": handle.workspace_id,
            "worktreeIdentityHash": handle.worktree_identity_hash,
            "inputScopeHash": input_scope_hash,
            "state": "USER_CONTROLLED",
            "issuedReadbackHash": _hash(getattr(reconciliation, "fresh_readback_hash", None), "fresh readback hash"),
            "reconciledReadbackHash": None,
            "issuedAt": issued_at,
            "expiresAt": issued_at + ttl_seconds,
        }
        lease_hash = stable_hash(payload)
        return cls(
            lease_id=f"livelease-{lease_hash[:24]}",
            session_binding_hash=payload["sessionBindingHash"],
            owner_subject_hash=payload["ownerSubjectHash"],
            run_id=payload["runId"],
            attempt_id=payload["attemptId"],
            workspace_id=payload["workspaceId"],
            worktree_identity_hash=payload["worktreeIdentityHash"],
            input_scope_hash=payload["inputScopeHash"],
            state=payload["state"],
            issued_readback_hash=payload["issuedReadbackHash"],
            reconciled_readback_hash=None,
            issued_at=payload["issuedAt"],
            expires_at=payload["expiresAt"],
            record_hash=stable_hash({**payload, "leaseId": f"livelease-{lease_hash[:24]}"}),
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DesktopControlRecordV1":
        if not isinstance(value, dict) or value.get("schemaVersion") != _CONTROL_SCHEMA:
            raise FleetContractError("desktop control record is invalid")
        state = _text(value.get("state"), "control state", 48)
        if state not in _CONTROL_STATES:
            raise FleetContractError("desktop control state is invalid")
        reconciled = value.get("reconciledReadbackHash")
        payload = {
            "schemaVersion": _CONTROL_SCHEMA,
            "leaseId": _text(value.get("leaseId"), "lease id", 80),
            "sessionBindingHash": _hash(value.get("sessionBindingHash"), "session binding hash"),
            "ownerSubjectHash": _hash(value.get("ownerSubjectHash"), "owner subject hash"),
            "runId": _text(value.get("runId"), "run id", 120),
            "attemptId": _text(value.get("attemptId"), "attempt id", 80),
            "workspaceId": _text(value.get("workspaceId"), "workspace id", 160),
            "worktreeIdentityHash": _hash(value.get("worktreeIdentityHash"), "worktree identity hash"),
            "inputScopeHash": _hash(value.get("inputScopeHash"), "input scope hash"),
            "state": state,
            "issuedReadbackHash": _hash(value.get("issuedReadbackHash"), "issued readback hash"),
            "reconciledReadbackHash": None if reconciled is None else _hash(reconciled, "reconciled readback hash"),
            "issuedAt": _epoch(value.get("issuedAt"), "issued at"),
            "expiresAt": _epoch(value.get("expiresAt"), "expires at"),
        }
        if not payload["leaseId"].startswith("livelease-") or payload["expiresAt"] <= payload["issuedAt"]:
            raise FleetContractError("desktop control lease is invalid")
        expected = stable_hash(payload)
        record_hash = _hash(value.get("recordHash"), "control record hash")
        if record_hash != expected:
            raise FleetContractError("desktop control record hash is invalid")
        return cls(
            lease_id=payload["leaseId"],
            session_binding_hash=payload["sessionBindingHash"],
            owner_subject_hash=payload["ownerSubjectHash"],
            run_id=payload["runId"],
            attempt_id=payload["attemptId"],
            workspace_id=payload["workspaceId"],
            worktree_identity_hash=payload["worktreeIdentityHash"],
            input_scope_hash=payload["inputScopeHash"],
            state=payload["state"],
            issued_readback_hash=payload["issuedReadbackHash"],
            reconciled_readback_hash=payload["reconciledReadbackHash"],
            issued_at=payload["issuedAt"],
            expires_at=payload["expiresAt"],
            record_hash=record_hash,
        )

    def reconcile(self, *, context: Any, now: int) -> "DesktopControlRecordV1":
        reconciliation = getattr(context, "reconciliation", None)
        session = getattr(context, "session", None)
        if reconciliation is None or session is None or getattr(reconciliation, "session_binding_hash", None) != self.session_binding_hash:
            raise FleetContractError("give back readback belongs to another session")
        state = "AGENT_CONTROLLED_REBOUND" if getattr(reconciliation, "projection_state", None) == "LIVE" else "BLOCKED_STALE_STATE"
        payload = {
            "schemaVersion": _CONTROL_SCHEMA,
            "leaseId": self.lease_id,
            "sessionBindingHash": self.session_binding_hash,
            "ownerSubjectHash": self.owner_subject_hash,
            "runId": self.run_id,
            "attemptId": self.attempt_id,
            "workspaceId": self.workspace_id,
            "worktreeIdentityHash": self.worktree_identity_hash,
            "inputScopeHash": self.input_scope_hash,
            "state": state,
            "issuedReadbackHash": self.issued_readback_hash,
            "reconciledReadbackHash": _hash(getattr(reconciliation, "fresh_readback_hash", None), "fresh readback hash"),
            "issuedAt": self.issued_at,
            "expiresAt": max(self.expires_at, _epoch(now, "reconciled at")),
        }
        return DesktopControlRecordV1(
            lease_id=self.lease_id,
            session_binding_hash=self.session_binding_hash,
            owner_subject_hash=self.owner_subject_hash,
            run_id=self.run_id,
            attempt_id=self.attempt_id,
            workspace_id=self.workspace_id,
            worktree_identity_hash=self.worktree_identity_hash,
            input_scope_hash=self.input_scope_hash,
            state=state,
            issued_readback_hash=self.issued_readback_hash,
            reconciled_readback_hash=payload["reconciledReadbackHash"],
            issued_at=self.issued_at,
            expires_at=payload["expiresAt"],
            record_hash=stable_hash(payload),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": _CONTROL_SCHEMA,
            "leaseId": self.lease_id,
            "sessionBindingHash": self.session_binding_hash,
            "ownerSubjectHash": self.owner_subject_hash,
            "runId": self.run_id,
            "attemptId": self.attempt_id,
            "workspaceId": self.workspace_id,
            "worktreeIdentityHash": self.worktree_identity_hash,
            "inputScopeHash": self.input_scope_hash,
            "state": self.state,
            "issuedReadbackHash": self.issued_readback_hash,
            "reconciledReadbackHash": self.reconciled_readback_hash,
            "issuedAt": self.issued_at,
            "expiresAt": self.expires_at,
            "recordHash": self.record_hash,
        }

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "leaseId": self.lease_id,
            "sessionBindingHash": self.session_binding_hash,
            "attemptId": self.attempt_id,
            "workspaceId": self.workspace_id,
            "worktreeIdentityHash": self.worktree_identity_hash,
            "leaseKind": "USER_INPUT",
            "state": self.state,
            "issuedReadbackHash": self.issued_readback_hash,
            "reconciledReadbackHash": self.reconciled_readback_hash,
            "expiresAt": self.expires_at,
            "controlHash": self.record_hash,
            "authoritative": False,
        }


class DesktopControlGatewayV1:
    def __init__(
        self,
        *,
        issuer: DesktopActivationIssuerV1,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], float] = time.time,
        lease_ttl_seconds: int = 600,
    ) -> None:
        self.issuer = issuer
        self.activation_root = issuer.activation_root
        self.opener = opener
        self.clock = clock
        self.lease_ttl_seconds = lease_ttl_seconds

    @classmethod
    def from_env(cls) -> "DesktopControlGatewayV1":
        return cls(issuer=DesktopActivationIssuerV1.from_env())

    def _control_path(self, activation_id: str) -> Path:
        if not _ACTIVATION_RE.fullmatch(activation_id):
            raise FleetContractError("desktop activation id is invalid")
        return self.activation_root / f"{activation_id}.control.json"

    @contextmanager
    def _locked_control(self, activation_id: str):
        """Serialize handoff and host-input dispatch for one exact activation."""
        if self.activation_root.is_symlink() or not self.activation_root.is_dir():
            raise FleetContractError("desktop activation root is unavailable")
        lock_path = self.activation_root / f"{_hash(activation_id, 'activation id')}.control.lock"
        try:
            descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        except OSError as exc:
            raise FleetContractError("desktop control lock is unavailable") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
                raise FleetContractError("desktop control lock is unsafe")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _activation_document(self, *, context: Any, activation_id: str) -> tuple[DesktopActivationHandleV1, dict[str, Any]]:
        if self.activation_root.is_symlink() or not self.activation_root.is_dir():
            raise FleetContractError("desktop activation root is unavailable")
        document = self.activation_root / f"{_hash(activation_id, 'activation id')}.json"
        if document.is_symlink() or not document.is_file() or document.stat().st_mode & 0o077:
            raise FleetContractError("desktop activation document is unsafe")
        try:
            raw = json.loads(document.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FleetContractError("desktop activation document is unreadable") from exc
        if not isinstance(raw, dict):
            raise FleetContractError("desktop activation document is invalid")
        handle = self.issuer._handle(raw)
        if handle.activation_id != activation_id:
            raise FleetContractError("desktop activation id does not bind this document")
        session = getattr(context, "session", None)
        workspace = getattr(context, "attempt_workspace", None)
        if (
            session is None
            or workspace is None
            or handle.session_binding_hash != getattr(session, "session_binding_hash", None)
            or handle.attempt_id != getattr(workspace, "attempt_id", None)
            or handle.workspace_id != getattr(workspace, "workspace_id", None)
            or handle.worktree_identity_hash != getattr(workspace, "worktree_readback_sha256", None)
        ):
            raise FleetContractError("desktop activation belongs to another live workspace")
        return handle, raw

    def _read_record(self, *, handle: DesktopActivationHandleV1) -> DesktopControlRecordV1:
        path = self._control_path(handle.activation_id)
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
            raise FleetContractError("desktop control record is unavailable")
        try:
            raw = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FleetContractError("desktop control record is unreadable") from exc
        record = DesktopControlRecordV1.from_dict(raw)
        if (
            record.session_binding_hash != handle.session_binding_hash
            or record.attempt_id != handle.attempt_id
            or record.workspace_id != handle.workspace_id
            or record.worktree_identity_hash != handle.worktree_identity_hash
        ):
            raise FleetContractError("desktop control record does not bind this activation")
        return record

    def _write_record(self, record: DesktopControlRecordV1, *, handle: DesktopActivationHandleV1) -> None:
        if self.activation_root.is_symlink() or not self.activation_root.is_dir():
            raise FleetContractError("desktop activation root is unavailable")
        path = self._control_path(handle.activation_id)
        if path.exists() and path.is_symlink():
            raise FleetContractError("desktop control record is unsafe")
        temporary = self.activation_root / f".{handle.activation_id}.{secrets.token_hex(12)}.control.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as output:
                descriptor = -1
                output.write(json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8"))
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise FleetContractError("desktop control record could not be persisted") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    @staticmethod
    def _owner_hash(user_id: str) -> str:
        return hashlib.sha256(("sovereign.user-input.v1|" + _text(user_id, "owner subject", 256)).encode("utf-8")).hexdigest()

    def takeover(self, *, context: Any, user_id: str) -> dict[str, Any]:
        handle = self.issuer.issue(context=context)
        now = int(self.clock())
        with self._locked_control(handle.activation_id):
            try:
                current = self._read_record(handle=handle)
            except FleetContractError:
                current = None
            if current is not None and current.state == "USER_CONTROLLED" and now < current.expires_at:
                if current.owner_subject_hash != self._owner_hash(user_id):
                    raise FleetContractError("desktop input is exclusively held by another user")
                return {"ok": True, "desktopActivation": handle.to_dict(), "control": current.to_public_dict()}
            record = DesktopControlRecordV1.issue(
                context=context,
                handle=handle,
                owner_subject=user_id,
                now=now,
                ttl_seconds=self.lease_ttl_seconds,
            )
            self._write_record(record, handle=handle)
        return {"ok": True, "desktopActivation": handle.to_dict(), "control": record.to_public_dict()}

    def give_back(self, *, context: Any, user_id: str, activation_id: str, lease_id: str) -> dict[str, Any]:
        handle, _raw = self._activation_document(context=context, activation_id=activation_id)
        with self._locked_control(handle.activation_id):
            record = self._read_record(handle=handle)
            if record.lease_id != _text(lease_id, "lease id", 80) or record.owner_subject_hash != self._owner_hash(user_id):
                raise FleetContractError("desktop control lease is not owned by this user")
            next_record = record.reconcile(context=context, now=int(self.clock()))
            self._write_record(next_record, handle=handle)
        return {
            "ok": next_record.state == "AGENT_CONTROLLED_REBOUND",
            "control": next_record.to_public_dict(),
            "reason": None if next_record.state == "AGENT_CONTROLLED_REBOUND" else "WORKSPACE_RECONCILIATION_REQUIRED",
        }

    def _input_scope(self, *, handle: DesktopActivationHandleV1, raw: dict[str, Any]) -> str:
        name = str(raw.get("inputScopeFile") or "").strip()
        if not _SCOPE_NAME_RE.fullmatch(name):
            raise FleetContractError("desktop input scope filename is invalid")
        path = self.activation_root / name
        if path.is_symlink() or not path.is_file():
            raise FleetContractError("desktop input scope is unavailable")
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077 or metadata.st_size > 256:
            raise FleetContractError("desktop input scope is unsafe")
        value = path.read_text("utf-8").strip()
        expected = _hash(raw.get("inputScopeHash"), "input scope hash")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,160}", value) or hashlib.sha256(value.encode("utf-8")).hexdigest() != expected:
            raise FleetContractError("desktop input scope does not match activation")
        return value

    @staticmethod
    def _input_payload(arguments: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            raise FleetContractError("desktop input must be an object")
        action_id = _text(arguments.get("actionId") or arguments.get("action_id"), "action id", 120)
        if not _ACTION_ID_RE.fullmatch(action_id):
            raise FleetContractError("desktop input action id is invalid")
        action = _text(arguments.get("action"), "action", 40).lower()
        if action not in {"pointer_move", "click", "type", "keypress", "scroll", "window_focus"}:
            raise FleetContractError("desktop input action is forbidden")
        payload: dict[str, Any] = {"actionId": action_id, "action": action}
        if action in {"pointer_move", "click"}:
            for key in ("x", "y"):
                value = arguments.get(key)
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 7680:
                    raise FleetContractError(f"desktop input {key} is invalid")
                payload[key] = value
            if action == "click":
                button = _text(arguments.get("button") or "left", "button", 12).lower()
                if button not in {"left", "middle", "right"}:
                    raise FleetContractError("desktop input button is invalid")
                payload["button"] = button
        elif action == "type":
            value = arguments.get("text")
            if not isinstance(value, str) or not value or len(value.encode("utf-8")) > _MAX_INPUT_BYTES:
                raise FleetContractError("desktop input text is invalid")
            payload["text"] = value
        elif action == "keypress":
            value = _text(arguments.get("key"), "key", 80)
            if not re.fullmatch(r"[A-Za-z0-9_+.-]{1,80}", value):
                raise FleetContractError("desktop input key is invalid")
            payload["key"] = value
        elif action == "scroll":
            value = arguments.get("amount")
            if isinstance(value, bool) or not isinstance(value, int) or not -20 <= value <= 20 or value == 0:
                raise FleetContractError("desktop input amount is invalid")
            payload["amount"] = value
        else:
            value = _text(arguments.get("windowId") or arguments.get("window_id"), "window id", 12)
            if not value.isdecimal():
                raise FleetContractError("desktop input window id is invalid")
            payload["windowId"] = value
        return payload

    def user_input(self, *, context: Any, user_id: str, activation_id: str, lease_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handle, raw = self._activation_document(context=context, activation_id=activation_id)
        with self._locked_control(handle.activation_id):
            record = self._read_record(handle=handle)
            now = int(self.clock())
            if (
                record.lease_id != _text(lease_id, "lease id", 80)
                or record.owner_subject_hash != self._owner_hash(user_id)
                or record.state != "USER_CONTROLLED"
                or now >= record.expires_at
            ):
                raise FleetContractError("user input lease is unavailable")
            payload = self._input_payload(arguments)
            scope = self._input_scope(handle=handle, raw=raw)
            request = Request(
                f"http://sovereign-desktop-{handle.session_binding_hash[:20]}:8765/input",
                data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-Sovereign-Desktop-Scope": scope},
                method="POST",
            )
            try:
                response = self.opener(request, timeout=8)
                with response:
                    body = json.loads(response.read(4_096).decode("utf-8"))
            except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FleetContractError("desktop user input delivery failed") from exc
            if not isinstance(body, dict) or body.get("status") not in {"SENT", "OBSERVED"}:
                raise FleetContractError("desktop user input delivery failed")
        return {
            "ok": True,
            "status": str(body["status"]),
            "actionId": payload["actionId"],
            "inputKind": str(body.get("inputKind") or payload["action"]).upper(),
            "requestHash": str(body.get("requestHash") or ""),
            "runtimeIdentityHash": handle.runtime_identity_hash,
            "targetEffectVerified": False,
            "authoritative": False,
        }

    def frame_allowed(self, *, context: Any) -> bool:
        """Pause frame delivery while a human holds this exact input surface."""
        handle = self.issuer.issue(context=context)
        with self._locked_control(handle.activation_id):
            try:
                record = self._read_record(handle=handle)
            except FleetContractError:
                return True
            return record.state != "USER_CONTROLLED"


__all__ = ["DesktopControlGatewayV1", "DesktopControlRecordV1"]
