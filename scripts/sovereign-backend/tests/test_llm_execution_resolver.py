from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from llm_execution_resolver import (
    FREE_SINGLE_AGENT_PROFILE,
    FREE_SWARM_PROFILE,
    PAID_SWARM_PROFILE,
    ExecutionResolutionError,
    advance_free_revolver_resolution,
    build_paid_to_free_candidates,
    free_fallback_resolution,
    resolve_execution_profile,
)
from llm_revolver import verify_free_route_reason
from llm_transport import FREELLM_BASE_URL, OPENROUTER_BASE_URL


SOURCE_REVISION = "1" * 40
IMAGE_DIGEST = "sha256:" + ("2" * 64)
os.environ["SOVEREIGN_SOURCE_REVISION"] = SOURCE_REVISION
os.environ["SOVEREIGN_IMAGE_DIGEST"] = IMAGE_DIGEST


def route(
    route_id: str,
    *,
    category: str,
    scope: str,
    priority: int,
    profile: str,
) -> dict:
    free = category == "free"
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
            "executionProfile": profile,
            **({
                "inputUsdPerMillion": 1.0,
                "cachedInputUsdPerMillion": 1.0,
                "outputUsdPerMillion": 1.0,
            } if not free else {}),
            "catalogVerified": not free,
            "transportCanaryVerified": not free,
            "selectable": not free,
            "supportedExecutionRoles": ["main", "swarm_agents"] if not free else ["free_single_agent"],
            "repositoryExecutionAllowed": True,
            "providerPolicy": {
                "require_parameters": True,
                "allow_fallbacks": False,
                "data_collection": "deny",
            } if not free else {},
            "runtimeIdentity": {
                "sourceRevision": SOURCE_REVISION,
                "sourceRevisionVerified": True,
                "imageDigest": IMAGE_DIGEST,
                "imageDigestVerified": True,
            } if free else {},
            "canaryReceipt": {
                "schemaVersion": "sovereign.freellm-route-receipt.v3",
                "generalChatEvidenceVerified": True,
                "receiptSha256": "3" * 64,
            } if free else {},
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


def test_existing_credit_balance_unlocks_free_but_not_paid_provider() -> None:
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
        provider_funded_credits=0,
        credit_balance=500,
    )

    assert resolution is not None
    assert resolution.profile_id == FREE_SINGLE_AGENT_PROFILE
    assert resolution.max_background_agents == 0
    assert resolution.repository_execution_allowed is True
    assert resolution.primary_route["id"] == "free"


def test_free_requires_purchase_or_existing_credit_entitlement() -> None:
    free = route(
        "free-no-entitlement",
        category="free",
        scope="free:no-entitlement",
        priority=10,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )

    try:
        resolve_execution_profile(
            routes=[free],
            state_by_scope={},
            paid_purchase_verified=False,
            provider_funded_credits=0,
            credit_balance=0,
            requested_mode="free",
        )
    except ExecutionResolutionError as exc:
        assert exc.failure_family == "execution_entitlement_required"
        assert exc.status_code == 403
    else:
        raise AssertionError("free execution must require purchase or persisted credits")


def test_seven_verified_free_quota_scopes_unlock_free_swarm() -> None:
    free_routes = [
        route(
            f"free-{index}",
            category="free",
            scope=f"free:key-{index}",
            priority=index,
            profile=FREE_SINGLE_AGENT_PROFILE,
        )
        for index in range(7)
    ]

    resolution = resolve_execution_profile(
        routes=free_routes,
        state_by_scope={},
        paid_purchase_verified=False,
        provider_funded_credits=0,
        credit_balance=25,
        requested_mode="free",
    )

    assert resolution is not None
    assert resolution.profile_id == FREE_SWARM_PROFILE
    assert resolution.max_background_agents == 6
    assert resolution.primary_route["id"] == "free-0"
    assert [item["id"] for item in resolution.candidate_routes[:7]] == [
        f"free-{index}" for index in range(7)
    ]


def test_free_route_diagnostics_explain_revolver_contract_failures() -> None:
    free = route(
        "free-diagnostic",
        category="free",
        scope="free:diagnostic",
        priority=10,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )
    verified = verify_free_route_reason(free)
    assert verified["ok"] is True
    assert verified["routeFamily"] == "FREELLM_FREE"
    assert verified["failureFamilies"] == []

    free["config"]["canaryConfirmationCount"] = 1
    free["config"]["quotaEvidence"]["stateOwner"] = "wrong-owner"
    diagnostic = verify_free_route_reason(free)
    assert diagnostic["ok"] is False
    assert "free_double_canary_missing" in diagnostic["failureFamilies"]
    assert "free_quota_state_owner_mismatch" in diagnostic["failureFamilies"]
    assert diagnostic["secretValuesReturned"] is False


