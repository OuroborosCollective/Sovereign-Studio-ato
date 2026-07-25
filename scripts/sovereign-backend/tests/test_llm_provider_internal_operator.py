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
    from openrouter_provider_runtime import register_openrouter_provider_runtime  # noqa: E402
else:
    register_openrouter_provider_runtime = None


def test_internal_openrouter_operator_contract_is_present_without_optional_flask() -> None:
    runtime = (BACKEND / "openrouter_provider_runtime.py").read_text("utf-8")
    app = (BACKEND / "app.py").read_text("utf-8")
    assert '"/api/internal/llm/openrouter/status"' in runtime
    assert '"/api/internal/llm/openrouter/activate"' in runtime
    assert "register_llm_provider_routes" not in app


def _identity_decorator(function):
    return function


def _build_app(monkeypatch, query_calls: list[str]) -> Flask:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "owner-bridge-key")
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", "/tmp/sovereign-openrouter-test")
    app = Flask(__name__)

    def query(sql: str, params=(), one: bool = False, write: bool = False):
        del params, one, write
        query_calls.append(sql)
        if "selectable_models" in sql and "llm_provider_deployments" in sql:
            return {
                "status": "ready",
                "key_hint": "…1234",
                "last_canary_request_id": "req_openrouter",
                "last_canary_at": "2026-07-25T12:00:00Z",
                "last_error_code": None,
                "selectable_models": 7,
            }
        raise AssertionError(f"Unexpected query: {sql[:120]}")

    register_openrouter_provider_runtime(
        app,
        require_admin=_identity_decorator,
        require_session=_identity_decorator,
        query=query,
        get_connection=lambda: (_ for _ in ()).throw(AssertionError("DB connection not expected")),
        audit=lambda *_args, **_kwargs: None,
    )
    return app


@pytest.mark.skipif(Flask is None, reason="Flask is validated in the full backend CI image")
def test_internal_openrouter_status_requires_owner_service_key(monkeypatch) -> None:
    query_calls: list[str] = []
    app = _build_app(monkeypatch, query_calls)
    response = app.test_client().get("/api/internal/llm/openrouter/status")

    assert response.status_code == 401
    assert query_calls == []


@pytest.mark.skipif(Flask is None, reason="Flask is validated in the full backend CI image")
def test_internal_openrouter_status_is_secret_free(monkeypatch) -> None:
    query_calls: list[str] = []
    app = _build_app(monkeypatch, query_calls)
    response = app.test_client().get(
        "/api/internal/llm/openrouter/status",
        headers={"X-Sovereign-Owner-Request-Key": "owner-bridge-key"},
    )
    payload: dict[str, Any] = response.get_json()

    assert response.status_code == 200
    assert payload["transport"] == "openrouter"
    assert payload["routeId"] == "openrouter-paid-gpt-5-4-mini"
    assert payload["selectableModels"] == 7
    assert payload["secretValuesReturned"] is False
    assert "apiKey" not in str(payload)
    assert len(query_calls) == 1


@pytest.mark.skipif(Flask is None, reason="Flask is validated in the full backend CI image")
def test_internal_openrouter_activation_rejects_unknown_route_before_db_or_secret_access(monkeypatch) -> None:
    query_calls: list[str] = []
    app = _build_app(monkeypatch, query_calls)
    response = app.test_client().post(
        "/api/internal/llm/openrouter/activate",
        headers={"X-Sovereign-Owner-Request-Key": "owner-bridge-key"},
        json={"routeId": "unknown-provider-route"},
    )

    assert response.status_code == 404
    assert query_calls == []
