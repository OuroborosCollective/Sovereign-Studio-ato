from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "scripts/vps-config/nginx/openhands.arelorian.de.conf"
SETUP_PATH = ROOT / "scripts/vps-config/setup-nginx.sh"


def _embedded_nginx_config(setup_script: str) -> str:
    match = re.search(
        r"cat > \"\$CONFIG_FILE\" << 'NGINXCONF'(.+?)NGINXCONF",
        setup_script,
        re.DOTALL,
    )
    assert match, "Could not find NGINXCONF heredoc in setup script"
    return match.group(1).strip()


def test_committed_and_generated_nginx_servers_are_identical() -> None:
    """Verify committed config and embedded config in setup script match."""
    committed = CONFIG_PATH.read_text(encoding="utf-8")
    generated = _embedded_nginx_config(SETUP_PATH.read_text(encoding="utf-8"))
    committed_servers = committed[committed.index("server {") :].strip()

    assert generated == committed_servers


def test_mcp_route_requires_api_key() -> None:
    """Verify /mcp requires X-API-Key authentication."""
    config = CONFIG_PATH.read_text(encoding="utf-8")

    # Must have exact-match /mcp location
    assert "location = /mcp {" in config
    # Must check X-API-Key header
    assert '$http_x_api_key' in config
    assert 'return 401;' in config
    # Must include owner-managed key file
    assert "include /opt/sovereign-owner-managed/openhands_mcp_api_key.txt" in config


def test_mcp_route_proxies_to_port_8090() -> None:
    """Verify /mcp proxies to 127.0.0.1:8090 (MCP, not Browserless)."""
    config = CONFIG_PATH.read_text(encoding="utf-8")

    assert "proxy_pass http://127.0.0.1:8090/mcp" in config


def test_root_route_proxies_to_port_3000() -> None:
    """Verify root / proxies to 127.0.0.1:3000 (existing local service)."""
    config = CONFIG_PATH.read_text(encoding="utf-8")

    assert "location / {" in config
    assert "proxy_pass http://127.0.0.1:3000;" in config


def test_key_file_verification_in_setup_script() -> None:
    """Verify setup script checks for owner-managed API key file."""
    setup = SETUP_PATH.read_text(encoding="utf-8")

    assert "/opt/sovereign-owner-managed/openhands_mcp_api_key.txt" in setup
    assert 'chmod 0600' in setup
    assert 'KEY_FILE="/opt/sovereign-owner-managed/openhands_mcp_api_key.txt"' in setup


def test_setup_script_validates_permissions() -> None:
    """Verify setup script checks key file has 0600 permissions."""
    setup = SETUP_PATH.read_text(encoding="utf-8")

    assert 'KEY_PERMS=$(stat' in setup
    assert '"600"' in setup


def test_no_hardcoded_api_keys() -> None:
    """Verify no actual API keys are committed to the repository."""
    config = CONFIG_PATH.read_text(encoding="utf-8")
    setup = SETUP_PATH.read_text(encoding="utf-8")

    # The config should set variable to empty string as default
    assert 'set $mcp_api_key "";' in config
    # Should NOT have any actual key values
    assert "sk-" not in config and "sk-" not in setup
    assert "api_key" not in config.lower() or "mcp_api_key" in config.lower()
