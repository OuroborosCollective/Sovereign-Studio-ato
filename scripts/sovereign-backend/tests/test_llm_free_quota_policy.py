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


def _free_route(*, funding_mode: str, input_price: float, output_price: float) -> dict:
    return {
        "model_id": "sovereign-groq-openai-gpt-oss-20b",
        "config": {
            "providerModel": "groq/openai/gpt-oss-20b",
            "billingCategory": "free",
            "markupMultiplier": 0,
            "fundingMode": funding_mode,
            "inputUsdPerMillion": input_price,
            "cachedInputUsdPerMillion": input_price,
            "outputUsdPerMillion": output_price,
            "pricingVerified": True,
            "pricingSource": "litellm-model-info",
            "usdMicrosPerCredit": 1000,
        },
    }


def test_provider_free_quota_keeps_positive_list_prices_and_zero_markup() -> None:
    policy = route_billing_policy(
        _free_route(
            funding_mode=FREE_FUNDING_PROVIDER_QUOTA,
            input_price=0.075,
            output_price=0.30,
        )
    )

    assert policy["billingCategory"] == "free"
    assert policy["fundingMode"] == FREE_FUNDING_PROVIDER_QUOTA
    assert policy["markupMultiplier"] == 0
    assert policy["inputUsdPerMillion"] == Decimal("0.075")
    assert policy["outputUsdPerMillion"] == Decimal("0.30")


def test_verified_zero_cost_rejects_positive_provider_prices() -> None:
    with pytest.raises(BillingPolicyError, match="verified zero provider prices"):
        route_billing_policy(
            _free_route(
                funding_mode=FREE_FUNDING_VERIFIED_ZERO_COST,
                input_price=0.075,
                output_price=0.30,
            )
        )


def test_verified_zero_cost_accepts_only_zero_provider_prices() -> None:
    policy = route_billing_policy(
        _free_route(
            funding_mode=FREE_FUNDING_VERIFIED_ZERO_COST,
            input_price=0,
            output_price=0,
        )
    )

    assert policy["fundingMode"] == FREE_FUNDING_VERIFIED_ZERO_COST
    assert policy["markupMultiplier"] == 0
