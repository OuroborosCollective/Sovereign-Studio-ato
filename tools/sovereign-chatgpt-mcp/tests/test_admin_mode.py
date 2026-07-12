from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from admin_mode import PrivateAdminRuntime, _adapt_schema_ledger


def test_schema_ledger_adapts_id_name_to_legacy_version_with_timestamp() -> None:
    sql = """BEGIN;
CREATE TABLE IF NOT EXISTS example(id integer);
INSERT INTO schema_migrations (id, name)
VALUES (8, 'knowledge_memory_passkeys_stepup')
ON CONFLICT (id) DO NOTHING;
COMMIT;
"""
    result = _adapt_schema_ledger(sql, {"version", "applied_at"})
    assert result["repair"]["status"] == "APPLIED"
    assert result["repair"]["action"] == "id_name_to_legacy_version"
    assert result["repair"]["used_columns"] == ["version", "applied_at"]
    assert "schema_migrations (version, applied_at)" in result["sql"]
    assert "VALUES ('008', NOW())" in result["sql"]
    assert result["repair"]["source_unchanged"] is True


def test_schema_ledger_adapts_id_name_to_version_only() -> None:
    sql = """BEGIN;
INSERT INTO schema_migrations (id, name)
VALUES (8, 'knowledge_memory_passkeys_stepup')
ON CONFLICT (id) DO NOTHING;
COMMIT;
"""
    result = _adapt_schema_ledger(sql, {"version"})
    assert result["repair"]["status"] == "APPLIED"
    assert result["repair"]["used_columns"] == ["version"]
    assert "schema_migrations (version)" in result["sql"]
    assert "VALUES ('008')" in result["sql"]
    assert "applied_at" not in result["sql"]


def test_schema_ledger_adapts_legacy_version_to_id_name() -> None:
    sql = """INSERT INTO schema_migrations (version, applied_at)
VALUES ('005', NOW())
ON CONFLICT (version) DO NOTHING;
"""
    result = _adapt_schema_ledger(sql, {"id", "name", "applied_at"})
    assert result["repair"]["status"] == "APPLIED"
    assert result["repair"]["action"] == "legacy_version_to_id_name"
    assert "schema_migrations (id, name)" in result["sql"]
    assert "VALUES (5, 'migration_005')" in result["sql"]


class FakeOperations:
    def __init__(self, tmp_path: Path, migration_sql: str, ledger_columns: set[str] | None = None) -> None:
        self.workspace_root = tmp_path / "workspaces"
        self.workspace_root.mkdir()
        self.backend_env_file = tmp_path / "backend.env"
        self.backend_env_file.write_text(
            "POSTGRES_HOST=db\n"
            "POSTGRES_PORT=5432\n"
            "POSTGRES_DB=postgres\n"
            "POSTGRES_USER=postgres\n"
            "POSTGRES_PASSWORD=admin-secret\n",
            "utf-8",
        )
        self.migration_sql = migration_sql
        self.ledger_columns = ledger_columns or {"version", "applied_at"}
        self.calls: list[str] = []

    def _validate_connection(self, *_args, **_kwargs) -> None:
        return None

    def _psql_argv(self, *_args) -> list[str]:
        return ["psql"]

    def _run_input(self, _argv, input_text, *, password, timeout):
        assert password == "admin-secret"
        self.calls.append(input_text)
        if "information_schema.columns" in input_text:
            rows = "\n".join(sorted(self.ledger_columns))
            return {
                "ok": True,
                "exit_code": 0,
                "stdout": f" column_name\n-------------\n{rows}\n({len(self.ledger_columns)} rows)\n",
                "stderr": "",
            }
        return {"ok": True, "exit_code": 0, "stdout": "OK\n", "stderr": ""}

    def apply_verified_migration(self, **_kwargs):
        return {
            "ok": False,
            "status": "FAILED",
            "error": 'ERROR: column "id" of relation "schema_migrations" does not exist',
        }

    def _migration(self, _workspace_id, _path):
        return {
            "sql": self.migration_sql,
            "sha256": hashlib.sha256(self.migration_sql.encode("utf-8")).hexdigest(),
        }


def _migration_sql() -> str:
    return """BEGIN;
CREATE TABLE IF NOT EXISTS knowledge_blocks(id integer);
INSERT INTO schema_migrations (id, name)
VALUES (8, 'knowledge_memory_passkeys_stepup')
ON CONFLICT (id) DO NOTHING;
COMMIT;
"""


