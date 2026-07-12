from __future__ import annotations

from pathlib import Path


MCP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MCP_ROOT.parents[1]


def test_installer_releases_only_the_known_mcp_port_and_never_blind_kills() -> None:
    installer = (MCP_ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")

    assert 'MCP_HOST_PORT="8090"' in installer
    assert 'systemctl stop sovereign-openai-tunnel.service' in installer
    assert 'docker rm -f sovereign-chatgpt-mcp' in installer
    assert 'port_listener_evidence' in installer
    assert 'host port $MCP_HOST_PORT remains occupied after controlled MCP shutdown' in installer
    assert 'refusing to kill an unknown process' in installer
    assert 'kill -9' not in installer
    assert 'fuser -k' not in installer
    assert 'MCP_HOST_PORT="8788"' not in installer


def test_tunnel_is_restarted_after_the_new_mcp_passes_protocol_health() -> None:
    installer = (MCP_ROOT / "deploy" / "install-secure-tunnel.sh").read_text("utf-8")

    assert 'systemctl enable sovereign-openai-tunnel.service' in installer
    assert 'systemctl restart sovereign-openai-tunnel.service' in installer
    assert 'systemctl enable --now sovereign-openai-tunnel.service' not in installer


def test_github_actions_can_bootstrap_the_mcp_without_backend_image_resolution() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "sovereign-chatgpt-mcp.yml").read_text("utf-8")

    assert 'name: Bootstrap MCP on VPS' in workflow
    assert "if: github.event_name == 'push' && github.ref == 'refs/heads/main'" in workflow
    assert 'tar -czf sovereign-chatgpt-mcp.tar.gz tools/sovereign-chatgpt-mcp' in workflow
    assert 'EXPECTED_REVISION: ${{ github.sha }}' in workflow
    assert 'bash "$SOURCE_DIR/deploy/install-on-vps.sh"' in workflow
    assert 'mcp_protocol_ready' in workflow
    assert 'systemctl is-active --quiet sovereign-chatgpt-broker.service' in workflow
    assert 'systemctl is-active --quiet sovereign-openai-tunnel.service' in workflow
    assert 'backend_image_resolve' not in workflow
    assert 'resolve_backend_image' not in workflow
    assert 'docker pull' not in workflow
