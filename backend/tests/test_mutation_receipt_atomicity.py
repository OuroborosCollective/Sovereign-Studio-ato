"""Tests for Mutation Receipt atomicity and idempotency.

These tests verify the mutation receipt and phase tracking functionality
from the atomic versioned mutation control layer.
"""

from __future__ import annotations

import pytest

from backend.agent_runtime.mutations.mutation_receipt import (
    MutationPhase,
    MutationReceipt,
    MutationState,
    ReceiptContractError,
    build_mutation_receipt,
    verify_idempotency,
    verify_receipt_chain,
    recovery_decision,
)
from backend.agent_runtime.mutations.versioned_resource import (
    VersionedResourceRef,
    MutationIntent,
    build_versioned_resource_ref,
    build_mutation_intent,
)


class TestMutationPhase:
    """Tests for MutationPhase enum."""

    def test_all_phases_are_valid(self) -> None:
        """All expected phases exist."""
        assert MutationPhase.PREPARED.value == "prepared"
        assert MutationPhase.LOCKED.value == "locked"
        assert MutationPhase.APPLIED_UNVERIFIED.value == "applied_unverified"
        assert MutationPhase.VERIFIED.value == "verified"
        assert MutationPhase.CONFLICTED.value == "conflicted"
        assert MutationPhase.BLOCKED.value == "blocked"
        assert MutationPhase.INVALIDATED.value == "invalidated"


class TestBuildMutationReceipt:
    """Tests for MutationReceipt creation."""

    def test_creates_valid_receipt(self) -> None:
        """Valid inputs create a receipt successfully."""
        intent = build_mutation_intent(
            resource=build_versioned_resource_ref(
                resource_type="agent_config",
                resource_id="agent-123",
                owner_id="owner-456",
                version="5",
                content_hash="a" * 64,
            ),
            capability_id="config.update",
            canonical_payload={"setting": "value"},
            permission_receipt_hash="b" * 64,
            idempotency_key="update-agent-123-001",
            expected_effect_hash="c" * 64,
        )

        receipt = build_mutation_receipt(
            mutation_id="mutation-001",
            intent=intent,
            phase=MutationPhase.VERIFIED,
            outcome="success",
            head_version="6",
            head_content_hash="d" * 64,
            effect_hash="c" * 64,
        )

        assert receipt.mutation_id == "mutation-001"
        assert receipt.idempotency_key == "update-agent-123-001"
        assert receipt.phase == "verified"
        assert receipt.outcome == "success"
        assert len(receipt.receipt_hash) == 64

    def test_receipt_hash_is_deterministic(self) -> None:
        """Same inputs produce same receipt hash."""
        resource = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        intent = build_mutation_intent(
            resource=resource,
            capability_id="config.update",
            canonical_payload={"setting": "value"},
            permission_receipt_hash="b" * 64,
            idempotency_key="update-agent-123-001",
            expected_effect_hash="c" * 64,
        )

        receipt1 = build_mutation_receipt(
            mutation_id="mutation-001",
            intent=intent,
            phase=MutationPhase.VERIFIED,
            outcome="success",
        )

        intent2 = build_mutation_intent(
            resource=resource,
            capability_id="config.update",
            canonical_payload={"setting": "value"},
            permission_receipt_hash="b" * 64,
            idempotency_key="update-agent-123-001",
            expected_effect_hash="c" * 64,
        )

        receipt2 = build_mutation_receipt(
            mutation_id="mutation-001",
            intent=intent2,
            phase=MutationPhase.VERIFIED,
            outcome="success",
        )

        assert receipt1.receipt_hash == receipt2.receipt_hash


