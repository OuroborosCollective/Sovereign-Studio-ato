from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any, Callable

MANUS_SHARE_PATH_RE = re.compile(r"^/share/[A-Za-z0-9_-]{8,128}/?$")
MAX_RENDERED_HTML_BYTES = 900_000
MAX_VISIBLE_TEXT_CHARS = 320_000
DEFAULT_BROWSERLESS_CONTENT_URL = "http://127.0.0.1:3000/content"

BLOCKED_REQUEST_PATTERNS = (
    r"^https?://localhost(?:[:/]|$)",
    r"^https?://127(?:\.[0-9]{1,3}){3}(?:[:/]|$)",
    r"^https?://0\.0\.0\.0(?:[:/]|$)",
    r"^https?://\[?::1\]?(?:[:/]|$)",
    r"^https?://10(?:\.[0-9]{1,3}){3}(?:[:/]|$)",
    r"^https?://192\.168(?:\.[0-9]{1,3}){2}(?:[:/]|$)",
    r"^https?://172\.(?:1[6-9]|2[0-9]|3[01])(?:\.[0-9]{1,3}){2}(?:[:/]|$)",
    r"^https?://169\.254(?:\.[0-9]{1,3}){2}(?:[:/]|$)",
    r"^https?://100\.(?:6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])(?:\.[0-9]{1,3}){2}(?:[:/]|$)",
)


class _VisibleTextParser(HTMLParser):
    _SKIPPED = {"script", "style", "noscript", "svg", "canvas", "template"}
    _BREAKS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._title_depth = 0
        self._parts: list[str] = []
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in self._SKIPPED:
            self._skip_depth += 1
        if normalized == "title":
            self._title_depth += 1
        if normalized in self._BREAKS and self._skip_depth == 0:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized == "title" and self._title_depth:
            self._title_depth -= 1
        if normalized in self._SKIPPED and self._skip_depth:
            self._skip_depth -= 1
        if normalized in self._BREAKS and self._skip_depth == 0:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._title_depth:
            self._title_parts.append(data)
        if self._skip_depth == 0:
            self._parts.append(data)

    @staticmethod
    def _normalize(parts: list[str], limit: int) -> str:
        lines: list[str] = []
        for raw_line in "".join(parts).splitlines():
            normalized = " ".join(raw_line.split())
            if normalized and (not lines or lines[-1] != normalized):
                lines.append(normalized)
        return "\n".join(lines)[:limit]

    @property
    def title(self) -> str:
        return " ".join("".join(self._title_parts).split())[:500]

    @property
    def visible_text(self) -> str:
        return self._normalize(self._parts, MAX_VISIBLE_TEXT_CHARS)


def validate_manus_share_url(value: str) -> str:
    candidate = str(value or "").strip()
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme != "https":
        raise ValueError("Manus-Replay-URL muss HTTPS verwenden")
    if parsed.username or parsed.password:
        raise ValueError("Manus-Replay-URL darf keine Zugangsdaten enthalten")
    if parsed.hostname != "manus.im":
        raise ValueError("Nur öffentliche manus.im-Share-Links sind freigegeben")
    if parsed.port not in {None, 443}:
        raise ValueError("Manus-Replay-URL darf keinen fremden Port verwenden")
    if parsed.query or parsed.fragment:
        raise ValueError("Manus-Replay-URL darf keine Query oder Fragmentdaten enthalten")
    if not MANUS_SHARE_PATH_RE.fullmatch(parsed.path):
        raise ValueError("Manus-Replay-Pfad ist nicht freigegeben")
    return urllib.parse.urlunsplit(("https", "manus.im", parsed.path, "", ""))


