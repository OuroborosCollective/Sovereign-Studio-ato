from __future__ import annotations

import hashlib
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_028 = BACKEND_ROOT / "migrations/028_owner_learning_policy.sql"
MIGRATION_041 = BACKEND_ROOT / "migrations/041_reconcile_owner_learning_policy_ledger.sql"
MIGRATION_041_MIRROR = BACKEND_ROOT.parents[1] / "backend/migrations/041_reconcile_owner_learning_policy_ledger.sql"
CONFIRMED_MIGRATION_028_SHA256 = (
    "38d1a58f762e9622f37b41e9cb46711c20fabb4151b9bee6930e78b27da3d61e"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reconciliation_is_bound_to_the_confirmed_migration_028_source() -> None:
    digest = hashlib.sha256(MIGRATION_028.read_bytes()).hexdigest()
    sql = _text(MIGRATION_041)

    assert digest == CONFIRMED_MIGRATION_028_SHA256
    assert CONFIRMED_MIGRATION_028_SHA256 in sql
    assert "scripts/sovereign-backend/migrations/028_owner_learning_policy.sql" in sql


def test_reconciliation_mirror_is_byte_equal() -> None:
    assert MIGRATION_041.read_bytes() == MIGRATION_041_MIRROR.read_bytes()


def test_reconciliation_repairs_only_the_ledger_after_fail_closed_checks() -> None:
    sql = _text(MIGRATION_041)

    assert "CREATE TABLE" not in sql
    assert "DROP TABLE" not in sql
    assert "DELETE FROM owner_learning_policies" not in sql
    assert "UPDATE owner_learning_policies" not in sql
    assert "to_regclass(format('%I.owner_learning_policies', current_schema()))" in sql
    assert "owner_learning_policies layout mismatch" in sql
    assert "expected exactly one canonical enabled owner policy" in sql
    assert "policy_source = 'owner-explicit-2026-07-20'" in sql
    assert "to_regclass(format('%I.schema_migrations', current_schema()))" in sql
    assert "unsupported schema_migrations layout" in sql


def test_reconciliation_supports_known_ledgers_and_is_idempotent() -> None:
    sql = _text(MIGRATION_041)

    assert "INSERT INTO schema_migrations (version, applied_at)" in sql
    assert "INSERT INTO schema_migrations (version)" in sql
    assert "INSERT INTO schema_migrations (id, name)" in sql
    assert "VALUES ('028', NOW()), ('041', NOW())" in sql
    assert "VALUES ('028'), ('041')" in sql
    assert "(28, 'owner_learning_policy')" in sql
    assert "(41, 'reconcile_owner_learning_policy_ledger')" in sql
    assert sql.count("ON CONFLICT") == 3
    assert "DO NOTHING" in sql