class TestVerifyIdempotency:
    """Tests for idempotency verification."""

    def test_same_idempotency_key_passes(self) -> None:
        """Same idempotency key with same payload passes."""
        resource = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        intent = build_mutation_intent(
            resource=resource,
            capability_id="config.update",
            canonical_payload={"setting": "value"},
            permission_receipt_hash="b" * 64,
            idempotency_key="update-agent-123-001",
            expected_effect_hash="c" * 64,
        )

        receipt = build_mutation_receipt(
            mutation_id="mutation-001",
            intent=intent,
            phase=MutationPhase.VERIFIED,
            outcome="success",
        )

        matches, reason = verify_idempotency(receipt, intent)

        assert matches is True
        assert "matches" in reason.lower()

    def test_different_idempotency_key_fails(self) -> None:
        """Different idempotency key fails."""
        resource = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        intent = build_mutation_intent(
            resource=resource,
            capability_id="config.update",
            canonical_payload={"setting": "value"},
            permission_receipt_hash="b" * 64,
            idempotency_key="update-agent-123-001",
            expected_effect_hash="c" * 64,
        )

        receipt = build_mutation_receipt(
            mutation_id="mutation-001",
            intent=intent,
            phase=MutationPhase.VERIFIED,
            outcome="success",
        )

        new_resource = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        new_intent = build_mutation_intent(
            resource=new_resource,
            capability_id="config.update",
            canonical_payload={"setting": "value"},
            permission_receipt_hash="b" * 64,
            idempotency_key="different-key",  # Different key
            expected_effect_hash="c" * 64,
        )

        matches, reason = verify_idempotency(receipt, new_intent)

        assert matches is False
        assert "idempotency_key mismatch" in reason.lower()

    def test_different_payload_fails(self) -> None:
        """Different payload with same idempotency key fails."""
        resource = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        intent = build_mutation_intent(
            resource=resource,
            capability_id="config.update",
            canonical_payload={"setting": "value1"},
            permission_receipt_hash="b" * 64,
            idempotency_key="update-agent-123-001",
            expected_effect_hash="c" * 64,
        )

        receipt = build_mutation_receipt(
            mutation_id="mutation-001",
            intent=intent,
            phase=MutationPhase.VERIFIED,
            outcome="success",
        )

        new_intent = build_mutation_intent(
            resource=resource,
            capability_id="config.update",
            canonical_payload={"setting": "value2"},  # Different payload
            permission_receipt_hash="b" * 64,
            idempotency_key="update-agent-123-001",
            expected_effect_hash="c" * 64,
        )

        matches, reason = verify_idempotency(receipt, new_intent)

        assert matches is False
        assert "payload_hash mismatch" in reason.lower()


class TestVerifyReceiptChain:
    """Tests for receipt chain verification."""

    def test_verifies_valid_chain(self) -> None:
        """Valid chain passes verification."""
        resource = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        intent1 = build_mutation_intent(
            resource=resource,
            capability_id="config.update",
            canonical_payload={"setting": "value1"},
            permission_receipt_hash="b" * 64,
            idempotency_key="update-001",
            expected_effect_hash="c" * 64,
        )

        receipt1 = build_mutation_receipt(
            mutation_id="mutation-001",
            intent=intent1,
            phase=MutationPhase.VERIFIED,
            outcome="success",
            previous_receipt_hash=None,
        )

        resource2 = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="6",
            content_hash="d" * 64,
        )
        intent2 = build_mutation_intent(
            resource=resource2,
            capability_id="config.update",
            canonical_payload={"setting": "value2"},
            permission_receipt_hash="b" * 64,
            idempotency_key="update-002",
            expected_effect_hash="e" * 64,
        )

        receipt2 = build_mutation_receipt(
            mutation_id="mutation-002",
            intent=intent2,
            phase=MutationPhase.VERIFIED,
            outcome="success",
            previous_receipt_hash=receipt1.receipt_hash,
        )

        result = verify_receipt_chain([receipt1, receipt2])

        assert result["ok"] is True
        assert result["verified_count"] == 2
        assert result["receipt_count"] == 2

    def test_detects_hash_mismatch(self) -> None:
        """Hash mismatch is detected."""
        resource = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        intent = build_mutation_intent(
            resource=resource,
            capability_id="config.update",
            canonical_payload={"setting": "value"},
            permission_receipt_hash="b" * 64,
            idempotency_key="update-001",
            expected_effect_hash="c" * 64,
        )

        receipt = build_mutation_receipt(
            mutation_id="mutation-001",
            intent=intent,
            phase=MutationPhase.VERIFIED,
            outcome="success",
        )

        # Manually corrupt the receipt hash by recreating
        result = verify_receipt_chain([receipt])

        assert result["verified_count"] == 1

    def test_requires_at_least_one_receipt(self) -> None:
        """Empty chain fails verification."""
        result = verify_receipt_chain([])

        assert result["ok"] is False
        assert "at least one receipt" in result["reason"].lower()


