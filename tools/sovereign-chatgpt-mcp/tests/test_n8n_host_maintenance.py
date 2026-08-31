from __future__ import annotations

import json
from pathlib import Path

from command_contract import is_mutating_action
from n8n_host_maintenance import (
    N8N_CONTAINER,
    N8N_PROJECT,
    N8N_SANDBOX_API_CONTAINER,
    N8N_SANDBOX_CERTS_CONTAINER,
    N8N_SANDBOX_RUNNER_CONTAINER,
    N8NHostMaintenanceRuntime,
)


def _result(stdout: str = "", *, ok: bool = True, exit_code: int = 0) -> dict:
    return {"ok": ok, "exitCode": exit_code, "stdout": stdout, "stderr": ""}


def test_n8n_maintenance_reuses_existing_queue_mutation_surfaces() -> None:
    assert is_mutating_action("patchmon_patch_action_apply")
    assert is_mutating_action("deploy_managed_compose_stack")
    assert not is_mutating_action("patchmon_patch_action_plan")
    assert not is_mutating_action("managed_compose_stack_plan")
    assert not is_mutating_action("docker_cache_cleanup_apply")
    assert not is_mutating_action("n8n_host_stage1_apply")


def test_cleanup_apply_never_prunes_volumes_containers_or_tagged_images(monkeypatch) -> None:
    runtime = N8NHostMaintenanceRuntime()
    confirmation = "a" * 64
    calls: list[list[str]] = []
    running = {"count": 4, "sha256": "1" * 64}
    volumes = {"count": 2, "sha256": "2" * 64}
    after_disk = {"totalBytes": 1000, "usedBytes": 700, "freeBytes": 300, "usedPpm": 700000}
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "1")
    monkeypatch.setattr(runtime, "_running_container_identity", lambda: dict(running))
    monkeypatch.setattr(runtime, "_volume_identity", lambda: dict(volumes))
    monkeypatch.setattr(runtime, "_disk", lambda: dict(after_disk))
    monkeypatch.setattr(
        runtime,
        "docker_cache_cleanup_plan",
        lambda: {
            "ok": True,
            "confirmationSha256": confirmation,
            "disk": {"totalBytes": 1000, "usedBytes": 900, "freeBytes": 100, "usedPpm": 900000},
            "runningContainers": running,
            "volumes": volumes,
            "builders": ["aurion-isolated"],
        },
    )

    def run(argv, timeout=120):
        calls.append(argv)
        return _result()

    monkeypatch.setattr(runtime, "_run", run)

    result = runtime.docker_cache_cleanup_apply(
        confirmation_sha256=confirmation,
        owner_approved=True,
    )

    assert result["status"] == "DOCKER_CACHE_CLEANUP_VERIFIED"
    assert result["reclaimedBytes"] == 200
    assert result["volumesRemoved"] is False
    assert result["runningContainersRemoved"] is False
    assert result["taggedImagesExplicitlyRemoved"] is False
    assert ["docker", "image", "prune", "--force"] in calls
    assert not any(call[:3] == ["docker", "builder", "prune"] for call in calls)
    assert any(call[:3] == ["docker", "buildx", "prune"] for call in calls)
    rendered = "\n".join(" ".join(call) for call in calls)
    assert "volume prune" not in rendered
    assert "container prune" not in rendered
    assert "system prune" not in rendered
    assert "image prune --all" not in rendered


def test_cleanup_confirmation_ignores_volatile_disk_usage(monkeypatch) -> None:
    runtime = N8NHostMaintenanceRuntime()
    running = {"count": 4, "sha256": "1" * 64}
    volumes = {"count": 2, "sha256": "2" * 64}
    disks = iter(
        (
            {"totalBytes": 1000, "usedBytes": 900, "freeBytes": 100, "usedPpm": 900000},
            {"totalBytes": 1000, "usedBytes": 901, "freeBytes": 99, "usedPpm": 901000},
        )
    )
    monkeypatch.setattr(runtime, "_running_container_identity", lambda: dict(running))
    monkeypatch.setattr(runtime, "_volume_identity", lambda: dict(volumes))
    monkeypatch.setattr(runtime, "_disk", lambda: dict(next(disks)))
    monkeypatch.setattr(
        runtime,
        "_run",
        lambda argv, timeout=120: _result("0B\n" if argv[:3] == ["docker", "system", "df"] else ""),
    )

    first = runtime.docker_cache_cleanup_plan()
    second = runtime.docker_cache_cleanup_plan()

    assert first["confirmationSha256"] == second["confirmationSha256"]
    assert first["disk"] != second["disk"]
    assert first["runningContainers"] == second["runningContainers"]
    assert first["volumes"] == second["volumes"]


