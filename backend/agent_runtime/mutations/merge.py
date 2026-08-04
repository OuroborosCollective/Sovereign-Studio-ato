"""Deterministic disjoint merge for non-overlapping configuration changes.

This module provides merge logic for cases where two actors modify
different, non-coupled fields of the same resource. Changes are only
auto-merged if they are provably disjoint and no semantic coupling exists.

The module performs no network, database, filesystem, clock or random access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Mapping

from .cas import MutationConflict, ConflictCode


# Fields that are never auto-merged - they require explicit authorization
PROTECTED_MUTATION_FIELDS: Final[frozenset[str]] = frozenset({
    # Permissions and authorization
    "permissions",
    "permission",
    "roles",
    "role",
    "capabilities",
    "capability",
    "policies",
    "policy",
    "policy_actions",
    # Ownership and scope
    "owner_id",
    "ownerid",
    "organization_id",
    "organizationid",
    "tenant_id",
    "tenantid",
    "repository_id",
    "repositoryid",
    "workspace_id",
    "workspaceid",
    "environment_id",
    "environmentid",
    # Credentials and secrets
    "credentials",
    "credential",
    "api_key",
    "apikey",
    "api_key_id",
    "secret",
    "token",
    # Deployment and migration
    "deployment_target",
    "deployment_target_id",
    "migration_owner",
    "migration_ownership",
    # Continuity and ledger
    "continuity_ledger",
    "append_only",
})

# Field pairs that are semantically coupled and cannot be auto-merged
COUPLED_FIELD_PAIRS: Final[frozenset[frozenset[str]]] = frozenset({
    frozenset({"model", "provider"}),  # Model and provider must change together
    frozenset({"base_url", "endpoint"}),  # URL and endpoint are coupled
    frozenset({"timeout", "retry"}),  # Timeout and retry policy are coupled
    frozenset({"memory", "context"}),  # Memory and context are coupled
})


@dataclass(frozen=True, slots=True)
class MergeResult:
    """Result of a merge attempt."""

    merged: bool
    merged_payload: Mapping[str, Any] | None
    conflict_fields: tuple[str, ...]
    protected_conflict: bool
    coupled_conflict: bool
    reason: str


def _compute_changed_fields(
    base: Mapping[str, Any],
    current: Mapping[str, Any],
) -> frozenset[str]:
    """Compute the set of fields that differ between base and current."""

    all_keys = set(base.keys()) | set(current.keys())
    changed: set[str] = set()

    for key in all_keys:
        base_val = base.get(key)
        current_val = current.get(key)
        if base_val != current_val:
            changed.add(key)

    return frozenset(changed)


def _check_field_coupling(changed_head: frozenset[str], changed_proposed: frozenset[str]) -> bool:
    """Check if changes involve semantically coupled fields."""

    for coupled_pair in COUPLED_FIELD_PAIRS:
        head_in_pair = changed_head & coupled_pair
        proposed_in_pair = changed_proposed & coupled_pair

        # If both changes touch the same coupled pair, it's a conflict
        if head_in_pair and proposed_in_pair:
            return True

    return False


def merge_disjoint(
    base: Mapping[str, Any],
    head: Mapping[str, Any],
    proposed: Mapping[str, Any],
    protected_fields: frozenset[str] | None = None,
) -> MergeResult:
    """Attempt to merge head and proposed changes against base.

    Merge is only allowed if:
    1. Changes are provably disjoint (no overlapping modified fields)
    2. No protected fields are in the overlap
    3. No semantically coupled fields are modified by both parties

    Args:
        base: The base state that both head and proposed diverged from
        head: The current head state (after other actor's changes)
        proposed: The proposed changes to merge
        protected_fields: Additional protected fields beyond the default set

    Returns:
        MergeResult indicating success or failure with details
    """

    if protected_fields is None:
        protected_fields = PROTECTED_MUTATION_FIELDS
    else:
        protected_fields = frozenset(protected_fields) | PROTECTED_MUTATION_FIELDS

    # Compute changed fields
    changed_head = _compute_changed_fields(base, head)
    changed_proposed = _compute_changed_fields(base, proposed)

    # Check for overlap
    overlap = changed_head & changed_proposed

    if not overlap:
        # No overlap - can merge
        merged = {**head, **{k: proposed[k] for k in changed_proposed}}
        return MergeResult(
            merged=True,
            merged_payload=merged,
            conflict_fields=(),
            protected_conflict=False,
            coupled_conflict=False,
            reason="Changes are disjoint - auto-merge successful",
        )

    # Check for protected field overlap
    protected_overlap = overlap & protected_fields
    if protected_overlap:
        return MergeResult(
            merged=False,
            merged_payload=None,
            conflict_fields=tuple(sorted(overlap)),
            protected_conflict=True,
            coupled_conflict=False,
            reason=f"Protected fields overlap: {sorted(protected_overlap)}",
        )

    # Check for semantic coupling
    if _check_field_coupling(changed_head, changed_proposed):
        return MergeResult(
            merged=False,
            merged_payload=None,
            conflict_fields=tuple(sorted(overlap)),
            protected_conflict=False,
            coupled_conflict=True,
            reason="Changes involve semantically coupled fields",
        )

    # Non-protected overlap
    return MergeResult(
        merged=False,
        merged_payload=None,
        conflict_fields=tuple(sorted(overlap)),
        protected_conflict=False,
        coupled_conflict=False,
        reason="Non-overlapping changes required for auto-merge",
    )


def merge_or_raise(
    base: Mapping[str, Any],
    head: Mapping[str, Any],
    proposed: Mapping[str, Any],
    protected_fields: frozenset[str] | None = None,
) -> Mapping[str, Any]:
    """Merge or raise MutationConflict if merge is not possible.

    This is a convenience wrapper that raises MutationConflict with
    appropriate details when merge fails.
    """

    result = merge_disjoint(base, head, proposed, protected_fields)

    if result.merged:
        return result.merged_payload

    if result.protected_conflict:
        raise MutationConflict(
            code=ConflictCode.OVERLAPPING_CHANGE,
            message=f"Protected fields overlap: {result.conflict_fields}",
            expected_hash=None,
            actual_hash=None,
            conflict_fields=result.conflict_fields,
            allowed_next_step="manual_merge_required",
        )

    if result.coupled_conflict:
        raise MutationConflict(
            code=ConflictCode.OVERLAPPING_CHANGE,
            message=f"Semantically coupled fields overlap: {result.conflict_fields}",
            expected_hash=None,
            actual_hash=None,
            conflict_fields=result.conflict_fields,
            allowed_next_step="manual_merge_required",
        )

    raise MutationConflict(
        code=ConflictCode.OVERLAPPING_CHANGE,
        message=f"Overlapping changes in fields: {result.conflict_fields}",
        expected_hash=None,
        actual_hash=None,
        conflict_fields=result.conflict_fields,
        allowed_next_step="rebase_and_retry",
    )


def apply_mutation_with_merge(
    base: Mapping[str, Any],
    head: Mapping[str, Any],
    proposed: Mapping[str, Any],
    protected_fields: frozenset[str] | None = None,
    strict: bool = True,
) -> tuple[Mapping[str, Any], bool]:
    """Apply mutation with optional auto-merge.

    Args:
        base: The base state
        head: The current head state
        proposed: The proposed changes
        protected_fields: Protected field set
        strict: If True, raise on conflict; if False, return conflict info

    Returns:
        Tuple of (result_state, was_merged)
        If strict=True and merge fails, raises MutationConflict
    """

    result = merge_disjoint(base, head, proposed, protected_fields)

    if result.merged:
        return result.merged_payload, True

    if strict:
        merge_or_raise(base, head, proposed, protected_fields)
        # Never reached due to raise
        return base, False  # type: ignore[unreachable]

    # Return head as-is with merge=False
    return head, False


__all__ = [
    "PROTECTED_MUTATION_FIELDS",
    "COUPLED_FIELD_PAIRS",
    "MergeResult",
    "merge_disjoint",
    "merge_or_raise",
    "apply_mutation_with_merge",
]
