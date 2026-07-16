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
OPENAI_KEY_PATH = OWNER_SECRET_ROOT / "openai_api_key.txt"
BACKEND_MASTER_KEY_PATH = OWNER_SECRET_ROOT / "litellm_master_key.txt"
EXPECTED_MODEL_IDS = ("sovereign-fast", "sovereign-balanced")
REQUIRED_SECRET_NAMES = (
    "POSTGRES_PASSWORD",
    "LITELLM_MASTER_KEY",
    "LITELLM_SALT_KEY",
)
_SAFE_DB_PASSWORD = re.compile(r"^[A-Za-z0-9._~-]{16,256}$")
_SAFE_KEY_SECRET = re.compile(r"^[A-Za-z0-9._~!@%+=:,/-]{16,512}$")


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
        return {
            "ok": True,
            "status": "PLAN_READY",
            "project": PROJECT_NAME,
            "network": NETWORK_NAME,
            "deployRoot": str(self.deploy_root),
            "templates": {
                "docker-compose.yml": {"sha256": compose_sha, "bytes": len(compose)},
                "config.yaml": {"sha256": config_sha, "bytes": len(config)},
            },
            "composeWriteEnabled": (
                os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() == "1"
                and os.getenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "0").strip() == "1"
            ),
            "containers": {
                "litellm": self._container_state(LITELLM_CONTAINER),
                "db": self._container_state(DB_CONTAINER),
            },
            "acceptedInputs": ["confirmation_compose_sha256", "confirmation_config_sha256"],
            "arbitraryYamlAccepted": False,
            "arbitraryCommandAccepted": False,
            "secretValuesAccepted": False,
        }

    def _read_owner_provider_key(self) -> str:
        root = OWNER_SECRET_ROOT
        path = OPENAI_KEY_PATH
        if root.is_symlink() or path.is_symlink() or not path.is_file():
            raise RuntimeError("Geschützter OpenAI-Provider-Key fehlt im Owner-Speicher")
        size = path.stat().st_size
        if size < 16 or size > 8192:
            raise RuntimeError("Geschützter OpenAI-Provider-Key hat eine ungültige Größe")
        value = path.read_text("utf-8").strip()
        if not _SAFE_KEY_SECRET.fullmatch(value):
            raise RuntimeError("Geschützter OpenAI-Provider-Key hat ein ungültiges Format")
        return value

    def _write_backend_master_key(self, value: str) -> None:
        root = OWNER_SECRET_ROOT
        if root.is_symlink():
            raise RuntimeError("Owner-Secret-Root darf kein Symlink sein")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        if BACKEND_MASTER_KEY_PATH.is_symlink():
            raise RuntimeError("Backend-LiteLLM-Key-Ziel darf kein Symlink sein")
        self._write_atomic(BACKEND_MASTER_KEY_PATH, (value + "\n").encode("utf-8"), 0o600)

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

    def _validate_candidate(self, compose: bytes, config: bytes, env_payload: bytes) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="sovereign-litellm-") as directory:
            root = Path(directory)
            compose_path = root / "docker-compose.yml"
            config_path = root / "config.yaml"
            env_path = root / ".env"
            compose_path.write_bytes(compose)
            config_path.write_bytes(config)
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
                if service.get("entrypoint") or service.get("build") or service.get("extra_hosts"):
                    return {"ok": False, "error": f"forbidden execution override: {service_name}"}
                if service.get("ports"):
                    return {"ok": False, "error": f"published ports are forbidden: {service_name}"}
                service_networks = service.get("networks")
                used_networks = set(service_networks) if isinstance(service_networks, dict) else set(service_networks or [])
                if used_networks != {NETWORK_NAME}:
                    return {"ok": False, "error": f"unexpected service network: {service_name}"}

            if services["db"].get("command") not in (None, [], ""):
                return {"ok": False, "error": "unexpected database command"}
            if services["litellm"].get("command") != ["--config=/app/config.yaml", "--port", "4000"]:
                return {"ok": False, "error": "unexpected LiteLLM command"}
            db_environment = services["db"].get("environment") if isinstance(services["db"].get("environment"), dict) else {}
            if set(db_environment) != {"POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"}:
                return {"ok": False, "error": "unexpected database environment"}
            if db_environment.get("POSTGRES_DB") != "litellm" or db_environment.get("POSTGRES_USER") != "litellm":
                return {"ok": False, "error": "unexpected database identity"}
            litellm_environment = services["litellm"].get("environment") if isinstance(services["litellm"].get("environment"), dict) else {}
            if set(litellm_environment) != {"DATABASE_URL", "LITELLM_MASTER_KEY", "LITELLM_SALT_KEY", "OPENAI_API_KEY"}:
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
            if len(litellm_volumes) != 1:
                return {"ok": False, "error": "unexpected LiteLLM volume count"}
            litellm_volume = litellm_volumes[0] if isinstance(litellm_volumes[0], dict) else {}
            if (
                litellm_volume.get("type") != "bind"
                or Path(str(litellm_volume.get("source") or "")).resolve() != config_path.resolve()
                or litellm_volume.get("target") != "/app/config.yaml"
                or not bool(litellm_volume.get("read_only"))
            ):
                return {"ok": False, "error": "unexpected LiteLLM config mount"}
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
        normalized_model_ids = sorted({str(model_id or "").strip() for model_id in model_ids if str(model_id or "").strip()})
        expected_models_present = all(model_id in normalized_model_ids for model_id in EXPECTED_MODEL_IDS)
        return {
            "ok": payload.get("httpStatus") == 200 and expected_models_present,
            "httpStatus": payload.get("httpStatus"),
            "modelCount": len(normalized_model_ids),
            "modelIds": normalized_model_ids[:20],
            "expectedModelIds": list(EXPECTED_MODEL_IDS),
            "expectedModelsPresent": expected_models_present,
        }

    def deploy(
        self,
        *,
        confirmation_compose_sha256: str,
        confirmation_config_sha256: str,
    ) -> dict[str, Any]:
        if os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Private Owner Mode ist nicht aktiv"}
        if os.getenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "0").strip() != "1":
            return {"ok": False, "status": "BLOCKED", "blocker": "Allowlistete Compose-Writes sind nicht aktiviert"}

        compose, compose_sha = self._template("docker-compose.yml")
        config, config_sha = self._template("config.yaml")
        if confirmation_compose_sha256 != compose_sha or confirmation_config_sha256 != config_sha:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Bestätigte Template-Hashes stimmen nicht mit den installierten Templates überein",
                "expected": {"compose": compose_sha, "config": config_sha},
            }

        secret_values = self._existing_secret_values()
        provider_key = self._read_owner_provider_key()
        env_payload = (
            "\n".join(f"{name}={secret_values[name]}" for name in REQUIRED_SECRET_NAMES)
            + f"\nOPENAI_API_KEY={provider_key}\n"
        ).encode("utf-8")
        validation = self._validate_candidate(compose, config, env_payload)
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
        self._write_atomic(self.deploy_root / ".env", env_payload, 0o600)
        self._write_backend_master_key(secret_values["LITELLM_MASTER_KEY"])

        deployed = self._run(
            [
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
                "up",
                "-d",
                "--remove-orphans",
            ],
            timeout=600,
        )
        if not deployed["ok"]:
            return {
                "ok": False,
                "status": "FAILED",
                "blocker": "Allowlisteter LiteLLM-Compose-Deploy ist fehlgeschlagen",
                "deploy": {"ok": False, "exit_code": deployed["exit_code"], "error": "docker compose up failed"},
                "networkCreated": network_created,
            }

        runtime = self._wait_for_runtime()
        readiness = self._readiness()
        models = self._models()
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
        )
        return {
            "ok": runtime_ok,
            "status": "DEPLOYED_VERIFIED" if runtime_ok else "DEPLOYED_UNVERIFIED",
            "project": PROJECT_NAME,
            "network": NETWORK_NAME,
            "networkCreated": network_created,
            "templates": {"composeSha256": compose_sha, "configSha256": config_sha},
            "secretsPresent": [*REQUIRED_SECRET_NAMES, "OPENAI_API_KEY"],
            "backendMasterKeyFileReady": BACKEND_MASTER_KEY_PATH.is_file() and not BACKEND_MASTER_KEY_PATH.is_symlink(),
            "secretValuesExposed": False,
            "runtime": runtime,
            "readiness": readiness,
            "models": models,
        }
