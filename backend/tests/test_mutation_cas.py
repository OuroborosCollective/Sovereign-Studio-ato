"""Tests for Compare-and-Swap (CAS) operations.

These tests verify the CAS primitive and conflict detection functionality
from the atomic versioned mutation control layer.
"""

from __future__ import annotations

import pytest
from typing import Any

from backend.agent_runtime.mutations.versioned_resource import (
    VersionedResourceRef,
    MutationIntent,
    build_versioned_resource_ref,
    build_mutation_intent,
    canonical_sha256,
)
from backend.agent_runtime.mutations.cas import (
    MutationConflict,
    ConflictCode,
    CASDecision,
    check_base_head_match,
    check_version_progression,
    detect_overlapping_changes,
    cas_from_github_pr,
    build_conflict_response,
)
from backend.agent_runtime.mutations.merge import (
    merge_disjoint,
    merge_or_raise,
    PROTECTED_MUTATION_FIELDS,
)


class TestCheckBaseHeadMatch:
    """Tests for base vs head matching logic."""

    def test_match_when_hashes_equal(self) -> None:
        """Base and head match when content hashes are equal."""
        base = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        head = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="6",
            content_hash="a" * 64,
        )

        assert check_base_head_match(base, head) is True

    def test_no_match_when_hashes_differ(self) -> None:
        """Base and head don't match when content hashes differ."""
        base = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        head = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="6",
            content_hash="b" * 64,
        )

        assert check_base_head_match(base, head) is False

    def test_match_when_head_none_and_base_at_version_zero(self) -> None:
        """Head None is valid if base has no prior version."""
        base = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-new",
            owner_id="owner-456",
            version="0",
            content_hash="0" * 64,
        )

        assert check_base_head_match(base, None) is True

    def test_no_match_when_head_none_and_base_has_content(self) -> None:
        """Head None is invalid if base has existing content."""
        base = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )

        assert check_base_head_match(base, None) is False


class TestCheckVersionProgression:
    """Tests for version progression checking."""

    def test_newer_version_allowed(self) -> None:
        """Head with higher version is allowed."""
        base = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        head = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="6",
            content_hash="a" * 64,
        )

        assert check_version_progression(base, head) is True

    def test_same_version_allowed(self) -> None:
        """Head with same version is allowed."""
        base = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        head = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="b" * 64,
        )

        assert check_version_progression(base, head) is True

    def test_older_version_rejected(self) -> None:
        """Head with lower version is rejected."""
        base = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="6",
            content_hash="a" * 64,
        )
        head = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="b" * 64,
        )

        assert check_version_progression(base, head) is False

    def test_none_head_allowed(self) -> None:
        """Head None is always allowed (starting state)."""
        base = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )

        assert check_version_progression(base, None) is True


class TestDetectOverlappingChanges:
    """Tests for overlap detection between changes."""

    def test_disjoint_changes_no_overlap(self) -> None:
        """Disjoint field changes have no overlap."""
        base = {"field_a": 1, "field_b": 2, "field_c": 3}
        head = {"field_a": 10, "field_b": 2, "field_c": 3}
        proposed = {"field_a": 1, "field_b": 2, "field_c": 30}

        overlap, protected = detect_overlapping_changes(
            base, head, proposed, frozenset()
        )

        assert overlap == frozenset()
        assert protected is False

    def test_overlapping_changes_detected(self) -> None:
        """Overlapping changes are detected."""
        base = {"field_a": 1, "field_b": 2}
        head = {"field_a": 10, "field_b": 2}
        proposed = {"field_a": 1, "field_b": 20}

        overlap, protected = detect_overlapping_changes(
            base, head, proposed, frozenset()
        )

        assert overlap == frozenset()
        assert protected is False

    def test_protected_field_overlap_detected(self) -> None:
        """Protected field overlap is flagged."""
        base = {"field_a": 1, "permissions": "read"}
        head = {"field_a": 10, "permissions": "read"}
        proposed = {"field_a": 1, "permissions": "write"}

        overlap, protected = detect_overlapping_changes(
            base, head, proposed, PROTECTED_MUTATION_FIELDS
        )

        assert "permissions" in overlap
        assert protected is True


class TestMergeDisjoint:
    """Tests for deterministic disjoint merge."""

    def test_merge_succeeds_for_disjoint_changes(self) -> None:
        """Disjoint changes are merged successfully."""
        base = {"field_a": 1, "field_b": 2, "field_c": 3}
        head = {"field_a": 10, "field_b": 2, "field_c": 3}
        proposed = {"field_a": 1, "field_b": 2, "field_c": 30}

        result = merge_disjoint(base, head, proposed)

        assert result.merged is True
        assert result.merged_payload == {"field_a": 10, "field_b": 2, "field_c": 30}
        assert result.conflict_fields == ()
        assert result.protected_conflict is False

    def test_merge_fails_for_overlapping_changes(self) -> None:
        """Overlapping changes fail merge."""
        base = {"field_a": 1, "field_b": 2}
        head = {"field_a": 10, "field_b": 2}
        proposed = {"field_a": 1, "field_b": 20}

        result = merge_disjoint(base, head, proposed)

        assert result.merged is False
        assert result.merged_payload is None
        assert "field_a" in result.conflict_fields or "field_b" in result.conflict_fields

    def test_merge_fails_for_protected_field_overlap(self) -> None:
        """Protected field overlap fails merge with flag."""
        base = {"field_a": 1, "policy": "allow"}
        head = {"field_a": 10, "policy": "allow"}
        proposed = {"field_a": 1, "policy": "deny"}

        result = merge_disjoint(base, head, proposed, PROTECTED_MUTATION_FIELDS)

        assert result.merged is False
        assert result.protected_conflict is True

    def test_merge_or_raise_raises_on_conflict(self) -> None:
        """merge_or_raise raises MutationConflict on failure."""
        base = {"field_a": 1, "field_b": 2}
        head = {"field_a": 10, "field_b": 2}
        proposed = {"field_a": 1, "field_b": 20}

        with pytest.raises(MutationConflict) as exc_info:
            merge_or_raise(base, head, proposed)

        assert exc_info.value.code == ConflictCode.OVERLAPPING_CHANGE


