from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
from typing import Any
import zipfile

import pytest

from document_pipeline import (
    MAX_EXTRACTED_TEXT_BYTES,
    MAX_PDF_BYTES,
    DocumentPipelineRuntime,
)


ROOT = Path(__file__).resolve().parents[1]
MARKER = "SOVEREIGN_DOCUMENT_PIPELINE_CANARY"
PDF = b"%PDF-1.7\n" + (b"x" * 512)


class _DockerFixture:
    def __init__(
        self,
        *,
        names: dict[str, list[str]] | None = None,
        addresses: dict[str, str] | None = None,
        labels: dict[str, str] | None = None,
        inspect_output: dict[str, str] | None = None,
        environment: dict[str, list[str]] | None = None,
    ) -> None:
        self.names = names or {
            "gotenberg": ["gotenberg-acya-gotenberg-1"],
            "tika": ["apache-tika-2l6t-tika-1"],
        }
        self.addresses = addresses or {
            "gotenberg-acya-gotenberg-1": "172.30.0.2",
            "apache-tika-2l6t-tika-1": "172.31.0.2",
        }
        self.labels = labels or {
            "gotenberg-acya-gotenberg-1": "gotenberg",
            "apache-tika-2l6t-tika-1": "tika",
        }
        self.inspect_output = inspect_output or {}
        self.environment = environment or {
            "gotenberg-acya-gotenberg-1": [
                "GOTENBERG_API_BASIC_AUTH_USERNAME=user",
                "GOTENBERG_API_BASIC_AUTH_PASSWORD=pass",
                "UNRELATED_RUNTIME_SETTING=value",
            ]
        }
        self.calls: list[list[str]] = []

    def __call__(self, argv, *, capture_output, text, timeout, check):
        self.calls.append(list(argv))
        assert capture_output is True
        assert text is True
        assert check is False
        assert 5 <= timeout <= 30
        if argv[:2] == ["docker", "ps"]:
            label_filter = next(item for item in argv if item.startswith("label="))
            service = label_filter.rsplit("=", 1)[-1]
            stdout = "\n".join(self.names.get(service, []))
            return subprocess.CompletedProcess(argv, 0, stdout=stdout + ("\n" if stdout else ""), stderr="")
        if argv[:2] == ["docker", "inspect"]:
            container = argv[-1]
            if "{{json .Config.Env}}" in argv:
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout=json.dumps(self.environment.get(container, [])) + "\n",
                    stderr="",
                )
            if container in self.inspect_output:
                stdout = self.inspect_output[container]
            else:
                service = self.labels[container]
                networks = {
                    f"{service}-runtime_default": {
                        "IPAddress": self.addresses[container],
                    }
                }
                stdout = (
                    json.dumps({"Running": True})
                    + "|"
                    + service
                    + "|"
                    + json.dumps(networks)
                )
            return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")
        raise AssertionError(f"unexpected Docker command: {argv}")


class _Response:
    def __init__(self, status: int, payload: bytes, content_type: str) -> None:
        self.status = status
        self.payload = payload
        self.content_type = content_type

    def read(self, amount: int = -1) -> bytes:
        return self.payload if amount < 0 else self.payload[:amount]

    def getheader(self, name: str) -> str:
        return self.content_type if name.lower() == "content-type" else ""


class _Connection:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        response: _Response,
        requests: list[dict[str, Any]],
    ) -> None:
        self.host = host
        self.port = port
        self.response = response
        self.requests = requests
        self.closed = False

    def request(self, method: str, path: str, *, body: bytes, headers: dict[str, str]) -> None:
        self.requests.append({
            "host": self.host,
            "port": self.port,
            "method": method,
            "path": path,
            "body": body,
            "headers": dict(headers),
        })

    def getresponse(self) -> _Response:
        return self.response

    def close(self) -> None:
        self.closed = True


