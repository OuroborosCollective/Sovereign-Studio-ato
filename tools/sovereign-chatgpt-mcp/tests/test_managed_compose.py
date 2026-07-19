from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from command_contract import is_mutating_action
from managed_compose import ManagedComposeRuntime, STACKS


def _missing_runner(argv, **kwargs):
    return subprocess.CompletedProcess(argv, 1, "", "not found")


def test_managed_compose_stack_allowlist_is_exact() -> None:
    assert set(STACKS) == {
        "sovereign-litellm",
        "sovereign-backend",
        "gpt-tools",
        "code-server-46bq",
        "pgbackweb-wq5r",
        "patchmon-sovereign",
        "milvus-sovereign",
    }
    assert is_mutating_action("deploy_managed_compose_stack") is True
    assert is_mutating_action("litellm_model_aliases_activate") is True
    assert is_mutating_action("litellm_provider_model_inventory") is False
    assert is_mutating_action("openai_project_runtime_evidence") is False
    assert is_mutating_action("managed_compose_stack_plan") is False


def test_unknown_stack_is_blocked_before_any_runtime_call(tmp_path: Path) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    with pytest.raises(ValueError, match="nicht freigegeben"):
        runtime.plan("unknown-stack")


def test_unregistered_stack_template_is_reported_without_write(tmp_path: Path) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    result = runtime.plan("code-server-46bq")
    assert result["status"] == "TEMPLATE_NOT_REGISTERED"
    assert result["templateRegistered"] is False
    assert result["arbitraryYamlAccepted"] is False
    assert result["arbitraryCommandAccepted"] is False
    assert result["secretValuesAccepted"] is False


def test_deploy_is_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", raising=False)
    monkeypatch.delenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", raising=False)
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    result = runtime.deploy("sovereign-backend", "0" * 64)
    assert result["status"] == "BLOCKED"
    assert "Private Owner Mode" in result["blocker"]


def test_registered_but_missing_template_never_deploys(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "1")
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    result = runtime.deploy("gpt-tools", "0" * 64)
    assert result["status"] == "BLOCKED"
    assert "kein geprüftes Compose-Template" in result["blocker"]


def test_litellm_plan_requires_exact_installed_template_bundle(tmp_path: Path) -> None:
    template = tmp_path / "sovereign-litellm"
    template.mkdir()
    compose = b"services:\n  litellm:\n    image: example.invalid/litellm:v1\n"
    config = b"model_list: []\n"
    entrypoint = b"from __future__ import annotations\n"
    (template / "docker-compose.yml").write_bytes(compose)
    (template / "config.yaml").write_bytes(config)
    (template / "sovereign-entrypoint.py").write_bytes(entrypoint)
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    result = runtime.plan("sovereign-litellm")
    expected = hashlib.sha256(
        (
            f"{hashlib.sha256(compose).hexdigest()}:"
            f"{hashlib.sha256(config).hexdigest()}:"
            f"{hashlib.sha256(entrypoint).hexdigest()}"
        ).encode("ascii")
    ).hexdigest()
    assert result["templateBundleSha256"] == expected
    assert result["allowedStacks"] == sorted(STACKS)


def test_security_policy_blocks_privilege_latest_and_docker_socket(tmp_path: Path) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    stack = STACKS["gpt-tools"]
    with pytest.raises(RuntimeError, match="privileged"):
        runtime._validate_rendered(
            stack,
            {"services": {"browserless": {"image": "example:v1", "privileged": True}}},
        )
    with pytest.raises(RuntimeError, match="latest"):
        runtime._validate_rendered(
            stack,
            {"services": {"browserless": {"image": "example:latest"}}},
        )
    with pytest.raises(RuntimeError, match="Ausführungs-Override"):
        runtime._validate_rendered(
            stack,
            {"services": {"browserless": {"image": "example:v1", "command": ["sh", "-c", "echo blocked"]}}},
        )
    with pytest.raises(RuntimeError, match="Gesperrter Bind-Mount"):
        runtime._validate_rendered(
            stack,
            {
                "services": {
                    "dozzle": {
                        "image": "example:v1",
                        "volumes": [{"type": "bind", "source": "/var/run/docker.sock", "target": "/var/run/docker.sock"}],
                    }
                }
            },
        )


def test_pgbackweb_secret_env_is_generated_without_returning_values(tmp_path: Path) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    stack = STACKS["pgbackweb-wq5r"]
    stack = type(stack)(
        **{
            **stack.__dict__,
            "deploy_root": str(tmp_path / "deploy"),
        }
    )

    result = runtime._ensure_stack_secret_env(stack)
    env_path = Path(result["path"])
    text = env_path.read_text("utf-8")

    assert result["created"] is True
    assert result["secretValuesReturned"] is False
    assert env_path.stat().st_mode & 0o777 == 0o600
    assert "PG_BACKWEB_DB_PASSWORD=" in text
    assert "PG_BACKWEB_ENCRYPTION_KEY=" in text
    assert all(len(line.split("=", 1)[1]) == 64 for line in text.splitlines())
    assert not any(value in str(result) for value in (line.split("=", 1)[1] for line in text.splitlines()))