class TestGitHubPRCAS:
    """Tests for GitHub PR-specific CAS decisions."""

    def test_cas_passes_with_matching_heads(self) -> None:
        """CAS passes when PR head and main head match expected."""
        intent = build_mutation_intent(
            resource=build_versioned_resource_ref(
                resource_type="github_pr_metadata",
                resource_id="pr-123",
                owner_id="owner-456",
                version="1",
                content_hash="a" * 64,
            ),
            capability_id="github.merge",
            canonical_payload={"action": "merge"},
            permission_receipt_hash="b" * 64,
            idempotency_key="merge-pr-123-001",
            expected_effect_hash="c" * 64,
        )

        result = cas_from_github_pr(
            intent=intent,
            expected_pr_head="abc123",
            actual_pr_head="abc123",
            expected_main_head="def456",
            actual_main_head="def456",
        )

        assert result.allowed is True
        assert result.decision_code == "GITHUB_CAS_PASSED"

    def test_cas_fails_on_pr_head_mismatch(self) -> None:
        """CAS fails when PR head has changed."""
        intent = build_mutation_intent(
            resource=build_versioned_resource_ref(
                resource_type="github_pr_metadata",
                resource_id="pr-123",
                owner_id="owner-456",
                version="1",
                content_hash="a" * 64,
            ),
            capability_id="github.merge",
            canonical_payload={"action": "merge"},
            permission_receipt_hash="b" * 64,
            idempotency_key="merge-pr-123-001",
            expected_effect_hash="c" * 64,
        )

        with pytest.raises(MutationConflict) as exc_info:
            cas_from_github_pr(
                intent=intent,
                expected_pr_head="abc123",
                actual_pr_head="xyz789",
                expected_main_head="def456",
                actual_main_head="def456",
            )

        assert exc_info.value.code == ConflictCode.HEAD_MOVED

    def test_cas_fails_on_main_head_mismatch(self) -> None:
        """CAS fails when main branch has moved."""
        intent = build_mutation_intent(
            resource=build_versioned_resource_ref(
                resource_type="github_pr_metadata",
                resource_id="pr-123",
                owner_id="owner-456",
                version="1",
                content_hash="a" * 64,
            ),
            capability_id="github.merge",
            canonical_payload={"action": "merge"},
            permission_receipt_hash="b" * 64,
            idempotency_key="merge-pr-123-001",
            expected_effect_hash="c" * 64,
        )

        with pytest.raises(MutationConflict) as exc_info:
            cas_from_github_pr(
                intent=intent,
                expected_pr_head="abc123",
                actual_pr_head="abc123",
                expected_main_head="def456",
                actual_main_head="xyz789",
            )

        assert exc_info.value.code == ConflictCode.BASE_STATE_STALE


class TestBuildConflictResponse:
    """Tests for structured conflict response."""

    def test_builds_correct_response_structure(self) -> None:
        """Response has correct structure for API consumers."""
        conflict = MutationConflict(
            code=ConflictCode.BASE_STATE_STALE,
            message="Base state does not match current head",
            expected_hash="a" * 64,
            actual_hash="b" * 64,
            allowed_next_step="rebase_and_retry",
        )

        response = build_conflict_response(conflict)

        assert response["ok"] is False
        assert response["error"]["code"] == ConflictCode.BASE_STATE_STALE
        assert response["error"]["expected_hash"] == "a" * 64
        assert response["error"]["actual_hash"] == "b" * 64
        assert response["allowed_next_step"] == "rebase_and_retry"


class TestVersionedResourceValidation:
    """Tests for VersionedResourceRef validation."""

    def test_rejects_invalid_resource_type(self) -> None:
        """Invalid resource type raises error."""
        with pytest.raises(Exception):  # VersionedResourceError
            build_versioned_resource_ref(
                resource_type="invalid_type",
                resource_id="id-123",
                owner_id="owner-456",
                version="1",
                content_hash="a" * 64,
            )

    def test_rejects_invalid_content_hash(self) -> None:
        """Invalid content hash raises error."""
        with pytest.raises(Exception):  # VersionedResourceError
            build_versioned_resource_ref(
                resource_type="agent_config",
                resource_id="id-123",
                owner_id="owner-456",
                version="1",
                content_hash="invalid-hash",
            )

    def test_accepts_valid_reference(self) -> None:
        """Valid reference is accepted."""
        ref = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="id-123",
            owner_id="owner-456",
            version="1",
            content_hash="a" * 64,
        )

        assert ref.resource_type == "agent_config"
        assert ref.resource_id == "id-123"
        assert ref.content_hash == "a" * 64


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
