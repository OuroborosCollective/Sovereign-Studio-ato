"""Tests for ScaNN Snapshot Export.

Issue: #1171
"""

from __future__ import annotations

from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import pytest

from agent_runtime.retrieval.scann_snapshot_export import (
    ExportContractError,
    ExportRecord,
    normalize_content_for_embedding,
    compute_content_hash,
    extract_bug_evidence_for_export,
    extract_memory_leaf_for_export,
    export_snapshot,
    build_manifest_from_export,
)
from agent_runtime.retrieval.scann_manifest import (
    SCHEMA_VERSION,
    ScopeBinding,
    EmbeddingConfig,
    EmbeddingDataType,
    Normalization,
    DistanceMetric,
    ScaNNBuildConfig,
    IndexPartition,
    IndexQuantization,
    CPUArchitecture,
)


class TestNormalizeContentForEmbedding:
    def test_strips_iso_timestamps(self):
        content = "Error at 2024-01-15T10:30:00Z"
        normalized = normalize_content_for_embedding(content)
        assert "2024-01-15T10:30:00Z" not in normalized
        assert "<TS>" in normalized

    def test_strips_uuids(self):
        content = "ID: 123e4567-e89b-12d3-a456-426614174000"
        normalized = normalize_content_for_embedding(content)
        assert "123e4567-e89b-12d3-a456-426614174000" not in normalized
        assert "<UUID>" in normalized

    def test_strips_sha256_hashes(self):
        content = "Hash: abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
        normalized = normalize_content_for_embedding(content)
        assert "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789" not in normalized
        assert "<SHA256>" in normalized

    def test_strips_container_ids(self):
        content = "Container: abcdef012345"
        normalized = normalize_content_for_embedding(content)
        assert "abcdef012345" not in normalized
        assert "<CID>" in normalized

    def test_normalizes_whitespace(self):
        content = "Error    with\n\nmultiple   spaces"
        normalized = normalize_content_for_embedding(content)
        # Should be collapsed to single spaces
        assert "    " not in normalized
        assert "\n\n" not in normalized

    def test_truncates_long_content(self):
        content = "A" * 20_000
        normalized = normalize_content_for_embedding(content)
        assert len(normalized) <= 16_384


class TestComputeContentHash:
    def test_same_content_same_hash(self):
        content = "Test content"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256

    def test_different_content_different_hash(self):
        hash1 = compute_content_hash("Content A")
        hash2 = compute_content_hash("Content B")
        assert hash1 != hash2


class TestExtractBugEvidenceForExport:
    def setup_method(self):
        self.scope = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        self.source_revision = "a" * 40

    def test_extracts_verified_case(self):
        case = {
            "evidence_case_id": "abc123",
            "status": "verified",
            "failure_family": "github_actions_workflow_failure",
            "repo_owner": "ouroboroscollective",
            "repo_name": "sovereign-studio-ato",
            "normalized_signature": "Error: workflow failed",
            "diagnostic_tools": ["git", "docker"],
            "affected_surfaces": ["ci", "production"],
        }

        result = extract_bug_evidence_for_export(case, self.scope, self.source_revision)

        assert result is not None
        assert result.record_id == "be:abc123"
        assert result.source_type == "bug_evidence"
        assert result.evidence_class == "verified"
        assert "github_actions_workflow_failure" in result.normalized_content
        assert "Error: workflow failed" in result.normalized_content
        assert result.failure_family == "github_actions_workflow_failure"

    def test_extracts_observed_case(self):
        case = {
            "evidence_case_id": "def456",
            "status": "observed",
            "failure_family": "docker_compose_container_failure",
            "repo_owner": "ouroboroscollective",
            "repo_name": "sovereign-studio-ato",
            "normalized_signature": "Container exited",
        }

        result = extract_bug_evidence_for_export(case, self.scope, self.source_revision)

        assert result is not None
        assert result.evidence_class == "observed"

    def test_skips_candidate_case(self):
        case = {
            "evidence_case_id": "ghi789",
            "status": "candidate",
            "failure_family": "docker_compose_container_failure",
            "repo_owner": "ouroboroscollective",
            "repo_name": "sovereign-studio-ato",
            "normalized_signature": "Container issue",
        }

        result = extract_bug_evidence_for_export(case, self.scope, self.source_revision)

        assert result is None

    def test_skips_invalidated_case(self):
        case = {
            "evidence_case_id": "jkl012",
            "status": "invalidated",
            "failure_family": "postgres_migration_failure",
            "repo_owner": "ouroboroscollective",
            "repo_name": "sovereign-studio-ato",
            "normalized_signature": "Migration error",
        }

        result = extract_bug_evidence_for_export(case, self.scope, self.source_revision)

        assert result is None


