"""Versioned proof requirements for declared high-risk Sovereign mutations.

This module is deliberately thin. It does not collect evidence, access a
network, database, filesystem, clock or random source, and it does not enforce a
mutation. It only binds the eight operation families from issue #1097 to the
existing pure proof-verdict core. Collectors and protected write-path adapters
remain owned by issues #1099 through #1103.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final, Mapping, Sequence

from .proof_verdict import (
    ProofContractError,
    ProofEnvelope,
    ProofObservation,
    ProofRequirement,
    ProofRequirementSet,
    ProofVerdict,
    build_proof_envelope,
    canonical_proof_sha256,
    evaluate_proof,
)


_SCHEMA_REGISTRY: Final[str] = "sovereign.mutation-evidence-requirement-registry.v1"


def _requirement(
    requirement_id: str,
    evidence_kind: str,
    *allowed_source_kinds: str,
    runtime_required: bool = True,
) -> ProofRequirement:
    return ProofRequirement(
        requirement_id=requirement_id,
        evidence_kind=evidence_kind,
        allowed_source_kinds=tuple(allowed_source_kinds),
        runtime_required=runtime_required,
    )


def _set(operation_family: str, *requirements: ProofRequirement) -> ProofRequirementSet:
    return ProofRequirementSet(
        operation_family=operation_family,
        version=1,
        requirements=tuple(requirements),
    )


GITHUB_MERGE_RELEASE_REQUIREMENTS_V1: Final[ProofRequirementSet] = _set(
    "github_merge_release",
    _requirement("owner_authorization", "owner_authorization", "AGENT_RUN_RECEIPT", "REPOSITORY_READBACK"),
    _requirement("repository_baseline", "repository_baseline", "REPOSITORY_READBACK"),
    _requirement("input_diff_identity", "input_diff_identity", "AGENT_RUN_RECEIPT", "REPOSITORY_READBACK"),
    _requirement("exact_head_ci", "exact_head_ci", "CI_READBACK"),
    _requirement("mutation_readback", "mutation_readback", "REPOSITORY_READBACK", "CI_READBACK"),
    _requirement("capability_delta", "capability_delta", "REPOSITORY_READBACK", "RUNTIME_READBACK"),
)

SOVEREIGN_RESCUE_REPAIR_REQUIREMENTS_V1: Final[ProofRequirementSet] = _set(
    "sovereign_rescue_repair",
    _requirement("owner_authorization", "owner_authorization", "AGENT_RUN_RECEIPT", "REPOSITORY_READBACK"),
    _requirement("diagnostic_baseline", "diagnostic_baseline", "AGENT_RUN_RECEIPT", "RUNTIME_READBACK"),
    _requirement("agent_run_receipt", "agent_run_receipt", "AGENT_RUN_RECEIPT"),
    _requirement("input_diff_identity", "input_diff_identity", "AGENT_RUN_RECEIPT", "REPOSITORY_READBACK"),
    _requirement("exact_head_ci", "exact_head_ci", "CI_READBACK"),
    _requirement("repair_readback", "repair_readback", "REPOSITORY_READBACK", "RUNTIME_READBACK", "CI_READBACK"),
    _requirement("capability_delta", "capability_delta", "REPOSITORY_READBACK", "RUNTIME_READBACK"),
)

MCP_REGISTRY_SELF_UPDATE_REQUIREMENTS_V1: Final[ProofRequirementSet] = _set(
    "mcp_registry_self_update",
    _requirement("owner_authorization", "owner_authorization", "AGENT_RUN_RECEIPT", "REPOSITORY_READBACK"),
    _requirement("source_runtime_revision", "source_runtime_revision", "MCP_READBACK", "REPOSITORY_READBACK"),
    _requirement("immutable_image", "immutable_image", "IMAGE_READBACK"),
    _requirement("mcp_runtime_canary", "mcp_runtime_canary", "MCP_READBACK", "RUNTIME_READBACK"),
    _requirement("rollback_reference", "rollback_reference", "IMAGE_READBACK", "RUNTIME_READBACK"),
    _requirement("capability_delta", "capability_delta", "MCP_READBACK", "RUNTIME_READBACK"),
)

FLEET_DEPLOYMENT_REQUIREMENTS_V1: Final[ProofRequirementSet] = _set(
    "fleet_deployment",
    _requirement("owner_authorization", "owner_authorization", "AGENT_RUN_RECEIPT", "REPOSITORY_READBACK"),
    _requirement("source_runtime_revision", "source_runtime_revision", "REPOSITORY_READBACK", "RUNTIME_READBACK"),
    _requirement("immutable_image", "immutable_image", "IMAGE_READBACK"),
    _requirement("fleet_readback", "fleet_readback", "PATCHMON_READBACK", "RUNTIME_READBACK"),
    _requirement("rollback_reference", "rollback_reference", "IMAGE_READBACK", "RUNTIME_READBACK"),
    _requirement("capability_delta", "capability_delta", "PATCHMON_READBACK", "RUNTIME_READBACK"),
)

POSTGRES_PGVECTOR_MUTATION_REQUIREMENTS_V1: Final[ProofRequirementSet] = _set(
    "postgres_pgvector_mutation",
    _requirement("owner_authorization", "owner_authorization", "AGENT_RUN_RECEIPT", "REPOSITORY_READBACK"),
    _requirement("migration_identity", "migration_identity", "REPOSITORY_READBACK"),
    _requirement("schema_baseline", "schema_baseline", "DATABASE_READBACK"),
    _requirement("database_readback", "database_readback", "DATABASE_READBACK"),
    _requirement("rollback_reference", "rollback_reference", "DATABASE_READBACK", "REPOSITORY_READBACK"),
    _requirement("domain_isolation", "domain_isolation", "DATABASE_READBACK", "REPOSITORY_READBACK"),
    _requirement("capability_delta", "capability_delta", "DATABASE_READBACK", "RUNTIME_READBACK"),
)

PROVIDER_ROUTING_MUTATION_REQUIREMENTS_V1: Final[ProofRequirementSet] = _set(
    "provider_routing_mutation",
    _requirement("owner_authorization", "owner_authorization", "AGENT_RUN_RECEIPT", "REPOSITORY_READBACK"),
    _requirement("provider_boundary", "provider_boundary", "REPOSITORY_READBACK", "RUNTIME_READBACK"),
    _requirement("route_canary", "route_canary", "RUNTIME_READBACK"),
    _requirement("routing_readback", "routing_readback", "RUNTIME_READBACK"),
    _requirement(
        "no_litellm_static_contract",
        "no_litellm_static_contract",
        "STATIC_CANDIDATE",
        "REPOSITORY_READBACK",
        runtime_required=False,
    ),
    _requirement("capability_delta", "capability_delta", "REPOSITORY_READBACK", "RUNTIME_READBACK"),
)

CANONICAL_MIRROR_OWNERSHIP_REQUIREMENTS_V1: Final[ProofRequirementSet] = _set(
    "canonical_mirror_ownership",
    _requirement(
        "repository_baseline",
        "repository_baseline",
        "REPOSITORY_READBACK",
        runtime_required=False,
    ),
    _requirement(
        "mirror_readback",
        "mirror_readback",
        "REPOSITORY_READBACK",
        runtime_required=False,
    ),
    _requirement(
        "ownership_readback",
        "ownership_readback",
        "REPOSITORY_READBACK",
        runtime_required=False,
    ),
    _requirement("exact_head_ci", "exact_head_ci", "CI_READBACK"),
)

SECURITY_PERMISSION_CHANGE_REQUIREMENTS_V1: Final[ProofRequirementSet] = _set(
    "security_permission_change",
    _requirement("owner_authorization", "owner_authorization", "AGENT_RUN_RECEIPT", "REPOSITORY_READBACK"),
    _requirement("permission_baseline", "permission_baseline", "REPOSITORY_READBACK", "RUNTIME_READBACK"),
    _requirement("negative_access_test", "negative_access_test", "CI_READBACK", "RUNTIME_READBACK"),
    _requirement("permission_readback", "permission_readback", "REPOSITORY_READBACK", "RUNTIME_READBACK"),
    _requirement("capability_delta", "capability_delta", "REPOSITORY_READBACK", "RUNTIME_READBACK"),
)


_MUTATION_REQUIREMENT_SETS = {
    item.operation_family: item
    for item in sorted(
        (
            GITHUB_MERGE_RELEASE_REQUIREMENTS_V1,
            SOVEREIGN_RESCUE_REPAIR_REQUIREMENTS_V1,
            MCP_REGISTRY_SELF_UPDATE_REQUIREMENTS_V1,
            FLEET_DEPLOYMENT_REQUIREMENTS_V1,
            POSTGRES_PGVECTOR_MUTATION_REQUIREMENTS_V1,
            PROVIDER_ROUTING_MUTATION_REQUIREMENTS_V1,
            CANONICAL_MIRROR_OWNERSHIP_REQUIREMENTS_V1,
            SECURITY_PERMISSION_CHANGE_REQUIREMENTS_V1,
        ),
        key=lambda requirement_set: requirement_set.operation_family,
    )
}
MUTATION_REQUIREMENT_SETS_V1: Final[Mapping[str, ProofRequirementSet]] = MappingProxyType(
    _MUTATION_REQUIREMENT_SETS
)
MUTATION_FAMILY_IDS: Final[tuple[str, ...]] = tuple(sorted(MUTATION_REQUIREMENT_SETS_V1))


def mutation_requirement_registry_snapshot() -> dict[str, object]:
    """Return the deterministic, secret-free registry projection."""

    return {
        "families": [
            {
                **MUTATION_REQUIREMENT_SETS_V1[family].canonical_body(),
                "requirement_set_sha256": MUTATION_REQUIREMENT_SETS_V1[family].requirement_set_sha256,
            }
            for family in MUTATION_FAMILY_IDS
        ],
        "schema_version": _SCHEMA_REGISTRY,
    }


MUTATION_REQUIREMENT_REGISTRY_SHA256: Final[str] = canonical_proof_sha256(
    mutation_requirement_registry_snapshot()
)


def mutation_requirement_set(operation_family: str) -> ProofRequirementSet:
    family = str(operation_family or "").strip().lower()
    requirement_set = MUTATION_REQUIREMENT_SETS_V1.get(family)
    if requirement_set is None:
        raise ProofContractError("unknown mutation operation family")
    return requirement_set


def build_mutation_proof_envelope(
    *,
    operation_family: str,
    operation_identity: str,
    repository: str,
    revision: str,
    input_sha256: str,
    diff_sha256: str,
) -> ProofEnvelope:
    """Bind one declared family to the existing immutable proof envelope."""

    return build_proof_envelope(
        requirement_set=mutation_requirement_set(operation_family),
        operation_identity=operation_identity,
        repository=repository,
        revision=revision,
        input_sha256=input_sha256,
        diff_sha256=diff_sha256,
    )


def evaluate_mutation_evidence(
    envelope: ProofEnvelope,
    observations: Sequence[ProofObservation],
) -> ProofVerdict:
    """Delegate the verdict exclusively to the core from issue #1098."""

    return evaluate_proof(
        envelope,
        observations,
        requirement_sets=MUTATION_REQUIREMENT_SETS_V1,
    )


__all__ = [
    "CANONICAL_MIRROR_OWNERSHIP_REQUIREMENTS_V1",
    "FLEET_DEPLOYMENT_REQUIREMENTS_V1",
    "GITHUB_MERGE_RELEASE_REQUIREMENTS_V1",
    "MCP_REGISTRY_SELF_UPDATE_REQUIREMENTS_V1",
    "MUTATION_FAMILY_IDS",
    "MUTATION_REQUIREMENT_REGISTRY_SHA256",
    "MUTATION_REQUIREMENT_SETS_V1",
    "POSTGRES_PGVECTOR_MUTATION_REQUIREMENTS_V1",
    "PROVIDER_ROUTING_MUTATION_REQUIREMENTS_V1",
    "SECURITY_PERMISSION_CHANGE_REQUIREMENTS_V1",
    "SOVEREIGN_RESCUE_REPAIR_REQUIREMENTS_V1",
    "build_mutation_proof_envelope",
    "evaluate_mutation_evidence",
    "mutation_requirement_registry_snapshot",
    "mutation_requirement_set",
]
