from __future__ import annotations

from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
LEGACY = BACKEND / "migrations" / "021_litellm_provider_registry.sql"
DIRECT = BACKEND / "migrations" / "033_openrouter_paid_freellm_direct.sql"
RECONCILE = BACKEND / "migrations" / "037_reenable_verified_direct_freellm_routes.sql"
APP = BACKEND / "app.py"


def test_legacy_replay_disable_has_a_later_evidence_bound_reconciliation() -> None:
    legacy = LEGACY.read_text("utf-8")
    direct = DIRECT.read_text("utf-8")
    reconcile = RECONCILE.read_text("utf-8")
    app = APP.read_text("utf-8")

    assert "WHERE lower(COALESCE(provider, '')) <> 'litellm'" in legacy
    assert "provider = 'freellm'" in direct
    assert "037_reenable_verified_direct_freellm_routes.sql" in app
    assert app.index('"036_llm_route_scanner_candidates.sql"') < app.index(
        '"037_reenable_verified_direct_freellm_routes.sql"'
    )
    assert "SET disabled = false" in reconcile
    assert "provider = 'freellm'" in reconcile
    assert "runtime_kind = 'freellm'" in reconcile


def test_reconciliation_requires_persisted_free_and_double_canary_truth() -> None:
    reconcile = RECONCILE.read_text("utf-8")

    required_contracts = (
        "source.enabled = true",
        "source.auth_mode = 'managed-bearer'",
        "source.last_http_status = 200",
        "model.status = 'ready'",
        "model.enabled = true",
        "model.free_verified = true",
        "model.pricing_verified_at IS NOT NULL",
        "model.last_canary_at IS NOT NULL",
        "model.last_error_code IS NULL",
        "route.config->>'revolverProviderSourceId' = source.id::text",
        "route.config->>'transport', '') = 'freellm'",
        "route.config->>'direct', 'false') = 'true'",
        "route.config->>'fundingMode', '') = 'verified_zero_cost'",
        "route.config->>'pricingVerified', 'false') = 'true'",
        "route.config->>'canaryVerified', 'false') = 'true'",
        "route.config->>'executionProfile', '') = 'free_single_agent'",
        "route.config->>'resolverMode', '') = 'revolver'",
        "route.config->>'canaryConfirmationCount'",
        ">= 2",
    )
    for contract in required_contracts:
        assert contract in reconcile

    assert "openrouter" not in reconcile.lower()
    assert "paid" not in reconcile.lower()
    assert "UPDATE llm_revolver_provider_models" not in reconcile
    assert "UPDATE llm_revolver_provider_sources" not in reconcile


def test_reconciliation_is_idempotently_registered_as_migration_37() -> None:
    reconcile = RECONCILE.read_text("utf-8")

    assert "VALUES (37, 'reenable_verified_direct_freellm_routes')" in reconcile
    assert "ON CONFLICT (id) DO NOTHING" in reconcile
    assert reconcile.strip().startswith("-- Restore only evidence-backed")
    assert reconcile.strip().endswith("COMMIT;")
