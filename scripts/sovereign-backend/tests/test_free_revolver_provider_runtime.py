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
    general_chat_response_verified,
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


def test_model_names_and_free_flags_never_activate_without_eligibility_evidence() -> None:
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
    assert by_id["looks-free"]["freeEligible"] is False
    assert by_id["verified-free"]["freeEligible"] is True
    assert by_id["verified-free"]["capabilities"] == ["chat", "json"]


def test_managed_quota_contract_requires_chat_canary_when_capabilities_are_missing() -> None:
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
    for model_id in ("unreported", "incomplete"):
        assert by_id[model_id]["generalChatEligible"] is False
        assert by_id[model_id]["generalChatCanaryRequired"] is True
        assert by_id[model_id]["freeEligible"] is False
        assert by_id[model_id]["eligibilitySource"] == (
            "managed-freellm-chat-canary-required"
        )
        assert by_id[model_id]["generalChatEligibilitySource"] == (
            "general-chat-capability-unreported"
        )
    assert by_id["unreported"]["providerCostCatalogState"] == "unreported"
    assert by_id["nonzero"]["freeEligible"] is False
    assert by_id["nonzero"]["generalChatCanaryRequired"] is False
    assert by_id["nonzero"]["eligibilitySource"] == "provider-pricing-nonzero"
    assert by_id["invalid"]["freeEligible"] is False
    assert by_id["invalid"]["generalChatCanaryRequired"] is False
    assert by_id["invalid"]["eligibilitySource"] == "provider-pricing-invalid"


def test_specialist_only_models_never_enter_general_chat_revolver() -> None:
    models = normalize_models_payload(
        {
            "data": [
                {"id": "nemotron-3.5-content-safety"},
                {"id": "vendor/safeguard-20b"},
                {"id": "whisper-large-v3"},
                {"id": "openai/tts-1"},
                {"id": "dall-e-3"},
                {"id": "black-forest-labs/FLUX.1-dev"},
                {"id": "text-embedding-3", "capabilities": ["embeddings"]},
                {"id": "document-reranker", "capabilities": ["rerank"]},
                {"id": "general-reasoning", "capabilities": ["reasoning", "chat"]},
                {"id": "code-assistant", "capabilities": ["code", "chat", "json"]},
                {"id": "multimodal-assistant", "capabilities": ["vision", "chat"]},
            ],
        },
        managed_quota_contract=True,
    )
    by_id = {model["modelId"]: model for model in models}

    expected_block_sources = {
        "nemotron-3.5-content-safety": "specialist-model-identifier",
        "vendor/safeguard-20b": "specialist-model-identifier",
        "whisper-large-v3": "specialist-model-identifier",
        "openai/tts-1": "specialist-model-identifier",
        "dall-e-3": "specialist-model-identifier",
        "black-forest-labs/FLUX.1-dev": "specialist-model-identifier",
        "text-embedding-3": "explicit-non-chat-capability",
        "document-reranker": "explicit-non-chat-capability",
    }
    for model_id, blocker_source in expected_block_sources.items():
        assert by_id[model_id]["generalChatEligible"] is False
        assert by_id[model_id]["freeEligible"] is False
        assert by_id[model_id]["eligibilitySource"] == blocker_source
        assert by_id[model_id]["generalChatEligibilitySource"] == blocker_source
        assert by_id[model_id]["generalChatBlockVerified"] is True

    for model_id in (
        "general-reasoning",
        "code-assistant",
        "multimodal-assistant",
    ):
        assert by_id[model_id]["generalChatEligible"] is True
        assert by_id[model_id]["freeEligible"] is True
        assert by_id[model_id]["generalChatEligibilitySource"] == (
            "explicit-text-chat-capability"
        )
        assert by_id[model_id]["generalChatCanaryRequired"] is False


