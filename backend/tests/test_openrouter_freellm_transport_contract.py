from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime import cognitive_llm_transport as runtime
from llm_transport import (
    FREELLM_BASE_URL,
    OPENROUTER_BASE_URL,
    route_is_direct_freellm,
    route_is_openrouter_paid,
    route_provider_model,
    route_snapshot_hashes,
    route_transport,
)


def _route(*, transport: str, profile: str, category: str, base_url: str) -> dict:
    return {
        "id": f"{transport}-route",
        "model_id": f"{transport}-alias",
        "provider": transport,
        "runtime_kind": transport,
        "base_url": base_url,
        "disabled": False,
        "config": {
            "transport": transport,
            "direct": True,
            "catalogVerified": transport == "openrouter",
            "transportCanaryVerified": transport == "openrouter",
            "selectable": transport == "openrouter",
            "supportedExecutionRoles": (
                ["main", "swarm_agents"]
                if transport == "openrouter"
                else ["free_single_agent"]
            ),
            "providerPolicy": (
                {
                    "require_parameters": True,
                    "allow_fallbacks": False,
                    "data_collection": "deny",
                    "zdr": True,
                }
                if transport == "openrouter"
                else {}
            ),
            "providerModel": (
                "openai/gpt-5.4-mini" if transport == "openrouter" else "free-model"
            ),
            "executionProfile": profile,
            "billingCategory": category,
            "billingClass": category,
            "markupMultiplier": 4 if category == "standard" else 0,
            "fundingMode": "provider_priced" if category == "standard" else "verified_zero_cost",
            "inputUsdPerMillion": 0.75 if category == "standard" else 0,
            "cachedInputUsdPerMillion": 0.075 if category == "standard" else 0,
            "outputUsdPerMillion": 4.5 if category == "standard" else 0,
            "pricingVerified": True,
            "pricingSource": "test",
        },
    }


def test_paid_and_free_transports_are_disjoint() -> None:
    paid = _route(
        transport="openrouter",
        profile="paid_swarm_6",
        category="standard",
        base_url=OPENROUTER_BASE_URL,
    )
    free = _route(
        transport="freellm",
        profile="free_single_agent",
        category="free",
        base_url=FREELLM_BASE_URL,
    )

    assert route_is_openrouter_paid(paid)
    assert not route_is_direct_freellm(paid)
    assert route_is_direct_freellm(free)
    assert not route_is_openrouter_paid(free)
    assert route_transport(paid) != route_transport(free)
    assert route_provider_model(paid) == "openai/gpt-5.4-mini"


def test_route_and_price_snapshots_change_independently() -> None:
    paid = _route(
        transport="openrouter",
        profile="paid_swarm_6",
        category="standard",
        base_url=OPENROUTER_BASE_URL,
    )
    route_hash, price_hash = route_snapshot_hashes(paid)
    repriced = {**paid, "config": {**paid["config"], "outputUsdPerMillion": 5.0}}
    same_route_hash, changed_price_hash = route_snapshot_hashes(repriced)

    assert len(route_hash) == 64
    assert len(price_hash) == 64
    assert route_hash == same_route_hash
    assert price_hash != changed_price_hash


def test_pinned_agents_sdk_route_config_keeps_transports_and_policy_disjoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, list[dict]] = {
        "provider": [],
        "settings": [],
        "run_config": [],
    }

    class FakeProvider:
        def __init__(self, **kwargs):
            captured["provider"].append(kwargs)

    class FakeSettings:
        def __init__(self, **kwargs):
            captured["settings"].append(kwargs)

    class FakeRunConfig:
        def __init__(self, **kwargs):
            captured["run_config"].append(kwargs)

    modules = {
        "agents.models.openai_provider": types.SimpleNamespace(
            OpenAIProvider=FakeProvider
        ),
        "agents.run_config": types.SimpleNamespace(RunConfig=FakeRunConfig),
        "agents.model_settings": types.SimpleNamespace(ModelSettings=FakeSettings),
    }
    monkeypatch.setattr(
        runtime.importlib,
        "import_module",
        lambda name: modules[name],
    )
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    openrouter_key = tmp_path / "openrouter_api_key.txt"
    freellm_key = tmp_path / "freellmapi_unified_key.txt"
    openrouter_key.write_text("sk-or-v1-bounded-test-value", encoding="utf-8")
    freellm_key.write_text("bounded-freellm-test-value", encoding="utf-8")
    openrouter_key.chmod(0o600)
    freellm_key.chmod(0o600)

    paid = _route(
        transport="openrouter",
        profile="paid_swarm_6",
        category="standard",
        base_url=OPENROUTER_BASE_URL,
    )
    paid_runtime = runtime.build_route_run_config(paid, output_token_limit=512)

    assert paid_runtime.transport == "openrouter"
    assert captured["provider"][0]["base_url"] == OPENROUTER_BASE_URL
    assert captured["provider"][0]["use_responses"] is False
    assert captured["settings"][0]["max_tokens"] == 512
    assert captured["settings"][0]["include_usage"] is True
    assert captured["settings"][0]["extra_body"] == {
        "provider": {
            "require_parameters": True,
            "allow_fallbacks": False,
            "data_collection": "deny",
            "zdr": True,
        }
    }
    assert captured["run_config"][0]["tracing_disabled"] is True
    assert captured["run_config"][0]["trace_include_sensitive_data"] is False

    free = _route(
        transport="freellm",
        profile="free_single_agent",
        category="free",
        base_url=FREELLM_BASE_URL,
    )
    free_runtime = runtime.build_route_run_config(free, output_token_limit=256)

    assert free_runtime.transport == "freellm"
    assert captured["provider"][1]["base_url"] == FREELLM_BASE_URL
    assert captured["provider"][1]["use_responses"] is False
    assert captured["settings"][1] == {
        "max_tokens": 256,
        "include_usage": True,
    }


def test_transport_migration_is_additive_and_fail_closed() -> None:
    migration = (
        ROOT
        / "scripts"
        / "sovereign-backend"
        / "migrations"
        / "033_openrouter_paid_freellm_direct.sql"
    ).read_text("utf-8")

    assert "provider = 'freellm'" in migration
    assert "'https://openrouter.ai/api/v1'" in migration
    assert "'openai/gpt-5.4-mini'" in migration
    assert "'pricingVerified', true" in migration
    assert "'activationState', 'protected-key-and-canary-required'" in migration
    assert "disabled = CASE" in migration
    assert "DELETE FROM llm_routes" not in migration
