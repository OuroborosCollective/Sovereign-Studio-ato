from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

PROJECT_NAME = "sovereign-litellm"
NETWORK_NAME = "sovereign-private"
LITELLM_CONTAINER = "sovereign-litellm-litellm-1"
DB_CONTAINER = "sovereign-litellm-db-1"
LITELLM_IMAGE = "docker.litellm.ai/berriai/litellm:v1.89.4"
DB_IMAGE = "postgres:16-alpine"
OWNER_SECRET_ROOT = Path("/opt/sovereign-owner-managed")
PROVIDER_INPUT_PATH = OWNER_SECRET_ROOT / "openai_api_key.txt"
BACKEND_SERVICE_KEY_PATH = OWNER_SECRET_ROOT / "litellm_master_key.txt"
ALIAS_SELECTION_FILENAME = "model-aliases.json"
EXPECTED_MODEL_IDS = ("sovereign-fast", "sovereign-balanced")
REQUIRED_SECRET_NAMES = (
    "POSTGRES_PASSWORD",
    "LITELLM_MASTER_KEY",
    "LITELLM_SALT_KEY",
)
_SAFE_DB_PASSWORD = re.compile(r"^[A-Za-z0-9._~-]{16,256}$")
_SAFE_KEY_SECRET = re.compile(r"^[A-Za-z0-9._~!@%+=:,/-]{16,512}$")
_SAFE_PROVIDER_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bounded(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "ok": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": result.stdout[-24_000:],
        "stderr": result.stderr[-24_000:],
    }


