from __future__ import annotations

from urllib.parse import urlparse

from sovereign_cognitive_widget import RESOURCE_META, STRICT_CSP, WIDGET_DOMAIN


def test_widget_has_unique_submission_domain_on_standard_and_compatibility_metadata() -> None:
    parsed = urlparse(WIDGET_DOMAIN)

    assert parsed.scheme == "https"
    assert parsed.netloc
    assert parsed.path in {"", "/"}
    assert RESOURCE_META["ui"]["domain"] == WIDGET_DOMAIN
    assert RESOURCE_META["openai/widgetDomain"] == WIDGET_DOMAIN


def test_widget_keeps_least_privilege_inline_csp() -> None:
    assert STRICT_CSP == {
        "connectDomains": [],
        "resourceDomains": [],
        "frameDomains": [],
    }
    assert RESOURCE_META["ui"]["csp"] == STRICT_CSP
    assert RESOURCE_META["openai/widgetCSP"] == {
        "connect_domains": [],
        "resource_domains": [],
        "frame_domains": [],
        "redirect_domains": [],
    }
