"""Snapshot export from canonical #1111/#1117 records for ScaNN indexing.

Exports Bug Evidence Cases and Durable Memory Leaves into a scoped,
revision-bound vector snapshot that can be fed to the ScaNN index builder.

Design constraints:
- No network, database, filesystem, clock or random access in this module.
- Exports are deterministic: same source revision produces identical exports.
- Scope filtering is enforced before any export.
- Only VERIFIED or OBSERVED evidence classes are included.
- Raw content is normalized to remove volatile values (timestamps, UUIDs, etc.).

Canonical ownership:
- #1111 owns Bug Evidence Cases (failure families, normalized signatures).
- #1117 owns Durable Memory Leaves (long-lived insights, evidence classes).
- PostgreSQL remains Source of Truth for all canonical records.
- ScaNN is exclusively a derived retrieval projection.

Issue: #1171
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Final, FrozenSet, Sequence, Tuple

from .scann_manifest import (
    SCHEMA_VERSION,
    ChunkManifest,
    CPUArchitecture,
    EmbeddingConfig,
    EmbeddingDataType,
    Normalization,
    DistanceMetric,
    RecallReceipt,
    ScopeBinding,
    SourceRecordRef,
    ScaNNBuildConfig,
    VectorSnapshotManifest,
    ManifestContractError,
)


# ---------------------------------------------------------------------------
# Export configuration
# ---------------------------------------------------------------------------
_EXPORT_VERSION: Final[str] = "1.0.0"

# Evidence classes allowed for ScaNN indexing
_ALLOWED_EVIDENCE_CLASSES: Final[FrozenSet[str]] = frozenset({
    "verified",
    "observed",
})

# Source types for export
_SOURCE_TYPE_BUG_EVIDENCE: Final[str] = "bug_evidence"
_SOURCE_TYPE_DURABLE_MEMORY: Final[str] = "durable_memory"

# Volatile patterns stripped during normalization
_VOLATILE_TIMESTAMP_ISO: Final[re.Pattern[str]] = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?",
)
_VOLATILE_UUID: Final[re.Pattern[str]] = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_VOLATILE_SHA256: Final[re.Pattern[str]] = re.compile(r"\b[0-9a-f]{64}\b")
_VOLATILE_SHA40: Final[re.Pattern[str]] = re.compile(r"\b[0-9a-f]{40}\b")
_VOLATILE_CONTAINER_ID: Final[re.Pattern[str]] = re.compile(r"\b[0-9a-f]{12,64}\b")


class ExportContractError(ValueError):
    """An input violated an export invariant."""


# ---------------------------------------------------------------------------
# Export record
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ExportRecord:
    """A single record prepared for ScaNN indexing."""
    record_id: str
    source_type: str          # bug_evidence or durable_memory
    evidence_class: str
    normalized_content: str   # Volatile-stripped text for embedding
    raw_content_hash: str    # SHA-256 of original unnormalized content
    normalized_content_hash: str  # SHA-256 of normalized content
    source_revision: str
    source_file: str
    failure_family: str | None   # For bug_evidence records
    evidence_source: str | None  # For durable_memory records


# ---------------------------------------------------------------------------
# Snapshot export result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SnapshotExportResult:
    """Complete export result for ScaNN indexing."""
    export_version: str
    scope: ScopeBinding
    source_revision: str
    records: Tuple[ExportRecord, ...]
    export_hash: str         # SHA-256 of all exported content
    content_hash: str        # SHA-256 of normalized content for all records
    excluded_count: int      # Records excluded due to evidence class
    excluded_reasons: Tuple[str, ...]


# ---------------------------------------------------------------------------
# Content normalization
# ---------------------------------------------------------------------------

def normalize_content_for_embedding(content: str) -> str:
    """Normalize content by stripping volatile values.

    This ensures the same source produces identical embeddings across builds,
    even if the source contains timestamps, UUIDs, or other volatile data.
    """
    normalized = content

    # Strip ISO timestamps
    normalized = _VOLATILE_TIMESTAMP_ISO.sub("<TS>", normalized)

    # Strip UUIDs
    normalized = _VOLATILE_UUID.sub("<UUID>", normalized)

    # Strip SHA-256 hashes
    normalized = _VOLATILE_SHA256.sub("<SHA256>", normalized)

    # Strip SHA-40 git hashes
    normalized = _VOLATILE_SHA40.sub("<SHA40>", normalized)

    # Strip container IDs
    normalized = _VOLATILE_CONTAINER_ID.sub("<CID>", normalized)

    # Normalize whitespace
    normalized = " ".join(normalized.split())

    # Truncate to reasonable length
    max_len = 16_384
    if len(normalized) > max_len:
        normalized = normalized[:max_len]

    return normalized


def compute_content_hash(content: str) -> str:
    """Compute deterministic SHA-256 of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Bug Evidence Case interface
# ---------------------------------------------------------------------------

# Type alias for Bug Evidence Case dict (from bug_evidence_lane.py)
BugEvidenceCaseDict = dict

