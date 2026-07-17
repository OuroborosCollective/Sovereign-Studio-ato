from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_BACKEND = ROOT / "scripts" / "sovereign-backend"
APP_PATHS = (
    SCRIPT_BACKEND / "app.py",
)


def _load_litellm_runtime():
    spec = importlib.util.spec_from_file_location(
        "sovereign_litellm_runtime_contract",
        SCRIPT_BACKEND / "litellm_runtime.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_litellm_usage_parser_prefers_real_total_and_bounds_values() -> None:
    runtime = _load_litellm_runtime()
    evidence = runtime.extract_litellm_usage({
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 155}
    })
    assert evidence == {"promptTokens": 120, "completionTokens": 30, "totalTokens": 155}
    fallback_total = runtime.extract_litellm_usage({
        "usage": {"prompt_tokens": 20, "completion_tokens": 5}
    })
    assert fallback_total["totalTokens"] == 25


def test_backend_routes_reserve_then_settle_from_runtime_usage() -> None:
    required_fragments = (
        "from litellm_runtime import (",
        "def _create_llm_usage_settlement(",
        "INSERT INTO llm_usage_settlements",
        "ON CONFLICT (request_id) DO NOTHING",
        '"blocker": "duplicate_llm_request_id"',
        'if provider == "litellm":',
        "fetch_litellm(",
        '"direct_provider_route_blocked"',
        '"litellm_unavailable"',
        "extract_litellm_evidence(resp, result)",
        '"chargeBasis": "actual_usage" if total_tokens > 0 else "reserved_request_estimate"',
        'provider_tx_id=f"{request_id}:refund"',
        '"blocker": "litellm_streaming_not_enabled"',
    )
    for path in APP_PATHS:
        source = path.read_text("utf-8")
        for fragment in required_fragments:
            assert fragment in source, f"{fragment!r} missing from {path}"
        assert "OPENAI_API_KEY" not in source
        assert "getattr(resp, \"text\"" not in source
        assert "return refund_failed_run(\"litellm_unavailable\")" in source


def test_migration_adds_two_litellm_routes_and_settlement_evidence() -> None:
    migration = (SCRIPT_BACKEND / "migrations" / "012_litellm_usage_settlements.sql").read_text("utf-8")
    assert "CREATE TABLE IF NOT EXISTS llm_usage_settlements" in migration
    assert "request_id UUID PRIMARY KEY" in migration
    assert "reserved_credits" in migration
    assert "settled_credits" in migration
    assert "refunded_credits" in migration
    assert "upstream_request_id" in migration
    assert "provider_cost_usd" in migration
    assert "'sovereign-fast'" in migration
    assert "'sovereign-balanced'" in migration
    assert "'litellm'" in migration
    assert "http://litellm:4000" in migration
    assert "ON CONFLICT (model_id) DO UPDATE" in migration
    assert "id = EXCLUDED.id" in migration
    assert "disabled = true" in migration
    assert "disabled = llm_routes.disabled" not in migration
    assert "DELETE FROM" not in migration.upper()


def test_litellm_templates_stage_models_only_after_verified_provider_inventory() -> None:
    configs = (
        ROOT / "deploy" / "sovereign-litellm" / "config.yaml",
        ROOT / "tools" / "sovereign-chatgpt-mcp" / "templates" / "sovereign-litellm" / "config.yaml",
    )
    composes = (
        ROOT / "deploy" / "sovereign-litellm" / "docker-compose.yml",
        ROOT / "tools" / "sovereign-chatgpt-mcp" / "templates" / "sovereign-litellm" / "docker-compose.yml",
    )
    config_sources = [path.read_text("utf-8") for path in configs]
    assert config_sources[0] == config_sources[1]
    for source in config_sources:
        assert "model_list: []" in source
        assert "openai/gpt-5.6-luna" not in source
        assert "openai/gpt-5.6-terra" not in source
        assert "api_key:" not in source
        assert "model_name: '*'" not in source
        assert "model_name: \"*\"" not in source

    compose_sources = [path.read_text("utf-8") for path in composes]
    assert compose_sources[0] == compose_sources[1]
    for source in compose_sources:
        assert "./sovereign-entrypoint.py:/app/sovereign-entrypoint.py:ro" in source
        assert "/opt/sovereign-owner-managed/openai_api_key.txt:/run/secrets/openai_api_key:ro" in source
        assert "OPENAI_API_KEY:" not in source
        assert "ports:" not in source
        assert source.count("sovereign-private") >= 3
        assert "supabase_default" not in source
        assert "mcp-proxy" not in source


def test_backend_deploy_contract_connects_only_internal_litellm_network() -> None:
    deploy = (ROOT / "tools" / "sovereign-chatgpt-mcp" / "deploy" / "deploy-sovereign-backend").read_text("utf-8")
    rollback = (ROOT / "tools" / "sovereign-chatgpt-mcp" / "deploy" / "rollback-sovereign-backend").read_text("utf-8")
    installer = (ROOT / "tools" / "sovereign-chatgpt-mcp" / "deploy" / "install-on-vps.sh").read_text("utf-8")
    assert "docker network connect sovereign-private" in deploy
    assert "docker network connect sovereign-private" in rollback
    assert "LITELLM_BASE_URL=http://litellm:4000" in installer
    assert "LITELLM_MASTER_KEY_FILE=/opt/sovereign-owner-managed/litellm_master_key.txt" in installer
    assert "OPENAI_API_KEY=" not in installer
