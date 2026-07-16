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
    assert '"/opt/secure/owner-managed/openhands_api_key.txt"' not in app
    assert '"/opt/secure/openhands_api_key.txt"' not in app
    assert "OPENHANDS_API_URL" not in app
    assert "COPY owner_input_runtime.py ." in dockerfile
    owner_runtime = (ROOT / "owner_input_runtime.py").read_text("utf-8")
    swarm_agents = (ROOT / "agent_runtime" / "cognitive_swarm_agents.py").read_text("utf-8")
    swarm_routes = (ROOT / "agent_runtime" / "cognitive_swarm_routes.py").read_text("utf-8")
    assert '"openai_api_key"' in owner_runtime
    assert '"openhands_api_key"' not in owner_runtime
    assert '"openai_api_key.txt"' in owner_runtime
    assert "SET status='expired', resolved_at=NOW(), result_code='expired'" in owner_runtime
    assert "ON CONFLICT (target_id) WHERE status IN ('pending','processing') DO NOTHING" in owner_runtime
    assert "content_length > int(target[\"maxBytes\"])" in owner_runtime
    assert "def ensure_openai_runtime_key()" in swarm_agents
    assert 'os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", "/opt/sovereign-owner-managed")' in swarm_agents
    assert '_LITELLM_SERVICE_KEY_FILENAME: Final[str] = "litellm_master_key.txt"' in swarm_agents
    assert '_DEFAULT_LITELLM_BASE_URL: Final[str] = "http://litellm:4000"' in swarm_agents
    assert 'provider_module = importlib.import_module("agents.models.openai_provider")' in swarm_agents
    assert 'run_config_module = importlib.import_module("agents.run_config")' in swarm_agents
    assert 'provider_class = getattr(provider_module, "OpenAIProvider")' in swarm_agents
    assert 'run_config_class = getattr(run_config_module, "RunConfig")' in swarm_agents
    assert 'base_url=f"{base_url}/v1"' in swarm_agents
    assert "use_responses=False" in swarm_agents
    assert "tracing_disabled=True" in swarm_agents
    assert "trace_include_sensitive_data=False" in swarm_agents
    assert "run_config=_require_litellm_run_config()" in swarm_agents
    assert "set_default_openai_api" not in swarm_agents
    assert "set_tracing_disabled" not in swarm_agents
    assert 'os.environ["OPENAI_API_KEY"]' not in swarm_agents
    assert 'os.environ["OPENAI_BASE_URL"]' not in swarm_agents
    assert 'candidate.name != _LITELLM_SERVICE_KEY_FILENAME' in swarm_agents
    assert 'openai_api_key.txt' not in swarm_agents
    assert 'https://api.openai.com' not in swarm_agents
    assert 'if not ensure_openai_runtime_key()' in swarm_agents
    assert '"configured": ensure_openai_runtime_key()' in swarm_routes


def test_broker_deploy_keeps_secure_mounts_bounded_and_ci_stays_queue_only() -> None:
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
    assert "openhands-enterprise_default" not in deploy
    assert "release-policy-gate:" in workflow
    assert "appleboy/" not in workflow
    assert "VPS_PASSWORD" not in workflow
    assert "docker build" not in workflow
    assert "docker run" not in workflow
