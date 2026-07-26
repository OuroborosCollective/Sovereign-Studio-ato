from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.cognitive_usage_billing import AgentBillingError, AgentStageBilling
from llm_cost_policy import route_billing_policy
from llm_execution_resolver import (
    PAID_SWARM_PROFILE,
    ExecutionResolutionError,
    resolve_execution_profile,
)
from paid_execution_entitlement import resolve_paid_execution_entitlement


def _paid_route() -> dict:
    return {
        "id": "openrouter-paid-route",
        "model_id": "sovereign-paid",
        "model_name": "Sovereign Paid",
        "provider": "openrouter",
        "runtime_kind": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "disabled": False,
        "priority": 1,
        "config": {
            "transport": "openrouter",
            "direct": True,
            "catalogVerified": True,
            "transportCanaryVerified": True,
            "selectable": True,
            "supportedExecutionRoles": ["main", "swarm_agents"],
            "providerPolicy": {
                "require_parameters": True,
                "allow_fallbacks": False,
                "data_collection": "deny",
                "zdr": True,
            },
            "providerModel": "openai/gpt-5.4-mini",
            "executionProfile": "paid_swarm_6",
            "billingCategory": "standard",
            "billingClass": "standard",
            "markupMultiplier": 4,
            "fundingMode": "provider_priced",
            "inputUsdPerMillion": 0.75,
            "cachedInputUsdPerMillion": 0.075,
            "outputUsdPerMillion": 4.5,
            "pricingVerified": True,
            "pricingSource": "test",
        },
    }


def test_configured_owner_is_internal_integration_agent_entitled() -> None:
    entitlement = resolve_paid_execution_entitlement(
        account_id="00000000-0000-0000-0000-000000000001",
        email="owner@example.test",
        role="user",
        purchase_verified=False,
        configured_owner_id="00000000-0000-0000-0000-000000000001",
    )

    assert entitlement.verified is True
    assert entitlement.privileged is True
    assert entitlement.purchase_verified is False
    assert entitlement.source == "internal_integration_agent"


@pytest.mark.parametrize("role", ["admin", "superadmin", " ADMIN "])
def test_administrator_roles_are_paid_entitled_without_fake_purchase(role: str) -> None:
    entitlement = resolve_paid_execution_entitlement(
        account_id="00000000-0000-0000-0000-000000000002",
        email="admin@example.test",
        role=role,
        purchase_verified=False,
    )

    assert entitlement.verified is True
    assert entitlement.privileged is True
    assert entitlement.purchase_verified is False
    assert entitlement.source == "administrator"


def test_normal_user_still_requires_purchase() -> None:
    entitlement = resolve_paid_execution_entitlement(
        account_id="00000000-0000-0000-0000-000000000003",
        email="user@example.test",
        role="user",
        purchase_verified=False,
    )

    assert entitlement.verified is False
    assert entitlement.source == "none"


def test_privileged_entitlement_selects_paid_profile_but_preserves_purchase_truth() -> None:
    resolution = resolve_execution_profile(
        routes=[_paid_route()],
        state_by_scope={},
        paid_purchase_verified=False,
        paid_entitlement_verified=True,
        paid_entitlement_source="administrator",
        provider_funded_credits=10_000,
        requested_mode="paid",
    )

    assert resolution is not None
    assert resolution.profile_id == PAID_SWARM_PROFILE
    assert resolution.paid_purchase_verified is False
    assert resolution.paid_entitlement_verified is True
    assert resolution.paid_entitlement_source == "administrator"
    assert resolution.provider_funded_credits == 10_000


def test_privileged_entitlement_does_not_manufacture_provider_credits() -> None:
    with pytest.raises(ExecutionResolutionError) as raised:
        resolve_execution_profile(
            routes=[_paid_route()],
            state_by_scope={},
            paid_purchase_verified=False,
            paid_entitlement_verified=True,
            paid_entitlement_source="internal_integration_agent",
            provider_funded_credits=0,
            requested_mode="paid",
        )

    assert raised.value.failure_family == "paid_credits_required"
    assert raised.value.status_code == 402