def test_cleanup_plan_discovers_live_aurion_buildx_when_formatted_listing_is_unavailable(monkeypatch) -> None:
    runtime = N8NHostMaintenanceRuntime()
    running = {"count": 4, "sha256": "1" * 64}
    volumes = {"count": 2, "sha256": "2" * 64}
    disk = {"totalBytes": 1000, "usedBytes": 900, "freeBytes": 100, "usedPpm": 900000}

    monkeypatch.setattr(runtime, "_running_container_identity", lambda: dict(running))
    monkeypatch.setattr(runtime, "_volume_identity", lambda: dict(volumes))
    monkeypatch.setattr(runtime, "_disk", lambda: dict(disk))

    def run(argv, timeout=120):
        if argv[:4] == [
            "docker",
            "buildx",
            "ls",
            "--format",
        ]:
            return _result(ok=False, exit_code=1)
        if argv[:4] == [
            "docker",
            "ps",
            "--filter",
            "name=buildx_buildkit_aurion-isolated0",
        ]:
            return _result("buildx_buildkit_aurion-isolated0\n")
        return _result()

    monkeypatch.setattr(runtime, "_run", run)

    result = runtime.docker_cache_cleanup_plan()

    assert result["ok"] is True
    assert result["scope"] == ["buildx-cache-older-than-24h", "dangling-images"]
    assert result["builders"] == ["aurion-isolated"]


def _inspect(name: str, service: str, image: str, image_id: str, working_dir: str) -> dict:
    state = {
        "Status": "exited" if service == "sandbox-certs" else "running",
        "Running": service != "sandbox-certs",
        "ExitCode": 0,
    }
    return {
        "Id": (service[0] * 64),
        "Image": image_id,
        "Name": "/" + name,
        "Config": {
            "Image": image,
            "Labels": {
                "com.docker.compose.project": N8N_PROJECT,
                "com.docker.compose.service": service,
                "com.docker.compose.project.working_dir": working_dir,
                "com.docker.compose.project.config_files": working_dir + "/docker-compose.yml",
            },
        },
        "State": state,
        "NetworkSettings": {
            "Networks": {f"{N8N_PROJECT}_default": {"IPAddress": "172.30.0.2"}},
            "Ports": {"5678/tcp": [{"HostIp": "0.0.0.0", "HostPort": "32784"}]} if service == "n8n" else {},
        },
    }


