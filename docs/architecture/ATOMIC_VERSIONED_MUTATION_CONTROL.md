# Atomic Versioned Mutation Control Layer

**Status:** IMPLEMENTED  
**Revision:** c1acab21  
**Last Updated:** 2026-08-04

## Overview

This document describes the Atomic Versioned Mutation Control Layer for Sovereign Studio ATO, implementing Compare-and-Swap (CAS), Resource Locks, and Config Receipts as specified in issue #1119.

The implementation extends the existing `mutation_evidence_layer.py`, `agent_run_receipts.py`, and `proof_verdict.py` patterns with additional primitives for binding mutations to specific versioned states.

## Architecture

```
read canonical resource
    ↓
BaseStateReceipt
    ↓
construct canonical mutation payload
    ↓
PermissionReceipt binds base hash + payload hash
    ↓
acquire mutation lease or DB row lock
    ↓
read current head again
    ├── head == base → apply
    ├── deterministic non-overlap merge → apply merged payload
    └── conflict → block, no mutation
    ↓
write mutation + new immutable version + receipt atomically
    ↓
release lock/lease
    ↓
canonical target readback
```

## Core Components

### 1. Versioned Resource (`mutations/versioned_resource.py`)

```python
@dataclass(frozen=True, slots=True)
class VersionedResourceRef:
    resource_type: str           # agent_config, capability_manifest, etc.
    resource_id: str
    owner_id: str
    organization_id: str | None
    repository_id: str | None
    workspace_id: str | None
    environment_id: str | None
    version: str
    content_hash: str           # SHA-256 of canonical content

@dataclass(frozen=True, slots=True)
class MutationIntent:
    resource: VersionedResourceRef
    capability_id: str
    canonical_payload: Mapping[str, Any]
    payload_hash: str
    permission_receipt_hash: str
    idempotency_key: str
    expected_effect_hash: str
```

**Supported Resource Types:**
- `agent_config`
- `capability_manifest`
- `tool_assignment`
- `policy_set`
- `integration_plan_state`
- `github_issue`
- `github_pr_metadata`
- `repository_branch`
- `appdeploy_snapshot`
- `deployment_target`
- `database_migration_ownership`

### 2. Config Snapshot (`mutations/config_snapshot.py`)

Canonical, sorted, SHA-256 hashed snapshots of security-relevant configurations.

```python
@dataclass(frozen=True, slots=True)
class AgentConfigSnapshot:
    schema_version: str
    agent_id: str
    owner_id: str
    repository_id: str | None
    environment_id: str
    model_route: Mapping[str, Any]
    credential_identity: Mapping[str, Any] | None  # Redacted
    capability_manifest_hash: str
    policy_set_hash: str
    prompt_layer_hashes: tuple[str, ...]
    tool_contracts: tuple[Mapping[str, Any], ...]
    limits_hash: str
    snapshot_hash: str
```

**Features:**
- Secret fields are redacted (hash only, never raw value)
- Deterministic JSON canonicalization
- Collections sorted before hashing
- Versioned hash algorithm

### 3. Compare-and-Swap (`mutations/cas.py`)

```python
class MutationConflict(RuntimeError):
    """Raised when CAS check fails."""
    code: str                    # BASE_STATE_STALE, HEAD_MOVED, etc.
    expected_hash: str | None
    actual_hash: str | None
    conflict_fields: tuple[str, ...]
    lock_ref: str | None
    allowed_next_step: str       # retry_after_unlock, rebase_and_retry, etc.
```

**Conflict Codes:**
- `BASE_STATE_STALE` - Base version doesn't match current head
- `HEAD_MOVED` - Head version is older than base
- `OVERLAPPING_CHANGE` - Both parties modified same fields
- `RESOURCE_LOCKED` - Resource has an active lock
- `LOCK_SCOPE_MISMATCH` - Lock doesn't cover this scope
- `CONFIG_FINGERPRINT_CHANGED` - Config snapshot changed since intent
- `PERMISSION_BASE_MISMATCH` - Permission bound to different base
- `DUPLICATE_EFFECT_DETECTED` - Same effect already applied
- `MUTATED_UNRECEIPTED_BLOCKED` - Mutation without receipt blocked
- `IDEMPOTENCY_REPLAY_MISMATCH` - Same key with different payload

### 4. Deterministic Merge (`mutations/merge.py`)

Auto-merge only for provably disjoint changes:

```python
def merge_disjoint(base, head, proposed, protected_fields=None) -> MergeResult:
    # Returns merged payload if changes are disjoint
    # Raises MutationConflict if overlap detected
```

**Protected Fields (never auto-merged):**
- Permissions, roles, capabilities, policies
- Ownership (owner_id, organization_id, tenant_id, etc.)
- Credentials and secrets
- Deployment targets
- Migration ownership
- Continuity ledgers

### 5. Resource Locks (`mutations/resource_lock.py`)

