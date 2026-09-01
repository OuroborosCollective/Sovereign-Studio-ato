from __future__ import annotations

import json
from pathlib import Path

from command_contract import is_mutating_action
from n8n_host_maintenance import (
    AURION_BUILDKIT_CONTAINER,
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
            "buildkitEndpoint": {
                "container": AURION_BUILDKIT_CONTAINER,
                "pruneHelpSha256": "3" * 64,
            },
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
    assert [
        "docker",
        "exec",
        AURION_BUILDKIT_CONTAINER,
        "buildctl",
        "prune",
        "--all",
        "--keep-duration=24h",
    ] in calls
    assert not any(call[:3] == ["docker", "builder", "prune"] for call in calls)
    assert not any(call[:3] == ["docker", "buildx", "prune"] for call in calls)
    rendered = "\n".join(" ".join(call) for call in calls)
    assert "volume prune" not in rendered
    assert "container prune" not in rendered
    assert "system prune" not in rendered
    assert "image prune --all" not in rendered


def test_retired_document_image_cleanup_plan_selects_only_unreferenced_explicitly_retired_images(
    monkeypatch,
) -> None:
    runtime = N8NHostMaintenanceRuntime()
    retired = "sha256:" + "1" * 64
    referenced = "sha256:" + "2" * 64
    aliased = "sha256:" + "3" * 64
    calls: list[list[str]] = []
    monkeypatch.setattr(runtime, "_all_container_image_ids", lambda: {referenced})
    monkeypatch.setattr(
        runtime,
        "_disk",
        lambda: {
            "totalBytes": 1000,
            "usedBytes": 900,
            "freeBytes": 100,
            "usedPpm": 900000,
        },
    )

    def run(argv, timeout=120):
        calls.append(argv)
        if argv == [
            "docker",
            "image",
            "ls",
            "--no-trunc",
            "--format",
            "{{.ID}}",
            "apache/tika",
        ]:
            return _result("\n".join([referenced, aliased]) + "\n")
        if argv == [
            "docker",
            "image",
            "ls",
            "--no-trunc",
            "--format",
            "{{.ID}}",
            "gotenberg/gotenberg",
        ]:
            return _result(retired + "\n")
        if argv == [
            "docker",
            "image",
            "inspect",
            "--format",
            "{{json .RepoTags}}|{{.Size}}",
            retired,
        ]:
            return _result('["gotenberg/gotenberg:8.11"]|11')
        if argv == [
            "docker",
            "image",
            "inspect",
            "--format",
            "{{json .RepoTags}}|{{.Size}}",
            aliased,
        ]:
            return _result('["apache/tika:3.0", "ghcr.io/example/unrelated:1"]|17')
        raise AssertionError(argv)

    monkeypatch.setattr(runtime, "_run", run)

    result = runtime.retired_document_image_cleanup_plan()

    assert result["status"] == "RETIRED_DOCUMENT_IMAGE_CLEANUP_PLAN_READY"
    assert result["scope"] == ["unreferenced-gotenberg-and-tika-images-only"]
    assert result["candidateCount"] == 1
    assert result["estimatedReclaimableBytes"] == 11
    assert result["candidates"] == [
        {
            "imageId": retired,
            "repositories": ["gotenberg/gotenberg"],
            "repoTags": ["gotenberg/gotenberg:8.11"],
            "sizeBytes": 11,
        }
    ]
    assert "volumes" in result["excluded"]
    assert "running-container-images" in result["excluded"]
    assert "non-retired-images" in result["excluded"]
    assert [
        "docker",
        "image",
        "inspect",
        "--format",
        "{{json .RepoTags}}|{{.Size}}",
        retired,
    ] in calls
    assert [
        "docker",
        "image",
        "inspect",
        "--format",
        "{{json .RepoTags}}|{{.Size}}",
        aliased,
    ] in calls
    assert not any(referenced in call for call in calls)


def test_retired_document_image_cleanup_apply_uses_exact_ids_without_force(
    monkeypatch,
) -> None:
    runtime = N8NHostMaintenanceRuntime()
    image_id = "sha256:" + "4" * 64
    confirmation = "b" * 64
    calls: list[list[str]] = []
    before_disk = {
        "totalBytes": 1000,
        "usedBytes": 900,
        "freeBytes": 100,
        "usedPpm": 900000,
    }
    after_disk = {
        "totalBytes": 1000,
        "usedBytes": 700,
        "freeBytes": 300,
        "usedPpm": 700000,
    }
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "1")
    monkeypatch.setattr(
        runtime,
        "retired_document_image_cleanup_plan",
        lambda: {
            "ok": True,
            "confirmationSha256": confirmation,
            "disk": before_disk,
            "estimatedReclaimableBytes": 250,
            "candidates": [
                {
                    "imageId": image_id,
                    "repositories": ["apache/tika"],
                    "repoTags": ["apache/tika:3.0"],
                    "sizeBytes": 250,
                }
            ],
        },
    )
    monkeypatch.setattr(runtime, "_retired_document_image_candidates", lambda: [])
    monkeypatch.setattr(runtime, "_disk", lambda: dict(after_disk))

    def run(argv, timeout=120):
        calls.append(argv)
        return _result()

    monkeypatch.setattr(runtime, "_run", run)

    result = runtime.retired_document_image_cleanup_apply(
        confirmation_sha256=confirmation,
        owner_approved=True,
    )

    assert result["status"] == "RETIRED_DOCUMENT_IMAGE_CLEANUP_VERIFIED"
    assert result["reclaimedBytes"] == 200
    assert result["candidatesRemaining"] == []
    assert result["volumesRemoved"] is False
    assert result["runningContainersRemoved"] is False
    assert result["nonRetiredImagesExplicitlyRemoved"] is False
    assert calls == [["docker", "image", "rm", "--no-prune", image_id]]
    rendered = " ".join(calls[0])
    assert "--force" not in rendered
    assert "image prune" not in rendered
    assert "container" not in rendered
    assert "volume" not in rendered


