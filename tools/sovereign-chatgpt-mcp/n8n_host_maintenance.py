from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable


N8N_PROJECT = "n8n-with-ai-assistant-r7uy"
N8N_CONTAINER = f"{N8N_PROJECT}-n8n-1"
N8N_SANDBOX_CERTS_CONTAINER = f"{N8N_PROJECT}-sandbox-certs-1"
N8N_SANDBOX_API_CONTAINER = f"{N8N_PROJECT}-sandbox-api-1"
N8N_SANDBOX_RUNNER_CONTAINER = f"{N8N_PROJECT}-sandbox-runner-1-1"
N8N_EXPECTED_SERVICES = {
    N8N_CONTAINER: "n8n",
    N8N_SANDBOX_CERTS_CONTAINER: "sandbox-certs",
    N8N_SANDBOX_API_CONTAINER: "sandbox-api",
    N8N_SANDBOX_RUNNER_CONTAINER: "sandbox-runner-1",
}
N8N_REQUIRED_HOST_ENV_KEYS = {
    "TZ",
    "TRAEFIK_HOST",
    "SANDBOX_API_KEY",
    "SANDBOX_RUNNER_API_KEY",
    "SANDBOX_RUNNER_REGISTRATION_TOKEN",
}
N8N_SECRET_HOST_KEYS = (
    "SANDBOX_API_KEY",
    "SANDBOX_RUNNER_API_KEY",
    "SANDBOX_RUNNER_REGISTRATION_TOKEN",
)
N8N_MIN_FREE_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_MAINTENANCE_ROOT = "/opt/sovereign-chatgpt-tools/maintenance/n8n-stage1"
AURION_BUILDKIT_CONTAINER = "buildx_buildkit_aurion-isolated0"
RETIRED_DOCUMENT_IMAGE_REPOSITORIES = frozenset({"apache/tika", "gotenberg/gotenberg"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IMAGE_DIGEST_RE = re.compile(r"^[A-Za-z0-9._/-]+@sha256:[0-9a-f]{64}$")


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class N8NHostMaintenanceRuntime:
    """Strict n8n/host maintenance lane with no arbitrary target, command or secret output."""

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        maintenance_root: str | None = None,
    ) -> None:
        self._runner = runner or subprocess.run
        self.maintenance_root = Path(
            maintenance_root
            or os.getenv("SOVEREIGN_MCP_N8N_MAINTENANCE_ROOT", DEFAULT_MAINTENANCE_ROOT)
        )

    def _run(
        self,
        argv: list[str],
        *,
        timeout: int = 120,
        env_overrides: dict[str, str] | None = None,
    ) -> dict[str, Any]:
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
                    **(env_overrides or {}),
                },
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "ok": False,
                "exitCode": None,
                "stdout": "",
                "stderr": type(exc).__name__,
            }
        return {
            "ok": completed.returncode == 0,
            "exitCode": int(completed.returncode),
            "stdout": str(completed.stdout or "")[-48_000:],
            "stderr": str(completed.stderr or "")[-8_000:],
        }

    @staticmethod
    def _write_enabled() -> bool:
        return (
            os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() == "1"
            and os.getenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "0").strip() == "1"
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

    def _inspect(self, container: str) -> dict[str, Any] | None:
        result = self._run(["docker", "inspect", container], timeout=30)
        if not result.get("ok"):
            return None
        try:
            values = json.loads(result.get("stdout") or "")
        except json.JSONDecodeError as exc:
            raise RuntimeError("Docker inspect returned invalid JSON") from exc
        if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict):
            raise RuntimeError("Docker inspect did not return one object")
        return values[0]

    @staticmethod
    def _summary(inspect: dict[str, Any]) -> dict[str, Any]:
        config = inspect.get("Config") if isinstance(inspect.get("Config"), dict) else {}
        labels = config.get("Labels") if isinstance(config.get("Labels"), dict) else {}
        state = inspect.get("State") if isinstance(inspect.get("State"), dict) else {}
        network_settings = inspect.get("NetworkSettings") if isinstance(inspect.get("NetworkSettings"), dict) else {}
        ports = network_settings.get("Ports") if isinstance(network_settings.get("Ports"), dict) else {}
        bindings: list[dict[str, str]] = []
        for container_port, rows in sorted(ports.items()):
            for row in rows if isinstance(rows, list) else []:
                item = row if isinstance(row, dict) else {}
                bindings.append({
                    "containerPort": str(container_port),
                    "hostIp": str(item.get("HostIp") or ""),
                    "hostPort": str(item.get("HostPort") or ""),
                })
        networks = network_settings.get("Networks") if isinstance(network_settings.get("Networks"), dict) else {}
        return {
            "id": str(inspect.get("Id") or "")[:64],
            "name": str(inspect.get("Name") or "").lstrip("/"),
            "image": str(config.get("Image") or "")[:300],
            "imageId": str(inspect.get("Image") or "")[:100],
            "project": str(labels.get("com.docker.compose.project") or "")[:160],
            "service": str(labels.get("com.docker.compose.service") or "")[:160],
            "workingDir": str(labels.get("com.docker.compose.project.working_dir") or "")[:1000],
            "configFiles": str(labels.get("com.docker.compose.project.config_files") or "")[:2000],
            "running": bool(state.get("Running")),
            "status": str(state.get("Status") or "unknown")[:40],
            "exitCode": int(state.get("ExitCode") or 0),
            "ports": bindings,
            "networks": sorted(str(name) for name in networks),
        }

    def _container_env(self, container: str) -> dict[str, str]:
        result = self._run(
            ["docker", "inspect", "--format", "{{json .Config.Env}}", container],
            timeout=30,
        )
        if not result.get("ok"):
            raise RuntimeError(f"container environment unavailable: {container}")
        try:
            rows = json.loads(result.get("stdout") or "") or []
        except json.JSONDecodeError as exc:
            raise RuntimeError("container environment metadata invalid") from exc
        values: dict[str, str] = {}
        for raw in rows if isinstance(rows, list) else []:
            if isinstance(raw, str) and "=" in raw:
                key, value = raw.split("=", 1)
                values[key] = value
        return values

    @staticmethod
    def _read_host_env(path: Path) -> dict[str, str]:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Hostinger environment file is unavailable")
        payload = path.read_bytes()
        if len(payload) > 128_000 or b"\0" in payload:
            raise RuntimeError("Hostinger environment file is invalid")
        values: dict[str, str] = {}
        for raw in payload.decode("utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            selected = key.strip()
            rendered = value.strip()
            if len(rendered) >= 2 and rendered[0] == rendered[-1] and rendered[0] in {"'", '"'}:
                rendered = rendered[1:-1]
            values[selected] = rendered
        return values

    @staticmethod
    def _original_compose_files(config_files: str, working_dir: Path) -> list[Path]:
        root = working_dir.resolve()
        raw_paths = [item.strip() for item in str(config_files or "").split(",") if item.strip()]
        if not raw_paths:
            raise RuntimeError("Hostinger Compose source file metadata is unavailable")
        resolved_paths: list[Path] = []
        for raw in raw_paths:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = working_dir / candidate
            if candidate.is_symlink():
                raise RuntimeError("Hostinger Compose source file must not be a symlink")
            resolved = candidate.resolve()
            if resolved != root and root not in resolved.parents:
                raise RuntimeError("Hostinger Compose source file escaped its working directory")
            if not resolved.is_file():
                raise RuntimeError("Hostinger Compose source file is unavailable")
            resolved_paths.append(resolved)
        return resolved_paths

    @staticmethod
    def _compose_file_evidence(paths: list[Path]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for path in paths:
            payload = path.read_bytes()
            if len(payload) > 1_000_000 or b"\0" in payload:
                raise RuntimeError("Hostinger Compose source file violates the bounded text contract")
            evidence.append({
                "name": path.name,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            })
        return evidence

    def _repo_digest(self, image_id: str, image_hint: str) -> str:
        result = self._run(
            ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", image_id],
            timeout=30,
        )
        if not result.get("ok"):
            raise RuntimeError("Docker image digest metadata unavailable")
        try:
            rows = json.loads(result.get("stdout") or "") or []
        except json.JSONDecodeError as exc:
            raise RuntimeError("Docker image digest metadata invalid") from exc
        candidates = sorted(str(row) for row in rows if isinstance(row, str) and _IMAGE_DIGEST_RE.fullmatch(str(row)))
        if not candidates:
            raise RuntimeError("Runtime image has no immutable repository digest")
        repository_hint = image_hint.split("@", 1)[0]
        if ":" in repository_hint.rsplit("/", 1)[-1]:
            repository_hint = repository_hint.rsplit(":", 1)[0]
        return next((row for row in candidates if row.startswith(repository_hint + "@")), candidates[0])

    def _inner_sandbox_digest(self) -> str:
        result = self._run(
            [
                "docker",
                "exec",
                N8N_SANDBOX_RUNNER_CONTAINER,
                "docker",
                "image",
                "inspect",
                "--format",
                "{{json .RepoDigests}}",
                "n8nio/n8n-sandbox-service-sandbox:latest",
            ],
            timeout=60,
        )
        if not result.get("ok"):
            raise RuntimeError("Inner sandbox immutable image identity is unavailable")
        try:
            rows = json.loads(result.get("stdout") or "") or []
        except json.JSONDecodeError as exc:
            raise RuntimeError("Inner sandbox image metadata invalid") from exc
        candidates = sorted(str(row) for row in rows if isinstance(row, str) and _IMAGE_DIGEST_RE.fullmatch(str(row)))
        match = next((row for row in candidates if row.startswith("n8nio/n8n-sandbox-service-sandbox@")), "")
        if not match:
            raise RuntimeError("Inner sandbox image has no immutable repository digest")
        return match

    @staticmethod
    def _disk() -> dict[str, int]:
        usage = shutil.disk_usage("/var/lib/docker")
        return {
            "totalBytes": int(usage.total),
            "usedBytes": int(usage.used),
            "freeBytes": int(usage.free),
            "usedPpm": int(usage.used) * 1_000_000 // int(usage.total) if usage.total else 0,
        }

    def _running_container_identity(self) -> dict[str, Any]:
        result = self._run(["docker", "ps", "--no-trunc", "--format", "{{.ID}}|{{.Names}}|{{.Image}}"], timeout=30)
        if not result.get("ok"):
            raise RuntimeError("Running-container inventory unavailable")
        rows = sorted(line.strip() for line in str(result.get("stdout") or "").splitlines() if line.strip())
        return {"count": len(rows), "sha256": _canonical_sha256(rows)}

    def _volume_identity(self) -> dict[str, Any]:
        result = self._run(["docker", "volume", "ls", "--quiet"], timeout=30)
        if not result.get("ok"):
            raise RuntimeError("Docker-volume inventory unavailable")
        rows = sorted(line.strip() for line in str(result.get("stdout") or "").splitlines() if line.strip())
        return {"count": len(rows), "sha256": _canonical_sha256(rows)}

    def _buildkit_prune_endpoint(self) -> dict[str, str] | None:
        observed = self._run(
            [
                "docker",
                "ps",
                "--filter",
                f"name={AURION_BUILDKIT_CONTAINER}",
                "--format",
                "{{.Names}}",
            ],
            timeout=60,
        )
        names = {
            line.strip()
            for line in str(observed.get("stdout") or "").splitlines()
            if line.strip()
        }
        if not observed.get("ok") or names != {AURION_BUILDKIT_CONTAINER}:
            return None
        help_result = self._run(
            ["docker", "exec", AURION_BUILDKIT_CONTAINER, "buildctl", "prune", "--help"],
            timeout=60,
        )
        help_text = str(help_result.get("stdout") or "") + "\n" + str(help_result.get("stderr") or "")
        if not help_result.get("ok") or "--keep-duration" not in help_text:
            return None
        return {
            "container": AURION_BUILDKIT_CONTAINER,
            "pruneHelpSha256": _fingerprint(help_text),
        }

    def docker_cache_cleanup_plan(self) -> dict[str, Any]:
        try:
            running = self._running_container_identity()
            volumes = self._volume_identity()
            disk = self._disk()
            system_df = self._run(["docker", "system", "df"], timeout=60)
            endpoint = self._buildkit_prune_endpoint()
        except RuntimeError as exc:
            return self._failure("DOCKER_CACHE_CLEANUP_PLAN_BLOCKED", "DOCKER_INVENTORY_UNAVAILABLE", str(exc))
        if endpoint is None:
            return self._failure(
                "DOCKER_CACHE_CLEANUP_PLAN_BLOCKED",
                "BUILDKIT_PRUNE_UNAVAILABLE",
                "Exact BuildKit endpoint cannot prove time-bounded cache pruning support",
            )
        # Confirmation binds stable mutation scope and object identities only.
        # Disk usage and docker system-df output are intentionally evidence-only:
        # they can change between plan/apply from normal log or layer writes and
        # must not create an unresolvable confirmation race.
        state = {
            "schemaVersion": "sovereign.docker-cache-cleanup.v1",
            "action": "prune_buildkit_cache_not_used_last_24h_and_dangling_images_only",
            "runningContainers": running,
            "volumes": volumes,
            "buildkitEndpoint": endpoint,
        }
        return {
            "ok": True,
            "status": "DOCKER_CACHE_CLEANUP_PLAN_READY",
            "scope": ["buildkit-cache-not-used-last-24h", "dangling-images"],
            "excluded": ["volumes", "running-containers", "tagged-images"],
            "disk": disk,
            "systemDfSha256": _fingerprint(str(system_df.get("stdout") or "")),
            "builders": ["aurion-isolated"],
            "buildkitEndpoint": endpoint,
            "runningContainers": running,
            "volumes": volumes,
            "confirmationSha256": _canonical_sha256(state),
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    def docker_cache_cleanup_apply(self, *, confirmation_sha256: str, owner_approved: bool) -> dict[str, Any]:
        if not owner_approved:
            return self._failure("DOCKER_CACHE_CLEANUP_BLOCKED", "OWNER_APPROVAL_REQUIRED", "owner_approved=true is required")
        if not self._write_enabled():
            return self._failure("DOCKER_CACHE_CLEANUP_BLOCKED", "HOST_MAINTENANCE_WRITE_DISABLED", "Allowlisted Compose/host writes are disabled")
        plan = self.docker_cache_cleanup_plan()
        if not plan.get("ok"):
            return plan
        expected = str(plan.get("confirmationSha256") or "")
        supplied = str(confirmation_sha256 or "").strip().lower()
        if not _SHA256_RE.fullmatch(supplied) or supplied != expected:
            return self._failure(
                "DOCKER_CACHE_CLEANUP_BLOCKED",
                "CONFIRMATION_MISMATCH",
                "Cleanup confirmation no longer matches current running-container, volume and disk state",
                expectedConfirmationSha256=expected,
            )
        endpoint = plan.get("buildkitEndpoint")
        container = str(endpoint.get("container") or "") if isinstance(endpoint, dict) else ""
        if container != AURION_BUILDKIT_CONTAINER:
            return self._failure(
                "DOCKER_CACHE_CLEANUP_BLOCKED",
                "BUILDKIT_ENDPOINT_INVALID",
                "Cleanup plan did not bind the expected BuildKit endpoint",
            )
        before_disk = dict(plan["disk"])
        before_running = dict(plan["runningContainers"])
        before_volumes = dict(plan["volumes"])
        steps: list[dict[str, Any]] = []
        commands = [
            ["docker", "image", "prune", "--force"],
            [
                "docker",
                "exec",
                AURION_BUILDKIT_CONTAINER,
                "buildctl",
                "prune",
                "--all",
                "--keep-duration=24h",
            ],
        ]
        for argv in commands:
            result = self._run(argv, timeout=900)
            step = {"argv": argv, "ok": bool(result.get("ok")), "exitCode": result.get("exitCode")}
            if not result.get("ok"):
                stderr = str(result.get("stderr") or "")
                step["stderrSha256"] = _fingerprint(stderr)
                step["stderrBytes"] = len(stderr.encode("utf-8"))
            steps.append(step)
            if not result.get("ok"):
                break
        after_running = self._running_container_identity()
        after_volumes = self._volume_identity()
        after_disk = self._disk()
        identities_preserved = before_running == after_running and before_volumes == after_volumes
        reclaimed = max(0, int(after_disk["freeBytes"]) - int(before_disk["freeBytes"]))
        ok = bool(all(item["ok"] for item in steps) and identities_preserved)
        return {
            "ok": ok,
            "status": "DOCKER_CACHE_CLEANUP_VERIFIED" if ok else "DOCKER_CACHE_CLEANUP_INCOMPLETE",
            "steps": steps,
            "beforeDisk": before_disk,
            "afterDisk": after_disk,
            "reclaimedBytes": reclaimed,
            "runningContainersPreserved": before_running == after_running,
            "volumesPreserved": before_volumes == after_volumes,
            "volumesRemoved": False,
            "runningContainersRemoved": False,
            "taggedImagesExplicitlyRemoved": False,
            "readbackVerified": ok,
            "mutationPerformed": True,
            "secretValuesReturned": False,
        }

    def _stage1_compose(self, images: dict[str, str], *, instance_ai_enabled: bool = False) -> str:
        instance_ai_env = ""
        if instance_ai_enabled:
            instance_ai_env = """      - N8N_ENABLED_MODULES=instance-ai
      - N8N_INSTANCE_AI_MODEL_URL=https://api.nexos.ai/v1
      - N8N_INSTANCE_AI_MODEL=${N8N_INSTANCE_AI_MODEL}
      - N8N_INSTANCE_AI_MODEL_API_KEY=${NEXOS_API_KEY}
"""
        return f"""services:
  n8n:
    image: {images['n8n']}
    restart: unless-stopped
    ports:
      - \"127.0.0.1:5678:5678\"
    labels:
      - traefik.enable=true
      - traefik.http.routers.{N8N_PROJECT}.rule=Host(`{N8N_PROJECT}.${{TRAEFIK_HOST}}`)
      - traefik.http.routers.{N8N_PROJECT}.entrypoints=websecure
      - traefik.http.routers.{N8N_PROJECT}.tls.certresolver=letsencrypt
      - traefik.http.services.{N8N_PROJECT}.loadbalancer.server.port=5678
    environment:
      - N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true
      - N8N_SECURE_COOKIE=true
      - N8N_HOST={N8N_PROJECT}.${{TRAEFIK_HOST}}
      - N8N_PROTOCOL=https
      - N8N_PORT=5678
      - N8N_PROXY_HOPS=1
      - N8N_WEBHOOK_URL=https://{N8N_PROJECT}.${{TRAEFIK_HOST}}/
      - N8N_EDITOR_BASE_URL=https://{N8N_PROJECT}.${{TRAEFIK_HOST}}/
      - N8N_UNVERIFIED_PACKAGES_ENABLED=false
      - NODE_ENV=production
      - GENERIC_TIMEZONE=${{TZ}}
      - TZ=${{TZ}}
{instance_ai_env}      - N8N_INSTANCE_AI_SANDBOX_ENABLED=true
      - N8N_INSTANCE_AI_SANDBOX_PROVIDER=n8n-sandbox
      - N8N_SANDBOX_SERVICE_URL=http://sandbox-api:8080
      - N8N_SANDBOX_SERVICE_API_KEY=${{SANDBOX_API_KEY}}
    volumes:
      - n8n_data:/home/node/.n8n
    depends_on:
      sandbox-api:
        condition: service_started

  sandbox-certs:
    image: {images['sandboxApi']}
    user: '0:0'
    entrypoint: ['sh', '-c']
    command:
      - >
        bootstrap-mtls.sh --out-dir /tls --api-san sandbox-api
        --control-san-prefix sandbox-runner --world-readable &&
        chown -R sandbox-api:sandbox-api /tls/api && chmod -R a+rX /tls
    environment:
      - NUM_RUNNERS=1
    volumes:
      - sandbox-tls:/tls
    restart: \"no\"

  sandbox-api:
    image: {images['sandboxApi']}
    restart: unless-stopped
    depends_on:
      sandbox-certs:
        condition: service_completed_successfully
    environment:
      - SANDBOX_API_KEYS=${{SANDBOX_API_KEY}}
      - SANDBOX_API_RUNNER_REGISTRATION_TOKEN=${{SANDBOX_RUNNER_REGISTRATION_TOKEN}}
      - SANDBOX_API_RUNNER_API_KEY=${{SANDBOX_RUNNER_API_KEY}}
      - SANDBOX_API_GRPC_TLS_CERT_FILE=/tls/api/grpc-server.crt
      - SANDBOX_API_GRPC_TLS_KEY_FILE=/tls/api/grpc-server.key
      - SANDBOX_API_GRPC_TLS_CLIENT_CA_FILE=/tls/api/ca.crt
      - SANDBOX_API_RUNNER_CONTROL_GRPC_TLS_CA_FILE=/tls/api/ca.crt
      - SANDBOX_API_RUNNER_CONTROL_GRPC_TLS_CERT_FILE=/tls/api/control-grpc-api-client.crt
      - SANDBOX_API_RUNNER_CONTROL_GRPC_TLS_KEY_FILE=/tls/api/control-grpc-api-client.key
      - SANDBOX_API_RUNNER_CONTROL_GRPC_TLS_SERVER_NAME=sandbox-runner-1
    volumes:
      - sandbox-tls:/tls:ro

  sandbox-runner-1:
    image: {images['sandboxRunner']}
    restart: unless-stopped
    privileged: true
    depends_on:
      sandbox-api:
        condition: service_started
    environment:
      - SANDBOX_RUNNER_API_KEYS=${{SANDBOX_RUNNER_API_KEY}}
      - SANDBOX_RUNNER_REGISTRATION_TOKEN=${{SANDBOX_RUNNER_REGISTRATION_TOKEN}}
      - SANDBOX_RUNNER_API_GRPC_ADDR=sandbox-api:9090
      - SANDBOX_RUNNER_HTTP_BASE_URL=http://sandbox-runner-1:8080
      - SANDBOX_RUNNER_CONTROL_GRPC_LISTEN_ADDR=:9091
      - SANDBOX_RUNNER_CONTROL_GRPC_ADVERTISE_ADDR=sandbox-runner-1:9091
      - SANDBOX_RUNNER_ID=runner-1
      - SANDBOX_RUNNER_DOCKER_SANDBOX_IMAGE={images['innerSandbox']}
      - SANDBOX_RUNNER_REGISTRATION_GRPC_CA_FILE=/tls/runner/ca.crt
      - SANDBOX_RUNNER_REGISTRATION_GRPC_CERT_FILE=/tls/runner/grpc-client.crt
      - SANDBOX_RUNNER_REGISTRATION_GRPC_KEY_FILE=/tls/runner/grpc-client.key
      - SANDBOX_RUNNER_REGISTRATION_GRPC_SERVER_NAME=sandbox-api
      - SANDBOX_RUNNER_CONTROL_GRPC_TLS_CERT_FILE=/tls/runner/control-grpc-server.crt
      - SANDBOX_RUNNER_CONTROL_GRPC_TLS_KEY_FILE=/tls/runner/control-grpc-server.key
      - SANDBOX_RUNNER_CONTROL_GRPC_TLS_CLIENT_CA_FILE=/tls/runner/ca.crt
    volumes:
      - sandbox-tls:/tls:ro

volumes:
  n8n_data:
  sandbox-tls:
"""

    @staticmethod
    def _image_repository(tag: str) -> str:
        rendered = str(tag or "").strip()
        if not rendered or rendered == "<none>:<none>" or "@" in rendered:
            return ""
        repository, separator, selected_tag = rendered.rpartition(":")
        if not separator or not repository or not selected_tag:
            return ""
        return repository

    def _all_container_image_ids(self) -> set[str]:
        listed = self._run(
            ["docker", "ps", "--all", "--no-trunc", "--format", "{{.Names}}"],
            timeout=60,
        )
        if not listed.get("ok"):
            raise RuntimeError("Docker container inventory unavailable")
        names = sorted(
            line.strip()
            for line in str(listed.get("stdout") or "").splitlines()
            if line.strip()
        )
        if len(names) > 300:
            raise RuntimeError("Docker container inventory exceeded bounded limit")
        if not names:
            return set()
        inspected = self._run(
            ["docker", "inspect", "--format", "{{.Image}}", *names],
            timeout=90,
        )
        image_ids = [
            line.strip()
            for line in str(inspected.get("stdout") or "").splitlines()
            if line.strip()
        ]
        if (
            not inspected.get("ok")
            or len(image_ids) != len(names)
            or any(not _IMAGE_ID_RE.fullmatch(image_id) for image_id in image_ids)
        ):
            raise RuntimeError("Docker container image references unavailable")
        return set(image_ids)

    def _retired_document_image_candidates(self) -> list[dict[str, Any]]:
        referenced_image_ids = self._all_container_image_ids()
        listed = self._run(
            ["docker", "image", "ls", "--no-trunc", "--format", "{{.ID}}"],
            timeout=60,
        )
        if not listed.get("ok"):
            raise RuntimeError("Docker image inventory unavailable")
        requested_ids = sorted(
            {
                line.strip()
                for line in str(listed.get("stdout") or "").splitlines()
                if _IMAGE_ID_RE.fullmatch(line.strip())
            }
        )
        if len(requested_ids) > 500:
            raise RuntimeError("Docker image inventory exceeded bounded limit")
        if not requested_ids:
            return []
        inspected = self._run(
            ["docker", "image", "inspect", *requested_ids],
            timeout=120,
        )
        if not inspected.get("ok"):
            raise RuntimeError("Docker image metadata unavailable")
        try:
            metadata = json.loads(str(inspected.get("stdout") or ""))
        except json.JSONDecodeError as exc:
            raise RuntimeError("Docker image metadata invalid") from exc
        if not isinstance(metadata, list) or len(metadata) != len(requested_ids):
            raise RuntimeError("Docker image metadata cardinality mismatch")

        candidates: list[dict[str, Any]] = []
        for row in metadata:
            if not isinstance(row, dict):
                raise RuntimeError("Docker image metadata row invalid")
            image_id = str(row.get("Id") or "").strip()
            repo_tags = sorted(
                {
                    str(item).strip()
                    for item in (row.get("RepoTags") or [])
                    if isinstance(item, str) and str(item).strip()
                }
            )
            repositories = sorted(
                {
                    self._image_repository(tag)
                    for tag in repo_tags
                    if self._image_repository(tag)
                }
            )
            try:
                size_bytes = int(row.get("Size") or 0)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("Docker image size metadata invalid") from exc
            if (
                not _IMAGE_ID_RE.fullmatch(image_id)
                or image_id in referenced_image_ids
                or not repo_tags
                or not repositories
                or size_bytes < 0
                or not set(repositories).issubset(RETIRED_DOCUMENT_IMAGE_REPOSITORIES)
            ):
                continue
            candidates.append(
                {
                    "imageId": image_id,
                    "repositories": repositories,
                    "repoTags": repo_tags,
                    "sizeBytes": size_bytes,
                }
            )
        return sorted(candidates, key=lambda item: str(item["imageId"]))

    def retired_document_image_cleanup_plan(self) -> dict[str, Any]:
        try:
            candidates = self._retired_document_image_candidates()
            disk = self._disk()
        except RuntimeError as exc:
            return self._failure(
                "RETIRED_DOCUMENT_IMAGE_CLEANUP_PLAN_BLOCKED",
                "DOCKER_IMAGE_INVENTORY_UNAVAILABLE",
                str(exc),
            )
        state = {
            "schemaVersion": "sovereign.retired-document-image-cleanup.v1",
            "action": "remove_unreferenced_gotenberg_and_tika_images_only",
            "candidates": candidates,
        }
        return {
            "ok": True,
            "status": "RETIRED_DOCUMENT_IMAGE_CLEANUP_PLAN_READY",
            "scope": ["unreferenced-gotenberg-and-tika-images-only"],
            "excluded": [
                "volumes",
                "containers",
                "running-container-images",
                "stopped-container-images",
                "non-retired-images",
                "all-other-tagged-images",
            ],
            "candidates": candidates,
            "candidateCount": len(candidates),
            "estimatedReclaimableBytes": sum(
                int(item["sizeBytes"]) for item in candidates
            ),
            "disk": disk,
            "confirmationSha256": _canonical_sha256(state),
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    def retired_document_image_cleanup_apply(
        self,
        *,
        confirmation_sha256: str,
        owner_approved: bool,
    ) -> dict[str, Any]:
        if not owner_approved:
            return self._failure(
                "RETIRED_DOCUMENT_IMAGE_CLEANUP_BLOCKED",
                "OWNER_APPROVAL_REQUIRED",
                "owner_approved=true is required",
            )
        if not self._write_enabled():
            return self._failure(
                "RETIRED_DOCUMENT_IMAGE_CLEANUP_BLOCKED",
                "HOST_MAINTENANCE_WRITE_DISABLED",
                "Allowlisted Compose/host writes are disabled",
            )
        plan = self.retired_document_image_cleanup_plan()
        if not plan.get("ok"):
            return plan
        expected = str(plan.get("confirmationSha256") or "")
        supplied = str(confirmation_sha256 or "").strip().lower()
        if not _SHA256_RE.fullmatch(supplied) or supplied != expected:
            return self._failure(
                "RETIRED_DOCUMENT_IMAGE_CLEANUP_BLOCKED",
                "CONFIRMATION_MISMATCH",
                "Retired-document image cleanup confirmation no longer matches the candidate set",
                expectedConfirmationSha256=expected,
            )

        candidates = list(plan.get("candidates") or [])
        before_disk = dict(plan["disk"])
        if not candidates:
            return {
                "ok": True,
                "status": "RETIRED_DOCUMENT_IMAGE_CLEANUP_NOT_NEEDED",
                "beforeDisk": before_disk,
                "afterDisk": before_disk,
                "estimatedReclaimableBytes": 0,
                "reclaimedBytes": 0,
                "steps": [],
                "volumesRemoved": False,
                "runningContainersRemoved": False,
                "nonRetiredImagesExplicitlyRemoved": False,
                "mutationPerformed": False,
                "secretValuesReturned": False,
            }

        steps: list[dict[str, Any]] = []
        for candidate in candidates:
            image_id = str(candidate.get("imageId") or "")
            if not _IMAGE_ID_RE.fullmatch(image_id):
                return self._failure(
                    "RETIRED_DOCUMENT_IMAGE_CLEANUP_BLOCKED",
                    "IMAGE_CANDIDATE_INVALID",
                    "Cleanup plan contained an invalid image identity",
                )
            result = self._run(
                ["docker", "image", "rm", "--no-prune", image_id],
                timeout=300,
            )
            step = {
                "imageId": image_id,
                "ok": bool(result.get("ok")),
                "exitCode": result.get("exitCode"),
            }
            if not result.get("ok"):
                stderr = str(result.get("stderr") or "")
                step["stderrSha256"] = _fingerprint(stderr)
                step["stderrBytes"] = len(stderr.encode("utf-8"))
            steps.append(step)
            if not result.get("ok"):
                break

        try:
            remaining_candidates = self._retired_document_image_candidates()
        except RuntimeError:
            remaining_candidates = None
        after_disk = self._disk()
        original_ids = {str(item.get("imageId") or "") for item in candidates}
        remaining_ids = (
            sorted(
                original_ids
                & {
                    str(item.get("imageId") or "")
                    for item in remaining_candidates
                }
            )
            if remaining_candidates is not None
            else sorted(original_ids)
        )
        verified = bool(steps) and all(
            bool(step.get("ok")) for step in steps
        ) and not remaining_ids
        return {
            "ok": verified,
            "status": (
                "RETIRED_DOCUMENT_IMAGE_CLEANUP_VERIFIED"
                if verified
                else "RETIRED_DOCUMENT_IMAGE_CLEANUP_INCOMPLETE"
            ),
            "beforeDisk": before_disk,
            "afterDisk": after_disk,
            "estimatedReclaimableBytes": int(
                plan.get("estimatedReclaimableBytes") or 0
            ),
            "reclaimedBytes": max(
                0,
                int(before_disk.get("usedBytes") or 0)
                - int(after_disk.get("usedBytes") or 0),
            ),
            "steps": steps,
            "candidatesRemoved": sorted(
                str(step.get("imageId") or "")
                for step in steps
                if bool(step.get("ok"))
                and str(step.get("imageId") or "") not in remaining_ids
            ),
            "candidatesRemaining": remaining_ids,
            "volumesRemoved": False,
            "runningContainersRemoved": False,
            "nonRetiredImagesExplicitlyRemoved": False,
            "mutationPerformed": bool(steps),
            "secretValuesReturned": False,
        }

    def stage1_plan(self) -> dict[str, Any]:
        try:
            inspected = {name: self._inspect(name) for name in N8N_EXPECTED_SERVICES}
            if any(value is None for value in inspected.values()):
                raise RuntimeError("One or more n8n stack containers are absent")
            summaries = {name: self._summary(value or {}) for name, value in inspected.items()}
            for name, service in N8N_EXPECTED_SERVICES.items():
                row = summaries[name]
                if row.get("project") != N8N_PROJECT or row.get("service") != service:
                    raise RuntimeError(f"n8n container identity mismatch: {name}")
            anchor = summaries[N8N_CONTAINER]
            working_dir = Path(str(anchor.get("workingDir") or ""))
            if not working_dir.is_absolute() or not working_dir.is_dir() or working_dir.is_symlink():
                raise RuntimeError("Hostinger Compose working directory is unavailable")
            original_compose_files = self._original_compose_files(
                str(anchor.get("configFiles") or ""),
                working_dir,
            )
            original_compose_evidence = self._compose_file_evidence(original_compose_files)
            env_path = working_dir / ".env"
            host_env = self._read_host_env(env_path)
            missing = sorted(N8N_REQUIRED_HOST_ENV_KEYS - set(host_env))
            if missing:
                raise RuntimeError("Hostinger environment is missing required n8n keys: " + ",".join(missing))
            runtime_env = {
                N8N_CONTAINER: self._container_env(N8N_CONTAINER),
                N8N_SANDBOX_API_CONTAINER: self._container_env(N8N_SANDBOX_API_CONTAINER),
                N8N_SANDBOX_RUNNER_CONTAINER: self._container_env(N8N_SANDBOX_RUNNER_CONTAINER),
            }
            secret_bindings = {
                "sandboxApiKey": {
                    "hostPresent": bool(host_env.get("SANDBOX_API_KEY")),
                    "n8nMatchesHost": runtime_env[N8N_CONTAINER].get("N8N_SANDBOX_SERVICE_API_KEY") == host_env.get("SANDBOX_API_KEY"),
                    "apiMatchesHost": runtime_env[N8N_SANDBOX_API_CONTAINER].get("SANDBOX_API_KEYS") == host_env.get("SANDBOX_API_KEY"),
                },
                "runnerApiKey": {
                    "hostPresent": bool(host_env.get("SANDBOX_RUNNER_API_KEY")),
                    "apiMatchesHost": runtime_env[N8N_SANDBOX_API_CONTAINER].get("SANDBOX_API_RUNNER_API_KEY") == host_env.get("SANDBOX_RUNNER_API_KEY"),
                    "runnerMatchesHost": runtime_env[N8N_SANDBOX_RUNNER_CONTAINER].get("SANDBOX_RUNNER_API_KEYS") == host_env.get("SANDBOX_RUNNER_API_KEY"),
                },
                "runnerRegistrationToken": {
                    "hostPresent": bool(host_env.get("SANDBOX_RUNNER_REGISTRATION_TOKEN")),
                    "apiMatchesHost": runtime_env[N8N_SANDBOX_API_CONTAINER].get("SANDBOX_API_RUNNER_REGISTRATION_TOKEN") == host_env.get("SANDBOX_RUNNER_REGISTRATION_TOKEN"),
                    "runnerMatchesHost": runtime_env[N8N_SANDBOX_RUNNER_CONTAINER].get("SANDBOX_RUNNER_REGISTRATION_TOKEN") == host_env.get("SANDBOX_RUNNER_REGISTRATION_TOKEN"),
                },
            }
            host_values_present = all(bool(item.get("hostPresent")) for item in secret_bindings.values())
            runtime_matches_host = all(
                all(bool(value) for key, value in item.items() if key != "hostPresent")
                for item in secret_bindings.values()
            )
            runtime_n8n_env = runtime_env[N8N_CONTAINER]
            runtime_nexos_api_key = str(
                runtime_n8n_env.get("N8N_INSTANCE_AI_MODEL_API_KEY") or ""
            )
            runtime_instance_ai_model = str(
                runtime_n8n_env.get("N8N_INSTANCE_AI_MODEL") or ""
            )
            host_nexos_api_key = str(host_env.get("NEXOS_API_KEY") or "")
            host_instance_ai_model = str(host_env.get("N8N_INSTANCE_AI_MODEL") or "")
            effective_nexos_api_key = host_nexos_api_key or runtime_nexos_api_key
            effective_instance_ai_model = host_instance_ai_model or runtime_instance_ai_model
            instance_ai_enabled = bool(effective_nexos_api_key and effective_instance_ai_model)
            instance_ai_source = (
                "host-env"
                if host_nexos_api_key
                else "existing-runtime"
                if runtime_nexos_api_key
                else "disabled"
            )
            images = {
                "n8n": self._repo_digest(str(anchor.get("imageId") or ""), str(anchor.get("image") or "")),
                "sandboxApi": self._repo_digest(
                    str(summaries[N8N_SANDBOX_API_CONTAINER].get("imageId") or ""),
                    str(summaries[N8N_SANDBOX_API_CONTAINER].get("image") or ""),
                ),
                "sandboxRunner": self._repo_digest(
                    str(summaries[N8N_SANDBOX_RUNNER_CONTAINER].get("imageId") or ""),
                    str(summaries[N8N_SANDBOX_RUNNER_CONTAINER].get("image") or ""),
                ),
                "innerSandbox": self._inner_sandbox_digest(),
            }
            compose = self._stage1_compose(images, instance_ai_enabled=instance_ai_enabled)
            disk = self._disk()
            if disk["freeBytes"] < N8N_MIN_FREE_BYTES:
                raise RuntimeError("n8n stage1 requires at least 8 GiB free disk")
            state = {
                "schemaVersion": "sovereign.n8n-stage1.v1",
                "project": N8N_PROJECT,
                "containerIds": {name: row["id"] for name, row in summaries.items()},
                "hostEnvSha256": _fingerprint(env_path.read_text("utf-8")),
                "instanceAiEnabled": instance_ai_enabled,
                "instanceAiCredentialSha256": (
                    _fingerprint(effective_nexos_api_key) if instance_ai_enabled else ""
                ),
                "instanceAiModelSha256": (
                    _fingerprint(effective_instance_ai_model) if instance_ai_enabled else ""
                ),
                "images": images,
                "composeSha256": _fingerprint(compose),
                "originalComposeEvidence": original_compose_evidence,
                "diskFloorBytes": N8N_MIN_FREE_BYTES,
            }
            return {
                "ok": True,
                "status": "N8N_STAGE1_PLAN_READY",
                "project": N8N_PROJECT,
                "workingDirectory": str(working_dir),
                "hostEnvironment": {
                    "path": str(env_path),
                    "requiredKeysPresent": True,
                    "secretValuesReturned": False,
                },
                "secretBindings": secret_bindings,
                "hostSecretValuesPresent": host_values_present,
                "runtimeMatchesHostSecrets": runtime_matches_host,
                "rotationPendingRecreate": host_values_present and not runtime_matches_host,
                "instanceAiEnabled": instance_ai_enabled,
                "instanceAiCredential": {
                    "source": instance_ai_source,
                    "hostPresent": bool(host_nexos_api_key),
                    "runtimePresent": bool(runtime_nexos_api_key),
                    "modelHostPresent": bool(host_instance_ai_model),
                    "modelRuntimePresent": bool(runtime_instance_ai_model),
                    "secretValuesReturned": False,
                },
                "images": images,
                "containers": summaries,
                "disk": disk,
                "targetComposeSha256": state["composeSha256"],
                "originalComposeEvidence": original_compose_evidence,
                "confirmationSha256": _canonical_sha256(state),
                "originalComposeMutated": False,
                "mutationPerformed": False,
                "secretValuesReturned": False,
            }
        except (OSError, UnicodeError, RuntimeError) as exc:
            return self._failure("N8N_STAGE1_PLAN_BLOCKED", "N8N_RUNTIME_EVIDENCE_INCOMPLETE", str(exc))

    @staticmethod
    def _http_probe(host: str, port: int, path: str) -> bool:
        connection: http.client.HTTPConnection | None = None
        try:
            connection = http.client.HTTPConnection(host, port, timeout=5)
            connection.request("GET", path)
            response = connection.getresponse()
            response.read(4096)
            return 200 <= int(response.status) < 400
        except (OSError, http.client.HTTPException):
            return False
        finally:
            if connection is not None:
                connection.close()

    def _container_ip(self, inspect: dict[str, Any]) -> str:
        network_settings = inspect.get("NetworkSettings") if isinstance(inspect.get("NetworkSettings"), dict) else {}
        networks = network_settings.get("Networks") if isinstance(network_settings.get("Networks"), dict) else {}
        for value in networks.values():
            item = value if isinstance(value, dict) else {}
            candidate = str(item.get("IPAddress") or "")
            if candidate:
                return candidate
        return ""

    def _runtime_secret_matches(self, host_env: dict[str, str]) -> bool:
        n8n_env = self._container_env(N8N_CONTAINER)
        api_env = self._container_env(N8N_SANDBOX_API_CONTAINER)
        runner_env = self._container_env(N8N_SANDBOX_RUNNER_CONTAINER)
        return bool(
            n8n_env.get("N8N_SANDBOX_SERVICE_API_KEY") == host_env.get("SANDBOX_API_KEY")
            and api_env.get("SANDBOX_API_KEYS") == host_env.get("SANDBOX_API_KEY")
            and api_env.get("SANDBOX_API_RUNNER_API_KEY") == host_env.get("SANDBOX_RUNNER_API_KEY")
            and runner_env.get("SANDBOX_RUNNER_API_KEYS") == host_env.get("SANDBOX_RUNNER_API_KEY")
            and api_env.get("SANDBOX_API_RUNNER_REGISTRATION_TOKEN") == host_env.get("SANDBOX_RUNNER_REGISTRATION_TOKEN")
            and runner_env.get("SANDBOX_RUNNER_REGISTRATION_TOKEN") == host_env.get("SANDBOX_RUNNER_REGISTRATION_TOKEN")
        )

    def _original_compose_argv(
        self,
        *,
        working_dir: Path,
        env_path: Path,
        compose_files: list[Path],
    ) -> list[str]:
        argv = [
            "docker",
            "compose",
            "--project-name",
            N8N_PROJECT,
            "--project-directory",
            str(working_dir),
            "--env-file",
            str(env_path),
        ]
        for path in compose_files:
            argv.extend(["--file", str(path)])
        return argv

    def _rollback_original_compose(
        self,
        *,
        working_dir: Path,
        env_path: Path,
        compose_files: list[Path],
        host_env: dict[str, str],
        env_overrides: dict[str, str] | None = None,
        expected_instance_ai_model: str = "",
        expected_instance_ai_key: str = "",
    ) -> dict[str, Any]:
        argv = self._original_compose_argv(
            working_dir=working_dir,
            env_path=env_path,
            compose_files=compose_files,
        )
        rendered = self._run([*argv, "config"], timeout=120, env_overrides=env_overrides)
        if not rendered.get("ok"):
            return {
                "attempted": False,
                "verified": False,
                "failureFamily": "ORIGINAL_COMPOSE_RENDER_FAILED",
            }
        restored = self._run(
            [*argv, "up", "-d", "--force-recreate", "--remove-orphans", "--pull", "never"],
            timeout=900,
            env_overrides=env_overrides,
        )
        if not restored.get("ok"):
            return {
                "attempted": True,
                "verified": False,
                "failureFamily": "ORIGINAL_COMPOSE_RESTORE_FAILED",
                "exitCode": restored.get("exitCode"),
            }
        summaries: dict[str, Any] = {}
        for _attempt in range(45):
            observed = {name: self._inspect(name) for name in N8N_EXPECTED_SERVICES}
            summaries = {
                name: self._summary(value or {}) if value else {}
                for name, value in observed.items()
            }
            if (
                summaries.get(N8N_CONTAINER, {}).get("running")
                and summaries.get(N8N_SANDBOX_API_CONTAINER, {}).get("running")
                and summaries.get(N8N_SANDBOX_RUNNER_CONTAINER, {}).get("running")
                and summaries.get(N8N_SANDBOX_CERTS_CONTAINER, {}).get("status") == "exited"
                and summaries.get(N8N_SANDBOX_CERTS_CONTAINER, {}).get("exitCode") == 0
            ):
                break
            time.sleep(2)
        try:
            rotated_bindings_active = self._runtime_secret_matches(host_env)
            instance_ai_restored = True
            if expected_instance_ai_key:
                restored_n8n_env = self._container_env(N8N_CONTAINER)
                instance_ai_restored = bool(
                    restored_n8n_env.get("N8N_INSTANCE_AI_MODEL_API_KEY") == expected_instance_ai_key
                    and restored_n8n_env.get("N8N_INSTANCE_AI_MODEL") == expected_instance_ai_model
                )
        except RuntimeError:
            rotated_bindings_active = False
            instance_ai_restored = False
        verified = bool(
            summaries.get(N8N_CONTAINER, {}).get("running")
            and summaries.get(N8N_SANDBOX_API_CONTAINER, {}).get("running")
            and summaries.get(N8N_SANDBOX_RUNNER_CONTAINER, {}).get("running")
            and summaries.get(N8N_SANDBOX_CERTS_CONTAINER, {}).get("exitCode") == 0
            and rotated_bindings_active
            and instance_ai_restored
        )
        return {
            "attempted": True,
            "verified": verified,
            "failureFamily": None if verified else "ORIGINAL_COMPOSE_READBACK_INCOMPLETE",
            "rotatedSecretBindingsActive": rotated_bindings_active,
            "instanceAiRestored": instance_ai_restored,
            "containers": summaries,
            "secretValuesReturned": False,
        }

    def stage1_apply(self, *, confirmation_sha256: str, owner_approved: bool) -> dict[str, Any]:
        if not owner_approved:
            return self._failure("N8N_STAGE1_BLOCKED", "OWNER_APPROVAL_REQUIRED", "owner_approved=true is required")
        if not self._write_enabled():
            return self._failure("N8N_STAGE1_BLOCKED", "HOST_MAINTENANCE_WRITE_DISABLED", "Allowlisted Compose writes are disabled")
        plan = self.stage1_plan()
        if not plan.get("ok"):
            return plan
        expected = str(plan.get("confirmationSha256") or "")
        supplied = str(confirmation_sha256 or "").strip().lower()
        if not _SHA256_RE.fullmatch(supplied) or supplied != expected:
            return self._failure(
                "N8N_STAGE1_BLOCKED",
                "CONFIRMATION_MISMATCH",
                "n8n stage1 confirmation no longer matches current runtime, environment and image identity",
                expectedConfirmationSha256=expected,
            )
        if not plan.get("hostSecretValuesPresent"):
            return self._failure("N8N_STAGE1_BLOCKED", "HOST_ENV_SECRET_MISSING", "Rotated sandbox values are not present in the Hostinger environment")

        working_dir = Path(str(plan.get("workingDirectory") or ""))
        env_path = Path(str(plan.get("hostEnvironment", {}).get("path") or ""))
        host_env = self._read_host_env(env_path)
        current_n8n_env = self._container_env(N8N_CONTAINER)
        effective_nexos_api_key = str(
            host_env.get("NEXOS_API_KEY")
            or current_n8n_env.get("N8N_INSTANCE_AI_MODEL_API_KEY")
            or ""
        )
        effective_instance_ai_model = str(
            host_env.get("N8N_INSTANCE_AI_MODEL")
            or current_n8n_env.get("N8N_INSTANCE_AI_MODEL")
            or ""
        )
        instance_ai_enabled = bool(plan.get("instanceAiEnabled"))
        if instance_ai_enabled and not (effective_nexos_api_key and effective_instance_ai_model):
            return self._failure(
                "N8N_STAGE1_BLOCKED",
                "INSTANCE_AI_BINDING_DRIFT",
                "Instance AI was enabled in the plan but its runtime binding is no longer available",
            )
        compose_env_overrides = (
            {
                "NEXOS_API_KEY": effective_nexos_api_key,
                "N8N_INSTANCE_AI_MODEL": effective_instance_ai_model,
            }
            if instance_ai_enabled
            else {}
        )
        anchor = plan.get("containers", {}).get(N8N_CONTAINER, {})
        original_compose_files = self._original_compose_files(
            str(anchor.get("configFiles") or ""),
            working_dir,
        )
        if self._compose_file_evidence(original_compose_files) != list(plan.get("originalComposeEvidence") or []):
            return self._failure(
                "N8N_STAGE1_BLOCKED",
                "ORIGINAL_COMPOSE_DRIFT",
                "Hostinger Compose source changed after the confirmation plan was created",
            )
        images = dict(plan.get("images") or {})
        compose = self._stage1_compose(
            images,
            instance_ai_enabled=instance_ai_enabled,
        )
        self.maintenance_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.maintenance_root.is_symlink():
            return self._failure("N8N_STAGE1_BLOCKED", "MAINTENANCE_PATH_INVALID", "n8n maintenance root must not be a symlink")
        os.chmod(self.maintenance_root, 0o700)
        compose_path = self.maintenance_root / "compose.stage1.yml"
        descriptor = os.open(compose_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(compose)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(compose_path, 0o600)

        compose_argv = [
            "docker",
            "compose",
            "--project-name",
            N8N_PROJECT,
            "--project-directory",
            str(working_dir),
            "--env-file",
            str(env_path),
            "--file",
            str(compose_path),
        ]
        rendered = self._run(
            [*compose_argv, "config"],
            timeout=120,
            env_overrides=compose_env_overrides,
        )
        if not rendered.get("ok"):
            return self._failure("N8N_STAGE1_BLOCKED", "COMPOSE_RENDER_FAILED", "Generated n8n stage1 Compose did not render")

        previous_ids = {
            name: str(plan.get("containers", {}).get(name, {}).get("id") or "")
            for name in N8N_EXPECTED_SERVICES
        }
        deployed = self._run(
            [*compose_argv, "up", "-d", "--force-recreate", "--remove-orphans", "--pull", "never"],
            timeout=900,
            env_overrides=compose_env_overrides,
        )
        if not deployed.get("ok"):
            rollback = self._rollback_original_compose(
                working_dir=working_dir,
                env_path=env_path,
                compose_files=original_compose_files,
                host_env=host_env,
                env_overrides=compose_env_overrides,
                expected_instance_ai_model=effective_instance_ai_model if instance_ai_enabled else "",
                expected_instance_ai_key=effective_nexos_api_key if instance_ai_enabled else "",
            )
            return {
                **self._failure(
                    "N8N_STAGE1_DEPLOY_FAILED_ROLLED_BACK" if rollback.get("verified") else "N8N_STAGE1_DEPLOY_FAILED_ROLLBACK_INCOMPLETE",
                    "COMPOSE_UP_FAILED",
                    "n8n stage1 Compose recreate failed; original Hostinger Compose rollback was attempted",
                ),
                "rollback": rollback,
                "mutationPerformed": True,
            }

        summaries: dict[str, Any] = {}
        inspections: dict[str, Any] = {}
        for _attempt in range(45):
            inspections = {name: self._inspect(name) for name in N8N_EXPECTED_SERVICES}
            summaries = {name: self._summary(value or {}) if value else {} for name, value in inspections.items()}
            if (
                summaries.get(N8N_CONTAINER, {}).get("running")
                and summaries.get(N8N_SANDBOX_API_CONTAINER, {}).get("running")
                and summaries.get(N8N_SANDBOX_RUNNER_CONTAINER, {}).get("running")
                and summaries.get(N8N_SANDBOX_CERTS_CONTAINER, {}).get("status") == "exited"
                and summaries.get(N8N_SANDBOX_CERTS_CONTAINER, {}).get("exitCode") == 0
            ):
                break
            time.sleep(2)

        ids_changed = all(
            summaries.get(name, {}).get("id")
            and summaries.get(name, {}).get("id") != previous_ids.get(name)
            for name in N8N_EXPECTED_SERVICES
        )
        port_bindings = summaries.get(N8N_CONTAINER, {}).get("ports") or []
        loopback_only = bool(port_bindings) and all(
            item.get("hostIp") in {"127.0.0.1", "::1"}
            for item in port_bindings
            if item.get("hostPort")
        ) and any(
            item.get("containerPort") == "5678/tcp"
            and item.get("hostIp") == "127.0.0.1"
            and item.get("hostPort") == "5678"
            for item in port_bindings
        )
        images_match = bool(
            summaries.get(N8N_CONTAINER, {}).get("image") == images.get("n8n")
            and summaries.get(N8N_SANDBOX_API_CONTAINER, {}).get("image") == images.get("sandboxApi")
            and summaries.get(N8N_SANDBOX_RUNNER_CONTAINER, {}).get("image") == images.get("sandboxRunner")
        )
        secret_bindings_match = self._runtime_secret_matches(host_env)
        n8n_env = self._container_env(N8N_CONTAINER)
        instance_ai_preserved = bool(
            not instance_ai_enabled
            or (
                n8n_env.get("N8N_INSTANCE_AI_MODEL_API_KEY") == effective_nexos_api_key
                and n8n_env.get("N8N_INSTANCE_AI_MODEL") == effective_instance_ai_model
                and "instance-ai" in str(n8n_env.get("N8N_ENABLED_MODULES") or "")
            )
        )
        proxy_contract = bool(
            n8n_env.get("N8N_PROXY_HOPS") == "1"
            and n8n_env.get("N8N_SECURE_COOKIE") == "true"
            and n8n_env.get("N8N_WEBHOOK_URL", "").startswith("https://")
            and "WEBHOOK_URL" not in n8n_env
            and "N8N_RUNNERS_ENABLED" not in n8n_env
        )
        local_health = self._http_probe("127.0.0.1", 5678, "/healthz")
        api_ip = self._container_ip(inspections.get(N8N_SANDBOX_API_CONTAINER) or {})
        runner_ip = self._container_ip(inspections.get(N8N_SANDBOX_RUNNER_CONTAINER) or {})
        sandbox_api_health = bool(api_ip and self._http_probe(api_ip, 8080, "/healthz"))
        sandbox_runner_health = bool(runner_ip and self._http_probe(runner_ip, 8080, "/readyz"))
        logs = self._run(["docker", "logs", "--since", "5m", N8N_CONTAINER], timeout=60)
        combined_logs = str(logs.get("stdout") or "") + "\n" + str(logs.get("stderr") or "")
        proxy_error_absent = "ERR_ERL_UNEXPECTED_X_FORWARDED_FOR" not in combined_logs
        deprecated_webhook_absent = "WEBHOOK_URL -> Use N8N_WEBHOOK_URL" not in combined_logs
        disk = self._disk()
        verified = bool(
            ids_changed
            and loopback_only
            and images_match
            and secret_bindings_match
            and instance_ai_preserved
            and proxy_contract
            and local_health
            and sandbox_api_health
            and sandbox_runner_health
            and proxy_error_absent
            and deprecated_webhook_absent
            and summaries.get(N8N_SANDBOX_CERTS_CONTAINER, {}).get("exitCode") == 0
        )
        rollback = (
            {"attempted": False, "verified": False, "failureFamily": None}
            if verified
            else self._rollback_original_compose(
                working_dir=working_dir,
                env_path=env_path,
                compose_files=original_compose_files,
                host_env=host_env,
                env_overrides=compose_env_overrides,
                expected_instance_ai_model=effective_instance_ai_model if instance_ai_enabled else "",
                expected_instance_ai_key=effective_nexos_api_key if instance_ai_enabled else "",
            )
        )
        return {
            "ok": verified,
            "status": (
                "N8N_STAGE1_RECREATED_VERIFIED"
                if verified
                else "N8N_STAGE1_RECREATED_UNVERIFIED_ROLLED_BACK"
                if rollback.get("verified")
                else "N8N_STAGE1_RECREATED_UNVERIFIED_ROLLBACK_INCOMPLETE"
            ),
            "project": N8N_PROJECT,
            "containers": summaries,
            "containerIdsChanged": ids_changed,
            "loopbackPortVerified": loopback_only,
            "immutableImagesVerified": images_match,
            "rotatedSecretBindingsMatchHost": secret_bindings_match,
            "instanceAiPreserved": instance_ai_preserved,
            "proxyContractVerified": proxy_contract,
            "n8nHealthVerified": local_health,
            "sandboxApiHealthVerified": sandbox_api_health,
            "sandboxRunnerHealthVerified": sandbox_runner_health,
            "proxyForwardedForErrorAbsent": proxy_error_absent,
            "deprecatedWebhookWarningAbsent": deprecated_webhook_absent,
            "disk": disk,
            "originalHostingerComposeMutated": False,
            "runtimeComposePath": str(compose_path),
            "rollback": rollback,
            "readbackVerified": verified,
            "mutationPerformed": True,
            "secretValuesReturned": False,
        }