def test_failed_migration_repairs_legacy_schema_ledger_and_retries(tmp_path) -> None:
    sql = _migration_sql()
    operations = FakeOperations(tmp_path, sql)
    runtime = PrivateAdminRuntime(operations)  # type: ignore[arg-type]
    checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()

    result = runtime.apply_verified_migration_with_self_heal(
        workspace_id="job-123456abcdef",
        path="scripts/sovereign-backend/migrations/008.sql",
        confirmation_sha256=checksum,
    )

    assert result["status"] == "APPLIED_AFTER_REPAIR"
    assert result["schema_repair"]["action"] == "id_name_to_legacy_version"
    assert result["schema_repair"]["attempts"] == 2
    assert result["production_structure_preview"] == {"ok": True, "rolled_back": True}
    assert len(operations.calls) == 3
    assert "ROLLBACK;" in operations.calls[1]
    assert "schema_migrations (version, applied_at)" in operations.calls[2]


def test_failed_migration_retries_against_version_only_ledger(tmp_path) -> None:
    sql = _migration_sql()
    operations = FakeOperations(tmp_path, sql, {"version"})
    runtime = PrivateAdminRuntime(operations)  # type: ignore[arg-type]
    checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()

    result = runtime.apply_verified_migration_with_self_heal(
        workspace_id="job-123456abcdef",
        path="scripts/sovereign-backend/migrations/008.sql",
        confirmation_sha256=checksum,
    )

    assert result["status"] == "APPLIED_AFTER_REPAIR"
    assert result["schema_repair"]["detected_columns"] == ["version"]
    assert result["schema_repair"]["used_columns"] == ["version"]
    assert "schema_migrations (version)" in operations.calls[2]
    assert "applied_at" not in operations.calls[2]


def test_admin_sql_is_disabled_until_private_switch_is_active(tmp_path, monkeypatch) -> None:
    operations = FakeOperations(tmp_path, "SELECT 1;")
    runtime = PrivateAdminRuntime(operations)  # type: ignore[arg-type]
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_ADMIN_SQL", raising=False)
    result = runtime.execute_sql(sql="SELECT 1;")
    assert result["status"] == "BLOCKED"


def test_admin_sql_executes_complete_postgres_sql_when_enabled(tmp_path, monkeypatch) -> None:
    operations = FakeOperations(tmp_path, "SELECT 1;")
    runtime = PrivateAdminRuntime(operations)  # type: ignore[arg-type]
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_ADMIN_SQL", "1")
    result = runtime.execute_sql(sql="CREATE TABLE example(id integer); SELECT 1;", timeout_seconds=60)
    assert result["status"] == "EXECUTED"
    assert result["ok"] is True
    assert result["database"] == "postgres"


def test_main_push_is_disabled_until_private_switch_is_active(tmp_path, monkeypatch) -> None:
    operations = FakeOperations(tmp_path, "SELECT 1;")
    runtime = PrivateAdminRuntime(operations)  # type: ignore[arg-type]
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_MAIN_PUSH", raising=False)
    result = runtime.push_workspace_to_main(workspace_id="job-123456abcdef", commit_message="test")
    assert result["status"] == "BLOCKED"


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def test_private_main_push_commits_workspace_and_updates_remote_main(tmp_path, monkeypatch) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)

    operations = FakeOperations(tmp_path, "SELECT 1;")
    workspace_repo = operations.workspace_root / "job-123456abcdef" / "repo"
    workspace_repo.mkdir(parents=True)
    _git(workspace_repo, "init")
    _git(workspace_repo, "config", "user.name", "Test")
    _git(workspace_repo, "config", "user.email", "test@example.invalid")
    _git(workspace_repo, "remote", "add", "origin", str(remote))
    _git(workspace_repo, "checkout", "-b", "sovereign/chatgpt/test")
    (workspace_repo / "README.md").write_text("initial\n", "utf-8")
    _git(workspace_repo, "add", "README.md")
    _git(workspace_repo, "commit", "-m", "initial")
    _git(workspace_repo, "push", "origin", "HEAD:refs/heads/main")

    (workspace_repo / "README.md").write_text("updated by broker\n", "utf-8")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_MAIN_PUSH", "1")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    runtime = PrivateAdminRuntime(operations)  # type: ignore[arg-type]

    result = runtime.push_workspace_to_main(
        workspace_id="job-123456abcdef",
        commit_message="broker main update",
    )

    assert result["status"] == "PUSHED_MAIN"
    assert _git(remote, "log", "-1", "--format=%s", "refs/heads/main") == "broker main update"
