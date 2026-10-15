"""Exercise the installer's real broker projection without privileged host effects."""
from pathlib import Path
import subprocess

import pytest

INSTALLER = Path(__file__).resolve().parents[1] / "deploy" / "install-on-vps.sh"


def project_broker_environment(tmp_path, configured="", managed=""):
    source = INSTALLER.read_text(encoding="utf-8")
    section = source.split('INSTALL_STAGE="write_broker_environment"', 1)[1]
    body = section.split("if ! {\n", 1)[1].split('} > "$BROKER_ENV"; then', 1)[0]
    env_file = tmp_path / "configured.env"
    managed_file = tmp_path / "managed.env"
    broker_file = tmp_path / "broker.env"
    env_file.write_text(configured, encoding="utf-8")
    managed_file.write_text(managed, encoding="utf-8")
    result = subprocess.run(
        ["bash", "-eu", "-c", '{\n' + body + '} > "$BROKER_ENV"'],
        env={
            "PATH": "/usr/bin:/bin",
            "ENV_FILE": str(env_file),
            "MANAGED_ENV": str(managed_file),
            "BROKER_ENV": str(broker_file),
            "BIN_DIR": str(tmp_path / "bin"),
            "BROKER_GOVERNANCE_MODE": str(tmp_path / "governance"),
            "GITHUB_APP_PRIVATE_KEY_FILE": str(tmp_path / "github-key-path-only"),
            "COMMAND_QUEUE_DIR": str(tmp_path / "queue"),
            "COMPOSE_TEMPLATE_ROOT": str(tmp_path / "templates"),
            "DOCKER_CONFIG_VALUE": "",
        },
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == ""
    assert result.stderr == ""
    raw = broker_file.read_text(encoding="utf-8")
    return dict(line.split("=", 1) for line in raw.splitlines()), raw


@pytest.mark.parametrize("key,value", [
    ("AURION_ADMIN_MCP_ACCESS_TOKEN_FILE", "/protected/aurion-access-file"),
    ("AURION_ADMIN_MCP_RESOURCE_URL", "https://arelogic.space/admin-mcp"),
    ("AURION_ADMIN_MCP_SCOPES", "aurion.admin.read"),
    ("AURION_ADMIN_MCP_WOLFRAM_ENABLED", "0"),
    ("SOVEREIGN_MCP_ENABLE_AURION_ADMIN_MCP", "1"),
])
def test_configured_aurion_settings_reach_existing_broker(tmp_path, key, value):
    values, _ = project_broker_environment(tmp_path, f"{key}={value}\n")
    assert values.get(key) == value


def test_missing_aurion_authority_is_not_invented(tmp_path):
    values, _ = project_broker_environment(tmp_path)
    assert not any(key.startswith("AURION_ADMIN_MCP_") for key in values)
    assert "SOVEREIGN_MCP_ENABLE_AURION_ADMIN_MCP" not in values


def test_managed_config_retains_existing_precedence_without_reading_credential(tmp_path):
    # A directory deliberately cannot be read as a token file by the projection.
    protected_path = tmp_path / "protected-token-path"
    protected_path.mkdir()
    key = "AURION_ADMIN_MCP_ACCESS_TOKEN_FILE"
    values, raw = project_broker_environment(
        tmp_path,
        f"{key}=/earlier/path\n",
        f"{key}={protected_path}\nAURION_ADMIN_MCP_SCOPES=aurion.admin.read\n",
    )
    assert values.get(key) == str(protected_path)
    assert raw.index(f"{key}=/earlier/path") < raw.index(f"{key}={protected_path}")


def test_raw_credential_and_unknown_settings_are_not_projected(tmp_path):
    values, raw = project_broker_environment(
        tmp_path,
        "AURION_ADMIN_MCP_ACCESS_TOKEN=fixture-not-a-credential\n"
        "AURION_ADMIN_MCP_UNKNOWN=unsupported\n"
        "AURION_ADMIN_MCP_SCOPES_EXTRA=unsupported\n",
        "AURION_ADMIN_MCP_ACCESS_TOKEN=fixture-not-a-credential\n",
    )
    assert "AURION_ADMIN_MCP_ACCESS_TOKEN" not in values
    assert "AURION_ADMIN_MCP_UNKNOWN" not in values
    assert "AURION_ADMIN_MCP_SCOPES_EXTRA" not in values
    assert "fixture-not-a-credential" not in raw
