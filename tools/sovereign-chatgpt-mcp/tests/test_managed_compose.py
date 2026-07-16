from __future__ import annotations

import hashlib
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
    }
    assert is_mutating_action("deploy_managed_compose_stack") is True
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
    (template / "docker-compose.yml").write_bytes(compose)
    (template / "config.yaml").write_bytes(config)
    runtime = ManagedComposeRuntime(runner=_missing_runner, template_root=str(tmp_path))
    result = runtime.plan("sovereign-litellm")
    expected = hashlib.sha256(
        f"{hashlib.sha256(compose).hexdigest()}:{hashlib.sha256(config).hexdigest()}".encode("ascii")
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
