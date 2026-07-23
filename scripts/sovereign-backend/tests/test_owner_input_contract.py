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
    assert "COPY *.py ./" in dockerfile
    owner_runtime = (ROOT / "owner_input_runtime.py").read_text("utf-8")
    swarm_agents = (ROOT / "agent_runtime" / "cognitive_swarm_agents.py").read_text("utf-8")
    swarm_routes = (ROOT / "agent_runtime" / "cognitive_swarm_routes.py").read_text("utf-8")
    transport = (ROOT / "agent_runtime" / "cognitive_llm_transport.py").read_text("utf-8")
    assert '"openai_api_key"' not in owner_runtime
    assert '"litellm_provider_key"' not in owner_runtime
    assert '"openrouter_api_key"' in owner_runtime
    assert '"openhands_api_key"' not in owner_runtime
    assert '"openai_api_key.txt"' not in owner_runtime
    assert '"litellm_provider_key.txt"' not in owner_runtime
    assert '"openrouter_api_key.txt"' in owner_runtime
    assert "SET status='expired', resolved_at=NOW(), result_code='expired'" in owner_runtime
    assert "ON CONFLICT (target_id) WHERE status IN ('pending','processing') DO NOTHING" in owner_runtime
    assert "content_length > int(target[\"maxBytes\"])" in owner_runtime
    assert "def ensure_openai_runtime_key()" not in swarm_agents
    assert "http://litellm:4000" not in swarm_agents
    assert "build_route_run_config(" in swarm_agents
    assert "run_config=route_runtime.run_config" in swarm_agents
    assert "AGENTS_DIRECT_OPENROUTER_ROUTE_REQUIRED" in swarm_agents
    assert '_OPENROUTER_KEY_FILENAME: Final[str] = "openrouter_api_key.txt"' in transport
    assert '_FREELLM_KEY_FILENAME: Final[str] = "freellmapi_unified_key.txt"' in transport
    assert '_FREELLMPOOL_KEY_FILENAME: Final[str] = "freellmpool_proxy_key.txt"' in transport
    assert '_FREELLMAPI_BASE: Final[str] = "http://freellmapi:3001/v1"' in transport
    assert '_FREELLMPOOL_BASE: Final[str] = "http://freellmpool:8080/v1"' in transport
    assert 'SOVEREIGN_FREELLMPOOL_PROXY_KEY_FILE' in transport
    assert 'def _key_spec(transport: str, api_base: str)' in transport
    assert 'provider_module = importlib.import_module("agents.models.openai_provider")' in transport
    assert 'run_config_module = importlib.import_module("agents.run_config")' in transport
    assert 'provider_class = getattr(provider_module, "OpenAIProvider")' in transport
    assert 'run_config_class = getattr(run_config_module, "RunConfig")' in transport
    assert "api_base = route_api_base(route)" in transport
    assert "base_url=api_base" in transport
    assert "use_responses=False" in transport
    assert "tracing_disabled=True" in transport
    assert "trace_include_sensitive_data=False" in transport
    assert "set_default_openai_api" not in swarm_agents
    assert "set_tracing_disabled" not in swarm_agents
    assert 'os.environ["OPENAI_API_KEY"]' not in swarm_agents
    assert 'os.environ["OPENAI_BASE_URL"]' not in swarm_agents
    assert "candidate.name != filename" in transport
    assert 'openai_api_key.txt' not in transport
    assert 'https://api.openai.com' not in swarm_agents
    assert 'if not ensure_openai_runtime_key()' not in swarm_agents
    assert '"configured": None' in swarm_routes
    assert '"configurationResolution": "request-time-persisted-route"' in swarm_routes
    assert '"executionModes": ["auto", "paid", "free"]' in swarm_routes


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
