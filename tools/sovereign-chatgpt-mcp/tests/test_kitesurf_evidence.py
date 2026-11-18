from __future__ import annotations

import base64
import hashlib
import json

import pytest

from kitesurf_evidence import CdpSession, capture_cdp_page, capture_public_page, validate_public_path


class OfflineCdpTestTransport:
    """Synthetic CDP protocol fixture ONLY: never runtime or browser evidence."""

    def __init__(self, page_url="https://arelogic.space/", broken_png=False):
        self.sent = []
        self.pending = []
        self.closed = False
        self.page_url = page_url
        self.broken_png = broken_png

    def send(self, encoded):
        req = json.loads(encoded)
        self.sent.append(req)
        ident = req["id"]
        method = req["method"]
        answers = {
            "Target.createBrowserContext": {"browserContextId": "test-context"},
            "Target.createTarget": {"targetId": "test-target"},
            "Target.attachToTarget": {"sessionId": "test-session"},
            "Page.enable": {},
            "Runtime.enable": {},
            "Page.navigate": {"frameId": "test-frame"},
            "Runtime.evaluate": {
                "result": {
                    "type": "string",
                    "value": json.dumps({
                        "url": self.page_url,
                        "title": "Public showcase",
                        "ready": "complete",
                        "links": 4,
                    }),
                }
            },
            "Page.captureScreenshot": {
                "data": base64.b64encode(
                    b"invalid" if self.broken_png else b"\x89PNG\r\n\x1a\n" + b"x" * 64
                ).decode("ascii")
            },
            "Target.disposeBrowserContext": {},
        }
        if method == "Page.navigate":
            self.pending.append(json.dumps({"method": "Page.frameNavigated", "params": {}}))
        self.pending.append(json.dumps({"id": ident, "result": answers[method]}))

    def recv(self):
        assert self.pending, "Unexpected CDP receive without a reply"
        return self.pending.pop(0)

    def close(self):
        self.closed = True


@pytest.mark.parametrize("path", [
    "https://example.com/", "//example.com", "/../admin", "/a/./b",
    "/%2f%2fexample.com", "/?token=opaque", "/#fragment", "/a\\b",
    " /", "/a\r\nb", "/" + "x" * 300,
])
def test_scope_rejects_untrusted_paths(path):
    with pytest.raises(ValueError):
        validate_public_path(path)


def test_scope_accepts_only_public_arelogic_path():
    assert validate_public_path("/") == "https://arelogic.space/"
    assert validate_public_path("/projects/ashen-crypt") == "https://arelogic.space/projects/ashen-crypt"


def test_capture_is_disabled_without_explicit_feature_flag(monkeypatch):
    monkeypatch.delenv("SOVEREIGN_KITESURF_ENABLED", raising=False)
    assert capture_public_page("/")["status"] == "KITESURF_DISABLED"


def test_capture_uses_cdp_and_returns_projection_not_runtime_proof():
    socket = OfflineCdpTestTransport()
    result = capture_cdp_page(socket, "/", include_png=False)
    assert result["ok"] is True
    assert result["status"] == "BROWSER_PROJECTION_UNVERIFIED"
    assert result["authority"] == "browser_projection_only"
    assert result["engineRevisionVerified"] is False
    assert result["pageUrl"] == "https://arelogic.space/"
    assert result["screenshot"]["sha256"] == hashlib.sha256(
        b"\x89PNG\r\n\x1a\n" + b"x" * 64
    ).hexdigest()
    assert "base64" not in result["screenshot"]
    assert socket.closed is True
    assert [m["method"] for m in socket.sent] == [
        "Target.createBrowserContext", "Target.createTarget", "Target.attachToTarget",
        "Page.enable", "Runtime.enable", "Page.navigate",
        "Runtime.evaluate", "Page.captureScreenshot", "Target.disposeBrowserContext",
    ]


def test_redirect_off_origin_fails_closed_before_screenshot():
    socket = OfflineCdpTestTransport(page_url="https://example.net/")
    with pytest.raises(ValueError, match="redirect"):
        capture_cdp_page(socket, "/")
    assert "Page.captureScreenshot" not in [m["method"] for m in socket.sent]
    assert socket.closed


def test_corrupt_screenshot_is_rejected():
    socket = OfflineCdpTestTransport(broken_png=True)
    with pytest.raises(ValueError, match="PNG"):
        capture_cdp_page(socket, "/")
    assert socket.closed


def test_session_ignores_event_while_waiting_for_matching_reply():
    socket = OfflineCdpTestTransport()
    result = CdpSession(socket).call("Target.createBrowserContext")
    assert result["browserContextId"] == "test-context"


def test_existing_mcp_registry_exposes_only_scoped_optional_tools():
    import launcher
    tools = {tool.name: tool for tool in launcher.mcp._tool_manager.list_tools()}
    assert "kitesurf_engine_status" in tools
    assert "kitesurf_capture_public_page" in tools
    assert tools["kitesurf_capture_public_page"].annotations.readOnlyHint is True
    assert tools["kitesurf_capture_public_page"].annotations.openWorldHint is True
