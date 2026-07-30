from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime.agent_run_receipts import build_agent_run_receipt, canonical_sha256
from backend.agent_runtime.proof_verdict import (
    AGENT_REPOSITORY_MUTATION_REQUIREMENTS_V1,
    DEFAULT_PROOF_REQUIREMENT_SETS,
    ProofContractError,
    ProofObservation,
    ProofRequirement,
    ProofRequirementSet,
    build_proof_envelope,
    canonical_proof_sha256,
    evaluate_proof,
    observation_from_agent_run_receipt,
)


REVISION = "a" * 40
REPOSITORY = "OuroborosCollective/Sovereign-Studio-ato"
OPERATION_IDENTITY = "repository:issue-1098:proof-core"
INPUT_SHA256 = canonical_proof_sha256({"mission": "Integrate proof core", "revision": REVISION})
DIFF_SHA256 = canonical_proof_sha256({"changed_paths": ["backend/agent_runtime/proof_verdict.py"]})


def _envelope(requirement_set: ProofRequirementSet = AGENT_REPOSITORY_MUTATION_REQUIREMENTS_V1):
    return build_proof_envelope(
        requirement_set=requirement_set,
        operation_identity=OPERATION_IDENTITY,
        repository=REPOSITORY,
        revision=REVISION,
        input_sha256=INPUT_SHA256,
        diff_sha256=DIFF_SHA256,
    )


def _observation(
    *,
    requirement_id: str,
    evidence_kind: str,
    source_kind: str,
    evidence_sha256: str,
    assertion: str = "OBSERVED",
) -> ProofObservation:
    return ProofObservation(
        observation_id=f"{requirement_id}-observation",
        requirement_id=requirement_id,
        evidence_kind=evidence_kind,
        source_kind=source_kind,
        assertion=assertion,
        operation_family="agent_repository_mutation",
        operation_identity=OPERATION_IDENTITY,
        revision=REVISION,
        input_sha256=INPUT_SHA256,
        diff_sha256=DIFF_SHA256,
        evidence_sha256=evidence_sha256,
    )


def _receipt() -> dict:
    return build_agent_run_receipt(
        sequence=0,
        repository=REPOSITORY,
        base_commit_sha=REVISION,
        mcp_revision=REVISION,
        mcp_image_digest="sha256:" + "d" * 64,
        mcp_revision_verified=True,
        agent_run_id="run-proof-core",
        tool_name="repository_apply_search_replace",
        call_id="call-proof-core",
        operation_identity=OPERATION_IDENTITY,
        input_sha256=INPUT_SHA256,
        output_sha256=canonical_sha256({"status": "completed"}),
        diff_sha256=DIFF_SHA256,
        test_evidence_sha256=canonical_sha256({"tests": "passed"}),
        evidence_gate_result="PASS",
        mutation_performed=True,
        observed_effect="workspace-write",
        authoritative_readback_sha256=canonical_sha256({"head": REVISION}),
        previous_receipt_sha256="0" * 64,
    )


def test_complete_exact_evidence_is_the_only_verified_path() -> None:
    envelope = _envelope()
    observations = (
        _observation(
            requirement_id="agent_run_receipt",
            evidence_kind="agent_run_receipt",
            source_kind="AGENT_RUN_RECEIPT",
            evidence_sha256="b" * 64,
        ),
        _observation(
            requirement_id="authoritative_readback",
            evidence_kind="authoritative_readback",
            source_kind="REPOSITORY_READBACK",
            evidence_sha256="c" * 64,
        ),
    )

    verdict = evaluate_proof(envelope, observations, requirement_sets=DEFAULT_PROOF_REQUIREMENT_SETS)

    assert verdict.status == "VERIFIED"
    assert verdict.satisfied_requirements == ("agent_run_receipt", "authoritative_readback")
    assert verdict.missing_requirements == ()
    assert verdict.contradictory_requirements == ()
    assert verdict.finding_codes == ()
    assert verdict.to_dict()["verdict_sha256"] == verdict.verdict_sha256


def test_missing_required_evidence_is_blocked_fail_closed() -> None:
    verdict = evaluate_proof(
        _envelope(),
        (
            _observation(
                requirement_id="agent_run_receipt",
                evidence_kind="agent_run_receipt",
                source_kind="AGENT_RUN_RECEIPT",
                evidence_sha256="b" * 64,
            ),
        ),
        requirement_sets=DEFAULT_PROOF_REQUIREMENT_SETS,
    )

    assert verdict.status == "BLOCKED_BY_MISSING_EVIDENCE"
    assert verdict.satisfied_requirements == ("agent_run_receipt",)
    assert verdict.missing_requirements == ("authoritative_readback",)
    assert verdict.contradictory_requirements == ()


