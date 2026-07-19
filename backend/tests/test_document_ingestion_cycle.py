from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

import document_ingestion


class FakeResponse:
    def __init__(self, payload: bytes, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def iter_content(self, chunk_size: int = 64 * 1024):
        del chunk_size
        yield self.payload


def test_pdf_uses_private_tika_and_preserves_pipeline_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_put(url: str, **kwargs):
        seen["url"] = url
        seen["headers"] = kwargs["headers"]
        return FakeResponse(b"Extracted PDF knowledge")

    monkeypatch.setenv("SOVEREIGN_TIKA_URL", "http://tika:9998")
    monkeypatch.setattr(document_ingestion.requests, "put", fake_put)

    result = document_ingestion.extract_uploaded_document("manual.pdf", b"%PDF-test")

    assert result.text == "Extracted PDF knowledge"
    assert result.source_type == "pdf"
    assert result.metadata["documentPipeline"] == "tika"
    assert result.metadata["convertedByGotenberg"] is False
    assert seen["url"] == "http://tika:9998/tika"
    assert seen["headers"]["Content-Type"] == "application/pdf"


def test_office_document_flows_gotenberg_to_tika(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_post(url: str, **kwargs):
        calls.append(url)
        assert kwargs["files"]["files"][0] == "brief.docx"
        return FakeResponse(b"%PDF-converted")

    def fake_put(url: str, **kwargs):
        calls.append(url)
        assert kwargs["data"].startswith(b"%PDF-")
        return FakeResponse(b"Converted office knowledge")

    monkeypatch.setenv("SOVEREIGN_GOTENBERG_URL", "http://gotenberg:3000")
    monkeypatch.setenv("SOVEREIGN_TIKA_URL", "http://tika:9998")
    monkeypatch.setattr(document_ingestion.requests, "post", fake_post)
    monkeypatch.setattr(document_ingestion.requests, "put", fake_put)

    result = document_ingestion.extract_uploaded_document("brief.docx", b"office-bytes")

    assert calls == [
        "http://gotenberg:3000/forms/libreoffice/convert",
        "http://tika:9998/tika",
    ]
    assert result.source_type == "document"
    assert result.metadata["documentPipeline"] == "gotenberg-tika"
    assert result.metadata["convertedByGotenberg"] is True


def test_document_pipeline_rejects_public_or_credential_bearing_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOVEREIGN_DOCUMENT_PIPELINE_MODE", "require-private")
    monkeypatch.setenv("SOVEREIGN_TIKA_URL", "https://public.example.com")
    with pytest.raises(document_ingestion.DocumentPipelineUnavailable, match="PRIVATE_ENDPOINT_INVALID"):
        document_ingestion.extract_uploaded_document("manual.pdf", b"%PDF-test")

    monkeypatch.setenv("SOVEREIGN_TIKA_URL", "http://user:secret@tika:9998")
    with pytest.raises(document_ingestion.DocumentPipelineUnavailable, match="PRIVATE_ENDPOINT_INVALID"):
        document_ingestion.extract_uploaded_document("manual.pdf", b"%PDF-test")


def test_require_private_mode_does_not_hide_tika_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOVEREIGN_TIKA_URL", "http://tika:9998")
    monkeypatch.setenv("SOVEREIGN_DOCUMENT_PIPELINE_MODE", "require-private")

    def fail_put(*_args, **_kwargs):
        raise requests.ConnectionError("unreachable")

    monkeypatch.setattr(document_ingestion.requests, "put", fail_put)

    with pytest.raises(document_ingestion.DocumentPipelineUnavailable, match="TIKA_NETWORK_PEER_UNREACHABLE"):
        document_ingestion.extract_uploaded_document("manual.pdf", b"%PDF-test")
