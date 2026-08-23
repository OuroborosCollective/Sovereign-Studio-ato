#!/usr/bin/env python3
"""Authenticated, view-only private gateway for the desktop noVNC stream."""

from __future__ import annotations

import base64
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import select
import socket
import threading
import time
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit

_HASH_LENGTH = 64
_REVISION_LENGTH = 40
_TOKEN_MAX_BYTES = 8_192
_NONCE_CACHE_MAX = 4_096
_COOKIE_NAME = "desktop_view_session"
_STATIC_ROOT = Path("/usr/share/novnc").resolve()
_SESSIONS: dict[str, int] = {}
_CONSUMED_NONCES: dict[str, int] = {}
_NONCE_LOCK = threading.Lock()


def _now() -> int:
    return int(time.time())


def _b64decode(value: str) -> bytes:
    if not value or len(value) > _TOKEN_MAX_BYTES:
        raise ValueError("invalid view capability")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _required_hash(value: object) -> str:
    result = str(value or "").strip().lower()
    if len(result) != _HASH_LENGTH or any(character not in "0123456789abcdef" for character in result):
        raise RuntimeError("invalid gateway binding")
    return result


def _required_revision(value: object) -> str:
    result = str(value or "").strip().lower()
    if len(result) != _REVISION_LENGTH or any(character not in "0123456789abcdef" for character in result):
        raise RuntimeError("invalid gateway binding")
    return result


def _required_identifier(value: object, prefix: str) -> str:
    result = str(value or "").strip().lower()
    suffix = result.removeprefix(prefix)
    if not result.startswith(prefix) or len(suffix) != 24 or any(character not in "0123456789abcdef" for character in suffix):
        raise RuntimeError("invalid gateway binding")
    return result


def _required_session_id(value: object) -> str:
    result = str(value or "").strip().lower()
    if not result or len(result) > 160 or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._:-" for character in result):
        raise RuntimeError("invalid gateway binding")
    return result


def _read_secret(path: Path) -> bytes:
    try:
        value = path.read_bytes().strip()
    except OSError as exc:
        raise RuntimeError("gateway signing key is unavailable") from exc
    if len(value) < 32 or len(value) > 512:
        raise RuntimeError("gateway signing key is invalid")
    return value


def _config() -> dict[str, Any]:
    key_file = Path(os.environ.get("DESKTOP_VIEW_GATEWAY_KEY_FILE", "")).resolve()
    if not key_file.is_file():
        raise RuntimeError("gateway signing key is unavailable")
    port = int(os.environ.get("DESKTOP_VIEW_GATEWAY_PORT", "8080"))
    if port < 1024 or port > 65535:
        raise RuntimeError("gateway port is invalid")
    upstream_port = int(os.environ.get("DESKTOP_VIEW_UPSTREAM_PORT", "6080"))
    if upstream_port < 1024 or upstream_port > 65535:
        raise RuntimeError("gateway upstream port is invalid")
    upstream_host = os.environ.get("DESKTOP_VIEW_UPSTREAM_HOST", "").strip().lower()
    if not upstream_host or len(upstream_host) > 253 or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for character in upstream_host):
        raise RuntimeError("gateway upstream is invalid")
    return {
        "key": _read_secret(key_file),
        "bindHost": os.environ.get("DESKTOP_VIEW_GATEWAY_BIND_HOST", "0.0.0.0"),
        "port": port,
        "upstreamHost": upstream_host,
        "upstreamPort": upstream_port,
        "sessionId": _required_session_id(os.environ.get("DESKTOP_SESSION_ID")),
        "sessionBindingHash": _required_hash(os.environ.get("DESKTOP_SESSION_BINDING_HASH")),
        "admissionId": _required_identifier(os.environ.get("DESKTOP_ADMISSION_ID"), "desktop-admission-"),
        "viewScopeHash": _required_hash(os.environ.get("DESKTOP_VIEW_SCOPE_HASH")),
        "runtimeIdentityHash": _required_hash(os.environ.get("DESKTOP_RUNTIME_IDENTITY_HASH")),
        "containerIdentityHash": _required_hash(os.environ.get("DESKTOP_CONTAINER_IDENTITY_HASH")),
        "gatewayRuntimeIdentityHash": _required_hash(os.environ.get("DESKTOP_VIEW_GATEWAY_RUNTIME_IDENTITY_HASH")),
        "gatewayContainerIdentityHash": _required_hash(os.environ.get("DESKTOP_VIEW_GATEWAY_CONTAINER_IDENTITY_HASH")),
        "gatewayImageDigest": "sha256:" + _required_hash(str(os.environ.get("DESKTOP_GATEWAY_IMAGE_DIGEST", "")).removeprefix("sha256:")),
        "workerBackplaneNetworkIdentityHash": _required_hash(os.environ.get("DESKTOP_WORKER_BACKPLANE_NETWORK_IDENTITY_HASH")),
        "viewClientNetworkIdentityHash": _required_hash(os.environ.get("DESKTOP_VIEW_CLIENT_NETWORK_IDENTITY_HASH")),
        "attemptId": _required_identifier(os.environ.get("DESKTOP_ATTEMPT_ID"), "attempt-"),
        "attemptHash": _required_hash(os.environ.get("DESKTOP_ATTEMPT_HASH")),
        "worktreeIdentityHash": _required_hash(os.environ.get("DESKTOP_WORKTREE_IDENTITY_HASH")),
        "observedHeadRevision": _required_revision(os.environ.get("DESKTOP_HEAD_REVISION")),
    }


