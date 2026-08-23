"""Private, bounded HTTP bridge for one isolated desktop container.

This process deliberately exposes neither shell execution nor arbitrary process
control.  It is reachable only on the Docker-internal desktop network; each
view or controller-input operation additionally requires its distinct scope.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import tempfile
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

MAX_BODY_BYTES = 8_192
MAX_TEXT_BYTES = 2_048
MAX_FRAME_BYTES = 12 * 1024 * 1024
MAX_COORDINATE = 7_680
_ACTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
_WINDOW_ID_RE = re.compile(r"^[0-9]{1,12}$")
_KEY_RE = re.compile(r"^[A-Za-z0-9_+.-]{1,80}$")
_ALLOWED_ACTIONS = frozenset({"pointer_move", "click", "type", "keypress", "scroll", "window_focus"})


def _scope_from_file(name: str) -> str:
    path = Path(os.environ.get(name, ""))
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"{name} is unavailable")
    value = path.read_text("utf-8").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,160}", value):
        raise RuntimeError(f"{name} is invalid")
    return value


VIEW_SCOPE = _scope_from_file("DESKTOP_VIEW_SCOPE_FILE")
INPUT_SCOPE = _scope_from_file("DESKTOP_INPUT_SCOPE_FILE")
RUNTIME_IDENTITY_HASH = os.environ.get("DESKTOP_RUNTIME_IDENTITY_HASH", "").strip().lower()
if not re.fullmatch(r"[0-9a-f]{64}", RUNTIME_IDENTITY_HASH):
    raise RuntimeError("DESKTOP_RUNTIME_IDENTITY_HASH is invalid")
WALL_TIME_SECONDS = max(60, min(int(os.environ.get("DESKTOP_WALL_TIME_SECONDS", "3600")), 86_400))
IDLE_TIMEOUT_SECONDS = max(60, min(int(os.environ.get("DESKTOP_IDLE_TIMEOUT_SECONDS", "900")), WALL_TIME_SECONDS))


def _run(argv: list[str], *, timeout: float = 3.0) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout, check=False)


def _bounded_int(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} is outside bounded range")
    return value


def _action_id(value: Any) -> str:
    result = str(value or "").strip()
    if not _ACTION_ID_RE.fullmatch(result):
        raise ValueError("actionId is invalid")
    return result


def _safe_command(payload: dict[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
    action = str(payload.get("action") or "").strip().lower()
    if action not in _ALLOWED_ACTIONS:
        raise ValueError("desktop action is forbidden")
    if action == "pointer_move":
        x = _bounded_int(payload.get("x"), "x", minimum=0, maximum=MAX_COORDINATE)
        y = _bounded_int(payload.get("y"), "y", minimum=0, maximum=MAX_COORDINATE)
        return action, ["xdotool", "mousemove", "--sync", str(x), str(y)], {"x": x, "y": y}
    if action == "click":
        x = _bounded_int(payload.get("x"), "x", minimum=0, maximum=MAX_COORDINATE)
        y = _bounded_int(payload.get("y"), "y", minimum=0, maximum=MAX_COORDINATE)
        button = str(payload.get("button") or "left").strip().lower()
        button_map = {"left": "1", "middle": "2", "right": "3"}
        if button not in button_map:
            raise ValueError("click button is forbidden")
        return action, ["xdotool", "mousemove", "--sync", str(x), str(y), "click", button_map[button]], {"x": x, "y": y, "button": button}
    if action == "type":
        text = payload.get("text")
        if not isinstance(text, str) or not text or len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError("type text is outside bounded range")
        return action, ["xdotool", "type", "--clearmodifiers", "--delay", "1", "--", text], {"textBytes": len(text.encode("utf-8")), "textHash": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    if action == "keypress":
        key = str(payload.get("key") or "").strip()
        if not _KEY_RE.fullmatch(key):
            raise ValueError("keypress key is forbidden")
        return action, ["xdotool", "key", "--clearmodifiers", "--", key], {"key": key}
    if action == "scroll":
        amount = _bounded_int(payload.get("amount"), "amount", minimum=-20, maximum=20)
        if amount == 0:
            raise ValueError("scroll amount may not be zero")
        button = "4" if amount > 0 else "5"
        return action, ["xdotool", "click", "--repeat", str(abs(amount)), button], {"amount": amount}
    window_id = str(payload.get("windowId") or "").strip()
    if not _WINDOW_ID_RE.fullmatch(window_id):
        raise ValueError("windowId is forbidden")
    return action, ["xdotool", "windowactivate", "--sync", window_id], {"windowId": window_id}


class DesktopHandler(BaseHTTPRequestHandler):
    server_version = "SovereignDesktopWorker/1"
    protocol_version = "HTTP/1.1"

    @property
    def worker(self) -> "DesktopServer":
        return self.server  # type: ignore[return-value]

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _scope(self, expected: str) -> bool:
        supplied = self.headers.get("X-Sovereign-Desktop-Scope", "")
        if not hmac.compare_digest(supplied, expected):
            self._send_json(HTTPStatus.FORBIDDEN, {"status": "BLOCKED", "reason": "scope"})
            return False
        return True

    def _read_json(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = MAX_BODY_BYTES + 1
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"status": "BLOCKED", "reason": "body"})
            return None
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"status": "BLOCKED", "reason": "json"})
            return None
        if not isinstance(value, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"status": "BLOCKED", "reason": "json"})
            return None
        return value

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "OBSERVED", "runtimeIdentityHash": RUNTIME_IDENTITY_HASH, "authoritative": False})
            return
        if self.path not in {"/frame", "/windows", "/viewport"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"status": "BLOCKED"})
            return
        if not self._scope(VIEW_SCOPE):
            return
        self.worker.last_activity = time.monotonic()
        if self.path == "/frame":
            self._frame()
        elif self.path == "/windows":
            self._windows()
        else:
            self._viewport()

    def do_POST(self) -> None:
        if self.path != "/input":
            self._send_json(HTTPStatus.NOT_FOUND, {"status": "BLOCKED"})
            return
        if not self._scope(INPUT_SCOPE):
            return
        payload = self._read_json()
        if payload is None:
            return
        try:
            action_id = _action_id(payload.get("actionId"))
            action, argv, normalized = _safe_command(payload)
            request_hash = hashlib.sha256(
                json.dumps({"actionId": action_id, "action": action, "arguments": normalized}, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            result = _run(argv)
            status = "SENT" if result.returncode == 0 else "BLOCKED"
            self.worker.last_activity = time.monotonic()
            self._send_json(
                HTTPStatus.OK if status == "SENT" else HTTPStatus.CONFLICT,
                {
                    "status": status,
                    "actionId": action_id,
                    "inputKind": action.upper(),
                    "requestHash": request_hash,
                    "runtimeIdentityHash": RUNTIME_IDENTITY_HASH,
                    "targetEffectVerified": False,
                    "authoritative": False,
                },
            )
        except (ValueError, subprocess.TimeoutExpired):
            self._send_json(HTTPStatus.BAD_REQUEST, {"status": "BLOCKED", "reason": "action"})

    def _frame(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="desktop-frame-", suffix=".png", dir="/tmp", delete=False) as handle:
            path = Path(handle.name)
        try:
            result = _run(["scrot", "--overwrite", str(path)], timeout=5.0)
            if result.returncode != 0 or not path.is_file() or path.stat().st_size > MAX_FRAME_BYTES:
                self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "UNKNOWN", "reason": "frame"})
                return
            payload = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Sovereign-Observation", "OBSERVED")
            self.send_header("X-Sovereign-Frame-Hash", hashlib.sha256(payload).hexdigest())
            self.end_headers()
            self.wfile.write(payload)
        except (OSError, subprocess.TimeoutExpired):
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "UNKNOWN", "reason": "frame"})
        finally:
            path.unlink(missing_ok=True)

    def _windows(self) -> None:
        try:
            result = _run(["xdotool", "search", "--onlyvisible", "--name", "."], timeout=3.0)
            identifiers = [line.strip() for line in result.stdout.decode("utf-8", "replace").splitlines() if _WINDOW_ID_RE.fullmatch(line.strip())][:32]
            windows = []
            for identifier in identifiers:
                title = _run(["xdotool", "getwindowname", identifier], timeout=1.0).stdout.decode("utf-8", "replace").strip()[:256]
                windows.append({"windowId": identifier, "title": title})
            self._send_json(HTTPStatus.OK, {"status": "OBSERVED", "windows": windows, "authoritative": False})
        except subprocess.TimeoutExpired:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "UNKNOWN", "reason": "windows"})

    def _viewport(self) -> None:
        try:
            result = _run(["xdotool", "getdisplaygeometry"], timeout=1.0)
            parts = result.stdout.decode("utf-8", "replace").split()
            if result.returncode or len(parts) != 2:
                raise ValueError("geometry")
            width, height = (_bounded_int(int(value), "viewport", minimum=1, maximum=MAX_COORDINATE) for value in parts)
            self._send_json(HTTPStatus.OK, {"status": "OBSERVED", "width": width, "height": height, "authoritative": False})
        except (ValueError, subprocess.TimeoutExpired):
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "UNKNOWN", "reason": "viewport"})


class DesktopServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address, DesktopHandler)
        self.started_at = time.monotonic()
        self.last_activity = self.started_at


def main() -> None:
    server = DesktopServer(("0.0.0.0", int(os.environ.get("DESKTOP_WORKER_PORT", "8765"))))
    server.timeout = 1.0
    try:
        while True:
            now = time.monotonic()
            if now - server.started_at >= WALL_TIME_SECONDS or now - server.last_activity >= IDLE_TIMEOUT_SECONDS:
                return
            server.handle_request()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
