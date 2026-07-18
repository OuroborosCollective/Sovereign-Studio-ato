from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any


MIN_PDF_BYTES = 200
MAX_PDF_BYTES = 33 * 1024 * 1024
_CONTAINER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_NETWORK_CANARY_SCRIPT = r"""
const crypto = require('crypto');

const [marker, gotenbergHost, tikaHost, minimumRaw, maximumRaw] = process.argv.slice(1);
const minimum = Number(minimumRaw);
const maximum = Number(maximumRaw);

const fail = (family, details = {}) => {
  process.stderr.write(JSON.stringify({ failureFamily: family, ...details }) + '\n');
  process.exit(1);
};

const escapeHtml = (value) => value.replace(/[&<>\"]/g, (character) => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '\"': '&quot;',
})[character]);

(async () => {
  const html = '<!doctype html><html><head><meta charset="utf-8">' +
    '<title>Sovereign document canary</title></head><body><h1>' +
    escapeHtml(marker) +
    '</h1><p>Gotenberg to Tika live evidence.</p></body></html>';
  const form = new FormData();
  form.append('files', new Blob([html], { type: 'text/html' }), 'index.html');

  let generated;
  try {
    generated = await fetch(
      `http://${gotenbergHost}:3000/forms/chromium/convert/html`,
      { method: 'POST', body: form },
    );
  } catch (error) {
    fail('GOTENBERG_NETWORK_PEER_UNREACHABLE', { errorType: error?.name || 'Error' });
  }
  if (generated.status !== 200) {
    fail(`GOTENBERG_CONVERSION_HTTP_${generated.status}`);
  }
  const pdf = Buffer.from(await generated.arrayBuffer());
  if (!pdf.subarray(0, 5).equals(Buffer.from('%PDF-'))) {
    fail('GOTENBERG_OUTPUT_NOT_PDF');
  }
  if (pdf.length < minimum || pdf.length > maximum) {
    fail('GOTENBERG_OUTPUT_SIZE_INVALID', { pdfBytes: pdf.length });
  }

  let extracted;
  try {
    extracted = await fetch(`http://${tikaHost}:9998/tika`, {
      method: 'PUT',
      headers: {
        'Accept': 'text/plain; charset=utf-8',
        'Content-Type': 'application/pdf',
      },
      body: pdf,
    });
  } catch (error) {
    fail('TIKA_NETWORK_PEER_UNREACHABLE', { errorType: error?.name || 'Error' });
  }
  const extractedText = await extracted.text();
  if (extracted.status !== 200) {
    fail(`TIKA_EXTRACTION_HTTP_${extracted.status}`);
  }
  if (!extractedText.includes(marker)) {
    fail('TIKA_MARKER_NOT_EXTRACTED', { extractedCharacters: extractedText.length });
  }

  process.stdout.write(JSON.stringify({
    ok: true,
    status: 'DOCUMENT_PIPELINE_LIVE_CANARY_VERIFIED',
    gotenberg: {
      container: gotenbergHost,
      httpStatus: generated.status,
      contentType: String(generated.headers.get('content-type') || '').slice(0, 120),
      pdfBytes: pdf.length,
      maxPdfBytes: maximum,
      pdfSha256: crypto.createHash('sha256').update(pdf).digest('hex'),
    },
    tika: {
      container: tikaHost,
      httpStatus: extracted.status,
      extractedCharacters: extractedText.length,
      maxPdfBytes: maximum,
      markerVerified: true,
    },
    sourcePersisted: false,
    outputPersisted: false,
    documentContentReturned: false,
    secretValuesReturned: false,
  }) + '\n');
})().catch((error) => fail('DOCUMENT_NETWORK_PEER_CANARY_FAILED', {
  errorType: error?.name || 'Error',
}));
"""