def test_unknown_operation_family_cannot_be_implicitly_allowed() -> None:
    unknown = ProofRequirementSet(
        operation_family="unknown_operation",
        version=1,
        requirements=(
            ProofRequirement(
                requirement_id="runtime_readback",
                evidence_kind="runtime_readback",
                allowed_source_kinds=("RUNTIME_READBACK",),
            ),
        ),
    )

    verdict = evaluate_proof(_envelope(unknown), (), requirement_sets=DEFAULT_PROOF_REQUIREMENT_SETS)

    assert verdict.status == "BLOCKED_BY_MISSING_EVIDENCE"
    assert verdict.missing_requirements == ("registered_requirement_set",)
    assert verdict.finding_codes == ("unknown_operation_family",)


def test_requirement_set_tampering_is_contradicted_before_observations() -> None:
    tampered = replace(_envelope(), requirement_set_sha256="f" * 64)

    verdict = evaluate_proof(tampered, (), requirement_sets=DEFAULT_PROOF_REQUIREMENT_SETS)

    assert verdict.status == "CONTRADICTED"
    assert verdict.contradictory_requirements == ("requirement_set_binding",)
    assert verdict.finding_codes == ("requirement_set_binding_mismatch",)


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("operation_identity", "repository:issue-1098:other-operation"),
        ("revision", "b" * 40),
        ("input_sha256", "d" * 64),
        ("diff_sha256", "e" * 64),
    ],
)
def test_mismatched_operation_revision_or_digest_is_contradicted(field: str, replacement: str) -> None:
    receipt = _observation(
        requirement_id="agent_run_receipt",
        evidence_kind="agent_run_receipt",
        source_kind="AGENT_RUN_RECEIPT",
        evidence_sha256="b" * 64,
    )
    readback = replace(
        _observation(
            requirement_id="authoritative_readback",
            evidence_kind="authoritative_readback",
            source_kind="REPOSITORY_READBACK",
            evidence_sha256="c" * 64,
        ),
        **{field: replacement},
    )

    verdict = evaluate_proof(
        _envelope(),
        (receipt, readback),
        requirement_sets=DEFAULT_PROOF_REQUIREMENT_SETS,
    )

    assert verdict.status == "CONTRADICTED"
    assert verdict.contradictory_requirements == ("authoritative_readback",)
    assert "observation_binding_mismatch" in verdict.finding_codes


def test_static_candidate_cannot_satisfy_a_runtime_requirement() -> None:
    requirement_set = ProofRequirementSet(
        operation_family="runtime_probe",
        version=1,
        requirements=(
            ProofRequirement(
                requirement_id="runtime_readback",
                evidence_kind="runtime_readback",
                allowed_source_kinds=("RUNTIME_READBACK", "STATIC_CANDIDATE"),
                runtime_required=True,
            ),
        ),
    )
    envelope = build_proof_envelope(
        requirement_set=requirement_set,
        operation_identity="runtime:probe:one",
        repository=REPOSITORY,
        revision=REVISION,
        input_sha256=INPUT_SHA256,
        diff_sha256=DIFF_SHA256,
    )
    observation = ProofObservation(
        observation_id="static-probe-candidate",
        requirement_id="runtime_readback",
        evidence_kind="runtime_readback",
        source_kind="STATIC_CANDIDATE",
        assertion="OBSERVED",
        operation_family="runtime_probe",
        operation_identity="runtime:probe:one",
        revision=REVISION,
        input_sha256=INPUT_SHA256,
        diff_sha256=DIFF_SHA256,
        evidence_sha256="b" * 64,
    )

    verdict = evaluate_proof(envelope, (observation,), requirement_sets={"runtime_probe": requirement_set})

    assert verdict.status == "BLOCKED_BY_MISSING_EVIDENCE"
    assert verdict.missing_requirements == ("runtime_readback",)
    assert verdict.finding_codes == ("static_candidate_cannot_satisfy_runtime",)


def test_explicit_negative_observation_is_contradicted() -> None:
    observations = (
        _observation(
            requirement_id="agent_run_receipt",
            evidence_kind="agent_run_receipt",
            source_kind="AGENT_RUN_RECEIPT",
            evidence_sha256="b" * 64,
        ),
        _observation(
            requirement_id="authoritative_readback",
            evidence_kind="authoritative_readback",
            source_kind="RUNTIME_READBACK",
            evidence_sha256="c" * 64,
            assertion="CONTRADICTED",
        ),
    )

    verdict = evaluate_proof(_envelope(), observations, requirement_sets=DEFAULT_PROOF_REQUIREMENT_SETS)

    assert verdict.status == "CONTRADICTED"
    assert verdict.contradictory_requirements == ("authoritative_readback",)
    assert verdict.finding_codes == ("observation_reports_contradiction",)


