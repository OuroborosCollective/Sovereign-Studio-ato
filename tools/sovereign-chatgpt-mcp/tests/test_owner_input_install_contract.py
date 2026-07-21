from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]


def test_mcp_image_installer_and_workflow_include_owner_client() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text("utf-8")
    installer = (ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "sovereign-chatgpt-mcp.yml").read_text("utf-8")

    assert "owner_input_client.py" in dockerfile
    assert "owner_input_client.py" in installer
    assert "owner_input_client.py" in workflow
    assert "proven_learning_tools.py" in dockerfile
    assert "proven_learning_tools.py" in installer
    assert "proven_learning_tools.py" in workflow
    assert "a2a_runtime_client.py" in dockerfile
    assert "a2a_runtime_client.py" in installer
    assert "owner_input_widget.py" in dockerfile
    assert "owner_input_widget.py" in installer
    assert "owner_input_widget.py" in workflow
    assert "owner_approval_request_create" in workflow
    assert "owner_approval_request_status" in workflow
    assert "owner_approval_widget_open" in workflow
    assert "controller_run_start" in workflow
    assert "controller_run_list" in workflow
    assert "controller_run_status" in workflow
    assert "controller_run_resume" in workflow
    assert "a2a_live_canary" in workflow


def test_workflow_secret_scan_never_echoes_matching_lines() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "sovereign-chatgpt-mcp.yml").read_text("utf-8")

    assert "git grep -IlE" in workflow
    assert "grep -RInE" not in workflow
    assert "-- . ':!.env.example' ':!.tunnel.env.example'" in workflow


def test_installer_generates_one_bridge_key_and_never_prints_it() -> None:
    installer = (ROOT / "deploy" / "install-on-vps.sh").read_text("utf-8")

    assert 'OWNER_REQUEST_KEY="$(openssl rand -hex 32)"' in installer
    assert 'set_value "$MANAGED_ENV" SOVEREIGN_OWNER_REQUEST_KEY "$OWNER_REQUEST_KEY"' in installer
    assert 'set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_REQUEST_KEY "$OWNER_REQUEST_KEY"' in installer
    assert 'set_value "$MANAGED_ENV" SOVEREIGN_BACKEND_INTERNAL_URL "http://sovereign-backend:8787"' in installer
    assert 'set_value "$MANAGED_ENV" SOVEREIGN_BACKEND_MANAGED_ENV_FILE "$BACKEND_MANAGED_ENV"' in installer
    assert 'OWNER_REFERENCE_ID="26487"' in installer
    assert 'OWNER_ADMIN_EMAIL="rastamanweeste@gmail.com"' in installer
    assert "SOVEREIGN_OWNER_REFERENCE_ID" in installer
    assert "SOVEREIGN_OWNER_ADMIN_ID" in installer
    assert "SOVEREIGN_OWNER_ADMIN_EMAIL" in installer
    assert "configure a valid SOVEREIGN_OWNER_ADMIN_ID or SOVEREIGN_OWNER_ADMIN_EMAIL" in installer
    assert "unset OWNER_REQUEST_KEY OWNER_REFERENCE_ID OWNER_ADMIN_ID OWNER_ADMIN_EMAIL" in installer
    assert "echo $OWNER_REQUEST_KEY" not in installer
    assert "printf '%s' \"$OWNER_REQUEST_KEY\"" not in installer
    assert 'set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_REFERENCE_ID "$OWNER_REFERENCE_ID"' in installer
    assert 'set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_ADMIN_EMAIL "$OWNER_ADMIN_EMAIL"' in installer
    assert 'set_value "$BACKEND_MANAGED_ENV" SOVEREIGN_OWNER_INPUT_ROOT "/opt/sovereign-owner-managed"' in installer
    assert '/opt/secure/owner-managed' not in installer


