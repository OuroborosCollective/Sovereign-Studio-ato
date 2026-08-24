from __future__ import annotations

import hashlib
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
DEPLOY_MIGRATION = BACKEND_ROOT / "migrations" / "060_schema_migration_ledger_reconciliation.sql"
CANONICAL_MIGRATION = REPO_ROOT / "backend" / "migrations" / "060_schema_migration_ledger_reconciliation.sql"


def test_schema_migration_ledger_reconciliation_is_additive_and_mirrored() -> None:
    deploy = DEPLOY_MIGRATION.read_text("utf-8")
    canonical = CANONICAL_MIGRATION.read_text("utf-8")

    assert deploy == canonical
    assert hashlib.sha256(deploy.encode()).hexdigest() == hashlib.sha256(canonical.encode()).hexdigest()
    assert "ARRAY[56, 57, 58, 59]" in deploy
    for name in (
        "evidence_observatory_publication_receipts_v2",
        "durable_workflow_permission_receipts",
        "wolfram_cag_partner_analysis",
        "live_workspace_chat_bubbles",
    ):
        assert name in deploy
    assert "column_name='version'" in deploy
    assert "column_name='id'" in deploy
    assert "column_name='name'" in deploy
    assert "ON CONFLICT (version) DO NOTHING" in deploy
    assert "ON CONFLICT (id) DO NOTHING" in deploy
    assert "DELETE FROM schema_migrations" not in deploy
    assert "UPDATE schema_migrations" not in deploy
    assert "DROP TABLE" not in deploy


def test_migration_060_keeps_standard_adapter_self_registration_shape() -> None:
    deploy = DEPLOY_MIGRATION.read_text("utf-8")

    assert "INSERT INTO schema_migrations (id, name)" in deploy
    assert "VALUES (60, 'schema_migration_ledger_reconciliation')" in deploy
    assert deploy.rstrip().endswith("COMMIT;")
