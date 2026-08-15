"""Exact brute-force reference search path for ScaNN candidate rescoring.

This module implements the deterministic, dependency-free exact nearest-neighbor
search that serves as ground truth for measuring ScaNN ANN candidate recall
(Issue #1171, step 3). It is pure-stdlib (no numpy) so it can run in any
backend Python runtime and inside the production mirror without added deps.

Design principles (inherited from the retrieval package):
- The exact path is a *reference* projection, never canonical truth.
- PostgreSQL (#1111 Bug Evidence, #1117 Durable Memory) remains Source of Truth.
- Every returned candidate is read back against the bound VectorSnapshotManifest
  via ``manifest.verify_record``; a missing or mismatched record fails closed.
- Scope, revision and embedding-config drift are enforced *before* ranking.
- No exact result creates Permission, Transition, or VERIFIED status.
- Ranking is deterministic: ties break by ``record_id`` so the same
  (manifest, query, k) always yields byte-identical candidate ordering.

Issue: #1171
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Final, List, Sequence, Tuple

from .scann_manifest import (
    DistanceMetric,
    EmbeddingConfig,
    ManifestContractError,
    Normalization,
    ScopeBinding,
    VectorSnapshotManifest,
    check_embedding_drift,
    check_revision_drift,
    check_scope_drift,
    validate_manifest_completeness,
)

__all__ = [
    "ExactContractError",
    "ExactCandidate",
    "ExactSearchResult",
    "recall_at_k",
    "exact_distance",
    "normalize_vector",
    "search_exact",
]


class ExactContractError(ValueError):
    """An input or drift condition violated the exact-rescore contract."""


_MAX_K: Final[int] = 100_000
_EPS: Final[float] = 1e-12


# ---------------------------------------------------------------------------
# Vector math (pure stdlib)
# ---------------------------------------------------------------------------

def normalize_vector(
    vector: Sequence[float],
    normalization: Normalization,
) -> Tuple[float, ...]:
    """Return *vector* normalized per *normalization*.

    - ``NONE``: returned unchanged (as a tuple).
    - ``L2``: divided by the L2 norm (sqrt of sum of squares) -> unit vector.
    - ``L2_SQUARED``: unit-normalized like ``L2`` (sum of squares == 1). The
      squared convention only affects the reported distance, not the ranking,
      so unit normalization keeps the reference path ranking-consistent with
      an index that stored L2_SQUARED-normalized vectors.

    A zero vector under non-NONE normalization raises ``ExactContractError``
    because it would produce a non-finite direction and an undefined ranking.
    """
    values = tuple(float(v) for v in vector)
    if normalization is Normalization.NONE:
        return values
    norm = math.sqrt(sum(v * v for v in values))
    if norm < _EPS:
        raise ExactContractError(
            "cannot normalize a zero-length vector under non-NONE normalization"
        )
    return tuple(v / norm for v in values)


def exact_distance(
    query: Sequence[float],
    vector: Sequence[float],
    metric: DistanceMetric,
) -> float:
    """Compute the exact distance between *query* and *vector*.

    The returned value is a *distance* (lower is better) for all metrics so
    that ranking is uniform:
    - ``COSINE``: ``1 - cosine_similarity`` in [0, 2].
    - ``L2``: euclidean distance.
    - ``DOT_PRODUCT``: ``-dot(query, vector)`` (higher dot product ranks first).
    """
    if len(query) != len(vector):
        raise ExactContractError(
            f"dimension mismatch: query={len(query)} vector={len(vector)}"
        )
    if metric is DistanceMetric.COSINE:
        q_norm = math.sqrt(sum(q * q for q in query))
        v_norm = math.sqrt(sum(v * v for v in vector))
        if q_norm < _EPS or v_norm < _EPS:
            raise ExactContractError("cosine distance undefined for a zero vector")
        dot = sum(q * v for q, v in zip(query, vector))
        cos_sim = dot / (q_norm * v_norm)
        # Clamp to [-1, 1] to absorb float error that could push acos/domain.
        cos_sim = max(-1.0, min(1.0, cos_sim))
        return 1.0 - cos_sim
    if metric is DistanceMetric.L2:
        return math.sqrt(sum((q - v) ** 2 for q, v in zip(query, vector)))
    if metric is DistanceMetric.DOT_PRODUCT:
        return -sum(q * v for q, v in zip(query, vector))
    raise ExactContractError(f"unsupported distance metric: {metric!r}")


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ExactCandidate:
    """A single exactly-ranked candidate with manifest readback evidence."""
    rank: int                  # 1-based rank within the result set
    record_id: str
    content_hash: str          # read back from the manifest (verified)
    evidence_class: str
    distance: float            # lower is better (see exact_distance)

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "record_id": self.record_id,
            "content_hash": self.content_hash,
            "evidence_class": self.evidence_class,
            "distance": self.distance,
        }


@dataclass(frozen=True, slots=True)
class ExactSearchResult:
    """Immutable, deterministic exact-search receipt.

    Every field that influences ranking is captured so that two searches with
    equal ``search_hash`` are byte-identical projections.
    """
    manifest_id: str
    scope_owner: str
    scope_tenant: str
    scope_repo_owner: str
    scope_repo_name: str
    scope_environment: str
    source_revision: str
    embedding_config_hash: str
    distance_metric: str
    normalization: str
    query_hash: str            # SHA-256 of the normalized query vector
    requested_k: int
    total_vectors: int
    returned: int
    candidates: Tuple[ExactCandidate, ...]
    scope_ok: bool
    revision_ok: bool
    embedding_ok: bool
    search_hash: str           # canonical hash of the ranked result

    @property
    def record_ids(self) -> Tuple[str, ...]:
        return tuple(c.record_id for c in self.candidates)

    def to_dict(self) -> dict:
        return {
            "manifest_id": self.manifest_id,
            "scope": {
                "owner": self.scope_owner,
                "tenant": self.scope_tenant,
                "repo_owner": self.scope_repo_owner,
                "repo_name": self.scope_repo_name,
                "environment": self.scope_environment,
            },
            "source_revision": self.source_revision,
            "embedding_config_hash": self.embedding_config_hash,
            "distance_metric": self.distance_metric,
            "normalization": self.normalization,
            "query_hash": self.query_hash,
            "requested_k": self.requested_k,
            "total_vectors": self.total_vectors,
            "returned": self.returned,
            "candidates": [c.to_dict() for c in self.candidates],
            "scope_ok": self.scope_ok,
            "revision_ok": self.revision_ok,
            "embedding_ok": self.embedding_ok,
            "search_hash": self.search_hash,
        }


# ---------------------------------------------------------------------------
# Internal hashing helpers
# ---------------------------------------------------------------------------

def _canonical_sha256(value: object) -> str:
    serialised = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def _vector_hash(vector: Sequence[float]) -> str:
    # repr(float) is deterministic for a given float bit-pattern.
    payload = ",".join(repr(float(v)) for v in vector)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Exact search
# ---------------------------------------------------------------------------

def search_exact(
    manifest: VectorSnapshotManifest,
    vectors: Sequence[Sequence[float]],
    query: Sequence[float],
    k: int,
    query_scope: ScopeBinding,
    current_revision: str,
    current_embedding_config: EmbeddingConfig,
) -> ExactSearchResult:
    """Run an exact brute-force nearest-neighbor search and return a receipt.

    Contract (all enforced fail-closed before ranking):
    - *manifest* passes ``validate_manifest_completeness``.
    - ``len(vectors)`` equals ``manifest.vector_count`` and the record count.
    - Every vector and the query match ``embedding_config.dimension``.
    - ``query_scope`` matches the manifest scope (no scope drift).
    - ``current_revision`` matches the manifest source revision (no revision drift).
    - ``current_embedding_config`` matches the manifest embedding config (no embedding drift).
    - ``k >= 1`` and ``k <= _MAX_K``.

    Each returned candidate is read back through ``manifest.verify_record`` so a
    manifest that does not contain the record (or whose content hash differs)
    raises ``ExactContractError`` instead of returning an unverified candidate.

    When ``k`` exceeds the vector count, all vectors are returned in ranked
    order (``returned == total_vectors``); this is a degraded-but-honest result,
    not a failure.
    """
    if not isinstance(k, int) or isinstance(k, bool):
        raise ExactContractError(f"k must be an int (got {type(k).__name__})")
    if k < 1:
        raise ExactContractError(f"k must be >= 1 (got {k})")
    if k > _MAX_K:
        raise ExactContractError(f"k must be <= {_MAX_K} (got {k})")

    valid, msg = validate_manifest_completeness(manifest)
    if not valid:
        raise ExactContractError(f"manifest incomplete: {msg}")

    if len(vectors) != manifest.vector_count:
        raise ExactContractError(
            f"vector count mismatch: vectors={len(vectors)} manifest={manifest.vector_count}"
        )
    if len(vectors) != len(manifest.source_records):
        raise ExactContractError(
            "vectors and source_records are not aligned "
            f"(vectors={len(vectors)} records={len(manifest.source_records)})"
        )

    dim = manifest.embedding_config.dimension
    q_list = [float(v) for v in query]
    if len(q_list) != dim:
        raise ExactContractError(
            f"query dimension mismatch: query={len(q_list)} config={dim}"
        )

    scope_ok = check_scope_drift(manifest.scope, query_scope)
    revision_ok = check_revision_drift(manifest, current_revision)
    embedding_ok = check_embedding_drift(manifest.embedding_config, current_embedding_config)
    if not scope_ok:
        raise ExactContractError("scope drift: query scope does not match manifest scope")
    if not revision_ok:
        raise ExactContractError(
            f"revision drift: manifest={manifest.source_revision[:8]} current={current_revision[:8]}"
        )
    if not embedding_ok:
        raise ExactContractError("embedding config drift: query config does not match manifest")

    normalization = manifest.embedding_config.normalization
    metric = manifest.embedding_config.distance_metric

    try:
        norm_query = normalize_vector(q_list, normalization)
    except ExactContractError:
        raise
    query_hash = _vector_hash(norm_query)

    scored: List[Tuple[float, str, str, str]] = []
    for vec, record in zip(vectors, manifest.source_records):
        v_list = [float(v) for v in vec]
        if len(v_list) != dim:
            raise ExactContractError(
                f"vector dimension mismatch for record {record.record_id}: "
                f"vector={len(v_list)} config={dim}"
            )
        try:
            norm_vec = normalize_vector(v_list, normalization)
        except ExactContractError as exc:
            raise ExactContractError(
                f"cannot normalize vector for record {record.record_id}: {exc}"
            ) from exc
        dist = exact_distance(norm_query, norm_vec, metric)
        scored.append((dist, record.record_id, record.content_hash, record.evidence_class))

    # Deterministic ranking: distance first (lower is better), then record_id.
    scored.sort(key=lambda item: (item[0], item[1]))

    take = min(k, len(scored))
    candidates: List[ExactCandidate] = []
    for index, (dist, record_id, content_hash, evidence_class) in enumerate(scored[:take]):
        # Manifest readback: the candidate must be present with a matching hash.
        if not manifest.verify_record(record_id, content_hash):
            raise ExactContractError(
                f"manifest readback failed for ranked candidate {record_id}"
            )
        candidates.append(
            ExactCandidate(
                rank=index + 1,
                record_id=record_id,
                content_hash=content_hash,
                evidence_class=evidence_class,
                distance=dist,
            )
        )

    candidate_payload = [
        {"rank": c.rank, "record_id": c.record_id, "distance": c.distance}
        for c in candidates
    ]
    search_hash = _canonical_sha256({
        "manifest_id": manifest.manifest_id,
        "query_hash": query_hash,
        "distance_metric": metric.value,
        "normalization": normalization.value,
        "k": k,
        "candidates": candidate_payload,
    })

    return ExactSearchResult(
        manifest_id=manifest.manifest_id,
        scope_owner=manifest.scope.owner,
        scope_tenant=manifest.scope.tenant,
        scope_repo_owner=manifest.scope.repo_owner,
        scope_repo_name=manifest.scope.repo_name,
        scope_environment=manifest.scope.environment,
        source_revision=manifest.source_revision,
        embedding_config_hash=manifest.embedding_config.config_hash,
        distance_metric=metric.value,
        normalization=normalization.value,
        query_hash=query_hash,
        requested_k=k,
        total_vectors=manifest.vector_count,
        returned=len(candidates),
        candidates=tuple(candidates),
        scope_ok=scope_ok,
        revision_ok=revision_ok,
        embedding_ok=embedding_ok,
        search_hash=search_hash,
    )


# ---------------------------------------------------------------------------
# Recall measurement
# ---------------------------------------------------------------------------

def recall_at_k(
    approx_record_ids: Sequence[str],
    exact_record_ids: Sequence[str],
    k: int,
) -> float:
    """Recall@k of an ANN candidate set against the exact reference set.

    Defined as ``|approx_k ∩ exact_k| / min(k, len(exact))`` where both sets
    are truncated to their first *k* entries. Returns ``1.0`` when the exact
    set is empty (no reference to miss). The result is clamped to [0, 1].
    """
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ExactContractError(f"k must be a positive int (got {k})")
    exact_k = list(exact_record_ids[:k])
    if not exact_k:
        return 1.0
    approx_k = set(approx_record_ids[:k])
    hits = sum(1 for rid in exact_k if rid in approx_k)
    return hits / len(exact_k)