def _verify_token(token: str, config: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        payload_text, signature_text = token.split(".", 1)
        payload_bytes = _b64decode(payload_text)
        signature = _b64decode(signature_text)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid view capability") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("invalid view capability")
    expected_signature = hmac.new(config["key"], payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("invalid view capability")
    expected = {
        "sessionId": config["sessionId"],
        "sessionBindingHash": config["sessionBindingHash"],
        "admissionId": config["admissionId"],
        "viewScopeHash": config["viewScopeHash"],
        "runtimeIdentityHash": config["runtimeIdentityHash"],
        "containerIdentityHash": config["containerIdentityHash"],
        "gatewayRuntimeIdentityHash": config["gatewayRuntimeIdentityHash"],
        "gatewayContainerIdentityHash": config["gatewayContainerIdentityHash"],
        "gatewayImageDigest": config["gatewayImageDigest"],
        "workerBackplaneNetworkIdentityHash": config["workerBackplaneNetworkIdentityHash"],
        "viewClientNetworkIdentityHash": config["viewClientNetworkIdentityHash"],
        "attemptId": config["attemptId"],
        "attemptHash": config["attemptHash"],
        "worktreeIdentityHash": config["worktreeIdentityHash"],
        "observedHeadRevision": config["observedHeadRevision"],
    }
    if any(payload.get(field) != value for field, value in expected.items()):
        raise ValueError("view capability does not match gateway binding")
    grant_id = payload.get("grantId")
    subject_hash = payload.get("subjectHash")
    nonce = payload.get("nonce")
    issued = payload.get("issuedAtEpoch")
    expires = payload.get("expiresAtEpoch")
    if (
        not isinstance(grant_id, str)
        or not grant_id.startswith("desktop-view-")
        or len(grant_id) != len("desktop-view-") + 24
        or any(character not in "0123456789abcdef" for character in grant_id[len("desktop-view-"):])
        or not isinstance(subject_hash, str)
        or _required_hash(subject_hash) != subject_hash
        or not isinstance(nonce, str)
        or not nonce
        or len(nonce) > 128
        or not isinstance(issued, int)
        or not isinstance(expires, int)
        or issued > _now()
        or expires <= _now()
        or expires - issued > 900
    ):
        raise ValueError("view capability is invalid")
    return payload


def _consume_nonce(payload: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    """Consume one signed view nonce once, bounded by its immutable capability realm."""
    nonce = payload.get("nonce")
    grant_id = payload.get("grantId")
    subject_hash = payload.get("subjectHash")
    expiration = payload.get("expiresAtEpoch")
    if not isinstance(nonce, str) or not isinstance(grant_id, str) or not isinstance(subject_hash, str) or not isinstance(expiration, int):
        raise ValueError("invalid view capability")
    fingerprint = hashlib.sha256(
        _canonical(
            {
                "sessionId": config["sessionId"],
                "sessionBindingHash": config["sessionBindingHash"],
                "admissionId": config["admissionId"],
                "grantId": grant_id,
                "subjectHash": subject_hash,
                "nonce": nonce,
            }
        )
    ).hexdigest()
    with _NONCE_LOCK:
        now = _now()
        for candidate, candidate_expiration in tuple(_CONSUMED_NONCES.items()):
            if candidate_expiration <= now:
                _CONSUMED_NONCES.pop(candidate, None)
        if fingerprint in _CONSUMED_NONCES:
            raise ValueError("view capability was already consumed")
        if len(_CONSUMED_NONCES) >= _NONCE_CACHE_MAX:
            raise ValueError("view capability cache is full")
        _CONSUMED_NONCES[fingerprint] = expiration


def _make_cookie(expiration: int) -> str:
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = expiration
    for candidate, candidate_expiration in tuple(_SESSIONS.items()):
        if candidate_expiration <= _now():
            _SESSIONS.pop(candidate, None)
    return token


def _cookie_expiration(header: str | None) -> int | None:
    if not header:
        return None
    try:
        cookie = SimpleCookie()
        cookie.load(header)
        value = cookie.get(_COOKIE_NAME)
        if value is None:
            return None
        expiration = _SESSIONS.get(value.value)
        if expiration is None or expiration <= _now():
            return None
        return expiration
    except (KeyError, ValueError):
        return None


class ViewGatewayHandler(BaseHTTPRequestHandler):
    server_version = "SovereignDesktopViewGateway/1"
    protocol_version = "HTTP/1.1"

    @property
    def config(self) -> Mapping[str, Any]:
        return self.server.gateway_config  # type: ignore[attr-defined]

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send(self, status: HTTPStatus, *, body: bytes = b"", headers: Mapping[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        if headers:
            for name, value in headers.items():
                self.send_header(name, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _authorize(self) -> int | None:
        parsed = urlsplit(self.path)
        token_values = parse_qs(parsed.query, keep_blank_values=False).get("view_token", [])
        if token_values:
            if len(token_values) != 1:
                return None
            try:
                claims = _verify_token(token_values[0], self.config)
                _consume_nonce(claims, self.config)
            except ValueError:
                return None
            return claims["expiresAtEpoch"]
        return _cookie_expiration(self.headers.get("Cookie"))

    def _redirect_with_cookie(self, expiration: int) -> None:
        token = _make_cookie(expiration)
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/vnc.html")
        self.send_header(
            "Set-Cookie",
            f"{_COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max(1, expiration - _now())}",
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _static_path(self, path: str) -> Path | None:
        requested = "vnc.html" if path in {"", "/"} else path.lstrip("/")
        if not requested or "\\" in requested:
            return None
        candidate = (_STATIC_ROOT / requested).resolve()
        try:
            candidate.relative_to(_STATIC_ROOT)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None

    def _serve_static(self, path: str, expiration: int) -> None:
        if _now() >= expiration:
            self._send(HTTPStatus.UNAUTHORIZED)
            return
        candidate = self._static_path(path)
        if candidate is None:
            self._send(HTTPStatus.NOT_FOUND)
            return
        try:
            payload = candidate.read_bytes()
        except OSError:
            self._send(HTTPStatus.NOT_FOUND)
            return
        content_type = "text/plain; charset=utf-8"
        if candidate.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif candidate.suffix == ".js":
            content_type = "application/javascript"
        elif candidate.suffix == ".css":
            content_type = "text/css"
        elif candidate.suffix == ".svg":
            content_type = "image/svg+xml"
        elif candidate.suffix == ".png":
            content_type = "image/png"
        self._send(HTTPStatus.OK, body=payload, headers={"Content-Type": content_type})

    def _proxy_websocket(self, expiration: int) -> None:
        if _now() >= expiration:
            self._send(HTTPStatus.UNAUTHORIZED)
            return
        if self.headers.get("Upgrade", "").lower() != "websocket":
            self._send(HTTPStatus.BAD_REQUEST)
            return
        key = self.headers.get("Sec-WebSocket-Key", "")
        version = self.headers.get("Sec-WebSocket-Version", "")
        if not key or version != "13":
            self._send(HTTPStatus.BAD_REQUEST)
            return
        try:
            upstream = socket.create_connection(
                (self.config["upstreamHost"], self.config["upstreamPort"]), timeout=5
            )
        except OSError:
            self._send(HTTPStatus.BAD_GATEWAY)
            return
        try:
            lines = [
                "GET /websockify HTTP/1.1",
                f"Host: {self.config['upstreamHost']}:{self.config['upstreamPort']}",
                "Upgrade: websocket",
                "Connection: Upgrade",
                f"Sec-WebSocket-Key: {key}",
                "Sec-WebSocket-Version: 13",
            ]
            protocol = self.headers.get("Sec-WebSocket-Protocol")
            if protocol:
                lines.append(f"Sec-WebSocket-Protocol: {protocol}")
            upstream.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
            response = b""
            while b"\r\n\r\n" not in response and len(response) < 16_384:
                chunk = upstream.recv(4_096)
                if not chunk:
                    raise OSError("upstream closed")
                response += chunk
            header, remainder = response.split(b"\r\n\r\n", 1)
            status_line = header.split(b"\r\n", 1)[0]
            if not status_line.startswith(b"HTTP/1.1 101") and not status_line.startswith(b"HTTP/1.0 101"):
                self._send(HTTPStatus.BAD_GATEWAY)
                return
            self.connection.sendall(header + b"\r\n\r\n" + remainder)
            self.connection.setblocking(False)
            upstream.setblocking(False)
            while _now() < expiration:
                readable, _, _ = select.select((self.connection, upstream), (), (), 1)
                if not readable:
                    continue
                for source in readable:
                    chunk = source.recv(65_536)
                    if not chunk:
                        return
                    (upstream if source is self.connection else self.connection).sendall(chunk)
        except (OSError, ValueError):
            return
        finally:
            upstream.close()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/healthz":
            self._send(HTTPStatus.NO_CONTENT)
            return
        expiration = self._authorize()
        if expiration is None:
            self._send(HTTPStatus.UNAUTHORIZED)
            return
        if parse_qs(parsed.query, keep_blank_values=False).get("view_token"):
            self._redirect_with_cookie(expiration)
            return
        if parsed.path == "/websockify":
            self._proxy_websocket(expiration)
            return
        self._serve_static(parsed.path, expiration)

    def do_POST(self) -> None:
        self._send(HTTPStatus.METHOD_NOT_ALLOWED)

    def do_CONNECT(self) -> None:
        self._send(HTTPStatus.METHOD_NOT_ALLOWED)


def main() -> None:
    config = _config()
    server = ThreadingHTTPServer((config["bindHost"], config["port"]), ViewGatewayHandler)
    server.gateway_config = config  # type: ignore[attr-defined]
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
