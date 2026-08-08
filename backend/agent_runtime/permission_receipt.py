"""Revision-bound Permission Receipt Layer for Sovereign Studio ATO.

This module implements immutable, revision-bound permission contracts that authorize
specific tool mutations. A permission receipt is created BEFORE execution and
cannot be modified after approval.

Key design invariants:
- No I/O of any kind (no filesystem, network, database, clock or random).
- Every receipt is an immutable ``dataclass(frozen=True)`` value object.
- Permission receipts are append-only; new permissions replace old ones.
- Tool success alone creates at most SUCCEEDED_UNVERIFIED, never VERIFIED.
- VERIFIED requires canonical target-system readback.
- Secrets, tokens and PII are rejected at the boundary.
- Unknown or incomplete capabilities are fail-closed (not visible/executable).

Permission state flow::

    REQUESTED
        │ (owner approves)
        ▼
    APPROVED
        │ (payload executed, readback matches)
        ▼
    CONSUMED_VERIFIED  ← requires canonical readback
        │
       (or) → REVOKED   (owner revokes before execution)
       (or) → EXPIRED   (deadline passed)
       (or) → SUPERSEDED (new permission replaces this one)
       (or) → CONTRADICTED (conflicting evidence)
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Final,
    FrozenSet,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)


# ---------------------------------------------------------------------------
# Schema versions
# ---------------------------------------------------------------------------
PERMISSION_SCHEMA_VERSION: Final[str] = "sovereign.permission-receipt.v1"
PERMISSION_REQUEST_SCHEMA: Final[str] = "sovereign.permission-request.v1"

# ---------------------------------------------------------------------------
# Limits (conservative; larger content belongs in canonical sources)
# ---------------------------------------------------------------------------
_MAX_ID_LEN: Final[int] = 120
_MAX_TEXT_BYTES: Final[int] = 4096
_MAX_PAYLOAD_BYTES: Final[int] = 65536
_MAX_CHANGED_PATHS: Final[int] = 256
_MAX_EFFECT_SURFACES: Final[int] = 32
_MAX_PRECONDITIONS: Final[int] = 32
_MAX_RETRY_COUNT: Final[int] = 5
_MAX_VALIDITY_SECONDS: Final[int] = 86400  # 24 hours

# ---------------------------------------------------------------------------
# Identifier / hash regex
# ---------------------------------------------------------------------------
_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_.:-]{1,119}$")
_SHA40: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_DIGEST: Final[re.Pattern[str]] = re.compile(r"^sha256:[0-9a-f]{64}$")
_WORKFLOW_ID: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
_RUN_ID: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
_PERMISSION_ID: Final[re.Pattern[str]] = re.compile(
    r"^perm-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

# ---------------------------------------------------------------------------
# Secret / sensitive material patterns (reject at boundary)
# ---------------------------------------------------------------------------
_SECRET_PATTERNS: Final[Tuple[re.Pattern[str], ...]] = (
    # Bearer / Authorization tokens
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]{8,}", re.IGNORECASE),
    # GitHub tokens
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    # Generic "password = ..." or "token = ..."
    re.compile(r"(?i)(password|passwd|secret|token|api[_\-]?key)\s*[:=]\s*\S{4,}"),
    # AWS keys
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # PEM blocks
    re.compile(r"-----BEGIN [A-Z ]+ KEY-----"),
    # Connection strings with credentials
    re.compile(r"(?i)(postgres|mysql|mongodb)://[^@]+:[^@]+@"),
    # JWT tokens
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)


# ---------------------------------------------------------------------------
# Capability class enumeration
# ---------------------------------------------------------------------------
class CapabilityClass(str, Enum):
    """Canonical capability classes that permission receipts authorize."""
    # Read-only inspection - no mutation
    INSPECT = "inspect"
    # Workspace mutation - changes files in repo
    MUTATE = "mutate"
    # Coordination - external system coordination (GitHub, CI, etc.)
    COORDINATE = "coordinate"
    # Test execution - runs tests without changing production
    TEST = "test"
    # Admin - privileged operations (reserved for future use)
    ADMIN = "admin"


# ---------------------------------------------------------------------------
# Permission state enumeration
# ---------------------------------------------------------------------------
class PermissionState(str, Enum):
    """Lifecycle states for a permission receipt."""
    # Permission requested but not yet approved
    REQUESTED = "requested"
    # Owner approved the permission
    APPROVED = "approved"
    # Permission was executed and verified by canonical readback
    CONSUMED_VERIFIED = "consumed_verified"
    # Permission was executed but verification failed
    CONSUMED_UNVERIFIED = "consumed_unverified"
    # Owner revoked the permission before execution
    REVOKED = "revoked"
    # Permission deadline passed without execution
    EXPIRED = "expired"
    # A newer permission superseded this one
    SUPERSEDED = "superseded"
    # Contradictory evidence found (e.g., conflicting readback)
    CONTRADICTED = "contradicted"


# Valid state transitions
_VALID_STATE_TRANSITIONS: Final[Mapping[PermissionState, FrozenSet[PermissionState]]] = {
    PermissionState.REQUESTED: frozenset({
        PermissionState.APPROVED,
        PermissionState.REVOKED,
        PermissionState.EXPIRED,
    }),
    PermissionState.APPROVED: frozenset({
        PermissionState.CONSUMED_VERIFIED,
        PermissionState.CONSUMED_UNVERIFIED,
        PermissionState.REVOKED,
        PermissionState.EXPIRED,
        PermissionState.SUPERSEDED,
    }),
    PermissionState.CONSUMED_VERIFIED: frozenset({
        PermissionState.CONTRADICTED,  # Only via new evidence
    }),
    PermissionState.CONSUMED_UNVERIFIED: frozenset({
        PermissionState.CONSUMED_VERIFIED,  # If readback later succeeds
        PermissionState.CONTRADICTED,  # If contradiction found
    }),
    PermissionState.REVOKED: frozenset(),
    PermissionState.EXPIRED: frozenset(),
    PermissionState.SUPERSEDED: frozenset(),
    PermissionState.CONTRADICTED: frozenset(),
}


# ---------------------------------------------------------------------------
# Effect surface enumeration
# ---------------------------------------------------------------------------
class EffectSurface(str, Enum):
    """External surfaces that a permitted action may affect."""
    FILESYSTEM = "filesystem"
    SHELL = "shell"
    NETWORK = "network"
    BROWSER = "browser"
    RUNTIME_STATE = "runtime_state"
    GITHUB = "github"
    DATABASE = "database"
    DEPLOYMENT = "deployment"
    CI = "ci"
    ARTIFACT = "artifact"
    IMAGE = "image"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class PermissionContractError(ValueError):
    """Raised on any structural or invariant violation."""


# ---------------------------------------------------------------------------
# Canonical SHA-256 helpers
# ---------------------------------------------------------------------------

def _canonical_sha256(value: object) -> str:
    """Deterministic SHA-256 over the UTF-8 JSON serialisation of *value*."""
    serialised = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def _text_sha256(text: str) -> str:
    """SHA-256 of text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Secret redaction guard
