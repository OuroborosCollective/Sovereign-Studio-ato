from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_installer_assigns_workspace_to_container_user_and_probes_write_access() -> None:
    script = (ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")

    assert 'MCP_UID="10001"' in script
    assert 'MCP_GID="10001"' in script
    assert 'install -d -m 0770 -o "$MCP_UID" -g "$MCP_GID" "$WORKSPACE_DIR"' in script
    assert 'chown -R "$MCP_UID:$MCP_GID" "$WORKSPACE_DIR"' in script
    assert 'OWNER_INPUT_HOST_ROOT="/opt/sovereign-owner-managed"' in script
    assert 'mkdir -p "$OWNER_INPUT_HOST_ROOT"' in script
    assert 'chmod 0700 "$OWNER_INPUT_HOST_ROOT"' in script
    assert '[[ -w "$OWNER_INPUT_HOST_ROOT" && -x "$OWNER_INPUT_HOST_ROOT" ]]' in script
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
    assert "SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE" in script
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
    assert '/opt/sovereign-owner-managed' in worker_service
    assert '/opt/sovereign-litellm' in worker_service
    assert '/opt/sovereign-backend' in worker_service
    assert '/opt/gpt-tools' in worker_service
    assert '/opt/code-server-46bq' in worker_service
    assert 'install -m 0640 "$SOURCE_DIR/litellm_stack.py" "$BROKER_DIR/litellm_stack.py"' in script
    assert 'install -m 0640 "$SOURCE_DIR/managed_compose.py" "$BROKER_DIR/managed_compose.py"' in script
    assert '/opt/secure' in worker_service.split('ReadOnlyPaths=', 1)[1].splitlines()[0]


def test_android_hardening_runtime_and_validation_router_are_installed() -> None:
    installer = (ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")
    compose = (ROOT / "docker-compose.yml").read_text("utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text("utf-8")
    launcher = (ROOT / "launcher.py").read_text("utf-8")

    assert 'android_hardening.py' in installer
    assert 'android_validation_router.py' in installer
    assert 'tool_extensions.py' in installer
    assert 'deterministic_contract.py' in installer
    assert 'deterministic_architecture_tools.py' in installer
    assert 'launcher.py' in installer
    assert 'ANDROID_SDK_DIR="/opt/android-sdk"' in installer
    assert 'install -d -m 0755 "$ANDROID_SDK_DIR"' in installer
    assert '/opt/android-sdk:/opt/android-sdk:ro' in compose
    assert 'ANDROID_SDK_ROOT: /opt/android-sdk' in compose
    assert 'openjdk-17-jdk-headless' not in dockerfile
    assert 'SOVEREIGN_ANDROID_NATIVE_BUILD_MODE=github_actions' in dockerfile
    assert 'android_hardening.py' in dockerfile
    assert 'android_validation_router.py' in dockerfile
    assert 'tool_extensions.py' in dockerfile
    assert 'deterministic_contract.py' in dockerfile
    assert 'deterministic_architecture_tools.py' in dockerfile
    assert 'launcher.py' in dockerfile
    assert 'CMD ["python", "launcher.py"]' in dockerfile
    assert 'android_validation_router.install(server.android, server.runtime, server.broker)' in launcher
    assert 'deterministic_architecture_tools.register(server.mcp, server.runtime)' in launcher
    assert 'deterministic_contract.KAPPA_SCALE == 1000000' in installer
    assert 'callable(deterministic_architecture_tools.deterministic_transition_validate)' in installer
    assert '_native_validation_router_installed' in installer
    assert 'docker compose build' not in installer
    assert 'docker pull "$MCP_TAGGED_IMAGE"' in installer
    assert 'org.opencontainers.image.revision' in installer
    assert 'SOVEREIGN_MCP_EXPECTED_REVISION' in installer
    assert 'set_value "$MANAGED_ENV" SOVEREIGN_MCP_IMAGE "$MCP_IMAGE_DIGEST"' in installer
    assert 'export SOVEREIGN_MCP_IMAGE="$MCP_IMAGE_DIGEST"' in installer
    assert 'image: ${SOVEREIGN_MCP_IMAGE:' in compose
    assert '/opt/sovereign-chatgpt-tools/runtime.env' in compose
    assert 'build:' not in compose
    assert 'broker_rpc_ready()' in installer
    assert 'wait_for_broker_ready()' in installer
    assert '"action": "broker_health"' in installer
    assert 'host broker socket exists but the broker RPC did not become ready' in installer
    assert 'host broker socket disappeared after MCP recreation' in installer
    assert 'broker socket is not visible inside the recreated MCP container' in installer
    assert 'status=server.broker.status()' in installer
    assert '"broker_rpc_ready":true' in installer
    assert '"host_command_worker_active":true' in installer
    assert '"inbound_mutation_forbidden":true' in installer
    assert 'host_worker_canary' in installer
    assert '/opt/sovereign-chatgpt-tools/command-queue:/opt/sovereign-chatgpt-tools/command-queue' in compose
    assert 'command_contract.py command_queue.py broker_client.py' in dockerfile


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
    assert 'SOVEREIGN_MCP_EXPECTED_REVISION="$EXPECTED_REVISION"' in updater
    assert 'SELF_UPDATE_TUNNEL_MODE="${SOVEREIGN_MCP_SELF_UPDATE_TUNNEL_MODE:-disabled}"' in updater
    assert 'SOVEREIGN_MCP_TUNNEL_MODE="$SELF_UPDATE_TUNNEL_MODE"' in updater
    assert 'SOVEREIGN_MCP_REQUIRE_TUNNEL=1' not in updater
    assert 'bash "$INSTALLER"' in updater
    assert 'recover_control_plane()' in updater
    assert 'broker_rpc_ready()' in updater
    assert 'wait_for_broker_ready()' in updater
    assert '"action": "broker_health"' in updater
    assert 'stage=${CURRENT_STAGE}; self-update command failed; recovery attempted' in updater
    assert 'docker exec sovereign-chatgpt-mcp test -S /run/sovereign-chatgpt-broker/operator.sock' in updater
    assert 'status=server.broker.status()' in updater
    assert 'mcp_protocol_health.py --url http://127.0.0.1:8090/mcp' in updater
    assert 'if [[ "$SELF_UPDATE_TUNNEL_MODE" == "required" ]]; then' in updater
    assert 'systemctl is-active --quiet sovereign-openai-tunnel.service' in updater
    assert 'tunnel not required' in updater
    assert 'CURRENT_STAGE="completed"' in updater
    assert "StateDirectory=sovereign-chatgpt-self-update" in service


def test_github_vps_release_directory_uses_portable_bounded_creation() -> None:
    workflow = (ROOT.parents[1] / ".github" / "workflows" / "sovereign-chatgpt-mcp.yml").read_text("utf-8")
    prepare_step = workflow.split("- name: Prepare remote release directory", 1)[1].split("- name: Upload exact MCP release", 1)[0]

    assert "umask 077" in prepare_step
    assert "RELEASE_RELATIVE_DIR='${{ env.RELEASE_RELATIVE_DIR }}'" in prepare_step
    assert 'RELEASE_DIR="$HOME/$RELEASE_RELATIVE_DIR"' in prepare_step
    assert 'Release directory traversal is forbidden.' in prepare_step
    assert 'mkdir -p "$RELEASE_DIR"' in prepare_step
    assert 'chmod 0700 "$RELEASE_DIR"' in prepare_step
    assert 'test -d "$RELEASE_DIR" && test ! -L "$RELEASE_DIR"' in prepare_step
    assert 'test -w "$RELEASE_DIR" && test -x "$RELEASE_DIR"' in prepare_step
    assert 'install -d -m 0700 "$RELEASE_DIR"' not in prepare_step
    assert '/tmp/sovereign-chatgpt-mcp-' not in prepare_step


def test_github_vps_pull_uses_ephemeral_package_read_auth() -> None:
    workflow = (ROOT.parents[1] / ".github" / "workflows" / "sovereign-chatgpt-mcp.yml").read_text("utf-8")
    deploy_job = workflow.split("  deploy-vps:", 1)[1]
    before_install, install_and_after = deploy_job.split("- name: Install and verify private MCP on VPS", 1)
    install_step = install_and_after.split(
        "- name: Reverify deployed evidence in fresh SSH session",
        1,
    )[0]

    assert "permissions:\n      contents: read\n      packages: read" in deploy_job
    assert "GHCR_USERNAME:" not in before_install
    assert "GHCR_TOKEN:" not in before_install
    assert "GHCR_USERNAME: ${{ github.actor }}" in install_step
    assert "GHCR_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in install_step
    assert "envs: SUDO_PASSWORD,GHCR_USERNAME,GHCR_TOKEN" in install_step
    assert 'DOCKER_AUTH_DIR="$RELEASE_DIR/docker-auth"' in install_step
    assert "json.dumps({'auths': {'ghcr.io': {'auth': encoded}}}" in install_step
    assert 'chmod 0600 "$DOCKER_AUTH_DIR/config.json"' in install_step
    assert "unset GHCR_TOKEN" in install_step
    assert 'DOCKER_CONFIG="$DOCKER_AUTH_DIR"' in install_step
    assert 'run_root rm -rf "$RELEASE_DIR"' in install_step
    assert "docker login" not in install_step


def test_github_vps_runtime_canaries_keep_socket_and_host_worker_contracts_separate() -> None:
    workflow = (ROOT.parents[1] / ".github" / "workflows" / "sovereign-chatgpt-mcp.yml").read_text("utf-8")
    installer = (ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")
    install_step = workflow.split("- name: Install and verify private MCP on VPS", 1)[1].split(
        "- name: Reverify deployed evidence in fresh SSH session",
        1,
    )[0]

    assert 'failure_family") == "INBOUND_MUTATION_FORBIDDEN"' in installer
    assert 'worker.get("status") == "HOST_WORKER_READY"' in installer
    assert 'worker.get("execution_origin") == "host_worker"' in installer
    assert "canary.get('status') == 'HOST_WORKER_READY'" in install_step
    assert "canary.get('execution_origin') == 'host_worker'" in install_step
    assert "canary.get('failure_family') == 'INBOUND_MUTATION_FORBIDDEN'" not in install_step


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
    assert 'TUNNEL_PROFILE_SAMPLE="sample_mcp_remote_no_auth"' in installer
    assert 'TUNNEL_HEALTH_LISTEN_ADDR="${TUNNEL_HEALTH_LISTEN_ADDR:-127.0.0.1:9080}"' in installer
    assert 'TUNNEL_HEALTH_PORT <= 65535' in installer
    assert '--sample "$TUNNEL_PROFILE_SAMPLE"' in installer
    assert '--health-listen-addr "$TUNNEL_HEALTH_LISTEN_ADDR"' in installer
    assert 'systemctl stop sovereign-openai-tunnel.service' in installer
    assert '--health.listen-addr 127.0.0.1:0' in installer
    assert 'managed tunnel service did not stop before doctor' in installer
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
    assert 'TUNNEL_MODE="${SOVEREIGN_MCP_TUNNEL_MODE:-auto}"' in full_installer
    assert 'Tunnel checks skipped for the tunnel-independent MCP profile.' in full_installer
    assert 'the selected MCP profile requires a valid tunnel.env' in full_installer
    assert 'repeated malformed MCP requests detected after tunnel start' in full_installer
    assert 'SUCCESSFUL_MCP_REQUESTS' in full_installer
    assert 'MALFORMED_MCP_REQUESTS >= 2 && SUCCESSFUL_MCP_REQUESTS == 0' in full_installer
    assert '/opt/sovereign-chatgpt-tools/tunnel-home' not in installer
    assert '/opt/sovereign-chatgpt-tools/tunnel-home' not in service
