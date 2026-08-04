"""Revision-bound Vector Snapshot Manifest for ScaNN Incident Candidate Index.

Defines the immutable manifest that binds a ScaNN index to its source records,
embedding configuration, and build parameters. The manifest is the authoritative
source for index provenance and must be verified before any candidate search.

Design constraints:
- No network, database, filesystem, clock or random access in this module.
- Manifest is append-only; model/dimension changes produce a new manifest.
- Same source revision must produce identical source/manifest hashes.
- Timestamps are metadata, not index identity.
- Fail-closed on incomplete or unverifiable manifest.

Canonical ownership:
- #1111 owns verified Bug Evidence Cases (failure families, signatures).
- #1117 owns Durable Memory Leaves (long-lived insights, evidence classes).
- PostgreSQL remains Source of Truth for all canonical records.
- ScaNN is exclusively a derived retrieval projection, never canonical truth.

Issue: #1171
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, FrozenSet, Sequence, Tuple


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------
SCHEMA_VERSION: Final[str] = "sovereign.scann-manifest.v1"

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------
_MAX_OWNER_LEN: Final[int] = 128
_MAX_TENANT_LEN: Final[int] = 128
_MAX_REPO_LEN: Final[int] = 256
_MAX_ENV_LEN: Final[int] = 64
_MAX_MODEL_ID_LEN: Final[int] = 128
_MAX_DIMENSION: Final[int] = 4096
_MAX_RECORDS: Final[int] = 1_000_000
_MAX_CHUNKS: Final[int] = 1024

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:-]{1,119}$")
_OWNER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_.]{0,127}$")
_ALLOWED_EVIDENCE_CLASSES: Final[FrozenSet[str]] = frozenset({"verified", "observed"})


class ManifestContractError(ValueError):
    """An input violated a manifest invariant."""


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class DistanceMetric(str, Enum):
    """Supported distance functions for vector comparison."""
    COSINE = "cosine"
    L2 = "l2"
    DOT_PRODUCT = "dot_product"


class Normalization(str, Enum):
    """Vector normalization applied during indexing."""
    NONE = "none"
    L2 = "l2"
    L2_SQUARED = "l2_squared"


class EmbeddingDataType(str, Enum):
    """Data type for vector dimensions."""
    FLOAT32 = "float32"
    FLOAT16 = "float16"
    INT8 = "int8"


class IndexPartition(str, Enum):
    """Index partitioning strategy."""
    NONE = "none"
    FLAT = "flat"
    PARTITIONED = "partitioned"


class IndexQuantization(str, Enum):
    """Vector quantization strategy."""
    NONE = "none"
    SQ8 = "sq8"
    PQ = "pq"
    SQ4 = "sq4"


# ---------------------------------------------------------------------------
# Scope binding
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ScopeBinding:
    """Owner/Tenant/Repo/Environment scope for the index.

    All similarity ranking must respect scope boundaries. Cross-scope hits
    are blocked even if similarity is high.
    """
    owner: str
    tenant: str
    repo_owner: str
    repo_name: str
    environment: str

    def __post_init__(self) -> None:
        if not _OWNER_PATTERN.fullmatch(self.owner):
            raise ManifestContractError(f"Invalid owner: {self.owner!r}")
        if not _OWNER_PATTERN.fullmatch(self.tenant):
            raise ManifestContractError(f"Invalid tenant: {self.tenant!r}")
        if not _OWNER_PATTERN.fullmatch(self.repo_owner):
            raise ManifestContractError(f"Invalid repo_owner: {self.repo_owner!r}")
        if not _OWNER_PATTERN.fullmatch(self.repo_name):
            raise ManifestContractError(f"Invalid repo_name: {self.repo_name!r}")
        if len(self.environment) > _MAX_ENV_LEN:
            raise ManifestContractError(f"environment exceeds {_MAX_ENV_LEN} chars")

    @property
    def scope_hash(self) -> str:
        """Deterministic hash of the scope for manifest binding."""
        return _canonical_sha256({
            "owner": self.owner,
            "tenant": self.tenant,
            "repo_owner": self.repo_owner,
            "repo_name": self.repo_name,
            "environment": self.environment,
        })


# ---------------------------------------------------------------------------
# Embedding configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    """Embedding provider, model and dimensional configuration."""
    provider: str
    model_id: str
    model_revision: str
    model_hash: str          # SHA-256 of model binary/config if available
    dimension: int
    data_type: EmbeddingDataType
    normalization: Normalization
    distance_metric: DistanceMetric

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.provider):
            raise ManifestContractError(f"Invalid provider: {self.provider!r}")
        if not self.model_id or len(self.model_id) > _MAX_MODEL_ID_LEN:
            raise ManifestContractError(
                f"model_id must contain 1-{_MAX_MODEL_ID_LEN} chars"
            )
        if not self.model_revision:
            raise ManifestContractError("model_revision must not be empty")
        if not _SHA64.fullmatch(self.model_hash):
            raise ManifestContractError(f"model_hash must be SHA-256")
        if not 1 <= self.dimension <= _MAX_DIMENSION:
            raise ManifestContractError(f"dimension must be 1-{_MAX_DIMENSION}")

    @property
    def config_hash(self) -> str:
        """Deterministic hash of the embedding configuration."""
        return _canonical_sha256({
            "provider": self.provider,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "model_hash": self.model_hash,
            "dimension": self.dimension,
            "data_type": self.data_type.value,
            "normalization": self.normalization.value,
            "distance_metric": self.distance_metric.value,
        })


# ---------------------------------------------------------------------------
# Source record binding
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SourceRecordRef:
    """Reference to a single source record in the canonical store."""
    record_id: str
    content_hash: str         # SHA-256 of the canonical record content
    evidence_class: str       # reported, observed, verified, contradicted, invalidated
    source_revision: str      # Git SHA-40 at time of export
    source_file: str          # Canonical file path in source revision

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.record_id):
            raise ManifestContractError(f"Invalid record_id: {self.record_id!r}")
        if not _SHA64.fullmatch(self.content_hash):
            raise ManifestContractError(f"content_hash must be SHA-256")
        if self.evidence_class not in _ALLOWED_EVIDENCE_CLASSES:
            raise ManifestContractError(
                f"evidence_class must be one of {sorted(_ALLOWED_EVIDENCE_CLASSES)}"
            )
        if not _SHA40.fullmatch(self.source_revision):
            raise ManifestContractError(f"source_revision must be SHA-40")
        if not self.source_file.startswith("/") or self.source_file == "/":
            raise ManifestContractError(f"source_file must be an absolute record path")


# ---------------------------------------------------------------------------
# ScaNN build configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ScaNNBuildConfig:
    """ScaNN index build parameters."""
    scann_version: str        # e.g., "2.12.0"
    partition: IndexPartition
    partition_count: int      # Number of partitions (1 for flat)
    quantization: IndexQuantization
    pq_codebooks: int         # Number of PQ codebooks (0 if not using PQ)
    sq_block_size: int        # Block size for SQ (0 if not using SQ)
    min_cluster_size: int     # Minimum records per cluster
    max_cluster_size: int     # Maximum records per cluster
    training_sample_size: int # Records used for training partitions/quantization
    reorder_window: int       # Reorder window size for exact rescoring

    def __post_init__(self) -> None:
        if not self.scann_version:
            raise ManifestContractError("scann_version must not be empty")
        if self.partition_count < 1:
            raise ManifestContractError("partition_count must be >= 1")
        for name in (
            "pq_codebooks",
            "sq_block_size",
            "min_cluster_size",
            "max_cluster_size",
            "training_sample_size",
            "reorder_window",
        ):
            if getattr(self, name) < 0:
                raise ManifestContractError(f"{name} must be >= 0")
        if self.min_cluster_size > self.max_cluster_size:
            raise ManifestContractError("min_cluster_size must be <= max_cluster_size")
        if self.quantization == IndexQuantization.PQ and self.pq_codebooks == 0:
            raise ManifestContractError("PQ quantization requires pq_codebooks > 0")
        if self.quantization != IndexQuantization.PQ and self.pq_codebooks != 0:
            raise ManifestContractError("pq_codebooks must be 0 unless quantization is PQ")
        if self.quantization in {IndexQuantization.SQ8, IndexQuantization.SQ4} and self.sq_block_size == 0:
            raise ManifestContractError("SQ quantization requires sq_block_size > 0")
        if self.quantization not in {IndexQuantization.SQ8, IndexQuantization.SQ4} and self.sq_block_size != 0:
            raise ManifestContractError("sq_block_size must be 0 unless quantization is SQ")

    @property
    def config_hash(self) -> str:
        """Deterministic hash of the build configuration."""
        return _canonical_sha256({
            "scann_version": self.scann_version,
            "partition": self.partition.value,
            "partition_count": self.partition_count,
            "quantization": self.quantization.value,
            "pq_codebooks": self.pq_codebooks,
            "sq_block_size": self.sq_block_size,
            "min_cluster_size": self.min_cluster_size,
            "max_cluster_size": self.max_cluster_size,
            "training_sample_size": self.training_sample_size,
            "reorder_window": self.reorder_window,
        })


# ---------------------------------------------------------------------------
# CPU/architecture binding
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CPUArchitecture:
    """CPU architecture and instruction set requirements for the index."""
    architecture: str         # e.g., "x86_64", "arm64"
    features: Tuple[str, ...] # Required CPU features (e.g., "avx2", "avx512")

    def __post_init__(self) -> None:
        if not self.architecture:
            raise ManifestContractError("architecture must not be empty")
        for feature in self.features:
            if not _IDENTIFIER.fullmatch(feature):
                raise ManifestContractError(f"Invalid CPU feature: {feature!r}")

    @property
    def features_hash(self) -> str:
        return _canonical_sha256({
            "architecture": self.architecture,
            "features": sorted(self.features),
        })


# ---------------------------------------------------------------------------
# Chunk manifest for large indices
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ChunkManifest:
    """Manifest for one contiguous, content-addressed index chunk."""
    chunk_index: int
    record_start: int         # Starting record index in this chunk
    record_end: int           # Ending record index (exclusive)
    chunk_hash: str           # SHA-256 of chunk data
    chunk_size_bytes: int

    def __post_init__(self) -> None:
        if self.chunk_index < 0:
            raise ManifestContractError("chunk_index must be >= 0")
        if self.record_start < 0 or self.record_start >= self.record_end:
            raise ManifestContractError("chunk record range must be non-empty and non-negative")
        if not _SHA64.fullmatch(self.chunk_hash):
            raise ManifestContractError("chunk_hash must be SHA-256")
        if self.chunk_size_bytes <= 0:
            raise ManifestContractError("chunk_size_bytes must be > 0")


# ---------------------------------------------------------------------------
# Benchmark/recall receipt
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RecallReceipt:
    """Benchmark results validating index recall quality."""
    recall_at_1: float
    recall_at_10: float
    recall_at_100: float
    precision_at_k: float
    candidate_stability: float   # Jaccard overlap for same snapshot
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    memory_mb: float
    build_time_seconds: float
    benchmark_revision: str       # Git SHA-40 of benchmark code
    benchmark_dataset_hash: str   # SHA-256 of benchmark dataset

    def __post_init__(self) -> None:
        # Recall and precision values must be 0-1
        for name in ("recall_at_1", "recall_at_10", "recall_at_100", "precision_at_k",
                     "candidate_stability"):
            val = getattr(self, name)
            if not (0.0 <= val <= 1.0):
                raise ManifestContractError(f"{name} must be 0-1 (got {val})")
        # Latency, memory, and build time can be larger
        for name in ("latency_p50_ms", "latency_p95_ms", "latency_p99_ms",
                     "memory_mb", "build_time_seconds"):
            val = getattr(self, name)
            if not (0.0 <= val <= 10000.0):
                raise ManifestContractError(f"{name} must be 0-10000 (got {val})")
        if not _SHA40.fullmatch(self.benchmark_revision):
            raise ManifestContractError("benchmark_revision must be SHA-40")
        if not _SHA64.fullmatch(self.benchmark_dataset_hash):
            raise ManifestContractError("benchmark_dataset_hash must be SHA-256")


# ---------------------------------------------------------------------------
# Vector Snapshot Manifest (primary artifact)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class VectorSnapshotManifest:
    """Immutable manifest binding a ScaNN index to its source and configuration.

    The manifest is the authoritative source for index provenance. It must be
    verified before any candidate search. Missing or unverifiable manifest
    blocks search fail-closed.

    Required fields for a valid manifest:
    - Schema version and manifest version
    - Scope binding (owner/tenant/repo/environment)
    - Source revision and export hash
    - Sorted source record references with content hashes
    - Embedding configuration
    - ScaNN build configuration
    - Vector count and chunk manifest (if applicable)
    - Index hash
    - CPU architecture requirements
    - Recall receipt (optional but recommended)
    """
    # Versioning
    schema_version: str
    manifest_version: str      # Semantic version of manifest schema

    # Scope
    scope: ScopeBinding

    # Source binding
    source_revision: str       # Git SHA-40 of source repository
    source_export_hash: str    # SHA-256 of exported source data

    # Record inventory (sorted by record_id for deterministic hash)
    source_records: Tuple[SourceRecordRef, ...]

    # Embedding
    embedding_config: EmbeddingConfig

    # ScaNN
    build_config: ScaNNBuildConfig

    # Index
    vector_count: int
    chunk_manifest: Tuple[ChunkManifest, ...]
    index_hash: str           # SHA-256 of the built index file(s)

    # Architecture
    cpu_architecture: CPUArchitecture

    # Benchmark (optional)
    recall_receipt: RecallReceipt | None = None

    # Metadata (not used for identity)
    built_at: str | None = None   # ISO-8601 timestamp

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ManifestContractError(
                f"Expected schema version {SCHEMA_VERSION}, got {self.schema_version!r}"
            )
        if not self.manifest_version:
            raise ManifestContractError("manifest_version must not be empty")
        if not _SHA40.fullmatch(self.source_revision):
            raise ManifestContractError("source_revision must be SHA-40")
        if not _SHA64.fullmatch(self.source_export_hash):
            raise ManifestContractError("source_export_hash must be SHA-256")
        if not _SHA64.fullmatch(self.index_hash):
            raise ManifestContractError("index_hash must be SHA-256")
        if len(self.source_records) != self.vector_count:
            raise ManifestContractError(
                f"source_records count ({len(self.source_records)}) != vector_count ({self.vector_count})"
            )
        # Verify records are unique, sorted and bound to the manifest revision.
        record_ids = [r.record_id for r in self.source_records]
        if record_ids != sorted(record_ids):
            raise ManifestContractError("source_records must be sorted by record_id")
        if len(record_ids) != len(set(record_ids)):
            raise ManifestContractError("source_records must not contain duplicate record_id values")
        if any(r.source_revision != self.source_revision for r in self.source_records):
            raise ManifestContractError("every source_record must match manifest source_revision")

        # A present chunk manifest must be ordered, contiguous and cover all vectors.
        if len(self.chunk_manifest) > _MAX_CHUNKS:
            raise ManifestContractError(f"chunk_manifest exceeds {_MAX_CHUNKS} chunks")
        if self.chunk_manifest:
            expected_start = 0
            for expected_index, chunk in enumerate(self.chunk_manifest):
                if chunk.chunk_index != expected_index:
                    raise ManifestContractError("chunk_index values must be contiguous from 0")
                if chunk.record_start != expected_start:
                    raise ManifestContractError("chunk record ranges must be contiguous from 0")
                expected_start = chunk.record_end
            if expected_start != self.vector_count:
                raise ManifestContractError("chunk_manifest must cover exactly vector_count records")

    @property
    def manifest_id(self) -> str:
        """Unique identifier for this manifest."""
        return f"vsm:{self.schema_version}:{self.source_revision[:8]}:{self.index_hash[:16]}"

    @property
    def total_hash(self) -> str:
        """Canonical hash of the entire manifest for verification."""
        return _canonical_sha256({
            "schema_version": self.schema_version,
            "manifest_version": self.manifest_version,
            "scope_hash": self.scope.scope_hash,
            "source_revision": self.source_revision,
            "source_export_hash": self.source_export_hash,
            "records": [
                {
                    "record_id": r.record_id,
                    "content_hash": r.content_hash,
                    "evidence_class": r.evidence_class,
                    "source_revision": r.source_revision,
                    "source_file": r.source_file,
                }
                for r in self.source_records
            ],
            "embedding_config_hash": self.embedding_config.config_hash,
            "build_config_hash": self.build_config.config_hash,
            "vector_count": self.vector_count,
            "chunks": [
                {
                    "chunk_index": c.chunk_index,
                    "record_start": c.record_start,
                    "record_end": c.record_end,
                    "chunk_hash": c.chunk_hash,
                    "chunk_size_bytes": c.chunk_size_bytes,
                }
                for c in self.chunk_manifest
            ],
            "index_hash": self.index_hash,
            "cpu_features_hash": self.cpu_architecture.features_hash,
        })

    def verify_record(self, record_id: str, content_hash: str) -> bool:
        """Verify a record is in this manifest with matching content hash."""
        import bisect
        record_ids = [r.record_id for r in self.source_records]
        idx = bisect.bisect_left(record_ids, record_id)
        if idx < len(record_ids) and record_ids[idx] == record_id:
            return self.source_records[idx].content_hash == content_hash
        return False

    def to_dict(self) -> dict:
        """Serialize manifest to JSON-compatible dict."""
        return {
            "schema_version": self.schema_version,
            "manifest_version": self.manifest_version,
            "scope": {
                "owner": self.scope.owner,
                "tenant": self.scope.tenant,
                "repo_owner": self.scope.repo_owner,
                "repo_name": self.scope.repo_name,
                "environment": self.scope.environment,
            },
            "source_revision": self.source_revision,
            "source_export_hash": self.source_export_hash,
            "source_records": [
                {
                    "record_id": r.record_id,
                    "content_hash": r.content_hash,
                    "evidence_class": r.evidence_class,
                    "source_revision": r.source_revision,
                    "source_file": r.source_file,
                }
                for r in self.source_records
            ],
            "embedding_config": {
                "provider": self.embedding_config.provider,
                "model_id": self.embedding_config.model_id,
                "model_revision": self.embedding_config.model_revision,
                "model_hash": self.embedding_config.model_hash,
                "dimension": self.embedding_config.dimension,
                "data_type": self.embedding_config.data_type.value,
                "normalization": self.embedding_config.normalization.value,
                "distance_metric": self.embedding_config.distance_metric.value,
            },
            "build_config": {
                "scann_version": self.build_config.scann_version,
                "partition": self.build_config.partition.value,
                "partition_count": self.build_config.partition_count,
                "quantization": self.build_config.quantization.value,
                "pq_codebooks": self.build_config.pq_codebooks,
                "sq_block_size": self.build_config.sq_block_size,
                "min_cluster_size": self.build_config.min_cluster_size,
                "max_cluster_size": self.build_config.max_cluster_size,
                "training_sample_size": self.build_config.training_sample_size,
                "reorder_window": self.build_config.reorder_window,
            },
            "vector_count": self.vector_count,
            "chunk_manifest": [
                {
                    "chunk_index": c.chunk_index,
                    "record_start": c.record_start,
                    "record_end": c.record_end,
                    "chunk_hash": c.chunk_hash,
                    "chunk_size_bytes": c.chunk_size_bytes,
                }
                for c in self.chunk_manifest
            ],
            "index_hash": self.index_hash,
            "cpu_architecture": {
                "architecture": self.cpu_architecture.architecture,
                "features": list(self.cpu_architecture.features),
            },
            "recall_receipt": {
                "recall_at_1": self.recall_receipt.recall_at_1,
                "recall_at_10": self.recall_receipt.recall_at_10,
                "recall_at_100": self.recall_receipt.recall_at_100,
                "precision_at_k": self.recall_receipt.precision_at_k,
                "candidate_stability": self.recall_receipt.candidate_stability,
                "latency_p50_ms": self.recall_receipt.latency_p50_ms,
                "latency_p95_ms": self.recall_receipt.latency_p95_ms,
                "latency_p99_ms": self.recall_receipt.latency_p99_ms,
                "memory_mb": self.recall_receipt.memory_mb,
                "build_time_seconds": self.recall_receipt.build_time_seconds,
                "benchmark_revision": self.recall_receipt.benchmark_revision,
                "benchmark_dataset_hash": self.recall_receipt.benchmark_dataset_hash,
            } if self.recall_receipt else None,
            "built_at": self.built_at,
            "manifest_id": self.manifest_id,
            "total_hash": self.total_hash,
        }


# ---------------------------------------------------------------------------
# Canonical hash helper
# ---------------------------------------------------------------------------

def _canonical_sha256(value: object) -> str:
    """Deterministic SHA-256 over the UTF-8 JSON serialisation of *value*."""
    serialised = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Manifest validation helpers
# ---------------------------------------------------------------------------

def validate_manifest_completeness(manifest: VectorSnapshotManifest) -> Tuple[bool, str]:
    """Validate that a manifest is complete and self-consistent.

    Returns (is_valid, error_message).
    """
    if not manifest.schema_version:
        return False, "Missing schema_version"
    if not manifest.source_revision:
        return False, "Missing source_revision"
    if not manifest.source_records:
        return False, "No source_records"
    if manifest.vector_count <= 0:
        return False, f"Invalid vector_count: {manifest.vector_count}"
    if not manifest.index_hash:
        return False, "Missing index_hash"

    # Check for duplicate record IDs
    record_ids = [r.record_id for r in manifest.source_records]
    if len(record_ids) != len(set(record_ids)):
        return False, "Duplicate record_id in source_records"

    return True, ""


def check_scope_drift(
    manifest_scope: ScopeBinding,
    query_scope: ScopeBinding,
) -> bool:
    """Check if query scope matches manifest scope.

    Returns True if scopes match (no drift), False if drift detected.
    """
    return (
        manifest_scope.owner == query_scope.owner
        and manifest_scope.tenant == query_scope.tenant
        and manifest_scope.repo_owner == query_scope.repo_owner
        and manifest_scope.repo_name == query_scope.repo_name
        and manifest_scope.environment == query_scope.environment
    )


def check_revision_drift(
    manifest: VectorSnapshotManifest,
    current_revision: str,
) -> bool:
    """Check if source revision has drifted.

    Returns True if revision matches (no drift), False if drifted.
    """
    return manifest.source_revision == current_revision


def check_embedding_drift(
    manifest_config: EmbeddingConfig,
    current_config: EmbeddingConfig,
) -> bool:
    """Check if embedding configuration has drifted.

    Returns True if configs match (no drift), False if drift detected.
    """
    return manifest_config.config_hash == current_config.config_hash


__all__ = [
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
]
