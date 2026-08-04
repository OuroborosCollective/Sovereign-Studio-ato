"""Tests for Resource Lock operations.

These tests verify the resource lock primitive functionality
from the atomic versioned mutation control layer.
"""

from __future__ import annotations

import pytest

from backend.agent_runtime.mutations.resource_lock import (
    ResourceLock,
    LockMode,
    VALID_LOCK_MODES,
    ResourceLockError,
    build_resource_lock,
    validate_lock_release,
    check_resource_locked,
    LockReleaseRequest,
)
from backend.agent_runtime.mutations.versioned_resource import canonical_sha256


class TestResourceLockCreation:
    """Tests for ResourceLock creation and validation."""

    def test_creates_valid_lock(self) -> None:
        """Valid lock parameters create a lock successfully."""
        lock = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="incident_investigation",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner-123",
            created_by_receipt="a" * 64,
            created_at_revision="abc123",
            required_readbacks=["runtime_health", "image_revision"],
        )

        assert lock.resource_type == "deployment_target"
        assert lock.resource_id == "sovereign-production"
        assert lock.lock_mode == LockMode.DEPLOYMENT_FREEZE
        assert "runtime_health" in lock.required_readbacks
        assert "image_revision" in lock.required_readbacks
        assert len(lock.lock_hash) == 64

    def test_rejects_invalid_lock_mode(self) -> None:
        """Invalid lock mode raises error."""
        with pytest.raises(ResourceLockError):
            build_resource_lock(
                resource_type="deployment_target",
                resource_id="sovereign-production",
                lock_mode="invalid_mode",
                reason_code="test",
                required_unlock_capability="test.cap",
                owner_id="owner-123",
                created_by_receipt="a" * 64,
                created_at_revision="abc123",
            )

    def test_rejects_invalid_receipt_hash(self) -> None:
        """Invalid created_by_receipt hash raises error."""
        with pytest.raises(ResourceLockError):
            build_resource_lock(
                resource_type="deployment_target",
                resource_id="sovereign-production",
                lock_mode=LockMode.DEPLOYMENT_FREEZE,
                reason_code="test",
                required_unlock_capability="test.cap",
                owner_id="owner-123",
                created_by_receipt="invalid-hash",
                created_at_revision="abc123",
            )

    def test_lock_hash_is_deterministic(self) -> None:
        """Same inputs produce same lock hash."""
        lock1 = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="incident_investigation",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner-123",
            created_by_receipt="a" * 64,
            created_at_revision="abc123",
            required_readbacks=["runtime_health"],
        )

        lock2 = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="incident_investigation",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner-123",
            created_by_receipt="a" * 64,
            created_at_revision="abc123",
            required_readbacks=["runtime_health"],
        )

        assert lock1.lock_hash == lock2.lock_hash

    def test_different_inputs_produce_different_hash(self) -> None:
        """Different inputs produce different lock hash."""
        lock1 = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="incident_investigation",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner-123",
            created_by_receipt="a" * 64,
            created_at_revision="abc123",
            required_readbacks=["runtime_health"],
        )

        lock2 = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="incident_investigation",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner-123",
            created_by_receipt="b" * 64,  # Different receipt
            created_at_revision="abc123",
            required_readbacks=["runtime_health"],
        )

        assert lock1.lock_hash != lock2.lock_hash


class TestLockScopes:
    """Tests for lock scope matching."""

    def test_scopes_match_same_resource(self) -> None:
        """Same resource type and ID match."""
        lock = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="test",
            required_unlock_capability="test.cap",
            owner_id="owner-123",
            created_by_receipt="a" * 64,
            created_at_revision="abc123",
        )

        assert lock.scopes_match("deployment_target", "sovereign-production") is True

    def test_scopes_dont_match_different_id(self) -> None:
        """Different resource ID doesn't match."""
        lock = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="test",
            required_unlock_capability="test.cap",
            owner_id="owner-123",
            created_by_receipt="a" * 64,
            created_at_revision="abc123",
        )

        assert lock.scopes_match("deployment_target", "sovereign-staging") is False

    def test_scopes_dont_match_different_type(self) -> None:
        """Different resource type doesn't match."""
        lock = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="test",
            required_unlock_capability="test.cap",
            owner_id="owner-123",
            created_by_receipt="a" * 64,
            created_at_revision="abc123",
        )

        assert lock.scopes_match("agent_config", "sovereign-production") is False


class TestCanUnlockWith:
    """Tests for unlock authorization checking."""

    def test_can_unlock_with_correct_capability(self) -> None:
        """Correct capability can unlock."""
        lock = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="test",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner-123",
            created_by_receipt="a" * 64,
            created_at_revision="abc123",
            required_readbacks=["runtime_health", "image_revision"],
        )

        allowed, reason = lock.can_unlock_with(
            "deployment.freeze.release",
            ["runtime_health", "image_revision"]
        )

        assert allowed is True
        assert "authorized" in reason.lower()

    def test_cannot_unlock_with_wrong_capability(self) -> None:
        """Wrong capability cannot unlock."""
        lock = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="test",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner-123",
            created_by_receipt="a" * 64,
            created_at_revision="abc123",
            required_readbacks=["runtime_health"],
        )

        allowed, reason = lock.can_unlock_with(
            "wrong.capability",
            ["runtime_health"]
        )

        assert allowed is False
        assert "does not match" in reason

    def test_cannot_unlock_with_missing_readbacks(self) -> None:
        """Missing required readbacks cannot unlock."""
        lock = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="test",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner-123",
            created_by_receipt="a" * 64,
            created_at_revision="abc123",
            required_readbacks=["runtime_health", "image_revision"],
        )

        allowed, reason = lock.can_unlock_with(
            "deployment.freeze.release",
            ["runtime_health"]  # Missing image_revision
        )

        assert allowed is False
        assert "missing required readbacks" in reason.lower()


