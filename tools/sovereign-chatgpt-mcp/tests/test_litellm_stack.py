from __future__ import annotations

import json
import subprocess

import pytest
from pathlib import Path

from litellm_stack import DB_IMAGE, LITELLM_IMAGE, LiteLLMStackRuntime


def _rendered_payload(root: Path, *, public_port: bool = False, command: list[str] | None = None) -> dict:
    litellm: dict = {
        "image": LITELLM_IMAGE,
        "entrypoint": ["python", "/app/sovereign-entrypoint.py"],
        "command": command if command is not None else ["--config=/app/config.yaml", "--port", "4000"],
        "environment": {
            "DATABASE_URL": "postgresql://litellm:abcdefghijklmnop@db:5432/litellm",
            "LITELLM_MASTER_KEY": "sk-abcdefghijklmnop",
            "LITELLM_SALT_KEY": "sk-ponmlkjihgfedcba",
            "STORE_MODEL_IN_DB": "True",
        },
        "networks": {"sovereign-private": None},
        "volumes": [
            {
                "type": "bind",
                "source": str((root / "config.yaml").resolve()),
                "target": "/app/config.yaml",
                "read_only": True,
            },
            {
                "type": "bind",
                "source": str((root / "sovereign-entrypoint.py").resolve()),
                "target": "/app/sovereign-entrypoint.py",
                "read_only": True,
            },
            {
                "type": "bind",
                "source": "/opt/sovereign-owner-managed/openai_api_key.txt",
                "target": "/run/secrets/openai_api_key",
                "read_only": True,
            }
        ],
    }
    if public_port:
        litellm["ports"] = [{"host_ip": "0.0.0.0", "published": "4000", "target": 4000}]
    return {
        "services": {
            "db": {
                "image": DB_IMAGE,
                "environment": {
                    "POSTGRES_DB": "litellm",
                    "POSTGRES_USER": "litellm",
                    "POSTGRES_PASSWORD": "abcdefghijklmnop",
                },
                "networks": {"sovereign-private": None},
                "volumes": [
                    {
                        "type": "volume",
                        "source": "litellm_db",
                        "target": "/var/lib/postgresql/data",
                    }
                ],
            },
            "litellm": litellm,
        },
        "networks": {"sovereign-private": {"external": True}},
        "volumes": {"litellm_db": {}},
    }


def _runner_factory(*, public_port: bool = False, command: list[str] | None = None):
    def runner(argv, **kwargs):
        root = Path(argv[argv.index("--project-directory") + 1])
        payload = _rendered_payload(root, public_port=public_port, command=command)
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

    return runner


def test_fixed_litellm_candidate_passes_strict_rendered_policy(tmp_path: Path) -> None:
    runtime = LiteLLMStackRuntime(runner=_runner_factory(), template_root=str(tmp_path), deploy_root=str(tmp_path / "deploy"))
    result = runtime._validate_candidate(
        b"services: {}\n",
        b"model_list: []\n",
        b"from __future__ import annotations\n",
        b"POSTGRES_PASSWORD=abcdefghijklmnop\nLITELLM_MASTER_KEY=sk-abcdefghijklmnop\nLITELLM_SALT_KEY=sk-ponmlkjihgfedcba\n",
    )
    assert result == {"ok": True, "status": "VALIDATED"}
    assert "abcdefghijklmnop" not in repr(result)


def test_litellm_candidate_blocks_public_port(tmp_path: Path) -> None:
    runtime = LiteLLMStackRuntime(runner=_runner_factory(public_port=True), template_root=str(tmp_path), deploy_root=str(tmp_path / "deploy"))
    result = runtime._validate_candidate(
        b"services: {}\n",
        b"model_list: []\n",
        b"from __future__ import annotations\n",
        b"x=y\n",
    )
    assert result["ok"] is False
    assert result["error"] == "published ports are forbidden: litellm"


def test_litellm_candidate_blocks_command_override(tmp_path: Path) -> None:
    runtime = LiteLLMStackRuntime(
        runner=_runner_factory(command=["python", "-c", "print('override')"]),
        template_root=str(tmp_path),
        deploy_root=str(tmp_path / "deploy"),
    )
    result = runtime._validate_candidate(
        b"services: {}\n",
        b"model_list: []\n",
        b"from __future__ import annotations\n",
        b"x=y\n",
    )
    assert result["ok"] is False
    assert result["error"] == "unexpected LiteLLM command"


def test_compose_deploy_preserves_stack_update_and_forces_secret_remount(
    tmp_path: Path,
) -> None:
    runtime = LiteLLMStackRuntime(
        runner=_runner_factory(),
        template_root=str(tmp_path),
        deploy_root=str(tmp_path / "deploy"),
    )

    assert runtime._compose_up_command()[-3:] == [
        "up",
        "-d",
        "--remove-orphans",
    ]
    assert runtime._litellm_recreate_command()[-5:] == [
        "up",
        "-d",
        "--force-recreate",
        "--no-deps",
        "litellm",
    ]