class _ConnectionFactory:
    def __init__(self, responses: list[_Response | BaseException]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.connections: list[_Connection] = []

    def __call__(self, host: str, port: int, *, timeout: int):
        assert 5 <= timeout <= 120
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        connection = _Connection(
            host=host,
            port=port,
            response=response,
            requests=self.requests,
        )
        self.connections.append(connection)
        return connection


def _success_connections(marker: str = MARKER) -> _ConnectionFactory:
    return _ConnectionFactory([
        _Response(200, PDF, "application/pdf"),
        _Response(200, f"extracted {marker}".encode(), "text/plain; charset=utf-8"),
    ])


def test_mcp_image_packages_document_pipeline_module() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text("utf-8")
    for filename in (
        "a2a_runtime_client.py",
        "document_pipeline.py",
        "owner_input_widget.py",
    ):
        assert filename in dockerfile


def test_live_canary_discovers_current_compose_services_and_uses_private_endpoints() -> None:
    docker = _DockerFixture()
    connections = _success_connections()
    runtime = DocumentPipelineRuntime(runner=docker, connection_factory=connections)

    result = runtime.live_canary()

    assert result["ok"] is True
    assert result["status"] == "DOCUMENT_PIPELINE_LIVE_CANARY_VERIFIED"
    assert result["gotenberg"]["container"] == "gotenberg-acya-gotenberg-1"
    assert result["gotenberg"]["conversionMode"] == "office_docx_to_pdf"
    assert result["gotenberg"]["requestPath"] == "/forms/libreoffice/convert"
    assert result["gotenberg"]["pdfSha256"] == hashlib.sha256(PDF).hexdigest()
    assert result["gotenberg"]["basicAuthApplied"] is True
    assert result["tika"]["container"] == "apache-tika-2l6t-tika-1"
    assert result["tika"]["markerVerified"] is True
    assert result["probe"] == {
        "execution": "host_broker_private_container_endpoint",
        "discovery": "compose_service_label_and_docker_inspect",
        "network": "docker_private_container_endpoint",
        "genericShellUsed": False,
        "dockerExecUsed": False,
        "hostPublishedPortUsed": False,
        "networkMutationUsed": False,
    }
    assert result["sourcePersisted"] is False
    assert result["outputPersisted"] is False
    assert result["documentContentReturned"] is False
    assert result["secretValuesReturned"] is False

    assert connections.requests[0]["host"] == "172.30.0.2"
    assert connections.requests[0]["port"] == 3000
    assert connections.requests[0]["method"] == "POST"
    assert connections.requests[0]["path"] == "/forms/libreoffice/convert"
    assert b'filename="sovereign-canary.docx"' in connections.requests[0]["body"]
    assert b"application/vnd.openxmlformats-officedocument.wordprocessingml.document" in connections.requests[0]["body"]
    assert connections.requests[0]["headers"]["Authorization"] == (
        "Basic " + base64.b64encode(b"user:pass").decode("ascii")
    )
    assert connections.requests[1]["host"] == "172.31.0.2"
    assert connections.requests[1]["port"] == 9998
    assert connections.requests[1]["method"] == "PUT"
    assert connections.requests[1]["path"] == "/tika"
    assert connections.requests[1]["body"] == PDF
    assert all(connection.closed for connection in connections.connections)
    assert all(command[:2] in (["docker", "ps"], ["docker", "inspect"]) for command in docker.calls)
    assert not any("exec" in command or "port" in command for command in docker.calls)
    serialized_result = json.dumps(result)
    assert "user" not in serialized_result
    assert "pass" not in serialized_result
    assert connections.requests[0]["headers"]["Authorization"] not in serialized_result


def test_office_docx_contains_marker_and_required_package_parts() -> None:
    document = DocumentPipelineRuntime._office_docx(MARKER)

    assert document.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(document)) as archive:
        assert set(archive.namelist()) == {
            "[Content_Types].xml",
            "_rels/.rels",
            "word/document.xml",
        }
        content = archive.read("word/document.xml").decode("utf-8")
    assert MARKER in content
    assert "Gotenberg LibreOffice to Tika live evidence." in content


def test_service_discovery_is_bounded_to_exact_compose_labels() -> None:
    docker = _DockerFixture()
    runtime = DocumentPipelineRuntime(runner=docker, connection_factory=_success_connections())

    runtime.live_canary()

    ps_calls = [command for command in docker.calls if command[:2] == ["docker", "ps"]]
    assert len(ps_calls) == 2
    assert "label=com.docker.compose.service=gotenberg" in ps_calls[0]
    assert "label=com.docker.compose.service=tika" in ps_calls[1]
    assert all("status=running" in command for command in ps_calls)


def test_live_canary_blocks_ambiguous_gotenberg_discovery() -> None:
    docker = _DockerFixture(names={
        "gotenberg": ["gotenberg-one", "gotenberg-two"],
        "tika": ["apache-tika-2l6t-tika-1"],
    })
    runtime = DocumentPipelineRuntime(runner=docker, connection_factory=_success_connections())

    with pytest.raises(RuntimeError, match="GOTENBERG_CONTAINER_AMBIGUOUS"):
        runtime.live_canary()


