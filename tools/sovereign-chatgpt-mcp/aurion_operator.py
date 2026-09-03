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
MAX_HTTP_BYTES = 256_000


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redact(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "[bounded]"
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in list(value.items())[:120]:
            rendered_key = str(key)[:120]
            lowered = rendered_key.lower()
            if any(marker in lowered for marker in ("secret", "token", "password", "authorization", "cookie", "api_key", "apikey")):
                output[rendered_key] = "[redacted]"
            else:
                output[rendered_key] = _redact(item, depth=depth + 1)
        return output
    if isinstance(value, list):
        return [_redact(item, depth=depth + 1) for item in value[:120]]
    if isinstance(value, str):
        return value[:12_000]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)[:2_000]


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
    process.stdout.write(JSON.stringify({ rows: rows.map(({ id, openId, role }) => ({ id, openId, role })) }));
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
    const before = { id: rows[0].id, openId: rows[0].openId, role: rows[0].role };
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
      after: { id: readbackRows[0].id, openId: readbackRows[0].openId, role: readbackRows[0].role },
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
    """Bounded Echoes-of-Aurion owner operator; never exposes generic SQL, shell or arbitrary HTTP."""

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self._runner = runner or subprocess.run

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
                    "PATH": os.environ.get(
                        "PATH",
                        "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                    ),
                },
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "ok": False,
                "exitCode": None,
                "stdout": "",
                "stderr": type(exc).__name__,
            }
        stdout = str(completed.stdout or "")
        stderr = str(completed.stderr or "")
        return {
            "ok": completed.returncode == 0,
            "exitCode": int(completed.returncode),
            "stdout": stdout[-MAX_HTTP_BYTES:],
            "stderr": stderr[-32_000:],
        }

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

    @staticmethod
    def _validate_revision(expected_revision: str) -> str:
        revision = str(expected_revision or "").strip().lower()
        if not COMMIT_SHA_RE.fullmatch(revision):
            raise ValueError("expected_revision must be a full lowercase Git SHA")
        return revision

    @staticmethod
    def _validate_open_id(open_id: str) -> str:
        value = str(open_id or "").strip()
        if not LOCAL_OPEN_ID_RE.fullmatch(value):
            raise ValueError("open_id must be one bounded local:<handle> Aurion identity")
        return value

    @staticmethod
    def _validate_role(role: str) -> str:
        selected = str(role or "").strip().lower()
        if selected not in ALLOWED_ROLES:
            raise ValueError("role must be exactly user or admin")
        return selected

    def _inspect_app(self) -> dict[str, Any]:
        result = self._run(["docker", "inspect", AURION_APP_CONTAINER], timeout=30)
        if not result.get("ok"):
            raise RuntimeError("Aurion application container is unavailable")
        try:
            rows = json.loads(str(result.get("stdout") or ""))
        except json.JSONDecodeError as exc:
            raise RuntimeError("Aurion Docker identity is invalid") from exc
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise RuntimeError("Aurion Docker identity did not resolve exactly one container")
        return rows[0]

    def runtime_identity(self, expected_revision: str) -> dict[str, Any]:
        revision = self._validate_revision(expected_revision)
        try:
            inspected = self._inspect_app()
        except RuntimeError as exc:
            return self._failure("AURION_RUNTIME_BLOCKED", "AURION_CONTAINER_UNAVAILABLE", str(exc))
        config = inspected.get("Config") if isinstance(inspected.get("Config"), dict) else {}
        labels = config.get("Labels") if isinstance(config.get("Labels"), dict) else {}
        state = inspected.get("State") if isinstance(inspected.get("State"), dict) else {}
        image = str(config.get("Image") or "")
        match = AURION_IMAGE_RE.fullmatch(image)
        observed_revision = match.group(1) if match else ""
        project = str(labels.get("com.docker.compose.project") or "")
        service = str(labels.get("com.docker.compose.service") or "")
        health = state.get("Health") if isinstance(state.get("Health"), dict) else {}
        health_status = str(health.get("Status") or "")
        running = bool(state.get("Running"))
        identity_ok = bool(
            observed_revision == revision
            and project == AURION_COMPOSE_PROJECT
            and service == AURION_COMPOSE_SERVICE
            and running
            and health_status == "healthy"
        )
        return {
            "ok": identity_ok,
            "status": "AURION_RUNTIME_VERIFIED" if identity_ok else "AURION_RUNTIME_MISMATCH",
            "failureFamily": None if identity_ok else "AURION_RUNTIME_IDENTITY_MISMATCH",
            "expectedRevision": revision,
            "observedRevision": observed_revision or None,
            "container": AURION_APP_CONTAINER,
            "containerId": str(inspected.get("Id") or "")[:64],
            "image": image[:300],
            "imageId": str(inspected.get("Image") or "")[:100],
            "composeProject": project[:160],
            "composeService": service[:160],
            "running": running,
            "health": health_status or None,
            "revisionBound": observed_revision == revision,
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    def _exec_node_json(self, script: str, args: list[str], *, timeout: int = 60) -> dict[str, Any]:
        result = self._run(
            ["docker", "exec", AURION_APP_CONTAINER, "node", "-e", script, "--", *args],
            timeout=timeout,
        )
        if not result.get("ok"):
            stderr = str(result.get("stderr") or "")
            return self._failure(
                "AURION_DB_OPERATION_BLOCKED",
                "AURION_DB_EXECUTION_FAILED",
                "The fixed Aurion database helper failed inside the revision-bound application container",
                exitCode=result.get("exitCode"),
                stderrSha256=_fingerprint(stderr),
                stderrBytes=len(stderr.encode("utf-8")),
            )
        stdout = str(result.get("stdout") or "")
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return self._failure(
                "AURION_DB_OPERATION_BLOCKED",
                "AURION_DB_RESPONSE_INVALID",
                "The fixed Aurion database helper did not return valid JSON",
                stdoutSha256=_fingerprint(stdout),
                stdoutBytes=len(stdout.encode("utf-8")),
            )
        if not isinstance(payload, dict):
            return self._failure(
                "AURION_DB_OPERATION_BLOCKED",
                "AURION_DB_RESPONSE_INVALID",
                "The fixed Aurion database helper returned an unexpected payload",
            )
        return {"ok": True, "status": "AURION_DB_RESPONSE_READY", "payload": payload}

    def account_role_readback(self, *, open_id: str, expected_revision: str) -> dict[str, Any]:
        identity = self.runtime_identity(expected_revision)
        if not identity.get("ok"):
            return identity
        try:
            selected_open_id = self._validate_open_id(open_id)
        except ValueError as exc:
            return self._failure("AURION_ACCOUNT_READBACK_BLOCKED", "AURION_ACCOUNT_ID_INVALID", str(exc))
        executed = self._exec_node_json(_READ_ACCOUNT_SCRIPT, [selected_open_id])
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
        state = {
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
            "confirmationSha256": _canonical_sha256(state),
            "scope": ["users.id", "users.openId", "users.role"],
            "excluded": ["localCredentials", "passwordHash", "FusionAuth", "schema", "migrations", "other-users"],
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    @staticmethod
    def _account_write_enabled() -> bool:
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
        if not self._account_write_enabled():
            return self._failure("AURION_ACCOUNT_ROLE_APPLY_BLOCKED", "AURION_WRITE_DISABLED", "Bounded Aurion owner writes are disabled")
        plan = self.account_role_plan(open_id=open_id, role=role, expected_revision=expected_revision)
        if not plan.get("ok"):
            return plan
        expected_confirmation = str(plan.get("confirmationSha256") or "")
        supplied = str(confirmation_sha256 or "").strip().lower()
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

    @staticmethod
    def _genkit_write_enabled() -> bool:
        return (
            os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() == "1"
            and os.getenv("SOVEREIGN_MCP_ENABLE_AURION_GENKIT_WRITE", "0").strip() == "1"
        )

    @staticmethod
    def _genkit_config() -> dict[str, Any]:
        raw = os.getenv("SOVEREIGN_AURION_GENKIT_BASE_URL", "").strip()
        if not raw:
            return {
                "configured": False,
                "baseUrlConfigured": False,
                "statusPath": "",
                "proposalPath": "",
                "applyPath": "",
                "tokenFileConfigured": False,
            }
        parsed = urlparse(raw)
        if parsed.scheme != "https" or parsed.hostname != "arelogic.space" or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise RuntimeError("Aurion Genkit base URL must be exact HTTPS arelogic.space metadata")
        base_path = parsed.path.rstrip("/")
        if base_path and (not base_path.startswith("/") or ".." in base_path):
            raise RuntimeError("Aurion Genkit base path is invalid")

        def selected_path(name: str) -> str:
            value = os.getenv(name, "").strip()
            if not value:
                return ""
            if not value.startswith("/") or value.startswith("//") or ".." in value or "?" in value or "#" in value:
                raise RuntimeError(f"{name} must be one fixed absolute path")
            return value

        token_path = os.getenv("SOVEREIGN_AURION_GENKIT_TOKEN_FILE", "").strip()
        return {
            "configured": True,
            "scheme": "https",
            "host": "arelogic.space",
            "port": parsed.port or 443,
            "basePath": base_path,
            "baseUrlConfigured": True,
            "statusPath": selected_path("SOVEREIGN_AURION_GENKIT_STATUS_PATH"),
            "proposalPath": selected_path("SOVEREIGN_AURION_GENKIT_PROPOSAL_PATH"),
            "applyPath": selected_path("SOVEREIGN_AURION_GENKIT_APPLY_PATH"),
            "tokenFileConfigured": bool(token_path),
            "tokenFile": token_path,
        }

    @staticmethod
    def _read_genkit_token(path_value: str) -> str:
        if not path_value:
            return ""
        path = Path(path_value)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Aurion Genkit token file is unavailable")
        metadata = path.stat()
        if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise RuntimeError("Aurion Genkit token file must be root-owned and private")
        payload = path.read_bytes()
        if not payload or len(payload) > 8_192 or b"\0" in payload:
            raise RuntimeError("Aurion Genkit token file violates the bounded secret contract")
        token = payload.decode("utf-8").strip()
        if not token or "\n" in token or "\r" in token:
            raise RuntimeError("Aurion Genkit token file is invalid")
        return token

    def _genkit_request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            config = self._genkit_config()
        except RuntimeError as exc:
            return self._failure("AURION_GENKIT_BLOCKED", "AURION_GENKIT_CONFIG_INVALID", str(exc))
        if not config.get("configured") or not path:
            return self._failure("AURION_GENKIT_BLOCKED", "AURION_GENKIT_NOT_CONFIGURED", "Aurion Genkit endpoint metadata is not configured")
        body = b""
        headers = {"Accept": "application/json", "User-Agent": "Sovottt-V2/Aurion-Bridge"}
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            if len(body) > MAX_CONTEXT_BYTES:
                return self._failure("AURION_GENKIT_BLOCKED", "AURION_GENKIT_REQUEST_TOO_LARGE", "Aurion Genkit request exceeded the bounded payload limit")
            headers["Content-Type"] = "application/json"
        try:
            token = self._read_genkit_token(str(config.get("tokenFile") or ""))
        except (OSError, UnicodeError, RuntimeError) as exc:
            return self._failure("AURION_GENKIT_BLOCKED", "AURION_GENKIT_AUTH_UNAVAILABLE", str(exc))
        if token:
            headers["Authorization"] = f"Bearer {token}"
        connection: http.client.HTTPSConnection | None = None
        try:
            connection = http.client.HTTPSConnection(
                str(config["host"]),
                int(config["port"]),
                timeout=20,
                context=ssl.create_default_context(),
            )
            target = f"{config.get('basePath') or ''}{path}"
            connection.request(method, target, body=body if payload is not None else None, headers=headers)
            response = connection.getresponse()
            raw = response.read(MAX_HTTP_BYTES + 1)
            if len(raw) > MAX_HTTP_BYTES:
                return self._failure("AURION_GENKIT_BLOCKED", "AURION_GENKIT_RESPONSE_TOO_LARGE", "Aurion Genkit response exceeded the bounded payload limit", httpStatus=int(response.status))
            text = raw.decode("utf-8")
            response_hash = _fingerprint(text)
            try:
                decoded = json.loads(text) if text else {}
            except json.JSONDecodeError:
                return self._failure(
                    "AURION_GENKIT_BLOCKED",
                    "AURION_GENKIT_RESPONSE_INVALID",
                    "Aurion Genkit did not return JSON",
                    httpStatus=int(response.status),
                    responseSha256=response_hash,
                )
            if not isinstance(decoded, dict):
                return self._failure("AURION_GENKIT_BLOCKED", "AURION_GENKIT_RESPONSE_INVALID", "Aurion Genkit returned an unexpected JSON shape", httpStatus=int(response.status), responseSha256=response_hash)
            sanitized = _redact(decoded)
            return {
                "ok": 200 <= int(response.status) < 300,
                "status": "AURION_GENKIT_HTTP_READY" if 200 <= int(response.status) < 300 else "AURION_GENKIT_HTTP_REJECTED",
                "httpStatus": int(response.status),
                "response": sanitized,
                "responseSha256": response_hash,
                "authConfigured": bool(token),
                "secretValuesReturned": False,
            }
        except (OSError, UnicodeError, http.client.HTTPException) as exc:
            return self._failure("AURION_GENKIT_BLOCKED", "AURION_GENKIT_HTTP_UNAVAILABLE", f"Aurion Genkit HTTPS request failed: {type(exc).__name__}")
        finally:
            if connection is not None:
                connection.close()

    def genkit_status(self, *, expected_revision: str) -> dict[str, Any]:
        identity = self.runtime_identity(expected_revision)
        if not identity.get("ok"):
            return identity
        try:
            config = self._genkit_config()
        except RuntimeError as exc:
            return self._failure("AURION_GENKIT_STATUS_BLOCKED", "AURION_GENKIT_CONFIG_INVALID", str(exc), runtimeIdentity=identity)
        status_path = str(config.get("statusPath") or "")
        if not config.get("configured") or not status_path:
            return {
                "ok": False,
                "status": "AURION_GENKIT_NOT_CONFIGURED",
                "failureFamily": "AURION_GENKIT_NOT_CONFIGURED",
                "runtimeIdentity": identity,
                "configuration": {
                    "baseUrlConfigured": bool(config.get("baseUrlConfigured")),
                    "statusPathConfigured": bool(status_path),
                    "proposalPathConfigured": bool(config.get("proposalPath")),
                    "applyPathConfigured": bool(config.get("applyPath")),
                    "tokenFileConfigured": bool(config.get("tokenFileConfigured")),
                },
                "mutationPerformed": False,
                "secretValuesReturned": False,
            }
        probe = self._genkit_request("GET", status_path)
        response = probe.get("response") if isinstance(probe.get("response"), dict) else {}
        response_revision = str(response.get("sourceRevision") or response.get("revision") or "").strip().lower()
        revision_bound = response_revision == identity.get("expectedRevision")
        ok = bool(probe.get("ok") and revision_bound)
        return {
            "ok": ok,
            "status": "AURION_GENKIT_VERIFIED" if ok else "AURION_GENKIT_UNBOUND",
            "failureFamily": None if ok else "AURION_GENKIT_REVISION_EVIDENCE_MISSING",
            "runtimeIdentity": identity,
            "httpStatus": probe.get("httpStatus"),
            "response": response,
            "responseSha256": probe.get("responseSha256"),
            "revisionBound": revision_bound,
            "authConfigured": bool(probe.get("authConfigured")),
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    def genkit_propose(
        self,
        *,
        intent: str,
        expected_revision: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        selected_intent = str(intent or "").strip()
        if not selected_intent or len(selected_intent) > 12_000:
            return self._failure("AURION_GENKIT_PROPOSAL_BLOCKED", "AURION_GENKIT_INTENT_INVALID", "intent must contain 1..12000 characters")
        identity = self.runtime_identity(expected_revision)
        if not identity.get("ok"):
            return identity
        try:
            config = self._genkit_config()
        except RuntimeError as exc:
            return self._failure("AURION_GENKIT_PROPOSAL_BLOCKED", "AURION_GENKIT_CONFIG_INVALID", str(exc), runtimeIdentity=identity)
        proposal_path = str(config.get("proposalPath") or "")
        if not proposal_path:
            return self._failure("AURION_GENKIT_PROPOSAL_BLOCKED", "AURION_GENKIT_NOT_CONFIGURED", "Aurion Genkit proposal endpoint is not configured", runtimeIdentity=identity)
        selected_context = context if isinstance(context, dict) else {}
        if len(json.dumps(selected_context, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > 32_000:
            return self._failure("AURION_GENKIT_PROPOSAL_BLOCKED", "AURION_GENKIT_CONTEXT_TOO_LARGE", "context exceeded the bounded size limit", runtimeIdentity=identity)
        payload = {
            "schemaVersion": "sovereign.aurion-genkit-proposal-request.v1",
            "source": "sovottt-v2",
            "mode": "proposal_only",
            "expectedRevision": identity["expectedRevision"],
            "intent": selected_intent,
            "context": selected_context,
        }
        result = self._genkit_request("POST", proposal_path, payload)
        response = result.get("response") if isinstance(result.get("response"), dict) else {}
        response_revision = str(response.get("sourceRevision") or response.get("revision") or "").strip().lower()
        proposal_hash = str(response.get("proposalSha256") or response.get("proposalHash") or "").strip().lower()
        revision_bound = response_revision == identity["expectedRevision"]
        proposal_bound = bool(SHA256_RE.fullmatch(proposal_hash))
        no_apply = response.get("mutationPerformed") is not True and response.get("applied") is not True
        ok = bool(result.get("ok") and revision_bound and proposal_bound and no_apply)
        return {
            "ok": ok,
            "status": "AURION_GENKIT_PROPOSAL_VERIFIED" if ok else "AURION_GENKIT_PROPOSAL_UNVERIFIED",
            "failureFamily": None if ok else "AURION_GENKIT_PROPOSAL_CONTRACT_INCOMPLETE",
            "runtimeIdentity": identity,
            "proposalSha256": proposal_hash if proposal_bound else None,
            "response": response,
            "responseSha256": result.get("responseSha256"),
            "revisionBound": revision_bound,
            "proposalBound": proposal_bound,
            "worldMutationClaimed": not no_apply,
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    def genkit_apply_plan(self, *, proposal_sha256: str, expected_revision: str) -> dict[str, Any]:
        proposal_hash = str(proposal_sha256 or "").strip().lower()
        if not SHA256_RE.fullmatch(proposal_hash):
            return self._failure("AURION_GENKIT_APPLY_PLAN_BLOCKED", "AURION_GENKIT_PROPOSAL_HASH_INVALID", "proposal_sha256 must be a full SHA-256")
        identity = self.runtime_identity(expected_revision)
        if not identity.get("ok"):
            return identity
        try:
            config = self._genkit_config()
        except RuntimeError as exc:
            return self._failure("AURION_GENKIT_APPLY_PLAN_BLOCKED", "AURION_GENKIT_CONFIG_INVALID", str(exc), runtimeIdentity=identity)
        apply_path = str(config.get("applyPath") or "")
        if not apply_path:
            return self._failure("AURION_GENKIT_APPLY_PLAN_BLOCKED", "AURION_GENKIT_APPLY_NOT_CONFIGURED", "A separately reviewed Aurion Genkit apply endpoint is not configured", runtimeIdentity=identity)
        state = {
            "schemaVersion": "sovereign.aurion-genkit-apply.v1",
            "action": "apply_reviewed_aurion_genkit_proposal",
            "expectedRevision": identity["expectedRevision"],
            "containerId": identity["containerId"],
            "imageId": identity["imageId"],
            "proposalSha256": proposal_hash,
            "applyPathSha256": _fingerprint(apply_path),
        }
        return {
            "ok": True,
            "status": "AURION_GENKIT_APPLY_PLAN_READY",
            "runtimeIdentity": identity,
            "proposalSha256": proposal_hash,
            "confirmationSha256": _canonical_sha256(state),
            "authorityModel": "proposal_then_server_validation_then_owner_hash_then_apply_then_target_readback",
            "directSqlAllowed": False,
            "directWorldMutationByLlmAllowed": False,
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    def genkit_apply(
        self,
        *,
        proposal_sha256: str,
        expected_revision: str,
        confirmation_sha256: str,
        owner_approved: bool,
    ) -> dict[str, Any]:
        if not owner_approved:
            return self._failure("AURION_GENKIT_APPLY_BLOCKED", "OWNER_APPROVAL_REQUIRED", "owner_approved=true is required")
        if not self._genkit_write_enabled():
            return self._failure("AURION_GENKIT_APPLY_BLOCKED", "AURION_GENKIT_WRITE_DISABLED", "Aurion Genkit apply is disabled")
        plan = self.genkit_apply_plan(proposal_sha256=proposal_sha256, expected_revision=expected_revision)
        if not plan.get("ok"):
            return plan
        expected = str(plan.get("confirmationSha256") or "")
        supplied = str(confirmation_sha256 or "").strip().lower()
        if not SHA256_RE.fullmatch(supplied) or supplied != expected:
            return self._failure(
                "AURION_GENKIT_APPLY_BLOCKED",
                "CONFIRMATION_MISMATCH",
                "Aurion Genkit runtime or proposal binding changed after planning",
                expectedConfirmationSha256=expected,
            )
        try:
            config = self._genkit_config()
        except RuntimeError as exc:
            return self._failure("AURION_GENKIT_APPLY_BLOCKED", "AURION_GENKIT_CONFIG_INVALID", str(exc))
        payload = {
            "schemaVersion": "sovereign.aurion-genkit-apply-request.v1",
            "source": "sovottt-v2",
            "mode": "apply_reviewed_proposal",
            "expectedRevision": plan["runtimeIdentity"]["expectedRevision"],
            "proposalSha256": plan["proposalSha256"],
            "approvalSha256": supplied,
        }
        result = self._genkit_request("POST", str(config.get("applyPath") or ""), payload)
        response = result.get("response") if isinstance(result.get("response"), dict) else {}
        response_revision = str(response.get("sourceRevision") or response.get("revision") or "").strip().lower()
        receipt = response.get("receipt") if isinstance(response.get("receipt"), dict) else None
        target_readback = response.get("targetReadback") if isinstance(response.get("targetReadback"), dict) else None
        applied = response.get("applied") is True or response.get("mutationPerformed") is True
        readback_flag = response.get("targetReadbackVerified") is True or response.get("readbackVerified") is True
        revision_bound = response_revision == plan["runtimeIdentity"]["expectedRevision"]
        post_identity = self.runtime_identity(expected_revision)
        identity_preserved = bool(
            post_identity.get("ok")
            and post_identity.get("containerId") == plan["runtimeIdentity"].get("containerId")
            and post_identity.get("imageId") == plan["runtimeIdentity"].get("imageId")
        )
        verified = bool(result.get("ok") and applied and receipt and target_readback and readback_flag and revision_bound and identity_preserved)
        return {
            "ok": verified,
            "status": "AURION_GENKIT_APPLIED_VERIFIED" if verified else "AURION_GENKIT_APPLY_UNVERIFIED",
            "failureFamily": None if verified else "AURION_GENKIT_TARGET_READBACK_INCOMPLETE",
            "runtimeIdentity": post_identity,
            "proposalSha256": plan["proposalSha256"],
            "receipt": _redact(receipt) if receipt else None,
            "receiptSha256": _canonical_sha256(receipt) if receipt else None,
            "targetReadback": _redact(target_readback) if target_readback else None,
            "targetReadbackSha256": _canonical_sha256(target_readback) if target_readback else None,
            "revisionBound": revision_bound,
            "identityPreserved": identity_preserved,
            "readbackVerified": verified,
            "mutationPerformed": applied,
            "mutationState": "VERIFIED" if verified else "OBSERVED_BUT_UNVERIFIED" if applied else "NOT_CONFIRMED",
            "secretValuesReturned": False,
        }
