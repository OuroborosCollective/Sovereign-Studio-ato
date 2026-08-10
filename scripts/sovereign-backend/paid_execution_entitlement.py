"""Pure paid-execution entitlement contracts for trusted account identities.

Privileged entitlement replaces only the completed-purchase prerequisite. Real
provider-funded credit reservation, ledger mutation, provider-cost settlement,
and route verification remain mandatory.
"""
from __future__ import annotations

from dataclasses import dataclass


_ADMIN_ROLES = frozenset({"admin", "superadmin"})


@dataclass(frozen=True, slots=True)
class PaidExecutionEntitlement:
    verified: bool
    source: str
    purchase_verified: bool
    privileged: bool


def resolve_paid_execution_entitlement(
    *,
    account_id: str,
    email: str,
    role: str,
    purchase_verified: bool,
    credit_balance: int = 0,
    configured_owner_id: str = "",
    configured_owner_email: str = "",
) -> PaidExecutionEntitlement:
    """Resolve authenticated execution entitlement without manufacturing credits.

    A verified purchase remains sufficient, but an already-persisted positive credit
    balance also grants execution access. This intentionally covers legitimate credits
    granted earlier by account creation or app purchase while preserving the separate
    provider-funded balance required before any paid provider call.
    """

    normalized_id = str(account_id or "").strip().lower()
    normalized_email = str(email or "").strip().lower()
    normalized_role = str(role or "").strip().lower()
    owner_id = str(configured_owner_id or "").strip().lower()
    owner_email = str(configured_owner_email or "").strip().lower()
    purchased = bool(purchase_verified)
    credits_available = max(0, int(credit_balance or 0)) > 0

    owner_match = bool(
        (owner_id and normalized_id and owner_id == normalized_id)
        or (owner_email and normalized_email and owner_email == normalized_email)
    )
    if owner_match:
        return PaidExecutionEntitlement(
            verified=True,
            source="internal_integration_agent",
            purchase_verified=purchased,
            privileged=True,
        )
    if normalized_role in _ADMIN_ROLES:
        return PaidExecutionEntitlement(
            verified=True,
            source="administrator",
            purchase_verified=purchased,
            privileged=True,
        )
    if purchased:
        return PaidExecutionEntitlement(
            verified=True,
            source="verified_purchase",
            purchase_verified=True,
            privileged=False,
        )
    if credits_available:
        return PaidExecutionEntitlement(
            verified=True,
            source="existing_credit_balance",
            purchase_verified=False,
            privileged=False,
        )
    return PaidExecutionEntitlement(
        verified=False,
        source="none",
        purchase_verified=False,
        privileged=False,
    )
