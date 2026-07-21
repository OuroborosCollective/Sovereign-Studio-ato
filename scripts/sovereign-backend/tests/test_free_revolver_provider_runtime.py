from __future__ import annotations

from pathlib import Path
import socket
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
sys.path.insert(0, str(BACKEND))

from free_revolver_provider_contracts import (
    assert_public_https_host,
    models_url_candidates,
    normalize_api_base,
    normalize_models_payload,
    zero_price_evidence,
)


def test_models_url_is_normalized_and_discovered_deterministically() -> None:
    assert normalize_api_base("https://api.example.test/v1/models") == "https://api.example.test/v1"
    assert models_url_candidates("https://api.example.test") == (
        "https://api.example.test/v1/models",
        "https://api.example.test/models",
    )
    assert models_url_candidates("https://api.example.test/v1") == (
        "https://api.example.test/v1/models",
        "https://api.example.test/models",
    )


def test_provider_url_rejects_credentials_in_url() -> None:
    with pytest.raises(ValueError, match="Zugangsdaten"):
        normalize_api_base("https://user:secret@api.example.test/v1")


def test_ssrf_guard_rejects_private_resolved_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(ValueError, match="Private oder reservierte"):
        assert_public_https_host("https://api.example.test/v1/models")


def test_zero_cost_requires_complete_explicit_pricing() -> None:
    assert zero_price_evidence({
        "pricing": {"input_cost_per_token": 0, "output_cost_per_token": "0"},
    }) == (True, "provider-models-explicit-zero-pricing")
    assert zero_price_evidence({"pricing": {"cost_per_request": 0}})[0] is True
    assert zero_price_evidence({"pricing": {"input_cost_per_token": 0}}) == (
        False,
        "provider-pricing-unreported-or-incomplete",
    )
    assert zero_price_evidence({
        "pricing": {"input_cost_per_token": 0, "output_cost_per_token": 0.000001},
    }) == (False, "provider-pricing-nonzero")
    assert zero_price_evidence({"free": True}) == (
        False,
        "provider-pricing-unreported-or-incomplete",
    )


def test_model_names_and_free_flags_never_activate_without_price_evidence() -> None:
    models = normalize_models_payload({
        "data": [
            {"id": "looks-free", "free": True},
            {
                "id": "verified-free",
                "pricing": {"prompt": "0", "completion": "0"},
                "capabilities": ["chat", "json"],
            },
        ],
    })
    by_id = {model["modelId"]: model for model in models}
    assert by_id["looks-free"]["freeVerified"] is False
    assert by_id["verified-free"]["freeVerified"] is True
    assert by_id["verified-free"]["capabilities"] == ["chat", "json"]


def test_database_never_receives_raw_provider_keys() -> None:
    migration = (BACKEND / "migrations" / "032_free_revolver_provider_control.sql").read_text("utf-8")
    assert "api_key" not in migration.lower()
    assert "key_fingerprint" in migration
    assert "key_hint" in migration


def test_revolver_migrations_are_preview_safe_and_restore_production_foreign_keys() -> None:
    migration_31 = (BACKEND / "migrations" / "031_sovereign_free_revolver_v3.sql").read_text("utf-8")
    migration_32 = (BACKEND / "migrations" / "032_free_revolver_provider_control.sql").read_text("utf-8")

    assert "tenant_id UUID NULL REFERENCES admin_users" not in migration_31
    assert "tenant_id UUID NOT NULL REFERENCES admin_users" not in migration_31
    assert "to_regclass('admin_users') IS NOT NULL" in migration_31
    for constraint in (
        "fk_llm_revolver_profiles_tenant",
        "fk_llm_revolver_schema_contracts_tenant",
        "fk_llm_revolver_bandit_tenant",
        "fk_llm_semantic_cache_tenant",
    ):
        assert constraint in migration_31

    assert "owner_request_id UUID REFERENCES owner_input_requests" not in migration_32
    assert "created_by UUID REFERENCES admin_users" not in migration_32
    assert "to_regclass('owner_input_requests') IS NOT NULL" in migration_32
    assert "to_regclass('admin_users') IS NOT NULL" in migration_32
    assert "fk_llm_revolver_provider_owner_request" in migration_32
    assert "fk_llm_revolver_provider_created_by" in migration_32


def test_app_registers_provider_runtime_and_readiness_requires_migration() -> None:
    app = (BACKEND / "app.py").read_text("utf-8")
    owner_runtime = (BACKEND / "owner_input_runtime.py").read_text("utf-8")
    assert "register_free_revolver_provider_runtime(" in app
    assert "032_free_revolver_provider_control.sql" in app
    assert "llm_revolver_provider_sources" in app
    provider_runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    assert '"revolver_provider_key"' in owner_runtime
    assert 'f"revolver_provider_key.{safe_request_id}.txt"' in owner_runtime
    assert "_secret_path(owner_request_id)" in provider_runtime
    assert "allow_redirects=False" in provider_runtime
    assert "_MAX_MODELS_RESPONSE_BYTES" in provider_runtime


def test_provider_recovery_and_key_rotation_are_fail_closed() -> None:
    runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    assert "previous_request_id" in runtime
    assert "WHERE id=%s::uuid" in runtime
    assert "status='probing' AND updated_at < NOW() - INTERVAL '5 minutes'" in runtime
    assert "_cleanup_orphaned_secret_files(query)" in runtime
    assert 'glob("revolver_provider_key.*.txt")' in runtime
    assert "f\"{source_id}\\n{model_id}\\n{key_fingerprint}\"" in runtime
    assert 'key if source.get("auth_mode") == "bearer" else ""' in runtime
    assert "ON CONFLICT (id) DO UPDATE SET" in runtime
    assert "model_id=EXCLUDED.model_id" in runtime


def test_price_evidence_is_independent_bounded_and_non_circular() -> None:
    runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    route_runtime = (BACKEND / "free_revolver_runtime.py").read_text("utf-8")
    migration = (BACKEND / "migrations" / "032_free_revolver_provider_control.sql").read_text("utf-8")
    assert '"input_cost_per_token": 0' not in runtime
    assert '"output_cost_per_token": 0' not in runtime
    assert "litellm_completion_canary(alias)" in runtime
    assert "provider_cost not in (None, 0, 0.0)" in runtime
    assert "canary_cost_state" in migration
    assert "pricing_verified_at" in migration
    assert "last_discovered_at" in migration
    assert "FREE_REVOLVER_PRICING_EVIDENCE_TTL_HOURS" in route_runtime
    assert "provider_model.pricing_verified_at" in route_runtime
    assert "provider_session.trust_env = False" in runtime
    assert runtime.count("COALESCE(to_jsonb(%s::text), 'null'::jsonb)") >= 2