class TestValidateLockRelease:
    """Tests for lock release validation."""

    def test_validates_correct_release_request(self) -> None:
        """Valid release request passes validation."""
        lock = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="test",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner-123",
            created_by_receipt="a" * 64,
            created_at_revision="abc123",
            required_readbacks=["runtime_health"],
        )

        request = LockReleaseRequest(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_hash=lock.lock_hash,
            unlock_capability_id="deployment.freeze.release",
            unlock_receipt_hash="b" * 64,
            unlock_readbacks=["runtime_health"],
        )

        valid, reason = validate_lock_release(lock, request)

        assert valid is True

    def test_rejects_scope_mismatch(self) -> None:
        """Scope mismatch fails validation."""
        lock = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="test",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner-123",
            created_by_receipt="a" * 64,
            created_at_revision="abc123",
        )

        request = LockReleaseRequest(
            resource_type="deployment_target",
            resource_id="sovereign-staging",  # Different ID
            lock_hash=lock.lock_hash,
            unlock_capability_id="deployment.freeze.release",
            unlock_receipt_hash="b" * 64,
            unlock_readbacks=[],
        )

        valid, reason = validate_lock_release(lock, request)

        assert valid is False
        assert "scope mismatch" in reason.lower()

    def test_rejects_hash_mismatch(self) -> None:
        """Lock hash mismatch fails validation."""
        lock = build_resource_lock(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_mode=LockMode.DEPLOYMENT_FREEZE,
            reason_code="test",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner-123",
            created_by_receipt="a" * 64,
            created_at_revision="abc123",
        )

        request = LockReleaseRequest(
            resource_type="deployment_target",
            resource_id="sovereign-production",
            lock_hash="b" * 64,  # Wrong hash
            unlock_capability_id="deployment.freeze.release",
            unlock_receipt_hash="c" * 64,
            unlock_readbacks=[],
        )

        valid, reason = validate_lock_release(lock, request)

        assert valid is False
        assert "hash mismatch" in reason.lower()


class TestCheckResourceLocked:
    """Tests for checking if a resource is locked."""

    def test_finds_active_lock(self) -> None:
        """Active lock is found."""
        locks = [
            build_resource_lock(
                resource_type="deployment_target",
                resource_id="sovereign-production",
                lock_mode=LockMode.DEPLOYMENT_FREEZE,
                reason_code="test",
                required_unlock_capability="test.cap",
                owner_id="owner-123",
                created_by_receipt="a" * 64,
                created_at_revision="abc123",
            ),
        ]

        is_locked, blocking_lock = check_resource_locked(
            locks, "deployment_target", "sovereign-production"
        )

        assert is_locked is True
        assert blocking_lock is not None
        assert blocking_lock.lock_mode == LockMode.DEPLOYMENT_FREEZE

    def test_no_lock_when_none_exist(self) -> None:
        """No lock found when none exist."""
        locks = []

        is_locked, blocking_lock = check_resource_locked(
            locks, "deployment_target", "sovereign-production"
        )

        assert is_locked is False
        assert blocking_lock is None

    def test_excludes_specified_modes(self) -> None:
        """Excluded lock modes are not considered."""
        locks = [
            build_resource_lock(
                resource_type="deployment_target",
                resource_id="sovereign-production",
                lock_mode=LockMode.DEPLOYMENT_FREEZE,
                reason_code="test",
                required_unlock_capability="test.cap",
                owner_id="owner-123",
                created_by_receipt="a" * 64,
                created_at_revision="abc123",
            ),
        ]

        is_locked, blocking_lock = check_resource_locked(
            locks, "deployment_target", "sovereign-production",
            exclude_modes=frozenset([LockMode.DEPLOYMENT_FREEZE])
        )

        assert is_locked is False
        assert blocking_lock is None


class TestValidLockModes:
    """Tests for lock mode constants."""

    def test_all_lock_modes_are_valid(self) -> None:
        """All defined lock modes are in VALID_LOCK_MODES."""
        assert LockMode.MUTATION_LOCKED in VALID_LOCK_MODES
        assert LockMode.OWNER_LOCKED in VALID_LOCK_MODES
        assert LockMode.DEPLOYMENT_FREEZE in VALID_LOCK_MODES
        assert LockMode.INCIDENT_FREEZE in VALID_LOCK_MODES
        assert LockMode.MIGRATION_FREEZE in VALID_LOCK_MODES
        assert LockMode.READ_ONLY_MAINTENANCE in VALID_LOCK_MODES

    def test_lock_modes_are_distinct(self) -> None:
        """All lock modes are distinct."""
        modes = [
            LockMode.MUTATION_LOCKED,
            LockMode.OWNER_LOCKED,
            LockMode.DEPLOYMENT_FREEZE,
            LockMode.INCIDENT_FREEZE,
            LockMode.MIGRATION_FREEZE,
            LockMode.READ_ONLY_MAINTENANCE,
        ]
        assert len(modes) == len(set(modes))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
