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
from llm_transport import FREELLM_BASE_URL, OPENROUTER_BASE_URL


SOURCE_REVISION = "1" * 40
IMAGE_DIGEST = "sha256:" + ("2" * 64)


@pytest.fixture(autouse=True)
def _runtime_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", SOURCE_REVISION)
    monkeypatch.setenv("SOVEREIGN_IMAGE_DIGEST", IMAGE_DIGEST)


def route(
    route_id: str,
    *,
    scope: str,
    priority: int = 10,
    category: str = "free",
    latency_ms: int = 100,
):
    free = category == "free"
    transport = "freellm" if free else "openrouter"
    return {
        "id": route_id,
        "model_id": f"model-{route_id}",
        "provider": transport,
        "runtime_kind": transport,
        "base_url": FREELLM_BASE_URL if free else OPENROUTER_BASE_URL,
        "disabled": False,
        "priority": priority,
        "config": {
            "transport": transport,
            "direct": True,
            "providerModel": f"provider/model-{route_id}",
            "executionProfile": "free_single_agent" if free else "paid_swarm_6",
            "billingCategory": category,
            "billingClass": category,
            "fundingMode": "provider_free_quota" if free else "provider_priced",
            "markupMultiplier": 0 if free else 4,
            "pricingVerified": not free,
            "pricingSource": "test" if not free else "not-applicable-free-quota",
            "freeEligible": free,
            "quotaContractVerified": free,
            "userChargeCredits": 0 if free else None,
            "quotaScope": scope,
            "quotaEvidence": {
                "scope": scope,
                "stateOwner": "postgresql-revolver-state",
                "contractVerified": True,
            } if free else {},
            "canaryVerified": free,
            "canaryConfirmationCount": 2 if free else 0,
            "canaryLatencyMs": latency_ms,
            **({
                "inputUsdPerMillion": 1,
                "cachedInputUsdPerMillion": 1,
                "outputUsdPerMillion": 1,
            } if not free else {}),
            "runtimeIdentity": {
                "sourceRevision": SOURCE_REVISION,
                "sourceRevisionVerified": True,
                "imageDigest": IMAGE_DIGEST,
                "imageDigestVerified": True,
            },
            "canaryReceipt": {
                "schemaVersion": "sovereign.freellm-route-receipt.v2",
                "receiptSha256": "3" * 64,
            },
        },
    }


def test_revolver_prefers_best_route_per_unique_ready_free_scope():
    primary = route("a", scope="provider:key-a", priority=90)
    same_key = route("alias-a", scope="provider:key-a", priority=1)
    second = route("b", scope="provider:key-b", priority=20)
    paid = route("paid", scope="provider:key-c", priority=2, category="standard")
    assert [item["id"] for item in build_revolver_candidates(
        primary, [same_key, second, paid]
    )] == ["alias-a", "b"]


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


def test_revolver_rotates_least_recently_used_then_uses_latency_tie_break() -> None:
    now = datetime.now(timezone.utc)
    slow_unused = route("slow", scope="provider:key-slow", latency_ms=900)
    fast_unused = route("fast", scope="provider:key-fast", latency_ms=25)
    used = route("used", scope="provider:key-used", latency_ms=1)
    states = {
        "provider:key-used": {
            "status": "ready",
            "last_attempt_at": now - timedelta(hours=2),
        },
    }

    assert [item["id"] for item in build_revolver_candidates(
        used,
        [slow_unused, fast_unused],
        state_by_scope=states,
        now=now,
    )] == ["fast", "slow", "used"]


def test_expired_zero_quota_reenters_lru_order() -> None:
    now = datetime.now(timezone.utc)
    expired = route("expired", scope="provider:key-expired", latency_ms=800)
    recently_used = route("recent", scope="provider:key-recent", latency_ms=20)
    states = {
        "provider:key-expired": {
            "status": "cooldown",
            "quota_remaining": 0,
            "quota_limit": 100,
            "quota_reset_at": now - timedelta(minutes=5),
            "cooldown_until": now - timedelta(minutes=5),
            "consecutive_failures": 4,
            "last_attempt_at": now - timedelta(days=2),
        },
        "provider:key-recent": {
            "status": "ready",
            "last_attempt_at": now - timedelta(minutes=1),
        },
    }

    assert [item["id"] for item in build_revolver_candidates(
        recently_used,
        [expired, recently_used],
        state_by_scope=states,
        now=now,
    )] == ["expired", "recent"]


def test_revision_or_digest_drift_removes_free_route() -> None:
    current = route("current", scope="provider:key-current")
    stale = route("stale", scope="provider:key-stale")
    stale["config"]["runtimeIdentity"]["imageDigest"] = "sha256:" + ("9" * 64)

    assert [item["id"] for item in build_revolver_candidates(
        current,
        [current, stale],
    )] == ["current"]


def test_revolver_prefers_remaining_quota_and_skips_exhausted_until_reset():
    now = datetime.now(timezone.utc)
    exhausted = route("a", scope="provider:key-a", priority=1)
    remaining = route("b", scope="provider:key-b", priority=50)
    unknown = route("c", scope="provider:key-c", priority=2)
    states = {
        "provider:key-a": {
            "status": "cooldown",
            "quota_remaining": 0,
            "quota_limit": 100,
            "quota_reset_at": now + timedelta(hours=1),
            "cooldown_until": now + timedelta(hours=1),
        },
        "provider:key-b": {
            "status": "ready",
            "quota_remaining": 50,
            "quota_limit": 100,
        },
    }

    assert [item["id"] for item in build_revolver_candidates(
        exhausted,
        [remaining, unknown],
        state_by_scope=states,
        now=now,
    )] == ["b", "c"]
