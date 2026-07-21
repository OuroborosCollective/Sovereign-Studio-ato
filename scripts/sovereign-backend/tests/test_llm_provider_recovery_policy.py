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


@pytest.mark.parametrize("funding_mode", ["provider_free_quota", "verified_zero_cost"])
def test_paid_provider_recovery_cannot_convert_routes_to_free(funding_mode: str) -> None:
    with pytest.raises(BillingPolicyError, match="Free-Revolver-Providerbereich"):
        _normalize_provider_recovery_policy(
            {
                "billingCategory": "free",
                "fundingMode": funding_mode,
                "markupMultiplier": 0,
            },
            _deployment(),
            _priced_model(),
        )


def test_recovery_keeps_standard_paid_policy_valid() -> None:
    policy = _normalize_provider_recovery_policy(
        {
            "billingCategory": "standard",
            "markupMultiplier": 4,
            "priority": 25,
        },
        _deployment(),
        _priced_model(),
    )
    assert policy is not None
    assert policy["billingCategory"] == "standard"
    assert policy["fundingMode"] == "provider_priced"
    assert policy["markupMultiplier"] == 4
    assert policy["priority"] == 25


def test_plain_owner_input_refresh_does_not_change_policy() -> None:
    assert _normalize_provider_recovery_policy({}, _deployment(), None) is None
