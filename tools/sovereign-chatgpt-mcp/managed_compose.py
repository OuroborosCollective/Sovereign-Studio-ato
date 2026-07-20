from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from litellm_stack import LiteLLMStackRuntime


PATCHMON_REDIS_UID = 999
PATCHMON_REDIS_GID = 1000
PATCHMON_REDIS_USER = f"{PATCHMON_REDIS_UID}:{PATCHMON_REDIS_GID}"
MILVUS_GATEWAY_NETWORK = "milvus-kg4i_default"
MILVUS_GATEWAY_CONTAINER = "sovereign-memory-gateway"
MILVUS_COMPATIBILITY_IP = "172.16.5.4"
MILVUS_MIN_CPU_CORES = 4
MILVUS_MIN_MEMORY_BYTES = 8 * 1024 * 1024 * 1024
MILVUS_MIN_FREE_DISK_BYTES = 10 * 1024 * 1024 * 1024
CODE_SERVER_CONTAINER = "code-server-46bq-code-server-1"
CODE_SERVER_IMAGE = "lscr.io/linuxserver/code-server@sha256:dfc5e74083f43f3cb217fedfead149f32b319ee663744351c001bdc5e4245441"
CODE_SERVER_CONFIG_VOLUME = "code-server-46bq_code-server-config"
CODE_SERVER_REPOSITORY = "https://github.com/OuroborosCollective/Sovereign-Studio-ato.git"
CODE_SERVER_RUNTIME_UID = 10001
CODE_SERVER_RUNTIME_GID = 10001
BACKEND_WORKSPACE_HOST_ROOT = "/opt/sovereign-agent-workspaces"
BACKEND_WORKSPACE_CONTAINER_ROOT = "/var/lib/sovereign-agent/workspaces"
CODE_SERVER_WORKSPACE_ROOT = BACKEND_WORKSPACE_HOST_ROOT
CODE_SERVER_WORKSPACE_MOUNT = "/config/sovereign-agent-workspaces"
CODE_SERVER_ENV_KEYS = (
    "PUID",
    "PGID",
    "TZ",
    "PASSWORD",
    "HASHED_PASSWORD",
    "SUDO_PASSWORD",
    "SUDO_PASSWORD_HASH",
    "PROXY_DOMAIN",
    "DEFAULT_WORKSPACE",
)
CODE_SERVER_AUTH_KEYS = ("PASSWORD", "HASHED_PASSWORD")


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
        allowed_bind_roots=(
            "/opt/sovereign-backend",
            "/opt/secure",
            "/opt/sovereign-owner-managed",
            BACKEND_WORKSPACE_HOST_ROOT,
        ),
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
        allowed_bind_roots=("/opt/code-server-46bq", CODE_SERVER_WORKSPACE_ROOT),
        allowed_published_ports=("127.0.0.1:32782:8443",),
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
    "milvus-sovereign": ManagedStack(
        stack_id="milvus-sovereign",
        project_name="milvus-sovereign",
        anchor_container="milvus-standalone",
        expected_containers=("milvus-standalone", "milvus-etcd", "milvus-minio"),
        allowed_services=("standalone", "etcd", "minio"),
        deploy_root="/opt/milvus-sovereign",
        template_name="milvus-sovereign",
        allowed_networks=("milvus-storage", "memory-gateway"),
        allowed_bind_roots=("/opt/milvus-sovereign",),
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
                "{{json .State}}|{{json .Config.Labels}}|{{json .NetworkSettings.Networks}}|{{json .NetworkSettings.Ports}}|{{json .Config.Image}}|{{json .Image}}|{{json .Mounts}}",
                container,
            ],
            timeout=30,
        )
        if not result["ok"]:
            return {"present": False, "container": container}
        try:
            (
                state_raw,
                labels_raw,
                networks_raw,
                ports_raw,
                image_reference_raw,
                image_id_raw,
                mounts_raw,
            ) = result["stdout"].strip().split("|", 6)
            state = json.loads(state_raw)
            labels = json.loads(labels_raw) or {}
            networks = json.loads(networks_raw) or {}
            ports = json.loads(ports_raw) or {}
            image_reference = json.loads(image_reference_raw) or ""
            image_id = json.loads(image_id_raw) or ""
            mounts = json.loads(mounts_raw) or []
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Docker-Inspect ist ungültig: {container}: {exc}") from exc
        published = {
            key: value
            for key, value in ports.items()
            if isinstance(value, list) and value
        }
        safe_mounts = [
            {
                "type": str(item.get("Type") or ""),
                "name": str(item.get("Name") or ""),
                "source": str(item.get("Source") or ""),
                "destination": str(item.get("Destination") or ""),
                "rw": bool(item.get("RW")),
            }
            for item in mounts
            if isinstance(item, dict)
        ]
        repo_digests: list[str] = []
        if image_id:
            digest_result = self._run(
                ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", str(image_id)],
                timeout=30,
            )
            if digest_result.get("ok"):
                try:
                    raw_digests = json.loads(digest_result.get("stdout", "")) or []
                except json.JSONDecodeError:
                    raw_digests = []
                repo_digests = sorted(
                    value
                    for value in raw_digests
                    if isinstance(value, str)
                    and re.fullmatch(r"[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}", value)
                )
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
            "imageReference": str(image_reference),
            "imageId": str(image_id),
            "repoDigests": repo_digests,
            "mounts": safe_mounts,
            "networks": sorted(networks.keys()),
            "publishedPorts": published,
            "environmentReturned": False,
        }

    @staticmethod
    def _patchmon_server_transport_ready(state: dict[str, Any]) -> bool:
        bindings = state.get("publishedPorts", {}).get("3000/tcp", [])
        loopback_ready = any(
            str(binding.get("HostIp") or "") == "127.0.0.1"
            and str(binding.get("HostPort") or "") == "32830"
            for binding in bindings
            if isinstance(binding, dict)
        )
        return (
            bool(state.get("present"))
            and bool(state.get("running"))
            and "patchmon-sovereign_patchmon-edge" in set(state.get("networks") or [])
            and loopback_ready
        )

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
                "preserved_from_running_container"
                if stack.stack_id == "code-server-46bq"
                else "generated_on_confirmed_deploy"
                if stack.stack_id in {"pgbackweb-wq5r", "patchmon-sovereign", "milvus-sovereign"}
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
            if stack.stack_id == "patchmon-sovereign" and service_name == "redis":
                if str(service.get("user") or "") != PATCHMON_REDIS_USER:
                    raise RuntimeError("PatchMon Redis muss mit der gepinnten Nicht-Root-Identität laufen")
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
            allowed_milvus_commands = {
                "etcd": [
                    "etcd",
                    "--advertise-client-urls=http://127.0.0.1:2379",
                    "--listen-client-urls=http://0.0.0.0:2379",
                    "--data-dir=/etcd",
                ],
                "minio": ["minio", "server", "/minio_data", "--console-address", ":9001"],
                "standalone": ["milvus", "run", "standalone"],
            }
            allowed_milvus_command = (
                stack.stack_id == "milvus-sovereign"
                and service_name in allowed_milvus_commands
                and command == allowed_milvus_commands[service_name]
            )
            if command and not (allowed_patchmon_redis_command or allowed_milvus_command):
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

    @staticmethod
    def _bounded_env_value(value: str) -> str:
        if "\x00" in value or "\n" in value or "\r" in value or len(value) > 4096:
            raise RuntimeError("Code-Server-Umgebungswert verletzt den begrenzten Secret-Vertrag")
        return value

    @classmethod
    def _decode_code_server_env_value(cls, raw: str) -> str:
        if len(raw) >= 2 and raw.startswith("'") and raw.endswith("'"):
            inner = raw[1:-1]
            output: list[str] = []
            index = 0
            while index < len(inner):
                if inner[index] == "\\" and index + 1 < len(inner):
                    index += 1
                output.append(inner[index])
                index += 1
            return cls._bounded_env_value("".join(output))
        return cls._bounded_env_value(raw)

    @classmethod
    def _code_server_env_line(cls, key: str, value: str) -> str:
        bounded = cls._bounded_env_value(value)
        escaped = bounded.replace("\\", "\\\\").replace("'", "\\'")
        return f"{key}='{escaped}'"

    def _ensure_code_server_env(self, stack: ManagedStack) -> dict[str, Any]:
        deploy_root = Path(stack.deploy_root)
        if deploy_root.is_symlink():
            raise RuntimeError("Deploy-Root darf kein Symlink sein")
        deploy_root.mkdir(parents=True, exist_ok=True, mode=0o750)
        os.chmod(deploy_root, 0o750)
        env_path = deploy_root / ".env"
        if env_path.is_symlink() or (env_path.exists() and not env_path.is_file()):
            raise RuntimeError("Code-Server-Secret-Datei ist ungültig")
        workspace_root = Path(BACKEND_WORKSPACE_HOST_ROOT)
        if workspace_root.is_symlink() or (workspace_root.exists() and not workspace_root.is_dir()):
            raise RuntimeError("Backend-Workspace-Root ist ungültig")
        workspace_root.mkdir(parents=True, exist_ok=True, mode=0o770)
        if os.geteuid() == 0:
            os.chown(workspace_root, CODE_SERVER_RUNTIME_UID, CODE_SERVER_RUNTIME_GID)
        os.chmod(workspace_root, 0o770)

        values: dict[str, str] = {}
        source = "existing_managed_env" if env_path.is_file() else "running_container"
        if env_path.is_file():
            payload = env_path.read_bytes()
            if len(payload) > MAX_STACK_ENV_BYTES or b"\0" in payload:
                raise RuntimeError("Code-Server-Secret-Datei ist ungültig")
            for line in payload.decode("utf-8").splitlines():
                if not line or line.lstrip().startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                selected = key.strip()
                if selected in CODE_SERVER_ENV_KEYS:
                    values[selected] = self._decode_code_server_env_value(value)

        if not any(values.get(key) for key in CODE_SERVER_AUTH_KEYS):
            inspected = self._run(
                ["docker", "inspect", "--format", "{{json .Config.Env}}", stack.anchor_container],
                timeout=30,
            )
            if not inspected.get("ok"):
                raise RuntimeError("Bestehende Code-Server-Authentisierung kann nicht sicher übernommen werden")
            try:
                raw_env = json.loads(inspected.get("stdout", "")) or []
            except json.JSONDecodeError as exc:
                raise RuntimeError("Bestehende Code-Server-Umgebung ist ungültig") from exc
            for item in raw_env if isinstance(raw_env, list) else []:
                if not isinstance(item, str) or "=" not in item:
                    continue
                key, value = item.split("=", 1)
                if key in CODE_SERVER_ENV_KEYS and key not in values:
                    values[key] = self._bounded_env_value(value)
            source = "running_container"

        if not any(values.get(key) for key in CODE_SERVER_AUTH_KEYS):
            raise RuntimeError("Code-Server-Authentisierung fehlt; eine ungeschützte Neuerstellung ist gesperrt")

        values["PUID"] = str(CODE_SERVER_RUNTIME_UID)
        values["PGID"] = str(CODE_SERVER_RUNTIME_GID)
        values.setdefault("TZ", "Europe/Berlin")
        values["DEFAULT_WORKSPACE"] = CODE_SERVER_WORKSPACE_MOUNT
        rendered = [self._code_server_env_line(key, values.get(key, "")) for key in CODE_SERVER_ENV_KEYS]
        self._write_atomic(env_path, ("\n".join(rendered) + "\n").encode("utf-8"), mode=0o600)
        os.chmod(env_path, 0o600)
        auth_mode = "hashed_password" if values.get("HASHED_PASSWORD") else "password"
        return {
            "required": True,
            "created": source == "running_container",
            "path": str(env_path),
            "mode": "0600",
            "keysPresent": [key for key in CODE_SERVER_ENV_KEYS if values.get(key)],
            "authMode": auth_mode,
            "source": source,
            "workspaceRoot": {
                "path": str(workspace_root),
                "ownerUid": CODE_SERVER_RUNTIME_UID,
                "ownerGid": CODE_SERVER_RUNTIME_GID,
                "mode": "0770",
                "authority": "sovereign-backend",
            },
            "secretValuesReturned": False,
        }

    def _ensure_stack_secret_env(self, stack: ManagedStack) -> dict[str, Any]:
        if stack.stack_id == "code-server-46bq":
            return self._ensure_code_server_env(stack)
        if stack.stack_id not in {"pgbackweb-wq5r", "patchmon-sovereign", "milvus-sovereign"}:
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
        elif stack.stack_id == "patchmon-sovereign":
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
        else:
            required_lengths = {
                "MINIO_ACCESS_KEY_ID": 32,
                "MINIO_SECRET_ACCESS_KEY": 64,
            }
            fixed_values = {
                "MILVUS_GATEWAY_NETWORK": MILVUS_GATEWAY_NETWORK,
                "MILVUS_COMPATIBILITY_IP": MILVUS_COMPATIBILITY_IP,
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
            self._write_atomic(redis_path, redis_payload, mode=0o400)
            os.chown(redis_path, PATCHMON_REDIS_UID, PATCHMON_REDIS_GID)
            os.chmod(redis_path, 0o400)
            additional_files.append(
                {
                    "path": str(redis_path),
                    "mode": "0400",
                    "ownerUid": PATCHMON_REDIS_UID,
                    "ownerGid": PATCHMON_REDIS_GID,
                }
            )

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
    def _milvus_resource_preflight() -> dict[str, Any]:
        cpu_cores = int(os.cpu_count() or 0)
        try:
            memory_bytes = int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
        except (OSError, ValueError):
            memory_bytes = 0
        try:
            free_disk_bytes = int(shutil.disk_usage("/opt").free)
        except OSError:
            free_disk_bytes = 0
        checks = {
            "cpu": cpu_cores >= MILVUS_MIN_CPU_CORES,
            "memory": memory_bytes >= MILVUS_MIN_MEMORY_BYTES,
            "disk": free_disk_bytes >= MILVUS_MIN_FREE_DISK_BYTES,
        }
        ok = all(checks.values())
        return {
            "ok": ok,
            "status": "MILVUS_HOST_RESOURCES_VERIFIED" if ok else "MILVUS_HOST_RESOURCES_INSUFFICIENT",
            "cpuCores": cpu_cores,
            "minimumCpuCores": MILVUS_MIN_CPU_CORES,
            "memoryBytes": memory_bytes,
            "minimumMemoryBytes": MILVUS_MIN_MEMORY_BYTES,
            "freeDiskBytes": free_disk_bytes,
            "minimumFreeDiskBytes": MILVUS_MIN_FREE_DISK_BYTES,
            "checks": checks,
        }

    def _milvus_network_preflight(self) -> dict[str, Any]:
        result = self._run(
            [
                "docker",
                "network",
                "inspect",
                MILVUS_GATEWAY_NETWORK,
                "--format",
                "{{json .IPAM.Config}}|{{json .Containers}}",
            ],
            timeout=30,
        )
        if not result["ok"]:
            return {
                "ok": False,
                "status": "MILVUS_GATEWAY_NETWORK_MISSING",
                "network": MILVUS_GATEWAY_NETWORK,
            }
        try:
            ipam_raw, containers_raw = result["stdout"].strip().split("|", 1)
            ipam = json.loads(ipam_raw) or []
            containers = json.loads(containers_raw) or {}
        except (ValueError, json.JSONDecodeError):
            return {
                "ok": False,
                "status": "MILVUS_GATEWAY_NETWORK_INVALID",
                "network": MILVUS_GATEWAY_NETWORK,
            }
        subnets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        try:
            for item in ipam if isinstance(ipam, list) else []:
                subnet = str(item.get("Subnet") or "") if isinstance(item, dict) else ""
                if subnet:
                    subnets.append(ipaddress.ip_network(subnet, strict=False))
            compatibility_ip = ipaddress.ip_address(MILVUS_COMPATIBILITY_IP)
        except ValueError:
            return {
                "ok": False,
                "status": "MILVUS_GATEWAY_SUBNET_INVALID",
                "network": MILVUS_GATEWAY_NETWORK,
            }
        if not any(compatibility_ip in subnet for subnet in subnets):
            return {
                "ok": False,
                "status": "MILVUS_COMPATIBILITY_IP_OUTSIDE_NETWORK",
                "network": MILVUS_GATEWAY_NETWORK,
                "compatibilityIp": MILVUS_COMPATIBILITY_IP,
            }

        members: dict[str, str] = {}
        for item in containers.values() if isinstance(containers, dict) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("Name") or "")
            address = str(item.get("IPv4Address") or "").split("/", 1)[0]
            if name:
                members[name] = address
        allowed_members = {MILVUS_GATEWAY_CONTAINER, "milvus-standalone"}
        unexpected_members = sorted(set(members) - allowed_members)
        if unexpected_members:
            return {
                "ok": False,
                "status": "MILVUS_GATEWAY_NETWORK_NOT_ISOLATED",
                "network": MILVUS_GATEWAY_NETWORK,
                "unexpectedMembers": unexpected_members,
            }
        if MILVUS_GATEWAY_CONTAINER not in members:
            return {
                "ok": False,
                "status": "MILVUS_GATEWAY_NOT_ATTACHED",
                "network": MILVUS_GATEWAY_NETWORK,
            }
        occupied_by = next(
            (
                name
                for name, address in members.items()
                if address == MILVUS_COMPATIBILITY_IP and name != "milvus-standalone"
            ),
            "",
        )
        if occupied_by:
            return {
                "ok": False,
                "status": "MILVUS_COMPATIBILITY_IP_OCCUPIED",
                "network": MILVUS_GATEWAY_NETWORK,
                "occupiedBy": occupied_by,
            }
        return {
            "ok": True,
            "status": "MILVUS_GATEWAY_NETWORK_VERIFIED",
            "network": MILVUS_GATEWAY_NETWORK,
            "compatibilityIp": MILVUS_COMPATIBILITY_IP,
            "members": sorted(members),
            "externalPortsRequired": False,
        }

    def _milvus_runtime_canary(self) -> dict[str, Any]:
        tcp_script = (
            "const net=require('net');"
            f"const socket=net.createConnection({{host:'{MILVUS_COMPATIBILITY_IP}',port:19530}});"
            "const done=(code)=>{socket.destroy();process.exit(code)};"
            "socket.setTimeout(5000);socket.on('connect',()=>done(0));"
            "socket.on('timeout',()=>done(2));socket.on('error',()=>done(3));"
        )
        last_family = "unknown"
        for _attempt in range(45):
            health = self._run(
                [
                    "docker",
                    "exec",
                    "milvus-standalone",
                    "curl",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "http://127.0.0.1:9091/healthz",
                ],
                timeout=15,
            )
            gateway_path = self._run(
                ["docker", "exec", MILVUS_GATEWAY_CONTAINER, "node", "-e", tcp_script],
                timeout=15,
            )
            if health["ok"] and gateway_path["ok"]:
                return {
                    "ok": True,
                    "status": "MILVUS_GATEWAY_PATH_READY",
                    "milvusHealthz": True,
                    "gatewayTcpReachable": True,
                    "externalPortsPublished": False,
                    "responseBodyReturned": False,
                }
            last_family = (
                "milvus_healthz"
                if not health["ok"]
                else "gateway_tcp_path"
            )
            time.sleep(2)
        return {
            "ok": False,
            "status": "MILVUS_GATEWAY_PATH_UNAVAILABLE",
            "errorFamily": last_family,
            "responseBodyReturned": False,
        }

    @staticmethod
    def _code_server_transport_ready(state: dict[str, Any]) -> bool:
        bindings = state.get("publishedPorts", {}).get("8443/tcp", [])
        loopback_only = (
            len(bindings) == 1
            and str(bindings[0].get("HostIp") or "") == "127.0.0.1"
            and str(bindings[0].get("HostPort") or "") == "32782"
        ) if isinstance(bindings, list) and bindings else False
        config_mounts = [
            item
            for item in state.get("mounts") or []
            if isinstance(item, dict) and item.get("destination") == "/config"
        ]
        volume_ready = (
            len(config_mounts) == 1
            and config_mounts[0].get("type") == "volume"
            and config_mounts[0].get("name") == CODE_SERVER_CONFIG_VOLUME
            and config_mounts[0].get("rw") is True
        )
        workspace_mounts = [
            item
            for item in state.get("mounts") or []
            if isinstance(item, dict) and item.get("destination") == CODE_SERVER_WORKSPACE_MOUNT
        ]
        workspace_mount_ready = (
            len(workspace_mounts) == 1
            and workspace_mounts[0].get("type") == "bind"
            and workspace_mounts[0].get("source") == CODE_SERVER_WORKSPACE_ROOT
            and workspace_mounts[0].get("rw") is True
        )
        digest_ready = CODE_SERVER_IMAGE in set(state.get("repoDigests") or [])
        return bool(
            state.get("present")
            and state.get("running")
            and loopback_only
            and volume_ready
            and workspace_mount_ready
            and digest_ready
        )

    def _code_server_runtime_canary(self) -> dict[str, Any]:
        http_status = 0
        last_error = ""
        for _attempt in range(30):
            connection: http.client.HTTPConnection | None = None
            try:
                connection = http.client.HTTPConnection("127.0.0.1", 32782, timeout=5)
                connection.request("GET", "/healthz")
                response = connection.getresponse()
                http_status = int(response.status)
                response.read(4096)
                if 200 <= http_status < 400:
                    break
                last_error = f"HTTP {http_status}"
            except (OSError, http.client.HTTPException) as exc:
                last_error = type(exc).__name__
            finally:
                if connection is not None:
                    connection.close()
            time.sleep(2)

        token = secrets.token_hex(8)
        workspace = f"/config/workspace/.sovereign-clone-canary-{token}"
        backend_workspace_canary = f"{CODE_SERVER_WORKSPACE_MOUNT}/.code-server-canary-{token}"
        git_version = self._run(
            ["docker", "exec", "--user", "abc", CODE_SERVER_CONTAINER, "git", "--version"],
            timeout=30,
        )
        mkdir = self._run(
            ["docker", "exec", "--user", "abc", CODE_SERVER_CONTAINER, "mkdir", "-p", "/config/workspace"],
            timeout=30,
        )
        backend_workspace_write = self._run(
            [
                "docker",
                "exec",
                "--user",
                "abc",
                CODE_SERVER_CONTAINER,
                "sh",
                "-c",
                f"umask 077 && mkdir -p '{backend_workspace_canary}' && printf '%s' '{token}' > '{backend_workspace_canary}/marker' && test \"$(cat '{backend_workspace_canary}/marker')\" = '{token}'",
            ],
            timeout=30,
        )
        clone = self._run(
            [
                "docker",
                "exec",
                "--user",
                "abc",
                CODE_SERVER_CONTAINER,
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                "main",
                CODE_SERVER_REPOSITORY,
                workspace,
            ],
            timeout=240,
        ) if git_version.get("ok") and mkdir.get("ok") else {"ok": False, "stderr": "git_or_workspace_unavailable"}
        revision = self._run(
            ["docker", "exec", "--user", "abc", CODE_SERVER_CONTAINER, "git", "-C", workspace, "rev-parse", "HEAD"],
            timeout=30,
        ) if clone.get("ok") else {"ok": False, "stdout": ""}
        cleanup = self._run(
            ["docker", "exec", "--user", "abc", CODE_SERVER_CONTAINER, "rm", "-rf", workspace],
            timeout=30,
        )
        backend_workspace_cleanup = self._run(
            ["docker", "exec", "--user", "abc", CODE_SERVER_CONTAINER, "rm", "-rf", backend_workspace_canary],
            timeout=30,
        )
        cloned_revision = str(revision.get("stdout") or "").strip()
        revision_verified = bool(re.fullmatch(r"[0-9a-f]{40}", cloned_revision))
        ok = bool(
            200 <= http_status < 400
            and git_version.get("ok")
            and mkdir.get("ok")
            and backend_workspace_write.get("ok")
            and clone.get("ok")
            and revision.get("ok")
            and revision_verified
            and cleanup.get("ok")
            and backend_workspace_cleanup.get("ok")
        )
        return {
            "ok": ok,
            "status": "CODE_SERVER_WORKSPACE_CANARY_VERIFIED" if ok else "CODE_SERVER_WORKSPACE_CANARY_FAILED",
            "httpStatus": http_status,
            "authenticationEndpointReachable": 200 <= http_status < 400,
            "gitAvailable": bool(git_version.get("ok")),
            "workspaceWritable": bool(mkdir.get("ok")),
            "backendWorkspaceMountWritable": bool(backend_workspace_write.get("ok")),
            "repositoryCloneVerified": bool(clone.get("ok") and revision_verified),
            "clonedRevision": cloned_revision if revision_verified else None,
            "temporaryCloneRemoved": bool(cleanup.get("ok")),
            "backendWorkspaceCanaryRemoved": bool(backend_workspace_cleanup.get("ok")),
            "errorFamily": None if ok else (last_error or str(clone.get("stderr") or "workspace_canary_failed").strip().splitlines()[-1]),
            "repositoryContentReturned": False,
            "secretValuesReturned": False,
        }

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

    def memory_gateway_collection_canary(self) -> dict[str, Any]:
        script = r"""
const crypto = require('crypto');
const { MilvusClient, DataType } = require('@zilliz/milvus2-sdk-node');
const address = process.env.MILVUS_ADDRESS || process.env.MILVUS_HOST || '172.16.5.4:19530';
const marker = `SOVEREIGN_MEMORY_CANARY_${crypto.randomBytes(12).toString('hex')}`;
const collection = `sovereign_canary_${crypto.randomBytes(8).toString('hex')}`;
const markerSha256 = crypto.createHash('sha256').update(marker).digest('hex');
const client = new MilvusClient({ address });
let created = false;
let cleanup = false;
let stage = 'initialize';
const containsMarker = (value) => JSON.stringify(value || {}).includes(marker);
const boundedToken = (value, fallback) => {
  const rendered = String(value === undefined || value === null ? '' : value);
  return /^[A-Za-z0-9_.-]{1,80}$/.test(rendered) ? rendered : fallback;
};
const diagnostic = (error, errorStage) => {
  const message = String(error && error.message ? error.message : '');
  const normalized = message.toLowerCase();
  let family = `${errorStage}_failure`;
  if (/missing milvus sdk method/.test(normalized)) family = 'sdk_method_missing';
  else if (/unavailable|ehostunreach|econnrefused|deadline|timeout/.test(normalized)) family = 'transport_unavailable';
  else if (/schema|field|data type|datatype|dimension|dim/.test(normalized)) family = 'schema_contract';
  else if (/database/.test(normalized)) family = 'database_contract';
  return {
    diagnostic: true,
    errorStage,
    errorFamily: family,
    errorName: boundedToken(error && error.name, 'Error'),
    errorCode: boundedToken(error && error.code, 'none'),
    errorMessageSha256: crypto.createHash('sha256').update(message).digest('hex'),
  };
};
const call = async (names, payload) => {
  for (const name of names) {
    if (typeof client[name] === 'function') return await client[name](payload);
  }
  throw new Error(`Missing Milvus SDK method: ${names.join('/')}`);
};
(async () => {
  try {
    stage = 'create_collection';
    await call(['createCollection'], {
      collection_name: collection,
      fields: [
        { name: 'id', data_type: DataType.Int64, is_primary_key: true, autoID: false },
        { name: 'embedding', data_type: DataType.FloatVector, dim: 4 },
        { name: 'marker', data_type: DataType.VarChar, max_length: 160 },
      ],
    });
    created = true;
    stage = 'create_index';
    await call(['createIndex'], {
      collection_name: collection,
      field_name: 'embedding',
      index_type: 'AUTOINDEX',
      metric_type: 'COSINE',
      params: {},
    });
    stage = 'load_collection';
    await call(['loadCollectionSync', 'loadCollection'], { collection_name: collection });
    stage = 'insert_record';
    await call(['insert'], {
      collection_name: collection,
      fields_data: [{ id: 1, embedding: [1, 0, 0, 0], marker }],
    });
    stage = 'flush_collection';
    await call(['flushSync', 'flush'], { collection_names: [collection] });
    stage = 'query_readback';
    const query = await call(['query'], {
      collection_name: collection,
      expr: 'id == 1',
      output_fields: ['id', 'marker'],
    });
    stage = 'vector_search';
    const search = await call(['search'], {
      collection_name: collection,
      data: [[1, 0, 0, 0]],
      anns_field: 'embedding',
      limit: 1,
      metric_type: 'COSINE',
      output_fields: ['id', 'marker'],
    });
    stage = 'verify_readback';
    if (!containsMarker(query) || !containsMarker(search)) {
      throw new Error('Milvus canary readback marker missing');
    }
    process.stdout.write(JSON.stringify({
      ok: true,
      created: true,
      inserted: true,
      queried: true,
      searched: true,
      markerSha256,
    }) + '\n');
  } finally {
    if (created) {
      try {
        stage = 'drop_collection';
        await call(['dropCollection'], { collection_name: collection });
        cleanup = true;
      } catch (cleanupError) {
        cleanup = false;
        process.stdout.write(JSON.stringify({
          cleanup: false,
          ...diagnostic(cleanupError, 'drop_collection'),
        }) + '\n');
      }
    }
    process.stdout.write(JSON.stringify({ cleanup }) + '\n');
  }
})().catch((error) => {
  process.stdout.write(JSON.stringify(diagnostic(error, stage)) + '\n');
  process.exitCode = 1;
});
"""
        result = self._run(
            ["docker", "exec", MILVUS_GATEWAY_CONTAINER, "node", "-e", script],
            timeout=180,
        )
        lines = [line for line in result.get("stdout", "").splitlines() if line.strip()]
        receipts: list[dict[str, Any]] = []
        for line in lines[-8:]:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                receipts.append(value)
        canary = next((item for item in receipts if item.get("ok") is True), {})
        cleanup = next((item for item in reversed(receipts) if "cleanup" in item), {})
        diagnostic = next(
            (item for item in reversed(receipts) if item.get("diagnostic") is True),
            {},
        )
        ok = bool(
            result.get("ok")
            and canary.get("created")
            and canary.get("inserted")
            and canary.get("queried")
            and canary.get("searched")
            and cleanup.get("cleanup") is True
        )
        return {
            "ok": ok,
            "status": "MEMORY_COLLECTION_CANARY_VERIFIED" if ok else "MEMORY_COLLECTION_CANARY_FAILED",
            "gatewayContainer": MILVUS_GATEWAY_CONTAINER,
            "collectionCreated": bool(canary.get("created")),
            "recordInserted": bool(canary.get("inserted")),
            "queryReadbackVerified": bool(canary.get("queried")),
            "vectorSearchVerified": bool(canary.get("searched")),
            "collectionDropped": cleanup.get("cleanup") is True,
            "markerSha256": str(canary.get("markerSha256") or ""),
            "errorFamily": None if ok else str(diagnostic.get("errorFamily") or "unknown"),
            "errorStage": None if ok else str(diagnostic.get("errorStage") or "unknown"),
            "errorName": None if ok else str(diagnostic.get("errorName") or "Error"),
            "errorCode": None if ok else str(diagnostic.get("errorCode") or "none"),
            "errorMessageSha256": None if ok else str(diagnostic.get("errorMessageSha256") or ""),
            "diagnosticContentReturned": False,
            "responseContentReturned": False,
            "secretValuesReturned": False,
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

        resource_preflight = (
            self._milvus_resource_preflight()
            if stack.stack_id == "milvus-sovereign"
            else {"ok": True, "status": "NOT_REQUIRED"}
        )
        if not resource_preflight.get("ok"):
            return {
                "ok": False,
                "status": "BLOCKED",
                "stackId": stack.stack_id,
                "blocker": "Host-Ressourcen erfüllen die Milvus-Mindestanforderungen nicht",
                "resourcePreflight": resource_preflight,
            }
        network_preflight = (
            self._milvus_network_preflight()
            if stack.stack_id == "milvus-sovereign"
            else {"ok": True, "status": "NOT_REQUIRED"}
        )
        if not network_preflight.get("ok"):
            return {
                "ok": False,
                "status": "BLOCKED",
                "stackId": stack.stack_id,
                "blocker": "Milvus-Gateway-Netzwerk erfüllt den Sicherheitsvertrag nicht",
                "networkPreflight": network_preflight,
            }

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
        compose_argv = [
            "docker",
            "compose",
            "--project-name",
            stack.project_name,
            "--project-directory",
            str(deploy_root),
        ]
        env_path = deploy_root / ".env"
        if env_path.is_file() and not env_path.is_symlink():
            compose_argv.extend(["--env-file", str(env_path)])
        compose_argv.extend(["--file", str(deploy_root / compose_name)])
        result = self._run([*compose_argv, "up", "-d", "--remove-orphans"], timeout=600)
        if not result["ok"]:
            return {
                "ok": False,
                "status": "FAILED",
                "stackId": stack.stack_id,
                "deploy": {"ok": False, "exit_code": result["exit_code"], "error": "docker compose up failed"},
            }

        transport_repair: dict[str, Any] = {
            "attempted": False,
            "reason": None,
            "ok": True,
        }
        if stack.stack_id == "patchmon-sovereign":
            server_state = self._inspect(stack.anchor_container)
            if not self._patchmon_server_transport_ready(server_state):
                repair_result = self._run(
                    [
                        *compose_argv,
                        "up",
                        "-d",
                        "--no-deps",
                        "--force-recreate",
                        "server",
                    ],
                    timeout=600,
                )
                transport_repair = {
                    "attempted": True,
                    "reason": "PATCHMON_LOOPBACK_OR_EDGE_BINDING_MISSING",
                    "ok": bool(repair_result["ok"]),
                    "exitCode": int(repair_result["exit_code"]),
                    "scope": "patchmon_server_only",
                }
                if not repair_result["ok"]:
                    return {
                        "ok": False,
                        "status": "FAILED",
                        "stackId": stack.stack_id,
                        "deploy": {
                            "ok": False,
                            "exit_code": repair_result["exit_code"],
                            "error": "PatchMon server transport repair failed",
                        },
                        "transportRepair": transport_repair,
                    }

        states = self._verify_expected(stack)
        if stack.stack_id == "patchmon-sovereign":
            transport_verified = self._patchmon_server_transport_ready(states.get(stack.anchor_container, {}))
        elif stack.stack_id == "code-server-46bq":
            transport_verified = self._code_server_transport_ready(states.get(stack.anchor_container, {}))
        else:
            transport_verified = True

        if stack.stack_id == "patchmon-sovereign":
            runtime_canary = self._patchmon_http_canary()
        elif stack.stack_id == "milvus-sovereign":
            transport_canary = self._milvus_runtime_canary()
            collection_canary = (
                self.memory_gateway_collection_canary()
                if transport_canary.get("ok")
                else {"ok": False, "status": "SKIPPED_TRANSPORT_UNAVAILABLE"}
            )
            runtime_canary = {
                "ok": bool(transport_canary.get("ok") and collection_canary.get("ok")),
                "status": (
                    "MILVUS_TRANSPORT_AND_COLLECTION_VERIFIED"
                    if transport_canary.get("ok") and collection_canary.get("ok")
                    else "MILVUS_COLLECTION_RUNTIME_UNVERIFIED"
                ),
                "transport": transport_canary,
                "collection": collection_canary,
            }
        elif stack.stack_id == "code-server-46bq":
            runtime_canary = self._code_server_runtime_canary()
        else:
            runtime_canary = {"ok": True, "status": "NOT_REQUIRED"}
        runtime_ok = (
            all(state.get("running") for state in states.values())
            and bool(runtime_canary.get("ok"))
            and transport_verified
        )
        return {
            "ok": runtime_ok,
            "status": "DEPLOYED_VERIFIED" if runtime_ok else "DEPLOYED_UNVERIFIED",
            "stackId": stack.stack_id,
            "project": stack.project_name,
            "templateBundleSha256": bundle_sha,
            "containers": states,
            "transportVerified": transport_verified,
            "transportRepair": transport_repair,
            "runtimeCanary": runtime_canary,
            "networkPreflight": network_preflight,
            "resourcePreflight": resource_preflight,
            "secretEnvironment": secret_env,
            "secretValuesExposed": False,
        }
