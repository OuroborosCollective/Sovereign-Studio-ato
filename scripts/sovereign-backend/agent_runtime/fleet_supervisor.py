"""Fail-closed, side-effect-free Sovereign Fleet Supervisor contracts.

This module only plans, validates worker envelopes, evaluates supplied evidence and
projects status. It never creates a workspace, calls GitHub, writes a database, merges
a pull request, or claims deployment success on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from itertools import combinations
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "sovereign.fleet.v1"
_REVISION_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$", re.IGNORECASE)
_TASK_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,119}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SECRET_MARKERS = (
    "sk-proj-",
    "github_pat_",
    "ghp_",
    "authorization: bearer",
    "begin openssh private key",
    "begin rsa private key",
)


class FleetContractError(ValueError):
    """Raised when a request cannot be proven bounded and safe."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: object, field: str, *, minimum: int = 1, maximum: int = 320) -> str:
    normalized = str(value or "").strip()
    if not minimum <= len(normalized) <= maximum:
        raise FleetContractError(f"{field} must contain {minimum}..{maximum} characters")
    if any(marker in normalized.casefold() for marker in _SECRET_MARKERS):
        raise FleetContractError(f"{field} contains secret-shaped material")
    return normalized


def _revision(value: object, field: str, *, optional: bool = False) -> str:
    normalized = str(value or "").strip().lower()
    if optional and not normalized:
        return ""
    if not _REVISION_RE.fullmatch(normalized):
        raise FleetContractError(f"{field} must be an exact 40- or 64-character revision")
    return normalized


def _strings(
    value: object,
    field: str,
    *,
    maximum_items: int = 64,
    item_maximum: int = 240,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise FleetContractError(f"{field} must be a list")
    if len(value) > maximum_items:
        raise FleetContractError(f"{field} exceeds its bounded item limit")
    return tuple(sorted(dict.fromkeys(_text(item, field, maximum=item_maximum) for item in value)))


def _revisions(value: object, field: str, *, maximum_items: int = 64) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise FleetContractError(f"{field} must be a list")
    if len(value) > maximum_items:
        raise FleetContractError(f"{field} exceeds its bounded item limit")
    return tuple(sorted(dict.fromkeys(_revision(item, field) for item in value)))


def _field(value: Mapping[str, Any], snake: str, camel: str, default: object = None) -> object:
    return value[snake] if snake in value else value.get(camel, default)


def _shared(left: Sequence[str], right: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(left).intersection(right)))


