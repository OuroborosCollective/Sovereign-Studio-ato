from __future__ import annotations

from pathlib import Path
import re
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from agent_runtime import issue_closure_runtime


REVISION = "a" * 40
BASELINE = "b" * 40
DIGEST = "sha256:" + "c" * 64
RELEASE_SHA = "d" * 64
PATCHMON_SHA = "e" * 64


def test_deterministic_case_id_is_stable_uuid4_shape() -> None:
    first = issue_closure_runtime._deterministic_uuid4("closure")
    second = issue_closure_runtime._deterministic_uuid4("closure")

    assert first == second
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}",
        first,
    )


def test_closure_identity_requires_exact_revision_digest_and_evidence_hashes() -> None:
    issue_closure_runtime._require_identity(
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
        baseline_revision=BASELINE,
        release_evidence_sha256=RELEASE_SHA,
        patchmon_evidence_sha256=PATCHMON_SHA,
    )

    with pytest.raises(ValueError, match="expected_revision"):
        issue_closure_runtime._require_identity(
            expected_revision="main",
            expected_image_digest=DIGEST,
            baseline_revision=BASELINE,
            release_evidence_sha256=RELEASE_SHA,
            patchmon_evidence_sha256=PATCHMON_SHA,
        )
    with pytest.raises(ValueError, match="expected_image_digest"):
        issue_closure_runtime._require_identity(
            expected_revision=REVISION,
            expected_image_digest="latest",
            baseline_revision=BASELINE,
            release_evidence_sha256=RELEASE_SHA,
            patchmon_evidence_sha256=PATCHMON_SHA,
        )


def test_verified_bug_case_binds_release_runtime_and_patchmon_evidence() -> None:
    case = issue_closure_runtime._build_verified_bug_case(
        baseline_revision=BASELINE,
        expected_revision=REVISION,
        expected_image_digest=DIGEST,
        release_evidence_sha256=RELEASE_SHA,
        patchmon_evidence_sha256=PATCHMON_SHA,
    )

    assert case.status.value == "verified"
    assert case.base_revision == BASELINE
    assert case.head_revision == REVISION
    assert case.merge_revision == REVISION
    assert case.patch_commit == REVISION
    assert case.artifact_digest == DIGEST
    assert case.revision_label == REVISION
    assert case.patchmon_readback == f"patchmon:evidence:{PATCHMON_SHA}"
    assert case.runtime_readback == f"runtime:revision:{REVISION}"
    assert len(case.provenance_hash) == 64


def test_closure_runtime_requires_all_three_persistence_families() -> None:
    assert set(issue_closure_runtime.EXPECTED_SCHEMA_TABLES) == {
        "bug_evidence_cases",
        "bug_evidence_embeddings",
        "memory_forest_leaves",
        "memory_forest_embeddings",
        "memory_forest_conflicts",
        "environment_manifests",
        "principal_resolution_receipts",
        "credential_resolution_receipts",
        "egress_decision_receipts",
        "mcp_installation_bindings",
        "execution_identity_receipts",
    }


def test_backend_runtime_and_deployment_mirror_are_byte_identical() -> None:
    canonical = ROOT / "backend" / "agent_runtime" / "issue_closure_runtime.py"
    mirror = ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "issue_closure_runtime.py"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_append_only_migration_is_mirrored_and_has_no_comment_drop_example() -> None:
    canonical = ROOT / "backend" / "migrations" / "050_bug_evidence_append_only.sql"
    mirror = ROOT / "scripts" / "sovereign-backend" / "migrations" / "050_bug_evidence_append_only.sql"
    payload = canonical.read_text("utf-8")

    assert canonical.read_bytes() == mirror.read_bytes()
    assert "BUG_EVIDENCE_APPEND_ONLY_VIOLATION" in payload
    assert "BEFORE UPDATE OR DELETE ON bug_evidence_cases" in payload
    assert "DROP TABLE" not in payload
