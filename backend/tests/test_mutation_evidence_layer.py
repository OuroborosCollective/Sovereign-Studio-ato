from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime.mutation_evidence_layer import (
    MUTATION_FAMILY_IDS,
    MUTATION_REQUIREMENT_REGISTRY_SHA256,
    MUTATION_REQUIREMENT_SETS_V1,
    build_mutation_proof_envelope,
    evaluate_mutation_evidence,
    mutation_requirement_registry_snapshot,
    mutation_requirement_set,
)
from backend.agent_runtime.proof_verdict import (
    ProofContractError,
    ProofObservation,
    canonical_proof_sha256,
)


REVISION = "a" * 40
REPOSITORY = "OuroborosCollective/Sovereign-Studio-ato"
INPUT_SHA256 = canonical_proof_sha256({"mission": "bind mutation requirements", "revision": REVISION})
DIFF_SHA256 = canonical_proof_sha256({"changed_paths": ["backend/agent_runtime/mutation_evidence_layer.py"]})
EXPECTED_FAMILIES = (
    "canonical_mirror_ownership",
    "fleet_deployment",
    "github_merge_release",
    "mcp_registry_self_update",
    "postgres_pgvector_mutation",
    "provider_routing_mutation",
    "security_permission_change",
    "sovereign_rescue_repair",
)


def _envelope(family: str):
    return build_mutation_proof_envelope(
        operation_family=family,
        operation_identity=f"mutation:{family}:one",
        repository=REPOSITORY,
        revision=REVISION,
        input_sha256=INPUT_SHA256,
        diff_sha256=DIFF_SHA256,
    )


def _observations(family: str) -> tuple[ProofObservation, ...]:
    requirement_set = mutation_requirement_set(family)
    return tuple(
        ProofObservation(
            observation_id=f"{requirement.requirement_id}-observation",
            requirement_id=requirement.requirement_id,
            evidence_kind=requirement.evidence_kind,
            source_kind=requirement.allowed_source_kinds[0],
            assertion="OBSERVED",
            operation_family=family,
            operation_identity=f"mutation:{family}:one",
            revision=REVISION,
            input_sha256=INPUT_SHA256,
            diff_sha256=DIFF_SHA256,
            evidence_sha256=canonical_proof_sha256(
                {
                    "family": family,
                    "requirement": requirement.requirement_id,
                    "source": requirement.allowed_source_kinds[0],
                }
            ),
        )
        for requirement in requirement_set.requirements
    )


def test_registry_contains_exactly_the_eight_declared_families() -> None:
    assert MUTATION_FAMILY_IDS == EXPECTED_FAMILIES
    assert tuple(MUTATION_REQUIREMENT_SETS_V1) == EXPECTED_FAMILIES
    assert all(item.version == 1 for item in MUTATION_REQUIREMENT_SETS_V1.values())


def test_registry_projection_is_sorted_secret_free_and_hash_stable() -> None:
    first = mutation_requirement_registry_snapshot()
    second = mutation_requirement_registry_snapshot()

    assert first == second
    assert first["schema_version"] == "sovereign.mutation-evidence-requirement-registry.v1"
    assert [item["operation_family"] for item in first["families"]] == list(EXPECTED_FAMILIES)
    assert canonical_proof_sha256(first) == MUTATION_REQUIREMENT_REGISTRY_SHA256


def test_requirement_registry_is_runtime_immutable() -> None:
    with pytest.raises(TypeError):
        MUTATION_REQUIREMENT_SETS_V1["unexpected"] = mutation_requirement_set("fleet_deployment")  # type: ignore[index]


def test_unknown_family_is_never_implicitly_allowed() -> None:
    with pytest.raises(ProofContractError, match="unknown mutation operation family"):
        mutation_requirement_set("unknown_family")


@pytest.mark.parametrize("family", EXPECTED_FAMILIES)
def test_every_family_blocks_when_required_evidence_is_missing(family: str) -> None:
    envelope = _envelope(family)

    verdict = evaluate_mutation_evidence(envelope, ())

    assert verdict.status == "BLOCKED_BY_MISSING_EVIDENCE"
    assert verdict.satisfied_requirements == ()
    assert verdict.missing_requirements == mutation_requirement_set(family).requirement_ids
    assert verdict.contradictory_requirements == ()


@pytest.mark.parametrize("family", EXPECTED_FAMILIES)
def test_every_family_verifies_only_with_complete_exact_observations(family: str) -> None:
    envelope = _envelope(family)

    verdict = evaluate_mutation_evidence(envelope, _observations(family))

    assert verdict.status == "VERIFIED"
    assert verdict.satisfied_requirements == mutation_requirement_set(family).requirement_ids
    assert verdict.missing_requirements == ()
    assert verdict.contradictory_requirements == ()


def test_one_stale_observation_contradicts_the_bound_family() -> None:
    family = "mcp_registry_self_update"
    observations = list(_observations(family))
    observations[-1] = replace(observations[-1], revision="b" * 40)

    verdict = evaluate_mutation_evidence(_envelope(family), tuple(observations))

    assert verdict.status == "CONTRADICTED"
    assert observations[-1].requirement_id in verdict.contradictory_requirements
    assert "observation_binding_mismatch" in verdict.finding_codes


def test_static_candidate_cannot_replace_a_runtime_route_canary() -> None:
    family = "provider_routing_mutation"
    observations = list(_observations(family))
    route_index = next(
        index
        for index, item in enumerate(observations)
        if item.requirement_id == "route_canary"
    )
    observations[route_index] = replace(
        observations[route_index],
        source_kind="STATIC_CANDIDATE",
    )

    verdict = evaluate_mutation_evidence(_envelope(family), tuple(observations))

    assert verdict.status == "BLOCKED_BY_MISSING_EVIDENCE"
    assert "route_canary" in verdict.missing_requirements
    assert "observation_source_not_allowed" in verdict.finding_codes


def test_static_no_litellm_contract_is_not_promoted_to_route_capability() -> None:
    requirement_set = mutation_requirement_set("provider_routing_mutation")
    static_requirement = next(
        item for item in requirement_set.requirements if item.requirement_id == "no_litellm_static_contract"
    )
    route_requirement = next(item for item in requirement_set.requirements if item.requirement_id == "route_canary")

    assert static_requirement.runtime_required is False
    assert static_requirement.allowed_source_kinds == ("REPOSITORY_READBACK", "STATIC_CANDIDATE")
    assert route_requirement.runtime_required is True
    assert "STATIC_CANDIDATE" not in route_requirement.allowed_source_kinds


def test_canonical_and_deployment_mutation_layers_are_byte_identical() -> None:
    canonical = (ROOT / "backend/agent_runtime/mutation_evidence_layer.py").read_bytes()
    deployed = (ROOT / "scripts/sovereign-backend/agent_runtime/mutation_evidence_layer.py").read_bytes()
    assert canonical == deployed


def test_canonical_and_deployment_package_exports_are_byte_identical() -> None:
    canonical = (ROOT / "backend/agent_runtime/__init__.py").read_bytes()
    deployed = (ROOT / "scripts/sovereign-backend/agent_runtime/__init__.py").read_bytes()
    assert canonical == deployed