def test_deploy_confirms_remount_only_after_targeted_recreate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    template_root = tmp_path / "templates"
    deploy_root = tmp_path / "deploy"
    template_root.mkdir()
    (template_root / "docker-compose.yml").write_bytes(b"services: {}\n")
    (template_root / "config.yaml").write_bytes(b"model_list: []\n")
    (template_root / "sovereign-entrypoint.py").write_bytes(
        b"from __future__ import annotations\n"
    )
    captured: list[list[str]] = []

    def runner(argv, **kwargs):
        captured.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    runtime = LiteLLMStackRuntime(
        runner=runner,
        template_root=str(template_root),
        deploy_root=str(deploy_root),
    )
    monkeypatch.setenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "1")
    monkeypatch.setenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "1")
    monkeypatch.setattr(runtime, "_resolved_config", lambda config: (config, None))
    monkeypatch.setattr(
        runtime,
        "_existing_secret_values",
        lambda: {
            "POSTGRES_PASSWORD": "abcdefghijklmnop",
            "LITELLM_MASTER_KEY": "test-master-key-abcdefghijklmnop",
            "LITELLM_SALT_KEY": "test-salt-key-ponmlkjihgfedcba",
        },
    )
    monkeypatch.setattr(runtime, "_validate_owner_provider_input", lambda: None)
    monkeypatch.setattr(
        runtime,
        "_validate_candidate",
        lambda compose, config, entrypoint, env_payload: {
            "ok": True,
            "status": "VALIDATED",
        },
    )
    monkeypatch.setattr(runtime, "_write_backend_service_key", lambda value: None)
    monkeypatch.setattr(
        runtime,
        "_wait_for_runtime",
        lambda: {
            "litellm": {
                "running": True,
                "health": "healthy",
                "networks": ["sovereign-private"],
                "publishedPorts": {},
            },
            "db": {
                "running": True,
                "health": "healthy",
                "networks": ["sovereign-private"],
                "publishedPorts": {},
            },
        },
    )
    monkeypatch.setattr(runtime, "_readiness", lambda: {"ok": True})
    monkeypatch.setattr(runtime, "_models", lambda: {"ok": False})
    _, compose_sha = runtime._template("docker-compose.yml")
    _, config_sha = runtime._template("config.yaml")
    _, entrypoint_sha = runtime._template("sovereign-entrypoint.py")

    result = runtime.deploy(
        confirmation_compose_sha256=compose_sha,
        confirmation_config_sha256=config_sha,
        confirmation_entrypoint_sha256=entrypoint_sha,
    )

    compose_up_calls = [
        argv
        for argv in captured
        if argv[:2] == ["docker", "compose"] and "up" in argv
    ]
    assert compose_up_calls == [
        runtime._compose_up_command(),
        runtime._litellm_recreate_command(),
    ]
    assert result["status"] == "DEPLOYED_UNVERIFIED"
    assert result["providerSecretRemount"] == {
        "ok": True,
        "service": "litellm",
        "forceRecreate": True,
        "databaseRecreated": False,
    }


def _completion_runner(*, request_id_present: bool = True, total_tokens: int = 3):
    def runner(argv, **kwargs):
        payload = {
            "httpStatus": 200,
            "requestIdPresent": request_id_present,
            "resolvedModel": "openai/verified-model",
            "promptTokens": 2,
            "completionTokens": max(0, total_tokens - 2),
            "totalTokens": total_tokens,
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload) + "\n", "")

    return runner


def test_completion_canary_requires_request_id_and_positive_usage(tmp_path: Path) -> None:
    runtime = LiteLLMStackRuntime(
        runner=_completion_runner(),
        template_root=str(tmp_path),
        deploy_root=str(tmp_path / "deploy"),
    )
    result = runtime._completion_canary("sovereign-fast")
    assert result["ok"] is True
    assert result["requestedModel"] == "sovereign-fast"
    assert result["resolvedModel"] == "openai/verified-model"
    assert result["requestIdPresent"] is True
    assert result["usage"]["totalTokens"] == 3
    assert result["responseContentExposed"] is False
    assert result["secretValuesExposed"] is False
    assert "content" not in result


def test_completion_canary_rejects_missing_runtime_evidence(tmp_path: Path) -> None:
    runtime = LiteLLMStackRuntime(
        runner=_completion_runner(request_id_present=False, total_tokens=0),
        template_root=str(tmp_path),
        deploy_root=str(tmp_path / "deploy"),
    )
    result = runtime._completion_canary("sovereign-balanced")
    assert result["ok"] is False
    assert result["requestIdPresent"] is False
    assert result["usage"]["totalTokens"] == 0