def test_stage1_plan_detects_rotated_host_values_without_returning_them(monkeypatch, tmp_path) -> None:
    working = tmp_path / "hostinger"
    working.mkdir()
    (working / "docker-compose.yml").write_text("services:\n  n8n:\n    image: placeholder\n", encoding="utf-8")
    env = working / ".env"
    env.write_text(
        "\n".join(
            [
                "TZ=Europe/Berlin",
                "TRAEFIK_HOST=example.invalid",
                "N8N_INSTANCE_AI_MODEL=model",
                "NEXOS_API_KEY=" + "x" * 40,
                "SANDBOX_API_KEY=" + "a" * 40,
                "SANDBOX_RUNNER_API_KEY=" + "b" * 40,
                "SANDBOX_RUNNER_REGISTRATION_TOKEN=" + "c" * 40,
            ]
        ) + "\n",
        encoding="utf-8",
    )
    runtime = N8NHostMaintenanceRuntime(maintenance_root=str(tmp_path / "maintenance"))
    inspections = {
        N8N_CONTAINER: _inspect(N8N_CONTAINER, "n8n", "docker.n8n.io/n8nio/n8n:latest", "sha256:" + "1" * 64, str(working)),
        N8N_SANDBOX_CERTS_CONTAINER: _inspect(N8N_SANDBOX_CERTS_CONTAINER, "sandbox-certs", "n8nio/n8n-sandbox-service-api:latest", "sha256:" + "2" * 64, str(working)),
        N8N_SANDBOX_API_CONTAINER: _inspect(N8N_SANDBOX_API_CONTAINER, "sandbox-api", "n8nio/n8n-sandbox-service-api:latest", "sha256:" + "2" * 64, str(working)),
        N8N_SANDBOX_RUNNER_CONTAINER: _inspect(N8N_SANDBOX_RUNNER_CONTAINER, "sandbox-runner-1", "n8nio/n8n-sandbox-service-runner-dind:latest", "sha256:" + "3" * 64, str(working)),
    }
    monkeypatch.setattr(runtime, "_inspect", lambda name: inspections[name])
    monkeypatch.setattr(
        runtime,
        "_container_env",
        lambda name: {
            N8N_CONTAINER: {"N8N_SANDBOX_SERVICE_API_KEY": "old-a"},
            N8N_SANDBOX_API_CONTAINER: {
                "SANDBOX_API_KEYS": "old-a",
                "SANDBOX_API_RUNNER_API_KEY": "old-b",
                "SANDBOX_API_RUNNER_REGISTRATION_TOKEN": "old-c",
            },
            N8N_SANDBOX_RUNNER_CONTAINER: {
                "SANDBOX_RUNNER_API_KEYS": "old-b",
                "SANDBOX_RUNNER_REGISTRATION_TOKEN": "old-c",
            },
        }[name],
    )
    digests = iter(
        (
            "docker.n8n.io/n8nio/n8n@sha256:" + "4" * 64,
            "n8nio/n8n-sandbox-service-api@sha256:" + "5" * 64,
            "n8nio/n8n-sandbox-service-runner-dind@sha256:" + "6" * 64,
        )
    )
    monkeypatch.setattr(runtime, "_repo_digest", lambda *_args: next(digests))
    monkeypatch.setattr(
        runtime,
        "_inner_sandbox_digest",
        lambda: "n8nio/n8n-sandbox-service-sandbox@sha256:" + "7" * 64,
    )
    monkeypatch.setattr(
        runtime,
        "_disk",
        lambda: {"totalBytes": 100 * 1024**3, "usedBytes": 80 * 1024**3, "freeBytes": 20 * 1024**3, "usedPpm": 800000},
    )

    result = runtime.stage1_plan()

    assert result["status"] == "N8N_STAGE1_PLAN_READY"
    assert result["instanceAiEnabled"] is True
    assert result["rotationPendingRecreate"] is True
    assert result["runtimeMatchesHostSecrets"] is False
    assert result["hostSecretValuesPresent"] is True
    assert result["secretValuesReturned"] is False
    payload = json.dumps(result, sort_keys=True)
    assert "old-a" not in payload
    assert "old-b" not in payload
    assert "old-c" not in payload
    assert "a" * 40 not in payload
    assert ":latest" not in result["images"]["n8n"]


def test_stage1_compose_is_loopback_proxy_hardened_and_immutable(tmp_path) -> None:
    runtime = N8NHostMaintenanceRuntime(maintenance_root=str(tmp_path))
    compose = runtime._stage1_compose(
        {
            "n8n": "docker.n8n.io/n8nio/n8n@sha256:" + "1" * 64,
            "sandboxApi": "n8nio/n8n-sandbox-service-api@sha256:" + "2" * 64,
            "sandboxRunner": "n8nio/n8n-sandbox-service-runner-dind@sha256:" + "3" * 64,
            "innerSandbox": "n8nio/n8n-sandbox-service-sandbox@sha256:" + "4" * 64,
        }
    )

    assert '"127.0.0.1:5678:5678"' in compose
    assert "N8N_PROXY_HOPS=1" in compose
    assert "N8N_SECURE_COOKIE=true" in compose
    assert "N8N_WEBHOOK_URL=https://" in compose
    assert "N8N_EDITOR_BASE_URL=https://" in compose
    assert "N8N_RUNNERS_ENABLED=" not in compose
    assert "N8N_ENABLED_MODULES=instance-ai" not in compose
    assert "NEXOS_API_KEY" not in compose
    assert "WEBHOOK_URL=" not in compose.replace("N8N_WEBHOOK_URL=", "")
    assert ":latest" not in compose
    assert "privileged: true" in compose
    assert "ports:" not in compose.split("sandbox-api:", 1)[1].split("sandbox-runner-1:", 1)[0]