class BrowserlessReplayReader:
    def __init__(
        self,
        *,
        urlopen: Callable[..., Any] | None = None,
        resolver: Callable[..., Any] | None = None,
        endpoint: str | None = None,
    ) -> None:
        self._urlopen = urlopen or urllib.request.urlopen
        self._resolver = resolver or socket.getaddrinfo
        self.endpoint = str(
            endpoint
            or os.getenv("SOVEREIGN_BROWSERLESS_CONTENT_URL", DEFAULT_BROWSERLESS_CONTENT_URL)
        ).strip()
        parsed_endpoint = urllib.parse.urlsplit(self.endpoint)
        if parsed_endpoint.scheme != "http" or parsed_endpoint.hostname not in {"127.0.0.1", "localhost"}:
            raise RuntimeError("Browserless-Endpoint muss lokal gebunden sein")
        if parsed_endpoint.port != 3000 or parsed_endpoint.path != "/content":
            raise RuntimeError("Browserless-Endpoint muss exakt auf Port 3000 /content zeigen")

    def _verify_public_manus_dns(self) -> list[str]:
        records = self._resolver("manus.im", 443, type=socket.SOCK_STREAM)
        addresses = sorted(
            {
                str(record[4][0])
                for record in records
                if isinstance(record, tuple)
                and len(record) >= 5
                and isinstance(record[4], tuple)
                and record[4]
            }
        )
        if not addresses:
            raise RuntimeError("manus.im konnte nicht öffentlich aufgelöst werden")
        for address in addresses:
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError as exc:
                raise RuntimeError("manus.im lieferte eine ungültige IP-Adresse") from exc
            if not parsed.is_global:
                raise RuntimeError("manus.im löst auf eine nicht öffentliche IP-Adresse auf")
        return addresses

    @staticmethod
    def _payload(target: str) -> bytes:
        return json.dumps(
            {
                "url": target,
                "gotoOptions": {"waitUntil": "networkidle2", "timeout": 45_000},
                "waitForTimeout": 8_000,
                "bestAttempt": True,
                "rejectResourceTypes": ["media", "font"],
                "rejectRequestPattern": list(BLOCKED_REQUEST_PATTERNS),
            },
            separators=(",", ":"),
        ).encode("utf-8")

    def read_manus_replay(self, share_url: str) -> dict[str, Any]:
        target = validate_manus_share_url(share_url)
        resolved_addresses = self._verify_public_manus_dns()
        request = urllib.request.Request(
            self.endpoint,
            data=self._payload(target),
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "Accept": "text/html",
            },
            method="POST",
        )
        try:
            response = self._urlopen(request, timeout=60)
            status_code = int(getattr(response, "status", 200) or 200)
            rendered = response.read(MAX_RENDERED_HTML_BYTES + 1)
        except urllib.error.HTTPError as exc:
            error_body = exc.read(2_000).decode("utf-8", errors="replace")
            return {
                "ok": False,
                "status": "BROWSERLESS_HTTP_FAILED",
                "failure_family": "BROWSERLESS_HTTP_ERROR",
                "httpStatus": int(exc.code),
                "error": error_body,
                "secretValuesExposed": False,
            }
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {
                "ok": False,
                "status": "BROWSERLESS_UNAVAILABLE",
                "failure_family": "BROWSERLESS_CONNECTION_FAILED",
                "error": type(exc).__name__,
                "secretValuesExposed": False,
            }
        if status_code >= 400:
            return {
                "ok": False,
                "status": "BROWSERLESS_HTTP_FAILED",
                "failure_family": "BROWSERLESS_HTTP_ERROR",
                "httpStatus": status_code,
                "secretValuesExposed": False,
            }
        if len(rendered) > MAX_RENDERED_HTML_BYTES:
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "BROWSERLESS_RESPONSE_TOO_LARGE",
                "limitBytes": MAX_RENDERED_HTML_BYTES,
                "secretValuesExposed": False,
            }
        html_text = rendered.decode("utf-8", errors="replace")
        parser = _VisibleTextParser()
        parser.feed(html_text)
        visible_text = parser.visible_text
        if not visible_text:
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "BROWSERLESS_RENDER_EMPTY",
                "url": target,
                "renderedHtmlBytes": len(rendered),
                "renderedHtmlSha256": hashlib.sha256(rendered).hexdigest(),
                "secretValuesExposed": False,
            }
        return {
            "ok": True,
            "status": "RENDERED_EVIDENCE_READY",
            "url": target,
            "title": parser.title,
            "visibleText": visible_text,
            "visibleTextChars": len(visible_text),
            "renderedHtmlBytes": len(rendered),
            "renderedHtmlSha256": hashlib.sha256(rendered).hexdigest(),
            "resolvedPublicAddresses": resolved_addresses,
            "browserlessEndpoint": "local-fixed-content-api",
            "rawHtmlReturned": False,
            "secretValuesExposed": False,
        }