def test_pgbackweb_policy_accepts_loopback_and_blocks_public_port(tmp_path: Path) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    stack = STACKS["pgbackweb-wq5r"]
    runtime._validate_rendered(
        stack,
        {
            "services": {
                "pgbackweb": {
                    "image": "eduardolat/pgbackweb:0.5.1",
                    "ports": [{"host_ip": "127.0.0.1", "published": 32829, "target": 8085}],
                },
                "db": {"image": "postgres:18-bookworm"},
            },
            "networks": {"default": {}},
        },
    )
    with pytest.raises(RuntimeError, match="Nicht freigegebene Portbindung"):
        runtime._validate_rendered(
            stack,
            {
                "services": {
                    "pgbackweb": {
                        "image": "eduardolat/pgbackweb:0.5.1",
                        "ports": [{"host_ip": "0.0.0.0", "published": 32829, "target": 8085}],
                    },
                    "db": {"image": "postgres:18-bookworm"},
                },
                "networks": {"default": {}},
            },
        )


def test_patchmon_secret_env_and_redis_config_are_generated_without_secret_output(tmp_path: Path, monkeypatch) -> None:
    ownership: list[tuple[str, int, int]] = []
    monkeypatch.setattr(os, "chown", lambda path, uid, gid: ownership.append((str(path), uid, gid)))
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    stack = STACKS["patchmon-sovereign"]
    stack = type(stack)(
        **{
            **stack.__dict__,
            "deploy_root": str(tmp_path / "patchmon"),
        }
    )

    result = runtime._ensure_stack_secret_env(stack)
    env_path = Path(result["path"])
    redis_path = Path(result["additionalFiles"][0]["path"])
    values = dict(
        line.split("=", 1)
        for line in env_path.read_text("utf-8").splitlines()
        if line and "=" in line
    )

    assert result["created"] is True
    assert result["secretValuesReturned"] is False
    assert env_path.stat().st_mode & 0o777 == 0o600
    assert redis_path.stat().st_mode & 0o777 == 0o400
    assert result["additionalFiles"][0]["ownerUid"] == 999
    assert result["additionalFiles"][0]["ownerGid"] == 1000
    assert ownership == [(str(redis_path), 999, 1000)]
    assert len(values["POSTGRES_PASSWORD"]) == 64
    assert len(values["REDIS_PASSWORD"]) == 64
    assert len(values["JWT_SECRET"]) == 128
    assert len(values["SESSION_SECRET"]) == 128
    assert len(values["AI_ENCRYPTION_KEY"]) == 64
    assert values["DATABASE_URL"].startswith("postgresql://patchmon_user:")
    assert values["CORS_ORIGIN"] == "http://127.0.0.1:32830"
    assert values["AGENT_UPDATE_BODY_LIMIT"] == "5mb"
    assert f"requirepass {values['REDIS_PASSWORD']}" in redis_path.read_text("utf-8")
    for secret_key in result["keysPresent"]:
        assert values[secret_key] not in str(result)


def test_patchmon_template_scopes_environment_without_nested_env_file() -> None:
    template = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "patchmon-sovereign"
        / "docker-compose.yml"
    ).read_text("utf-8")

    assert "env_file:" not in template
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}" in template
    assert "REDIS_PASSWORD: ${REDIS_PASSWORD}" in template
    assert "JWT_SECRET: ${JWT_SECRET}" in template
    assert "AI_ENCRYPTION_KEY: ${AI_ENCRYPTION_KEY}" in template
    assert "127.0.0.1:32830:3000" in template
    assert 'user: "999:1000"' in template
    assert "/var/run/docker.sock" not in template


