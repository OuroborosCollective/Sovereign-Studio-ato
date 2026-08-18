from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = (
    ROOT / "backend" / "migrations" / "053_llm_usage_credit_ledger_types.sql",
    ROOT / "scripts" / "sovereign-backend" / "migrations" / "053_llm_usage_credit_ledger_types.sql",
)
APP_SOURCES = (
    ROOT / "backend" / "app.py",
    ROOT / "scripts" / "sovereign-backend" / "app.py",
)

PREEXISTING_LEDGER_TYPES = {
    "purchase",
    "adjustment",
    "bonus",
    "manual_adjustment",
    "correction",
    "refund",
    "chargeback",
    "spend",
    "opening_balance",
    "migration_reconciliation",
    "balance_reconciliation",
    "signup_bonus",
    "credit_purchase",
    "usage",
    "agent_usage_reservation",
    "agent_usage_adjustment",
    "agent_usage_refund",
    "verification_usage",
}
DIRECT_LLM_LEDGER_TYPES = {
    "llm_usage_reservation",
    "llm_usage_adjustment",
    "llm_usage_refund",
}


def _quoted_values(sql: str) -> set[str]:
    return set(re.findall(r"'([a-z0-9_]+)'", sql))


def test_migration_mirrors_are_byte_identical_and_preserve_existing_contract():
    canonical = MIGRATIONS[0].read_text(encoding="utf-8")
    deployment = MIGRATIONS[1].read_text(encoding="utf-8")
    assert canonical == deployment

    allowed = _quoted_values(canonical)
    assert PREEXISTING_LEDGER_TYPES <= allowed
    assert DIRECT_LLM_LEDGER_TYPES <= allowed
    assert "DROP CONSTRAINT IF EXISTS credit_ledger_type_check" in canonical
    assert "ADD CONSTRAINT credit_ledger_type_check CHECK (type IN (" in canonical


def test_every_direct_llm_runtime_ledger_type_is_allowed_by_migration():
    allowed = _quoted_values(MIGRATIONS[0].read_text(encoding="utf-8"))

    for path in APP_SOURCES:
        source = path.read_text(encoding="utf-8")
        runtime_types = set(
            re.findall(r'ledger_type="(llm_usage_[a-z0-9_]+)"', source)
        )
        assert runtime_types == DIRECT_LLM_LEDGER_TYPES
        assert runtime_types <= allowed


def test_paid_reservation_is_persisted_before_provider_execution():
    for path in APP_SOURCES:
        source = path.read_text(encoding="utf-8")
        start = source.index("def public_llm_chat():")
        route_source = source[start:]

        reservation = "_reserve_provider_funded_llm_credits("
        assert reservation in route_source
        assert "fetch_worker_ai(" in route_source
        assert route_source.index(reservation) < route_source.index("fetch_worker_ai(")
        assert 'ledger_type="llm_usage_reservation"' in source
        assert 'ledger_type="llm_usage_refund"' in source
        assert 'ledger_type="llm_usage_adjustment"' in source