def test_modality_or_format_capability_alone_never_certifies_text_chat() -> None:
    models = normalize_models_payload(
        {
            "data": [
                {"id": "vision-only", "capabilities": ["vision"]},
                {"id": "json-only", "capabilities": ["json"]},
                {"id": "multimodal-only", "capabilities": ["multimodal"]},
                {"id": "reasoning-only", "capabilities": ["reasoning"]},
                {"id": "code-only", "capabilities": ["code"]},
            ],
        },
        managed_quota_contract=True,
    )

    for model in models:
        assert model["generalChatEligible"] is False
        assert model["generalChatCanaryRequired"] is False
        assert model["generalChatBlockVerified"] is True
        assert model["freeEligible"] is False
        assert model["eligibilitySource"] == "no-text-chat-capability"
        assert model["generalChatEligibilitySource"] == "no-text-chat-capability"


def test_general_chat_canary_requires_explicit_assistant_text_reply() -> None:
    assert general_chat_response_verified({
        "choices": [{"message": {"role": "assistant", "content": "OK."}}],
    }) is True
    for payload in (
        {},
        {"choices": []},
        {"choices": [{"message": {"content": "OK"}}]},
        {"choices": [{"message": {"role": "tool", "content": "OK"}}]},
        {"choices": [{"message": {"role": "assistant", "content": None}}]},
        {"choices": [{"message": {"role": "assistant", "content": "SAFE"}}]},
    ):
        assert general_chat_response_verified(payload) is False


def test_unknown_model_id_is_not_catalog_certified_without_chat_evidence() -> None:
    model = normalize_models_payload(
        {"data": [{"id": "vendor/new-model-without-metadata"}]},
        managed_quota_contract=True,
    )[0]

    assert model["generalChatEligible"] is False
    assert model["generalChatCanaryRequired"] is True
    assert model["freeEligible"] is False
    assert model["capabilities"] == []
    assert model["capabilityEvidenceCount"] == 0
    assert model["generalChatEligibilitySource"] == (
        "general-chat-capability-unreported"
    )


def test_all_capabilities_are_classified_before_storage_truncation() -> None:
    capabilities = ["chat"] * 20 + ["moderation"]
    model = normalize_models_payload(
        {"data": [{"id": "mixed-capabilities", "capabilities": capabilities}]},
        managed_quota_contract=True,
    )[0]

    assert model["capabilities"] == ["chat"] * 20
    assert model["capabilityEvidenceCount"] == 21
    assert model["capabilitiesTruncated"] is True
    assert model["generalChatEligible"] is False
    assert model["generalChatCanaryRequired"] is False
    assert model["freeEligible"] is False
    assert model["generalChatEligibilitySource"] == (
        "explicit-non-chat-capability"
    )


def test_overlong_capability_evidence_fails_closed() -> None:
    capabilities = ["chat"] * 101
    model = normalize_models_payload(
        {"data": [{"id": "capability-overflow", "capabilities": capabilities}]},
        managed_quota_contract=True,
    )[0]

    assert model["capabilityEvidenceCount"] == 101
    assert model["capabilitiesTruncated"] is True
    assert model["generalChatEligible"] is False
    assert model["generalChatCanaryRequired"] is False
    assert model["freeEligible"] is False
    assert model["generalChatEligibilitySource"] == "capability-evidence-too-large"


def test_freellmpool_workflow_requires_v3_textual_chat_evidence() -> None:
    workflow = (REPO / ".github" / "workflows" / "sovereign-freellmpool-verify.yml").read_text("utf-8")

    assert "sovereign.freellm-route-receipt.v2" not in workflow
    assert '"schemaVersion": "sovereign.freellm-route-receipt.v3"' in workflow
    assert '"generalChatEvidenceVerified"' in workflow
    assert '"textualChatResponseVerified"' in workflow
    assert 'str(message.get("role") or "").strip().casefold() == "assistant"' in workflow
    assert 'normalized_reply.startswith("ok")' in workflow


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
    assert "036_llm_route_scanner_candidates.sql" in app
    assert "037_reenable_verified_direct_freellm_routes.sql" in app
    assert "038_reclassify_retryable_freellm_canary_failures.sql" in app
    assert "040_llm_route_scanner_free_quota_evidence.sql" in app
    assert "042_separate_freellm_quota_from_provider_pricing.sql" in app
    assert "llm_revolver_provider_sources" in app
    provider_runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    ast.parse(provider_runtime)
    assert '"revolver_provider_key"' in owner_runtime
    assert 'f"revolver_provider_key.{safe_request_id}.txt"' in owner_runtime
    assert "_secret_path(owner_request_id)" in provider_runtime
    assert "allow_redirects=False" in provider_runtime
    assert "_MAX_MODELS_RESPONSE_BYTES" in provider_runtime