def test_tagged_image_retention_plan_protects_container_images_and_two_newest_per_repository(
    monkeypatch,
) -> None:
    runtime = N8NHostMaintenanceRuntime()
    active = "sha256:" + "1" * 64
    app_latest = "sha256:" + "2" * 64
    app_rollback = "sha256:" + "3" * 64
    app_old = "sha256:" + "4" * 64
    other_latest = "sha256:" + "5" * 64
    other_rollback = "sha256:" + "6" * 64
    shared_old = "sha256:" + "7" * 64
    calls: list[list[str]] = []
    metadata = {
        app_latest: '["ghcr.io/example/app:latest"]|2026-09-01T00:00:00Z|21',
        app_rollback: '["ghcr.io/example/app:rollback-1"]|2026-08-31T00:00:00Z|19',
        app_old: '["ghcr.io/example/app:old"]|2026-08-30T00:00:00Z|17',
        other_latest: '["ghcr.io/example/other:latest"]|2026-09-01T00:00:00Z|15',
        other_rollback: '["ghcr.io/example/other:rollback-1"]|2026-08-31T00:00:00Z|13',
        shared_old: '["ghcr.io/example/app:legacy", "ghcr.io/example/other:legacy"]|2026-08-29T00:00:00Z|11',
    }
    monkeypatch.setattr(runtime, "_all_container_image_ids", lambda: {active})
    monkeypatch.setattr(
        runtime,
        "_disk",
        lambda: {
            "totalBytes": 1000,
            "usedBytes": 900,
            "freeBytes": 100,
            "usedPpm": 900000,
        },
    )

    def run(argv, timeout=120):
        calls.append(argv)
        if argv == [
            "docker",
            "image",
            "ls",
            "--no-trunc",
            "--filter",
            "dangling=false",
            "--format",
            "{{.ID}}",
        ]:
            return _result(
                "\n".join(
                    [
                        active,
                        app_latest,
                        app_rollback,
                        app_old,
                        other_latest,
                        other_rollback,
                        shared_old,
                        app_old,
                    ]
                )
                + "\n"
            )
        if argv[:5] == [
            "docker",
            "image",
            "inspect",
            "--format",
            "{{json .RepoTags}}|{{.Created}}|{{.Size}}",
        ]:
            return _result(metadata[argv[-1]])
        raise AssertionError(argv)

    monkeypatch.setattr(runtime, "_run", run)

    result = runtime.tagged_image_retention_cleanup_plan()

    assert result["status"] == "TAGGED_IMAGE_RETENTION_CLEANUP_PLAN_READY"
    assert result["taggedImageCount"] == 7
    assert result["unreferencedTaggedImageCount"] == 6
    assert result["protection"]["activeContainerImageCount"] == 1
    assert {
        (item["repository"], item["imageId"])
        for item in result["protection"]["rollbackReservations"]
    } == {
        ("ghcr.io/example/app", app_latest),
        ("ghcr.io/example/app", app_rollback),
        ("ghcr.io/example/other", other_latest),
        ("ghcr.io/example/other", other_rollback),
    }
    assert [item["imageId"] for item in result["candidates"]] == [
        app_old,
        shared_old,
    ]
    assert result["estimatedReclaimableBytes"] == 28
    assert "stopped-container-images" in result["excluded"]
    assert "two-newest-unreferenced-tagged-images-per-repository" in result["excluded"]
    assert not any(active in call for call in calls)


