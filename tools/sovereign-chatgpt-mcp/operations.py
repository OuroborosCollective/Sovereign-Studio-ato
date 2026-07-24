from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from self_heal import REPAIR_ENGINE

IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
WORKSPACE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{5,63}$")
SAFE_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
SAFE_HOST_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
SAFE_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
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
BLOCKED_PATH_PARTS = {".git", ".env", ".ssh", "node_modules", "secrets", "credentials"}


def _read_env_value(path: Path, key: str) -> str:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    value = ""
    for raw_line in path.read_text("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        current_key, current_value = line.split("=", 1)
        if current_key.strip() == key:
            value = current_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


class OperationsRuntime:
    def __init__(self) -> None:
        self.deploy_script = Path(os.getenv("SOVEREIGN_MCP_DEPLOY_SCRIPT", "/opt/sovereign-chatgpt-tools/bin/deploy-sovereign-backend"))
        self.rollback_script = Path(os.getenv("SOVEREIGN_MCP_ROLLBACK_SCRIPT", "/opt/sovereign-chatgpt-tools/bin/rollback-sovereign-backend"))
        self.workspace_root = Path(os.getenv("SOVEREIGN_MCP_WORKSPACE_ROOT", "/opt/sovereign-chatgpt-tools/workspaces"))
        self.backend_env_file = Path(os.getenv("SOVEREIGN_BACKEND_ENV_FILE", "/opt/sovereign-backend/.env"))
        self.backend_container = os.getenv("SOVEREIGN_BACKEND_CONTAINER", "sovereign-backend").strip()

    @staticmethod
    def _run(script: Path, args: list[str]) -> dict[str, Any]:
        completed = subprocess.run(
            [str(script), *args],
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
            env={**os.environ, "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")},
        )
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-24000:],
            "stderr": completed.stderr[-24000:],
        }

    @staticmethod
    def _run_input(argv: list[str], input_text: str, *, password: str, timeout: int) -> dict[str, Any]:
        completed = subprocess.run(
            argv,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={
                **os.environ,
                "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
                "PGPASSWORD": password,
            },
        )
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
        }

    def _migration(self, workspace_id: str, relative_path: str) -> dict[str, Any]:
        workspace_id = str(workspace_id or "").strip().lower()
        if not WORKSPACE_ID_RE.fullmatch(workspace_id):
            raise ValueError("Ungültige workspace_id")
        relative = Path(str(relative_path or "").strip())
        if relative.is_absolute() or not relative.parts or relative.suffix.lower() != ".sql":
            raise ValueError("Migration muss ein relativer SQL-Pfad sein")
        if any(part in BLOCKED_PATH_PARTS or part.startswith(".env") for part in relative.parts):
            raise ValueError("Geschützter Migrationspfad")
        repo = (self.workspace_root.resolve() / workspace_id / "repo").resolve()
        migration = (repo / relative).resolve()
        if repo not in migration.parents or not migration.is_file():
            raise FileNotFoundError(str(relative_path))
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
        normalization = REPAIR_ENGINE.normalize_migration_preview(sql)
        return {
            "path": migration,
            "sql": sql,
            "preview_sql": normalization["sql"],
            "policy_repair": normalization["repair"],
            "sha256": hashlib.sha256(data).hexdigest(),
            "destructive_actions": destructive,
            "data_backfill_actions": data_backfills,
        }

    @staticmethod
    def _validate_connection(host: str, port: str, database: str, user: str, password: str, prefix: str) -> None:
        if not SAFE_HOST_RE.fullmatch(host):
            raise ValueError(f"{prefix}_HOST ist ungültig")
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError(f"{prefix}_PORT ist ungültig")
        if not SAFE_DB_NAME_RE.fullmatch(database):
            raise ValueError(f"{prefix}_DB ist ungültig")
        if not SAFE_DB_NAME_RE.fullmatch(user):
            raise ValueError(f"{prefix}_USER ist ungültig")
        if not password:
            raise ValueError(f"{prefix}_PASSWORD fehlt")

    def _psql_argv(self, host: str, port: str, database: str, user: str) -> list[str]:
        if not SAFE_CONTAINER_RE.fullmatch(self.backend_container):
            raise ValueError("Backend-Containername ist ungültig")
        return [
            "docker",
            "exec",
            "-i",
            "-e",
            "PGPASSWORD",
            self.backend_container,
            "/usr/bin/psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            host,
            "-p",
            port,
            "-U",
            user,
            "-d",
            database,
        ]

    def apply_verified_migration(self, *, workspace_id: str, path: str, confirmation_sha256: str) -> dict[str, Any]:
        if os.getenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", "0") != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Produktive DB-Writes sind nicht aktiviert"}
        migration = self._migration(workspace_id, path)
        checksum = migration["sha256"]
        if confirmation_sha256 != checksum:
            return {"ok": False, "status": "BLOCKED", "blocker": "Bestätigungs-Hash stimmt nicht", "sha256": checksum}
        destructive = migration["destructive_actions"]
        data_backfills = migration["data_backfill_actions"]
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

        preview_host = os.getenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_HOST", "").strip()
        preview_port = os.getenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_PORT", "5432").strip()
        preview_db = os.getenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_DB", "").strip()
        preview_user = os.getenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_USER", "").strip()
        preview_password = os.getenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_PASSWORD", "")
        self._validate_connection(preview_host, preview_port, preview_db, preview_user, preview_password, "SOVEREIGN_MCP_PREVIEW_POSTGRES")
        preview_sql = (
            "BEGIN;\n"
            "SET LOCAL statement_timeout = '60s';\n"
            "SET LOCAL lock_timeout = '5s';\n"
            f"{migration['preview_sql']}\n"
            "ROLLBACK;\n"
        )
        preview = self._run_input(
            self._psql_argv(preview_host, preview_port, preview_db, preview_user),
            preview_sql,
            password=preview_password,
            timeout=90,
        )
        if not preview["ok"]:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Host-Broker-Preview ist fehlgeschlagen",
                "sha256": checksum,
                "preview": preview,
                "policy_repair": migration["policy_repair"],
            }

        admin_host = _read_env_value(self.backend_env_file, "POSTGRES_HOST") or "db"
        admin_port = _read_env_value(self.backend_env_file, "POSTGRES_PORT") or "5432"
        admin_db = _read_env_value(self.backend_env_file, "POSTGRES_DB") or "postgres"
        admin_user = _read_env_value(self.backend_env_file, "POSTGRES_USER")
        admin_password = _read_env_value(self.backend_env_file, "POSTGRES_PASSWORD")
        self._validate_connection(admin_host, admin_port, admin_db, admin_user, admin_password, "POSTGRES_ADMIN")
        applied = self._run_input(
            self._psql_argv(admin_host, admin_port, admin_db, admin_user),
            migration["sql"],
            password=admin_password,
            timeout=180,
        )
        if not applied["ok"]:
            return {
                "ok": False,
                "status": "FAILED",
                "sha256": checksum,
                "destructive_actions": list(destructive),
                "data_backfill_actions": list(data_backfills),
                "preview": {"ok": True, "rolled_back": True},
                "policy_repair": migration["policy_repair"],
                "error": applied["stderr"],
            }
        return {
            "ok": True,
            "status": "APPLIED",
            "sha256": checksum,
            "destructive_actions": list(destructive),
            "data_backfill_actions": list(data_backfills),
            "preview": {"ok": True, "rolled_back": True},
            "policy_repair": migration["policy_repair"],
            "production_database": admin_db,
        }

    def deploy_verified_release(self, *, image_digest: str, expected_revision: str, confirmation_revision: str) -> dict[str, Any]:
        if os.getenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "0") != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Deploy-Writes sind nicht aktiviert"}
        if not IMAGE_DIGEST_RE.fullmatch(image_digest):
            raise ValueError("image_digest muss ein vollständiger sha256-Digest sein")
        if not COMMIT_SHA_RE.fullmatch(expected_revision):
            raise ValueError("expected_revision muss ein vollständiger Commit-SHA sein")
        if confirmation_revision != expected_revision:
            return {"ok": False, "status": "BLOCKED", "blocker": "Bestätigung stimmt nicht mit expected_revision überein"}
        if not self.deploy_script.is_file() or not os.access(self.deploy_script, os.X_OK):
            return {"ok": False, "status": "BLOCKED", "blocker": f"Fixes Deploy-Skript fehlt: {self.deploy_script}"}
        result = self._run(self.deploy_script, [image_digest, expected_revision])
        if not result["ok"]:
            return {
                "ok": False,
                "status": "FAILED",
                "failureFamily": "BACKEND_DEPLOY_SCRIPT_FAILED",
                "blocker": "Das revisionsgebundene Backend-Deployskript ist fehlgeschlagen",
                "image_digest": image_digest,
                "expected_revision": expected_revision,
                "mutationPerformed": False,
                "readbackVerified": False,
                "stderrSha256": hashlib.sha256(result["stderr"].encode("utf-8")).hexdigest(),
                "secretValuesReturned": False,
            }

        try:
            lines = [line.strip() for line in result["stdout"].splitlines() if line.strip()]
            readback = json.loads(lines[-1])
        except (IndexError, TypeError, ValueError, json.JSONDecodeError):
            return {
                "ok": False,
                "status": "DEPLOYED_ADMIN_READBACK_INVALID",
                "failureFamily": "BACKEND_DEPLOY_READBACK_INVALID",
                "blocker": "Das Deployskript meldete Erfolg ohne gültigen strukturierten Readback",
                "image_digest": image_digest,
                "expected_revision": expected_revision,
                "mutationPerformed": True,
                "readbackVerified": False,
                "stdoutSha256": hashlib.sha256(result["stdout"].encode("utf-8")).hexdigest(),
                "secretValuesReturned": False,
            }

        health = readback.get("health") if isinstance(readback.get("health"), dict) else {}
        admin_canary = readback.get("adminCanary") if isinstance(readback.get("adminCanary"), dict) else {}
        rollback = readback.get("rollback") if isinstance(readback.get("rollback"), dict) else {}
        verified = bool(
            readback.get("ok") is True
            and readback.get("status") == "DEPLOYED_ADMIN_VERIFIED"
            and readback.get("imageDigest") == image_digest
            and readback.get("revision") == expected_revision
            and readback.get("readbackVerified") is True
            and health.get("ok") is True
            and health.get("sourceRevision") == expected_revision
            and health.get("imageDigest") == image_digest
            and admin_canary.get("ok") is True
            and admin_canary.get("status") == "ENTERPRISE_ADMIN_LIVE_CANARY_VERIFIED"
            and admin_canary.get("sourceRevision") == expected_revision
            and admin_canary.get("imageDigest") == image_digest
            and admin_canary.get("secretValuesReturned") is False
            and rollback.get("previewVerified") is True
            and IMAGE_DIGEST_RE.fullmatch(str(rollback.get("previousImageDigest") or ""))
            and COMMIT_SHA_RE.fullmatch(str(rollback.get("previousRevision") or ""))
            and re.fullmatch(r"[0-9a-f]{64}", str(rollback.get("receiptSha256") or ""))
        )
        return {
            "ok": verified,
            "status": "DEPLOYED_ADMIN_VERIFIED" if verified else "DEPLOYED_ADMIN_READBACK_INCOMPLETE",
            "failureFamily": None if verified else "BACKEND_DEPLOY_READBACK_INCOMPLETE",
            "blocker": None if verified else "Admin-, Revisions- oder Rollback-Readback ist unvollständig",
            "image_digest": image_digest,
            "expected_revision": expected_revision,
            "actualRevision": str(readback.get("revision") or "") or None,
            "readbackVerified": verified,
            "mutationPerformed": True,
            "ownerApproved": os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() == "1",
            "health": health,
            "adminCanary": admin_canary,
            "rollback": rollback,
            "stdoutSha256": hashlib.sha256(result["stdout"].encode("utf-8")).hexdigest(),
            "secretValuesReturned": False,
        }

    def rollback_release(self, *, target_image_digest: str, confirmation_digest: str) -> dict[str, Any]:
        if os.getenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "0") != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Deploy-Writes sind nicht aktiviert"}
        if not IMAGE_DIGEST_RE.fullmatch(target_image_digest):
            raise ValueError("target_image_digest muss ein vollständiger sha256-Digest sein")
        if confirmation_digest != target_image_digest:
            return {"ok": False, "status": "BLOCKED", "blocker": "Bestätigungs-Digest stimmt nicht"}
        if not self.rollback_script.is_file() or not os.access(self.rollback_script, os.X_OK):
            return {"ok": False, "status": "BLOCKED", "blocker": f"Fixes Rollback-Skript fehlt: {self.rollback_script}"}
        result = self._run(self.rollback_script, [target_image_digest])
        return {**result, "status": "ROLLED_BACK" if result["ok"] else "FAILED", "target_image_digest": target_image_digest}
