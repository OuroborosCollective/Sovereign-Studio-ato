"""Paid-credit reservation and actual-cost settlement for Agents SDK stages."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable
import uuid

from llm_cost_policy import (
    AGENTS_LITELLM_ALIAS,
    AGENTS_PROVIDER_MODEL,
    STANDARD_CATEGORY,
    BillingPolicyError,
    billed_credits_for_provider_cost,
    provider_cost_micros_from_usage,
    reservation_credits,
    route_billing_policy,
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
    ) -> None:
        super().__init__(family)
        self.family = family
        self.required_credits = max(0, int(required_credits))
        self.available_credits = max(0, int(available_credits))
        self.status_code = int(status_code)

    def safe_payload(self) -> dict[str, object]:
        return {
            "failureFamily": self.family,
            "requiredCredits": self.required_credits,
            "availableProviderFundedCredits": self.available_credits,
            "providerModel": AGENTS_PROVIDER_MODEL,
            "markupMultiplier": 4,
            "rawErrorPersisted": False,
        }


@dataclass(frozen=True)
class AgentStageReservation:
    request_id: str
    stage: str
    reserved_credits: int
    provider_cost_upper_bound_micros: int
    request_upper_bound: int


def _close(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def _usage_value(usage: Any, name: str) -> int:
    if isinstance(usage, dict):
        value = usage.get(name)
    else:
        value = getattr(usage, name, None)
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def extract_agents_sdk_usage(result: Any) -> dict[str, int]:
    context_wrapper = getattr(result, "context_wrapper", None)
    usage = getattr(context_wrapper, "usage", None)
    if usage is None:
        usage = getattr(result, "usage", None)
    input_tokens = _usage_value(usage, "input_tokens")
    output_tokens = _usage_value(usage, "output_tokens")
    requests = max(1, _usage_value(usage, "requests"))
    cached_tokens = 0
    details = (
        usage.get("input_tokens_details")
        if isinstance(usage, dict)
        else getattr(usage, "input_tokens_details", None)
    )
    if isinstance(details, dict):
        cached_tokens = _usage_value(details, "cached_tokens")
    elif details is not None:
        cached_tokens = _usage_value(details, "cached_tokens")
    return {
        "requestCount": requests,
        "promptTokens": input_tokens,
        "cachedPromptTokens": min(input_tokens, cached_tokens),
        "completionTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
    }


def _load_agent_policy(get_connection: ConnectionFactory) -> dict[str, Any]:
    """Load the Agents SDK billing policy from the active LiteLLM route."""

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT model_id, config
                   FROM llm_routes
                   WHERE model_id=%s AND lower(provider)='litellm' AND disabled=false
                   ORDER BY priority ASC LIMIT 1""",
                (AGENTS_LITELLM_ALIAS,),
            )
            route = cur.fetchone()
        if not route:
            raise AgentBillingError("AGENTS_LITELLM_ALIAS_NOT_READY", status_code=503)
        try:
            policy = route_billing_policy(route)
        except BillingPolicyError as exc:
            raise AgentBillingError("AGENTS_ROUTE_PRICING_UNVERIFIED", status_code=409) from exc
        if str(policy["providerModel"]) != AGENTS_PROVIDER_MODEL:
            raise AgentBillingError("AGENTS_PROVIDER_MODEL_MISMATCH", status_code=409)
        if policy["billingCategory"] != STANDARD_CATEGORY or int(policy["markupMultiplier"]) < 4:
            raise AgentBillingError("AGENTS_STANDARD_ROUTE_REQUIRED", status_code=409)
        return policy
    finally:
        _close(conn)


class AgentStageBilling:
    """Reserve paid credits before every SDK stage and settle actual SDK usage."""

    def __init__(
        self,
        *,
        get_connection: ConnectionFactory,
        user_id: str,
        run_id: str,
        trace_id: str,
    ) -> None:
        self._get_connection = get_connection
        self.user_id = str(user_id)
        self.run_id = str(run_id)
        self.trace_id = str(trace_id)
        self._sequence = 0
        self.policy = _load_agent_policy(get_connection)

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
        input_upper = self.input_token_upper_bound(prompt)
        request_upper = self.request_upper_bound(stage)
        credits, provider_upper = reservation_credits(
            input_token_upper_bound=input_upper,
            output_token_limit=_AGENT_OUTPUT_TOKEN_LIMIT,
            request_upper_bound=request_upper,
            policy=self.policy,
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
                            request_count, trace_id, stage)
                       VALUES (%s::uuid,%s::uuid,%s,%s,'litellm','reserved',
                               %s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        request_id,
                        self.user_id,
                        f"agents-sdk:{AGENTS_PROVIDER_MODEL}",
                        AGENTS_PROVIDER_MODEL,
                        input_upper + (_AGENT_OUTPUT_TOKEN_LIMIT * request_upper),
                        credits,
                        credits,
                        provider_upper,
                        provider_upper * int(self.policy["markupMultiplier"]),
                        int(self.policy["markupMultiplier"]),
                        str(self.policy["billingCategory"]),
                        str(self.policy["billingCategory"]),
                        request_upper,
                        self.trace_id,
                        str(stage)[:240],
                    ),
                )
                cur.execute(
                    """INSERT INTO credit_ledger
                           (user_id,type,amount,reason,provider,provider_tx_id)
                       VALUES (%s::uuid,'agent_usage_reservation',%s,%s,'litellm',%s)""",
                    (
                        self.user_id,
                        -credits,
                        f"Agents SDK cost reservation: {AGENTS_PROVIDER_MODEL}; stage={stage}",
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
        )

    def settle(self, reservation: AgentStageReservation, result: Any) -> dict[str, int]:
        usage = extract_agents_sdk_usage(result)
        provider_cost = provider_cost_micros_from_usage(
            prompt_tokens=usage["promptTokens"],
            cached_prompt_tokens=usage["cachedPromptTokens"],
            completion_tokens=usage["completionTokens"],
            policy=self.policy,
        )
        billed_credits = billed_credits_for_provider_cost(
            provider_cost,
            markup_multiplier=int(self.policy["markupMultiplier"]),
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
                           VALUES (%s::uuid,'agent_usage_adjustment',%s,%s,'litellm',%s)""",
                        (
                            self.user_id,
                            -delta,
                            f"Agents SDK actual-cost adjustment: {AGENTS_PROVIDER_MODEL}",
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
                           VALUES (%s::uuid,'agent_usage_refund',%s,%s,'litellm',%s)""",
                        (
                            self.user_id,
                            refund,
                            f"Agents SDK reservation refund: {AGENTS_PROVIDER_MODEL}",
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
                        provider_cost * int(self.policy["markupMultiplier"]),
                        usage["requestCount"],
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
        """Atomically release one reservation when the provider rejected before usage."""
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
                           VALUES (%s::uuid,'agent_usage_refund',%s,%s,'litellm',%s)""",
                        (
                            self.user_id,
                            refunded,
                            f"Agents SDK provider rejected before usage: {AGENTS_PROVIDER_MODEL}",
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
                       SET status='reconciliation_required', error_code=%s,
                           settled_at=NOW(), updated_at=NOW()
                       WHERE request_id=%s::uuid AND status='reserved'""",
                    (str(family)[:120], reservation.request_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            _close(conn)