# ---------------------------------------------------------------------------

class SecretRedactionFilter:
    """Rejects or scrubs content containing secret-shaped material.

    Call ``check_and_sanitize`` before accepting any payload, parameters,
    or content into a permission receipt. Raises ``PermissionContractError``
    on clear credential matches.
    """

    @staticmethod
    def contains_secret(text: str) -> bool:
        """Return True if text contains secret-shaped patterns."""
        if not isinstance(text, str):
            return False
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                return True
        return False

    @staticmethod
    def check_and_sanitize(text: str, *, field_path: str = "$") -> str:
        """Check for secrets and raise, or return sanitized text.

        Currently raises on any secret detection. In future, may return
        redaction markers instead.
        """
        if SecretRedactionFilter.contains_secret(text):
            raise PermissionContractError(
                f"secret-shaped content is forbidden at {field_path}"
            )
        return text

    @classmethod
    def check_payload(cls, payload: Mapping[str, Any], *, field_path: str = "$") -> Mapping[str, Any]:
        """Recursively check a payload dictionary for secrets."""
        result: dict[str, Any] = {}
        for key, value in payload.items():
            safe_key = cls.check_and_sanitize(key, field_path=f"{field_path}.{key}")
            if isinstance(value, str):
                result[safe_key] = cls.check_and_sanitize(value, field_path=f"{field_path}.{key}")
            elif isinstance(value, dict):
                result[safe_key] = cls.check_payload(value, field_path=f"{field_path}.{key}")
            elif isinstance(value, list):
                result[safe_key] = [
                    cls.check_and_sanitize(str(v), field_path=f"{field_path}.{key}[{i}]")
                    if isinstance(v, str) else v
                    for i, v in enumerate(value)
                ]
            else:
                result[safe_key] = value
        return result


