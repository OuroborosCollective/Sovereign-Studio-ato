"""Tests for free_revolver_provider_contracts — pricing evidence contracts.

Regression coverage for:
  BUG-A  : zero_price_evidence cross-source seen_input/seen_output accumulation
  BUG-A.2: _numeric_zero treating boolean False as zero price

Both the canonical copy (backend/) and the deployment-mirror copy
(scripts/sovereign-backend/) are exercised to prevent silent divergence.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
DEPLOY_MIRROR = REPO_ROOT / "scripts" / "sovereign-backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from free_revolver_provider_contracts import (
    _numeric_zero,
    normalize_models_payload,
    zero_price_evidence,
)


def _load_mirror() -> tuple:
    """Load the deployment-mirror module isolated from sys.modules."""
    spec = importlib.util.spec_from_file_location(
        "_mirror_free_revolver_provider_contracts",
        DEPLOY_MIRROR / "free_revolver_provider_contracts.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod._numeric_zero, mod.zero_price_evidence, mod.normalize_models_payload


_mirror_numeric_zero, _mirror_zero_price_evidence, _mirror_normalize = _load_mirror()


# ── _numeric_zero ──────────────────────────────────────────────────────────────

class TestNumericZero:
    def test_accepts_integer_zero(self) -> None:
        assert _numeric_zero(0) is True

    def test_accepts_float_zero(self) -> None:
        assert _numeric_zero(0.0) is True

    def test_accepts_string_zero(self) -> None:
        assert _numeric_zero("0") is True
        assert _numeric_zero("0.0") is True
        assert _numeric_zero("0.00") is True

    def test_rejects_nonzero_number(self) -> None:
        assert _numeric_zero(0.001) is False
        assert _numeric_zero(1) is False
        assert _numeric_zero("0.001") is False

    def test_returns_none_for_none(self) -> None:
        assert _numeric_zero(None) is None

    def test_returns_none_for_empty_string(self) -> None:
        assert _numeric_zero("") is None

    def test_returns_none_for_non_numeric_string(self) -> None:
        assert _numeric_zero("free") is None
        assert _numeric_zero("false") is None
        assert _numeric_zero("null") is None

    # BUG-A.2 regression: boolean False must not be treated as zero price
    def test_rejects_boolean_false_as_zero(self) -> None:
        """JSON false in a pricing field is absent/invalid data, not a price of 0."""
        assert _numeric_zero(False) is None

    def test_rejects_boolean_true_as_zero(self) -> None:
        assert _numeric_zero(True) is None


# ── zero_price_evidence ────────────────────────────────────────────────────────

class TestZeroPriceEvidence:
    def test_returns_true_for_complete_zero_pricing_in_single_source(self) -> None:
        item = {"pricing": {"prompt": 0.0, "completion": 0.0}}
        ok, source = zero_price_evidence(item)
        assert ok is True
        assert source == "provider-models-explicit-zero-pricing"

    def test_returns_true_for_request_field_alone(self) -> None:
        item = {"pricing": {"request": 0.0}}
        ok, source = zero_price_evidence(item)
        assert ok is True
        assert source == "provider-models-explicit-zero-pricing"

    def test_returns_true_when_alternate_key_has_complete_zero_pricing(self) -> None:
        # 'price' key instead of 'pricing'
        item = {"price": {"input": 0.0, "output": 0.0}}
        ok, source = zero_price_evidence(item)
        assert ok is True

    def test_returns_true_from_cost_per_request_zero(self) -> None:
        item = {"billing": {"cost_per_request": 0.0}}
        ok, source = zero_price_evidence(item)
        assert ok is True

    # BUG-A regression: split evidence across two dicts must not produce True
    def test_rejects_split_input_output_across_two_source_dicts(self) -> None:
        """prompt in 'pricing' and completion in 'price' must not combine to True."""
        item = {
            "pricing": {"prompt": 0.0},    # only input side
            "price": {"completion": 0.0},  # only output side
        }
        ok, source = zero_price_evidence(item)
        assert ok is False
        assert source == "provider-pricing-unreported-or-incomplete"

    def test_rejects_split_with_alternative_field_names(self) -> None:
        item = {
            "pricing": {"input": 0.0},
            "cost": {"output": 0.0},
        }
        ok, source = zero_price_evidence(item)
        assert ok is False

    # BUG-A.2 regression: boolean False in pricing field must not produce True
    def test_rejects_boolean_false_in_pricing_fields(self) -> None:
        item = {"pricing": {"prompt": False, "completion": False}}
        ok, source = zero_price_evidence(item)
        assert ok is False
        assert source == "provider-pricing-invalid"

    def test_rejects_nonzero_input_price(self) -> None:
        item = {"pricing": {"prompt": 0.001, "completion": 0.0}}
        ok, source = zero_price_evidence(item)
        assert ok is False
        assert source == "provider-pricing-nonzero"

    def test_rejects_nonzero_output_price(self) -> None:
        item = {"pricing": {"prompt": 0.0, "completion": 0.002}}
        ok, source = zero_price_evidence(item)
        assert ok is False
        assert source == "provider-pricing-nonzero"

    def test_returns_incomplete_when_no_pricing_at_all(self) -> None:
        item: dict = {"id": "test"}
        ok, source = zero_price_evidence(item)
        assert ok is False
        assert source == "provider-pricing-unreported-or-incomplete"

    def test_returns_incomplete_when_only_input_present(self) -> None:
        item = {"pricing": {"prompt": 0.0}}
        ok, source = zero_price_evidence(item)
        assert ok is False
        assert source == "provider-pricing-unreported-or-incomplete"

    def test_returns_incomplete_when_only_output_present(self) -> None:
        item = {"pricing": {"completion": 0.0}}
        ok, source = zero_price_evidence(item)
        assert ok is False
        assert source == "provider-pricing-unreported-or-incomplete"

    def test_complete_first_source_wins_regardless_of_later_sources(self) -> None:
        """When the first source is complete zero-pricing, it wins before any later source is read."""
        item = {
            "pricing": {"prompt": 0.0, "completion": 0.0},  # first source: complete zero evidence
            "price": {"input": 0.001},  # second source: non-zero, but never reached
        }
        ok, source = zero_price_evidence(item)
        assert ok is True  # first complete source wins
        assert source == "provider-models-explicit-zero-pricing"

    def test_invalid_pricing_value_in_first_source_blocks_immediately(self) -> None:
        item = {
            "pricing": {"prompt": None},  # None → invalid
            "price": {"input": 0.0, "output": 0.0},
        }
        ok, source = zero_price_evidence(item)
        assert ok is False
        assert source == "provider-pricing-invalid"


# ── normalize_models_payload (integration) ───────────────────────────────────

class TestNormalizeModelsPayload:
    def _chat_item(self, extra: dict) -> dict:
        return {"id": "test-model", "capabilities": ["chat"], **extra}

    # BUG-A regression
    def test_split_source_pricing_does_not_yield_free_eligible(self) -> None:
        item = self._chat_item({
            "pricing": {"prompt": 0.0},
            "price": {"completion": 0.0},
        })
        result = normalize_models_payload([item])
        assert result[0]["freeEligible"] is False
        assert result[0]["providerCostCatalogState"] == "unreported"

    # BUG-A.2 regression
    def test_bool_false_pricing_not_free_eligible(self) -> None:
        item = self._chat_item({"pricing": {"prompt": False, "completion": False}})
        result = normalize_models_payload([item])
        assert result[0]["freeEligible"] is False
        assert result[0]["eligibilitySource"] == "provider-pricing-invalid"

    def test_legitimate_zero_pricing_yields_free_eligible_with_chat(self) -> None:
        item = self._chat_item({"pricing": {"prompt": 0.0, "completion": 0.0}})
        result = normalize_models_payload([item])
        assert result[0]["freeEligible"] is True
        assert result[0]["eligibilitySource"] == "explicit-provider-zero-cost"
        assert result[0]["providerCostCatalogState"] == "zero"

    def test_nonzero_pricing_not_free_eligible(self) -> None:
        item = self._chat_item({"pricing": {"prompt": 0.0, "completion": 0.001}})
        result = normalize_models_payload([item])
        assert result[0]["freeEligible"] is False
        assert result[0]["providerCostCatalogState"] == "nonzero"

    def test_request_zero_pricing_yields_free_eligible_with_chat(self) -> None:
        # 'billing' is one of the four recognized source keys in zero_price_evidence
        item = self._chat_item({"billing": {"request": 0.0}})
        result = normalize_models_payload([item])
        assert result[0]["freeEligible"] is True
        assert result[0]["eligibilitySource"] == "explicit-provider-zero-cost"
        assert result[0]["providerCostCatalogState"] == "zero"

    def test_managed_quota_contract_grants_eligibility_when_pricing_unreported(self) -> None:
        item = {"id": "managed-model", "capabilities": ["chat"]}
        result = normalize_models_payload([item], managed_quota_contract=True)
        assert result[0]["freeEligible"] is True
        assert result[0]["eligibilitySource"] == "managed-freellm-quota-contract"


# ── Deployment-mirror parity ──────────────────────────────────────────────────

class TestDeploymentMirrorParity:
    """Assert that scripts/sovereign-backend/free_revolver_provider_contracts.py
    produces identical results to the canonical backend/ copy for every
    regression case so divergence cannot re-appear silently."""

    # BUG-A.2: boolean False must be rejected in deployment mirror
    def test_mirror_rejects_boolean_false_as_zero(self) -> None:
        assert _mirror_numeric_zero(False) is None

    def test_mirror_rejects_boolean_true_as_zero(self) -> None:
        assert _mirror_numeric_zero(True) is None

    # BUG-A: split-source seen_* flags must not combine across sources in mirror
    def test_mirror_rejects_split_input_output_across_sources(self) -> None:
        item = {
            "pricing": {"prompt": 0.0},
            "price": {"completion": 0.0},
        }
        ok, source = _mirror_zero_price_evidence(item)
        assert ok is False
        assert source == "provider-pricing-unreported-or-incomplete"

    def test_mirror_rejects_boolean_false_in_pricing_fields(self) -> None:
        item = {"pricing": {"prompt": False, "completion": False}}
        ok, source = _mirror_zero_price_evidence(item)
        assert ok is False
        assert source == "provider-pricing-invalid"

    def test_mirror_accepts_complete_zero_pricing(self) -> None:
        item = {"pricing": {"prompt": 0.0, "completion": 0.0}}
        ok, source = _mirror_zero_price_evidence(item)
        assert ok is True
        assert source == "provider-models-explicit-zero-pricing"

    def test_mirror_normalize_bool_false_not_free_eligible(self) -> None:
        item = {"id": "test-model", "capabilities": ["chat"],
                "pricing": {"prompt": False, "completion": False}}
        result = _mirror_normalize([item])
        assert result[0]["freeEligible"] is False
        assert result[0]["eligibilitySource"] == "provider-pricing-invalid"

    def test_mirror_normalize_split_source_not_free_eligible(self) -> None:
        item = {"id": "test-model", "capabilities": ["chat"],
                "pricing": {"prompt": 0.0},
                "price": {"completion": 0.0}}
        result = _mirror_normalize([item])
        assert result[0]["freeEligible"] is False
        assert result[0]["providerCostCatalogState"] == "unreported"
