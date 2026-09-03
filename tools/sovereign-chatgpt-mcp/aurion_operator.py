from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from typing import Any, Callable


AURION_APP_CONTAINER = "echoes-of-aurion-aurion-1"
AURION_COMPOSE_PROJECT = "echoes-of-aurion"
AURION_COMPOSE_SERVICE = "aurion"
AURION_IMAGE_RE = re.compile(r"^(?:[A-Za-z0-9._/-]+/)?echoes-of-aurion:([0-9a-f]{40})$")
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LOCAL_OPEN_ID_RE = re.compile(r"^local:[A-Za-z0-9_.-]{1,32}$")
ALLOWED_ROLES = frozenset({"user", "admin"})
MAX_OUTPUT_BYTES = 256_000


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


_READ_ACCOUNT_SCRIPT = r'''
const mysql = require("mysql2/promise");
(async () => {
  const openId = process.argv[1];
  if (!process.env.DATABASE_URL) throw new Error("DATABASE_URL_MISSING");
  const connection = await mysql.createConnection(process.env.DATABASE_URL);
  try {
    const [rows] = await connection.execute(
      "SELECT id, openId, role FROM users WHERE openId = ? LIMIT 2",
      [openId],
    );
    process.stdout.write(JSON.stringify({rows: rows.map(({id, openId, role}) => ({id, openId, role}))}));
  } finally {
    await connection.end();
  }
})().catch((error) => {
  process.stderr.write(String(error && error.message ? error.message : "AURION_DB_READ_FAILED"));
  process.exitCode = 1;
});
'''.strip()


_SET_ROLE_SCRIPT = r'''
const mysql = require("mysql2/promise");
(async () => {
  const openId = process.argv[1];
  const targetRole = process.argv[2];
  const expectedCurrentRole = process.argv[3];
  if (!process.env.DATABASE_URL) throw new Error("DATABASE_URL_MISSING");
  const connection = await mysql.createConnection(process.env.DATABASE_URL);
  let mutationPerformed = false;
  try {
    await connection.beginTransaction();
    const [rows] = await connection.execute(
      "SELECT id, openId, role FROM users WHERE openId = ? LIMIT 2 FOR UPDATE",
      [openId],
    );
    if (!Array.isArray(rows) || rows.length !== 1) throw new Error("ACCOUNT_CARDINALITY_MISMATCH");
    const before = {id: rows[0].id, openId: rows[0].openId, role: rows[0].role};
    if (before.role !== expectedCurrentRole) throw new Error("CURRENT_ROLE_MISMATCH");
    if (before.role !== targetRole) {
      const [updated] = await connection.execute(
        "UPDATE users SET role = ? WHERE id = ? AND openId = ? AND role = ?",
        [targetRole, before.id, openId, expectedCurrentRole],
      );
      if (!updated || updated.affectedRows !== 1) throw new Error("ROLE_UPDATE_CARDINALITY_MISMATCH");
      mutationPerformed = true;
    }
    const [readbackRows] = await connection.execute(
      "SELECT id, openId, role FROM users WHERE id = ? AND openId = ? LIMIT 2",
      [before.id, openId],
    );
    if (!Array.isArray(readbackRows) || readbackRows.length !== 1 || readbackRows[0].role !== targetRole) {
      throw new Error("ROLE_READBACK_MISMATCH");
    }
    await connection.commit();
    process.stdout.write(JSON.stringify({
      before,
      after: {id: readbackRows[0].id, openId: readbackRows[0].openId, role: readbackRows[0].role},
      mutationPerformed,
    }));
  } catch (error) {
    try { await connection.rollback(); } catch {}
    throw error;
  } finally {
    await connection.end();
  }
})().catch((error) => {
  process.stderr.write(String(error && error.message ? error.message : "AURION_DB_WRITE_FAILED"));
  process.exitCode = 1;
});
'''.strip()


