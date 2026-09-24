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
- bitcoin_graph: Canonical Bitcoin transaction/UTXO graph primitives
- bitcoin_scann: ScaNN candidate generation and exact rescore bridge
- bitcoin_wolfram_contract: Bounded Wolfram CAG graph checks

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

from .bitcoin_graph import (
    SATOSHIS_PER_BTC,
    BitcoinGraphContractError,
    BitcoinInput,
    BitcoinOutput,
    BitcoinTransaction,
    BitcoinBlock,
    PrevoutRef,
    GraphEdge,
    GraphSnapshot,
    transaction_from_rpc,
    block_from_rpc,
    graph_edges,
    build_snapshot,
    transaction_feature_vector,
    transaction_fingerprint,
)
from .bitcoin_scann import (
    BitcoinScannContractError,
    BitcoinVectorRecord,
    AnnCandidate,
    ExactRescoredCandidate,
    SimilarityReceipt,
    exact_rank_all,
    rescore_ann_candidates,
    recall_at_k as bitcoin_recall_at_k,
    run_ann_then_exact,
)
from .bitcoin_canonical_store import (
    BitcoinStoreError,
    StoredPrevout,
    BitcoinCanonicalStore,
)
from .bitcoin_chain_indexer import (
    BitcoinIngestError,
    BitcoinIngestResult,
    ingest_chain,
)
from .bitcoin_scann_runtime import (
    BitcoinScannRuntimeError,
    build_live_searcher,
    search_with_exact_rescore,
)

from .bitcoin_wolfram_contract import (
    BitcoinWolframContractError,
    BitcoinCheck,
    FeeObservation,
    ChronologyObservation,
    UniqueSpendObservation,
    VectorDistanceObservation,
    build_wolfram_expression,
    evaluate_local as evaluate_bitcoin_check_local,
    build_cag_countercheck,
    evidence_binding,
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
    # Bitcoin graph
    "SATOSHIS_PER_BTC",
    "BitcoinGraphContractError",
    "BitcoinInput",
    "BitcoinOutput",
    "BitcoinTransaction",
    "BitcoinBlock",
    "PrevoutRef",
    "GraphEdge",
    "GraphSnapshot",
    "transaction_from_rpc",
    "block_from_rpc",
    "graph_edges",
    "build_snapshot",
    "transaction_feature_vector",
    "transaction_fingerprint",
    # Bitcoin ScaNN bridge
    "BitcoinScannContractError",
    "BitcoinVectorRecord",
    "AnnCandidate",
    "ExactRescoredCandidate",
    "SimilarityReceipt",
    "exact_rank_all",
    "rescore_ann_candidates",
    "bitcoin_recall_at_k",
    "run_ann_then_exact",
    # Live ScaNN runtime
    "BitcoinScannRuntimeError",
    "build_live_searcher",
    "search_with_exact_rescore",
    # Bitcoin canonical persistence
    "BitcoinStoreError",
    "StoredPrevout",
    "BitcoinCanonicalStore",
    "BitcoinIngestError",
    "BitcoinIngestResult",
    "ingest_chain",
    # Bitcoin Wolfram CAG contract
    "BitcoinWolframContractError",
    "BitcoinCheck",
    "FeeObservation",
    "ChronologyObservation",
    "UniqueSpendObservation",
    "VectorDistanceObservation",
    "build_wolfram_expression",
    "evaluate_bitcoin_check_local",
    "build_cag_countercheck",
    "evidence_binding",
    # Exact rescore
    "ExactContractError",
    "ExactCandidate",
    "ExactSearchResult",
    "recall_at_k",
    "exact_distance",
    "normalize_vector",
    "search_exact",
]