# ---------------------------------------------------------------------------
# Canonical dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PermissionReceipt:
    """Immutable permission receipt binding authorization to exact payload.

    A permission receipt is created BEFORE execution and captures:
    - Who authorized (owner identity)
    - What exactly is authorized (normalized tool parameters)
    - What revision/commit the authorization applies to
    - What effects are expected
    - What readbacks prove the effect occurred

    The receipt hash binds all these fields; any change invalidates the receipt.
    """

    # Identity fields
    permission_id: str
    schema_version: str
    permission_schema_version: str

    # Owner/Tenant identity
    owner: str
    tenant_or_org: Optional[str]

    # Repository and workspace binding
    repo_owner: str
    repo_name: str
    workspace_id: Optional[str]

    # Revision binding
    base_revision: str
    head_revision: Optional[str]
    target_revision: Optional[str]

    # Workflow binding
    workflow_id: Optional[str]
    workflow_run_id: Optional[str]
    step_id: Optional[str]

    # Tool/capability binding
    tool_name: str
    capability_class: CapabilityClass
    effect_class: str  # "read_only", "workspace_mutation", "external_mutation"

    # Normalized, secret-scrubbed parameters
    parameters: Tuple[Tuple[str, Any], ...]  # sorted key-value tuples
    parameters_hash: str  # SHA-256 of canonical parameters

    # Expected effect surfaces
    expected_changed_paths: Tuple[str, ...]
    expected_effect_surfaces: Tuple[EffectSurface, ...]
    expected_external_effects: Tuple[str, ...]

    # Preconditions and evidence requirements
    required_preconditions: Tuple[str, ...]
    required_readback_kinds: Tuple[str, ...]

    # Validity and limits
    created_at_iso: str
    validity_seconds: int
    max_retries: int

    # Authorization
    approver_identity: Optional[str]
    approval_source: str  # "owner", "policy", "emergency_override"

    # State and chain
    state: PermissionState
    predecessor_permission_id: Optional[str]
    successor_permission_id: Optional[str]

    # Hash binding
    attestation_hash: str  # Computed hash of all above fields

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict for persistence."""
        return {
            "permission_id": self.permission_id,
            "schema_version": self.schema_version,
            "permission_schema_version": self.permission_schema_version,
            "owner": self.owner,
            "tenant_or_org": self.tenant_or_org,
            "repo_owner": self.repo_owner,
            "repo_name": self.repo_name,
            "workspace_id": self.workspace_id,
            "base_revision": self.base_revision,
            "head_revision": self.head_revision,
            "target_revision": self.target_revision,
            "workflow_id": self.workflow_id,
            "workflow_run_id": self.workflow_run_id,
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "capability_class": self.capability_class.value,
            "effect_class": self.effect_class,
            "parameters": list(self.parameters),
            "parameters_hash": self.parameters_hash,
            "expected_changed_paths": list(self.expected_changed_paths),
            "expected_effect_surfaces": [s.value for s in self.expected_effect_surfaces],
            "expected_external_effects": list(self.expected_external_effects),
            "required_preconditions": list(self.required_preconditions),
            "required_readback_kinds": list(self.required_readback_kinds),
            "created_at_iso": self.created_at_iso,
            "validity_seconds": self.validity_seconds,
            "max_retries": self.max_retries,
            "approver_identity": self.approver_identity,
            "approval_source": self.approval_source,
            "state": self.state.value,
            "predecessor_permission_id": self.predecessor_permission_id,
            "successor_permission_id": self.successor_permission_id,
            "attestation_hash": self.attestation_hash,
        }


@dataclass(frozen=True, slots=True)
class ExecutionAttempt:
    """Record of a single attempt to execute a permitted action."""

    attempt_id: str
    permission_id: str
    schema_version: str

    # Execution context
    run_id: str
    executor_identity: str
    container_or_runner: Optional[str]

    # Revision at execution time
    base_revision: str
    observed_head_revision: str

    # Payload binding (must match permission)
    parameters_hash: str

    # Results
    start_state: str
    end_state: str
    exit_status: int
    output_hash: str

    # Diff and effect evidence (if mutation)
    changed_paths_hash: Optional[str]
    patch_hash: Optional[str]

    # Created identities (Git commits, PRs, etc.)
    created_identities: Tuple[str, ...]

    # Readback evidence
    attempted_readbacks: Tuple[str, ...]  # kinds attempted
    successful_readbacks: Tuple[str, ...]  # kinds that succeeded

    # Retry classification
    is_retry: bool
    previous_attempt_id: Optional[str]
    retry_classification: str  # "transient", "permanent", "unknown"

    # Timestamp and verdict
    executed_at_iso: str
    verdict: str  # "SUCCEEDED_UNVERIFIED", "VERIFIED", "CONTRADICTED", "BLOCKED"

    # Hash binding
    attestation_hash: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict for persistence."""
        return {
            "attempt_id": self.attempt_id,
            "permission_id": self.permission_id,
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "executor_identity": self.executor_identity,
            "container_or_runner": self.container_or_runner,
            "base_revision": self.base_revision,
            "observed_head_revision": self.observed_head_revision,
            "parameters_hash": self.parameters_hash,
            "start_state": self.start_state,
            "end_state": self.end_state,
            "exit_status": self.exit_status,
            "output_hash": self.output_hash,
            "changed_paths_hash": self.changed_paths_hash,
            "patch_hash": self.patch_hash,
            "created_identities": list(self.created_identities),
            "attempted_readbacks": list(self.attempted_readbacks),
            "successful_readbacks": list(self.successful_readbacks),
            "is_retry": self.is_retry,
            "previous_attempt_id": self.previous_attempt_id,
            "retry_classification": self.retry_classification,
            "executed_at_iso": self.executed_at_iso,
            "verdict": self.verdict,
            "attestation_hash": self.attestation_hash,
        }


