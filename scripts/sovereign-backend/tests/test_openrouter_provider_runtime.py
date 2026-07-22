from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

try:
    import flask  # noqa: F401
except ModuleNotFoundError:
    flask_stub = types.ModuleType("flask")
    flask_stub.jsonify = lambda value=None, **kwargs: value if value is not None else kwargs
    flask_stub.request = types.SimpleNamespace(json={})
    sys.modules["flask"] = flask_stub

import openrouter_provider_runtime as runtime


def _catalog_item(model_id: str = "openai/gpt-5.4-mini") -> dict:
    return {
        "id": model_id,
        "canonical_slug": f"{model_id}-20260317",
        "name": "GPT-5.4 Mini",
        "context_length": 400000,
        "top_provider": {"max_completion_tokens": 128000},
        "supported_parameters": ["tools", "tool_choice", "response_format"],
        "architecture": {
            "input_modalities": ["text"],
            "output_modalities": ["text"],
        },
        "pricing": {
            "prompt": "0.00000075",
            "input_cache_read": "0.000000075",
            "completion": "0.0000045",
        },
    }


def test_catalog_normalization_requires_paid_tool_and_structured_output_model() -> None:
    model = runtime._normalize_model(_catalog_item())

    assert model is not None
    assert model["modelId"] == "openai/gpt-5.4-mini"
    assert model["inputUsdPerMillion"] == "0.75"
    assert model["cachedInputUsdPerMillion"] == "0.075"
    assert model["outputUsdPerMillion"] == "4.5"

    missing_tools = _catalog_item("vendor/no-tools")
    missing_tools["supported_parameters"] = ["response_format"]
    assert runtime._normalize_model(missing_tools) is None

    free_model = _catalog_item("vendor/free-model:free")
    assert runtime._normalize_model(free_model) is None


def test_zdr_canary_selection_prefers_default_then_cheapest_compatible_model() -> None:
    default = {
        "openai/gpt-5.4-mini": {
            "modelId": "openai/gpt-5.4-mini",
            "inputUsdPerMillion": "0.75",
            "outputUsdPerMillion": "4.5",
        },
        "openai/gpt-4o": {
            "modelId": "openai/gpt-4o",
            "inputUsdPerMillion": "2.5",
            "outputUsdPerMillion": "10",
        },
    }
    assert runtime._select_zdr_canary_model(default) == "openai/gpt-5.4-mini"

    fallback = {
        "vendor/expensive": {
            "modelId": "vendor/expensive",
            "inputUsdPerMillion": "1",
            "outputUsdPerMillion": "8",
        },
        "vendor/cheap": {
            "modelId": "vendor/cheap",
            "inputUsdPerMillion": "0.5",
            "outputUsdPerMillion": "2",
        },
    }
    assert runtime._select_zdr_canary_model(fallback) == "vendor/cheap"
    assert runtime._route_id("vendor/cheap", default_model="vendor/cheap") == (
        runtime.OPENROUTER_ROOT_ROUTE_ID
    )


def test_zdr_contract_requires_tools_tool_choice_and_max_tokens() -> None:
    assert runtime._REQUIRED_CANARY_PARAMETERS == {
        "tools",
        "tool_choice",
        "max_tokens",
    }
    source = (BACKEND / "openrouter_provider_runtime.py").read_text("utf-8")
    assert 'f"{OPENROUTER_BASE_URL}/endpoints/zdr"' in source
    assert "model[\"modelId\"] in zdr_endpoints" in source
    assert source.count("zdr_endpoints=zdr_endpoints") == 2
    assert source.count("zdr_catalog_request_id=zdr_catalog_request_id") == 2


