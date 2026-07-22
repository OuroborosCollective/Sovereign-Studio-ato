"""Paid-credit reservation and actual-cost settlement for Agents SDK stages."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
import uuid

from llm_cost_policy import (
    STANDARD_CATEGORY,
    BillingPolicyError,
    billed_credits_for_provider_cost,
    provider_cost_micros_from_usage,
    reservation_credits,
    route_billing_policy,
)
from llm_transport import (
    OPENROUTER_TRANSPORT,
    route_is_openrouter_paid,
    route_provider_model,
    route_snapshot_hashes,
    route_transport,
)


ConnectionFactory = Callable[[], Any]
_AGENT_INPUT_TOKEN_LIMIT = 32_000
_AGENT_OUTPUT_TOKEN_LIMIT = 2_048
_AGENT_DEFAULT_REQUEST_LIMIT = 1
_AGENT_WORKER_REQUEST_LIMIT = 6


class AgentBillingError(RuntimeError):
    def __init__(
        self,
        family: str,
        *,
        required_credits: int = 0,
        available_credits: int = 0,
        status_code: int = 402,
        provider_model: str = "openai/gpt-5.4-mini",
        transport: str = OPENROUTER_TRANSPORT,
    ) -> None:
        super().__init__(family)
        self.family = family
        self.required_credits = max(0, int(required_credits))
        self.available_credits = max(0, int(available_credits))
        self.status_code = int(status_code)
        self.provider_model = str(provider_model)
        self.transport = str(transport)

    def safe_payload(self) -> dict[str, object]:
        return {
            "failureFamily": self.family,
            "requiredCredits": self.required_credits,
            "availableProviderFundedCredits": self.available_credits,
            "providerModel": self.provider_model,
            "resolvedTransport": self.transport,
            "rawErrorPersisted": False,
        }


@dataclass(frozen=True)
class AgentStageReservation:
    request_id: str
    stage: str
    reserved_credits: int
    provider_cost_upper_bound_micros: int
    request_upper_bound: int
    billing_role: str
    route_id: str
    provider_model: str
    transport: str
    route_snapshot_sha256: str
    price_snapshot_sha256: str
    policy: dict[str, Any]


def _close(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def _object_value(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _usage_value(usage: Any, name: str) -> int:
    try:
        return max(0, int(_object_value(usage, name) or 0))
    except (TypeError, ValueError):
        return 0


def _usd_micros(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return int((amount * Decimal(1_000_000)).to_integral_value())


def extract_agents_sdk_usage(result: Any) -> dict[str, Any]:
    """Extract token usage plus OpenRouter cost/id without persisting raw responses."""

    context_wrapper = getattr(result, "context_wrapper", None)
    usage = getattr(context_wrapper, "usage", None)
    if usage is None:
        usage = getattr(result, "usage", None)
    raw_responses = list(getattr(result, "raw_responses", None) or [])
    response_candidates = [*reversed(raw_responses), result]

    input_tokens = _usage_value(usage, "input_tokens")
    output_tokens = _usage_value(usage, "output_tokens")
    requests = max(1, _usage_value(usage, "requests"))
    details = _object_value(usage, "input_tokens_details")
    cached_tokens = _usage_value(details, "cached_tokens")

    provider_cost = _usd_micros(_object_value(usage, "cost"))
    generation_id = (
        _object_value(usage, "generation_id")
        or _object_value(usage, "generationId")
    )
    for response in response_candidates:
        response_usage = _object_value(response, "usage")
        if provider_cost is None:
            provider_cost = _usd_micros(_object_value(response_usage, "cost"))
        if not generation_id:
            generation_id = (
                _object_value(response, "id")
                or _object_value(response, "response_id")
                or _object_value(response_usage, "generation_id")
            )
        if provider_cost is not None and generation_id:
            break

    return {
        "requestCount": requests,
        "promptTokens": input_tokens,
        "cachedPromptTokens": min(input_tokens, cached_tokens),
        "completionTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
        "reportedProviderCostUsdMicros": provider_cost,
        "providerGenerationId": str(generation_id or "")[:200] or None,
    }


def _load_agent_route_policy(
    get_connection: ConnectionFactory,
    expected_route: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reload and verify the exact active OpenRouter route before reserving."""

    route_id = str(expected_route.get("id") or "").strip()
    if not route_id:
        raise AgentBillingError("AGENTS_ROUTE_ID_MISSING", status_code=409)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id::text, model_id, model_name, provider, base_url,
                          credits_per_unit::float AS credits_per_unit,
                          disabled, priority, runtime_kind, tier, config
                   FROM llm_routes
                   WHERE id::text=%s AND disabled=false
                   LIMIT 1""",
                (route_id,),
            )
            loaded = cur.fetchone()
        if not loaded:
            raise AgentBillingError("OPENROUTER_PAID_ROUTE_NOT_READY", status_code=503)
        route = dict(loaded)
        if not route_is_openrouter_paid(route):
            raise AgentBillingError("OPENROUTER_PAID_ROUTE_REJECTED", status_code=409)
        if route_snapshot_hashes(route) != route_snapshot_hashes(expected_route):
            raise AgentBillingError("OPENROUTER_ROUTE_CHANGED_BEFORE_RESERVATION", status_code=409)
        try:
            policy = route_billing_policy(route)
        except BillingPolicyError as exc:
            raise AgentBillingError("AGENTS_ROUTE_PRICING_UNVERIFIED", status_code=409) from exc
        if (
            policy["billingCategory"] != STANDARD_CATEGORY
            or int(policy["markupMultiplier"]) < 4
        ):
            raise AgentBillingError("AGENTS_STANDARD_ROUTE_REQUIRED", status_code=409)
        if route_transport(route) != OPENROUTER_TRANSPORT:
            raise AgentBillingError("AGENTS_OPENROUTER_ROUTE_REQUIRED", status_code=409)
        return route, policy
    finally:
        _close(conn)


class AgentStageBilling:
    """Reserve paid credits before each OpenRouter stage and settle actual usage."""

    def __init__(
        self,
        *,
        get_connection: ConnectionFactory,
        user_id: str,
        run_id: str,
        trace_id: str,
        route: dict[str, Any] | None = None,
        main_route: dict[str, Any] | None = None,
        agent_route: dict[str, Any] | None = None,
        requested_mode: str,
    ) -> None:
        self._get_connection = get_connection
        self.user_id = str(user_id)
        self.run_id = str(run_id)
        self.trace_id = str(trace_id)
        self.requested_mode = str(requested_mode or "auto")
        self._sequence = 0

        expected_main = main_route or route
        if not isinstance(expected_main, dict):
            raise AgentBillingError("AGENTS_MAIN_ROUTE_MISSING", status_code=409)
        expected_agents = agent_route or expected_main
        self.main_route, self.main_policy = _load_agent_route_policy(
            get_connection, expected_main
        )
        if str(expected_agents.get("id") or "") == str(self.main_route.get("id") or ""):
            self.agent_route, self.agent_policy = self.main_route, self.main_policy
        else:
            self.agent_route, self.agent_policy = _load_agent_route_policy(
                get_connection, expected_agents
            )

        # Backward-compatible attributes describe the paid main model.
        self.route = self.main_route
        self.policy = self.main_policy
        self.route_id = str(self.main_route["id"])
        self.provider_model = route_provider_model(self.main_route)
        self.transport = route_transport(self.main_route)
        self.route_snapshot_sha256, self.price_snapshot_sha256 = (
            route_snapshot_hashes(self.main_route)
        )

    def _profile_for_stage(self, stage: str) -> dict[str, Any]:
        use_agents = ":worker:" in str(stage or "").casefold()
        route = self.agent_route if use_agents else self.main_route
        policy = self.agent_policy if use_agents else self.main_policy
        route_hash, price_hash = route_snapshot_hashes(route)
        return {
            "billingRole": "swarm_agents" if use_agents else "main",
            "route": route,
            "policy": policy,
            "routeId": str(route["id"]),
            "providerModel": route_provider_model(route),
            "transport": route_transport(route),
            "routeSnapshotSha256": route_hash,
            "priceSnapshotSha256": price_hash,
        }

    @property
    def output_token_limit(self) -> int:
        return _AGENT_OUTPUT_TOKEN_LIMIT

    @staticmethod
    def request_upper_bound(stage: str) -> int:
        normalized = str(stage or "").casefold()
        return (
            _AGENT_WORKER_REQUEST_LIMIT
            if ":worker:" in normalized
            else _AGENT_DEFAULT_REQUEST_LIMIT
        )

    @staticmethod
    def input_token_upper_bound(prompt: str) -> int:
        estimate = len(str(prompt or "").encode("utf-8")) + 8_192
        if estimate > _AGENT_INPUT_TOKEN_LIMIT:
            raise AgentBillingError(
                "AGENT_INPUT_COST_BOUND_EXCEEDED",
                status_code=413,
            )
        return max(1, estimate)

    def _next_request_id(self, stage: str) -> str:
        self._sequence += 1
        material = f"sovereign-agent:{self.run_id}:{self.trace_id}:{stage}:{self._sequence}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, material))

    def reserve(self, *, stage: str, prompt: str) -> AgentStageReservation:
        profile = self._profile_for_stage(stage)
        policy = profile["policy"]
        input_upper = self.input_token_upper_bound(prompt)
        request_upper = self.request_upper_bound(stage)
        credits, provider_upper = reservation_credits(
            input_token_upper_bound=input_upper,
            output_token_limit=_AGENT_OUTPUT_TOKEN_LIMIT,
            request_upper_bound=request_upper,
            policy=policy,
        )
        request_id = self._next_request_id(stage)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id::text, credits::integer, provider_funded_credits::integer
                       FROM admin_users WHERE id=%s::uuid LIMIT 1 FOR UPDATE""",
                    (self.user_id,),
                )
                account = cur.fetchone()
                if not account:
                    raise AgentBillingError("AGENT_BILLING_USER_NOT_FOUND", status_code=404)
                cur.execute(
                    "SELECT COALESCE(SUM(amount),0)::integer AS balance "
                    "FROM credit_ledger WHERE user_id=%s::uuid",
                    (self.user_id,),
                )
                ledger_balance = int(cur.fetchone()["balance"])
                if ledger_balance != int(account["credits"]):
                    raise AgentBillingError("CREDIT_STATE_VERIFICATION_FAILED", status_code=409)
                cur.execute(
                    """SELECT EXISTS(
                           SELECT 1
                           FROM transactions AS tx
                           JOIN credit_receipts AS receipt
                             ON receipt.user_id = tx.user_id
                            AND receipt.provider = tx.provider
                            AND receipt.provider_tx_id = tx.provider_tx_id
                           WHERE tx.user_id=%s::uuid
                             AND tx.type='credit_purchase'
                             AND tx.status='completed'
                       ) AS purchased""",
                    (self.user_id,),
                )
                if not bool(cur.fetchone()["purchased"]):
                    raise AgentBillingError("PAID_CREDIT_PURCHASE_REQUIRED")
                funded = int(account["provider_funded_credits"])
                if funded < credits or int(account["credits"]) < credits:
                    raise AgentBillingError(
                        "INSUFFICIENT_PROVIDER_FUNDED_CREDITS",
                        required_credits=credits,
                        available_credits=min(funded, int(account["credits"])),
                    )
                cur.execute(
                    """INSERT INTO llm_usage_settlements
                           (request_id, user_id, route_id, model_id, provider, status,
                            estimated_tokens, reserved_credits, funded_credits_reserved,
                            provider_cost_usd_micros, billed_value_usd_micros,
                            markup_multiplier, billing_class, billing_category,
                            request_count, trace_id, stage, requested_mode,
                            execution_role, resolved_transport, provider_cost_source,
                            route_snapshot_sha256, price_snapshot_sha256)
                       VALUES (%s::uuid,%s::uuid,%s,%s,%s,'reserved',
                               %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        request_id,
                        self.user_id,
                        profile["routeId"],
                        profile["providerModel"],
                        profile["transport"],
                        input_upper + (_AGENT_OUTPUT_TOKEN_LIMIT * request_upper),
                        credits,
                        credits,
                        provider_upper,
                        provider_upper * int(policy["markupMultiplier"]),
                        int(policy["markupMultiplier"]),
                        str(policy["billingCategory"]),
                        str(policy["billingCategory"]),
                        request_upper,
                        self.trace_id,
                        str(stage)[:240],
                        self.requested_mode,
                        profile["billingRole"],
                        profile["transport"],
                        "route_price_snapshot_upper_bound",
                        profile["routeSnapshotSha256"],
                        profile["priceSnapshotSha256"],
                    ),
                )
                cur.execute(
                    """INSERT INTO credit_ledger
                           (user_id,type,amount,reason,provider,provider_tx_id)
                       VALUES (%s::uuid,'agent_usage_reservation',%s,%s,%s,%s)""",
                    (
                        self.user_id,
                        -credits,
                        f"Agents SDK cost reservation: {profile['providerModel']}; stage={stage}",
                        profile["transport"],
                        f"{request_id}:reservation",
                    ),
                )
                cur.execute(
                    """UPDATE admin_users
                       SET credits=credits-%s,
                           provider_funded_credits=provider_funded_credits-%s,
                           last_active_at=NOW()
                       WHERE id=%s::uuid""",
                    (credits, credits, self.user_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            _close(conn)
        return AgentStageReservation(
            request_id=request_id,
            stage=str(stage),
            reserved_credits=credits,
            provider_cost_upper_bound_micros=provider_upper,
            request_upper_bound=request_upper,
            billing_role=str(profile["billingRole"]),
            route_id=str(profile["routeId"]),
            provider_model=str(profile["providerModel"]),
            transport=str(profile["transport"]),
            route_snapshot_sha256=str(profile["routeSnapshotSha256"]),
            price_snapshot_sha256=str(profile["priceSnapshotSha256"]),
            policy=dict(policy),
        )

    def settle(self, reservation: AgentStageReservation, result: Any) -> dict[str, Any]:
        usage = extract_agents_sdk_usage(result)
        reported_cost = usage["reportedProviderCostUsdMicros"]
        if reported_cost is None:
            provider_cost = provider_cost_micros_from_usage(
                prompt_tokens=usage["promptTokens"],
                cached_prompt_tokens=usage["cachedPromptTokens"],
                completion_tokens=usage["completionTokens"],
                policy=reservation.policy,
            )
            provider_cost_source = "route_price_snapshot"
        else:
            provider_cost = int(reported_cost)
            provider_cost_source = "openrouter_usage_cost"
        billed_credits = billed_credits_for_provider_cost(
            provider_cost,
            markup_multiplier=int(reservation.policy["markupMultiplier"]),
        )
        delta = billed_credits - reservation.reserved_credits
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT credits::integer, provider_funded_credits::integer
                       FROM admin_users WHERE id=%s::uuid LIMIT 1 FOR UPDATE""",
                    (self.user_id,),
                )
                account = cur.fetchone()
                if not account:
                    raise AgentBillingError("AGENT_BILLING_USER_NOT_FOUND", status_code=404)
                if delta > 0:
                    available = min(
                        int(account["credits"]),
                        int(account["provider_funded_credits"]),
                    )
                    if available < delta:
                        raise AgentBillingError(
                            "AGENT_ACTUAL_COST_EXCEEDED_RESERVATION",
                            required_credits=delta,
                            available_credits=available,
                        )
                    cur.execute(
                        """INSERT INTO credit_ledger
                               (user_id,type,amount,reason,provider,provider_tx_id)
                           VALUES (%s::uuid,'agent_usage_adjustment',%s,%s,%s,%s)""",
                        (
                            self.user_id,
                            -delta,
                            f"Agents SDK actual-cost adjustment: {reservation.provider_model}",
                            reservation.transport,
                            f"{reservation.request_id}:adjustment",
                        ),
                    )
                    cur.execute(
                        """UPDATE admin_users
                           SET credits=credits-%s,
                               provider_funded_credits=provider_funded_credits-%s,
                               last_active_at=NOW()
                           WHERE id=%s::uuid""",
                        (delta, delta, self.user_id),
                    )
                elif delta < 0:
                    refund = -delta
                    cur.execute(
                        """INSERT INTO credit_ledger
                               (user_id,type,amount,reason,provider,provider_tx_id)
                           VALUES (%s::uuid,'agent_usage_refund',%s,%s,%s,%s)""",
                        (
                            self.user_id,
                            refund,
                            f"Agents SDK reservation refund: {reservation.provider_model}",
                            reservation.transport,
                            f"{reservation.request_id}:refund",
                        ),
                    )
                    cur.execute(
                        """UPDATE admin_users
                           SET credits=credits+%s,
                               provider_funded_credits=provider_funded_credits+%s,
                               last_active_at=NOW()
                           WHERE id=%s::uuid""",
                        (refund, refund, self.user_id),
                    )
                cur.execute(
                    """UPDATE llm_usage_settlements
                       SET status='settled_usage',
                           settled_credits=%s,
                           refunded_credits=%s,
                           prompt_tokens=%s,
                           cached_prompt_tokens=%s,
                           completion_tokens=%s,
                           total_tokens=%s,
                           provider_cost_usd=%s,
                           provider_cost_usd_micros=%s,
                           billed_value_usd_micros=%s,
                           request_count=%s,
                           provider_generation_id=%s,
                           upstream_request_id=%s,
                           provider_cost_source=%s,
                           settled_at=NOW(), updated_at=NOW()
                       WHERE request_id=%s::uuid""",
                    (
                        billed_credits,
                        max(0, -delta),
                        usage["promptTokens"],
                        usage["cachedPromptTokens"],
                        usage["completionTokens"],
                        usage["totalTokens"],
                        float(Decimal(provider_cost) / Decimal(1_000_000)),
                        provider_cost,
                        provider_cost * int(reservation.policy["markupMultiplier"]),
                        usage["requestCount"],
                        usage["providerGenerationId"],
                        usage["providerGenerationId"],
                        provider_cost_source,
                        reservation.request_id,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            _close(conn)
        return {
            **usage,
            "providerCostUsdMicros": provider_cost,
            "providerCostSource": provider_cost_source,
            "billedCredits": billed_credits,
            "reservedCredits": reservation.reserved_credits,
            "refundedCredits": max(0, -delta),
        }

    def refund_failed_before_usage(
        self,
        reservation: AgentStageReservation,
        *,
        family: str,
    ) -> bool:
        """Atomically release one reservation when OpenRouter rejected before usage."""

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE llm_usage_settlements
                       SET status='refunded',
                           refunded_credits=reserved_credits,
                           settled_credits=0,
                           prompt_tokens=0,
                           cached_prompt_tokens=0,
                           completion_tokens=0,
                           total_tokens=0,
                           provider_cost_usd=0,
                           provider_cost_usd_micros=0,
                           billed_value_usd_micros=0,
                           provider_cost_source='rejected_before_usage',
                           error_code=%s,
                           settled_at=NOW(), updated_at=NOW()
                       WHERE request_id=%s::uuid AND status='reserved'
                       RETURNING reserved_credits::integer AS refunded""",
                    (str(family)[:120], reservation.request_id),
                )
                row = cur.fetchone()
                if not row:
                    conn.commit()
                    return False
                refunded = max(0, int(row["refunded"] or 0))
                if refunded:
                    cur.execute(
                        """INSERT INTO credit_ledger
                               (user_id,type,amount,reason,provider,provider_tx_id)
                           VALUES (%s::uuid,'agent_usage_refund',%s,%s,%s,%s)""",
                        (
                            self.user_id,
                            refunded,
                            f"Agents SDK provider rejected before usage: {reservation.provider_model}",
                            reservation.transport,
                            f"{reservation.request_id}:failed-before-usage",
                        ),
                    )
                    cur.execute(
                        """UPDATE admin_users
                           SET credits=credits+%s,
                               provider_funded_credits=provider_funded_credits+%s,
                               last_active_at=NOW()
                           WHERE id=%s::uuid""",
                        (refunded, refunded, self.user_id),
                    )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            _close(conn)

    def mark_reconciliation_required(
        self,
        reservation: AgentStageReservation,
        *,
        family: str,
    ) -> None:
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE llm_usage_settlements
                       SET status='reconciliation_required',
                           provider_cost_source='provider_readback_required',
                           error_code=%s, settled_at=NOW(), updated_at=NOW()
                       WHERE request_id=%s::uuid AND status='reserved'""",
                    (str(family)[:120], reservation.request_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            _close(conn)
