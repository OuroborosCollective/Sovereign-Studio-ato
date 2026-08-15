"""ScaNN Incident Candidate Index Retrieval Package.

This package implements a rebuildable ScaNN-based candidate index for finding
similar historical incident cases in Sovereign Studio ATO.

Design principles:
- ScaNN is exclusively a derived retrieval projection, never canonical truth.
- PostgreSQL (#1111 Bug Evidence, #1117 Durable Memory) remains Source of Truth.
- Every candidate must be exactly rescored and read back against canonical records.
- Scope isolation (Owner/Tenant/Repo/Environment) is enforced before ranking.
- No ScaNN result creates Permission, Transition, or VERIFIED status.

Submodules:
- scann_manifest: Vector Snapshot Manifest contract and validation
- scann_snapshot_export: Export from canonical records

Issue: #1171
"""

from .scann_manifest import (
    SCHEMA_VERSION,
    ManifestContractError,
    DistanceMetric,
    Normalization,
    EmbeddingDataType,
    IndexPartition,
    IndexQuantization,
    ScopeBinding,
    EmbeddingConfig,
    SourceRecordRef,
    ScaNNBuildConfig,
    CPUArchitecture,
    ChunkManifest,
    RecallReceipt,
    VectorSnapshotManifest,
    validate_manifest_completeness,
    check_scope_drift,
    check_revision_drift,
    check_embedding_drift,
)

from .scann_snapshot_export import (
    ExportContractError,
    ExportRecord,
    SnapshotExportResult,
    normalize_content_for_embedding,
    compute_content_hash,
    extract_bug_evidence_for_export,
    extract_memory_leaf_for_export,
    export_snapshot,
    build_manifest_from_export,
)

from .scann_exact_rescore import (
    ExactContractError,
    ExactCandidate,
    ExactSearchResult,
    recall_at_k,
    exact_distance,
    normalize_vector,
    search_exact,
)


__all__ = [
    # Manifest
    "SCHEMA_VERSION",
    "ManifestContractError",
    "DistanceMetric",
    "Normalization",
    "EmbeddingDataType",
    "IndexPartition",
    "IndexQuantization",
    "ScopeBinding",
    "EmbeddingConfig",
    "SourceRecordRef",
    "ScaNNBuildConfig",
    "CPUArchitecture",
    "ChunkManifest",
    "RecallReceipt",
    "VectorSnapshotManifest",
    "validate_manifest_completeness",
    "check_scope_drift",
    "check_revision_drift",
    "check_embedding_drift",
    # Export
    "ExportContractError",
    "ExportRecord",
    "SnapshotExportResult",
    "normalize_content_for_embedding",
    "compute_content_hash",
    "extract_bug_evidence_for_export",
    "extract_memory_leaf_for_export",
    "export_snapshot",
    "build_manifest_from_export",
    # Exact rescore
    "ExactContractError",
    "ExactCandidate",
    "ExactSearchResult",
    "recall_at_k",
    "exact_distance",
    "normalize_vector",
    "search_exact",
]
