import os
from contextlib import contextmanager
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sovereign-legacy-mcp-common"))
sys.path.insert(0, str(ROOT / "sovereign-toolchain" / "src"))

from sovereign_toolchain.core import GitHubClient


@contextmanager
def environment(values: dict[str, str | None]):
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_persistent_github_token_does_not_enable_toolchain_client() -> None:
    with environment(
        {
            "GITHUB_TOKEN": "persistent-token-must-not-be-used",
            "SOVEREIGN_MCP_GITHUB_APP_ID": None,
            "SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID": None,
            "SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE": None,
            "SOVEREIGN_MCP_REPOSITORY": None,
            "CREDENTIALS_DIRECTORY": None,
        }
    ), pytest.raises(RuntimeError, match="SOVEREIGN_MCP_GITHUB_APP_ID is invalid"):
        GitHubClient()


def test_toolchain_core_uses_shared_app_only_adapter() -> None:
    source = (ROOT / "sovereign-toolchain" / "src" / "sovereign_toolchain" / "core.py").read_text("utf-8")
    assert "GitHubAppInstallationAuth" in source
    assert "GitHubAppInstallationConfig" in source
    assert 'os.getenv("GITHUB_TOKEN"' not in source
    assert "with self.auth.token() as issued" in source