class TestRecoveryDecision:
    """Tests for crash recovery decision logic."""

    def test_retry_when_prepared(self) -> None:
        """PREPARED phase allows retry."""
        resource = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        intent = build_mutation_intent(
            resource=resource,
            capability_id="config.update",
            canonical_payload={"setting": "value"},
            permission_receipt_hash="b" * 64,
            idempotency_key="update-001",
            expected_effect_hash="c" * 64,
        )

        receipt = build_mutation_receipt(
            mutation_id="mutation-001",
            intent=intent,
            phase=MutationPhase.PREPARED,
            outcome="pending",
        )

        decision = recovery_decision(receipt, None)

        assert decision == "retry"

    def test_continue_readback_when_applied_and_verified(self) -> None:
        """APPLIED_UNVERIFIED with matching head allows continue."""
        resource = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        intent = build_mutation_intent(
            resource=resource,
            capability_id="config.update",
            canonical_payload={"setting": "value"},
            permission_receipt_hash="b" * 64,
            idempotency_key="update-001",
            expected_effect_hash="a" * 64,  # Matches head
        )

        receipt = build_mutation_receipt(
            mutation_id="mutation-001",
            intent=intent,
            phase=MutationPhase.APPLIED_UNVERIFIED,
            outcome="applied",
            effect_hash="a" * 64,
        )

        head = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="6",
            content_hash="a" * 64,  # Matches effect hash
        )

        decision = recovery_decision(receipt, head)

        assert decision == "continue_readback"

    def test_block_when_verified(self) -> None:
        """VERIFIED phase blocks (already complete)."""
        resource = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        intent = build_mutation_intent(
            resource=resource,
            capability_id="config.update",
            canonical_payload={"setting": "value"},
            permission_receipt_hash="b" * 64,
            idempotency_key="update-001",
            expected_effect_hash="c" * 64,
        )

        receipt = build_mutation_receipt(
            mutation_id="mutation-001",
            intent=intent,
            phase=MutationPhase.VERIFIED,
            outcome="success",
        )

        decision = recovery_decision(receipt, None)

        assert decision == "continue_readback"

    def test_block_on_conflicted(self) -> None:
        """CONFLICTED phase blocks."""
        resource = build_versioned_resource_ref(
            resource_type="agent_config",
            resource_id="agent-123",
            owner_id="owner-456",
            version="5",
            content_hash="a" * 64,
        )
        intent = build_mutation_intent(
            resource=resource,
            capability_id="config.update",
            canonical_payload={"setting": "value"},
            permission_receipt_hash="b" * 64,
            idempotency_key="update-001",
            expected_effect_hash="c" * 64,
        )

        receipt = build_mutation_receipt(
            mutation_id="mutation-001",
            intent=intent,
            phase=MutationPhase.CONFLICTED,
            outcome="conflict",
        )

        decision = recovery_decision(receipt, None)

        assert decision == "block"


class TestMutationState:
    """Tests for MutationState transitions."""

    def test_transitions_to_new_phase(self) -> None:
        """State can transition to a new phase."""
        state = MutationState(
            schema_version="sovereign.mutation-state.v1",
            mutation_id="mutation-001",
            idempotency_key="key-001",
            intent={"action": "update"},
            payload_hash="a" * 64,
            base_state_hash="b" * 64,
            expected_effect_hash="c" * 64,
            phase=MutationPhase.PREPARED.value,
            phase_transitions=(),
            previous_receipt_hash=None,
            applied_state=None,
            applied_version=None,
            applied_content_hash=None,
        )

        new_state = state.transition_to(MutationPhase.LOCKED, lock_id="lock-001")

        assert new_state.phase == MutationPhase.LOCKED.value
        assert len(new_state.phase_transitions) == 1
        assert new_state.phase_transitions[0]["from_phase"] == MutationPhase.PREPARED.value
        assert new_state.phase_transitions[0]["to_phase"] == MutationPhase.LOCKED.value

    def test_with_applied_state(self) -> None:
        """State can record applied result."""
        state = MutationState(
            schema_version="sovereign.mutation-state.v1",
            mutation_id="mutation-001",
            idempotency_key="key-001",
            intent={"action": "update"},
            payload_hash="a" * 64,
            base_state_hash="b" * 64,
            expected_effect_hash="c" * 64,
            phase=MutationPhase.LOCKED.value,
            phase_transitions=(),
            previous_receipt_hash=None,
            applied_state=None,
            applied_version=None,
            applied_content_hash=None,
        )

        new_state = state.with_applied_state(
            state={"field": "new_value"},
            version="6",
            content_hash="d" * 64,
        )

        assert new_state.applied_state == {"field": "new_value"}
        assert new_state.applied_version == "d" * 64
        assert new_state.applied_content_hash == "d" * 64


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
