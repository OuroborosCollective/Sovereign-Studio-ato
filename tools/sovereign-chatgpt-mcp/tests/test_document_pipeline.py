from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import pytest

from document_pipeline import MAX_PDF_BYTES, DocumentPipelineRuntime, _NETWORK_CANARY_SCRIPT


ROOT = Path(__file__).resolve().parents[1]


def _verified_result(*, pdf_bytes: int = 4096) -> dict[str, Any]:
    return {
        "ok": True,
        "status": "DOCUMENT_PIPELINE_LIVE_CANARY_VERIFIED",
        "gotenberg": {
            "container": "gotenberg",
            "httpStatus": 200,
            "contentType": "application/pdf",
            "pdfBytes": pdf_bytes,
            "maxPdfBytes": MAX_PDF_BYTES,
            "pdfSha256": "a" * 64,
        },
        "tika": {
            "container": "tika",
            "httpStatus": 200,
            "extractedCharacters": 96,
            "maxPdfBytes": MAX_PDF_BYTES,
            "markerVerified": True,
        },
        "sourcePersisted": False,
        "outputPersisted": False,
        "documentContentReturned": False,
        "secretValuesReturned": False,
    }


def test_mcp_image_packages_document_pipeline_module() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text("utf-8")
    assert "a2a_runtime_client.py document_pipeline.py owner_input_widget.py" in dockerfile


def test_live_canary_runs_fixed_node_probe_with_compose_service_dns(monkeypatch) -> None:
    runtime = DocumentPipelineRuntime()
    calls: list[dict[str, Any]] = []

    def fake_run(argv, *, capture_output, text, timeout, check):
        calls.append({
            "argv": argv,
            "capture_output": capture_output,
            "text": text,
            "timeout": timeout,
            "check": check,
        })
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(_verified_result()) + "\n",
            stderr="",
        )

    monkeypatch.setattr("document_pipeline.subprocess.run", fake_run)

    result = runtime.live_canary()

    assert result["ok"] is True
    assert result["status"] == "DOCUMENT_PIPELINE_LIVE_CANARY_VERIFIED"
    assert result["gotenberg"]["pdfSha256"] == "a" * 64
    assert result["tika"]["markerVerified"] is True
    assert result["probe"] == {
        "container": "gpt-browserless",
        "execution": "fixed_node_network_peer",
        "genericShellUsed": False,
        "network": "gpt-tools-compose-network",
    }
    assert result["documentContentReturned"] is False
    assert result["secretValuesReturned"] is False

    command = calls[0]["argv"]
    assert command[:2] == ["docker", "exec"]
    assert "HTTP_PROXY=" in command
    assert "HTTPS_PROXY=" in command
    assert "ALL_PROXY=" in command
    assert "NO_PROXY=*" in command
    assert command[command.index("node") + 1] == "-e"
    assert command[command.index("-e", command.index("node")) + 1] == _NETWORK_CANARY_SCRIPT
    assert "SOVEREIGN_DOCUMENT_PIPELINE_CANARY" in command
    assert "gpt-browserless" in command
    assert "gotenberg" in command
    assert "tika" in command
    assert "gpt-gotenberg" not in command
    assert "gpt-tika" not in command
    assert calls[0]["check"] is False


def test_document_runtime_defaults_to_stable_compose_service_aliases() -> None:
    runtime = DocumentPipelineRuntime()

    assert runtime.probe_container == "gpt-browserless"
    assert runtime.gotenberg_container == "gotenberg"
    assert runtime.tika_container == "tika"


def test_network_probe_uses_only_fixed_service_urls_and_in_memory_artifacts() -> None:
    assert "http://${gotenbergHost}:3000/forms/chromium/convert/html" in _NETWORK_CANARY_SCRIPT
    assert "http://${tikaHost}:9998/tika" in _NETWORK_CANARY_SCRIPT
    assert "new FormData()" in _NETWORK_CANARY_SCRIPT
    assert "new Blob([html]" in _NETWORK_CANARY_SCRIPT
    assert "writeFile" not in _NETWORK_CANARY_SCRIPT
    assert "child_process" not in _NETWORK_CANARY_SCRIPT


def test_live_canary_preserves_precise_network_peer_failure_family(monkeypatch) -> None:
    runtime = DocumentPipelineRuntime()

    monkeypatch.setattr(
        "document_pipeline.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            1,
            stdout="",
            stderr=json.dumps({"failureFamily": "GOTENBERG_NETWORK_PEER_UNREACHABLE"}) + "\n",
        ),
    )

    with pytest.raises(RuntimeError, match="GOTENBERG_NETWORK_PEER_UNREACHABLE"):
        runtime.live_canary()


def test_live_canary_rejects_invalid_peer_result(monkeypatch) -> None:
    runtime = DocumentPipelineRuntime()
    monkeypatch.setattr(
        "document_pipeline.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout="not-json\n",
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="DOCUMENT_NETWORK_PEER_RESULT_INVALID"):
        runtime.live_canary()


def test_live_canary_accepts_pdf_at_exactly_33_mib(monkeypatch) -> None:
    runtime = DocumentPipelineRuntime()
    monkeypatch.setattr(
        "document_pipeline.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout=json.dumps(_verified_result(pdf_bytes=MAX_PDF_BYTES)) + "\n",
            stderr="",
        ),
    )

    result = runtime.live_canary()

    assert result["gotenberg"]["pdfBytes"] == MAX_PDF_BYTES
    assert result["tika"]["markerVerified"] is True


def test_live_canary_rejects_peer_result_larger_than_33_mib(monkeypatch) -> None:
    runtime = DocumentPipelineRuntime()
    monkeypatch.setattr(
        "document_pipeline.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout=json.dumps(_verified_result(pdf_bytes=MAX_PDF_BYTES + 1)) + "\n",
            stderr="",
        ),
    )

    with pytest.raises(RuntimeError, match="GOTENBERG_OUTPUT_SIZE_INVALID"):
        runtime.live_canary()


def test_live_canary_rejects_unbounded_marker_before_docker_exec(monkeypatch) -> None:
    runtime = DocumentPipelineRuntime()
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("docker exec must not run")

    monkeypatch.setattr("document_pipeline.subprocess.run", fake_run)
    with pytest.raises(ValueError, match="1 to 160"):
        runtime.live_canary("x" * 161)
    assert called is False


def test_document_runtime_rejects_unsafe_container_names(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_DOCUMENT_PROBE_CONTAINER", "gpt-browserless;rm")
    with pytest.raises(RuntimeError, match="safe container name"):
        DocumentPipelineRuntime()


def test_pdf_size_limit_accepts_33_mib_and_rejects_the_next_byte() -> None:
    runtime = DocumentPipelineRuntime()
    assert MAX_PDF_BYTES == 33 * 1024 * 1024
    runtime._validate_pdf_size(MAX_PDF_BYTES)
    with pytest.raises(RuntimeError, match="GOTENBERG_OUTPUT_SIZE_INVALID"):
        runtime._validate_pdf_size(MAX_PDF_BYTES + 1)
