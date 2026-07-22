from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from llm_execution_resolver import (
    FREE_SINGLE_AGENT_PROFILE,
    PAID_SWARM_PROFILE,
    build_paid_to_free_candidates,
    free_fallback_resolution,
    resolve_execution_profile,
)
from llm_transport import FREELLM_BASE_URL, OPENROUTER_BASE_URL


def route(
    route_id: str,
    *,
    category: str,
    scope: str,
    priority: int,
    profile: str,
) -> dict:
    free = category == "free"
    price = 1.0
    transport = "freellm" if free else "openrouter"
    return {
        "id": route_id,
        "model_id": f"alias-{route_id}",
        "model_name": route_id,
        "provider": transport,
        "runtime_kind": transport,
        "base_url": FREELLM_BASE_URL if free else OPENROUTER_BASE_URL,
        "disabled": False,
        "priority": priority,
        "config": {
            "transport": transport,
            "direct": True,
            "providerModel": f"provider/model-{route_id}",
            "billingCategory": category,
            "billingClass": category,
            "fundingMode": "provider_free_quota" if free else "provider_priced",
            "markupMultiplier": 0 if free else 4,
            "inputUsdPerMillion": price,
            "cachedInputUsdPerMillion": price,
            "outputUsdPerMillion": price,
            "pricingVerified": True,
            "pricingSource": "test",
            "quotaScope": scope,
            "executionProfile": profile,
            "catalogVerified": not free,
            "transportCanaryVerified": not free,
            "selectable": not free,
            "supportedExecutionRoles": ["main", "swarm_agents"] if not free else ["free_single_agent"],
            "providerPolicy": {
                "require_parameters": True,
                "allow_fallbacks": False,
                "data_collection": "deny",
                "zdr": True,
            } if not free else {},
        },
    }


def test_paid_purchase_selects_paid_swarm_and_keeps_free_fallbacks() -> None:
    paid = route(
        "paid-openai",
        category="standard",
        scope="paid:key-openai",
        priority=10,
        profile=PAID_SWARM_PROFILE,
    )
    free_a = route(
        "free-a",
        category="free",
        scope="free:key-a",
        priority=20,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )
    free_b = route(
        "free-b",
        category="free",
        scope="free:key-b",
        priority=30,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )

    resolution = resolve_execution_profile(
        routes=[free_b, paid, free_a],
        state_by_scope={},
        paid_purchase_verified=True,
        provider_funded_credits=100,
    )

    assert resolution is not None
    assert resolution.profile_id == PAID_SWARM_PROFILE
    assert resolution.max_background_agents == 6
    assert resolution.repository_execution_allowed is True
    assert [item["id"] for item in resolution.candidate_routes] == [
        "paid-openai",
        "free-a",
        "free-b",
    ]


def test_bonus_or_admin_credits_do_not_unlock_paid_swarm() -> None:
    paid = route(
        "paid",
        category="standard",
        scope="paid:key-a",
        priority=10,
        profile=PAID_SWARM_PROFILE,
    )
    free = route(
        "free",
        category="free",
        scope="free:key-a",
        priority=20,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )

    resolution = resolve_execution_profile(
        routes=[paid, free],
        state_by_scope={},
        paid_purchase_verified=False,
        provider_funded_credits=500,
    )

    assert resolution is not None
    assert resolution.profile_id == FREE_SINGLE_AGENT_PROFILE
    assert resolution.max_background_agents == 0
    assert resolution.repository_execution_allowed is True
    assert resolution.primary_route["id"] == "free"


def test_paid_quota_cooldown_resolves_to_free_profile() -> None:
    now = datetime.now(timezone.utc)
    paid = route(
        "paid",
        category="standard",
        scope="paid:key-a",
        priority=10,
        profile=PAID_SWARM_PROFILE,
    )
    free = route(
        "free",
        category="free",
        scope="free:key-a",
        priority=20,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )

    resolution = resolve_execution_profile(
        routes=[paid, free],
        state_by_scope={
            "paid:key-a": {
                "status": "cooldown",
                "cooldown_until": now + timedelta(hours=1),
            }
        },
        paid_purchase_verified=True,
        provider_funded_credits=500,
        now=now,
    )

    assert resolution is not None
    assert resolution.profile_id == FREE_SINGLE_AGENT_PROFILE
    assert resolution.reason == "paid_route_unavailable_resolved_to_free_revolver"