```python
class LockMode:
    MUTATION_LOCKED = "mutation_locked"
    OWNER_LOCKED = "owner_locked"
    DEPLOYMENT_FREEZE = "deployment_freeze"
    INCIDENT_FREEZE = "incident_freeze"
    MIGRATION_FREEZE = "migration_freeze"
    READ_ONLY_MAINTENANCE = "read_only_maintenance"

@dataclass(frozen=True, slots=True)
class ResourceLock:
    resource_type: str
    resource_id: str
    lock_mode: str
    reason_code: str
    required_unlock_capability: str
    required_readbacks: tuple[str, ...]
    owner_id: str
    created_by_receipt: str      # Hash of authorizing receipt
    created_at_revision: str
    predecessor_hash: str | None # For lock chain
    expires_at_version: str | None
    lock_hash: str              # Canonical hash
```

**Lock Rules:**
- Lock prevents mutation, not readback
- Unlock requires explicit authorized payload + new receipt
- LLM text alone cannot remove a lock
- Lock inherits to sub-resources that change parent state

### 6. Mutation Receipts (`mutations/mutation_receipt.py`)

```python
class MutationPhase(StrEnum):
    PREPARED = "prepared"
    LOCKED = "locked"
    APPLIED_UNVERIFIED = "applied_unverified"
    VERIFIED = "verified"
    CONFLICTED = "conflicted"
    BLOCKED = "blocked"
    INVALIDATED = "invalidated"

@dataclass(frozen=True, slots=True)
class MutationReceipt:
    mutation_id: str
    idempotency_key: str
    resource_type: str
    resource_id: str
    owner_id: str
    capability_id: str
    base_version: str
    base_content_hash: str
    head_version: str | None
    head_content_hash: str | None
    payload_hash: str
    permission_receipt_hash: str
    phase: str
    outcome: str
    effect_hash: str | None
    previous_receipt_hash: str | None  # For chain
    receipt_hash: str
```

**Atomicity Model:**
1. Same DB transaction for mutation, version, and receipt
2. Transactional outbox with guaranteed delivery
3. External target: prepared intent → mutation → readback → completion

**Crash Recovery:**
```
Receipt PREPARED, Target unchanged → safe retry
Receipt APPLIED_UNVERIFIED, Target changed → continue readback
Target changed, no receipt → block + incident
```

## JSON Schemas

Located in `backend/agent_runtime/contracts/`:

| Schema | Purpose |
|--------|---------|
| `base_state_receipt.v1.schema.json` | Receipt binding mutation to base state |
| `config_snapshot.v1.schema.json` | Agent configuration fingerprint |
| `mutation_conflict.v1.schema.json` | Structured conflict information |
| `resource_lock.v1.schema.json` | Resource lock specification |
| `mutation_receipt.v1.schema.json` | Complete mutation receipt |

## Usage Example

```python
from backend.agent_runtime.mutations import (
    build_versioned_resource_ref,
    build_mutation_intent,
    build_mutation_receipt,
    merge_disjoint,
    MutationPhase,
)

# 1. Read current state and create base reference
base = build_versioned_resource_ref(
    resource_type="agent_config",
    resource_id="agent-123",
    owner_id="owner-456",
    version="5",
    content_hash=canonical_sha256(current_config),
)

# 2. Build mutation intent
intent = build_mutation_intent(
    resource=base,
    capability_id="config.update",
    canonical_payload={"setting": "new_value"},
    permission_receipt_hash=permission.receipt_hash,
    idempotency_key="update-agent-123-001",
    expected_effect_hash=canonical_sha256(new_config),
)

# 3. Check for conflicts
if head.content_hash != base.content_hash:
    result = merge_disjoint(base_state, head_state, proposed)
    if not result.merged:
        raise MutationConflict(...)

# 4. Create receipt
receipt = build_mutation_receipt(
    mutation_id="mutation-001",
    intent=intent,
    phase=MutationPhase.VERIFIED,
    outcome="success",
    head_version="6",
    head_content_hash=canonical_sha256(new_config),
    effect_hash=intent.expected_effect_hash,
)
```

## Security Properties

- **No secret material in receipts** - Only redacted identity hashes
- **Deterministic hashing** - Canonical JSON with sorted keys
- **Hash chaining** - Receipts chain via previous_receipt_hash
- **Capability binding** - Mutations bound to specific capabilities
- **Cross-tenant protection** - CAS checks scope boundaries

## Implementation Notes

- All modules perform no network, database, filesystem, clock, or random access
- Pure validation and canonicalization only
- Real persistence and network access must be implemented in adapters
- See `backend/tests/test_mutation_*.py` for comprehensive tests

## Relationships

- Extends #1113 (Durable Workflow + Permission Receipts)
- Extends #1116 (Immutable Config Fingerprints)
- Provides conflict/invalidation data to #1112 and #1117
- Target effect verification belongs to #1100
- GitHub revision checks must remain compatible with Revision Guardian
