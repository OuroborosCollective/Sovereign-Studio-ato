"""Deterministic, price-gated direct-FreeLLM revolver policy.

The module is intentionally side-effect free. PostgreSQL persistence and provider
network calls stay in runtime modules so candidate selection and retry decisions
can be unit-tested without credentials or a running provider.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from llm_cost_policy import BillingPolicyError, FREE_CATEGORY, route_billing_policy
from llm_transport import (
    FREELLM_TRANSPORT,
    LEGACY_LITELLM_TRANSPORT,
    route_is_direct_freellm,
    route_transport,
)

_SCOPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_RETRY_WINDOWS_SECONDS = {
    "provider_quota_exhausted": 3600,
    "provider_rate_limited": 60,
    "litellm_upstream_unavailable": 30,
    "openrouter_rate_limited": 60,
    "openrouter_timeout": 30,
    "openrouter_upstream_unavailable": 30,
    "freellm_rate_limited": 60,
    "freellm_timeout": 30,
    "freellm_upstream_unavailable": 30,
}
_BLOCKED_FAILURES = {
    "provider_credentials_rejected",
    "litellm_model_alias_missing",
    "litellm_model_alias_invalid",
    "openrouter_credentials_rejected",
    "freellm_credentials_rejected",
}


def default_quota_scope(
    route_id: Any,
    *,
    transport: str = LEGACY_LITELLM_TRANSPORT,
) -> str:
    """Return an opaque stable fallback scope without exposing route or key material."""
    normalized_transport = route_transport({
        "provider": transport,
        "runtime_kind": transport,
    }) or LEGACY_LITELLM_TRANSPORT
    digest = hashlib.sha256(str(route_id or "missing-route").encode("utf-8")).hexdigest()
    return f"{normalized_transport}:route:{digest[:24]}"


def normalize_quota_scope(value: Any, *, route_id: Any) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return default_quota_scope(route_id)
    if not _SCOPE_RE.fullmatch(candidate):
        raise ValueError(
            "quotaScope muss 8-128 Zeichen lang sein und darf nur Buchstaben, "
            "Zahlen, Punkt, Unterstrich, Doppelpunkt oder Bindestrich enthalten"
        )
    return candidate


def route_quota_scope(route: dict[str, Any]) -> str:
    config = route.get("config") if isinstance(route.get("config"), dict) else {}
    configured = config.get("quotaScope")
    if configured:
        return normalize_quota_scope(configured, route_id=route.get("id"))
    return default_quota_scope(
        route.get("id"),
        transport=route_transport(route) or LEGACY_LITELLM_TRANSPORT,
    )


def route_is_verified_free(route: dict[str, Any]) -> bool:
    if not route_is_direct_freellm(route):
        return False
    if route_transport(route) != FREELLM_TRANSPORT:
        return False
    try:
        policy = route_billing_policy(route)
    except BillingPolicyError:
        return False
    return (
        policy["billingCategory"] == FREE_CATEGORY
        and bool(policy["pricingVerified"])
        and int(policy["markupMultiplier"]) == 0
    )


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _first_number(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        parsed = _number(value)
        if parsed is not None:
            return parsed
    return None


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _quota_rank(
    route: dict[str, Any],
    state: dict[str, Any] | None,
    *,
    primary_id: str,
) -> tuple[Any, ...]:
    config = route.get("config") if isinstance(route.get("config"), dict) else {}
    current = state or {}
    remaining = _first_number(
        current.get("quota_remaining"),
        current.get("quotaRemaining"),
        config.get("quotaRemaining"),
    )
    limit = _first_number(
        current.get("quota_limit"),
        current.get("quotaLimit"),
        config.get("quotaLimit"),
    )
    ratio = remaining / limit if remaining is not None and limit and limit > 0 else remaining
    availability = 0 if remaining is not None and remaining > 0 else 2 if remaining == 0 else 1
    return (
        availability,
        -(ratio if ratio is not None else 0),
        int(current.get("consecutive_failures") or current.get("consecutiveFailures") or 0),
        int(route.get("priority") or 0),
        0 if str(route.get("id") or "") == primary_id else 1,
        str(route.get("model_id") or route.get("modelId") or "").casefold(),
        str(route.get("id") or ""),
    )


def _state_available(state: dict[str, Any] | None, now: datetime) -> bool:
    if not state:
        return True
    status = str(state.get("status") or "ready").strip().lower()
    if status == "blocked":
        return False
    remaining = _first_number(
        state.get("quota_remaining"),
        state.get("quotaRemaining"),
    )
    quota_reset = _as_datetime(
        state.get("quota_reset_at") or state.get("quotaResetAt")
    )
    if remaining == 0 and quota_reset is not None and quota_reset > now:
        return False
    cooldown_until = _as_datetime(
        state.get("cooldown_until") or state.get("cooldownUntil")
    )
    if status != "cooldown":
        return True
    return cooldown_until is not None and cooldown_until <= now


def build_revolver_candidates(
    primary: dict[str, Any],
    routes: Iterable[dict[str, Any]],
    *,
    state_by_scope: dict[str, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return verified free routes, primary first, with one route per quota scope."""
    if not route_is_verified_free(primary):
        return [primary]
    state_by_scope = state_by_scope or {}
    current_time = now or datetime.now(timezone.utc)
    primary_id = str(primary.get("id") or "")
    verified_routes = [
        route for route in routes if route_is_verified_free(route)
    ]
    if not any(str(route.get("id") or "") == primary_id for route in verified_routes):
        verified_routes.append(primary)
    ordered = sorted(
        verified_routes,
        key=lambda route: _quota_rank(
            route,
            state_by_scope.get(route_quota_scope(route)),
            primary_id=primary_id,
        ),
    )
    candidates: list[dict[str, Any]] = []
    seen_scopes: set[str] = set()
    for route in ordered:
        if not route_is_verified_free(route):
            continue
        scope = route_quota_scope(route)
        if scope in seen_scopes or not _state_available(state_by_scope.get(scope), current_time):
            continue
        candidates.append(route)
        seen_scopes.add(scope)
    return candidates


def provider_usage_seen(evidence: dict[str, Any]) -> bool:
    """An upstream request id alone is not billable usage evidence."""
    try:
        if int(evidence.get("totalTokens") or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    try:
        cost = evidence.get("providerCostUsd")
        return cost is not None and float(cost) > 0
    except (TypeError, ValueError):
        return False


def failure_decision(classified: dict[str, Any], *, usage_seen: bool) -> dict[str, Any]:
    blocker = str(classified.get("blocker") or "provider_rejected")[:120]
    if usage_seen:
        return {
            "blocker": blocker,
            "retryAllowed": False,
            "state": "blocked",
            "cooldownSeconds": 0,
        }
    if blocker in _RETRY_WINDOWS_SECONDS:
        return {
            "blocker": blocker,
            "retryAllowed": True,
            "state": "cooldown",
            "cooldownSeconds": _RETRY_WINDOWS_SECONDS[blocker],
        }
    return {
        "blocker": blocker,
        "retryAllowed": False,
        "state": "blocked" if blocker in _BLOCKED_FAILURES else "ready",
        "cooldownSeconds": 0,
    }