def test_backend_deploy_mounts_only_owner_managed_subdirectory_writable() -> None:
    deploy = (ROOT / "deploy" / "deploy-sovereign-backend").read_text("utf-8")

    assert 'OWNER_INPUT_HOST_ROOT="/opt/sovereign-owner-managed"' in deploy
    assert 'OWNER_INPUT_CONTAINER_ROOT="/opt/sovereign-owner-managed"' in deploy
    assert 'OWNER_INPUT_CONTAINER_ROOT="/opt/secure/owner-managed"' not in deploy
    assert 'umask 077' in deploy
    assert 'mkdir -p "$OWNER_INPUT_HOST_ROOT"' in deploy
    assert 'chmod 0700 "$OWNER_INPUT_HOST_ROOT"' in deploy
    assert '[[ -d "$OWNER_INPUT_HOST_ROOT" && ! -L "$OWNER_INPUT_HOST_ROOT" ]]' in deploy
    assert '[[ -w "$OWNER_INPUT_HOST_ROOT" && -x "$OWNER_INPUT_HOST_ROOT" ]]' in deploy
    assert 'install -d -m 0700 "$OWNER_INPUT_HOST_ROOT"' not in deploy
    assert deploy.count("--volume /opt/secure:/opt/secure:ro") == 2
    assert deploy.count('--env-file "$MANAGED_ENV_FILE"') == 2
    assert deploy.count('--volume "$OWNER_INPUT_HOST_ROOT:$OWNER_INPUT_CONTAINER_ROOT:rw"') == 2
    assert 'WORKSPACE_HOST_ROOT="/opt/sovereign-agent-workspaces"' in deploy
    assert 'WORKSPACE_CONTAINER_ROOT="/var/lib/sovereign-agent/workspaces"' in deploy
    assert 'chown "$WORKSPACE_UID:$WORKSPACE_GID" "$WORKSPACE_HOST_ROOT"' in deploy
    assert 'chmod 0770 "$WORKSPACE_HOST_ROOT"' in deploy
    assert deploy.count('--volume "$WORKSPACE_HOST_ROOT:$WORKSPACE_CONTAINER_ROOT:rw"') == 2
    assert deploy.count('--env "SOVEREIGN_AGENT_WORKSPACE_ROOT=$WORKSPACE_CONTAINER_ROOT"') == 2
    assert "install -d -m 0700 /opt/secure/owner-managed" not in deploy
    assert ':/opt/secure/owner-managed:rw' not in deploy
    assert "--volume /opt/secure:/opt/secure:rw" not in deploy


def test_backend_rollback_preserves_owner_managed_openai_key_mount() -> None:
    rollback = (ROOT / "deploy" / "rollback-sovereign-backend").read_text("utf-8")

    assert 'OWNER_INPUT_HOST_ROOT="/opt/sovereign-owner-managed"' in rollback
    assert 'OWNER_INPUT_CONTAINER_ROOT="/opt/sovereign-owner-managed"' in rollback
    assert 'mkdir -p "$OWNER_INPUT_HOST_ROOT"' in rollback
    assert 'chmod 0700 "$OWNER_INPUT_HOST_ROOT"' in rollback
    assert '--volume "$OWNER_INPUT_HOST_ROOT:$OWNER_INPUT_CONTAINER_ROOT:rw"' in rollback
    assert 'WORKSPACE_HOST_ROOT="/opt/sovereign-agent-workspaces"' in rollback
    assert 'WORKSPACE_CONTAINER_ROOT="/var/lib/sovereign-agent/workspaces"' in rollback
    assert '--volume "$WORKSPACE_HOST_ROOT:$WORKSPACE_CONTAINER_ROOT:rw"' in rollback
    assert '--env "SOVEREIGN_AGENT_WORKSPACE_ROOT=$WORKSPACE_CONTAINER_ROOT"' in rollback
    assert '--env-file "$MANAGED_ENV_FILE"' in rollback
    assert "openhands-enterprise_default" not in rollback


