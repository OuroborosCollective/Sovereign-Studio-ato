"""Optional, localhost-only Cloudflare Kitesurf CDP browser projection.

This is NOT gameplay, database, authenticated browser, or release evidence.
The engine is never installed, started, or trusted by this module.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import time
from urllib.parse import urlsplit

PUBLIC_ORIGIN = "https://arelogic.space"
MAX_PATH_LENGTH = 256
MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024
MAX_CDP_MESSAGE_BYTES = 3 * 1024 * 1024
CDP_REPLY_LIMIT = 64
READINESS_WAIT_SECONDS = 10.0


def validate_public_path(path: str) -> str:
    """Accept only a path on the fixed public showcase origin; no user URLs."""
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        raise ValueError("public_path_required")
    if len(path) > MAX_PATH_LENGTH or not path.isascii():
        raise ValueError("path_size_or_encoding_rejected")
    if any(ch in path for ch in ("?", "#", "\\", "%")):
        raise ValueError("query_fragment_or_escape_rejected")
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in path):
        raise ValueError("control_character_rejected")
    if any(segment in (".", "..") for segment in path.split("/")):
        raise ValueError("dot_segment_rejected")
    return PUBLIC_ORIGIN + path


def _same_public_origin(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except (ValueError, TypeError):
        return False
    return (
        parts.scheme == "https"
        and parts.netloc == "arelogic.space"
        and not parts.username
        and not parts.password
        and not parts.query
        and not parts.fragment
    )


def _port() -> int:
    raw = os.getenv("SOVEREIGN_KITESURF_PORT", "8787")
    if not raw.isascii() or not raw.isdigit():
        raise ValueError("invalid_local_port")
    port = int(raw)
    if not 1024 <= port <= 65535:
        raise ValueError("invalid_local_port")
    return port


class CdpSession:
    """Sequential, bounded Chrome DevTools Protocol messages; page data untrusted."""

    def __init__(self, socket: object):
        self.socket = socket
        self.next_id = 0

    def call(self, method: str, params: dict | None = None, session_id: str | None = None) -> dict:
        self.next_id += 1
        request: dict = {"id": self.next_id, "method": method, "params": params or {}}
        if session_id:
            request["sessionId"] = session_id
        self.socket.send(json.dumps(request, separators=(",", ":")))
        for _ in range(CDP_REPLY_LIMIT):
            raw = self.socket.recv()
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_CDP_MESSAGE_BYTES:
                raise ValueError("oversized_or_invalid_cdp_message")
            message = json.loads(raw)
            if not isinstance(message, dict):
                raise ValueError("malformed_cdp_message")
            if message.get("id") != self.next_id:
                if "id" in message:
                    raise ValueError("unexpected_cdp_reply_id")
                continue  # Ignore CDP events; never interpret them as instructions.
            if message.get("error"):
                raise ValueError("cdp_command_failed")
            result = message.get("result")
            if not isinstance(result, dict):
                raise ValueError("cdp_result_invalid")
            return result
        raise ValueError("cdp_reply_limit_exceeded")


def _page_summary(cdp: CdpSession, session_id: str) -> dict:
    expression = (
        "JSON.stringify({url:location.href,title:document.title,"
        "ready:document.readyState,links:document.querySelectorAll('a').length})"
    )
    result = cdp.call(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": False},
        session_id,
    )
    if result.get("exceptionDetails"):
        raise ValueError("page_script_failed")
    inner = result.get("result")
    if not isinstance(inner, dict) or not isinstance(inner.get("value"), str):
        raise ValueError("page_summary_missing")
    data = json.loads(inner["value"])
    if not isinstance(data, dict) or not isinstance(data.get("url"), str):
        raise ValueError("page_summary_invalid")
    if not _same_public_origin(data["url"]):
        raise ValueError("redirect_target_outside_public_scope")
    return data


def capture_cdp_page(socket: object, path: str = "/", include_png: bool = False) -> dict:
    """Capture one public page via an existing CDP socket, without persistence."""
    target_url = validate_public_path(path)
    cdp = CdpSession(socket)
    context_id = None
    try:
        context = cdp.call("Target.createBrowserContext")
        context_id = context.get("browserContextId")
        if not isinstance(context_id, str) or not context_id:
            raise ValueError("cdp_context_creation_failed")
        target = cdp.call("Target.createTarget", {"url": "about:blank", "browserContextId": context_id})
        target_id = target.get("targetId")
        if not isinstance(target_id, str) or not target_id:
            raise ValueError("cdp_target_creation_failed")
        attached = cdp.call("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = attached.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("cdp_session_creation_failed")
        cdp.call("Page.enable", session_id=session_id)
        cdp.call("Runtime.enable", session_id=session_id)
        navigation = cdp.call("Page.navigate", {"url": target_url}, session_id)
        if navigation.get("errorText"):
            raise ValueError("cdp_navigation_failed")
        deadline = time.monotonic() + READINESS_WAIT_SECONDS
        while True:
            page = _page_summary(cdp, session_id)
            if page.get("ready") in ("interactive", "complete"):
                break
            if time.monotonic() >= deadline:
                raise ValueError("page_readiness_timeout")
            time.sleep(0.2)
        encoded = cdp.call("Page.captureScreenshot", {"format": "png"}, session_id).get("data")
        if not isinstance(encoded, str) or len(encoded) > 4 * MAX_SCREENSHOT_BYTES // 3 + 16:
            raise ValueError("screenshot_size_rejected")
        try:
            png = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("PNG_payload_invalid") from None
        if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > MAX_SCREENSHOT_BYTES:
            raise ValueError("PNG_payload_invalid")
        screenshot = {
            "mimeType": "image/png",
            "bytes": len(png),
            "sha256": hashlib.sha256(png).hexdigest(),
            "persisted": False,
        }
        if include_png:
            screenshot["base64"] = encoded
        return {
            "ok": True,
            "status": "BROWSER_PROJECTION_UNVERIFIED",
            "authority": "browser_projection_only",
            "engineRevisionVerified": False,
            "runtimeVerified": False,
            "sourceUrl": target_url,
            "pageUrl": PUBLIC_ORIGIN + (urlsplit(page["url"]).path or "/"),
            "title": str(page.get("title") or "")[:120],
            "linkCount": page.get("links") if isinstance(page.get("links"), int) else None,
            "screenshot": screenshot,
        }
    finally:
        if context_id:
            try:
                cdp.call("Target.disposeBrowserContext", {"browserContextId": context_id})
            except Exception:
                pass  # Cleanup remains best-effort; never masks the capture result.
        socket.close()


def probe_local_engine() -> dict:
    """Read a loopback health endpoint only. Does not verify build identity."""
    if os.getenv("SOVEREIGN_KITESURF_ENABLED", "0") != "1":
        return {"ok": False, "status": "KITESURF_DISABLED", "runtimeVerified": False}
    try:
        port = _port()
        import requests
        session = requests.Session()
        session.trust_env = False  # No environment proxy, credentials, or redirects.
        try:
            response = session.get("http://127.0.0.1:" + str(port) + "/health", timeout=2, allow_redirects=False)
        finally:
            session.close()
        if response.status_code != 200:
            return {"ok": False, "status": "ENGINE_HEALTH_UNVERIFIED", "runtimeVerified": False}
        return {"ok": True, "status": "ENGINE_HEALTH_REACHABLE", "runtimeVerified": False,
                "engineRevisionVerified": False, "cdpAddress": "loopback_only", "port": port}
    except Exception:
        return {"ok": False, "status": "ENGINE_UNAVAILABLE", "runtimeVerified": False}


def capture_public_page(path: str = "/", include_png: bool = False) -> dict:
    """One bounded capture through a previously started, locally bound Kitesurf.

    No engine start, credentials, login, arbitrary URL, or external WebSocket.
    """
    if os.getenv("SOVEREIGN_KITESURF_ENABLED", "0") != "1":
        return {"ok": False, "status": "KITESURF_DISABLED", "runtimeVerified": False}
    try:
        validate_public_path(path)
    except ValueError:
        return {"ok": False, "status": "TARGET_REJECTED", "runtimeVerified": False}
    health = probe_local_engine()
    if not health.get("ok"):
        return health
    try:
        from websocket import create_connection
        port = _port()
        ws = create_connection(
            "ws://127.0.0.1:" + str(port) + "/devtools/browser",
            timeout=12,
            http_no_proxy=["127.0.0.1"],
            enable_multithread=False,
        )
        return capture_cdp_page(ws, path, include_png)
    except Exception:
        return {"ok": False, "status": "CDP_CAPTURE_FAILED", "runtimeVerified": False}
