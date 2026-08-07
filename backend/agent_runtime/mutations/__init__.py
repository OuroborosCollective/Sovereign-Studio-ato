"""Atomic versioned mutation control layer for Sovereign Studio ATO.

This package provides Compare-and-Swap (CAS) primitives, resource locks,
versioned resource contracts, and config snapshots for deterministic
mutation control.

Based on MVCC, append-only ledger, and content-addressed design principles.
No enterprise-marked Archestra surfaces are included.

Architecture:
    mutations/
    ├── __init__.py         # Package exports
    ├── cas.py              # Compare-and-swap primitives
    ├── resource_lock.py    # Resource lock primitives
    ├── versioned_resource.py  # VersionedResource contracts
    └── config_snapshot.py  # Config fingerprinting

Referenced by:
    - Issue #1119: Atomic Versioned Mutation Control
    - Issue #1113: Durable Workflow and Permission Receipt Layer
    - Issue #1116: Harness-Neutral Execution Envelopes
"""

from .cas import (
    CASDecision,
    CASResult,
    check_cas_prerequisites,
    compare_and_swap,
    detect_field_overlap,
    merge_disjoint_fields,
)
from .config_snapshot import (
    AgentConfigSnapshot,
    compute_config_fingerprint,
)
from .resource_lock import (
    LOCK_MODE_MUTATION_LOCKED,
    LOCK_MODE_OWNER_LOCKED,
    LOCK_MODE_DEPLOYMENT_FREEZE,
    LOCK_MODE_INCIDENT_FREEZE,
    LOCK_MODE_MIGRATION_FREEZE,
    LOCK_MODE_READ_ONLY_MAINTENANCE,
    ResourceLock,
    ResourceLockError,
)
from .versioned_resource import (
    MutationIntent,
    ResourceScope,
    VersionedResource,
    VersionedResourceRef,
)

__all__ = [
    # CAS primitives
    "CASDecision",
    "CASResult",
    "check_cas_prerequisites",
    "compare_and_swap",
    "detect_field_overlap",
    "merge_disjoint_fields",
    # Config snapshot
    "AgentConfigSnapshot",
    "compute_config_fingerprint",
    # Resource locks
    "LOCK_MODE_MUTATION_LOCKED",
    "LOCK_MODE_OWNER_LOCKED",
    "LOCK_MODE_DEPLOYMENT_FREEZE",
    "LOCK_MODE_INCIDENT_FREEZE",
    "LOCK_MODE_MIGRATION_FREEZE",
    "LOCK_MODE_READ_ONLY_MAINTENANCE",
    "ResourceLock",
    "ResourceLockError",
    # Versioned resource
    "MutationIntent",
    "ResourceScope",
    "VersionedResource",
    "VersionedResourceRef",
]
