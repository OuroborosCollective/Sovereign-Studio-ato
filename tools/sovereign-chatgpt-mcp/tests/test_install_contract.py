from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_installer_assigns_workspace_to_container_user_and_probes_write_access() -> None:
    script = (ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")

    assert 'MCP_UID="10001"' in script
    assert 'MCP_GID="10001"' in script
    assert 'install -d -m 0770 -o "$MCP_UID" -g "$MCP_GID" "$WORKSPACE_DIR"' in script
    assert 'chown -R "$MCP_UID:$MCP_GID" "$WORKSPACE_DIR"' in script
    assert '.permission-probe' in script


def test_database_bootstrap_uses_real_binaries_and_authentication_canaries() -> None:
    script = (ROOT / "deploy" / "bootstrap-database.sh").read_text("utf-8")

    assert 'docker exec "$BACKEND_CONTAINER" "$PSQL_BIN" --version' in script
    assert 'docker exec "$BACKEND_CONTAINER" "$CREATEDB_BIN" --version' in script
    assert 'command -v psql' not in script
    assert 'production reader authentication canary failed' in script
    assert 'preview database authentication or DDL canary failed' in script
    assert 'reader_canary":true' in script
    assert 'preview_canary":true' in script


def test_tunnel_state_is_outside_root_only_install_directory() -> None:
    installer = (ROOT / "deploy" / "install-secure-tunnel.sh").read_text("utf-8")
    service = (ROOT / "deploy" / "sovereign-openai-tunnel.service").read_text("utf-8")

    assert 'TUNNEL_HOME="/var/lib/sovereign-tunnel"' in installer
    assert 'WorkingDirectory=/var/lib/sovereign-tunnel' in service
    assert 'StateDirectory=sovereign-tunnel' in service
    assert 'ReadWritePaths=/var/lib/sovereign-tunnel' in service
    assert '/opt/sovereign-chatgpt-tools/tunnel-home' not in installer
    assert '/opt/sovereign-chatgpt-tools/tunnel-home' not in service
