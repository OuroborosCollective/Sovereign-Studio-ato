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
DEPLOY_DIAGNOSTIC_RE = re.compile(
    r"SOVEREIGN_DEPLOY_DIAGNOSTIC:([a-z0-9_-]{1,80}):([A-Za-z][A-Za-z0-9_]{0,79})"
)
DEPLOY_CANDIDATE_EVIDENCE_RE = re.compile(
    r"SOVEREIGN_DEPLOY_CANDIDATE:"
    r"status=([a-z]{2,24}):"
    r"exit=(-?[0-9]{1,5}):"
    r"oom=(true|false):"
    r"lastMigration=([A-Za-z0-9._-]{1,120}):"
    r"logsSha256=([0-9a-f]{64})"
)
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
MAX_PREVIEW_SCHEMA_BYTES = 16_000_000
SCHEMA_DUMP_ROW_DATA = re.compile(r"(?im)^\s*(?:COPY\s+|INSERT\s+INTO\s+)")
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

    @staticmethod
    def _run_capture(
        argv: list[str],
        *,
        password: str,
        timeout: int,
        max_stdout_bytes: int,
    ) -> dict[str, Any]:
        completed = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout,
            check=False,
            env={
                **os.environ,
                "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
                "PGPASSWORD": password,
            },
        )
        stdout = bytes(completed.stdout or b"")
        stderr = bytes(completed.stderr or b"")
        if len(stdout) > max_stdout_bytes:
            return {
                "ok": False,
                "exit_code": completed.returncode,
                "stdout": "",
                "stdout_bytes": len(stdout),
                "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
                "failure_family": "PREVIEW_SCHEMA_DUMP_TOO_LARGE",
            }
        try:
            decoded = stdout.decode("utf-8")
        except UnicodeDecodeError:
            return {
                "ok": False,
                "exit_code": completed.returncode,
                "stdout": "",
                "stdout_bytes": len(stdout),
                "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
                "failure_family": "PREVIEW_SCHEMA_DUMP_NOT_UTF8",
            }
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": decoded,
            "stdout_bytes": len(stdout),
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
            "failure_family": None if completed.returncode == 0 else "PREVIEW_SCHEMA_DUMP_FAILED",
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

    def _pg_dump_argv(self, host: str, port: str, database: str, user: str) -> list[str]:
        if not SAFE_CONTAINER_RE.fullmatch(self.backend_container):
            raise ValueError("Backend-Containername ist ungültig")
        return [
            "docker",
            "exec",
            "-i",
            "-e",
            "PGPASSWORD",
            self.backend_container,
            "/usr/bin/pg_dump",
            "--schema-only",
            "--no-owner",
            "--no-privileges",
            "--no-comments",
            "-h",
            host,
            "-p",
            port,
            "-U",
            user,
            "-d",
            database,
        ]

    def _admin_connection_values(self) -> tuple[str, str, str, str, str]:
        host = _read_env_value(self.backend_env_file, "POSTGRES_HOST") or "db"
        port = _read_env_value(self.backend_env_file, "POSTGRES_PORT") or "5432"
        database = _read_env_value(self.backend_env_file, "POSTGRES_DB") or "postgres"
        user = _read_env_value(self.backend_env_file, "POSTGRES_USER")
        password = _read_env_value(self.backend_env_file, "POSTGRES_PASSWORD")
        self._validate_connection(host, port, database, user, password, "POSTGRES_ADMIN")
        return host, port, database, user, password

    def _preview_connection_values(self, *, admin_host: str, admin_port: str, admin_db: str) -> tuple[str, str, str]:
        host = os.getenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_HOST", "").strip()
        port = os.getenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_PORT", "5432").strip()
        database = os.getenv("SOVEREIGN_MCP_PREVIEW_POSTGRES_DB", "").strip()
        if not SAFE_HOST_RE.fullmatch(host):
            raise ValueError("SOVEREIGN_MCP_PREVIEW_POSTGRES_HOST ist ungültig")
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError("SOVEREIGN_MCP_PREVIEW_POSTGRES_PORT ist ungültig")
        if not SAFE_DB_NAME_RE.fullmatch(database):
            raise ValueError("SOVEREIGN_MCP_PREVIEW_POSTGRES_DB ist ungültig")
        if host != admin_host or port != admin_port:
            raise ValueError("Preview-DB muss für schema-only Hydration im selben PostgreSQL-Cluster liegen")
        if database == admin_db:
            raise ValueError("Preview-DB darf niemals die Produktionsdatenbank sein")
        return host, port, database

    @staticmethod
    def _sanitized_command_failure(stage: str, result: dict[str, Any], checksum: str) -> dict[str, Any]:
        stderr = str(result.get("stderr") or "").encode("utf-8")
        return {
            "ok": False,
            "status": "BLOCKED",
            "blocker": f"Migration-Preview scheiterte in Stufe {stage}",
            "failure_family": f"PREVIEW_{stage.upper()}_FAILED",
            "sha256": checksum,
            "failure_stage": stage,
            "exit_code": int(result.get("exit_code") or 0),
            "stderr_sha256": (
                str(result.get("stderr_sha256") or "")
                or hashlib.sha256(stderr).hexdigest()
            ),
            "rolled_back": stage == "migration",
            "database_scope": "preview",
            "production_write_performed": False,
            "secretValuesReturned": False,
        }

    def preview_verified_migration(
        self,
        *,
        workspace_id: str,
        path: str,
        expected_sha256: str = "",
    ) -> dict[str, Any]:
        migration = self._migration(workspace_id, path)
        checksum = str(migration["sha256"])
        expected = str(expected_sha256 or "").strip().lower()
        if expected and expected != checksum:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Preview-Hash stimmt nicht mit der Workspace-Migration überein",
                "sha256": checksum,
                "rolled_back": True,
                "database_scope": "preview",
                "production_write_performed": False,
                "secretValuesReturned": False,
            }

        admin_host, admin_port, admin_db, admin_user, admin_password = self._admin_connection_values()
        preview_host, preview_port, preview_db = self._preview_connection_values(
            admin_host=admin_host,
            admin_port=admin_port,
            admin_db=admin_db,
        )
        reset_sql = (
            f'DROP DATABASE IF EXISTS "{preview_db}" WITH (FORCE);\n'
            f'CREATE DATABASE "{preview_db}" WITH OWNER "{admin_user}" TEMPLATE template0;\n'
        )
        reset = self._run_input(
            self._psql_argv(admin_host, admin_port, admin_db, admin_user),
            reset_sql,
            password=admin_password,
            timeout=90,
        )
        if not reset.get("ok"):
            return self._sanitized_command_failure("reset", reset, checksum)

        schema_dump = self._run_capture(
            self._pg_dump_argv(admin_host, admin_port, admin_db, admin_user),
            password=admin_password,
            timeout=120,
            max_stdout_bytes=MAX_PREVIEW_SCHEMA_BYTES,
        )
        if not schema_dump.get("ok"):
            return self._sanitized_command_failure("schema_dump", schema_dump, checksum)
        schema_sql = str(schema_dump.get("stdout") or "")
        if SCHEMA_DUMP_ROW_DATA.search(schema_sql):
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Schema-only Preview-Dump enthielt unerwartete Row-Data-Anweisungen",
                "failure_family": "PREVIEW_SCHEMA_DUMP_ROW_DATA_DETECTED",
                "sha256": checksum,
                "rolled_back": True,
                "database_scope": "preview",
                "production_write_performed": False,
                "schema_dump_sha256": str(schema_dump.get("stdout_sha256") or ""),
                "secretValuesReturned": False,
            }

        restore = self._run_input(
            self._psql_argv(preview_host, preview_port, preview_db, admin_user),
            schema_sql,
            password=admin_password,
            timeout=180,
        )
        if not restore.get("ok"):
            return self._sanitized_command_failure("restore", restore, checksum)

        preview_sql = (
            "BEGIN;\n"
            "SET LOCAL statement_timeout = '60s';\n"
            "SET LOCAL lock_timeout = '5s';\n"
            f"{migration['preview_sql']}\n"
            "ROLLBACK;\n"
        )
        preview = self._run_input(
            self._psql_argv(preview_host, preview_port, preview_db, admin_user),
            preview_sql,
            password=admin_password,
            timeout=90,
        )
        if not preview.get("ok"):
            return {
                **self._sanitized_command_failure("migration", preview, checksum),
                "schema_hydrated": True,
                "schema_dump_sha256": str(schema_dump.get("stdout_sha256") or ""),
                "schema_dump_bytes": int(schema_dump.get("stdout_bytes") or 0),
                "production_rows_copied": False,
                "policy_repair": migration["policy_repair"],
            }
        return {
            "ok": True,
            "status": "PREVIEW_VERIFIED",
            "rolled_back": True,
            "sha256": checksum,
            "database_scope": "preview",
            "schema_hydrated": True,
            "schema_source": "production-schema-only",
            "schema_dump_sha256": str(schema_dump.get("stdout_sha256") or ""),
            "schema_dump_bytes": int(schema_dump.get("stdout_bytes") or 0),
            "production_rows_copied": False,
            "production_write_performed": False,
            "destructive_actions": list(migration["destructive_actions"]),
            "data_backfill_actions": list(migration["data_backfill_actions"]),
            "policy_repair": migration["policy_repair"],
            "secretValuesReturned": False,
        }

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

        preview = self.preview_verified_migration(
            workspace_id=workspace_id,
            path=path,
            expected_sha256=checksum,
        )
        if not preview.get("ok"):
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Host-Broker-Preview ist fehlgeschlagen",
                "sha256": checksum,
                "preview": preview,
                "policy_repair": migration["policy_repair"],
            }

        admin_host, admin_port, admin_db, admin_user, admin_password = self._admin_connection_values()
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
                "preview": preview,
                "policy_repair": migration["policy_repair"],
                "error": applied["stderr"],
            }
        return {
            "ok": True,
            "status": "APPLIED",
            "sha256": checksum,
            "destructive_actions": list(destructive),
            "data_backfill_actions": list(data_backfills),
            "preview": preview,
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
            diagnostic_matches = DEPLOY_DIAGNOSTIC_RE.findall(result["stderr"])
            diagnostic_trace = [
                {"stage": stage, "errorType": error_type}
                for stage, error_type in diagnostic_matches[:8]
            ]
            causal_diagnostic = diagnostic_matches[0] if diagnostic_matches else None
            terminal_diagnostic = diagnostic_matches[-1] if diagnostic_matches else None
            diagnostic_stage = causal_diagnostic[0] if causal_diagnostic else None
            diagnostic_error_type = causal_diagnostic[1] if causal_diagnostic else None
            candidate_matches = DEPLOY_CANDIDATE_EVIDENCE_RE.findall(result["stderr"])
            candidate = candidate_matches[-1] if candidate_matches else None
            return {
                "ok": False,
                "status": "FAILED",
                "failureFamily": "BACKEND_DEPLOY_SCRIPT_FAILED",
                "blocker": "Das revisionsgebundene Backend-Deployskript ist fehlgeschlagen",
                "image_digest": image_digest,
                "expected_revision": expected_revision,
                "mutationPerformed": False,
                "readbackVerified": False,
                "diagnosticStage": diagnostic_stage,
                "diagnosticErrorType": diagnostic_error_type,
                "diagnosticTrace": diagnostic_trace,
                "terminalDiagnosticStage": terminal_diagnostic[0] if terminal_diagnostic else None,
                "terminalDiagnosticErrorType": terminal_diagnostic[1] if terminal_diagnostic else None,
                "candidateStatus": candidate[0] if candidate else None,
                "candidateExitCode": int(candidate[1]) if candidate else None,
                "candidateOOMKilled": candidate[2] == "true" if candidate else None,
                "candidateLastMigration": candidate[3] if candidate else None,
                "candidateLogsSha256": candidate[4] if candidate else None,
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
