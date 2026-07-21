from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


if "flask" not in sys.modules:
    flask_stub = ModuleType("flask")
    flask_stub.jsonify = lambda value=None, **kwargs: value if value is not None else kwargs
    flask_stub.request = SimpleNamespace()
    sys.modules["flask"] = flask_stub


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from llm_cost_policy import BillingPolicyError  # noqa: E402
from llm_provider_runtime import _normalize_provider_recovery_policy  # noqa: E402


def _deployment() -> dict:
    return {
        "billing_category": "premium",
        "markup_multiplier": 8,
        "funding_mode": "provider_priced",
        "priority": 50,
    }


def _priced_model() -> dict:
    return {
        "modelId": "sovereign-groq-openai-gpt-oss-20b-301e7b07",
        "providerModel": "groq/openai/gpt-oss-20b",
        "inputUsdPerMillion": 0.075,
        "cachedInputUsdPerMillion": 0.075,
        "outputUsdPerMillion": 0.30,
        "pricingVerified": True,
        "pricingSource": "litellm-model-info",
        "freeEligible": False,
    }


def test_recovery_converts_blocked_route_to_provider_free_quota() -> None:
    policy = _normalize_provider_recovery_policy(
        {
            "billingCategory": "free",
            "fundingMode": "provider_free_quota",
            "markupMultiplier": 0,
        },
        _deployment(),
        _priced_model(),
    )

    assert policy is not None
    assert policy["billingCategory"] == "free"
    assert policy["fundingMode"] == "provider_free_quota"
    assert policy["markupMultiplier"] == 0
    assert policy["creditsPerUnit"] == 0
    assert policy["priority"] == 50


def test_recovery_rejects_positive_prices_as_verified_zero_cost() -> None:
    with pytest.raises(BillingPolicyError, match="verified_zero_cost"):
        _normalize_provider_recovery_policy(
            {
                "billingCategory": "free",
                "fundingMode": "verified_zero_cost",
                "markupMultiplier": 0,
            },
            _deployment(),
            _priced_model(),
        )


def test_plain_owner_input_refresh_does_not_change_policy() -> None:
    assert _normalize_provider_recovery_policy({}, _deployment(), None) is None
