from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEVCONTAINER = ROOT / ".devcontainer" / "devcontainer.json"
BOOTSTRAP = ROOT / ".devcontainer" / "bootstrap.sh"
RUN_TESTS = ROOT / ".devcontainer" / "run-tests.sh"


def _config() -> dict:
    return json.loads(DEVCONTAINER.read_text(encoding="utf-8"))


def test_devcontainer_uses_official_additive_runtime_features() -> None:
    config = _config()

    assert config["image"] == "mcr.microsoft.com/devcontainers/base:ubuntu-24.04"
    assert config["remoteUser"] == "vscode"

    features = config["features"]
    assert features["ghcr.io/devcontainers/features/node:2"]["version"] == "22"
    assert features["ghcr.io/devcontainers/features/python:1"]["version"] == "3.11"
    assert features["ghcr.io/devcontainers/features/java:1"]["version"] == "17"
    assert "ghcr.io/devcontainers/features/docker-in-docker:4" in features
    assert "ghcr.io/devcontainers/features/github-cli:1" in features


def test_devcontainer_matches_repository_runtime_ports_and_resources() -> None:
    config = _config()

    assert config["postCreateCommand"] == "bash .devcontainer/bootstrap.sh"
    assert set(config["forwardPorts"]) == {3000, 8787}
    assert config["hostRequirements"]["cpus"] >= 4
    assert config["hostRequirements"]["memory"] == "8gb"


def test_bootstrap_keeps_backend_and_mcp_python_contracts_isolated() -> None:
    text = BOOTSTRAP.read_text(encoding="utf-8")

    assert "pnpm@9.12.2" in text
    assert ".venv-backend-tests" in text
    assert ".venv-mcp-tests" in text
    assert "backend/requirements-test.txt" in text
    assert "tools/sovereign-chatgpt-mcp/requirements.txt" in text
    assert "scripts/check-backend-python-runtime.py" in text
    assert "playwright install --with-deps chromium" in text
    assert "pytest=8.4.1" in text


def test_codespace_profiles_exercise_real_agent_and_mcp_test_paths() -> None:
    text = RUN_TESTS.read_text(encoding="utf-8")

    assert "backend/tests/test_agent_runtime_no_openhands_required.py" in text
    assert "backend/tests/test_agent_runtime_e2e.py" in text
    assert "pnpm run test:agent-runtime:frontend" in text
    assert "tools/sovereign-chatgpt-mcp/tests/test_runtime_production_flow.py" in text
    assert "tools/sovereign-chatgpt-mcp/tests/test_registry_runtime_evidence.py" in text
    assert "pnpm run test:e2e" in text
    assert "pnpm run verify" in text


def test_devcontainer_does_not_embed_secrets_or_replace_production_entrypoints() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (DEVCONTAINER, BOOTSTRAP, RUN_TESTS)
    ).lower()

    forbidden = (
        "github_token=",
        "openai_api_key=",
        "authorization: bearer",
        "docker cp",
        "litellm",
        "cloudflare",
    )
    for marker in forbidden:
        assert marker not in combined
