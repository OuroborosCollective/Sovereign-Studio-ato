from __future__ import annotations

from urllib.parse import urlparse

from owner_input_widget import (
    OWNER_BACKEND_ORIGIN,
    RESOURCE_META,
    STRICT_CSP,
    TOOL_META,
    WIDGET_DOMAIN,
    WIDGET_HTML,
    WIDGET_URI,
)


def test_owner_widget_uses_one_https_backend_origin() -> None:
    parsed = urlparse(WIDGET_DOMAIN)

    assert parsed.scheme == "https"
    assert parsed.netloc
    assert parsed.path in {"", "/"}
    assert OWNER_BACKEND_ORIGIN == WIDGET_DOMAIN
    assert STRICT_CSP == {
        "connectDomains": [],
        "resourceDomains": [],
        "frameDomains": [],
    }
    assert RESOURCE_META["ui"]["domain"] == WIDGET_DOMAIN
    assert RESOURCE_META["ui"]["csp"] == STRICT_CSP
    assert RESOURCE_META["openai/widgetDomain"] == WIDGET_DOMAIN
    assert RESOURCE_META["openai/widgetCSP"]["connect_domains"] == []
    assert RESOURCE_META["openai/widgetCSP"]["redirect_domains"] == [OWNER_BACKEND_ORIGIN]


def test_owner_widget_is_bound_to_the_request_tool() -> None:
    assert WIDGET_URI == "ui://sovereign/owner_input.html"
    assert TOOL_META["ui"]["resourceUri"] == WIDGET_URI
    assert TOOL_META["openai/outputTemplate"] == WIDGET_URI
    assert TOOL_META["ui"]["visibility"] == ["model", "app"]


def test_owner_widget_routes_all_protected_input_to_same_origin_owner_page() -> None:
    assert "sendFollowUpMessage" not in WIDGET_HTML
    assert "console." not in WIDGET_HTML
    assert "window.openai.toolOutput" in WIDGET_HTML
    assert "ui/notifications/tool-result" in WIDGET_HTML
    assert "event.source !== window.parent" in WIDGET_HTML
    assert "message.jsonrpc !== '2.0'" in WIDGET_HTML
    assert "window.openai.openExternal" in WIDGET_HTML
    assert "redirectUrl: false" in WIDGET_HTML
    assert "/owner-approvals?request_id=" in WIDGET_HTML
    assert "fetch(" not in WIDGET_HTML
    assert "adminKey" not in WIDGET_HTML
    assert "protectedValue" not in WIDGET_HTML
    assert "TextEncoder" not in WIDGET_HTML
    assert "application/octet-stream" not in WIDGET_HTML
