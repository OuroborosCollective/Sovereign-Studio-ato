from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import secrets
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from litellm_stack import LiteLLMStackRuntime


@dataclass(frozen=True)
class ManagedStack:
    stack_id: str
    project_name: str
    anchor_container: str
    expected_containers: tuple[str, ...]
    allowed_services: tuple[str, ...]
    deploy_root: str
    template_name: str
    allowed_networks: tuple[str, ...]
    allowed_bind_roots: tuple[str, ...]
    allowed_published_ports: tuple[str, ...] = ()


STACKS: dict[str, ManagedStack] = {
    "sovereign-litellm": ManagedStack(
        stack_id="sovereign-litellm",
        project_name="sovereign-litellm",
        anchor_container="sovereign-litellm-litellm-1",
        expected_containers=("sovereign-litellm-litellm-1", "sovereign-litellm-db-1"),
        allowed_services=("litellm", "db"),
        deploy_root="/opt/sovereign-litellm",
        template_name="sovereign-litellm",
        allowed_networks=("sovereign-private",),
        allowed_bind_roots=("/opt/sovereign-litellm",),
    ),
    "sovereign-backend": ManagedStack(
        stack_id="sovereign-backend",
        project_name="sovereign-backend",
        anchor_container="sovereign-backend",
        expected_containers=("sovereign-backend",),
        allowed_services=("sovereign-backend",),
        deploy_root="/opt/sovereign-backend",
        template_name="sovereign-backend",
        allowed_networks=("sovereign-private", "supabase_default"),
        allowed_bind_roots=("/opt/sovereign-backend", "/opt/secure", "/opt/sovereign-owner-managed"),
        allowed_published_ports=("127.0.0.1:8788:8787",),
    ),
    "gpt-tools": ManagedStack(
        stack_id="gpt-tools",
        project_name="gpt-tools",
        anchor_container="gpt-browserless",
        expected_containers=("gpt-browserless", "gpt-tika", "gpt-gotenberg", "gpt-dozzle"),
        allowed_services=("browserless", "tika", "gotenberg", "dozzle"),
        deploy_root="/opt/gpt-tools",
        template_name="gpt-tools",
        allowed_networks=("mcp-proxy",),
        allowed_bind_roots=("/opt/gpt-tools",),
        allowed_published_ports=(
            "127.0.0.1:3000:3000",
            "127.0.0.1:9998:9998",
            "127.0.0.1:3001:3000",
            "127.0.0.1:8081:8080",
        ),
    ),
    "code-server-46bq": ManagedStack(
        stack_id="code-server-46bq",
        project_name="code-server-46bq",
        anchor_container="code-server-46bq-code-server-1",
        expected_containers=("code-server-46bq-code-server-1",),
        allowed_services=("code-server",),
        deploy_root="/opt/code-server-46bq",
        template_name="code-server-46bq",
        allowed_networks=("default", "code-server-46bq_default", "sovereign-private"),
        allowed_bind_roots=("/opt/code-server-46bq",),
        allowed_published_ports=("127.0.0.1:32782:8443", "32782:8443"),
    ),
    "pgbackweb-wq5r": ManagedStack(
        stack_id="pgbackweb-wq5r",
        project_name="pgbackweb-wq5r",
        anchor_container="pgbackweb-wq5r-pgbackweb-1",
        expected_containers=("pgbackweb-wq5r-pgbackweb-1", "pgbackweb-wq5r-db-1"),
        allowed_services=("pgbackweb", "db"),
        deploy_root="/opt/pgbackweb-wq5r",
        template_name="pgbackweb-wq5r",
        allowed_networks=("default",),
        allowed_bind_roots=("/opt/pgbackweb-wq5r",),
        allowed_published_ports=("127.0.0.1:32829:8085",),
    ),
    "patchmon-sovereign": ManagedStack(
        stack_id="patchmon-sovereign",
        project_name="patchmon-sovereign",
        anchor_container="patchmon-sovereign-server-1",
        expected_containers=(
            "patchmon-sovereign-server-1",
            "patchmon-sovereign-database-1",
            "patchmon-sovereign-redis-1",
            "patchmon-sovereign-guacd-1",
        ),
        allowed_services=("server", "database", "redis", "guacd"),
        deploy_root="/opt/patchmon-sovereign",
        template_name="patchmon-sovereign",
        allowed_networks=("patchmon-internal", "patchmon-edge"),
        allowed_bind_roots=("/opt/patchmon-sovereign",),
        allowed_published_ports=("127.0.0.1:32830:3000",),
    ),
}

