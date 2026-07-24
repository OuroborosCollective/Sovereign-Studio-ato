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

    def schema_inventory(self) -> dict[str, Any]:
        """Read bounded non-system table metadata without returning row data."""
        conn = self._connection("POSTGRES")
        try:
            conn.set_session(readonly=True, autocommit=False)
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT current_database() AS database, current_user AS user")
                identity = dict(cur.fetchone() or {})
                cur.execute(
                    """SELECT table_schema, table_name
                       FROM information_schema.tables
                       WHERE table_type = 'BASE TABLE'
                         AND table_schema NOT IN ('pg_catalog', 'information_schema')
                       ORDER BY table_schema, table_name
                       LIMIT 1001"""
                )
                rows = [dict(row) for row in cur.fetchall()]
            conn.rollback()
            truncated = len(rows) > 1000
            tables = rows[:1000]
            return {
                "ok": True,
                "status": "POSTGRES_SCHEMA_INVENTORY",
                "database": str(identity.get("database") or "")[:160],
                "user": str(identity.get("user") or "")[:160],
                "tableCount": len(tables),
                "tables": tables,
                "truncated": truncated,
                "rowDataReturned": False,
                "secretValuesExposed": False,
            }
        finally:
            conn.close()

    def schema_contract_inventory(self, table_names: list[str]) -> dict[str, Any]:
        """Read bounded column, constraint and index metadata for exact table identities without reading rows."""
        normalized = sorted({str(name).strip().lower() for name in table_names if str(name).strip()})
        if not normalized or len(normalized) > 100:
            raise ValueError("table_names must contain between 1 and 100 exact table identities")
        identity_pattern = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")
        if any(not identity_pattern.fullmatch(name) for name in normalized):
            raise ValueError("table_names must use exact schema.table identities")

        conn = self._connection("POSTGRES")
        try:
            conn.set_session(readonly=True, autocommit=False)
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT current_database() AS database, current_user AS user")
                identity = dict(cur.fetchone() or {})
                cur.execute(
                    """SELECT n.nspname AS table_schema,
                              c.relname AS table_name,
                              a.attnum AS ordinal_position,
                              a.attname AS column_name,
                              pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
                              a.attnotnull AS not_null,
                              pg_catalog.pg_get_expr(ad.adbin, ad.adrelid) AS default_expression
                       FROM pg_catalog.pg_class c
                       JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                       JOIN pg_catalog.pg_attribute a
                         ON a.attrelid = c.oid
                        AND a.attnum > 0
                        AND NOT a.attisdropped
                       LEFT JOIN pg_catalog.pg_attrdef ad
                         ON ad.adrelid = c.oid
                        AND ad.adnum = a.attnum
                       WHERE c.relkind IN ('r', 'p')
                         AND (n.nspname || '.' || c.relname) = ANY(%s)
                       ORDER BY n.nspname, c.relname, a.attnum""",
                    (normalized,),
                )
                column_rows = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """SELECT n.nspname AS table_schema,
                              c.relname AS table_name,
                              con.conname AS constraint_name,
                              CASE con.contype
                                WHEN 'p' THEN 'PRIMARY KEY'
                                WHEN 'f' THEN 'FOREIGN KEY'
                                WHEN 'u' THEN 'UNIQUE'
                                WHEN 'c' THEN 'CHECK'
                                ELSE con.contype::text
                              END AS constraint_type,
                              pg_catalog.pg_get_constraintdef(con.oid, true) AS definition
                       FROM pg_catalog.pg_class c
                       JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                       JOIN pg_catalog.pg_constraint con ON con.conrelid = c.oid
                       WHERE c.relkind IN ('r', 'p')
                         AND con.contype IN ('p', 'f', 'u', 'c')
                         AND (n.nspname || '.' || c.relname) = ANY(%s)
                       ORDER BY n.nspname, c.relname, constraint_type, con.conname""",
                    (normalized,),
                )
                constraint_rows = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """SELECT n.nspname AS table_schema,
                              c.relname AS table_name,
                              idx.relname AS index_name,
                              i.indisunique AS is_unique,
                              i.indisprimary AS is_primary,
                              pg_catalog.pg_get_indexdef(i.indexrelid) AS definition
                       FROM pg_catalog.pg_class c
                       JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                       JOIN pg_catalog.pg_index i ON i.indrelid = c.oid
                       JOIN pg_catalog.pg_class idx ON idx.oid = i.indexrelid
                       WHERE c.relkind IN ('r', 'p')
                         AND (n.nspname || '.' || c.relname) = ANY(%s)
                       ORDER BY n.nspname, c.relname, idx.relname""",
                    (normalized,),
                )
                index_rows = [dict(row) for row in cur.fetchall()]
            conn.rollback()

            table_map: dict[str, dict[str, Any]] = {}
            for row in column_rows:
                table = f"{row['table_schema']}.{row['table_name']}".lower()
                entry = table_map.setdefault(table, {"table": table, "columns": [], "constraints": [], "indexes": []})
                entry["columns"].append(
                    {
                        "name": str(row.get("column_name") or ""),
                        "ordinalPosition": int(row.get("ordinal_position") or 0),
                        "dataType": str(row.get("data_type") or ""),
                        "notNull": bool(row.get("not_null")),
                        "defaultExpression": row.get("default_expression"),
                    }
                )
            for row in constraint_rows:
                table = f"{row['table_schema']}.{row['table_name']}".lower()
                entry = table_map.setdefault(table, {"table": table, "columns": [], "constraints": [], "indexes": []})
                entry["constraints"].append(
                    {
                        "name": str(row.get("constraint_name") or ""),
                        "type": str(row.get("constraint_type") or ""),
                        "definition": str(row.get("definition") or ""),
                    }
                )
            for row in index_rows:
                table = f"{row['table_schema']}.{row['table_name']}".lower()
                entry = table_map.setdefault(table, {"table": table, "columns": [], "constraints": [], "indexes": []})
                entry["indexes"].append(
                    {
                        "name": str(row.get("index_name") or ""),
                        "isUnique": bool(row.get("is_unique")),
                        "isPrimary": bool(row.get("is_primary")),
                        "definition": str(row.get("definition") or ""),
                    }
                )
            return {
                "ok": True,
                "status": "POSTGRES_SCHEMA_CONTRACT_INVENTORY",
                "database": str(identity.get("database") or "")[:160],
                "user": str(identity.get("user") or "")[:160],
                "requestedTables": normalized,
                "tables": [table_map[name] for name in sorted(table_map)],
                "missingTables": sorted(set(normalized) - set(table_map)),
                "rowDataReturned": False,
                "secretValuesExposed": False,
            }
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
