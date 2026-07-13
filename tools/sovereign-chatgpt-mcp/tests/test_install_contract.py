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


def test_private_broker_admin_mode_is_installed_and_receives_its_switches() -> None:
    script = (ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")
    service = (ROOT / "deploy" / "sovereign-chatgpt-broker.service").read_text("utf-8")
    worker_service = (ROOT / "deploy" / "sovereign-chatgpt-command-worker.service").read_text("utf-8")

    assert 'install -m 0640 "$SOURCE_DIR/admin_mode.py" "$BROKER_DIR/admin_mode.py"' in script
    assert 'install -m 0640 "$SOURCE_DIR/github_admin.py" "$BROKER_DIR/github_admin.py"' in script
    assert "SOVEREIGN_MCP_ENABLE_ADMIN_SQL" in script
    assert "SOVEREIGN_MCP_ENABLE_MAIN_PUSH" in script
    assert "SOVEREIGN_MCP_ENABLE_PR_MERGE" in script
    assert "SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL" in script
    assert "SOVEREIGN_MCP_ALLOWED_WORKFLOWS" in script
    assert "GITHUB_TOKEN" in script
    assert "ReadWritePaths=/run/sovereign-chatgpt-broker /opt/sovereign-chatgpt-tools/workspaces" in service
    assert "RuntimeDirectoryPreserve=yes" in service
    assert 'install -m 0640 "$SOURCE_DIR/command_worker.py" "$BROKER_DIR/command_worker.py"' in script
    assert 'install -m 0644 "$SOURCE_DIR/deploy/sovereign-chatgpt-command-worker.service"' in script
    assert 'systemctl enable --now sovereign-chatgpt-command-worker.service' in script
    assert 'SOVEREIGN_MCP_COMMAND_QUEUE=' in script
    assert 'ExecStart=/usr/bin/python3 /opt/sovereign-chatgpt-tools/broker/command_worker.py' in worker_service
    assert 'ReadWritePaths=/opt/sovereign-chatgpt-tools/command-queue' in worker_service


def test_android_hardening_runtime_uses_lightweight_orchestrator_image() -> None:
    installer = (ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")
    compose = (ROOT / "docker-compose.yml").read_text("utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text("utf-8")

    assert 'android_hardening.py' in installer
    assert 'tool_extensions.py' in installer
    assert 'launcher.py' in installer
    assert 'ANDROID_SDK_DIR="/opt/android-sdk"' in installer
    assert 'install -d -m 0755 "$ANDROID_SDK_DIR"' in installer
    assert '/opt/android-sdk:/opt/android-sdk:ro' in compose
    assert 'ANDROID_SDK_ROOT: /opt/android-sdk' in compose
    assert 'openjdk-17-jdk-headless' not in dockerfile
    assert 'SOVEREIGN_ANDROID_NATIVE_BUILD_MODE=github_actions' in dockerfile
    assert 'android_hardening.py' in dockerfile
    assert 'tool_extensions.py' in dockerfile
    assert 'launcher.py' in dockerfile
    assert 'CMD ["python", "launcher.py"]' in dockerfile
    assert 'docker exec sovereign-chatgpt-mcp java -version' not in installer
    assert 'docker compose build' not in installer
    assert 'docker pull "$MCP_TAGGED_IMAGE"' in installer
    assert 'org.opencontainers.image.revision' in installer
    assert 'SOVEREIGN_MCP_EXPECTED_REVISION' in installer
    assert "grep -q '^SOVEREIGN_MCP_IMAGE=' \"$ENV_FILE\"" in installer
    assert 'SOVEREIGN_MCP_IMAGE=$MCP_IMAGE_DIGEST' in installer
    assert 'image: ${SOVEREIGN_MCP_IMAGE:' in compose
    assert 'build:' not in compose
    assert 'docker compose up -d --no-build --force-recreate --remove-orphans' in installer
    assert 'MCP container did not pass protocol health' in installer
    assert 'mcp_protocol_health.py --url http://127.0.0.1:8090/mcp' in installer
    assert 'host broker socket disappeared after MCP recreation' in installer
    assert 'broker socket is not visible inside the recreated MCP container' in installer
    assert 'status=server.broker.status()' in installer
    assert '"broker_rpc_ready":true' in installer
    assert '"host_command_worker_active":true' in installer
    assert '"inbound_mutation_forbidden":true' in installer
    assert 'host_worker_canary' in installer
    assert '/opt/sovereign-chatgpt-tools/command-queue:/opt/sovereign-chatgpt-tools/command-queue' in compose
    assert 'command_contract.py command_queue.py broker_client.py' in dockerfile
    assert '"running no-health"' not in installer


def test_private_mcp_self_update_is_installed_and_bound_to_exact_revision() -> None:
    installer = (ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")
    updater = (ROOT / "deploy" / "self-update-chatgpt-mcp.sh").read_text("utf-8")
    service = (ROOT / "deploy" / "sovereign-chatgpt-mcp-self-update.service").read_text("utf-8")

    assert 'install -m 0640 "$SOURCE_DIR/self_update.py" "$BROKER_DIR/self_update.py"' in installer
    assert 'install -m 0750 "$SOURCE_DIR/deploy/self-update-chatgpt-mcp.sh"' in installer
    assert "SOVEREIGN_MCP_ENABLE_SELF_UPDATE" in installer
    assert 'git rev-parse origin/main' in updater
    assert '[[ "$ACTUAL_REVISION" == "$EXPECTED_REVISION" ]]' in updater
    assert 'git reset --hard "$EXPECTED_REVISION"' in updater
    assert 'SOVEREIGN_MCP_EXPECTED_REVISION="$EXPECTED_REVISION" bash "$INSTALLER"' in updater
    assert 'recover_control_plane()' in updater
    assert 'stage=${CURRENT_STAGE}; self-update command failed; recovery attempted' in updater
    assert 'docker exec sovereign-chatgpt-mcp test -S /run/sovereign-chatgpt-broker/operator.sock' in updater
    assert 'status=server.broker.status()' in updater
    assert 'mcp_protocol_health.py --url http://127.0.0.1:8090/mcp' in updater
    assert 'systemctl is-active --quiet sovereign-openai-tunnel.service' in updater
    assert 'CURRENT_STAGE="completed"' in updater
    assert "StateDirectory=sovereign-chatgpt-self-update" in service


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
    assert 'TUNNEL_SERVICE="/etc/systemd/system/sovereign-openai-tunnel.service"' in installer
    assert 'for command in python3 runuser systemctl sha256sum; do' in installer
    assert 'for command in curl ' not in installer
    assert 'installed tunnel service still contains a curl-based MCP probe' in installer
    assert 'systemctl reset-failed sovereign-openai-tunnel.service' in installer
    assert 'TUNNEL_STATE="$(systemctl is-active sovereign-openai-tunnel.service' in installer
    assert 'WorkingDirectory=/var/lib/sovereign-tunnel' in service
    assert 'StateDirectory=sovereign-tunnel' in service
    assert 'ReadWritePaths=/var/lib/sovereign-tunnel' in service
    assert 'mcp_protocol_health.py --url http://127.0.0.1:8090/mcp' in service
    assert 'Restart=on-failure' in service
    assert 'StartLimitIntervalSec=60' in service
    assert 'StartLimitBurst=3' in service
    assert 'curl ' not in service
    full_installer = (ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")
    assert 'repeated malformed MCP requests detected after tunnel start' in full_installer
    assert 'SUCCESSFUL_MCP_REQUESTS' in full_installer
    assert 'MALFORMED_MCP_REQUESTS >= 2 && SUCCESSFUL_MCP_REQUESTS == 0' in full_installer
    assert '/opt/sovereign-chatgpt-tools/tunnel-home' not in installer
    assert '/opt/sovereign-chatgpt-tools/tunnel-home' not in service
