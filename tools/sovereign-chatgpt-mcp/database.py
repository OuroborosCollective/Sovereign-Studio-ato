from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

from policy import safe_repo_path

FORBIDDEN_SQL = re.compile(
    r"\b(DROP\s+DATABASE|ALTER\s+SYSTEM|COPY\s+.+\s+PROGRAM|CREATE\s+EXTENSION\s+plpython|TRUNCATE\b|VACUUM\s+FULL|REINDEX\s+SYSTEM)\b",
    re.IGNORECASE | re.DOTALL,
)
DESTRUCTIVE_SQL_PATTERNS = {
    "drop_table": re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    "drop_schema": re.compile(r"\bDROP\s+SCHEMA\b", re.IGNORECASE),
    "drop_column": re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE),
    "delete_rows": re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    "update_rows": re.compile(r"\bUPDATE\s+[A-Za-z_\"]", re.IGNORECASE),
}
MAX_MIGRATION_BYTES = 500_000


class DatabaseRuntime:
    def __init__(self, workspace_resolver) -> None:
        self.workspace_resolver = workspace_resolver

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

    def _migration(self, workspace_id: str, path: str) -> tuple[Path, str, str, tuple[str, ...]]:
        repo = self.workspace_resolver(workspace_id)
        migration = safe_repo_path(repo, path, must_exist=True)
        data = migration.read_bytes()
        if len(data) > MAX_MIGRATION_BYTES:
            raise ValueError("Migration ist zu groß")
        sql = data.decode("utf-8")
        if FORBIDDEN_SQL.search(sql):
            raise ValueError("Migration enthält eine vollständig gesperrte SQL-Operation")
        destructive = tuple(name for name, pattern in DESTRUCTIVE_SQL_PATTERNS.items() if pattern.search(sql))
        return migration, sql, hashlib.sha256(data).hexdigest(), destructive

    def preview_migration(self, workspace_id: str, path: str) -> dict[str, Any]:
        _, sql, checksum, destructive = self._migration(workspace_id, path)
        conn = self._connection("SOVEREIGN_MCP_PREVIEW_POSTGRES")
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '60s'")
                cur.execute("SET LOCAL lock_timeout = '5s'")
                cur.execute(sql)
            conn.rollback()
            return {
                "ok": True,
                "rolled_back": True,
                "sha256": checksum,
                "database_scope": "preview",
                "destructive_actions": list(destructive),
            }
        except Exception as exc:
            conn.rollback()
            return {
                "ok": False,
                "rolled_back": True,
                "sha256": checksum,
                "database_scope": "preview",
                "destructive_actions": list(destructive),
                "error": str(exc)[:2000],
            }
        finally:
            conn.close()

    def apply_migration(self, workspace_id: str, path: str, confirmation_sha256: str) -> dict[str, Any]:
        if os.getenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", "0") != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Produktive DB-Writes sind nicht aktiviert"}
        _, sql, checksum, destructive = self._migration(workspace_id, path)
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
        preview = self.preview_migration(workspace_id, path)
        if not preview.get("ok"):
            return {"ok": False, "status": "BLOCKED", "blocker": "Preview-Migration ist fehlgeschlagen", "preview": preview}

        conn = self._connection("POSTGRES")
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '120s'")
                cur.execute("SET LOCAL lock_timeout = '5s'")
                cur.execute(sql)
            conn.commit()
            return {
                "ok": True,
                "status": "APPLIED",
                "sha256": checksum,
                "destructive_actions": list(destructive),
                "preview": preview,
            }
        except Exception as exc:
            conn.rollback()
            return {"ok": False, "status": "FAILED", "sha256": checksum, "error": str(exc)[:2000]}
        finally:
            conn.close()
