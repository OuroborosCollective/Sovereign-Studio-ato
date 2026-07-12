from __future__ import annotations

import hashlib
import importlib.util
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "scripts/sovereign-backend"
BOOTSTRAP = BACKEND_ROOT / "migrations/000_backend_bootstrap_schema.sql"
MIGRATION_001 = BACKEND_ROOT / "migrations/001_admin_api_keys_and_credit_ledger.sql"
MIGRATION_005 = BACKEND_ROOT / "migrations/005_sovereign_agent_schema_sync.sql"
MIGRATION_012 = BACKEND_ROOT / "migrations/012_credit_ledger_type_contract.sql"
MIGRATION_008 = BACKEND_ROOT / "migrations/008_knowledge_memory_passkeys_stepup.sql"
ADAPTER_PATH = BACKEND_ROOT / "migration_ledger_adapter.py"
AUTO_MIGRATE = BACKEND_ROOT / "auto-migrate.sh"
DOCKERFILE = BACKEND_ROOT / "Dockerfile"
CONFIRMED_MIGRATION_008_SHA256 = "bfbfa64306fdf94d6949897927c8554b876693b8ebd1a32f78ae69f9862824dc"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_adapter():
    spec = importlib.util.spec_from_file_location("migration_ledger_adapter", ADAPTER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bootstrap_indexes_whichever_llm_route_state_column_exists() -> None:
    sql = _text(BOOTSTRAP)

    assert "FROM information_schema.columns" in sql
    assert "column_name = 'enabled'" in sql
    assert "column_name = 'disabled'" in sql
    assert "idx_llm_routes_enabled ON llm_routes(enabled)" in sql
    assert "idx_llm_routes_disabled ON llm_routes(disabled)" in sql

    # Never manufacture the legacy flag on the modern schema. Migration 008
    # maps a genuinely existing enabled flag to disabled; adding enabled here
    # would incorrectly disable all routes during the next migration pass.
    assert not re.search(r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+enabled\b", sql, re.IGNORECASE)


def test_bootstrap_repairs_launcher_overrides_to_runtime_contract() -> None:
    sql = _text(BOOTSTRAP)

    required_columns = (
        "label",
        "disabled",
        "badge",
        "sort_order",
        "base_url",
        "auth_mode",
        "created_at",
        "updated_at",
    )
    for column in required_columns:
        assert f"ADD COLUMN IF NOT EXISTS {column}" in sql

    assert "idx_launcher_overrides_sort_order" in sql
    assert "ON launcher_overrides(sort_order)" in sql
    assert "ON launcher_overrides(tool_id)" not in sql


def test_credit_ledger_constraint_is_reconciled_to_runtime_types() -> None:
    required_types = (
        "opening_balance",
        "migration_reconciliation",
        "balance_reconciliation",
        "signup_bonus",
        "credit_purchase",
        "usage",
    )
    for migration in (MIGRATION_001, MIGRATION_012):
        sql = _text(migration)
        assert "pg_get_constraintdef" in sql
        assert "DROP CONSTRAINT IF EXISTS credit_ledger_type_check" in sql
        assert "ADD CONSTRAINT credit_ledger_type_check CHECK" in sql
        for ledger_type in required_types:
            assert f"'{ledger_type}'" in sql
            assert f"NOT LIKE '%{ledger_type}%'" in sql

    repair_sql = _text(MIGRATION_012)
    assert "to_regclass" in repair_sql
    assert "Existing append-only rows are never rewritten or deleted" in repair_sql


def test_runtime_adapter_maps_id_name_insert_to_legacy_version_layout() -> None:
    adapter = _load_adapter()
    result = adapter.adapt_schema_ledger(_text(MIGRATION_008), {"version"})

    assert result["evidence"]["status"] == "APPLIED"
    assert result["evidence"]["action"] == "id_name_to_legacy_version"
    assert result["evidence"]["source_unchanged"] is True
    assert "INSERT INTO schema_migrations (version)" in result["sql"]
    assert "VALUES ('008')" in result["sql"]
    assert "INSERT INTO schema_migrations (id, name)" not in result["sql"]


def test_runtime_adapter_maps_legacy_version_insert_to_current_layout() -> None:
    adapter = _load_adapter()
    result = adapter.adapt_schema_ledger(
        _text(MIGRATION_005), {"id", "name", "applied_at"}
    )

    assert result["evidence"]["status"] == "APPLIED"
    assert result["evidence"]["action"] == "legacy_version_to_id_name"
    assert "INSERT INTO schema_migrations (id, name)" in result["sql"]
    assert "VALUES (5, 'migration_005')" in result["sql"]
    assert "INSERT INTO schema_migrations (version, applied_at)" not in result["sql"]


def test_runtime_adapter_rejects_unknown_nonempty_ledger_layout() -> None:
    adapter = _load_adapter()
    with pytest.raises(ValueError, match="Unsupported schema_migrations layout"):
        adapter.adapt_schema_ledger(_text(MIGRATION_008), {"unexpected"})


def test_container_start_path_uses_runtime_adapter_and_refreshes_layout() -> None:
    migrate = _text(AUTO_MIGRATE)
    dockerfile = _text(DOCKERFILE)

    assert "python3 /app/migration_ledger_adapter.py" in migrate
    assert "current_ledger_columns=\"$(read_ledger_columns)\"" in migrate
    assert migrate.count("current_ledger_columns=\"$(read_ledger_columns)\"") == 2
    assert "COPY migration_ledger_adapter.py ./migration_ledger_adapter.py" in dockerfile


def test_confirmed_migration_008_remains_byte_for_byte_unchanged() -> None:
    digest = hashlib.sha256(MIGRATION_008.read_bytes()).hexdigest()
    assert digest == CONFIRMED_MIGRATION_008_SHA256
