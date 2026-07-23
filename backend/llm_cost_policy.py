"""Three-category provider-cost policy for Sovereign LLM billing.

The categories are deliberately small and stable:
- free: zero verified provider cost, reserved for the Revolver
- standard: at least 4x real provider cost
- premium: at least 8x real provider cost

All money calculations use integer micro-US-dollars. Paid calls are reserved
before provider execution and settled from direct-provider cost evidence or verified
usage/pricing metadata. Multipliers may only be raised, never lowered below the
category floor.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any, Final

AGENTS_LITELLM_ALIAS: Final[str] = "sovereign-fast"
AGENTS_PROVIDER_MODEL: Final[str] = "gpt-5.4-mini"
FREE_CATEGORY: Final[str] = "free"
STANDARD_CATEGORY: Final[str] = "standard"
PREMIUM_CATEGORY: Final[str] = "premium"
FREE_FUNDING_VERIFIED_ZERO_COST: Final[str] = "verified_zero_cost"
FREE_FUNDING_PROVIDER_QUOTA: Final[str] = "provider_free_quota"
BILLING_CATEGORIES: Final[frozenset[str]] = frozenset(
    {FREE_CATEGORY, STANDARD_CATEGORY, PREMIUM_CATEGORY}
)
CATEGORY_MINIMUM_MULTIPLIERS: Final[dict[str, int]] = {
    FREE_CATEGORY: 0,
    STANDARD_CATEGORY: 4,
    PREMIUM_CATEGORY: 8,
}
STANDARD_MARKUP_MULTIPLIER: Final[int] = CATEGORY_MINIMUM_MULTIPLIERS[STANDARD_CATEGORY]
PREMIUM_MARKUP_MULTIPLIER: Final[int] = CATEGORY_MINIMUM_MULTIPLIERS[PREMIUM_CATEGORY]
USD_MICROS_PER_CREDIT: Final[int] = 1_000
MIN_PACKAGE_EUR_PER_CREDIT: Final[Decimal] = Decimal("0.0016")

class BillingPolicyError(ValueError):
    """Route or package cannot safely finance an external provider call."""


def _decimal(value: Any, *, field: str) -> Decimal:
    if value is None or value == "":
        raise BillingPolicyError(f"{field} is required")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BillingPolicyError(f"{field} is invalid") from exc
    if not parsed.is_finite() or parsed < 0:
        raise BillingPolicyError(f"{field} must be a non-negative finite number")
    return parsed


def _ceil_decimal(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def normalize_billing_category(value: Any) -> str:
    category = str(value or "").strip().lower()
    if category not in BILLING_CATEGORIES:
        raise BillingPolicyError("billingCategory must be free, standard or premium")
    return category


def category_minimum_multiplier(category: Any) -> int:
    return CATEGORY_MINIMUM_MULTIPLIERS[normalize_billing_category(category)]


def normalize_funding_mode(category: Any, configured: Any = None) -> str:
    normalized_category = normalize_billing_category(category)
    if normalized_category != FREE_CATEGORY:
        return "provider_priced"
    mode = str(configured or FREE_FUNDING_VERIFIED_ZERO_COST).strip().lower()
    if mode not in {FREE_FUNDING_VERIFIED_ZERO_COST, FREE_FUNDING_PROVIDER_QUOTA}:
        raise BillingPolicyError(
            "free fundingMode must be verified_zero_cost or provider_free_quota"
        )
    return mode


def normalized_multiplier(category: Any, configured: Any = None) -> int:
    normalized_category = normalize_billing_category(category)
    minimum = category_minimum_multiplier(normalized_category)
    if normalized_category == FREE_CATEGORY:
        if configured not in (None, "", 0, "0", 0.0):
            raise BillingPolicyError("free routes must use markupMultiplier 0")
        return 0
    try:
        value = int(configured if configured not in (None, "") else minimum)
    except (TypeError, ValueError) as exc:
        raise BillingPolicyError("markupMultiplier is invalid") from exc
    if value < minimum:
        raise BillingPolicyError(
            f"{normalized_category} routes require markupMultiplier >= {minimum}"
        )
    if value > 10_000:
        raise BillingPolicyError("markupMultiplier is outside the allowed range")
    return value


def _route_prices(config: dict[str, Any], provider_model: str) -> dict[str, Decimal]:
    return {
        "input": _decimal(config.get("inputUsdPerMillion"), field="inputUsdPerMillion"),
        "cachedInput": _decimal(
            config.get("cachedInputUsdPerMillion"),
            field="cachedInputUsdPerMillion",
        ),
        "output": _decimal(config.get("outputUsdPerMillion"), field="outputUsdPerMillion"),
    }


def route_billing_policy(route: Any) -> dict[str, Any]:
    row = dict(route or {})
    config = row.get("config") if isinstance(row.get("config"), dict) else {}
    provider_model = str(config.get("providerModel") or "").strip()
    category = normalize_billing_category(
        config.get("billingCategory") or config.get("billingClass")
    )
    multiplier = normalized_multiplier(category, config.get("markupMultiplier"))
    funding_mode = normalize_funding_mode(category, config.get("fundingMode"))
    prices = _route_prices(config, provider_model)
    pricing_verified = bool(config.get("pricingVerified"))

    if not provider_model:
        raise BillingPolicyError("providerModel is required")
    if prices["cachedInput"] > prices["input"]:
        raise BillingPolicyError("cached input price cannot exceed input price")
    if category == FREE_CATEGORY:
        if funding_mode == FREE_FUNDING_VERIFIED_ZERO_COST:
            if any(price != 0 for price in prices.values()):
                raise BillingPolicyError("free routes require verified zero provider prices")
        elif prices["input"] <= 0 or prices["output"] <= 0:
            raise BillingPolicyError(
                "provider_free_quota routes require positive verified provider list prices"
            )
    elif prices["input"] <= 0 or prices["output"] <= 0:
        raise BillingPolicyError("paid routes require positive input and output prices")
    if not pricing_verified:
        raise BillingPolicyError("route pricing is not verified")

    return {
        "billingCategory": category,
        "billingClass": category,
        "providerModel": provider_model,
        "markupMultiplier": multiplier,
        "fundingMode": funding_mode,
        "inputUsdPerMillion": prices["input"],
        "cachedInputUsdPerMillion": prices["cachedInput"],
        "outputUsdPerMillion": prices["output"],
        "usdMicrosPerCredit": USD_MICROS_PER_CREDIT,
        "pricingVerified": True,
        "pricingSource": str(config.get("pricingSource") or "verified-route-config").strip(),
    }


def provider_cost_micros_from_usage(
    *,
    prompt_tokens: int,
    cached_prompt_tokens: int,
    completion_tokens: int,
    policy: dict[str, Any],
) -> int:
    prompt = max(0, int(prompt_tokens))
    cached = min(prompt, max(0, int(cached_prompt_tokens)))
    uncached = prompt - cached
    output = max(0, int(completion_tokens))
    cost_usd = (
        Decimal(uncached) * policy["inputUsdPerMillion"]
        + Decimal(cached) * policy["cachedInputUsdPerMillion"]
        + Decimal(output) * policy["outputUsdPerMillion"]
    ) / Decimal(1_000_000)
    return max(0, _ceil_decimal(cost_usd * Decimal(1_000_000)))


def provider_cost_usd_to_micros(value: Any) -> int | None:
    if value is None or value == "":
        return None
    parsed = _decimal(value, field="providerCostUsd")
    return max(0, _ceil_decimal(parsed * Decimal(1_000_000)))


def billed_credits_for_provider_cost(
    provider_cost_usd_micros: int,
    *,
    markup_multiplier: int,
) -> int:
    cost = max(0, int(provider_cost_usd_micros))
    multiplier = max(0, int(markup_multiplier))
    if cost == 0 or multiplier == 0:
        return 0
    return max(
        1,
        (cost * multiplier + USD_MICROS_PER_CREDIT - 1) // USD_MICROS_PER_CREDIT,
    )


def reservation_credits(
    *,
    input_token_upper_bound: int,
    output_token_limit: int,
    request_upper_bound: int,
    policy: dict[str, Any],
) -> tuple[int, int]:
    requests = max(1, int(request_upper_bound))
    per_request_cost = provider_cost_micros_from_usage(
        prompt_tokens=max(1, int(input_token_upper_bound)),
        cached_prompt_tokens=0,
        completion_tokens=max(1, int(output_token_limit)),
        policy=policy,
    )
    total_provider_cost = per_request_cost * requests
    credits = billed_credits_for_provider_cost(
        total_provider_cost,
        markup_multiplier=int(policy["markupMultiplier"]),
    )
    return credits, total_provider_cost


def package_has_cash_buffer(*, credits: int, price_eur: Any) -> bool:
    normalized_credits = int(credits)
    if normalized_credits <= 0:
        return False
    price = _decimal(price_eur, field="priceEur")
    return price >= Decimal(normalized_credits) * MIN_PACKAGE_EUR_PER_CREDIT


def require_package_cash_buffer(*, credits: int, price_eur: Any) -> None:
    if not package_has_cash_buffer(credits=credits, price_eur=price_eur):
        minimum = Decimal(int(credits)) * MIN_PACKAGE_EUR_PER_CREDIT
        raise BillingPolicyError(
            f"package price must be at least EUR {minimum.quantize(Decimal('0.01'), rounding=ROUND_CEILING)}"
        )
