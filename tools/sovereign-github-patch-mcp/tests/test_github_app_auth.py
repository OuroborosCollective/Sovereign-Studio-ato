import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "sovereign-legacy-mcp-common"
PATCH_MCP = ROOT / "sovereign-github-patch-mcp"
sys.path.insert(0, str(COMMON))
sys.path.insert(0, str(PATCH_MCP))

from github_app_auth import GitHubAppInstallationAuth, GitHubAppInstallationConfig
import server


class _Environment:
    def __init__(self, values: dict[str, str | None]) -> None:
        self.values = values
        self.previous: dict[str, str | None] = {}

    def __enter__(self) -> None:
        for key, value in self.values.items():
            self.previous[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def __exit__(self, *_: object) -> None:
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _config_environment(key: Path) -> _Environment:
    return _Environment(
        {
            "SOVEREIGN_MCP_GITHUB_APP_ID": "12345",
            "SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID": "67890",
            "SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE": str(key),
            "SOVEREIGN_MCP_REPOSITORY": "OuroborosCollective/Sovereign-Studio-ato",
        }
    )


def test_app_jwt_is_signed_by_the_configured_private_key(tmp_path: Path) -> None:
    key = tmp_path / "github-app.pem"
    public_key = tmp_path / "github-app.pub.pem"
    subprocess.run(["openssl", "genrsa", "-out", str(key), "2048"], check=True, capture_output=True)
    key.chmod(0o600)
    subprocess.run(["openssl", "pkey", "-in", str(key), "-pubout", "-out", str(public_key)], check=True, capture_output=True)

    with _config_environment(key):
        config = GitHubAppInstallationConfig.from_env()
        jwt = GitHubAppInstallationAuth(config, now=lambda: 1_700_000_000)._app_jwt()

    header, claims, signature = jwt.split(".")
    decoded_header = json.loads(base64.urlsafe_b64decode(header + "=="))
    decoded_claims = json.loads(base64.urlsafe_b64decode(claims + "=="))
    assert decoded_header == {"alg": "RS256", "typ": "JWT"}
    assert decoded_claims == {"iat": 1_699_999_940, "exp": 1_700_000_540, "iss": "12345"}
    signature_file = tmp_path / "jwt.sig"
    signing_input = tmp_path / "jwt.input"
    signature_file.write_bytes(base64.urlsafe_b64decode(signature + "=="))
    signing_input.write_text(f"{header}.{claims}", "ascii")
    verification = subprocess.run(
        ["openssl", "dgst", "-sha256", "-verify", str(public_key), "-signature", str(signature_file), str(signing_input)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert verification.returncode == 0, verification.stderr
    assert verification.stdout.strip() == "Verified OK"


def test_app_config_uses_systemd_credential_directory_when_explicit_path_is_absent(tmp_path: Path) -> None:
    key = tmp_path / "github-app-private-key.pem"
    key.write_text("not-used", "utf-8")
    key.chmod(0o400)
    with _Environment(
        {
            "SOVEREIGN_MCP_GITHUB_APP_ID": "12345",
            "SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID": "67890",
            "SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE": None,
            "SOVEREIGN_MCP_REPOSITORY": "OuroborosCollective/Sovereign-Studio-ato",
            "CREDENTIALS_DIRECTORY": str(tmp_path),
        }
    ):
        config = GitHubAppInstallationConfig.from_env()
    assert config.private_key_file == key


def test_app_config_rejects_a_group_readable_private_key(tmp_path: Path) -> None:
    key = tmp_path / "github-app.pem"
    key.write_text("not-used", "utf-8")
    key.chmod(0o644)
    with _config_environment(key), pytest.raises(RuntimeError, match="security contract"):
        GitHubAppInstallationConfig.from_env()


def test_patch_mcp_does_not_fall_back_to_persistent_github_token() -> None:
    with _Environment(
        {
            "GITHUB_TOKEN": "test-persistent-token-must-not-be-used",
            "SOVEREIGN_MCP_GITHUB_APP_ID": None,
            "SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID": None,
            "SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE": None,
            "SOVEREIGN_MCP_REPOSITORY": None,
        }
    ), pytest.raises(server.McpToolError, match="GitHub App installation authentication"):
        async def invoke() -> None:
            async with server._github_headers():
                raise AssertionError("persistent token fallback unexpectedly succeeded")

        asyncio.run(invoke())