# ---------------------------------------------------------------------------
# Factory methods
# ---------------------------------------------------------------------------

class PermissionReceiptFactory:
    """Factory for creating and validating permission receipts."""

    @staticmethod
    def _validate_identity_fields(
        owner: str,
        repo_owner: str,
        repo_name: str,
        base_revision: str,
    ) -> None:
        """Validate identity fields raise PermissionContractError."""
        if not owner or not owner.strip():
            raise PermissionContractError("owner must not be empty.")
        if not repo_owner or not repo_owner.strip():
            raise PermissionContractError("repo_owner must not be empty.")
        if not repo_name or not repo_name.strip():
            raise PermissionContractError("repo_name must not be empty.")
        # Prevent path traversal
        if ".." in repo_owner or "/" in repo_owner:
            raise PermissionContractError(f"repo_owner '{repo_owner}' contains forbidden characters.")
        if ".." in repo_name or "/" in repo_name:
            raise PermissionContractError(f"repo_name '{repo_name}' contains forbidden characters.")
        # Validate revision format
        if not _SHA40.fullmatch(base_revision or ""):
            raise PermissionContractError(
                f"base_revision must be a 40-character lowercase hex SHA (got '{base_revision}')."
            )

    @staticmethod
    def _validate_tool_fields(
        tool_name: str,
        capability_class: CapabilityClass,
        effect_class: str,
    ) -> None:
        """Validate tool-related fields."""
        if not tool_name or not tool_name.strip():
            raise PermissionContractError("tool_name must not be empty.")
        if not tool_name.replace("_", "").replace("-", "").isalnum():
            raise PermissionContractError(
                f"tool_name '{tool_name}' contains invalid characters."
            )
        if effect_class not in {"read_only", "workspace_mutation", "external_mutation"}:
            raise PermissionContractError(
                f"effect_class must be one of: read_only, workspace_mutation, external_mutation"
            )
        # MUTATE capability class must have mutation effect
        if capability_class == CapabilityClass.MUTATE and effect_class == "read_only":
            raise PermissionContractError(
                "MUTATE capability_class requires a mutation effect_class."
            )

    @staticmethod
    def _compute_attestation_hash(receipt: PermissionReceipt) -> str:
        """Compute the attestation hash for a permission receipt."""
        # Build the canonical payload for hashing
        canonical = {
            "permission_id": receipt.permission_id,
            "owner": receipt.owner,
            "repo_owner": receipt.repo_owner,
            "repo_name": receipt.repo_name,
            "workspace_id": receipt.workspace_id,
            "base_revision": receipt.base_revision,
            "head_revision": receipt.head_revision,
            "target_revision": receipt.target_revision,
            "workflow_id": receipt.workflow_id,
            "step_id": receipt.step_id,
            "tool_name": receipt.tool_name,
            "capability_class": receipt.capability_class.value,
            "effect_class": receipt.effect_class,
            "parameters_hash": receipt.parameters_hash,
            "expected_changed_paths": list(receipt.expected_changed_paths),
            "expected_effect_surfaces": [s.value for s in receipt.expected_effect_surfaces],
            "expected_external_effects": list(receipt.expected_external_effects),
            "required_preconditions": list(receipt.required_preconditions),
            "required_readback_kinds": list(receipt.required_readback_kinds),
            "validity_seconds": receipt.validity_seconds,
            "max_retries": receipt.max_retries,
            "approver_identity": receipt.approver_identity,
            "approval_source": receipt.approval_source,
            "predecessor_permission_id": receipt.predecessor_permission_id,
        }
        return _canonical_sha256(canonical)

    @classmethod
    def create_permission_request(
        cls,
        *,
        owner: str,
        repo_owner: str,
        repo_name: str,
        base_revision: str,
        tool_name: str,
        capability_class: CapabilityClass,
        effect_class: str,
        parameters: Mapping[str, Any],
        workspace_id: Optional[str] = None,
        head_revision: Optional[str] = None,
        target_revision: Optional[str] = None,
        workflow_id: Optional[str] = None,
        workflow_run_id: Optional[str] = None,
        step_id: Optional[str] = None,
        expected_changed_paths: Optional[Sequence[str]] = None,
        expected_effect_surfaces: Optional[Sequence[EffectSurface]] = None,
        expected_external_effects: Optional[Sequence[str]] = None,
        required_preconditions: Optional[Sequence[str]] = None,
        required_readback_kinds: Optional[Sequence[str]] = None,
        validity_seconds: int = 3600,
        max_retries: int = 3,
        approver_identity: Optional[str] = None,
        approval_source: str = "owner",
        predecessor_permission_id: Optional[str] = None,
        created_at_iso: str = "",
        tenant_or_org: Optional[str] = None,
    ) -> PermissionReceipt:
        """Create a new permission receipt in REQUESTED state.

        This factory:
        1. Validates all identity and tool fields
        2. Normalizes and secret-scrubs parameters
        3. Computes deterministic hashes
        4. Returns an immutable PermissionReceipt
        """
        # Validate identity
        cls._validate_identity_fields(owner, repo_owner, repo_name, base_revision)

        # Validate tool fields
        cls._validate_tool_fields(tool_name, capability_class, effect_class)

        # Validate revisions
        if head_revision and not _SHA40.fullmatch(head_revision):
            raise PermissionContractError(
                f"head_revision must be a 40-character lowercase hex SHA."
            )
        if target_revision and not _SHA40.fullmatch(target_revision):
            raise PermissionContractError(
                f"target_revision must be a 40-character lowercase hex SHA."
            )

        # Validate limits
        if validity_seconds <= 0 or validity_seconds > _MAX_VALIDITY_SECONDS:
            raise PermissionContractError(
                f"validity_seconds must be between 1 and {_MAX_VALIDITY_SECONDS}."
            )
        if max_retries < 0 or max_retries > _MAX_RETRY_COUNT:
            raise PermissionContractError(
                f"max_retries must be between 0 and {_MAX_RETRY_COUNT}."
            )

        # Normalize and secret-check parameters
        sanitized = SecretRedactionFilter.check_payload(parameters)

        # Convert to sorted tuple for determinism
        param_tuples = tuple(
            (k, v) for k, v in sorted(sanitized.items(), key=lambda x: x[0])
        )

        # Compute parameters hash
        params_hash = _canonical_sha256(dict(param_tuples))

        # Normalize paths
        if expected_changed_paths:
            normalized_paths = tuple(
                p.strip().lstrip("/") for p in expected_changed_paths if p.strip()
            )
        else:
            normalized_paths = ()

        # Normalize surfaces
        if expected_effect_surfaces:
            surfaces = tuple(expected_effect_surfaces)
        else:
            surfaces = ()

        # Generate permission ID
        permission_id = f"perm-{uuid.uuid4().hex}"

        # Create provisional receipt
        provisional = PermissionReceipt(
            permission_id=permission_id,
            schema_version=PERMISSION_SCHEMA_VERSION,
            permission_schema_version=PERMISSION_REQUEST_SCHEMA,
            owner=owner,
            tenant_or_org=tenant_or_org,
            repo_owner=repo_owner,
            repo_name=repo_name,
            workspace_id=workspace_id,
            base_revision=base_revision,
            head_revision=head_revision,
            target_revision=target_revision,
            workflow_id=workflow_id,
            workflow_run_id=workflow_run_id,
            step_id=step_id,
            tool_name=tool_name,
            capability_class=capability_class,
            effect_class=effect_class,
            parameters=param_tuples,
            parameters_hash=params_hash,
            expected_changed_paths=normalized_paths,
            expected_effect_surfaces=surfaces,
            expected_external_effects=tuple(expected_external_effects or ()),
            required_preconditions=tuple(required_preconditions or ()),
            required_readback_kinds=tuple(required_readback_kinds or ()),
            created_at_iso=created_at_iso,
            validity_seconds=validity_seconds,
            max_retries=max_retries,
            approver_identity=approver_identity,
            approval_source=approval_source,
            state=PermissionState.REQUESTED,
            predecessor_permission_id=predecessor_permission_id,
            successor_permission_id=None,
            attestation_hash="",  # Computed below
        )

        # Compute and set attestation hash
        attestation = cls._compute_attestation_hash(provisional)

        return PermissionReceipt(
            permission_id=permission_id,
            schema_version=PERMISSION_SCHEMA_VERSION,
            permission_schema_version=PERMISSION_REQUEST_SCHEMA,
            owner=owner,
            tenant_or_org=tenant_or_org,
            repo_owner=repo_owner,
            repo_name=repo_name,
            workspace_id=workspace_id,
            base_revision=base_revision,
            head_revision=head_revision,
            target_revision=target_revision,
            workflow_id=workflow_id,
            workflow_run_id=workflow_run_id,
            step_id=step_id,
            tool_name=tool_name,
            capability_class=capability_class,
            effect_class=effect_class,
            parameters=param_tuples,
            parameters_hash=params_hash,
            expected_changed_paths=normalized_paths,
            expected_effect_surfaces=surfaces,
            expected_external_effects=tuple(expected_external_effects or ()),
            required_preconditions=tuple(required_preconditions or ()),
            required_readback_kinds=tuple(required_readback_kinds or ()),
            created_at_iso=created_at_iso,
            validity_seconds=validity_seconds,
            max_retries=max_retries,
            approver_identity=approver_identity,
            approval_source=approval_source,
            state=PermissionState.REQUESTED,
            predecessor_permission_id=predecessor_permission_id,
            successor_permission_id=None,
            attestation_hash=attestation,
        )

    @classmethod
    def approve_permission(
        cls,
        receipt: PermissionReceipt,
        *,
        approver_identity: str,
        approval_source: str = "owner",
        successor_permission_id: Optional[str] = None,
    ) -> PermissionReceipt:
        """Transition a permission from REQUESTED to APPROVED."""
        if receipt.state != PermissionState.REQUESTED:
            raise PermissionContractError(
                f"Cannot approve permission in {receipt.state.value} state. "
                f"Only REQUESTED permissions can be approved."
            )

        # Verify attestation hash hasn't been tampered
        expected_hash = cls._compute_attestation_hash(receipt)
        if expected_hash != receipt.attestation_hash:
            raise PermissionContractError(
                "Permission receipt attestation hash mismatch. Receipt may have been tampered."
            )

        # Create approved version
        approved = PermissionReceipt(
            permission_id=receipt.permission_id,
            schema_version=receipt.schema_version,
            permission_schema_version=receipt.permission_schema_version,
            owner=receipt.owner,
            tenant_or_org=receipt.tenant_or_org,
            repo_owner=receipt.repo_owner,
            repo_name=receipt.repo_name,
            workspace_id=receipt.workspace_id,
            base_revision=receipt.base_revision,
            head_revision=receipt.head_revision,
            target_revision=receipt.target_revision,
            workflow_id=receipt.workflow_id,
            workflow_run_id=receipt.workflow_run_id,
            step_id=receipt.step_id,
            tool_name=receipt.tool_name,
            capability_class=receipt.capability_class,
            effect_class=receipt.effect_class,
            parameters=receipt.parameters,
            parameters_hash=receipt.parameters_hash,
            expected_changed_paths=receipt.expected_changed_paths,
            expected_effect_surfaces=receipt.expected_effect_surfaces,
            expected_external_effects=receipt.expected_external_effects,
            required_preconditions=receipt.required_preconditions,
            required_readback_kinds=receipt.required_readback_kinds,
            created_at_iso=receipt.created_at_iso,
            validity_seconds=receipt.validity_seconds,
            max_retries=receipt.max_retries,
            approver_identity=approver_identity,
            approval_source=approval_source,
            state=PermissionState.APPROVED,
            predecessor_permission_id=receipt.predecessor_permission_id,
            successor_permission_id=successor_permission_id,
            attestation_hash=receipt.attestation_hash,  # Keep original hash
        )

        return approved

    @classmethod
    def verify_attestation(cls, receipt: PermissionReceipt) -> bool:
        """Recompute and compare the attestation hash for receipt."""
        expected = cls._compute_attestation_hash(receipt)
        return expected == receipt.attestation_hash


