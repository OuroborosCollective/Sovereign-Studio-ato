from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "scripts/vps-config/nginx/openhands.arelorian.de.conf"
SETUP_PATH = ROOT / "scripts/vps-config/setup-nginx.sh"


def _config() -> str:
    return CONFIG_PATH.read_text(encoding="utf-8")


def _setup() -> str:
    return SETUP_PATH.read_text(encoding="utf-8")


def test_installer_uses_the_committed_nginx_config_as_its_only_source() -> None:
    setup = _setup()

    assert 'SOURCE_CONFIG="$SCRIPT_DIR/nginx/openhands.arelorian.de.conf"' in setup
    assert 'install -m 0644 "$SOURCE_CONFIG" "$CONFIG_FILE"' in setup
    assert "NGINXCONF" not in setup
    assert "cat > \"$CONFIG_FILE\"" not in setup


def test_mcp_route_requires_the_owner_managed_api_key() -> None:
    config = _config()

    assert "location = /mcp {" in config
    assert "$http_x_api_key != $mcp_api_key" in config
    assert "return 401;" in config
    assert "include /opt/sovereign-owner-managed/openhands_mcp_api_key.txt;" in config


def test_mcp_route_has_one_loopback_streamable_http_upstream() -> None:
    config = _config()

    assert config.count("proxy_pass http://127.0.0.1:8090/mcp;") == 1
    assert "/sse" not in config
    assert "/messages" not in config


def test_mcp_subpaths_do_not_fall_through_to_the_root_service() -> None:
    config = _config()

    assert "location ^~ /mcp/ {\n        return 404;\n    }" in config
    assert config.index("location = /mcp {") < config.index("location ^~ /mcp/")
    assert config.index("location ^~ /mcp/") < config.index("location / {")


def test_root_route_remains_bound_to_the_existing_service() -> None:
    config = _config()

    assert "location / {" in config
    assert "proxy_pass http://127.0.0.1:3000;" in config


def test_installer_requires_a_regular_root_owned_mode_600_key_file() -> None:
    setup = _setup()

    assert 'KEY_FILE="/opt/sovereign-owner-managed/openhands_mcp_api_key.txt"' in setup
    assert '[ ! -L "$KEY_FILE" ]' in setup
    assert 'stat -c "%a" "$KEY_FILE"' in setup
    assert 'stat -c "%u:%g" "$KEY_FILE"' in setup
    assert '[ "$KEY_PERMS" = "600" ]' in setup
    assert '[ "$KEY_OWNER" = "0:0" ]' in setup


def test_installer_stages_the_canonical_config_and_rolls_back_on_all_nginx_failures() -> None:
    setup = _setup()

    assert "BACKUP_FILE=" in setup
    assert "rollback()" in setup
    assert 'install -m 0600 "$CONFIG_FILE" "$BACKUP_FILE"' in setup
    assert "if ! nginx -t; then" in setup
    assert "if ! systemctl reload nginx; then" in setup
    assert "if ! systemctl is-active --quiet nginx; then" in setup
    assert setup.count("rollback") >= 4
    assert "pkill -HUP nginx" not in setup


def test_installer_has_valid_bash_syntax() -> None:
    subprocess.run(["bash", "-n", str(SETUP_PATH)], check=True)


def test_no_secret_shaped_literal_is_tracked_in_the_contract() -> None:
    text = _config() + "\n" + _setup()

    assert "<secret" not in text.lower()
    assert not re.search(r"\b(?:sk|pk)_[A-Za-z0-9_-]+", text)
