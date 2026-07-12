from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_LEDGER_ID_RE = re.compile(
    r"INSERT\s+INTO\s+schema_migrations\s*\(\s*id\s*,\s*name\s*\)\s*"
    r"VALUES\s*\(\s*(?P<id>\d+)\s*,\s*'(?P<name>(?:''|[^'])*)'\s*\)\s*"
    r"ON\s+CONFLICT\s*\(\s*id\s*\)\s*DO\s+NOTHING\s*;",
    re.IGNORECASE | re.DOTALL,
)
SCHEMA_LEDGER_VERSION_RE = re.compile(
    r"INSERT\s+INTO\s+schema_migrations\s*\(\s*version(?:\s*,\s*applied_at)?\s*\)\s*"
    r"VALUES\s*\(\s*'(?P<version>\d+)'(?:\s*,\s*NOW\(\))?\s*\)\s*"
    r"ON\s+CONFLICT\s*\(\s*version\s*\)\s*DO\s+NOTHING\s*;",
    re.IGNORECASE | re.DOTALL,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _legacy_version_insert(migration_id: int, columns: set[str]) -> str:
    if "applied_at" in columns:
        return (
            "INSERT INTO schema_migrations (version, applied_at)\n"
            f"VALUES ('{migration_id:03d}', NOW())\n"
            "ON CONFLICT (version) DO NOTHING;"
        )
    return (
        "INSERT INTO schema_migrations (version)\n"
        f"VALUES ('{migration_id:03d}')\n"
        "ON CONFLICT (version) DO NOTHING;"
    )


def adapt_schema_ledger(sql: str, columns: set[str]) -> dict[str, Any]:
    source = str(sql)
    adapted = source
    action = "not_needed"
    used_columns: list[str] = []

    if not columns:
        return {
            "sql": source,
            "evidence": {
                "family": "schema_migrations_layout_drift",
                "status": "NOT_NEEDED",
                "action": "ledger_not_created_yet",
                "scope": "runtime_sql_only",
                "source_unchanged": True,
                "source_sha256": _sha256(source),
                "runtime_sql_sha256": _sha256(source),
                "detected_columns": [],
                "used_columns": [],
            },
        }

    if {"version"}.issubset(columns) and not {"id", "name"}.issubset(columns):
        match = SCHEMA_LEDGER_ID_RE.search(source)
        if match:
            migration_id = int(match.group("id"))
            adapted = SCHEMA_LEDGER_ID_RE.sub(
                _legacy_version_insert(migration_id, columns), source, count=1
            )
            action = "id_name_to_legacy_version"
            used_columns = [name for name in ("version", "applied_at") if name in columns]
    elif {"id", "name"}.issubset(columns) and "version" not in columns:
        match = SCHEMA_LEDGER_VERSION_RE.search(source)
        if match:
            migration_id = int(match.group("version"))
            replacement = (
                "INSERT INTO schema_migrations (id, name)\n"
                f"VALUES ({migration_id}, 'migration_{migration_id:03d}')\n"
                "ON CONFLICT (id) DO NOTHING;"
            )
            adapted = SCHEMA_LEDGER_VERSION_RE.sub(replacement, source, count=1)
            action = "legacy_version_to_id_name"
            used_columns = ["id", "name"]
    elif not ({"version"}.issubset(columns) or {"id", "name"}.issubset(columns)):
        raise ValueError(
            "Unsupported schema_migrations layout: " + ",".join(sorted(columns))
        )

    return {
        "sql": adapted,
        "evidence": {
            "family": "schema_migrations_layout_drift",
            "status": "APPLIED" if adapted != source else "NOT_NEEDED",
            "action": action,
            "scope": "runtime_sql_only",
            "source_unchanged": True,
            "source_sha256": _sha256(source),
            "runtime_sql_sha256": _sha256(adapted),
            "detected_columns": sorted(columns),
            "used_columns": used_columns,
        },
    }


def _parse_columns(raw: str) -> set[str]:
    return {part.strip() for part in str(raw or "").split(",") if part.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Adapt only schema_migrations ledger inserts for the detected production layout."
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ledger-columns", default="")
    args = parser.parse_args()

    source_path = Path(args.source)
    output_path = Path(args.output)
    source_sql = source_path.read_text(encoding="utf-8")
    result = adapt_schema_ledger(source_sql, _parse_columns(args.ledger_columns))
    output_path.write_text(result["sql"], encoding="utf-8")
    print(json.dumps(result["evidence"], sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
