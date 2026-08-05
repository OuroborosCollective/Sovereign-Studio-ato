"""Contract tests for openhands.arelorian.de nginx configuration.

Issue: #1187 - codify authenticated OpenHands MCP reverse-proxy contract

These tests verify:
1. Committed and generated nginx configs are identical
2. /mcp route requires X-API-Key header (fail-closed without it)
3. /mcp proxies to 127.0.0.1:8090 (MCP, not Browserless)
4. Root / proxies to 127.0.0.1:3000 (unchanged)
5. All other /mcp/* paths return 403 (fail-closed)
6. API key file validation is performed
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "scripts/vps-config/nginx/openhands.arelorian.de.conf"
SETUP_PATH = ROOT / "scripts/vps-config/setup-nginx.sh"


def _embedded_nginx_config(setup_script: str) -> str:
    """Extract the nginx config from the setup script's heredoc."""
    start_marker = 'cat > "$CONFIG_FILE" << \'NGINXCONF\'\n'
    end_marker = "\nNGINXCONF\n"
    assert setup_script.count(start_marker) == 1, "Expected exactly one NGINXCONF heredoc"
    start = setup_script.index(start_marker) + len(start_marker)
    end = setup_script.index(end_marker, start)
    return setup_script[start:end].strip()


def _committed_nginx_servers(config: str) -> str:
    """Extract server blocks from the committed config."""
    return config[config.index("server {") :].strip()


class TestCommittedAndGeneratedParity:
    """Verify committed and generated configs are identical."""

    def test_configs_match(self) -> None:
        committed = CONFIG_PATH.read_text(encoding="utf-8")
        generated = _embedded_nginx_config(SETUP_PATH.read_text(encoding="utf-8"))
        committed_servers = _committed_nginx_servers(committed)
        assert generated == committed_servers, (
            "Committed config and generated config differ. "
            "Update setup-nginx.sh to match nginx/openhands.arelorian.de.conf"
        )


class TestAuthenticatedMCPProxy:
    """Verify /mcp authenticated proxy contract."""

    def test_mcp_route_exists_with_api_key_block(self) -> None:
        config = CONFIG_PATH.read_text(encoding="utf-8")
        assert 'location = /mcp' in config
        # Fail-closed: X-API-Key header must be present
        assert 'if ($http_x_api_key = "")' in config
        assert "return 403;" in config

    def test_mcp_proxies_to_localhost_8090(self) -> None:
        config = CONFIG_PATH.read_text(encoding="utf-8")
        # MCP runs on loopback at port 8090
        assert "127.0.0.1:8090" in config
        assert "proxy_pass http://127.0.0.1:8090/mcp" in config

    def test_mcp_passes_api_key_header(self) -> None:
        config = CONFIG_PATH.read_text(encoding="utf-8")
        # Nginx passes X-API-Key to MCP for owner-managed validation
        assert 'proxy_set_header X-API-Key $http_x_api_key;' in config

    def test_no_api_key_value_in_repository(self) -> None:
        config = CONFIG_PATH.read_text(encoding="utf-8")
        # API key comes from owner-managed file, not committed here
        # X-API-Key header references are allowed (they're header names in nginx config)
        # but actual secret values (sk-, <secret-hidden>, etc.) are not
        assert "<secret" not in config.lower()
        assert "sk-" not in config
        # The config references the header but not a secret value
        assert "$http_x_api_key" in config  # References header variable, not hardcoded value


class TestRootRouteUnchanged:
    """Verify root / route serves existing service at port 3000."""

    def test_root_proxies_to_port_3000(self) -> None:
        config = CONFIG_PATH.read_text(encoding="utf-8")
        # Root route serves existing local service at port 3000 (unchanged)
        assert "location / {" in config
        assert "proxy_pass http://127.0.0.1:3000" in config


class TestFailClosedPaths:
    """Verify fail-closed behavior for unauthorized paths."""

    def test_mcp_subpaths_return_403(self) -> None:
        config = CONFIG_PATH.read_text(encoding="utf-8")
        # Deny all other MCP-related paths
        assert 'location ~ ^/mcp/' in config
        assert "return 403;" in config

    def test_no_sockets_location(self) -> None:
        config = CONFIG_PATH.read_text(encoding="utf-8")
        # No /sockets location (legacy OpenHands assumption not adopted)
        assert "location /sockets" not in config


class TestSetupScript:
    """Verify setup script requirements."""

    def test_checks_api_key_file_exists(self) -> None:
        setup = SETUP_PATH.read_text(encoding="utf-8")
        # Must verify owner-managed API key file
        assert "API_KEY_FILE" in setup
        assert 'if [ ! -f "$API_KEY_FILE" ]' in setup

    def test_checks_api_key_file_permissions(self) -> None:
        setup = SETUP_PATH.read_text(encoding="utf-8")
        # Should warn on wrong permissions
        assert "chmod 600" in setup

    def test_tests_nginx_config(self) -> None:
        setup = SETUP_PATH.read_text(encoding="utf-8")
        # Must validate config before reload
        assert "nginx -t" in setup

    def test_no_secret_value_committed(self) -> None:
        setup = SETUP_PATH.read_text(encoding="utf-8")
        # Setup script should not contain actual secret values
        assert "<secret" not in setup.lower()
        assert "sk-" not in setup
        # The API key file path is fine, but not the value
