"""Fail-closed evidence gate for PostgreSQL, pgvector and DB-lifecycle operations.

Issue: #1102 — [Evidence/Data] PostgreSQL, pgvector und OpenRouter/FreeRoute-Mutationen absichern

Protected operation families
-----------------------------
- postgres_schema_migration         PostgreSQL migrations and schema changes
- postgres_table_constraint_change  Table, constraint, index and ownership changes
- pgvector_extension_change         pgvector extension, index and canary changes
- postgres_data_migration           Data migrations with production impact
- postgres_backup_restore_rollback  Backup, restore and rollback actions

Fail-closed invariants
----------------------
- Migration success is not inferred from exit-code alone; post-apply schema readback is required.
- An existing table without the expected constraints and indexes is not a complete success.
- pgvector is a PostgreSQL extension and is not treated as a separate database truth; it is
  covered by the same schema inventory and ownership requirements.
- No Areloria-Wasd ownership surface may be modified; every envelope must carry explicit
  pre_no_areloria_wasd_overlap evidence.
- Rollback or restore evidence is required for all mutation families (not optional).
- No raw database rows, connection strings, credentials, migration SQL content, or user-data
  values may appear in any evidence field — only structural hashes and counts.
- ``auto_merge_allowed`` is always ``False``.

This module contains no network, database, filesystem, clock, or random access.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Final, Sequence


_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:-]{1,119}$")

POSTGRES_EVIDENCE_SCHEMA: Final[str] = "sovereign.postgres-pgvector-evidence-gate.v1"

VERDICT_VERIFIED: Final[str] = "VERIFIED"
VERDICT_CONTRADICTED: Final[str] = "CONTRADICTED"
VERDICT_BLOCKED: Final[str] = "BLOCKED_BY_MISSING_EVIDENCE"

OPERATION_FAMILIES: Final[frozenset[str]] = frozenset({
    "pgvector_extension_change",
    "postgres_backup_restore_rollback",
    "postgres_data_migration",
    "postgres_schema_migration",
    "postgres_table_constraint_change",
})

# ---------------------------------------------------------------------------
# Per-family evidence requirements
#
# pre_*  — observed BEFORE the migration runs
# post_* — observed AFTER the migration completes
# ---------------------------------------------------------------------------
_FAMILY_REQUIREMENTS: Final[dict[str, tuple[str, ...]]] = {
    "postgres_schema_migration": (
        "pre_migration_identity",
        "pre_schema_inventory",
        "pre_canonical_ownership",
        "pre_no_areloria_wasd_overlap",
        "post_schema_readback",
        "post_constraint_index_readback",
        "post_rollback_reference",
        "post_capability_delta",
    ),
    "postgres_table_constraint_change": (
        "pre_migration_identity",
        "pre_schema_inventory",
        "pre_canonical_ownership",
        "pre_no_areloria_wasd_overlap",
        "post_schema_readback",
        "post_constraint_index_readback",
        "post_rollback_reference",
        "post_capability_delta",
    ),
    "pgvector_extension_change": (
        "pre_migration_identity",
        "pre_schema_inventory",
        "pre_canonical_ownership",
        "pre_no_areloria_wasd_overlap",
        "post_schema_readback",
        "post_constraint_index_readback",
        "post_pgvector_canary",
        "post_rollback_reference",
        "post_capability_delta",
    ),
    "postgres_data_migration": (
        "pre_migration_identity",
        "pre_schema_inventory",
        "pre_canonical_ownership",
        "pre_no_areloria_wasd_overlap",
        "pre_row_count_baseline",
        "post_schema_readback",
        "post_row_count_readback",
        "post_rollback_reference",
        "post_capability_delta",
    ),
    "postgres_backup_restore_rollback": (
        "pre_migration_identity",
        "pre_schema_inventory",
        "pre_canonical_ownership",
        "pre_no_areloria_wasd_overlap",
        "post_restore_readback",
        "post_schema_readback",
        "post_constraint_index_readback",
        "post_capability_delta",
    ),
}


def _canonical_sha256(value: Any) -> str:
    def _canonical(v: Any) -> Any:
        if v is None or isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            raise ValueError("float forbidden in postgres-pgvector evidence")
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return {str(k): _canonical(val) for k, val in sorted(v.items())}
        if isinstance(v, (list, tuple)):
            return [_canonical(item) for item in v]
        raise ValueError(f"non-serializable type: {type(v).__name__}")
    serialized = json.dumps(_canonical(value), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Evidence envelope
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PostgresEvidenceEnvelope:
    """Immutable evidence envelope for one PostgreSQL/pgvector operation.

    Fields
    ------
    operation_family
        One of the five OPERATION_FAMILIES.
    operation_identity
        Opaque, non-secret identifier for this operation instance.
    repository
        Canonical ``owner/repo`` of the Sovereign repository.
    base_revision
        Full Git SHA-40 at envelope-creation time (migration source revision).
    migration_hash
        SHA-256 of the canonical, secret-free migration descriptor.
        Must not contain SQL content, database rows, or credentials.
    schema_inventory_hash
        SHA-256 of the pre-migration schema inventory (table names, column
        counts, constraint counts, index counts — no row data).
    declared_tables
        Sorted tuple of table names the migration declares it will modify.
        At least one entry is required.
    areloria_wasd_excluded
        Explicit caller assertion that no Areloria-Wasd ownership surface is
        in scope for this operation.  Must be True; False → envelope rejected.
    """

    operation_family: str
    operation_identity: str
    repository: str
    base_revision: str
    migration_hash: str
    schema_inventory_hash: str
    declared_tables: tuple[str, ...]
    areloria_wasd_excluded: bool
    envelope_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        family = str(self.operation_family or "").strip().lower()
        if family not in OPERATION_FAMILIES:
            raise ValueError(f"unknown operation_family: {family!r}")
        if not _IDENTIFIER.fullmatch(str(self.operation_identity or "").strip()):
            raise ValueError("operation_identity must match [a-z][a-z0-9_.:-]{1,119}")
        if not _SHA40.fullmatch(str(self.base_revision or "").strip().lower()):
            raise ValueError("base_revision must be a full Git SHA-40")
        if not _SHA64.fullmatch(str(self.migration_hash or "").strip().lower()):
            raise ValueError("migration_hash must be a SHA-256")
        if not _SHA64.fullmatch(str(self.schema_inventory_hash or "").strip().lower()):
            raise ValueError("schema_inventory_hash must be a SHA-256")
        if not self.declared_tables:
            raise ValueError("declared_tables must not be empty")
        if self.areloria_wasd_excluded is not True:
            raise ValueError(
                "areloria_wasd_excluded must be True; Areloria-Wasd surfaces "
                "must be explicitly confirmed as out-of-scope before this envelope is created"
            )

        object.__setattr__(self, "operation_family", family)
        object.__setattr__(self, "base_revision", str(self.base_revision).strip().lower())
        object.__setattr__(self, "migration_hash", str(self.migration_hash).strip().lower())
        object.__setattr__(self, "schema_inventory_hash", str(self.schema_inventory_hash).strip().lower())
        object.__setattr__(
            self,
            "declared_tables",
            tuple(sorted(str(t).strip() for t in self.declared_tables if str(t).strip())),
        )
        sha = _canonical_sha256(self._body())
        object.__setattr__(self, "envelope_sha256", sha)

    def _body(self) -> dict[str, Any]:
        return {
            "areloria_wasd_excluded": True,
            "base_revision": str(self.base_revision),
            "declared_tables": list(self.declared_tables),
            "migration_hash": str(self.migration_hash),
            "operation_family": str(self.operation_family),
            "operation_identity": str(self.operation_identity),
            "repository": str(self.repository),
            "schema_inventory_hash": str(self.schema_inventory_hash),
            "schema_version": POSTGRES_EVIDENCE_SCHEMA,
        }


# ---------------------------------------------------------------------------
# Evidence observation
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PostgresObservation:
    """Single collected observation for one PostgreSQL/pgvector evidence requirement.

    Fail-closed guidance for collectors
    ------------------------------------
    - Exit-code-only migration success (no schema readback) → UNAVAILABLE.
    - A table that exists but whose constraint_count or index_count does not
      match the expected delta → CONTRADICTED.
    - pgvector availability without an explicit canary query → UNAVAILABLE.
    - Row-count observations must contain only counts — no row content.
    - Areloria-Wasd overlap detected → CONTRADICTED (not UNAVAILABLE).
    """

    requirement_id: str
    value_hash: str         # SHA-256 of the canonical, secret-free observation payload
    source: str             # e.g. "DATABASE_READBACK", "REPOSITORY_READBACK", "AGENT_RUN_RECEIPT"
    assertion: str          # "OBSERVED" | "CONTRADICTED" | "UNAVAILABLE"
    bound_revision: str     # git SHA-40; must match envelope.base_revision when non-empty

    def __post_init__(self) -> None:
        assertion = str(self.assertion or "").strip().upper()
        if assertion not in {"OBSERVED", "CONTRADICTED", "UNAVAILABLE"}:
            raise ValueError(f"unsupported assertion: {assertion!r}")
        object.__setattr__(self, "assertion", assertion)
        if not _SHA64.fullmatch(str(self.value_hash or "").strip().lower()):
            raise ValueError("value_hash must be a SHA-256")
        object.__setattr__(self, "value_hash", str(self.value_hash).strip().lower())
        rev = str(self.bound_revision or "").strip().lower()
        if rev and not _SHA40.fullmatch(rev):
            raise ValueError("bound_revision must be a full Git SHA-40 or empty string")
        object.__setattr__(self, "bound_revision", rev)

    @property
    def observation_sha256(self) -> str:
        return _canonical_sha256({
            "assertion": self.assertion,
            "bound_revision": self.bound_revision,
            "requirement_id": self.requirement_id,
            "source": self.source,
            "value_hash": self.value_hash,
        })


# ---------------------------------------------------------------------------
# Evaluation result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PostgresEvidenceResult:
    """Fail-closed verdict for one PostgreSQL/pgvector operation."""

    verdict: str
    operation_family: str
    envelope_sha256: str
    satisfied: tuple[str, ...]
    missing: tuple[str, ...]
    contradicted: tuple[str, ...]
    finding_codes: tuple[str, ...]
    auto_merge_allowed: bool  # always False


# ---------------------------------------------------------------------------
# Fail-closed evaluation
# ---------------------------------------------------------------------------

def evaluate_postgres_evidence(
    envelope: PostgresEvidenceEnvelope,
    observations: Sequence[PostgresObservation],
) -> PostgresEvidenceResult:
    """Evaluate fail-closed evidence for a PostgreSQL/pgvector operation.

    Verdict rules
    -------------
    VERIFIED
        Every requirement for the family has at least one OBSERVED observation
        with matching bound_revision (when non-empty).

    CONTRADICTED
        Any requirement has a CONTRADICTED observation, or a bound_revision that
        differs from envelope.base_revision.  Contradictions take priority.

    BLOCKED_BY_MISSING_EVIDENCE
        One or more requirements have no satisfying observation.

    Additional invariants
    ---------------------
    - ``pre_no_areloria_wasd_overlap`` with assertion CONTRADICTED immediately
      produces CONTRADICTED for the whole evaluation (Areloria-Wasd fence).
    - A ``post_constraint_index_readback`` observation with UNAVAILABLE does not
      satisfy the requirement — an existing table without verified
      constraints/indexes is not a complete success.
    """
    required = _FAMILY_REQUIREMENTS.get(envelope.operation_family, ())
    obs_by_req: dict[str, list[PostgresObservation]] = {}
    for obs in observations:
        obs_by_req.setdefault(obs.requirement_id, []).append(obs)

    satisfied: set[str] = set()
    missing: set[str] = set()
    contradicted: set[str] = set()
    findings: set[str] = set()

    for req_id in required:
        candidates = obs_by_req.get(req_id, [])
        if not candidates:
            missing.add(req_id)
            findings.add("required_observation_missing")
            continue

        req_satisfied = False
        req_contradicted = False

        for obs in candidates:
            # Revision binding check
            if obs.bound_revision and obs.bound_revision != envelope.base_revision:
                req_contradicted = True
                findings.add("observation_bound_to_stale_revision")
                continue

            if obs.assertion == "CONTRADICTED":
                req_contradicted = True
                findings.add("observation_reports_contradiction")
                if req_id == "pre_no_areloria_wasd_overlap":
                    findings.add("areloria_wasd_overlap_detected")
                continue

            if obs.assertion == "UNAVAILABLE":
                findings.add("observation_unavailable")
                continue

            req_satisfied = True

        if req_contradicted:
            contradicted.add(req_id)
        elif req_satisfied:
            satisfied.add(req_id)
        else:
            missing.add(req_id)

    if contradicted:
        verdict = VERDICT_CONTRADICTED
    elif missing:
        verdict = VERDICT_BLOCKED
    else:
        verdict = VERDICT_VERIFIED

    return PostgresEvidenceResult(
        verdict=verdict,
        operation_family=envelope.operation_family,
        envelope_sha256=envelope.envelope_sha256,
        satisfied=tuple(sorted(satisfied)),
        missing=tuple(sorted(missing)),
        contradicted=tuple(sorted(contradicted)),
        finding_codes=tuple(sorted(findings)),
        auto_merge_allowed=False,
    )


# ---------------------------------------------------------------------------
# Areloria-Wasd fence audit
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class AraeloriaWasdFenceAudit:
    """Audit result for an Areloria-Wasd ownership overlap check."""

    clear: bool
    blocker: str | None
    overlap_tables: tuple[str, ...]


_ARELORIA_WASD_TABLE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"(?<![a-z0-9])areloria(?![a-z0-9])|^areloria",
        r"(?<![a-z0-9])wasd(?![a-z0-9])|^wasd",
        r"(?<![a-z0-9])mmorpg(?![a-z0-9])|^mmorpg",
        r"game_world",
        r"player_char",
        r"quest_",
        r"guild_",
        r"item_drop",
    )
)


def audit_areloria_wasd_fence(
    declared_tables: Sequence[str],
) -> AraeloriaWasdFenceAudit:
    """Verify that no declared table name matches an Areloria-Wasd ownership pattern.

    The Sovereign Studio ATO and the Areloria/WASD/MMORPG codebase are strictly
    separate.  Any migration that touches tables matching known Areloria-Wasd
    naming patterns must be rejected before an envelope can be created.
    """
    overlap: list[str] = []
    for table in declared_tables:
        name = str(table or "").strip()
        if any(pat.search(name) for pat in _ARELORIA_WASD_TABLE_PATTERNS):
            overlap.append(name)

    if overlap:
        return AraeloriaWasdFenceAudit(
            clear=False,
            blocker=f"declared_tables_overlap_areloria_wasd_ownership: {', '.join(sorted(overlap))}",
            overlap_tables=tuple(sorted(overlap)),
        )

    return AraeloriaWasdFenceAudit(
        clear=True,
        blocker=None,
        overlap_tables=(),
    )


__all__ = [
    "OPERATION_FAMILIES",
    "POSTGRES_EVIDENCE_SCHEMA",
    "VERDICT_BLOCKED",
    "VERDICT_CONTRADICTED",
    "VERDICT_VERIFIED",
    "AraeloriaWasdFenceAudit",
    "PostgresEvidenceEnvelope",
    "PostgresEvidenceResult",
    "PostgresObservation",
    "audit_areloria_wasd_fence",
    "evaluate_postgres_evidence",
]
