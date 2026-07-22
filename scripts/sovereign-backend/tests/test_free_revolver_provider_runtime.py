from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import socket
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
sys.path.insert(0, str(BACKEND))

from free_revolver_provider_contracts import (
    ManagedKeyContractError,
    assert_provider_target_allowed,
    assert_public_https_host,
    is_managed_internal_provider_url,
    managed_internal_source_spec,
    models_url_candidates,
    normalize_api_base,
    normalize_max_auto_activate,
    normalize_models_payload,
    normalize_provider_source_id,
    read_managed_freellm_key_file,
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


def test_only_exact_managed_free_endpoints_bypass_public_https_resolution() -> None:
    managed_sources = {
        "freellmapi-direct": "http://freellmapi:3001/v1",
        "freellmpool-private": "http://freellmpool:8080/v1",
    }
    for source_type, managed in managed_sources.items():
        assert normalize_api_base(managed) == managed
        assert is_managed_internal_provider_url(managed) is True
        assert is_managed_internal_provider_url(f"{managed}/models") is True
        assert is_managed_internal_provider_url(f"{managed}/chat/completions") is True
        assert managed_internal_source_spec(managed)["sourceId"] == source_type
        assert_provider_target_allowed(f"{managed}/models")
        assert_provider_target_allowed(f"{managed}/chat/completions")
    for blocked in (
        "http://freellmapi:3002/v1",
        "http://freellmapi:3001/admin",
        "http://freellmpool:8081/v1",
        "http://freellmpool:8080/admin",
        "http://sovereign-backend:8787/v1",
        "http://127.0.0.1:3001/v1",
    ):
        with pytest.raises(ValueError):
            normalize_api_base(blocked)


def test_managed_key_contract_reads_only_the_exact_owner_file(tmp_path: Path) -> None:
    key = "freellmapi-" + ("a" * 48)
    path = tmp_path / "freellmapi_unified_key.txt"
    path.write_text(f"{key}\n", encoding="utf-8")
    path.chmod(0o600)

    protected, resolved_key = read_managed_freellm_key_file(
        owner_root=tmp_path,
        configured_path=str(path),
        expected_fingerprint=hashlib.sha256(key.encode()).hexdigest(),
    )
    try:
        assert resolved_key == key
        assert bytes(protected) == f"{key}\n".encode()
    finally:
        for index in range(len(protected)):
            protected[index] = 0
    assert not any(protected)


def test_managed_key_contract_rejects_non_owner_permissions(tmp_path: Path) -> None:
    path = tmp_path / "freellmapi_unified_key.txt"
    path.write_text("freellmapi-" + ("b" * 48), encoding="utf-8")
    path.chmod(0o640)

    with pytest.raises(ManagedKeyContractError) as caught:
        read_managed_freellm_key_file(
            owner_root=tmp_path,
            configured_path=str(path),
        )
    assert caught.value.code == "freellm_managed_key_permissions_invalid"


def test_managed_key_contract_reports_fingerprint_mismatch_without_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "freellmapi_unified_key.txt"
    path.write_text("freellmapi-" + ("c" * 48), encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(ManagedKeyContractError) as caught:
        read_managed_freellm_key_file(
            owner_root=tmp_path,
            configured_path=str(path),
            expected_fingerprint="0" * 64,
        )
    assert caught.value.code == "freellm_managed_key_fingerprint_mismatch"


def test_managed_key_contract_rejects_paths_outside_owner_root(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    path = nested / "freellmapi_unified_key.txt"
    path.write_text("freellmapi-" + ("d" * 48), encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(ManagedKeyContractError) as caught:
        read_managed_freellm_key_file(
            owner_root=tmp_path,
            configured_path=str(path),
        )
    assert caught.value.code == "freellm_managed_key_path_invalid"


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


def test_managed_quota_contract_only_promotes_missing_price_fields() -> None:
    models = normalize_models_payload(
        {
            "data": [
                {"id": "unreported"},
                {"id": "incomplete", "pricing": {"prompt": 0}},
                {"id": "nonzero", "pricing": {"prompt": 0, "completion": 0.1}},
                {"id": "invalid", "pricing": {"prompt": "unknown", "completion": 0}},
            ],
        },
        managed_quota_contract=True,
    )
    by_id = {model["modelId"]: model for model in models}
    assert by_id["unreported"]["freeVerified"] is True
    assert by_id["incomplete"]["freeVerified"] is True
    assert by_id["unreported"]["pricingSource"] == (
        "managed-freellm-zero-cost-quota-contract"
    )
    assert by_id["nonzero"]["freeVerified"] is False
    assert by_id["nonzero"]["pricingSource"] == "provider-pricing-nonzero"
    assert by_id["invalid"]["freeVerified"] is False
    assert by_id["invalid"]["pricingSource"] == "provider-pricing-invalid"


def test_database_never_receives_raw_provider_keys() -> None:
    migration = (BACKEND / "migrations" / "032_free_revolver_provider_control.sql").read_text("utf-8")
    assert "api_key" not in migration.lower()
    assert "key_fingerprint" in migration
    assert "key_hint" in migration


def test_revolver_migrations_are_preview_safe_and_restore_production_foreign_keys() -> None:
    migration_31 = (BACKEND / "migrations" / "031_sovereign_free_revolver_v3.sql").read_text("utf-8")
    migration_32 = (BACKEND / "migrations" / "032_free_revolver_provider_control.sql").read_text("utf-8")
    migration_33 = (BACKEND / "migrations" / "033_freellmapi_managed_provider.sql").read_text("utf-8")
    migration_34 = (BACKEND / "migrations" / "034_freellm_provider_check_kinds.sql").read_text("utf-8")
    migration_35 = (BACKEND / "migrations" / "035_freellmpool_private_source.sql").read_text("utf-8")

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
    assert "managed-bearer" in migration_33
    assert "api_key" not in migration_33.lower()
    assert "managed_quota_direct_canary" in migration_34
    assert "direct_route_canary" in migration_34
    assert "VALIDATE CONSTRAINT llm_revolver_provider_checks_check_kind_check" in migration_34
    assert "c79ff468-ee08-5686-97df-756fa58b74f0" in migration_35
    assert "http://freellmpool:8080/v1" in migration_35
    assert "api_key" not in migration_35.lower()


def test_app_registers_provider_runtime_and_readiness_requires_migration() -> None:
    app = (BACKEND / "app.py").read_text("utf-8")
    owner_runtime = (BACKEND / "owner_input_runtime.py").read_text("utf-8")
    assert "register_free_revolver_provider_runtime(" in app
    assert "032_free_revolver_provider_control.sql" in app
    assert "033_openrouter_paid_freellm_direct.sql" in app
    assert "033_freellmapi_managed_provider.sql" in app
    assert "034_freellm_provider_check_kinds.sql" in app
    assert "035_freellmpool_private_source.sql" in app
    assert "llm_revolver_provider_sources" in app
    provider_runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    ast.parse(provider_runtime)
    assert '"revolver_provider_key"' in owner_runtime
    assert 'f"revolver_provider_key.{safe_request_id}.txt"' in owner_runtime
    assert "_secret_path(owner_request_id)" in provider_runtime
    assert "allow_redirects=False" in provider_runtime
    assert "_MAX_MODELS_RESPONSE_BYTES" in provider_runtime


def test_provider_route_identifiers_and_activation_limits_fail_closed() -> None:
    source_id = "1a866402-68c4-4f40-8d09-55ed8deabf68"
    assert normalize_provider_source_id(source_id) == source_id
    with pytest.raises(ValueError, match="source_id_invalid"):
        normalize_provider_source_id("not-a-uuid")
    assert normalize_max_auto_activate(0) == 1
    assert normalize_max_auto_activate(999) == 100
    with pytest.raises(ValueError, match="ganze Zahl"):
        normalize_max_auto_activate("20")
    with pytest.raises(ValueError, match="ganze Zahl"):
        normalize_max_auto_activate(True)


def test_provider_toggle_requires_fresh_recheck_before_routes_reactivate() -> None:
    runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    assert "UPDATE llm_routes SET disabled=true" in runtime
    assert "provider_recheck_required" in runtime
    assert "SET enabled=false" in runtime
    assert "SET disabled=%s" not in runtime


def test_provider_recovery_and_key_rotation_are_fail_closed() -> None:
    runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    assert "previous_request_id" in runtime
    assert "WHERE id=%s::uuid" in runtime
    assert "status='probing' AND updated_at < NOW() - INTERVAL '5 minutes'" in runtime
    assert "_cleanup_orphaned_secret_files(query)" in runtime
    assert 'glob("revolver_provider_key.*.txt")' in runtime
    assert "f\"{source_id}\\n{model_id}\\n{key_fingerprint}\"" in runtime
    assert 'str(source.get("auth_mode") or "") != _MANAGED_AUTH_MODE' in runtime
    assert "is_managed_internal_provider_url" in runtime
    assert "ON CONFLICT (id) DO UPDATE SET" in runtime
    assert "model_id=EXCLUDED.model_id" in runtime


def test_price_evidence_is_independent_bounded_and_non_circular() -> None:
    runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    route_runtime = (BACKEND / "free_revolver_runtime.py").read_text("utf-8")
    migration = (BACKEND / "migrations" / "032_free_revolver_provider_control.sql").read_text("utf-8")
    assert '"input_cost_per_token": 0' not in runtime
    assert '"output_cost_per_token": 0' not in runtime
    assert "_direct_completion_canary(" in runtime
    assert "_confirmed_completion_canary(" in runtime
    assert 'for confirmation_index in (1, 2)' in runtime
    assert '"confirmationCount": 2' in runtime
    assert '"x_freellmpool"' in runtime
    assert "never traverses\nLiteLLM" in runtime
    assert "any(value not in (None, 0, 0.0) for value in provider_costs)" in runtime
    assert "def _normalized_provider_cost" in runtime
    assert "math.isfinite(parsed)" in runtime
    assert runtime.count('evidence.get("providerCostsUsd")') >= 2
    assert "canary_cost_state" in migration
    assert "pricing_verified_at" in migration
    assert "last_discovered_at" in migration
    assert "FREE_REVOLVER_PRICING_EVIDENCE_TTL_HOURS" in route_runtime
    assert "provider_model.pricing_verified_at" in route_runtime
    assert "provider_session.trust_env = False" in runtime
    assert runtime.count("COALESCE(to_jsonb(%s::text), 'null'::jsonb)") >= 2
    contracts = (BACKEND / "free_revolver_provider_contracts.py").read_text("utf-8")
    assert 'SOVEREIGN_FREELLMAPI_UNIFIED_KEY_FILE' in contracts
    assert 'SOVEREIGN_FREELLMPOOL_PROXY_KEY_FILE' in contracts
    assert 'candidate.name != filename' in contracts
    assert '"freellmpool-private"' in contracts
    assert '"freellmpool_proxy_key.txt"' in contracts
    assert "read_managed_freellm_key_file" in runtime
    assert "ManagedKeyContractError" in runtime
    assert "_managed_secret_path" not in runtime
    assert runtime.count("protected, key = _read_managed_key(") >= 3
    assert "freellm_model_activation_invalid_evidence" in runtime
    assert "freellm_model_reconcile_failed" in runtime
    assert '"managedKeyAvailable"' in runtime
    assert '"managedKeyBlocker"' in runtime
    assert '"keyFingerprintMatchesFile"' in runtime
    assert 'source.get("auth_mode") in {"bearer", "x-api-key"}' in runtime
    assert "managed_quota_contract=(" in runtime
    assert "managed-freellm-zero-cost-quota-contract" in runtime
    assert "hmac.compare_digest(expected, presented)" in runtime
    assert '"/api/internal/llm/freellm/providers"' in runtime
    assert '"/api/internal/llm/freellm/providers/<source_id>/reconcile"' in runtime
    assert "protected, key = _read_managed_key(" in runtime
    assert "freellm_managed_key_unavailable" in runtime
    assert "free_verified=true, pricing_source=%s" in runtime
    assert '"maxForegroundAgents": 1' in runtime
    assert '"maxBackgroundAgents": 0' in runtime
