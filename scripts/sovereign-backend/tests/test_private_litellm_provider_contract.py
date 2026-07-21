from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "scripts" / "sovereign-backend"


def test_only_canonical_backend_is_built_for_production() -> None:
    workflow = (ROOT / ".github" / "workflows" / "sovereign-backend-image.yml").read_text("utf-8")
    dockerfile = (BACKEND / "Dockerfile").read_text("utf-8")
    assert "context: scripts/sovereign-backend" in workflow
    assert "file: scripts/sovereign-backend/Dockerfile" in workflow
    assert "COPY *.py ./" in dockerfile
    assert "COPY agent_runtime/ ./agent_runtime/" in dockerfile
    assert "COPY migrations ./migrations" in dockerfile
    assert "COPY app.py ." not in dockerfile
    assert "context: backend" not in workflow


def test_provider_onboarding_is_owner_gated_and_canary_bound() -> None:
    runtime = (BACKEND / "llm_provider_runtime.py").read_text("utf-8")
    owner_input = (BACKEND / "owner_input_runtime.py").read_text("utf-8")
    migration = (BACKEND / "migrations" / "021_litellm_provider_registry.sql").read_text("utf-8")

    assert '"litellm_provider_key"' in owner_input
    assert "owner_input_requests" in runtime
    assert '"/model/new"' in runtime
    assert '"/v1/chat/completions"' in runtime
    assert '"/api/admin/llm/provider-deployments/<route_id>/owner-input"' in runtime
    assert "provider_canary_failed" in runtime
    assert "_catalog_model_with_retry" in runtime
    assert "requires_secret = secret_available or not model_present or not key_fingerprint" in runtime
    assert "_normalize_provider_recovery_policy" in runtime
    assert "provider_recovery_policy_invalid" in runtime
    assert "policyUpdated" in runtime
    assert "if secret_loaded:" in runtime
    assert "key_fingerprint=%s, key_hint=%s" in runtime
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
    assert "classify_litellm_failure" in app
    assert "free_route_revolver_exhausted" in app
    assert "Keine preisverifizierte LiteLLM-Route verfügbar" in app
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
    assert "026_llm_free_route_revolver.sql" in app
    assert "027_billing_idempotency_and_package_uniqueness.sql" in app
    assert "uq_credit_packages_name" in app
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


def test_three_category_cost_policy_is_fail_closed() -> None:
    policy = (BACKEND / "llm_cost_policy.py").read_text("utf-8")
    billing = (BACKEND / "agent_runtime" / "cognitive_usage_billing.py").read_text("utf-8")
    provider = (BACKEND / "llm_provider_runtime.py").read_text("utf-8")
    app = (BACKEND / "app.py").read_text("utf-8")
    ui = (BACKEND / "enterprise_admin_ui.py").read_text("utf-8")
    migration = (BACKEND / "migrations" / "022_llm_cost_floor_and_funded_credits.sql").read_text("utf-8")

    assert 'FREE_CATEGORY: Final[str] = "free"' in policy
    assert 'STANDARD_CATEGORY: Final[str] = "standard"' in policy
    assert 'PREMIUM_CATEGORY: Final[str] = "premium"' in policy
    assert "STANDARD_MARKUP_MULTIPLIER" in policy
    assert "PREMIUM_MARKUP_MULTIPLIER" in policy
    assert "free routes require verified zero provider prices" in policy
    assert 'FREE_FUNDING_PROVIDER_QUOTA: Final[str] = "provider_free_quota"' in policy
    assert "normalize_funding_mode" in policy
    assert "provider_free_quota routes require positive verified provider list prices" in policy
    assert "AGENTS_PROVIDER_MODEL: Final[str] = \"gpt-5.4-mini\"" in policy

    assert "provider_funded_credits" in migration
    assert "billing_category IN ('free', 'standard', 'premium')" in migration
    assert "billing_category = 'standard' AND markup_multiplier >= 4" in migration
    assert "billing_category = 'premium' AND markup_multiplier >= 8" in migration
    assert "credit_packages_cash_buffer_check" in migration

    assert "_load_agent_policy" in billing
    assert "AGENTS_LITELLM_ALIAS_NOT_READY" in billing
    assert "AGENTS_PROVIDER_MODEL_MISMATCH" in billing
    assert "AGENTS_STANDARD_ROUTE_REQUIRED" in billing
    assert "funded_credits_reserved" in billing

    assert '"billingCategories": list(BILLING_CATEGORY_OPTIONS)' in provider
    assert '"fundingModes": list(FUNDING_MODE_OPTIONS)' in provider
    assert "FREE_FUNDING_PROVIDER_QUOTA" in provider
    assert '"/api/admin/llm/model-catalog"' in provider
    assert '"/api/admin/llm/model-catalog/attach"' in provider
    assert "litellm_pricing_not_eligible" in provider
    assert "free_route_nonzero_or_unreported_cost" in provider

    assert "provider_funded_delta=-amount" in app
    assert "providerBillingCategory" in ui
    assert "providerFundingMode" in ui
    assert "providerMarkupMultiplier" in ui
    assert "billingCategory:document.getElementById('providerBillingCategory').value" in ui
    assert "fundingMode:document.getElementById('providerFundingMode').value" in ui
    assert "markupMultiplier:Number(document.getElementById('providerMarkupMultiplier').value||0)" in ui
    assert "refreshProviderOwnerInput" in ui
    assert "prepareProviderFreeQuota" in ui
    assert "provider_free_quota" in ui
    assert "providerCredentialLabel" in ui
    assert "lastErrorCode" in ui
    assert "billingCategory" in ui
    assert "markupMultiplier" in ui
    assert "llm_route_attempts" in ui
    assert "llm_route_revolver_state" in ui
    assert "manual_llm_price_editing_disabled" in ui
    assert "free_route_user_charge_nonzero" in ui
