from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Any

import requests


MAX_PDF_BYTES = 33 * 1024 * 1024


class DocumentPipelineRuntime:
    """Run bounded live Tika/Gotenberg evidence without persisting document content."""

    def __init__(self) -> None:
        self.tika_container = os.getenv("SOVEREIGN_TIKA_CONTAINER", "gpt-tika").strip() or "gpt-tika"
        self.gotenberg_container = os.getenv("SOVEREIGN_GOTENBERG_CONTAINER", "gpt-gotenberg").strip() or "gpt-gotenberg"
        self.timeout_seconds = max(5, min(int(os.getenv("SOVEREIGN_DOCUMENT_CANARY_TIMEOUT", "45")), 120))

    @staticmethod
    def _inspect_networks(container: str) -> list[str]:
        completed = subprocess.run(
            ["docker", "inspect", "--format", "{{json .NetworkSettings.Networks}}", container],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"DOCUMENT_CONTAINER_UNAVAILABLE:{container}")
        try:
            networks = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"DOCUMENT_CONTAINER_NETWORK_INVALID:{container}") from exc
        if not isinstance(networks, dict):
            raise RuntimeError(f"DOCUMENT_CONTAINER_NETWORK_INVALID:{container}")
        ips = sorted({
            str(values.get("IPAddress") or "").strip()
            for values in networks.values()
            if isinstance(values, dict) and str(values.get("IPAddress") or "").strip()
        })
        if not ips:
            raise RuntimeError(f"DOCUMENT_CONTAINER_IP_MISSING:{container}")
        return ips

    def _first_reachable(self, container: str, port: int, health_path: str) -> str:
        last_family = "DOCUMENT_SERVICE_UNREACHABLE"
        for ip_address in self._inspect_networks(container):
            base_url = f"http://{ip_address}:{port}"
            try:
                response = requests.get(
                    f"{base_url}{health_path}",
                    timeout=min(self.timeout_seconds, 15),
                )
            except requests.RequestException:
                last_family = "DOCUMENT_SERVICE_CONNECTION_FAILED"
                continue
            if response.status_code < 500:
                return base_url
            last_family = f"DOCUMENT_SERVICE_HTTP_{response.status_code}"
        raise RuntimeError(last_family)

    @staticmethod
    def _html(marker: str) -> bytes:
        escaped = (
            marker.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        return (
            "<!doctype html><html><head><meta charset=\"utf-8\">"
            "<title>Sovereign document canary</title></head>"
            f"<body><h1>{escaped}</h1><p>Gotenberg to Tika live evidence.</p></body></html>"
        ).encode("utf-8")

    def live_canary(self, marker: str = "SOVEREIGN_DOCUMENT_PIPELINE_CANARY") -> dict[str, Any]:
        normalized_marker = str(marker or "").strip()
        if not normalized_marker or len(normalized_marker) > 160:
            raise ValueError("marker must contain 1 to 160 characters")

        gotenberg_url = self._first_reachable(self.gotenberg_container, 3000, "/health")
        tika_url = self._first_reachable(self.tika_container, 9998, "/version")

        try:
            generated = requests.post(
                f"{gotenberg_url}/forms/chromium/convert/html",
                files={"files": ("index.html", self._html(normalized_marker), "text/html")},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise RuntimeError("GOTENBERG_CONVERSION_UNAVAILABLE") from exc
        if generated.status_code != 200:
            raise RuntimeError(f"GOTENBERG_CONVERSION_HTTP_{generated.status_code}")
        pdf_bytes = bytes(generated.content or b"")
        if not pdf_bytes.startswith(b"%PDF-"):
            raise RuntimeError("GOTENBERG_OUTPUT_NOT_PDF")
        if not 200 <= len(pdf_bytes) <= MAX_PDF_BYTES:
            raise RuntimeError("GOTENBERG_OUTPUT_SIZE_INVALID")

        try:
            extracted = requests.put(
                f"{tika_url}/tika",
                data=pdf_bytes,
                headers={
                    "Accept": "text/plain; charset=utf-8",
                    "Content-Type": "application/pdf",
                },
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise RuntimeError("TIKA_EXTRACTION_UNAVAILABLE") from exc
        if extracted.status_code != 200:
            raise RuntimeError(f"TIKA_EXTRACTION_HTTP_{extracted.status_code}")
        extracted_text = extracted.text or ""
        marker_verified = normalized_marker in extracted_text
        if not marker_verified:
            raise RuntimeError("TIKA_MARKER_NOT_EXTRACTED")

        return {
            "ok": True,
            "status": "DOCUMENT_PIPELINE_LIVE_CANARY_VERIFIED",
            "gotenberg": {
                "container": self.gotenberg_container,
                "httpStatus": generated.status_code,
                "contentType": str(generated.headers.get("Content-Type") or "")[:120],
                "pdfBytes": len(pdf_bytes),
                "maxPdfBytes": MAX_PDF_BYTES,
                "pdfSha256": hashlib.sha256(pdf_bytes).hexdigest(),
            },
            "tika": {
                "container": self.tika_container,
                "httpStatus": extracted.status_code,
                "extractedCharacters": len(extracted_text),
                "maxPdfBytes": MAX_PDF_BYTES,
                "markerVerified": marker_verified,
            },
            "sourcePersisted": False,
            "outputPersisted": False,
            "documentContentReturned": False,
            "secretValuesReturned": False,
        }
