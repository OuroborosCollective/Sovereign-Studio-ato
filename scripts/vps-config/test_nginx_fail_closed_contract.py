from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "scripts/vps-config/nginx/openhands.arelorian.de.conf"
SETUP_PATH = ROOT / "scripts/vps-config/setup-nginx.sh"


FORBIDDEN_LEGACY = (
    "proxy_pass",
    "127.0.0.1:3000",
    "127.0.0.1:8090",
    "mcp_api_key",
    "X-API-Key",
    "location = /mcp",
)


def test_openhands_nginx_config_is_retired_and_fail_closed() -> None:
    config = CONFIG_PATH.read_text(encoding="utf-8")

    assert "server_name openhands.arelorian.de;" in config
    assert config.count("return 410;") == 2
    assert "listen 80;" in config
    assert "listen 443 ssl http2;" in config

    for marker in FORBIDDEN_LEGACY:
        assert marker not in config

    assert re.findall(r"proxy_pass\s+[^;]+;", config) == []


def test_openhands_retirement_installer_is_rollback_safe() -> None:
    setup = SETUP_PATH.read_text(encoding="utf-8")

    assert 'SOURCE_CONFIG="$SCRIPT_DIR/nginx/openhands.arelorian.de.conf"' in setup
    assert 'CONFIG_FILE="/etc/nginx/sites-available/openhands.arelorian.de"' in setup
    assert 'SYM_LINK="/etc/nginx/conf.d/openhands.arelorian.de.conf"' in setup
    assert 'LEGACY_ENABLED_LINK="/etc/nginx/sites-enabled/openhands.arelorian.de"' in setup
    assert 'BACKUP_ROOT="/var/backups/sovereign-nginx/openhands-retirement"' in setup
    assert "backup_path" in setup
    assert "rollback()" in setup
    assert 'install -o root -g root -m 0644 "$SOURCE_CONFIG" "$CONFIG_FILE"' in setup
    assert 'rm -f -- "$LEGACY_ENABLED_LINK" "$SYM_LINK"' in setup
    assert "nginx -t" in setup
    assert "systemctl reload nginx" in setup
    assert "systemctl is-active --quiet nginx" in setup
    assert "OPENHANDS_RUNTIME_RETIRED" in setup
    assert "browserless_proxy_present=false" in setup
    assert "mcp_proxy_present=false" in setup
    assert "credential_include_present=false" in setup

    assert "openhands_mcp_api_key.txt" not in setup
    assert "KEY_FILE=" not in setup
    assert "YOUR_KEY_HERE" not in setup
    assert "forbidden legacy integration surface" in setup


def test_openhands_retirement_installer_has_valid_bash_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(SETUP_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_retirement_files_contain_no_secret_or_bearer_material() -> None:
    config = CONFIG_PATH.read_text(encoding="utf-8")
    setup = SETUP_PATH.read_text(encoding="utf-8")
    joined = config + "\n" + setup

    assert not re.search(
        r"(?:Bearer\s+|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{16,})",
        joined,
    )