class AurionOperatorRuntime:
    """Bounded Echoes-of-Aurion MariaDB owner operator; no generic SQL surface."""

    def __init__(self, *, runner: Callable[..., subprocess.CompletedProcess[str]] | None = None) -> None:
        self._runner = runner or subprocess.run

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

    def _run(self, argv: list[str], *, timeout: int = 60) -> dict[str, Any]:
        try:
            completed = self._runner(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env={
                    **os.environ,
                    "LC_ALL": "C",
                    "LANG": "C",
                    "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
                },
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "exitCode": None, "stdout": "", "stderr": type(exc).__name__}
        stdout = str(completed.stdout or "")
        stderr = str(completed.stderr or "")
        return {
            "ok": completed.returncode == 0,
            "exitCode": int(completed.returncode),
            "stdout": stdout[-MAX_OUTPUT_BYTES:],
            "stderr": stderr[-32_000:],
        }

    @staticmethod
    def _validate_revision(value: str) -> str:
        revision = str(value or "").strip().lower()
        if not COMMIT_SHA_RE.fullmatch(revision):
            raise ValueError("expected_revision must be a full lowercase Git SHA")
        return revision

    @staticmethod
    def _validate_open_id(value: str) -> str:
        open_id = str(value or "").strip()
        if not LOCAL_OPEN_ID_RE.fullmatch(open_id):
            raise ValueError("open_id must be one bounded local:<handle> Aurion identity")
        return open_id

    @staticmethod
    def _validate_role(value: str) -> str:
        role = str(value or "").strip().lower()
        if role not in ALLOWED_ROLES:
            raise ValueError("role must be exactly user or admin")
        return role

    def runtime_identity(self, expected_revision: str) -> dict[str, Any]:
        revision = self._validate_revision(expected_revision)
        inspected = self._run(["docker", "inspect", AURION_APP_CONTAINER], timeout=30)
        if not inspected.get("ok"):
            return self._failure(
                "AURION_RUNTIME_BLOCKED",
                "AURION_CONTAINER_UNAVAILABLE",
                "The fixed Echoes of Aurion application container is unavailable",
                stderrSha256=_fingerprint(str(inspected.get("stderr") or "")),
            )
        try:
            rows = json.loads(str(inspected.get("stdout") or ""))
        except json.JSONDecodeError:
            return self._failure("AURION_RUNTIME_BLOCKED", "AURION_DOCKER_IDENTITY_INVALID", "Aurion Docker identity is invalid")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            return self._failure("AURION_RUNTIME_BLOCKED", "AURION_CONTAINER_CARDINALITY_MISMATCH", "Aurion must resolve to exactly one container")
        row = rows[0]
        config = row.get("Config") if isinstance(row.get("Config"), dict) else {}
        labels = config.get("Labels") if isinstance(config.get("Labels"), dict) else {}
        state = row.get("State") if isinstance(row.get("State"), dict) else {}
        health = state.get("Health") if isinstance(state.get("Health"), dict) else {}
        image = str(config.get("Image") or "")
        match = AURION_IMAGE_RE.fullmatch(image)
        observed_revision = match.group(1) if match else ""
        project = str(labels.get("com.docker.compose.project") or "")
        service = str(labels.get("com.docker.compose.service") or "")
        health_status = str(health.get("Status") or "")
        running = bool(state.get("Running"))
        verified = bool(
            observed_revision == revision
            and project == AURION_COMPOSE_PROJECT
            and service == AURION_COMPOSE_SERVICE
            and running
            and health_status == "healthy"
        )
        return {
            "ok": verified,
            "status": "AURION_RUNTIME_VERIFIED" if verified else "AURION_RUNTIME_MISMATCH",
            "failureFamily": None if verified else "AURION_RUNTIME_IDENTITY_MISMATCH",
            "expectedRevision": revision,
            "observedRevision": observed_revision or None,
            "container": AURION_APP_CONTAINER,
            "containerId": str(row.get("Id") or "")[:64],
            "image": image[:300],
            "imageId": str(row.get("Image") or "")[:100],
            "composeProject": project[:160],
            "composeService": service[:160],
            "running": running,
            "health": health_status or None,
            "revisionBound": observed_revision == revision,
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    def _exec_node_json(self, script: str, args: list[str], *, timeout: int) -> dict[str, Any]:
        executed = self._run(["docker", "exec", AURION_APP_CONTAINER, "node", "-e", script, "--", *args], timeout=timeout)
        if not executed.get("ok"):
            stderr = str(executed.get("stderr") or "")
            return self._failure(
                "AURION_DB_OPERATION_BLOCKED",
                "AURION_DB_EXECUTION_FAILED",
                "The fixed Aurion MariaDB helper failed inside the verified application container",
                exitCode=executed.get("exitCode"),
                stderrSha256=_fingerprint(stderr),
                stderrBytes=len(stderr.encode("utf-8")),
            )
        stdout = str(executed.get("stdout") or "")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return self._failure(
                "AURION_DB_OPERATION_BLOCKED",
                "AURION_DB_RESPONSE_INVALID",
                "The fixed Aurion MariaDB helper did not return valid JSON",
                stdoutSha256=_fingerprint(stdout),
            )
        if not isinstance(payload, dict):
            return self._failure("AURION_DB_OPERATION_BLOCKED", "AURION_DB_RESPONSE_INVALID", "Aurion MariaDB helper returned an unexpected payload")
        return {"ok": True, "payload": payload}

    def account_role_readback(self, *, open_id: str, expected_revision: str) -> dict[str, Any]:
        try:
            selected_open_id = self._validate_open_id(open_id)
        except ValueError as exc:
            return self._failure("AURION_ACCOUNT_READBACK_BLOCKED", "AURION_ACCOUNT_ID_INVALID", str(exc))
        identity = self.runtime_identity(expected_revision)
        if not identity.get("ok"):
            return identity
        executed = self._exec_node_json(_READ_ACCOUNT_SCRIPT, [selected_open_id], timeout=60)
        if not executed.get("ok"):
            return {**executed, "runtimeIdentity": identity}
        rows = executed.get("payload", {}).get("rows")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            return self._failure(
                "AURION_ACCOUNT_READBACK_BLOCKED",
                "AURION_ACCOUNT_CARDINALITY_MISMATCH",
                "Aurion local account must resolve to exactly one users row",
                rowCount=len(rows) if isinstance(rows, list) else None,
                runtimeIdentity=identity,
            )
        row = rows[0]
        role = str(row.get("role") or "")
        if row.get("openId") != selected_open_id or role not in ALLOWED_ROLES or not isinstance(row.get("id"), int):
            return self._failure(
                "AURION_ACCOUNT_READBACK_BLOCKED",
                "AURION_ACCOUNT_ROW_INVALID",
                "Aurion users row violated the bounded id/openId/role contract",
                runtimeIdentity=identity,
            )
        account = {"id": int(row["id"]), "openId": selected_open_id, "role": role}
        return {
            "ok": True,
            "status": "AURION_ACCOUNT_ROLE_READBACK_VERIFIED",
            "runtimeIdentity": identity,
            "account": account,
            "readbackSha256": _canonical_sha256(account),
            "readbackVerified": True,
            "localCredentialsRead": False,
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    def account_role_plan(self, *, open_id: str, role: str, expected_revision: str) -> dict[str, Any]:
        try:
            selected_role = self._validate_role(role)
        except ValueError as exc:
            return self._failure("AURION_ACCOUNT_ROLE_PLAN_BLOCKED", "AURION_ROLE_INVALID", str(exc))
        readback = self.account_role_readback(open_id=open_id, expected_revision=expected_revision)
        if not readback.get("ok"):
            return readback
        identity = dict(readback["runtimeIdentity"])
        account = dict(readback["account"])
        confirmation_state = {
            "schemaVersion": "sovereign.aurion-account-role.v1",
            "action": "set_local_account_role",
            "expectedRevision": identity["expectedRevision"],
            "containerId": identity["containerId"],
            "imageId": identity["imageId"],
            "account": account,
            "requestedRole": selected_role,
        }
        return {
            "ok": True,
            "status": "AURION_ACCOUNT_ROLE_PLAN_READY",
            "runtimeIdentity": identity,
            "account": account,
            "requestedRole": selected_role,
            "alreadySatisfied": account["role"] == selected_role,
            "confirmationSha256": _canonical_sha256(confirmation_state),
            "scope": ["users.id", "users.openId", "users.role"],
            "excluded": ["localCredentials", "passwordHash", "FusionAuth", "schema", "migrations", "other-users"],
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    @staticmethod
    def _write_enabled() -> bool:
        return (
            os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() == "1"
            and os.getenv("SOVEREIGN_MCP_ENABLE_AURION_WRITE", "0").strip() == "1"
        )

    def account_role_apply(
        self,
        *,
        open_id: str,
        role: str,
        expected_revision: str,
        confirmation_sha256: str,
        owner_approved: bool,
    ) -> dict[str, Any]:
        if not owner_approved:
            return self._failure("AURION_ACCOUNT_ROLE_APPLY_BLOCKED", "OWNER_APPROVAL_REQUIRED", "owner_approved=true is required")
        if not self._write_enabled():
            return self._failure("AURION_ACCOUNT_ROLE_APPLY_BLOCKED", "AURION_WRITE_DISABLED", "Bounded Aurion owner writes are disabled")
        plan = self.account_role_plan(open_id=open_id, role=role, expected_revision=expected_revision)
        if not plan.get("ok"):
            return plan
        supplied = str(confirmation_sha256 or "").strip().lower()
        expected_confirmation = str(plan.get("confirmationSha256") or "")
        if not SHA256_RE.fullmatch(supplied) or supplied != expected_confirmation:
            return self._failure(
                "AURION_ACCOUNT_ROLE_APPLY_BLOCKED",
                "CONFIRMATION_MISMATCH",
                "Aurion account/runtime state changed after planning",
                expectedConfirmationSha256=expected_confirmation,
            )
        account = dict(plan["account"])
        executed = self._exec_node_json(
            _SET_ROLE_SCRIPT,
            [str(account["openId"]), str(plan["requestedRole"]), str(account["role"])],
            timeout=90,
        )
        if not executed.get("ok"):
            return {**executed, "runtimeIdentity": plan["runtimeIdentity"]}
        payload = executed.get("payload") if isinstance(executed.get("payload"), dict) else {}
        before = payload.get("before") if isinstance(payload.get("before"), dict) else {}
        after = payload.get("after") if isinstance(payload.get("after"), dict) else {}
        helper_mutation = bool(payload.get("mutationPerformed"))
        post_identity = self.runtime_identity(expected_revision)
        final_readback = self.account_role_readback(open_id=open_id, expected_revision=expected_revision)
        identity_preserved = bool(
            post_identity.get("ok")
            and post_identity.get("containerId") == plan["runtimeIdentity"].get("containerId")
            and post_identity.get("imageId") == plan["runtimeIdentity"].get("imageId")
        )
        readback_ok = bool(
            final_readback.get("ok")
            and final_readback.get("account", {}).get("id") == account["id"]
            and final_readback.get("account", {}).get("openId") == account["openId"]
            and final_readback.get("account", {}).get("role") == plan["requestedRole"]
            and before.get("id") == account["id"]
            and before.get("openId") == account["openId"]
            and before.get("role") == account["role"]
            and after.get("id") == account["id"]
            and after.get("openId") == account["openId"]
            and after.get("role") == plan["requestedRole"]
            and identity_preserved
        )
        return {
            "ok": readback_ok,
            "status": "AURION_ACCOUNT_ROLE_APPLIED_VERIFIED" if readback_ok else "AURION_ACCOUNT_ROLE_APPLIED_UNVERIFIED",
            "failureFamily": None if readback_ok else "AURION_ACCOUNT_POST_WRITE_READBACK_FAILED",
            "runtimeIdentity": post_identity,
            "before": {"id": before.get("id"), "openId": before.get("openId"), "role": before.get("role")},
            "after": final_readback.get("account") if isinstance(final_readback.get("account"), dict) else None,
            "identityPreserved": identity_preserved,
            "readbackVerified": readback_ok,
            "localCredentialsRead": False,
            "mutationPerformed": helper_mutation,
            "secretValuesReturned": False,
        }
