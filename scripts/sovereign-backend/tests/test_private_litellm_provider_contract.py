from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "scripts" / "sovereign-backend"


def test_only_canonical_backend_is_built_for_production() -> None:
    workflow = (ROOT / ".github" / "workflows" / "sovereign-backend-image.yml").read_text("utf-8")
    dockerfile = (BACKEND / "Dockerfile").read_text("utf-8")
    assert "context: scripts/sovereign-backend" in workflow
    assert "file: scripts/sovereign-backend/Dockerfile" in workflow
    assert "COPY llm_provider_runtime.py ." in dockerfile
    assert "context: backend" not in workflow


def test_provider_onboarding_is_owner_gated_and_canary_bound() -> None:
    runtime = (BACKEND / "llm_provider_runtime.py").read_text("utf-8")
    owner_input = (BACKEND / "owner_input_runtime.py").read_text("utf-8")
    migration = (BACKEND / "migrations" / "021_litellm_provider_registry.sql").read_text("utf-8")

    assert '"litellm_provider_key"' in owner_input
    assert "owner_input_requests" in runtime
    assert '"/model/new"' in runtime
    assert '"/v1/chat/completions"' in runtime
    assert "provider_canary_failed" in runtime
    assert "SET status='ready'" in runtime
    assert "SET provider='litellm'" in runtime
    assert "_securely_remove(path)" in runtime
    assert "CREATE TABLE IF NOT EXISTS llm_provider_deployments" in migration
    assert "UPDATE llm_routes" in migration
    assert "lower(COALESCE(provider, '')) <> 'litellm'" in migration
    assert "SET api_key = NULL" in migration


def test_live_chat_and_catalog_accept_only_private_litellm_routes() -> None:
    app = (BACKEND / "app.py").read_text("utf-8")
    assert "WHERE lower(provider)='litellm'" in app
    assert "direct_provider_route_blocked" in app
    assert "litellm_unavailable" in app
    assert "Keine durch den Owner bestätigte LiteLLM-Route verfügbar" in app
    assert "Automatische Direktprovider-Routenerzeugung ist deaktiviert" in app
    assert '"status": "Always available (free)"' not in app


def test_readiness_and_litellm_dynamic_model_persistence_are_required() -> None:
    app = (BACKEND / "app.py").read_text("utf-8")
    backend_compose = (BACKEND / "docker-compose.yml").read_text("utf-8")
    deploy_compose = (ROOT / "deploy" / "sovereign-litellm" / "docker-compose.yml").read_text("utf-8")
    template_compose = (
        ROOT
        / "tools"
        / "sovereign-chatgpt-mcp"
        / "templates"
        / "sovereign-litellm"
        / "docker-compose.yml"
    ).read_text("utf-8")
    stack = (ROOT / "tools" / "sovereign-chatgpt-mcp" / "litellm_stack.py").read_text("utf-8")

    assert '@app.route("/health/ready")' in app
    assert "migration21" in app
    assert "invalidDirectRoutes" in app
    assert "/health/ready" in backend_compose
    assert 'STORE_MODEL_IN_DB: "True"' in deploy_compose
    assert deploy_compose == template_compose
    assert '"STORE_MODEL_IN_DB"' in stack
    assert "dynamic model persistence is disabled" in stack


def test_frontend_online_adapter_never_constructs_direct_provider_routes() -> None:
    builder = (ROOT / "src" / "features" / "product" / "llm" / "sovereignLlmAdapters.ts").read_text("utf-8")
    adapter = (
        ROOT
        / "src"
        / "features"
        / "product"
        / "llm"
        / "adapters"
        / "primaryBridgeAdapter.ts"
    ).read_text("utf-8")
    config = (ROOT / "src" / "features" / "product" / "llm" / "primaryBridgeConfig.ts").read_text("utf-8")

    for legacy_import in (
        "mlvocaAdapter",
        "pollinationsAdapter",
        "groqAdapter",
        "huggingfaceAdapter",
        "togetherAdapter",
        "openrouterAdapter",
        "ovhAnonymousAdapter",
        "hfPublicSpaceAdapter",
        "puterJsAdapter",
    ):
        assert legacy_import not in builder
    assert "/api/llm/routes" in adapter
    assert "/api/llm/chat" in adapter
    assert "credentials: 'include'" in adapter
    assert "VITE_SOVEREIGN_LLM_PROXY_URL" not in config
    assert "projectouroboroscollective.workers.dev" not in config
    assert "gateway.ai.cloudflare.com" not in config