# Type alias for Durable Memory Leaf dict (from durable_memory_forest.py)
DurableMemoryLeafDict = dict


def extract_bug_evidence_for_export(
    case: BugEvidenceCaseDict,
    scope: ScopeBinding,
    source_revision: str,
) -> ExportRecord | None:
    """Extract a Bug Evidence Case for ScaNN export if eligible.

    Returns None if the case is not eligible (wrong scope, evidence class, etc.).
    """
    # Check evidence class and optional owner/tenant/environment bindings.
    status = case.get("status", "")
    if status not in _ALLOWED_EVIDENCE_CLASSES:
        return None
    for field_name, expected in (
        ("owner", scope.owner),
        ("tenant", scope.tenant),
        ("environment", scope.environment),
    ):
        supplied = case.get(field_name)
        if supplied not in (None, "", expected):
            return None

    # Build normalized content from a complete canonical identity.
    evidence_case_id = case.get("evidence_case_id", "")
    signature = case.get("normalized_signature", "")
    failure_family = case.get("failure_family", "")
    if not evidence_case_id or not signature or not failure_family:
        return None
    repo_owner = case.get("repo_owner", "")
    repo_name = case.get("repo_name", "")

    content_parts = [
        f"Failure: {failure_family}",
        f"Repo: {repo_owner}/{repo_name}",
        signature,
    ]

    # Add diagnostic info if available
    if case.get("diagnostic_tools"):
        content_parts.append(f"Tools: {', '.join(case.get('diagnostic_tools', []))}")

    # Add affected surfaces
    if case.get("affected_surfaces"):
        surfaces = case.get("affected_surfaces", [])
        content_parts.append(f"Surfaces: {', '.join(surfaces)}")

    raw_content = "\n".join(content_parts)
    normalized = normalize_content_for_embedding(raw_content)

    record_id = f"be:{evidence_case_id}"
    source_file = f"/bug_evidence/{evidence_case_id}"

    return ExportRecord(
        record_id=record_id,
        source_type=_SOURCE_TYPE_BUG_EVIDENCE,
        evidence_class=status,
        normalized_content=normalized,
        raw_content_hash=compute_content_hash(raw_content),
        normalized_content_hash=compute_content_hash(normalized),
        source_revision=source_revision,
        source_file=source_file,
        failure_family=failure_family,
        evidence_source=None,
    )


def extract_memory_leaf_for_export(
    leaf: DurableMemoryLeafDict,
    scope: ScopeBinding,
    source_revision: str,
) -> ExportRecord | None:
    """Extract a Durable Memory Leaf for ScaNN export if eligible.

    Returns None if the leaf is not eligible (wrong scope, evidence class, etc.).
    """
    # Check evidence class and require a canonical record identity.
    evidence_class = leaf.get("evidence_class", "")
    leaf_id = leaf.get("leaf_id", "")
    if evidence_class not in _ALLOWED_EVIDENCE_CLASSES or not leaf_id:
        return None

    # Build normalized content
    content_parts = []

    # Add kind/summary
    kind = leaf.get("kind", "")
    summary = leaf.get("summary", "")
    if kind:
        content_parts.append(f"Kind: {kind}")
    if summary:
        content_parts.append(f"Summary: {summary}")

    # Add content
    content = leaf.get("content", "")
    if content:
        content_parts.append(content)

    # Add period label if present
    period_label = leaf.get("period_label", "")
    if period_label:
        content_parts.append(f"Period: {period_label}")

    raw_content = "\n".join(content_parts)
    if not raw_content.strip():
        return None
    normalized = normalize_content_for_embedding(raw_content)

    record_id = f"ml:{leaf_id}"
    source_file = f"/memory/{leaf_id}"

    return ExportRecord(
        record_id=record_id,
        source_type=_SOURCE_TYPE_DURABLE_MEMORY,
        evidence_class=evidence_class,
        normalized_content=normalized,
        raw_content_hash=compute_content_hash(raw_content),
        normalized_content_hash=compute_content_hash(normalized),
        source_revision=source_revision,
        source_file=source_file,
        failure_family=None,
        evidence_source=leaf.get("source_class", ""),
    )


# ---------------------------------------------------------------------------
# Snapshot export
# ---------------------------------------------------------------------------

