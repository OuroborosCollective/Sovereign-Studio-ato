"""Atomic Versioned Mutation Control Layer.

This package provides Compare-and-Swap (CAS), Resource Locks, and Config Receipts
for binding mutations to specific versioned states. The implementation follows
the architecture defined in issue #1119.

Modules:
    versioned_resource: VersionedResourceRef and MutationIntent contracts
    config_snapshot: Canonical configuration snapshot compiler
    cas: Compare-and-Swap primitive and conflict detection
    merge: Deterministic disjoint merge for non-overlapping changes
    resource_lock: Owner/scope-bound resource locks
    mutation_receipt: Atomic mutation receipts with phase tracking

Usage:
    from .mutations import (
        VersionedResourceRef,
        MutationIntent,
        build_versioned_resource_ref,
        build_mutation_intent,
        compare_and_swap,
        merge_disjoint,
        ResourceLock,
        MutationReceipt,
        MutationPhase,
    )

No network, database, filesystem, clock or random access is performed by this
package. It only validates and canonicalizes structured data.
"""

from .versioned_resource import (  # noqa: F401
    RESOURCE_TYPES,
    VersionedResourceError,
    VersionedResourceRef,
    MutationIntent,
    build_versioned_resource_ref,
    build_mutation_intent,
    verify_intent_integrity,
    canonical_sha256,
    canonical_value,
    canonical_bytes,
)

from .config_snapshot import (  # noqa: F401
    ConfigSnapshotError,
    AgentConfigSnapshot,
    build_agent_config_snapshot,
    compile_config_fingerprint,
    verify_config_fingerprint,
    canonical_config_sha256,
    canonical_config_value,
    canonical_config_bytes,
)

from .cas import (  # noqa: F401
    MutationConflict,
    ConflictCode,
    CASDecision,
    CASContext,
    ResourceStore,
    compare_and_swap,
    check_base_head_match,
    check_version_progression,
    detect_overlapping_changes,
    cas_from_github_pr,
    build_conflict_response,
)

from .merge import (  # noqa: F401
    PROTECTED_MUTATION_FIELDS,
    COUPLED_FIELD_PAIRS,
    MergeResult,
    merge_disjoint,
    merge_or_raise,
    apply_mutation_with_merge,
)

from .resource_lock import (  # noqa: F401
    LockMode,
    VALID_LOCK_MODES,
    ResourceLockError,
    ResourceLock,
    LockAcquisitionRequest,
    LockReleaseRequest,
    build_resource_lock,
    validate_lock_release,
    check_resource_locked,
)

from .mutation_receipt import (  # noqa: F401
    MutationPhase,
    ReceiptContractError,
    MutationPhaseError,
    MutationState,
    MutationReceipt,
    build_mutation_receipt,
    verify_idempotency,
    verify_receipt_chain,
    recovery_decision,
)
