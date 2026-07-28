from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable

FILEBROWSER_CONTAINER = "file-browser-cunr-filebrowser-1"
FILEBROWSER_IMAGE_PREFIX = "filebrowser/filebrowser:"
POSTGRES_CONTAINER = "supabase-db"
POSTGRES_DATABASE = "postgres"
POSTGRES_USER = "postgres"
POSTGRES_RESTORE_USER = "supabase_admin"
DEFAULT_MAINTENANCE_ROOT = "/opt/sovereign-chatgpt-tools/maintenance"
MIN_BACKUP_AVAILABLE_BYTES = 1_073_741_824
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_VAULT_RESTORE_COMPATIBILITY = (
    (
        "FUNCTION vault.secrets_encrypt_secret_secret()",
        re.compile(
            r"^\d+;\s+\d+\s+\d+\s+FUNCTION\s+vault\s+"
            r"secrets_encrypt_secret_secret\(\)(?:\s+\S+)?$"
        ),
    ),
    (
        "TRIGGER vault.secrets_encrypt_secret_trigger_secret",
        re.compile(
            r"^\d+;\s+\d+\s+\d+\s+"
            r"(?:(?:CONSTRAINT\s+)?TRIGGER(?:\s+CONSTRAINT)?)\s+\S+\s+"
            r"(?:\S+\s+)*secrets_encrypt_secret_trigger_secret(?:\s+\S+)*$"
        ),
    ),
    (
        "VIEW vault.decrypted_secrets",
        re.compile(
            r"^\d+;\s+\d+\s+\d+\s+(?:TABLE|VIEW)\s+vault\s+"
            r"decrypted_secrets(?:\s+\S+)?$"
        ),
    ),
)
_VAULT_OPTIONAL_RESTORE_COMPATIBILITY = frozenset(
    {"TRIGGER vault.secrets_encrypt_secret_trigger_secret"}
)
_SUCCESSFUL_PATCH_STATES = frozenset({"completed", "complete", "success", "succeeded"})
_PREPATCH_STATES = frozenset({"pending_approval"})


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bounded(value: Any, limit: int = 200) -> str:
    return str(value or "").strip()[: max(1, int(limit))]


def _quote_identifier(value: str) -> str:
    if not value or any(ord(char) < 32 for char in value):
        raise ValueError("database identifier contains control characters")
    return '"' + value.replace('"', '""') + '"'


def _compatible_restore_toc(value: Any) -> tuple[str, list[str]]:
    """Omit the exact Vault objects recreated by the archived extension step."""
    if isinstance(value, bytes):
        listing = value.decode("utf-8", errors="strict")
    else:
        listing = str(value or "")
    if not listing.strip():
        raise RuntimeError("pg_restore archive list is empty")
    counts = {label: 0 for label, _pattern in _VAULT_RESTORE_COMPATIBILITY}
    filtered: list[str] = []
    for line in listing.splitlines():
        matches = [
            label
            for label, pattern in _VAULT_RESTORE_COMPATIBILITY
            if pattern.fullmatch(line)
        ]
        if len(matches) > 1:
            raise RuntimeError("pg_restore Vault compatibility patterns overlap")
        if matches:
            counts[matches[0]] += 1
            filtered.append(";" + line)
        else:
            filtered.append(line)
    trigger_candidates: list[str] = []
    for line in listing.splitlines():
        if "secrets_encrypt_secret_trigger_secret" not in line:
            continue
        tokens = line.split()
        if tokens:
            tokens[-1] = "<owner>"
        trigger_candidates.append(_bounded(" ".join(tokens), 300))
        if len(trigger_candidates) >= 5:
            break
    required_invalid = any(
        count != 1
        for label, count in counts.items()
        if label not in _VAULT_OPTIONAL_RESTORE_COMPATIBILITY
    )
    optional_invalid = any(
        count > 1
        or (count == 0 and bool(trigger_candidates))
        for label, count in counts.items()
        if label in _VAULT_OPTIONAL_RESTORE_COMPATIBILITY
    )
    if required_invalid or optional_invalid:
        raise RuntimeError(
            "pg_restore Vault compatibility inventory drifted: "
            + json.dumps(counts, sort_keys=True, separators=(",", ":"))
            + "; triggerCandidates="
            + json.dumps(trigger_candidates, sort_keys=True, separators=(",", ":"))
        )
    omissions = [label for label, count in counts.items() if count == 1]
    return "\n".join(filtered) + "\n", omissions