class _BillingCursor:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = list(rows)
        self.executions: list[tuple[str, tuple | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str, params=None) -> None:
        self.executions.append((sql, params))

    def fetchone(self):
        if not self.rows:
            raise AssertionError("unexpected fetchone")
        return self.rows.pop(0)


class _BillingConnection:
    def __init__(self, rows: list[dict]) -> None:
        self.cursor_instance = _BillingCursor(rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        return None


def _billing_for(connection: _BillingConnection) -> AgentStageBilling:
    route = _paid_route()
    billing = AgentStageBilling.__new__(AgentStageBilling)
    billing._get_connection = lambda: connection
    billing.user_id = "00000000-0000-0000-0000-000000000004"
    billing.run_id = "run-entitlement"
    billing.trace_id = "trace-entitlement"
    billing.requested_mode = "paid"
    billing._sequence = 0
    billing.main_route = route
    billing.main_policy = route_billing_policy(route)
    billing.agent_route = route
    billing.agent_policy = billing.main_policy
    return billing


def test_admin_reservation_bypasses_purchase_only_and_debits_real_credits() -> None:
    connection = _BillingConnection([
        {
            "id": "00000000-0000-0000-0000-000000000004",
            "email": "admin@example.test",
            "role": "admin",
            "credits": 1_000_000,
            "provider_funded_credits": 1_000_000,
        },
        {"balance": 1_000_000},
        {"purchased": False},
    ])

    reservation = _billing_for(connection).reserve(stage="dispatcher", prompt="bounded")

    assert reservation.paid_entitlement_source == "administrator"
    assert reservation.reserved_credits > 0
    assert connection.commits == 1
    sql_text = "\n".join(sql for sql, _params in connection.cursor_instance.executions)
    params_text = repr([params for _sql, params in connection.cursor_instance.executions])
    assert "INSERT INTO llm_usage_settlements" in sql_text
    assert "INSERT INTO credit_ledger" in sql_text
    assert "provider_funded_credits=provider_funded_credits-%s" in sql_text
    assert "entitlement=administrator" in params_text


def test_normal_user_without_purchase_is_still_blocked_before_debit() -> None:
    connection = _BillingConnection([
        {
            "id": "00000000-0000-0000-0000-000000000004",
            "email": "user@example.test",
            "role": "user",
            "credits": 1_000_000,
            "provider_funded_credits": 1_000_000,
        },
        {"balance": 1_000_000},
        {"purchased": False},
    ])

    with pytest.raises(AgentBillingError) as raised:
        _billing_for(connection).reserve(stage="dispatcher", prompt="bounded")

    assert raised.value.family == "PAID_CREDIT_PURCHASE_REQUIRED"
    assert connection.commits == 0
    assert connection.rollbacks == 1
    sql_text = "\n".join(sql for sql, _params in connection.cursor_instance.executions)
    assert "INSERT INTO credit_ledger" not in sql_text


def test_paid_entitlement_runtime_mirrors_remain_byte_equal() -> None:
    # Deployment mirrors are part of the production entitlement contract.
    mirror_pairs = [
        (
            BACKEND / "paid_execution_entitlement.py",
            ROOT / "scripts" / "sovereign-backend" / "paid_execution_entitlement.py",
        ),
        (
            BACKEND / "llm_execution_resolver.py",
            ROOT / "scripts" / "sovereign-backend" / "llm_execution_resolver.py",
        ),
        (
            BACKEND / "agent_runtime" / "cognitive_usage_billing.py",
            ROOT
            / "scripts"
            / "sovereign-backend"
            / "agent_runtime"
            / "cognitive_usage_billing.py",
        ),
    ]

    for canonical, deployment in mirror_pairs:
        assert canonical.read_bytes() == deployment.read_bytes()
