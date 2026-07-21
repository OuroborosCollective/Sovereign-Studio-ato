from __future__ import annotations

from typing import Any

import pytest

from owner_input_client import ControllerRuntimeClient, OwnerInputClient, ProviderRuntimeClient


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
    monkeypatch.setenv("SOVEREIGN_BACKEND_PUBLIC_URL", "https://sovereign-backend.arelorian.de")
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
    assert result["owner_url"] == (
        "https://sovereign-backend.arelorian.de/owner-approvals"
        "?request_id=11111111-1111-4111-8111-111111111111"
    )


def test_create_request_allows_litellm_provider_target(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_BACKEND_INTERNAL_URL", "http://backend:8787")
    monkeypatch.setenv("SOVEREIGN_BACKEND_PUBLIC_URL", "https://sovereign-backend.arelorian.de")
    request_id = "44444444-4444-4444-8444-444444444444"
    session = FakeSession([
        FakeResponse(201, {
            "ok": True,
            "request": {
                "id": request_id,
                "targetId": "litellm_provider_key",
                "status": "pending",
            },
        })
    ])
    client = OwnerInputClient(session=session)

    result = client.create_request(
        target_id="litellm_provider_key",
        title="Free-Route Providerzugang",
        reason="Eine LiteLLM-Free-Route benötigt eine geschützte Owner-Eingabe.",
    )

    call = session.calls[0]
    assert call["json"]["targetId"] == "litellm_provider_key"
    assert call["json"]["fieldLabel"] == "LiteLLM Provider API-Key"
    assert "protectedValue" not in call["json"]
    assert result["owner_url"] == (
        "https://sovereign-backend.arelorian.de/owner-approvals"
        f"?request_id={request_id}"
    )
    assert result["llm_can_receive_protected_value"] is False


def test_activate_provider_route_uses_private_owner_bridge(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_BACKEND_INTERNAL_URL", "http://backend:8787")
    route_id = "litellm-admin-301e7b07f7a4bbcb95b4731b"
    request_id = "44444444-4444-4444-8444-444444444444"
    session = FakeSession([
        FakeResponse(200, {
            "ok": True,
            "status": "ready",
            "routeId": route_id,
            "modelId": "sovereign-free-route",
        })
    ])
    client = OwnerInputClient(session=session)

    result = client.activate_provider_route(
        route_id=route_id,
        owner_request_id=request_id,
    )

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == (
        "http://backend:8787/api/internal/llm/provider-deployments/"
        f"{route_id}/activate"
    )
    assert call["headers"]["X-Sovereign-Owner-Request-Key"] == "bridge-key"
    assert call["json"] == {"ownerRequestId": request_id}
    assert call["timeout"] == 180
    assert result["status"] == "ready"
    assert result["protected_values_returned"] is False


def test_status_returns_metadata_only(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_BACKEND_PUBLIC_URL", "https://sovereign-backend.arelorian.de")
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
    assert result["owner_url"] == (
        "https://sovereign-backend.arelorian.de/owner-approvals"
        f"?request_id={request_id}"
    )
    assert session.calls[0]["method"] == "GET"


def test_litellm_provider_route_activation_uses_private_backend_without_secret(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_BACKEND_INTERNAL_URL", "http://backend:8787")
    route_id = "litellm-admin-301e7b07f7a4bbcb95b4731b"
    session = FakeSession([
        FakeResponse(200, {
            "ok": True,
            "status": "ready",
            "routeId": route_id,
            "canaryRequestId": "req_123",
        })
    ])
    client = OwnerInputClient(session=session)

    result = client.activate_litellm_provider_route(route_id)

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == (
        "http://backend:8787/api/internal/llm/provider-deployments/"
        f"{route_id}/activate"
    )
    assert call["headers"]["X-Sovereign-Owner-Request-Key"] == "bridge-key"
    assert call["json"] is None
    assert call["timeout"] == 1200
    assert result["status"] == "ready"
    assert result["protected_values_returned"] is False
    assert "secret" not in str(call).lower()
    assert "api_key" not in str(call).lower()


def test_litellm_provider_route_activation_rejects_invalid_route_before_network(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    session = FakeSession([])
    client = OwnerInputClient(session=session)

    with pytest.raises(ValueError, match="route_id ist ungültig"):
        client.activate_litellm_provider_route("../../etc/passwd")
    assert session.calls == []


def test_rejects_non_https_public_owner_origin(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_BACKEND_PUBLIC_URL", "http://sovereign-backend.arelorian.de")

    with pytest.raises(RuntimeError, match="sichere HTTPS-Origin"):
        OwnerInputClient(session=FakeSession([]))


def test_proven_learning_plan_and_apply_use_private_backend_only(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_BACKEND_INTERNAL_URL", "http://backend:8787")
    request_id = "33333333-3333-4333-8333-333333333333"
    digest = "a" * 64
    record = {"title": "Verified pattern"}
    session = FakeSession([
        FakeResponse(200, {
            "ok": True,
            "status": "PROVEN_LEARNING_PLAN_READY",
            "confirmationSha256": digest,
            "record": record,
        }),
        FakeResponse(200, {
            "ok": True,
            "status": "PROVEN_LEARNING_PATTERN_STORED",
            "candidateId": "pattern-1",
        }),
    ])
    client = OwnerInputClient(session=session)

    plan = client.plan_proven_learning(record)
    applied = client.apply_proven_learning(
        request_id=request_id,
        confirmation_sha256=digest,
        record=record,
    )

    assert plan["status"] == "PROVEN_LEARNING_PLAN_READY"
    assert applied["status"] == "PROVEN_LEARNING_PATTERN_STORED"
    assert session.calls[0]["url"] == "http://backend:8787/api/internal/proven-learning/plan"
    assert session.calls[1]["url"] == "http://backend:8787/api/internal/proven-learning/apply"
    assert session.calls[1]["json"] == {
        "requestId": request_id,
        "confirmationSha256": digest,
        "record": record,
    }
    assert session.calls[1]["timeout"] == 120


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
        client.start_run("Nutze sk-proj-x")
    assert session.calls == []


def test_controller_external_event_uses_idempotent_owner_bridge_contract(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_BACKEND_INTERNAL_URL", "http://backend:8787")
    session = FakeSession([
        FakeResponse(201, {
            "ok": True,
            "event": {
                "eventId": "event-external-1234",
                "created": True,
                "runStateChanged": False,
            },
        })
    ])
    client = ControllerRuntimeClient(session=session)
    run_id = "run-11111111111111111111111111111111"

    result = client.record_external_event(
        run_id,
        source="github",
        external_identity="workflow:29648652001",
        event_type="workflow_completed",
        summary="Exact-head workflow completed.",
        payload={"headSha": "a" * 40, "conclusion": "success"},
    )

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == (
        "http://backend:8787/api/internal/controller/runs/"
        f"{run_id}/events/external"
    )
    assert call["json"]["source"] == "github"
    assert call["json"]["externalIdentity"] == "workflow:29648652001"
    assert call["timeout"] == 30
    assert result["status"] == "CONTROLLER_EXTERNAL_EVENT_RECORDED"
    assert result["protected_values_returned"] is False


def test_controller_external_event_rejects_secret_before_network(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    session = FakeSession([])
    client = ControllerRuntimeClient(session=session)

    with pytest.raises(ValueError, match="secret-shaped"):
        client.record_external_event(
            "run-11111111111111111111111111111111",
            source="github",
            external_identity="workflow:29648652001",
            event_type="workflow_completed",
            summary="Exact-head workflow completed.",
            payload={"token": "sk-proj-" + "x" * 30},
        )
    assert session.calls == []


def test_provider_deployments_are_read_without_protected_values(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_BACKEND_INTERNAL_URL", "http://backend:8787")
    session = FakeSession([
        FakeResponse(200, {
            "ok": True,
            "status": "PROVIDER_DEPLOYMENTS_READ",
            "deployments": [{
                "routeId": "litellm-admin-route-1",
                "status": "awaiting_owner_input",
                "keyFingerprintPresent": False,
            }],
            "protectedValuesReturned": False,
        })
    ])
    client = ProviderRuntimeClient(session=session)

    result = client.list_deployments()

    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "http://backend:8787/api/internal/llm/provider-deployments"
    assert result["protected_values_returned"] is False
    assert result["deployments"][0]["routeId"] == "litellm-admin-route-1"


def test_provider_activation_accepts_only_route_identity(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    monkeypatch.setenv("SOVEREIGN_BACKEND_INTERNAL_URL", "http://backend:8787")
    route_id = "litellm-admin-301e7b07f7a4bbcb95b4731b"
    session = FakeSession([
        FakeResponse(200, {
            "ok": True,
            "status": "ready",
            "routeId": route_id,
            "modelId": "sovereign-groq-model",
        })
    ])
    client = ProviderRuntimeClient(session=session)

    result = client.activate(route_id)

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == (
        "http://backend:8787/api/internal/llm/provider-deployments/"
        f"{route_id}/activate"
    )
    assert call["json"] is None
    assert result["secret_argument_accepted"] is False
    assert result["protected_values_returned"] is False


def test_provider_activation_rejects_path_escape_before_network(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    session = FakeSession([])
    client = ProviderRuntimeClient(session=session)

    with pytest.raises(ValueError, match="route_id ist ungültig"):
        client.activate("../../owner-secret")
    assert session.calls == []


def test_status_rejects_non_uuid_before_network(monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "bridge-key")
    session = FakeSession([])
    client = OwnerInputClient(session=session)

    with pytest.raises(ValueError, match="ungültig"):
        client.status("../../etc/passwd")
    assert session.calls == []
