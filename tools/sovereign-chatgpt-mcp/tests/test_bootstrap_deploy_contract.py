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
    assert 'systemctl stop sovereign-openai-tunnel.service' in installer
    assert 'systemctl restart sovereign-openai-tunnel.service' in installer
    assert 'systemctl enable --now sovereign-openai-tunnel.service' not in installer
    assert 'TUNNEL_PROFILE_SAMPLE="sample_mcp_remote_no_auth"' in installer
    assert 'DOCTOR_VALIDATOR="$INSTALL_ROOT/bin/validate-tunnel-doctor-report"' in installer
    assert '--sample "$TUNNEL_PROFILE_SAMPLE"' in installer
    assert '--health.listen-addr 127.0.0.1:0' in installer
    assert '--health-listen-addr "$TUNNEL_HEALTH_LISTEN_ADDR"' in installer
    assert '--json > "$DOCTOR_REPORT"' in installer
    assert '"$DOCTOR_EXIT"' in installer
    assert '"$TUNNEL_PROFILE_SAMPLE"' in installer
    assert 'tunnel doctor contract validation failed' in installer
    assert 'validate-tunnel-doctor-report.py' in full_installer
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
    assert "KAPPA_POS: '1000000'" in workflow
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow
    assert '--sort=name' in workflow
    assert '--mtime="@${COMMIT_EPOCH}"' in workflow
    assert '| gzip -n > sovereign-chatgpt-mcp.tar.gz' in workflow
    assert 'sha256sum --check sovereign-chatgpt-mcp.sha256' in workflow
    assert 'EXPECTED_REVISION: ${{ github.sha }}' in workflow
    assert 'EXPECTED_IMAGE_DIGEST: ${{ needs.publish-mcp-image.outputs.digest }}' in workflow
    assert 'RELEASE_RELATIVE_DIR: .sovereign-releases/sovereign-chatgpt-mcp-${{ github.run_id }}-${{ github.run_attempt }}' in workflow
    assert 'RELEASE_DIR: /tmp/sovereign-chatgpt-mcp-' not in workflow
    assert 'RELEASE_DIR="$HOME/$RELEASE_RELATIVE_DIR"' in workflow
    assert 'target: ${{ env.RELEASE_RELATIVE_DIR }}' in workflow
    assert 'Release directory traversal is forbidden.' in workflow
    assert '/opt/sovereign-chatgpt-mcp/releases/' not in workflow
    assert 'envs: SUDO_PASSWORD' in workflow
    assert 'SOVEREIGN_MCP_EXPECTED_REVISION="$EXPECTED_REVISION"' in workflow
    assert 'SOVEREIGN_MCP_TUNNEL_MODE=disabled' in workflow
    assert 'bash "$SOURCE_DIR/deploy/install-on-vps.sh"' in workflow
    assert 'run_root docker inspect sovereign-chatgpt-mcp' in workflow
    assert 'name: Publish immutable MCP image' in workflow
    assert 'digest: ${{ steps.publish.outputs.digest }}' in workflow
    assert 'packages: write' in workflow
    assert 'docker/build-push-action@v6' in workflow
    assert 'id: publish' in workflow
    assert 'tags: ${{ env.IMAGE_REPOSITORY }}:${{ github.sha }}' in workflow
    assert 'org.opencontainers.image.revision=${{ github.sha }}' in workflow
    assert 'io.ouroboros.sovereign.kappa-pos=${{ env.KAPPA_POS }}' in workflow
    assert 'provenance: true' in workflow
    assert 'sbom: true' in workflow
    assert 'name: Verify published MCP digest' in workflow
    assert 'EXPECTED_IMAGE_DIGEST: ${{ needs.publish-mcp-image.outputs.digest }}' in workflow
    assert 'docker pull "$IMAGE_REFERENCE"' in workflow
    assert 'test "$REVISION_LABEL" = "$GITHUB_SHA"' in workflow
    assert 'test "$KAPPA_LABEL" = "$KAPPA_POS"' in workflow
    assert 'needs: [validate, publish-mcp-image, verify-published-mcp-image]' in workflow
    assert 'test "$CONTAINER_IMAGE_REFERENCE" = "$EXPECTED_IMAGE_REFERENCE"' in workflow
    assert 'test "$INSTALLED_REVISION" = "$EXPECTED_REVISION"' in workflow
    assert 'test "$INSTALLED_KAPPA_POS" = "$KAPPA_POS"' in workflow
    assert 'test "$CONTAINER_REPO_DIGEST" = "$EXPECTED_IMAGE_REFERENCE"' in workflow
    assert 'test -S /run/sovereign-chatgpt-broker/operator.sock' in workflow
    assert 'docker exec sovereign-chatgpt-mcp test -S /run/sovereign-chatgpt-broker/operator.sock' in workflow
    assert 'status=server.broker.status()' in workflow
    assert "canary.get('failure_family') == 'INBOUND_MUTATION_FORBIDDEN'" in workflow
    assert 'COMMAND_WORKER_STATE="$(run_root systemctl is-active sovereign-chatgpt-command-worker.service)"' in workflow
    assert 'BROKER_SERVICE_STATE="$(run_root systemctl is-active sovereign-chatgpt-broker.service)"' in workflow
    assert 'TUNNEL_SERVICE_STATE=not_required' in workflow
    assert 'test "$TUNNEL_SERVICE_STATE" = active' not in workflow
    assert 'test "$(run_root systemctl is-active sovereign-openai-tunnel.service)" = active' not in workflow
    assert "'mcp_protocol_ready': mcp_protocol_state == 'ready'" in workflow
    assert "'broker_rpc_ready': broker_rpc_state == 'ready'" in workflow
    assert "'broker_socket_host_visible': broker_socket_host_state == 'visible'" in workflow
    assert "'broker_socket_container_visible': broker_socket_container_state == 'visible'" in workflow
    assert "'host_command_worker_active': command_worker_state == 'active'" in workflow
    assert "'inbound_mutation_forbidden': inbound_mutation_state == 'forbidden'" in workflow
    assert "'tunnel_mode': 'disabled'" in workflow
    assert "'tunnel_not_required': tunnel_service_state == 'not_required'" in workflow
    assert "payload.get('tunnel_not_required') is True" in workflow
    assert "'ok': all(checks.values())" in workflow
    assert "'evidence_sha256': hashlib.sha256(canonical).hexdigest()" in workflow
    assert 'name: Reverify deployed evidence in fresh SSH session' in workflow
    assert "'fresh_session_runtime_evidence': True" in workflow
    assert "'mcp_protocol_ready': True" not in workflow
    assert "'broker_rpc_ready': True" not in workflow
    assert 'backend_image_resolve' not in workflow
    assert 'resolve_backend_image' not in workflow
    assert "The VPS must not build the MCP image." in workflow
