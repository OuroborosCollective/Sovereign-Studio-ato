from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "sovereign-github-patch-mcp" / "deploy" / "sovereign-mcp.service"
INSTALLER = ROOT / "sovereign-github-patch-mcp" / "deploy" / "install-on-vps.sh"
ENV_TEMPLATE = ROOT / "sovereign-github-patch-mcp" / ".env.example"
SERVER = ROOT / "sovereign-github-patch-mcp" / "server.py"


def test_unit_uses_systemd_credential_and_no_persistent_token() -> None:
    unit = SERVICE.read_text("utf-8")
    assert "LoadCredential=github-app-private-key.pem:/opt/secure/sovereign-github-app/private-key.pem" in unit
    assert "SOVEREIGN_MCP_GITHUB_APP_PRIVATE_KEY_FILE=" not in unit
    assert "%d/github-app-private-key.pem" not in unit
    assert "EnvironmentFile=/etc/sovereign-github-patch-mcp/runtime.env" in unit
    assert "GITHUB_TOKEN=" not in unit
    assert "GH_TOKEN=" not in unit
    assert "GITHUB_PAT=" not in unit


def test_template_and_server_require_app_auth_not_a_persistent_token() -> None:
    template = ENV_TEMPLATE.read_text("utf-8")
    server = SERVER.read_text("utf-8")
    assert "SOVEREIGN_MCP_GITHUB_APP_ID=" in template
    assert "SOVEREIGN_MCP_GITHUB_APP_INSTALLATION_ID=" in template
    assert "SOVEREIGN_MCP_REPOSITORY=OuroborosCollective/Sovereign-Studio-ato" in template
    assert "GITHUB_TOKEN=github_pat_" not in template
    assert 'os.getenv("GITHUB_TOKEN"' not in server
    assert "GitHubAppInstallationAuth" in server
    assert "GitHubAppInstallationConfig" in server


def test_installer_builds_locked_runtime_and_readbacks_token_absence() -> None:
    installer = INSTALLER.read_text("utf-8")
    assert "uv sync --frozen --no-dev" in installer
    assert "SOVEREIGN_MCP_INSTALL_FAILURE" in installer
    assert "systemctl restart \"$SERVICE\"" in installer
    assert "persistent GitHub token inherited by service" in installer
    assert "runtime environment has persistent GitHub token" in installer
    assert "[[ \"$KEY_UID\" == \"0\" ]] || fail \"GitHub App private key owner is invalid\"" in installer
    assert "GitHub App private key mode is invalid" in installer
    assert "KEY_GID=" not in installer
    assert "SOVEREIGN_MCP_GID=" not in installer
    assert "GITHUB_TOKEN=ghp_" not in installer
