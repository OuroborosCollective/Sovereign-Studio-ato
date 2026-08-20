"""Revision-bound durable workflow and permission receipt contracts.

This module is deliberately transport-free.  Server routes and workers must create
these immutable contracts from server-resolved identities, persist their canonical
bodies append-only, and pass independent target readbacks back to this state
machine.  A tool return value can never create ``VERIFIED`` on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


WORKFLOW_SCHEMA_VERSION = "sovereign.durable-workflow.v1"
STEP_SCHEMA_VERSION = "sovereign.workflow-step.v1"
TRANSITION_SCHEMA_VERSION = "sovereign.workflow-transition.v1"
PERMISSION_SCHEMA_VERSION = "sovereign.permission-receipt.v1"
EXECUTION_SCHEMA_VERSION = "sovereign.execution-receipt.v1"
_ZERO_SHA256 = "0" * 64
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{1,119}$")
_SECRET_KEY = re.compile(r"(?i)(password|passwd|secret|token|authorization|api[_-]?key|cookie|private[_-]?key)")
_SECRET_VALUE = re.compile(r"(?i)(bearer\s+\S{8,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]+ KEY-----)")


class DurableWorkflowError(ValueError):
    """Raised when a workflow, permission or receipt violates its contract."""


class WorkflowState(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    WAITING_FOR_PERMISSION = "WAITING_FOR_PERMISSION"
    AUTHORIZED = "AUTHORIZED"
    RUNNING = "RUNNING"
    WAITING_FOR_EXTERNAL_EVIDENCE = "WAITING_FOR_EXTERNAL_EVIDENCE"
    SUCCEEDED_UNVERIFIED = "SUCCEEDED_UNVERIFIED"
    VERIFIED = "VERIFIED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"
    BLOCKED = "BLOCKED"
    CONTRADICTED = "CONTRADICTED"
    INVALIDATED = "INVALIDATED"
    CANCELLED = "CANCELLED"


class StepKind(str, Enum):
    READBACK = "READBACK"
    DIAGNOSE = "DIAGNOSE"
    PLAN_TRANSITION = "PLAN_TRANSITION"
    TOOL_MUTATION = "TOOL_MUTATION"
    TEST = "TEST"
    CI_WAIT = "CI_WAIT"
    ARTIFACT_WAIT = "ARTIFACT_WAIT"
    DEPLOYMENT_WAIT = "DEPLOYMENT_WAIT"
    RUNTIME_VERIFY = "RUNTIME_VERIFY"
    PERMISSION_WAIT = "PERMISSION_WAIT"
    OWNER_BLOCKED = "OWNER_BLOCKED"
    COMPLETE = "COMPLETE"
    INVALIDATED = "INVALIDATED"


class PermissionDecision(str, Enum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    SUPERSEDED = "SUPERSEDED"


class ExecutionVerdict(str, Enum):
    SUCCEEDED_UNVERIFIED = "SUCCEEDED_UNVERIFIED"
    VERIFIED = "VERIFIED"
    CONTRADICTED = "CONTRADICTED"
    INVALIDATED = "INVALIDATED"
    BLOCKED = "BLOCKED"
    RETRYABLE_FAILURE = "RETRYABLE_FAILURE"


class ReadbackVerdict(str, Enum):
    VERIFIED = "VERIFIED"
    CONTRADICTED = "CONTRADICTED"
    INVALIDATED = "INVALIDATED"


def _canonical(value: Any, *, path: str = "$") -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        raise DurableWorkflowError(f"floating-point value is forbidden at {path}")
    if isinstance(value, str):
        if _SECRET_VALUE.search(value):
            raise DurableWorkflowError(f"secret-shaped value is forbidden at {path}")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise DurableWorkflowError(f"invalid object key at {path}")
            if _SECRET_KEY.search(key):
                raise DurableWorkflowError(f"secret-shaped key is forbidden at {path}.{key}")
            result[key] = _canonical(item, path=f"{path}.{key}")
        return result
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_canonical(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    raise DurableWorkflowError(f"unsupported value at {path}")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(_canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _require_sha40(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA40.fullmatch(normalized):
        raise DurableWorkflowError(f"{label} must be a SHA-40")
    return normalized


def _require_sha64(value: str, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA64.fullmatch(normalized):
        raise DurableWorkflowError(f"{label} must be a SHA-256")
    return normalized


def _require_identifier(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(normalized):
        raise DurableWorkflowError(f"{label} is invalid")
    return normalized


@dataclass(frozen=True, slots=True)
class WorkflowBinding:
    workflow_run_id: str
    workflow_definition_hash: str
    owner_identity: str
    tenant_or_org_identity: str
    repository_identity: str
    workspace_id: str
    base_revision: str
    head_revision: str | None = None
    merge_revision: str | None = None
    integration_id: str | None = None
    issue_number: int | None = None
    pull_request_number: int | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.workflow_run_id, "workflow_run_id")
        _require_sha64(self.workflow_definition_hash, "workflow_definition_hash")
        for field_name in ("owner_identity", "tenant_or_org_identity", "repository_identity", "workspace_id"):
            if not str(getattr(self, field_name) or "").strip():
                raise DurableWorkflowError(f"{field_name} must not be empty")
        _require_sha40(self.base_revision, "base_revision")
        for field_name in ("head_revision", "merge_revision"):
            value = getattr(self, field_name)
            if value is not None:
                _require_sha40(value, field_name)
        for value in (self.issue_number, self.pull_request_number):
            if value is not None and (not isinstance(value, int) or value <= 0):
                raise DurableWorkflowError("issue and PR references must be positive integers")

    def canonical(self) -> dict[str, Any]:
        return {
            "workflow_run_id": self.workflow_run_id,
            "workflow_definition_hash": self.workflow_definition_hash,
            "owner_identity": self.owner_identity,
            "tenant_or_org_identity": self.tenant_or_org_identity,
            "repository_identity": self.repository_identity,
            "workspace_id": self.workspace_id,
            "base_revision": self.base_revision,
            "head_revision": self.head_revision,
            "merge_revision": self.merge_revision,
            "integration_id": self.integration_id,
            "issue_number": self.issue_number,
            "pull_request_number": self.pull_request_number,
        }


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    step_id: str
    kind: StepKind
    allowed_from: tuple[WorkflowState, ...]
    allowed_to: tuple[WorkflowState, ...]
    permission_required: bool
    capability: str
    timeout_seconds: int
    max_attempts: int
    idempotency_key: str
    required_readback_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.step_id, "step_id")
        _require_identifier(self.capability, "capability")
        _require_identifier(self.idempotency_key, "idempotency_key")
        if not self.allowed_from or not self.allowed_to:
            raise DurableWorkflowError("workflow step must declare allowed transitions")
        if self.timeout_seconds <= 0 or self.max_attempts < 0:
            raise DurableWorkflowError("workflow step timeout/attempt bounds are invalid")
        if self.kind == StepKind.TOOL_MUTATION and not self.permission_required:
            raise DurableWorkflowError("mutating workflow steps always require permission")
        if self.kind == StepKind.TOOL_MUTATION and not self.required_readback_kinds:
            raise DurableWorkflowError("mutating workflow steps require an authoritative readback kind")

    def canonical(self) -> dict[str, Any]:
        return {
            "schema_version": STEP_SCHEMA_VERSION,
            "step_id": self.step_id,
            "kind": self.kind.value,
            "allowed_from": [state.value for state in self.allowed_from],
            "allowed_to": [state.value for state in self.allowed_to],
            "permission_required": self.permission_required,
            "capability": self.capability,
            "timeout_seconds": self.timeout_seconds,
            "max_attempts": self.max_attempts,
            "idempotency_key": self.idempotency_key,
            "required_readback_kinds": list(self.required_readback_kinds),
        }


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    workflow_id: str
    schema_version: str
    steps: tuple[WorkflowStep, ...]
    definition_hash: str

    @classmethod
    def create(cls, *, workflow_id: str, steps: Sequence[WorkflowStep]) -> "WorkflowDefinition":
        _require_identifier(workflow_id, "workflow_id")
        materialized = tuple(steps)
        if not materialized or len({step.step_id for step in materialized}) != len(materialized):
            raise DurableWorkflowError("workflow definition must contain uniquely named steps")
        body = {"schema_version": WORKFLOW_SCHEMA_VERSION, "workflow_id": workflow_id, "steps": [step.canonical() for step in materialized]}
        return cls(workflow_id, WORKFLOW_SCHEMA_VERSION, materialized, canonical_sha256(body))

    def step(self, step_id: str) -> WorkflowStep:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        raise DurableWorkflowError("unknown workflow step")


@dataclass(frozen=True, slots=True)
class PermissionReceipt:
    permission_id: str
    binding: WorkflowBinding
    step_id: str
    tool_name: str
    capability: str
    normalized_parameters: Mapping[str, Any]
    parameters_hash: str
    expected_changed_paths: tuple[str, ...]
    required_readback_kinds: tuple[str, ...]
    valid_until_epoch: int
    max_attempts: int
    decision: PermissionDecision
    approver_identity: str | None
    approval_source: str | None
    predecessor_receipt_hash: str
    receipt_hash: str

    def canonical(self) -> dict[str, Any]:
        return {
            "schema_version": PERMISSION_SCHEMA_VERSION,
            "permission_id": self.permission_id,
            "binding": self.binding.canonical(),
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "capability": self.capability,
            "normalized_parameters": _canonical(self.normalized_parameters),
            "parameters_hash": self.parameters_hash,
            "expected_changed_paths": list(self.expected_changed_paths),
            "required_readback_kinds": list(self.required_readback_kinds),
            "valid_until_epoch": self.valid_until_epoch,
            "max_attempts": self.max_attempts,
            "decision": self.decision.value,
            "approver_identity": self.approver_identity,
            "approval_source": self.approval_source,
            "predecessor_receipt_hash": self.predecessor_receipt_hash,
        }

    def verify(self) -> bool:
        return canonical_sha256(self.canonical()) == self.receipt_hash


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    execution_id: str
    permission_receipt_hash: str
    binding: WorkflowBinding
    step_id: str
    attempt_number: int
    parameters_hash: str
    observed_revision: str
    idempotency_key: str
    exit_status: int
    output_hash: str
    changed_paths: tuple[str, ...]
    patch_hash: str
    verdict: ExecutionVerdict
    readback_kind: str | None
    readback_hash: str | None
    previous_execution_hash: str
    execution_hash: str

    def canonical(self) -> dict[str, Any]:
        return {
            "schema_version": EXECUTION_SCHEMA_VERSION,
            "execution_id": self.execution_id,
            "permission_receipt_hash": self.permission_receipt_hash,
            "binding": self.binding.canonical(),
            "step_id": self.step_id,
            "attempt_number": self.attempt_number,
            "parameters_hash": self.parameters_hash,
            "observed_revision": self.observed_revision,
            "idempotency_key": self.idempotency_key,
            "exit_status": self.exit_status,
            "output_hash": self.output_hash,
            "changed_paths": list(self.changed_paths),
            "patch_hash": self.patch_hash,
            "verdict": self.verdict.value,
            "readback_kind": self.readback_kind,
            "readback_hash": self.readback_hash,
            "previous_execution_hash": self.previous_execution_hash,
        }

    def verify(self) -> bool:
        return canonical_sha256(self.canonical()) == self.execution_hash


@dataclass(frozen=True, slots=True)
class CanonicalReadback:
    source: str
    repository_identity: str
    observed_revision: str
    kind: str
    result_hash: str
    verdict: ReadbackVerdict

    def __post_init__(self) -> None:
        _require_identifier(self.source, "readback source")
        _require_identifier(self.kind, "readback kind")
        _require_sha40(self.observed_revision, "readback revision")
        _require_sha64(self.result_hash, "readback result hash")


@dataclass(frozen=True, slots=True)
class WorkflowSnapshot:
    binding: WorkflowBinding
    state: WorkflowState
    current_step_id: str
    attempt_number: int
    last_permission_hash: str
    last_execution_hash: str


def create_permission_request(
    *,
    binding: WorkflowBinding,
    definition: WorkflowDefinition,
    step_id: str,
    tool_name: str,
    parameters: Mapping[str, Any],
    expected_changed_paths: Sequence[str],
    valid_until_epoch: int,
    max_attempts: int,
    predecessor_receipt_hash: str = _ZERO_SHA256,
) -> PermissionReceipt:
    if binding.workflow_definition_hash != definition.definition_hash:
        raise DurableWorkflowError("workflow binding does not match its definition hash")
    step = definition.step(step_id)
    if not step.permission_required:
        raise DurableWorkflowError("read-only step must not mint a permission receipt")
    if max_attempts <= 0 or max_attempts > step.max_attempts:
        raise DurableWorkflowError("permission attempt budget exceeds workflow step budget")
    if valid_until_epoch <= 0:
        raise DurableWorkflowError("permission expiry must be sourced from a trusted runtime")
    normalized_parameters = _canonical(parameters)
    parameter_hash = canonical_sha256(normalized_parameters)
    normalized_paths = tuple(sorted({str(path).strip().lstrip("/") for path in expected_changed_paths if str(path).strip()}))
    if any(path.startswith("../") or path == ".." for path in normalized_paths):
        raise DurableWorkflowError("expected changed path escapes workspace")
    predecessor = _require_sha64(predecessor_receipt_hash, "predecessor receipt hash")
    identity = canonical_sha256({"binding": binding.canonical(), "step_id": step_id, "tool_name": tool_name, "parameters_hash": parameter_hash, "predecessor": predecessor})
    receipt = PermissionReceipt(
        permission_id=f"perm-{identity[:32]}",
        binding=binding,
        step_id=step_id,
        tool_name=_require_identifier(tool_name, "tool name"),
        capability=step.capability,
        normalized_parameters=normalized_parameters,
        parameters_hash=parameter_hash,
        expected_changed_paths=normalized_paths,
        required_readback_kinds=step.required_readback_kinds,
        valid_until_epoch=valid_until_epoch,
        max_attempts=max_attempts,
        decision=PermissionDecision.REQUESTED,
        approver_identity=None,
        approval_source=None,
        predecessor_receipt_hash=predecessor,
        receipt_hash="",
    )
    return replace(receipt, receipt_hash=canonical_sha256(receipt.canonical()))


def approve_permission(receipt: PermissionReceipt, *, approver_identity: str, approval_source: str, observed_epoch: int) -> PermissionReceipt:
    if not receipt.verify():
        raise DurableWorkflowError("permission receipt hash is contradicted")
    if receipt.decision != PermissionDecision.REQUESTED:
        raise DurableWorkflowError("only requested permissions can be approved")
    if observed_epoch > receipt.valid_until_epoch:
        raise DurableWorkflowError("expired permission cannot be approved")
    approved = replace(
        receipt,
        decision=PermissionDecision.APPROVED,
        approver_identity=_require_identifier(approver_identity, "approver identity"),
        approval_source=_require_identifier(approval_source, "approval source"),
        receipt_hash="",
    )
    return replace(approved, receipt_hash=canonical_sha256(approved.canonical()))


def create_execution_receipt(
    *,
    permission: PermissionReceipt,
    definition: WorkflowDefinition,
    observed_epoch: int,
    observed_revision: str,
    parameters: Mapping[str, Any],
    attempt_number: int,
    exit_status: int,
    output_hash: str,
    changed_paths: Sequence[str],
    patch_hash: str,
    previous_execution_hash: str = _ZERO_SHA256,
) -> tuple[ExecutionReceipt, WorkflowState]:
    if not permission.verify() or permission.decision != PermissionDecision.APPROVED:
        raise DurableWorkflowError("execution requires a verified approved permission")
    if observed_epoch > permission.valid_until_epoch:
        raise DurableWorkflowError("permission has expired")
    step = definition.step(permission.step_id)
    if attempt_number <= 0 or attempt_number > permission.max_attempts or attempt_number > step.max_attempts:
        raise DurableWorkflowError("execution attempt exceeds its bound")
    if canonical_sha256(parameters) != permission.parameters_hash:
        raise DurableWorkflowError("execution parameters differ from approved payload")
    expected_revision = permission.binding.head_revision or permission.binding.base_revision
    if _require_sha40(observed_revision, "observed revision") != expected_revision:
        raise DurableWorkflowError("execution revision differs from permission binding")
    normalized_paths = tuple(sorted({str(path).strip().lstrip("/") for path in changed_paths if str(path).strip()}))
    if step.kind == StepKind.TOOL_MUTATION and tuple(normalized_paths) != permission.expected_changed_paths:
        raise DurableWorkflowError("execution changed paths differ from approved effect surface")
    previous = _require_sha64(previous_execution_hash, "previous execution hash")
    verdict = ExecutionVerdict.SUCCEEDED_UNVERIFIED if exit_status == 0 else ExecutionVerdict.RETRYABLE_FAILURE
    execution_identity = canonical_sha256({"permission": permission.receipt_hash, "attempt": attempt_number, "previous": previous, "output": output_hash, "patch": patch_hash})
    receipt = ExecutionReceipt(
        execution_id=f"exec-{execution_identity[:32]}",
        permission_receipt_hash=permission.receipt_hash,
        binding=permission.binding,
        step_id=permission.step_id,
        attempt_number=attempt_number,
        parameters_hash=permission.parameters_hash,
        observed_revision=expected_revision,
        idempotency_key=step.idempotency_key,
        exit_status=exit_status,
        output_hash=_require_sha64(output_hash, "output hash"),
        changed_paths=normalized_paths,
        patch_hash=_require_sha64(patch_hash, "patch hash"),
        verdict=verdict,
        readback_kind=None,
        readback_hash=None,
        previous_execution_hash=previous,
        execution_hash="",
    )
    receipt = replace(receipt, execution_hash=canonical_sha256(receipt.canonical()))
    return receipt, (WorkflowState.SUCCEEDED_UNVERIFIED if verdict == ExecutionVerdict.SUCCEEDED_UNVERIFIED else WorkflowState.RETRYABLE_FAILURE)


def apply_canonical_readback(
    execution: ExecutionReceipt,
    *,
    permission: PermissionReceipt,
    readback: CanonicalReadback,
) -> tuple[ExecutionReceipt, WorkflowState]:
    if not execution.verify() or not permission.verify():
        raise DurableWorkflowError("receipt hash is contradicted")
    if execution.permission_receipt_hash != permission.receipt_hash:
        raise DurableWorkflowError("execution is not bound to the supplied permission")
    if execution.verdict != ExecutionVerdict.SUCCEEDED_UNVERIFIED:
        raise DurableWorkflowError("only successful-unverified executions await readback")
    if readback.repository_identity != permission.binding.repository_identity:
        raise DurableWorkflowError("readback repository differs from permission binding")
    expected_revision = permission.binding.head_revision or permission.binding.base_revision
    if readback.observed_revision != expected_revision:
        raise DurableWorkflowError("readback revision differs from permission binding")
    if readback.kind not in permission.required_readback_kinds:
        raise DurableWorkflowError("readback kind was not authorized for this step")
    target_verdict = {
        ReadbackVerdict.VERIFIED: ExecutionVerdict.VERIFIED,
        ReadbackVerdict.CONTRADICTED: ExecutionVerdict.CONTRADICTED,
        ReadbackVerdict.INVALIDATED: ExecutionVerdict.INVALIDATED,
    }[readback.verdict]
    updated = replace(
        execution,
        verdict=target_verdict,
        readback_kind=readback.kind,
        readback_hash=readback.result_hash,
        execution_hash="",
    )
    updated = replace(updated, execution_hash=canonical_sha256(updated.canonical()))
    return updated, {
        ExecutionVerdict.VERIFIED: WorkflowState.VERIFIED,
        ExecutionVerdict.CONTRADICTED: WorkflowState.CONTRADICTED,
        ExecutionVerdict.INVALIDATED: WorkflowState.INVALIDATED,
    }[target_verdict]


def resume_snapshot(
    *,
    snapshot: WorkflowSnapshot,
    execution: ExecutionReceipt | None,
    external_readback: CanonicalReadback | None,
) -> WorkflowState:
    """Fail closed on resume: an external effect may never be blindly replayed."""
    if execution is None:
        return WorkflowState.READY
    if not execution.verify() or execution.binding != snapshot.binding:
        return WorkflowState.CONTRADICTED
    if execution.verdict == ExecutionVerdict.SUCCEEDED_UNVERIFIED:
        if external_readback is None:
            return WorkflowState.WAITING_FOR_EXTERNAL_EVIDENCE
        if external_readback.repository_identity != snapshot.binding.repository_identity:
            return WorkflowState.CONTRADICTED
        return WorkflowState.WAITING_FOR_EXTERNAL_EVIDENCE
    if execution.verdict == ExecutionVerdict.VERIFIED:
        return WorkflowState.VERIFIED
    if execution.verdict == ExecutionVerdict.CONTRADICTED:
        return WorkflowState.CONTRADICTED
    if execution.verdict == ExecutionVerdict.INVALIDATED:
        return WorkflowState.INVALIDATED
    return WorkflowState.BLOCKED


__all__ = [
    "WORKFLOW_SCHEMA_VERSION", "STEP_SCHEMA_VERSION", "TRANSITION_SCHEMA_VERSION", "PERMISSION_SCHEMA_VERSION", "EXECUTION_SCHEMA_VERSION",
    "DurableWorkflowError", "WorkflowState", "StepKind", "PermissionDecision", "ExecutionVerdict", "ReadbackVerdict",
    "WorkflowBinding", "WorkflowStep", "WorkflowDefinition", "PermissionReceipt", "ExecutionReceipt", "CanonicalReadback", "WorkflowSnapshot",
    "canonical_sha256", "create_permission_request", "approve_permission", "create_execution_receipt", "apply_canonical_readback", "resume_snapshot",
]
