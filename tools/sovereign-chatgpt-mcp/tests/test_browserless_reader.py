from __future__ import annotations

import json
from pathlib import Path

import pytest

from broker import BrokerRuntime
from browserless_reader import (
    MAX_RENDERED_HTML_BYTES,
    BrowserlessReplayReader,
    validate_manus_share_url,
)


PUBLIC_DNS = [
    (2, 1, 6, "", ("104.18.1.1", 443)),
    (2, 1, 6, "", ("104.18.2.1", 443)),
]


class FakeResponse:
    def __init__(self, payload: bytes, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]


def public_resolver(host: str, port: int, **kwargs):
    assert host == "manus.im"
    assert port == 443
    return PUBLIC_DNS


def test_manus_replay_reader_returns_bounded_visible_evidence() -> None:
    observed: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        observed["url"] = request.full_url
        observed["timeout"] = timeout
        observed["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(
            b"<html><head><title>Replay title</title><script>secret()</script></head>"
            b"<body><main><h1>Creating an Architectural Skill</h1><p>Direct evidence.</p></main></body></html>"
        )

    reader = BrowserlessReplayReader(urlopen=fake_urlopen, resolver=public_resolver)
    result = reader.read_manus_replay("https://manus.im/share/eEhUsiXFtmo55UgbYsym3m")

    assert result["ok"] is True
    assert result["status"] == "RENDERED_EVIDENCE_READY"
    assert result["title"] == "Replay title"
    assert "Creating an Architectural Skill" in result["visibleText"]
    assert "Direct evidence." in result["visibleText"]
    assert "secret()" not in result["visibleText"]
    assert result["rawHtmlReturned"] is False
    assert result["secretValuesExposed"] is False
    assert observed["url"] == "http://127.0.0.1:3000/content"
    payload = observed["payload"]
    assert isinstance(payload, dict)
    assert payload["url"] == "https://manus.im/share/eEhUsiXFtmo55UgbYsym3m"
    assert payload["gotoOptions"]["waitUntil"] == "networkidle2"
    assert payload["rejectRequestPattern"]


def test_manus_replay_reader_rejects_non_manus_targets() -> None:
    with pytest.raises(ValueError, match="manus.im"):
        validate_manus_share_url("https://example.com/share/eEhUsiXFtmo55UgbYsym3m")
    with pytest.raises(ValueError, match="Query"):
        validate_manus_share_url("https://manus.im/share/eEhUsiXFtmo55UgbYsym3m?token=secret")
    with pytest.raises(ValueError, match="Pfad"):
        validate_manus_share_url("https://manus.im/private/eEhUsiXFtmo55UgbYsym3m")


def test_manus_replay_reader_blocks_private_dns_resolution() -> None:
    def private_resolver(host: str, port: int, **kwargs):
        return [(2, 1, 6, "", ("127.0.0.1", 443))]

    reader = BrowserlessReplayReader(
        urlopen=lambda *_args, **_kwargs: pytest.fail("Browserless must not be called"),
        resolver=private_resolver,
    )
    with pytest.raises(RuntimeError, match="nicht öffentliche"):
        reader.read_manus_replay("https://manus.im/share/eEhUsiXFtmo55UgbYsym3m")


def test_manus_replay_reader_blocks_oversized_render_output() -> None:
    reader = BrowserlessReplayReader(
        urlopen=lambda *_args, **_kwargs: FakeResponse(b"x" * (MAX_RENDERED_HTML_BYTES + 1)),
        resolver=public_resolver,
    )
    result = reader.read_manus_replay("https://manus.im/share/eEhUsiXFtmo55UgbYsym3m")
    assert result["ok"] is False
    assert result["failure_family"] == "BROWSERLESS_RESPONSE_TOO_LARGE"


def test_broker_dispatch_exposes_manus_replay_reader(monkeypatch) -> None:
    runtime = BrokerRuntime()
    monkeypatch.setattr(
        runtime.browserless,
        "read_manus_replay",
        lambda share_url: {"ok": True, "status": "RENDERED_EVIDENCE_READY", "url": share_url},
    )
    result = runtime.dispatch(
        "manus_public_replay_read",
        {"share_url": "https://manus.im/share/eEhUsiXFtmo55UgbYsym3m"},
    )
    assert result["ok"] is True
    assert result["status"] == "RENDERED_EVIDENCE_READY"


def test_mcp_server_registers_manus_replay_tool() -> None:
    server_source = (Path(__file__).parents[1] / "server.py").read_text("utf-8")
    assert "def manus_public_replay_read(share_url: str)" in server_source
    assert 'broker.call("manus_public_replay_read", {"share_url": share_url}, timeout=90)' in server_source
