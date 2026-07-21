from __future__ import annotations

from typing import Any

from owner_input_client import ProviderRuntimeClient


class FakeProviderRuntimeClient(ProviderRuntimeClient):
    def __init__(self, deployments: list[dict[str, Any]]) -> None:
        self._deployments = deployments
        self.activation: tuple[str, str] | None = None

    def list_deployments(self) -> dict[str, Any]:
        return {
            "deployments": self._deployments,
            "protected_values_returned": False,
        }

    def activate_provider_route(self, *, route_id: str, owner_request_id: str) -> dict[str, Any]:
        self.activation = (route_id, owner_request_id)
        return {
            "ok": True,
            "routeId": route_id,
            "ownerRequestId": owner_request_id,
            "protected_values_returned": False,
        }


def test_activation_resolves_owner_request_from_secret_free_metadata() -> None:
    request_id = "baf81781-6c12-4913-99b1-20fe38db6f56"
    client = FakeProviderRuntimeClient([
        {
            "routeId": "sovereign-groq-openai-gpt-oss-20b-test",
            "ownerRequestId": request_id,
            "keyHint": "groq-…",
        }
    ])

    result = client.activate("sovereign-groq-openai-gpt-oss-20b-test")

    assert result["ok"] is True
    assert client.activation == ("sovereign-groq-openai-gpt-oss-20b-test", request_id)
    assert result["protected_values_returned"] is False


def test_activation_fails_closed_without_bound_owner_request() -> None:
    client = FakeProviderRuntimeClient([
        {"routeId": "sovereign-groq-openai-gpt-oss-20b-test", "ownerRequestId": None}
    ])

    try:
        client.activate("sovereign-groq-openai-gpt-oss-20b-test")
    except RuntimeError as exc:
        assert "Owner-Request-ID" in str(exc)
    else:
        raise AssertionError("Activation must fail closed without owner request metadata")
