"""Tests for the exact brute-force reference search path (ScaNN rescoring).

These tests exercise the real ``scann_exact_rescore`` implementation, not a
copy of its logic. They cover success, expected failures, invalid input,
stale revision, scope/embedding drift, empty index, k > count, deterministic
reproducibility and recall measurement.

Issue: #1171 (step 3)
"""

from __future__ import annotations

from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import pytest

from agent_runtime.retrieval.scann_manifest import (
    SCHEMA_VERSION,
    DistanceMetric,
    EmbeddingDataType,
    IndexPartition,
    IndexQuantization,
    Normalization,
    ScopeBinding,
    EmbeddingConfig,
    SourceRecordRef,
    ScaNNBuildConfig,
    CPUArchitecture,
    VectorSnapshotManifest,
)
from agent_runtime.retrieval.scann_exact_rescore import (
    ExactContractError,
    ExactCandidate,
    ExactSearchResult,
    recall_at_k,
    exact_distance,
    normalize_vector,
    search_exact,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_REV = "d" * 40


def _scope(
    *,
    owner: str = "test-owner",
    tenant: str = "test-tenant",
    repo_owner: str = "ouroboroscollective",
    repo_name: str = "sovereign-studio-ato",
    environment: str = "production",
) -> ScopeBinding:
    return ScopeBinding(
        owner=owner,
        tenant=tenant,
        repo_owner=repo_owner,
        repo_name=repo_name,
        environment=environment,
    )


def _embedding(
    *,
    dimension: int = 4,
    normalization: Normalization = Normalization.L2,
    distance_metric: DistanceMetric = DistanceMetric.COSINE,
    model_hash: str = "a" * 64,
) -> EmbeddingConfig:
    return EmbeddingConfig(
        provider="cloudflare",
        model_id="@cf/google/embeddinggemma-300m",
        model_revision="1.0",
        model_hash=model_hash,
        dimension=dimension,
        data_type=EmbeddingDataType.FLOAT32,
        normalization=normalization,
        distance_metric=distance_metric,
    )


def _build() -> ScaNNBuildConfig:
    return ScaNNBuildConfig(
        scann_version="2.12.0",
        partition=IndexPartition.FLAT,
        partition_count=1,
        quantization=IndexQuantization.NONE,
        pq_codebooks=0,
        sq_block_size=0,
        min_cluster_size=1,
        max_cluster_size=100,
        training_sample_size=10,
        reorder_window=10,
    )


def _record(record_id: str, content_hash: str) -> SourceRecordRef:
    return SourceRecordRef(
        record_id=record_id,
        content_hash=content_hash,
        evidence_class="verified",
        source_revision=_REV,
        source_file=f"/bug_evidence/{record_id}",
    )


def _manifest(
    records,
    vectors,
    *,
    embedding: EmbeddingConfig | None = None,
    scope: ScopeBinding | None = None,
    source_revision: str = _REV,
) -> tuple[VectorSnapshotManifest, list[list[float]]]:
    emb = embedding if embedding is not None else _embedding()
    scp = scope if scope is not None else _scope()
    manifest = VectorSnapshotManifest(
        schema_version=SCHEMA_VERSION,
        manifest_version="1.0.0",
        scope=scp,
        source_revision=source_revision,
        source_export_hash="f" * 64,
        source_records=tuple(records),
        embedding_config=emb,
        build_config=_build(),
        vector_count=len(vectors),
        chunk_manifest=(),
        index_hash="0" * 64,
        cpu_architecture=CPUArchitecture(architecture="x86_64", features=("avx2",)),
    )
    return manifest, vectors


def _build_index():
    """Deterministic 4-dim index with 3 records.

    Records are sorted by record_id, which the manifest contract requires.
    Distances to the query below are chosen so the ranking is unambiguous.
    """
    records = (
        _record("be:aaa", "1" * 64),
        _record("be:bbb", "2" * 64),
        _record("be:ccc", "3" * 64),
    )
    vectors = [
        [0.0, 1.0, 0.0, 0.0],  # be:aaa
        [1.0, 0.0, 0.0, 0.0],  # be:bbb
        [0.0, 0.0, 1.0, 0.0],  # be:ccc
    ]
    return _manifest(records, vectors)


_QUERY = [0.0, 0.0, 1.0, 0.0]  # closest to be:ccc


# ---------------------------------------------------------------------------
# search_exact: success
# ---------------------------------------------------------------------------

class TestSearchExactSuccess:
    def test_ranks_by_exact_distance_and_reads_back_records(self):
        manifest, vectors = _build_index()
        result = search_exact(
            manifest, vectors, _QUERY, k=3,
            query_scope=_scope(), current_revision=_REV,
            current_embedding_config=manifest.embedding_config,
        )
        assert isinstance(result, ExactSearchResult)
        assert result.returned == 3
        assert result.record_ids == ("be:ccc", "be:aaa", "be:bbb")
        top = result.candidates[0]
        assert top.rank == 1
        assert top.record_id == "be:ccc"
        assert top.distance == pytest.approx(0.0)
        # The returned content hash was read back from the manifest.
        assert top.content_hash == "3" * 64
        assert result.scope_ok and result.revision_ok and result.embedding_ok

    def test_k_limits_returned_candidates(self):
        manifest, vectors = _build_index()
        result = search_exact(
            manifest, vectors, _QUERY, k=1,
            query_scope=_scope(), current_revision=_REV,
            current_embedding_config=manifest.embedding_config,
        )
        assert result.requested_k == 1
        assert result.returned == 1
        assert result.record_ids == ("be:ccc",)

    def test_k_greater_than_count_returns_all_ranked(self):
        manifest, vectors = _build_index()
        result = search_exact(
            manifest, vectors, _QUERY, k=10,
            query_scope=_scope(), current_revision=_REV,
            current_embedding_config=manifest.embedding_config,
        )
        assert result.requested_k == 10
        assert result.total_vectors == 3
        assert result.returned == 3  # degraded-but-honest, not a failure

    def test_rank_indices_are_one_based_and_contiguous(self):
        manifest, vectors = _build_index()
        result = search_exact(
            manifest, vectors, _QUERY, k=3,
            query_scope=_scope(), current_revision=_REV,
            current_embedding_config=manifest.embedding_config,
        )
        assert [c.rank for c in result.candidates] == [1, 2, 3]

    def test_search_hash_is_deterministic_for_same_inputs(self):
        manifest, vectors = _build_index()
        args = dict(
            query_scope=_scope(), current_revision=_REV,
            current_embedding_config=manifest.embedding_config,
        )
        r1 = search_exact(manifest, vectors, _QUERY, k=3, **args)
        r2 = search_exact(manifest, vectors, _QUERY, k=3, **args)
        assert r1.search_hash == r2.search_hash
        assert r1.to_dict() == r2.to_dict()

    def test_different_k_yields_different_search_hash(self):
        manifest, vectors = _build_index()
        args = dict(
            query_scope=_scope(), current_revision=_REV,
            current_embedding_config=manifest.embedding_config,
        )
        r1 = search_exact(manifest, vectors, _QUERY, k=1, **args)
        r2 = search_exact(manifest, vectors, _QUERY, k=3, **args)
        assert r1.search_hash != r2.search_hash

    def test_to_dict_roundtrips_candidate_fields(self):
        manifest, vectors = _build_index()
        result = search_exact(
            manifest, vectors, _QUERY, k=3,
            query_scope=_scope(), current_revision=_REV,
            current_embedding_config=manifest.embedding_config,
        )
        payload = result.to_dict()
        assert payload["returned"] == 3
        assert payload["candidates"][0]["record_id"] == "be:ccc"
        assert payload["distance_metric"] == "cosine"


# ---------------------------------------------------------------------------
# search_exact: failure / invalid input
# ---------------------------------------------------------------------------

class TestSearchExactFailures:
    def test_invalid_k_zero_raises(self):
        manifest, vectors = _build_index()
        with pytest.raises(ExactContractError, match="k must be >= 1"):
            search_exact(
                manifest, vectors, _QUERY, k=0,
                query_scope=_scope(), current_revision=_REV,
                current_embedding_config=manifest.embedding_config,
            )

    def test_invalid_k_negative_raises(self):
        manifest, vectors = _build_index()
        with pytest.raises(ExactContractError, match="k must be >= 1"):
            search_exact(
                manifest, vectors, _QUERY, k=-1,
                query_scope=_scope(), current_revision=_REV,
                current_embedding_config=manifest.embedding_config,
            )

    def test_k_must_be_int_not_bool(self):
        manifest, vectors = _build_index()
        with pytest.raises(ExactContractError, match="k must be an int"):
            search_exact(
                manifest, vectors, _QUERY, k=True,
                query_scope=_scope(), current_revision=_REV,
                current_embedding_config=manifest.embedding_config,
            )

    def test_query_dimension_mismatch_raises(self):
        manifest, vectors = _build_index()
        with pytest.raises(ExactContractError, match="query dimension mismatch"):
            search_exact(
                manifest, vectors, [0.0, 0.0, 1.0], k=3,  # 3-dim, config is 4-dim
                query_scope=_scope(), current_revision=_REV,
                current_embedding_config=manifest.embedding_config,
            )

    def test_vector_dimension_mismatch_raises(self):
        records = (
            _record("be:aaa", "1" * 64),
            _record("be:bbb", "2" * 64),
        )
        vectors = [
            [0.0, 1.0, 0.0, 0.0],
            [1.0, 0.0],  # wrong dimension
        ]
        manifest, vectors = _manifest(records, vectors)
        with pytest.raises(ExactContractError, match="vector dimension mismatch"):
            search_exact(
                manifest, vectors, _QUERY, k=2,
                query_scope=_scope(), current_revision=_REV,
                current_embedding_config=manifest.embedding_config,
            )

    def test_vector_count_mismatch_raises(self):
        manifest, vectors = _build_index()
        with pytest.raises(ExactContractError, match="vector count mismatch"):
            search_exact(
                manifest, vectors[:2], _QUERY, k=3,
                query_scope=_scope(), current_revision=_REV,
                current_embedding_config=manifest.embedding_config,
            )

    def test_stale_revision_raises(self):
        manifest, vectors = _build_index()
        with pytest.raises(ExactContractError, match="revision drift"):
            search_exact(
                manifest, vectors, _QUERY, k=3,
                query_scope=_scope(),
                current_revision="e" * 40,  # drifted
                current_embedding_config=manifest.embedding_config,
            )

    def test_scope_drift_rejected(self):
        manifest, vectors = _build_index()
        with pytest.raises(ExactContractError, match="scope drift"):
            search_exact(
                manifest, vectors, _QUERY, k=3,
                query_scope=_scope(owner="other-owner"),
                current_revision=_REV,
                current_embedding_config=manifest.embedding_config,
            )

    def test_embedding_drift_rejected(self):
        manifest, vectors = _build_index()
        drifted_embedding = _embedding(model_hash="b" * 64)
        with pytest.raises(ExactContractError, match="embedding config drift"):
            search_exact(
                manifest, vectors, _QUERY, k=3,
                query_scope=_scope(), current_revision=_REV,
                current_embedding_config=drifted_embedding,
            )

    def test_empty_index_is_rejected(self):
        # An empty manifest fails completeness (vector_count <= 0).
        records = ()
        vectors = []
        manifest, vectors = _manifest(records, vectors)
        with pytest.raises(ExactContractError, match="manifest incomplete"):
            search_exact(
                manifest, vectors, _QUERY, k=3,
                query_scope=_scope(), current_revision=_REV,
                current_embedding_config=manifest.embedding_config,
            )

    def test_incomplete_manifest_no_source_records_rejected(self):
        import dataclasses
        manifest, _vectors = _build_index()
        # Blank out source_records / vector_count to fail completeness,
        # using replace() which respects the frozen dataclass contract.
        bad = dataclasses.replace(
            manifest, source_records=(), vector_count=0,
        )
        with pytest.raises(ExactContractError, match="manifest incomplete"):
            search_exact(
                bad, [], _QUERY, k=3,
                query_scope=_scope(), current_revision=_REV,
                current_embedding_config=manifest.embedding_config,
            )


# ---------------------------------------------------------------------------
# Tie-breaking determinism / replay denial
# ---------------------------------------------------------------------------

class TestDeterminismAndReplay:
    def test_equal_distances_break_ties_by_record_id(self):
        # Two identical vectors -> equal distance; tie breaks by record_id.
        # Records must be sorted by record_id (manifest contract).
        records = (
            _record("be:aaa", "1" * 64),
            _record("be:zzz", "9" * 64),
        )
        vectors = [
            [1.0, 0.0, 0.0, 0.0],  # be:aaa
            [1.0, 0.0, 0.0, 0.0],  # be:zzz (identical vector)
        ]
        manifest, vectors = _manifest(records, vectors)
        result = search_exact(
            manifest, vectors, [1.0, 0.0, 0.0, 0.0], k=2,
            query_scope=_scope(), current_revision=_REV,
            current_embedding_config=manifest.embedding_config,
        )
        # Equal distance -> be:aaa precedes be:zzz by record_id tie-break.
        assert result.record_ids == ("be:aaa", "be:zzz")
        assert result.candidates[0].distance == result.candidates[1].distance

    def test_independently_reconstructed_index_yields_same_receipt(self):
        # The receipt is content-addressed: two separate manifest objects built
        # from identical logical data must produce byte-identical search_hash,
        # proving ranking is a pure function of content, not object identity.
        records = (
            _record("be:aaa", "1" * 64),
            _record("be:bbb", "2" * 64),
            _record("be:ccc", "3" * 64),
        )
        vectors = [
            [0.0, 1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
        ]
        manifest_a, va = _manifest(records, vectors)
        manifest_b, vb = _manifest(records, vectors)
        assert manifest_a is not manifest_b
        args = dict(
            query_scope=_scope(), current_revision=_REV,
            current_embedding_config=manifest_a.embedding_config,
        )
        ra = search_exact(manifest_a, va, _QUERY, k=3, **args)
        rb = search_exact(manifest_b, vb, _QUERY, k=3, **args)
        assert ra.record_ids == rb.record_ids
        assert ra.search_hash == rb.search_hash


# ---------------------------------------------------------------------------
# Distance metrics
# ---------------------------------------------------------------------------

class TestDistanceMetrics:
    def test_l2_metric_ranks_correctly(self):
        records = (
            _record("be:aaa", "1" * 64),
            _record("be:bbb", "2" * 64),
        )
        vectors = [
            [0.0, 0.0, 0.0, 0.0],  # be:aaa, far from query
            [0.0, 0.0, 1.0, 0.0],  # be:bbb, exact match
        ]
        embedding = _embedding(
            normalization=Normalization.NONE,
            distance_metric=DistanceMetric.L2,
        )
        manifest, vectors = _manifest(records, vectors, embedding=embedding)
        result = search_exact(
            manifest, vectors, _QUERY, k=2,
            query_scope=_scope(), current_revision=_REV,
            current_embedding_config=embedding,
        )
        assert result.record_ids == ("be:bbb", "be:aaa")
        assert result.candidates[0].distance == pytest.approx(0.0)

    def test_dot_product_metric_ranks_highest_first(self):
        records = (
            _record("be:aaa", "1" * 64),
            _record("be:bbb", "2" * 64),
        )
        vectors = [
            [0.0, 1.0, 0.0, 0.0],  # be:aaa, dot = 0
            [0.0, 0.0, 1.0, 0.0],  # be:bbb, dot = 1
        ]
        embedding = _embedding(
            normalization=Normalization.NONE,
            distance_metric=DistanceMetric.DOT_PRODUCT,
        )
        manifest, vectors = _manifest(records, vectors, embedding=embedding)
        result = search_exact(
            manifest, vectors, _QUERY, k=2,
            query_scope=_scope(), current_revision=_REV,
            current_embedding_config=embedding,
        )
        assert result.record_ids == ("be:bbb", "be:aaa")
        assert result.candidates[0].distance == pytest.approx(-1.0)

    def test_exact_distance_dimension_mismatch(self):
        with pytest.raises(ExactContractError, match="dimension mismatch"):
            exact_distance([1.0, 2.0], [1.0], DistanceMetric.L2)


# ---------------------------------------------------------------------------
# normalize_vector
# ---------------------------------------------------------------------------

class TestNormalizeVector:
    def test_none_returns_tuple_unchanged(self):
        out = normalize_vector([1.0, 2.0, 3.0], Normalization.NONE)
        assert out == (1.0, 2.0, 3.0)

    def test_l2_normalizes_to_unit_length(self):
        out = normalize_vector([3.0, 4.0], Normalization.L2)
        assert out[0] == pytest.approx(0.6)
        assert out[1] == pytest.approx(0.8)

    def test_zero_vector_raises_under_normalization(self):
        with pytest.raises(ExactContractError, match="zero-length vector"):
            normalize_vector([0.0, 0.0], Normalization.L2)


# ---------------------------------------------------------------------------
# recall_at_k
# ---------------------------------------------------------------------------

class TestRecallAtK:
    def test_full_recall(self):
        exact = ["a", "b", "c"]
        approx = ["a", "b", "c"]
        assert recall_at_k(approx, exact, k=3) == 1.0

    def test_partial_recall(self):
        exact = ["a", "b", "c"]
        approx = ["a", "x", "c"]
        assert recall_at_k(approx, exact, k=3) == pytest.approx(2 / 3)

    def test_no_recall(self):
        exact = ["a", "b", "c"]
        approx = ["x", "y", "z"]
        assert recall_at_k(approx, exact, k=3) == 0.0

    def test_empty_exact_returns_one(self):
        assert recall_at_k(["a"], [], k=3) == 1.0

    def test_k_truncates_both_sets(self):
        exact = ["a", "b", "c", "d"]
        approx = ["a", "b", "z", "z"]
        # min(k, len(exact)) = 2 -> exact_k = [a, b], both hit
        assert recall_at_k(approx, exact, k=2) == 1.0

    def test_invalid_k_raises(self):
        with pytest.raises(ExactContractError, match="k must be a positive int"):
            recall_at_k(["a"], ["a"], k=0)


# ---------------------------------------------------------------------------
# Cross-scope isolation boundary
# ---------------------------------------------------------------------------

class TestCrossScopeBoundary:
    def test_different_environment_is_blocked(self):
        manifest, vectors = _build_index()
        with pytest.raises(ExactContractError, match="scope drift"):
            search_exact(
                manifest, vectors, _QUERY, k=3,
                query_scope=_scope(environment="staging"),
                current_revision=_REV,
                current_embedding_config=manifest.embedding_config,
            )

    def test_different_repo_is_blocked(self):
        manifest, vectors = _build_index()
        with pytest.raises(ExactContractError, match="scope drift"):
            search_exact(
                manifest, vectors, _QUERY, k=3,
                query_scope=_scope(repo_name="other-repo"),
                current_revision=_REV,
                current_embedding_config=manifest.embedding_config,
            )