def test_tagged_image_retention_cleanup_apply_uses_exact_candidate_ids_without_force(
    monkeypatch,
) -> None:
    runtime = N8NHostMaintenanceRuntime()
    image_id = "sha256:" + "8" * 64
    confirmation = "c" * 64
    calls: list[list[str]] = []
    before_disk = {
        "totalBytes": 1000,
        "usedBytes": 900,
        "freeBytes": 100,
        "usedPpm": 900000,
    }
    after_disk = {
        "totalBytes": 1000,
        "usedBytes": 700,
        "freeBytes": 300,
        "usedPpm": 700000,
    }
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "1")
    monkeypatch.setattr(
        runtime,
        "tagged_image_retention_cleanup_plan",
        lambda: {
            "ok": True,
            "confirmationSha256": confirmation,
            "disk": before_disk,
            "estimatedReclaimableBytes": 250,
            "candidates": [
                {
                    "imageId": image_id,
                    "repositories": ["ghcr.io/example/app"],
                    "repoTags": ["ghcr.io/example/app:old"],
                    "createdAt": "2026-08-30T00:00:00Z",
                    "sizeBytes": 250,
                }
            ],
        },
    )
    monkeypatch.setattr(
        runtime,
        "_tagged_image_retention_data",
        lambda: {"candidates": []},
    )
    monkeypatch.setattr(runtime, "_disk", lambda: dict(after_disk))

    def run(argv, timeout=120):
        calls.append(argv)
        return _result()

    monkeypatch.setattr(runtime, "_run", run)

    result = runtime.tagged_image_retention_cleanup_apply(
        confirmation_sha256=confirmation,
        owner_approved=True,
    )

    assert result["status"] == "TAGGED_IMAGE_RETENTION_CLEANUP_VERIFIED"
    assert result["reclaimedBytes"] == 200
    assert result["candidatesRemaining"] == []
    assert result["volumesRemoved"] is False
    assert result["runningContainersRemoved"] is False
    assert result["containerReferencedImagesExplicitlyRemoved"] is False
    assert result["rollbackReservedImagesExplicitlyRemoved"] is False
    assert calls == [["docker", "image", "rm", "--no-prune", image_id]]
    rendered = " ".join(calls[0])
    assert "--force" not in rendered
    assert "image prune" not in rendered
    assert "container" not in rendered
    assert "volume" not in rendered


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
    def run(argv, timeout=120):
        if argv[:4] == [
            "docker",
            "ps",
            "--filter",
            "name=buildx_buildkit_aurion-isolated0",
        ]:
            return _result("buildx_buildkit_aurion-isolated0\n")
        if argv == ["docker", "exec", AURION_BUILDKIT_CONTAINER, "buildctl", "prune", "--help"]:
            return _result("--keep-duration duration\n")
        return _result("0B\n" if argv[:3] == ["docker", "system", "df"] else "")

    monkeypatch.setattr(runtime, "_run", run)

    first = runtime.docker_cache_cleanup_plan()
    second = runtime.docker_cache_cleanup_plan()

    assert first["confirmationSha256"] == second["confirmationSha256"]
    assert first["disk"] != second["disk"]
    assert first["runningContainers"] == second["runningContainers"]
    assert first["volumes"] == second["volumes"]


