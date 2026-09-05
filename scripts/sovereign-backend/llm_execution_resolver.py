"""Database-driven LLM transport, route, and agent-profile resolution.

The paid OpenRouter transport and direct managed FreeLLM transport remain
independent. This module selects only active, policy-verified routes; it never
reads credentials, registers providers, or treats a model alias as a transport.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any, Callable, Iterable

from llm_cost_policy import (
    BillingPolicyError,
    FREE_CATEGORY,
    PREMIUM_CATEGORY,
    STANDARD_CATEGORY,
    route_billing_policy,
)
from llm_revolver import build_revolver_candidates, route_is_verified_free, route_quota_scope
from llm_transport import (
    FREELLM_TRANSPORT,
    OPENROUTER_TRANSPORT,
    route_is_openrouter_paid,
    route_provider_model,
    route_snapshot_hashes,
    route_transport,
    route_transport_diagnostics,
)
from paid_execution_entitlement import resolve_paid_execution_entitlement

FREE_SINGLE_AGENT_PROFILE = "free_single_agent"
FREE_SWARM_PROFILE = "free_swarm_6"
PAID_SWARM_PROFILE = "paid_swarm_6"
FREE_SWARM_MIN_READY_ROUTES = 7
AUTO_MODE = "auto"
PAID_MODE = "paid"
FREE_MODE = "free"
EXECUTION_MODES = frozenset({AUTO_MODE, PAID_MODE, FREE_MODE})


class ExecutionResolutionError(RuntimeError):
    """Typed, secret-safe resolution failure for an explicitly requested mode."""

    def __init__(
        self,
        failure_family: str,
        message: str,
        *,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_family = str(failure_family)
        self.status_code = int(status_code)
        self.details = dict(details or {})

    def safe_payload(self) -> dict[str, Any]:
        payload = {
            "error": self.failure_family,
            "message": str(self),
            "statusCode": self.status_code,
            "secretValuesReturned": False,
        }
        if self.details:
            payload["details"] = self.details
        return payload


def normalize_execution_mode(value: Any) -> str:
    mode = str(value or AUTO_MODE).strip().lower()
    if mode not in EXECUTION_MODES:
        raise ExecutionResolutionError(
            "invalid_execution_mode",
            "execution mode must be one of: auto, paid, free",
            status_code=422,
        )
    return mode


@dataclass(frozen=True, slots=True)
class ExecutionResolution:
    profile_id: str
    primary_route: dict[str, Any]
    agent_route: dict[str, Any]
    candidate_routes: tuple[dict[str, Any], ...]
    max_foreground_agents: int
    max_background_agents: int
    repository_execution_allowed: bool
    paid_purchase_verified: bool
    paid_entitlement_verified: bool
    paid_entitlement_source: str
    provider_funded_credits: int
    requested_mode: str
    reason: str
    fallback_from_transport: str | None = None

    def safe_payload(self) -> dict[str, Any]:
        main_route_hash, main_price_hash = route_snapshot_hashes(self.primary_route)
        agent_route_hash, agent_price_hash = route_snapshot_hashes(self.agent_route)
        billing = route_billing_policy(self.primary_route)
        transport = route_transport(self.primary_route)
        billing_category = str(billing["billingCategory"])
        if transport == FREELLM_TRANSPORT and billing_category == FREE_CATEGORY:
            transport_class = "FREELLM_FREE"
            pricing_display = "free (provider quota)"
        elif transport == OPENROUTER_TRANSPORT and billing_category == FREE_CATEGORY:
            transport_class = "OPENROUTER_FREE"
            pricing_display = "free (provider quota)"
        elif transport == OPENROUTER_TRANSPORT:
            transport_class = "OPENROUTER_PAID"
            pricing_display = "paid (OpenRouter)"
        else:
            transport_class = "UNRESOLVED"
            pricing_display = "unresolved"
        return {
            "profileId": self.profile_id,
            "primaryRouteId": str(self.primary_route.get("id") or ""),
            "primaryModelId": str(
                self.primary_route.get("model_id")
                or self.primary_route.get("modelId")
                or ""
            ),
            "providerModel": route_provider_model(self.primary_route),
            "mainRouteId": str(self.primary_route.get("id") or ""),
            "mainModel": route_provider_model(self.primary_route),
            "agentRouteId": str(self.agent_route.get("id") or ""),
            "agentModel": route_provider_model(self.agent_route),
            "resolvedTransport": transport,
            "resolvedTransportClass": transport_class,
            "billingCategory": billing_category,
            "fundingMode": str(billing["fundingMode"]),
            "pricingDisplay": pricing_display,
            "requestedMode": self.requested_mode,
            "fallbackFromTransport": self.fallback_from_transport,
            "candidateRouteIds": [
                str(route.get("id") or "") for route in self.candidate_routes
            ],
            "maxForegroundAgents": self.max_foreground_agents,
            "maxBackgroundAgents": self.max_background_agents,
            "repositoryExecutionAllowed": self.repository_execution_allowed,
            "paidPurchaseVerified": self.paid_purchase_verified,
            "paidEntitlementVerified": self.paid_entitlement_verified,
            "paidEntitlementSource": self.paid_entitlement_source,
            "providerFundedCredits": self.provider_funded_credits,
            "routeSnapshotSha256": main_route_hash,
            "priceSnapshotSha256": main_price_hash,
            "mainRouteSnapshotSha256": main_route_hash,
            "mainPriceSnapshotSha256": main_price_hash,
            "agentRouteSnapshotSha256": agent_route_hash,
            "agentPriceSnapshotSha256": agent_price_hash,
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


def _route_matches(route: dict[str, Any], requested: str) -> bool:
    normalized = str(requested or "").strip()
    return normalized in {
        _route_id(route),
        _model_id(route),
        route_provider_model(route),
    }


def _route_profile(route: dict[str, Any]) -> str:
    return str(_route_config(route).get("executionProfile") or "").strip()


def _first_transport_failure(
    routes: Iterable[dict[str, Any]],
    *,
    profiles: frozenset[str],
) -> dict[str, Any] | None:
    for route in routes:
        if bool(route.get("disabled")) or _route_profile(route) not in profiles:
            continue
        diagnostic = route_transport_diagnostics(route)
        if diagnostic.get("ok") is not True:
            return {
                "routeId": str(diagnostic.get("routeId") or ""),
                "transportFailureFamily": str(
                    diagnostic.get("failureFamily") or "route_transport_invalid"
                ),
                "sourceFields": dict(diagnostic.get("sourceFields") or {}),
                "secretValuesReturned": False,
            }
    return None


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
    if not route_is_openrouter_paid(route):
        return False
    if route_transport(route) != OPENROUTER_TRANSPORT:
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


def _free_swarm_route_capable(route: dict[str, Any]) -> bool:
    """Require explicit persisted workspace/tool eligibility in addition to free-route canaries."""
    config = _route_config(route)
    return route_is_verified_free(route) and config.get("repositoryExecutionAllowed") is True


def _free_swarm_candidate_order(candidates: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    ordered = list(candidates)
    capable = [route for route in ordered if _free_swarm_route_capable(route)]
    ready = len(capable) >= FREE_SWARM_MIN_READY_ROUTES
    if not ready:
        return ordered, False
    capable_ids = {_route_id(route) for route in capable}
    return [*capable, *(route for route in ordered if _route_id(route) not in capable_ids)], True


def build_paid_to_free_candidates(
    primary: dict[str, Any],
    routes: Iterable[dict[str, Any]],
    *,
    state_by_scope: dict[str, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return a paid primary followed by independent ready free quota scopes.

    A free primary keeps the existing free-only revolver behavior. Paid and free
    candidates retain disjoint transports and quota scopes.
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
    # Invalid/disabled primary identities still fail closed. A verified paid
    # route in budget/quota cooldown must not erase independent free routes.
    if not route_is_verified_paid(primary):
        return []
    paid_available = _paid_route_available(
        primary,
        state_by_scope=states,
        now=current_time,
    )

    free_routes = _ordered_free_routes(
        route for route in routes if route_is_verified_free(route)
    )
    if not free_routes:
        return [primary] if paid_available else []
    free_candidates = build_revolver_candidates(
        free_routes[0],
        free_routes,
        state_by_scope=states,
        now=current_time,
    )
    return [*([primary] if paid_available else []), *free_candidates]


def resolve_execution_profile(
    *,
    routes: Iterable[dict[str, Any]],
    state_by_scope: dict[str, dict[str, Any]] | None,
    paid_purchase_verified: bool,
    provider_funded_credits: int,
    credit_balance: int = 0,
    paid_entitlement_verified: bool | None = None,
    paid_entitlement_source: str = "",
    requested_model: str = "",
    requested_main_model: str = "",
    requested_agent_model: str = "",
    requested_mode: str = AUTO_MODE,
    now: datetime | None = None,
) -> ExecutionResolution | None:
    """Resolve one explicit paid model pair or an automatic direct-FreeLLM route."""
    mode = normalize_execution_mode(requested_mode)
    all_routes = [dict(route) for route in routes]
    states = state_by_scope or {}
    current_time = now or datetime.now(timezone.utc)
    legacy_requested = str(requested_model or "").strip()
    main_requested = str(requested_main_model or legacy_requested).strip()
    agent_requested = str(requested_agent_model or legacy_requested).strip()
    funded = max(0, int(provider_funded_credits))
    credits = max(0, int(credit_balance))
    entitlement_verified = (
        bool(paid_purchase_verified or credits > 0)
        if paid_entitlement_verified is None
        else bool(paid_entitlement_verified)
    )
    entitlement_source = str(
        paid_entitlement_source
        or (
            "verified_purchase"
            if paid_purchase_verified
            else "existing_credit_balance"
            if credits > 0
            else "none"
        )
    ).strip()[:80]

    verified_paid_routes: list[dict[str, Any]] = []
    paid_routes: list[dict[str, Any]] = []
    if mode != FREE_MODE:
        verified_paid_routes = [
            route
            for route in _ordered_paid_routes(all_routes)
            if route_is_verified_paid(route)
        ]
        paid_routes = [
            route
            for route in verified_paid_routes
            if _paid_route_available(route, state_by_scope=states, now=current_time)
        ]

    if (
        mode != FREE_MODE
        and entitlement_verified
        and funded > 0
        and paid_routes
    ):
        main_route = (
            next((route for route in paid_routes if _route_matches(route, main_requested)), None)
            if main_requested
            else paid_routes[0]
        )
        agent_route = (
            next((route for route in paid_routes if _route_matches(route, agent_requested)), None)
            if agent_requested
            else main_route
        )
        if main_route is None:
            raise ExecutionResolutionError(
                "openrouter_main_model_not_selectable",
                "the requested paid main model is not in the active OpenRouter agent catalog",
                status_code=422,
            )
        if agent_route is None:
            raise ExecutionResolutionError(
                "openrouter_agent_model_not_selectable",
                "the requested six-agent model is not in the active OpenRouter agent catalog",
                status_code=422,
            )

        candidates: list[dict[str, Any]] = [main_route]
        if _route_id(agent_route) != _route_id(main_route):
            candidates.append(agent_route)
        if mode == AUTO_MODE:
            for route in build_paid_to_free_candidates(
                main_route,
                all_routes,
                state_by_scope=states,
                now=current_time,
            ):
                if _route_id(route) not in {_route_id(candidate) for candidate in candidates}:
                    candidates.append(route)
        return ExecutionResolution(
            profile_id=PAID_SWARM_PROFILE,
            primary_route=main_route,
            agent_route=agent_route,
            candidate_routes=tuple(candidates),
            max_foreground_agents=1,
            max_background_agents=6,
            repository_execution_allowed=True,
            paid_purchase_verified=bool(paid_purchase_verified),
            paid_entitlement_verified=True,
            paid_entitlement_source=entitlement_source,
            provider_funded_credits=funded,
            requested_mode=mode,
            reason="verified_paid_entitlement_credits_and_selected_openrouter_model_pair_ready",
        )

    if mode == PAID_MODE:
        transport_failure = _first_transport_failure(
            all_routes,
            profiles=frozenset({PAID_SWARM_PROFILE}),
        )
        if not verified_paid_routes and transport_failure is not None:
            raise ExecutionResolutionError(
                "route_transport_mismatch",
                "a paid route has conflicting, missing, or unsupported transport metadata",
                status_code=503,
                details=transport_failure,
            )
        if not entitlement_verified:
            raise ExecutionResolutionError(
                "paid_purchase_required",
                "paid execution requires a verified purchase or privileged internal entitlement",
                status_code=403,
            )
        if funded <= 0:
            raise ExecutionResolutionError(
                "paid_credits_required",
                "paid execution requires a positive provider-funded credit balance",
                status_code=402,
            )
        raise ExecutionResolutionError(
            "openrouter_paid_route_unavailable",
            "the verified OpenRouter paid model catalog is not currently available",
            status_code=503,
        )

    free_routes = _ordered_free_routes(
        route for route in all_routes if route_is_verified_free(route)
    )
    if not free_routes:
        if mode == FREE_MODE:
            transport_failure = _first_transport_failure(
                all_routes,
                profiles=frozenset({FREE_SINGLE_AGENT_PROFILE}),
            )
            if transport_failure is not None:
                raise ExecutionResolutionError(
                    "route_transport_mismatch",
                    "a free route has conflicting, missing, or unsupported transport metadata",
                    status_code=503,
                    details=transport_failure,
                )
        return None
    if not entitlement_verified:
        raise ExecutionResolutionError(
            "execution_entitlement_required",
            "agent execution requires an authenticated account with a verified purchase or positive persisted credit balance",
            status_code=403,
        )
    candidates = build_revolver_candidates(
        free_routes[0],
        free_routes,
        state_by_scope=states,
        now=current_time,
    )
    if not candidates:
        return None
    candidates, free_swarm_ready = _free_swarm_candidate_order(candidates)
    return ExecutionResolution(
        profile_id=FREE_SWARM_PROFILE if free_swarm_ready else FREE_SINGLE_AGENT_PROFILE,
        primary_route=candidates[0],
        agent_route=candidates[1] if free_swarm_ready else candidates[0],
        candidate_routes=tuple(candidates),
        max_foreground_agents=1,
        max_background_agents=6 if free_swarm_ready else 0,
        repository_execution_allowed=True,
        paid_purchase_verified=bool(paid_purchase_verified),
        paid_entitlement_verified=entitlement_verified,
        paid_entitlement_source=entitlement_source,
        provider_funded_credits=funded,
        requested_mode=mode,
        reason=(
            "free_swarm_ready_with_seven_independent_verified_quota_scopes"
            if free_swarm_ready
            else "paid_route_unavailable_resolved_to_free_revolver"
            if (
                mode == AUTO_MODE
                and entitlement_verified
                and funded > 0
                and verified_paid_routes
            )
            else "auto_resolved_to_quota_aware_direct_freellm"
            if mode == AUTO_MODE
            else "explicit_quota_aware_direct_freellm"
        ),
    )

def free_fallback_resolution(
    resolution: ExecutionResolution,
    *,
    reason: str,
) -> ExecutionResolution | None:
    """Derive a direct-FreeLLM fallback from automatic paid or forced-free resolution."""
    if resolution.profile_id == FREE_SINGLE_AGENT_PROFILE:
        free_candidates = tuple(
            route
            for route in resolution.candidate_routes
            if route_is_verified_free(route)
        )
        fallback_transport = resolution.fallback_from_transport or OPENROUTER_TRANSPORT
    elif resolution.requested_mode == AUTO_MODE:
        free_candidates = tuple(
            route
            for route in resolution.candidate_routes
            if route_is_verified_free(route)
        )
        fallback_transport = route_transport(resolution.primary_route)
    else:
        return None
    if not free_candidates:
        return None
    ordered_free, free_swarm_ready = _free_swarm_candidate_order(free_candidates)
    return ExecutionResolution(
        profile_id=FREE_SWARM_PROFILE if free_swarm_ready else FREE_SINGLE_AGENT_PROFILE,
        primary_route=ordered_free[0],
        agent_route=ordered_free[1] if free_swarm_ready else ordered_free[0],
        candidate_routes=tuple(ordered_free),
        max_foreground_agents=1,
        max_background_agents=6 if free_swarm_ready else 0,
        repository_execution_allowed=True,
        paid_purchase_verified=resolution.paid_purchase_verified,
        paid_entitlement_verified=resolution.paid_entitlement_verified,
        paid_entitlement_source=resolution.paid_entitlement_source,
        provider_funded_credits=resolution.provider_funded_credits,
        requested_mode=AUTO_MODE,
        fallback_from_transport=fallback_transport,
        reason=str(reason or "openrouter_failed_resolved_to_direct_freellm")[:240],
    )

def advance_free_revolver_resolution(
    resolution: ExecutionResolution,
    *,
    failed_route_id: str,
    reason: str,
) -> ExecutionResolution | None:
    """Advance to the next verified free quota scope after one failed route.

    Runtime code must persist the failed route cooldown before using the returned
    resolution. Paid routes are never reintroduced into this failover chain.
    """
    normalized_failed = str(failed_route_id or "").strip()
    free_candidates = tuple(
        route
        for route in resolution.candidate_routes
        if route_is_verified_free(route)
    )
    failed_index = next(
        (
            index
            for index, route in enumerate(free_candidates)
            if _route_id(route) == normalized_failed
        ),
        -1,
    )
    remaining = (
        free_candidates[failed_index + 1 :]
        if failed_index >= 0
        else tuple(
            route for route in free_candidates if _route_id(route) != normalized_failed
        )
    )
    if not remaining:
        return None
    return ExecutionResolution(
        profile_id=FREE_SINGLE_AGENT_PROFILE,
        primary_route=remaining[0],
        agent_route=remaining[0],
        candidate_routes=remaining,
        max_foreground_agents=1,
        max_background_agents=0,
        repository_execution_allowed=True,
        paid_purchase_verified=resolution.paid_purchase_verified,
        paid_entitlement_verified=resolution.paid_entitlement_verified,
        paid_entitlement_source=resolution.paid_entitlement_source,
        provider_funded_credits=resolution.provider_funded_credits,
        requested_mode=resolution.requested_mode,
        fallback_from_transport=resolution.fallback_from_transport,
        reason=str(reason or "free_route_failed_advanced_to_next_quota_scope")[:240],
    )


def load_execution_resolution(
    get_connection: Callable[[], Any],
    *,
    user_id: str,
    requested_model: str = "",
    requested_main_model: str = "",
    requested_agent_model: str = "",
    requested_mode: str = AUTO_MODE,
) -> ExecutionResolution | None:
    """Load account entitlement, active routes and revolver state from PostgreSQL."""
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT account.id::text AS id, account.email, account.role,
                          account.credits::integer AS credits,
                          account.provider_funded_credits::integer AS provider_funded_credits,
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
                          disabled, priority, runtime_kind, tier, config
                   FROM llm_routes
                   WHERE disabled = false
                     AND lower(COALESCE(runtime_kind, provider))
                         IN ('openrouter', 'freellm')
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
                    """SELECT quota_scope, status, cooldown_until,
                              quota_remaining, quota_limit, quota_reset_at,
                              consecutive_failures, last_attempt_at
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

    entitlement = resolve_paid_execution_entitlement(
        account_id=str(account["id"]),
        email=str(account.get("email") or ""),
        role=str(account.get("role") or ""),
        purchase_verified=bool(account["paid_purchase_verified"]),
        credit_balance=int(account["credits"] or 0),
        configured_owner_id=os.getenv("SOVEREIGN_OWNER_ADMIN_ID", ""),
        configured_owner_email=os.getenv("SOVEREIGN_OWNER_ADMIN_EMAIL", ""),
    )
    return resolve_execution_profile(
        routes=routes,
        state_by_scope=states,
        paid_purchase_verified=entitlement.purchase_verified,
        paid_entitlement_verified=entitlement.verified,
        paid_entitlement_source=entitlement.source,
        provider_funded_credits=int(account["provider_funded_credits"] or 0),
        credit_balance=int(account["credits"] or 0),
        requested_model=requested_model,
        requested_main_model=requested_main_model,
        requested_agent_model=requested_agent_model,
        requested_mode=requested_mode,
    )
