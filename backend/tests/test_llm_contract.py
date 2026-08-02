from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.llm_contract import (
    ROUTE_CLASS_FREELLM_FREE,
    ROUTE_CLASS_OPENROUTER_PAID,
    ZERO_SHA256,
    LlmContractError,
    LlmOutputContract,
    LlmSemanticObservation,
    build_request_envelope,
    build_route_binding,
    compile_contract_prompt,
    verify_llm_response,
)
from agent_runtime.provider_neutral_runtime import canonical_sha256
from llm_transport import FREELLM_BASE_URL, OPENROUTER_BASE_URL

REVISION = "a" * 40


def _route(*, transport: str) -> dict:
    paid = transport == "openrouter"
    category = "standard" if paid else "free"
    return {
        "id": f"{transport}-route",
        "model_id": f"{transport}-alias",
        "provider": transport,
        "runtime_kind": transport,
        "base_url": OPENROUTER_BASE_URL if paid else FREELLM_BASE_URL,
        "disabled": False,
        "config": {
            "transport": transport,
            "direct": True,
            "catalogVerified": paid,
            "transportCanaryVerified": paid,
            "selectable": paid,
            "supportedExecutionRoles": ["main", "swarm_agents"] if paid else ["free_single_agent"],
            "providerPolicy": (
                {
                    "require_parameters": True,
                    "allow_fallbacks": False,
                    "data_collection": "deny",
                    "zdr": True,
                }
                if paid
                else {}
            ),
            "providerModel": "openai/gpt-5.4-mini" if paid else "free-model",
            "executionProfile": "paid_swarm_6" if paid else "free_single_agent",
            "billingCategory": category,
            "fundingMode": "provider_priced" if paid else "provider_free_quota",
            "pricingVerified": paid,
            "pricingSource": "test" if paid else "not-applicable-free-quota",
            **(
                {
                    "inputUsdPerMillion": 1,
                    "cachedInputUsdPerMillion": 0,
                    "outputUsdPerMillion": 4,
                    "markupMultiplier": 4,
                }
                if paid
                else {}
            ),
        },
    }


def _contract(*requirements: str) -> LlmOutputContract:
    return LlmOutputContract(
        contract_id="mission.intent",
        version=1,
        semantic_requirement_ids=tuple(requirements),
        json_schema={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["conversation", "read_only_analysis", "repository_execution"],
                },
                "normalizedGoal": {"type": "string", "minLength": 1, "maxLength": 2000},
                "requiresOnlineTools": {"type": "boolean"},
                "requiresRepositoryWorkspace": {"type": "boolean"},
                "learningScope": {
                    "type": "array",
                    "maxItems": 12,
                    "items": {"type": "string", "maxLength": 160},
                },
            },
            "required": [
                "mode",
                "normalizedGoal",
                "requiresOnlineTools",
                "requiresRepositoryWorkspace",
                "learningScope",
            ],
            "additionalProperties": False,
        },
    )


def _payload() -> dict:
    return {
        "mode": "read_only_analysis",
        "normalizedGoal": "Inspect exact runtime evidence.",
        "requiresOnlineTools": True,
        "requiresRepositoryWorkspace": False,
        "learningScope": [],
    }


def test_paid_and_free_bindings_share_contract_but_keep_route_truth_separate() -> None:
    paid = build_route_binding(_route(transport="openrouter"), source_revision=REVISION)
    free = build_route_binding(_route(transport="freellm"), source_revision=REVISION)

    assert paid.route_class == ROUTE_CLASS_OPENROUTER_PAID
    assert paid.transport == "openrouter"
    assert paid.price_snapshot_sha256 != ZERO_SHA256
    assert free.route_class == ROUTE_CLASS_FREELLM_FREE
    assert free.transport == "freellm"
    assert free.price_snapshot_sha256 == ZERO_SHA256
    assert paid.binding_sha256 != free.binding_sha256


def test_route_binding_rejects_unverified_revision_and_unverified_route() -> None:
    with pytest.raises(LlmContractError, match="Git SHA-40"):
        build_route_binding(_route(transport="openrouter"), source_revision="main")

    route = _route(transport="openrouter")
    route["config"]["transportCanaryVerified"] = False
    with pytest.raises(LlmContractError, match="active verified"):
        build_route_binding(route, source_revision=REVISION)


def test_request_hash_is_stable_and_changes_with_prompt_revision_or_schema() -> None:
    contract = _contract()
    binding = build_route_binding(_route(transport="openrouter"), source_revision=REVISION)
    first = build_request_envelope(
        operation_identity="intent.route",
        route_binding=binding,
        prompt="Classify this mission.",
        contract=contract,
        context={"runId": "run-1", "tick": 7},
    )
    repeated = build_request_envelope(
        operation_identity="intent.route",
        route_binding=binding,
        prompt="Classify this mission.",
        contract=contract,
        context={"tick": 7, "runId": "run-1"},
    )
    changed_prompt = build_request_envelope(
        operation_identity="intent.route",
        route_binding=binding,
        prompt="Classify a different mission.",
        contract=contract,
        context={"runId": "run-1", "tick": 7},
    )

    assert first.request_sha256 == repeated.request_sha256
    assert first.request_sha256 != changed_prompt.request_sha256
    assert first.route_binding.source_revision == REVISION


