"""Tests for resource lock primitives.

Referenced by:
    - Issue #1119: Atomic Versioned Mutation Control
    - Section 5: Resource Locks
"""

import pytest

from backend.agent_runtime.mutations.resource_lock import (
    build_lock_error,
    check_lock_active,
    check_mutation_blocked_by_lock,
    format_lock_manifest,
    validate_lock_scope,
    validate_unlock_capability,
)
from backend.agent_runtime.mutations.versioned_resource import (
    LOCK_MODE_DEPLOYMENT_FREEZE,
    LOCK_MODE_INCIDENT_FREEZE,
    LOCK_MODE_MUTATION_LOCKED,
    ResourceLock,
    ResourceLockError,
    ResourceScope,
    ResourceType,
)


class TestValidateLockScope:
    """Tests for lock scope validation."""

    def test_same_scope_valid(self) -> None:
        """Lock and mutation with same scope are valid."""
        scope = ResourceScope(owner_id="owner1", organization_id="org1")
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_DEPLOYMENT_FREEZE,
            reason_code="incident",
            required_unlock_capability="cap",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            scope=scope,
        )

        is_valid, error = validate_lock_scope(
            lock, scope, "deployment_target", "prod"
        )

        assert is_valid
        assert error is None

    def test_different_owner_invalid(self) -> None:
        """Different owners make the lock scope invalid for this mutation."""
        lock_scope = ResourceScope(owner_id="owner1")
        mutation_scope = ResourceScope(owner_id="owner2")
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_DEPLOYMENT_FREEZE,
            reason_code="incident",
            required_unlock_capability="cap",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            scope=lock_scope,
        )

        is_valid, error = validate_lock_scope(
            lock, mutation_scope, "deployment_target", "prod"
        )

        assert not is_valid
        assert "owner1" in error
        assert "owner2" in error

    def test_different_org_invalid(self) -> None:
        """Different organizations make the lock scope invalid."""
        lock_scope = ResourceScope(owner_id="owner1", organization_id="org1")
        mutation_scope = ResourceScope(owner_id="owner1", organization_id="org2")
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_DEPLOYMENT_FREEZE,
            reason_code="incident",
            required_unlock_capability="cap",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            scope=lock_scope,
        )

        is_valid, error = validate_lock_scope(
            lock, mutation_scope, "deployment_target", "prod"
        )

        assert not is_valid
        assert "org1" in error

    def test_legacy_lock_without_scope_invalid(self) -> None:
        """Legacy locks without scope are invalid for scoped mutations."""
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_DEPLOYMENT_FREEZE,
            reason_code="incident",
            required_unlock_capability="cap",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            scope=None,  # Legacy lock
        )
        mutation_scope = ResourceScope(owner_id="owner1")

        is_valid, error = validate_lock_scope(
            lock, mutation_scope, "deployment_target", "prod"
        )

        assert not is_valid
        assert "without scope" in error


class TestCheckLockActive:
    """Tests for lock active status check."""

    def test_active_lock(self) -> None:
        """Lock without expiration is active."""
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_MUTATION_LOCKED,
            reason_code="test",
            required_unlock_capability="cap",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            expires_at=None,  # No expiration
        )

        is_active, reason = check_lock_active(lock, current_time=1000)

        assert is_active
        assert reason is None

    def test_expired_lock(self) -> None:
        """Expired lock is not active."""
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_MUTATION_LOCKED,
            reason_code="test",
            required_unlock_capability="cap",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            expires_at=500,  # Expired at 500
        )

        is_active, reason = check_lock_active(lock, current_time=1000)

        assert not is_active
        assert "expired" in reason

    def test_future_expiration_still_active(self) -> None:
        """Lock with future expiration is still active."""
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_MUTATION_LOCKED,
            reason_code="test",
            required_unlock_capability="cap",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            expires_at=2000,  # Expires at 2000
        )

        is_active, reason = check_lock_active(lock, current_time=1000)

        assert is_active


class TestValidateUnlockCapability:
    """Tests for unlock capability validation."""

    def test_correct_capability(self) -> None:
        """Correct capability can unlock."""
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_DEPLOYMENT_FREEZE,
            reason_code="incident",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
        )

        is_authorized, error = validate_unlock_capability(
            lock, "deployment.freeze.release"
        )

        assert is_authorized
        assert error is None

    def test_wrong_capability_rejected(self) -> None:
        """Wrong capability cannot unlock."""
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_DEPLOYMENT_FREEZE,
            reason_code="incident",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
        )

        is_authorized, error = validate_unlock_capability(lock, "wrong.capability")

        assert not is_authorized
        assert "wrong.capability" in error


