"""Tests for Compare-and-Swap (CAS) primitives.

Referenced by:
    - Issue #1119: Atomic Versioned Mutation Control
    - Section 3: CAS-Entscheidung
    - Section 4: Deterministischer Merge
"""

import pytest

from backend.agent_runtime.mutations.cas import (
    CASDecision,
    CASResult,
    check_cas_prerequisites,
    detect_field_overlap,
    merge_disjoint_fields,
)
from backend.agent_runtime.mutations.versioned_resource import (
    MutationConflict,
    MutationFailureCode,
)


class TestMergeDisjointFields:
    """Tests for field-level merge detection."""

    def test_merge_disjoint_fields_success(self) -> None:
        """Two actors change different fields - merge should succeed."""
        base = {"name": "test", "status": "active", "version": 1}
        head = {"name": "actor1_name", "status": "active", "version": 1}  # Actor 1 changed name
        proposed = {"name": "test", "status": "inactive", "version": 1}  # Actor 2 changed status

        merged, decision = merge_disjoint_fields(base, head, proposed)

        assert decision.decision == "merge"
        assert merged["name"] == "actor1_name"  # Preserved from head
        assert merged["status"] == "inactive"  # Applied from proposal
        assert merged["version"] == 1

    def test_merge_disjoint_fields_same_field_conflict(self) -> None:
        """Two actors change the same field - merge should fail."""
        base = {"name": "test", "status": "active"}
        head = {"name": "actor1_name", "status": "active"}  # Actor 1 changed name
        proposed = {"name": "actor2_name", "status": "active"}  # Actor 2 also changed name

        with pytest.raises(MutationConflict) as exc_info:
            merge_disjoint_fields(base, head, proposed)

        assert exc_info.value.code == MutationFailureCode.OVERLAPPING_CHANGE
        assert "name" in exc_info.value.conflicting_fields

    def test_merge_disjoint_fields_protected_field_rejected(self) -> None:
        """Modifying a protected field (like permissions) is never allowed."""
        base = {"name": "test", "permissions": ["read"]}
        head = {"name": "test", "permissions": ["read"]}
        proposed = {"name": "test", "permissions": ["read", "write"]}  # Trying to add write

        with pytest.raises(MutationConflict) as exc_info:
            merge_disjoint_fields(base, head, proposed)

        assert exc_info.value.code == MutationFailureCode.OVERLAPPING_CHANGE
        assert "permissions" in exc_info.value.conflicting_fields

    def test_merge_disjoint_fields_empty_changes(self) -> None:
        """When proposal has no changes, should just return head."""
        base = {"name": "test", "status": "active"}
        head = {"name": "modified", "status": "active"}
        proposed = {"name": "test", "status": "active"}  # No changes

        merged, decision = merge_disjoint_fields(base, head, proposed)

        assert decision.decision == "merge"
        assert merged == head  # Should be identical to head

    def test_merge_disjoint_fields_nested_dicts(self) -> None:
        """Nested dict changes should be detected as field changes."""
        base = {"config": {"key": "value"}, "status": "active"}
        head = {"config": {"key": "new_value"}, "status": "active"}  # config changed
        proposed = {"config": {"key": "value"}, "status": "inactive"}  # status changed

        merged, decision = merge_disjoint_fields(base, head, proposed)

        assert decision.decision == "merge"
        assert merged["config"] == {"key": "new_value"}  # From head
        assert merged["status"] == "inactive"  # From proposal


