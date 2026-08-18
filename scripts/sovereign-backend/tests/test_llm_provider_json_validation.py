from __future__ import annotations

from pathlib import Path
import sys

import pytest
from flask import Flask

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import llm_provider_runtime


def test_source_code_contract_for_json_dictionary_validation() -> None:
    source = (BACKEND_ROOT / "llm_provider_runtime.py").read_text("utf-8")

    attach_start = source.index('@app.route("/api/admin/llm/model-catalog/attach"')
    attach_block = source[attach_start:attach_start + 500]
    assert "isinstance(raw, dict)" in attach_block
    assert "Malformed payload; dictionary required" in attach_block

    prepare_start = source.index('@app.route("/api/admin/llm/provider-deployments/prepare"')
    prepare_block = source[prepare_start:prepare_start + 500]
    assert "isinstance(raw, dict)" in prepare_block
    assert "Malformed payload; dictionary required" in prepare_block

    refresh_start = source.index('@app.route("/api/admin/llm/provider-deployments/<route_id>/owner-input"')
    refresh_block = source[refresh_start:refresh_start + 1500]
    assert "isinstance(raw, dict)" in refresh_block
    assert "Malformed payload; dictionary required" in refresh_block

    activate_start = source.index('@app.route("/api/internal/llm/provider-deployments/<route_id>/activate"')
    activate_block = source[activate_start:activate_start + 1000]
    assert "isinstance(raw, dict)" in activate_block
    assert "Malformed payload; dictionary required" in activate_block


def mock_query(sql: str, params=(), one: bool = False, write: bool = False):
    if "SELECT deployment.route_id" in sql:
        return {
            "route_id": "litellm-test-route",
            "provider_name": "Test Provider",
            "litellm_model_name": "test-model",
            "status": "awaiting_owner_input",
            "billing_category": "standard",
            "markup_multiplier": 4,
            "priority": 50,
            "funding_mode": "provider_priced",
            "owner_request_id": "11111111-1111-4111-8111-111111111111",
        }
    if "SELECT owner_request_id" in sql:
        return {"owner_request_id": "11111111-1111-4111-8111-111111111111"}
    return None if one else []


def _registered_app() -> Flask:
    app = Flask(__name__)
    llm_provider_runtime.register_llm_provider_routes(
        app,
        require_admin=lambda fn: fn,
        query=mock_query,
        get_connection=lambda: None,
        get_current_admin=lambda: {"id": "00000000-0000-4000-8000-000000000000"},
        audit=lambda event, target, meta: None,
    )
    return app


def test_attach_litellm_model_rejects_non_dict_json() -> None:
    client = _registered_app().test_client()
    malformed_bodies = [[], [1, 2], "string_payload", 12345, True]

    for malformed in malformed_bodies:
        response = client.post("/api/admin/llm/model-catalog/attach", json=malformed)
        payload = response.get_json()
        assert response.status_code == 400
        assert payload["error"] == "Malformed payload; dictionary required"


def test_prepare_llm_provider_rejects_non_dict_json() -> None:
    client = _registered_app().test_client()
    malformed_bodies = [[], [1, 2], "string_payload", 12345, True]

    for malformed in malformed_bodies:
        response = client.post("/api/admin/llm/provider-deployments/prepare", json=malformed)
        payload = response.get_json()
        assert response.status_code == 400
        assert payload["error"] == "Malformed payload; dictionary required"


def test_refresh_owner_input_rejects_non_dict_json() -> None:
    client = _registered_app().test_client()
    malformed_bodies = [[], [1, 2], "string_payload", 12345, True]

    for malformed in malformed_bodies:
        response = client.post(
            "/api/admin/llm/provider-deployments/litellm-test-route/owner-input",
            json=malformed,
        )
        payload = response.get_json()
        assert response.status_code == 400
        assert payload["error"] == "Malformed payload; dictionary required"


def test_internal_activate_rejects_non_dict_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_REQUEST_KEY", "secret-owner-key")
    client = _registered_app().test_client()
    headers = {"X-Sovereign-Owner-Request-Key": "secret-owner-key"}
    malformed_bodies = [[], [1, 2], "string_payload", 12345, True]

    for malformed in malformed_bodies:
        response = client.post(
            "/api/internal/llm/provider-deployments/litellm-test-route/activate",
            headers=headers,
            json=malformed,
        )
        payload = response.get_json()
        assert response.status_code == 400
        assert payload["error"] == "Malformed payload; dictionary required"