def test_paid_to_free_candidates_deduplicate_shared_quota_scopes() -> None:
    paid = route(
        "paid",
        category="standard",
        scope="paid:key-a",
        priority=10,
        profile=PAID_SWARM_PROFILE,
    )
    free_a = route(
        "free-a",
        category="free",
        scope="free:key-a",
        priority=20,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )
    free_same_key = route(
        "free-a-alias",
        category="free",
        scope="free:key-a",
        priority=1,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )
    free_b = route(
        "free-b",
        category="free",
        scope="free:key-b",
        priority=30,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )

    assert [item["id"] for item in build_paid_to_free_candidates(
        paid,
        [paid, free_a, free_same_key, free_b],
    )] == ["paid", "free-a-alias", "free-b"]


def test_paid_provider_failure_derives_free_single_agent_fallback() -> None:
    paid = route(
        "paid",
        category="standard",
        scope="paid:key-a",
        priority=10,
        profile=PAID_SWARM_PROFILE,
    )
    free = route(
        "free",
        category="free",
        scope="free:key-a",
        priority=20,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )
    resolution = resolve_execution_profile(
        routes=[paid, free],
        state_by_scope={},
        paid_purchase_verified=True,
        provider_funded_credits=500,
    )

    assert resolution is not None
    fallback = free_fallback_resolution(
        resolution,
        reason="paid_provider_429_resolved_to_free_revolver",
    )

    assert fallback is not None
    assert fallback.profile_id == FREE_SINGLE_AGENT_PROFILE
    assert fallback.primary_route["id"] == "free"
    assert fallback.max_background_agents == 0
    assert fallback.repository_execution_allowed is True
    assert fallback.reason == "paid_provider_429_resolved_to_free_revolver"



def test_paid_resolver_selects_distinct_main_and_shared_six_agent_models() -> None:
    main = route(
        "paid-main",
        category="standard",
        scope="paid:main",
        priority=10,
        profile=PAID_SWARM_PROFILE,
    )
    workers = route(
        "paid-workers",
        category="standard",
        scope="paid:workers",
        priority=20,
        profile=PAID_SWARM_PROFILE,
    )
    free = route(
        "free",
        category="free",
        scope="free:key-a",
        priority=30,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )

    resolution = resolve_execution_profile(
        routes=[workers, free, main],
        state_by_scope={},
        paid_purchase_verified=True,
        provider_funded_credits=100,
        requested_main_model="paid-main",
        requested_agent_model="provider/model-paid-workers",
        requested_mode="paid",
    )

    assert resolution is not None
    assert resolution.primary_route["id"] == "paid-main"
    assert resolution.agent_route["id"] == "paid-workers"
    assert resolution.max_background_agents == 6
    payload = resolution.safe_payload()
    assert payload["mainModel"] == "provider/model-paid-main"
    assert payload["agentModel"] == "provider/model-paid-workers"


def test_forced_free_resolution_preserves_openrouter_fallback_context() -> None:
    free = route(
        "free",
        category="free",
        scope="free:key-a",
        priority=10,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )
    resolution = resolve_execution_profile(
        routes=[free],
        state_by_scope={},
        paid_purchase_verified=True,
        provider_funded_credits=100,
        requested_mode="free",
    )

    assert resolution is not None
    fallback = free_fallback_resolution(
        resolution,
        reason="paid_provider_429_resolved_to_free_revolver",
    )

    assert fallback is not None
    assert fallback.requested_mode == "auto"
    assert fallback.fallback_from_transport == "openrouter"
    assert fallback.primary_route["id"] == "free"