def test_agent_receipt_adapter_projects_evidence_but_never_a_verdict() -> None:
    observation = observation_from_agent_run_receipt(
        _receipt(),
        observation_id="agent-receipt-adapter",
        requirement_id="agent_run_receipt",
        operation_family="agent_repository_mutation",
        expected_repository=REPOSITORY,
        expected_revision=REVISION,
    )

    assert isinstance(observation, ProofObservation)
    assert observation.assertion == "OBSERVED"
    assert observation.source_kind == "AGENT_RUN_RECEIPT"
    assert "verdict" not in observation.canonical_body()

    verdict = evaluate_proof(
        _envelope(),
        (
            observation,
            _observation(
                requirement_id="authoritative_readback",
                evidence_kind="authoritative_readback",
                source_kind="REPOSITORY_READBACK",
                evidence_sha256="c" * 64,
            ),
        ),
        requirement_sets=DEFAULT_PROOF_REQUIREMENT_SETS,
    )
    assert verdict.status == "VERIFIED"


def test_tampered_agent_receipt_projects_a_contradiction() -> None:
    tampered = deepcopy(_receipt())
    tampered["body"]["base_commit_sha"] = "b" * 40

    observation = observation_from_agent_run_receipt(
        tampered,
        observation_id="tampered-agent-receipt",
        requirement_id="agent_run_receipt",
        operation_family="agent_repository_mutation",
        expected_repository=REPOSITORY,
        expected_revision=REVISION,
    )

    assert observation.assertion == "CONTRADICTED"
    verdict = evaluate_proof(
        _envelope(),
        (observation,),
        requirement_sets=DEFAULT_PROOF_REQUIREMENT_SETS,
    )
    assert verdict.status == "CONTRADICTED"
    assert verdict.contradictory_requirements == ("agent_run_receipt",)


def test_canonical_contract_rejects_floats_secrets_time_and_unordered_values() -> None:
    with pytest.raises(ProofContractError, match="floating-point"):
        canonical_proof_sha256({"score": 1.5})
    with pytest.raises(ProofContractError, match="secret-shaped"):
        canonical_proof_sha256({"api_key": "private"})
    with pytest.raises(ProofContractError, match="implicit time"):
        canonical_proof_sha256({"created_at": 123})
    with pytest.raises(ProofContractError, match="unsupported canonical type"):
        canonical_proof_sha256({"unordered": {"a", "b"}})


def test_contract_objects_are_immutable() -> None:
    envelope = _envelope()
    with pytest.raises(FrozenInstanceError):
        envelope.revision = "b" * 40  # type: ignore[misc]


def test_golden_vectors_are_byte_stable() -> None:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "proof_verdict_golden_vectors.v1.json").read_text("utf-8")
    )
    envelope = _envelope()
    receipt_observation = _observation(
        requirement_id="agent_run_receipt",
        evidence_kind="agent_run_receipt",
        source_kind="AGENT_RUN_RECEIPT",
        evidence_sha256="b" * 64,
    )
    readback_observation = _observation(
        requirement_id="authoritative_readback",
        evidence_kind="authoritative_readback",
        source_kind="REPOSITORY_READBACK",
        evidence_sha256="c" * 64,
    )
    mismatched_readback = replace(readback_observation, revision="d" * 40)

    verified = evaluate_proof(
        envelope,
        (receipt_observation, readback_observation),
        requirement_sets=DEFAULT_PROOF_REQUIREMENT_SETS,
    )
    blocked = evaluate_proof(
        envelope,
        (receipt_observation,),
        requirement_sets=DEFAULT_PROOF_REQUIREMENT_SETS,
    )
    contradicted = evaluate_proof(
        envelope,
        (receipt_observation, mismatched_readback),
        requirement_sets=DEFAULT_PROOF_REQUIREMENT_SETS,
    )

    assert fixture["input_sha256"] == INPUT_SHA256
    assert fixture["diff_sha256"] == DIFF_SHA256
    assert fixture["requirement_set_sha256"] == AGENT_REPOSITORY_MUTATION_REQUIREMENTS_V1.requirement_set_sha256
    assert fixture["envelope_sha256"] == envelope.envelope_sha256
    assert fixture["observation_sha256s"] == {
        "agent_run_receipt": receipt_observation.observation_sha256,
        "authoritative_readback": readback_observation.observation_sha256,
        "mismatched_readback": mismatched_readback.observation_sha256,
    }
    assert fixture["verdict_sha256s"] == {
        "verified": verified.verdict_sha256,
        "blocked": blocked.verdict_sha256,
        "contradicted": contradicted.verdict_sha256,
    }


def test_canonical_and_deployment_proof_core_are_byte_identical() -> None:
    root = Path(__file__).resolve().parents[2]
    canonical = (root / "backend/agent_runtime/proof_verdict.py").read_bytes()
    deployed = (root / "scripts/sovereign-backend/agent_runtime/proof_verdict.py").read_bytes()
    assert canonical == deployed