def test_contract_schema_rejects_float_and_open_object_escape_hatches() -> None:
    with pytest.raises(LlmContractError, match="additionalProperties=false"):
        LlmOutputContract(
            contract_id="open.object",
            version=1,
            json_schema={"type": "object", "properties": {}, "required": []},
        )

    with pytest.raises(LlmContractError, match="non-negative integer"):
        LlmOutputContract(
            contract_id="float.bound",
            version=1,
            json_schema={
                "type": "object",
                "properties": {"score": {"type": "integer", "maximum": 0.5}},
                "required": ["score"],
                "additionalProperties": False,
            },
        )


def test_schema_only_response_is_verified_for_paid_and_free_routes() -> None:
    contract = _contract()
    for transport in ("openrouter", "freellm"):
        binding = build_route_binding(_route(transport=transport), source_revision=REVISION)
        envelope = build_request_envelope(
            operation_identity="intent.route",
            route_binding=binding,
            prompt="Classify the bounded mission.",
            contract=contract,
        )
        verification = verify_llm_response(
            envelope=envelope,
            contract=contract,
            response=_payload(),
        )

        assert verification.accepted is True
        assert verification.receipt.verdict == "VERIFIED"
        assert verification.receipt.verification_scope == "SCHEMA_ONLY"
        assert verification.receipt.source_revision == REVISION
        assert verification.receipt.route_binding_sha256 == binding.binding_sha256
        assert verification.receipt.contract_output_sha256 == canonical_sha256(_payload())
        assert "schema_valid" in verification.receipt.finding_codes


def test_fenced_json_is_locally_verified_but_extra_fields_are_contradicted() -> None:
    contract = _contract()
    binding = build_route_binding(_route(transport="freellm"), source_revision=REVISION)
    envelope = build_request_envelope(
        operation_identity="intent.route",
        route_binding=binding,
        prompt="Classify the bounded mission.",
        contract=contract,
    )
    fenced = "```json\n" + __import__("json").dumps(_payload()) + "\n```"
    accepted = verify_llm_response(
        envelope=envelope,
        contract=contract,
        response=fenced,
    )
    rejected = verify_llm_response(
        envelope=envelope,
        contract=contract,
        response={**_payload(), "providerSaysSuccess": True},
    )

    assert accepted.accepted is True
    assert rejected.accepted is False
    assert rejected.receipt.verdict == "CONTRADICTED"
    assert rejected.receipt.contradicted_requirements == ("output_schema",)
    assert rejected.receipt.contract_output_sha256 == ZERO_SHA256
    assert "schema_invalid" in rejected.receipt.finding_codes


def test_semantic_requirements_fail_closed_until_hash_bound_evidence_is_observed() -> None:
    contract = _contract("runtime.readback")
    binding = build_route_binding(_route(transport="openrouter"), source_revision=REVISION)
    envelope = build_request_envelope(
        operation_identity="intent.route",
        route_binding=binding,
        prompt="Classify the bounded mission.",
        contract=contract,
    )

    missing = verify_llm_response(
        envelope=envelope,
        contract=contract,
        response=_payload(),
    )
    observed = verify_llm_response(
        envelope=envelope,
        contract=contract,
        response=_payload(),
        observations=(
            LlmSemanticObservation(
                requirement_id="runtime.readback",
                assertion="OBSERVED",
                source="runtime.readback",
                value_sha256=canonical_sha256({"status": "ready", "revision": REVISION}),
            ),
        ),
    )
    contradicted = verify_llm_response(
        envelope=envelope,
        contract=contract,
        response=_payload(),
        observations=(
            LlmSemanticObservation(
                requirement_id="runtime.readback",
                assertion="CONTRADICTED",
                source="runtime.readback",
                value_sha256=canonical_sha256({"status": "stale", "revision": "b" * 40}),
            ),
        ),
    )

    assert missing.receipt.verdict == "BLOCKED_BY_MISSING_EVIDENCE"
    assert missing.receipt.missing_requirements == ("runtime.readback",)
    assert observed.accepted is True
    assert observed.receipt.verification_scope == "SCHEMA_AND_SEMANTICS"
    assert observed.receipt.satisfied_requirements == ("runtime.readback",)
    assert contradicted.receipt.verdict == "CONTRADICTED"
    assert contradicted.receipt.contradicted_requirements == ("runtime.readback",)


def test_compiled_prompt_binds_hashes_without_claiming_provider_enforcement() -> None:
    contract = _contract()
    binding = build_route_binding(_route(transport="openrouter"), source_revision=REVISION)
    envelope = build_request_envelope(
        operation_identity="intent.route",
        route_binding=binding,
        prompt="Classify the bounded mission.",
        contract=contract,
    )
    compiled = compile_contract_prompt(
        envelope=envelope,
        contract=contract,
        prompt="Classify the bounded mission.",
    )

    assert envelope.request_sha256 in compiled
    assert binding.binding_sha256 in compiled
    assert contract.contract_sha256 in compiled
    assert REVISION in compiled
    assert "Return exactly one JSON value" in compiled
    assert contract.response_format()["json_schema"]["strict"] is True
