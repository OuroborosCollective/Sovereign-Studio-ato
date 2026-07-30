"""Tests for the eight Sovereign mutation evidence requirement sets.

All tests are deterministic: no clock, no I/O beyond reading source files
for the byte-identity check.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime.mutation_evidence_layer import (
    ALL_MUTATION_REQUIREMENT_SETS,
    CANONICAL_MIRROR_OWNERSHIP_REQUIREMENTS_V1,
    DOCKER_VPS_PATCHMON_DEPLOYMENT_REQUIREMENTS_V1,
    GITHUB_MERGE_RELEASE_REQUIREMENTS_V1,
    MCP_REGISTRY_SELF_UPDATE_REQUIREMENTS_V1,
    OPENROUTER_FREEROUTE_REVOLVER_REQUIREMENTS_V1,
    POSTGRESQL_MIGRATIONS_PGVECTOR_REQUIREMENTS_V1,
    SECURITY_PERMISSION_CHANGE_REQUIREMENTS_V1,
    SOVEREIGN_RESCUE_REPAIR_REQUIREMENTS_V1,
)
from backend.agent_runtime.proof_verdict import (
    ProofObservation,
    ProofRequirementSet,
    build_proof_envelope,
    canonical_proof_sha256,
    evaluate_proof,
)

REVISION: str = "c" * 40
REPOSITORY: str = "OuroborosCollective/Sovereign-Studio-ato"
INPUT_SHA256: str = canonical_proof_sha256({"mission": "test-mutation-evidence-layer"})
DIFF_SHA256: str = canonical_proof_sha256(
    {"changed_paths": ["backend/agent_runtime/mutation_evidence_layer.py"]}
)

_SOURCE_MAP: dict[str, str] = {
    "agent_run_receipt": "AGENT_RUN_RECEIPT",
    "ci_readback": "CI_READBACK",
    "repository_readback": "REPOSITORY_READBACK",
    "mcp_readback": "MCP_READBACK",
    "image_readback": "IMAGE_READBACK",
    "patchmon_readback": "PATCHMON_READBACK",
    "database_readback": "DATABASE_READBACK",
    "runtime_readback": "RUNTIME_READBACK",
}


def _observation(
    req_set: ProofRequirementSet,
    *,
    requirement_id: str,
    evidence_kind: str,
    source_kind: str,
    evidence_sha256: str = "a" * 64,
    assertion: str = "OBSERVED",
    revision: str = REVISION,
) -> ProofObservation:
    return ProofObservation(
        observation_id=f"{requirement_id}-obs",
        requirement_id=requirement_id,
        evidence_kind=evidence_kind,
        source_kind=source_kind,
        assertion=assertion,
        operation_family=req_set.operation_family,
        operation_identity=f"test:{req_set.operation_family}",
        revision=revision,
        input_sha256=INPUT_SHA256,
        diff_sha256=DIFF_SHA256,
        evidence_sha256=evidence_sha256,
    )


def _full_observations(req_set: ProofRequirementSet) -> tuple[ProofObservation, ...]:
    return tuple(
        _observation(
            req_set,
            requirement_id=req.requirement_id,
            evidence_kind=req.evidence_kind,
            source_kind=_SOURCE_MAP[req.evidence_kind],
        )
        for req in req_set.requirements
    )


def _envelope(req_set: ProofRequirementSet):
    return build_proof_envelope(
        requirement_set=req_set,
        operation_identity=f"test:{req_set.operation_family}",
        repository=REPOSITORY,
        revision=REVISION,
        input_sha256=INPUT_SHA256,
        diff_sha256=DIFF_SHA256,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Registry completeness
# ─────────────────────────────────────────────────────────────────────────────


def test_all_mutation_requirement_sets_contains_eight_families() -> None:
    assert len(ALL_MUTATION_REQUIREMENT_SETS) == 8


def test_all_family_names_are_canonical_identifiers() -> None:
    import re
    pattern = re.compile(r"^[a-z][a-z0-9_.:-]{1,119}$")
    for family in ALL_MUTATION_REQUIREMENT_SETS:
        assert pattern.fullmatch(family), f"Non-canonical family name: {family!r}"


def test_all_families_require_agent_run_receipt() -> None:
    for family, req_set in ALL_MUTATION_REQUIREMENT_SETS.items():
        ids = [r.requirement_id for r in req_set.requirements]
        assert "agent_run_receipt" in ids, f"{family} missing agent_run_receipt"


def test_all_families_have_at_least_two_requirements() -> None:
    for family, req_set in ALL_MUTATION_REQUIREMENT_SETS.items():
        assert len(req_set.requirements) >= 2, (
            f"{family} has only {len(req_set.requirements)} requirement(s)"
        )


def test_all_requirements_are_runtime_required() -> None:
    for family, req_set in ALL_MUTATION_REQUIREMENT_SETS.items():
        for req in req_set.requirements:
            assert req.runtime_required, (
                f"{family}/{req.requirement_id} must be runtime_required"
            )


def test_requirement_ids_are_unique_within_each_family() -> None:
    for family, req_set in ALL_MUTATION_REQUIREMENT_SETS.items():
        ids = [r.requirement_id for r in req_set.requirements]
        assert len(ids) == len(set(ids)), f"{family} has duplicate requirement_ids"


def test_eight_family_constants_are_registered() -> None:
    expected = {
        GITHUB_MERGE_RELEASE_REQUIREMENTS_V1.operation_family,
        SOVEREIGN_RESCUE_REPAIR_REQUIREMENTS_V1.operation_family,
        MCP_REGISTRY_SELF_UPDATE_REQUIREMENTS_V1.operation_family,
        DOCKER_VPS_PATCHMON_DEPLOYMENT_REQUIREMENTS_V1.operation_family,
        POSTGRESQL_MIGRATIONS_PGVECTOR_REQUIREMENTS_V1.operation_family,
        OPENROUTER_FREEROUTE_REVOLVER_REQUIREMENTS_V1.operation_family,
        CANONICAL_MIRROR_OWNERSHIP_REQUIREMENTS_V1.operation_family,
        SECURITY_PERMISSION_CHANGE_REQUIREMENTS_V1.operation_family,
    }
    assert set(ALL_MUTATION_REQUIREMENT_SETS.keys()) == expected


# ─────────────────────────────────────────────────────────────────────────────
# VERIFIED – full evidence for every family
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("req_set", list(ALL_MUTATION_REQUIREMENT_SETS.values()))
def test_full_evidence_yields_verified(req_set: ProofRequirementSet) -> None:
    verdict = evaluate_proof(
        _envelope(req_set),
        _full_observations(req_set),
        requirement_sets=ALL_MUTATION_REQUIREMENT_SETS,
    )
    assert verdict.status == "VERIFIED", (
        f"{req_set.operation_family}: expected VERIFIED, got {verdict.status} "
        f"(findings={verdict.finding_codes})"
    )
    assert verdict.missing_requirements == ()
    assert verdict.contradictory_requirements == ()


# ─────────────────────────────────────────────────────────────────────────────
# Fail-closed – empty observations always yield BLOCKED_BY_MISSING_EVIDENCE
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("req_set", list(ALL_MUTATION_REQUIREMENT_SETS.values()))
def test_empty_observations_yield_blocked(req_set: ProofRequirementSet) -> None:
    verdict = evaluate_proof(
        _envelope(req_set),
        (),
        requirement_sets=ALL_MUTATION_REQUIREMENT_SETS,
    )
    assert verdict.status == "BLOCKED_BY_MISSING_EVIDENCE", (
        f"{req_set.operation_family}: expected BLOCKED, got {verdict.status}"
    )
    assert len(verdict.missing_requirements) == len(req_set.requirements)


# ─────────────────────────────────────────────────────────────────────────────
# CONTRADICTED – mismatched revision contaminates any family
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("req_set", list(ALL_MUTATION_REQUIREMENT_SETS.values()))
def test_mismatched_revision_yields_contradicted(req_set: ProofRequirementSet) -> None:
    good = list(_full_observations(req_set))
    # Corrupt the revision on the second observation.
    good[1] = replace(good[1], revision="d" * 40)
    verdict = evaluate_proof(
        _envelope(req_set),
        tuple(good),
        requirement_sets=ALL_MUTATION_REQUIREMENT_SETS,
    )
    assert verdict.status == "CONTRADICTED", (
        f"{req_set.operation_family}: expected CONTRADICTED, got {verdict.status}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Family-specific structural checks
# ─────────────────────────────────────────────────────────────────────────────


def test_github_merge_release_requires_three_evidence_kinds() -> None:
    ids = {r.requirement_id for r in GITHUB_MERGE_RELEASE_REQUIREMENTS_V1.requirements}
    assert ids == {"agent_run_receipt", "ci_readback", "repository_readback"}


def test_docker_vps_patchmon_deployment_requires_three_evidence_kinds() -> None:
    ids = {r.requirement_id for r in DOCKER_VPS_PATCHMON_DEPLOYMENT_REQUIREMENTS_V1.requirements}
    assert ids == {"agent_run_receipt", "image_readback", "patchmon_readback"}


def test_security_permission_change_requires_three_evidence_kinds() -> None:
    ids = {r.requirement_id for r in SECURITY_PERMISSION_CHANGE_REQUIREMENTS_V1.requirements}
    assert ids == {"agent_run_receipt", "ci_readback", "runtime_readback"}


def test_mcp_registry_self_update_requires_mcp_readback() -> None:
    ids = {r.requirement_id for r in MCP_REGISTRY_SELF_UPDATE_REQUIREMENTS_V1.requirements}
    assert "mcp_readback" in ids


def test_postgresql_migrations_pgvector_requires_database_readback() -> None:
    ids = {r.requirement_id for r in POSTGRESQL_MIGRATIONS_PGVECTOR_REQUIREMENTS_V1.requirements}
    assert "database_readback" in ids


# ─────────────────────────────────────────────────────────────────────────────
# Partial evidence – exactly one missing requirement blocks the verdict
# ─────────────────────────────────────────────────────────────────────────────


def test_missing_one_requirement_yields_blocked() -> None:
    req_set = GITHUB_MERGE_RELEASE_REQUIREMENTS_V1
    all_obs = list(_full_observations(req_set))
    # Remove the ci_readback observation.
    trimmed = [o for o in all_obs if o.requirement_id != "ci_readback"]
    verdict = evaluate_proof(
        _envelope(req_set),
        tuple(trimmed),
        requirement_sets=ALL_MUTATION_REQUIREMENT_SETS,
    )
    assert verdict.status == "BLOCKED_BY_MISSING_EVIDENCE"
    assert "ci_readback" in verdict.missing_requirements


# ─────────────────────────────────────────────────────────────────────────────
# Byte-equality: canonical == deployment mirror
# ─────────────────────────────────────────────────────────────────────────────


def test_canonical_and_deployment_mutation_layer_are_byte_identical() -> None:
    canonical = (ROOT / "backend/agent_runtime/mutation_evidence_layer.py").read_bytes()
    deployed = (ROOT / "scripts/sovereign-backend/agent_runtime/mutation_evidence_layer.py").read_bytes()
    assert canonical == deployed, (
        "mutation_evidence_layer.py: canonical and deployment mirror must be byte-identical"
    )