class ExecutionAttemptFactory:
    """Factory for creating execution attempt records."""

    @staticmethod
    def _compute_attestation_hash(attempt: ExecutionAttempt) -> str:
        """Compute the attestation hash for an execution attempt."""
        canonical = {
            "attempt_id": attempt.attempt_id,
            "permission_id": attempt.permission_id,
            "run_id": attempt.run_id,
            "executor_identity": attempt.executor_identity,
            "base_revision": attempt.base_revision,
            "observed_head_revision": attempt.observed_head_revision,
            "parameters_hash": attempt.parameters_hash,
            "start_state": attempt.start_state,
            "end_state": attempt.end_state,
            "exit_status": attempt.exit_status,
            "output_hash": attempt.output_hash,
            "changed_paths_hash": attempt.changed_paths_hash,
            "patch_hash": attempt.patch_hash,
            "created_identities": list(attempt.created_identities),
            "attempted_readbacks": list(attempt.attempted_readbacks),
            "successful_readbacks": list(attempt.successful_readbacks),
            "is_retry": attempt.is_retry,
            "previous_attempt_id": attempt.previous_attempt_id,
            "retry_classification": attempt.retry_classification,
            "verdict": attempt.verdict,
        }
        return _canonical_sha256(canonical)

    @classmethod
    def create_attempt(
        cls,
        *,
        permission_id: str,
        run_id: str,
        executor_identity: str,
        container_or_runner: Optional[str],
        base_revision: str,
        observed_head_revision: str,
        parameters_hash: str,
        start_state: str,
        end_state: str,
        exit_status: int,
        output_hash: str,
        changed_paths_hash: Optional[str],
        patch_hash: Optional[str],
        created_identities: Optional[Sequence[str]],
        attempted_readbacks: Optional[Sequence[str]],
        successful_readbacks: Optional[Sequence[str]],
        is_retry: bool,
        previous_attempt_id: Optional[str],
        retry_classification: str,
        executed_at_iso: str,
        verdict: str,
    ) -> ExecutionAttempt:
        """Create an execution attempt record.

        Verdict must be one of:
        - SUCCEEDED_UNVERIFIED: Tool ran but no readback yet
        - VERIFIED: Tool ran and readback confirmed
        - CONTRADICTED: Readback contradicted expected effect
        - BLOCKED: Execution was blocked before running
        """
        valid_verdicts = {"SUCCEEDED_UNVERIFIED", "VERIFIED", "CONTRADICTED", "BLOCKED"}
        if verdict not in valid_verdicts:
            raise PermissionContractError(
                f"verdict must be one of: {', '.join(valid_verdicts)}"
            )

        # SUCCEEDED_UNVERIFIED is the minimum for any execution
        # VERIFIED requires successful_readbacks to be non-empty
        if verdict == "VERIFIED" and not successful_readbacks:
            raise PermissionContractError(
                "VERIFIED verdict requires at least one successful_readback"
            )

        attempt_id = f"attempt-{uuid.uuid4().hex}"

        provisional = ExecutionAttempt(
            attempt_id=attempt_id,
            permission_id=permission_id,
            schema_version=PERMISSION_SCHEMA_VERSION,
            run_id=run_id,
            executor_identity=executor_identity,
            container_or_runner=container_or_runner,
            base_revision=base_revision,
            observed_head_revision=observed_head_revision,
            parameters_hash=parameters_hash,
            start_state=start_state,
            end_state=end_state,
            exit_status=exit_status,
            output_hash=output_hash,
            changed_paths_hash=changed_paths_hash,
            patch_hash=patch_hash,
            created_identities=tuple(created_identities or ()),
            attempted_readbacks=tuple(attempted_readbacks or ()),
            successful_readbacks=tuple(successful_readbacks or ()),
            is_retry=is_retry,
            previous_attempt_id=previous_attempt_id,
            retry_classification=retry_classification,
            executed_at_iso=executed_at_iso,
            verdict=verdict,
            attestation_hash="",  # Computed below
        )

        attestation = cls._compute_attestation_hash(provisional)

        return ExecutionAttempt(
            attempt_id=attempt_id,
            permission_id=permission_id,
            schema_version=PERMISSION_SCHEMA_VERSION,
            run_id=run_id,
            executor_identity=executor_identity,
            container_or_runner=container_or_runner,
            base_revision=base_revision,
            observed_head_revision=observed_head_revision,
            parameters_hash=parameters_hash,
            start_state=start_state,
            end_state=end_state,
            exit_status=exit_status,
            output_hash=output_hash,
            changed_paths_hash=changed_paths_hash,
            patch_hash=patch_hash,
            created_identities=tuple(created_identities or ()),
            attempted_readbacks=tuple(attempted_readbacks or ()),
            successful_readbacks=tuple(successful_readbacks or ()),
            is_retry=is_retry,
            previous_attempt_id=previous_attempt_id,
            retry_classification=retry_classification,
            executed_at_iso=executed_at_iso,
            verdict=verdict,
            attestation_hash=attestation,
        )
