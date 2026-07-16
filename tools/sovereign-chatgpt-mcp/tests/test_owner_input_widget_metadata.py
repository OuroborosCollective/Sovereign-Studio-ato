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
        "connectDomains": [OWNER_BACKEND_ORIGIN],
        "resourceDomains": [],
        "frameDomains": [],
    }
    assert RESOURCE_META["ui"]["domain"] == WIDGET_DOMAIN
    assert RESOURCE_META["ui"]["csp"] == STRICT_CSP
    assert RESOURCE_META["openai/widgetDomain"] == WIDGET_DOMAIN
    assert RESOURCE_META["openai/widgetCSP"]["connect_domains"] == [OWNER_BACKEND_ORIGIN]


def test_owner_widget_is_bound_to_the_request_tool() -> None:
    assert WIDGET_URI == "ui://sovereign/owner_input.html"
    assert TOOL_META["ui"]["resourceUri"] == WIDGET_URI
    assert TOOL_META["openai/outputTemplate"] == WIDGET_URI
    assert TOOL_META["ui"]["visibility"] == ["model", "app"]


def test_owner_widget_never_routes_protected_value_through_chat_or_tool_calls() -> None:
    assert "sendFollowUpMessage" not in WIDGET_HTML
    assert "console." not in WIDGET_HTML
    assert "window.openai.toolOutput" in WIDGET_HTML
    assert "ui/notifications/tool-result" in WIDGET_HTML
    assert "Content-Type': 'application/octet-stream'" in WIDGET_HTML
    assert "credentials: 'omit'" in WIDGET_HTML
    assert "cache: 'no-store'" in WIDGET_HTML
    assert "encoded.fill(0)" in WIDGET_HTML
    assert "clearSensitiveInputs()" in WIDGET_HTML
    assert "byId('adminKey').value = ''" in WIDGET_HTML
    assert "byId('protectedValue').value = ''" in WIDGET_HTML
    assert "/api/admin/owner-input/requests/" in WIDGET_HTML