class TestCheckMutationBlockedByLock:
    """Tests for mutation blocking check."""

    def test_no_locks_allows_mutation(self) -> None:
        """No locks means mutation is not blocked."""
        scope = ResourceScope(owner_id="owner1")

        is_blocked, lock, error = check_mutation_blocked_by_lock(
            locks=[],
            mutation_scope=scope,
            mutation_resource_type="deployment_target",
            mutation_resource_id="prod",
        )

        assert not is_blocked
        assert lock is None

    def test_active_matching_lock_blocks(self) -> None:
        """Active lock with matching scope blocks mutation."""
        scope = ResourceScope(owner_id="owner1")
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_INCIDENT_FREEZE,
            reason_code="incident_investigation",
            required_unlock_capability="incident.unfreeze",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            scope=scope,
            expires_at=None,
        )

        is_blocked, blocking_lock, error = check_mutation_blocked_by_lock(
            locks=[lock],
            mutation_scope=scope,
            mutation_resource_type="deployment_target",
            mutation_resource_id="prod",
        )

        assert is_blocked
        assert blocking_lock is lock
        assert blocking_lock.reason_code == "incident_investigation"

    def test_expired_lock_does_not_block(self) -> None:
        """Expired lock does not block mutation."""
        scope = ResourceScope(owner_id="owner1")
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_INCIDENT_FREEZE,
            reason_code="incident_investigation",
            required_unlock_capability="incident.unfreeze",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            scope=scope,
            expires_at=500,  # Expired
        )

        is_blocked, blocking_lock, error = check_mutation_blocked_by_lock(
            locks=[lock],
            mutation_scope=scope,
            mutation_resource_type="deployment_target",
            mutation_resource_id="prod",
        )

        assert not is_blocked

    def test_different_scope_lock_does_not_block(self) -> None:
        """Lock with different scope does not block mutation."""
        lock_scope = ResourceScope(owner_id="owner1", organization_id="org1")
        mutation_scope = ResourceScope(owner_id="owner1", organization_id="org2")
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_INCIDENT_FREEZE,
            reason_code="incident_investigation",
            required_unlock_capability="incident.unfreeze",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            scope=lock_scope,
        )

        is_blocked, blocking_lock, error = check_mutation_blocked_by_lock(
            locks=[lock],
            mutation_scope=mutation_scope,
            mutation_resource_type="deployment_target",
            mutation_resource_id="prod",
        )

        assert not is_blocked


class TestBuildLockError:
    """Tests for lock error construction."""

    def test_build_lock_error(self) -> None:
        """Builds proper ResourceLockError."""
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_DEPLOYMENT_FREEZE,
            reason_code="incident",
            required_unlock_capability="cap",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            lock_id="lock-123",
        )

        error = build_lock_error(lock, "deployment_target", "prod")

        assert isinstance(error, ResourceLockError)
        assert error.resource_type == "deployment_target"
        assert error.resource_id == "prod"
        assert error.lock_mode == "deployment_freeze"
        assert error.reason_code == "incident"
        assert error.lock_id == "lock-123"


class TestFormatLockManifest:
    """Tests for lock manifest formatting."""

    def test_format_empty_manifest(self) -> None:
        """Empty lock list formats correctly."""
        manifest = format_lock_manifest([])

        assert manifest["lock_count"] == 0
        assert manifest["locks"] == []

    def test_format_single_lock(self) -> None:
        """Single lock formats correctly."""
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_INCIDENT_FREEZE,
            reason_code="incident",
            required_unlock_capability="cap",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            lock_id="lock-123",
            created_at=1000,
            expires_at=None,
        )

        manifest = format_lock_manifest([lock])

        assert manifest["lock_count"] == 1
        assert len(manifest["locks"]) == 1
        assert manifest["locks"][0]["resource_type"] == "deployment_target"
        assert manifest["locks"][0]["resource_id"] == "prod"
        assert manifest["locks"][0]["lock_id"] == "lock-123"

    def test_format_multiple_locks(self) -> None:
        """Multiple locks format correctly."""
        lock1 = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod",
            mode=LOCK_MODE_DEPLOYMENT_FREEZE,
            reason_code="maintenance",
            required_unlock_capability="cap1",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            created_at=1000,
        )
        lock2 = ResourceLock(
            resource_type="appdeploy_snapshot",
            resource_id="snap-1",
            mode=LOCK_MODE_MUTATION_LOCKED,
            reason_code="update",
            required_unlock_capability="cap2",
            owner_id="owner1",
            created_by_capability="cap",
            created_at_revision="rev",
            created_at=2000,
        )

        manifest = format_lock_manifest([lock1, lock2])

        assert manifest["lock_count"] == 2
        assert len(manifest["locks"]) == 2
