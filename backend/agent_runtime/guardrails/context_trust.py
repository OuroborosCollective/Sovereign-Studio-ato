"""Context Trust State Machine for Sovereign Agent Runtime.

Implements the monotone, restriction-rank-based state transitions defined in Issue #1118.
This module contains no UI, telemetry, or external dependencies. It provides the foundation
for provenance-bound context trust and deterministic tool-chain guardrails.

State transitions are monotonically restrictive within the same context epoch.
A new context epoch must be explicitly created with a hashed DelegationTrustReceipt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class ContextTrust(StrEnum):
    """Context trust states, ordered by restriction rank.

    Transitions are always monotonically restrictive within the same epoch.
    No LLM may upgrade trust state. A new isolated context epoch is required
    for any upward transition.
    """

    TRUSTED_VERIFIED = "trusted_verified"
    OWNER_ASSERTED = "owner_asserted"
    CLEAN_RESTRICTED = "clean_restricted"
    SANITIZED_UNVERIFIED = "sanitized_unverified"
    TAINTED_UNTRUSTED = "tainted_untrusted"
    QUARANTINED = "quarantined"
    BLOCKED = "blocked"
    INVALIDATED = "invalidated"


RESTRICTION_RANK: dict[ContextTrust, int] = {
    ContextTrust.TRUSTED_VERIFIED: 0,
    ContextTrust.OWNER_ASSERTED: 1,
    ContextTrust.CLEAN_RESTRICTED: 2,
    ContextTrust.SANITIZED_UNVERIFIED: 3,
    ContextTrust.TAINTED_UNTRUSTED: 4,
    ContextTrust.QUARANTINED: 5,
    ContextTrust.BLOCKED: 6,
    ContextTrust.INVALIDATED: 7,
}


@dataclass(frozen=True)
class TrustTransitionReceipt:
    """Append-only receipt for trust state transitions.

    This receipt is immutable. No field may be modified after creation.
    Timestamp is metadata only; it never serves as identity.
    """

    schema_version: str = "sovereign.context-trust-transition.v1"
    transition_id: str = ""
    parent_epoch_id: str = ""
    child_epoch_id: str = ""
    owner_id: str = ""
    tenant_id: str | None = None
    repository_id: str | None = None
    workspace_id: str | None = None
    run_id: str = ""
    step_id: str = ""
    from_state: ContextTrust = ContextTrust.CLEAN_RESTRICTED
    to_state: ContextTrust = ContextTrust.CLEAN_RESTRICTED
    trigger_event: str = ""
    predecessor_hash: str = ""
    policy_set_hash: str = ""
    created_at: str = ""


@dataclass
class ContextTrustState:
    """Runtime state for context trust within a single context epoch.

    This is NOT a receipt. It tracks the current state for a run/step.
    State transitions produce TrustTransitionReceipt records.
    """

    epoch_id: str
    owner_id: str
    tenant_id: str | None = None
    repository_id: str | None = None
    workspace_id: str | None = None
    run_id: str = ""
    step_id: str = ""
    current_state: ContextTrust = ContextTrust.CLEAN_RESTRICTED
    predecessor_hash: str = ""
    policy_set_hash: str = ""
    transitions: list[TrustTransitionReceipt] = field(default_factory=list)
    sensitivity_markers: frozenset[str] = field(default_factory=frozenset)
    allowed_capabilities: frozenset[str] = field(default_factory=frozenset)
    forbidden_effect_classes: frozenset[str] = field(default_factory=frozenset)

    def transition(self, new_state: ContextTrust, *, trigger_event: str, predecessor_hash: str = "") -> TrustTransitionReceipt:
        """Transition to a new trust state if permitted by restriction rank.

        Returns a TrustTransitionReceipt. Raises ValueError if the transition
        would upgrade trust (decrease restriction rank).
        """
        from_rank = RESTRICTION_RANK[self.current_state]
        to_rank = RESTRICTION_RANK[new_state]

        if to_rank < from_rank:
            raise ValueError(
                f"Trust upgrade forbidden: {self.current_state} ({from_rank}) -> {new_state} ({to_rank}). "
                "Create a new isolated context epoch instead."
            )

        receipt = TrustTransitionReceipt(
            transition_id=self._make_transition_id(),
            parent_epoch_id=self.epoch_id,
            child_epoch_id=self.epoch_id,
            owner_id=self.owner_id,
            tenant_id=self.tenant_id,
            repository_id=self.repository_id,
            workspace_id=self.workspace_id,
            run_id=self.run_id,
            step_id=self.step_id,
            from_state=self.current_state,
            to_state=new_state,
            trigger_event=trigger_event,
            predecessor_hash=predecessor_hash or self.predecessor_hash,
            policy_set_hash=self.policy_set_hash,
        )

        self.current_state = new_state
        self.transitions.append(receipt)
        self._update_capabilities()

        return receipt

    def _make_transition_id(self) -> str:
        import hashlib
        import time
        payload = f"{self.epoch_id}:{len(self.transitions)}:{time.time_ns()}"
        return hashlib.sha256(payload.encode()).hexdigest()[:24]

    def _update_capabilities(self) -> None:
        """Update effective capabilities based on current trust state."""
        if self.current_state == ContextTrust.TRUSTED_VERIFIED:
            self.forbidden_effect_classes = frozenset()
        elif self.current_state == ContextTrust.OWNER_ASSERTED:
            self.forbidden_effect_classes = frozenset()
        elif self.current_state == ContextTrust.CLEAN_RESTRICTED:
            self.forbidden_effect_classes = frozenset()
        elif self.current_state == ContextTrust.SANITIZED_UNVERIFIED:
            self.forbidden_effect_classes = frozenset({"EXTERNAL_WRITE", "CROSS_TENANT", "CROSS_REPO"})
        elif self.current_state == ContextTrust.TAINTED_UNTRUSTED:
            self.forbidden_effect_classes = frozenset({"EXTERNAL_WRITE", "CROSS_TENANT", "CROSS_REPO", "DELEGATION"})
        elif self.current_state == ContextTrust.QUARANTINED:
            self.forbidden_effect_classes = frozenset({"INSPECT", "READ", "WRITE", "EXTERNAL_WRITE", "DELEGATION"})
        elif self.current_state in {ContextTrust.BLOCKED, ContextTrust.INVALIDATED}:
            self.forbidden_effect_classes = frozenset({"INSPECT", "READ", "WRITE", "EXTERNAL_WRITE", "DELEGATION"})
        else:
            self.forbidden_effect_classes = frozenset({"EXTERNAL_WRITE", "CROSS_TENANT", "CROSS_REPO", "DELEGATION"})


def transition_trust(
    current: ContextTrust,
    candidate: ContextTrust,
) -> ContextTrust:
    """Determine the resulting trust state after a transition.

    This is a pure function that implements the monotone restriction rule.
    Returns the more restrictive of the two states (higher restriction rank wins).
    """
    current_rank = RESTRICTION_RANK[current]
    candidate_rank = RESTRICTION_RANK[candidate]
    return candidate if candidate_rank >= current_rank else current


def initial_trust_state(
    *,
    epoch_id: str,
    owner_id: str,
    tenant_id: str | None = None,
    repository_id: str | None = None,
    workspace_id: str | None = None,
    run_id: str = "",
    step_id: str = "",
) -> ContextTrustState:
    """Create an initial trust state for a new context epoch.

    New epochs always start in CLEAN_RESTRICTED state.
    """
    return ContextTrustState(
        epoch_id=epoch_id,
        owner_id=owner_id,
        tenant_id=tenant_id,
        repository_id=repository_id,
        workspace_id=workspace_id,
        run_id=run_id,
        step_id=step_id,
        current_state=ContextTrust.CLEAN_RESTRICTED,
    )
