from __future__ import annotations

import hashlib

import pytest

from database import DatabaseRuntime, _preview_body


def test_schema_inventory_returns_metadata_only(monkeypatch) -> None:
    class Cursor:
        def __init__(self) -> None:
            self.query_count = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _query):
            self.query_count += 1

        def fetchone(self):
            return {"database": "sovereign", "user": "runtime_reader"}

        def fetchall(self):
            return [
                {"table_schema": "public", "table_name": "agent_jobs"},
                {"table_schema": "auth", "table_name": "users"},
            ]

    class Connection:
        def __init__(self) -> None:
            self.cursor_instance = Cursor()
            self.readonly = False
            self.rolled_back = False
            self.closed = False

        def set_session(self, *, readonly, autocommit):
            self.readonly = readonly is True and autocommit is False

        def cursor(self, **_kwargs):
            return self.cursor_instance

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(DatabaseRuntime, "_connection", staticmethod(lambda _prefix="POSTGRES": connection))
    database = DatabaseRuntime(lambda _workspace_id: None)

    result = database.schema_inventory()

    assert result["ok"] is True
    assert result["tableCount"] == 2
    assert result["tables"] == [
        {"table_schema": "public", "table_name": "agent_jobs"},
        {"table_schema": "auth", "table_name": "users"},
    ]
    assert result["rowDataReturned"] is False
    assert result["secretValuesExposed"] is False
    assert connection.readonly is True
    assert connection.rolled_back is True
    assert connection.closed is True


def test_migration_blocks_dangerous_sql(repo_runtime) -> None:
    runtime, workspace_id, repo = repo_runtime
    migration = repo / "migrations" / "001.sql"
    migration.parent.mkdir()
    migration.write_text("DROP DATABASE postgres;\n", "utf-8")
    database = DatabaseRuntime(runtime._repo)
    with pytest.raises(ValueError, match="gesperrte SQL"):
        database.preview_migration(workspace_id, "migrations/001.sql")


def test_migration_blocks_psql_meta_commands(repo_runtime) -> None:
    runtime, workspace_id, repo = repo_runtime
    migration = repo / "migrations" / "meta.sql"
    migration.parent.mkdir()
    migration.write_text("\\! id\n", "utf-8")
    database = DatabaseRuntime(runtime._repo)
    with pytest.raises(ValueError, match="Metabefehle"):
        database.preview_migration(workspace_id, "migrations/meta.sql")


def test_preview_removes_one_outer_transaction_pair() -> None:
    sql = "-- additive migration\nBEGIN;\nCREATE TABLE example(id integer);\nCOMMIT;\n"
    preview = _preview_body(sql)
    assert "CREATE TABLE example" in preview
    assert not preview.lstrip().upper().startswith("BEGIN;")
    assert not preview.rstrip().upper().endswith("COMMIT;")


def test_preview_keeps_plpgsql_begin_inside_dollar_quoted_block() -> None:
    sql = """BEGIN;
DO $$
BEGIN
    IF EXISTS (SELECT 1) THEN
        EXECUTE 'UPDATE llm_routes SET model_id = model WHERE model_id IS NULL';
    END IF;
END $$;
COMMIT;
"""
    preview = _preview_body(sql)
    assert "DO $$" in preview
    assert "BEGIN\n    IF EXISTS" in preview
    assert "END $$;" in preview


def test_productive_migration_is_disabled_by_default(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    migration = repo / "migrations" / "002.sql"
    migration.parent.mkdir(exist_ok=True)
    migration.write_text("CREATE TABLE operator_preview(id integer);\n", "utf-8")
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", raising=False)
    database = DatabaseRuntime(runtime._repo)
    result = database.apply_migration(workspace_id, "migrations/002.sql", "not-used")
    assert result == {
        "ok": False,
        "status": "BLOCKED",
        "blocker": "Produktive DB-Writes sind nicht aktiviert",
    }


def test_confirmation_hash_must_match_before_connection(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    migration = repo / "migrations" / "003.sql"
    migration.parent.mkdir(exist_ok=True)
    migration.write_text("CREATE TABLE operator_preview(id integer);\n", "utf-8")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", "1")
    database = DatabaseRuntime(runtime._repo)
    result = database.apply_migration(workspace_id, "migrations/003.sql", "0" * 64)
    assert result["status"] == "BLOCKED"
    assert result["blocker"] == "Bestätigungs-Hash stimmt nicht"


def test_destructive_migration_requires_separate_activation(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    migration = repo / "migrations" / "004.sql"
    migration.parent.mkdir(exist_ok=True)
    sql = "ALTER TABLE users DROP COLUMN legacy_value;\n"
    migration.write_text(sql, "utf-8")
    checksum = hashlib.sha256(sql.encode()).hexdigest()
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", "1")
    monkeypatch.delenv("SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS", raising=False)
    database = DatabaseRuntime(runtime._repo)
    result = database.apply_migration(workspace_id, "migrations/004.sql", checksum)
    assert result["status"] == "BLOCKED"
    assert result["destructive_actions"] == ["drop_column"]


def test_update_backfill_has_its_own_persistent_gate(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    migration = repo / "migrations" / "005.sql"
    migration.parent.mkdir(exist_ok=True)
    sql = "UPDATE llm_routes SET model_id = model WHERE model_id IS NULL;\n"
    migration.write_text(sql, "utf-8")
    checksum = hashlib.sha256(sql.encode()).hexdigest()
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", "1")
    monkeypatch.delenv("SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS", raising=False)
    database = DatabaseRuntime(runtime._repo)
    result = database.apply_migration(workspace_id, "migrations/005.sql", checksum)
    assert result["status"] == "BLOCKED"
    assert result["blocker"] == "Daten-Backfills sind nicht separat aktiviert"
    assert result["data_backfill_actions"] == ["update_rows"]
    assert "destructive_actions" not in result


def test_enabled_backfill_uses_fixed_host_broker_after_preview(repo_runtime, monkeypatch) -> None:
    runtime, workspace_id, repo = repo_runtime
    migration = repo / "migrations" / "006.sql"
    migration.parent.mkdir(exist_ok=True)
    sql = "UPDATE llm_routes SET model_id = model WHERE model_id IS NULL;\n"
    migration.write_text(sql, "utf-8")
    checksum = hashlib.sha256(sql.encode()).hexdigest()
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS", "1")
    database = DatabaseRuntime(runtime._repo)
    monkeypatch.setattr(
        database,
        "preview_migration",
        lambda *_args, **_kwargs: {
            "ok": True,
            "rolled_back": True,
            "sha256": checksum,
            "data_backfill_actions": ["update_rows"],
            "policy_repair": {"status": "NOT_NEEDED"},
        },
    )
    calls = []

    def fake_call(action, arguments, timeout):
        calls.append((action, arguments, timeout))
        return {"ok": True, "status": "APPLIED", "sha256": checksum}

    monkeypatch.setattr(database.broker, "call", fake_call)
    result = database.apply_migration(workspace_id, "migrations/006.sql", checksum)
    assert result["status"] == "APPLIED"
    assert result["local_preview"]["rolled_back"] is True
    assert result["local_preview"]["policy_repair"]["status"] == "NOT_NEEDED"
    assert calls == [
        (
            "apply_verified_migration",
            {
                "workspace_id": workspace_id,
                "path": "migrations/006.sql",
                "confirmation_sha256": checksum,
            },
            240,
        )
    ]
