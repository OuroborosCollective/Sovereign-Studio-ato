"""Tests for versioned resource contracts.

Referenced by:
    - Issue #1119: Atomic Versioned Mutation Control
    - Section 1: Versioned Resource Contract
"""

import pytest

from backend.agent_runtime.mutations.versioned_resource import (
    LOCK_MODE_DEPLOYMENT_FREEZE,
    LOCK_MODE_INCIDENT_FREEZE,
    LOCK_MODE_MIGRATION_FREEZE,
    LOCK_MODE_MUTATION_LOCKED,
    LOCK_MODE_OWNER_LOCKED,
    LOCK_MODE_READ_ONLY_MAINTENANCE,
    LOCK_MODES,
    PROTECTED_FIELDS,
    MutationConflict,
    MutationFailureCode,
    MutationIntent,
    MutationPhase,
    ResourceLock,
    ResourceLockError,
    ResourceScope,
    VersionedResource,
    VersionedResourceRef,
    verify_scope_isolation,
)


class TestResourceScope:
    """Tests for ResourceScope validation."""

    def test_valid_scope(self) -> None:
        """Valid scope with all fields."""
        scope = ResourceScope(
            owner_id="owner1",
            organization_id="org1",
            repository_id="repo1",
            workspace_id="ws1",
            environment_id="env1",
        )
        assert scope.owner_id == "owner1"

    def test_scope_requires_owner(self) -> None:
        """Scope must have an owner."""
        with pytest.raises(ValueError, match="owner_id is required"):
            ResourceScope(owner_id="")

    def test_scope_minimal(self) -> None:
        """Scope can be minimal with just owner_id."""
        scope = ResourceScope(owner_id="owner1")
        assert scope.owner_id == "owner1"
        assert scope.organization_id is None


class TestVersionedResourceRef:
    """Tests for VersionedResourceRef validation."""

    def test_valid_ref(self) -> None:
        """Valid reference with all fields."""
        scope = ResourceScope(owner_id="owner1")
        ref = VersionedResourceRef(
            resource_type="agent_config",
            resource_id="config-123",
            scope=scope,
            version="v1.0.0",
            content_hash="0" * 64,
        )
        assert ref.resource_type == "agent_config"
        assert ref.version == "v1.0.0"

    def test_ref_requires_resource_id(self) -> None:
        """Reference must have a resource_id."""
        scope = ResourceScope(owner_id="owner1")
        with pytest.raises(ValueError, match="resource_id is required"):
            VersionedResourceRef(
                resource_type="agent_config",
                resource_id="",
                scope=scope,
                version="v1",
                content_hash="0" * 64,
            )

    def test_ref_requires_valid_content_hash(self) -> None:
        """Reference must have a valid 64-char hex content_hash."""
        scope = ResourceScope(owner_id="owner1")
        with pytest.raises(ValueError, match="content_hash must be a 64-character hex"):
            VersionedResourceRef(
                resource_type="agent_config",
                resource_id="id123",
                scope=scope,
                version="v1",
                content_hash="invalid",
            )

    def test_ref_requires_version(self) -> None:
        """Reference must have a version."""
        scope = ResourceScope(owner_id="owner1")
        with pytest.raises(ValueError, match="version is required"):
            VersionedResourceRef(
                resource_type="agent_config",
                resource_id="id123",
                scope=scope,
                version="",
                content_hash="0" * 64,
            )


class TestVersionedResource:
    """Tests for VersionedResource."""

    def test_versioned_resource_properties(self) -> None:
        """Properties delegate to the underlying ref."""
        scope = ResourceScope(owner_id="owner1")
        ref = VersionedResourceRef(
            resource_type="policy_set",
            resource_id="policy-456",
            scope=scope,
            version="v2",
            content_hash="a" * 64,
        )
        resource = VersionedResource(
            ref=ref,
            payload={"rules": ["allow"]},
            created_at=1000,
            updated_at=2000,
        )

        assert resource.resource_type == "policy_set"
        assert resource.resource_id == "policy-456"
        assert resource.version == "v2"
        assert resource.content_hash == "a" * 64
        assert resource.scope == scope
        assert resource.payload == {"rules": ["allow"]}


class TestMutationIntent:
    """Tests for MutationIntent."""

    def test_valid_intent(self) -> None:
        """Valid mutation intent."""
        scope = ResourceScope(owner_id="owner1")
        ref = VersionedResourceRef(
            resource_type="agent_config",
            resource_id="config-123",
            scope=scope,
            version="v1",
            content_hash="b" * 64,
        )
        intent = MutationIntent(
            resource=ref,
            capability_id="deploy.capability",
            canonical_payload={"key": "value"},
            payload_hash="c" * 64,
            permission_receipt_hash="d" * 64,
        )

        assert intent.capability_id == "deploy.capability"
        assert intent.intent_id  # Should be generated
        assert intent.created_at  # Should be set

    def test_intent_requires_capability(self) -> None:
        """Intent must have a capability_id."""
        scope = ResourceScope(owner_id="owner1")
        ref = VersionedResourceRef(
            resource_type="agent_config",
            resource_id="config-123",
            scope=scope,
            version="v1",
            content_hash="b" * 64,
        )
        with pytest.raises(ValueError, match="capability_id is required"):
            MutationIntent(
                resource=ref,
                capability_id="",
                canonical_payload={"key": "value"},
                payload_hash="c" * 64,
                permission_receipt_hash="d" * 64,
            )

    def test_intent_requires_valid_payload_hash(self) -> None:
        """Intent must have a valid 64-char payload_hash."""
        scope = ResourceScope(owner_id="owner1")
        ref = VersionedResourceRef(
            resource_type="agent_config",
            resource_id="config-123",
            scope=scope,
            version="v1",
            content_hash="b" * 64,
        )
        with pytest.raises(ValueError, match="payload_hash must be"):
            MutationIntent(
                resource=ref,
                capability_id="cap",
                canonical_payload={},
                payload_hash="short",
                permission_receipt_hash="d" * 64,
            )


