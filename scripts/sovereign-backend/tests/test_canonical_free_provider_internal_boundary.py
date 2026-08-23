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
    import free_revolver_provider_runtime as runtime  # noqa: E402
else:
    runtime = None


def _identity_decorator(function):
    return function


def test_canonical_free_provider_runtime_contract_is_present_without_optional_flask() -> None:
    source = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    contracts = (BACKEND / "free_revolver_provider_contracts.py").read_text("utf-8")

    assert '_RETIRED_FREELLMPOOL_API_BASE = "http://freellmpool:8080/v1"' in contracts
    assert "or error_code == _RETIRED_FREELLMPOOL_ERROR" in contracts
    assert '"/api/internal/llm/freellm/providers/<source_id>/discover"' in source
    assert '"/api/internal/llm/freellm/providers/<source_id>/reconcile"' in source
    assert "canonical_provider_action_required" in source


def _build_app(monkeypatch, query_calls: list[tuple[str, bool]]) -> Flask:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "owner-bridge-key")
    monkeypatch.setattr(runtime._FreeLlmEvidenceMaintainer, "start", lambda _self: None)
    app = Flask(__name__)
    retired_source = {
        "id": "c79ff468-ee08-5686-97df-756fa58b74f0",
        "label": "FreeLLMPool historical reference",
        "api_base": "http://freellmpool:8080/v1",
        "auth_mode": "managed-bearer",
        "key_fingerprint": "a" * 64,
        "models_url": "http://freellmpool:8080/v1/models",
        "status": "degraded",
        "enabled": True,
        "last_error_code": None,
        "last_http_status": 200,
        "last_discovered_at": "2026-08-23T00:00:00Z",
        "catalog_fresh": True,
    }

    def query(sql: str, params=(), one: bool = False, write: bool = False):
        del params, one
        query_calls.append((sql, write))
        if "FROM llm_revolver_provider_sources" in sql:
            return dict(retired_source)
        raise AssertionError(f"Unexpected query: {sql[:160]}")

    runtime.register_free_revolver_provider_runtime(
        app,
        require_admin=_identity_decorator,
        query=query,
        get_connection=lambda: (_ for _ in ()).throw(
            AssertionError("DB connection not expected before canonical boundary")
        ),
        get_current_admin=lambda: {"id": "00000000-0000-0000-0000-000000000001"},
        audit=lambda *_args, **_kwargs: None,
    )
    return app


@pytest.mark.skipif(Flask is None, reason="Flask is validated in the full backend CI image")
@pytest.mark.parametrize("path", [
    "/api/internal/llm/freellm/providers/c79ff468-ee08-5686-97df-756fa58b74f0/discover",
    "/api/internal/llm/freellm/providers/c79ff468-ee08-5686-97df-756fa58b74f0/reconcile",
])
def test_internal_retired_pool_mutations_fail_before_any_write(monkeypatch, path: str) -> None:
    query_calls: list[tuple[str, bool]] = []
    app = _build_app(monkeypatch, query_calls)

    response = app.test_client().post(
        path,
        headers={"X-Sovereign-Owner-Request-Key": "owner-bridge-key"},
        json={"maxModels": 1},
    )
    payload: dict[str, Any] = response.get_json()

    assert response.status_code == 409
    assert payload == {
        "error": "Dieser Provider kann nur über seine kanonische typisierte Aktion verändert werden.",
        "blocker": "canonical_provider_action_required",
        "providerSurfaceKind": "retired-reference",
        "canonicalAction": "none",
        "protectedValuesReturned": False,
    }
    assert query_calls
    assert not any(write for _sql, write in query_calls)


@pytest.mark.skipif(Flask is None, reason="Flask is validated in the full backend CI image")
def test_retired_pool_cannot_be_recreated_before_insert(monkeypatch) -> None:
    query_calls: list[tuple[str, bool]] = []
    app = _build_app(monkeypatch, query_calls)

    response = app.test_client().post(
        "/api/admin/llm/revolver-v3/providers",
        json={
            "label": "FreeLLMPool should remain historical",
            "apiBase": "http://freellmpool:8080/v1",
            "authMode": "managed-bearer",
        },
    )
    payload: dict[str, Any] = response.get_json()

    assert response.status_code == 409
    assert payload["blocker"] == "canonical_provider_action_required"
    assert payload["providerSurfaceKind"] == "retired-reference"
    assert payload["canonicalAction"] == "none"
    assert query_calls == []