class TestExtractMemoryLeafForExport:
    def setup_method(self):
        self.scope = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        self.source_revision = "a" * 40

    def test_extracts_verified_leaf(self):
        leaf = {
            "leaf_id": "leaf-abc123",
            "owner": "test-owner",
            "tenant": "test-tenant",
            "repo_owner": "ouroboroscollective",
            "repo_name": "sovereign-studio-ato",
            "evidence_class": "verified",
            "source_class": "runtime_readback",
            "kind": "error_pattern",
            "summary": "Common Docker failure",
            "content": "Docker containers often fail due to port conflicts",
        }

        result = extract_memory_leaf_for_export(leaf, self.scope, self.source_revision)

        assert result is not None
        assert result.record_id == "ml:leaf-abc123"
        assert result.source_type == "durable_memory"
        assert result.evidence_class == "verified"
        assert result.evidence_source == "runtime_readback"
        assert "Common Docker failure" in result.normalized_content

    def test_extracts_observed_leaf(self):
        leaf = {
            "leaf_id": "leaf-def456",
            "owner": "test-owner",
            "tenant": "test-tenant",
            "repo_owner": "ouroboroscollective",
            "repo_name": "sovereign-studio-ato",
            "evidence_class": "observed",
            "source_class": "repository_readback",
            "kind": "pattern",
            "content": "Pattern content",
        }

        result = extract_memory_leaf_for_export(leaf, self.scope, self.source_revision)

        assert result is not None
        assert result.evidence_class == "observed"

    def test_skips_reported_leaf(self):
        leaf = {
            "leaf_id": "leaf-ghi789",
            "owner": "test-owner",
            "tenant": "test-tenant",
            "repo_owner": "ouroboroscollective",
            "repo_name": "sovereign-studio-ato",
            "evidence_class": "reported",
            "source_class": "human_reported",
            "content": "User reported issue",
        }

        result = extract_memory_leaf_for_export(leaf, self.scope, self.source_revision)

        assert result is None

    def test_extracts_with_scope_but_evidence_class_filter(self):
        """Note: extract_memory_leaf_for_export does NOT check scope.

        Scope filtering is done at the export_snapshot level. This function
        only checks evidence_class.
        """
        leaf = {
            "leaf_id": "leaf-jkl012",
            "owner": "wrong-owner",  # Wrong scope, but function doesn't check
            "tenant": "test-tenant",
            "repo_owner": "ouroboroscollective",
            "repo_name": "sovereign-studio-ato",
            "evidence_class": "verified",
            "content": "Content",
        }

        # Should return a record because evidence_class is valid
        # Scope is checked at export_snapshot level, not here
        result = extract_memory_leaf_for_export(leaf, self.scope, self.source_revision)
        assert result is not None
        assert result.record_id == "ml:leaf-jkl012"
        assert result.evidence_class == "verified"

    def test_skips_wrong_evidence_class(self):
        """Scope is checked at export_snapshot level, but evidence_class is checked here."""
        leaf = {
            "leaf_id": "leaf-jkl012",
            "owner": "test-owner",
            "tenant": "test-tenant",
            "repo_owner": "ouroboroscollective",
            "repo_name": "sovereign-studio-ato",
            "evidence_class": "reported",  # Not allowed
            "content": "Content",
        }

        result = extract_memory_leaf_for_export(leaf, self.scope, self.source_revision)
        assert result is None


