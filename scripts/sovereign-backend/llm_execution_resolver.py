"""Database-driven LLM route and agent-profile resolution.

Provider identities and aliases remain in PostgreSQL/LiteLLM. This module only
selects among already active, price-verified routes. It never reads credentials,
registers providers, or treats a provider name as a billing contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from llm_cost_policy import (
    BillingPolicyError,
    FREE_CATEGORY,
    PREMIUM_CATEGORY,
    STANDARD_CATEGORY,
    route_billing_policy,
)
from llm_revolver import build_revolver_candidates, route_is_verified_free, route_quota_scope

FREE_SINGLE_AGENT_PROFILE = "free_single_agent"
PAID_SWARM_PROFILE = "paid_swarm_6"


@dataclass(frozen=True, slots=True)
class ExecutionResolution:
    profile_id: str
    primary_route: dict[str, Any]
    candidate_routes: tuple[dict[str, Any], ...]
    max_foreground_agents: int
    max_background_agents: int
    repository_execution_allowed: bool
    paid_purchase_verified: bool
    provider_funded_credits: int
    reason: str

    def safe_payload(self) -> dict[str, Any]:
        return {
            "profileId": self.profile_id,
            "primaryRouteId": str(self.primary_route.get("id") or ""),
            "primaryModelId": str(
                self.primary_route.get("model_id")
                or self.primary_route.get("modelId")
                or ""
            ),
            "candidateRouteIds": [
                str(route.get("id") or "") for route in self.candidate_routes
            ],
            "maxForegroundAgents": self.max_foreground_agents,
            "maxBackgroundAgents": self.max_background_agents,
            "repositoryExecutionAllowed": self.repository_execution_allowed,
            "paidPurchaseVerified": self.paid_purchase_verified,
            "providerFundedCredits": self.provider_funded_credits,
            "reason": self.reason,
            "secretValuesReturned": False,
        }


def _route_config(route: dict[str, Any]) -> dict[str, Any]:
    config = route.get("config")
    return dict(config) if isinstance(config, dict) else {}


def _model_id(route: dict[str, Any]) -> str:
    return str(route.get("model_id") or route.get("modelId") or "").strip()


def _route_id(route: dict[str, Any]) -> str:
    return str(route.get("id") or "").strip()


def _route_profile(route: dict[str, Any]) -> str:
    return str(_route_config(route).get("executionProfile") or "").strip()


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


def route_is_verified_paid(route: dict[str, Any]) -> bool:
    if bool(route.get("disabled")):
        return False
    if str(route.get("provider") or "").strip().lower() != "litellm":
        return False
    try:
        policy = route_billing_policy(route)
    except BillingPolicyError:
        return False
    return policy["billingCategory"] in {STANDARD_CATEGORY, PREMIUM_CATEGORY}


def _paid_route_available(
    route: dict[str, Any],
    *,
    state_by_scope: dict[str, dict[str, Any]],
    now: datetime,
) -> bool:
    if not route_is_verified_paid(route):
        return False
    try:
        scope = route_quota_scope(route)
    except ValueError:
        return False
    return _state_available(state_by_scope.get(scope), now)


def _ordered_paid_routes(routes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        routes,
        key=lambda route: (
            0 if _route_profile(route) == PAID_SWARM_PROFILE else 1,
            int(route.get("priority") or 0),
            _model_id(route).casefold(),
            _route_id(route),
        ),
    )


def _ordered_free_routes(routes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        routes,
        key=lambda route: (
            int(route.get("priority") or 0),
            _model_id(route).casefold(),
            _route_id(route),
        ),
    )


def build_paid_to_free_candidates(
    primary: dict[str, Any],
    routes: Iterable[dict[str, Any]],
    *,
    state_by_scope: dict[str, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return a paid primary followed by independent ready free quota scopes.

    A free primary keeps the existing free-only revolver behavior. Provider names
    are irrelevant; only active LiteLLM routes and verified billing contracts are
    considered.
    """
    states = state_by_scope or {}
    current_time = now or datetime.now(timezone.utc)
    if route_is_verified_free(primary):
        return build_revolver_candidates(
            primary,
            routes,
            state_by_scope=states,
            now=current_time,
        )
    if not _paid_route_available(
        primary,
        state_by_scope=states,
        now=current_time,
    ):
        return []

    free_routes = _ordered_free_routes(
        route for route in routes if route_is_verified_free(route)
    )
    if not free_routes:
        return [primary]
    free_candidates = build_revolver_candidates(
        free_routes[0],
        free_routes,
        state_by_scope=states,
        now=current_time,
    )
    return [primary, *free_candidates]


