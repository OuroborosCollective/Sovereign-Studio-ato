from __future__ import annotations

from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from free_revolver_runtime import resolve_free_revolver_plan
from llm_transport import route_is_direct_freellm


def _free_route() -> dict:
    return {
        "id": "133d036c-5a2a-59e3-a73b-d9575ba5800f",
        "model_id": "sovereign-free-test",
        "model_name": "Sovereign Free Test",
        "provider": "freellm",
        "base_url": "http://freellmapi:3001/v1",
        "runtime_kind": "freellm",
        "tier": "free",
        "credits_per_unit": 0.0,
        "disabled": False,
        "priority": 50,
        "config": {
            "routingOwner": "free-revolver-v3",
            "transport": "freellm",
            "direct": True,
            "providerModel": "auto",
            "billingCategory": "free",
            "billingClass": "free",
            "fundingMode": "provider_free_quota",
            "markupMultiplier": 0,
            "pricingVerified": False,
            "freeEligible": True,
            "quotaContractVerified": True,
            "userChargeCredits": 0,
            "canaryVerified": True,
            "canaryConfirmationCount": 2,
            "executionProfile": "free_single_agent",
            "capabilities": ["chat"],
        },
    }


def test_revolver_plan_preserves_fields_required_by_direct_executor() -> None:
    route = _free_route()

    def query(sql: str, params=None, *, one=False, **_kwargs):
        normalized = " ".join(sql.split())
        if "FROM llm_revolver_profiles" in normalized:
            return None
        if "FROM llm_routes AS route" in normalized:
            # Regression guard for live blocker freellm_direct_route_rejected:
            # planner output must carry the same execution identity consumed by
            # fetch_direct_llm(), not only display/ranking metadata.
            assert "route.base_url" in normalized
            assert "route.runtime_kind" in normalized
            assert "route.tier" in normalized
            assert "route.credits_per_unit::float AS credits_per_unit" in normalized
            return [route]
        raise AssertionError(f"unexpected query: {normalized}")

    _profile, planned = resolve_free_revolver_plan(
        query,
        tenant_id=None,
        request_id="319ba172-0e6e-458c-96e8-e75ccc4f70a0",
    )

    assert len(planned) == 1
    assert planned[0]["id"] == route["id"]
    assert planned[0]["base_url"] == "http://freellmapi:3001/v1"
    assert planned[0]["runtime_kind"] == "freellm"
    assert route_is_direct_freellm(planned[0]) is True
