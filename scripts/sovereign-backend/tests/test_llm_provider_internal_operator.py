from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest

try:
    from flask import Flask
except ModuleNotFoundError:  # Lightweight MCP test image; full backend CI installs Flask.
    Flask = None  # type: ignore[assignment]

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

if Flask is not None:
    from llm_provider_runtime import register_llm_provider_routes  # noqa: E402
else:
    register_llm_provider_routes = None


def test_internal_operator_contract_is_present_without_optional_flask() -> None:
    runtime = (BACKEND / "llm_provider_runtime.py").read_text("utf-8")
    assert '"/api/internal/llm/provider-deployments"' in runtime
    assert '"/api/internal/llm/provider-deployments/<route_id>/activate"' in runtime


def _identity_decorator(function):
    return function


def _build_app(monkeypatch, query_calls: list[str]) -> Flask:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "owner-bridge-key")
    app = Flask(__name__)

    def query(sql: str, params=(), one: bool = False, write: bool = False):
        query_calls.append(sql)
        if "LIMIT 100" in sql and "llm_provider_deployments" in sql:
            return [{
                "routeId": "litellm-admin-route-1",
                "providerName": "Groq",
                "providerPrefix": "groq",
                "upstreamModelId": "model-1",
                "litellmModelName": "sovereign-groq-model-1",
                "billingCategory": "free",
                "markupMultiplier": 0,
                "pricingVerifiedAt": None,
                "keyHint": "",
                "status": "awaiting_owner_input",
                "lastErrorCode": "",
                "lastCanaryRequestId": None,
                "lastCanaryAt": None,
                "ownerRequestId": "11111111-1111-4111-8111-111111111111",
                "ownerInputStatus": "consumed",
                "ownerInputResultCode": "target_updated",
                "fundingMode": "provider_free_quota",
                "routeDisabled": True,
                "routePricingVerified": False,
                "keyFingerprintPresent": False,
            }]
        raise AssertionError(f"Unexpected query: {sql[:120]}")

    register_llm_provider_routes(
        app,
        require_admin=_identity_decorator,
        query=query,
        get_connection=lambda: (_ for _ in ()).throw(AssertionError("DB connection not expected")),
        get_current_admin=lambda: None,
        audit=lambda *_args, **_kwargs: None,
    )
    return app


@pytest.mark.skipif(Flask is None, reason="Flask is validated in the full backend CI image")
def test_internal_provider_metadata_requires_owner_service_key(monkeypatch) -> None:
    query_calls: list[str] = []
    app = _build_app(monkeypatch, query_calls)
    client = app.test_client()

    response = client.get("/api/internal/llm/provider-deployments")

    assert response.status_code == 401
    assert query_calls == []


@pytest.mark.skipif(Flask is None, reason="Flask is validated in the full backend CI image")
def test_internal_provider_metadata_is_secret_free(monkeypatch) -> None:
    query_calls: list[str] = []
    app = _build_app(monkeypatch, query_calls)
    client = app.test_client()

    response = client.get(
        "/api/internal/llm/provider-deployments",
        headers={"X-Sovereign-Owner-Request-Key": "owner-bridge-key"},
    )
    payload: dict[str, Any] = response.get_json()

    assert response.status_code == 200
    assert payload["protectedValuesReturned"] is False
    assert payload["deployments"][0]["routeId"] == "litellm-admin-route-1"
    assert "apiKey" not in str(payload)
    assert len(query_calls) == 1


@pytest.mark.skipif(Flask is None, reason="Flask is validated in the full backend CI image")
def test_internal_activation_rejects_invalid_route_before_db_or_secret_access(monkeypatch) -> None:
    query_calls: list[str] = []
    app = _build_app(monkeypatch, query_calls)
    client = app.test_client()

    response = client.post(
        "/api/internal/llm/provider-deployments/%2E%2E%2Fowner-secret/activate",
        headers={"X-Sovereign-Owner-Request-Key": "owner-bridge-key"},
    )

    assert response.status_code in {400, 404}
    assert query_calls == []