def test_free_resolution_exposes_transport_and_quota_pricing_class() -> None:
    free = route(
        "free-display",
        category="free",
        scope="free:display",
        priority=10,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )
    resolution = resolve_execution_profile(
        routes=[free],
        state_by_scope={},
        paid_purchase_verified=False,
        provider_funded_credits=0,
        credit_balance=25,
        requested_mode="free",
    )

    assert resolution is not None
    payload = resolution.safe_payload()
    assert payload["resolvedTransport"] == "freellm"
    assert payload["resolvedTransportClass"] == "FREELLM_FREE"
    assert payload["billingCategory"] == "free"
    assert payload["fundingMode"] == "provider_free_quota"
    assert payload["pricingDisplay"] == "free (provider quota)"


def test_conflicting_paid_transport_metadata_surfaces_typed_resolution_error() -> None:
    paid = route(
        "paid-conflict",
        category="standard",
        scope="paid:conflict",
        priority=10,
        profile=PAID_SWARM_PROFILE,
    )
    paid["runtime_kind"] = "freellm"

    try:
        resolve_execution_profile(
            routes=[paid],
            state_by_scope={},
            paid_purchase_verified=True,
            paid_entitlement_verified=True,
            provider_funded_credits=100,
            requested_mode="paid",
        )
    except ExecutionResolutionError as exc:
        payload = exc.safe_payload()
        assert exc.failure_family == "route_transport_mismatch"
        assert exc.status_code == 503
        assert payload["details"]["transportFailureFamily"] == "route_transport_conflict"
        assert payload["details"]["secretValuesReturned"] is False
    else:
        raise AssertionError("conflicting paid transport metadata must fail closed")


def test_free_swarm_threshold_counts_only_routes_marked_for_repository_execution() -> None:
    free_routes = [
        route(
            f"free-capable-{index}",
            category="free",
            scope=f"free:capable-{index}",
            priority=index,
            profile=FREE_SINGLE_AGENT_PROFILE,
        )
        for index in range(7)
    ]
    free_routes[-1]["config"]["repositoryExecutionAllowed"] = False

    resolution = resolve_execution_profile(
        routes=free_routes,
        state_by_scope={},
        paid_purchase_verified=False,
        provider_funded_credits=0,
        credit_balance=25,
        requested_mode="free",
    )

    assert resolution is not None
    assert resolution.profile_id == FREE_SINGLE_AGENT_PROFILE
    assert resolution.max_background_agents == 0


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


def test_paid_budget_cooldown_keeps_verified_free_candidates():
    now = datetime.now(timezone.utc)
    paid = route("paid", category="standard", scope="paid:key-a", priority=10,
                 profile=PAID_SWARM_PROFILE)
    free = route("free", category="free", scope="free:key-a", priority=20,
                 profile=FREE_SINGLE_AGENT_PROFILE)
    states = {"paid:key-a": {"status": "cooldown",
                            "cooldown_until": now + timedelta(hours=1)}}
    assert build_paid_to_free_candidates(paid, [paid, free], state_by_scope=states, now=now) == [free]
    assert build_paid_to_free_candidates(paid, [paid], state_by_scope=states, now=now) == []
    invalid = {**paid, "disabled": True}
    assert build_paid_to_free_candidates(invalid, [free], state_by_scope=states, now=now) == []


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



def test_free_revolver_advances_to_next_verified_quota_scope() -> None:
    free_a = route(
        "free-a",
        category="free",
        scope="free:key-a",
        priority=10,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )
    free_b = route(
        "free-b",
        category="free",
        scope="free:key-b",
        priority=20,
        profile=FREE_SINGLE_AGENT_PROFILE,
    )
    paid = route(
        "paid",
        category="standard",
        scope="paid:key-a",
        priority=1,
        profile=PAID_SWARM_PROFILE,
    )
    resolution = resolve_execution_profile(
        routes=[paid, free_a, free_b],
        state_by_scope={},
        paid_purchase_verified=False,
        provider_funded_credits=0,
        credit_balance=25,
        requested_mode="free",
    )

    assert resolution is not None
    advanced = advance_free_revolver_resolution(
        resolution,
        failed_route_id="free-a",
        reason="free_route_failed_advanced_to_next_quota_scope",
    )

    assert advanced is not None
    assert advanced.primary_route["id"] == "free-b"
    assert [item["id"] for item in advanced.candidate_routes] == ["free-b"]
    assert advanced.requested_mode == "free"
    assert all(item["id"] != "paid" for item in advanced.candidate_routes)


def test_free_revolver_stops_after_last_verified_quota_scope() -> None:
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
        paid_purchase_verified=False,
        provider_funded_credits=0,
        credit_balance=25,
        requested_mode="free",
    )

    assert resolution is not None
    assert advance_free_revolver_resolution(
        resolution,
        failed_route_id="free",
        reason="free_route_failed_advanced_to_next_quota_scope",
    ) is None


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
    assert payload["resolvedTransport"] == "openrouter"
    assert payload["resolvedTransportClass"] == "OPENROUTER_PAID"
    assert payload["billingCategory"] == "standard"
    assert payload["fundingMode"] == "provider_priced"
    assert payload["pricingDisplay"] == "paid (OpenRouter)"


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