def resolve_execution_profile(
    *,
    routes: Iterable[dict[str, Any]],
    state_by_scope: dict[str, dict[str, Any]] | None,
    paid_purchase_verified: bool,
    provider_funded_credits: int,
    requested_model: str = "",
    now: datetime | None = None,
) -> ExecutionResolution | None:
    """Resolve the allowed execution profile from persisted account and route truth."""
    all_routes = [dict(route) for route in routes]
    states = state_by_scope or {}
    current_time = now or datetime.now(timezone.utc)
    normalized_requested = str(requested_model or "").strip()

    paid_routes = [
        route
        for route in _ordered_paid_routes(all_routes)
        if _paid_route_available(route, state_by_scope=states, now=current_time)
    ]
    if normalized_requested:
        requested_paid = next(
            (
                route
                for route in paid_routes
                if normalized_requested in {_route_id(route), _model_id(route)}
            ),
            None,
        )
        if requested_paid:
            paid_routes = [requested_paid, *(
                route for route in paid_routes if _route_id(route) != _route_id(requested_paid)
            )]

    funded = max(0, int(provider_funded_credits))
    if paid_purchase_verified and funded > 0 and paid_routes:
        primary = paid_routes[0]
        candidates = build_paid_to_free_candidates(
            primary,
            all_routes,
            state_by_scope=states,
            now=current_time,
        )
        return ExecutionResolution(
            profile_id=PAID_SWARM_PROFILE,
            primary_route=primary,
            candidate_routes=tuple(candidates or [primary]),
            max_foreground_agents=1,
            max_background_agents=6,
            repository_execution_allowed=True,
            paid_purchase_verified=True,
            provider_funded_credits=funded,
            reason="verified_purchase_and_paid_route_ready",
        )

    free_routes = _ordered_free_routes(
        route for route in all_routes if route_is_verified_free(route)
    )
    if normalized_requested:
        requested_free = next(
            (
                route
                for route in free_routes
                if normalized_requested in {_route_id(route), _model_id(route)}
            ),
            None,
        )
        if requested_free:
            free_routes = [requested_free, *(
                route for route in free_routes if _route_id(route) != _route_id(requested_free)
            )]
    if not free_routes:
        return None
    candidates = build_revolver_candidates(
        free_routes[0],
        free_routes,
        state_by_scope=states,
        now=current_time,
    )
    if not candidates:
        return None
    return ExecutionResolution(
        profile_id=FREE_SINGLE_AGENT_PROFILE,
        primary_route=candidates[0],
        candidate_routes=tuple(candidates),
        max_foreground_agents=1,
        max_background_agents=0,
        repository_execution_allowed=True,
        paid_purchase_verified=bool(paid_purchase_verified),
        provider_funded_credits=funded,
        reason=(
            "paid_route_unavailable_resolved_to_free_revolver"
            if paid_purchase_verified
            else "free_profile_without_verified_purchase"
        ),
    )


def free_fallback_resolution(
    resolution: ExecutionResolution,
    *,
    reason: str,
) -> ExecutionResolution | None:
    """Derive a free single-agent resolution from one paid route magazine."""
    free_candidates = tuple(
        route
        for route in resolution.candidate_routes
        if route_is_verified_free(route)
    )
    if not free_candidates:
        return None
    return ExecutionResolution(
        profile_id=FREE_SINGLE_AGENT_PROFILE,
        primary_route=free_candidates[0],
        candidate_routes=free_candidates,
        max_foreground_agents=1,
        max_background_agents=0,
        repository_execution_allowed=True,
        paid_purchase_verified=resolution.paid_purchase_verified,
        provider_funded_credits=resolution.provider_funded_credits,
        reason=str(reason or "paid_route_failed_resolved_to_free_revolver")[:240],
    )


def load_execution_resolution(
    get_connection: Callable[[], Any],
    *,
    user_id: str,
    requested_model: str = "",
) -> ExecutionResolution | None:
    """Load account entitlement, active routes and revolver state from PostgreSQL."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT account.provider_funded_credits::integer AS provider_funded_credits,
                          EXISTS(
                            SELECT 1
                            FROM transactions AS tx
                            JOIN credit_receipts AS receipt
                              ON receipt.user_id = tx.user_id
                             AND receipt.provider = tx.provider
                             AND receipt.provider_tx_id = tx.provider_tx_id
                            WHERE tx.user_id = account.id
                              AND tx.type = 'credit_purchase'
                              AND tx.status = 'completed'
                          ) AS paid_purchase_verified
                   FROM admin_users AS account
                   WHERE account.id = %s::uuid
                   LIMIT 1""",
                (str(user_id),),
            )
            account = cursor.fetchone()
            if not account:
                raise LookupError("authenticated user account was not found")
            cursor.execute(
                """SELECT id::text, model_id, model_name, provider, base_url,
                          credits_per_unit::float AS credits_per_unit,
                          disabled, priority, config
                   FROM llm_routes
                   WHERE disabled = false AND lower(provider) = 'litellm'
                   ORDER BY priority ASC, model_name ASC"""
            )
            routes = [dict(row) for row in cursor.fetchall()]
            scopes: list[str] = []
            for route in routes:
                try:
                    scopes.append(route_quota_scope(route))
                except ValueError:
                    continue
            if scopes:
                cursor.execute(
                    """SELECT quota_scope, status, cooldown_until
                       FROM llm_route_revolver_state
                       WHERE quota_scope = ANY(%s)""",
                    (scopes,),
                )
                states = {
                    str(row["quota_scope"]): dict(row)
                    for row in cursor.fetchall()
                }
            else:
                states = {}
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()

    return resolve_execution_profile(
        routes=routes,
        state_by_scope=states,
        paid_purchase_verified=bool(account["paid_purchase_verified"]),
        provider_funded_credits=int(account["provider_funded_credits"] or 0),
        requested_model=requested_model,
    )