def test_stage1_compose_can_optionally_enable_instance_ai(tmp_path) -> None:
    runtime = N8NHostMaintenanceRuntime(maintenance_root=str(tmp_path))
    compose = runtime._stage1_compose(
        {
            "n8n": "docker.n8n.io/n8nio/n8n@sha256:" + "1" * 64,
            "sandboxApi": "n8nio/n8n-sandbox-service-api@sha256:" + "2" * 64,
            "sandboxRunner": "n8nio/n8n-sandbox-service-runner-dind@sha256:" + "3" * 64,
            "innerSandbox": "n8nio/n8n-sandbox-service-sandbox@sha256:" + "4" * 64,
        },
        instance_ai_enabled=True,
    )

    assert "N8N_ENABLED_MODULES=instance-ai" in compose
    assert "N8N_INSTANCE_AI_MODEL=${N8N_INSTANCE_AI_MODEL}" in compose
    assert "N8N_INSTANCE_AI_MODEL_API_KEY=${NEXOS_API_KEY}" in compose


def test_failed_stage1_can_restore_original_compose_with_rotated_bindings(monkeypatch, tmp_path) -> None:
    runtime = N8NHostMaintenanceRuntime(maintenance_root=str(tmp_path / "maintenance"))
    working = tmp_path / "hostinger"
    working.mkdir()
    env_path = working / ".env"
    env_path.write_text("TZ=Europe/Berlin\n", encoding="utf-8")
    original = working / "docker-compose.yml"
    original.write_text("services:\n  n8n:\n    image: original\n", encoding="utf-8")
    calls: list[list[str]] = []
    services = {
        N8N_CONTAINER: "n8n",
        N8N_SANDBOX_CERTS_CONTAINER: "sandbox-certs",
        N8N_SANDBOX_API_CONTAINER: "sandbox-api",
        N8N_SANDBOX_RUNNER_CONTAINER: "sandbox-runner-1",
    }

    def run(argv, timeout=120):
        calls.append(argv)
        return _result()

    monkeypatch.setattr(runtime, "_run", run)
    monkeypatch.setattr(
        runtime,
        "_inspect",
        lambda name: _inspect(
            name,
            services[name],
            "example.invalid/image:fixed",
            "sha256:" + "9" * 64,
            str(working),
        ),
    )
    monkeypatch.setattr(runtime, "_runtime_secret_matches", lambda _host_env: True)

    result = runtime._rollback_original_compose(
        working_dir=working,
        env_path=env_path,
        compose_files=[original],
        host_env={"SANDBOX_API_KEY": "not-returned"},
    )

    assert result["attempted"] is True
    assert result["verified"] is True
    assert result["rotatedSecretBindingsActive"] is True
    assert all("not-returned" not in json.dumps(item) for item in (result, calls))
    up_calls = [call for call in calls if "up" in call]
    assert len(up_calls) == 1
    assert str(original) in up_calls[0]
    assert "--pull" in up_calls[0] and "never" in up_calls[0]


def test_stage1_mutations_require_owner_and_compose_write(monkeypatch) -> None:
    runtime = N8NHostMaintenanceRuntime()
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", raising=False)
    assert runtime.docker_cache_cleanup_apply(confirmation_sha256="a" * 64, owner_approved=False)["failureFamily"] == "OWNER_APPROVAL_REQUIRED"
    assert runtime.stage1_apply(confirmation_sha256="a" * 64, owner_approved=False)["failureFamily"] == "OWNER_APPROVAL_REQUIRED"
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    assert runtime.docker_cache_cleanup_apply(confirmation_sha256="a" * 64, owner_approved=True)["failureFamily"] == "HOST_MAINTENANCE_WRITE_DISABLED"