def test_cleanup_plan_binds_direct_buildkit_endpoint(monkeypatch) -> None:
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
            "ps",
            "--filter",
            "name=buildx_buildkit_aurion-isolated0",
        ]:
            return _result("buildx_buildkit_aurion-isolated0\n")
        if argv == ["docker", "exec", AURION_BUILDKIT_CONTAINER, "buildctl", "prune", "--help"]:
            return _result("--keep-duration duration\n")
        return _result()

    monkeypatch.setattr(runtime, "_run", run)

    result = runtime.docker_cache_cleanup_plan()

    assert result["ok"] is True
    assert result["scope"] == ["buildkit-cache-not-used-last-24h", "dangling-images"]
    assert result["builders"] == ["aurion-isolated"]
    assert result["buildkitEndpoint"]["container"] == AURION_BUILDKIT_CONTAINER
    assert len(result["buildkitEndpoint"]["pruneHelpSha256"]) == 64


def test_cleanup_plan_blocks_without_direct_buildkit_keep_duration_support(monkeypatch) -> None:
    runtime = N8NHostMaintenanceRuntime()
    monkeypatch.setattr(runtime, "_running_container_identity", lambda: {"count": 4, "sha256": "1" * 64})
    monkeypatch.setattr(runtime, "_volume_identity", lambda: {"count": 2, "sha256": "2" * 64})
    monkeypatch.setattr(
        runtime,
        "_disk",
        lambda: {"totalBytes": 1000, "usedBytes": 900, "freeBytes": 100, "usedPpm": 900000},
    )

    def run(argv, timeout=120):
        if argv[:4] == [
            "docker",
            "ps",
            "--filter",
            "name=buildx_buildkit_aurion-isolated0",
        ]:
            return _result("buildx_buildkit_aurion-isolated0\n")
        if argv == ["docker", "exec", AURION_BUILDKIT_CONTAINER, "buildctl", "prune", "--help"]:
            return _result("--all\n")
        return _result()

    monkeypatch.setattr(runtime, "_run", run)

    result = runtime.docker_cache_cleanup_plan()

    assert result["ok"] is False
    assert result["failureFamily"] == "BUILDKIT_PRUNE_UNAVAILABLE"
    assert result["secretValuesReturned"] is False


def _inspect(name: str, service: str, image: str, image_id: str, working_dir: str) -> dict:
    state = {
        "Status": "exited" if service == "sandbox-certs" else "running",
        "Running": service != "sandbox-certs",
        "ExitCode": 0,
    }
    mounts = {
        "sandbox-api": [{
            "Type": "volume",
            "Name": f"{N8N_PROJECT}_sandbox-api-tls",
            "Destination": "/tls",
            "RW": False,
        }],
        "sandbox-runner-1": [{
            "Type": "volume",
            "Name": f"{N8N_PROJECT}_sandbox-runner-tls",
            "Destination": "/tls",
            "RW": False,
        }],
    }.get(service, [])
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
        "HostConfig": {
            "Privileged": False,
            "Runtime": "sysbox-runc" if service == "sandbox-runner-1" else "runc",
        },
        "Mounts": mounts,
        "NetworkSettings": {
            "Networks": (
                {f"{N8N_PROJECT}_sandbox-control": {"IPAddress": "172.31.0.4"}}
                if service == "sandbox-runner-1"
                else {
                    f"{N8N_PROJECT}_default": {"IPAddress": "172.30.0.3"},
                    f"{N8N_PROJECT}_sandbox-control": {"IPAddress": "172.31.0.3"},
                }
                if service == "sandbox-api"
                else {}
                if service == "sandbox-certs"
                else {f"{N8N_PROJECT}_default": {"IPAddress": "172.30.0.2"}}
            ),
            "Ports": {"5678/tcp": [{"HostIp": "0.0.0.0", "HostPort": "32784"}]} if service == "n8n" else {},
        },
    }