class TestDetectFieldOverlap:
    """Tests for field overlap detection."""

    def test_detect_overlap_no_overlap(self) -> None:
        """No overlap when changes are on different fields."""
        base = {"a": 1, "b": 2, "c": 3}
        current = {"a": 10, "b": 2, "c": 3}  # Only 'a' changed
        proposed = {"a": 1, "b": 20, "c": 3}  # Only 'b' changed

        has_overlap, fields = detect_field_overlap(base, current, proposed)

        assert not has_overlap
        assert len(fields) == 0

    def test_detect_overlap_with_overlap(self) -> None:
        """Detects overlap when same field changed."""
        base = {"a": 1, "b": 2, "c": 3}
        current = {"a": 10, "b": 2, "c": 3}  # 'a' changed
        proposed = {"a": 20, "b": 2, "c": 3}  # 'a' also changed

        has_overlap, fields = detect_field_overlap(base, current, proposed)

        assert has_overlap
        assert fields == {"a"}

    def test_detect_overlap_multiple_fields(self) -> None:
        """Detects multiple overlapping fields."""
        base = {"a": 1, "b": 2, "c": 3}
        current = {"a": 10, "b": 20, "c": 3}  # a and b changed
        proposed = {"a": 11, "b": 21, "c": 30}  # a, b, and c changed

        has_overlap, fields = detect_field_overlap(base, current, proposed)

        assert has_overlap
        assert fields == {"a", "b"}


class TestCheckCASPrerequisites:
    """Tests for CAS prerequisite checking."""

    def test_prerequisites_met(self) -> None:
        """All prerequisites met - should pass."""
        ok, error = check_cas_prerequisites(
            base_hash="abc123",
            head_hash="abc123",  # Same as base - no drift
            payload_hash="def456",
            expected_base_hash="abc123",
            expected_payload_hash="def456",
        )

        assert ok
        assert error is None

    def test_prerequisites_stale_base(self) -> None:
        """Base hash doesn't match - stale base state."""
        ok, error = check_cas_prerequisites(
            base_hash="abc123",
            head_hash="abc123",
            payload_hash="def456",
            expected_base_hash="xyz789",  # Different base
            expected_payload_hash="def456",
        )

        assert not ok
        assert error is not None
        assert error.code == MutationFailureCode.BASE_STATE_STALE

    def test_prerequisites_head_moved(self) -> None:
        """Head hash different from base - another mutation occurred."""
        ok, error = check_cas_prerequisites(
            base_hash="abc123",
            head_hash="xyz789",  # Different from base
            payload_hash="def456",
            expected_base_hash="abc123",
            expected_payload_hash="def456",
        )

        assert not ok
        assert error is not None
        assert error.code == MutationFailureCode.HEAD_MOVED

    def test_prerequisites_idempotency_mismatch(self) -> None:
        """Same idempotency key with different payload - suspicious."""
        ok, error = check_cas_prerequisites(
            base_hash="abc123",
            head_hash="abc123",
            payload_hash="def456",
            expected_base_hash="abc123",
            expected_payload_hash="different",  # Different payload
        )

        assert not ok
        assert error is not None
        assert error.code == MutationFailureCode.IDEMPOTENCY_REPLAY_MISMATCH


class TestCASResult:
    """Tests for CAS result structures."""

    def test_cas_result_success(self) -> None:
        """Successful CAS result."""
        result = CASResult[str](
            success=True,
            new_resource="new_value",
            cas_decision=CASDecision(decision="apply", head=None),
        )

        assert result.success
        assert result.new_resource == "new_value"
        assert result.cas_decision.decision == "apply"

    def test_cas_result_conflict(self) -> None:
        """Conflicted CAS result."""
        conflict = MutationConflict(
            code=MutationFailureCode.BASE_STATE_STALE,
            expected_hash="abc123",
            actual_hash="xyz789",
        )
        result = CASResult[str](
            success=False,
            new_resource=None,
            cas_decision=CASDecision(decision="conflict", head=None),
            error=conflict,
        )

        assert not result.success
        assert result.new_resource is None
        assert result.error is conflict


class TestMutationConflictToDict:
    """Tests for MutationConflict serialization."""

    def test_to_dict_redacts_hashes(self) -> None:
        """Hashes are partially redacted in API output."""
        conflict = MutationConflict(
            code=MutationFailureCode.BASE_STATE_STALE,
            expected_hash="0" * 64,
            actual_hash="f" * 64,
            conflicting_fields=("field1", "field2"),
            suggested_action="Read new head",
        )

        result = conflict.to_dict()

        assert result["code"] == "BASE_STATE_STALE"
        assert "..." in result["expected_hash_prefix"]
        assert "..." in result["actual_hash_prefix"]
        assert result["conflicting_fields"] == ["field1", "field2"]
