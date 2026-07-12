from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from operations import OperationsRuntime, _read_env_value
from self_heal import REPAIR_ENGINE

MAX_ADMIN_SQL_BYTES = 1_000_000
WORKSPACE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{5,63}$")
SCHEMA_LEDGER_ID_RE = re.compile(
    r"INSERT\s+INTO\s+schema_migrations\s*\(\s*id\s*,\s*name\s*\)\s*"
    r"VALUES\s*\(\s*(?P<id>\d+)\s*,\s*'(?P<name>(?:''|[^'])*)'\s*\)\s*"
    r"ON\s+CONFLICT\s*\(\s*id\s*\)\s*DO\s+NOTHING\s*;",
    re.IGNORECASE | re.DOTALL,
)
SCHEMA_LEDGER_VERSION_RE = re.compile(
    r"INSERT\s+INTO\s+schema_migrations\s*\(\s*version\s*,\s*applied_at\s*\)\s*"
    r"VALUES\s*\(\s*'(?P<version>\d+)'\s*,\s*NOW\(\)\s*\)\s*"
    r"ON\s+CONFLICT\s*\(\s*version\s*\)\s*DO\s+NOTHING\s*;",
    re.IGNORECASE | re.DOTALL,
)
SCHEMA_LEDGER_ERROR = re.compile(
    r"column \"(?:id|name|version)\" of relation \"schema_migrations\" does not exist",
    re.IGNORECASE,
)


def _enabled(name: str) -> bool:
    return os.getenv(name, "0").strip() == "1"


def _adapt_schema_ledger(sql: str, columns: set[str]) -> dict[str, Any]:
    source = str(sql)
    adapted = source
    action = "not_needed"

    id_match = SCHEMA_LEDGER_ID_RE.search(source)
    if id_match and "version" in columns and not {"id", "name"}.issubset(columns):
        migration_id = int(id_match.group("id"))
        replacement = (
            "INSERT INTO schema_migrations (version, applied_at)\n"
            f"VALUES ('{migration_id:03d}', NOW())\n"
            "ON CONFLICT (version) DO NOTHING;"
        )
        adapted = SCHEMA_LEDGER_ID_RE.sub(replacement, source, count=1)
        action = "id_name_to_legacy_version"

    version_match = SCHEMA_LEDGER_VERSION_RE.search(source)
    if version_match and {"id", "name"}.issubset(columns) and "version" not in columns:
        migration_id = int(version_match.group("version"))
        replacement = (
            "INSERT INTO schema_migrations (id, name)\n"
            f"VALUES ({migration_id}, 'migration_{migration_id:03d}')\n"
            "ON CONFLICT (id) DO NOTHING;"
        )
        adapted = SCHEMA_LEDGER_VERSION_RE.sub(replacement, source, count=1)
        action = "legacy_version_to_id_name"

    return {
        "sql": adapted,
        "repair": {
            "family": "schema_migrations_layout_drift",
            "status": "APPLIED" if adapted != source else "NOT_NEEDED",
            "action": action,
            "scope": "runtime_sql_only",
            "source_unchanged": True,
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "runtime_sql_sha256": hashlib.sha256(adapted.encode("utf-8")).hexdigest(),
            "detected_columns": sorted(columns),
            "attempts": 1 if adapted != source else 0,
            "max_attempts": 2,
        },
    }


