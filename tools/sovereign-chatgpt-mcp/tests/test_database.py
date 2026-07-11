from __future__ import annotations

import os

import pytest

from database import DatabaseRuntime


def test_migration_blocks_dangerous_sql(repo_runtime) -> None:
    runtime, workspace_id, repo = repo_runtime
    migration = repo / "migrations" / "001.sql"
    migration.parent.mkdir()
    migration.write_text("DROP DATABASE postgres;\n", "utf-8")
    database = DatabaseRuntime(runtime._repo)
    with pytest.raises(ValueError, match="gesperrte SQL"):
        database.preview_migration(workspace_id, "migrations/001.sql")


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