def test_patchmon_policy_accepts_only_fixed_redis_command_and_loopback_port(tmp_path: Path) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    stack = STACKS["patchmon-sovereign"]
    rendered = {
        "services": {
            "server": {
                "image": "ghcr.io/patchmon/patchmon-server:2.0.2",
                "ports": [{"host_ip": "127.0.0.1", "published": 32830, "target": 3000}],
                "networks": ["patchmon-internal", "patchmon-edge"],
            },
            "database": {
                "image": "postgres:17.10-alpine3.23",
                "networks": ["patchmon-internal"],
            },
            "redis": {
                "image": "redis:7.4.7-alpine3.21",
                "user": "999:1000",
                "command": ["redis-server", "/usr/local/etc/redis/redis.conf"],
                "volumes": [
                    {
                        "type": "bind",
                        "source": "/opt/patchmon-sovereign/redis.conf",
                        "target": "/usr/local/etc/redis/redis.conf",
                    }
                ],
                "networks": ["patchmon-internal"],
            },
            "guacd": {
                "image": "guacamole/guacd:1.6.0",
                "networks": ["patchmon-internal"],
            },
        },
        "networks": {"patchmon-internal": {}, "patchmon-edge": {}},
    }
    runtime._validate_rendered(stack, rendered)

    rendered["services"]["redis"]["user"] = "0:0"
    with pytest.raises(RuntimeError, match="Nicht-Root-Identität"):
        runtime._validate_rendered(stack, rendered)
    rendered["services"]["redis"]["user"] = "999:1000"

    rendered["services"]["redis"]["command"] = ["sh", "-c", "echo blocked"]
    with pytest.raises(RuntimeError, match="Ausführungs-Override"):
        runtime._validate_rendered(stack, rendered)

    rendered["services"]["redis"]["command"] = ["redis-server", "/usr/local/etc/redis/redis.conf"]
    rendered["services"]["server"]["ports"] = [
        {"host_ip": "0.0.0.0", "published": 32830, "target": 3000}
    ]
    with pytest.raises(RuntimeError, match="Nicht freigegebene Portbindung"):
        runtime._validate_rendered(stack, rendered)


def test_security_policy_blocks_unknown_services_networks_and_ports(tmp_path: Path) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    stack = STACKS["sovereign-backend"]
    with pytest.raises(RuntimeError, match="Nicht freigegebene Compose-Services"):
        runtime._validate_rendered(stack, {"services": {"shell": {"image": "example:v1"}}})
    with pytest.raises(RuntimeError, match="Nicht freigegebene Compose-Netzwerke"):
        runtime._validate_rendered(
            stack,
            {
                "services": {"sovereign-backend": {"image": "example:v1"}},
                "networks": {"host-admin": {}},
            },
        )
    with pytest.raises(RuntimeError, match="Nicht freigegebene Portbindung"):
        runtime._validate_rendered(
            stack,
            {
                "services": {
                    "sovereign-backend": {
                        "image": "example:v1",
                        "ports": [{"host_ip": "0.0.0.0", "published": 9999, "target": 8787}],
                    }
                }
            },
        )



def test_milvus_template_is_private_pinned_and_agentmemory_free() -> None:
    template = (
        Path(__file__).resolve().parents[1]
        / "templates"
        / "milvus-sovereign"
        / "docker-compose.yml"
    ).read_text("utf-8")

    assert "milvusdb/milvus:v2.5.27" in template
    assert "quay.io/coreos/etcd:v3.5.18" in template
    assert "minio/minio:RELEASE.2024-12-18T13-15-44Z" in template
    assert "ports:" not in template
    assert "external: true" in template
    assert "internal: true" in template
    assert "${MILVUS_COMPATIBILITY_IP:" in template
    assert "agentmemory" not in template.lower()
    assert "/var/run/docker.sock" not in template


def test_milvus_secret_env_is_generated_without_secret_output(tmp_path: Path) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    stack = STACKS["milvus-sovereign"]
    stack = type(stack)(
        **{
            **stack.__dict__,
            "deploy_root": str(tmp_path / "milvus"),
        }
    )

    result = runtime._ensure_stack_secret_env(stack)
    env_path = Path(result["path"])
    values = dict(
        line.split("=", 1)
        for line in env_path.read_text("utf-8").splitlines()
        if line and "=" in line
    )

    assert result["created"] is True
    assert result["secretValuesReturned"] is False
    assert env_path.stat().st_mode & 0o777 == 0o600
    assert len(values["MINIO_ACCESS_KEY_ID"]) == 32
    assert len(values["MINIO_SECRET_ACCESS_KEY"]) == 64
    assert values["MILVUS_GATEWAY_NETWORK"] == "milvus-kg4i_default"
    assert values["MILVUS_COMPATIBILITY_IP"] == "172.16.5.4"
    for secret_key in result["keysPresent"]:
        assert values[secret_key] not in str(result)