class PrivateAdminRuntime:
    def __init__(self, operations: OperationsRuntime) -> None:
        self.operations = operations

    def _admin_connection(self, database: str = "") -> tuple[str, str, str, str, str]:
        host = _read_env_value(self.operations.backend_env_file, "POSTGRES_HOST") or "db"
        port = _read_env_value(self.operations.backend_env_file, "POSTGRES_PORT") or "5432"
        configured_db = _read_env_value(self.operations.backend_env_file, "POSTGRES_DB") or "postgres"
        user = _read_env_value(self.operations.backend_env_file, "POSTGRES_USER")
        password = _read_env_value(self.operations.backend_env_file, "POSTGRES_PASSWORD")
        selected_db = str(database or configured_db).strip()
        self.operations._validate_connection(host, port, selected_db, user, password, "POSTGRES_ADMIN")
        return host, port, selected_db, user, password

    def execute_sql(self, *, sql: str, database: str = "", timeout_seconds: int = 300) -> dict[str, Any]:
        if not _enabled("SOVEREIGN_MCP_ENABLE_ADMIN_SQL"):
            return {"ok": False, "status": "BLOCKED", "blocker": "Privates Admin-SQL ist nicht aktiviert"}
        statement = str(sql or "")
        encoded = statement.encode("utf-8")
        if not statement.strip():
            raise ValueError("SQL darf nicht leer sein")
        if len(encoded) > MAX_ADMIN_SQL_BYTES:
            raise ValueError("SQL überschreitet das Admin-Limit")
        if re.search(r"(?m)^\s*\\", statement):
            raise ValueError("psql-Metabefehle und Shell-Escapes sind kein PostgreSQL-SQL")
        timeout = max(1, min(int(timeout_seconds), 3600))
        host, port, selected_db, user, password = self._admin_connection(database)
        result = self.operations._run_input(
            self.operations._psql_argv(host, port, selected_db, user),
            statement,
            password=password,
            timeout=timeout,
        )
        return {
            **result,
            "status": "EXECUTED" if result["ok"] else "FAILED",
            "database": selected_db,
            "sql_sha256": hashlib.sha256(encoded).hexdigest(),
        }

    def _git(self, repo: Path, argv: list[str], *, env: dict[str, str] | None = None, timeout: int = 300) -> dict[str, Any]:
        completed = subprocess.run(
            ["git", *argv],
            cwd=str(repo),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-24000:],
            "stderr": completed.stderr[-24000:],
        }

    def push_workspace_to_main(self, *, workspace_id: str, commit_message: str) -> dict[str, Any]:
        if not _enabled("SOVEREIGN_MCP_ENABLE_MAIN_PUSH"):
            return {"ok": False, "status": "BLOCKED", "blocker": "Direkter Main-Push ist nicht aktiviert"}
        workspace = str(workspace_id or "").strip().lower()
        if not WORKSPACE_ID_RE.fullmatch(workspace):
            raise ValueError("Ungültige workspace_id")
        message = str(commit_message or "").strip()
        if not message:
            raise ValueError("Commit-Nachricht darf nicht leer sein")
        repo = (self.operations.workspace_root.resolve() / workspace / "repo").resolve()
        root = self.operations.workspace_root.resolve()
        if root not in repo.parents or not (repo / ".git").is_dir():
            raise FileNotFoundError("Workspace-Repository fehlt")

        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            raise RuntimeError("GITHUB_TOKEN fehlt im privaten Broker")
        self._git(repo, ["config", "user.name", os.getenv("SOVEREIGN_MCP_GIT_AUTHOR_NAME", "Sovereign ChatGPT Operator")])
        self._git(repo, ["config", "user.email", os.getenv("SOVEREIGN_MCP_GIT_AUTHOR_EMAIL", "sovereign-operator@users.noreply.github.com")])
        diff_check = self._git(repo, ["diff", "--check"])
        if not diff_check["ok"]:
            return {**diff_check, "status": "FAILED", "blocker": "git diff --check ist fehlgeschlagen"}

        add = self._git(repo, ["add", "--all"])
        if not add["ok"]:
            return {**add, "status": "FAILED", "blocker": "git add ist fehlgeschlagen"}
        staged = self._git(repo, ["diff", "--cached", "--quiet"])
        if staged["exit_code"] == 1:
            commit = self._git(repo, ["commit", "-m", message[:200]])
            if not commit["ok"]:
                return {**commit, "status": "FAILED", "blocker": "Commit ist fehlgeschlagen"}
        elif staged["exit_code"] not in {0, 1}:
            return {**staged, "status": "FAILED", "blocker": "Staging-Status konnte nicht gelesen werden"}

        askpass_dir = tempfile.mkdtemp(prefix="sovereign-broker-askpass-")
        try:
            script = Path(askpass_dir) / "askpass.sh"
            script.write_text(
                "#!/bin/sh\ncase \"$1\" in *Username*) echo x-access-token ;; *Password*) printf '%s' \"$GITHUB_TOKEN\" ;; esac\n",
                "utf-8",
            )
            script.chmod(0o700)
            env = os.environ.copy()
            env.update({"GIT_ASKPASS": str(script), "GIT_TERMINAL_PROMPT": "0", "GITHUB_TOKEN": token})
            push = self._git(repo, ["push", "origin", "HEAD:refs/heads/main"], env=env, timeout=600)
        finally:
            shutil.rmtree(askpass_dir, ignore_errors=True)
        if not push["ok"]:
            return {**push, "status": "FAILED", "blocker": "Direkter Main-Push ist fehlgeschlagen"}
        head = self._git(repo, ["rev-parse", "HEAD"])
        return {
            "ok": True,
            "status": "PUSHED_MAIN",
            "workspace_id": workspace,
            "commit_sha": head["stdout"].strip(),
            "push_stdout": push["stdout"],
        }

    def _schema_migration_columns(self, *, host: str, port: str, database: str, user: str, password: str) -> set[str]:
        query = (
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name='schema_migrations' "
            "ORDER BY ordinal_position;\n"
        )
        result = self.operations._run_input(
            self.operations._psql_argv(host, port, database, user),
            query,
            password=password,
            timeout=30,
        )
        if not result["ok"]:
            raise RuntimeError(result["stderr"] or "schema_migrations konnte nicht geprüft werden")
        return {line.strip() for line in result["stdout"].splitlines() if line.strip() and line.strip() != "column_name" and not line.startswith("-") and not line.startswith("(")}

    def apply_verified_migration_with_self_heal(
        self,
        *,
        workspace_id: str,
        path: str,
        confirmation_sha256: str,
    ) -> dict[str, Any]:
        first = self.operations.apply_verified_migration(
            workspace_id=workspace_id,
            path=path,
            confirmation_sha256=confirmation_sha256,
        )
        if first.get("ok") or not SCHEMA_LEDGER_ERROR.search(str(first.get("error") or first.get("blocker") or "")):
            return first

        migration = self.operations._migration(workspace_id, path)
        if migration["sha256"] != confirmation_sha256:
            return {"ok": False, "status": "BLOCKED", "blocker": "Bestätigungs-Hash stimmt nicht", "sha256": migration["sha256"]}

        host, port, database, user, password = self._admin_connection()
        columns = self._schema_migration_columns(host=host, port=port, database=database, user=user, password=password)
        adaptation = _adapt_schema_ledger(migration["sql"], columns)
        if adaptation["repair"]["status"] != "APPLIED":
            return {
                **first,
                "schema_repair": adaptation["repair"],
                "blocker": "Schema-Drift erkannt, aber keine eindeutige kompatible Ledger-Anpassung möglich",
            }

        normalized = REPAIR_ENGINE.normalize_migration_preview(str(adaptation["sql"]))
        live_preview_sql = (
            "BEGIN;\n"
            "SET LOCAL statement_timeout = '120s';\n"
            "SET LOCAL lock_timeout = '5s';\n"
            f"{normalized['sql']}\n"
            "ROLLBACK;\n"
        )
        live_preview = self.operations._run_input(
            self.operations._psql_argv(host, port, database, user),
            live_preview_sql,
            password=password,
            timeout=180,
        )
        if not live_preview["ok"]:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Automatische Schema-Reparatur bestand die Produktionsstruktur-Preview nicht",
                "sha256": migration["sha256"],
                "schema_repair": adaptation["repair"],
                "preview": live_preview,
            }

        applied = self.operations._run_input(
            self.operations._psql_argv(host, port, database, user),
            str(adaptation["sql"]),
            password=password,
            timeout=240,
        )
        return {
            "ok": applied["ok"],
            "status": "APPLIED_AFTER_REPAIR" if applied["ok"] else "FAILED",
            "sha256": migration["sha256"],
            "schema_repair": {**adaptation["repair"], "attempts": 2},
            "production_structure_preview": {"ok": live_preview["ok"], "rolled_back": True},
            "production_database": database,
            "stdout": applied["stdout"],
            "error": applied["stderr"] if not applied["ok"] else "",
        }