def export_snapshot(
    bug_evidence_cases: Sequence[BugEvidenceCaseDict],
    memory_leaves: Sequence[DurableMemoryLeafDict],
    scope: ScopeBinding,
    source_revision: str,
) -> SnapshotExportResult:
    """Export canonical records into a snapshot for ScaNN indexing.

    Args:
        bug_evidence_cases: Bug Evidence Cases from #1111
        memory_leaves: Durable Memory Leaves from #1117
        scope: Owner/Tenant/Repo/Environment scope for filtering
        source_revision: Git SHA-40 of source repository

    Returns:
        SnapshotExportResult with all eligible records

    Raises:
        ExportContractError: If input validation fails
    """
    if not _VALID_REVISION.fullmatch(source_revision):
        raise ExportContractError(f"Invalid source_revision: {source_revision!r}")

    excluded_reasons: list[str] = []
    records: list[ExportRecord] = []

    # Export Bug Evidence Cases
    for case in bug_evidence_cases:
        # Scope filter for bug evidence
        case_repo_owner = case.get("repo_owner", "")
        case_repo_name = case.get("repo_name", "")

        if case_repo_owner != scope.repo_owner or case_repo_name != scope.repo_name:
            excluded_reasons.append(f"be:scope_mismatch:{case.get('evidence_case_id', '')}")
            continue

        export_record = extract_bug_evidence_for_export(case, scope, source_revision)
        if export_record is None:
            excluded_reasons.append(f"be:ineligible:{case.get('evidence_case_id', '')}")
        else:
            records.append(export_record)

    # Export Durable Memory Leaves
    for leaf in memory_leaves:
        # Scope filter for memory leaves
        leaf_owner = leaf.get("owner", "")
        leaf_tenant = leaf.get("tenant", "")
        leaf_repo_owner = leaf.get("repo_owner", "")
        leaf_repo_name = leaf.get("repo_name", "")

        if (leaf_owner != scope.owner
                or leaf_tenant != scope.tenant
                or leaf_repo_owner != scope.repo_owner
                or leaf_repo_name != scope.repo_name):
            excluded_reasons.append(f"ml:scope_mismatch:{leaf.get('leaf_id', '')}")
            continue

        export_record = extract_memory_leaf_for_export(leaf, scope, source_revision)
        if export_record is None:
            excluded_reasons.append(f"ml:ineligible:{leaf.get('leaf_id', '')}")
        else:
            records.append(export_record)

    # Sort records by record_id for deterministic ordering and reject collisions.
    records.sort(key=lambda r: r.record_id)
    record_ids = [record.record_id for record in records]
    if len(record_ids) != len(set(record_ids)):
        raise ExportContractError("Duplicate record_id in snapshot export")
    excluded_reasons.sort()

    # Compute export hash
    export_data = {
        "scope_hash": scope.scope_hash,
        "source_revision": source_revision,
        "records": [
            {
                "record_id": r.record_id,
                "source_type": r.source_type,
                "evidence_class": r.evidence_class,
                "content_hash": r.normalized_content_hash,
            }
            for r in records
        ],
    }
    export_hash = _canonical_sha256(export_data)

    # Compute an unambiguous content identity from ordered record hashes.
    content_hash = _canonical_sha256(
        [
            {
                "record_id": r.record_id,
                "normalized_content_hash": r.normalized_content_hash,
            }
            for r in records
        ]
    )

    return SnapshotExportResult(
        export_version=_EXPORT_VERSION,
        scope=scope,
        source_revision=source_revision,
        records=tuple(records),
        export_hash=export_hash,
        content_hash=content_hash,
        excluded_count=len(excluded_reasons),
        excluded_reasons=tuple(excluded_reasons),
    )


# ---------------------------------------------------------------------------
# Manifest building
# ---------------------------------------------------------------------------

def build_manifest_from_export(
    export: SnapshotExportResult,
    embedding_config: EmbeddingConfig,
    build_config: ScaNNBuildConfig,
    index_hash: str,
    cpu_architecture: CPUArchitecture,
    recall_receipt: RecallReceipt | None = None,
) -> VectorSnapshotManifest:
    """Build a VectorSnapshotManifest from a SnapshotExportResult.

    This creates the manifest that will be stored alongside the ScaNN index.
    """
    if not export.records:
        raise ExportContractError("Cannot build a ScaNN manifest from an empty export")

    # Convert export records to source record references
    source_records = tuple(
        SourceRecordRef(
            record_id=r.record_id,
            content_hash=r.normalized_content_hash,
            evidence_class=r.evidence_class,
            source_revision=r.source_revision,
            source_file=r.source_file,
        )
        for r in export.records
    )

    return VectorSnapshotManifest(
        schema_version=SCHEMA_VERSION,
        manifest_version=_EXPORT_VERSION,
        scope=export.scope,
        source_revision=export.source_revision,
        source_export_hash=export.export_hash,
        source_records=source_records,
        embedding_config=embedding_config,
        build_config=build_config,
        vector_count=len(export.records),
        chunk_manifest=(),  # Filled by index builder if needed
        index_hash=index_hash,
        cpu_architecture=cpu_architecture,
        recall_receipt=recall_receipt,
    )


# ---------------------------------------------------------------------------
# Helper patterns
# ---------------------------------------------------------------------------
_VALID_REVISION: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")


def _canonical_sha256(value: object) -> str:
    """Deterministic SHA-256 over the UTF-8 JSON serialisation of *value*."""
    serialised = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


__all__ = [
    "ExportContractError",
    "ExportRecord",
    "SnapshotExportResult",
    "normalize_content_for_embedding",
    "compute_content_hash",
    "BugEvidenceCaseDict",
    "DurableMemoryLeafDict",
    "extract_bug_evidence_for_export",
    "extract_memory_leaf_for_export",
    "export_snapshot",
    "build_manifest_from_export",
]