class TestExportSnapshot:
    def setup_method(self):
        self.scope = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        self.source_revision = "a" * 40

    def test_export_with_both_sources(self):
        bug_cases = [
            {
                "evidence_case_id": "be001",
                "status": "verified",
                "failure_family": "github_actions_workflow_failure",
                "repo_owner": "ouroboroscollective",
                "repo_name": "sovereign-studio-ato",
                "normalized_signature": "Workflow failed",
                "diagnostic_tools": [],
                "affected_surfaces": [],
            },
            {
                "evidence_case_id": "be002",
                "status": "observed",
                "failure_family": "docker_compose_container_failure",
                "repo_owner": "ouroboroscollective",
                "repo_name": "sovereign-studio-ato",
                "normalized_signature": "Container error",
                "diagnostic_tools": [],
                "affected_surfaces": [],
            },
        ]

        memory_leaves = [
            {
                "leaf_id": "ml001",
                "owner": "test-owner",
                "tenant": "test-tenant",
                "repo_owner": "ouroboroscollective",
                "repo_name": "sovereign-studio-ato",
                "evidence_class": "verified",
                "source_class": "runtime_readback",
                "kind": "pattern",
                "summary": "Error pattern",
                "content": "Pattern content",
            },
        ]

        result = export_snapshot(
            bug_evidence_cases=bug_cases,
            memory_leaves=memory_leaves,
            scope=self.scope,
            source_revision=self.source_revision,
        )

        assert result.export_version
        assert result.scope == self.scope
        assert result.source_revision == self.source_revision
        assert len(result.records) == 3
        assert result.excluded_count == 0
        # Records should be sorted
        record_ids = [r.record_id for r in result.records]
        assert record_ids == sorted(record_ids)

    def test_export_with_scope_mismatch(self):
        bug_cases = [
            {
                "evidence_case_id": "be001",
                "status": "verified",
                "failure_family": "github_actions_workflow_failure",
                "repo_owner": "different-owner",  # Wrong
                "repo_name": "sovereign-studio-ato",
                "normalized_signature": "Workflow failed",
                "diagnostic_tools": [],
                "affected_surfaces": [],
            },
        ]

        memory_leaves = []

        result = export_snapshot(
            bug_evidence_cases=bug_cases,
            memory_leaves=memory_leaves,
            scope=self.scope,
            source_revision=self.source_revision,
        )

        assert len(result.records) == 0
        assert result.excluded_count == 1
        assert "be:scope_mismatch" in result.excluded_reasons[0]

    def test_export_with_ineligible_records(self):
        bug_cases = [
            {
                "evidence_case_id": "be001",
                "status": "candidate",  # Not eligible
                "failure_family": "github_actions_workflow_failure",
                "repo_owner": "ouroboroscollective",
                "repo_name": "sovereign-studio-ato",
                "normalized_signature": "Workflow failed",
                "diagnostic_tools": [],
                "affected_surfaces": [],
            },
        ]

        memory_leaves = [
            {
                "leaf_id": "ml001",
                "owner": "test-owner",
                "tenant": "test-tenant",
                "repo_owner": "ouroboroscollective",
                "repo_name": "sovereign-studio-ato",
                "evidence_class": "reported",  # Not eligible
                "source_class": "human_reported",
                "content": "Content",
            },
        ]

        result = export_snapshot(
            bug_evidence_cases=bug_cases,
            memory_leaves=memory_leaves,
            scope=self.scope,
            source_revision=self.source_revision,
        )

        assert len(result.records) == 0
        assert result.excluded_count == 2

    def test_export_invalid_revision_raises(self):
        with pytest.raises(ExportContractError, match="Invalid source_revision"):
            export_snapshot(
                bug_evidence_cases=[],
                memory_leaves=[],
                scope=self.scope,
                source_revision="invalid",
            )

    def test_export_empty_records(self):
        result = export_snapshot(
            bug_evidence_cases=[],
            memory_leaves=[],
            scope=self.scope,
            source_revision=self.source_revision,
        )

        assert len(result.records) == 0
        assert result.excluded_count == 0
        assert result.export_hash  # Still has a hash
        assert result.content_hash  # Empty content hash


