"""Provider-neutral route identity for Sovereign LLM execution."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

OPENROUTER_TRANSPORT: Final[str] = "openrouter"
FREELLM_TRANSPORT: Final[str] = "freellm"
LEGACY_LITELLM_TRANSPORT: Final[str] = "litellm"
OPENROUTER_BASE_URL: Final[str] = "https://openrouter.ai/api/v1"
FREELLM_BASE_URL: Final[str] = "http://freellmapi:3001/v1"
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
        and policy.get("zdr") is True
    )


def route_is_direct_freellm(route: dict[str, Any]) -> bool:
    config = route_config(route)
    return (
        not bool(route.get("disabled"))
        and route_transport(route) == FREELLM_TRANSPORT
        and route_profile(route) == "free_single_agent"
        and route_api_base(route) == FREELLM_BASE_URL
        and config.get("direct") is True
    )


def route_snapshot_hashes(route: dict[str, Any]) -> tuple[str, str]:
    config = route_config(route)
    route_snapshot = {
        "routeId": str(route.get("id") or ""),
        "transport": route_transport(route),
        "providerModel": route_provider_model(route),
        "apiBase": route_api_base(route),
        "executionProfile": route_profile(route),
        "billingCategory": str(
            config.get("billingCategory") or config.get("billingClass") or ""
        ).strip(),
        "fundingMode": str(config.get("fundingMode") or "").strip(),
    }
    price_snapshot = {
        "inputUsdPerMillion": config.get("inputUsdPerMillion"),
        "cachedInputUsdPerMillion": config.get("cachedInputUsdPerMillion"),
        "outputUsdPerMillion": config.get("outputUsdPerMillion"),
        "markupMultiplier": config.get("markupMultiplier"),
        "pricingSource": config.get("pricingSource"),
        "pricingVerified": bool(config.get("pricingVerified")),
    }

    def digest(value: dict[str, Any]) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    return digest(route_snapshot), digest(price_snapshot)
