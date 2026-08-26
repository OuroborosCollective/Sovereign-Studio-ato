"""Authenticated live RFB stream bridge for the monitor-first desktop.

The browser receives a short-lived signed ticket over an authenticated HTTP
route. The WebSocket then proxies the real RFB byte stream from the isolated
worker. The worker itself is VNC view-only; keyboard and pointer authority stay
on the existing takeover/input lease path.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import socket
import threading
import time
from typing import Any

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_JOB_RE = re.compile(r"^job-[a-z0-9-]{6,63}$")


class DesktopStreamError(ValueError):
    pass


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret() -> bytes:
    raw = str(os.getenv("SOVEREIGN_DESKTOP_STREAM_TICKET_SECRET") or os.getenv("JWT_SECRET") or "").encode("utf-8")
    if len(raw) < 32:
        raise DesktopStreamError("desktop stream ticket secret is unavailable")
    return raw


def issue_stream_ticket(*, user_id: str, job_id: str, activation_id: str, session_binding_hash: str, ttl_seconds: int = 90) -> dict[str, Any]:
    if not user_id or len(user_id) > 160:
        raise DesktopStreamError("desktop stream user binding is invalid")
    if not _JOB_RE.fullmatch(job_id):
        raise DesktopStreamError("desktop stream job binding is invalid")
    if not _HASH_RE.fullmatch(activation_id) or not _HASH_RE.fullmatch(session_binding_hash):
        raise DesktopStreamError("desktop stream activation binding is invalid")
    ttl = max(15, min(int(ttl_seconds), 120))
    payload = {
        "v": 1,
        "uid": user_id,
        "job": job_id,
        "activation": activation_id,
        "session": session_binding_hash,
        "exp": int(time.time()) + ttl,
    }
    body = _b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return {"ticket": f"{body}.{signature}", "expiresAtEpoch": payload["exp"]}


def verify_stream_ticket(ticket: str, *, job_id: str) -> dict[str, Any]:
    try:
        body, signature = ticket.split(".", 1)
    except ValueError as exc:
        raise DesktopStreamError("desktop stream ticket framing is invalid") from exc
    expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise DesktopStreamError("desktop stream ticket signature is invalid")
    try:
        payload = json.loads(_b64decode(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DesktopStreamError("desktop stream ticket payload is invalid") from exc
    if not isinstance(payload, dict) or payload.get("v") != 1 or payload.get("job") != job_id:
        raise DesktopStreamError("desktop stream ticket binding is invalid")
    if not isinstance(payload.get("exp"), int) or payload["exp"] < int(time.time()):
        raise DesktopStreamError("desktop stream ticket expired")
    if not _HASH_RE.fullmatch(str(payload.get("activation") or "")) or not _HASH_RE.fullmatch(str(payload.get("session") or "")):
        raise DesktopStreamError("desktop stream ticket identity is invalid")
    return payload


def desktop_worker_host(session_binding_hash: str) -> str:
    if not _HASH_RE.fullmatch(session_binding_hash):
        raise DesktopStreamError("desktop stream session binding is invalid")
    return f"sovereign-desktop-{session_binding_hash[:20]}"


def proxy_rfb_websocket(ws: Any, *, session_binding_hash: str, port: int = 5900) -> None:
    """Proxy one binary RFB session. x11vnc is view-only by construction."""
    target = socket.create_connection((desktop_worker_host(session_binding_hash), int(port)), timeout=8)
    target.settimeout(1.0)
    stopped = threading.Event()

    def downstream() -> None:
        try:
            while not stopped.is_set():
                try:
                    chunk = target.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                ws.send(chunk)
        except Exception:
            pass
        finally:
            stopped.set()

    reader = threading.Thread(target=downstream, name="sovereign-rfb-downstream", daemon=True)
    reader.start()
    try:
        while not stopped.is_set():
            message = ws.receive(timeout=1)
            if message is None:
                break
            if isinstance(message, str):
                message = message.encode("latin-1")
            if isinstance(message, (bytes, bytearray)) and message:
                target.sendall(bytes(message))
    except Exception:
        pass
    finally:
        stopped.set()
        try:
            target.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        target.close()
        reader.join(timeout=2)
