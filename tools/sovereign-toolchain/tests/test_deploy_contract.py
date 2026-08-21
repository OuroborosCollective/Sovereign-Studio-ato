import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIT = ROOT / "sovereign-toolchain" / "deploy" / "sovereign-toolchain.service"
INSTALLER = ROOT / "sovereign-toolchain" / "deploy" / "install-on-vps.sh"
APP = ROOT / "sovereign-toolchain" / "src" / "sovereign_toolchain" / "app.py"
METADATA_READER = ROOT / "sovereign-toolchain" / "deploy" / "read-broker-github-app-metadata.sh"
WORKFLOW = ROOT.parent / ".github" / "workflows" / "sovereign-toolchain.yml"


def test_unit_uses_systemd_credential_without_persistent_github_token() -> None:
    unit = UNIT.read_text("utf-8")
    assert "LoadCredential=github-app-private-key.pem:/opt/secure/sovereign-github-app/private-key.pem" in unit
    assert "EnvironmentFile=/etc/sovereign-toolchain/runtime.env" in unit
    assert "GITHUB_TOKEN=" not in unit
    assert "GH_TOKEN=" not in unit
    assert "GITHUB_PAT=" not in unit
    assert "%d/" not in unit


def test_installer_requires_locked_runtime_and_tokenfree_process_readback() -> None:
    installer = INSTALLER.read_text("utf-8")
    assert "uv sync --frozen --no-dev" in installer
    assert "SOVEREIGN_TOOLCHAIN_INSTALL_FAILURE" in installer
    assert "LoadCredential" not in installer
    assert "persistent GitHub token inherited by service" in installer
    assert "runtime environment has persistent GitHub token" in installer
    assert "GitHub App private key owner is invalid" in installer
    assert "GitHub App private key mode is invalid" in installer
    assert ". /opt/sovereign-chatgpt-tools/broker.env" not in installer
    assert "read-broker-github-app-metadata.sh" in installer


def test_metadata_reader_ignores_unrelated_non_shellsafe_dotenv_line(tmp_path: Path) -> None:
    broker_env = tmp_path / "broker.env"
    broker_env.write_text(
        "SOVEREIGN_MCP_GITHUB_APP_ID=12345\n"
        "SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID=67890\n"
        "SOVEREIGN_MCP_REPOSITORY=OuroborosCollective/Sovereign-Studio-ato\n"
        "UNRELATED_NOTE=NOCode command-shaped text\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(METADATA_READER), str(broker_env)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stderr == ""
    assert result.stdout.splitlines() == [
        "SOVEREIGN_MCP_GITHUB_APP_ID=12345",
        "SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID=67890",
        "SOVEREIGN_MCP_REPOSITORY=OuroborosCollective/Sovereign-Studio-ato",
    ]


def test_metadata_reader_rejects_duplicate_required_literal(tmp_path: Path) -> None:
    broker_env = tmp_path / "broker.env"
    broker_env.write_text(
        "SOVEREIGN_MCP_GITHUB_APP_ID=12345\n"
        "SOVEREIGN_MCP_GITHUB_APP_ID=54321\n"
        "SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID=67890\n"
        "SOVEREIGN_MCP_REPOSITORY=OuroborosCollective/Sovereign-Studio-ato\n",
        encoding="utf-8",
    )
    result = subprocess.run(["bash", str(METADATA_READER), str(broker_env)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "cardinality invalid" in result.stderr


def test_ci_is_supplemental_and_exact_head_bound() -> None:
    workflow = WORKFLOW.read_text("utf-8")
    assert "pull_request:" not in workflow
    assert "workflow_dispatch:" in workflow
    assert "expected_head_sha:" in workflow
    assert "ref: ${{ inputs.expected_head_sha || github.sha }}" in workflow
    assert "Verify exact dispatch revision" in workflow
    assert "astral-sh/setup-uv@38f3f104447c67c051c4a08e39b64a148898af3a # v4" in workflow
    assert "astral-sh/setup-uv@v4" not in workflow


def test_app_exposes_the_installer_health_contract() -> None:
    app = APP.read_text("utf-8")
    assert "@app.get(\"/\")" in app
    assert '"ok": True' in app
    assert '"name": "Sovereign Universal Toolchain"' in app