def test_keyless_activation_is_owner_bounded_current_and_not_readiness() -> None:
    runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    credentials = (BACKEND / "freellm_provider_credentials.py").read_text("utf-8")

    assert '_KNOWN_KEYLESS_POOL_PROVIDERS = {"ovh", "ovhcloud", "kilo", "llm7"}' in runtime
    assert '_KNOWN_KEYLESS_POOL_PROVIDERS = {"pollinations"' not in runtime
    assert '"label": "Pollinations (Publishable Key)"' in credentials
    pollinations_block = credentials.split('"pollinations": {', 1)[1].split("},", 1)[0]
    assert '"keyless": False' in pollinations_block
    assert '"/api/internal/llm/freellm/provider-credentials/<provider_id>/keyless"' in runtime
    assert "def internal_activate_freellm_keyless_provider(" in runtime
    assert "if not _internal_owner_authorized():" in runtime
    assert "normalize_freellm_provider_id(provider_id)" in runtime
    assert "if not bool(spec.get(\"keyless\")):" in runtime
    assert "_write_keyless_marker(provider_id, True)" in runtime
    assert '"runtimeImportPending": True' in runtime
    assert '"routeReady": False' in runtime
    assert '"protectedValuesReturned": False' in runtime
    assert '"rawCredentialReturned": False' in runtime


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


