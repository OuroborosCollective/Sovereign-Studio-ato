"""Bounded private document conversion and extraction for knowledge ingestion.

The product backend talks only to explicitly configured private Gotenberg and
Tika endpoints. PostgreSQL/pgvector remains the canonical memory; this module
only transforms uploaded bytes into text plus provenance metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import ipaddress
import mimetypes
import os
import re
from typing import Any
from urllib.parse import urlparse

import requests


MAX_PDF_BYTES = 33 * 1024 * 1024
MAX_DOCUMENT_BYTES = 12 * 1024 * 1024
MAX_EXTRACTED_TEXT_BYTES = 12 * 1024 * 1024
MAX_PDF_PAGES = 500
_OFFICE_EXTENSIONS = {
    ".doc", ".docx", ".odt", ".rtf",
    ".ppt", ".pptx", ".odp",
    ".xls", ".xlsx", ".ods",
}
_SAFE_DOCKER_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class DocumentPipelineUnavailable(RuntimeError):
    """Private Gotenberg/Tika pipeline could not complete a bounded request."""


@dataclass(frozen=True)
class DocumentExtraction:
    text: str
    source_type: str
    metadata: dict[str, Any]


def supported_office_extensions() -> frozenset[str]:
    return frozenset(_OFFICE_EXTENSIONS)


def _suffix(filename: str) -> str:
    clean = str(filename or "").lower()
    return "." + clean.rsplit(".", 1)[-1] if "." in clean else ""


def _private_base_url(env_name: str, default: str) -> str:
    value = str(os.getenv(env_name, default) or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password:
        raise DocumentPipelineUnavailable(f"{env_name}_PRIVATE_ENDPOINT_INVALID")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise DocumentPipelineUnavailable(f"{env_name}_PRIVATE_ENDPOINT_INVALID")

    hostname = parsed.hostname
    private_host = False
    try:
        address = ipaddress.ip_address(hostname)
        private_host = address.is_private or address.is_loopback
    except ValueError:
        private_host = bool(_SAFE_DOCKER_HOST_RE.fullmatch(hostname)) and "." not in hostname
    if not private_host:
        raise DocumentPipelineUnavailable(f"{env_name}_PRIVATE_ENDPOINT_REQUIRED")
    return value


def _bounded_response_bytes(response: Any, maximum: int, family: str) -> bytes:
    payload = bytearray()
    iterator = getattr(response, "iter_content", None)
    if callable(iterator):
        for chunk in iterator(chunk_size=64 * 1024):
            if not chunk:
                continue
            payload.extend(chunk)
            if len(payload) > maximum:
                raise DocumentPipelineUnavailable(f"{family}_RESPONSE_TOO_LARGE")
        return bytes(payload)
    raw = bytes(getattr(response, "content", b"") or b"")
    if len(raw) > maximum:
        raise DocumentPipelineUnavailable(f"{family}_RESPONSE_TOO_LARGE")
    return raw


def _timeout_seconds() -> int:
    try:
        configured = int(os.getenv("SOVEREIGN_DOCUMENT_PIPELINE_TIMEOUT_SECONDS", "45"))
    except ValueError:
        configured = 45
    return max(5, min(configured, 120))


def _tika_extract(payload: bytes, content_type: str) -> str:
    endpoint = _private_base_url("SOVEREIGN_TIKA_URL", "http://tika:9998")
    try:
        response = requests.put(
            f"{endpoint}/tika",
            data=payload,
            headers={
                "Accept": "text/plain; charset=utf-8",
                "Content-Type": content_type,
                "Content-Length": str(len(payload)),
            },
            timeout=_timeout_seconds(),
            stream=True,
        )
    except requests.RequestException as exc:
        raise DocumentPipelineUnavailable("TIKA_NETWORK_PEER_UNREACHABLE") from exc
    if int(getattr(response, "status_code", 0) or 0) != 200:
        raise DocumentPipelineUnavailable(f"TIKA_EXTRACTION_HTTP_{getattr(response, 'status_code', 0)}")
    extracted = _bounded_response_bytes(response, MAX_EXTRACTED_TEXT_BYTES, "TIKA_EXTRACTION")
    text = extracted.decode("utf-8", errors="replace").replace("\x00", "").strip()
    if not text:
        raise DocumentPipelineUnavailable("TIKA_EXTRACTION_EMPTY")
    return text


def _gotenberg_auth() -> tuple[str, str] | None:
    username = str(
        os.getenv("SOVEREIGN_GOTENBERG_USERNAME", "")
        or os.getenv("GOTENBERG_API_BASIC_AUTH_USERNAME", "")
    ).strip()
    password = str(
        os.getenv("SOVEREIGN_GOTENBERG_PASSWORD", "")
        or os.getenv("GOTENBERG_API_BASIC_AUTH_PASSWORD", "")
    )
    if not username and not password:
        return None
    if not username or not password or ":" in username or len(username) > 512 or len(password) > 1024:
        raise DocumentPipelineUnavailable("GOTENBERG_BASIC_AUTH_INVALID")
    return username, password


def _gotenberg_convert_office(filename: str, payload: bytes) -> bytes:
    endpoint = _private_base_url("SOVEREIGN_GOTENBERG_URL", "http://gotenberg:3000")
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    try:
        response = requests.post(
            f"{endpoint}/forms/libreoffice/convert",
            files={"files": (filename, payload, content_type)},
            headers={"Accept": "application/pdf"},
            auth=_gotenberg_auth(),
            timeout=_timeout_seconds(),
            stream=True,
        )
    except requests.RequestException as exc:
        raise DocumentPipelineUnavailable("GOTENBERG_NETWORK_PEER_UNREACHABLE") from exc
    if int(getattr(response, "status_code", 0) or 0) != 200:
        raise DocumentPipelineUnavailable(f"GOTENBERG_CONVERSION_HTTP_{getattr(response, 'status_code', 0)}")
    pdf = _bounded_response_bytes(response, MAX_PDF_BYTES, "GOTENBERG_CONVERSION")
    if not pdf.startswith(b"%PDF-"):
        raise DocumentPipelineUnavailable("GOTENBERG_OUTPUT_NOT_PDF")
    return pdf


def _pypdf_fallback(filename: str, payload: bytes, pipeline_blocker: str) -> DocumentExtraction:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentPipelineUnavailable("PDF_FALLBACK_DEPENDENCY_UNAVAILABLE") from exc

    reader = PdfReader(io.BytesIO(payload))
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError(f"PDF exceeds the {MAX_PDF_PAGES}-page limit")
    pages: list[str] = []
    for index, page in enumerate(reader.pages):
        text = str(page.extract_text() or "").strip()
        if text:
            pages.append(f"# Page {index + 1}\n\n{text}")
    if not pages:
        raise ValueError("PDF contains no extractable text; scanned PDFs need Tika/OCR preprocessing")
    return DocumentExtraction(
        text="\n\n".join(pages),
        source_type="pdf",
        metadata={
            "filename": filename,
            "pages": len(reader.pages),
            "documentPipeline": "pypdf-fallback",
            "privatePipelineBlocker": pipeline_blocker[:160],
        },
    )


def extract_uploaded_document(filename: str, payload: bytes) -> DocumentExtraction:
    """Transform one bounded PDF/office upload into text with truthful provenance."""
    suffix = _suffix(filename)
    if suffix == ".pdf":
        if len(payload) > MAX_PDF_BYTES:
            raise ValueError("PDF exceeds 33 MB")
        try:
            text = _tika_extract(payload, "application/pdf")
            return DocumentExtraction(
                text=text,
                source_type="pdf",
                metadata={
                    "filename": filename,
                    "documentPipeline": "tika",
                    "convertedByGotenberg": False,
                },
            )
        except DocumentPipelineUnavailable as exc:
            mode = str(os.getenv("SOVEREIGN_DOCUMENT_PIPELINE_MODE", "prefer-private") or "").strip().lower()
            if mode == "require-private":
                raise
            return _pypdf_fallback(filename, payload, str(exc))

    if suffix not in _OFFICE_EXTENSIONS:
        raise ValueError("Document pipeline supports PDF and office documents")
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise ValueError("Office document exceeds 12 MB")
    pdf = _gotenberg_convert_office(filename, payload)
    text = _tika_extract(pdf, "application/pdf")
    return DocumentExtraction(
        text=text,
        source_type="document",
        metadata={
            "filename": filename,
            "extension": suffix,
            "documentPipeline": "gotenberg-tika",
            "convertedByGotenberg": True,
            "convertedPdfBytes": len(pdf),
        },
    )