def test_user_catalog_exposes_only_customer_prices_and_separate_role_selection() -> None:
    source_row = {
        "id": "openrouter-paid-model",
        "model_id": "sovereign-openrouter:openai/gpt-5.4-mini",
        "model_name": "GPT-5.4 Mini",
        "disabled": False,
        "config": {
            "providerModel": "openai/gpt-5.4-mini",
            "canonicalModelSlug": "openai/gpt-5.4-mini-20260317",
            "supportedExecutionRoles": ["main", "swarm_agents"],
            "inputUsdPerMillion": "0.75",
            "cachedInputUsdPerMillion": "0.075",
            "outputUsdPerMillion": "4.5",
            "markupMultiplier": 4,
            "priceOverridesPresent": False,
            "pricingSource": "openrouter:/api/v1/models",
            "selectable": True,
        },
    }

    row = runtime._user_catalog_row(source_row)

    assert row["selectionId"] == "openai/gpt-5.4-mini"
    assert row["supportedRoles"] == ["main", "swarm_agents"]
    assert row["prices"]["input"] == "3"
    assert row["prices"]["cachedInput"] == "0.3"
    assert row["prices"]["output"] == "18"
    assert row["prices"]["inputCredits"] == 3000
    assert row["selectable"] is True
    assert row["zdrRequired"] is True
    serialized = json.dumps(row, sort_keys=True)
    assert "providerInput" not in serialized
    assert "providerOutput" not in serialized
    assert "providerCost" not in serialized
    assert "markupMultiplier" not in serialized
    assert "pricingSource" not in serialized

    admin_row = runtime._admin_catalog_row(source_row)
    assert admin_row["pricingAdmin"]["providerCost"]["input"] == "0.75"
    assert admin_row["pricingAdmin"]["customerPrice"]["input"] == "3"
    assert admin_row["pricingAdmin"]["markupMultiplier"] == 4
    assert admin_row["pricingAdmin"]["minimumMarkupMultiplier"] == 4


def test_openrouter_canary_matches_documented_chat_completions_shape() -> None:
    source = (BACKEND / "openrouter_provider_runtime.py").read_text("utf-8")
    canary_source = source.split("def _completion_canary", 1)[1].split("def _sync_catalog", 1)[0]

    assert '"temperature"' not in canary_source
    assert '"max_tokens": 64' in canary_source
    assert '"max_completion_tokens"' not in canary_source
    assert '"strict": True' not in canary_source
    assert '"require_parameters": True' in source
    assert "_openrouter_error_family(response)" in canary_source


def test_openrouter_error_tokens_are_bounded_and_secret_safe() -> None:
    assert runtime._safe_openrouter_error_token("No endpoints found that support ZDR") == (
        "no_endpoints_found_that_support_zdr"
    )
    assert runtime._safe_openrouter_error_token("x" * 200) == "x" * 60


def test_provider_policy_is_fail_closed_and_application_headers_are_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SOVEREIGN_OPENROUTER_HTTP_REFERER", raising=False)
    monkeypatch.delenv("SOVEREIGN_OPENROUTER_APP_TITLE", raising=False)
    headers = runtime._request_headers("protected-test-value")

    assert "HTTP-Referer" not in headers
    assert headers["X-OpenRouter-Title"] == "Sovereign Studio"
    assert runtime._PROVIDER_POLICY == {
        "require_parameters": True,
        "allow_fallbacks": False,
        "data_collection": "deny",
        "zdr": True,
    }


def test_protected_key_path_cannot_escape_owner_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "owner"
    root.mkdir()
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(root))
    monkeypatch.setenv(
        "SOVEREIGN_OPENROUTER_API_KEY_FILE",
        str(tmp_path / "outside-openrouter-key.txt"),
    )

    with pytest.raises(runtime.OpenRouterRuntimeError) as captured:
        runtime._key_path()

    assert captured.value.family == "openrouter_secret_path_invalid"


def test_source_contract_never_persists_or_returns_raw_openrouter_key() -> None:
    source = (BACKEND / "openrouter_provider_runtime.py").read_text("utf-8")

    assert "openrouter_api_key.txt" in source
    assert "stat.S_IMODE(info.st_mode) & 0o077" in source
    assert "for index in range(len(protected)):" in source
    assert "protected[index] = 0" in source
    assert '"secretValuesReturned": False' in source
    assert "providerPolicy" in source
    assert '"rawSecretPersistedInDatabase": False' in source
    assert '@app.route("/api/admin/llm/openrouter/models", methods=["GET"])' in source
    assert '"/api/admin/llm/openrouter/models/<route_id>/markup"' in source
    assert "not _MARKUP_MULTIPLIER <= raw_multiplier <= 32_767" in source
    assert "config=EXCLUDED.config || jsonb_build_object(" in source