def test_quota_and_canary_evidence_is_independent_bounded_and_non_circular() -> None:
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
    assert "never traverses\nLegacy LiteLLM" in runtime
    assert "any(value not in (None, 0, 0.0) for value in provider_costs)" in runtime
    assert "def _normalized_provider_cost" in runtime
    assert "math.isfinite(parsed)" in runtime
    assert runtime.count('evidence.get("providerCostsUsd")') == 1
    assert runtime.count("result = activate_model(") >= 3
    assert "canary_cost_state" in migration
    assert "pricing_verified_at" in migration
    migration_42 = (BACKEND / "migrations" / "042_separate_freellm_quota_from_provider_pricing.sql").read_text("utf-8")
    assert "provider_free_quota" in migration_42
    assert "pricingVerified', false" in migration_42
    assert "freellm_quota_contract_recheck_required" in migration_42
    assert "free_eligible BOOLEAN NOT NULL DEFAULT false" in migration_42
    assert "eligibility_source TEXT NOT NULL DEFAULT 'unverified'" in migration_42
    assert "eligibility_verified_at TIMESTAMPTZ" in migration_42
    assert "last_discovered_at" in migration
    assert "FREE_REVOLVER_ELIGIBILITY_EVIDENCE_TTL_HOURS" in route_runtime
    assert "provider_model.last_canary_at" in route_runtime
    assert "provider_session.trust_env = False" in runtime
    assert "COALESCE(to_jsonb(%s::text), 'null'::jsonb)" not in runtime
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
    assert "def _persist_verified_general_chat_blocks(" in runtime
    assert "_VERIFIED_GENERAL_CHAT_BLOCKERS = frozenset({" in runtime
    assert "eligibility_verified_at=NOW()" in runtime
    assert "eligibility_source = ANY(%s)" in runtime
    assert '"blockedEvidence": _blocked_general_chat_evidence(' in runtime
    assert '"generalChatBlockVerified": True' in runtime
    assert "_verified_general_chat_block_source(model.get(\"eligibility_source\"))" in runtime
    assert "eligibility_source='specialist-model-identifier'" in runtime
    assert '"keyFingerprintMatchesFile"' in runtime
    assert 'source.get("auth_mode") in {"bearer", "x-api-key"}' in runtime
    assert "managed_quota_contract=(" in runtime
    assert "managed-freellm-quota-contract" in runtime
    assert "hmac.compare_digest(expected, presented)" in runtime
    assert '"/api/internal/llm/freellm/providers"' in runtime
    assert '"/api/internal/llm/freellm/providers/<source_id>/discover"' in runtime
    assert '"/api/internal/llm/freellm/providers/<source_id>/reconcile"' in runtime
    assert "def internal_discover_managed_freellm_provider" in runtime
    assert '"managedCatalogBootstrap": True' in runtime
    assert '"doubleCanaryRequired": True' in runtime
    assert '"authenticatedCatalogHttpStatus": last_status' in runtime
    assert '"rawProviderResponsesReturned": False' in runtime
    assert '"failureFamily": "upstream_http_4xx"' in runtime
    assert '"failureFamily": "upstream_http_5xx"' in runtime
    assert '"failureFamily": "transport_request_exception"' in runtime
    assert '"failureFamily": "response_decode_invalid"' in runtime
    assert '"requestExceptionType": type(exc).__name__[:80]' in runtime
    assert '"failedConfirmation": confirmation_index' in runtime
    assert '"httpStatus": result.get("httpStatus")' in runtime
    assert '"failureFamily": result.get("failureFamily")' in runtime
    assert '"requestExceptionType": result.get("requestExceptionType")' in runtime
    assert "exceptionMessage" not in runtime
    assert "rawProviderResponseBody" not in runtime
    assert "protected, key = _read_managed_key(" in runtime
    assert "freellm_managed_key_unavailable" in runtime
    assert "free_eligible=true, eligibility_source=%s" in runtime
    assert "free_verified" not in runtime
    assert "pricing_source" not in runtime
    assert "pricing_verified_at" not in runtime
    assert '"fundingMode": "provider_free_quota"' in runtime
    assert '"providerPricingRequired": False' in runtime
    assert '"pricingVerified": False' in runtime
    assert '"freeEligible": True' in runtime
    assert '"quotaContractVerified": True' in runtime
    assert '"eligibilityEvidence": {' in runtime
    assert '"pricingEvidence": {' not in runtime
    assert '"maxForegroundAgents": 1' in runtime
    assert '"maxBackgroundAgents": 0' in runtime
    assert "def _runtime_identity()" in runtime
    assert 'os.getenv("SOVEREIGN_SOURCE_REVISION"' in runtime
    assert 'os.getenv("SOVEREIGN_IMAGE_DIGEST"' in runtime
    assert "def _canonical_sha256" in runtime
    assert '"freellm_revision_bound_receipt_required"' in runtime
    assert '_FREELLM_RECEIPT_SCHEMA = "sovereign.freellm-route-receipt.v3"' in runtime
    assert '"generalChatEvidenceVerified": True' in runtime
    assert '"textualChatResponsesVerified": True' in runtime
    assert '"schemaVersion": _FREELLM_RECEIPT_SCHEMA' in runtime
    assert '"receiptSha256": receipt_sha256' in runtime
    assert '"readyReceipts": [' in runtime
    assert '"quotaEvidence": quota_contract' in runtime
    assert '"retryEvidence": retry_contract' in runtime
    assert '"cooldownEvidence": cooldown_contract' in runtime
    assert '"candidateFailuresAreIsolated": True' in runtime
    assert '"reactivationRequiresFreshDoubleCanary": True' in runtime


def test_admin_projection_uses_direct_route_terms_and_revision_receipts() -> None:
    runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    api_client = (REPO / "src/features/admin/api/adminApiClient.ts").read_text("utf-8")
    control_center = (
        REPO / "src/features/admin/components/FreeRevolverControlCenter.tsx"
    ).read_text("utf-8")

    assert '"routeAlias": model.get("litellm_alias")' in runtime
    assert '"litellmAlias": model.get("litellm_alias")' not in runtime
    assert "routeAlias: string | null" in api_client
    assert "litellmAlias: string | null" not in api_client
    assert "hasRevisionBoundReceipt" in control_center
    assert "model.runtimeIdentity.sourceRevisionVerified === true" in control_center
    assert "model.runtimeIdentity.imageDigestVerified === true" in control_center
    assert "model.canaryReceipt.schemaVersion === 'sovereign.freellm-route-receipt.v3'" in control_center
    assert "model.canaryReceipt.generalChatEvidenceVerified === true" in control_center
    assert "model.canaryReceipt.receiptSha256" in control_center
    assert "generalChatEvidenceVerified?: boolean" in api_client
    assert "model.litellmAlias" not in control_center


