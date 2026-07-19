from __future__ import annotations

import csv
import hashlib
import http.client
import io
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Callable


PATCHMON_STACK_ID = "patchmon-sovereign"
PATCHMON_PROJECT = "patchmon-sovereign"
PATCHMON_SERVER_CONTAINER = "patchmon-sovereign-server-1"
PATCHMON_DATABASE_CONTAINER = "patchmon-sovereign-database-1"
PATCHMON_REDIS_CONTAINER = "patchmon-sovereign-redis-1"
PATCHMON_GUACD_CONTAINER = "patchmon-sovereign-guacd-1"
PATCHMON_CONTAINERS = (
    PATCHMON_SERVER_CONTAINER,
    PATCHMON_DATABASE_CONTAINER,
    PATCHMON_REDIS_CONTAINER,
    PATCHMON_GUACD_CONTAINER,
)
PATCHMON_SERVICES = ("server", "database", "redis", "guacd")
PATCHMON_INTERNAL_NETWORK = f"{PATCHMON_PROJECT}_patchmon-internal"
PATCHMON_EDGE_NETWORK = f"{PATCHMON_PROJECT}_patchmon-edge"
PATCHMON_EXPECTED_CONTAINER_NETWORKS = {
    PATCHMON_SERVER_CONTAINER: frozenset({PATCHMON_INTERNAL_NETWORK, PATCHMON_EDGE_NETWORK}),
    PATCHMON_DATABASE_CONTAINER: frozenset({PATCHMON_INTERNAL_NETWORK}),
    PATCHMON_REDIS_CONTAINER: frozenset({PATCHMON_INTERNAL_NETWORK}),
    PATCHMON_GUACD_CONTAINER: frozenset({PATCHMON_INTERNAL_NETWORK}),
}
PATCHMON_EXPECTED_NETWORK_MEMBERS = {
    PATCHMON_INTERNAL_NETWORK: frozenset(PATCHMON_CONTAINERS),
    PATCHMON_EDGE_NETWORK: frozenset({PATCHMON_SERVER_CONTAINER}),
}
PATCHMON_EXPECTED_NETWORK_INTERNAL = {
    PATCHMON_INTERNAL_NETWORK: True,
    PATCHMON_EDGE_NETWORK: False,
}
PATCHMON_DATABASE_USER = "patchmon_user"
PATCHMON_DATABASE_NAME = "patchmon_db"
PATCHMON_LOOPBACK_HOST = "127.0.0.1"
PATCHMON_LOOPBACK_PORT = 32830
PATCHMON_TOKEN_ROOT = Path("/opt/patchmon-sovereign")
PATCHMON_DEFAULT_TOKEN_FILE = PATCHMON_TOKEN_ROOT / "mcp-admin.jwt"
MAX_FLEET_CONTAINERS = 200
MAX_QUERY_ROWS = 200
MAX_RESPONSE_BYTES = 500_000
MAX_CELL_CHARS = 2_000
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")
_STATUS_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,255}$")
_JWT_RE = re.compile(r"^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$")
_JWT_VALUE_RE = re.compile(r"\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_BEARER_VALUE_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_OPENAI_KEY_RE = re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|credential|authorization|cookie|session|jwt|private[_-]?key|encryption[_-]?key)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_SENSITIVE_KEY_RE = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|credential|authorization|cookie|session|jwt|private[_-]?key|encryption[_-]?key)",
    re.IGNORECASE,
)
_ALLOWED_PATCH_ACTIONS = frozenset(
    {
        "validate_packages",
        "submit_for_approval",
        "approve_run",
        "retry_validation",
        "stop_run",
    }
)


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _bounded_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class PatchmonOperatorRuntime:
    """Host-side PatchMon control plane without generic shell or Docker-socket exposure."""

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        token_file: str | None = None,
    ) -> None:
        self._runner = runner or subprocess.run
        configured_token_file = token_file or os.getenv(
            "PATCHMON_MCP_ADMIN_TOKEN_FILE",
            str(PATCHMON_DEFAULT_TOKEN_FILE),
        )
        self.token_file = Path(configured_token_file)

    def _run(self, argv: list[str], *, timeout: int = 60, output_limit: int = MAX_RESPONSE_BYTES) -> dict[str, Any]:
        try:
            completed = self._runner(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env={
                    **os.environ,
                    "PATH": os.environ.get(
                        "PATH",
                        "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                    ),
                },
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "exitCode": None,
                "stdout": "",
                "stderr": "",
                "failureFamily": "COMMAND_TIMEOUT",
            }
        except OSError as exc:
            return {
                "ok": False,
                "exitCode": None,
                "stdout": "",
                "stderr": str(exc)[:2_000],
                "failureFamily": "COMMAND_UNAVAILABLE",
            }
        return {
            "ok": completed.returncode == 0,
            "exitCode": completed.returncode,
            "stdout": str(completed.stdout or "")[-output_limit:],
            "stderr": str(completed.stderr or "")[-8_000:],
            "failureFamily": None if completed.returncode == 0 else "COMMAND_FAILED",
        }

    @classmethod
    def _redact(cls, value: Any, key: str = "") -> Any:
        if _SENSITIVE_KEY_RE.search(key):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {
                str(item_key): cls._redact(item_value, str(item_key))
                for item_key, item_value in value.items()
            }
        if isinstance(value, list):
            return [cls._redact(item, key) for item in value[:500]]
        if isinstance(value, str):
            redacted = _BEARER_VALUE_RE.sub("Bearer [REDACTED]", value)
            redacted = _OPENAI_KEY_RE.sub("[REDACTED]", redacted)
            redacted = _JWT_VALUE_RE.sub("[REDACTED]", redacted)
            redacted = _SECRET_ASSIGNMENT_RE.sub(r"\1\2[REDACTED]", redacted)
            return redacted[:MAX_CELL_CHARS]
        return value

    def _inspect_container(self, container: str) -> dict[str, Any]:
        result = self._run(["docker", "inspect", container], timeout=30)
        if not result["ok"]:
            return {
                "present": False,
                "container": container,
                "failureFamily": "CONTAINER_ABSENT",
            }
        try:
            decoded = json.loads(result["stdout"])
            inspect = decoded[0]
        except (json.JSONDecodeError, IndexError, TypeError):
            return {
                "present": False,
                "container": container,
                "failureFamily": "CONTAINER_INSPECT_INVALID",
            }

        state = inspect.get("State") if isinstance(inspect.get("State"), dict) else {}
        config = inspect.get("Config") if isinstance(inspect.get("Config"), dict) else {}
        labels = config.get("Labels") if isinstance(config.get("Labels"), dict) else {}
        network_settings = (
            inspect.get("NetworkSettings")
            if isinstance(inspect.get("NetworkSettings"), dict)
            else {}
        )
        networks_raw = (
            network_settings.get("Networks")
            if isinstance(network_settings.get("Networks"), dict)
            else {}
        )
        ports_raw = (
            network_settings.get("Ports")
            if isinstance(network_settings.get("Ports"), dict)
            else {}
        )
        mounts_raw = inspect.get("Mounts") if isinstance(inspect.get("Mounts"), list) else []

        networks = []
        for name, data in sorted(networks_raw.items()):
            details = data if isinstance(data, dict) else {}
            networks.append(
                {
                    "name": str(name),
                    "ipAddress": str(details.get("IPAddress") or ""),
                    "globalIPv6Address": str(details.get("GlobalIPv6Address") or ""),
                }
            )

        published_ports: list[dict[str, str]] = []
        for container_port, bindings in sorted(ports_raw.items()):
            if not isinstance(bindings, list):
                continue
            for binding in bindings:
                if not isinstance(binding, dict):
                    continue
                published_ports.append(
                    {
                        "containerPort": str(container_port),
                        "hostIp": str(binding.get("HostIp") or ""),
                        "hostPort": str(binding.get("HostPort") or ""),
                    }
                )

        mounts = []
        for mount in mounts_raw:
            if not isinstance(mount, dict):
                continue
            mounts.append(
                {
                    "type": str(mount.get("Type") or ""),
                    "name": str(mount.get("Name") or ""),
                    "destination": str(mount.get("Destination") or ""),
                    "rw": bool(mount.get("RW")),
                }
            )

        health = state.get("Health") if isinstance(state.get("Health"), dict) else {}
        host_config = (
            inspect.get("HostConfig")
            if isinstance(inspect.get("HostConfig"), dict)
            else {}
        )
        return {
            "present": True,
            "container": container,
            "id": str(inspect.get("Id") or "")[:64],
            "name": str(inspect.get("Name") or "").lstrip("/"),
            "imageReference": str(config.get("Image") or ""),
            "imageId": str(inspect.get("Image") or ""),
            "project": str(labels.get("com.docker.compose.project") or ""),
            "service": str(labels.get("com.docker.compose.service") or ""),
            "state": {
                "status": str(state.get("Status") or "unknown"),
                "running": bool(state.get("Running")),
                "paused": bool(state.get("Paused")),
                "restarting": bool(state.get("Restarting")),
                "oomKilled": bool(state.get("OOMKilled")),
                "dead": bool(state.get("Dead")),
                "exitCode": int(state.get("ExitCode") or 0),
                "startedAt": str(state.get("StartedAt") or ""),
                "finishedAt": str(state.get("FinishedAt") or ""),
                "health": str(health.get("Status") or "none"),
                "restartCount": int(inspect.get("RestartCount") or 0),
            },
            "security": {
                "privileged": bool(host_config.get("Privileged")),
                "readOnlyRootfs": bool(host_config.get("ReadonlyRootfs")),
                "networkMode": str(host_config.get("NetworkMode") or ""),
            },
            "networks": networks,
            "publishedPorts": published_ports,
            "mounts": mounts,
        }

    def _network_inventory(self, container_states: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        names: set[str] = set()
        result = self._run(
            [
                "docker",
                "network",
                "ls",
                "--filter",
                f"label=com.docker.compose.project={PATCHMON_PROJECT}",
                "--format",
                "{{json .}}",
            ],
            timeout=30,
        )
        if result["ok"]:
            for line in result["stdout"].splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                name = str(row.get("Name") or "")
                if name:
                    names.add(name)
        for state in container_states.values():
            for network in state.get("networks") if isinstance(state.get("networks"), list) else []:
                if isinstance(network, dict) and network.get("name"):
                    names.add(str(network["name"]))

        inventories: list[dict[str, Any]] = []
        for name in sorted(names):
            inspect_result = self._run(["docker", "network", "inspect", name], timeout=30)
            if not inspect_result["ok"]:
                inventories.append({"name": name, "present": False})
                continue
            try:
                decoded = json.loads(inspect_result["stdout"])
                network = decoded[0]
            except (json.JSONDecodeError, IndexError, TypeError):
                inventories.append({"name": name, "present": False, "failureFamily": "NETWORK_INSPECT_INVALID"})
                continue
            labels = network.get("Labels") if isinstance(network.get("Labels"), dict) else {}
            members = []
            containers = network.get("Containers") if isinstance(network.get("Containers"), dict) else {}
            for container_id, member in sorted(containers.items()):
                item = member if isinstance(member, dict) else {}
                members.append(
                    {
                        "containerId": str(container_id)[:64],
                        "name": str(item.get("Name") or ""),
                        "ipv4Address": str(item.get("IPv4Address") or ""),
                        "ipv6Address": str(item.get("IPv6Address") or ""),
                    }
                )
            inventories.append(
                {
                    "name": name,
                    "present": True,
                    "id": str(network.get("Id") or "")[:64],
                    "driver": str(network.get("Driver") or ""),
                    "scope": str(network.get("Scope") or ""),
                    "internal": bool(network.get("Internal")),
                    "attachable": bool(network.get("Attachable")),
                    "ingress": bool(network.get("Ingress")),
                    "project": str(labels.get("com.docker.compose.project") or ""),
                    "members": members,
                }
            )
        return inventories

    def _fleet_inventory(self, limit: int) -> dict[str, Any]:
        result = self._run(
            ["docker", "ps", "-a", "--no-trunc", "--format", "{{json .}}"],
            timeout=30,
        )
        if not result["ok"]:
            return {
                "ok": False,
                "status": "DOCKER_FLEET_UNAVAILABLE",
                "containers": [],
                "failureFamily": result.get("failureFamily"),
            }
        rows = []
        for line in result["stdout"].splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(
                {
                    "id": str(row.get("ID") or "")[:64],
                    "name": str(row.get("Names") or ""),
                    "image": str(row.get("Image") or ""),
                    "state": str(row.get("State") or ""),
                    "status": str(row.get("Status") or ""),
                    "networks": sorted(
                        item.strip()
                        for item in str(row.get("Networks") or "").split(",")
                        if item.strip()
                    ),
                    "ports": str(row.get("Ports") or "")[:1_000],
                }
            )
        total = len(rows)
        return {
            "ok": True,
            "status": "DOCKER_FLEET_INVENTORIED",
            "totalContainers": total,
            "containers": rows[:limit],
            "truncated": total > limit,
        }

    @staticmethod
    def _server_transport_ready(state: dict[str, Any]) -> bool:
        bindings = state.get("publishedPorts", [])
        loopback_ready = any(
            str(binding.get("containerPort") or "") == "3000/tcp"
            and str(binding.get("hostIp") or "") == "127.0.0.1"
            and str(binding.get("hostPort") or "") == "32830"
            for binding in bindings
            if isinstance(binding, dict)
        )
        network_names = {
            str(network.get("name") or "")
            for network in state.get("networks", [])
            if isinstance(network, dict)
        }
        return (
            bool(state.get("state", {}).get("running"))
            and "patchmon-sovereign_patchmon-edge" in network_names
            and loopback_ready
        )

    def _http_health(self) -> dict[str, Any]:
        connection: http.client.HTTPConnection | None = None
        try:
            connection = http.client.HTTPConnection(
                PATCHMON_LOOPBACK_HOST,
                PATCHMON_LOOPBACK_PORT,
                timeout=5,
            )
            connection.request(
                "GET",
                "/api/v1/health?format=json",
                headers={"Accept": "application/json"},
            )
            response = connection.getresponse()
            payload = response.read(16_384)
            try:
                body = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                body = {"bodySha256": hashlib.sha256(payload).hexdigest()}
            return {
                "ok": 200 <= response.status < 300,
                "status": "PATCHMON_HTTP_HEALTH_READY" if 200 <= response.status < 300 else "PATCHMON_HTTP_HEALTH_FAILED",
                "httpStatus": int(response.status),
                "endpoint": "http://127.0.0.1:32830/api/v1/health?format=json",
                "health": self._redact(body),
                "responseBytes": len(payload),
            }
        except (OSError, http.client.HTTPException) as exc:
            return {
                "ok": False,
                "status": "PATCHMON_HTTP_UNAVAILABLE",
                "failureFamily": type(exc).__name__,
            }
        finally:
            if connection is not None:
                connection.close()

    def runtime_inventory(
        self,
        *,
        include_fleet: bool = True,
        max_fleet_containers: int = 100,
    ) -> dict[str, Any]:
        limit = _bounded_int(max_fleet_containers, 1, MAX_FLEET_CONTAINERS, 100)
        states = {name: self._inspect_container(name) for name in PATCHMON_CONTAINERS}
        networks = self._network_inventory(states)
        fleet = self._fleet_inventory(limit) if include_fleet else {
            "ok": True,
            "status": "NOT_REQUESTED",
            "containers": [],
        }

        violations: list[dict[str, Any]] = []
        for name, state in states.items():
            if not state.get("present"):
                continue
            if state.get("project") != PATCHMON_PROJECT:
                violations.append({"code": "PROJECT_LABEL_MISMATCH", "container": name})
            if state.get("service") not in PATCHMON_SERVICES:
                violations.append({"code": "SERVICE_LABEL_UNEXPECTED", "container": name})
            if state.get("security", {}).get("privileged"):
                violations.append({"code": "PRIVILEGED_CONTAINER", "container": name})
            published_ports = state.get("publishedPorts", [])
            if name != PATCHMON_SERVER_CONTAINER and published_ports:
                violations.append(
                    {
                        "code": "PATCHMON_INTERNAL_SERVICE_PUBLISHED",
                        "container": name,
                    }
                )
            for binding in published_ports:
                host_ip = str(binding.get("hostIp") or "")
                if host_ip not in {"127.0.0.1", "::1"}:
                    violations.append(
                        {
                            "code": "NON_LOOPBACK_PUBLISHED_PORT",
                            "container": name,
                            "binding": binding,
                        }
                    )
        network_by_name = {
            str(network.get("name") or ""): network
            for network in networks
            if str(network.get("name") or "")
        }
        for network_name, expected_members in PATCHMON_EXPECTED_NETWORK_MEMBERS.items():
            network = network_by_name.get(network_name)
            if not network or not network.get("present"):
                violations.append(
                    {
                        "code": "REQUIRED_PATCHMON_NETWORK_MISSING",
                        "network": network_name,
                    }
                )
                continue
            if bool(network.get("internal")) != PATCHMON_EXPECTED_NETWORK_INTERNAL[network_name]:
                violations.append(
                    {
                        "code": "PATCHMON_NETWORK_INTERNAL_MODE_MISMATCH",
                        "network": network_name,
                        "expectedInternal": PATCHMON_EXPECTED_NETWORK_INTERNAL[network_name],
                        "actualInternal": bool(network.get("internal")),
                    }
                )
            if network.get("driver") != "bridge":
                violations.append(
                    {
                        "code": "PATCHMON_NETWORK_DRIVER_MISMATCH",
                        "network": network_name,
                        "expectedDriver": "bridge",
                        "actualDriver": network.get("driver"),
                    }
                )
            observed_members = {
                str(member.get("name") or "")
                for member in network.get("members", [])
                if isinstance(member, dict) and str(member.get("name") or "")
            }
            for container in sorted(expected_members - observed_members):
                violations.append(
                    {
                        "code": "PATCHMON_NETWORK_MEMBER_MISSING",
                        "network": network_name,
                        "container": container,
                    }
                )
            for container in sorted(observed_members - expected_members):
                violations.append(
                    {
                        "code": "UNEXPECTED_PATCHMON_NETWORK_MEMBER",
                        "network": network_name,
                        "container": container,
                    }
                )

        for container, state in states.items():
            if not state.get("present"):
                continue
            observed_networks = {
                str(network.get("name") or "")
                for network in state.get("networks", [])
                if isinstance(network, dict) and str(network.get("name") or "")
            }
            expected_networks = PATCHMON_EXPECTED_CONTAINER_NETWORKS[container]
            for network_name in sorted(expected_networks - observed_networks):
                violations.append(
                    {
                        "code": "PATCHMON_CONTAINER_NETWORK_MISSING",
                        "container": container,
                        "network": network_name,
                    }
                )
            for network_name in sorted(observed_networks - expected_networks):
                violations.append(
                    {
                        "code": "PATCHMON_CONTAINER_NETWORK_UNEXPECTED",
                        "container": container,
                        "network": network_name,
                    }
                )

        present = sum(1 for state in states.values() if state.get("present"))
        running = sum(1 for state in states.values() if state.get("state", {}).get("running"))
        healthy = sum(
            1
            for state in states.values()
            if state.get("state", {}).get("running")
            and state.get("state", {}).get("health") in {"healthy", "none"}
        )
        server_state = states[PATCHMON_SERVER_CONTAINER]
        if not server_state.get("present"):
            http_health = {
                "ok": False,
                "status": "PATCHMON_NOT_DEPLOYED",
            }
        elif not self._server_transport_ready(server_state):
            http_health = {
                "ok": False,
                "status": "PATCHMON_HTTP_SKIPPED_UNVERIFIED_TRANSPORT",
                "reason": "expected PatchMon loopback binding and edge network are not both active",
            }
        else:
            http_health = self._http_health()
        ready = (
            present == len(PATCHMON_CONTAINERS)
            and running == len(PATCHMON_CONTAINERS)
            and healthy == len(PATCHMON_CONTAINERS)
            and bool(http_health.get("ok"))
            and not violations
        )
        return {
            "ok": ready,
            "status": "PATCHMON_RUNTIME_VERIFIED" if ready else (
                "PATCHMON_NOT_DEPLOYED" if present == 0 else "PATCHMON_RUNTIME_DEGRADED"
            ),
            "stackId": PATCHMON_STACK_ID,
            "project": PATCHMON_PROJECT,
            "expectedContainers": list(PATCHMON_CONTAINERS),
            "counts": {
                "expected": len(PATCHMON_CONTAINERS),
                "present": present,
                "running": running,
                "healthyOrNoHealthcheck": healthy,
            },
            "containers": states,
            "networks": networks,
            "httpHealth": http_health,
            "fleet": fleet,
            "boundaryViolations": violations,
            "dockerSocketMountedInMcp": False,
            "brokerTransport": "unix_socket_allowlisted_actions",
            "mutationPerformed": False,
            "secretValuesExposed": False,
        }

    def _psql(self, sql: str, *, timeout: int = 30, max_rows: int = MAX_QUERY_ROWS) -> dict[str, Any]:
        result = self._run(
            [
                "docker",
                "exec",
                PATCHMON_DATABASE_CONTAINER,
                "psql",
                "-X",
                "--set",
                "ON_ERROR_STOP=1",
                "--csv",
                "--pset",
                "footer=off",
                "-U",
                PATCHMON_DATABASE_USER,
                "-d",
                PATCHMON_DATABASE_NAME,
                "-c",
                sql,
            ],
            timeout=timeout,
            output_limit=MAX_RESPONSE_BYTES,
        )
        if not result["ok"]:
            return {
                "ok": False,
                "status": "PATCHMON_DATABASE_QUERY_FAILED",
                "failureFamily": result.get("failureFamily"),
                "exitCode": result.get("exitCode"),
                "error": self._redact(str(result.get("stderr") or "")[-2_000:]),
                "rows": [],
                "columns": [],
            }
        try:
            reader = csv.DictReader(io.StringIO(result["stdout"]))
            columns = [str(item or "") for item in (reader.fieldnames or [])]
            rows = []
            truncated = False
            for row in reader:
                if len(rows) >= max_rows:
                    truncated = True
                    break
                rows.append(
                    {
                        column: self._redact(str(row.get(column) or ""), column)
                        for column in columns
                    }
                )
        except (csv.Error, UnicodeError) as exc:
            return {
                "ok": False,
                "status": "PATCHMON_DATABASE_RESULT_INVALID",
                "failureFamily": type(exc).__name__,
                "rows": [],
                "columns": [],
            }
        return {
            "ok": True,
            "status": "PATCHMON_DATABASE_QUERY_OK",
            "columns": columns,
            "rows": rows,
            "rowCount": len(rows),
            "truncated": truncated,
            "querySha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
        }

    def database_inventory(
        self,
        *,
        max_tables: int = 200,
        max_columns: int = 2_000,
    ) -> dict[str, Any]:
        table_limit = _bounded_int(max_tables, 1, 500, 200)
        column_limit = _bounded_int(max_columns, 1, 5_000, 2_000)
        readiness = self._psql("SELECT current_database() AS database, current_user AS database_user, 1 AS ready", max_rows=1)
        if not readiness.get("ok"):
            return {
                "ok": False,
                "status": "PATCHMON_DATABASE_UNAVAILABLE",
                "readiness": readiness,
                "tables": [],
                "mutationPerformed": False,
                "secretValuesExposed": False,
            }

        column_fetch_limit = column_limit + 1
        table_fetch_limit = table_limit + 1
        columns_result = self._psql(
            f"""
SELECT table_schema, table_name, column_name, ordinal_position, data_type, udt_name, is_nullable
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position
LIMIT {column_fetch_limit}
""".strip(),
            max_rows=column_fetch_limit,
        )
        estimates_result = self._psql(
            f"""
SELECT n.nspname AS table_schema, c.relname AS table_name,
       GREATEST(c.reltuples::bigint, 0) AS estimated_rows
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname
LIMIT {table_fetch_limit}
""".strip(),
            max_rows=table_fetch_limit,
        )
        if not columns_result.get("ok") or not estimates_result.get("ok"):
            return {
                "ok": False,
                "status": "PATCHMON_DATABASE_INVENTORY_FAILED",
                "readiness": readiness,
                "columnsEvidence": columns_result,
                "estimatesEvidence": estimates_result,
                "mutationPerformed": False,
                "secretValuesExposed": False,
            }

        estimate_rows = estimates_result.get("rows", [])
        column_rows = columns_result.get("rows", [])
        estimates = {
            (str(row.get("table_schema") or ""), str(row.get("table_name") or "")): row.get("estimated_rows")
            for row in estimate_rows[:table_limit]
        }
        tables: dict[tuple[str, str], dict[str, Any]] = {}
        for row in column_rows[:column_limit]:
            key = (str(row.get("table_schema") or ""), str(row.get("table_name") or ""))
            if key not in tables and len(tables) >= table_limit:
                continue
            table = tables.setdefault(
                key,
                {
                    "schema": key[0],
                    "name": key[1],
                    "estimatedRows": estimates.get(key, "0"),
                    "columns": [],
                },
            )
            table["columns"].append(
                {
                    "name": row.get("column_name"),
                    "ordinalPosition": row.get("ordinal_position"),
                    "dataType": row.get("data_type"),
                    "udtName": row.get("udt_name"),
                    "nullable": row.get("is_nullable") == "YES",
                    "sensitiveByName": bool(_SENSITIVE_KEY_RE.search(str(row.get("column_name") or ""))),
                }
            )

        migration = {"status": "NOT_PRESENT"}
        if any(table["name"] == "schema_migrations" for table in tables.values()):
            migration = self._psql(
                "SELECT version::text AS version, dirty::text AS dirty FROM schema_migrations ORDER BY version DESC LIMIT 20",
                max_rows=20,
            )

        return {
            "ok": True,
            "status": "PATCHMON_DATABASE_INVENTORIED",
            "database": PATCHMON_DATABASE_NAME,
            "databaseUser": PATCHMON_DATABASE_USER,
            "readiness": readiness,
            "tables": list(tables.values()),
            "tableCount": len(tables),
            "columnsTruncated": len(column_rows) > column_limit,
            "tablesTruncated": len(estimate_rows) > table_limit,
            "migration": migration,
            "rowDataReturned": False,
            "mutationPerformed": False,
            "secretValuesExposed": False,
        }

    @staticmethod
    def _validate_host_id(host_id: str) -> str:
        value = str(host_id or "").strip()
        if value and not _UUID_RE.fullmatch(value):
            raise ValueError("host_id must be a UUID")
        return value

    @staticmethod
    def _validate_run_id(run_id: str) -> str:
        value = str(run_id or "").strip()
        if value and not _UUID_RE.fullmatch(value):
            raise ValueError("run_id must be a UUID")
        return value

    @staticmethod
    def _validate_status(status: str) -> str:
        value = str(status or "").strip()
        if value and not _STATUS_RE.fullmatch(value):
            raise ValueError("status is invalid")
        return value

    def query(
        self,
        *,
        view: str,
        limit: int = 50,
        host_id: str = "",
        status: str = "",
    ) -> dict[str, Any]:
        query_view = str(view or "").strip()
        row_limit = _bounded_int(limit, 1, MAX_QUERY_ROWS, 50)
        try:
            selected_host = self._validate_host_id(host_id)
            selected_status = self._validate_status(status)
        except ValueError as exc:
            return {"ok": False, "status": "BLOCKED", "blocker": str(exc)}

        host_filter = f" AND h.id = {_sql_literal(selected_host)}" if selected_host else ""
        run_status = f" AND pr.status = {_sql_literal(selected_status)}" if selected_status else ""
        host_status = f" AND h.status = {_sql_literal(selected_status)}" if selected_status else ""
        alert_status = ""
        if query_view == "alerts" and selected_status:
            if selected_status not in {"active", "resolved"}:
                return {
                    "ok": False,
                    "status": "BLOCKED",
                    "blocker": "alerts accepts status active or resolved",
                }
            alert_status = " AND a.is_active = " + ("TRUE" if selected_status == "active" else "FALSE")

        queries = {
            "fleet_summary": """
SELECT
  (SELECT COUNT(*) FROM hosts) AS hosts_total,
  (SELECT COUNT(*) FROM hosts WHERE status = 'active') AS hosts_active,
  (SELECT COUNT(*) FROM hosts WHERE needs_reboot IS TRUE) AS hosts_needing_reboot,
  (SELECT COUNT(DISTINCT host_id) FROM host_packages WHERE needs_update IS TRUE) AS hosts_needing_updates,
  (SELECT COUNT(*) FROM host_packages WHERE needs_update IS TRUE) AS pending_packages,
  (SELECT COUNT(*) FROM host_packages WHERE needs_update IS TRUE AND is_security_update IS TRUE) AS pending_security_packages,
  (SELECT COUNT(*) FROM patch_runs WHERE status IN ('queued','running','scheduled','pending_validation','pending_approval')) AS patch_runs_active_or_waiting,
  (SELECT COUNT(*) FROM patch_runs WHERE status IN ('failed','validation_failed')) AS patch_runs_failed,
  (SELECT COUNT(*) FROM alerts WHERE is_active IS TRUE) AS active_alerts,
  (SELECT COUNT(*) FROM docker_containers) AS docker_containers_observed,
  (SELECT COUNT(*) FROM docker_images) AS docker_images_observed,
  (SELECT COUNT(*) FROM docker_networks) AS docker_networks_observed,
  (SELECT COUNT(*) FROM docker_volumes) AS docker_volumes_observed
""".strip(),
            "hosts": f"""
SELECT h.id, h.friendly_name, h.hostname, h.ip, h.os_type, h.os_version,
       h.architecture, h.status, h.last_update, h.needs_reboot,
       h.docker_enabled, h.compliance_enabled, h.agent_version,
       COUNT(hp.id) FILTER (WHERE hp.needs_update IS TRUE) AS pending_updates,
       COUNT(hp.id) FILTER (WHERE hp.needs_update IS TRUE AND hp.is_security_update IS TRUE) AS security_updates
FROM hosts h
LEFT JOIN host_packages hp ON hp.host_id = h.id
WHERE TRUE{host_filter}{host_status}
GROUP BY h.id
ORDER BY security_updates DESC, pending_updates DESC, h.friendly_name
LIMIT {row_limit}
""".strip(),
            "pending_updates": f"""
SELECT h.id AS host_id, h.friendly_name, h.hostname, p.name AS package_name,
       hp.current_version, hp.available_version, hp.is_security_update,
       hp.last_checked
FROM host_packages hp
JOIN hosts h ON h.id = hp.host_id
JOIN packages p ON p.id = hp.package_id
WHERE hp.needs_update IS TRUE{host_filter}
ORDER BY hp.is_security_update DESC, h.friendly_name, p.name
LIMIT {row_limit}
""".strip(),
            "patch_runs": f"""
SELECT pr.id, pr.host_id, h.friendly_name, h.hostname, pr.patch_type,
       pr.package_name, pr.status, pr.dry_run, pr.scheduled_at,
       pr.started_at, pr.completed_at, LEFT(COALESCE(pr.error_message, ''), 500) AS error_message,
       pr.validation_run_id, pr.created_at, pr.updated_at
FROM patch_runs pr
JOIN hosts h ON h.id = pr.host_id
WHERE TRUE{host_filter}{run_status}
ORDER BY pr.created_at DESC
LIMIT {row_limit}
""".strip(),
            "docker_assets": f"""
SELECT * FROM (
  SELECT 'container' AS asset_type, dc.host_id, h.friendly_name,
         dc.container_id AS external_id, dc.name,
         dc.image_name || ':' || dc.image_tag AS reference,
         dc.status AS state, dc.last_checked
  FROM docker_containers dc
  JOIN hosts h ON h.id = dc.host_id
  WHERE TRUE{host_filter}
  UNION ALL
  SELECT DISTINCT 'image' AS asset_type, dc.host_id, h.friendly_name,
         di.image_id AS external_id, di.repository || ':' || di.tag AS name,
         COALESCE(di.digest, '') AS reference,
         di.source AS state, di.last_checked
  FROM docker_images di
  LEFT JOIN docker_containers dc ON dc.image_id = di.id
  LEFT JOIN hosts h ON h.id = dc.host_id
  WHERE TRUE{host_filter}
  UNION ALL
  SELECT 'network' AS asset_type, dn.host_id, h.friendly_name,
         dn.network_id AS external_id, dn.name, dn.driver AS reference,
         CASE WHEN dn.internal THEN 'internal' ELSE dn.scope END AS state,
         dn.last_checked
  FROM docker_networks dn
  JOIN hosts h ON h.id = dn.host_id
  WHERE TRUE{host_filter}
  UNION ALL
  SELECT 'volume' AS asset_type, dv.host_id, h.friendly_name,
         dv.volume_id AS external_id, dv.name, dv.driver AS reference,
         dv.scope AS state, dv.last_checked
  FROM docker_volumes dv
  JOIN hosts h ON h.id = dv.host_id
  WHERE TRUE{host_filter}
) assets
ORDER BY asset_type, friendly_name, name
LIMIT {row_limit}
""".strip(),
            "alerts": f"""
SELECT a.id, a.type, a.severity, a.title,
       LEFT(COALESCE(a.message, ''), 500) AS message,
       a.is_active, a.resolved_at, a.created_at, a.updated_at
FROM alerts a
WHERE TRUE{alert_status}
ORDER BY a.is_active DESC, a.created_at DESC
LIMIT {row_limit}
""".strip(),
            "compliance": f"""
SELECT cs.id, cs.host_id, h.friendly_name, cs.status, cs.started_at,
       cs.completed_at, cs.total_rules, cs.passed, cs.failed, cs.warnings,
       cs.score, LEFT(COALESCE(cs.error_message, ''), 500) AS error_message
FROM compliance_scans cs
JOIN hosts h ON h.id = cs.host_id
WHERE TRUE{host_filter}
ORDER BY cs.started_at DESC
LIMIT {row_limit}
""".strip(),
        }
        if query_view not in queries:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "view is not allowlisted",
                "allowedViews": sorted(queries),
                "arbitrarySqlAccepted": False,
            }
        if selected_status and query_view not in {"hosts", "patch_runs", "alerts"}:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": f"status is not supported for {query_view}",
            }

        result = self._psql(queries[query_view], max_rows=row_limit)
        return {
            **result,
            "status": "PATCHMON_QUERY_COMPLETED" if result.get("ok") else result.get("status"),
            "view": query_view,
            "filters": {
                "hostId": selected_host or None,
                "status": selected_status or None,
                "limit": row_limit,
            },
            "arbitrarySqlAccepted": False,
            "mutationPerformed": False,
            "secretValuesExposed": False,
        }

    def brain_snapshot(self, *, include_fleet: bool = True) -> dict[str, Any]:
        runtime = self.runtime_inventory(include_fleet=include_fleet)
        summary = self.query(view="fleet_summary", limit=1)
        risks: list[dict[str, Any]] = []

        present = int(runtime.get("counts", {}).get("present") or 0)
        if present == 0:
            risks.append(
                {
                    "severity": "critical",
                    "code": "PATCHMON_STACK_NOT_DEPLOYED",
                    "evidence": list(PATCHMON_CONTAINERS),
                }
            )
        else:
            for name, state in runtime.get("containers", {}).items():
                if not state.get("present") or not state.get("state", {}).get("running"):
                    risks.append(
                        {
                            "severity": "critical",
                            "code": "PATCHMON_CONTAINER_NOT_RUNNING",
                            "container": name,
                        }
                    )
                elif state.get("state", {}).get("health") == "unhealthy":
                    risks.append(
                        {
                            "severity": "high",
                            "code": "PATCHMON_CONTAINER_UNHEALTHY",
                            "container": name,
                        }
                    )
        for violation in runtime.get("boundaryViolations", []):
            risks.append(
                {
                    "severity": "critical",
                    "code": str(violation.get("code") or "RUNTIME_BOUNDARY_VIOLATION"),
                    "evidence": violation,
                }
            )
        if not summary.get("ok"):
            risks.append(
                {
                    "severity": "critical" if present else "high",
                    "code": "PATCHMON_DATABASE_UNAVAILABLE",
                    "evidence": summary.get("status"),
                }
            )

        summary_row = summary.get("rows", [{}])[0] if summary.get("rows") else {}
        if summary_row:
            try:
                failed_runs = int(summary_row.get("patch_runs_failed") or 0)
                security_updates = int(summary_row.get("pending_security_packages") or 0)
                active_alerts = int(summary_row.get("active_alerts") or 0)
            except (TypeError, ValueError):
                failed_runs = security_updates = active_alerts = 0
            if failed_runs:
                risks.append({"severity": "high", "code": "PATCH_RUN_FAILURES_PRESENT", "count": failed_runs})
            if security_updates:
                risks.append({"severity": "high", "code": "SECURITY_UPDATES_PENDING", "count": security_updates})
            if active_alerts:
                risks.append({"severity": "medium", "code": "ACTIVE_ALERTS_PRESENT", "count": active_alerts})

        if present == 0:
            status = "PATCHMON_BRAIN_NOT_DEPLOYED"
        elif any(item["severity"] == "critical" for item in risks):
            status = "PATCHMON_BRAIN_DEGRADED"
        else:
            status = "PATCHMON_BRAIN_READY"
        return {
            "ok": status == "PATCHMON_BRAIN_READY",
            "status": status,
            "runtime": runtime,
            "databaseSummary": summary,
            "risks": risks,
            "riskCounts": {
                severity: sum(1 for item in risks if item.get("severity") == severity)
                for severity in ("critical", "high", "medium", "low")
            },
            "causalNextActions": [
                "Deploy or reconcile only the fixed patchmon-sovereign template after confirming its exact bundle hash"
                if present == 0
                else "Resolve critical runtime and network-boundary evidence before patch execution",
                "Provision a root-only short-lived PatchMon admin JWT outside the MCP container before enabling API mutations",
                "Create pending-approval runs first; approve a run only after reading its current validation evidence",
            ],
            "patchCompletionClaimed": False,
            "mutationPerformed": False,
            "secretValuesExposed": False,
        }

    def _token_metadata(self) -> dict[str, Any]:
        path = self.token_file
        try:
            if path.is_symlink():
                return {"ready": False, "status": "TOKEN_FILE_SYMLINK_BLOCKED"}
            resolved = path.resolve(strict=False)
            root = PATCHMON_TOKEN_ROOT.resolve(strict=False)
            if resolved != root and root not in resolved.parents:
                return {"ready": False, "status": "TOKEN_FILE_OUTSIDE_PATCHMON_ROOT"}
            info = path.stat()
        except FileNotFoundError:
            return {"ready": False, "status": "TOKEN_FILE_MISSING", "path": str(path)}
        except OSError as exc:
            return {"ready": False, "status": "TOKEN_FILE_UNREADABLE", "failureFamily": type(exc).__name__}
        mode = stat.S_IMODE(info.st_mode)
        if not stat.S_ISREG(info.st_mode):
            return {"ready": False, "status": "TOKEN_FILE_NOT_REGULAR"}
        if info.st_uid != 0:
            return {"ready": False, "status": "TOKEN_FILE_OWNER_INVALID", "ownerUid": info.st_uid}
        if mode & 0o077:
            return {"ready": False, "status": "TOKEN_FILE_MODE_TOO_OPEN", "mode": oct(mode)}
        if info.st_size <= 20 or info.st_size > 16_384:
            return {"ready": False, "status": "TOKEN_FILE_SIZE_INVALID", "bytes": info.st_size}
        return {
            "ready": True,
            "status": "TOKEN_FILE_READY",
            "path": str(path),
            "mode": oct(mode),
            "bytes": info.st_size,
        }

    def _read_admin_token(self) -> str:
        metadata = self._token_metadata()
        if not metadata.get("ready"):
            raise RuntimeError(str(metadata.get("status") or "TOKEN_FILE_NOT_READY"))
        token = self.token_file.read_text("utf-8").strip()
        if not _JWT_RE.fullmatch(token):
            raise RuntimeError("TOKEN_FILE_CONTENT_INVALID")
        return token

    def _target_state(self, action: str, host_id: str, run_id: str) -> dict[str, Any]:
        if action in {"validate_packages", "submit_for_approval"}:
            result = self._psql(
                f"""
SELECT id, friendly_name, hostname, status, last_update, needs_reboot
FROM hosts
WHERE id = {_sql_literal(host_id)}
LIMIT 1
""".strip(),
                max_rows=1,
            )
            if not result.get("ok") or not result.get("rows"):
                raise RuntimeError("PATCHMON_HOST_NOT_FOUND_OR_DATABASE_UNAVAILABLE")
            return result["rows"][0]
        result = self._psql(
            f"""
SELECT pr.id, pr.host_id, pr.patch_type, pr.package_name, pr.package_names,
       pr.status, pr.dry_run, pr.scheduled_at, pr.started_at, pr.completed_at,
       pr.validation_run_id, pr.updated_at, h.friendly_name, h.status AS host_status,
       h.last_update
FROM patch_runs pr
JOIN hosts h ON h.id = pr.host_id
WHERE pr.id = {_sql_literal(run_id)}
LIMIT 1
""".strip(),
            max_rows=1,
        )
        if not result.get("ok") or not result.get("rows"):
            raise RuntimeError("PATCHMON_RUN_NOT_FOUND_OR_DATABASE_UNAVAILABLE")
        state = result["rows"][0]
        if action == "approve_run" and state.get("status") not in {
            "validated",
            "pending_validation",
            "pending_approval",
        }:
            raise RuntimeError("PATCHMON_RUN_NOT_APPROVABLE")
        if action == "retry_validation" and (
            state.get("status") != "pending_validation"
            or state.get("patch_type") != "patch_package"
        ):
            raise RuntimeError("PATCHMON_RUN_NOT_RETRYABLE")
        if action == "stop_run" and state.get("status") != "running":
            raise RuntimeError("PATCHMON_RUN_NOT_RUNNING")
        return state

    def patch_action_plan(
        self,
        *,
        action: str,
        host_id: str = "",
        run_id: str = "",
        patch_type: str = "patch_all",
        package_names: list[str] | None = None,
        schedule_override: str = "",
    ) -> dict[str, Any]:
        selected_action = str(action or "").strip()
        if selected_action not in _ALLOWED_PATCH_ACTIONS:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "action is not allowlisted",
                "allowedActions": sorted(_ALLOWED_PATCH_ACTIONS),
            }
        try:
            selected_host = self._validate_host_id(host_id)
            selected_run = self._validate_run_id(run_id)
        except ValueError as exc:
            return {"ok": False, "status": "BLOCKED", "blocker": str(exc)}
        selected_patch_type = str(patch_type or "patch_all").strip()
        if selected_patch_type not in {"patch_all", "patch_package"}:
            return {"ok": False, "status": "BLOCKED", "blocker": "patch_type must be patch_all or patch_package"}
        override = str(schedule_override or "").strip()
        if override not in {"", "immediate"}:
            return {"ok": False, "status": "BLOCKED", "blocker": "schedule_override must be empty or immediate"}
        if override and selected_action != "approve_run":
            return {"ok": False, "status": "BLOCKED", "blocker": "schedule_override is only supported for approve_run"}

        packages = sorted({str(item or "").strip() for item in (package_names or []) if str(item or "").strip()})
        if len(packages) > 100 or any(not _PACKAGE_RE.fullmatch(item) for item in packages):
            return {"ok": False, "status": "BLOCKED", "blocker": "package_names must contain at most 100 valid package names"}

        if selected_action in {"validate_packages", "submit_for_approval"}:
            if not selected_host:
                return {"ok": False, "status": "BLOCKED", "blocker": "host_id is required"}
            if selected_patch_type == "patch_package" and not packages:
                return {"ok": False, "status": "BLOCKED", "blocker": "patch_package requires package_names"}
            if selected_action == "validate_packages" and selected_patch_type != "patch_package":
                return {"ok": False, "status": "BLOCKED", "blocker": "validate_packages only supports patch_package"}
        elif not selected_run:
            return {"ok": False, "status": "BLOCKED", "blocker": "run_id is required"}

        try:
            current_state = self._target_state(selected_action, selected_host, selected_run)
        except RuntimeError as exc:
            return {"ok": False, "status": "BLOCKED", "blocker": str(exc)}

        if selected_action in {"validate_packages", "submit_for_approval"}:
            endpoint = "/api/v1/patching/trigger"
            body: dict[str, Any] = {
                "host_id": selected_host,
                "patch_type": selected_patch_type,
                "dry_run": selected_action == "validate_packages",
                "pending_approval": selected_action == "submit_for_approval",
            }
            if packages:
                body["package_names"] = packages
        else:
            suffix = {
                "approve_run": "approve",
                "retry_validation": "retry-validation",
                "stop_run": "stop",
            }[selected_action]
            endpoint = f"/api/v1/patching/runs/{selected_run}/{suffix}"
            body = {"schedule_override": override} if selected_action == "approve_run" and override else {}

        impact = {
            "validate_packages": "agent_dry_run_only",
            "submit_for_approval": "creates_pending_approval_without_host_execution",
            "approve_run": "queues_real_package_mutation_on_target_host",
            "retry_validation": "requeues_agent_dry_run",
            "stop_run": "requests_stop_for_existing_patch_run",
        }[selected_action]
        plan_core = {
            "schemaVersion": "sovereign.patchmon-action-plan.v1",
            "action": selected_action,
            "method": "POST",
            "endpoint": endpoint,
            "requestBody": body,
            "currentState": current_state,
            "impact": impact,
        }
        confirmation = _sha256_json(plan_core)
        token_metadata = self._token_metadata()
        write_enabled = (
            os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() == "1"
            and os.getenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "0").strip() == "1"
        )
        return {
            "ok": True,
            "status": "PATCHMON_ACTION_PLAN_READY",
            **plan_core,
            "confirmationSha256": confirmation,
            "requiresExactConfirmation": True,
            "writeEnabled": write_enabled,
            "adminCredential": token_metadata,
            "readyToApply": write_enabled and bool(token_metadata.get("ready")),
            "arbitraryEndpointAccepted": False,
            "arbitraryCommandAccepted": False,
            "directDatabaseMutationUsed": False,
            "mutationPerformed": False,
            "secretValuesExposed": False,
        }

    def _api_request(self, method: str, endpoint: str, body: dict[str, Any], token: str) -> dict[str, Any]:
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        connection: http.client.HTTPConnection | None = None
        try:
            connection = http.client.HTTPConnection(
                PATCHMON_LOOPBACK_HOST,
                PATCHMON_LOOPBACK_PORT,
                timeout=30,
            )
            connection.request(
                method,
                endpoint,
                body=encoded,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Content-Length": str(len(encoded)),
                    "X-Forwarded-Host": f"127.0.0.1:{PATCHMON_LOOPBACK_PORT}",
                },
            )
            response = connection.getresponse()
            payload = response.read(64_000)
            try:
                decoded: Any = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                decoded = {
                    "bodySha256": hashlib.sha256(payload).hexdigest(),
                    "bodyBytes": len(payload),
                }
            return {
                "ok": 200 <= response.status < 300,
                "httpStatus": int(response.status),
                "response": self._redact(decoded),
                "responseBytes": len(payload),
            }
        except (OSError, http.client.HTTPException) as exc:
            return {
                "ok": False,
                "httpStatus": None,
                "failureFamily": type(exc).__name__,
                "response": {},
            }
        finally:
            if connection is not None:
                connection.close()

    def patch_action_apply(
        self,
        *,
        action: str,
        confirmation_sha256: str,
        host_id: str = "",
        run_id: str = "",
        patch_type: str = "patch_all",
        package_names: list[str] | None = None,
        schedule_override: str = "",
    ) -> dict[str, Any]:
        if os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Private Owner Mode is not active"}
        if os.getenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "0").strip() != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "PatchMon patch writes are not enabled"}
        plan = self.patch_action_plan(
            action=action,
            host_id=host_id,
            run_id=run_id,
            patch_type=patch_type,
            package_names=package_names,
            schedule_override=schedule_override,
        )
        if not plan.get("ok"):
            return plan
        if not re.fullmatch(r"[0-9a-f]{64}", str(confirmation_sha256 or "")):
            return {"ok": False, "status": "BLOCKED", "blocker": "confirmation_sha256 is invalid"}
        if confirmation_sha256 != plan.get("confirmationSha256"):
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "PatchMon action plan hash does not match current state",
                "expected": plan.get("confirmationSha256"),
            }
        try:
            token = self._read_admin_token()
        except (OSError, UnicodeError, RuntimeError) as exc:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": str(exc),
                "secretValuesExposed": False,
            }

        result = self._api_request(
            str(plan["method"]),
            str(plan["endpoint"]),
            dict(plan["requestBody"]),
            token,
        )
        accepted = bool(result.get("ok"))
        return {
            "ok": accepted,
            "status": "PATCHMON_ACTION_ACCEPTED" if accepted else "PATCHMON_ACTION_REJECTED",
            "action": plan.get("action"),
            "impact": plan.get("impact"),
            "confirmationSha256": confirmation_sha256,
            "httpStatus": result.get("httpStatus"),
            "response": result.get("response"),
            "failureFamily": result.get("failureFamily"),
            "mutationPerformed": accepted,
            "patchCompletionClaimed": False,
            "nextAction": (
                "Read patch_runs for the returned run id until terminal evidence is present"
                if accepted
                else "Inspect the bounded HTTP status and PatchMon runtime evidence before retrying"
            ),
            "secretValuesExposed": False,
        }

    @staticmethod
    def tool_inventory() -> dict[str, Any]:
        return {
            "ok": True,
            "status": "PATCHMON_OPERATOR_TOOLS_REGISTERED",
            "tools": [
                {"name": "patchmon_runtime_inventory", "mutation": False, "source": "Docker host broker"},
                {"name": "patchmon_database_inventory", "mutation": False, "source": "PatchMon PostgreSQL metadata"},
                {"name": "patchmon_query", "mutation": False, "source": "fixed secret-safe SQL views"},
                {"name": "patchmon_brain_snapshot", "mutation": False, "source": "runtime plus database evidence"},
                {"name": "patchmon_patch_action_plan", "mutation": False, "source": "current DB state plus official API contract"},
                {"name": "patchmon_patch_action_apply", "mutation": True, "source": "official PatchMon HTTP API via host queue"},
            ],
            "boundaries": {
                "dockerSocketMountedInMcp": False,
                "genericShellAccepted": False,
                "arbitrarySqlAccepted": False,
                "arbitraryHttpEndpointAccepted": False,
                "mutationTransport": "host_command_queue_only",
                "adminCredentialLocation": "root_only_host_file",
                "externalPatchmonPortRequired": False,
            },
            "mutationPerformed": False,
            "secretValuesExposed": False,
        }
