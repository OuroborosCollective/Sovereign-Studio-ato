from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import re
import secrets
import stat
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from patchmon_operator import (
    PATCHMON_LOOPBACK_HOST,
    PATCHMON_LOOPBACK_PORT,
    PATCHMON_TOKEN_ROOT,
    PatchmonOperatorRuntime,
    _sha256_json,
    _sql_literal,
)


PATCHMON_CREDENTIAL_FILE = PATCHMON_TOKEN_ROOT / "mcp-admin-credentials.json"
PATCHMON_AGENT_CONFIG = Path("/etc/patchmon/config.yml")
PATCHMON_AGENT_BINARY = Path("/usr/local/bin/patchmon-agent")
PATCHMON_AGENT_SERVICE = "patchmon-agent.service"
PATCHMON_INSTALL_SCRIPT = PATCHMON_TOKEN_ROOT / ".mcp-patchmon-agent-install.sh"
PATCHMON_LOCAL_HOST_NAME = "sovereign-vps"
MAX_HTTP_BYTES = 2_000_000
_FRIENDLY_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{1,79}$")
_JWT_RE = re.compile(r"^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$")


class PatchmonFleetRuntime:
    """Fixed local-host enrollment and evidence-bound PatchMon fleet bootstrap."""

    def __init__(self, operator: PatchmonOperatorRuntime) -> None:
        self.operator = operator
        self.operator.set_admin_token_provider(self.ensure_admin_token)

    @staticmethod
    def _safe_friendly_name(value: str) -> str:
        name = str(value or PATCHMON_LOCAL_HOST_NAME).strip()
        if not _FRIENDLY_NAME_RE.fullmatch(name):
            raise ValueError("friendly_name must be 2-80 safe characters")
        return name

    @staticmethod
    def _secret_metadata(path: Path) -> dict[str, Any]:
        try:
            if path.is_symlink():
                return {"ready": False, "status": "SECRET_FILE_SYMLINK_BLOCKED"}
            resolved = path.resolve(strict=False)
            root = PATCHMON_TOKEN_ROOT.resolve(strict=False)
            if resolved != root and root not in resolved.parents:
                return {"ready": False, "status": "SECRET_FILE_OUTSIDE_PATCHMON_ROOT"}
            info = path.stat()
        except FileNotFoundError:
            return {"ready": False, "status": "SECRET_FILE_MISSING", "path": str(path)}
        except OSError as exc:
            return {"ready": False, "status": "SECRET_FILE_UNREADABLE", "failureFamily": type(exc).__name__}
        mode = stat.S_IMODE(info.st_mode)
        if not stat.S_ISREG(info.st_mode):
            return {"ready": False, "status": "SECRET_FILE_NOT_REGULAR"}
        if info.st_uid != 0:
            return {"ready": False, "status": "SECRET_FILE_OWNER_INVALID", "ownerUid": info.st_uid}
        if mode & 0o077:
            return {"ready": False, "status": "SECRET_FILE_MODE_TOO_OPEN", "mode": oct(mode)}
        if info.st_size <= 2 or info.st_size > 64_000:
            return {"ready": False, "status": "SECRET_FILE_SIZE_INVALID", "bytes": info.st_size}
        return {"ready": True, "status": "SECRET_FILE_READY", "path": str(path), "mode": oct(mode), "bytes": info.st_size}

    @staticmethod
    def _atomic_secret_write(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        temporary = path.with_name(path.name + ".tmp")
        try:
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                raise
            os.chown(temporary, 0, 0)
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()

    def _load_credentials(self) -> dict[str, Any]:
        metadata = self._secret_metadata(PATCHMON_CREDENTIAL_FILE)
        if not metadata.get("ready"):
            raise RuntimeError(str(metadata.get("status") or "PATCHMON_CREDENTIALS_NOT_READY"))
        try:
            decoded = json.loads(PATCHMON_CREDENTIAL_FILE.read_text("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("PATCHMON_CREDENTIALS_INVALID") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("PATCHMON_CREDENTIALS_INVALID")
        return decoded

    def _save_credentials(self, credentials: dict[str, Any]) -> None:
        encoded = json.dumps(credentials, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self._atomic_secret_write(PATCHMON_CREDENTIAL_FILE, encoded)

    @staticmethod
    def _jwt_expires_at(token: str) -> int:
        try:
            payload = token.split(".", 2)[1]
            payload += "=" * (-len(payload) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
            return int(decoded.get("exp") or 0)
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            return 0

    def _token_is_fresh(self, token: str, minimum_seconds: int = 120) -> bool:
        if not _JWT_RE.fullmatch(token):
            return False
        expires_at = self._jwt_expires_at(token)
        return expires_at == 0 or expires_at > int(time.time()) + minimum_seconds

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        body: dict[str, Any] | None = None,
        token: str = "",
        headers: dict[str, str] | None = None,
        expect_json: bool = True,
        timeout: int = 30,
    ) -> tuple[int, Any]:
        if not endpoint.startswith("/api/v1/") or ".." in endpoint or "\n" in endpoint or "\r" in endpoint:
            raise RuntimeError("PATCHMON_ENDPOINT_BLOCKED")
        encoded = b""
        request_headers = {"Accept": "application/json" if expect_json else "text/plain"}
        if body is not None:
            encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
            request_headers["Content-Length"] = str(len(encoded))
        if token:
            request_headers["Authorization"] = f"Bearer {token}"
        if headers:
            request_headers.update(headers)
        connection: http.client.HTTPConnection | None = None
        try:
            connection = http.client.HTTPConnection(PATCHMON_LOOPBACK_HOST, PATCHMON_LOOPBACK_PORT, timeout=timeout)
            connection.request(method, endpoint, body=encoded if body is not None else None, headers=request_headers)
            response = connection.getresponse()
            payload = response.read(MAX_HTTP_BYTES + 1)
            if len(payload) > MAX_HTTP_BYTES:
                raise RuntimeError("PATCHMON_HTTP_RESPONSE_TOO_LARGE")
            if expect_json:
                try:
                    decoded: Any = json.loads(payload.decode("utf-8")) if payload else {}
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RuntimeError("PATCHMON_HTTP_JSON_INVALID") from exc
                return int(response.status), decoded
            return int(response.status), payload
        except (OSError, http.client.HTTPException) as exc:
            raise RuntimeError(f"PATCHMON_HTTP_UNAVAILABLE:{type(exc).__name__}") from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _require_success(status: int, operation: str) -> None:
        if not 200 <= int(status) < 300:
            raise RuntimeError(f"{operation}_HTTP_{int(status)}")

    def ensure_admin_token(self) -> str:
        token_metadata = self.operator._token_metadata()
        if token_metadata.get("ready"):
            try:
                token = self.operator.token_file.read_text("utf-8").strip()
            except (OSError, UnicodeError):
                token = ""
            if self._token_is_fresh(token):
                return token

        credentials = self._load_credentials()
        admin = credentials.get("admin") if isinstance(credentials.get("admin"), dict) else {}
        username = str(admin.get("username") or "")
        password = str(admin.get("password") or "")
        if not username or not password:
            raise RuntimeError("PATCHMON_ADMIN_LOGIN_CREDENTIALS_MISSING")
        status, response = self._request(
            "POST",
            "/api/v1/auth/login",
            body={"username": username, "password": password},
        )
        self._require_success(status, "PATCHMON_ADMIN_LOGIN")
        token = str(response.get("token") or "") if isinstance(response, dict) else ""
        if not self._token_is_fresh(token, minimum_seconds=30):
            raise RuntimeError("PATCHMON_ADMIN_LOGIN_TOKEN_INVALID")
        self._atomic_secret_write(self.operator.token_file, (token + "\n").encode("utf-8"))
        return token

    @staticmethod
    def _generate_password() -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%^&*_-+="
        return "Aa1!" + "".join(secrets.choice(alphabet) for _ in range(44))

    def _bootstrap_admin(self) -> str:
        username = "sovereign_patchmon_mcp"
        password = self._generate_password()
        credentials = {
            "schemaVersion": "sovereign.patchmon-credentials.v1",
            "admin": {
                "username": username,
                "email": "patchmon-mcp@localhost.invalid",
                "password": password,
                "createdAtEpoch": int(time.time()),
            },
            "host": {},
        }
        self._save_credentials(credentials)
        status, response = self._request(
            "POST",
            "/api/v1/auth/setup-admin",
            body={
                "firstName": "Sovereign",
                "lastName": "Operator",
                "username": username,
                "email": "patchmon-mcp@localhost.invalid",
                "password": password,
            },
        )
        self._require_success(status, "PATCHMON_SETUP_ADMIN")
        token = str(response.get("token") or "") if isinstance(response, dict) else ""
        if not self._token_is_fresh(token, minimum_seconds=30):
            raise RuntimeError("PATCHMON_SETUP_ADMIN_TOKEN_INVALID")
        self._atomic_secret_write(self.operator.token_file, (token + "\n").encode("utf-8"))
        return token

    def _agent_state(self) -> dict[str, Any]:
        result = self.operator._run(
            [
                "systemctl",
                "show",
                PATCHMON_AGENT_SERVICE,
                "--property=LoadState",
                "--property=ActiveState",
                "--property=SubState",
            ],
            timeout=20,
            output_limit=2_000,
        )
        properties: dict[str, str] = {}
        for line in str(result.get("stdout") or "").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"LoadState", "ActiveState", "SubState"}:
                properties[key] = value.strip()
        return {
            "queryOk": bool(result.get("ok")),
            "loadState": properties.get("LoadState", "unknown"),
            "activeState": properties.get("ActiveState", "unknown"),
            "subState": properties.get("SubState", "unknown"),
            "binaryPresent": PATCHMON_AGENT_BINARY.is_file(),
            "configPresent": PATCHMON_AGENT_CONFIG.is_file(),
        }

    def _database_state(self, friendly_name: str) -> dict[str, Any]:
        result = self.operator._psql(
            f"""
SELECT
  (SELECT COUNT(*) FROM users) AS users_total,
  (SELECT COUNT(*) FROM settings) AS settings_total,
  (SELECT COUNT(*) FROM hosts) AS hosts_total,
  (SELECT COUNT(*) FROM hosts WHERE status = 'active') AS hosts_active,
  (SELECT COUNT(*) FROM docker_containers) AS docker_containers_observed,
  (SELECT COUNT(*) FROM docker_images) AS docker_images_observed,
  (SELECT COUNT(*) FROM docker_networks) AS docker_networks_observed,
  (SELECT COUNT(*) FROM docker_volumes) AS docker_volumes_observed,
  COALESCE((SELECT id FROM hosts WHERE friendly_name = {_sql_literal(friendly_name)} ORDER BY created_at LIMIT 1), '') AS local_host_id,
  COALESCE((SELECT status FROM hosts WHERE friendly_name = {_sql_literal(friendly_name)} ORDER BY created_at LIMIT 1), '') AS local_host_status,
  COALESCE((SELECT docker_enabled::text FROM hosts WHERE friendly_name = {_sql_literal(friendly_name)} ORDER BY created_at LIMIT 1), '') AS local_host_docker_enabled
""".strip(),
            max_rows=1,
        )
        if not result.get("ok") or not result.get("rows"):
            raise RuntimeError("PATCHMON_BOOTSTRAP_DATABASE_UNAVAILABLE")
        return dict(result["rows"][0])

    def _state(self, friendly_name: str) -> dict[str, Any]:
        runtime = self.operator.runtime_inventory(include_fleet=True, max_fleet_containers=200)
        database = self._database_state(friendly_name)
        return {
            "runtimeStatus": runtime.get("status"),
            "runtimeReady": bool(runtime.get("ok")),
            "fleetContainerCount": int(runtime.get("fleet", {}).get("totalContainers") or 0),
            "database": database,
            "agent": self._agent_state(),
            "adminToken": self.operator._token_metadata(),
            "credentialBundle": self._secret_metadata(PATCHMON_CREDENTIAL_FILE),
        }

    def bootstrap_plan(self, *, friendly_name: str = PATCHMON_LOCAL_HOST_NAME) -> dict[str, Any]:
        try:
            selected_name = self._safe_friendly_name(friendly_name)
            current_state = self._state(selected_name)
        except (ValueError, RuntimeError) as exc:
            return {"ok": False, "status": "BLOCKED", "blocker": str(exc), "mutationPerformed": False}
        plan_core = {
            "schemaVersion": "sovereign.patchmon-fleet-bootstrap-plan.v1",
            "action": "bootstrap_local_patchmon_fleet",
            "friendlyName": selected_name,
            "currentState": current_state,
            "effects": [
                "create_root_only_patchmon_admin_identity_if_no_users_exist",
                "configure_loopback_server_url_through_official_patchmon_api",
                "create_or_reuse_one_local_host_with_docker_enabled",
                "install_official_patchmon_agent_as_systemd_service",
                "request_real_docker_inventory_refresh",
            ],
            "immutableContainerLane": "unchanged_existing_revision_bound_image_deploy_path",
        }
        confirmation = _sha256_json(plan_core)
        write_enabled = (
            os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() == "1"
            and os.getenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "0").strip() == "1"
        )
        return {
            "ok": True,
            "status": "PATCHMON_FLEET_BOOTSTRAP_PLAN_READY",
            **plan_core,
            "confirmationSha256": confirmation,
            "requiresExactConfirmation": True,
            "requiresOwnerApproval": True,
            "writeEnabled": write_enabled,
            "readyToApply": write_enabled and bool(current_state.get("runtimeReady")),
            "genericShellAccepted": False,
            "arbitraryEndpointAccepted": False,
            "directDatabaseMutationUsed": False,
            "mutationPerformed": False,
            "secretValuesExposed": False,
        }

    def _host_row(self, friendly_name: str) -> dict[str, Any] | None:
        result = self.operator._psql(
            f"""
SELECT id, friendly_name, hostname, status, docker_enabled, last_update
FROM hosts
WHERE friendly_name = {_sql_literal(friendly_name)}
ORDER BY created_at
LIMIT 1
""".strip(),
            max_rows=1,
        )
        if not result.get("ok"):
            raise RuntimeError("PATCHMON_HOST_LOOKUP_FAILED")
        return dict(result["rows"][0]) if result.get("rows") else None

    def _update_host_credentials(self, host_id: str, api_id: str, api_key: str) -> None:
        credentials = self._load_credentials()
        credentials["host"] = {
            "hostId": host_id,
            "apiId": api_id,
            "apiKey": api_key,
            "updatedAtEpoch": int(time.time()),
        }
        self._save_credentials(credentials)

    def _host_credentials(self, host_id: str) -> tuple[str, str]:
        credentials = self._load_credentials()
        host = credentials.get("host") if isinstance(credentials.get("host"), dict) else {}
        if str(host.get("hostId") or "") != host_id:
            return "", ""
        return str(host.get("apiId") or ""), str(host.get("apiKey") or "")

    def _create_or_reuse_host(self, token: str, friendly_name: str) -> dict[str, Any]:
        existing = self._host_row(friendly_name)
        if existing is None:
            status, response = self._request(
                "POST",
                "/api/v1/hosts/create",
                token=token,
                body={
                    "friendly_name": friendly_name,
                    "docker_enabled": True,
                    "compliance_enabled": False,
                    "expected_platform": "linux",
                },
            )
            self._require_success(status, "PATCHMON_HOST_CREATE")
            host_id = str(response.get("hostId") or "") if isinstance(response, dict) else ""
            api_id = str(response.get("apiId") or "") if isinstance(response, dict) else ""
            api_key = str(response.get("apiKey") or "") if isinstance(response, dict) else ""
            if not host_id or not api_id or not api_key:
                raise RuntimeError("PATCHMON_HOST_CREATE_RESPONSE_INVALID")
            self._update_host_credentials(host_id, api_id, api_key)
            existing = self._host_row(friendly_name)
            if existing is None:
                raise RuntimeError("PATCHMON_HOST_CREATE_READBACK_FAILED")
            return existing

        host_id = str(existing.get("id") or "")
        api_id, api_key = self._host_credentials(host_id)
        agent = self._agent_state()
        if (not api_id or not api_key) and agent.get("activeState") != "active":
            status, response = self._request(
                "POST",
                f"/api/v1/hosts/{host_id}/regenerate-credentials",
                token=token,
                body={},
            )
            self._require_success(status, "PATCHMON_HOST_CREDENTIAL_REGENERATION")
            api_id = str(response.get("apiId") or "") if isinstance(response, dict) else ""
            api_key = str(response.get("apiKey") or "") if isinstance(response, dict) else ""
            if not api_id or not api_key:
                raise RuntimeError("PATCHMON_HOST_CREDENTIAL_REGENERATION_INVALID")
            self._update_host_credentials(host_id, api_id, api_key)
        return existing

    def _install_agent(self, host_id: str) -> dict[str, Any]:
        before = self._agent_state()
        if before.get("activeState") == "active" and before.get("configPresent") and before.get("binaryPresent"):
            return {"installed": False, "reason": "already_active", "state": before}
        api_id, api_key = self._host_credentials(host_id)
        if not api_id or not api_key:
            raise RuntimeError("PATCHMON_HOST_INSTALL_CREDENTIALS_MISSING")
        query = urlencode({"force": "true", "os": "linux"})
        status, payload = self._request(
            "GET",
            f"/api/v1/hosts/install?{query}",
            headers={"X-API-ID": api_id, "X-API-KEY": api_key},
            expect_json=False,
            timeout=60,
        )
        self._require_success(status, "PATCHMON_AGENT_INSTALL_SCRIPT")
        script = bytes(payload)
        if not script.startswith(b"#!/bin/sh\n"):
            raise RuntimeError("PATCHMON_AGENT_INSTALL_SCRIPT_INVALID")
        if b'PATCHMON_URL="http://127.0.0.1:32830"' not in script:
            raise RuntimeError("PATCHMON_AGENT_INSTALL_SCRIPT_NOT_LOOPBACK_BOUND")
        script_sha256 = hashlib.sha256(script).hexdigest()
        self._atomic_secret_write(PATCHMON_INSTALL_SCRIPT, script)
        os.chmod(PATCHMON_INSTALL_SCRIPT, 0o700)
        try:
            result = self.operator._run(
                ["/bin/sh", str(PATCHMON_INSTALL_SCRIPT)],
                timeout=210,
                output_limit=8_000,
            )
        finally:
            try:
                PATCHMON_INSTALL_SCRIPT.unlink()
            except FileNotFoundError:
                pass
        if not result.get("ok"):
            raise RuntimeError("PATCHMON_AGENT_INSTALL_EXECUTION_FAILED")
        deadline = time.monotonic() + 45
        after = self._agent_state()
        while after.get("activeState") != "active" and time.monotonic() < deadline:
            time.sleep(2)
            after = self._agent_state()
        if after.get("activeState") != "active":
            raise RuntimeError("PATCHMON_AGENT_SERVICE_NOT_ACTIVE")
        return {"installed": True, "scriptSha256": script_sha256, "state": after}

    def _ensure_docker_enabled(self, token: str, host: dict[str, Any]) -> None:
        host_id = str(host.get("id") or "")
        if str(host.get("docker_enabled") or "").lower() not in {"true", "t", "1"}:
            status, _ = self._request(
                "POST",
                f"/api/v1/hosts/{host_id}/integrations/docker/toggle",
                token=token,
                body={"enabled": True},
            )
            self._require_success(status, "PATCHMON_DOCKER_TOGGLE")
            deadline = time.monotonic() + 45
            while True:
                status, _ = self._request(
                    "POST",
                    f"/api/v1/hosts/{host_id}/integrations/apply-pending-config",
                    token=token,
                    body={},
                )
                if 200 <= status < 300:
                    break
                if status != 503 or time.monotonic() >= deadline:
                    self._require_success(status, "PATCHMON_DOCKER_CONFIG_APPLY")
                time.sleep(2)

    def _refresh_and_wait(
        self,
        token: str,
        host_id: str,
        friendly_name: str,
        expected_minimum: int,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + 120
        last_state = self._database_state(friendly_name)
        refresh_sent = False
        while time.monotonic() < deadline:
            host = self._host_row(friendly_name)
            if host and str(host.get("status") or "") == "active" and not refresh_sent:
                status, _ = self._request(
                    "POST",
                    f"/api/v1/hosts/{host_id}/refresh-docker",
                    token=token,
                    body={},
                )
                self._require_success(status, "PATCHMON_DOCKER_REFRESH")
                refresh_sent = True
            last_state = self._database_state(friendly_name)
            observed = int(last_state.get("docker_containers_observed") or 0)
            active = int(last_state.get("hosts_active") or 0)
            if active >= 1 and observed >= max(1, expected_minimum):
                return last_state
            time.sleep(2)
        return last_state

    def bootstrap_apply(
        self,
        *,
        confirmation_sha256: str,
        friendly_name: str = PATCHMON_LOCAL_HOST_NAME,
        owner_approved: bool = False,
    ) -> dict[str, Any]:
        if not owner_approved:
            return {"ok": False, "status": "BLOCKED", "blocker": "Explicit owner approval is required"}
        if os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Private Owner Mode is not active"}
        if os.getenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "0").strip() != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "PatchMon writes are not enabled"}
        if not re.fullmatch(r"[0-9a-f]{64}", str(confirmation_sha256 or "")):
            return {"ok": False, "status": "BLOCKED", "blocker": "confirmation_sha256 is invalid"}
        plan = self.bootstrap_plan(friendly_name=friendly_name)
        if not plan.get("ok"):
            return plan
        if confirmation_sha256 != plan.get("confirmationSha256"):
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "PatchMon fleet bootstrap plan hash does not match current state",
                "expected": plan.get("confirmationSha256"),
            }
        try:
            selected_name = self._safe_friendly_name(friendly_name)
            initial_database = plan.get("currentState", {}).get("database", {})
            users_total = int(initial_database.get("users_total") or 0)
            if users_total == 0:
                token = self._bootstrap_admin()
            else:
                token = self.ensure_admin_token()

            status, _ = self._request(
                "PATCH",
                "/api/v1/settings",
                token=token,
                body={
                    "server_url": "http://127.0.0.1:32830",
                    "server_protocol": "http",
                    "server_host": "127.0.0.1",
                    "server_port": 32830,
                },
            )
            self._require_success(status, "PATCHMON_SETTINGS_UPDATE")
            host = self._create_or_reuse_host(token, selected_name)
            host_id = str(host.get("id") or "")
            install = self._install_agent(host_id)
            current_host = self._host_row(selected_name) or host
            self._ensure_docker_enabled(token, current_host)
            expected_fleet = int(plan.get("currentState", {}).get("fleetContainerCount") or 0)
            final_database = self._refresh_and_wait(
                token,
                host_id,
                selected_name,
                expected_fleet,
            )
            observed = int(final_database.get("docker_containers_observed") or 0)
            active = int(final_database.get("hosts_active") or 0)
            complete = active >= 1 and observed >= max(1, expected_fleet)
            return {
                "ok": complete,
                "status": "PATCHMON_FLEET_BOOTSTRAPPED" if complete else "PATCHMON_FLEET_BOOTSTRAP_INCOMPLETE",
                "friendlyName": selected_name,
                "hostId": host_id,
                "agent": install,
                "database": final_database,
                "expectedFleetContainers": expected_fleet,
                "observedDockerContainers": observed,
                "hostActive": active >= 1,
                "immutableContainerLane": "unchanged_existing_revision_bound_image_deploy_path",
                "mutationPerformed": True,
                "secretValuesExposed": False,
                "nextAction": None if complete else "Inspect bounded PatchMon agent and Docker refresh evidence before retrying",
            }
        except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
            return {
                "ok": False,
                "status": "PATCHMON_FLEET_BOOTSTRAP_FAILED",
                "failureFamily": str(exc)[:240],
                "mutationPerformed": True,
                "secretValuesExposed": False,
                "nextAction": "Repair the exact failure family and rerun a fresh state-bound bootstrap plan",
            }

    def tool_inventory(self) -> dict[str, Any]:
        inventory = self.operator.tool_inventory()
        tools = list(inventory.get("tools") or [])
        tools.extend(
            [
                {"name": "patchmon_fleet_bootstrap_plan", "mutation": False, "source": "runtime plus PatchMon DB plus systemd evidence"},
                {"name": "patchmon_fleet_bootstrap_apply", "mutation": True, "source": "official PatchMon API plus fixed local agent installer"},
                {"name": "patchmon_fleet_orchestrator_status", "mutation": False, "source": "PatchMon plus repository workflow evidence"},
            ]
        )
        boundaries = dict(inventory.get("boundaries") or {})
        boundaries.update(
            {
                "localAgentTarget": PATCHMON_AGENT_SERVICE,
                "agentInstallSource": "fixed_patchmon_loopback_api_only",
                "generatedAdminCredentialLocation": "root_only_host_file",
                "containerRevisionMutationDelegatedToPatchMon": False,
            }
        )
        return {**inventory, "tools": tools, "boundaries": boundaries}
