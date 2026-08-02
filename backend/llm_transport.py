"""Provider-neutral route identity for Sovereign LLM execution."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Final

OPENROUTER_TRANSPORT: Final[str] = "openrouter"
FREELLM_TRANSPORT: Final[str] = "freellm"
LEGACY_LITELLM_TRANSPORT: Final[str] = "litellm"
OPENROUTER_BASE_URL: Final[str] = "https://openrouter.ai/api/v1"
FREELLM_BASE_URL: Final[str] = "http://freellmapi:3001/v1"
FREELLMPOOL_BASE_URL: Final[str] = "http://freellmpool:8080/v1"
FREELLM_BASE_URLS: Final[frozenset[str]] = frozenset(
    {FREELLM_BASE_URL, FREELLMPOOL_BASE_URL}
)
SUPPORTED_EXECUTION_TRANSPORTS: Final[frozenset[str]] = frozenset(
    {OPENROUTER_TRANSPORT, FREELLM_TRANSPORT}
)


def route_config(route: dict[str, Any]) -> dict[str, Any]:
    value = route.get("config")
    return dict(value) if isinstance(value, dict) else {}


def normalize_transport(value: Any) -> str:
    transport = str(value or "").strip().lower()
    if transport in {"freellmapi", "free-llm", "free_llm"}:
        return FREELLM_TRANSPORT
    return transport


def route_transport(route: dict[str, Any]) -> str:
    config = route_config(route)
    for value in (
        config.get("transport"),
        route.get("runtime_kind"),
        route.get("runtimeKind"),
        route.get("provider"),
    ):
        normalized = normalize_transport(value)
        if normalized:
            return normalized
    return ""


def route_provider_model(route: dict[str, Any]) -> str:
    config = route_config(route)
    return str(
        config.get("providerModel")
        or route.get("model_id")
        or route.get("modelId")
        or ""
    ).strip()


def route_profile(route: dict[str, Any]) -> str:
    return str(route_config(route).get("executionProfile") or "").strip()


def route_api_base(route: dict[str, Any]) -> str:
    return str(route.get("base_url") or route.get("baseUrl") or "").strip().rstrip("/")


def route_supported_roles(route: dict[str, Any]) -> frozenset[str]:
    config = route_config(route)
    roles = config.get("supportedExecutionRoles")
    if not isinstance(roles, list):
        return frozenset()
    return frozenset(str(role).strip() for role in roles if str(role).strip())


def route_is_openrouter_paid(route: dict[str, Any]) -> bool:
    config = route_config(route)
    policy = config.get("providerPolicy")
    return (
        not bool(route.get("disabled"))
        and route_transport(route) == OPENROUTER_TRANSPORT
        and route_profile(route) == "paid_swarm_6"
        and route_api_base(route) == OPENROUTER_BASE_URL
        and config.get("direct") is True
        and config.get("catalogVerified") is True
        and config.get("transportCanaryVerified") is True
        and config.get("selectable") is True
        and {"main", "swarm_agents"}.issubset(route_supported_roles(route))
        and isinstance(policy, dict)
        and policy.get("require_parameters") is True
        and policy.get("allow_fallbacks") is False
        and policy.get("data_collection") == "deny"
    )


def route_is_direct_freellm(route: dict[str, Any]) -> bool:
    config = route_config(route)
    return (
        not bool(route.get("disabled"))
        and route_transport(route) == FREELLM_TRANSPORT
        and route_profile(route) == "free_single_agent"
        and route_api_base(route) in FREELLM_BASE_URLS
        and config.get("direct") is True
    )


def _snapshot_canonical(value: Any) -> Any:
    """Normalize route snapshots without floats or implicit object ordering."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, (float, Decimal)):
        try:
            decimal_value = Decimal(str(value)).normalize()
        except InvalidOperation as exc:
            raise ValueError("route snapshot contains an invalid decimal") from exc
        return format(decimal_value, "f")
    if isinstance(value, dict):
        return {
            str(key): _snapshot_canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_snapshot_canonical(item) for item in value]
    raise ValueError(f"unsupported route snapshot value: {type(value).__name__}")


def _price_decimal(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("price snapshot values must be numeric or null")
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except InvalidOperation as exc:
        raise ValueError("price snapshot contains an invalid decimal") from exc


def route_snapshot_hashes(route: dict[str, Any]) -> tuple[str, str]:
    config = route_config(route)
    provider_policy = config.get("providerPolicy")
    route_snapshot = {
        "schemaVersion": "sovereign.llm-route-snapshot.v2",
        "routeId": str(route.get("id") or ""),
        "transport": route_transport(route),
        "providerModel": route_provider_model(route),
        "apiBase": route_api_base(route),
        "executionProfile": route_profile(route),
        "billingCategory": str(
            config.get("billingCategory") or config.get("billingClass") or ""
        ).strip(),
        "fundingMode": str(config.get("fundingMode") or "").strip(),
        "direct": config.get("direct") is True,
        "catalogVerified": config.get("catalogVerified") is True,
        "transportCanaryVerified": config.get("transportCanaryVerified") is True,
        "selectable": config.get("selectable") is True,
        "supportedExecutionRoles": sorted(route_supported_roles(route)),
        "providerPolicy": (
            {
                "require_parameters": provider_policy.get("require_parameters"),
                "allow_fallbacks": provider_policy.get("allow_fallbacks"),
                "data_collection": provider_policy.get("data_collection"),
                "zdr": provider_policy.get("zdr"),
            }
            if isinstance(provider_policy, dict)
            else {}
        ),
        "freeEligible": config.get("freeEligible") is True,
        "quotaContractVerified": config.get("quotaContractVerified") is True,
    }
    price_snapshot = {
        "schemaVersion": "sovereign.llm-price-snapshot.v2",
        "numericEncoding": "canonical-decimal-string-v1",
        "inputUsdPerMillion": _price_decimal(config.get("inputUsdPerMillion")),
        "cachedInputUsdPerMillion": _price_decimal(config.get("cachedInputUsdPerMillion")),
        "outputUsdPerMillion": _price_decimal(config.get("outputUsdPerMillion")),
        "markupMultiplier": _price_decimal(config.get("markupMultiplier")),
        "pricingSource": config.get("pricingSource"),
        "pricingVerified": bool(config.get("pricingVerified")),
    }

    def digest(value: dict[str, Any]) -> str:
        encoded = json.dumps(
            _snapshot_canonical(value),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    return digest(route_snapshot), digest(price_snapshot)