@dataclass(frozen=True)
class FleetTask:
    task_id: str
    source_type: str
    source_id: str
    expected_base_revision: str
    expected_head_revision: str = ""
    changed_paths: tuple[str, ...] = ()
    architecture_domains: tuple[str, ...] = ()
    canonical_owners: tuple[str, ...] = ()
    invariant_scopes: tuple[str, ...] = ()
    required_gates: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    mutation_resources: tuple[str, ...] = ()
    lock_scopes: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    independence_proven: bool = False

    def __post_init__(self) -> None:
        if not _TASK_ID_RE.fullmatch(self.task_id):
            raise FleetContractError("task_id is invalid")
        if self.source_type not in {"issue", "pr", "integration_step"}:
            raise FleetContractError("source_type is invalid")
        _text(self.source_id, "source_id", maximum=160)
        _revision(self.expected_base_revision, "expected_base_revision")
        _revision(self.expected_head_revision, "expected_head_revision", optional=True)
        for dependency in self.depends_on:
            if not _TASK_ID_RE.fullmatch(dependency) or dependency == self.task_id:
                raise FleetContractError("depends_on contains an invalid task id")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FleetTask":
        if not isinstance(value, Mapping):
            raise FleetContractError("task must be an object")
        return cls(
            task_id=_text(_field(value, "task_id", "taskId"), "task_id", maximum=120),
            source_type=_text(_field(value, "source_type", "sourceType"), "source_type", maximum=40),
            source_id=_text(_field(value, "source_id", "sourceId"), "source_id", maximum=160),
            expected_base_revision=_revision(
                _field(value, "expected_base_revision", "expectedBaseRevision"),
                "expected_base_revision",
            ),
            expected_head_revision=_revision(
                _field(value, "expected_head_revision", "expectedHeadRevision", ""),
                "expected_head_revision",
                optional=True,
            ),
            changed_paths=_strings(_field(value, "changed_paths", "changedPaths", []), "changed_paths"),
            architecture_domains=_strings(_field(value, "architecture_domains", "architectureDomains", []), "architecture_domains"),
            canonical_owners=_strings(_field(value, "canonical_owners", "canonicalOwners", []), "canonical_owners"),
            invariant_scopes=_strings(_field(value, "invariant_scopes", "invariantScopes", []), "invariant_scopes"),
            required_gates=_strings(_field(value, "required_gates", "requiredGates", []), "required_gates"),
            required_capabilities=_strings(_field(value, "required_capabilities", "requiredCapabilities", []), "required_capabilities"),
            mutation_resources=_strings(_field(value, "mutation_resources", "mutationResources", []), "mutation_resources"),
            lock_scopes=_strings(_field(value, "lock_scopes", "lockScopes", []), "lock_scopes"),
            depends_on=_strings(_field(value, "depends_on", "dependsOn", []), "depends_on"),
            reason_codes=_strings(_field(value, "reason_codes", "reasonCodes", []), "reason_codes"),
            independence_proven=bool(_field(value, "independence_proven", "independenceProven", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "taskId": self.task_id,
            "sourceType": self.source_type,
            "sourceId": self.source_id,
            "expectedBaseRevision": self.expected_base_revision,
            "expectedHeadRevision": self.expected_head_revision or None,
            "changedPaths": list(self.changed_paths),
            "architectureDomains": list(self.architecture_domains),
            "canonicalOwners": list(self.canonical_owners),
            "invariantScopes": list(self.invariant_scopes),
            "requiredGates": list(self.required_gates),
            "requiredCapabilities": list(self.required_capabilities),
            "mutationResources": list(self.mutation_resources),
            "lockScopes": list(self.lock_scopes),
            "dependsOn": list(self.depends_on),
            "reasonCodes": list(self.reason_codes),
            "independenceProven": self.independence_proven,
        }
        return {**payload, "taskHash": stable_hash(payload)}


@dataclass(frozen=True)
class FleetConflict:
    task_a: str
    task_b: str
    code: str
    detail: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FleetConflict":
        return cls(
            task_a=_text(_field(value, "task_a", "taskA"), "task_a", maximum=120),
            task_b=_text(_field(value, "task_b", "taskB"), "task_b", maximum=120),
            code=_text(value.get("code"), "code", maximum=120),
            detail=_text(value.get("detail"), "detail", maximum=500),
        )

    def to_dict(self) -> dict[str, str]:
        return {"taskA": self.task_a, "taskB": self.task_b, "code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class FleetLane:
    lane_id: str
    sequence: int
    task_ids: tuple[str, ...]
    parallel_safe: bool

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FleetLane":
        task_ids = _strings(_field(value, "task_ids", "taskIds", []), "task_ids")
        if not task_ids:
            raise FleetContractError("lane must contain at least one task")
        sequence = int(value.get("sequence") or 0)
        if sequence < 1:
            raise FleetContractError("lane sequence is invalid")
        return cls(
            lane_id=_text(_field(value, "lane_id", "laneId"), "lane_id", maximum=120),
            sequence=sequence,
            task_ids=task_ids,
            parallel_safe=bool(_field(value, "parallel_safe", "parallelSafe", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "laneId": self.lane_id,
            "sequence": self.sequence,
            "taskIds": list(self.task_ids),
            "parallelSafe": self.parallel_safe,
        }


@dataclass(frozen=True)
class FleetPlan:
    integration_id: str
    repository: str
    base_revision: str
    architecture_receipt_hashes: tuple[str, ...]
    max_parallel_lanes: int
    tasks: tuple[FleetTask, ...]
    lanes: tuple[FleetLane, ...]
    conflicts: tuple[FleetConflict, ...]
    risk_codes: tuple[str, ...]
    plan_hash: str

    def _payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "integrationId": self.integration_id,
            "repository": self.repository,
            "baseRevision": self.base_revision,
            "architectureReceiptHashes": list(self.architecture_receipt_hashes),
            "maxParallelLanes": self.max_parallel_lanes,
            "tasks": [task.to_dict() for task in self.tasks],
            "lanes": [lane.to_dict() for lane in self.lanes],
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
            "riskCodes": list(self.risk_codes),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "planHash": self.plan_hash}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FleetPlan":
        if not isinstance(value, Mapping):
            raise FleetContractError("plan must be an object")
        raw_tasks = value.get("tasks")
        raw_lanes = value.get("lanes")
        raw_conflicts = value.get("conflicts", [])
        if not isinstance(raw_tasks, Sequence) or isinstance(raw_tasks, (str, bytes, bytearray)):
            raise FleetContractError("plan tasks must be a list")
        if not isinstance(raw_lanes, Sequence) or isinstance(raw_lanes, (str, bytes, bytearray)):
            raise FleetContractError("plan lanes must be a list")
        if not isinstance(raw_conflicts, Sequence) or isinstance(raw_conflicts, (str, bytes, bytearray)):
            raise FleetContractError("plan conflicts must be a list")
        plan = cls(
            integration_id=_text(_field(value, "integration_id", "integrationId"), "integration_id", maximum=120),
            repository=_text(value.get("repository"), "repository", maximum=160),
            base_revision=_revision(_field(value, "base_revision", "baseRevision"), "base_revision"),
            architecture_receipt_hashes=_revisions(_field(value, "architecture_receipt_hashes", "architectureReceiptHashes", []), "architecture_receipt_hashes"),
            max_parallel_lanes=max(1, min(int(_field(value, "max_parallel_lanes", "maxParallelLanes", 1) or 1), 8)),
            tasks=tuple(FleetTask.from_dict(item) for item in raw_tasks),
            lanes=tuple(FleetLane.from_dict(item) for item in raw_lanes),
            conflicts=tuple(FleetConflict.from_dict(item) for item in raw_conflicts),
            risk_codes=_strings(_field(value, "risk_codes", "riskCodes", []), "risk_codes"),
            plan_hash=_revision(_field(value, "plan_hash", "planHash"), "plan_hash"),
        )
        if not _REPOSITORY_RE.fullmatch(plan.repository):
            raise FleetContractError("repository is invalid")
        if not plan.tasks or not plan.lanes:
            raise FleetContractError("plan must contain tasks and lanes")
        if stable_hash(plan._payload()) != plan.plan_hash:
            raise FleetContractError("plan hash does not bind the submitted plan")
        return plan


def pair_conflicts(left: FleetTask, right: FleetTask) -> tuple[FleetConflict, ...]:
    """Return all reasons why two tasks must not share a parallel lane."""

    task_a, task_b = sorted((left.task_id, right.task_id))
    findings: list[FleetConflict] = []

    def add(code: str, values: Sequence[str], label: str) -> None:
        if values:
            findings.append(FleetConflict(task_a, task_b, code, f"shared {label}: {', '.join(values)}"))

    add("DIRECT_PATH_CONFLICT", _shared(left.changed_paths, right.changed_paths), "changed paths")
    add("CANONICAL_OWNER_CONFLICT", _shared(left.canonical_owners, right.canonical_owners), "canonical owners")
    add("INVARIANT_SCOPE_CONFLICT", _shared(left.invariant_scopes, right.invariant_scopes), "invariant scopes")
    add("MUTATION_RESOURCE_CONFLICT", _shared(left.mutation_resources, right.mutation_resources), "mutation resources")
    add("LOCK_SCOPE_CONFLICT", _shared(left.lock_scopes, right.lock_scopes), "lock scopes")
    if not left.independence_proven or not right.independence_proven:
        findings.append(FleetConflict(
            task_a,
            task_b,
            "UNPROVEN_INDEPENDENCE",
            "parallel execution is forbidden until an architecture receipt proves non-overlap",
        ))
    return tuple(findings)


def _validate_dependencies(tasks: Sequence[FleetTask]) -> None:
    by_id = {task.task_id: task for task in tasks}
    if len(by_id) != len(tasks):
        raise FleetContractError("task ids must be unique")
    for task in tasks:
        unknown = sorted(set(task.depends_on).difference(by_id))
        if unknown:
            raise FleetContractError(f"{task.task_id} depends on unknown tasks: {', '.join(unknown)}")
    active: set[str] = set()
    complete: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in complete:
            return
        if task_id in active:
            raise FleetContractError("dependency graph contains a cycle")
        active.add(task_id)
        for dependency in by_id[task_id].depends_on:
            visit(dependency)
        active.remove(task_id)
        complete.add(task_id)

    for task_id in sorted(by_id):
        visit(task_id)


def _pick_lane(ready: Sequence[FleetTask], max_parallel_lanes: int) -> tuple[FleetTask, ...]:
    selected: list[FleetTask] = []
    for candidate in sorted(ready, key=lambda task: task.task_id):
        if len(selected) >= max_parallel_lanes:
            break
        if not selected and not candidate.independence_proven:
            return (candidate,)
        if selected and (not candidate.independence_proven or any(pair_conflicts(candidate, existing) for existing in selected)):
            continue
        selected.append(candidate)
    return tuple(selected or (sorted(ready, key=lambda task: task.task_id)[0],))


def build_fleet_plan(
    *,
    integration_id: str,
    repository: str,
    base_revision: str,
    tasks: Sequence[Mapping[str, Any] | FleetTask],
    architecture_receipt_hashes: Sequence[str] | None = None,
    max_parallel_lanes: int = 1,
) -> FleetPlan:
    """Build deterministic lanes and serialize anything that lacks proof of independence."""

    normalized_tasks = tuple(
        item if isinstance(item, FleetTask) else FleetTask.from_dict(item)
        for item in tasks
    )
    if not normalized_tasks:
        raise FleetContractError("at least one fleet task is required")
    normalized_base = _revision(base_revision, "base_revision")
    if any(task.expected_base_revision != normalized_base for task in normalized_tasks):
        raise FleetContractError("every task must bind the exact fleet base revision")
    _validate_dependencies(normalized_tasks)

    normalized_integration_id = _text(integration_id, "integration_id", maximum=120)
    normalized_repository = _text(repository, "repository", maximum=160)
    if not _REPOSITORY_RE.fullmatch(normalized_repository):
        raise FleetContractError("repository is invalid")
    receipts = _revisions(architecture_receipt_hashes or (), "architecture_receipt_hashes")
    parallelism = max(1, min(int(max_parallel_lanes), 8))
    ordered_tasks = tuple(sorted(normalized_tasks, key=lambda task: task.task_id))
    conflicts = tuple(
        conflict
        for left, right in combinations(ordered_tasks, 2)
        for conflict in pair_conflicts(left, right)
    )

    done: set[str] = set()
    lanes: list[FleetLane] = []
    while len(done) < len(ordered_tasks):
        ready = [task for task in ordered_tasks if task.task_id not in done and set(task.depends_on).issubset(done)]
        if not ready:
            raise FleetContractError("dependency graph cannot make progress")
        selected = _pick_lane(ready, parallelism)
        sequence = len(lanes) + 1
        lanes.append(FleetLane(
            lane_id=f"lane-{sequence:02d}",
            sequence=sequence,
            task_ids=tuple(task.task_id for task in selected),
            parallel_safe=len(selected) > 1,
        ))
        done.update(task.task_id for task in selected)

    risks = {conflict.code for conflict in conflicts}
    if not receipts:
        risks.add("ARCHITECTURE_RECEIPTS_MISSING")
    if any(not task.independence_proven for task in ordered_tasks):
        risks.add("UNPROVEN_INDEPENDENCE")
    risk_codes = _strings(sorted(risks), "risk_codes")
    provisional = FleetPlan(
        integration_id=normalized_integration_id,
        repository=normalized_repository,
        base_revision=normalized_base,
        architecture_receipt_hashes=receipts,
        max_parallel_lanes=parallelism,
        tasks=ordered_tasks,
        lanes=tuple(lanes),
        conflicts=conflicts,
        risk_codes=risk_codes,
        plan_hash="0" * 64,
    )
    return FleetPlan(**{**provisional.__dict__, "plan_hash": stable_hash(provisional._payload())})


@dataclass(frozen=True)
class FleetWorkerAssignment:
    assignment_id: str
    plan_hash: str
    lane_id: str
    task_id: str
    controller_run_id: str
    workspace_id: str
    workspace_branch: str
    expected_base_revision: str
    expected_head_revision: str
    run_envelope_hash: str
    capability_manifest_hash: str
    permission_receipt_hashes: tuple[str, ...]
    allowed_effects: tuple[str, ...]
    assignment_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "assignmentId": self.assignment_id,
            "planHash": self.plan_hash,
            "laneId": self.lane_id,
            "taskId": self.task_id,
            "controllerRunId": self.controller_run_id,
            "workspaceId": self.workspace_id,
            "workspaceBranch": self.workspace_branch,
            "expectedBaseRevision": self.expected_base_revision,
            "expectedHeadRevision": self.expected_head_revision or None,
            "runEnvelopeHash": self.run_envelope_hash,
            "capabilityManifestHash": self.capability_manifest_hash,
            "permissionReceiptHashes": list(self.permission_receipt_hashes),
            "allowedEffects": list(self.allowed_effects),
            "assignmentHash": self.assignment_hash,
        }


def create_worker_assignment(
    plan: FleetPlan | Mapping[str, Any],
    *,
    lane_id: str,
    task_id: str,
    controller_run_id: str,
    workspace_id: str,
    workspace_branch: str,
    run_envelope_hash: str,
    capability_manifest_hash: str,
    permission_receipt_hashes: Sequence[str] | None = None,
    allowed_effects: Sequence[str] | None = None,
) -> FleetWorkerAssignment:
    """Bind a worker only to a controller-created workspace and a known plan lane."""

    selected_plan = plan if isinstance(plan, FleetPlan) else FleetPlan.from_dict(plan)
    lane = next((item for item in selected_plan.lanes if item.lane_id == lane_id), None)
    task = next((item for item in selected_plan.tasks if item.task_id == task_id), None)
    if lane is None or task is None or task_id not in lane.task_ids:
        raise FleetContractError("assignment is not bound to a plan lane and task")
    effects = _strings(allowed_effects or ("READ", "PROPOSE_CHANGE", "REPORT_EVIDENCE"), "allowed_effects")
    if set(effects).difference({"READ", "PROPOSE_CHANGE", "REPORT_EVIDENCE"}):
        raise FleetContractError("worker effects must remain bounded and non-authoritative")
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "planHash": selected_plan.plan_hash,
        "laneId": _text(lane_id, "lane_id", maximum=120),
        "taskId": _text(task_id, "task_id", maximum=120),
        "controllerRunId": _text(controller_run_id, "controller_run_id", maximum=160),
        "workspaceId": _text(workspace_id, "workspace_id", maximum=160),
        "workspaceBranch": _text(workspace_branch, "workspace_branch", maximum=200),
        "expectedBaseRevision": task.expected_base_revision,
        "expectedHeadRevision": task.expected_head_revision or None,
        "runEnvelopeHash": _revision(run_envelope_hash, "run_envelope_hash"),
        "capabilityManifestHash": _revision(capability_manifest_hash, "capability_manifest_hash"),
        "permissionReceiptHashes": list(_revisions(permission_receipt_hashes or (), "permission_receipt_hashes")),
        "allowedEffects": list(effects),
    }
    assignment_hash = stable_hash(payload)
    return FleetWorkerAssignment(
        assignment_id=f"assignment-{assignment_hash[:24]}",
        plan_hash=selected_plan.plan_hash,
        lane_id=payload["laneId"],
        task_id=payload["taskId"],
        controller_run_id=payload["controllerRunId"],
        workspace_id=payload["workspaceId"],
        workspace_branch=payload["workspaceBranch"],
        expected_base_revision=task.expected_base_revision,
        expected_head_revision=task.expected_head_revision,
        run_envelope_hash=payload["runEnvelopeHash"],
        capability_manifest_hash=payload["capabilityManifestHash"],
        permission_receipt_hashes=tuple(payload["permissionReceiptHashes"]),
        allowed_effects=effects,
        assignment_hash=assignment_hash,
    )


def validate_worker_event(
    assignment: FleetWorkerAssignment | Mapping[str, Any],
    *,
    event_type: str,
    summary: str,
    evidence_refs: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Validate a report without turning worker completion into verification."""

    raw_assignment = assignment.to_dict() if isinstance(assignment, FleetWorkerAssignment) else dict(assignment)
    assignment_hash = _revision(_field(raw_assignment, "assignment_hash", "assignmentHash"), "assignment_hash")
    normalized_type = _text(event_type, "event_type", maximum=120).upper()
    allowed = {
        "WORKER_READY",
        "WORKER_STARTED",
        "WORKER_BLOCKED",
        "WORKER_FAILED",
        "WORKER_COMPLETED_UNVERIFIED",
    }
    if normalized_type not in allowed or ("VERIFIED" in normalized_type and normalized_type != "WORKER_COMPLETED_UNVERIFIED"):
        raise FleetContractError("worker events cannot claim verification, merge, or runtime success")
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "assignmentHash": assignment_hash,
        "taskId": _text(_field(raw_assignment, "task_id", "taskId"), "task_id", maximum=120),
        "eventType": normalized_type,
        "status": "COMPLETED_UNVERIFIED" if normalized_type == "WORKER_COMPLETED_UNVERIFIED" else normalized_type.removeprefix("WORKER_"),
        "summary": _text(summary, "summary", maximum=2000),
        "evidenceRefs": list(_revisions(evidence_refs or (), "evidence_refs", maximum_items=20)),
    }
    return {**payload, "eventId": f"fleet-event-{stable_hash(payload)[:24]}", "eventHash": stable_hash(payload)}


def evaluate_fleet_verdict(
    task: FleetTask | Mapping[str, Any],
    *,
    assignment: FleetWorkerAssignment | Mapping[str, Any] | None,
    observed_base_revision: str,
    observed_head_revision: str,
    workspace_head_revision: str,
    check_receipts: Sequence[Mapping[str, Any]] | None = None,
    merge_readback: Mapping[str, Any] | None = None,
    runtime_readback: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate exact-head evidence. This is a projection, never a merge operation."""

    selected_task = task if isinstance(task, FleetTask) else FleetTask.from_dict(task)
    gaps: list[str] = []
    status = "WORKER_COMPLETED_UNVERIFIED"
    expected_head = selected_task.expected_head_revision
    if not assignment:
        gaps.append("WORKER_ASSIGNMENT_MISSING")
    if _revision(observed_base_revision, "observed_base_revision") != selected_task.expected_base_revision:
        status = "BLOCKED_BASE_DRIFT"
        gaps.append("EXACT_BASE_MISMATCH")
    elif not expected_head:
        status = "BLOCKED_HEAD_UNBOUND"
        gaps.append("EXPECTED_HEAD_MISSING")
    elif _revision(observed_head_revision, "observed_head_revision") != expected_head:
        status = "BLOCKED_HEAD_MISMATCH"
        gaps.append("PR_HEAD_MISMATCH")
    elif _revision(workspace_head_revision, "workspace_head_revision") != expected_head:
        status = "BLOCKED_WORKSPACE_HEAD_MISMATCH"
        gaps.append("WORKSPACE_HEAD_MISMATCH")
    else:
        by_gate: dict[str, Mapping[str, Any]] = {}
        for receipt in check_receipts or ():
            if isinstance(receipt, Mapping):
                gate = str(receipt.get("gate") or receipt.get("name") or "").strip()
                if gate:
                    by_gate[gate] = receipt
        missing = [gate for gate in selected_task.required_gates if gate not in by_gate]
        failed = [
            gate for gate, receipt in by_gate.items()
            if str(receipt.get("status") or "").strip().lower() not in {"success", "passed", "neutral"}
            or str(receipt.get("headSha") or receipt.get("head_sha") or "").strip().lower() != expected_head
        ]
        if missing:
            status = "CI_WAITING"
            gaps.extend(f"CHECK_MISSING:{gate}" for gate in missing)
        elif failed:
            status = "CI_FAILED"
            gaps.extend(f"CHECK_NOT_EXACT_SUCCESS:{gate}" for gate in sorted(failed))
        else:
            status = "MERGE_CANDIDATE"

    if status == "MERGE_CANDIDATE" and isinstance(merge_readback, Mapping):
        merge_head = str(merge_readback.get("headSha") or merge_readback.get("head_sha") or "").strip().lower()
        merged = bool(merge_readback.get("merged")) and bool(merge_readback.get("readbackVerified") or merge_readback.get("readback_verified"))
        if merged and merge_head == expected_head and str(merge_readback.get("mergeCommitSha") or merge_readback.get("merge_commit_sha") or "").strip():
            status = "MERGED"
        else:
            gaps.append("GITHUB_MERGE_READBACK_REQUIRED")

    if status == "MERGED" and isinstance(runtime_readback, Mapping):
        runtime_revision = str(runtime_readback.get("deployedRevision") or runtime_readback.get("deployed_revision") or "").strip().lower()
        runtime_ok = bool(runtime_readback.get("imageDigest")) and bool(runtime_readback.get("patchmonHealthy")) and bool(runtime_readback.get("functionVerified"))
        if runtime_ok and runtime_revision == expected_head:
            status = "RUNTIME_VERIFIED"
        else:
            gaps.append("RUNTIME_READBACK_REQUIRED")

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "taskId": selected_task.task_id,
        "expectedBaseRevision": selected_task.expected_base_revision,
        "expectedHeadRevision": expected_head or None,
        "status": status,
        "evidenceGaps": sorted(dict.fromkeys(gaps)),
        "mergeAuthorized": False,
        "runtimeClaimed": status == "RUNTIME_VERIFIED",
    }
    return {**payload, "verdictHash": stable_hash(payload)}


def build_fleet_projection(
    plan: FleetPlan | Mapping[str, Any],
    *,
    assignments: Sequence[Mapping[str, Any]] | None = None,
    worker_events: Sequence[Mapping[str, Any]] | None = None,
    verdicts: Sequence[Mapping[str, Any]] | None = None,
    observed_main_revision: str = "",
) -> dict[str, Any]:
    """Return a rebuildable read-only projection from supplied controller evidence."""

    selected_plan = plan if isinstance(plan, FleetPlan) else FleetPlan.from_dict(plan)
    if len(assignments or ()) > 200 or len(worker_events or ()) > 500 or len(verdicts or ()) > 200:
        raise FleetContractError("projection evidence exceeds bounded limits")
    observed = _revision(observed_main_revision, "observed_main_revision", optional=True)
    evidence_gaps = set(selected_plan.risk_codes)
    stale = not observed or observed != selected_plan.base_revision
    if stale:
        evidence_gaps.add("MAIN_HEAD_STALE_OR_UNAVAILABLE")

    assignment_by_task = {
        str(_field(item, "task_id", "taskId") or "").strip(): item
        for item in assignments or ()
        if isinstance(item, Mapping)
    }
    event_by_task = {
        str(_field(item, "task_id", "taskId") or "").strip(): item
        for item in worker_events or ()
        if isinstance(item, Mapping)
    }
    verdict_by_task = {
        str(_field(item, "task_id", "taskId") or "").strip(): item
        for item in verdicts or ()
        if isinstance(item, Mapping)
    }

    task_states: list[dict[str, Any]] = []
    for task in selected_plan.tasks:
        status = "PLANNED"
        if task.task_id in assignment_by_task:
            status = "ASSIGNED"
        event = event_by_task.get(task.task_id)
        if event:
            status = str(event.get("status") or event.get("eventType") or status)
        verdict = verdict_by_task.get(task.task_id)
        if verdict:
            status = str(verdict.get("status") or status)
            for gap in verdict.get("evidenceGaps") or verdict.get("evidence_gaps") or ():
                evidence_gaps.add(str(gap))
        task_states.append({
            "taskId": task.task_id,
            "sourceType": task.source_type,
            "sourceId": task.source_id,
            "status": status,
            "expectedBaseRevision": task.expected_base_revision,
            "expectedHeadRevision": task.expected_head_revision or None,
        })

    lanes = []
    for lane in selected_plan.lanes:
        lane_tasks = [state for state in task_states if state["taskId"] in lane.task_ids]
        lane_status = (
            "STALE" if stale
            else "BLOCKED" if any(str(task["status"]).startswith("BLOCKED") for task in lane_tasks)
            else "ACTIVE" if any(task["status"] not in {"PLANNED", "MERGED", "RUNTIME_VERIFIED"} for task in lane_tasks)
            else "PLANNED"
        )
        lanes.append({**lane.to_dict(), "tasks": lane_tasks, "status": lane_status})

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "status": "FLEET_STALE" if stale else "FLEET_PROJECTED",
        "readOnly": True,
        "mutationPerformed": False,
        "planHash": selected_plan.plan_hash,
        "baseRevision": selected_plan.base_revision,
        "observedMainRevision": observed or None,
        "stale": stale,
        "commandsBlocked": stale,
        "nextEligibleActions": ["REPLAN"] if stale else ["READBACK", "ASSIGN_THROUGH_EXISTING_CONTROLLER"],
        "lanes": lanes,
        "tasks": task_states,
        "evidenceGaps": sorted(evidence_gaps),
    }
    return {**payload, "projectionHash": stable_hash(payload)}
