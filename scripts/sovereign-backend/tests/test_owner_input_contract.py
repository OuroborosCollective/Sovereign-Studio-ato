from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_migration_is_metadata_only_and_has_bounded_lifecycle() -> None:
    migration = (ROOT / "migrations" / "017_owner_input_requests.sql").read_text("utf-8")

    assert "CREATE TABLE IF NOT EXISTS owner_input_requests" in migration
    assert "status IN ('pending', 'processing', 'denied', 'consumed', 'failed', 'expired')" in migration
    assert "expires_at > requested_at" in migration
    assert "char_length(owner_comment) <= 1000" in migration
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_owner_input_requests_open_target" in migration
    assert "WHERE status IN ('pending', 'processing')" in migration
    assert "Protected values are accepted only by the owner endpoint and are never persisted here" in migration
    lowered = migration.lower()
    assert "protected_value" not in lowered
    assert "secret_value" not in lowered
    assert "credential_value" not in lowered


def test_backend_registers_owner_routes_and_supports_separate_owner_managed_keys() -> None:
    app = (ROOT / "app.py").read_text("utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text("utf-8")

    assert "from owner_input_runtime import register_owner_input_routes" in app
    assert "register_owner_input_routes(" in app
    assert '"/opt/secure/owner-managed/openhands_api_key.txt"' in app
    assert app.index('"/opt/secure/owner-managed/openhands_api_key.txt"') < app.index('"/opt/secure/openhands_api_key.txt"')
    assert "COPY owner_input_runtime.py ." in dockerfile
    owner_runtime = (ROOT / "owner_input_runtime.py").read_text("utf-8")
    swarm_agents = (ROOT / "agent_runtime" / "cognitive_swarm_agents.py").read_text("utf-8")
    swarm_routes = (ROOT / "agent_runtime" / "cognitive_swarm_routes.py").read_text("utf-8")
    assert '"openai_api_key"' in owner_runtime
    assert '"openai_api_key.txt"' in owner_runtime
    assert "SET status='expired', resolved_at=NOW(), result_code='expired'" in owner_runtime
    assert "ON CONFLICT (target_id) WHERE status IN ('pending','processing') DO NOTHING" in owner_runtime
    assert "content_length > int(target[\"maxBytes\"])" in owner_runtime
    assert "def ensure_openai_runtime_key()" in swarm_agents
    assert 'os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", "/opt/sovereign-owner-managed")' in swarm_agents
    assert 'if not ensure_openai_runtime_key()' in swarm_agents
    assert '"configured": ensure_openai_runtime_key()' in swarm_routes


def test_backend_deploy_keeps_global_secure_mount_read_only_and_only_owner_subdir_writable() -> None:
    repository_root = ROOT.parent.parent
    deploy = (repository_root / "tools" / "sovereign-chatgpt-mcp" / "deploy" / "deploy-sovereign-backend").read_text("utf-8")
    workflow = (repository_root / ".github" / "workflows" / "sovereign-agent-backend.yml").read_text("utf-8")

    assert 'OWNER_INPUT_HOST_ROOT="/opt/sovereign-owner-managed"' in deploy
    assert 'OWNER_INPUT_CONTAINER_ROOT="/opt/sovereign-owner-managed"' in deploy
    assert 'mkdir -p "$OWNER_INPUT_HOST_ROOT"' in deploy
    assert 'chmod 0700 "$OWNER_INPUT_HOST_ROOT"' in deploy
    assert '[[ -d "$OWNER_INPUT_HOST_ROOT" && ! -L "$OWNER_INPUT_HOST_ROOT" ]]' in deploy
    assert '[[ -w "$OWNER_INPUT_HOST_ROOT" && -x "$OWNER_INPUT_HOST_ROOT" ]]' in deploy
    assert 'install -d -m 0700 "$OWNER_INPUT_HOST_ROOT"' not in deploy
    assert deploy.count("--volume /opt/secure:/opt/secure:ro") == 2
    assert deploy.count('--volume "$OWNER_INPUT_HOST_ROOT:$OWNER_INPUT_CONTAINER_ROOT:rw"') == 2
    assert ':/opt/secure/owner-managed:rw' not in deploy
    assert "--volume /opt/secure:/opt/secure:rw" not in deploy
    assert 'OWNER_INPUT_ROOT="/opt/sovereign-owner-managed"' in workflow
    assert 'if [ ! -d "$OWNER_INPUT_ROOT" ] || [ -L "$OWNER_INPUT_ROOT" ]; then' in workflow
    assert workflow.count('--volume "$OWNER_INPUT_ROOT:$OWNER_INPUT_ROOT:rw"') == 2
    assert workflow.count("--volume /opt/secure:/opt/secure:ro") == 2