class LiteLLMStackRuntime:
    """Deploy exactly one fixed Sovereign LiteLLM stack without generic shell access."""

    def __init__(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        template_root: str | None = None,
        deploy_root: str | None = None,
    ) -> None:
        self._runner = runner or subprocess.run
        self.template_root = Path(
            template_root
            or os.getenv(
                "SOVEREIGN_LITELLM_TEMPLATE_ROOT",
                "/opt/sovereign-chatgpt-tools/templates/sovereign-litellm",
            )
        )
        self.deploy_root = Path(
            deploy_root
            or os.getenv("SOVEREIGN_LITELLM_DEPLOY_ROOT", "/opt/sovereign-litellm")
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
        return _bounded(completed)

    def _template(self, name: str) -> tuple[bytes, str]:
        path = self.template_root / name
        if self.template_root.is_symlink() or path.is_symlink() or not path.is_file():
            raise FileNotFoundError(f"Festes LiteLLM-Template fehlt: {name}")
        payload = path.read_bytes()
        if len(payload) > 100_000:
            raise ValueError(f"LiteLLM-Template ist zu groß: {name}")
        return payload, _sha256(payload)

    def _compose_command_prefix(self) -> list[str]:
        return [
            "docker",
            "compose",
            "--project-name",
            PROJECT_NAME,
            "--project-directory",
            str(self.deploy_root),
            "--env-file",
            str(self.deploy_root / ".env"),
            "--file",
            str(self.deploy_root / "docker-compose.yml"),
        ]

    def _compose_up_command(self) -> list[str]:
        return [
            *self._compose_command_prefix(),
            "up",
            "-d",
            "--remove-orphans",
        ]

    def _litellm_recreate_command(self) -> list[str]:
        """Recreate only LiteLLM so atomic provider-secret rotation remounts the new inode."""
        return [
            *self._compose_command_prefix(),
            "up",
            "-d",
            "--force-recreate",
            "--no-deps",
            "litellm",
        ]

    def _container_state(self, container: str) -> dict[str, Any]:
        inspected = self._run(
            [
                "docker",
                "inspect",
                "--format",
                "{{json .State}}|{{json .NetworkSettings.Networks}}|{{json .NetworkSettings.Ports}}",
                container,
            ],
            timeout=30,
        )
        if not inspected["ok"]:
            return {"present": False, "container": container}
        try:
            state_raw, networks_raw, ports_raw = inspected["stdout"].strip().split("|", 2)
            state = json.loads(state_raw)
            networks = json.loads(networks_raw)
            ports = json.loads(ports_raw)
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Docker-Inspect für {container} ist ungültig: {exc}") from exc
        published = {
            key: value
            for key, value in (ports or {}).items()
            if isinstance(value, list) and value
        }
        return {
            "present": True,
            "container": container,
            "running": bool(state.get("Running")),
            "status": str(state.get("Status") or "unknown"),
            "health": str((state.get("Health") or {}).get("Status") or "none"),
            "networks": sorted((networks or {}).keys()),
            "publishedPorts": published,
        }

    def plan(self) -> dict[str, Any]:
        compose, compose_sha = self._template("docker-compose.yml")
        config, config_sha = self._template("config.yaml")
        entrypoint, entrypoint_sha = self._template("sovereign-entrypoint.py")
        return {
            "ok": True,
            "status": "PLAN_READY",
            "project": PROJECT_NAME,
            "network": NETWORK_NAME,
            "deployRoot": str(self.deploy_root),
            "templates": {
                "docker-compose.yml": {"sha256": compose_sha, "bytes": len(compose)},
                "config.yaml": {"sha256": config_sha, "bytes": len(config)},
                "sovereign-entrypoint.py": {"sha256": entrypoint_sha, "bytes": len(entrypoint)},
            },
            "composeWriteEnabled": (
                os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() == "1"
                and os.getenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "0").strip() == "1"
            ),
            "aliasSelectionPresent": self._alias_selection_path().is_file()
            and not self._alias_selection_path().is_symlink(),
            "containers": {
                "litellm": self._container_state(LITELLM_CONTAINER),
                "db": self._container_state(DB_CONTAINER),
            },
            "acceptedInputs": [
                "confirmation_compose_sha256",
                "confirmation_config_sha256",
                "confirmation_entrypoint_sha256",
            ],
            "arbitraryYamlAccepted": False,
            "arbitraryCommandAccepted": False,
            "secretValuesAccepted": False,
        }

    def _validate_owner_provider_input(self) -> None:
        root = OWNER_SECRET_ROOT
        path = PROVIDER_INPUT_PATH
        if root.is_symlink() or path.is_symlink() or not path.is_file():
            raise RuntimeError("Geschützter Provider-Zugang fehlt im Owner-Speicher")
        metadata = path.stat()
        size = metadata.st_size
        if size < 16 or size > 8192:
            raise RuntimeError("Geschützter Provider-Zugang hat eine ungültige Größe")
        if metadata.st_mode & 0o077:
            raise RuntimeError("Geschützter Provider-Zugang besitzt unsichere Dateirechte")

    def provider_model_inventory(self) -> dict[str, Any]:
        """Read only OpenAI model ids in an ephemeral, portless LiteLLM image."""
        self._validate_owner_provider_input()
        script = """
import json
import pathlib
import urllib.request

path = pathlib.Path('/run/secrets/openai_api_key')
if path.is_symlink() or not path.is_file():
    raise SystemExit(21)
value = path.read_text('utf-8').strip()
if len(value) < 16 or '\\x00' in value or '\\n' in value or '\\r' in value:
    raise SystemExit(22)
request = urllib.request.Request(
    'https://api.openai.com/v1/models',
    headers={'Authorization': 'Bearer ' + value},
)
with urllib.request.urlopen(request, timeout=30) as response:
    model_http_status = response.status
    model_project_id = str(response.headers.get('openai-project') or '').strip()
    payload = json.loads(response.read().decode('utf-8'))
identity_request = urllib.request.Request(
    'https://api.openai.com/v1/me',
    headers={'Authorization': 'Bearer ' + value},
)
with urllib.request.urlopen(identity_request, timeout=30) as identity_response:
    identity_http_status = identity_response.status
    identity_project_id = str(identity_response.headers.get('openai-project') or '').strip()
    identity_payload = json.loads(identity_response.read().decode('utf-8'))
model_ids = sorted({
    str(item.get('id') or '').strip()
    for item in payload.get('data', [])
    if isinstance(item, dict) and str(item.get('id') or '').strip()
})
organization_ids = sorted({
    str(item.get('id') or '').strip()
    for item in ((identity_payload.get('orgs') or {}).get('data') or [])
    if isinstance(item, dict) and str(item.get('id') or '').strip()
})
print(json.dumps({
    'httpStatus': model_http_status,
    'modelIds': model_ids,
    'identityHttpStatus': identity_http_status,
    'principalId': str(identity_payload.get('id') or '').strip(),
    'principalName': str(identity_payload.get('name') or '').strip(),
    'organizationIds': organization_ids,
    'projectId': identity_project_id or model_project_id,
}, separators=(',', ':')))
"""
        result = self._run(
            [
                "docker",
                "run",
                "--rm",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=16m",
                "--mount",
                f"type=bind,src={PROVIDER_INPUT_PATH},dst=/run/secrets/openai_api_key,readonly",
                "--entrypoint",
                "python",
                LITELLM_IMAGE,
                "-c",
                script,
            ],
            timeout=60,
        )
        if not result["ok"]:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "OpenAI-Modellinventar konnte im isolierten LiteLLM-Image nicht gelesen werden",
                "exitCode": result["exit_code"],
                "secretValuesExposed": False,
            }
        try:
            payload = json.loads(result["stdout"].strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "OpenAI-Modellinventar lieferte keine gültige Metadatenantwort",
                "secretValuesExposed": False,
            }
        model_ids = sorted({
            str(model_id or "").strip()
            for model_id in payload.get("modelIds", [])
            if _SAFE_PROVIDER_MODEL.fullmatch(str(model_id or "").strip())
        })
        principal_id = str(payload.get("principalId") or "").strip()
        if not _SAFE_PROVIDER_MODEL.fullmatch(principal_id):
            principal_id = ""
        principal_name = "".join(
            character
            for character in str(payload.get("principalName") or "")
            if character.isprintable()
        ).strip()[:160]
        organization_ids = sorted({
            str(organization_id or "").strip()
            for organization_id in payload.get("organizationIds", [])
            if _SAFE_PROVIDER_MODEL.fullmatch(str(organization_id or "").strip())
        })
        project_id = str(payload.get("projectId") or "").strip()
        if project_id and not _SAFE_PROVIDER_MODEL.fullmatch(project_id):
            project_id = ""
        identity_verified = payload.get("identityHttpStatus") == 200 and bool(principal_id)
        inventory_sha = _sha256(("\n".join(model_ids) + "\n").encode("utf-8"))
        return {
            "ok": payload.get("httpStatus") == 200 and bool(model_ids) and identity_verified,
            "status": "PROVIDER_MODEL_INVENTORY",
            "httpStatus": payload.get("httpStatus"),
            "modelCount": len(model_ids),
            "modelIds": model_ids[:200],
            "inventorySha256": inventory_sha,
            "truncated": len(model_ids) > 200,
            "providerIdentity": {
                "verified": identity_verified,
                "httpStatus": payload.get("identityHttpStatus"),
                "principalId": principal_id,
                "principalName": principal_name,
                "organizationIds": organization_ids,
                "projectId": project_id,
            },
            "providerKeyPresent": True,
            "providerKeyValueReturned": False,
            "secretValuesExposed": False,
            "publicPortOpened": False,
        }

    def _alias_selection_path(self) -> Path:
        return self.deploy_root / ALIAS_SELECTION_FILENAME

    def _load_alias_selection(self) -> dict[str, str] | None:
        path = self._alias_selection_path()
        if path.is_symlink():
            raise RuntimeError("LiteLLM-Alias-Auswahl darf kein Symlink sein")
        if not path.exists():
            return None
        if not path.is_file() or path.stat().st_size > 8192:
            raise RuntimeError("LiteLLM-Alias-Auswahl ist ungültig")
        try:
            payload = json.loads(path.read_text("utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("LiteLLM-Alias-Auswahl ist kein gültiges JSON") from exc
        if not isinstance(payload, dict) or set(payload) != {
            "inventorySha256",
            "sovereign-fast",
            "sovereign-balanced",
        }:
            raise RuntimeError("LiteLLM-Alias-Auswahl besitzt ein ungültiges Schema")
        normalized = {key: str(value or "").strip() for key, value in payload.items()}
        if not re.fullmatch(r"[0-9a-f]{64}", normalized["inventorySha256"]):
            raise RuntimeError("LiteLLM-Inventar-Bindung ist ungültig")
        if not all(_SAFE_PROVIDER_MODEL.fullmatch(normalized[key]) for key in EXPECTED_MODEL_IDS):
            raise RuntimeError("LiteLLM-Provider-Modellauswahl ist ungültig")
        return normalized

    @staticmethod
    def _alias_config(selection: dict[str, str]) -> bytes:
        fast_model = json.dumps("openai/" + selection["sovereign-fast"])
        balanced_model = json.dumps("openai/" + selection["sovereign-balanced"])
        return (
            "# Generated only from a confirmed provider inventory.\n"
            "model_list:\n"
            "  - model_name: sovereign-fast\n"
            "    litellm_params:\n"
            f"      model: {fast_model}\n"
            "      api_key: os.environ/OPENAI_API_KEY\n"
            "  - model_name: sovereign-balanced\n"
            "    litellm_params:\n"
            f"      model: {balanced_model}\n"
            "      api_key: os.environ/OPENAI_API_KEY\n"
            "\nlitellm_settings:\n"
            "  drop_params: true\n"
        ).encode("utf-8")

    def _resolved_config(self, template_config: bytes) -> tuple[bytes, dict[str, Any] | None]:
        selection = self._load_alias_selection()
        if selection is None:
            return template_config, None
        inventory = self.provider_model_inventory()
        if not inventory.get("ok"):
            raise RuntimeError("Provider-Modellinventar ist für die Alias-Auswahl nicht verfügbar")
        if inventory.get("inventorySha256") != selection["inventorySha256"]:
            raise RuntimeError("Provider-Modellinventar hat sich seit der Alias-Bestätigung geändert")
        available = set(inventory.get("modelIds") or [])
        missing = [selection[key] for key in EXPECTED_MODEL_IDS if selection[key] not in available]
        if missing:
            raise RuntimeError("Bestätigte Provider-Modelle sind im aktuellen Inventar nicht verfügbar")
        return self._alias_config(selection), {
            "inventorySha256": selection["inventorySha256"],
            "aliases": {key: selection[key] for key in EXPECTED_MODEL_IDS},
        }

    def _write_backend_service_key(self, value: str) -> None:
        root = OWNER_SECRET_ROOT
        if root.is_symlink():
            raise RuntimeError("Owner-Secret-Root darf kein Symlink sein")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        if BACKEND_SERVICE_KEY_PATH.is_symlink():
            raise RuntimeError("Backend-Service-Key-Ziel darf kein Symlink sein")
        self._write_atomic(BACKEND_SERVICE_KEY_PATH, (value + "\n").encode("utf-8"), 0o600)

    def _existing_secret_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for container in (LITELLM_CONTAINER, DB_CONTAINER):
            result = self._run(
                ["docker", "inspect", "--format", "{{json .Config.Env}}", container],
                timeout=30,
            )
            if not result["ok"]:
                continue
            try:
                environment = json.loads(result["stdout"])
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Container-Environment ist nicht lesbar: {container}") from exc
            for item in environment if isinstance(environment, list) else []:
                if not isinstance(item, str) or "=" not in item:
                    continue
                key, value = item.split("=", 1)
                if key in REQUIRED_SECRET_NAMES and value:
                    values[key] = value
        missing = [name for name in REQUIRED_SECRET_NAMES if not values.get(name)]
        if missing:
            raise RuntimeError(
                "Bestehende LiteLLM-Container enthalten nicht alle benötigten geschützten Werte: "
                + ", ".join(missing)
            )
        invalid = [
            name
            for name, value in values.items()
            if not (
                (_SAFE_DB_PASSWORD.fullmatch(value) if name == "POSTGRES_PASSWORD" else _SAFE_KEY_SECRET.fullmatch(value))
            )
        ]
        if invalid:
            raise RuntimeError(
                "Geschützte Werte können nicht sicher in die feste Compose-Env migriert werden: "
                + ", ".join(sorted(invalid))
            )
        return values

    @staticmethod
    def _write_atomic(path: Path, payload: bytes, mode: int) -> None:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            mode,
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, mode)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _prepare_root(self) -> None:
        if self.deploy_root.is_symlink():
            raise RuntimeError("LiteLLM-Deploy-Root darf kein Symlink sein")
        self.deploy_root.mkdir(parents=True, exist_ok=True, mode=0o750)
        os.chmod(self.deploy_root, 0o750)

    def _validate_candidate(
        self,
        compose: bytes,
        config: bytes,
        entrypoint: bytes,
        env_payload: bytes,
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="sovereign-litellm-") as directory:
            root = Path(directory)
            compose_path = root / "docker-compose.yml"
            config_path = root / "config.yaml"
            entrypoint_path = root / "sovereign-entrypoint.py"
            env_path = root / ".env"
            compose_path.write_bytes(compose)
            config_path.write_bytes(config)
            entrypoint_path.write_bytes(entrypoint)
            env_path.write_bytes(env_payload)
            rendered = self._run(
                [
                    "docker",
                    "compose",
                    "--project-name",
                    PROJECT_NAME,
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
            if not rendered["ok"]:
                return {
                    "ok": False,
                    "exit_code": rendered["exit_code"],
                    "error": "docker compose config failed",
                }
            try:
                payload = json.loads(rendered["stdout"])
            except json.JSONDecodeError:
                return {"ok": False, "error": "docker compose config returned invalid JSON"}

            services = payload.get("services") if isinstance(payload.get("services"), dict) else {}
            if set(services) != {"db", "litellm"}:
                return {"ok": False, "error": "unexpected LiteLLM services"}
            networks = payload.get("networks") if isinstance(payload.get("networks"), dict) else {}
            if set(networks) != {NETWORK_NAME}:
                return {"ok": False, "error": "unexpected LiteLLM networks"}
            volumes = payload.get("volumes") if isinstance(payload.get("volumes"), dict) else {}
            if set(volumes) != {"litellm_db"}:
                return {"ok": False, "error": "unexpected LiteLLM volumes"}

            expected_images = {"db": DB_IMAGE, "litellm": LITELLM_IMAGE}
            for service_name, service in services.items():
                if not isinstance(service, dict):
                    return {"ok": False, "error": f"invalid service: {service_name}"}
                if str(service.get("image") or "") != expected_images[service_name]:
                    return {"ok": False, "error": f"unexpected image: {service_name}"}
                if service.get("privileged") or service.get("devices") or service.get("cap_add"):
                    return {"ok": False, "error": f"forbidden privileges: {service_name}"}
                if service.get("network_mode") == "host" or service.get("pid") == "host" or service.get("ipc") == "host":
                    return {"ok": False, "error": f"forbidden host namespace: {service_name}"}
                if service.get("build") or service.get("extra_hosts"):
                    return {"ok": False, "error": f"forbidden execution override: {service_name}"}
                if service.get("ports"):
                    return {"ok": False, "error": f"published ports are forbidden: {service_name}"}
                service_networks = service.get("networks")
                used_networks = set(service_networks) if isinstance(service_networks, dict) else set(service_networks or [])
                if used_networks != {NETWORK_NAME}:
                    return {"ok": False, "error": f"unexpected service network: {service_name}"}

            if services["db"].get("command") not in (None, [], ""):
                return {"ok": False, "error": "unexpected database command"}
            if services["db"].get("entrypoint") not in (None, [], ""):
                return {"ok": False, "error": "unexpected database entrypoint"}
            if services["litellm"].get("entrypoint") != ["python", "/app/sovereign-entrypoint.py"]:
                return {"ok": False, "error": "unexpected LiteLLM entrypoint"}
            if services["litellm"].get("command") != ["--config=/app/config.yaml", "--port", "4000"]:
                return {"ok": False, "error": "unexpected LiteLLM command"}
            db_environment = services["db"].get("environment") if isinstance(services["db"].get("environment"), dict) else {}
            if set(db_environment) != {"POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"}:
                return {"ok": False, "error": "unexpected database environment"}
            if db_environment.get("POSTGRES_DB") != "litellm" or db_environment.get("POSTGRES_USER") != "litellm":
                return {"ok": False, "error": "unexpected database identity"}
            litellm_environment = services["litellm"].get("environment") if isinstance(services["litellm"].get("environment"), dict) else {}
            if set(litellm_environment) != {"DATABASE_URL", "LITELLM_MASTER_KEY", "LITELLM_SALT_KEY"}:
                return {"ok": False, "error": "unexpected LiteLLM environment"}
            database_url = str(litellm_environment.get("DATABASE_URL") or "")
            if not database_url.startswith("postgresql://litellm:") or not database_url.endswith("@db:5432/litellm"):
                return {"ok": False, "error": "unexpected LiteLLM database URL"}

            db_volumes = services["db"].get("volumes") if isinstance(services["db"].get("volumes"), list) else []
            if len(db_volumes) != 1:
                return {"ok": False, "error": "unexpected database volume count"}
            db_volume = db_volumes[0] if isinstance(db_volumes[0], dict) else {}
            if db_volume.get("type") != "volume" or db_volume.get("source") != "litellm_db" or db_volume.get("target") != "/var/lib/postgresql/data":
                return {"ok": False, "error": "unexpected database volume"}

            litellm_volumes = services["litellm"].get("volumes") if isinstance(services["litellm"].get("volumes"), list) else []
            if len(litellm_volumes) != 3:
                return {"ok": False, "error": "unexpected LiteLLM volume count"}
            mounts = {
                str(volume.get("target") or ""): volume
                for volume in litellm_volumes
                if isinstance(volume, dict)
            }
            config_mount = mounts.get("/app/config.yaml", {})
            if (
                config_mount.get("type") != "bind"
                or Path(str(config_mount.get("source") or "")).resolve() != config_path.resolve()
                or not bool(config_mount.get("read_only"))
            ):
                return {"ok": False, "error": "unexpected LiteLLM config mount"}
            entrypoint_mount = mounts.get("/app/sovereign-entrypoint.py", {})
            if (
                entrypoint_mount.get("type") != "bind"
                or Path(str(entrypoint_mount.get("source") or "")).resolve() != entrypoint_path.resolve()
                or not bool(entrypoint_mount.get("read_only"))
            ):
                return {"ok": False, "error": "unexpected LiteLLM entrypoint mount"}
            provider_mount = mounts.get("/run/secrets/openai_api_key", {})
            if (
                provider_mount.get("type") != "bind"
                or Path(str(provider_mount.get("source") or "")).resolve() != PROVIDER_INPUT_PATH.resolve()
                or not bool(provider_mount.get("read_only"))
            ):
                return {"ok": False, "error": "unexpected LiteLLM provider mount"}
            return {"ok": True, "status": "VALIDATED"}

    def _wait_for_runtime(self) -> dict[str, Any]:
        last_litellm: dict[str, Any] = {}
        last_db: dict[str, Any] = {}
        for _attempt in range(45):
            last_litellm = self._container_state(LITELLM_CONTAINER)
            last_db = self._container_state(DB_CONTAINER)
            if (
                last_litellm.get("running")
                and last_litellm.get("health") == "healthy"
                and last_db.get("running")
                and last_db.get("health") == "healthy"
            ):
                break
            time.sleep(2)
        return {"litellm": last_litellm, "db": last_db}

    def _readiness(self) -> dict[str, Any]:
        script = (
            "import json,urllib.request;"
            "r=urllib.request.urlopen('http://127.0.0.1:4000/health/readiness',timeout=8);"
            "d=json.loads(r.read().decode());"
            "print(json.dumps({'httpStatus':r.status,'status':d.get('status'),'db':d.get('db')}))"
        )
        result = self._run(["docker", "exec", LITELLM_CONTAINER, "python", "-c", script], timeout=30)
        if not result["ok"]:
            return {"ok": False, "error": "LiteLLM readiness request failed", "exit_code": result["exit_code"]}
        try:
            payload = json.loads(result["stdout"].strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            return {"ok": False, "error": "Readiness-Antwort ist kein gültiges JSON"}
        return {"ok": payload.get("httpStatus") == 200, **payload}

    def _models(self) -> dict[str, Any]:
        script = (
            "import json,os,urllib.request;"
            "q=urllib.request.Request('http://127.0.0.1:4000/v1/models',headers={'Authorization':'Bearer '+os.environ['LITELLM_MASTER_KEY']});"
            "r=urllib.request.urlopen(q,timeout=8);"
            "d=json.loads(r.read().decode());"
            "print(json.dumps({'httpStatus':r.status,'modelIds':[str(x.get('id') or '') for x in d.get('data',[]) if isinstance(x,dict)]}))"
        )
        result = self._run(["docker", "exec", LITELLM_CONTAINER, "python", "-c", script], timeout=30)
        if not result["ok"]:
            return {"ok": False, "error": "LiteLLM models request failed", "exit_code": result["exit_code"]}
        try:
            payload = json.loads(result["stdout"].strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            return {"ok": False, "error": "Modell-Antwort ist kein gültiges JSON"}
        model_ids = payload.get("modelIds") if isinstance(payload.get("modelIds"), list) else []
        normalized_model_ids = sorted({
            str(model_id or "").strip()
            for model_id in model_ids
            if str(model_id or "").strip()
        })
        expected_models_present = all(
            model_id in normalized_model_ids for model_id in EXPECTED_MODEL_IDS
        )
        return {
            "ok": payload.get("httpStatus") == 200 and expected_models_present,
            "httpStatus": payload.get("httpStatus"),
            "modelCount": len(normalized_model_ids),
            "modelIds": normalized_model_ids[:20],
            "expectedModelIds": list(EXPECTED_MODEL_IDS),
            "expectedModelsPresent": expected_models_present,
        }

    def _completion_canary(self, model_id: str) -> dict[str, Any]:
        script = (
            "import json,os,sys,urllib.request;"
            "model=sys.argv[1];"
            "body=json.dumps({'model':model,'messages':[{'role':'user','content':'Reply with OK.'}],'max_tokens':8,'stream':False},separators=(',',':')).encode('utf-8');"
            "q=urllib.request.Request('http://127.0.0.1:4000/v1/chat/completions',data=body,headers={'Authorization':'Bearer '+os.environ['LITELLM_MASTER_KEY'],'Content-Type':'application/json'},method='POST');"
            "r=urllib.request.urlopen(q,timeout=45);"
            "d=json.loads(r.read().decode());"
            "u=d.get('usage') if isinstance(d.get('usage'),dict) else {};"
            "rid=r.headers.get('x-litellm-call-id') or r.headers.get('x-request-id') or d.get('id') or '';"
            "print(json.dumps({'httpStatus':r.status,'requestIdPresent':bool(str(rid).strip()),'resolvedModel':str(d.get('model') or ''),'promptTokens':int(u.get('prompt_tokens') or 0),'completionTokens':int(u.get('completion_tokens') or 0),'totalTokens':int(u.get('total_tokens') or 0)}))"
        )
        result = self._run(
            ["docker", "exec", LITELLM_CONTAINER, "python", "-c", script, model_id],
            timeout=60,
        )
        if not result["ok"]:
            return {
                "ok": False,
                "requestedModel": model_id,
                "error": "LiteLLM completion canary failed",
                "exit_code": result["exit_code"],
            }
        try:
            payload = json.loads(result["stdout"].strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            return {
                "ok": False,
                "requestedModel": model_id,
                "error": "Completion-Canary-Antwort ist kein gültiges JSON",
            }
        total_tokens = max(0, int(payload.get("totalTokens") or 0))
        request_id_present = bool(payload.get("requestIdPresent"))
        resolved_model = str(payload.get("resolvedModel") or "").strip()[:160]
        return {
            "ok": (
                payload.get("httpStatus") == 200
                and request_id_present
                and total_tokens > 0
                and bool(resolved_model)
            ),
            "requestedModel": model_id,
            "resolvedModel": resolved_model,
            "httpStatus": payload.get("httpStatus"),
            "requestIdPresent": request_id_present,
            "usage": {
                "promptTokens": max(0, int(payload.get("promptTokens") or 0)),
                "completionTokens": max(0, int(payload.get("completionTokens") or 0)),
                "totalTokens": total_tokens,
            },
            "responseContentExposed": False,
            "secretValuesExposed": False,
        }

    def deploy(
        self,
        *,
        confirmation_compose_sha256: str,
        confirmation_config_sha256: str,
        confirmation_entrypoint_sha256: str,
    ) -> dict[str, Any]:
        if os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Private Owner Mode ist nicht aktiv"}
        if os.getenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "0").strip() != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Allowlistete Compose-Writes sind nicht aktiviert"}

        compose, compose_sha = self._template("docker-compose.yml")
        template_config, config_sha = self._template("config.yaml")
        entrypoint, entrypoint_sha = self._template("sovereign-entrypoint.py")
        if (
            confirmation_compose_sha256 != compose_sha
            or confirmation_config_sha256 != config_sha
            or confirmation_entrypoint_sha256 != entrypoint_sha
        ):
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Bestätigte Template-Hashes stimmen nicht mit den installierten Templates überein",
                "expected": {
                    "compose": compose_sha,
                    "config": config_sha,
                    "entrypoint": entrypoint_sha,
                },
            }

        config, alias_selection = self._resolved_config(template_config)
        secret_values = self._existing_secret_values()
        self._validate_owner_provider_input()
        env_payload = (
            "\n".join(f"{name}={secret_values[name]}" for name in REQUIRED_SECRET_NAMES) + "\n"
        ).encode("utf-8")
        validation = self._validate_candidate(compose, config, entrypoint, env_payload)
        if not validation["ok"]:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Feste LiteLLM-Compose-Konfiguration ist ungültig",
                "validation": validation,
            }

        network = self._run(["docker", "network", "inspect", NETWORK_NAME], timeout=30)
        network_created = False
        if not network["ok"]:
            created = self._run(["docker", "network", "create", "--driver", "bridge", NETWORK_NAME], timeout=30)
            if not created["ok"]:
                return {
                    "ok": False,
                    "status": "FAILED",
                    "blocker": "Privates LiteLLM-Netzwerk konnte nicht erstellt werden",
                    "network": {"ok": False, "exit_code": created["exit_code"]},
                }
            network_created = True

        self._prepare_root()
        self._write_atomic(self.deploy_root / "docker-compose.yml", compose, 0o640)
        self._write_atomic(self.deploy_root / "config.yaml", config, 0o640)
        self._write_atomic(self.deploy_root / "sovereign-entrypoint.py", entrypoint, 0o640)
        self._write_atomic(self.deploy_root / ".env", env_payload, 0o600)
        self._write_backend_service_key(secret_values["LITELLM_MASTER_KEY"])

        deployed = self._run(self._compose_up_command(), timeout=600)
        if not deployed["ok"]:
            return {
                "ok": False,
                "status": "FAILED",
                "blocker": "Allowlisteter LiteLLM-Compose-Deploy ist fehlgeschlagen",
                "deploy": {"ok": False, "exit_code": deployed["exit_code"], "error": "docker compose up failed"},
                "networkCreated": network_created,
            }

        remounted = self._run(self._litellm_recreate_command(), timeout=600)
        if not remounted["ok"]:
            return {
                "ok": False,
                "status": "FAILED",
                "blocker": "LiteLLM konnte den atomar rotierten Provider-Zugang nicht neu mounten",
                "providerSecretRemount": {
                    "ok": False,
                    "exit_code": remounted["exit_code"],
                    "error": "docker compose force-recreate litellm failed",
                },
                "networkCreated": network_created,
            }

        runtime = self._wait_for_runtime()
        readiness = self._readiness()
        models = self._models()
        completion_canaries = (
            {
                model_id: self._completion_canary(model_id)
                for model_id in EXPECTED_MODEL_IDS
            }
            if models.get("ok")
            else {
                model_id: {
                    "ok": False,
                    "requestedModel": model_id,
                    "error": "model_inventory_not_verified",
                }
                for model_id in EXPECTED_MODEL_IDS
            }
        )
        completion_canaries_ok = all(
            canary.get("ok") is True for canary in completion_canaries.values()
        )
        litellm = runtime["litellm"]
        db = runtime["db"]
        runtime_ok = bool(
            litellm.get("running")
            and litellm.get("health") == "healthy"
            and db.get("running")
            and db.get("health") == "healthy"
            and litellm.get("networks") == [NETWORK_NAME]
            and db.get("networks") == [NETWORK_NAME]
            and not litellm.get("publishedPorts")
            and readiness.get("ok")
            and models.get("ok")
            and completion_canaries_ok
        )
        return {
            "ok": runtime_ok,
            "status": "DEPLOYED_VERIFIED" if runtime_ok else "DEPLOYED_UNVERIFIED",
            "project": PROJECT_NAME,
            "network": NETWORK_NAME,
            "networkCreated": network_created,
            "templates": {
                "composeSha256": compose_sha,
                "configSha256": config_sha,
                "entrypointSha256": entrypoint_sha,
            },
            "secretsPresent": list(REQUIRED_SECRET_NAMES),
            "providerInputFileReady": PROVIDER_INPUT_PATH.is_file() and not PROVIDER_INPUT_PATH.is_symlink(),
            "backendServiceKeyFileReady": BACKEND_SERVICE_KEY_PATH.is_file() and not BACKEND_SERVICE_KEY_PATH.is_symlink(),
            "providerSecretRemount": {
                "ok": True,
                "service": "litellm",
                "forceRecreate": True,
                "databaseRecreated": False,
            },
            "activeConfigSha256": _sha256(config),
            "aliasSelection": alias_selection,
            "secretValuesExposed": False,
            "runtime": runtime,
            "readiness": readiness,
            "models": models,
            "completionCanaries": completion_canaries,
            "completionCanariesPassed": completion_canaries_ok,
        }


    def activate_model_aliases(
        self,
        *,
        fast_provider_model: str,
        balanced_provider_model: str,
        confirmation_inventory_sha256: str,
    ) -> dict[str, Any]:
        """Persist two fixed aliases only when bound to the current provider inventory."""
        if os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Private Owner Mode ist nicht aktiv"}
        if os.getenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "0").strip() != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Allowlistete Compose-Writes sind nicht aktiviert"}

        requested = {
            "sovereign-fast": str(fast_provider_model or "").strip(),
            "sovereign-balanced": str(balanced_provider_model or "").strip(),
        }
        if not all(_SAFE_PROVIDER_MODEL.fullmatch(value) for value in requested.values()):
            return {"ok": False, "status": "BLOCKED", "blocker": "Provider-Modellauswahl ist ungültig"}
        if not re.fullmatch(r"[0-9a-f]{64}", str(confirmation_inventory_sha256 or "")):
            return {"ok": False, "status": "BLOCKED", "blocker": "Inventar-Bestätigung ist ungültig"}

        inventory = self.provider_model_inventory()
        if not inventory.get("ok"):
            return inventory
        if inventory.get("inventorySha256") != confirmation_inventory_sha256:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Bestätigter Inventar-Hash ist nicht mehr aktuell",
                "currentInventorySha256": inventory.get("inventorySha256"),
                "secretValuesExposed": False,
            }
        available = set(inventory.get("modelIds") or [])
        if any(value not in available for value in requested.values()):
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Mindestens ein Provider-Modell ist nicht im bestätigten Inventar enthalten",
                "secretValuesExposed": False,
            }

        plan = self.plan()
        templates = plan.get("templates") if isinstance(plan.get("templates"), dict) else {}
        compose_sha = str((templates.get("docker-compose.yml") or {}).get("sha256") or "")
        config_sha = str((templates.get("config.yaml") or {}).get("sha256") or "")
        entrypoint_sha = str((templates.get("sovereign-entrypoint.py") or {}).get("sha256") or "")
        if not all((compose_sha, config_sha, entrypoint_sha)):
            return {"ok": False, "status": "BLOCKED", "blocker": "LiteLLM-Template-Bundle ist unvollständig"}

        path = self._alias_selection_path()
        if path.is_symlink():
            return {"ok": False, "status": "BLOCKED", "blocker": "LiteLLM-Alias-Auswahl darf kein Symlink sein"}
        try:
            self._load_alias_selection()
        except RuntimeError as exc:
            return {"ok": False, "status": "BLOCKED", "blocker": str(exc)}
        previous: bytes | None = None
        if path.is_file():
            if path.stat().st_size > 8192:
                return {"ok": False, "status": "BLOCKED", "blocker": "Bestehende Alias-Auswahl ist ungültig"}
            previous = path.read_bytes()
        selection = {
            "inventorySha256": confirmation_inventory_sha256,
            **requested,
        }
        selection_payload = (
            json.dumps(selection, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        self._prepare_root()
        self._write_atomic(path, selection_payload, 0o640)
        try:
            deployed = self.deploy(
                confirmation_compose_sha256=compose_sha,
                confirmation_config_sha256=config_sha,
                confirmation_entrypoint_sha256=entrypoint_sha,
            )
        except (ValueError, FileNotFoundError, RuntimeError, subprocess.TimeoutExpired):
            deployed = {
                "ok": False,
                "status": "FAILED",
                "blocker": "Alias-Aktivierung wurde vor vollständiger Runtime-Evidence abgebrochen",
            }
        if deployed.get("ok"):
            return {
                **deployed,
                "status": "ALIASES_ACTIVATED_VERIFIED",
                "inventorySha256": confirmation_inventory_sha256,
                "providerModels": requested,
                "secretValuesExposed": False,
            }

        if previous is None:
            path.unlink(missing_ok=True)
        else:
            self._write_atomic(path, previous, 0o640)
        try:
            rollback = self.deploy(
                confirmation_compose_sha256=compose_sha,
                confirmation_config_sha256=config_sha,
                confirmation_entrypoint_sha256=entrypoint_sha,
            )
        except (ValueError, FileNotFoundError, RuntimeError, subprocess.TimeoutExpired):
            rollback = {"ok": False, "status": "ROLLBACK_FAILED"}
        return {
            "ok": False,
            "status": "ALIAS_ACTIVATION_FAILED",
            "blocker": "Alias-Aktivierung bestand die Runtime-Canaries nicht",
            "activation": deployed,
            "rollbackAttempted": True,
            "rollbackStatus": rollback.get("status"),
            "secretValuesExposed": False,
        }