def test_mcp_server_contract_never_accepts_protected_value_argument() -> None:
    server = (ROOT / "server.py").read_text("utf-8")
    client = (ROOT / "owner_input_client.py").read_text("utf-8")

    signature = server.split("def owner_approval_request_create(", 1)[1].split(") ->", 1)[0]
    open_signature = server.split("def owner_approval_widget_open(", 1)[1].split(") ->", 1)[0]
    assert "protected" not in signature.lower()
    assert "secret" not in signature.lower()
    assert "request_id: str" in open_signature
    assert "protected" not in open_signature.lower()
    assert "secret" not in open_signature.lower()
    assert 'target_id: str = "openai_api_key"' in signature
    assert '"openai_api_key": "OpenAI API-Key"' in client
    assert '"litellm_provider_key": "LiteLLM Provider API-Key"' in client
    assert '"proven_learning_confirmation": "Exakter Learning-Plan-Hash"' in client
    assert "def activate_provider_route(" in client
    assert "def activate_litellm_provider_route(" in client
    assert "def plan_proven_learning(" in client
    assert "def apply_proven_learning(" in client
    assert "openhands_api_key" not in client
    assert "OpenHands API-Key" not in client
    assert '"targetId": selected_target' in client
    assert "if selected_target not in ALLOWED_TARGETS" in client
    assert "owner_input.create_request(" in server
    assert server.count("def litellm_provider_route_activate(") == 1
    assert "provider_runtime.activate(route_id)" in server
    assert "payload = owner_input.status(request_id)" in server
    assert "def owner_approval_widget_open(" in server
    assert "meta=OWNER_INPUT_TOOL_META" in server
    assert "structured_output=True" in server
    assert '"sensitiveValuesIncluded": False' in server
    assert '"protectedValueTransport": "direct_backend_https_only"' in server
    assert '"llm_can_receive_protected_value": False' in client


def test_controller_widget_forwards_persisted_release_hunt_and_task_lifecycle() -> None:
    server = (ROOT / "server.py").read_text("utf-8")

    assert '"taskLifecycle": _bounded_controller_text(item.get("taskLifecycle"), 40)' in server
    assert '"isCurrentTask": bool(item.get("isCurrentTask"))' in server
    assert '"isActiveBlocker": bool(item.get("isActiveBlocker"))' in server
    assert '"resolvedByTaskId": _bounded_controller_text(item.get("resolvedByTaskId"), 100)' in server
    assert 'release_hunt = detail.get("releaseHunt")' in server
    assert '"releaseHunt": {' in server
    assert '"nullfindConfirmed": bool(release_hunt.get("nullfindConfirmed"))' in server


def test_controller_operator_tools_are_owner_scoped_and_secret_bounded() -> None:
    server = (ROOT / "server.py").read_text("utf-8")
    client = (ROOT / "owner_input_client.py").read_text("utf-8")

    assert "ControllerRuntimeClient" in server
    assert "controller_runtime = ControllerRuntimeClient()" in server
    assert "A2ARuntimeClient" in server
    assert "a2a_runtime = A2ARuntimeClient()" in server
    assert "def a2a_live_canary(" in server
    assert "def controller_run_start(" in server
    assert "def controller_run_list(" in server
    assert "def controller_run_status(" in server
    assert "def controller_run_resume(" in server
    assert "controller_runtime.start_run(" in server
    assert "controller_runtime.list_runs(" in server
    assert "controller_runtime.run_status(" in server
    assert "controller_runtime.resume_run(" in server
    assert 'RUN_ID_RE = re.compile(r"^run-[0-9a-f]{32}$")' in client
    assert "MAX_OPERATOR_MISSION = 20_000" in client
    assert "MAX_OPERATOR_EVIDENCE = 250_000" in client
    assert "Secret-förmige Evidence ist im Operator-Resume verboten" in client
    assert '"/api/internal/controller/runs"' in client
    assert '"/api/internal/controller/runs/{selected}/resume"' in client
    assert "timeout=1200" in client