def test_milvus_policy_accepts_only_fixed_commands_and_no_published_ports(tmp_path: Path) -> None:
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    stack = STACKS["milvus-sovereign"]
    rendered = {
        "services": {
            "etcd": {
                "image": "quay.io/coreos/etcd:v3.5.18",
                "command": [
                    "etcd",
                    "--advertise-client-urls=http://127.0.0.1:2379",
                    "--listen-client-urls=http://0.0.0.0:2379",
                    "--data-dir=/etcd",
                ],
                "networks": ["milvus-storage"],
            },
            "minio": {
                "image": "minio/minio:RELEASE.2024-12-18T13-15-44Z",
                "command": ["minio", "server", "/minio_data", "--console-address", ":9001"],
                "networks": ["milvus-storage"],
            },
            "standalone": {
                "image": "milvusdb/milvus:v2.5.27",
                "command": ["milvus", "run", "standalone"],
                "networks": {
                    "milvus-storage": {},
                    "memory-gateway": {
                        "ipv4_address": "172.16.5.4",
                    },
                },
            },
        },
        "networks": {"milvus-storage": {}, "memory-gateway": {}},
    }
    runtime._validate_rendered(stack, rendered)

    rendered["services"]["standalone"]["command"] = ["sh", "-c", "echo blocked"]
    with pytest.raises(RuntimeError, match="Ausführungs-Override"):
        runtime._validate_rendered(stack, rendered)
    rendered["services"]["standalone"]["command"] = ["milvus", "run", "standalone"]

    rendered["services"]["standalone"]["ports"] = [
        {"host_ip": "127.0.0.1", "published": 19530, "target": 19530}
    ]
    with pytest.raises(RuntimeError, match="Nicht freigegebene Portbindung"):
        runtime._validate_rendered(stack, rendered)



def test_milvus_resource_preflight_enforces_official_minimums(monkeypatch) -> None:
    class DiskUsage:
        free = 10 * 1024 * 1024 * 1024

    monkeypatch.setattr(os, "cpu_count", lambda: 4)
    monkeypatch.setattr(
        os,
        "sysconf",
        lambda name: 4096 if name == "SC_PAGE_SIZE" else 2 * 1024 * 1024,
    )
    monkeypatch.setattr("managed_compose.shutil.disk_usage", lambda _path: DiskUsage())

    verified = ManagedComposeRuntime._milvus_resource_preflight()
    assert verified["ok"] is True
    assert verified["status"] == "MILVUS_HOST_RESOURCES_VERIFIED"

    monkeypatch.setattr(os, "cpu_count", lambda: 2)
    blocked = ManagedComposeRuntime._milvus_resource_preflight()
    assert blocked["ok"] is False
    assert blocked["status"] == "MILVUS_HOST_RESOURCES_INSUFFICIENT"
    assert blocked["checks"]["cpu"] is False


def test_milvus_network_preflight_requires_isolated_gateway_and_expected_subnet(tmp_path: Path) -> None:
    def runner(argv, **kwargs):
        if argv[:3] == ["docker", "network", "inspect"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                '[{"Subnet":"172.16.5.0/24"}]|'
                '{"gateway":{"Name":"sovereign-memory-gateway","IPv4Address":"172.16.5.2/24"}}',
                "",
            )
        return subprocess.CompletedProcess(argv, 1, "", "not found")

    runtime = ManagedComposeRuntime(runner=runner, template_root=str(tmp_path))
    result = runtime._milvus_network_preflight()

    assert result["ok"] is True
    assert result["status"] == "MILVUS_GATEWAY_NETWORK_VERIFIED"
    assert result["compatibilityIp"] == "172.16.5.4"
    assert result["externalPortsRequired"] is False


def test_milvus_network_preflight_blocks_unexpected_member(tmp_path: Path) -> None:
    def runner(argv, **kwargs):
        if argv[:3] == ["docker", "network", "inspect"]:
            return subprocess.CompletedProcess(
                argv,
                0,
                '[{"Subnet":"172.16.5.0/24"}]|'
                '{"gateway":{"Name":"sovereign-memory-gateway","IPv4Address":"172.16.5.2/24"},'
                '"foreign":{"Name":"foreign-service","IPv4Address":"172.16.5.3/24"}}',
                "",
            )
        return subprocess.CompletedProcess(argv, 1, "", "not found")

    runtime = ManagedComposeRuntime(runner=runner, template_root=str(tmp_path))
    result = runtime._milvus_network_preflight()

    assert result["ok"] is False
    assert result["status"] == "MILVUS_GATEWAY_NETWORK_NOT_ISOLATED"
    assert result["unexpectedMembers"] == ["foreign-service"]


def test_litellm_inventory_and_alias_tools_are_broker_bounded() -> None:
    root = Path(__file__).resolve().parents[1]
    server = (root / "server.py").read_text("utf-8")
    broker = (root / "broker.py").read_text("utf-8")

    assert "def litellm_provider_model_inventory()" in server
    assert "def litellm_model_aliases_activate(" in server
    assert 'broker.call("litellm_provider_model_inventory", {}, timeout=90)' in server
    assert '"litellm_model_aliases_activate"' in server
    assert '"litellm_provider_model_inventory": lambda _values:' in broker
    assert '"openai_project_runtime_evidence": lambda _values:' in broker
    assert '"litellm_model_aliases_activate": lambda values:' in broker