def test_metadata_free_discovery_preserves_current_v3_certified_routes() -> None:
    runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")

    assert "def _current_certified_model_sources(" in runtime
    assert runtime.count("certified_model_sources = _current_certified_model_sources(") == 2
    assert runtime.count("preserved_model_ids = {") == 2
    assert runtime.count("and str(model[\"modelId\"]) not in preserved_model_ids") == 2
    assert runtime.count("if str(model[\"modelId\"]) in preserved_model_ids:") == 2
    assert "route.config->'canaryReceipt'->>'schemaVersion'=%s" in runtime
    assert "route.config->'canaryReceipt'->>'generalChatEvidenceVerified'='true'" in runtime
    assert "route.config->'canaryReceipt'->>'receiptSha256' ~ '^[0-9a-f]{64}$'" in runtime
    assert "SET free_eligible=true, status='ready', enabled=true" in runtime
    assert "certified_model_sources[str(model[\"modelId\"])]" in runtime
    assert "activation_models[:max_models]" in runtime


def test_failed_metadata_free_chat_canaries_remain_recheckable() -> None:
    runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")
    control_center = (
        REPO / "src/features/admin/components/FreeRevolverControlCenter.tsx"
    ).read_text("utf-8")

    assert "OR eligibility_source='managed-freellm-chat-canary-required'" in runtime
    assert "model.eligibilitySource === 'managed-freellm-chat-canary-required'" in control_center
    assert "Boolean(model.routeAlias)" in control_center


def test_managed_reconcile_accepts_five_and_keeps_ready_routes_unbounded() -> None:
    runtime = (BACKEND / "free_revolver_provider_runtime.py").read_text("utf-8")

    assert "_DEFAULT_MIN_READY_ROUTES = 5" in runtime
    assert "return _DEFAULT_MIN_READY_ROUTES" in runtime
    assert "SOVEREIGN_FREELLM_MIN_READY_ROUTES" not in runtime
    assert "receipt_current" in runtime
    assert "current_ready = []" in runtime
    assert "len(current_ready) + len(ready) >= target_ready_count" not in runtime
    assert "retryAfterSeconds" in runtime
    assert "_reconcile_pace_seconds()" in runtime
    assert "overall_ready_count = int(ready_state.get(\"ready_count\") or 0)" in runtime
    assert "minimum_ready_satisfied = overall_ready_count >= target_ready_count" in runtime
    assert '"minimumReadyRoutes": target_ready_count' in runtime
    assert '"minimumReadySatisfied": minimum_ready_satisfied' in runtime
    assert '"readyRouteCeiling": None' in runtime
    assert '"additionalReadyRoutesAllowed": True' in runtime
    assert '"currentReady": current_ready' in runtime
    assert '"readyCount": overall_ready_count' in runtime
    assert '"ok": minimum_ready_satisfied' in runtime
    assert "200 if minimum_ready_satisfied else 409" in runtime
    assert 'reconcile_stage = "route_activation_parity"' in runtime
    assert "SET disabled=NOT (" in runtime
    assert "route.config->'runtimeIdentity'->>'sourceRevision'=%s" in runtime
    assert "route.config->'runtimeIdentity'->>'imageDigest'=%s" in runtime
    assert "route.config->'canaryReceipt'->>'generalChatEvidenceVerified'='true'" in runtime
    assert "route.config->'canaryReceipt'->>'receiptSha256' ~ '^[0-9a-f]{64}$'" in runtime
    assert '"canaryLatencyMs"' in runtime
    assert '"certificationState": "certified"' in runtime
