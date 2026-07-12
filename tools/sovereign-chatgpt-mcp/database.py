from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

from broker_client import HostBrokerClient
from policy import safe_repo_path
from self_heal import REPAIR_ENGINE

FORBIDDEN_SQL = re.compile(
    r"\b(DROP\s+DATABASE|ALTER\s+SYSTEM|COPY\s+.+\s+PROGRAM|CREATE\s+EXTENSION\s+plpython|TRUNCATE\b|VACUUM\s+FULL|REINDEX\s+SYSTEM)\b",
    re.IGNORECASE | re.DOTALL,
)
DESTRUCTIVE_SQL_PATTERNS = {
    "drop_table": re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    "drop_schema": re.compile(r"\bDROP\s+SCHEMA\b", re.IGNORECASE),
    "drop_column": re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE),
    "delete_rows": re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
}
DATA_BACKFILL_SQL_PATTERNS = {
    "update_rows": re.compile(r"\bUPDATE\s+[A-Za-z_\"]", re.IGNORECASE),
}
PSQL_META_COMMAND = re.compile(r"(?m)^\s*\\")
MAX_MIGRATION_BYTES = 500_000


def _preview_normalization(sql: str) -> dict[str, Any]:
    return REPAIR_ENGINE.normalize_migration_preview(sql)


def _preview_body(sql: str) -> str:
    return str(_preview_normalization(sql)["sql"])


class DatabaseRuntime:
    def __init__(self, workspace_resolver) -> None:
        self.workspace_resolver = workspace_resolver
        self.broker = HostBrokerClient()

    @staticmethod
    def _connection(prefix: str = "POSTGRES"):
        host = os.getenv(f"{prefix}_HOST", "").strip()
        database = os.getenv(f"{prefix}_DB", "").strip()
        user = os.getenv(f"{prefix}_USER", "").strip()
        password = os.getenv(f"{prefix}_PASSWORD", "")
        port = int(os.getenv(f"{prefix}_PORT", "5432"))
        if not host or not database or not user:
            raise RuntimeError(f"{prefix}_HOST, {prefix}_DB und {prefix}_USER müssen gesetzt sein")
        return psycopg2.connect(host=host, port=port, dbname=database, user=user, password=password, connect_timeout=10)

    def canary(self) -> dict[str, Any]:
        conn = self._connection("POSTGRES")
        try:
            conn.set_session(readonly=True, autocommit=False)
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS value, current_database() AS database, current_user AS user")
                row = cur.fetchone()
            conn.rollback()
            return {"ok": row[0] == 1, "value": row[0], "database": row[1], "user": row[2]}
        finally:
            conn.close()

    def vector_canary(self) -> dict[str, Any]:
        conn = self._connection("POSTGRES")
        try:
            conn.set_session(readonly=True, autocommit=False)
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                extension = cur.fetchone()
                cur.execute(
                    """SELECT n.nspname AS schema, c.relname AS table_name, a.attname AS column_name
                       FROM pg_attribute a
                       JOIN pg_class c ON c.oid = a.attrelid
                       JOIN pg_namespace n ON n.oid = c.relnamespace
                       JOIN pg_type t ON t.oid = a.atttypid
                       WHERE t.typname = 'vector' AND a.attnum > 0 AND NOT a.attisdropped
                       ORDER BY 1, 2, 3 LIMIT 100"""
                )
                columns = [dict(row) for row in cur.fetchall()]
            conn.rollback()
            return {"ok": extension is not None, "extension_version": extension["extversion"] if extension else None, "vector_columns": columns}
        finally:
            conn.close()

    def _migration(self, workspace_id: str, path: str) -> tuple[Path, str, str, tuple[str, ...], tuple[str, ...]]:
        repo = self.workspace_resolver(workspace_id)
        migration = safe_repo_path(repo, path, must_exist=True)
        if migration.suffix.lower() != ".sql":
            raise ValueError("Migration muss eine SQL-Datei sein")
        data = migration.read_bytes()
        if len(data) > MAX_MIGRATION_BYTES:
            raise ValueError("Migration ist zu groß")
        sql = data.decode("utf-8")
        if PSQL_META_COMMAND.search(sql):
            raise ValueError("psql-Metabefehle sind in Migrationen gesperrt")
        if FORBIDDEN_SQL.search(sql):
            raise ValueError("Migration enthält eine vollständig gesperrte SQL-Operation")
        destructive = tuple(name for name, pattern in DESTRUCTIVE_SQL_PATTERNS.items() if pattern.search(sql))
        data_backfills = tuple(name for name, pattern in DATA_BACKFILL_SQL_PATTERNS.items() if pattern.search(sql))
        _preview_normalization(sql)
        return migration, sql, hashlib.sha256(data).hexdigest(), destructive, data_backfills

    def preview_migration(self, workspace_id: str, path: str) -> dict[str, Any]:
        _, sql, checksum, destructive, data_backfills = self._migration(workspace_id, path)
        normalization = _preview_normalization(sql)
        conn = self._connection("SOVEREIGN_MCP_PREVIEW_POSTGRES")
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '60s'")
                cur.execute("SET LOCAL lock_timeout = '5s'")
                cur.execute(str(normalization["sql"]))
            conn.rollback()
            return {
                "ok": True,
                "rolled_back": True,
                "sha256": checksum,
                "database_scope": "preview",
                "destructive_actions": list(destructive),
                "data_backfill_actions": list(data_backfills),
                "policy_repair": normalization["repair"],
            }
        except Exception as exc:
            conn.rollback()
            return {
                "ok": False,
                "rolled_back": True,
                "sha256": checksum,
                "database_scope": "preview",
                "destructive_actions": list(destructive),
                "data_backfill_actions": list(data_backfills),
                "policy_repair": normalization["repair"],
                "error": str(exc)[:2000],
            }
        finally:
            conn.close()

    def apply_migration(self, workspace_id: str, path: str, confirmation_sha256: str) -> dict[str, Any]:
        if os.getenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", "0") != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Produktive DB-Writes sind nicht aktiviert"}
        _, _, checksum, destructive, data_backfills = self._migration(workspace_id, path)
        if confirmation_sha256 != checksum:
            return {"ok": False, "status": "BLOCKED", "blocker": "Bestätigungs-Hash stimmt nicht", "sha256": checksum}
        if destructive and os.getenv("SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS", "0") != "1":
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Destruktive Migrationen sind nicht separat aktiviert",
                "sha256": checksum,
                "destructive_actions": list(destructive),
            }
        if data_backfills and os.getenv("SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS", "0") != "1":
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Daten-Backfills sind nicht separat aktiviert",
                "sha256": checksum,
                "data_backfill_actions": list(data_backfills),
            }
        preview = self.preview_migration(workspace_id, path)
        if not preview.get("ok"):
            return {"ok": False, "status": "BLOCKED", "blocker": "Preview-Migration ist fehlgeschlagen", "preview": preview}
        result = self.broker.call(
            "apply_verified_migration",
            {
                "workspace_id": workspace_id,
                "path": path,
                "confirmation_sha256": confirmation_sha256,
            },
            timeout=240,
        )
        return {**result, "local_preview": preview}