class DocumentPipelineRuntime:
    """Run bounded live Tika/Gotenberg evidence inside the fixed gpt-tools network."""

    def __init__(self) -> None:
        self.tika_container = self._container_name(
            os.getenv("SOVEREIGN_TIKA_CONTAINER", "gpt-tika"),
            "SOVEREIGN_TIKA_CONTAINER",
        )
        self.gotenberg_container = self._container_name(
            os.getenv("SOVEREIGN_GOTENBERG_CONTAINER", "gpt-gotenberg"),
            "SOVEREIGN_GOTENBERG_CONTAINER",
        )
        self.probe_container = self._container_name(
            os.getenv("SOVEREIGN_DOCUMENT_PROBE_CONTAINER", "gpt-browserless"),
            "SOVEREIGN_DOCUMENT_PROBE_CONTAINER",
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

    @staticmethod
    def _validate_pdf_size(size_bytes: int) -> None:
        if not MIN_PDF_BYTES <= int(size_bytes) <= MAX_PDF_BYTES:
            raise RuntimeError("GOTENBERG_OUTPUT_SIZE_INVALID")

    @staticmethod
    def _last_diagnostic(stderr: str) -> str:
        lines = [line.strip() for line in str(stderr or "").splitlines() if line.strip()]
        if not lines:
            return "DOCUMENT_NETWORK_PEER_CANARY_FAILED"
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError:
            return "DOCUMENT_NETWORK_PEER_CANARY_FAILED"
        family = str(payload.get("failureFamily") or "DOCUMENT_NETWORK_PEER_CANARY_FAILED")
        return family if re.fullmatch(r"[A-Z0-9_]{3,120}", family) else "DOCUMENT_NETWORK_PEER_CANARY_FAILED"

    def live_canary(self, marker: str = "SOVEREIGN_DOCUMENT_PIPELINE_CANARY") -> dict[str, Any]:
        normalized_marker = str(marker or "").strip()
        if not normalized_marker or len(normalized_marker) > 160:
            raise ValueError("marker must contain 1 to 160 characters")

        completed = subprocess.run(
            [
                "docker",
                "exec",
                "-e",
                "HTTP_PROXY=",
                "-e",
                "HTTPS_PROXY=",
                "-e",
                "ALL_PROXY=",
                "-e",
                "NO_PROXY=*",
                "-e",
                "NODE_NO_WARNINGS=1",
                self.probe_container,
                "node",
                "-e",
                _NETWORK_CANARY_SCRIPT,
                normalized_marker,
                self.gotenberg_container,
                self.tika_container,
                str(MIN_PDF_BYTES),
                str(MAX_PDF_BYTES),
            ],
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(self._last_diagnostic(completed.stderr))
        try:
            result = json.loads(completed.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise RuntimeError("DOCUMENT_NETWORK_PEER_RESULT_INVALID") from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError("DOCUMENT_NETWORK_PEER_RESULT_INVALID")

        gotenberg = result.get("gotenberg")
        tika = result.get("tika")
        if not isinstance(gotenberg, dict) or not isinstance(tika, dict):
            raise RuntimeError("DOCUMENT_NETWORK_PEER_RESULT_INVALID")
        self._validate_pdf_size(int(gotenberg.get("pdfBytes") or 0))
        if int(gotenberg.get("maxPdfBytes") or 0) != MAX_PDF_BYTES:
            raise RuntimeError("DOCUMENT_NETWORK_PEER_LIMIT_MISMATCH")
        if not _SHA256_RE.fullmatch(str(gotenberg.get("pdfSha256") or "")):
            raise RuntimeError("DOCUMENT_NETWORK_PEER_HASH_INVALID")
        if int(gotenberg.get("httpStatus") or 0) != 200:
            raise RuntimeError("GOTENBERG_CONVERSION_NOT_VERIFIED")
        if int(tika.get("httpStatus") or 0) != 200 or tika.get("markerVerified") is not True:
            raise RuntimeError("TIKA_EXTRACTION_NOT_VERIFIED")
        if int(tika.get("maxPdfBytes") or 0) != MAX_PDF_BYTES:
            raise RuntimeError("DOCUMENT_NETWORK_PEER_LIMIT_MISMATCH")

        return {
            **result,
            "probe": {
                "container": self.probe_container,
                "execution": "fixed_node_network_peer",
                "genericShellUsed": False,
                "network": "gpt-tools-compose-network",
            },
            "sourcePersisted": False,
            "outputPersisted": False,
            "documentContentReturned": False,
            "secretValuesReturned": False,
        }
