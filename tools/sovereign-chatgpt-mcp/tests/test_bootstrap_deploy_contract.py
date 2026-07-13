from __future__ import annotations

from pathlib import Path
import subprocess


MCP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MCP_ROOT.parents[1]


def test_changed_recovery_shell_assets_parse() -> None:
    for relative in (
        "deploy/deploy-sovereign-backend",
        "deploy/rollback-sovereign-backend",
        "deploy/install-on-vps.sh",
        "deploy/install-secure-tunnel.sh",
        "deploy/self-update-chatgpt-mcp.sh",
    ):
        path = MCP_ROOT / relative
        result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True, check=False)
        assert result.returncode == 0, f"{relative}: {result.stderr}"


def test_operator_deployment_path_has_no_curl_dependency() -> None:
    for relative in (
        "deploy/deploy-sovereign-backend",
        "deploy/rollback-sovereign-backend",
        "deploy/install-secure-tunnel.sh",
        "deploy/sovereign-openai-tunnel.service",
    ):
        content = (MCP_ROOT / relative).read_text("utf-8")
        assert "curl " not in content, relative
    assert "urllib.request.urlopen" in (MCP_ROOT / "deploy" / "deploy-sovereign-backend").read_text("utf-8")
    assert "urllib.request.urlopen" in (MCP_ROOT / "deploy" / "rollback-sovereign-backend").read_text("utf-8")


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
    full_installer = (MCP_ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")
    service = (MCP_ROOT / "deploy" / "sovereign-openai-tunnel.service").read_text("utf-8")

    assert 'systemctl enable sovereign-openai-tunnel.service' in installer
    assert 'systemctl reset-failed sovereign-openai-tunnel.service' in installer
    assert 'systemctl restart sovereign-openai-tunnel.service' in installer
    assert 'systemctl enable --now sovereign-openai-tunnel.service' not in installer
    assert 'Restart=on-failure' in service
    assert 'StartLimitIntervalSec=60' in service
    assert 'StartLimitBurst=3' in service
    assert 'repeated malformed MCP requests detected after tunnel start' in full_installer
    assert 'SUCCESSFUL_MCP_REQUESTS' in full_installer
    assert 'MALFORMED_MCP_REQUESTS >= 2 && SUCCESSFUL_MCP_REQUESTS == 0' in full_installer


def test_github_actions_builds_image_before_vps_bootstrap() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "sovereign-chatgpt-mcp.yml").read_text("utf-8")

    assert 'name: Bootstrap MCP on VPS' in workflow
    assert "if: (github.event_name == 'push' || github.event_name == 'workflow_dispatch') && github.ref == 'refs/heads/main'" in workflow
    assert 'tar -czf sovereign-chatgpt-mcp.tar.gz tools/sovereign-chatgpt-mcp' in workflow
    assert 'EXPECTED_REVISION: ${{ github.sha }}' in workflow
    assert 'RELEASE_DIR: /tmp/sovereign-chatgpt-mcp-${{ github.run_id }}-${{ github.run_attempt }}' in workflow
    assert '/opt/sovereign-chatgpt-mcp/releases/' not in workflow
    assert 'envs: SUDO_PASSWORD' in workflow
    assert 'run_root env SOVEREIGN_MCP_EXPECTED_REVISION="$EXPECTED_REVISION" bash "$SOURCE_DIR/deploy/install-on-vps.sh"' in workflow
    assert 'run_root docker inspect sovereign-chatgpt-mcp' in workflow
    assert 'run_root systemctl is-active --quiet sovereign-chatgpt-broker.service' in workflow
    assert 'name: Publish immutable MCP image' in workflow
    assert 'packages: write' in workflow
    assert 'docker/build-push-action@v6' in workflow
    assert 'ghcr.io/ouroboroscollective/sovereign-chatgpt-mcp:${{ github.sha }}' in workflow
    assert 'org.opencontainers.image.revision=${{ github.sha }}' in workflow
    assert 'needs: [validate, publish-mcp-image]' in workflow
    assert 'SOVEREIGN_MCP_EXPECTED_REVISION="$EXPECTED_REVISION" bash "$SOURCE_DIR/deploy/install-on-vps.sh"' in workflow
    assert 'mcp_protocol_ready' in workflow
    assert 'systemctl is-active --quiet sovereign-chatgpt-broker.service' in workflow
    assert 'test -S /run/sovereign-chatgpt-broker/operator.sock' in workflow
    assert 'docker exec sovereign-chatgpt-mcp test -S /run/sovereign-chatgpt-broker/operator.sock' in workflow
    assert 'status=server.broker.status()' in workflow
    assert 'systemctl is-active --quiet sovereign-chatgpt-command-worker.service' in workflow
    assert 'command_contract.py command_queue.py command_worker.py' in workflow
    assert 'sovereign-chatgpt-command-worker.service' in workflow
    assert "'broker_rpc_ready': True" in workflow
    assert "'broker_socket_host_visible': True" in workflow
    assert "'broker_socket_container_visible': True" in workflow
    assert "'host_command_worker_active': True" in workflow
    assert "'inbound_mutation_forbidden': True" in workflow
    assert 'systemctl is-active --quiet sovereign-openai-tunnel.service' in workflow
    assert 'backend_image_resolve' not in workflow
    assert 'resolve_backend_image' not in workflow
    assert "The VPS must not build the MCP image." in workflow
