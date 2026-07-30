"""Mutation Evidence Layer – fail-closed ProofRequirementSets for the eight
risky Sovereign mutation families defined in issue #1097.

This module only declares what evidence is required per family; it contains
no I/O, no clock, no random access and no persistence. Every verdict is
derived by the pure engine in proof_verdict.py from caller-supplied
observations.
"""

from __future__ import annotations

from typing import Final, Mapping

from .proof_verdict import (
    ProofRequirement,
    ProofRequirementSet,
)

# ─────────────────────────────────────────────────────────────────────────────
# Family 1 – GitHub Merge, Rulesets and Release
# ─────────────────────────────────────────────────────────────────────────────
GITHUB_MERGE_RELEASE_REQUIREMENTS_V1: Final[ProofRequirementSet] = ProofRequirementSet(
    operation_family="github_merge_release",
    version=1,
    requirements=(
        ProofRequirement(
            requirement_id="agent_run_receipt",
            evidence_kind="agent_run_receipt",
            allowed_source_kinds=("AGENT_RUN_RECEIPT",),
            runtime_required=True,
        ),
        ProofRequirement(
            requirement_id="ci_readback",
            evidence_kind="ci_readback",
            allowed_source_kinds=("CI_READBACK",),
            runtime_required=True,
        ),
        ProofRequirement(
            requirement_id="repository_readback",
            evidence_kind="repository_readback",
            allowed_source_kinds=("REPOSITORY_READBACK",),
            runtime_required=True,
        ),
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# Family 2 – Sovereign Rescue and automated repairs
# ─────────────────────────────────────────────────────────────────────────────
SOVEREIGN_RESCUE_REPAIR_REQUIREMENTS_V1: Final[ProofRequirementSet] = ProofRequirementSet(
    operation_family="sovereign_rescue_repair",
    version=1,
    requirements=(
        ProofRequirement(
            requirement_id="agent_run_receipt",
            evidence_kind="agent_run_receipt",
            allowed_source_kinds=("AGENT_RUN_RECEIPT",),
            runtime_required=True,
        ),
        ProofRequirement(
            requirement_id="repository_readback",
            evidence_kind="repository_readback",
            allowed_source_kinds=("REPOSITORY_READBACK",),
            runtime_required=True,
        ),
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# Family 3 – MCP Registry, Broker and Self-Update
# ─────────────────────────────────────────────────────────────────────────────
MCP_REGISTRY_SELF_UPDATE_REQUIREMENTS_V1: Final[ProofRequirementSet] = ProofRequirementSet(
    operation_family="mcp_registry_self_update",
    version=1,
    requirements=(
        ProofRequirement(
            requirement_id="agent_run_receipt",
            evidence_kind="agent_run_receipt",
            allowed_source_kinds=("AGENT_RUN_RECEIPT",),
            runtime_required=True,
        ),
        ProofRequirement(
            requirement_id="mcp_readback",
            evidence_kind="mcp_readback",
            allowed_source_kinds=("MCP_READBACK",),
            runtime_required=True,
        ),
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# Family 4 – Docker, VPS, PatchMon and Deployment
# ─────────────────────────────────────────────────────────────────────────────
DOCKER_VPS_PATCHMON_DEPLOYMENT_REQUIREMENTS_V1: Final[ProofRequirementSet] = ProofRequirementSet(
    operation_family="docker_vps_patchmon_deployment",
    version=1,
    requirements=(
        ProofRequirement(
            requirement_id="agent_run_receipt",
            evidence_kind="agent_run_receipt",
            allowed_source_kinds=("AGENT_RUN_RECEIPT",),
            runtime_required=True,
        ),
        ProofRequirement(
            requirement_id="image_readback",
            evidence_kind="image_readback",
            allowed_source_kinds=("IMAGE_READBACK",),
            runtime_required=True,
        ),
        ProofRequirement(
            requirement_id="patchmon_readback",
            evidence_kind="patchmon_readback",
            allowed_source_kinds=("PATCHMON_READBACK",),
            runtime_required=True,
        ),
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# Family 5 – PostgreSQL Migrations and pgvector
# ─────────────────────────────────────────────────────────────────────────────
POSTGRESQL_MIGRATIONS_PGVECTOR_REQUIREMENTS_V1: Final[ProofRequirementSet] = ProofRequirementSet(
    operation_family="postgresql_migrations_pgvector",
    version=1,
    requirements=(
        ProofRequirement(
            requirement_id="agent_run_receipt",
            evidence_kind="agent_run_receipt",
            allowed_source_kinds=("AGENT_RUN_RECEIPT",),
            runtime_required=True,
        ),
        ProofRequirement(
            requirement_id="database_readback",
            evidence_kind="database_readback",
            allowed_source_kinds=("DATABASE_READBACK",),
            runtime_required=True,
        ),
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# Family 6 – OpenRouter, FreeRoute and Revolver Routing
# ─────────────────────────────────────────────────────────────────────────────
OPENROUTER_FREEROUTE_REVOLVER_REQUIREMENTS_V1: Final[ProofRequirementSet] = ProofRequirementSet(
    operation_family="openrouter_freeroute_revolver",
    version=1,
    requirements=(
        ProofRequirement(
            requirement_id="agent_run_receipt",
            evidence_kind="agent_run_receipt",
            allowed_source_kinds=("AGENT_RUN_RECEIPT",),
            runtime_required=True,
        ),
        ProofRequirement(
            requirement_id="runtime_readback",
            evidence_kind="runtime_readback",
            allowed_source_kinds=("RUNTIME_READBACK",),
            runtime_required=True,
        ),
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# Family 7 – Canonical Mirrors and Ownerships
# ─────────────────────────────────────────────────────────────────────────────
CANONICAL_MIRROR_OWNERSHIP_REQUIREMENTS_V1: Final[ProofRequirementSet] = ProofRequirementSet(
    operation_family="canonical_mirror_ownership",
    version=1,
    requirements=(
        ProofRequirement(
            requirement_id="agent_run_receipt",
            evidence_kind="agent_run_receipt",
            allowed_source_kinds=("AGENT_RUN_RECEIPT",),
            runtime_required=True,
        ),
        ProofRequirement(
            requirement_id="repository_readback",
            evidence_kind="repository_readback",
            allowed_source_kinds=("REPOSITORY_READBACK",),
            runtime_required=True,
        ),
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# Family 8 – Security-relevant Permission Changes
# ─────────────────────────────────────────────────────────────────────────────
SECURITY_PERMISSION_CHANGE_REQUIREMENTS_V1: Final[ProofRequirementSet] = ProofRequirementSet(
    operation_family="security_permission_change",
    version=1,
    requirements=(
        ProofRequirement(
            requirement_id="agent_run_receipt",
            evidence_kind="agent_run_receipt",
            allowed_source_kinds=("AGENT_RUN_RECEIPT",),
            runtime_required=True,
        ),
        ProofRequirement(
            requirement_id="ci_readback",
            evidence_kind="ci_readback",
            allowed_source_kinds=("CI_READBACK",),
            runtime_required=True,
        ),
        ProofRequirement(
            requirement_id="runtime_readback",
            evidence_kind="runtime_readback",
            allowed_source_kinds=("RUNTIME_READBACK",),
            runtime_required=True,
        ),
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# Unified registry – all eight families
# ─────────────────────────────────────────────────────────────────────────────
ALL_MUTATION_REQUIREMENT_SETS: Final[Mapping[str, ProofRequirementSet]] = {
    GITHUB_MERGE_RELEASE_REQUIREMENTS_V1.operation_family: GITHUB_MERGE_RELEASE_REQUIREMENTS_V1,
    SOVEREIGN_RESCUE_REPAIR_REQUIREMENTS_V1.operation_family: SOVEREIGN_RESCUE_REPAIR_REQUIREMENTS_V1,
    MCP_REGISTRY_SELF_UPDATE_REQUIREMENTS_V1.operation_family: MCP_REGISTRY_SELF_UPDATE_REQUIREMENTS_V1,
    DOCKER_VPS_PATCHMON_DEPLOYMENT_REQUIREMENTS_V1.operation_family: DOCKER_VPS_PATCHMON_DEPLOYMENT_REQUIREMENTS_V1,
    POSTGRESQL_MIGRATIONS_PGVECTOR_REQUIREMENTS_V1.operation_family: POSTGRESQL_MIGRATIONS_PGVECTOR_REQUIREMENTS_V1,
    OPENROUTER_FREEROUTE_REVOLVER_REQUIREMENTS_V1.operation_family: OPENROUTER_FREEROUTE_REVOLVER_REQUIREMENTS_V1,
    CANONICAL_MIRROR_OWNERSHIP_REQUIREMENTS_V1.operation_family: CANONICAL_MIRROR_OWNERSHIP_REQUIREMENTS_V1,
    SECURITY_PERMISSION_CHANGE_REQUIREMENTS_V1.operation_family: SECURITY_PERMISSION_CHANGE_REQUIREMENTS_V1,
}

__all__ = [
    "ALL_MUTATION_REQUIREMENT_SETS",
    "CANONICAL_MIRROR_OWNERSHIP_REQUIREMENTS_V1",
    "DOCKER_VPS_PATCHMON_DEPLOYMENT_REQUIREMENTS_V1",
    "GITHUB_MERGE_RELEASE_REQUIREMENTS_V1",
    "MCP_REGISTRY_SELF_UPDATE_REQUIREMENTS_V1",
    "OPENROUTER_FREEROUTE_REVOLVER_REQUIREMENTS_V1",
    "POSTGRESQL_MIGRATIONS_PGVECTOR_REQUIREMENTS_V1",
    "SECURITY_PERMISSION_CHANGE_REQUIREMENTS_V1",
    "SOVEREIGN_RESCUE_REPAIR_REQUIREMENTS_V1",
]