def test_provider_inventory_runs_in_portless_fixed_image_and_returns_only_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: list[list[str]] = []

    def runner(argv, **kwargs):
        captured.append(list(argv))
        payload = {
            "httpStatus": 200,
            "modelIds": ["gpt-confirmed-b", "invalid model id", "gpt-confirmed-a"],
            "identityHttpStatus": 200,
            "principalId": "user-confirmed-service-account",
            "principalName": "Sovereignatp",
            "organizationIds": ["org-confirmed"],
            "projectId": "proj-confirmed",
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload) + "\n", "")

    runtime = LiteLLMStackRuntime(
        runner=runner,
        template_root=str(tmp_path),
        deploy_root=str(tmp_path / "deploy"),
    )
    monkeypatch.setattr(runtime, "_validate_owner_provider_input", lambda: None)

    result = runtime.provider_model_inventory()

    assert result["ok"] is True
    assert result["modelIds"] == ["gpt-confirmed-a", "gpt-confirmed-b"]
    assert result["providerKeyPresent"] is True
    assert result["providerKeyValueReturned"] is False
    assert result["secretValuesExposed"] is False
    assert result["publicPortOpened"] is False
    assert result["providerIdentity"] == {
        "verified": True,
        "httpStatus": 200,
        "principalId": "user-confirmed-service-account",
        "principalName": "Sovereignatp",
        "organizationIds": ["org-confirmed"],
        "projectId": "proj-confirmed",
    }
    argv = captured[0]
    assert argv[:3] == ["docker", "run", "--rm"]
    assert "--read-only" in argv
    assert "--cap-drop" in argv
    assert "--publish" not in argv
    assert "-p" not in argv
    assert LITELLM_IMAGE in argv
    assert "https://api.openai.com/v1/me" in " ".join(argv)
    assert "sk-proj-" not in " ".join(argv)


def test_provider_inventory_blocks_without_safe_principal_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def runner(argv, **kwargs):
        payload = {
            "httpStatus": 200,
            "modelIds": ["gpt-confirmed-a"],
            "identityHttpStatus": 200,
            "principalId": "",
            "principalName": "",
            "organizationIds": [],
            "projectId": "",
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload) + "\n", "")

    runtime = LiteLLMStackRuntime(
        runner=runner,
        template_root=str(tmp_path),
        deploy_root=str(tmp_path / "deploy"),
    )
    monkeypatch.setattr(runtime, "_validate_owner_provider_input", lambda: None)

    result = runtime.provider_model_inventory()

    assert result["ok"] is False
    assert result["providerIdentity"]["verified"] is False
    assert result["providerKeyValueReturned"] is False
    assert result["secretValuesExposed"] is False


def test_alias_config_is_derived_only_from_confirmed_provider_models() -> None:
    selection = {
        "inventorySha256": "a" * 64,
        "sovereign-fast": "gpt-confirmed-fast",
        "sovereign-balanced": "gpt-confirmed-balanced",
    }

    config = LiteLLMStackRuntime._alias_config(selection).decode("utf-8")

    assert "model_name: sovereign-fast" in config
    assert "model_name: sovereign-balanced" in config
    assert 'model: "openai/gpt-confirmed-fast"' in config
    assert 'model: "openai/gpt-confirmed-balanced"' in config
    assert "api_key: os.environ/OPENAI_API_KEY" in config
    assert "sk-proj-" not in config


def test_resolved_alias_config_requires_current_inventory_digest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    deploy_root = tmp_path / "deploy"
    deploy_root.mkdir()
    selection = {
        "inventorySha256": "b" * 64,
        "sovereign-fast": "gpt-confirmed-fast",
        "sovereign-balanced": "gpt-confirmed-balanced",
    }
    (deploy_root / "model-aliases.json").write_text(json.dumps(selection), "utf-8")
    runtime = LiteLLMStackRuntime(
        runner=_runner_factory(),
        template_root=str(tmp_path),
        deploy_root=str(deploy_root),
    )
    monkeypatch.setattr(
        runtime,
        "provider_model_inventory",
        lambda: {
            "ok": True,
            "inventorySha256": "b" * 64,
            "modelIds": ["gpt-confirmed-fast", "gpt-confirmed-balanced"],
        },
    )

    config, evidence = runtime._resolved_config(b"model_list: []\n")

    assert b"model_name: sovereign-fast" in config
    assert evidence == {
        "inventorySha256": "b" * 64,
        "aliases": {
            "sovereign-fast": "gpt-confirmed-fast",
            "sovereign-balanced": "gpt-confirmed-balanced",
        },
    }

    monkeypatch.setattr(
        runtime,
        "provider_model_inventory",
        lambda: {
            "ok": True,
            "inventorySha256": "c" * 64,
            "modelIds": ["gpt-confirmed-fast", "gpt-confirmed-balanced"],
        },
    )
    with pytest.raises(RuntimeError, match="geändert"):
        runtime._resolved_config(b"model_list: []\n")