class TestBuildManifestFromExport:
    def setup_method(self):
        self.scope = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        self.source_revision = "a" * 40
        self.embedding = EmbeddingConfig(
            provider="cloudflare",
            model_id="@cf/google/embeddinggemma-300m",
            model_revision="1.0",
            model_hash="b" * 64,
            dimension=768,
            data_type=EmbeddingDataType.FLOAT32,
            normalization=Normalization.L2,
            distance_metric=DistanceMetric.COSINE,
        )
        self.build = ScaNNBuildConfig(
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
        self.cpu = CPUArchitecture(
            architecture="x86_64",
            features=("avx2",),
        )

    def test_build_manifest(self):
        export = export_snapshot(
            bug_evidence_cases=[
                {
                    "evidence_case_id": "be001",
                    "status": "verified",
                    "failure_family": "github_actions_workflow_failure",
                    "repo_owner": "ouroboroscollective",
                    "repo_name": "sovereign-studio-ato",
                    "normalized_signature": "Workflow failed",
                    "diagnostic_tools": [],
                    "affected_surfaces": [],
                },
            ],
            memory_leaves=[],
            scope=self.scope,
            source_revision=self.source_revision,
        )

        manifest = build_manifest_from_export(
            export=export,
            embedding_config=self.embedding,
            build_config=self.build,
            index_hash="c" * 64,
            cpu_architecture=self.cpu,
        )

        assert manifest.schema_version == SCHEMA_VERSION
        assert manifest.scope == self.scope
        assert manifest.source_revision == self.source_revision
        assert manifest.vector_count == 1
        assert manifest.index_hash == "c" * 64
        assert len(manifest.source_records) == 1
        assert manifest.source_records[0].record_id == "be:be001"

    def test_build_manifest_with_recall_receipt(self):
        from agent_runtime.retrieval.scann_manifest import RecallReceipt

        export = export_snapshot(
            bug_evidence_cases=[
                {
                    "evidence_case_id": "be001",
                    "status": "verified",
                    "failure_family": "github_actions_workflow_failure",
                    "repo_owner": "ouroboroscollective",
                    "repo_name": "sovereign-studio-ato",
                    "normalized_signature": "Workflow failed",
                    "diagnostic_tools": [],
                    "affected_surfaces": [],
                },
            ],
            memory_leaves=[],
            scope=self.scope,
            source_revision=self.source_revision,
        )

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
            benchmark_revision=self.source_revision,
            benchmark_dataset_hash="d" * 64,
        )

        manifest = build_manifest_from_export(
            export=export,
            embedding_config=self.embedding,
            build_config=self.build,
            index_hash="c" * 64,
            cpu_architecture=self.cpu,
            recall_receipt=receipt,
        )

        assert manifest.recall_receipt is not None
        assert manifest.recall_receipt.recall_at_10 == 0.95

    def test_empty_export_cannot_be_promoted_to_manifest(self):
        export = export_snapshot(
            bug_evidence_cases=[],
            memory_leaves=[],
            scope=self.scope,
            source_revision=self.source_revision,
        )
        with pytest.raises(ExportContractError, match="empty export"):
            build_manifest_from_export(
                export=export,
                embedding_config=self.embedding,
                build_config=self.build,
                index_hash="c" * 64,
                cpu_architecture=self.cpu,
            )


class TestExportFailClosedHardening:
    def setup_method(self):
        self.scope = ScopeBinding(
            owner="test-owner",
            tenant="test-tenant",
            repo_owner="ouroboroscollective",
            repo_name="sovereign-studio-ato",
            environment="production",
        )
        self.revision = "a" * 40

    def test_missing_bug_identity_or_signature_is_excluded(self):
        cases = [
            {
                "evidence_case_id": "",
                "status": "verified",
                "failure_family": "workflow_failure",
                "repo_owner": "ouroboroscollective",
                "repo_name": "sovereign-studio-ato",
                "normalized_signature": "failed",
            },
            {
                "evidence_case_id": "case-2",
                "status": "verified",
                "failure_family": "workflow_failure",
                "repo_owner": "ouroboroscollective",
                "repo_name": "sovereign-studio-ato",
                "normalized_signature": "",
            },
        ]
        result = export_snapshot(cases, [], self.scope, self.revision)
        assert result.records == ()
        assert result.excluded_count == 2

    def test_optional_bug_owner_binding_fails_closed_when_present(self):
        case = {
            "evidence_case_id": "case-1",
            "status": "verified",
            "failure_family": "workflow_failure",
            "repo_owner": "ouroboroscollective",
            "repo_name": "sovereign-studio-ato",
            "owner": "different-owner",
            "normalized_signature": "failed",
        }
        result = export_snapshot([case], [], self.scope, self.revision)
        assert result.records == ()
        assert result.excluded_count == 1

    def test_duplicate_record_ids_are_rejected(self):
        case = {
            "evidence_case_id": "same-id",
            "status": "verified",
            "failure_family": "workflow_failure",
            "repo_owner": "ouroboroscollective",
            "repo_name": "sovereign-studio-ato",
            "normalized_signature": "failed",
        }
        with pytest.raises(ExportContractError, match="Duplicate record_id"):
            export_snapshot([case, dict(case)], [], self.scope, self.revision)

    def test_empty_memory_content_is_excluded(self):
        leaf = {
            "leaf_id": "leaf-empty",
            "owner": "test-owner",
            "tenant": "test-tenant",
            "repo_owner": "ouroboroscollective",
            "repo_name": "sovereign-studio-ato",
            "evidence_class": "verified",
            "summary": "",
            "content": "",
        }
        result = export_snapshot([], [leaf], self.scope, self.revision)
        assert result.records == ()
        assert result.excluded_count == 1
