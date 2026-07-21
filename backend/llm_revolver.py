"""Deterministic, price-gated free-route revolver policy.

The module is intentionally side-effect free. PostgreSQL persistence and LiteLLM
network calls stay in app.py so candidate selection and retry decisions can be
unit-tested without credentials or a running provider.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from llm_cost_policy import BillingPolicyError, FREE_CATEGORY, route_billing_policy

_SCOPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_RETRY_WINDOWS_SECONDS = {
    "provider_quota_exhausted": 3600,
    "provider_rate_limited": 60,
    "litellm_upstream_unavailable": 30,
}
_BLOCKED_FAILURES = {
    "provider_credentials_rejected",
    "litellm_model_alias_missing",
    "litellm_model_alias_invalid",
}


def default_quota_scope(route_id: Any) -> str:
    """Return an opaque stable fallback scope without exposing route or key material."""
    digest = hashlib.sha256(str(route_id or "missing-route").encode("utf-8")).hexdigest()
    return f"litellm:route:{digest[:24]}"


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
    return normalize_quota_scope(config.get("quotaScope"), route_id=route.get("id"))


def route_is_verified_free(route: dict[str, Any]) -> bool:
    if bool(route.get("disabled")):
        return False
    if str(route.get("provider") or "").strip().lower() != "litellm":
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


def _state_available(state: dict[str, Any] | None, now: datetime) -> bool:
    if not state:
        return True
    status = str(state.get("status") or "ready").strip().lower()
    if status == "blocked":
        return False
    cooldown_until = state.get("cooldown_until") or state.get("cooldownUntil")
    if status != "cooldown" or cooldown_until is None:
        return True
    if isinstance(cooldown_until, str):
        try:
            cooldown_until = datetime.fromisoformat(cooldown_until.replace("Z", "+00:00"))
        except ValueError:
            return False
    if not isinstance(cooldown_until, datetime):
        return False
    if cooldown_until.tzinfo is None:
        cooldown_until = cooldown_until.replace(tzinfo=timezone.utc)
    return cooldown_until <= now


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
    ordered = [primary, *sorted(
        (route for route in routes if str(route.get("id")) != str(primary.get("id"))),
        key=lambda route: (
            int(route.get("priority") or 0),
            str(route.get("model_id") or route.get("modelId") or "").casefold(),
            str(route.get("id") or ""),
        ),
    )]
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
