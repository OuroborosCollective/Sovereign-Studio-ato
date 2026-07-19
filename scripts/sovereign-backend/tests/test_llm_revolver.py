from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from llm_revolver import (
    build_revolver_candidates,
    failure_decision,
    normalize_quota_scope,
    provider_usage_seen,
    route_quota_scope,
)


def route(route_id: str, *, scope: str, priority: int = 10, category: str = "free"):
    price = 0 if category == "free" else 1
    return {
        "id": route_id,
        "model_id": f"model-{route_id}",
        "provider": "litellm",
        "disabled": False,
        "priority": priority,
        "config": {
            "providerModel": f"provider/model-{route_id}",
            "billingCategory": category,
            "markupMultiplier": 0 if category == "free" else 4,
            "inputUsdPerMillion": price,
            "cachedInputUsdPerMillion": price,
            "outputUsdPerMillion": price,
            "pricingVerified": True,
            "pricingSource": "test",
            "quotaScope": scope,
        },
    }


def test_revolver_uses_primary_then_unique_ready_free_scopes():
    primary = route("a", scope="provider:key-a", priority=90)
    same_key = route("alias-a", scope="provider:key-a", priority=1)
    second = route("b", scope="provider:key-b", priority=20)
    paid = route("paid", scope="provider:key-c", priority=2, category="standard")
    assert [item["id"] for item in build_revolver_candidates(
        primary, [same_key, second, paid]
    )] == ["a", "b"]


def test_revolver_skips_active_cooldowns_and_blocked_scopes():
    now = datetime.now(timezone.utc)
    primary = route("a", scope="provider:key-a")
    cooling = route("b", scope="provider:key-b")
    blocked = route("c", scope="provider:key-c")
    states = {
        "provider:key-b": {
            "status": "cooldown",
            "cooldown_until": now + timedelta(minutes=5),
        },
        "provider:key-c": {"status": "blocked"},
    }
    assert [item["id"] for item in build_revolver_candidates(
        primary, [cooling, blocked], state_by_scope=states, now=now
    )] == ["a"]


def test_paid_route_never_rotates():
    paid = route("paid", scope="provider:key-paid", category="standard")
    assert build_revolver_candidates(
        paid, [route("free", scope="provider:key-free")]
    ) == [paid]


def test_quota_and_rate_limit_rotate_only_without_usage():
    quota = failure_decision(
        {"blocker": "provider_quota_exhausted"}, usage_seen=False
    )
    assert quota["retryAllowed"] is True
    assert quota["state"] == "cooldown"
    assert failure_decision(
        {"blocker": "provider_rate_limited"}, usage_seen=True
    )["retryAllowed"] is False


def test_request_id_alone_is_not_usage_evidence():
    assert provider_usage_seen({
        "totalTokens": 0,
        "providerCostUsd": None,
        "upstreamRequestId": "request-only",
    }) is False
    assert provider_usage_seen({"totalTokens": 1}) is True
    assert provider_usage_seen({"providerCostUsd": 0.001}) is True


def test_quota_scope_is_validated_and_default_is_opaque():
    generated = normalize_quota_scope("", route_id="route-secret-looking-id")
    assert generated.startswith("litellm:route:")
    assert "route-secret-looking-id" not in generated
    with pytest.raises(ValueError):
        normalize_quota_scope("bad scope", route_id="a")
    assert route_quota_scope(route("a", scope="provider:key-a")) == "provider:key-a"
