from __future__ import annotations

import json
import subprocess
from pathlib import Path

from litellm_stack import DB_IMAGE, LITELLM_IMAGE, LiteLLMStackRuntime


def _rendered_payload(root: Path, *, public_port: bool = False, command: list[str] | None = None) -> dict:
    litellm: dict = {
        "image": LITELLM_IMAGE,
        "command": command if command is not None else ["--config=/app/config.yaml", "--port", "4000"],
        "environment": {
            "DATABASE_URL": "postgresql://litellm:abcdefghijklmnop@db:5432/litellm",
            "LITELLM_MASTER_KEY": "sk-abcdefghijklmnop",
            "LITELLM_SALT_KEY": "sk-ponmlkjihgfedcba",
        },
        "networks": {"sovereign-private": None},
        "volumes": [
            {
                "type": "bind",
                "source": str((root / "config.yaml").resolve()),
                "target": "/app/config.yaml",
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
        b"POSTGRES_PASSWORD=abcdefghijklmnop\nLITELLM_MASTER_KEY=sk-abcdefghijklmnop\nLITELLM_SALT_KEY=sk-ponmlkjihgfedcba\n",
    )
    assert result == {"ok": True, "status": "VALIDATED"}
    assert "abcdefghijklmnop" not in repr(result)


def test_litellm_candidate_blocks_public_port(tmp_path: Path) -> None:
    runtime = LiteLLMStackRuntime(runner=_runner_factory(public_port=True), template_root=str(tmp_path), deploy_root=str(tmp_path / "deploy"))
    result = runtime._validate_candidate(b"services: {}\n", b"model_list: []\n", b"x=y\n")
    assert result["ok"] is False
    assert result["error"] == "published ports are forbidden: litellm"


def test_litellm_candidate_blocks_command_override(tmp_path: Path) -> None:
    runtime = LiteLLMStackRuntime(
        runner=_runner_factory(command=["python", "-c", "print('override')"]),
        template_root=str(tmp_path),
        deploy_root=str(tmp_path / "deploy"),
    )
    result = runtime._validate_candidate(b"services: {}\n", b"model_list: []\n", b"x=y\n")
    assert result["ok"] is False
    assert result["error"] == "unexpected LiteLLM command"