class TestResourceLock:
    """Tests for ResourceLock."""

    def test_valid_lock(self) -> None:
        """Valid lock with all required fields."""
        lock = ResourceLock(
            resource_type="deployment_target",
            resource_id="prod-deploy",
            mode=LOCK_MODE_DEPLOYMENT_FREEZE,
            reason_code="incident_investigation",
            required_unlock_capability="deployment.freeze.release",
            owner_id="owner1",
            created_by_capability="incident.capability",
            created_at_revision="abc123",
        )

        assert lock.resource_type == "deployment_target"
        assert lock.mode == "deployment_freeze"
        assert lock.lock_id  # Should be generated

    def test_lock_invalid_mode(self) -> None:
        """Lock must have a valid mode."""
        with pytest.raises(ValueError, match="Invalid lock mode"):
            ResourceLock(
                resource_type="deployment_target",
                resource_id="prod-deploy",
                mode="invalid_mode",
                reason_code="test",
                required_unlock_capability="cap",
                owner_id="owner1",
                created_by_capability="cap",
                created_at_revision="rev",
            )

    def test_lock_requires_resource_id(self) -> None:
        """Lock must have a resource_id."""
        with pytest.raises(ValueError, match="resource_id is required"):
            ResourceLock(
                resource_type="deployment_target",
                resource_id="",
                mode=LOCK_MODE_MUTATION_LOCKED,
                reason_code="test",
                required_unlock_capability="cap",
                owner_id="owner1",
                created_by_capability="cap",
                created_at_revision="rev",
            )


class TestMutationPhase:
    """Tests for MutationPhase enum."""

    def test_all_phases_defined(self) -> None:
        """All required phases are defined."""
        assert MutationPhase.PREPARED.value == "prepared"
        assert MutationPhase.LOCKED.value == "locked"
        assert MutationPhase.APPLIED_UNVERIFIED.value == "applied_unverified"
        assert MutationPhase.VERIFIED.value == "verified"
        assert MutationPhase.CONFLICTED.value == "conflicted"
        assert MutationPhase.BLOCKED.value == "blocked"
        assert MutationPhase.INVALIDATED.value == "invalidated"


class TestMutationFailureCode:
    """Tests for MutationFailureCode enum."""

    def test_all_codes_defined(self) -> None:
        """All required failure codes are defined."""
        assert MutationFailureCode.BASE_STATE_STALE.value == "BASE_STATE_STALE"
        assert MutationFailureCode.HEAD_MOVED.value == "HEAD_MOVED"
        assert MutationFailureCode.OVERLAPPING_CHANGE.value == "OVERLAPPING_CHANGE"
        assert MutationFailureCode.RESOURCE_LOCKED.value == "RESOURCE_LOCKED"
        assert MutationFailureCode.LOCK_SCOPE_MISMATCH.value == "LOCK_SCOPE_MISMATCH"
        assert MutationFailureCode.CONFIG_FINGERPRINT_CHANGED.value == "CONFIG_FINGERPRINT_CHANGED"
        assert MutationFailureCode.PERMISSION_BASE_MISMATCH.value == "PERMISSION_BASE_MISMATCH"
        assert MutationFailureCode.DUPLICATE_EFFECT_DETECTED.value == "DUPLICATE_EFFECT_DETECTED"
        assert MutationFailureCode.MUTATED_UNRECEIPTED_BLOCKED.value == "MUTATED_UNRECEIPTED_BLOCKED"
        assert MutationFailureCode.IDEMPOTENCY_REPLAY_MISMATCH.value == "IDEMPOTENCY_REPLAY_MISMATCH"


class TestProtectedFields:
    """Tests for protected fields set."""

    def test_critical_fields_protected(self) -> None:
        """Critical security fields are protected."""
        assert "permissions" in PROTECTED_FIELDS
        assert "owner_id" in PROTECTED_FIELDS
        assert "credentials" in PROTECTED_FIELDS
        assert "policy_actions" in PROTECTED_FIELDS
        assert "deployment_target" in PROTECTED_FIELDS
        assert "secret" in PROTECTED_FIELDS
        assert "api_key" in PROTECTED_FIELDS


class TestVerifyScopeIsolation:
    """Tests for scope isolation verification."""

    def test_same_scope_is_isolated(self) -> None:
        """Same scope is considered isolated."""
        scope_a = ResourceScope(owner_id="owner1", organization_id="org1")
        scope_b = ResourceScope(owner_id="owner1", organization_id="org1")

        assert verify_scope_isolation(scope_a, scope_b)

    def test_different_owner_not_isolated(self) -> None:
        """Different owners are not isolated."""
        scope_a = ResourceScope(owner_id="owner1")
        scope_b = ResourceScope(owner_id="owner2")

        assert not verify_scope_isolation(scope_a, scope_b)

    def test_different_org_not_isolated(self) -> None:
        """Different organizations are not isolated even with same owner."""
        scope_a = ResourceScope(owner_id="owner1", organization_id="org1")
        scope_b = ResourceScope(owner_id="owner1", organization_id="org2")

        assert not verify_scope_isolation(scope_a, scope_b)
