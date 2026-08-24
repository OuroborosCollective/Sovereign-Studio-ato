"""Bounded repository tools exposed to the OpenAI Agents SDK workers.

Natural-language understanding remains in the routed model. This module owns only
capability, workspace, path, evidence and write boundaries. Every tool call runs
against the linked Sovereign Agent Job and persists sanitized runtime evidence.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path, PurePosixPath
import re
from threading import Lock
import uuid
from typing import Any, Final, Iterator, Mapping

from .agent_run_receipts import (
    canonical_sha256,
    read_git_workspace_identity,
    read_mcp_runtime_identity,
)
from .cognitive_run_store import (
    create_agent_task,
    finish_agent_tool_call,
    start_agent_tool_call,
)
from .cognitive_swarm_manifest import WORKER_ROLES, manifest_payload
from .fleet_attempts import FleetWorkerAttempt, create_worker_attempt, require_active_attempt
from .fleet_attempt_worktrees import (
    AttemptWorkspace,
    AttemptWorktreeRelease,
    cleanup_settled_attempt_worktree,
    discard_unpersisted_attempt_worktree,
    provision_attempt_worktree,
    resolve_active_attempt_worktree,
)
from .fleet_supervisor import (
    FleetContractError,
    FleetPlan,
    FleetTask,
    FleetWorkerAssignment,
    build_fleet_plan,
    create_worker_assignment,
    stable_hash,
)
from .job_store import append_agent_evidence_anchor, append_agent_projection, read_agent_job
from .live_workspace import WorkspaceEvidenceAnchorV1
from .live_workspace_context import LiveWorkspaceContextResolver
from .live_workspace_projection import projection_for_tool_result, public_projection_event
from .tool_events import append_tool_result_to_job
from .tool_runner import run_agent_job_tool
from .tools.base import ToolResult
from .workspace_policy import repo_dir_for_workspace


ConnectionFactory = Callable[[], Any]

ROLE_WORK_PACKAGES: Final[dict[str, str]] = {
    "free_single_agent": "Implement one bounded coding mission in the isolated Code-Server workspace; read before writing and preserve diff plus test evidence.",
    "data_storage": "Inspect SQL, Agent Job persistence, pattern candidates and pgvector learning; accept learning only after tool and test evidence.",
    "business_core": "Inspect intent, ARE inference and evidence-gate semantics; model output must never create runtime success.",
    "endpoint_bridge": "Inspect route, job, workspace and executor handoff; prove every state transition from real tool evidence.",
    "chat_cognitive": "Inspect natural-language understanding and Agents SDK orchestration; remove local language interpretation from online execution paths.",
    "ui_accessibility": "Inspect Controller and chat surfaces; visible status must mirror persisted tasks, events, blockers and approvals.",
    "predictive_qa": "Inspect predictive signals, test gates and capability boundaries; derive follow-up failures to depth three and verify reruns.",
}

ROLE_PATH_PREFIXES: Final[dict[str, tuple[str, ...]]] = {
    "free_single_agent": ("__workspace_all__",),
    "data_storage": (
        "scripts/sovereign-backend/migrations/",
        "scripts/sovereign-backend/knowledge_library.py",
        "scripts/sovereign-backend/agent_runtime/job_store.py",
        "scripts/sovereign-backend/agent_runtime/pattern_gateway.py",
        "scripts/sovereign-backend/agent_runtime/pattern_vector_memory.py",
        "backend/agent_runtime/job_store.py",
        "backend/agent_runtime/pattern_gateway.py",
        "backend/agent_runtime/pattern_vector_memory.py",
    ),
    "business_core": (
        "scripts/sovereign-backend/are_inference.py",
        "scripts/sovereign-backend/agent_runtime/contracts.py",
        "scripts/sovereign-backend/agent_runtime/evidence_gate.py",
        "backend/agent_runtime/contracts.py",
        "backend/agent_runtime/evidence_gate.py",
    ),
    "endpoint_bridge": (
        "scripts/sovereign-backend/app.py",
        "scripts/sovereign-backend/agent_runtime/cognitive_swarm_routes.py",
        "scripts/sovereign-backend/agent_runtime/routes.py",
        "backend/agent_runtime/cognitive_swarm_routes.py",
        "backend/agent_runtime/routes.py",
    ),
    "chat_cognitive": (
        "scripts/sovereign-backend/agent_runtime/cognitive_swarm_agents.py",
        "scripts/sovereign-backend/agent_runtime/cognitive_swarm_manifest.py",
        "scripts/sovereign-backend/agent_runtime/skills/",
        "backend/agent_runtime/cognitive_swarm_agents.py",
        "backend/agent_runtime/cognitive_swarm_manifest.py",
        "backend/agent_runtime/skills/",
    ),
    "ui_accessibility": (
        "scripts/sovereign-backend/controller_board.py",
        "src/",
        "apps/",
        "packages/",
    ),
    "predictive_qa": (
        ".github/workflows/",
        "scripts/sovereign-backend/tests/",
        "backend/tests/",
        "scripts/sovereign-backend/agent_runtime/tool_events.py",
        "scripts/sovereign-backend/agent_runtime/tool_runner.py",
        "scripts/sovereign-backend/agent_runtime/tools/",
        "backend/agent_runtime/tool_events.py",
        "backend/agent_runtime/tool_runner.py",
        "backend/agent_runtime/tools/",
    ),
}

READ_REPOSITORY_TOOL_NAMES: Final[tuple[str, ...]] = (
    "read_repository_file",
    "scan_repository_family",
    "inspect_repository_status",
    "inspect_repository_diff",
    "run_repository_test",
)
WRITE_REPOSITORY_TOOL_NAMES: Final[tuple[str, ...]] = (
    "apply_exact_repository_patch",
    "write_repository_file",
)

_SECRET_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"github_pat_[A-Za-z0-9_]{16,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"Authorization:\s*(?:Bearer\s+)?[^\s\n]+", re.IGNORECASE),
)


def _close(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def _safe_path(value: str) -> str:
    normalized = str(value or "").strip().replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or pure.is_absolute()
        or ".." in pure.parts
        or any(part in {".git", ".env", "node_modules", "__pycache__", ".pytest_cache"} for part in pure.parts)
    ):
        raise ValueError("repository path is unsafe")
    return pure.as_posix()


def _path_in_role_scope(role: str, path: str) -> bool:
    for prefix in ROLE_PATH_PREFIXES.get(role, ()):
        if prefix == "__workspace_all__":
            return True
        if prefix.endswith("/") and path.startswith(prefix):
            return True
        if path == prefix:
            return True
    return False


def _redact(text: str, limit: int = 40_000) -> str:
    bounded = str(text or "")[:limit]
    for pattern in _SECRET_VALUE_PATTERNS:
        bounded = pattern.sub("[REDACTED]", bounded)
    return bounded


def _qualified_test_execution_kind(action: str, result: ToolResult) -> str:
    if str(action or "").strip().lower() != "test":
        return "none"
    metadata = dict(result.metadata or {})
    command = str(metadata.get("command") or "").strip().lower()
    framework = str(metadata.get("framework") or "").strip().lower()
    qualifying_prefixes = (
        "python -m pytest",
        "python3 -m pytest",
        "pytest",
        "pnpm test",
        "pnpm run test",
        "pnpm exec vitest run",
        "npm test",
        "npm run test",
        "npx vitest run",
        "npx jest",
        "go test",
        "cargo test",
    )
    if command.startswith(qualifying_prefixes) or framework in {"pytest", "jest", "vitest", "go test", "cargo test", "npm"}:
        return "qualifying-test"
    return "nonqualifying-test"


def _merge_job_evidence(job: Any, result: ToolResult) -> ToolResult:
    return ToolResult(
        tool=result.tool,
        allowed=result.allowed,
        status=result.status,
        stdout=result.stdout,
        stderr=result.stderr,
        output=result.output,
        error=result.error,
        metadata=result.metadata,
        changed_files=result.changed_files or job.changed_files,
        diff_summary=result.diff_summary or job.diff_summary,
        test_summary=result.test_summary or job.test_summary,
        blocker=result.blocker,
        exit_code=result.exit_code,
        events=result.events,
        predictive_signal=result.predictive_signal,
    )


@dataclass(frozen=True)
class RepositoryFleetBindings:
    """One real repository-worker schedule bound to a cloned workspace readback.

    The object is deliberately transient: canonical task/evidence persistence remains
    in ``agent_tasks``/``agent_evidence``.  It supplies the exact plan and worker
    assignment envelope that the execution path must persist before model workers
    may receive repository tools.
    """

    plan: FleetPlan
    task_ids_by_role: dict[str, str]
    assignments_by_role: dict[str, FleetWorkerAssignment]
    repository: str
    workspace_id: str
    base_revision: str


FLEET_ATTEMPT_SNAPSHOT_SCHEMA_VERSION: Final[str] = "sovereign.fleet.active-attempt-snapshot.v1"


@dataclass(frozen=True)
class FleetAttemptSnapshotBinding:
    """One path-free role binding in a persisted active-attempt snapshot."""

    role: str
    assignment_hash: str
    task_id: str
    attempt_id: str
    attempt_sequence: int
    attempt_hash: str
    worktree_binding_hash: str
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "assignmentHash": self.assignment_hash,
            "taskId": self.task_id,
            "attemptId": self.attempt_id,
            "attemptSequence": self.attempt_sequence,
            "attemptHash": self.attempt_hash,
            "worktreeBindingHash": self.worktree_binding_hash,
            "receiptHash": self.receipt_hash,
        }


@dataclass(frozen=True)
class FleetAttemptSnapshot:
    """Exact path-free controller input for a retry persistence handoff."""

    fleet_plan_hash: str
    controller_run_id: str
    bindings: tuple[FleetAttemptSnapshotBinding, ...]
    attempt_receipts_by_role: dict[str, dict[str, Any]]
    snapshot_hash: str

    @classmethod
    def from_workspaces(
        cls,
        *,
        fleet_bindings: RepositoryFleetBindings,
        workspaces_by_role: Mapping[str, AttemptWorkspace],
    ) -> "FleetAttemptSnapshot":
        if set(workspaces_by_role) != set(fleet_bindings.assignments_by_role):
            raise FleetContractError("Fleet active-attempt snapshot is missing a worker role")
        records: list[FleetAttemptSnapshotBinding] = []
        receipts: dict[str, dict[str, Any]] = {}
        for role in WORKER_ROLES:
            assignment = fleet_bindings.assignments_by_role.get(role)
            workspace = workspaces_by_role.get(role)
            if assignment is None or workspace is None:
                raise FleetContractError("Fleet active-attempt snapshot role is incomplete")
            receipt = workspace.receipt_binding()
            if (
                workspace.run_id != assignment.controller_run_id
                or workspace.task_id != assignment.task_id
                or workspace.assignment_hash != assignment.assignment_hash
                or receipt.get("assignmentHash") != assignment.assignment_hash
                or receipt.get("attemptId") != workspace.attempt_id
                or receipt.get("attemptHash") != workspace.attempt_hash
                or receipt.get("worktreeBindingHash") != workspace.binding_hash
            ):
                raise FleetContractError("Fleet active-attempt snapshot binding is inconsistent")
            receipts[role] = dict(receipt)
            records.append(FleetAttemptSnapshotBinding(
                role=role,
                assignment_hash=assignment.assignment_hash,
                task_id=assignment.task_id,
                attempt_id=workspace.attempt_id,
                attempt_sequence=workspace.attempt_sequence,
                attempt_hash=workspace.attempt_hash,
                worktree_binding_hash=workspace.binding_hash,
                receipt_hash=stable_hash(receipt),
            ))
        payload = {
            "schemaVersion": FLEET_ATTEMPT_SNAPSHOT_SCHEMA_VERSION,
            "fleetPlanHash": fleet_bindings.plan.plan_hash,
            "controllerRunId": fleet_bindings.plan.integration_id,
            "bindings": [record.to_dict() for record in records],
        }
        return cls(
            fleet_plan_hash=fleet_bindings.plan.plan_hash,
            controller_run_id=fleet_bindings.plan.integration_id,
            bindings=tuple(records),
            attempt_receipts_by_role=receipts,
            snapshot_hash=stable_hash(payload),
        )


@dataclass(frozen=True)
class FleetAttemptSnapshotEvidence:
    """Durable evidence returned by the snapshot observer before activation."""

    fleet_plan_hash: str
    controller_run_id: str
    snapshot_hash: str
    evidence_id: str
    evidence_sha256: str

    def verify_for(self, snapshot: FleetAttemptSnapshot) -> None:
        if (
            self.fleet_plan_hash != snapshot.fleet_plan_hash
            or self.controller_run_id != snapshot.controller_run_id
            or self.snapshot_hash != snapshot.snapshot_hash
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,159}", self.evidence_id)
            or not re.fullmatch(r"[0-9a-f]{64}", self.evidence_sha256)
        ):
            raise FleetContractError("Fleet retry snapshot persistence receipt is not bound to the candidate")


def _required_worker_task_ids(task_ids_by_agent: dict[str, str]) -> dict[str, str]:
    resolved = {
        role: str(task_ids_by_agent.get(role) or "").strip()
        for role in WORKER_ROLES
    }
    if any(not task_id for task_id in resolved.values()):
        raise FleetContractError("every repository worker requires one persisted task id")
    if len(set(resolved.values())) != len(resolved):
        raise FleetContractError("repository worker task ids must be unique")
    return resolved


def build_repository_fleet_bindings(
    *,
    run_id: str,
    repository: str,
    workspace_id: str,
    workspace_branch: str,
    base_revision: str,
    task_ids_by_agent: dict[str, str],
) -> RepositoryFleetBindings:
    """Build the fail-closed FleetPlan used by real repository worker execution.

    The current runtime has one physical Agent Job clone.  Until #1524 provides
    separate attempt worktrees and an architecture receipt proves non-overlap, every
    worker shares its workspace mutation/lock scope and therefore receives a serial
    lane.  This is a deliberate safety property, not a claim that workers are
    independent.
    """

    role_task_ids = _required_worker_task_ids(task_ids_by_agent)
    normalized_repository = str(repository or "").strip()
    normalized_workspace = str(workspace_id or "").strip()
    normalized_branch = str(workspace_branch or "").strip()
    normalized_run = str(run_id or "").strip()
    if not normalized_repository or not normalized_workspace or not normalized_branch or not normalized_run:
        raise FleetContractError("repository Fleet binding requires run, repository and workspace identity")

    shared_scope = f"workspace:{normalized_workspace}"
    tasks = tuple(
        FleetTask(
            task_id=role_task_ids[role],
            source_type="integration_step",
            source_id=role,
            expected_base_revision=base_revision,
            changed_paths=ROLE_PATH_PREFIXES[role],
            architecture_domains=("repository_execution", role),
            canonical_owners=(role,),
            invariant_scopes=(shared_scope,),
            required_gates=("git_readback", "agent_tool_receipt"),
            required_capabilities=READ_REPOSITORY_TOOL_NAMES + WRITE_REPOSITORY_TOOL_NAMES,
            mutation_resources=(shared_scope,),
            lock_scopes=(shared_scope,),
            # No architecture receipt currently proves these role scopes independent.
            independence_proven=False,
        )
        for role in WORKER_ROLES
    )
    plan = build_fleet_plan(
        integration_id=normalized_run,
        repository=normalized_repository,
        base_revision=base_revision,
        tasks=tasks,
        architecture_receipt_hashes=(),
        max_parallel_lanes=len(WORKER_ROLES),
    )
    manifest_hash = canonical_sha256(manifest_payload())
    run_envelope_hash = canonical_sha256({
        "schemaVersion": "sovereign.repository-fleet-envelope.v1",
        "runId": normalized_run,
        "repository": normalized_repository,
        "workspaceId": normalized_workspace,
        "workspaceBranch": normalized_branch,
        "baseRevision": base_revision,
        "fleetPlanHash": plan.plan_hash,
    })
    assignments: dict[str, FleetWorkerAssignment] = {}
    for lane in plan.lanes:
        for task_id in lane.task_ids:
            role = next(role for role, bound_task_id in role_task_ids.items() if bound_task_id == task_id)
            assignments[role] = create_worker_assignment(
                plan,
                lane_id=lane.lane_id,
                task_id=task_id,
                controller_run_id=normalized_run,
                workspace_id=normalized_workspace,
                workspace_branch=normalized_branch,
                run_envelope_hash=run_envelope_hash,
                capability_manifest_hash=manifest_hash,
            )
    if set(assignments) != set(WORKER_ROLES):
        raise FleetContractError("FleetPlan did not assign every repository worker")
    return RepositoryFleetBindings(
        plan=plan,
        task_ids_by_role=role_task_ids,
        assignments_by_role=assignments,
        repository=normalized_repository,
        workspace_id=normalized_workspace,
        base_revision=base_revision,
    )


def create_repository_swarm_tasks(
    conn: Any,
    *,
    run_id: str,
    evidence_id: str,
    write_confirmed: bool,
) -> dict[str, str]:
    """Persist dispatcher, six worker and judge tasks for one repository-backed swarm run."""

    task_ids: dict[str, str] = {}
    forbidden = (
        "persist or reveal secrets",
        "write outside the assigned role paths",
        "merge a pull request",
        "deploy to production",
        "claim success without tool, diff and test evidence",
    )
    dispatcher_id = f"task-dispatcher-{uuid.uuid4().hex}"
    create_agent_task(
        conn,
        run_id=run_id,
        task_id=dispatcher_id,
        agent_id="dispatcher",
        specialist_role="orchestration",
        work_package="Interpret the mission plan already classified by the routed LLM and assign exactly six bounded repository work packages.",
        evidence_id=evidence_id,
        status="QUEUED",
        next_action="CREATE_SIX_ROLE_PLAN",
        acceptance_criteria=("Exactly six worker packages are ordered.", "No repository mutation is claimed by the dispatcher."),
        forbidden_actions=forbidden,
        max_tool_calls=0,
        commit=False,
    )
    task_ids["dispatcher"] = dispatcher_id

    allowed_tools = (*READ_REPOSITORY_TOOL_NAMES, *(WRITE_REPOSITORY_TOOL_NAMES if write_confirmed else ()))
    for role in WORKER_ROLES:
        task_id = f"task-{role}-{uuid.uuid4().hex}"
        create_agent_task(
            conn,
            run_id=run_id,
            task_id=task_id,
            agent_id=role,
            specialist_role=role,
            work_package=ROLE_WORK_PACKAGES[role],
            evidence_id=evidence_id,
            status="QUEUED",
            next_action="WAIT_FOR_DISPATCHER_PLAN",
            allowed_files=ROLE_PATH_PREFIXES[role],
            allowed_tools=allowed_tools,
            acceptance_criteria=(
                "At least one real repository tool call is persisted for this role.",
                "Every finding names evidence from the linked isolated workspace.",
                "Any mutation is exact, SHA-bound and followed by status, diff and relevant test evidence.",
                "Predictive follow-up failures are derived to depth three when a finding exists.",
            ),
            forbidden_actions=forbidden,
            max_tool_calls=30,
            max_retries=2,
            commit=False,
        )
        task_ids[role] = task_id

    judge_id = f"task-judge-{uuid.uuid4().hex}"
    create_agent_task(
        conn,
        run_id=run_id,
        task_id=judge_id,
        agent_id="judge",
        specialist_role="evidence_controller",
        work_package="Reject unsupported claims and accept readiness only after all six roles used tools and the linked job has changed-file, diff and test evidence.",
        evidence_id=evidence_id,
        status="QUEUED",
        next_action="WAIT_FOR_SIX_WORKER_REPORTS",
        acceptance_criteria=(
            "All six role task states and tool-call records are present.",
            "The linked Agent Job passes the repository evidence gate.",
            "Learning remains pending until validated solution or blocker evidence exists.",
            "At most one Draft PR is allowed and auto-merge is disabled.",
        ),
        forbidden_actions=forbidden,
        max_tool_calls=0,
        commit=False,
    )
    task_ids["judge"] = judge_id
    conn.commit()
    return task_ids


def create_repository_single_agent_task(
    conn: Any,
    *,
    run_id: str,
    evidence_id: str,
    write_confirmed: bool,
) -> str:
    """Persist exactly one coding task for the free single-agent profile."""
    task_id = f"free-agent-work-{uuid.uuid4().hex}"
    allowed_tools = (
        *READ_REPOSITORY_TOOL_NAMES,
        *(WRITE_REPOSITORY_TOOL_NAMES if write_confirmed else ()),
    )
    create_agent_task(
        conn,
        run_id=run_id,
        task_id=task_id,
        agent_id="free_single_agent",
        specialist_role="free_single_agent",
        work_package=ROLE_WORK_PACKAGES["free_single_agent"],
        evidence_id=evidence_id,
        status="QUEUED",
        next_action="EXECUTE_SINGLE_AGENT_WORKSPACE_MISSION",
        allowed_files=("isolated_code_server_workspace",),
        allowed_tools=allowed_tools,
        acceptance_criteria=(
            "The single agent uses real workspace tools before making repository claims.",
            "Every write remains inside the isolated Agent Job repository clone.",
            "Status, diff and at least one relevant test are read after mutation.",
            "No background agent, production deploy, merge or auto-merge is started.",
        ),
        forbidden_actions=(
            "persist or reveal secrets",
            "write outside the isolated workspace",
            "start background agents",
            "merge a pull request",
            "deploy to production",
            "claim success without tool, diff and test evidence",
        ),
        max_tool_calls=40,
        max_retries=2,
        commit=True,
    )
    return task_id


def _require_function_tool() -> Callable[..., Any]:
    module = importlib.import_module("agents")
    factory = getattr(module, "function_tool", None)
    if not callable(factory):
        raise RuntimeError("OpenAI Agents SDK function_tool API is unavailable")
    return factory


@dataclass
class BoundRepositoryToolset:
    get_connection: ConnectionFactory
    user_id: str
    run_id: str
    job_id: str
    task_ids_by_agent: dict[str, str]
    workspace_root: Path | None
    write_confirmed: bool = False
    fleet_bindings: RepositoryFleetBindings | None = None
    _call_counts: dict[str, int] = field(default_factory=dict)
    _mutation_counts: dict[str, int] = field(default_factory=dict)
    _consecutive_failures: dict[str, int] = field(default_factory=dict)
    _open_circuits: set[str] = field(default_factory=set)
    _active_fleet_lane_id: str | None = None
    _active_fleet_roles: frozenset[str] = field(default_factory=frozenset)
    _fleet_attempts_by_role: dict[str, FleetWorkerAttempt] = field(default_factory=dict)
    _active_fleet_attempts_by_role: dict[str, FleetWorkerAttempt] = field(default_factory=dict)
    _fleet_workspaces_by_role: dict[str, AttemptWorkspace] = field(default_factory=dict)
    _settled_fleet_attempts_by_id: dict[str, FleetWorkerAttempt] = field(default_factory=dict)
    _settled_fleet_workspaces_by_attempt_id: dict[str, AttemptWorkspace] = field(default_factory=dict)
    _fleet_attempt_workspace_snapshot_observer: Callable[[FleetAttemptSnapshot], FleetAttemptSnapshotEvidence] | None = None
    _fleet_attempt_rebind_pending: bool = False
    _lock: Lock = field(default_factory=Lock)

    def has_repository_fleet_workers(self) -> bool:
        return set(WORKER_ROLES).issubset(self.task_ids_by_agent)

    def resolve_fleet_bindings(self) -> RepositoryFleetBindings:
        """Read the exact cloned repository identity before any worker is scheduled."""

        if not self.has_repository_fleet_workers():
            raise FleetContractError("the toolset does not contain all six repository workers")
        if self.workspace_root is None:
            raise FleetContractError("repository Fleet execution requires an isolated workspace root")
        conn = self.get_connection()
        try:
            job = read_agent_job(conn, user_id=self.user_id, job_id=self.job_id)
            if not job:
                raise FleetContractError("linked Sovereign Agent Job was not found")
            workspace_id = str(job.workspace_id or self.job_id).strip()
            repository_path = repo_dir_for_workspace(workspace_id, self.workspace_root)
            git_identity = read_git_workspace_identity(repository_path, repository=job.repo_url)
            repository_url = str(job.repo_url or "").strip().removesuffix(".git")
            prefix = "https://github.com/"
            if not repository_url.startswith(prefix):
                raise FleetContractError("repository Fleet execution requires a GitHub repository URL")
            repository = repository_url[len(prefix):]
            return build_repository_fleet_bindings(
                run_id=self.run_id,
                repository=repository,
                workspace_id=workspace_id,
                workspace_branch=str(job.branch or "main"),
                base_revision=git_identity.base_commit_sha,
                task_ids_by_agent=self.task_ids_by_agent,
            )
        finally:
            _close(conn)

    def bind_fleet_execution(self, bindings: RepositoryFleetBindings) -> None:
        if not self.has_repository_fleet_workers():
            raise FleetContractError("the toolset does not contain all six repository workers")
        if set(bindings.task_ids_by_role) != set(WORKER_ROLES):
            raise FleetContractError("Fleet bindings are missing a worker role")
        if any(
            self.task_ids_by_agent.get(role) != task_id
            for role, task_id in bindings.task_ids_by_role.items()
        ):
            raise FleetContractError("Fleet bindings do not match persisted worker tasks")
        with self._lock:
            if self._fleet_attempt_rebind_pending:
                raise FleetContractError("Fleet bindings cannot change during a pending retry transition")
            if self.fleet_bindings and self.fleet_bindings.plan.plan_hash != bindings.plan.plan_hash:
                raise FleetContractError("a different FleetPlan is already bound to this toolset")
            self.fleet_bindings = bindings

    def set_fleet_attempt_workspace_snapshot_observer(
        self,
        observer: Callable[[FleetAttemptSnapshot], FleetAttemptSnapshotEvidence],
    ) -> None:
        """Install the required persistence hook for active-attempt transitions.

        The hook receives a typed, path-free snapshot and must return a durable
        evidence receipt for that exact plan/role/assignment/attempt binding.
        Retrying a worker without recording its new active attempt would leave
        reconnect consumers unable to distinguish a retained historical worktree
        from the current one, so rebinding fails closed until this observer is
        installed.
        """

        if not callable(observer):
            raise FleetContractError("Fleet attempt snapshot observer is invalid")
        with self._lock:
            if self._active_fleet_lane_id is not None or self._fleet_attempt_rebind_pending:
                raise FleetContractError("Fleet attempt snapshot observer cannot change during an active lane")
            if self._fleet_attempt_workspace_snapshot_observer is not None:
                raise FleetContractError("Fleet attempt snapshot observer is immutable once installed")
            self._fleet_attempt_workspace_snapshot_observer = observer

    def provision_fleet_attempt_workspaces(self) -> dict[str, AttemptWorkspace]:
        """Create deterministic physical worktrees before repository workers run.

        Attempt identity is generated from the already server-bound assignment; callers
        cannot choose an attempt id, branch, or worktree path.  A later retry must
        bind a fresh attempt explicitly instead of reusing this mapping.
        """

        bindings = self.fleet_bindings
        if bindings is None or self.workspace_root is None:
            raise FleetContractError("Fleet attempt worktrees require a bound plan and workspace root")
        conn = self.get_connection()
        try:
            job = read_agent_job(conn, user_id=self.user_id, job_id=self.job_id)
            if not job:
                raise FleetContractError("linked Sovereign Agent Job was not found")
            workspace_id = str(job.workspace_id or self.job_id).strip()
            if workspace_id != bindings.workspace_id:
                raise FleetContractError("Fleet attempt worktree workspace changed after plan binding")
            repository_url = str(job.repo_url or "").strip()
            with self._lock:
                if self._active_fleet_lane_id is not None or self._fleet_attempt_rebind_pending:
                    raise FleetContractError("Fleet attempt worktrees cannot change during an active lane")
                existing_attempts = dict(self._active_fleet_attempts_by_role)
                existing_workspaces = dict(self._fleet_workspaces_by_role)
            expected_roles = frozenset(bindings.assignments_by_role)
            if existing_attempts or existing_workspaces:
                if frozenset(existing_attempts) != expected_roles or frozenset(existing_workspaces) != expected_roles:
                    raise FleetContractError("Fleet active attempt bindings are incomplete")
                attempts = existing_attempts
            else:
                attempts = {
                    role: create_worker_attempt(assignment, attempt_sequence=1)
                    for role, assignment in bindings.assignments_by_role.items()
                }
            workspaces = {
                role: provision_attempt_worktree(
                    assignment=assignment,
                    attempt=attempts[role],
                    active_attempt=attempts[role],
                    repository_url=repository_url,
                    root=self.workspace_root,
                )
                for role, assignment in bindings.assignments_by_role.items()
            }
            with self._lock:
                if self._active_fleet_lane_id is not None or self._fleet_attempt_rebind_pending:
                    raise FleetContractError("Fleet attempt worktrees cannot change during an active lane")
                if existing_attempts and self._active_fleet_attempts_by_role != existing_attempts:
                    raise FleetContractError("Fleet active attempt changed while worktrees were being read back")
                self._fleet_attempts_by_role = attempts
                self._active_fleet_attempts_by_role = dict(attempts)
                self._fleet_workspaces_by_role = workspaces
            return dict(workspaces)
        finally:
            _close(conn)

    def rebind_fleet_attempt_workspace(
        self,
        role: str,
        active_attempt: FleetWorkerAttempt,
    ) -> AttemptWorkspace:
        """Atomically make one higher, server-issued retry attempt active.

        This is a controller-only transition: a caller supplies no path or branch,
        and the higher attempt must round-trip through the hash-bound
        ``FleetWorkerAttempt`` contract for this role's existing assignment.  The
        previous worktree remains retained by attempt id until an explicit
        controller release authorizes targeted cleanup.
        """

        bindings = self.fleet_bindings
        if bindings is None or self.workspace_root is None:
            raise FleetContractError("Fleet attempt rebind requires a bound plan and workspace root")
        assignment = bindings.assignments_by_role.get(role)
        if assignment is None:
            raise FleetContractError("repository worker is not bound to a Fleet assignment")
        if not isinstance(active_attempt, FleetWorkerAttempt):
            raise FleetContractError("Fleet attempt rebind requires a server-issued FleetWorkerAttempt")
        # Reparse to reject a forged dataclass with fields that do not bind its hash.
        selected = FleetWorkerAttempt.from_dict(active_attempt.to_dict())
        require_active_attempt(selected, selected, assignment)
        replacement: AttemptWorkspace | None = None
        repository_url = ""
        pending = False
        with self._lock:
            if self._active_fleet_lane_id is not None:
                raise FleetContractError("Fleet attempt worktrees cannot change during an active lane")
            if self._fleet_attempt_rebind_pending:
                raise FleetContractError("another Fleet retry transition is already pending")
            previous_attempt = self._active_fleet_attempts_by_role.get(role)
            previous_workspace = self._fleet_workspaces_by_role.get(role)
            if previous_attempt is None or previous_workspace is None:
                raise FleetContractError("Fleet attempt rebind requires an existing active worktree")
            if selected.attempt_sequence <= previous_attempt.attempt_sequence:
                raise FleetContractError("Fleet retry attempt sequence must be higher than the active attempt")
            snapshot_observer = self._fleet_attempt_workspace_snapshot_observer
            if snapshot_observer is None:
                # Check before provisioning: an unrecorded retry worktree is not a
                # reconnect target and must never be created merely to discover
                # that no persistence handoff was installed.
                raise FleetContractError("Fleet retry rebind requires a persisted active-attempt snapshot observer")
            # Fence provisioning, durable evidence and the in-memory active switch
            # as one serialized transition.  No lane can start or observer change
            # while the candidate is being persisted.
            self._fleet_attempt_rebind_pending = True
            pending = True
        try:
            conn = self.get_connection()
            try:
                job = read_agent_job(conn, user_id=self.user_id, job_id=self.job_id)
                if not job:
                    raise FleetContractError("linked Sovereign Agent Job was not found")
                workspace_id = str(job.workspace_id or self.job_id).strip()
                if workspace_id != assignment.workspace_id:
                    raise FleetContractError("Fleet attempt worktree workspace changed after assignment")
                repository_url = str(job.repo_url or "").strip()
                replacement = provision_attempt_worktree(
                    assignment=assignment,
                    attempt=selected,
                    active_attempt=selected,
                    repository_url=repository_url,
                    root=self.workspace_root,
                )
            finally:
                _close(conn)
            with self._lock:
                if (
                    self._active_fleet_lane_id is not None
                    or not self._fleet_attempt_rebind_pending
                    or self._active_fleet_attempts_by_role.get(role) != previous_attempt
                    or self._fleet_workspaces_by_role.get(role) != previous_workspace
                    or self._fleet_attempt_workspace_snapshot_observer is not snapshot_observer
                ):
                    raise FleetContractError("Fleet retry binding changed during candidate provisioning")
                workspaces = dict(self._fleet_workspaces_by_role)
                workspaces[role] = replacement
            snapshot = FleetAttemptSnapshot.from_workspaces(
                fleet_bindings=bindings,
                workspaces_by_role=workspaces,
            )
            persisted = snapshot_observer(snapshot)
            if not isinstance(persisted, FleetAttemptSnapshotEvidence):
                raise FleetContractError("Fleet retry observer did not return a typed persistence receipt")
            persisted.verify_for(snapshot)
            with self._lock:
                if (
                    self._active_fleet_lane_id is not None
                    or not self._fleet_attempt_rebind_pending
                    or self._active_fleet_attempts_by_role.get(role) != previous_attempt
                    or self._fleet_workspaces_by_role.get(role) != previous_workspace
                    or self._fleet_attempt_workspace_snapshot_observer is not snapshot_observer
                ):
                    raise FleetContractError("Fleet retry binding changed before activation")
                self._settled_fleet_attempts_by_id[previous_attempt.attempt_id] = previous_attempt
                self._settled_fleet_workspaces_by_attempt_id[previous_attempt.attempt_id] = previous_workspace
                self._fleet_attempts_by_role[role] = selected
                self._active_fleet_attempts_by_role[role] = selected
                self._fleet_workspaces_by_role[role] = replacement
                self._fleet_attempt_rebind_pending = False
                pending = False
            return replacement
        except Exception:
            if replacement is not None:
                try:
                    discard_unpersisted_attempt_worktree(
                        assignment=assignment,
                        attempt=selected,
                        current_active_attempt=previous_attempt,
                        attempt_workspace=replacement,
                        repository_url=repository_url,
                        root=self.workspace_root,
                    )
                except Exception as cleanup_exc:
                    raise FleetContractError("Fleet retry rebind failed and candidate cleanup failed") from cleanup_exc
            raise
        finally:
            if pending:
                with self._lock:
                    self._fleet_attempt_rebind_pending = False

    def settled_fleet_attempt_receipts(self) -> dict[str, dict[str, Any]]:
        """Return controller-visible, path-free retained-attempt evidence only."""

        with self._lock:
            return {
                attempt_id: workspace.receipt_binding()
                for attempt_id, workspace in self._settled_fleet_workspaces_by_attempt_id.items()
            }

    def cleanup_released_fleet_attempt_workspace(self, release: AttemptWorktreeRelease) -> None:
        """Apply one explicit controller release to one retained attempt worktree."""

        if not isinstance(release, AttemptWorktreeRelease):
            raise FleetContractError("Fleet attempt cleanup requires a controller release")
        bindings = self.fleet_bindings
        if bindings is None or self.workspace_root is None:
            raise FleetContractError("Fleet attempt cleanup requires a bound plan and workspace root")
        with self._lock:
            settled_attempt = self._settled_fleet_attempts_by_id.get(release.attempt_id)
            settled_workspace = self._settled_fleet_workspaces_by_attempt_id.get(release.attempt_id)
            role = next(
                (
                    worker_role
                    for worker_role, candidate in bindings.assignments_by_role.items()
                    if candidate.task_id == release.task_id
                    and candidate.assignment_hash == release.assignment_hash
                ),
                None,
            )
            assignment = bindings.assignments_by_role.get(role) if role is not None else None
            active_attempt = self._active_fleet_attempts_by_role.get(role) if role is not None else None
        if settled_attempt is None or settled_workspace is None or assignment is None or active_attempt is None:
            raise FleetContractError("Fleet attempt cleanup target is not a retained controller attempt")
        conn = self.get_connection()
        try:
            job = read_agent_job(conn, user_id=self.user_id, job_id=self.job_id)
            if not job:
                raise FleetContractError("linked Sovereign Agent Job was not found")
            cleanup_settled_attempt_worktree(
                assignment=assignment,
                attempt=settled_attempt,
                active_attempt=active_attempt,
                attempt_workspace=settled_workspace,
                release=release,
                repository_url=str(job.repo_url or "").strip(),
                root=self.workspace_root,
            )
        finally:
            _close(conn)
        with self._lock:
            if self._settled_fleet_workspaces_by_attempt_id.get(release.attempt_id) == settled_workspace:
                self._settled_fleet_workspaces_by_attempt_id.pop(release.attempt_id, None)
                self._settled_fleet_attempts_by_id.pop(release.attempt_id, None)

    def _resolve_active_fleet_worktree(
        self,
        *,
        role: str,
        assignment: FleetWorkerAssignment,
        job: Any,
    ) -> tuple[FleetWorkerAttempt, AttemptWorkspace]:
        """Resolve only the current server-bound worktree for one worker action."""

        if self.workspace_root is None:
            raise FleetContractError("Fleet attempt worktree requires an isolated workspace root")
        with self._lock:
            attempt = self._fleet_attempts_by_role.get(role)
            active_attempt = self._active_fleet_attempts_by_role.get(role)
            workspace = self._fleet_workspaces_by_role.get(role)
        if attempt is None or active_attempt is None or workspace is None:
            raise FleetContractError("repository Fleet worker has no active attempt worktree binding")
        selected = require_active_attempt(attempt, active_attempt, assignment)
        workspace_id = str(job.workspace_id or self.job_id).strip()
        if workspace_id != assignment.workspace_id:
            raise FleetContractError("Fleet attempt worktree job workspace changed after assignment")
        refreshed = resolve_active_attempt_worktree(
            assignment=assignment,
            attempt=selected,
            active_attempt=active_attempt,
            attempt_workspace=workspace,
            repository_url=str(job.repo_url or "").strip(),
            root=self.workspace_root,
        )
        with self._lock:
            self._fleet_workspaces_by_role[role] = refreshed
        return selected, refreshed

    def read_fleet_workspace_head(self) -> str:
        """Re-read every active Fleet attempt head before a worker pass.

        The outer Agent Job clone is only the immutable provenance boundary.  It
        must never stand in for a worker's physical worktree readback: every role
        in the bound plan needs an active, server-derived attempt binding first.
        A Fleet plan is still based on one exact revision, so a committed attempt
        head is intentionally rejected here rather than silently being used as a
        later lane's preflight base.  A later Draft-PR flow must use the explicit
        attempt handoff gate instead.
        """

        bindings = self.fleet_bindings
        if bindings is None or self.workspace_root is None:
            raise FleetContractError("Fleet workspace readback requires a bound plan and workspace root")
        conn = self.get_connection()
        try:
            job = read_agent_job(conn, user_id=self.user_id, job_id=self.job_id)
            if not job:
                raise FleetContractError("linked Sovereign Agent Job was not found")
            workspace_id = str(job.workspace_id or self.job_id).strip()
            if workspace_id != bindings.workspace_id:
                raise FleetContractError("Fleet workspace identity changed after plan binding")
            with self._lock:
                provisioned_roles = frozenset(self._fleet_workspaces_by_role)
            expected_roles = frozenset(bindings.assignments_by_role)
            if provisioned_roles != expected_roles:
                raise FleetContractError("Fleet workspace readback requires every active attempt worktree")
            observed_heads = {
                role: self._resolve_active_fleet_worktree(
                    role=role,
                    assignment=assignment,
                    job=job,
                )[1].head_revision
                for role, assignment in bindings.assignments_by_role.items()
            }
            if any(head != bindings.base_revision for head in observed_heads.values()):
                raise FleetContractError(
                    "Fleet attempt worktree heads no longer match the plan base revision"
                )
            return bindings.base_revision
        finally:
            _close(conn)

    @contextmanager
    def activate_fleet_lane(self, lane_id: str, roles: tuple[str, ...]) -> Iterator[None]:
        """Admit repository tools only for the exact roles in one current Fleet lane."""

        bindings = self.fleet_bindings
        if bindings is None:
            raise FleetContractError("repository Fleet tools require a bound FleetPlan")
        lane = next((item for item in bindings.plan.lanes if item.lane_id == lane_id), None)
        if lane is None:
            raise FleetContractError("Fleet lane is not part of the bound plan")
        expected_roles = frozenset(
            role
            for role, task_id in bindings.task_ids_by_role.items()
            if task_id in lane.task_ids
        )
        actual_roles = frozenset(roles)
        if not actual_roles or actual_roles != expected_roles:
            raise FleetContractError("Fleet lane roles do not match the bound plan")
        with self._lock:
            if self._active_fleet_lane_id is not None or self._fleet_attempt_rebind_pending:
                raise FleetContractError("another Fleet lane is already active")
            self._active_fleet_lane_id = lane_id
            self._active_fleet_roles = actual_roles
        try:
            yield
        finally:
            with self._lock:
                if self._active_fleet_lane_id == lane_id:
                    self._active_fleet_lane_id = None
                    self._active_fleet_roles = frozenset()

    def _assert_fleet_lane_admission(self, role: str, task_id: str) -> FleetWorkerAssignment | None:
        bindings = self.fleet_bindings
        if bindings is None:
            return None
        assignment = bindings.assignments_by_role.get(role)
        if assignment is None or assignment.task_id != task_id:
            raise FleetContractError("repository worker is not bound to the Fleet assignment")
        with self._lock:
            active_lane = self._active_fleet_lane_id
            active_roles = self._active_fleet_roles
        if active_lane != assignment.lane_id or role not in active_roles:
            raise FleetContractError("repository worker attempted a tool outside its active Fleet lane")
        return assignment

    def allowed_paths(self, role: str) -> tuple[str, ...]:
        if role == "free_single_agent":
            return (".",)
        return ROLE_PATH_PREFIXES.get(role, ())

    def allowed_tool_names(self, role: str) -> tuple[str, ...]:
        return (
            (*READ_REPOSITORY_TOOL_NAMES, *WRITE_REPOSITORY_TOOL_NAMES)
            if self.write_confirmed
            else READ_REPOSITORY_TOOL_NAMES
        )

    def _validate_role_path(self, role: str, path: str) -> str:
        normalized = _safe_path(path)
        if role not in ROLE_PATH_PREFIXES:
            raise ValueError("unknown repository worker role")
        if not _path_in_role_scope(role, normalized):
            raise ValueError("repository path is outside the worker role boundary")
        return normalized

    def _record_call(self, role: str, *, mutation: bool, failed: bool) -> None:
        with self._lock:
            self._call_counts[role] = self._call_counts.get(role, 0) + 1
            if mutation:
                self._mutation_counts[role] = self._mutation_counts.get(role, 0) + 1
            if failed:
                failures = self._consecutive_failures.get(role, 0) + 1
                self._consecutive_failures[role] = failures
                if failures >= 3:
                    self._open_circuits.add(role)
            else:
                self._consecutive_failures[role] = 0

    def _assert_circuit_closed(self, role: str) -> None:
        with self._lock:
            if role in self._open_circuits:
                raise RuntimeError("repository tool circuit is open after three consecutive failures")

    def _execute(self, role: str, action: str, parameters: dict[str, Any], *, mutation: bool = False) -> str:
        self._assert_circuit_closed(role)
        task_id = self.task_ids_by_agent.get(role)
        if not task_id:
            raise LookupError("repository worker task is missing")
        if self.workspace_root is None:
            raise RuntimeError("repository tool receipt requires a real isolated workspace")
        conn = self.get_connection()
        tool_call_id = ""
        job: Any = None
        before_git: Any = None
        mcp_identity: Any = None
        assignment: FleetWorkerAssignment | None = None
        attempt: FleetWorkerAttempt | None = None
        attempt_workspace: AttemptWorkspace | None = None
        repository_path: Path | None = None
        try:
            assignment = self._assert_fleet_lane_admission(role, task_id)
            job = read_agent_job(conn, user_id=self.user_id, job_id=self.job_id)
            if not job:
                raise LookupError("linked Sovereign Agent Job was not found")
            if assignment is not None:
                attempt, attempt_workspace = self._resolve_active_fleet_worktree(
                    role=role,
                    assignment=assignment,
                    job=job,
                )
                repository_path = attempt_workspace.worktree_path
            else:
                repository_path = repo_dir_for_workspace(
                    str(job.workspace_id or self.job_id),
                    self.workspace_root,
                )
            before_git = read_git_workspace_identity(
                repository_path,
                repository=job.repo_url,
            )
            mcp_identity = read_mcp_runtime_identity(
                expected_revision=before_git.base_commit_sha,
            )
            receipt_arguments = dict(parameters)
            if assignment is not None:
                receipt_arguments["fleetBinding"] = {
                    "planHash": assignment.plan_hash,
                    "assignmentHash": assignment.assignment_hash,
                    "laneId": assignment.lane_id,
                    "taskId": assignment.task_id,
                }
                receipt_arguments["fleetAttempt"] = attempt.to_dict() if attempt else {}
                receipt_arguments["attemptWorktree"] = (
                    attempt_workspace.receipt_binding() if attempt_workspace else {}
                )
            tool_call_id = start_agent_tool_call(
                conn,
                run_id=self.run_id,
                task_id=task_id,
                agent_id=role,
                tool_name=action,
                arguments=receipt_arguments,
                mutating=mutation,
            )
            result = run_agent_job_tool(self.job_id, action, parameters, repository_path)
            merged = _merge_job_evidence(job, result)
            gate = append_tool_result_to_job(conn, self.job_id, merged)
            if assignment is not None:
                attempt, attempt_workspace = self._resolve_active_fleet_worktree(
                    role=role,
                    assignment=assignment,
                    job=job,
                )
            after_git = read_git_workspace_identity(
                repository_path,
                repository=job.repo_url,
            )
            mutation_performed = bool(
                mutation
                and result.status == "done"
                and before_git.diff_sha256 != after_git.diff_sha256
            )
            gate_result = (
                "PASS"
                if gate.passed
                else "BLOCKED"
                if result.status == "blocked"
                else "FAIL"
            )
            canonical_receipt = finish_agent_tool_call(
                conn,
                tool_call_id=tool_call_id,
                status=(
                    "COMPLETED"
                    if result.status == "done"
                    else "BLOCKED"
                    if result.status == "blocked"
                    else "FAILED_RECOVERABLE"
                ),
                result_summary={
                    "status": result.status,
                    "exitCode": int(result.exit_code or 0),
                    "predictiveSignal": result.predictive_signal,
                    "changedFiles": list(merged.changed_files),
                    "hasDiff": bool(merged.diff_summary),
                    "hasTests": bool(merged.test_summary),
                    "evidencePassed": gate.passed,
                    **({
                        "fleetPlanHash": assignment.plan_hash,
                        "assignmentHash": assignment.assignment_hash,
                        "fleetLaneId": assignment.lane_id,
                        "fleetTaskId": assignment.task_id,
                        "fleetAttempt": attempt.to_dict() if attempt else {},
                        "attemptWorktree": attempt_workspace.receipt_binding() if attempt_workspace else {},
                    } if assignment is not None else {}),
                },
                repository=job.repo_url,
                base_commit_sha=before_git.base_commit_sha,
                mcp_revision=mcp_identity.revision,
                mcp_image_digest=mcp_identity.image_digest,
                mcp_revision_verified=mcp_identity.revision_verified,
                operation_identity=(
                    f"agent-repository-tool:{role}:{action}:fleet:{assignment.plan_hash}:assignment:{assignment.assignment_hash}:attempt:{attempt.attempt_id if attempt else 'missing'}:worktree:{attempt_workspace.binding_hash if attempt_workspace else 'missing'}"
                    if assignment is not None
                    else f"agent-repository-tool:{role}:{action}"
                ),
                diff_sha256=after_git.diff_sha256,
                test_evidence_sha256=canonical_sha256({
                    "exit_code": int(result.exit_code or 0),
                    "test_summary": merged.test_summary or "",
                }),
                evidence_gate_result=gate_result,
                mutation_performed=mutation_performed,
                observed_effect=(
                    "workspace-write"
                    if mutation_performed
                    else "read"
                    if not mutation
                    else "none"
                ),
                authoritative_readback_sha256=after_git.authoritative_readback_sha256,
                test_execution_kind=_qualified_test_execution_kind(action, result),
                changed_paths=after_git.changed_paths,
                failure_family=(
                    None if result.status == "done" else "AGENT_REPOSITORY_TOOL_BLOCKED"
                    if result.status == "blocked" else "AGENT_REPOSITORY_TOOL_FAILED"
                ),
            )
            if assignment is not None and attempt is not None and attempt_workspace is not None:
                # Best-effort display side channel only. Failure cannot alter the
                # canonical tool result, receipt or controller state.
                try:
                    context = LiveWorkspaceContextResolver(workspace_root=self.workspace_root)(conn, job)
                    if context is not None and context.role == role:
                        receipt_hash = str(canonical_receipt.get("header", {}).get("hash") or "")
                        projection_result = ToolResult(
                            tool=merged.tool,
                            allowed=merged.allowed,
                            status=merged.status,
                            stdout=merged.stdout,
                            stderr=merged.stderr,
                            output=merged.output,
                            error=merged.error,
                            metadata={
                                **dict(merged.metadata or {}),
                                "actionId": tool_call_id,
                                "providerNeutralEvidenceSha256": receipt_hash,
                            },
                            changed_files=merged.changed_files,
                            diff_summary=merged.diff_summary,
                            test_summary=merged.test_summary,
                            blocker=merged.blocker,
                            exit_code=merged.exit_code,
                            events=merged.events,
                            predictive_signal=merged.predictive_signal,
                        )
                        projection = projection_for_tool_result(
                            job=job,
                            attempt_workspace=context.attempt_workspace,
                            route_action=action,
                            parameters=parameters,
                            result=projection_result,
                            session=context.session,
                            reconciliation=context.reconciliation,
                        )
                        anchor = WorkspaceEvidenceAnchorV1.from_agent_run_receipt(
                            session=context.session,
                            receipt=canonical_receipt,
                            observation_event=projection,
                            observed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        )
                        append_agent_projection(
                            conn,
                            job_id=self.job_id,
                            projection=public_projection_event(projection),
                        )
                        append_agent_evidence_anchor(
                            conn,
                            job_id=self.job_id,
                            anchor=anchor.to_dict(),
                        )
                except Exception:
                    pass
        except Exception as exc:
            self._record_call(role, mutation=False, failed=True)
            if tool_call_id and job is not None and before_git is not None and mcp_identity is not None and repository_path is not None:
                try:
                    failed_git = read_git_workspace_identity(
                        repository_path,
                        repository=job.repo_url,
                    )
                    finish_agent_tool_call(
                        conn,
                        tool_call_id=tool_call_id,
                        status="FAILED_RECOVERABLE",
                        result_summary={"errorType": type(exc).__name__},
                        repository=job.repo_url,
                        base_commit_sha=before_git.base_commit_sha,
                        mcp_revision=mcp_identity.revision,
                        mcp_image_digest=mcp_identity.image_digest,
                        mcp_revision_verified=mcp_identity.revision_verified,
                        operation_identity=(
                            f"agent-repository-tool:{role}:{action}:fleet:{assignment.plan_hash}:assignment:{assignment.assignment_hash}:attempt:{attempt.attempt_id if attempt else 'missing'}:worktree:{attempt_workspace.binding_hash if attempt_workspace else 'missing'}"
                            if assignment is not None
                            else f"agent-repository-tool:{role}:{action}"
                        ),
                        diff_sha256=failed_git.diff_sha256,
                        test_evidence_sha256=canonical_sha256({"exit_code": 1, "test_summary": ""}),
                        evidence_gate_result="FAIL",
                        mutation_performed=False,
                        observed_effect="none" if mutation else "read",
                        authoritative_readback_sha256=failed_git.authoritative_readback_sha256,
                        failure_family="AGENT_REPOSITORY_TOOL_EXECUTION_FAILED",
                    )
                except Exception:
                    pass
            raise
        finally:
            _close(conn)
        self._record_call(
            role,
            mutation=mutation_performed,
            failed=result.status != "done",
        )
        safe_metadata = {
            key: result.metadata.get(key)
            for key in ("path", "bytes", "sha256", "count", "mode", "family", "recommendedTestCommand")
            if isinstance(result.metadata, dict) and key in result.metadata
        }
        payload = {
            "tool": action,
            "status": result.status,
            "output": _redact(result.output or result.stdout or ""),
            "error": _redact(result.error or result.stderr or "", 2_000),
            "blocker": _redact(result.blocker or "", 2_000),
            "changedFiles": list(merged.changed_files),
            "diffSummary": _redact(merged.diff_summary or "", 20_000),
            "testSummary": _redact(merged.test_summary or "", 20_000),
            "predictiveSignal": result.predictive_signal,
            "metadata": safe_metadata,
            "evidence": {
                "passed": gate.passed,
                "reason": _redact(gate.reason, 2_000),
                "canPrepareDraftPr": gate.can_prepare_draft_pr,
                "canLearnPattern": gate.can_learn_pattern,
            },
        }
        if assignment is not None and attempt is not None and attempt_workspace is not None:
            payload["fleetAttempt"] = attempt.to_dict()
            payload["attemptWorktree"] = attempt_workspace.receipt_binding()
        findings = result.metadata.get("findings") if isinstance(result.metadata, dict) else None
        if isinstance(findings, list):
            payload["findings"] = findings[:20]
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def tools_for_role(self, role: str) -> list[Any]:
        if role not in ROLE_PATH_PREFIXES:
            return []
        function_tool = _require_function_tool()
        allowed_paths = self.allowed_paths(role)

        def read_repository_file(path: str, max_bytes: int = 120_000) -> str:
            """Read one UTF-8 repository file inside this worker's assigned path boundary."""
            target = self._validate_role_path(role, path)
            bounded = max(1_000, min(int(max_bytes), 300_000))
            return self._execute(role, "file", {"mode": "read", "path": target, "maxBytes": bounded})

        def scan_repository_family(family: str) -> str:
            """Run the deterministic Janitor scan only inside this worker's assigned repository paths."""
            return self._execute(role, "janitor", {
                "mode": "scan",
                "family": str(family or "runtime evidence handoff")[:300],
                "paths": list(allowed_paths),
                "maxFindings": 18,
                "maxFiles": 300,
                "includeDocs": role == "chat_cognitive",
                "explainWithLocalModel": False,
            })

        def inspect_repository_status() -> str:
            """Read real Git status evidence from the linked isolated workspace."""
            return self._execute(role, "git-status", {})

        def inspect_repository_diff(path: str = "") -> str:
            """Read the current Git diff, optionally restricted to one role-scoped file."""
            parameters: dict[str, Any] = {"stat": False, "staged": False}
            if str(path or "").strip():
                parameters["file"] = self._validate_role_path(role, path)
            return self._execute(role, "diff", parameters)

        def run_repository_test(command: str) -> str:
            """Run one allowlisted repository test command and persist its result as runtime evidence."""
            bounded = str(command or "").strip()[:500]
            if not bounded:
                raise ValueError("test command is required")
            return self._execute(role, "test", {"command": bounded, "timeout": 600, "verbose": True})

        tools = [
            function_tool(read_repository_file),
            function_tool(scan_repository_family),
            function_tool(inspect_repository_status),
            function_tool(inspect_repository_diff),
            function_tool(run_repository_test),
        ]
        if self.write_confirmed:
            def write_repository_file(path: str, content: str) -> str:
                """Create or fully replace one UTF-8 file inside the assigned workspace boundary."""
                target = self._validate_role_path(role, path)
                bounded_content = str(content or "")
                if len(bounded_content.encode("utf-8")) > 500_000:
                    raise ValueError("repository file content exceeds the bounded write limit")
                return self._execute(
                    role,
                    "file",
                    {"mode": "write", "path": target, "content": bounded_content, "append": False},
                    mutation=True,
                )

            def apply_exact_repository_patch(
                path: str,
                search_text: str,
                replacement_text: str,
                expected_sha256: str,
            ) -> str:
                """Apply one exact SHA-bound SEARCH/REPLACE inside this worker's assigned path boundary."""
                target = self._validate_role_path(role, path)
                return self._execute(role, "janitor", {
                    "mode": "apply",
                    "path": target,
                    "searchText": search_text,
                    "replacementText": replacement_text,
                    "expectedSha256": expected_sha256,
                    "confirm": True,
                }, mutation=True)

            tools.extend((
                function_tool(write_repository_file),
                function_tool(apply_exact_repository_patch),
            ))
        return tools

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "runId": self.run_id,
                "jobId": self.job_id,
                "writeConfirmed": self.write_confirmed,
                "callsByRole": dict(self._call_counts),
                "mutationsByRole": dict(self._mutation_counts),
                "consecutiveFailuresByRole": dict(self._consecutive_failures),
                "openCircuits": sorted(self._open_circuits),
                "rolesWithCalls": sorted(role for role, count in self._call_counts.items() if count > 0),
                "rolesWithMutations": sorted(role for role, count in self._mutation_counts.items() if count > 0),
                "fleetPlanHash": self.fleet_bindings.plan.plan_hash if self.fleet_bindings else None,
                "activeFleetLaneId": self._active_fleet_lane_id,
            }
