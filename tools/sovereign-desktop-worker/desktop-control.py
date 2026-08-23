#!/usr/bin/env python3
"""Bounded local GUI control service for the isolated desktop worker."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import time
from typing import Any, Mapping

MAX_MESSAGE_BYTES = 8_192
MAX_SCREENSHOT_BYTES = 16 * 1024 * 1024
MAX_CONSUMED_EFFECT_REQUESTS = 1_024
MAX_REVOKED_INPUT_LEASES = 1_024
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
SESSION_ID_RE = re.compile(r"^[a-z0-9._:-]{1,160}$")
ADMISSION_RE = re.compile(r"^desktop-admission-[0-9a-f]{24}$")
ATTEMPT_RE = re.compile(r"^attempt-[0-9a-f]{24}$")
GRANT_RE = re.compile(r"^desktop-(?:view|input)-[0-9a-f]{24}$")
LEASE_RE = re.compile(r"^livelease-[0-9a-f]{24}$")
VIEW_KINDS = frozenset({"SCREENSHOT", "WINDOW_LIST", "VIEWPORT_READBACK"})
INPUT_KINDS = frozenset(
    {"POINTER_MOVE", "CLICK", "TYPE", "KEYPRESS", "SCROLL", "WINDOW_FOCUS"}
)
ALL_KINDS = VIEW_KINDS | INPUT_KINDS
REQUEST_SCHEMA_VERSION = "sovereign.computer-use-request.v2"
SOCKET_PATH = Path(os.environ.get("DESKTOP_CONTROL_SOCKET", "/run/desktop-control/worker.sock"))
ACTIVITY_PATH = Path(os.environ.get("DESKTOP_ACTIVITY_PATH", "/run/desktop-control/activity"))
_ACTIVE_INPUT_LEASE: dict[str, Any] | None = None
_CONSUMED_EFFECT_REQUESTS: dict[str, int] = {}
_REVOKED_INPUT_LEASES: dict[str, int] = {}


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stable_hash(value: Mapping[str, Any]) -> str:
    return _hash(
        json.dumps(
            value,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _required_hash(name: str) -> str:
    value = os.environ.get(name, "").strip().lower()
    if not HASH_RE.fullmatch(value):
        raise RuntimeError("invalid worker binding")
    return value


def _required_text(name: str, pattern: re.Pattern[str]) -> str:
    value = os.environ.get(name, "").strip().lower()
    if not pattern.fullmatch(value):
        raise RuntimeError("invalid worker binding")
    return value


def _required_uid(name: str) -> int:
    value = os.environ.get(name, "").strip()
    if not value.isdecimal():
        raise RuntimeError("invalid worker binding")
    uid = int(value)
    if uid < 1 or uid > 65_535:
        raise RuntimeError("invalid worker binding")
    return uid


def _optional_admission_id() -> str:
    value = os.environ.get("DESKTOP_ADMISSION_ID", "").strip().lower()
    if not value:
        return ""
    if not ADMISSION_RE.fullmatch(value):
        raise RuntimeError("invalid worker binding")
    return value


def _bindings() -> dict[str, str]:
    return {
        "sessionId": _required_text("DESKTOP_SESSION_ID", SESSION_ID_RE),
        "sessionBindingHash": _required_hash("DESKTOP_SESSION_BINDING_HASH"),
        "runtimeIdentityHash": _required_hash("DESKTOP_RUNTIME_IDENTITY_HASH"),
        "containerIdentityHash": _required_hash("DESKTOP_CONTAINER_IDENTITY_HASH"),
        "inputScopeHash": _required_hash("DESKTOP_INPUT_SCOPE_HASH"),
        "viewScopeHash": _required_hash("DESKTOP_VIEW_SCOPE_HASH"),
        "admissionId": _optional_admission_id(),
        "imageDigest": _required_text(
            "DESKTOP_IMAGE_DIGEST", re.compile(r"^sha256:[0-9a-f]{64}$")
        ),
        "attemptId": _required_text("DESKTOP_ATTEMPT_ID", ATTEMPT_RE),
        "attemptHash": _required_hash("DESKTOP_ATTEMPT_HASH"),
        "worktreeIdentityHash": _required_hash("DESKTOP_WORKTREE_IDENTITY_HASH"),
        "observedHeadRevision": _required_text("DESKTOP_HEAD_REVISION", REVISION_RE),
        "controlClientUid": str(_required_uid("DESKTOP_CONTROL_CLIENT_UID")),
    }


def _run(arguments: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        arguments,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=3,
    )


def _number(value: object, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError("numeric value required")
    result = float(value)
    if not math.isfinite(result) or result < minimum or result > maximum:
        raise ValueError("numeric value out of bounds")
    return result


def _integer(value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError("integer value required")
    result = int(value)
    if result < minimum or result > maximum:
        raise ValueError("integer value out of bounds")
    return result


def _payload(raw: object) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("payload must be an object")
    return raw


def _only_keys(payload: Mapping[str, Any], allowed: set[str]) -> None:
    if set(payload) != allowed:
        raise ValueError("payload keys are not allowed")


def _normalised_coordinate(value: object) -> float:
    return round(_number(value, minimum=0.0, maximum=1.0), 6)


def _normalise_payload(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if kind in VIEW_KINDS:
        _only_keys(payload, set())
        return {}
    if kind == "POINTER_MOVE":
        _only_keys(payload, {"x", "y"})
        return {"x": _normalised_coordinate(payload.get("x")), "y": _normalised_coordinate(payload.get("y"))}
    if kind == "CLICK":
        _only_keys(payload, {"x", "y", "button"})
        return {
            "x": _normalised_coordinate(payload.get("x")),
            "y": _normalised_coordinate(payload.get("y")),
            "button": _integer(payload.get("button"), minimum=1, maximum=3),
        }
    if kind == "TYPE":
        _only_keys(payload, {"text"})
        text = payload.get("text")
        if not isinstance(text, str) or not text or len(text) > 2_000 or "\x00" in text:
            raise ValueError("text input is invalid")
        return {"text": text}
    if kind == "KEYPRESS":
        _only_keys(payload, {"key"})
        key = payload.get("key")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9+_.-]{1,80}", key):
            raise ValueError("keypress is invalid")
        return {"key": key}
    if kind == "SCROLL":
        _only_keys(payload, {"deltaX", "deltaY"})
        delta_x = _integer(payload.get("deltaX"), minimum=-20, maximum=20)
        delta_y = _integer(payload.get("deltaY"), minimum=-20, maximum=20)
        if delta_x != 0 or delta_y == 0:
            raise ValueError("scroll operation is unsupported")
        return {"deltaX": delta_x, "deltaY": delta_y}
    if kind == "WINDOW_FOCUS":
        _only_keys(payload, {"windowId"})
        window_id = payload.get("windowId")
        if not isinstance(window_id, str) or not re.fullmatch(r"[0-9a-f]{1,16}", window_id.lower()):
            raise ValueError("window focus is invalid")
        return {"windowId": window_id.lower()}
    raise ValueError("unsupported bounded operation")


def _display_size() -> tuple[int, int]:
    result = _run(["xdotool", "getdisplaygeometry"])
    if result.returncode != 0:
        raise RuntimeError("display unavailable")
    values = result.stdout.decode("ascii", "strict").strip().split()
    if len(values) != 2:
        raise RuntimeError("display geometry unavailable")
    return _integer(values[0], minimum=1, maximum=8192), _integer(values[1], minimum=1, maximum=8192)


def _pointer(payload: Mapping[str, Any]) -> dict[str, int]:
    width, height = _display_size()
    x = round(float(payload["x"]) * (width - 1))
    y = round(float(payload["y"]) * (height - 1))
    return {"x": x, "y": y}


def _observe(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if kind == "VIEWPORT_READBACK":
        width, height = _display_size()
        return {"width": width, "height": height}
    if kind == "WINDOW_LIST":
        result = _run(["xdotool", "search", "--onlyvisible", "--name", "."])
        if result.returncode not in {0, 1}:
            raise RuntimeError("window query unavailable")
        window_ids = [line for line in result.stdout.decode("ascii", "ignore").splitlines() if line.isdigit()][:24]
        return {"windowCount": len(window_ids), "windowSetHash": _hash("\n".join(window_ids).encode("ascii"))}
    if kind == "SCREENSHOT":
        result = _run(["xwd", "-root", "-silent"])
        if result.returncode != 0 or len(result.stdout) > MAX_SCREENSHOT_BYTES:
            raise RuntimeError("screenshot unavailable")
        return {"screenshotHash": _hash(result.stdout), "bytes": len(result.stdout)}
    raise ValueError("unsupported view operation")


def _input(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if kind == "POINTER_MOVE":
        point = _pointer(payload)
        result = _run(["xdotool", "mousemove", str(point["x"]), str(point["y"])])
    elif kind == "CLICK":
        point = _pointer(payload)
        result = _run(["xdotool", "mousemove", str(point["x"]), str(point["y"])])
        if result.returncode == 0:
            result = _run(["xdotool", "click", str(payload["button"])])
    elif kind == "TYPE":
        result = _run(["xdotool", "type", "--clearmodifiers", "--delay", "1", str(payload["text"])])
    elif kind == "KEYPRESS":
        result = _run(["xdotool", "key", "--clearmodifiers", str(payload["key"])])
    elif kind == "SCROLL":
        delta = int(payload["deltaY"])
        button = "4" if delta > 0 else "5"
        result = _run(["xdotool", "click", "--repeat", str(abs(delta)), button])
    elif kind == "WINDOW_FOCUS":
        result = _run(["xdotool", "windowactivate", "--sync", str(payload["windowId"])])
    else:
        raise ValueError("unsupported input operation")
    if result.returncode != 0:
        raise RuntimeError("bounded input unavailable")
    return {"delivery": "SENT"}


def _response(
    *,
    status: str,
    request_hash: str,
    kind: str,
    bindings: Mapping[str, str],
    detail: Mapping[str, Any],
    request: Mapping[str, Any] | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    observation_hash = _hash(
        json.dumps(
            {"status": status, "kind": kind, "detail": dict(detail)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    response: dict[str, Any] = {
        "status": status,
        "requestHash": request_hash,
        "sessionId": bindings["sessionId"],
        "sessionBindingHash": bindings["sessionBindingHash"],
        "admissionId": bindings["admissionId"],
        "runtimeIdentityHash": bindings["runtimeIdentityHash"],
        "containerIdentityHash": bindings["containerIdentityHash"],
        "imageDigest": bindings["imageDigest"],
        "attemptId": bindings["attemptId"],
        "attemptHash": bindings["attemptHash"],
        "worktreeIdentityHash": bindings["worktreeIdentityHash"],
        "observedHeadRevision": bindings["observedHeadRevision"],
        "inputKind": kind,
        "observationHash": observation_hash,
        "observedAtEpoch": int(time.time()),
    }
    if request is not None:
        for field in ("grantId", "subjectHash", "scopeHash"):
            value = request.get(field)
            if isinstance(value, str):
                response[field] = value
    if error_code:
        response["errorCode"] = error_code
    return response


def _required_message_text(message: Mapping[str, Any], name: str, pattern: re.Pattern[str]) -> str:
    value = message.get(name)
    if not isinstance(value, str) or not pattern.fullmatch(value.lower()):
        raise ValueError("request binding is invalid")
    return value.lower()


def _required_message_epoch(message: Mapping[str, Any], name: str) -> int:
    value = message.get(name)
    if isinstance(value, bool):
        raise ValueError("request epoch is invalid")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("request epoch is invalid") from exc
    if result < 1 or result > 4_102_444_800:
        raise ValueError("request epoch is invalid")
    return result


def _require_exact_binding(message: Mapping[str, Any], bindings: Mapping[str, str], fields: tuple[str, ...]) -> None:
    for field in fields:
        value = message.get(field)
        if not isinstance(value, str) or value.lower() != bindings[field]:
            raise ValueError("request binding is invalid")


def _apply_admission_bind(message: object, bindings: dict[str, str]) -> dict[str, Any]:
    if not isinstance(message, Mapping):
        raise ValueError("admission bind must be an object")
    _require_exact_binding(
        message,
        bindings,
        (
            "sessionId",
            "sessionBindingHash",
            "runtimeIdentityHash",
            "containerIdentityHash",
            "imageDigest",
            "attemptId",
            "attemptHash",
            "worktreeIdentityHash",
            "observedHeadRevision",
        ),
    )
    admission_id = _required_message_text(message, "admissionId", ADMISSION_RE)
    if bindings["admissionId"] and bindings["admissionId"] != admission_id:
        raise ValueError("admission bind is immutable")
    bindings["admissionId"] = admission_id
    _record_activity()
    return _response(
        status="OBSERVED",
        request_hash="0" * 64,
        kind="ADMISSION_BIND",
        bindings=bindings,
        detail={"bound": True},
    )


def _lease_fingerprint(lease: Mapping[str, Any]) -> str:
    return _stable_hash(
        {
            "leaseId": lease["leaseId"],
            "leaseReadbackHash": lease["leaseReadbackHash"],
        }
    )


def _purge_expired_leases() -> None:
    now = int(time.time())
    for fingerprint, expiration in tuple(_REVOKED_INPUT_LEASES.items()):
        if expiration <= now:
            _REVOKED_INPUT_LEASES.pop(fingerprint, None)


def _revoke_input_lease(lease: Mapping[str, Any] | None) -> None:
    if lease is None:
        return
    _purge_expired_leases()
    expiration = int(lease["expiresAtEpoch"])
    fingerprint = _lease_fingerprint(lease)
    if expiration <= int(time.time()):
        return
    if fingerprint not in _REVOKED_INPUT_LEASES and len(_REVOKED_INPUT_LEASES) >= MAX_REVOKED_INPUT_LEASES:
        raise RuntimeError("lease replay cache is exhausted")
    _REVOKED_INPUT_LEASES[fingerprint] = expiration


def _validate_lease_update(message: object, bindings: Mapping[str, str]) -> dict[str, Any] | None:
    if not isinstance(message, Mapping):
        raise ValueError("lease update must be an object")
    if not bindings["admissionId"]:
        raise ValueError("controller admission is required")
    _require_exact_binding(
        message,
        bindings,
        ("sessionId", "sessionBindingHash", "admissionId", "inputScopeHash"),
    )
    state = message.get("controlLeaseState")
    if state == "AGENT_CONTROLLED_REBOUND":
        return None
    if state != "USER_CONTROLLED":
        raise ValueError("lease update state is invalid")
    grant_id = _required_message_text(message, "grantId", GRANT_RE)
    lease_id = _required_message_text(message, "controlLeaseId", LEASE_RE)
    subject_hash = _required_message_text(message, "subjectHash", HASH_RE)
    lease_readback_hash = _required_message_text(message, "controlLeaseReadbackHash", HASH_RE)
    expires_at = _required_message_epoch(message, "grantExpiresAtEpoch")
    if not grant_id.startswith("desktop-input-") or expires_at <= int(time.time()):
        raise ValueError("lease update is expired or invalid")
    candidate = {
        "grantId": grant_id,
        "leaseId": lease_id,
        "subjectHash": subject_hash,
        "scopeHash": bindings["inputScopeHash"],
        "leaseReadbackHash": lease_readback_hash,
        "expiresAtEpoch": expires_at,
    }
    _purge_expired_leases()
    if _lease_fingerprint(candidate) in _REVOKED_INPUT_LEASES:
        raise ValueError("lease update replays a revoked lease")
    replacing_active_lease = _ACTIVE_INPUT_LEASE is not None and _ACTIVE_INPUT_LEASE != candidate
    required_slots = 1 + (1 if replacing_active_lease else 0)
    if len(_REVOKED_INPUT_LEASES) + required_slots > MAX_REVOKED_INPUT_LEASES:
        raise ValueError("lease replay cache capacity is exhausted")
    return candidate


def _apply_lease_update(message: object, bindings: Mapping[str, str]) -> dict[str, Any]:
    global _ACTIVE_INPUT_LEASE
    candidate = _validate_lease_update(message, bindings)
    if candidate is None:
        _revoke_input_lease(_ACTIVE_INPUT_LEASE)
        _ACTIVE_INPUT_LEASE = None
    else:
        if _ACTIVE_INPUT_LEASE is not None and _ACTIVE_INPUT_LEASE != candidate:
            _revoke_input_lease(_ACTIVE_INPUT_LEASE)
        _ACTIVE_INPUT_LEASE = candidate
    _record_activity()
    return _response(
        status="OBSERVED",
        request_hash="0" * 64,
        kind="LEASE_UPDATE",
        bindings=bindings,
        detail={"active": _ACTIVE_INPUT_LEASE is not None},
    )


def _validate_message(message: object, bindings: Mapping[str, str]) -> dict[str, Any]:
    if not isinstance(message, Mapping):
        raise ValueError("request must be an object")
    operation = message.get("operation", "COMPUTER_USE")
    if operation != "COMPUTER_USE":
        raise ValueError("request operation is invalid")
    if not bindings["admissionId"]:
        raise ValueError("controller admission is required")
    if message.get("schemaVersion") != REQUEST_SCHEMA_VERSION:
        raise ValueError("request schema is invalid")
    request_hash = _required_message_text(message, "requestHash", HASH_RE)
    kind_value = message.get("inputKind")
    if not isinstance(kind_value, str):
        raise ValueError("request kind is invalid")
    kind = kind_value.upper()
    if kind not in ALL_KINDS:
        raise ValueError("request kind is invalid")
    _require_exact_binding(
        message,
        bindings,
        (
            "sessionId",
            "sessionBindingHash",
            "admissionId",
            "runtimeIdentityHash",
            "containerIdentityHash",
            "imageDigest",
            "attemptId",
            "attemptHash",
            "worktreeIdentityHash",
            "observedHeadRevision",
        ),
    )
    grant_id = _required_message_text(message, "grantId", GRANT_RE)
    subject_hash = _required_message_text(message, "subjectHash", HASH_RE)
    scope_hash = _required_message_text(message, "scopeHash", HASH_RE)
    expected_scope = bindings["viewScopeHash"] if kind in VIEW_KINDS else bindings["inputScopeHash"]
    if scope_hash != expected_scope:
        raise ValueError("request scope is invalid")
    if kind in VIEW_KINDS and not grant_id.startswith("desktop-view-"):
        raise ValueError("request grant is invalid")
    if kind in INPUT_KINDS and not grant_id.startswith("desktop-input-"):
        raise ValueError("request grant is invalid")
    action_id = message.get("actionId")
    if not isinstance(action_id, str) or not action_id or len(action_id) > 160:
        raise ValueError("request action is invalid")
    requested_at = _required_message_epoch(message, "requestedAtEpoch")
    expires_at = _required_message_epoch(message, "grantExpiresAtEpoch")
    now = int(time.time())
    if requested_at > now or expires_at <= now or expires_at <= requested_at:
        raise ValueError("request time is invalid")
    safe_payload = _normalise_payload(kind, _payload(message.get("payload")))
    payload_hash = _required_message_text(message, "payloadHash", HASH_RE)
    if payload_hash != _stable_hash({"inputKind": kind, "payload": safe_payload}):
        raise ValueError("request payload is inconsistent")
    control_lease_id: str | None = None
    control_lease_readback_hash: str | None = None
    if kind in INPUT_KINDS:
        control_lease_id = _required_message_text(message, "controlLeaseId", LEASE_RE)
        control_lease_readback_hash = _required_message_text(message, "controlLeaseReadbackHash", HASH_RE)
    elif message.get("controlLeaseId") is not None or message.get("controlLeaseReadbackHash") is not None:
        raise ValueError("view request may not carry input lease authority")
    expected_request_hash = _stable_hash(
        {
            "schemaVersion": REQUEST_SCHEMA_VERSION,
            "sessionId": bindings["sessionId"],
            "sessionBindingHash": bindings["sessionBindingHash"],
            "admissionId": bindings["admissionId"],
            "grantId": grant_id,
            "subjectHash": subject_hash,
            "scopeHash": scope_hash,
            "runtimeIdentityHash": bindings["runtimeIdentityHash"],
            "containerIdentityHash": bindings["containerIdentityHash"],
            "imageDigest": bindings["imageDigest"],
            "attemptId": bindings["attemptId"],
            "attemptHash": bindings["attemptHash"],
            "worktreeIdentityHash": bindings["worktreeIdentityHash"],
            "observedHeadRevision": bindings["observedHeadRevision"],
            "controlLeaseId": control_lease_id,
            "controlLeaseReadbackHash": control_lease_readback_hash,
            "grantExpiresAtEpoch": expires_at,
            "actionId": action_id,
            "inputKind": kind,
            "payloadHash": payload_hash,
            "requestedAtEpoch": requested_at,
        }
    )
    if request_hash != expected_request_hash:
        raise ValueError("request hash is inconsistent")
    return {
        "requestHash": request_hash,
        "inputKind": kind,
        "grantId": grant_id,
        "subjectHash": subject_hash,
        "scopeHash": scope_hash,
        "controlLeaseId": control_lease_id,
        "controlLeaseReadbackHash": control_lease_readback_hash,
        "grantExpiresAtEpoch": expires_at,
        "payload": safe_payload,
    }


def _lease_allows(request: Mapping[str, Any]) -> bool:
    if _ACTIVE_INPUT_LEASE is None:
        return False
    return (
        _ACTIVE_INPUT_LEASE["grantId"] == request["grantId"]
        and _ACTIVE_INPUT_LEASE["leaseId"] == request["controlLeaseId"]
        and _ACTIVE_INPUT_LEASE["subjectHash"] == request["subjectHash"]
        and _ACTIVE_INPUT_LEASE["scopeHash"] == request["scopeHash"]
        and _ACTIVE_INPUT_LEASE["leaseReadbackHash"] == request["controlLeaseReadbackHash"]
        and _ACTIVE_INPUT_LEASE["expiresAtEpoch"] == request["grantExpiresAtEpoch"]
        and int(time.time()) < _ACTIVE_INPUT_LEASE["expiresAtEpoch"]
    )


def _reserve_effect_request(request_hash: str, *, expires_at_epoch: int) -> None:
    now = int(time.time())
    for candidate, expiration in tuple(_CONSUMED_EFFECT_REQUESTS.items()):
        if expiration <= now:
            _CONSUMED_EFFECT_REQUESTS.pop(candidate, None)
    if request_hash in _CONSUMED_EFFECT_REQUESTS:
        raise ValueError("effect request was already consumed")
    if expires_at_epoch <= now:
        raise ValueError("effect request is expired")
    if len(_CONSUMED_EFFECT_REQUESTS) >= MAX_CONSUMED_EFFECT_REQUESTS:
        raise ValueError("effect replay cache is exhausted")
    _CONSUMED_EFFECT_REQUESTS[request_hash] = expires_at_epoch


def _record_activity() -> None:
    ACTIVITY_PATH.parent.mkdir(mode=0o711, parents=True, exist_ok=True)
    ACTIVITY_PATH.touch(exist_ok=True)
    os.chmod(ACTIVITY_PATH, 0o600)


def _handle(message: object, bindings: Mapping[str, str]) -> dict[str, Any]:
    request_hash = "0" * 64
    kind = "UNKNOWN"
    try:
        if isinstance(message, Mapping) and message.get("operation") == "ADMISSION_BIND":
            if not isinstance(bindings, dict):
                raise ValueError("admission bind requires mutable bindings")
            return _apply_admission_bind(message, bindings)
        if isinstance(message, Mapping) and message.get("operation") == "LEASE_UPDATE":
            return _apply_lease_update(message, bindings)
        request = _validate_message(message, bindings)
        request_hash = request["requestHash"]
        kind = request["inputKind"]
        if kind in VIEW_KINDS:
            detail = _observe(kind, request["payload"])
            _record_activity()
            return _response(
                status="OBSERVED",
                request_hash=request_hash,
                kind=kind,
                bindings=bindings,
                detail=detail,
                request=request,
            )
        if not _lease_allows(request):
            raise ValueError("input lease is not current")
        _reserve_effect_request(request_hash, expires_at_epoch=request["grantExpiresAtEpoch"])
        _record_activity()
        detail = _input(kind, request["payload"])
        _record_activity()
        return _response(
            status="SENT",
            request_hash=request_hash,
            kind=kind,
            bindings=bindings,
            detail=detail,
            request=request,
        )
    except (ValueError, RuntimeError, subprocess.SubprocessError, OSError, TypeError):
        return _response(
            status="BLOCKED",
            request_hash=request_hash,
            kind=kind,
            bindings=bindings,
            detail={},
            error_code="BOUNDED_OPERATION_REJECTED",
        )


def _peer_uid(connection: socket.socket) -> int | None:
    try:
        credentials = connection.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
        )
        _, uid, _ = struct.unpack("3i", credentials)
        return uid
    except (AttributeError, OSError, struct.error):
        return None


def _serve_connection(connection: socket.socket, bindings: Mapping[str, str]) -> None:
    connection.settimeout(5)
    try:
        raw = connection.recv(MAX_MESSAGE_BYTES + 1)
        if len(raw) > MAX_MESSAGE_BYTES:
            response = _response(
                status="BLOCKED",
                request_hash="0" * 64,
                kind="UNKNOWN",
                bindings=bindings,
                detail={},
                error_code="MESSAGE_TOO_LARGE",
            )
        elif _peer_uid(connection) != int(bindings["controlClientUid"]):
            response = _response(
                status="BLOCKED",
                request_hash="0" * 64,
                kind="UNKNOWN",
                bindings=bindings,
                detail={},
                error_code="UNAUTHORIZED_PEER",
            )
        else:
            response = _handle(json.loads(raw.decode("utf-8")), bindings)
    except (UnicodeDecodeError, json.JSONDecodeError, OSError):
        response = _response(
            status="BLOCKED",
            request_hash="0" * 64,
            kind="UNKNOWN",
            bindings=bindings,
            detail={},
            error_code="INVALID_ENCODING",
        )
    connection.sendall(json.dumps(response, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def main() -> None:
    bindings = _bindings()
    SOCKET_PATH.parent.mkdir(mode=0o711, parents=True, exist_ok=True)
    os.chmod(SOCKET_PATH.parent, 0o711)
    try:
        SOCKET_PATH.unlink()
    except FileNotFoundError:
        pass
    _record_activity()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(SOCKET_PATH))
        os.chmod(SOCKET_PATH, 0o666)
        server.listen(16)
        while True:
            connection, _ = server.accept()
            with connection:
                _serve_connection(connection, bindings)


if __name__ == "__main__":
    main()
