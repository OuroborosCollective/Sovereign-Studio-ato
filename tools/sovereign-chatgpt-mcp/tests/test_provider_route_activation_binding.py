from __future__ import annotations

from typing import Any

from owner_input_client import ProviderRuntimeClient


class FakeProviderRuntimeClient(ProviderRuntimeClient):
    def __init__(self) -> None:
        self.activation: str | None = None

    def openrouter_activate(self, route_id: str = "openrouter-paid-gpt-5-4-mini") -> dict[str, Any]:
        selected = self._route_id(route_id)
        self.activation = selected
        return {
            "ok": True,
            "routeId": selected,
            "transport": "openrouter",
            "protected_values_returned": False,
            "secret_argument_accepted": False,
        }


def test_activation_delegates_to_direct_openrouter_without_legacy_owner_binding() -> None:
    client = FakeProviderRuntimeClient()

    result = client.activate("openrouter-paid-gpt-5-4-mini")

    assert result["ok"] is True
    assert client.activation == "openrouter-paid-gpt-5-4-mini"
    assert result["transport"] == "openrouter"
    assert result["protected_values_returned"] is False
    assert "ownerRequestId" not in result


def test_activation_rejects_invalid_route_before_direct_provider_call() -> None:
    client = FakeProviderRuntimeClient()

    try:
        client.activate("../../owner-secret")
    except ValueError as exc:
        assert "route_id ist ungültig" in str(exc)
    else:
        raise AssertionError("Activation must fail closed for an invalid route identity")

    assert client.activation is None
