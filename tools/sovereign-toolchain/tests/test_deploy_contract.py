from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIT = ROOT / "sovereign-toolchain" / "deploy" / "sovereign-toolchain.service"
INSTALLER = ROOT / "sovereign-toolchain" / "deploy" / "install-on-vps.sh"
APP = ROOT / "sovereign-toolchain" / "src" / "sovereign_toolchain" / "app.py"


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


def test_app_exposes_the_installer_health_contract() -> None:
    app = APP.read_text("utf-8")
    assert "@app.get(\"/\")" in app
    assert '"ok": True' in app
    assert '"name": "Sovereign Universal Toolchain"' in app