def test_stage1_plan_detects_rotated_host_values_without_returning_them(monkeypatch, tmp_path) -> None:
    working = tmp_path / "hostinger"
    working.mkdir()
    (working / "docker-compose.yml").write_text("services:\n  n8n:\n    image: placeholder\n", encoding="utf-8")
    env = working / ".env"
    runtime_nexos = "runtime-" + "x" * 40
    env.write_text(
        "\n".join(
            [
                "TZ=Europe/Berlin",
                "TRAEFIK_HOST=example.invalid",
                "N8N_INSTANCE_AI_MODEL=model",
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
    monkeypatch.setattr(runtime, "_sysbox_runtime_registered", lambda: True)
    monkeypatch.setattr(
        runtime,
        "_container_env",
        lambda name: {
            N8N_CONTAINER: {
                "N8N_SANDBOX_SERVICE_API_KEY": "old-a",
                "N8N_INSTANCE_AI_MODEL_API_KEY": runtime_nexos,
                "N8N_INSTANCE_AI_MODEL": "model",
            },
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
    assert result["instanceAiCredential"] == {
        "source": "existing-runtime",
        "hostPresent": False,
        "runtimePresent": True,
        "modelHostPresent": True,
        "modelRuntimePresent": True,
        "secretValuesReturned": False,
    }
    assert result["rotationPendingRecreate"] is True
    assert result["runtimeMatchesHostSecrets"] is False
    assert result["hostSecretValuesPresent"] is True
    assert result["secretValuesReturned"] is False
    payload = json.dumps(result, sort_keys=True)
    assert "old-a" not in payload
    assert "old-b" not in payload
    assert "old-c" not in payload
    assert runtime_nexos not in payload
    assert "a" * 40 not in payload
    assert ":latest" not in result["images"]["n8n"]
    assert result["sysboxRuntimeRegistered"] is True
    assert result["targetRunnerIsolation"] == "sysbox-runc"


def test_stage1_plan_verifies_already_deployed_generated_compose(monkeypatch, tmp_path) -> None:
    working = tmp_path / "hostinger"
    working.mkdir()
    env = working / ".env"
    api_key = "a" * 40
    runner_key = "b" * 40
    registration_token = "c" * 40
    env.write_text(
        "\n".join(
            [
                "TZ=Europe/Berlin",
                "TRAEFIK_HOST=example.invalid",
                "SANDBOX_API_KEY=" + api_key,
                "SANDBOX_RUNNER_API_KEY=" + runner_key,
                "SANDBOX_RUNNER_REGISTRATION_TOKEN=" + registration_token,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    maintenance = tmp_path / "maintenance"
    runtime = N8NHostMaintenanceRuntime(maintenance_root=str(maintenance))
    images = {
        "n8n": "docker.n8n.io/n8nio/n8n@sha256:" + "1" * 64,
        "sandboxApi": "n8nio/n8n-sandbox-service-api@sha256:" + "2" * 64,
        "sandboxRunner": "n8nio/n8n-sandbox-service-runner-dind@sha256:" + "3" * 64,
        "innerSandbox": "n8nio/n8n-sandbox-service-sandbox@sha256:" + "4" * 64,
    }
    maintenance.mkdir()
    stage1_path = maintenance / "compose.stage1.yml"
    stage1_path.write_text(runtime._stage1_compose(images), encoding="utf-8")
    inspections = {
        N8N_CONTAINER: _inspect(N8N_CONTAINER, "n8n", images["n8n"], "sha256:" + "1" * 64, str(working)),
        N8N_SANDBOX_CERTS_CONTAINER: _inspect(N8N_SANDBOX_CERTS_CONTAINER, "sandbox-certs", images["sandboxApi"], "sha256:" + "2" * 64, str(working)),
        N8N_SANDBOX_API_CONTAINER: _inspect(N8N_SANDBOX_API_CONTAINER, "sandbox-api", images["sandboxApi"], "sha256:" + "2" * 64, str(working)),
        N8N_SANDBOX_RUNNER_CONTAINER: _inspect(N8N_SANDBOX_RUNNER_CONTAINER, "sandbox-runner-1", images["sandboxRunner"], "sha256:" + "3" * 64, str(working)),
    }
    monkeypatch.setattr(runtime, "_sysbox_runtime_registered", lambda: True)
    for inspect in inspections.values():
        inspect["Config"]["Labels"]["com.docker.compose.project.config_files"] = str(stage1_path)
    inspections[N8N_CONTAINER]["NetworkSettings"]["Ports"] = {
        "5678/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5678"}]
    }
    monkeypatch.setattr(runtime, "_inspect", lambda name: inspections[name])
    monkeypatch.setattr(
        runtime,
        "_container_env",
        lambda name: {
            N8N_CONTAINER: {
                "N8N_SANDBOX_SERVICE_API_KEY": api_key,
                "N8N_PROXY_HOPS": "1",
                "N8N_SECURE_COOKIE": "true",
                "N8N_WEBHOOK_URL": "https://n8n.example.invalid/",
            },
            N8N_SANDBOX_API_CONTAINER: {
                "SANDBOX_API_KEYS": api_key,
                "SANDBOX_API_RUNNER_API_KEY": runner_key,
                "SANDBOX_API_RUNNER_REGISTRATION_TOKEN": registration_token,
            },
            N8N_SANDBOX_RUNNER_CONTAINER: {
                "SANDBOX_RUNNER_API_KEYS": runner_key,
                "SANDBOX_RUNNER_REGISTRATION_TOKEN": registration_token,
            },
        }[name],
    )
    digests = iter((images["n8n"], images["sandboxApi"], images["sandboxRunner"]))
    monkeypatch.setattr(runtime, "_repo_digest", lambda *_args: next(digests))
    monkeypatch.setattr(runtime, "_inner_sandbox_digest", lambda: images["innerSandbox"])
    monkeypatch.setattr(runtime, "_wait_for_stage1_health", lambda *_args, **_kwargs: (True, True, True))
    monkeypatch.setattr(runtime, "_run", lambda *_args, **_kwargs: _result())
    monkeypatch.setattr(
        runtime,
        "_disk",
        lambda: {"totalBytes": 100 * 1024**3, "usedBytes": 80 * 1024**3, "freeBytes": 20 * 1024**3, "usedPpm": 800000},
    )

    result = runtime.stage1_plan()

    assert result["ok"] is True
    assert result["status"] == "N8N_STAGE1_ALREADY_VERIFIED"
    assert result["alreadyDeployed"] is True
    assert result["managedComposeMatchesTarget"] is True
    assert result["runnerIsolationVerified"] is True
    assert result["sandboxTlsMaterialSeparated"] is True
    assert result["sandboxNetworksSeparated"] is True
    assert result["originalComposeRecoveryAvailable"] is False
    assert result["mutationPerformed"] is False
    payload = json.dumps(result, sort_keys=True)
    assert api_key not in payload
    assert runner_key not in payload
    assert registration_token not in payload


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
    runner = compose.split("  sandbox-runner-1:", 1)[1].split("\nvolumes:", 1)[0]
    assert "runtime: sysbox-runc" in runner
    assert "privileged: false" in runner
    assert "privileged: true" not in compose
    assert "SANDBOX_RUNNER_HTTP_BASE_URL=https://" in runner
    assert "sandbox-runner-tls:/tls:ro" in runner
    assert "networks:\n      - sandbox-control" in runner
    assert "      - default" not in runner
    assert "control-grpc-api-client.crt" not in runner
    assert "--world-readable" not in compose
    assert "network_mode: none" in compose.split("  sandbox-certs:", 1)[1].split("  sandbox-api:", 1)[0]
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


def test_stage1_health_wait_retries_until_all_endpoints_are_ready(monkeypatch) -> None:
    runtime = N8NHostMaintenanceRuntime()
    calls: list[tuple[str, int, str, bool]] = []

    monkeypatch.setattr(
        runtime,
        "_http_probe",
        lambda host, port, path, *, tls=False: (
            calls.append((host, port, path, tls)) is None and len(calls) > 3
        ),
    )
    inspections = {
        N8N_SANDBOX_API_CONTAINER: {
            "NetworkSettings": {"Networks": {"n8n": {"IPAddress": "172.30.0.3"}}}
        },
        N8N_SANDBOX_RUNNER_CONTAINER: {
            "NetworkSettings": {"Networks": {"n8n": {"IPAddress": "172.30.0.4"}}}
        },
    }

    result = runtime._wait_for_stage1_health(
        inspections,
        attempts=2,
        delay_seconds=0,
    )

    assert result == (True, True, True)
    assert calls == [
        ("127.0.0.1", 5678, "/healthz", False),
        ("172.30.0.3", 8080, "/healthz", False),
        ("172.30.0.4", 8080, "/readyz", True),
        ("127.0.0.1", 5678, "/healthz", False),
        ("172.30.0.3", 8080, "/healthz", False),
        ("172.30.0.4", 8080, "/readyz", True),
    ]


def test_sysbox_runtime_inventory_is_exact_and_fail_closed(monkeypatch) -> None:
    runtime = N8NHostMaintenanceRuntime()
    monkeypatch.setattr(
        runtime,
        "_run",
        lambda *_args, **_kwargs: _result(
            '{"runc": {"path": "runc"}, "sysbox-runc": {"path": "sysbox-runc"}}'
        ),
    )
    assert runtime._sysbox_runtime_registered() is True

    monkeypatch.setattr(
        runtime,
        "_run",
        lambda *_args, **_kwargs: _result('{"runc": {"path": "runc"}}'),
    )
    assert runtime._sysbox_runtime_registered() is False


def test_stage1_plan_blocks_before_inspection_without_sysbox(monkeypatch) -> None:
    runtime = N8NHostMaintenanceRuntime()
    monkeypatch.setattr(runtime, "_sysbox_runtime_registered", lambda: False)
    monkeypatch.setattr(
        runtime,
        "_inspect",
        lambda _name: (_ for _ in ()).throw(
            AssertionError("container inspection must not run without Sysbox")
        ),
    )

    result = runtime.stage1_plan()

    assert result["ok"] is False
    assert result["status"] == "N8N_STAGE1_PLAN_BLOCKED"
    assert result["failureFamily"] == "N8N_RUNTIME_EVIDENCE_INCOMPLETE"
    assert "privileged runner fallback is prohibited" in result["blocker"]
    assert result["mutationPerformed"] is False


def test_stage1_apply_blocks_without_sysbox_before_compose_mutation(
    monkeypatch,
    tmp_path,
) -> None:
    maintenance_root = tmp_path / "maintenance"
    runtime = N8NHostMaintenanceRuntime(maintenance_root=str(maintenance_root))
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "1")
    monkeypatch.setattr(runtime, "_sysbox_runtime_registered", lambda: False)
    monkeypatch.setattr(
        runtime,
        "_inspect",
        lambda _name: (_ for _ in ()).throw(
            AssertionError("container inspection must not run without Sysbox")
        ),
    )

    result = runtime.stage1_apply(
        confirmation_sha256="a" * 64,
        owner_approved=True,
    )

    assert result["status"] == "N8N_STAGE1_PLAN_BLOCKED"
    assert result["mutationPerformed"] is False
    assert not maintenance_root.exists()


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
    seen_override_keys: list[set[str]] = []

    def run(argv, timeout=120, env_overrides=None):
        calls.append(argv)
        seen_override_keys.append(set((env_overrides or {}).keys()))
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


def test_stage1_apply_refuses_an_already_verified_runtime(monkeypatch) -> None:
    runtime = N8NHostMaintenanceRuntime()
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "1")
    monkeypatch.setattr(runtime, "stage1_plan", lambda: {"ok": True, "alreadyDeployed": True})

    result = runtime.stage1_apply(confirmation_sha256="a" * 64, owner_approved=True)

    assert result["status"] == "N8N_STAGE1_BLOCKED"
    assert result["failureFamily"] == "N8N_STAGE1_ALREADY_DEPLOYED"
    assert result["mutationPerformed"] is False


def test_stage1_mutations_require_owner_and_compose_write(monkeypatch) -> None:
    runtime = N8NHostMaintenanceRuntime()
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", raising=False)
    assert runtime.docker_cache_cleanup_apply(confirmation_sha256="a" * 64, owner_approved=False)["failureFamily"] == "OWNER_APPROVAL_REQUIRED"
    assert runtime.stage1_apply(confirmation_sha256="a" * 64, owner_approved=False)["failureFamily"] == "OWNER_APPROVAL_REQUIRED"
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    assert runtime.docker_cache_cleanup_apply(confirmation_sha256="a" * 64, owner_approved=True)["failureFamily"] == "HOST_MAINTENANCE_WRITE_DISABLED"
