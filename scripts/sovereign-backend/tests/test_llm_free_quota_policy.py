from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from llm_cost_policy import (  # noqa: E402
    BillingPolicyError,
    FREE_FUNDING_PROVIDER_QUOTA,
    FREE_FUNDING_VERIFIED_ZERO_COST,
    route_billing_policy,
)


def _free_route(*, funding_mode: str = FREE_FUNDING_PROVIDER_QUOTA) -> dict:
    return {
        "model_id": "sovereign-groq-openai-gpt-oss-20b",
        "config": {
            "providerModel": "groq/openai/gpt-oss-20b",
            "billingCategory": "free",
            "markupMultiplier": 0,
            "fundingMode": funding_mode,
            "freeEligible": True,
            "quotaContractVerified": True,
            "userChargeCredits": 0,
        },
    }


def test_provider_free_quota_requires_no_provider_price_fields() -> None:
    policy = route_billing_policy(_free_route())

    assert policy["billingCategory"] == "free"
    assert policy["fundingMode"] == FREE_FUNDING_PROVIDER_QUOTA
    assert policy["markupMultiplier"] == 0
    assert policy["pricingRequired"] is False
    assert policy["pricingVerified"] is False
    assert policy["freeEligible"] is True
    assert policy["quotaContractVerified"] is True
    assert policy["inputUsdPerMillion"] == Decimal("0")
    assert policy["outputUsdPerMillion"] == Decimal("0")


def test_free_route_rejects_provider_pricing_verification_claim() -> None:
    route = _free_route()
    route["config"]["pricingVerified"] = True
    with pytest.raises(BillingPolicyError, match="must not claim"):
        route_billing_policy(route)


def test_legacy_zero_cost_label_normalizes_to_free_quota_without_prices() -> None:
    policy = route_billing_policy(
        _free_route(funding_mode=FREE_FUNDING_VERIFIED_ZERO_COST)
    )

    assert policy["fundingMode"] == FREE_FUNDING_PROVIDER_QUOTA
    assert policy["pricingVerified"] is False


def test_free_route_requires_eligibility_quota_and_zero_user_charge() -> None:
    for field in ("freeEligible", "quotaContractVerified"):
        route = _free_route()
        route["config"].pop(field)
        with pytest.raises(BillingPolicyError):
            route_billing_policy(route)

    charged = _free_route()
    charged["config"]["userChargeCredits"] = 1
    with pytest.raises(BillingPolicyError, match="zero user credits"):
        route_billing_policy(charged)


def test_paid_routes_still_require_verified_positive_prices() -> None:
    paid = {
        "config": {
            "providerModel": "openrouter/model",
            "billingCategory": "standard",
            "markupMultiplier": 4,
            "inputUsdPerMillion": 1,
            "cachedInputUsdPerMillion": 0.5,
            "outputUsdPerMillion": 2,
            "pricingVerified": True,
        }
    }
    policy = route_billing_policy(paid)
    assert policy["pricingRequired"] is True
    assert policy["pricingVerified"] is True

    paid["config"]["pricingVerified"] = False
    with pytest.raises(BillingPolicyError, match="pricing is not verified"):
        route_billing_policy(paid)
