"""Tests for ScaNN Vector Snapshot Manifest.

Issue: #1171
"""

from __future__ import annotations

from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import pytest

from agent_runtime.retrieval.scann_manifest import (
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


class TestScopeBinding:
    def test_valid_scope_binding(self):
        scope = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        assert scope.owner == "test-owner"
        assert scope.scope_hash  # Should be a SHA-256

    def test_invalid_owner_raises(self):
        with pytest.raises(ManifestContractError, match="Invalid owner"):
            ScopeBinding(
                owner="invalid/owner",  # Contains /
                tenant="test-tenant",
                repo_owner="ouroboroscollective",
                repo_name="sovereign-studio-ato",
                environment="production",
            )

    def test_invalid_tenant_raises(self):
        with pytest.raises(ManifestContractError, match="Invalid tenant"):
            ScopeBinding(
                owner="test-owner",
                tenant="invalid tenant",  # Contains space
                repo_owner="ouroboroscollective",
                repo_name="sovereign-studio-ato",
                environment="production",
            )


class TestEmbeddingConfig:
    def test_valid_embedding_config(self):
        config = EmbeddingConfig(
            provider="cloudflare",
            model_id="@cf/google/embeddinggemma-300m",
            model_revision="1.0",
            model_hash="a" * 64,
            dimension=768,
            data_type=EmbeddingDataType.FLOAT32,
            normalization=Normalization.L2,
            distance_metric=DistanceMetric.COSINE,
        )
        assert config.provider == "cloudflare"
        assert config.dimension == 768
        assert config.config_hash  # Should be a SHA-256

    def test_invalid_model_hash_raises(self):
        with pytest.raises(ManifestContractError, match="model_hash must be SHA-256"):
            EmbeddingConfig(
                provider="cloudflare",
                model_id="@cf/google/embeddinggemma-300m",
                model_revision="1.0",
                model_hash="not-a-sha256",
                dimension=768,
                data_type=EmbeddingDataType.FLOAT32,
                normalization=Normalization.L2,
                distance_metric=DistanceMetric.COSINE,
            )

    def test_invalid_dimension_raises(self):
        with pytest.raises(ManifestContractError, match="dimension must be"):
            EmbeddingConfig(
                provider="cloudflare",
                model_id="@cf/google/embeddinggemma-300m",
                model_revision="1.0",
                model_hash="a" * 64,
                dimension=0,  # Invalid
                data_type=EmbeddingDataType.FLOAT32,
                normalization=Normalization.L2,
                distance_metric=DistanceMetric.COSINE,
            )


class TestScaNNBuildConfig:
    def test_valid_build_config(self):
        config = ScaNNBuildConfig(
            scann_version="2.12.0",
            partition=IndexPartition.PARTITIONED,
            partition_count=4,
            quantization=IndexQuantization.PQ,
            pq_codebooks=128,
            sq_block_size=0,
            min_cluster_size=100,
            max_cluster_size=100000,
            training_sample_size=100000,
            reorder_window=100,
        )
        assert config.scann_version == "2.12.0"
        assert config.partition == IndexPartition.PARTITIONED
        assert config.config_hash  # Should be a SHA-256

    def test_invalid_partition_count_raises(self):
        with pytest.raises(ManifestContractError, match="partition_count must be"):
            ScaNNBuildConfig(
                scann_version="2.12.0",
                partition=IndexPartition.PARTITIONED,
                partition_count=0,  # Invalid
                quantization=IndexQuantization.PQ,
                pq_codebooks=128,
                sq_block_size=0,
                min_cluster_size=100,
                max_cluster_size=100000,
                training_sample_size=100000,
                reorder_window=100,
            )


class TestCPUArchitecture:
    def test_valid_cpu_architecture(self):
        cpu = CPUArchitecture(
            architecture="x86_64",
            features=("avx2", "avx512"),
        )
        assert cpu.architecture == "x86_64"
        assert "avx2" in cpu.features
        assert cpu.features_hash  # Should be a SHA-256

    def test_empty_architecture_raises(self):
        with pytest.raises(ManifestContractError, match="architecture must not be empty"):
            CPUArchitecture(
                architecture="",  # Invalid
                features=(),
            )


class TestRecallReceipt:
    def test_valid_recall_receipt(self):
        receipt = RecallReceipt(
            recall_at_1=0.85,
            recall_at_10=0.95,
            recall_at_100=0.99,
            precision_at_k=0.78,
            candidate_stability=0.92,
            latency_p50_ms=5.2,
            latency_p95_ms=12.8,
            latency_p99_ms=25.1,
            memory_mb=512.0,
            build_time_seconds=120.5,
            benchmark_revision="a" * 40,
            benchmark_dataset_hash="b" * 64,
        )
        assert receipt.recall_at_10 == 0.95
        assert receipt.latency_p50_ms == 5.2

    def test_invalid_recall_value_raises(self):
        with pytest.raises(ManifestContractError, match="recall_at_1 must be"):
            RecallReceipt(
                recall_at_1=1.5,  # Invalid: > 1.0
                recall_at_10=0.95,
                recall_at_100=0.99,
                precision_at_k=0.78,
                candidate_stability=0.92,
                latency_p50_ms=5.2,
                latency_p95_ms=12.8,
                latency_p99_ms=25.1,
                memory_mb=512.0,
                build_time_seconds=120.5,
                benchmark_revision="a" * 40,
                benchmark_dataset_hash="b" * 64,
            )

    def test_invalid_benchmark_revision_raises(self):
        with pytest.raises(ManifestContractError, match="benchmark_revision must be SHA-40"):
            RecallReceipt(
                recall_at_1=0.85,
                recall_at_10=0.95,
                recall_at_100=0.99,
                precision_at_k=0.78,
                candidate_stability=0.92,
                latency_p50_ms=5.2,
                latency_p95_ms=12.8,
                latency_p99_ms=25.1,
                memory_mb=512.0,
                build_time_seconds=120.5,
                benchmark_revision="not-a-sha40",  # Invalid
                benchmark_dataset_hash="b" * 64,
            )


class TestVectorSnapshotManifest:
    def test_valid_manifest(self):
        scope = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        embedding = EmbeddingConfig(
            provider="cloudflare",
            model_id="@cf/google/embeddinggemma-300m",
            model_revision="1.0",
            model_hash="a" * 64,  # 64 hex chars
            dimension=768,
            data_type=EmbeddingDataType.FLOAT32,
            normalization=Normalization.L2,
            distance_metric=DistanceMetric.COSINE,
        )
        build = ScaNNBuildConfig(
            scann_version="2.12.0",
            partition=IndexPartition.FLAT,
            partition_count=1,
            quantization=IndexQuantization.NONE,
            pq_codebooks=0,
            sq_block_size=0,
            min_cluster_size=100,
            max_cluster_size=100000,
            training_sample_size=100000,
            reorder_window=100,
        )
        cpu = CPUArchitecture(
            architecture="x86_64",
            features=("avx2",),
        )
        records = (
            SourceRecordRef(
                record_id="be:abc123",
                content_hash="c" * 64,  # 64 hex chars
                evidence_class="verified",
                source_revision="d" * 40,  # 40 hex chars (SHA-40)
                source_file="/bug_evidence/abc123",
            ),
            SourceRecordRef(
                record_id="ml:def456",
                content_hash="e" * 64,  # 64 hex chars
                evidence_class="observed",
                source_revision="d" * 40,  # 40 hex chars
                source_file="/memory/def456",
            ),
        )

        manifest = VectorSnapshotManifest(
            schema_version=SCHEMA_VERSION,
            manifest_version="1.0.0",
            scope=scope,
            source_revision="d" * 40,  # 40 hex chars
            source_export_hash="f" * 64,  # 64 hex chars
            source_records=records,
            embedding_config=embedding,
            build_config=build,
            vector_count=2,
            chunk_manifest=(),
            index_hash="0" * 64,  # Valid hex SHA-256
            cpu_architecture=cpu,
        )

        assert manifest.schema_version == SCHEMA_VERSION
        assert manifest.vector_count == 2
        assert manifest.manifest_id  # Should be set
        assert manifest.total_hash  # Should be computed

    def test_unsorted_records_raises(self):
        scope = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        embedding = EmbeddingConfig(
            provider="cloudflare",
            model_id="@cf/google/embeddinggemma-300m",
            model_revision="1.0",
            model_hash="a" * 64,
            dimension=768,
            data_type=EmbeddingDataType.FLOAT32,
            normalization=Normalization.L2,
            distance_metric=DistanceMetric.COSINE,
        )
        build = ScaNNBuildConfig(
            scann_version="2.12.0",
            partition=IndexPartition.FLAT,
            partition_count=1,
            quantization=IndexQuantization.NONE,
            pq_codebooks=0,
            sq_block_size=0,
            min_cluster_size=100,
            max_cluster_size=100000,
            training_sample_size=100000,
            reorder_window=100,
        )
        cpu = CPUArchitecture(
            architecture="x86_64",
            features=(),
        )
        # Records NOT sorted by record_id
        records = (
            SourceRecordRef(
                record_id="ml:def456",  # This should come after be:abc123
                content_hash="e" * 64,
                evidence_class="observed",
                source_revision="d" * 40,
                source_file="/memory/def456",
            ),
            SourceRecordRef(
                record_id="be:abc123",
                content_hash="c" * 64,
                evidence_class="verified",
                source_revision="d" * 40,
                source_file="/bug_evidence/abc123",
            ),
        )

        with pytest.raises(ManifestContractError, match="source_records must be sorted"):
            VectorSnapshotManifest(
                schema_version=SCHEMA_VERSION,
                manifest_version="1.0.0",
                scope=scope,
                source_revision="d" * 40,
                source_export_hash="f" * 64,
                source_records=records,
                embedding_config=embedding,
                build_config=build,
                vector_count=2,
                chunk_manifest=(),
                index_hash="0" * 64,
                cpu_architecture=cpu,
            )

    def test_manifest_to_dict(self):
        scope = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        embedding = EmbeddingConfig(
            provider="cloudflare",
            model_id="@cf/google/embeddinggemma-300m",
            model_revision="1.0",
            model_hash="a" * 64,
            dimension=768,
            data_type=EmbeddingDataType.FLOAT32,
            normalization=Normalization.L2,
            distance_metric=DistanceMetric.COSINE,
        )
        build = ScaNNBuildConfig(
            scann_version="2.12.0",
            partition=IndexPartition.FLAT,
            partition_count=1,
            quantization=IndexQuantization.NONE,
            pq_codebooks=0,
            sq_block_size=0,
            min_cluster_size=100,
            max_cluster_size=100000,
            training_sample_size=100000,
            reorder_window=100,
        )
        cpu = CPUArchitecture(
            architecture="x86_64",
            features=("avx2",),
        )
        records = (
            SourceRecordRef(
                record_id="be:abc123",
                content_hash="c" * 64,
                evidence_class="verified",
                source_revision="d" * 40,
                source_file="/bug_evidence/abc123",
            ),
        )

        manifest = VectorSnapshotManifest(
            schema_version=SCHEMA_VERSION,
            manifest_version="1.0.0",
            scope=scope,
            source_revision="d" * 40,
            source_export_hash="f" * 64,
            source_records=records,
            embedding_config=embedding,
            build_config=build,
            vector_count=1,
            chunk_manifest=(),
            index_hash="0" * 64,
            cpu_architecture=cpu,
        )

        d = manifest.to_dict()
        assert d["schema_version"] == SCHEMA_VERSION
        assert d["vector_count"] == 1
        assert "manifest_id" in d
        assert "total_hash" in d
        assert d["scope"]["owner"] == "test-owner"
        assert d["embedding_config"]["dimension"] == 768


class TestValidationHelpers:
    def test_validate_manifest_completeness_valid(self):
        scope = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        embedding = EmbeddingConfig(
            provider="cloudflare",
            model_id="@cf/google/embeddinggemma-300m",
            model_revision="1.0",
            model_hash="a" * 64,
            dimension=768,
            data_type=EmbeddingDataType.FLOAT32,
            normalization=Normalization.L2,
            distance_metric=DistanceMetric.COSINE,
        )
        build = ScaNNBuildConfig(
            scann_version="2.12.0",
            partition=IndexPartition.FLAT,
            partition_count=1,
            quantization=IndexQuantization.NONE,
            pq_codebooks=0,
            sq_block_size=0,
            min_cluster_size=100,
            max_cluster_size=100000,
            training_sample_size=100000,
            reorder_window=100,
        )
        cpu = CPUArchitecture(
            architecture="x86_64",
            features=(),
        )
        records = (
            SourceRecordRef(
                record_id="be:abc123",
                content_hash="c" * 64,
                evidence_class="verified",
                source_revision="d" * 40,
                source_file="/bug_evidence/abc123",
            ),
        )

        manifest = VectorSnapshotManifest(
            schema_version=SCHEMA_VERSION,
            manifest_version="1.0.0",
            scope=scope,
            source_revision="d" * 40,
            source_export_hash="f" * 64,
            source_records=records,
            embedding_config=embedding,
            build_config=build,
            vector_count=1,
            chunk_manifest=(),
            index_hash="0" * 64,
            cpu_architecture=cpu,
        )

        valid, error = validate_manifest_completeness(manifest)
        assert valid is True
        assert error == ""

    def test_validate_manifest_completeness_empty_records(self):
        scope = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        embedding = EmbeddingConfig(
            provider="cloudflare",
            model_id="@cf/google/embeddinggemma-300m",
            model_revision="1.0",
            model_hash="a" * 64,
            dimension=768,
            data_type=EmbeddingDataType.FLOAT32,
            normalization=Normalization.L2,
            distance_metric=DistanceMetric.COSINE,
        )
        build = ScaNNBuildConfig(
            scann_version="2.12.0",
            partition=IndexPartition.FLAT,
            partition_count=1,
            quantization=IndexQuantization.NONE,
            pq_codebooks=0,
            sq_block_size=0,
            min_cluster_size=100,
            max_cluster_size=100000,
            training_sample_size=100000,
            reorder_window=100,
        )
        cpu = CPUArchitecture(
            architecture="x86_64",
            features=(),
        )

        manifest = VectorSnapshotManifest(
            schema_version=SCHEMA_VERSION,
            manifest_version="1.0.0",
            scope=scope,
            source_revision="d" * 40,
            source_export_hash="f" * 64,
            source_records=(),  # Empty
            embedding_config=embedding,
            build_config=build,
            vector_count=0,
            chunk_manifest=(),
            index_hash="0" * 64,
            cpu_architecture=cpu,
        )

        valid, error = validate_manifest_completeness(manifest)
        assert valid is False
        assert "No source_records" in error

    def test_check_scope_drift_match(self):
        scope1 = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        scope2 = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )

        assert check_scope_drift(scope1, scope2) is True

    def test_check_scope_drift_mismatch(self):
        scope1 = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        scope2 = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="different-repo",  # Different
            environment="production",
        )

        assert check_scope_drift(scope1, scope2) is False

    def test_check_revision_drift_match(self):
        scope = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        embedding = EmbeddingConfig(
            provider="cloudflare",
            model_id="@cf/google/embeddinggemma-300m",
            model_revision="1.0",
            model_hash="a" * 64,
            dimension=768,
            data_type=EmbeddingDataType.FLOAT32,
            normalization=Normalization.L2,
            distance_metric=DistanceMetric.COSINE,
        )
        build = ScaNNBuildConfig(
            scann_version="2.12.0",
            partition=IndexPartition.FLAT,
            partition_count=1,
            quantization=IndexQuantization.NONE,
            pq_codebooks=0,
            sq_block_size=0,
            min_cluster_size=100,
            max_cluster_size=100000,
            training_sample_size=100000,
            reorder_window=100,
        )
        cpu = CPUArchitecture(
            architecture="x86_64",
            features=(),
        )
        revision = "d" * 40
        records = (
            SourceRecordRef(
                record_id="be:abc123",
                content_hash="c" * 64,
                evidence_class="verified",
                source_revision=revision,
                source_file="/bug_evidence/abc123",
            ),
        )

        manifest = VectorSnapshotManifest(
            schema_version=SCHEMA_VERSION,
            manifest_version="1.0.0",
            scope=scope,
            source_revision=revision,
            source_export_hash="f" * 64,
            source_records=records,
            embedding_config=embedding,
            build_config=build,
            vector_count=1,
            chunk_manifest=(),
            index_hash="0" * 64,
            cpu_architecture=cpu,
        )

        assert check_revision_drift(manifest, revision) is True

    def test_check_revision_drift_mismatch(self):
        scope = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        embedding = EmbeddingConfig(
            provider="cloudflare",
            model_id="@cf/google/embeddinggemma-300m",
            model_revision="1.0",
            model_hash="a" * 64,
            dimension=768,
            data_type=EmbeddingDataType.FLOAT32,
            normalization=Normalization.L2,
            distance_metric=DistanceMetric.COSINE,
        )
        build = ScaNNBuildConfig(
            scann_version="2.12.0",
            partition=IndexPartition.FLAT,
            partition_count=1,
            quantization=IndexQuantization.NONE,
            pq_codebooks=0,
            sq_block_size=0,
            min_cluster_size=100,
            max_cluster_size=100000,
            training_sample_size=100000,
            reorder_window=100,
        )
        cpu = CPUArchitecture(
            architecture="x86_64",
            features=(),
        )
        records = (
            SourceRecordRef(
                record_id="be:abc123",
                content_hash="c" * 64,
                evidence_class="verified",
                source_revision="d" * 40,
                source_file="/bug_evidence/abc123",
            ),
        )

        manifest = VectorSnapshotManifest(
            schema_version=SCHEMA_VERSION,
            manifest_version="1.0.0",
            scope=scope,
            source_revision="d" * 40,
            source_export_hash="f" * 64,
            source_records=records,
            embedding_config=embedding,
            build_config=build,
            vector_count=1,
            chunk_manifest=(),
            index_hash="0" * 64,
            cpu_architecture=cpu,
        )

        # Different revision
        assert check_revision_drift(manifest, "e" * 40) is False

    def test_check_embedding_drift_match(self):
        config1 = EmbeddingConfig(
            provider="cloudflare",
            model_id="@cf/google/embeddinggemma-300m",
            model_revision="1.0",
            model_hash="a" * 64,
            dimension=768,
            data_type=EmbeddingDataType.FLOAT32,
            normalization=Normalization.L2,
            distance_metric=DistanceMetric.COSINE,
        )
        config2 = EmbeddingConfig(
            provider="cloudflare",
            model_id="@cf/google/embeddinggemma-300m",
            model_revision="1.0",
            model_hash="a" * 64,
            dimension=768,
            data_type=EmbeddingDataType.FLOAT32,
            normalization=Normalization.L2,
            distance_metric=DistanceMetric.COSINE,
        )

        assert check_embedding_drift(config1, config2) is True

    def test_check_embedding_drift_dimension_mismatch(self):
        config1 = EmbeddingConfig(
            provider="cloudflare",
            model_id="@cf/google/embeddinggemma-300m",
            model_revision="1.0",
            model_hash="a" * 64,
            dimension=768,
            data_type=EmbeddingDataType.FLOAT32,
            normalization=Normalization.L2,
            distance_metric=DistanceMetric.COSINE,
        )
        config2 = EmbeddingConfig(
            provider="cloudflare",
            model_id="@cf/google/embeddinggemma-300m",
            model_revision="1.0",
            model_hash="a" * 64,
            dimension=1024,  # Different
            data_type=EmbeddingDataType.FLOAT32,
            normalization=Normalization.L2,
            distance_metric=DistanceMetric.COSINE,
        )

        assert check_embedding_drift(config1, config2) is False
