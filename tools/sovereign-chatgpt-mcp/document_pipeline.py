from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import http.client
import ipaddress
import json
import os
import re
import subprocess
from typing import Any, Callable


MIN_PDF_BYTES = 200
MAX_PDF_BYTES = 33 * 1024 * 1024
MAX_EXTRACTED_TEXT_BYTES = 2 * 1024 * 1024
_CONTAINER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class _ServiceEndpoint:
    container: str
    address: str
    port: int
    network: str


class DocumentPipelineRuntime:
    """Run bounded live Tika/Gotenberg evidence from the host broker."""

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        connection_factory: Callable[..., http.client.HTTPConnection] | None = None,
    ) -> None:
        self._runner = runner or subprocess.run
        self._connection_factory = connection_factory or http.client.HTTPConnection
        self.tika_container_override = self._optional_container_name(
            os.getenv("SOVEREIGN_TIKA_RUNTIME_CONTAINER", ""),
            "SOVEREIGN_TIKA_RUNTIME_CONTAINER",
        )
        self.gotenberg_container_override = self._optional_container_name(
            os.getenv("SOVEREIGN_GOTENBERG_RUNTIME_CONTAINER", ""),
            "SOVEREIGN_GOTENBERG_RUNTIME_CONTAINER",
        )
        self.timeout_seconds = max(
            5,
            min(int(os.getenv("SOVEREIGN_DOCUMENT_CANARY_TIMEOUT", "45")), 120),
        )

    @staticmethod
    def _container_name(value: str, label: str) -> str:
        candidate = str(value or "").strip()
        if not _CONTAINER_NAME_RE.fullmatch(candidate):
            raise RuntimeError(f"{label} is not a safe container name")
        return candidate

    @classmethod
    def _optional_container_name(cls, value: str, label: str) -> str:
        candidate = str(value or "").strip()
        return cls._container_name(candidate, label) if candidate else ""

    @staticmethod
    def _validate_pdf_size(size_bytes: int) -> None:
        if not MIN_PDF_BYTES <= int(size_bytes) <= MAX_PDF_BYTES:
            raise RuntimeError("GOTENBERG_OUTPUT_SIZE_INVALID")

    def _docker(self, argv: list[str], failure_family: str) -> str:
        completed = self._runner(
            argv,
            capture_output=True,
            text=True,
            timeout=min(self.timeout_seconds, 30),
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(failure_family)
        return completed.stdout

    def _discover_container(self, service: str, override: str, family: str) -> str:
        if override:
            return override
        output = self._docker(
            [
                "docker",
                "ps",
                "--filter",
                "status=running",
                "--filter",
                f"label=com.docker.compose.service={service}",
                "--format",
                "{{.Names}}",
            ],
            f"{family}_CONTAINER_DISCOVERY_FAILED",
        )
        names = [line.strip() for line in output.splitlines() if line.strip()]
        if len(names) != 1:
            suffix = "NOT_FOUND" if not names else "AMBIGUOUS"
            raise RuntimeError(f"{family}_CONTAINER_{suffix}")
        return self._container_name(names[0], f"{family}_RUNTIME_CONTAINER")

    def _private_endpoint(
        self,
        *,
        service: str,
        override: str,
        port: int,
        family: str,
    ) -> _ServiceEndpoint:
        container = self._discover_container(service, override, family)
        output = self._docker(
            [
                "docker",
                "inspect",
                "--format",
                '{{json .State}}|{{index .Config.Labels "com.docker.compose.service"}}|{{json .NetworkSettings.Networks}}',
                container,
            ],
            f"{family}_CONTAINER_INSPECT_FAILED",
        ).strip()
        try:
            state_raw, label, networks_raw = output.split("|", 2)
            state = json.loads(state_raw)
            networks = json.loads(networks_raw)
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"{family}_CONTAINER_INSPECT_INVALID") from exc
        if not isinstance(state, dict) or state.get("Running") is not True:
            raise RuntimeError(f"{family}_CONTAINER_NOT_RUNNING")
        if label.strip() != service:
            raise RuntimeError(f"{family}_CONTAINER_SERVICE_MISMATCH")
        if not isinstance(networks, dict) or len(networks) > 16:
            raise RuntimeError(f"{family}_PRIVATE_ENDPOINT_INVALID")

        endpoints: list[tuple[str, str]] = []
        for network, settings in networks.items():
            if not isinstance(settings, dict):
                continue
            address = str(settings.get("IPAddress") or "").strip()
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError:
                continue
            if not (parsed.is_private or parsed.is_loopback):
                continue
            endpoints.append((str(network), address))
        if not endpoints:
            raise RuntimeError(f"{family}_PRIVATE_ENDPOINT_NOT_FOUND")
        network, address = sorted(endpoints)[0]
        return _ServiceEndpoint(
            container=container,
            address=address,
            port=port,
            network=network,
        )

    def _request(
        self,
        *,
        endpoint: _ServiceEndpoint,
        method: str,
        path: str,
        body: bytes,
        headers: dict[str, str],
        maximum_response_bytes: int,
        failure_family: str,
    ) -> tuple[int, str, bytes]:
        connection: http.client.HTTPConnection | None = None
        try:
            connection = self._connection_factory(
                endpoint.address,
                endpoint.port,
                timeout=self.timeout_seconds,
            )
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read(maximum_response_bytes + 1)
            content_type = str(response.getheader("Content-Type") or "")[:120]
            status = int(response.status)
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            raise RuntimeError(failure_family) from exc
        finally:
            if connection is not None:
                connection.close()
        if len(payload) > maximum_response_bytes:
            raise RuntimeError(f"{failure_family}_RESPONSE_TOO_LARGE")
        return status, content_type, payload

    @staticmethod
    def _gotenberg_body(marker: str) -> tuple[str, bytes]:
        boundary = "----sovereign-document-canary"
        page = (
            '<!doctype html><html><head><meta charset="utf-8">'
            "<title>Sovereign document canary</title></head><body><h1>"
            f"{html.escape(marker, quote=True)}"
            "</h1><p>Gotenberg to Tika live evidence.</p></body></html>"
        ).encode("utf-8")
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="files"; filename="index.html"\r\n'
            "Content-Type: text/html; charset=utf-8\r\n\r\n"
        ).encode("ascii") + page + f"\r\n--{boundary}--\r\n".encode("ascii")
        return boundary, body

    def live_canary(self, marker: str = "SOVEREIGN_DOCUMENT_PIPELINE_CANARY") -> dict[str, Any]:
        normalized_marker = str(marker or "").strip()
        if not normalized_marker or len(normalized_marker) > 160:
            raise ValueError("marker must contain 1 to 160 characters")

        gotenberg_endpoint = self._private_endpoint(
            service="gotenberg",
            override=self.gotenberg_container_override,
            port=3000,
            family="GOTENBERG",
        )
        tika_endpoint = self._private_endpoint(
            service="tika",
            override=self.tika_container_override,
            port=9998,
            family="TIKA",
        )
        boundary, conversion_body = self._gotenberg_body(normalized_marker)
        gotenberg_status, gotenberg_content_type, pdf = self._request(
            endpoint=gotenberg_endpoint,
            method="POST",
            path="/forms/chromium/convert/html",
            body=conversion_body,
            headers={
                "Accept": "application/pdf",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(conversion_body)),
            },
            maximum_response_bytes=MAX_PDF_BYTES,
            failure_family="GOTENBERG_NETWORK_PEER_UNREACHABLE",
        )
        if gotenberg_status != 200:
            raise RuntimeError(f"GOTENBERG_CONVERSION_HTTP_{gotenberg_status}")
        if not pdf.startswith(b"%PDF-"):
            raise RuntimeError("GOTENBERG_OUTPUT_NOT_PDF")
        self._validate_pdf_size(len(pdf))

        tika_status, _tika_content_type, extracted = self._request(
            endpoint=tika_endpoint,
            method="PUT",
            path="/tika",
            body=pdf,
            headers={
                "Accept": "text/plain; charset=utf-8",
                "Content-Type": "application/pdf",
                "Content-Length": str(len(pdf)),
            },
            maximum_response_bytes=MAX_EXTRACTED_TEXT_BYTES,
            failure_family="TIKA_NETWORK_PEER_UNREACHABLE",
        )
        if tika_status != 200:
            raise RuntimeError(f"TIKA_EXTRACTION_HTTP_{tika_status}")
        extracted_text = extracted.decode("utf-8", errors="replace")
        if normalized_marker not in extracted_text:
            raise RuntimeError("TIKA_MARKER_NOT_EXTRACTED")

        pdf_sha256 = hashlib.sha256(pdf).hexdigest()
        if not _SHA256_RE.fullmatch(pdf_sha256):
            raise RuntimeError("DOCUMENT_NETWORK_PEER_HASH_INVALID")
        return {
            "ok": True,
            "status": "DOCUMENT_PIPELINE_LIVE_CANARY_VERIFIED",
            "gotenberg": {
                "container": gotenberg_endpoint.container,
                "httpStatus": gotenberg_status,
                "contentType": gotenberg_content_type,
                "pdfBytes": len(pdf),
                "maxPdfBytes": MAX_PDF_BYTES,
                "pdfSha256": pdf_sha256,
            },
            "tika": {
                "container": tika_endpoint.container,
                "httpStatus": tika_status,
                "extractedCharacters": len(extracted_text),
                "maxPdfBytes": MAX_PDF_BYTES,
                "markerVerified": True,
            },
            "probe": {
                "execution": "host_broker_private_container_endpoint",
                "discovery": "compose_service_label_and_docker_inspect",
                "network": "docker_private_container_endpoint",
                "genericShellUsed": False,
                "dockerExecUsed": False,
                "hostPublishedPortUsed": False,
                "networkMutationUsed": False,
            },
            "sourcePersisted": False,
            "outputPersisted": False,
            "documentContentReturned": False,
            "secretValuesReturned": False,
        }