class FleetMaintenanceRuntime:
    """Fixed, state-bound host maintenance actions; no arbitrary target or command is accepted."""

    def __init__(
        self,
        patch_run_reader: Callable[[str], dict[str, Any]] | None = None,
        maintenance_root: str | None = None,
    ) -> None:
        self.patch_run_reader = patch_run_reader
        self.maintenance_root = Path(
            maintenance_root
            or os.getenv("SOVEREIGN_MCP_MAINTENANCE_ROOT", DEFAULT_MAINTENANCE_ROOT)
        )

    @staticmethod
    def _run_text(argv: list[str], timeout: int = 120) -> dict[str, Any]:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={
                **os.environ,
                "LC_ALL": "C",
                "LANG": "C",
                "PATH": os.environ.get(
                    "PATH",
                    "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                ),
            },
        )
        return {
            "ok": completed.returncode == 0,
            "exit_code": int(completed.returncode),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    @staticmethod
    def _run_file_input(argv: list[str], path: Path, timeout: int = 1200) -> dict[str, Any]:
        with path.open("rb") as handle:
            completed = subprocess.run(
                argv,
                stdin=handle,
                capture_output=True,
                timeout=timeout,
                check=False,
                env={
                    **os.environ,
                    "LC_ALL": "C",
                    "LANG": "C",
                    "PATH": os.environ.get(
                        "PATH",
                        "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                    ),
                },
            )
        return {
            "ok": completed.returncode == 0,
            "exit_code": int(completed.returncode),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    @staticmethod
    def _feature_enabled() -> bool:
        return (
            os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() == "1"
            and os.getenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "0").strip() == "1"
        )

    @staticmethod
    def _failure(status: str, family: str, blocker: str, **extra: Any) -> dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "failureFamily": family,
            "blocker": blocker,
            "mutationPerformed": False,
            "secretValuesReturned": False,
            **extra,
        }

    def _docker_inspect(self, container: str) -> dict[str, Any] | None:
        result = self._run_text(["docker", "inspect", container], timeout=30)
        if not result.get("ok"):
            return None
        try:
            payload = json.loads(str(result.get("stdout") or ""))
        except json.JSONDecodeError as exc:
            raise RuntimeError("Docker inspect returned invalid JSON") from exc
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            raise RuntimeError("Docker inspect did not return exactly one object")
        return payload[0]

    @staticmethod
    def _container_summary(inspect: dict[str, Any]) -> dict[str, Any]:
        config = inspect.get("Config") if isinstance(inspect.get("Config"), dict) else {}
        state = inspect.get("State") if isinstance(inspect.get("State"), dict) else {}
        health = state.get("Health") if isinstance(state.get("Health"), dict) else {}
        labels = config.get("Labels") if isinstance(config.get("Labels"), dict) else {}
        mounts = inspect.get("Mounts") if isinstance(inspect.get("Mounts"), list) else []
        networks_raw = (
            inspect.get("NetworkSettings", {}).get("Networks", {})
            if isinstance(inspect.get("NetworkSettings"), dict)
            else {}
        )
        ports_raw = (
            inspect.get("NetworkSettings", {}).get("Ports", {})
            if isinstance(inspect.get("NetworkSettings"), dict)
            else {}
        )
        normalized_mounts: list[dict[str, Any]] = []
        for raw in mounts:
            item = raw if isinstance(raw, dict) else {}
            mount_type = _bounded(item.get("Type"), 20)
            normalized_mounts.append(
                {
                    "type": mount_type,
                    "name": _bounded(item.get("Name"), 160) if mount_type == "volume" else "",
                    "sourceFingerprint": (
                        hashlib.sha256(_bounded(item.get("Source"), 1000).encode("utf-8")).hexdigest()
                        if mount_type == "bind" and item.get("Source")
                        else ""
                    ),
                    "destination": _bounded(item.get("Destination"), 240),
                    "readWrite": bool(item.get("RW")),
                }
            )
        normalized_mounts.sort(key=lambda row: (row["destination"], row["type"], row["name"]))
        normalized_ports: list[dict[str, Any]] = []
        if isinstance(ports_raw, dict):
            for container_port, bindings in ports_raw.items():
                for binding in bindings if isinstance(bindings, list) else []:
                    item = binding if isinstance(binding, dict) else {}
                    normalized_ports.append(
                        {
                            "containerPort": _bounded(container_port, 40),
                            "hostIp": _bounded(item.get("HostIp"), 80),
                            "hostPort": _bounded(item.get("HostPort"), 20),
                        }
                    )
        normalized_ports.sort(key=lambda row: (row["hostPort"], row["hostIp"], row["containerPort"]))
        return {
            "containerId": _bounded(inspect.get("Id"), 80),
            "name": _bounded(inspect.get("Name"), 180).lstrip("/"),
            "image": _bounded(config.get("Image"), 300),
            "imageId": _bounded(inspect.get("Image"), 100),
            "status": _bounded(state.get("Status"), 40),
            "running": bool(state.get("Running")),
            "health": _bounded(health.get("Status"), 40) or None,
            "composeProject": _bounded(labels.get("com.docker.compose.project"), 160) or None,
            "composeService": _bounded(labels.get("com.docker.compose.service"), 160) or None,
            "networks": sorted(_bounded(name, 160) for name in networks_raw) if isinstance(networks_raw, dict) else [],
            "ports": normalized_ports,
            "mounts": normalized_mounts,
        }

    def filebrowser_retirement_plan(self) -> dict[str, Any]:
        try:
            inspect = self._docker_inspect(FILEBROWSER_CONTAINER)
        except RuntimeError as exc:
            return self._failure(
                "FILEBROWSER_RETIREMENT_PLAN_BLOCKED",
                "DOCKER_STATE_INVALID",
                str(exc),
            )
        if inspect is None:
            return {
                "ok": True,
                "status": "FILEBROWSER_ALREADY_RETIRED",
                "target": FILEBROWSER_CONTAINER,
                "confirmationRequired": False,
                "preserveImages": True,
                "preserveVolumes": True,
                "mutationPerformed": False,
                "secretValuesReturned": False,
            }
        summary = self._container_summary(inspect)
        if summary.get("name") != FILEBROWSER_CONTAINER or not str(summary.get("image") or "").startswith(FILEBROWSER_IMAGE_PREFIX):
            return self._failure(
                "FILEBROWSER_RETIREMENT_PLAN_BLOCKED",
                "TARGET_IDENTITY_MISMATCH",
                "The fixed Filebrowser container name now resolves to a different image identity.",
                observed={"name": summary.get("name"), "image": summary.get("image")},
            )
        named_volumes = sorted(
            str(item.get("name"))
            for item in summary.get("mounts", [])
            if item.get("type") == "volume" and item.get("name")
        )
        state = {
            "schemaVersion": "sovereign.filebrowser-retirement.v1",
            "action": "remove_exact_container_preserve_image_and_volumes",
            "target": FILEBROWSER_CONTAINER,
            "container": summary,
            "preservedNamedVolumes": named_volumes,
        }
        return {
            "ok": True,
            "status": "FILEBROWSER_RETIREMENT_PLAN_READY",
            "target": FILEBROWSER_CONTAINER,
            "reason": "owner_confirmed_private_app_not_required_by_sovereign",
            "container": summary,
            "preservedNamedVolumes": named_volumes,
            "preserveImages": True,
            "preserveVolumes": True,
            "confirmationRequired": True,
            "confirmationSha256": _canonical_sha256(state),
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    def filebrowser_retirement_apply(
        self,
        *,
        confirmation_sha256: str,
        owner_approved: bool,
    ) -> dict[str, Any]:
        if not owner_approved:
            return self._failure(
                "FILEBROWSER_RETIREMENT_BLOCKED",
                "OWNER_APPROVAL_REQUIRED",
                "owner_approved=true is required for the exact container retirement.",
            )
        if not self._feature_enabled():
            return self._failure(
                "FILEBROWSER_RETIREMENT_BLOCKED",
                "FLEET_MAINTENANCE_WRITE_DISABLED",
                "PatchMon/fleet write capability is disabled on the host worker.",
            )
        plan = self.filebrowser_retirement_plan()
        if plan.get("status") == "FILEBROWSER_ALREADY_RETIRED":
            return {**plan, "readbackVerified": True}
        if not plan.get("ok"):
            return plan
        expected = str(plan.get("confirmationSha256") or "")
        supplied = str(confirmation_sha256 or "").strip().lower()
        if not _SHA256_RE.fullmatch(supplied) or supplied != expected:
            return self._failure(
                "FILEBROWSER_RETIREMENT_BLOCKED",
                "CONFIRMATION_MISMATCH",
                "The confirmation hash no longer matches the exact live container state.",
                expectedConfirmationSha256=expected,
            )
        preserved = list(plan.get("preservedNamedVolumes") or [])
        removal = self._run_text(["docker", "rm", "--force", FILEBROWSER_CONTAINER], timeout=120)
        if not removal.get("ok"):
            return self._failure(
                "FILEBROWSER_RETIREMENT_FAILED",
                "DOCKER_REMOVE_FAILED",
                "Docker did not remove the exact Filebrowser container.",
            )
        absent = self._docker_inspect(FILEBROWSER_CONTAINER) is None
        volume_checks = []
        for volume in preserved:
            checked = self._run_text(["docker", "volume", "inspect", volume], timeout=30)
            volume_checks.append({"name": volume, "preserved": bool(checked.get("ok"))})
        fleet = self._run_text(["docker", "ps", "--format", "{{json .}}"], timeout=30)
        published_32832 = False
        if fleet.get("ok"):
            for line in str(fleet.get("stdout") or "").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "32832->" in str(row.get("Ports") or ""):
                    published_32832 = True
                    break
        volumes_preserved = all(item["preserved"] for item in volume_checks)
        verified = absent and volumes_preserved and not published_32832
        return {
            "ok": verified,
            "status": "FILEBROWSER_RETIRED_VERIFIED" if verified else "FILEBROWSER_RETIREMENT_INCOMPLETE",
            "target": FILEBROWSER_CONTAINER,
            "containerAbsent": absent,
            "publishedPort32832Absent": not published_32832,
            "preservedVolumes": volume_checks,
            "imageRemoved": False,
            "readbackVerified": verified,
            "mutationPerformed": True,
            "secretValuesReturned": False,
        }

    def _patch_run_state(self, run_id: str) -> dict[str, Any] | None:
        normalized = str(run_id or "").strip().lower()
        if not _UUID_RE.fullmatch(normalized) or self.patch_run_reader is None:
            return None
        payload = self.patch_run_reader(normalized)
        candidates: list[Any] = []
        if isinstance(payload, dict):
            for container in (payload, payload.get("data"), payload.get("databaseSummary")):
                if not isinstance(container, dict):
                    continue
                for key in ("rows", "patchRuns", "runs"):
                    value = container.get(key)
                    if isinstance(value, list):
                        candidates.extend(value)
        for raw in candidates:
            row = raw if isinstance(raw, dict) else {}
            observed_id = _bounded(row.get("id") or row.get("run_id") or row.get("runId"), 80).lower()
            if observed_id == normalized:
                return {
                    "runId": normalized,
                    "status": _bounded(row.get("status"), 80).lower(),
                    "hostId": _bounded(row.get("host_id") or row.get("hostId"), 80).lower(),
                    "patchType": _bounded(row.get("patch_type") or row.get("patchType"), 80).lower(),
                    "updatedAt": _bounded(row.get("updated_at") or row.get("updatedAt"), 80),
                }
        return None

    def _postgres_container_state(self) -> dict[str, Any] | None:
        inspect = self._docker_inspect(POSTGRES_CONTAINER)
        if inspect is None:
            return None
        summary = self._container_summary(inspect)
        return {
            "containerId": summary.get("containerId"),
            "image": summary.get("image"),
            "imageId": summary.get("imageId"),
            "running": summary.get("running"),
            "health": summary.get("health"),
        }

    def _boot_id(self) -> str:
        try:
            value = Path("/proc/sys/kernel/random/boot_id").read_text("utf-8").strip().lower()
        except OSError:
            return ""
        return value if _UUID_RE.fullmatch(value) else ""

    def postgres_backup_restore_plan(self, *, patch_run_id: str) -> dict[str, Any]:
        run_id = str(patch_run_id or "").strip().lower()
        if not _UUID_RE.fullmatch(run_id):
            return self._failure(
                "POSTGRES_BACKUP_RESTORE_PLAN_BLOCKED",
                "PATCH_RUN_ID_INVALID",
                "patch_run_id must be one exact UUID.",
            )
        patch_run = self._patch_run_state(run_id)
        if patch_run is None:
            return self._failure(
                "POSTGRES_BACKUP_RESTORE_PLAN_BLOCKED",
                "PATCH_RUN_NOT_FOUND",
                "The exact PatchMon run was not found in authoritative readback.",
            )
        if patch_run.get("status") not in _PREPATCH_STATES:
            return self._failure(
                "POSTGRES_BACKUP_RESTORE_PLAN_BLOCKED",
                "PATCH_RUN_NOT_WAITING_FOR_APPROVAL",
                "Backup/restore must be completed before approving the pending PatchMon run.",
                patchRun=patch_run,
            )
        postgres = self._postgres_container_state()
        if postgres is None or not postgres.get("running") or postgres.get("health") not in {None, "healthy"}:
            return self._failure(
                "POSTGRES_BACKUP_RESTORE_PLAN_BLOCKED",
                "POSTGRES_CONTAINER_NOT_HEALTHY",
                "The canonical PostgreSQL container is not running healthy.",
                postgres=postgres,
            )
        disk = self._run_text(["df", "--output=avail", "--block-size=1", str(self.maintenance_root.parent)], timeout=30)
        available = 0
        if disk.get("ok"):
            values = [line.strip() for line in str(disk.get("stdout") or "").splitlines() if line.strip().isdigit()]
            available = int(values[-1]) if values else 0
        if available < MIN_BACKUP_AVAILABLE_BYTES:
            return self._failure(
                "POSTGRES_BACKUP_RESTORE_PLAN_BLOCKED",
                "BACKUP_DISK_CAPACITY_INSUFFICIENT",
                "At least 1 GiB free space is required for the bounded backup/restore canary.",
                availableBytes=available,
                minimumAvailableBytes=MIN_BACKUP_AVAILABLE_BYTES,
            )
        state = {
            "schemaVersion": "sovereign.postgres-backup-restore.v1",
            "action": "backup_restore_isolated_then_preserve_backup",
            "patchRun": patch_run,
            "postgres": postgres,
            "bootId": self._boot_id(),
            "minimumAvailableBytes": MIN_BACKUP_AVAILABLE_BYTES,
        }
        return {
            "ok": True,
            "status": "POSTGRES_BACKUP_RESTORE_PLAN_READY",
            "patchRun": patch_run,
            "postgres": postgres,
            "bootId": state["bootId"],
            "availableBytes": available,
            "minimumAvailableBytes": MIN_BACKUP_AVAILABLE_BYTES,
            "isolatedRestoreRequired": True,
            "backupRetention": "preserve_until_post_reboot_verification",
            "confirmationSha256": _canonical_sha256(state),
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    def _psql(self, database: str, sql: str, timeout: int = 300) -> dict[str, Any]:
        return self._run_text(
            [
                "docker",
                "exec",
                POSTGRES_CONTAINER,
                "psql",
                "--no-psqlrc",
                "--tuples-only",
                "--no-align",
                "--set",
                "ON_ERROR_STOP=1",
                "--username",
                POSTGRES_USER,
                "--dbname",
                database,
                "--command",
                sql,
            ],
            timeout=timeout,
        )

    def _database_manifest(self, database: str) -> dict[str, Any]:
        schema_sql = """
SELECT n.nspname, c.relname, c.relkind, COALESCE(a.attnum, 0), COALESCE(a.attname, ''),
       COALESCE(pg_catalog.format_type(a.atttypid, a.atttypmod), ''), COALESCE(a.attnotnull, false)
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
ORDER BY n.nspname, c.relname, c.relkind, a.attnum;
""".strip()
        constraints_sql = """
SELECT n.nspname, c.relname, con.conname, con.contype, pg_catalog.pg_get_constraintdef(con.oid, true)
FROM pg_catalog.pg_constraint con
JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
ORDER BY n.nspname, c.relname, con.conname;
""".strip()
        tables_sql = """
SELECT n.nspname || E'\\t' || c.relname
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
  AND c.relkind IN ('r', 'p')
ORDER BY n.nspname, c.relname;
""".strip()
        schema = self._psql(database, schema_sql)
        constraints = self._psql(database, constraints_sql)
        tables = self._psql(database, tables_sql)
        if not schema.get("ok") or not constraints.get("ok") or not tables.get("ok"):
            raise RuntimeError("database metadata inventory failed")
        row_counts: list[tuple[str, str, int]] = []
        for line in str(tables.get("stdout") or "").splitlines():
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                raise RuntimeError("database table inventory is malformed")
            namespace, table = parts
            count = self._psql(
                database,
                f"SELECT count(*)::bigint FROM {_quote_identifier(namespace)}.{_quote_identifier(table)};",
                timeout=600,
            )
            if not count.get("ok"):
                raise RuntimeError("database row-count inventory failed")
            try:
                value = int(str(count.get("stdout") or "").strip())
            except ValueError as exc:
                raise RuntimeError("database row-count result is malformed") from exc
            row_counts.append((namespace, table, value))
        structural = {
            "schema": str(schema.get("stdout") or ""),
            "constraints": str(constraints.get("stdout") or ""),
        }
        rows = [[namespace, table, value] for namespace, table, value in row_counts]
        return {
            "schemaDigest": _canonical_sha256(structural),
            "rowCountDigest": _canonical_sha256(rows),
            "tableCount": len(rows),
            "totalRows": sum(item[2] for item in rows),
        }

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _vault_compatibility_digest(self, database: str) -> str:
        result = self._psql(
            database,
            """
SELECT jsonb_build_object(
    'function',
    pg_catalog.pg_get_functiondef(
        to_regprocedure('vault.secrets_encrypt_secret_secret()')
    ),
    'trigger',
    (
        SELECT pg_catalog.pg_get_triggerdef(t.oid, true)
        FROM pg_catalog.pg_trigger t
        JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'vault'
          AND c.relname = 'secrets'
          AND t.tgname = 'secrets_encrypt_secret_trigger_secret'
          AND NOT t.tgisinternal
    ),
    'view',
    pg_catalog.pg_get_viewdef(to_regclass('vault.decrypted_secrets'), true)
)::text;
""".strip(),
        )
        if not result.get("ok"):
            raise RuntimeError("Vault compatibility definition inventory failed")
        try:
            payload = json.loads(str(result.get("stdout") or "").strip())
        except json.JSONDecodeError as exc:
            raise RuntimeError("Vault compatibility definition inventory is invalid") from exc
        expected = {"function", "trigger", "view"}
        if (
            not isinstance(payload, dict)
            or set(payload) != expected
            or any(not isinstance(payload[key], str) or not payload[key].strip() for key in expected)
        ):
            raise RuntimeError("Vault compatibility definition inventory is incomplete")
        return _canonical_sha256(payload)

    def _drop_restore_database(self, database: str) -> bool:
        dropped = self._run_text(
            [
                "docker",
                "exec",
                POSTGRES_CONTAINER,
                "dropdb",
                "--if-exists",
                "--force",
                "--username",
                POSTGRES_USER,
                database,
            ],
            timeout=180,
        )
        if not dropped.get("ok"):
            return False
        checked = self._psql(
            POSTGRES_DATABASE,
            "SELECT count(*) FROM pg_catalog.pg_database WHERE datname = "
            + "'" + database.replace("'", "''") + "';",
        )
        return bool(checked.get("ok")) and str(checked.get("stdout") or "").strip() == "0"

    def postgres_backup_restore_apply(
        self,
        *,
        patch_run_id: str,
        confirmation_sha256: str,
        owner_approved: bool,
    ) -> dict[str, Any]:
        if not owner_approved:
            return self._failure(
                "POSTGRES_BACKUP_RESTORE_BLOCKED",
                "OWNER_APPROVAL_REQUIRED",
                "owner_approved=true is required for the pre-patch backup/restore.",
            )
        if not self._feature_enabled():
            return self._failure(
                "POSTGRES_BACKUP_RESTORE_BLOCKED",
                "FLEET_MAINTENANCE_WRITE_DISABLED",
                "PatchMon/fleet write capability is disabled on the host worker.",
            )
        plan = self.postgres_backup_restore_plan(patch_run_id=patch_run_id)
        if not plan.get("ok"):
            return plan
        expected = str(plan.get("confirmationSha256") or "")
        supplied = str(confirmation_sha256 or "").strip().lower()
        if not _SHA256_RE.fullmatch(supplied) or supplied != expected:
            return self._failure(
                "POSTGRES_BACKUP_RESTORE_BLOCKED",
                "CONFIRMATION_MISMATCH",
                "The confirmation hash no longer matches PostgreSQL, PatchMon, boot and disk safety state.",
                expectedConfirmationSha256=expected,
            )
        root = self.maintenance_root
        backups = root / "backups"
        receipts = root / "receipts"
        for directory in (root, backups, receipts):
            if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
                return self._failure(
                    "POSTGRES_BACKUP_RESTORE_BLOCKED",
                    "MAINTENANCE_PATH_INVALID",
                    "The root-only maintenance path must be a regular directory tree without symlinks.",
                )
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(directory, 0o700)
        backup_id = uuid.uuid4().hex
        host_temporary = backups / f".{backup_id}.dump.tmp"
        host_toc = backups / f".{backup_id}.toc.tmp"
        host_final = backups / f"sovereign-prepatch-{backup_id}.dump"
        container_temporary = f"/tmp/sovereign-prepatch-{backup_id}.dump"
        container_toc = f"/tmp/sovereign-prepatch-{backup_id}.toc"
        restore_database = f"sovereign_restore_{backup_id[:20]}"
        restore_created = False
        cleanup_verified = False
        restore_compatibility_omissions: list[str] = []
        restore_toc_digest = ""
        vault_compatibility_digest = ""
        try:
            source_before = self._database_manifest(POSTGRES_DATABASE)
            source_vault_before = self._vault_compatibility_digest(POSTGRES_DATABASE)
            dumped = self._run_text(
                [
                    "docker",
                    "exec",
                    POSTGRES_CONTAINER,
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--username",
                    POSTGRES_USER,
                    "--dbname",
                    POSTGRES_DATABASE,
                    "--file",
                    container_temporary,
                ],
                timeout=1200,
            )
            if not dumped.get("ok"):
                raise RuntimeError("pg_dump failed")
            copied = self._run_text(
                ["docker", "cp", f"{POSTGRES_CONTAINER}:{container_temporary}", str(host_temporary)],
                timeout=600,
            )
            if not copied.get("ok") or not host_temporary.is_file() or host_temporary.stat().st_size <= 0:
                raise RuntimeError("backup archive copy failed")
            os.chmod(host_temporary, 0o600)
            source_after = self._database_manifest(POSTGRES_DATABASE)
            source_vault_after = self._vault_compatibility_digest(POSTGRES_DATABASE)
            if source_before != source_after or source_vault_before != source_vault_after:
                raise RuntimeError("source database changed during backup evidence collection")
            vault_compatibility_digest = source_vault_after
            listed = self._run_text(
                ["docker", "exec", POSTGRES_CONTAINER, "pg_restore", "--list", container_temporary],
                timeout=300,
            )
            if not listed.get("ok") or not str(listed.get("stdout") or "").strip():
                detail = _bounded(listed.get("stderr"), 800)
                raise RuntimeError(f"pg_restore archive-list validation failed: {detail}")
            restore_toc, restore_compatibility_omissions = _compatible_restore_toc(
                listed.get("stdout")
            )
            restore_toc_digest = hashlib.sha256(restore_toc.encode("utf-8")).hexdigest()
            descriptor = os.open(
                host_toc,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(restore_toc)
                handle.flush()
                os.fsync(handle.fileno())
            copied_toc = self._run_text(
                ["docker", "cp", str(host_toc), f"{POSTGRES_CONTAINER}:{container_toc}"],
                timeout=120,
            )
            if not copied_toc.get("ok"):
                detail = _bounded(copied_toc.get("stderr"), 800)
                raise RuntimeError(f"restore compatibility list copy failed: {detail}")
            readable_toc = self._run_text(
                [
                    "docker",
                    "exec",
                    "--user",
                    "0",
                    POSTGRES_CONTAINER,
                    "chmod",
                    "0444",
                    container_toc,
                ],
                timeout=30,
            )
            if not readable_toc.get("ok"):
                detail = _bounded(readable_toc.get("stderr"), 800)
                raise RuntimeError(f"restore compatibility list permission failed: {detail}")
            created = self._run_text(
                [
                    "docker",
                    "exec",
                    POSTGRES_CONTAINER,
                    "createdb",
                    "--username",
                    POSTGRES_USER,
                    "--template",
                    "template0",
                    restore_database,
                ],
                timeout=180,
            )
            if not created.get("ok"):
                raise RuntimeError("isolated restore database creation failed")
            restore_created = True
            restored = self._run_text(
                [
                    "docker",
                    "exec",
                    POSTGRES_CONTAINER,
                    "sh",
                    "-c",
                    (
                        'PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}" '
                        'exec pg_restore "$@"'
                    ),
                    "pg_restore",
                    "--use-list",
                    container_toc,
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    "--username",
                    POSTGRES_RESTORE_USER,
                    "--dbname",
                    restore_database,
                    container_temporary,
                ],
                timeout=1200,
            )
            if not restored.get("ok"):
                detail = _bounded(restored.get("stderr"), 800)
                raise RuntimeError(
                    f"isolated pg_restore failed (exit={restored.get('exit_code')}): {detail}"
                )
            restored_manifest = self._database_manifest(restore_database)
            restored_vault_digest = self._vault_compatibility_digest(restore_database)
            if restored_manifest != source_after:
                raise RuntimeError("restored schema or table row counts differ from source evidence")
            if restored_vault_digest != vault_compatibility_digest:
                raise RuntimeError("restored Vault definitions differ from source evidence")
            cleanup_verified = self._drop_restore_database(restore_database)
            restore_created = False
            if not cleanup_verified:
                raise RuntimeError("isolated restore database cleanup could not be verified")
            archive_digest = self._file_sha256(host_temporary)
            archive_size = host_temporary.stat().st_size
            host_temporary.replace(host_final)
            receipt = {
                "schemaVersion": "sovereign.backup-restore-receipt.v1",
                "asset": "postgresql:supabase-db/postgres",
                "backupArtifact": host_final.name,
                "backupDigest": f"sha256:{archive_digest}",
                "restoredArchiveDigest": f"sha256:{archive_digest}",
                "archiveBytes": archive_size,
                "schemaDigest": source_after["schemaDigest"],
                "rowCountDigest": source_after["rowCountDigest"],
                "tableCount": source_after["tableCount"],
                "totalRows": source_after["totalRows"],
                "restoreStatus": "passed",
                "isolatedTarget": True,
                "isolatedTargetRemoved": True,
                "restoreTocDigest": f"sha256:{restore_toc_digest}",
                "restoreCompatibilityOmissions": restore_compatibility_omissions,
                "vaultCompatibilityDigest": f"sha256:{vault_compatibility_digest}",
                "patchRunId": str(patch_run_id).strip().lower(),
                "bootId": str(plan.get("bootId") or ""),
                "createdAtEpoch": int(time.time()),
            }
            receipt_sha = _canonical_sha256(receipt)
            receipt_path = receipts / f"{receipt_sha}.json"
            encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n"
            descriptor = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            return {
                "ok": True,
                "status": "POSTGRES_BACKUP_RESTORE_VERIFIED",
                "asset": receipt["asset"],
                "backupArtifact": receipt["backupArtifact"],
                "backupDigest": receipt["backupDigest"],
                "restoredArchiveDigest": receipt["restoredArchiveDigest"],
                "archiveBytes": archive_size,
                "schemaDigest": receipt["schemaDigest"],
                "rowCountDigest": receipt["rowCountDigest"],
                "tableCount": receipt["tableCount"],
                "totalRows": receipt["totalRows"],
                "restoreStatus": "passed",
                "isolatedTarget": True,
                "isolatedTargetRemoved": True,
                "restoreTocDigest": receipt["restoreTocDigest"],
                "restoreCompatibilityOmissions": receipt["restoreCompatibilityOmissions"],
                "vaultCompatibilityDigest": receipt["vaultCompatibilityDigest"],
                "backupReceiptSha256": receipt_sha,
                "patchRunId": receipt["patchRunId"],
                "readbackVerified": True,
                "mutationPerformed": True,
                "secretValuesReturned": False,
            }
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            return self._failure(
                "POSTGRES_BACKUP_RESTORE_FAILED",
                "BACKUP_RESTORE_EXECUTION_FAILED",
                _bounded(exc, 500),
            )
        finally:
            self._run_text(
                [
                    "docker",
                    "exec",
                    POSTGRES_CONTAINER,
                    "rm",
                    "-f",
                    container_temporary,
                    container_toc,
                ],
                timeout=30,
            )
            if restore_created:
                cleanup_verified = self._drop_restore_database(restore_database)
            if host_temporary.exists():
                host_temporary.unlink(missing_ok=True)
            if host_toc.exists():
                host_toc.unlink(missing_ok=True)

    def _read_backup_receipt(self, receipt_sha256: str) -> dict[str, Any] | None:
        value = str(receipt_sha256 or "").strip().lower()
        if not _SHA256_RE.fullmatch(value):
            return None
        path = self.maintenance_root / "receipts" / f"{value}.json"
        if self.maintenance_root.is_symlink() or path.parent.is_symlink():
            return None
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 32_000:
                return None
            payload = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or _canonical_sha256(payload) != value:
            return None
        artifact = self.maintenance_root / "backups" / str(payload.get("backupArtifact") or "")
        if artifact.parent != self.maintenance_root / "backups" or artifact.is_symlink() or not artifact.is_file():
            return None
        observed = f"sha256:{self._file_sha256(artifact)}"
        if observed != payload.get("backupDigest") or observed != payload.get("restoredArchiveDigest"):
            return None
        return payload

    def _pending_updates(self) -> dict[str, Any]:
        result = self._run_text(
            ["apt-get", "--simulate", "-o", "Debug::NoLocking=true", "dist-upgrade"],
            timeout=300,
        )
        if not result.get("ok"):
            return {"ok": False, "count": -1, "digest": None}
        packages: list[str] = []
        for line in str(result.get("stdout") or "").splitlines():
            if not line.startswith("Inst "):
                continue
            name = line.split(None, 2)[1].strip()
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+_.:-]{0,200}", name):
                packages.append(name)
        packages = sorted(set(packages))
        return {"ok": True, "count": len(packages), "digest": _canonical_sha256(packages)}

    def _critical_containers(self) -> dict[str, Any]:
        rows = []
        ready = True
        for name in ("sovereign-backend", "sovereign-chatgpt-mcp", POSTGRES_CONTAINER):
            inspect = self._docker_inspect(name)
            if inspect is None:
                rows.append({"name": name, "running": False, "health": None})
                ready = False
                continue
            summary = self._container_summary(inspect)
            healthy = bool(summary.get("running")) and summary.get("health") in {None, "healthy"}
            rows.append({"name": name, "running": bool(summary.get("running")), "health": summary.get("health")})
            ready = ready and healthy
        return {"ready": ready, "containers": rows, "digest": _canonical_sha256(rows)}

    def host_reboot_plan(self, *, patch_run_id: str, backup_receipt_sha256: str) -> dict[str, Any]:
        run_id = str(patch_run_id or "").strip().lower()
        patch_run = self._patch_run_state(run_id)
        if patch_run is None:
            return self._failure(
                "HOST_REBOOT_PLAN_BLOCKED",
                "PATCH_RUN_NOT_FOUND",
                "The exact PatchMon run was not found in authoritative readback.",
            )
        if patch_run.get("status") not in _SUCCESSFUL_PATCH_STATES:
            return self._failure(
                "HOST_REBOOT_PLAN_BLOCKED",
                "PATCH_RUN_NOT_SUCCESSFUL",
                "The exact PatchMon run is not in a successful terminal state.",
                patchRun=patch_run,
            )
        receipt = self._read_backup_receipt(backup_receipt_sha256)
        if receipt is None or receipt.get("patchRunId") != run_id:
            return self._failure(
                "HOST_REBOOT_PLAN_BLOCKED",
                "BACKUP_RECEIPT_INVALID",
                "The retained backup/restore receipt is absent, corrupt or bound to another PatchMon run.",
            )
        updates = self._pending_updates()
        if not updates.get("ok") or int(updates.get("count") or 0) != 0:
            return self._failure(
                "HOST_REBOOT_PLAN_BLOCKED",
                "PENDING_UPDATES_REMAIN",
                "Host reboot is blocked until package simulation reports zero pending upgrades.",
                pendingUpdates=updates,
            )
        critical = self._critical_containers()
        if not critical.get("ready"):
            return self._failure(
                "HOST_REBOOT_PLAN_BLOCKED",
                "CRITICAL_RUNTIME_NOT_READY",
                "Critical runtime containers must be running healthy before reboot scheduling.",
                criticalRuntime=critical,
            )
        current_boot = self._boot_id()
        previous_boot = str(receipt.get("bootId") or "")
        reboot_required = Path("/var/run/reboot-required").is_file()
        if previous_boot and current_boot != previous_boot and not reboot_required:
            return {
                "ok": True,
                "status": "HOST_REBOOT_ALREADY_VERIFIED_BY_BOOT_CHANGE",
                "patchRun": patch_run,
                "backupReceiptSha256": str(backup_receipt_sha256).lower(),
                "previousBootId": previous_boot,
                "currentBootId": current_boot,
                "pendingUpdates": updates,
                "criticalRuntime": critical,
                "confirmationRequired": False,
                "mutationPerformed": False,
                "secretValuesReturned": False,
            }
        if not reboot_required:
            return self._failure(
                "HOST_REBOOT_PLAN_BLOCKED",
                "REBOOT_NOT_REQUIRED_AND_BOOT_UNCHANGED",
                "The reboot-required marker is absent but the boot ID has not changed since the backup receipt.",
            )
        state = {
            "schemaVersion": "sovereign.host-reboot.v1",
            "action": "schedule_single_systemd_reboot",
            "patchRun": patch_run,
            "backupReceiptSha256": str(backup_receipt_sha256).lower(),
            "currentBootId": current_boot,
            "pendingUpdates": updates,
            "criticalRuntimeDigest": critical["digest"],
            "rebootRequired": True,
        }
        return {
            "ok": True,
            "status": "HOST_REBOOT_PLAN_READY",
            "patchRun": patch_run,
            "backupReceiptSha256": state["backupReceiptSha256"],
            "previousBootId": current_boot,
            "pendingUpdates": updates,
            "criticalRuntime": critical,
            "rebootRequired": True,
            "confirmationRequired": True,
            "confirmationSha256": _canonical_sha256(state),
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    def host_reboot_apply(
        self,
        *,
        patch_run_id: str,
        backup_receipt_sha256: str,
        confirmation_sha256: str,
        owner_approved: bool,
    ) -> dict[str, Any]:
        if not owner_approved:
            return self._failure(
                "HOST_REBOOT_BLOCKED",
                "OWNER_APPROVAL_REQUIRED",
                "owner_approved=true is required for the scheduled host reboot.",
            )
        if not self._feature_enabled():
            return self._failure(
                "HOST_REBOOT_BLOCKED",
                "FLEET_MAINTENANCE_WRITE_DISABLED",
                "PatchMon/fleet write capability is disabled on the host worker.",
            )
        plan = self.host_reboot_plan(
            patch_run_id=patch_run_id,
            backup_receipt_sha256=backup_receipt_sha256,
        )
        if plan.get("status") == "HOST_REBOOT_ALREADY_VERIFIED_BY_BOOT_CHANGE":
            return {**plan, "readbackVerified": True}
        if not plan.get("ok"):
            return plan
        supplied = str(confirmation_sha256 or "").strip().lower()
        expected = str(plan.get("confirmationSha256") or "")
        if not _SHA256_RE.fullmatch(supplied) or supplied != expected:
            return self._failure(
                "HOST_REBOOT_BLOCKED",
                "CONFIRMATION_MISMATCH",
                "The confirmation hash no longer matches the patch, backup, boot and runtime state.",
                expectedConfirmationSha256=expected,
            )
        previous_boot = str(plan.get("previousBootId") or "")
        unit = f"sovereign-maintenance-reboot-{previous_boot.replace('-', '')[:12]}"
        scheduled = self._run_text(
            [
                "systemd-run",
                f"--unit={unit}",
                "--on-active=15s",
                "--property=Type=oneshot",
                "/usr/bin/systemctl",
                "reboot",
            ],
            timeout=60,
        )
        if not scheduled.get("ok"):
            return self._failure(
                "HOST_REBOOT_SCHEDULING_FAILED",
                "SYSTEMD_REBOOT_SCHEDULE_FAILED",
                "systemd did not accept the bounded delayed reboot unit.",
            )
        return {
            "ok": True,
            "status": "HOST_REBOOT_SCHEDULED",
            "unit": unit,
            "delaySeconds": 15,
            "previousBootId": previous_boot,
            "patchRunId": str(patch_run_id).lower(),
            "backupReceiptSha256": str(backup_receipt_sha256).lower(),
            "readbackRequired": True,
            "mutationPerformed": True,
            "secretValuesReturned": False,
        }

    def host_post_reboot_verify(
        self,
        *,
        expected_previous_boot_id: str,
        patch_run_id: str,
        backup_receipt_sha256: str,
    ) -> dict[str, Any]:
        previous = str(expected_previous_boot_id or "").strip().lower()
        current = self._boot_id()
        receipt = self._read_backup_receipt(backup_receipt_sha256)
        patch_run = self._patch_run_state(str(patch_run_id or "").strip().lower())
        updates = self._pending_updates()
        critical = self._critical_containers()
        reboot_marker_absent = not Path("/var/run/reboot-required").is_file()
        verified = bool(
            _UUID_RE.fullmatch(previous)
            and current
            and current != previous
            and receipt is not None
            and receipt.get("patchRunId") == str(patch_run_id or "").strip().lower()
            and patch_run is not None
            and patch_run.get("status") in _SUCCESSFUL_PATCH_STATES
            and updates.get("ok")
            and int(updates.get("count") or 0) == 0
            and critical.get("ready")
            and reboot_marker_absent
        )
        return {
            "ok": verified,
            "status": "HOST_POST_REBOOT_VERIFIED" if verified else "HOST_POST_REBOOT_INCOMPLETE",
            "previousBootId": previous,
            "currentBootId": current,
            "bootChanged": bool(current and current != previous),
            "patchRun": patch_run,
            "backupReceiptValid": receipt is not None,
            "pendingUpdates": updates,
            "rebootRequiredMarkerAbsent": reboot_marker_absent,
            "criticalRuntime": critical,
            "readbackVerified": verified,
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }
