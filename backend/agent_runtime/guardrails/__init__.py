"""Guardrails module for context trust and tool-chain policy enforcement.

This module implements the Sovereign context trust state machine and related
guardrails per Issue #1118. All receipts are append-only and revision-bound.
"""

from .context_trust import (
    ContextTrust,
    RESTRICTION_RANK,
    transition_trust,
    initial_trust_state,
)

__all__ = [
    "ContextTrust",
    "RESTRICTION_RANK",
    "transition_trust",
    "initial_trust_state",
]
