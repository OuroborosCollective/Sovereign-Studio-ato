from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "scripts" / "sovereign-backend"


def test_billing_migration_repairs_live_schema_and_package_duplicates() -> None:
    migration = (
        BACKEND / "migrations" / "027_billing_idempotency_and_package_uniqueness.sql"
    ).read_text("utf-8")
    assert "ADD COLUMN IF NOT EXISTS provider TEXT" in migration
    assert "ADD COLUMN IF NOT EXISTS provider_tx_id TEXT" in migration
    assert "ADD COLUMN IF NOT EXISTS request_fingerprint TEXT" in migration
    assert "ROW_NUMBER() OVER" in migration
    assert "DELETE FROM credit_packages" in migration
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_credit_packages_name" in migration
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_transactions_provider_receipt" in migration


def test_admin_credit_adjustments_require_content_bound_idempotency() -> None:
    app = (BACKEND / "app.py").read_text("utf-8")
    start = app.index('def admin_credit_adjustment(uid):')
    end = app.index("# ── Transactions", start)
    endpoint = app[start:end]
    helper_start = app.index("def _apply_credit_delta(")
    helper_end = app.index("def _add_credits_and_log(", helper_start)
    helper = app[helper_start:helper_end]

    assert 'request.headers.get("Idempotency-Key")' in endpoint
    assert "uuid.UUID(raw_idempotency_key)" in endpoint
    assert "request_fingerprint = hashlib.sha256" in endpoint
    assert "request_fingerprint=request_fingerprint" in endpoint
    assert '"duplicate": bool(result.get("duplicate"))' in endpoint

    assert "request_fingerprint: str | None = None" in helper
    assert "SELECT user_id::text, credits, request_fingerprint" in helper
    assert "Idempotency-Key kollidiert" in helper
    assert "(provider, provider_tx_id, user_id, credits," in helper


def test_seed_endpoints_use_database_conflicts_not_check_then_insert() -> None:
    app = (BACKEND / "app.py").read_text("utf-8")
    payment_start = app.index("def admin_init_payment_methods():")
    package_start = app.index("def admin_init_credit_packages():")
    payment_block = app[payment_start:package_start]
    package_block = app[
        package_start:app.index(
            '@app.route("/api/admin/credit-packages/<pid>"',
            package_start,
        )
    ]

    assert "ON CONFLICT (type) DO NOTHING" in payment_block
    assert "SELECT id FROM payment_methods WHERE type" not in payment_block
    assert "ON CONFLICT (name) DO NOTHING" in package_block
    assert "SELECT id FROM credit_packages WHERE name" not in package_block
