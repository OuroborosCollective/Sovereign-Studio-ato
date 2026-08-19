from __future__ import annotations

from decimal import Decimal
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
    OMNIROUTE_BASE_URL,
    OPENROUTER_BASE_URL,
    route_is_direct_freellm,
    route_is_openrouter_paid,
    route_provider_model,
    route_snapshot_hashes,
    route_transport,
    route_transport_diagnostics,
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
            "fundingMode": "provider_priced" if category == "standard" else "provider_free_quota",
            "pricingVerified": category == "standard",
            "pricingSource": "test" if category == "standard" else "not-applicable-free-quota",
            "freeEligible": category == "free",
            "quotaContractVerified": category == "free",
            "userChargeCredits": 0 if category == "free" else None,
            **({
                "inputUsdPerMillion": 0.75,
                "cachedInputUsdPerMillion": 0.075,
                "outputUsdPerMillion": 4.5,
            } if category == "standard" else {}),
        },
    }


def test_openrouter_aliases_normalize_without_collapsing_free_transport() -> None:
    paid = _route(
        transport="openrouter",
        profile="paid_swarm_6",
        category="standard",
        base_url=OPENROUTER_BASE_URL,
    )
    paid["config"]["transport"] = "open-router"
    paid["runtime_kind"] = "open_router"
    paid["provider"] = "openrouter.ai"

    diagnostic = route_transport_diagnostics(paid)
    assert diagnostic["ok"] is True
    assert diagnostic["transport"] == "openrouter"
    assert route_transport(paid) == "openrouter"
    assert route_is_openrouter_paid(paid) is True


def test_conflicting_transport_fields_fail_closed_instead_of_using_precedence() -> None:
    paid = _route(
        transport="openrouter",
        profile="paid_swarm_6",
        category="standard",
        base_url=OPENROUTER_BASE_URL,
    )
    paid["runtime_kind"] = "freellm"

    diagnostic = route_transport_diagnostics(paid)
    assert diagnostic["ok"] is False
    assert diagnostic["failureFamily"] == "route_transport_conflict"
    assert diagnostic["secretValuesReturned"] is False
    assert route_transport(paid) == ""
    assert route_is_openrouter_paid(paid) is False
    assert route_is_direct_freellm(paid) is False


def test_omniroute_keyless_transport_never_maps_to_a_protected_key_file() -> None:
    with pytest.raises(runtime.RouteRuntimeError) as captured:
        runtime._key_spec("freellm", OMNIROUTE_BASE_URL)

    assert captured.value.family == "OMNIROUTE_KEYLESS_AGENTS_SDK_UNSUPPORTED"
    assert captured.value.next_action == (
        "USE_DIRECT_KEYLESS_OMNIROUTE_RUNTIME_OR_ADD_VERIFIED_KEYLESS_SDK_ADAPTER"
    )


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


def test_route_snapshot_binds_routing_policy_but_not_price_changes() -> None:
    paid = _route(
        transport="openrouter",
        profile="paid_swarm_6",
        category="standard",
        base_url=OPENROUTER_BASE_URL,
    )
    route_hash, price_hash = route_snapshot_hashes(paid)
    changed_policy = {
        **paid,
        "config": {
            **paid["config"],
            "providerPolicy": {
                **paid["config"]["providerPolicy"],
                "zdr": False,
            },
        },
    }
    changed_route_hash, same_price_hash = route_snapshot_hashes(changed_policy)

    assert changed_route_hash != route_hash
    assert same_price_hash == price_hash


def test_price_snapshot_uses_canonical_decimal_strings() -> None:
    paid = _route(
        transport="openrouter",
        profile="paid_swarm_6",
        category="standard",
        base_url=OPENROUTER_BASE_URL,
    )
    _, float_price_hash = route_snapshot_hashes(paid)
    decimal_prices = {
        **paid,
        "config": {
            **paid["config"],
            "inputUsdPerMillion": Decimal("0.75"),
            "cachedInputUsdPerMillion": Decimal("0.075"),
            "outputUsdPerMillion": Decimal("4.5"),
            "markupMultiplier": Decimal("4.0"),
        },
    }
    string_prices = {
        **paid,
        "config": {
            **paid["config"],
            "inputUsdPerMillion": " 0.750 ",
            "cachedInputUsdPerMillion": "0.0750",
            "outputUsdPerMillion": "4.50",
            "markupMultiplier": "4.000",
        },
    }
    _, decimal_price_hash = route_snapshot_hashes(decimal_prices)
    _, string_price_hash = route_snapshot_hashes(string_prices)

    assert decimal_price_hash == float_price_hash
    assert string_price_hash == float_price_hash


@pytest.mark.parametrize("invalid_price", ["", "not-a-number", "NaN", "Infinity", True, []])
def test_price_snapshot_rejects_non_finite_or_non_numeric_values(invalid_price) -> None:
    paid = _route(
        transport="openrouter",
        profile="paid_swarm_6",
        category="standard",
        base_url=OPENROUTER_BASE_URL,
    )
    paid["config"]["inputUsdPerMillion"] = invalid_price

    with pytest.raises(ValueError, match="price snapshot values must be numeric or null"):
        route_snapshot_hashes(paid)


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
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "a" * 40)
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
    assert paid_runtime.route_binding.source_revision == "a" * 40
    assert paid_runtime.route_binding.route_class == "OPENROUTER_PAID"
    assert paid_runtime.route_binding.price_snapshot_sha256 != "0" * 64
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
    assert free_runtime.route_binding.source_revision == "a" * 40
    assert free_runtime.route_binding.route_class == "FREELLM_FREE"
    assert free_runtime.route_binding.price_snapshot_sha256 == "0" * 64
    assert captured["provider"][1]["base_url"] == FREELLM_BASE_URL
    assert captured["provider"][1]["use_responses"] is False
    assert captured["settings"][1] == {
        "max_tokens": 256,
        "include_usage": True,
    }


def test_route_config_rejects_unverified_runtime_revision_before_key_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    monkeypatch.delenv("SOVEREIGN_SOURCE_REVISION", raising=False)
    paid = _route(
        transport="openrouter",
        profile="paid_swarm_6",
        category="standard",
        base_url=OPENROUTER_BASE_URL,
    )

    with pytest.raises(runtime.RouteRuntimeError) as captured:
        runtime.build_route_run_config(paid, output_token_limit=128)

    assert captured.value.family == "LLM_RUNTIME_REVISION_UNVERIFIED"
    assert captured.value.next_action == "DEPLOY_WITH_EXACT_SOVEREIGN_SOURCE_REVISION"


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
