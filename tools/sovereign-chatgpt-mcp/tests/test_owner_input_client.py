from __future__ import annotations

from typing import Any

import pytest

from owner_input_client import ControllerRuntimeClient, OwnerInputClient


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append({
            "method": method,
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        })
        if not self.responses:
            raise AssertionError("Unexpected request")
        return self.responses.pop(0)


def test_create_request_sends_openai_target_and_no_protected_value(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_BACKEND_INTERNAL_URL", "http://backend:8787")
    session = FakeSession([
        FakeResponse(201, {
            "ok": True,
            "request": {
                "id": "11111111-1111-4111-8111-111111111111",
                "targetId": "openai_api_key",
                "status": "pending",
            },
        })
    ])
    client = OwnerInputClient(session=session)

    result = client.create_request(
        target_id="openai_api_key",
        title="OpenAI Agents SDK benötigt Zugang",
        reason="Der bestätigte Serverlauf kann ohne OpenAI-Zugang nicht fortgesetzt werden.",
    )

    call = session.calls[0]
    assert call["url"] == "http://backend:8787/api/internal/owner-input/requests"
    assert call["headers"]["X-Sovereign-Owner-Request-Key"] == "bridge-key"
    assert call["json"]["targetId"] == "openai_api_key"
    assert "protectedValue" not in call["json"]
    assert "secret" not in " ".join(call["json"].keys()).lower()
    assert result["llm_can_receive_protected_value"] is False
    assert result["protected_value_transport"] == "owner_ui_only"


def test_status_returns_metadata_only(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    request_id = "22222222-2222-4222-8222-222222222222"
    session = FakeSession([
        FakeResponse(200, {
            "ok": True,
            "request": {"id": request_id, "status": "consumed", "resultCode": "target_updated"},
        })
    ])
    client = OwnerInputClient(session=session)

    result = client.status(request_id)

    assert result["protected_value_returned"] is False
    assert "protectedValue" not in result["request"]
    assert session.calls[0]["method"] == "GET"


def test_client_requires_private_bridge_key(monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_OWNER_REQUEST_KEY", raising=False)
    client = OwnerInputClient(session=FakeSession([]))

    with pytest.raises(RuntimeError, match="nicht konfiguriert"):
        client.create_request(target_id="openai_api_key", title="Titel", reason="Begründung")


def test_controller_start_sends_bounded_non_secret_mission(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_BACKEND_INTERNAL_URL", "http://backend:8787")
    session = FakeSession([
        FakeResponse(202, {
            "runtime": "openai-agents-sdk",
            "runId": "run-11111111111111111111111111111111",
            "status": "WAITING_FOR_OWNER",
        })
    ])
    client = ControllerRuntimeClient(session=session)

    result = client.start_run("Prüfe die Agents-SDK-Runtime.", "Canary ohne Secrets.")

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "http://backend:8787/api/internal/controller/runs"
    assert call["json"] == {
        "mission": "Prüfe die Agents-SDK-Runtime.",
        "evidence": "Canary ohne Secrets.",
    }
    assert call["timeout"] == 1200
    assert result["runtime"] == "openai-agents-sdk"


def test_controller_start_rejects_secret_shaped_input_before_network(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    session = FakeSession([])
    client = ControllerRuntimeClient(session=session)

    with pytest.raises(ValueError, match="Secret-förmiger"):
        client.start_run("Nutze sk-proj-not-allowed-in-tools")
    assert session.calls == []


def test_status_rejects_non_uuid_before_network(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    session = FakeSession([])
    client = OwnerInputClient(session=session)

    with pytest.raises(ValueError, match="ungültig"):
        client.status("../../etc/passwd")
    assert session.calls == []
