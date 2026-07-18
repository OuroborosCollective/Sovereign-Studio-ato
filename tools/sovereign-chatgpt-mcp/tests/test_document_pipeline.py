from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from document_pipeline import MAX_PDF_BYTES, DocumentPipelineRuntime


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        content: bytes = b"",
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.text = text
        self.headers = headers or {}


def test_mcp_image_packages_document_pipeline_module() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text("utf-8")
    assert "a2a_runtime_client.py document_pipeline.py owner_input_widget.py" in dockerfile


def test_live_canary_correlates_real_pdf_generation_and_text_extraction(monkeypatch) -> None:
    runtime = DocumentPipelineRuntime()
    monkeypatch.setattr(runtime, "_first_reachable", lambda container, port, path: f"http://{container}:{port}")

    calls: list[dict[str, Any]] = []

    def fake_post(url, files, timeout):
        calls.append({"kind": "post", "url": url, "files": files, "timeout": timeout})
        return FakeResponse(
            200,
            content=b"%PDF-1.7\n" + (b"real-pdf-evidence" * 16),
            headers={"Content-Type": "application/pdf"},
        )

    def fake_put(url, data, headers, timeout):
        calls.append({"kind": "put", "url": url, "data": data, "headers": headers, "timeout": timeout})
        return FakeResponse(200, text="SOVEREIGN_DOCUMENT_PIPELINE_CANARY\nGotenberg to Tika live evidence.")

    monkeypatch.setattr("document_pipeline.requests.post", fake_post)
    monkeypatch.setattr("document_pipeline.requests.put", fake_put)

    result = runtime.live_canary()

    assert result["ok"] is True
    assert result["status"] == "DOCUMENT_PIPELINE_LIVE_CANARY_VERIFIED"
    assert MAX_PDF_BYTES == 33 * 1024 * 1024
    assert result["gotenberg"]["maxPdfBytes"] == MAX_PDF_BYTES
    assert result["gotenberg"]["pdfSha256"]
    assert result["tika"]["maxPdfBytes"] == MAX_PDF_BYTES
    assert result["tika"]["markerVerified"] is True
    assert result["documentContentReturned"] is False
    assert result["secretValuesReturned"] is False
    assert calls[0]["url"].endswith("/forms/chromium/convert/html")
    assert calls[1]["headers"]["Content-Type"] == "application/pdf"


def test_live_canary_fails_closed_when_tika_does_not_return_marker(monkeypatch) -> None:
    runtime = DocumentPipelineRuntime()
    monkeypatch.setattr(runtime, "_first_reachable", lambda container, port, path: f"http://{container}:{port}")
    monkeypatch.setattr(
        "document_pipeline.requests.post",
        lambda *args, **kwargs: FakeResponse(
            200,
            content=b"%PDF-1.7\n" + (b"real-pdf-evidence" * 16),
        ),
    )
    monkeypatch.setattr(
        "document_pipeline.requests.put",
        lambda *args, **kwargs: FakeResponse(200, text="different text"),
    )

    with pytest.raises(RuntimeError, match="TIKA_MARKER_NOT_EXTRACTED"):
        runtime.live_canary()


def test_live_canary_accepts_pdf_at_exactly_33_mib(monkeypatch) -> None:
    runtime = DocumentPipelineRuntime()
    monkeypatch.setattr(runtime, "_first_reachable", lambda container, port, path: f"http://{container}:{port}")
    prefix = b"%PDF-1.7\n"
    monkeypatch.setattr(
        "document_pipeline.requests.post",
        lambda *args, **kwargs: FakeResponse(
            200,
            content=prefix + (b"x" * (MAX_PDF_BYTES - len(prefix))),
            headers={"Content-Type": "application/pdf"},
        ),
    )
    monkeypatch.setattr(
        "document_pipeline.requests.put",
        lambda *args, **kwargs: FakeResponse(200, text="SOVEREIGN_DOCUMENT_PIPELINE_CANARY"),
    )

    result = runtime.live_canary()

    assert result["gotenberg"]["pdfBytes"] == MAX_PDF_BYTES
    assert result["tika"]["markerVerified"] is True


def test_live_canary_rejects_pdf_larger_than_33_mib_before_tika(monkeypatch) -> None:
    runtime = DocumentPipelineRuntime()
    monkeypatch.setattr(runtime, "_first_reachable", lambda container, port, path: f"http://{container}:{port}")
    monkeypatch.setattr(
        "document_pipeline.requests.post",
        lambda *args, **kwargs: FakeResponse(
            200,
            content=b"%PDF-1.7\n" + (b"x" * MAX_PDF_BYTES),
        ),
    )

    tika_called = False

    def fake_put(*args, **kwargs):
        nonlocal tika_called
        tika_called = True
        return FakeResponse(200, text="SOVEREIGN_DOCUMENT_PIPELINE_CANARY")

    monkeypatch.setattr("document_pipeline.requests.put", fake_put)

    with pytest.raises(RuntimeError, match="GOTENBERG_OUTPUT_SIZE_INVALID"):
        runtime.live_canary()
    assert tika_called is False


def test_live_canary_rejects_unbounded_marker_before_network() -> None:
    runtime = DocumentPipelineRuntime()
    with pytest.raises(ValueError, match="1 to 160"):
        runtime.live_canary("x" * 161)


def test_pdf_size_limit_accepts_33_mib_and_rejects_the_next_byte() -> None:
    runtime = DocumentPipelineRuntime()
    assert MAX_PDF_BYTES == 33 * 1024 * 1024
    runtime._validate_pdf_size(MAX_PDF_BYTES)
    with pytest.raises(RuntimeError, match="GOTENBERG_OUTPUT_SIZE_INVALID"):
        runtime._validate_pdf_size(MAX_PDF_BYTES + 1)