FORBIDDEN_BIND_SOURCES = {
    "/",
    "/boot",
    "/dev",
    "/etc",
    "/proc",
    "/root",
    "/run/docker.sock",
    "/sys",
    "/var/run/docker.sock",
}
MAX_TEMPLATE_FILES = 20
MAX_TEMPLATE_BYTES = 500_000
MAX_STACK_ENV_BYTES = 64_000
_SECRET_VALUE_RE = re.compile(r"^[A-Za-z0-9_-]{32,160}$")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class ManagedComposeRuntime:
    """Manage fixed, installed Compose templates for a strict stack allowlist."""

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        template_root: str | None = None,
    ) -> None:
        self._runner = runner or subprocess.run
        self.template_root = Path(
            template_root
            or os.getenv("SOVEREIGN_COMPOSE_TEMPLATE_ROOT", "/opt/sovereign-chatgpt-tools/templates")
        )
        self.litellm = LiteLLMStackRuntime(
            runner=self._runner,
            template_root=str(self.template_root / "sovereign-litellm"),
            deploy_root=STACKS["sovereign-litellm"].deploy_root,
        )

    def _run(self, argv: list[str], timeout: int = 120) -> dict[str, Any]:
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
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-24_000:],
            "stderr": completed.stderr[-24_000:],
        }

    @staticmethod
    def _stack(stack_id: str) -> ManagedStack:
        stack = STACKS.get(str(stack_id or "").strip())
        if stack is None:
            raise ValueError("Compose-Stack ist nicht freigegeben")
        return stack

    def _inspect(self, container: str) -> dict[str, Any]:
        result = self._run(
            [
                "docker",
                "inspect",
                "--format",
                "{{json .State}}|{{json .Config.Labels}}|{{json .NetworkSettings.Networks}}|{{json .NetworkSettings.Ports}}",
                container,
            ],
            timeout=30,
        )
        if not result["ok"]:
            return {"present": False, "container": container}
        try:
            state_raw, labels_raw, networks_raw, ports_raw = result["stdout"].strip().split("|", 3)
            state = json.loads(state_raw)
            labels = json.loads(labels_raw) or {}
            networks = json.loads(networks_raw) or {}
            ports = json.loads(ports_raw) or {}
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Docker-Inspect ist ungültig: {container}: {exc}") from exc
        published = {
            key: value
            for key, value in ports.items()
            if isinstance(value, list) and value
        }
        return {
            "present": True,
            "container": container,
            "running": bool(state.get("Running")),
            "status": str(state.get("Status") or "unknown"),
            "health": str((state.get("Health") or {}).get("Status") or "none"),
            "project": str(labels.get("com.docker.compose.project") or ""),
            "service": str(labels.get("com.docker.compose.service") or ""),
            "workingDir": str(labels.get("com.docker.compose.project.working_dir") or ""),
            "configFiles": str(labels.get("com.docker.compose.project.config_files") or ""),
            "networks": sorted(networks.keys()),
            "publishedPorts": published,
        }

    def _template_files(self, stack: ManagedStack) -> tuple[list[tuple[str, bytes]], str]:
        root = self.template_root / stack.template_name
        if self.template_root.is_symlink() or root.is_symlink() or not root.is_dir():
            return [], ""
        files: list[tuple[str, bytes]] = []
        for path in sorted(root.iterdir()):
            if path.is_symlink() or not path.is_file():
                raise RuntimeError(f"Ungültiger Template-Eintrag: {path.name}")
            if path.name.startswith(".") or path.name in {"env", ".env"}:
                raise RuntimeError("Compose-Templates dürfen keine Secret-Dateien enthalten")
            payload = path.read_bytes()
            if len(payload) > MAX_TEMPLATE_BYTES:
                raise RuntimeError(f"Template-Datei ist zu groß: {path.name}")
            files.append((path.name, payload))
        if len(files) > MAX_TEMPLATE_FILES:
            raise RuntimeError("Zu viele Compose-Template-Dateien")
        if not any(name in {"docker-compose.yml", "compose.yml", "compose.yaml"} for name, _ in files):
            return [], ""
        digest = hashlib.sha256()
        for name, payload in files:
            digest.update(name.encode("utf-8") + b"\0")
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
        return files, digest.hexdigest()

    def plan(self, stack_id: str) -> dict[str, Any]:
        stack = self._stack(stack_id)
        if stack.stack_id == "sovereign-litellm":
            special = self.litellm.plan()
            compose_sha = str(special.get("templates", {}).get("docker-compose.yml", {}).get("sha256") or "")
            config_sha = str(special.get("templates", {}).get("config.yaml", {}).get("sha256") or "")
            entrypoint_sha = str(special.get("templates", {}).get("sovereign-entrypoint.py", {}).get("sha256") or "")
            bundle_sha = (
                _sha256(f"{compose_sha}:{config_sha}:{entrypoint_sha}".encode("ascii"))
                if compose_sha and config_sha and entrypoint_sha
                else ""
            )
            return {
                **special,
                "stackId": stack.stack_id,
                "anchor": self._inspect(stack.anchor_container),
                "templateBundleSha256": bundle_sha,
                "acceptedInputs": ["stack_id", "confirmation_sha256"],
                "allowedStacks": sorted(STACKS),
            }
        files, bundle_sha = self._template_files(stack)
        return {
            "ok": True,
            "status": "PLAN_READY" if files else "TEMPLATE_NOT_REGISTERED",
            "stackId": stack.stack_id,
            "project": stack.project_name,
            "anchor": self._inspect(stack.anchor_container),
            "expectedContainers": list(stack.expected_containers),
            "deployRoot": stack.deploy_root,
            "templateRegistered": bool(files),
            "templateFiles": [
                {"name": name, "sha256": _sha256(payload), "bytes": len(payload)}
                for name, payload in files
            ],
            "templateBundleSha256": bundle_sha,
            "acceptedInputs": ["stack_id", "confirmation_sha256"],
            "composeWriteEnabled": (
                os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() == "1"
                and os.getenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "0").strip() == "1"
            ),
            "allowedStacks": sorted(STACKS),
            "arbitraryYamlAccepted": False,
            "arbitraryCommandAccepted": False,
            "secretValuesAccepted": False,
            "secretProvisioning": (
                "generated_on_confirmed_deploy"
                if stack.stack_id in {"pgbackweb-wq5r", "patchmon-sovereign"}
                else "external_or_not_required"
            ),
        }

    @staticmethod
    def _volume_source(volume: Any) -> str:
        if isinstance(volume, dict):
            return str(volume.get("source") or "")
        if isinstance(volume, str):
            return volume.split(":", 1)[0]
        return ""

    @staticmethod
    def _published_port_strings(ports: Any) -> set[str]:
        values: set[str] = set()
        for port in ports if isinstance(ports, list) else []:
            if isinstance(port, str):
                values.add(port)
                continue
            if not isinstance(port, dict):
                continue
            target = str(port.get("target") or "")
            published = str(port.get("published") or "")
            host_ip = str(port.get("host_ip") or "")
            if not target or not published:
                continue
            values.add(f"{host_ip + ':' if host_ip else ''}{published}:{target}")
        return values

    def _validate_rendered(self, stack: ManagedStack, rendered: dict[str, Any]) -> None:
        services = rendered.get("services")
        if not isinstance(services, dict) or not services:
            raise RuntimeError("Compose enthält keine Services")
        unknown = sorted(set(services) - set(stack.allowed_services))
        if unknown:
            raise RuntimeError("Nicht freigegebene Compose-Services: " + ", ".join(unknown))
        networks = rendered.get("networks") if isinstance(rendered.get("networks"), dict) else {}
        unknown_networks = sorted(set(networks) - set(stack.allowed_networks))
        if unknown_networks:
            raise RuntimeError("Nicht freigegebene Compose-Netzwerke: " + ", ".join(unknown_networks))
        for service_name, service in services.items():
            if not isinstance(service, dict):
                raise RuntimeError(f"Service ist ungültig: {service_name}")
            if service.get("privileged"):
                raise RuntimeError(f"privileged ist gesperrt: {service_name}")
            if service.get("network_mode") == "host" or service.get("pid") == "host" or service.get("ipc") == "host":
                raise RuntimeError(f"Host-Namespace ist gesperrt: {service_name}")
            if service.get("devices") or service.get("cap_add"):
                raise RuntimeError(f"Geräte oder zusätzliche Capabilities sind gesperrt: {service_name}")
            if service.get("entrypoint") or service.get("build") or service.get("extra_hosts"):
                raise RuntimeError(f"Ausführungs-Override ist gesperrt: {service_name}")
            command = service.get("command")
            allowed_patchmon_redis_command = (
                stack.stack_id == "patchmon-sovereign"
                and service_name == "redis"
                and command == ["redis-server", "/usr/local/etc/redis/redis.conf"]
            )
            if command and not allowed_patchmon_redis_command:
                raise RuntimeError(f"Ausführungs-Override ist gesperrt: {service_name}")
            image = str(service.get("image") or "")
            if image and (image.endswith(":latest") or ":latest@" in image):
                raise RuntimeError(f"Unfixiertes latest-Image ist gesperrt: {service_name}")
            service_networks = service.get("networks")
            if isinstance(service_networks, dict):
                used_networks = set(service_networks)
            elif isinstance(service_networks, list):
                used_networks = {str(item) for item in service_networks}
            else:
                used_networks = set()
            forbidden_networks = sorted(used_networks - set(stack.allowed_networks))
            if forbidden_networks:
                raise RuntimeError(f"Service nutzt fremde Netzwerke: {service_name}")
            for volume in service.get("volumes") if isinstance(service.get("volumes"), list) else []:
                source = self._volume_source(volume)
                if not source or not source.startswith("/"):
                    continue
                resolved = str(Path(source).resolve())
                if resolved in FORBIDDEN_BIND_SOURCES or resolved.startswith("/var/run/docker.sock"):
                    raise RuntimeError(f"Gesperrter Bind-Mount: {service_name}")
                if not any(resolved == root or resolved.startswith(root.rstrip("/") + "/") for root in stack.allowed_bind_roots):
                    raise RuntimeError(f"Bind-Mount außerhalb der Stack-Grenzen: {service_name}: {resolved}")
            published = self._published_port_strings(service.get("ports"))
            forbidden_ports = sorted(published - set(stack.allowed_published_ports))
            if forbidden_ports:
                raise RuntimeError(f"Nicht freigegebene Portbindung: {service_name}: {', '.join(forbidden_ports)}")

    def _render_template(
        self,
        stack: ManagedStack,
        files: list[tuple[str, bytes]],
    ) -> tuple[Path, tempfile.TemporaryDirectory[str], dict[str, Any]]:
        temporary = tempfile.TemporaryDirectory(prefix=f"managed-compose-{stack.stack_id}-")
        root = Path(temporary.name)
        for name, payload in files:
            (root / name).write_bytes(payload)
        compose_path = next(
            root / name
            for name, _ in files
            if name in {"docker-compose.yml", "compose.yml", "compose.yaml"}
        )
        deploy_env = Path(stack.deploy_root) / ".env"
        env_path = deploy_env if deploy_env.is_file() and not deploy_env.is_symlink() else root / ".env"
        if env_path == root / ".env":
            env_path.write_text("", encoding="utf-8")
        result = self._run(
            [
                "docker",
                "compose",
                "--project-name",
                stack.project_name,
                "--project-directory",
                str(root),
                "--env-file",
                str(env_path),
                "--file",
                str(compose_path),
                "config",
                "--format",
                "json",
            ],
            timeout=60,
        )
        if not result["ok"]:
            temporary.cleanup()
            raise RuntimeError("Compose-Template kann nicht sicher gerendert werden")
        try:
            rendered = json.loads(result["stdout"])
        except json.JSONDecodeError as exc:
            temporary.cleanup()
            raise RuntimeError("Gerenderte Compose-Konfiguration ist kein JSON") from exc
        self._validate_rendered(stack, rendered)
        return compose_path, temporary, rendered

    @staticmethod
    def _write_atomic(path: Path, payload: bytes, mode: int = 0o640) -> None:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, mode)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _ensure_stack_secret_env(self, stack: ManagedStack) -> dict[str, Any]:
        if stack.stack_id not in {"pgbackweb-wq5r", "patchmon-sovereign"}:
            return {
                "required": False,
                "created": False,
                "secretValuesReturned": False,
            }

        deploy_root = Path(stack.deploy_root)
        if deploy_root.is_symlink():
            raise RuntimeError("Deploy-Root darf kein Symlink sein")
        deploy_root.mkdir(parents=True, exist_ok=True, mode=0o750)
        os.chmod(deploy_root, 0o750)
        env_path = deploy_root / ".env"
        if env_path.is_symlink() or (env_path.exists() and not env_path.is_file()):
            raise RuntimeError("Stack-Secret-Datei ist ungültig")

        existing_lines: list[str] = []
        values: dict[str, str] = {}
        if env_path.is_file():
            payload = env_path.read_bytes()
            if len(payload) > MAX_STACK_ENV_BYTES or b"\0" in payload:
                raise RuntimeError("Stack-Secret-Datei ist ungültig")
            existing_lines = payload.decode("utf-8").splitlines()
            for line in existing_lines:
                if not line or line.lstrip().startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()

        if stack.stack_id == "pgbackweb-wq5r":
            required_lengths = {
                "PG_BACKWEB_DB_PASSWORD": 64,
                "PG_BACKWEB_ENCRYPTION_KEY": 64,
            }
            fixed_values: dict[str, str] = {}
        else:
            required_lengths = {
                "POSTGRES_PASSWORD": 64,
                "REDIS_PASSWORD": 64,
                "JWT_SECRET": 128,
                "SESSION_SECRET": 128,
                "AI_ENCRYPTION_KEY": 64,
            }
            fixed_values = {
                "POSTGRES_HOST": "database",
                "POSTGRES_USER": "patchmon_user",
                "POSTGRES_DB": "patchmon_db",
                "REDIS_HOST": "redis",
                "REDIS_PORT": "6379",
                "REDIS_DB": "0",
                "GUACD_ADDRESS": "guacd:4822",
                "CORS_ORIGIN": "http://127.0.0.1:32830",
                "SERVER_PROTOCOL": "http",
                "SERVER_HOST": "127.0.0.1",
                "SERVER_PORT": "32830",
                "PORT": "3000",
                "APP_ENV": "production",
                "TRUST_PROXY": "false",
                "ENABLE_HSTS": "false",
                "TZ": "Europe/Berlin",
                "AGENT_UPDATE_BODY_LIMIT": "5mb",
            }

        for key, expected_length in required_lengths.items():
            current = values.get(key, "")
            if current and (not _SECRET_VALUE_RE.fullmatch(current) or len(current) != expected_length):
                raise RuntimeError(f"Vorhandenes {key} erfüllt den Secret-Vertrag nicht")

        created = False
        for key, expected_length in required_lengths.items():
            if not values.get(key):
                values[key] = secrets.token_hex(expected_length // 2)
                created = True

        if stack.stack_id == "patchmon-sovereign":
            fixed_values["DATABASE_URL"] = (
                "postgresql://patchmon_user:"
                + values["POSTGRES_PASSWORD"]
                + "@database:5432/patchmon_db"
            )

        managed_keys = tuple(required_lengths) + tuple(fixed_values)
        retained = [
            line
            for line in existing_lines
            if not any(line.startswith(key + "=") for key in managed_keys)
        ]
        rendered = retained + [f"{key}={values[key]}" for key in required_lengths]
        rendered.extend(f"{key}={value}" for key, value in fixed_values.items())
        self._write_atomic(env_path, ("\n".join(rendered).rstrip() + "\n").encode("utf-8"), mode=0o600)
        os.chmod(env_path, 0o600)

        additional_files: list[dict[str, Any]] = []
        if stack.stack_id == "patchmon-sovereign":
            redis_path = deploy_root / "redis.conf"
            redis_payload = (
                "appendonly yes\n"
                "protected-mode yes\n"
                "bind 0.0.0.0\n"
                "port 6379\n"
                f"requirepass {values['REDIS_PASSWORD']}\n"
            ).encode("utf-8")
            self._write_atomic(redis_path, redis_payload, mode=0o600)
            os.chmod(redis_path, 0o600)
            additional_files.append({"path": str(redis_path), "mode": "0600"})

        return {
            "required": True,
            "created": created,
            "path": str(env_path),
            "mode": "0600",
            "keysPresent": list(required_lengths),
            "managedNonSecretKeys": sorted(fixed_values),
            "additionalFiles": additional_files,
            "secretValuesReturned": False,
        }

    def _verify_expected(self, stack: ManagedStack) -> dict[str, Any]:
        states: dict[str, Any] = {}
        for _attempt in range(45):
            states = {container: self._inspect(container) for container in stack.expected_containers}
            if all(state.get("running") for state in states.values()):
                break
            time.sleep(2)
        return states

    @staticmethod
    def _patchmon_http_canary() -> dict[str, Any]:
        last_error = ""
        for _attempt in range(30):
            connection: http.client.HTTPConnection | None = None
            try:
                connection = http.client.HTTPConnection("127.0.0.1", 32830, timeout=5)
                connection.request("GET", "/")
                response = connection.getresponse()
                status = int(response.status)
                response.read(4096)
                if 200 <= status < 400:
                    return {
                        "ok": True,
                        "status": "PATCHMON_HTTP_READY",
                        "httpStatus": status,
                        "url": "http://127.0.0.1:32830/",
                        "responseBodyReturned": False,
                    }
                last_error = f"HTTP {status}"
            except (OSError, http.client.HTTPException) as exc:
                last_error = type(exc).__name__
            finally:
                if connection is not None:
                    connection.close()
            time.sleep(2)
        return {
            "ok": False,
            "status": "PATCHMON_HTTP_UNAVAILABLE",
            "errorFamily": last_error or "unknown",
            "responseBodyReturned": False,
        }

    def litellm_provider_model_inventory(self) -> dict[str, Any]:
        return self.litellm.provider_model_inventory()

    def openai_project_runtime_evidence(self) -> dict[str, Any]:
        return self.litellm.runtime_access_evidence()

    def activate_litellm_model_aliases(
        self,
        *,
        fast_provider_model: str,
        balanced_provider_model: str,
        confirmation_inventory_sha256: str,
    ) -> dict[str, Any]:
        return self.litellm.activate_model_aliases(
            fast_provider_model=fast_provider_model,
            balanced_provider_model=balanced_provider_model,
            confirmation_inventory_sha256=confirmation_inventory_sha256,
        )

    def deploy(self, stack_id: str, confirmation_sha256: str) -> dict[str, Any]:
        stack = self._stack(stack_id)
        if os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Private Owner Mode ist nicht aktiv"}
        if os.getenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "0").strip() != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Allowlistete Compose-Writes sind nicht aktiviert"}
        if stack.stack_id == "sovereign-litellm":
            special = self.litellm.plan()
            compose_sha = str(special.get("templates", {}).get("docker-compose.yml", {}).get("sha256") or "")
            config_sha = str(special.get("templates", {}).get("config.yaml", {}).get("sha256") or "")
            entrypoint_sha = str(special.get("templates", {}).get("sovereign-entrypoint.py", {}).get("sha256") or "")
            bundle_sha = (
                _sha256(f"{compose_sha}:{config_sha}:{entrypoint_sha}".encode("ascii"))
                if compose_sha and config_sha and entrypoint_sha
                else ""
            )
            if confirmation_sha256 != bundle_sha:
                return {"ok": False, "status": "BLOCKED", "blocker": "Template-Bundle-Hash stimmt nicht", "expected": bundle_sha}
            return self.litellm.deploy(
                confirmation_compose_sha256=compose_sha,
                confirmation_config_sha256=config_sha,
                confirmation_entrypoint_sha256=entrypoint_sha,
            )

        files, bundle_sha = self._template_files(stack)
        if not files:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": f"Für {stack.stack_id} ist noch kein geprüftes Compose-Template registriert",
            }
        if confirmation_sha256 != bundle_sha:
            return {"ok": False, "status": "BLOCKED", "blocker": "Template-Bundle-Hash stimmt nicht", "expected": bundle_sha}

        secret_env = self._ensure_stack_secret_env(stack)
        _compose_path, temporary, _rendered = self._render_template(stack, files)
        temporary.cleanup()
        deploy_root = Path(stack.deploy_root)
        if deploy_root.is_symlink():
            return {"ok": False, "status": "BLOCKED", "blocker": "Deploy-Root darf kein Symlink sein"}
        deploy_root.mkdir(parents=True, exist_ok=True, mode=0o750)
        os.chmod(deploy_root, 0o750)
        for name, payload in files:
            self._write_atomic(deploy_root / name, payload)
        compose_name = next(name for name, _ in files if name in {"docker-compose.yml", "compose.yml", "compose.yaml"})
        argv = [
            "docker",
            "compose",
            "--project-name",
            stack.project_name,
            "--project-directory",
            str(deploy_root),
        ]
        env_path = deploy_root / ".env"
        if env_path.is_file() and not env_path.is_symlink():
            argv.extend(["--env-file", str(env_path)])
        argv.extend(["--file", str(deploy_root / compose_name), "up", "-d", "--remove-orphans"])
        result = self._run(argv, timeout=600)
        if not result["ok"]:
            return {
                "ok": False,
                "status": "FAILED",
                "stackId": stack.stack_id,
                "deploy": {"ok": False, "exit_code": result["exit_code"], "error": "docker compose up failed"},
            }
        states = self._verify_expected(stack)
        runtime_canary = (
            self._patchmon_http_canary()
            if stack.stack_id == "patchmon-sovereign"
            else {"ok": True, "status": "NOT_REQUIRED"}
        )
        runtime_ok = all(state.get("running") for state in states.values()) and bool(runtime_canary.get("ok"))
        return {
            "ok": runtime_ok,
            "status": "DEPLOYED_VERIFIED" if runtime_ok else "DEPLOYED_UNVERIFIED",
            "stackId": stack.stack_id,
            "project": stack.project_name,
            "templateBundleSha256": bundle_sha,
            "containers": states,
            "runtimeCanary": runtime_canary,
            "secretEnvironment": secret_env,
            "secretValuesExposed": False,
        }
