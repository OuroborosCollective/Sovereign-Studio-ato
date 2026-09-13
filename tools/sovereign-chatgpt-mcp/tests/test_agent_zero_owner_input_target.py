from __future__ import annotations

from typing import Any

from owner_input_client import OwnerInputClient


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


def test_agent_zero_owner_input_target_is_metadata_only(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_BACKEND_INTERNAL_URL", "http://backend:8787")
    request_id = "44444444-4444-4444-8444-444444444444"
    session = FakeSession([
        FakeResponse(201, {
            "ok": True,
            "request": {
                "id": request_id,
                "targetId": "agent_zero_api_key",
                "status": "pending",
            },
        })
    ])
    client = OwnerInputClient(session=session)

    result = client.create_request(
        target_id="agent_zero_api_key",
        title="Agent Zero Repository-A2A aktivieren",
        reason="Der Backend-A2A-Pfad benötigt eine geschützte Owner-Eingabe.",
    )

    call = session.calls[0]
    assert call["json"]["targetId"] == "agent_zero_api_key"
    assert call["json"]["fieldLabel"] == "Agent Zero API-Key"
    assert "protectedValue" not in call["json"]
    assert result["llm_can_receive_protected_value"] is False
    assert result["protected_value_transport"] == "owner_ui_only"