def test_live_canary_blocks_public_container_endpoint() -> None:
    docker = _DockerFixture(addresses={
        "gotenberg-acya-gotenberg-1": "8.8.8.8",
        "apache-tika-2l6t-tika-1": "172.31.0.2",
    })
    runtime = DocumentPipelineRuntime(runner=docker, connection_factory=_success_connections())

    with pytest.raises(RuntimeError, match="GOTENBERG_PRIVATE_ENDPOINT_NOT_FOUND"):
        runtime.live_canary()


def test_live_canary_blocks_incomplete_gotenberg_basic_auth() -> None:
    docker = _DockerFixture(environment={
        "gotenberg-acya-gotenberg-1": [
            "GOTENBERG_API_BASIC_AUTH_USERNAME=user",
        ]
    })
    runtime = DocumentPipelineRuntime(runner=docker, connection_factory=_success_connections())

    with pytest.raises(RuntimeError, match="GOTENBERG_BASIC_AUTH_INCOMPLETE"):
        runtime.live_canary()


def test_live_canary_allows_gotenberg_without_basic_auth_configuration() -> None:
    docker = _DockerFixture(environment={"gotenberg-acya-gotenberg-1": []})
    connections = _success_connections()
    runtime = DocumentPipelineRuntime(runner=docker, connection_factory=connections)

    result = runtime.live_canary()

    assert result["gotenberg"]["basicAuthApplied"] is False
    assert "Authorization" not in connections.requests[0]["headers"]


def test_live_canary_preserves_gotenberg_network_failure_family() -> None:
    docker = _DockerFixture()
    connections = _ConnectionFactory([OSError("unreachable")])
    runtime = DocumentPipelineRuntime(runner=docker, connection_factory=connections)

    with pytest.raises(RuntimeError, match="GOTENBERG_NETWORK_PEER_UNREACHABLE"):
        runtime.live_canary()


def test_live_canary_preserves_tika_network_failure_family() -> None:
    docker = _DockerFixture()
    connections = _ConnectionFactory([
        _Response(200, PDF, "application/pdf"),
        OSError("unreachable"),
    ])
    runtime = DocumentPipelineRuntime(runner=docker, connection_factory=connections)

    with pytest.raises(RuntimeError, match="TIKA_NETWORK_PEER_UNREACHABLE"):
        runtime.live_canary()


def test_live_canary_rejects_non_pdf_gotenberg_output() -> None:
    docker = _DockerFixture()
    connections = _ConnectionFactory([_Response(200, b"not-a-pdf" * 40, "text/plain")])
    runtime = DocumentPipelineRuntime(runner=docker, connection_factory=connections)

    with pytest.raises(RuntimeError, match="GOTENBERG_OUTPUT_NOT_PDF"):
        runtime.live_canary()


def test_live_canary_rejects_oversized_tika_response() -> None:
    docker = _DockerFixture()
    connections = _ConnectionFactory([
        _Response(200, PDF, "application/pdf"),
        _Response(200, b"x" * (MAX_EXTRACTED_TEXT_BYTES + 1), "text/plain"),
    ])
    runtime = DocumentPipelineRuntime(runner=docker, connection_factory=connections)

    with pytest.raises(RuntimeError, match="TIKA_NETWORK_PEER_UNREACHABLE_RESPONSE_TOO_LARGE"):
        runtime.live_canary()


def test_live_canary_rejects_unbounded_marker_before_docker_discovery() -> None:
    called = False

    def fail_runner(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("Docker discovery must not run")

    runtime = DocumentPipelineRuntime(runner=fail_runner, connection_factory=_success_connections())
    with pytest.raises(ValueError, match="1 to 160"):
        runtime.live_canary("x" * 161)
    assert called is False


def test_document_runtime_rejects_unsafe_container_override(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_GOTENBERG_RUNTIME_CONTAINER", "gotenberg;rm")
    with pytest.raises(RuntimeError, match="safe container name"):
        DocumentPipelineRuntime()


def test_pdf_size_limit_accepts_33_mib_and_rejects_the_next_byte() -> None:
    runtime = DocumentPipelineRuntime()
    assert MAX_PDF_BYTES == 33 * 1024 * 1024
    runtime._validate_pdf_size(MAX_PDF_BYTES)
    with pytest.raises(RuntimeError, match="GOTENBERG_OUTPUT_SIZE_INVALID"):
        runtime._validate_pdf_size(MAX_PDF_BYTES + 1)
