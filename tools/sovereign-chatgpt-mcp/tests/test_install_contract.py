from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_installer_has_valid_bash_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(ROOT / "deploy" / "install-on-vps.sh")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


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
    assert 'BACKEND_WORKSPACE_HOST_ROOT="/opt/sovereign-agent-workspaces"' in script
    assert 'BACKEND_WORKSPACE_UID="10001"' in script
    assert 'BACKEND_WORKSPACE_GID="10001"' in script
    assert 'install -d -m 0770 -o "$BACKEND_WORKSPACE_UID" -g "$BACKEND_WORKSPACE_GID" "$BACKEND_WORKSPACE_HOST_ROOT"' in script
    assert 'chown "$BACKEND_WORKSPACE_UID:$BACKEND_WORKSPACE_GID" "$BACKEND_WORKSPACE_HOST_ROOT"' in script
    assert 'chmod 0770 "$BACKEND_WORKSPACE_HOST_ROOT"' in script
    assert '[[ -w "$BACKEND_WORKSPACE_HOST_ROOT" && -x "$BACKEND_WORKSPACE_HOST_ROOT" ]]' in script
    assert '.permission-probe' in script


def test_private_broker_admin_mode_is_installed_and_receives_its_switches() -> None:
    script = (ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")
    service = (ROOT / "deploy" / "sovereign-chatgpt-broker.service").read_text("utf-8")
    worker_service = (ROOT / "deploy" / "sovereign-chatgpt-command-worker.service").read_text("utf-8")

    assert 'install -m 0640 "$SOURCE_DIR/admin_mode.py" "$BROKER_DIR/admin_mode.py"' in script
    assert 'install -m 0640 "$SOURCE_DIR/browserless_reader.py" "$BROKER_DIR/browserless_reader.py"' in script
    assert 'install -m 0640 "$SOURCE_DIR/github_admin.py" "$BROKER_DIR/github_admin.py"' in script
    assert "SOVEREIGN_MCP_ENABLE_ADMIN_SQL" in script
    assert "SOVEREIGN_MCP_ENABLE_MAIN_PUSH" in script
    assert "SOVEREIGN_MCP_ENABLE_PR_MERGE" in script
    assert "SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL" in script
    assert "SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE" in script
    assert "SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE" in script
    assert "PATCHMON_MCP_ADMIN_TOKEN_FILE=/opt/patchmon-sovereign/mcp-admin.jwt" in script
    assert "SOVEREIGN_MCP_PRIVATE_OWNER_MODE" in script
    assert 'PRIVATE_OWNER_MODE="1"' in script
    assert 'set_value "$MANAGED_ENV" "$OWNER_CAPABILITY" "1"' in script
    assert 'MANAGED_ENV="$INSTALL_ROOT/runtime.env"' in script
    assert 'BACKEND_MANAGED_ENV="$INSTALL_ROOT/backend-runtime.env"' in script
    assert "SOVEREIGN_MCP_ALLOW_MERGE_WITHOUT_CHECKS" in script
    assert "SOVEREIGN_MCP_ALLOW_DESTRUCTIVE_MIGRATIONS" in script
    assert "SOVEREIGN_MCP_ALLOWED_WORKFLOWS" in script
    assert "e2e-testing.yml" in script
    assert "sovereign-backend-image.yml" in script
    assert "SOVEREIGN_MCP_ALLOWED_CONTAINERS" in script
    assert "gpt-browserless" in script
    assert "sovereign-litellm-litellm-1" in script
    assert "sovereign-litellm-db-1" in script
    assert "code-server-46bq-code-server-1" in script
    assert "pgbackweb-wq5r-pgbackweb-1" in script
    assert "pgbackweb-wq5r-db-1" in script
    assert "patchmon-sovereign-server-1" in script
    assert "patchmon-sovereign-database-1" in script
    assert "patchmon-sovereign-redis-1" in script
    assert "patchmon-sovereign-guacd-1" in script
    assert "sovereign-freellmapi" in script
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
    assert '/opt/sovereign-agent-workspaces' in worker_service
    assert '/opt/sovereign-litellm' in worker_service
    assert '/opt/sovereign-backend' in worker_service
    assert '/opt/gpt-tools' in worker_service
    assert '/opt/code-server-46bq' in worker_service
    assert '/opt/pgbackweb-wq5r' in worker_service
    assert '/opt/patchmon-sovereign' in worker_service
    assert '/opt/milvus-sovereign' in worker_service
    assert '/opt/sovereign-freellmapi' in worker_service
    assert 'install -m 0640 "$SOURCE_DIR/litellm_stack.py" "$BROKER_DIR/litellm_stack.py"' in script
    assert 'install -m 0640 "$SOURCE_DIR/managed_compose.py" "$BROKER_DIR/managed_compose.py"' in script
    assert 'install -m 0640 "$SOURCE_DIR/patchmon_operator.py" "$BROKER_DIR/patchmon_operator.py"' in script
    assert 'templates/sovereign-litellm' in script
    assert 'templates/pgbackweb-wq5r' in script
    assert 'templates/patchmon-sovereign' in script
    assert 'templates/milvus-sovereign' in script
    assert 'templates/sovereign-freellmapi' in script
    assert 'install -m 0640 "$PGBACKWEB_TEMPLATE_SOURCE/docker-compose.yml" "$PGBACKWEB_TEMPLATE_DIR/docker-compose.yml"' in script
    assert 'install -m 0640 "$PATCHMON_TEMPLATE_SOURCE/docker-compose.yml" "$PATCHMON_TEMPLATE_DIR/docker-compose.yml"' in script
    assert 'install -m 0640 "$MILVUS_TEMPLATE_SOURCE/docker-compose.yml" "$MILVUS_TEMPLATE_DIR/docker-compose.yml"' in script
    assert 'install -m 0640 "$FREELLMAPI_TEMPLATE_SOURCE/docker-compose.yml" "$FREELLMAPI_TEMPLATE_DIR/docker-compose.yml"' in script
    assert '"pgbackweb-wq5r"' in script
    assert '"patchmon-sovereign"' in script
    assert '"milvus-sovereign"' in script
    assert '"sovereign-freellmapi"' in script
    assert 'SOVEREIGN_FREELLMAPI_UNIFIED_KEY_FILE' in script
    assert '/opt/secure' in worker_service.split('ReadOnlyPaths=', 1)[1].splitlines()[0]


def test_android_hardening_runtime_uses_lightweight_orchestrator_image() -> None:
    installer = (ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")
    compose = (ROOT / "docker-compose.yml").read_text("utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text("utf-8")
    requirements = (ROOT / "requirements.txt").read_text("utf-8")
    launcher = (ROOT / "launcher.py").read_text("utf-8")

    assert 'android_hardening.py' in installer
    assert 'document_pipeline.py' in installer
    assert 'tool_extensions.py' in installer
    assert 'repository_skill_tools.py' in installer
    assert 'proven_learning_tools.py' in installer
    assert 'skill_supply_chain_tools.py' in installer
    assert 'deterministic_contract.py' in installer
    assert 'deterministic_architecture_tools.py' in installer
    assert 'enterprise_backend_tools.py' in installer
    assert 'openai_project_access_tools.py' in installer
    assert 'operational_governance_tools.py' in installer
    assert 'operational_assurance_tools.py' in installer
    assert 'output_contracts.py' in installer
    assert 'toolchain_composition.py' in installer
    assert 'skills/sovereign-operational-governance/SKILL.md' in installer
    assert '/app/skills/sovereign-operational-governance/SKILL.md' in installer
    assert 'skills/sovereign-operational-assurance/SKILL.md' in installer
    assert '/app/skills/sovereign-operational-assurance/SKILL.md' in installer
    assert 'patchmon_operator.py' in installer
    assert 'launcher.py' in installer
    assert 'ANDROID_SDK_DIR="/opt/android-sdk"' in installer
    assert 'install -d -m 0755 "$ANDROID_SDK_DIR"' in installer
    assert '/opt/android-sdk:/opt/android-sdk:ro' in compose
    assert 'ANDROID_SDK_ROOT: /opt/android-sdk' in compose
    assert 'openjdk-17-jdk-headless' not in dockerfile
    assert 'SOVEREIGN_ANDROID_NATIVE_BUILD_MODE=github_actions' in dockerfile
    assert 'android_hardening.py' in dockerfile
    assert 'document_pipeline.py' in dockerfile
    assert 'patchmon_operator.py' in dockerfile
    assert 'tool_extensions.py' in dockerfile
    assert 'repository_skill_tools.py' in dockerfile
    assert 'proven_learning_tools.py' in dockerfile
    assert 'skill_supply_chain_tools.py' in dockerfile
    assert 'deterministic_contract.py' in dockerfile
    assert 'deterministic_architecture_tools.py' in dockerfile
    assert 'enterprise_backend_tools.py' in dockerfile
    assert 'operational_governance_tools.py' in dockerfile
    assert 'operational_assurance_tools.py' in dockerfile
    assert 'output_contracts.py' in dockerfile
    assert 'toolchain_composition.py' in dockerfile
    assert 'COPY skills /app/skills' in dockerfile
    assert (ROOT / 'skills' / 'sovereign-operational-governance' / 'SKILL.md').is_file()
    assert (ROOT / 'skills' / 'sovereign-operational-assurance' / 'SKILL.md').is_file()
    assert 'PyYAML==6.0.3' in requirements
    assert 'openai_project_access_tools.py' in dockerfile
    assert 'launcher.py' in dockerfile
    assert 'import repository_skill_tools' in launcher
    assert 'import proven_learning_tools' in launcher
    assert 'repository_skill_tools.register(server.mcp, server.runtime, server.database)' in launcher
    assert 'proven_learning_tools.register(server.mcp, server.runtime, server.owner_input)' in launcher
    assert 'import skill_supply_chain_tools' in launcher
    assert 'skill_supply_chain_tools.register(server.mcp, server.runtime)' in launcher
    assert 'import deterministic_architecture_tools' in launcher
    assert 'deterministic_architecture_tools.register(server.mcp, server.runtime)' in launcher
    assert 'import enterprise_backend_tools' in launcher
    assert 'enterprise_backend_tools.register(server.mcp, server.runtime, server.broker)' in launcher
    assert 'import openai_project_access_tools' in launcher
    assert 'openai_project_access_tools.register(server.mcp, server.broker, server.controller_runtime)' in launcher
    assert 'import operational_governance_tools' in launcher
    assert 'operational_governance_tools.register(server.mcp, server.runtime, server.database, server.broker)' in launcher
    assert 'import operational_assurance_tools' in launcher
    assert 'operational_assurance_tools.register(server.mcp, server.runtime, server.database, server.broker)' in launcher
    assert 'import output_contracts' in launcher
    assert 'import toolchain_composition' in launcher
    assert 'toolchain_composition.register(server.mcp)' in launcher
    assert 'output_contracts.install_output_contracts(server.mcp)' in launcher
    assert 'CMD ["python", "launcher.py"]' in dockerfile
    assert 'docker exec sovereign-chatgpt-mcp java -version' not in installer
    assert 'docker compose build' not in installer
    assert 'docker pull "$MCP_TAGGED_IMAGE"' in installer
    assert 'org.opencontainers.image.revision' in installer
    assert 'SOVEREIGN_MCP_EXPECTED_REVISION' in installer
    assert 'set_value "$MANAGED_ENV" SOVEREIGN_MCP_IMAGE "$MCP_IMAGE_DIGEST"' in installer
    assert 'export SOVEREIGN_MCP_IMAGE="$MCP_IMAGE_DIGEST"' in installer
    assert 'resolve_running_mcp_image_digest' in installer
    assert 'PREVIOUS_MCP_IMAGE_DIGEST' in installer
    assert 'INSTALL_STAGE="ensure_recovery_image_digest"' in installer
    assert 'the running MCP container has no immutable GHCR digest' in installer
    assert 'image: ${SOVEREIGN_MCP_IMAGE:' in compose
    assert '/opt/sovereign-chatgpt-tools/runtime.env' in compose
    assert 'build:' not in compose
    assert 'docker compose up -d --no-build --force-recreate --remove-orphans' in installer
    assert 'MCP container did not pass protocol health' in installer
    assert 'mcp_protocol_health.py --url http://127.0.0.1:8090/mcp' in installer
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
    assert 'docker exec -i sovereign-chatgpt-mcp python -' in installer
    assert 'INSTALL_STAGE="verify_broker_socket_visibility"' in installer
    assert 'INSTALL_STAGE="verify_inbound_mutation_boundary"' in installer
    assert 'INSTALL_STAGE="verify_runtime_import_contracts"' in installer
    assert 'callable(repository_skill_tools.repository_knowledge_surface_scan)' in installer
    assert 'callable(repository_skill_tools.repository_release_hunt_manifest)' in installer
    assert 'callable(repository_skill_tools.repository_architecture_snapshot)' in installer
    assert 'callable(repository_skill_tools.repository_architecture_drift_report)' in installer
    assert 'callable(repository_skill_tools.repository_architecture_runtime_drift_evidence)' in installer
    assert 'callable(repository_skill_tools.repository_mirror_diff_report)' in installer
    assert 'callable(repository_skill_tools.repository_endpoint_reference)' in installer
    assert 'callable(skill_supply_chain_tools.skill_supply_chain_inventory)' in installer
    assert 'callable(skill_supply_chain_tools.template_generation_plan)' in installer
    assert 'deterministic_contract.KAPPA_SCALE == 1000000' in installer
    assert 'callable(deterministic_architecture_tools.deterministic_tool_inventory)' in installer
    assert 'callable(deterministic_architecture_tools.deterministic_replay_verify)' in installer
    assert 'callable(deterministic_architecture_tools.deterministic_transformation_plan)' in installer
    assert 'callable(enterprise_backend_tools.backend_engineering_tool_inventory)' in installer
    assert 'callable(enterprise_backend_tools.backend_architecture_assess)' in installer
    assert 'callable(enterprise_backend_tools.backend_stack_select)' in installer
    assert 'callable(enterprise_backend_tools.backend_delivery_plan)' in installer
    assert 'callable(enterprise_backend_tools.backend_api_security_plan)' in installer
    assert 'callable(enterprise_backend_tools.repository_revision_resolve)' in installer
    assert 'callable(openai_project_access_tools.openai_project_access_plan)' in installer
    assert 'callable(openai_project_access_tools.openai_project_access_runtime_evidence)' in installer
    assert 'callable(operational_governance_tools.operational_skill_inventory)' in installer
    assert 'callable(operational_governance_tools.tool_recommend_for_mission)' in installer
    assert 'callable(operational_governance_tools.mcp_registry_snapshot_verify)' in installer
    assert 'callable(operational_governance_tools.evidence_graph_build)' in installer
    assert 'callable(operational_governance_tools.runtime_runbook_generate)' in installer
    assert 'callable(operational_governance_tools.compliance_evidence_export)' in installer
    assert 'callable(operational_assurance_tools.operational_assurance_skill_inventory)' in installer
    assert 'callable(operational_assurance_tools.vps_capacity_resource_pressure_assess)' in installer
    assert 'callable(operational_assurance_tools.runtime_dependency_health_matrix)' in installer
    assert 'callable(operational_assurance_tools.data_integrity_invariant_audit)' in installer
    assert 'callable(operational_assurance_tools.mcp_schema_compatibility_audit)' in installer
    assert 'callable(operational_assurance_tools.secret_literal_triage)' in installer
    assert 'callable(operational_assurance_tools.authentication_chaos_negative_test_assess)' in installer
    assert 'output_contracts.ToolOutputEnvelope is not None' in installer
    assert 'callable(toolchain_composition.mcp_toolchain_compile)' in installer
    assert 'callable(toolchain_composition.mcp_toolchain_validate)' in installer
    assert 'callable(toolchain_composition.mcp_toolchain_next_step)' in installer
    assert 'all(getattr(tool, "output_schema", None)' in installer
    assert 'assurance=operational_assurance_tools.operational_assurance_skill_inventory()' in installer
    assert 'registry=operational_governance_tools.mcp_tool_contract_registry(include_schemas=False)' in installer
    assert '"enterprise_backend_tools":true' in installer
    assert '"operational_governance_tools":true' in installer
    assert '"operational_assurance_tools":true' in installer
    assert '"repository_revision_resolver":true' in installer
    assert '"workspace_pr_head_sync_available":true' in installer
    assert 'callable(server.repository_sync_workspace_to_pr_head)' in installer
    assert 'callable(server.postgres_schema_inventory)' in installer
    assert 'callable(server.controller_run_external_event)' in installer
    assert 'INSTALL_STAGE="verify_host_worker_canary"' in installer
    assert 'INSTALL_STAGE="verify_mcp_protocol_handshake"' in installer
    assert 'INSTALL_STAGE="verify_android_native_boundary"' in installer
    assert 'INSTALL_STAGE="verify_workspace_write_boundary"' in installer
    assert 'sovereign_cognitive_widget.WIDGET_MANIFEST.get("agentCount") == 8' not in installer
    assert '/opt/sovereign-chatgpt-tools/command-queue:/opt/sovereign-chatgpt-tools/command-queue' in compose
    assert 'command_contract.py command_queue.py broker_client.py' in dockerfile
    assert '"running no-health"' not in installer


def test_main_workflow_runs_real_memory_collection_post_install_canary() -> None:
    workflow = (
        ROOT.parents[1] / ".github" / "workflows" / "sovereign-chatgpt-mcp.yml"
    ).read_text("utf-8")

    assert "Verify Memory Gateway to Milvus collection canary" in workflow
    assert "memory_gateway_collection_canary" in workflow
    assert '"MEMORY_COLLECTION_CANARY_VERIFIED"' in workflow
    assert 'print(json.dumps(result, sort_keys=True, separators=(",", ":")))' in workflow
    assert 'result.get("collectionCreated") is True' in workflow
    assert 'result.get("recordInserted") is True' in workflow
    assert 'result.get("queryReadbackVerified") is True' in workflow
    assert 'result.get("vectorSearchVerified") is True' in workflow
    assert 'result.get("collectionDropped") is True' in workflow
    assert 'result.get("responseContentReturned") is False' in workflow
    assert 'result.get("secretValuesReturned") is False' in workflow
    assert 're.fullmatch(r"[0-9a-f]{64}", marker_sha256)' in workflow
    assert 'summary["evidenceSha256"] = hashlib.sha256(canonical).hexdigest()' in workflow


def test_main_workflow_runs_real_gotenberg_to_tika_post_install_canary() -> None:
    workflow = (
        ROOT.parents[1] / ".github" / "workflows" / "sovereign-chatgpt-mcp.yml"
    ).read_text("utf-8")

    assert "Verify Gotenberg to Tika live canary" in workflow
    assert "document_pipeline.py" in workflow
    assert "repository_skill_tools.py" in workflow
    assert "proven_learning_tools.py" in workflow
    assert "skill_supply_chain_tools.py" in workflow
    assert "openai_project_access_tools.py" in workflow
    assert "operational_governance_tools.py" in workflow
    assert "operational_assurance_tools.py" in workflow
    assert "skills/sovereign-operational-governance/SKILL.md" in workflow
    assert "/app/skills/sovereign-operational-governance/SKILL.md" in workflow
    assert "skills/sovereign-operational-assurance/SKILL.md" in workflow
    assert "/app/skills/sovereign-operational-assurance/SKILL.md" in workflow
    assert "runtime_capacity_snapshot" in workflow
    assert "document_pipeline_live_canary" in workflow
    assert "controller_run_external_event" in workflow
    assert 'server.broker.call(' in workflow
    assert '"DOCUMENT_PIPELINE_LIVE_CANARY_VERIFIED"' in workflow
    assert "33 * 1024 * 1024" in workflow
    assert 'result.get("sourcePersisted") is False' in workflow
    assert 'result.get("outputPersisted") is False' in workflow
    assert 'result.get("documentContentReturned") is False' in workflow
    assert 'result.get("secretValuesReturned") is False' in workflow
    assert 'summary["evidenceSha256"] = hashlib.sha256(canonical).hexdigest()' in workflow


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
    assert 'repeated malformed MCP requests detected after tunnel start' in full_installer
    assert 'SOVEREIGN_MCP_REQUIRE_TUNNEL' in full_installer
    assert 'TUNNEL_MODE="${SOVEREIGN_MCP_TUNNEL_MODE:-auto}"' in full_installer
    assert 'INSTALL_STAGE="verify_tunnel_configuration"' in full_installer
    assert 'Tunnel checks skipped for the tunnel-independent MCP profile.' in full_installer
    assert 'the selected MCP profile requires a valid tunnel.env' in full_installer
    assert 'tunnel installer returned without an active service' in full_installer
    assert 'SUCCESSFUL_MCP_REQUESTS' in full_installer
    assert 'MALFORMED_MCP_REQUESTS >= 2 && SUCCESSFUL_MCP_REQUESTS == 0' in full_installer
    assert '/opt/sovereign-chatgpt-tools/tunnel-home' not in installer
    assert '/opt/sovereign-chatgpt-tools/tunnel-home' not in service
