"""Retry-safe, deterministic Fleet worker attempt contracts.

A Fleet task and assignment may have multiple execution attempts. This module binds
worker lifecycle/evidence events to exactly one active attempt without granting the
worker verification, merge, deployment, or runtime authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

from .fleet_supervisor import (
    FleetContractError,
    FleetWorkerAssignment,
    stable_hash,
    validate_worker_event,
)


ATTEMPT_SCHEMA_VERSION = "sovereign.fleet.attempt.v1"
_ATTEMPT_ID_RE = re.compile(r"^attempt-[0-9a-f]{24}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_TASK_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,119}$")
_ACTIVE_HEARTBEAT_STATES = frozenset({"ASSIGNED", "WORKSPACE_BOUND", "RUNNING", "BLOCKED", "VERIFYING"})
_SECRET_MARKERS = (
    "sk-proj-",
    "github_pat_",
    "ghp_",
    "authorization: bearer",
    "begin openssh private key",
    "begin rsa private key",
    "begin private key",
)


@dataclass(frozen=True)
class FleetWorkerAttempt:
    attempt_id: str
    attempt_sequence: int
    assignment_hash: str
    task_id: str
    controller_run_id: str
    expected_base_revision: str
    expected_head_revision: str
    capability_manifest_hash: str
    attempt_hash: str

    def _payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": ATTEMPT_SCHEMA_VERSION,
            "controllerRunId": self.controller_run_id,
            "taskId": self.task_id,
            "assignmentHash": self.assignment_hash,
            "attemptSequence": self.attempt_sequence,
            "expectedBaseRevision": self.expected_base_revision,
            "expectedHeadRevision": self.expected_head_revision or None,
            "capabilityManifestHash": self.capability_manifest_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "attemptId": self.attempt_id, "attemptHash": self.attempt_hash}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FleetWorkerAttempt":
        if not isinstance(value, Mapping):
            raise FleetContractError("attempt must be an object")
        attempt = cls(
            attempt_id=_attempt_id(value.get("attemptId") or value.get("attempt_id")),
            attempt_sequence=_attempt_sequence(value.get("attemptSequence") if "attemptSequence" in value else value.get("attempt_sequence")),
            assignment_hash=_hash(value.get("assignmentHash") or value.get("assignment_hash"), "assignment_hash"),
            task_id=_task_id(value.get("taskId") or value.get("task_id")),
            controller_run_id=_bounded_text(value.get("controllerRunId") or value.get("controller_run_id"), "controller_run_id", 160),
            expected_base_revision=_revision(value.get("expectedBaseRevision") or value.get("expected_base_revision"), "expected_base_revision"),
            expected_head_revision=_revision(value.get("expectedHeadRevision") or value.get("expected_head_revision") or "", "expected_head_revision", optional=True),
            capability_manifest_hash=_hash(value.get("capabilityManifestHash") or value.get("capability_manifest_hash"), "capability_manifest_hash"),
            attempt_hash=_hash(value.get("attemptHash") or value.get("attempt_hash"), "attempt_hash"),
        )
        expected_hash = stable_hash(attempt._payload())
        if expected_hash != attempt.attempt_hash:
            raise FleetContractError("attempt hash does not bind the submitted attempt")
        if attempt.attempt_id != f"attempt-{expected_hash[:24]}":
            raise FleetContractError("attempt id does not bind the submitted attempt hash")
        return attempt


def _bounded_text(value: object, field: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise FleetContractError(f"{field} is invalid")
    if any(marker in normalized.casefold() for marker in _SECRET_MARKERS):
        raise FleetContractError(f"{field} contains secret-shaped material")
    return normalized


def _hash(value: object, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _HASH_RE.fullmatch(normalized):
        raise FleetContractError(f"{field} must be an exact SHA-256 value")
    return normalized


def _revision(value: object, field: str, *, optional: bool = False) -> str:
    normalized = str(value or "").strip().lower()
    if optional and not normalized:
        return ""
    if not _REVISION_RE.fullmatch(normalized):
        raise FleetContractError(f"{field} must be an exact revision")
    return normalized


def _attempt_id(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if not _ATTEMPT_ID_RE.fullmatch(normalized):
        raise FleetContractError("attempt_id is invalid")
    return normalized


def _task_id(value: object) -> str:
    normalized = str(value or "").strip()
    if not _TASK_ID_RE.fullmatch(normalized):
        raise FleetContractError("task_id is invalid")
    return normalized


def _attempt_sequence(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise FleetContractError("attempt_sequence must be a positive integer")
    return value


def _assignment_dict(assignment: FleetWorkerAssignment | Mapping[str, Any]) -> dict[str, Any]:
    return assignment.to_dict() if isinstance(assignment, FleetWorkerAssignment) else dict(assignment)


def _assignment_value(raw: Mapping[str, Any], snake: str, camel: str) -> object:
    return raw[snake] if snake in raw else raw.get(camel)


def create_worker_attempt(
    assignment: FleetWorkerAssignment | Mapping[str, Any],
    *,
    attempt_sequence: int,
) -> FleetWorkerAttempt:
    """Create one deterministic execution attempt for an existing assignment."""

    raw = _assignment_dict(assignment)
    payload = {
        "schemaVersion": ATTEMPT_SCHEMA_VERSION,
        "controllerRunId": _bounded_text(_assignment_value(raw, "controller_run_id", "controllerRunId"), "controller_run_id", 160),
        "taskId": _task_id(_assignment_value(raw, "task_id", "taskId")),
        "assignmentHash": _hash(_assignment_value(raw, "assignment_hash", "assignmentHash"), "assignment_hash"),
        "attemptSequence": _attempt_sequence(attempt_sequence),
        "expectedBaseRevision": _revision(_assignment_value(raw, "expected_base_revision", "expectedBaseRevision"), "expected_base_revision"),
        "expectedHeadRevision": _revision(_assignment_value(raw, "expected_head_revision", "expectedHeadRevision") or "", "expected_head_revision", optional=True) or None,
        "capabilityManifestHash": _hash(_assignment_value(raw, "capability_manifest_hash", "capabilityManifestHash"), "capability_manifest_hash"),
    }
    attempt_hash = stable_hash(payload)
    return FleetWorkerAttempt(
        attempt_id=f"attempt-{attempt_hash[:24]}",
        attempt_sequence=payload["attemptSequence"],
        assignment_hash=payload["assignmentHash"],
        task_id=payload["taskId"],
        controller_run_id=payload["controllerRunId"],
        expected_base_revision=payload["expectedBaseRevision"],
        expected_head_revision=str(payload["expectedHeadRevision"] or ""),
        capability_manifest_hash=payload["capabilityManifestHash"],
        attempt_hash=attempt_hash,
    )


def _selected_attempt(value: FleetWorkerAttempt | Mapping[str, Any]) -> FleetWorkerAttempt:
    return value if isinstance(value, FleetWorkerAttempt) else FleetWorkerAttempt.from_dict(value)


def require_active_attempt(
    attempt: FleetWorkerAttempt | Mapping[str, Any],
    active_attempt: FleetWorkerAttempt | Mapping[str, Any],
    assignment: FleetWorkerAssignment | Mapping[str, Any],
) -> FleetWorkerAttempt:
    """Reject stale, superseded or assignment-mismatched attempts fail-closed."""

    selected = _selected_attempt(attempt)
    active = _selected_attempt(active_attempt)
    raw_assignment = _assignment_dict(assignment)
    assignment_hash = _hash(_assignment_value(raw_assignment, "assignment_hash", "assignmentHash"), "assignment_hash")
    task_id = _task_id(_assignment_value(raw_assignment, "task_id", "taskId"))
    if selected.assignment_hash != assignment_hash or selected.task_id != task_id:
        raise FleetContractError("worker attempt is not bound to the supplied assignment")
    if active.assignment_hash != assignment_hash or active.task_id != task_id:
        raise FleetContractError("active attempt is not bound to the supplied assignment")
    if selected.attempt_sequence < active.attempt_sequence:
        raise FleetContractError("stale worker attempt cannot affect the active retry")
    if selected.attempt_sequence > active.attempt_sequence:
        raise FleetContractError("future worker attempt cannot affect the active retry")
    if selected.attempt_id != active.attempt_id or selected.attempt_hash != active.attempt_hash:
        raise FleetContractError("worker attempt identity does not match the active retry")
    return selected


def validate_active_worker_event(
    assignment: FleetWorkerAssignment | Mapping[str, Any],
    attempt: FleetWorkerAttempt | Mapping[str, Any],
    active_attempt: FleetWorkerAttempt | Mapping[str, Any],
    *,
    event_type: str,
    summary: str,
    evidence_refs: Sequence[str] | None = None,
    sequence: int | None = None,
    base_revision: str = "",
    head_revision: str = "",
    predecessor_hash: str = "",
    lifecycle_state: str = "RUNNING",
) -> dict[str, Any]:
    """Validate one active-attempt event without granting worker authority.

    WORKER_HEARTBEAT is a liveness sensor only. It never transitions lifecycle state,
    verifies work, renews a superseded attempt, or satisfies controller evidence gates.
    """

    selected = require_active_attempt(attempt, active_attempt, assignment)
    normalized_type = _bounded_text(event_type, "event_type", 120).upper()
    if normalized_type == "WORKER_HEARTBEAT":
        state = _bounded_text(lifecycle_state, "lifecycle_state", 120).upper()
        if state not in _ACTIVE_HEARTBEAT_STATES:
            raise FleetContractError("worker heartbeat is only valid for an active non-terminal lifecycle")
        payload: dict[str, Any] = {
            "schemaVersion": ATTEMPT_SCHEMA_VERSION,
            "assignmentHash": selected.assignment_hash,
            "attemptId": selected.attempt_id,
            "attemptSequence": selected.attempt_sequence,
            "attemptHash": selected.attempt_hash,
            "taskId": selected.task_id,
            "eventType": "WORKER_HEARTBEAT",
            "status": state,
            "summary": _bounded_text(summary, "summary", 2000),
            "evidenceRefs": [],
            "livenessOnly": True,
            "authoritative": False,
        }
        if sequence is not None:
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
                raise FleetContractError("sequence must be a non-negative integer")
            payload["sequence"] = sequence
        if base_revision:
            payload["baseRevision"] = _revision(base_revision, "base_revision")
        if head_revision:
            payload["headRevision"] = _revision(head_revision, "head_revision")
        if predecessor_hash:
            payload["predecessorHash"] = _hash(predecessor_hash, "predecessor_hash")
        event_hash = stable_hash(payload)
        return {**payload, "eventId": f"fleet-event-{event_hash[:24]}", "eventHash": event_hash}

    event = validate_worker_event(
        assignment,
        event_type=normalized_type,
        summary=summary,
        evidence_refs=evidence_refs,
        sequence=sequence,
        base_revision=base_revision,
        head_revision=head_revision,
        predecessor_hash=predecessor_hash,
    )
    payload = {key: value for key, value in event.items() if key not in {"eventId", "eventHash"}}
    payload.update({
        "schemaVersion": ATTEMPT_SCHEMA_VERSION,
        "attemptId": selected.attempt_id,
        "attemptSequence": selected.attempt_sequence,
        "attemptHash": selected.attempt_hash,
        "livenessOnly": False,
        "authoritative": False,
    })
    event_hash = stable_hash(payload)
    return {**payload, "eventId": f"fleet-event-{event_hash[:24]}", "eventHash": event_hash}


def evidence_matches_active_attempt(
    evidence: Mapping[str, Any],
    active_attempt: FleetWorkerAttempt | Mapping[str, Any],
) -> bool:
    """Return true only for evidence exactly bound to the active attempt identity."""

    try:
        active = _selected_attempt(active_attempt)
        attempt_id = _attempt_id(evidence.get("attemptId") or evidence.get("attempt_id"))
        attempt_sequence = _attempt_sequence(evidence.get("attemptSequence") if "attemptSequence" in evidence else evidence.get("attempt_sequence"))
        assignment_hash = _hash(evidence.get("assignmentHash") or evidence.get("assignment_hash"), "assignment_hash")
        attempt_hash = _hash(evidence.get("attemptHash") or evidence.get("attempt_hash"), "attempt_hash")
    except (FleetContractError, TypeError, ValueError):
        return False
    return (
        attempt_id == active.attempt_id
        and attempt_sequence == active.attempt_sequence
        and assignment_hash == active.assignment_hash
        and attempt_hash == active.attempt_hash
    )
