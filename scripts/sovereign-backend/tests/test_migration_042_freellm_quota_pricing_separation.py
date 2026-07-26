from __future__ import annotations

from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND_ROOT / "migrations/042_separate_freellm_quota_from_provider_pricing.sql"
MIRROR = BACKEND_ROOT.parents[1] / "backend/migrations/042_separate_freellm_quota_from_provider_pricing.sql"


def test_migration_mirror_is_byte_equal() -> None:
    assert MIGRATION.read_bytes() == MIRROR.read_bytes()


def test_migration_changes_only_direct_freellm_quota_routes() -> None:
    sql = MIGRATION.read_text("utf-8")

    assert "lower(COALESCE(runtime_kind, provider)) = 'freellm'" in sql
    assert "routingOwner', '') = 'free-revolver-v3'" in sql
    assert "provider_free_quota" in sql
    assert "providerPricingRequired', false" in sql
    assert "pricingVerified', false" in sql
    assert "freeEligible', false" in sql
    assert "quotaContractVerified', false" in sql
    assert "userChargeCredits', 0" in sql
    assert "freellm_quota_contract_recheck_required" in sql
    assert "free_eligible BOOLEAN NOT NULL DEFAULT false" in sql
    assert "eligibility_source TEXT NOT NULL DEFAULT 'unverified'" in sql
    assert "eligibility_verified_at TIMESTAMPTZ" in sql
    assert "lower(COALESCE(runtime_kind, provider)) = 'openrouter'" not in sql
    assert "provider='openrouter'" not in sql


def test_migration_records_version_042_for_supported_ledgers() -> None:
    sql = MIGRATION.read_text("utf-8")

    assert "schema_migrations is missing" in sql
    assert "INSERT INTO schema_migrations (version, applied_at)" in sql
    assert "INSERT INTO schema_migrations (version)" in sql
    assert "VALUES ('042', NOW())" in sql
    assert "VALUES ('042')" in sql
    assert "INSERT INTO schema_migrations (id, name)" in sql
    assert "(42, 'separate_freellm_quota_from_provider_pricing')" in sql
    assert "unsupported schema_migrations layout" in sql


def test_migration_removes_free_price_projection_and_fails_closed() -> None:
    sql = MIGRATION.read_text("utf-8")

    assert "- 'inputUsdPerMillion'" in sql
    assert "- 'cachedInputUsdPerMillion'" in sql
    assert "- 'outputUsdPerMillion'" in sql
    assert "- 'pricingSource'" in sql
    assert "- 'pricingEvidence'" in sql
    assert "disabled = true" in sql
    assert "certificationState', 'recheck_required'" in sql
    assert "pricing_verified_at = NULL" in sql
