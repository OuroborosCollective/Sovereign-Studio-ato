"""Single-Agent repository execution through Sovereign's internal executor.

Sovereign owns the persisted job, repository checkout, workspace mutation,
evidence closeout and Draft-PR gates. No external execution worker is used.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Final
import uuid

from .contracts import SovereignAgentEvent, sanitize_agent_text
from .cognitive_repository_tools import BoundRepositoryToolset, create_repository_single_agent_task
from .cognitive_run_store import (
    create_agent_run,
    read_agent_run,
    read_agent_task_ids,
    record_agent_stage_event,
    transition_agent_run,
)
from .cognitive_swarm_agents import MissionIntent, run_free_single_agent
from .draft_pr_gate import draft_pr_input_from_job, prepare_draft_pr
from .durable_workflow import (
    PermissionDecision,
    StepKind,
    WorkflowBinding,
    WorkflowDefinition,
    WorkflowStep,
    approve_permission,
    canonical_sha256,
    create_permission_request,
)
from .durable_workflow_store import (
    append_permission_receipt,
    bind_repository_job_permission,
    persist_workflow_run,
    read_latest_permission_receipt,
    read_permission_authority_head,
)
from .revocation_closure import RevocationClosureError, require_live_permission
from .rescue import resolve_github_head
from .evidence_gate import EvidenceGateInput, evaluate_agent_evidence
from .git_workspace import git_diff_check, git_diff_full
from .job_lifecycle import create_sovereign_agent_job
from .job_store import (
    StoredSovereignAgentJob,
    append_agent_event,
    compare_and_swap_agent_job_external_ref,
    list_reconcilable_repository_jobs,
    mark_draft_pr_prepared,
    read_agent_job,
    update_agent_job_state,
)
from .tool_runner import run_agent_job_tool
from .workspace_policy import repo_dir_for_workspace, validate_workspace_relative_path
from llm_execution_resolver import FREE_SINGLE_AGENT_PROFILE, load_execution_resolution
from llm_transport import route_provider_model


ConnectionFactory = Callable[[], Any]

_REPOSITORY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_EXECUTOR_PREFIX: Final[str] = "sovereign-local-runner:"
_EXECUTOR_RETRY_PREFIX: Final[str] = "sovereign-local-runner:retry:"
_EXECUTOR_PENDING_PREFIX: Final[str] = "sovereign-local-runner:pending:submit:"
_EXECUTOR_CLAIM_PREFIX: Final[str] = "sovereign-local-runner:claim:"
_MAX_CLOSEOUT_DIFF_BYTES: Final[int] = 2_000_000
_MAX_CLOSEOUT_CHANGED_FILES: Final[int] = 50
_MAX_DOCUMENTATION_REGRESSION_BYTES: Final[int] = 1_000_000
_DOCUMENTATION_SUFFIXES: Final[frozenset[str]] = frozenset({".md", ".mdx", ".rst"})
_DOCUMENTATION_ROOT_FILES: Final[frozenset[str]] = frozenset({
    "README.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md",
    "AGENTS.md", "AGENTS_SKILLS.md", "AGENTS_BEST_PRACTICES.md", "AGENTS_KNOWLEDGE.md", "Memory.md",
})

_ALLOWED_REGRESSION_PREFIXES: Final[tuple[tuple[str, ...], ...]] = (
    ("python", "-m", "pytest"),
    ("python3", "-m", "pytest"),
    ("pytest",),
    ("pnpm", "test"),
    ("pnpm", "run", "test"),
    ("pnpm", "exec", "vitest", "run"),
    ("npm", "test"),
    ("npm", "run", "test"),
    ("npx", "vitest", "run"),
    ("npx", "jest"),
    ("go", "test"),
    ("cargo", "test"),
)
_SHELL_CONTROL_TOKENS: Final[frozenset[str]] = frozenset({"||", ";", "|", ">", ">>", "<", "<<", "&"})
_RECONCILER_THREAD_LOCK = threading.Lock()
_RECONCILER_THREAD: threading.Thread | None = None
_LOGGER = logging.getLogger(__name__)


class RepositoryExecutionError(RuntimeError):
    """Fail-closed persisted repository execution error."""


class RepositoryExecutionTransientError(RepositoryExecutionError):
    """A readback failed but no executor side effect may be repeated."""


def _bounded_env_seconds(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _repository_reconciler_poll_seconds() -> float:
    return _bounded_env_seconds("SOVEREIGN_REPOSITORY_RECONCILER_POLL_SECONDS", 2.0, 0.5, 30.0)


def _configured_repository_url() -> str:
    value = os.getenv(
        "SOVEREIGN_CONTROLLER_REPOSITORY",
        "OuroborosCollective/Sovereign-Studio-ato",
    ).strip()
    if not _REPOSITORY_PATTERN.fullmatch(value):
        raise RepositoryExecutionError("SOVEREIGN_CONTROLLER_REPOSITORY is invalid")
    return f"https://github.com/{value}"


def _resolve_expected_head_sha(repo_url: str, branch: str) -> str:
    """Resolve a branch HEAD SHA via the public GitHub API (read-only)."""
    try:
        revision = resolve_github_head(repo_url, branch, token=None)
    except (ValueError, OSError) as exc:
        raise RepositoryExecutionError(
            "repository head could not be resolved for "
            f"{repo_url}#{branch}: {sanitize_agent_text(str(exc), 200)}"
        ) from exc
    sha = str(revision.get("baseSha") or "").strip().lower()
    if not sha:
        raise RepositoryExecutionError(
            f"repository head resolved an empty SHA for {repo_url}#{branch}"
        )
    return sha


def _normalized_repository_payload(body: dict[str, Any]) -> dict[str, Any]:
    mode = str(body.get("mode") or "free").strip().lower()
    agent_mode = str(body.get("agentMode") or "single").strip().lower()
    intent_mode = str(body.get("intentMode") or "repository_execution").strip().lower()
    if mode != "free":
        raise RepositoryExecutionError("repository execution requires mode=free; paid fallback is forbidden")
    if agent_mode != "single":
        raise RepositoryExecutionError("repository execution requires exactly one agent")
    if intent_mode != "repository_execution":
        raise RepositoryExecutionError("repository execution requires intentMode=repository_execution")
    if body.get("allowAutoMerge") is True:
        raise RepositoryExecutionError("repository execution may not auto-merge")

    mission = str(body.get("mission") or "").strip()
    if not mission:
        raise RepositoryExecutionError("repository execution mission is required")
    repo_url = str(body.get("repositoryUrl") or body.get("repoUrl") or _configured_repository_url()).strip()
    branch = str(body.get("repositoryBranch") or body.get("branch") or "main").strip() or "main"
    payload: dict[str, Any] = {
        "repoUrl": repo_url,
        "branch": branch,
        "mission": mission,
        "draftPrOnly": True,
        "allowAutoMerge": False,
    }
    expected_head = str(body.get("expectedHeadSha") or "").strip().lower()
    if expected_head:
        payload["expectedHeadSha"] = expected_head
    return payload


def _claim(kind: str, identity: str = "") -> str:
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16] if identity else "new"
    return f"{_EXECUTOR_CLAIM_PREFIX}{kind}:{digest}:{uuid.uuid4().hex}"


def _executor_ref(job_id: str, retry: bool = False) -> str:
    return f"{_EXECUTOR_RETRY_PREFIX if retry else _EXECUTOR_PREFIX}{job_id}"


def _pending_submit_ref(job_id: str) -> str:
    digest = hashlib.sha256(job_id.encode("utf-8")).hexdigest()[:24]
    return f"{_EXECUTOR_PENDING_PREFIX}{digest}"


def is_repository_executor_job(job: StoredSovereignAgentJob | None) -> bool:
    return bool(job and str(job.external_ref or "").startswith(_EXECUTOR_PREFIX))


def cancel_repository_execution(
    conn: Any,
    *,
    job: StoredSovereignAgentJob,
) -> StoredSovereignAgentJob:
    """Stop the persisted Sovereign-local job without contacting another executor."""
    if job.status in {"completed", "failed", "blocked", "cleaned"}:
        return job
    updated = update_agent_job_state(
        conn,
        job_id=job.job_id,
        status="blocked",
        blocker="Cancelled by owner; Sovereign-local-runner will perform no further work.",
    )
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="sovereign_executor_cancelled",
        level="warning",
        message="Owner cancellation recorded locally; no external executor cancellation is required.",
    ))
    return read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job


def _block_job(conn: Any, job: StoredSovereignAgentJob, reason: str, stage: str) -> StoredSovereignAgentJob:
    blocker = sanitize_agent_text(reason, 1200) or "Repository execution blocked."
    update_agent_job_state(conn, job_id=job.job_id, status="blocked", blocker=blocker)
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage=stage,
        level="warning",
        message=blocker,
    ))
    return read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job


def _ensure_local_single_agent_run(
    get_connection: ConnectionFactory,
    *,
    job: StoredSovereignAgentJob,
) -> tuple[str, str, str]:
    """Create or reuse exactly one persisted Agents-SDK run for this repository job."""
    run_id = f"repo-{job.job_id}"
    session_key = f"repo-session-{job.job_id}"
    trace_id = f"repo-trace-{job.job_id}"
    conn = get_connection()
    try:
        run = read_agent_run(conn, user_id=job.user_id, run_id=run_id)
        if run is None:
            created = create_agent_run(
                conn,
                user_id=job.user_id,
                run_id=run_id,
                session_key=session_key,
                mission=job.mission,
                supplied_evidence="",
                trace_id=trace_id,
                max_active_specialists=1,
                max_iterations=2,
                job_id=job.job_id,
            )
            evidence_id = created["evidenceId"]
            trace_id = created["traceId"]
        else:
            evidence_id = run.evidence_id
            trace_id = run.trace_id
        task_ids = read_agent_task_ids(conn, run_id=run_id)
        task_id = task_ids.get("free_single_agent")
        if not task_id:
            task_id = create_repository_single_agent_task(
                conn,
                run_id=run_id,
                evidence_id=evidence_id,
                write_confirmed=True,
            )
        transition_agent_run(
            conn,
            user_id=job.user_id,
            run_id=run_id,
            status="RUNNING",
            source="agents-sdk",
            trace_id=trace_id,
            reason="Sovereign-local-runner admitted the repository mission to the foreground single agent.",
            next_action="WAIT_FOR_FREE_SINGLE_AGENT",
            evidence_kind="repository_execution_started",
            evidence_summary="A persisted Free single-agent run owns the isolated repository workspace.",
            evidence_payload={
                "jobId": job.job_id,
                "workspaceId": str(job.workspace_id or job.job_id),
                "executor": "sovereign-local-runner",
                "externalExecutor": False,
                "backgroundAgents": 0,
            },
            agent_id="free_single_agent",
            task_id=task_id,
        )
        return run_id, trace_id, task_id
    finally:
        close = getattr(conn, "close", None)
        if callable(close):
            close()


def _submit_after_claim(
    conn: Any,
    *,
    job: StoredSovereignAgentJob,
    claim_ref: str,
    retry: bool,
    workspace_root: Path | None = None,
    get_connection: ConnectionFactory | None = None,
) -> StoredSovereignAgentJob:
    try:
        if not _require_repository_effect_authority(conn, job=job):
            return _block_job(
                conn,
                job,
                "Repository effect path is not bound to a live canonical permission; submit is blocked.",
                "repository_permission_unbound",
            )
    except RevocationClosureError as exc:
        return _block_job(
            conn,
            job,
            f"REVOKED_BEFORE_SOVEREIGN_EFFECT: {exc}",
            "repository_revocation_blocked",
        )

    workspace_id = str(job.workspace_id or job.job_id)
    resolved_connection_factory = get_connection or (lambda: conn)
    repo_path = repo_dir_for_workspace(workspace_id, workspace_root)
    if not repo_path.is_dir() or not (repo_path / ".git").is_dir():
        return _block_job(
            conn,
            job,
            "Sovereign executor workspace repository is unavailable; no external executor fallback is allowed.",
            "sovereign_executor_workspace_missing",
        )

    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="sovereign_executor_started",
        level="success",
        message="Sovereign-local-runner owns repository execution; no external executor is used.",
    ))
    update_agent_job_state(
        conn,
        job_id=job.job_id,
        status="running",
        workspace_id=workspace_id,
        clear_blocker=True,
    )

    try:
        run_id, trace_id, task_id = _ensure_local_single_agent_run(
            resolved_connection_factory,
            job=job,
        )
        resolution = load_execution_resolution(
            resolved_connection_factory,
            user_id=job.user_id,
            requested_mode="free",
        )
        if resolution is None or resolution.profile_id != FREE_SINGLE_AGENT_PROFILE:
            raise RepositoryExecutionError("NO_VERIFIED_FREE_SINGLE_AGENT_ROUTE")
        if not resolution.repository_execution_allowed:
            raise RepositoryExecutionError("REPOSITORY_EXECUTION_NOT_ALLOWED_FOR_FREE_SINGLE_AGENT")
        model = route_provider_model(resolution.primary_route)
        if not model:
            raise RepositoryExecutionError("RESOLVED_FREE_AGENT_MODEL_MISSING")
        repository_toolset = BoundRepositoryToolset(
            get_connection=resolved_connection_factory,
            user_id=job.user_id,
            run_id=run_id,
            job_id=job.job_id,
            task_ids_by_agent={"free_single_agent": task_id},
            workspace_root=repo_path.parent.parent,
            write_confirmed=True,
        )

        def stage_observer(stage: dict[str, object]) -> dict[str, str]:
            stage_conn = resolved_connection_factory()
            try:
                return record_agent_stage_event(
                    stage_conn,
                    user_id=job.user_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    agent_id=str(stage.get("agentId") or "free_single_agent"),
                    event_type=str(stage.get("eventType") or "agent_stage"),
                    status=str(stage.get("status") or "RUNNING"),
                    summary=str(stage.get("summary") or "Sovereign agent stage changed."),
                    next_action=str(stage.get("nextAction") or "WAIT_FOR_FREE_SINGLE_AGENT"),
                    evidence_payload={
                        "jobId": job.job_id,
                        "executor": "sovereign-local-runner",
                        "loop": stage.get("loop"),
                        "repositoryExecution": True,
                        "rawModelOutputPersisted": False,
                    },
                    task_id=task_id,
                )
            finally:
                close = getattr(stage_conn, "close", None)
                if callable(close):
                    close()

        mission_intent = MissionIntent(
            mode="repository_execution",
            normalized_goal=job.mission[:2000],
            requires_online_tools=True,
            requires_repository_workspace=True,
            learning_scope=[],
            confidence=1.0,
        )
        agent_result = asyncio.run(run_free_single_agent(
            job.mission,
            evidence="",
            model=model,
            intent=mission_intent,
            route=resolution.primary_route,
            stage_observer=stage_observer,
            repository_tool_factory=repository_toolset.tools_for_role,
            capability_tool_factory=None,
        ))
        if str(agent_result.get("status") or "BLOCKED") != "COMPLETED":
            return _block_job(
                conn,
                job,
                str(agent_result.get("reason") or agent_result.get("blocker") or "Sovereign single-agent execution was blocked.")[:2000],
                "sovereign_executor_execution_blocked",
            )
        transition_conn = resolved_connection_factory()
        try:
            transition_agent_run(
                transition_conn,
                user_id=job.user_id,
                run_id=run_id,
                status="VERIFYING",
                source="agents-sdk",
                trace_id=trace_id,
                reason="Sovereign-local-runner completed the foreground model pass; repository evidence is being closed out.",
                next_action="VERIFY_SINGLE_AGENT_WORKSPACE_EVIDENCE",
                evidence_kind="repository_execution_completed",
                evidence_summary="Foreground single-agent model execution returned; Git, diff and regression closeout remains authoritative.",
                evidence_payload={
                    "jobId": job.job_id,
                    "executor": "sovereign-local-runner",
                    "repositoryExecutionPerformed": bool(agent_result.get("repositoryExecutionPerformed")),
                    "backgroundAgentsStarted": 0,
                    "rawModelOutputPersisted": False,
                },
                agent_id="free_single_agent",
                task_id=task_id,
            )
        finally:
            close = getattr(transition_conn, "close", None)
            if callable(close):
                close()
    except Exception as exc:
        return _block_job(
            conn,
            job,
            sanitize_agent_text(str(exc), 2000) or "Sovereign-local-runner execution failed closed.",
            "sovereign_executor_execution_failed",
        )

    target_ref = f"sovereign-local-runner:{'retry:' if retry else ''}{job.job_id}"
    if not compare_and_swap_agent_job_external_ref(
        conn,
        job_id=job.job_id,
        expected_ref=claim_ref,
        new_ref=target_ref,
    ):
        return _block_job(
            conn,
            job,
            "Sovereign executor binding could not be finalized; refusing duplicate execution.",
            "sovereign_executor_binding_finalize_failed",
        )

    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="sovereign_executor_bound",
        level="success",
        message=(
            "Sovereign-local-runner bound for restart recovery after verified model execution."
            if retry
            else "Sovereign-local-runner bound as the sole repository executor after verified foreground execution."
        ),
    ))
    return read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job


def _bind_repository_execution_permission(
    conn: Any,
    *,
    job: StoredSovereignAgentJob,
    expected_head_sha: str,
) -> None:
    if not expected_head_sha:
        append_agent_event(conn, job.job_id, SovereignAgentEvent(
            stage="repository_revocation_uncovered",
            level="warning",
            message=(
                "SRCC revocation coverage is unavailable because this repository mission "
                "was not bound to an exact expectedHeadSha."
            ),
        ))
        return

    from .durable_workflow import WorkflowState
    step = WorkflowStep(
        step_id="repository-sovereign-execute",
        kind=StepKind.TOOL_MUTATION,
        allowed_from=(WorkflowState.READY,),
        allowed_to=(WorkflowState.RUNNING,),
        permission_required=True,
        capability="repository.sovereign-execute",
        timeout_seconds=3600,
        max_attempts=2,
        idempotency_key=f"repository-submit:{job.job_id}",
        required_readback_kinds=("sovereign_local_execution",),
    )
    definition = WorkflowDefinition.create(
        workflow_id=f"repository-execution-{job.job_id}",
        steps=(step,),
    )
    binding = WorkflowBinding(
        workflow_run_id=f"repo-run-{job.job_id}",
        workflow_definition_hash=definition.definition_hash,
        owner_identity=str(job.user_id),
        tenant_or_org_identity=str(job.user_id),
        repository_identity=job.repo_url,
        workspace_id=str(job.workspace_id or job.job_id),
        base_revision=expected_head_sha,
        head_revision=expected_head_sha,
    )
    persist_workflow_run(conn, binding)
    requested = create_permission_request(
        binding=binding,
        definition=definition,
        step_id=step.step_id,
        tool_name="sovereign-local-runner",
        parameters={
            "job_id": job.job_id,
            "repository": job.repo_url,
            "branch": job.branch,
            "mission_sha256": canonical_sha256({"mission": job.mission}),
        },
        expected_changed_paths=(),
        valid_until_epoch=int(time.time()) + 21600,
        max_attempts=2,
    )
    append_permission_receipt(conn, receipt=requested, sequence=0)
    approved = approve_permission(
        requested,
        approver_identity=f"owner-{job.user_id}",
        approval_source="repository-run-owner-session",
        observed_epoch=int(time.time()),
    )
    append_permission_receipt(conn, receipt=approved, sequence=1)
    bind_repository_job_permission(conn, job_id=job.job_id, approved_receipt=approved)
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="repository_permission_bound",
        level="success",
        message="Repository submit authority is bound to an append-only permission chain.",
    ))


def start_repository_execution(
    conn: Any,
    *,
    user_id: str,
    body: dict[str, Any],
    workspace_root: Path | None = None,
) -> StoredSovereignAgentJob:
    """Persist one Sovereign-local repository job and queue its local execution."""

    if "githubAccessToken" in body:
        raise RepositoryExecutionError("GITHUB_CREDENTIAL_FORBIDDEN_ON_EXECUTION")

    payload = _normalized_repository_payload(body)
    if not str(payload.get("expectedHeadSha") or "").strip():
        payload["expectedHeadSha"] = _resolve_expected_head_sha(
            str(payload.get("repoUrl") or "").strip(),
            str(payload.get("branch") or "main").strip() or "main",
        )
    lifecycle = create_sovereign_agent_job(
        conn,
        user_id=user_id,
        payload=payload,
        workspace_root=workspace_root,
        provision_workspace=True,
        clone_repo=True,
    )
    job = read_agent_job(conn, user_id=user_id, job_id=lifecycle.job_id)
    if job is None:
        raise RepositoryExecutionError("persisted repository job readback is missing")
    if job.status == "provisioning":
        update_agent_job_state(
            conn,
            job_id=job.job_id,
            status="running",
            workspace_id=str(job.workspace_id or job.job_id),
            clear_blocker=True,
        )
        append_agent_event(conn, job.job_id, SovereignAgentEvent(
            stage="sovereign_repository_checked_out",
            level="success",
            message="Sovereign-local-runner owns repository checkout and execution inside the isolated workspace.",
        ))
        job = read_agent_job(conn, user_id=user_id, job_id=job.job_id) or job
    if job.status != "running":
        return job

    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="repository_execution_contract_bound",
        level="success",
        message=(
            "Repository execution contract bound: Sovereign persists the job, repository state and evidence; "
            "sovereign-local-runner is the sole executor and no external execution worker is allowed."
        ),
    ))
    job = read_agent_job(conn, user_id=user_id, job_id=job.job_id) or job

    _bind_repository_execution_permission(
        conn,
        job=job,
        expected_head_sha=str(payload.get("expectedHeadSha") or "").strip().lower(),
    )

    pending_ref = _pending_submit_ref(job.job_id)
    if not compare_and_swap_agent_job_external_ref(
        conn,
        job_id=job.job_id,
        expected_ref=None,
        new_ref=pending_ref,
    ):
        return read_agent_job(conn, user_id=user_id, job_id=job.job_id) or job
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="sovereign_local_execution_queued",
        level="info",
        message="Sovereign-local-runner execution was durably queued for the server-owned reconciler.",
    ))
    return read_agent_job(conn, user_id=user_id, job_id=job.job_id) or job


def _submit_pending_repository_job(
    conn: Any,
    *,
    job: StoredSovereignAgentJob,
    workspace_root: Path | None = None,
    get_connection: ConnectionFactory | None = None,
) -> StoredSovereignAgentJob:
    """Claim and execute one durable local repository run outside the HTTP request."""

    pending_ref = str(job.external_ref or "")
    if job.status != "running" or not pending_ref.startswith(_EXECUTOR_PENDING_PREFIX):
        return job
    claim_ref = _claim("submit", job.job_id)
    if not compare_and_swap_agent_job_external_ref(
        conn,
        job_id=job.job_id,
        expected_ref=pending_ref,
        new_ref=claim_ref,
    ):
        return read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job
    claimed = read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job
    return _submit_after_claim(
        conn,
        job=claimed,
        claim_ref=claim_ref,
        retry=False,
        workspace_root=workspace_root,
        get_connection=get_connection,
    )


def _safe_regression_commands(recommended: object) -> tuple[str, ...]:
    text = str(recommended or "").strip()
    if not text:
        return ()
    candidates = [segment.strip() for segment in text.split("&&") if segment.strip()]
    selected: list[str] = []
    for candidate in candidates:
        tokens = candidate.split()
        if not tokens or any(token in _SHELL_CONTROL_TOKENS for token in tokens):
            continue
        if any(tuple(tokens[: len(prefix)]) == prefix for prefix in _ALLOWED_REGRESSION_PREFIXES):
            selected.append(candidate)
    return tuple(selected)


def _documentation_only_changed_files(changed_files: object) -> tuple[str, ...] | None:
    if not isinstance(changed_files, (tuple, list)) or not changed_files:
        return None
    normalized: list[str] = []
    for value in changed_files:
        relative = str(value or "").strip()
        try:
            safe = validate_workspace_relative_path(relative)
        except Exception:
            return None
        path = Path(safe)
        if path.suffix.lower() not in _DOCUMENTATION_SUFFIXES:
            return None
        if path.name not in _DOCUMENTATION_ROOT_FILES and (not path.parts or path.parts[0] not in {"docs", ".github"}):
            return None
        normalized.append(safe)
    return tuple(normalized)


def _documentation_regression(
    job: StoredSovereignAgentJob,
    changed_files: object,
    workspace_root: Path | None,
) -> tuple[bool, str] | None:
    documentation = _documentation_only_changed_files(changed_files)
    if documentation is None:
        return None
    try:
        repository = repo_dir_for_workspace(str(job.workspace_id or job.job_id), workspace_root).resolve()
        if not repository.is_dir() or repository.is_symlink():
            return False, "Documentation regression could not verify the repository workspace."
        readme_verified = False
        for relative in documentation:
            target = (repository / relative).resolve()
            if repository not in target.parents or target.is_symlink() or not target.is_file():
                return False, "Documentation regression found an invalid changed-file path."
            if target.stat().st_size > _MAX_DOCUMENTATION_REGRESSION_BYTES:
                return False, "Documentation regression changed-file size exceeds the bounded limit."
            text = target.read_text(encoding="utf-8", errors="strict")
            if "\x00" in text:
                return False, "Documentation regression rejected binary content."
            if Path(relative).name == "README.md":
                lines = text.splitlines()
                if not lines or not lines[0].startswith("# "):
                    return False, "Documentation regression requires README.md to preserve its first Markdown heading."
                readme_verified = True
        summary = (
            f"documentation-regression: {len(documentation)} UTF-8 documentation file(s) verified"
            + ("; README heading preserved" if readme_verified else "")
        )
        return True, summary
    except (OSError, UnicodeError, ValueError):
        return False, "Documentation regression could not read the changed documentation safely."


def _closeout_repository_job(
    conn: Any,
    *,
    job: StoredSovereignAgentJob,
    claim_ref: str,
    bound_ref: str,
    workspace_root: Path | None,
) -> StoredSovereignAgentJob:
    status_result = run_agent_job_tool(job, "git-status", {}, workspace_root)
    if status_result.status != "done" or not status_result.changed_files:
        return _block_job(
            conn,
            job,
            status_result.blocker or status_result.error or "Sovereign-local-runner completed without workspace changes.",
            "repository_closeout_git_status_blocked",
        )

    diff_result = run_agent_job_tool(job, "diff", {"staged": False, "stat": False}, workspace_root)
    if diff_result.status != "done":
        return _block_job(
            conn,
            job,
            diff_result.blocker or diff_result.error or "Workspace diff readback failed.",
            "repository_closeout_diff_blocked",
        )
    patch, full_diff_result = git_diff_full(
        str(job.workspace_id or job.job_id),
        workspace_root,
        max_bytes=_MAX_CLOSEOUT_DIFF_BYTES,
        max_files=_MAX_CLOSEOUT_CHANGED_FILES,
    )
    if full_diff_result.status != "done" or not patch.strip():
        return _block_job(
            conn,
            job,
            full_diff_result.blocker or "Workspace diff is missing.",
            "repository_closeout_diff_missing",
        )

    check_result = git_diff_check(str(job.workspace_id or job.job_id), workspace_root)
    if check_result.status != "done":
        return _block_job(
            conn,
            job,
            check_result.blocker or "git diff --check failed.",
            "repository_closeout_diff_check_blocked",
        )

    janitor = run_agent_job_tool(
        job,
        "janitor",
        {
            "mode": "scan",
            "paths": list(status_result.changed_files),
            "maxFindings": 50,
            "maxFiles": _MAX_CLOSEOUT_CHANGED_FILES,
            "explainWithLocalModel": False,
        },
        workspace_root,
    )
    if janitor.status != "done":
        return _block_job(
            conn,
            job,
            janitor.blocker or janitor.error or "Janitor scan failed.",
            "repository_closeout_janitor_blocked",
        )
    severity_counts = janitor.metadata.get("severityCounts") if isinstance(janitor.metadata, dict) else {}
    if isinstance(severity_counts, dict) and int(severity_counts.get("critical") or 0) > 0:
        return _block_job(
            conn,
            job,
            "Janitor found a critical repository defect in the changed surface.",
            "repository_closeout_janitor_critical",
        )

    # Observed work remains evidence even when the following regression blocks.
    # Do not require passing tests before reporting real workspace changes.
    diff_summary = sanitize_agent_text(patch.decode("utf-8", errors="replace"), 4000)
    update_agent_job_state(
        conn,
        job_id=job.job_id,
        status="running",
        changed_files=status_result.changed_files,
        diff_summary=diff_summary,
    )
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="repository_regression_started",
        level="info",
        message=(
            f"Observed {len(status_result.changed_files)} changed file(s) in the shared workspace. "
            "Diff and Janitor checks passed; independent regression is now pending."
        ),
    ))
    job = read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job

    documentation_regression = _documentation_regression(job, status_result.changed_files, workspace_root)
    test_outputs: list[str] = []
    if documentation_regression is not None:
        documentation_passed, documentation_summary = documentation_regression
        if not documentation_passed:
            return _block_job(
                conn,
                job,
                documentation_summary,
                "repository_closeout_documentation_regression_blocked",
            )
        test_outputs.append(documentation_summary)
    else:
        commands = _safe_regression_commands(
            janitor.metadata.get("recommendedTestCommand") if isinstance(janitor.metadata, dict) else None
        )
        if commands:
            for command in commands:
                test_result = run_agent_job_tool(
                    job,
                    "test",
                    {"command": command, "timeout": 600, "verbose": True},
                    workspace_root,
                )
                if test_result.status != "done":
                    return _block_job(
                        conn,
                        job,
                        test_result.blocker or test_result.error or f"Regression failed: {command}",
                        "repository_closeout_regression_blocked",
                    )
                test_outputs.append(f"{command}: {str(test_result.output or 'passed')[:1200]}")
        else:
            test_result = run_agent_job_tool(
                job,
                "test",
                {"timeout": 600, "verbose": True},
                workspace_root,
            )
            if test_result.status != "done":
                return _block_job(
                    conn,
                    job,
                    test_result.blocker or test_result.error or "Repository regression test failed or was unavailable.",
                    "repository_closeout_regression_blocked",
                )
            test_outputs.append(str(test_result.output or "Auto-detected regression passed.")[:2000])

    test_summary = sanitize_agent_text("\n".join(test_outputs), 4000)
    gate = evaluate_agent_evidence(EvidenceGateInput(
        job_id=job.job_id,
        changed_files=tuple(status_result.changed_files),
        diff_summary=diff_summary,
        test_summary=test_summary,
        can_prepare_draft_pr=True,
    ))
    if not gate.passed or not gate.can_prepare_draft_pr:
        return _block_job(
            conn,
            job,
            gate.reason or "Evidence Gate rejected repository closeout.",
            "repository_closeout_evidence_gate_blocked",
        )

    update_agent_job_state(
        conn,
        job_id=job.job_id,
        status="running",
        changed_files=status_result.changed_files,
        diff_summary=diff_summary,
        test_summary=test_summary,
        clear_blocker=True,
    )
    evidenced = read_agent_job(conn, user_id=job.user_id, job_id=job.job_id)
    if evidenced is None:
        raise RepositoryExecutionError("repository closeout job readback is missing")
    preparation = prepare_draft_pr(draft_pr_input_from_job(evidenced))
    if not preparation.allowed:
        return _block_job(
            conn,
            evidenced,
            "; ".join(preparation.blockers) or preparation.summary,
            "repository_closeout_draft_pr_prepare_blocked",
        )
    mark_draft_pr_prepared(
        conn,
        job_id=evidenced.job_id,
        head_branch=preparation.head_branch or "",
        base_branch=preparation.base_branch or "main",
        title=preparation.title or "Draft: Sovereign agent changes",
        body=preparation.body or "",
    )
    if not compare_and_swap_agent_job_external_ref(
        conn,
        job_id=evidenced.job_id,
        expected_ref=claim_ref,
        new_ref=bound_ref,
    ):
        prepared = read_agent_job(conn, user_id=evidenced.user_id, job_id=evidenced.job_id) or evidenced
        return _block_job(
            conn,
            prepared,
            "Draft-PR preparation succeeded but the Sovereign-local-runner closeout binding could not be restored.",
            "repository_closeout_binding_restore_failed",
        )
    append_agent_event(conn, evidenced.job_id, SovereignAgentEvent(
        stage="repository_ready_for_draft_pr",
        level="success",
        message="Sovereign independently verified workspace diff, regression, Janitor and Evidence Gate. Draft PR creation still requires the explicit user action.",
    ))
    return read_agent_job(conn, user_id=evidenced.user_id, job_id=evidenced.job_id) or evidenced


def reconcile_repository_execution(
    conn: Any,
    *,
    user_id: str,
    job_id: str,
    workspace_root: Path | None = None,
) -> StoredSovereignAgentJob | None:
    """Reconcile one Sovereign-local repository job without external polling."""

    job = read_agent_job(conn, user_id=user_id, job_id=job_id)
    if job is None or job.status != "running":
        return job
    external_ref = str(job.external_ref or "")
    if not external_ref.startswith(_EXECUTOR_PREFIX):
        return job
    if external_ref.startswith(_EXECUTOR_PENDING_PREFIX) or external_ref.startswith(_EXECUTOR_CLAIM_PREFIX):
        return job

    claim_ref = _claim("closeout", job.job_id)
    if not compare_and_swap_agent_job_external_ref(
        conn,
        job_id=job.job_id,
        expected_ref=external_ref,
        new_ref=claim_ref,
    ):
        return read_agent_job(conn, user_id=user_id, job_id=job_id) or job
    claimed = read_agent_job(conn, user_id=user_id, job_id=job_id) or job
    return _closeout_repository_job(
        conn,
        job=claimed,
        claim_ref=claim_ref,
        bound_ref=external_ref,
        workspace_root=workspace_root,
    )

def recover_stalled_repository_job_from_verified_readback(
    conn: Any,
    *,
    user_id: str,
    job_id: str,
    workspace_root: Path | None = None,
) -> tuple[StoredSovereignAgentJob | None, bool]:
    """Recover a blocked local job only when its workspace still contains real evidence."""
    job = read_agent_job(conn, user_id=user_id, job_id=job_id)
    if job is None:
        return None, False
    if job.status != "blocked" or not is_repository_executor_job(job):
        return job, False
    status_result = run_agent_job_tool(job, "git-status", {}, workspace_root)
    if status_result.status != "done" or not status_result.changed_files:
        return job, False
    update_agent_job_state(conn, job_id=job.job_id, status="running", clear_blocker=True)
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="self_healing_workspace_readback_recovered",
        level="success",
        message="Workspace readback proved real changes exist; Sovereign resumed canonical closeout without external execution.",
    ))
    recovered = reconcile_repository_execution(
        conn,
        user_id=user_id,
        job_id=job_id,
        workspace_root=workspace_root,
    )
    return recovered, True

def _close_reconciler_connection(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def reconcile_repository_jobs_once(
    *,
    get_connection: ConnectionFactory,
    workspace_root: Path | None = None,
    limit: int = 50,
) -> dict[str, int]:
    """Reconcile persisted Sovereign-local repository jobs without client-side execution."""

    listing_conn = get_connection()
    try:
        candidates = list_reconcilable_repository_jobs(listing_conn, limit=limit)
    finally:
        _close_reconciler_connection(listing_conn)

    reconciled = 0
    transient_failures = 0
    unexpected_failures = 0
    for candidate in candidates:
        conn = get_connection()
        try:
            if str(candidate.external_ref or "").startswith(_EXECUTOR_PENDING_PREFIX):
                _submit_pending_repository_job(
                    conn,
                    job=candidate,
                    workspace_root=workspace_root,
                    get_connection=get_connection,
                )
            else:
                reconcile_repository_execution(
                    conn,
                    user_id=candidate.user_id,
                    job_id=candidate.job_id,
                    workspace_root=workspace_root,
                )
            reconciled += 1
        except RepositoryExecutionTransientError:
            transient_failures += 1
        except Exception as exc:  # keep the daemon alive; no secret-shaped payload is logged
            unexpected_failures += 1
            _LOGGER.warning(
                "repository local-runner reconcile failed job=%s type=%s",
                candidate.job_id,
                type(exc).__name__,
            )
        finally:
            _close_reconciler_connection(conn)
    return {
        "scanned": len(candidates),
        "reconciled": reconciled,
        "transientFailures": transient_failures,
        "unexpectedFailures": unexpected_failures,
    }


def start_repository_reconciler(
    *,
    get_connection: ConnectionFactory,
    workspace_root: Path | None = None,
) -> bool:
    """Start one process-local daemon that owns Sovereign repository lifecycle reconciliation."""

    global _RECONCILER_THREAD
    with _RECONCILER_THREAD_LOCK:
        if _RECONCILER_THREAD is not None and _RECONCILER_THREAD.is_alive():
            return False

        def loop() -> None:
            while True:
                try:
                    reconcile_repository_jobs_once(
                        get_connection=get_connection,
                        workspace_root=workspace_root,
                    )
                except Exception as exc:
                    _LOGGER.warning(
                        "repository local-runner reconcile cycle failed type=%s",
                        type(exc).__name__,
                    )
                time.sleep(_repository_reconciler_poll_seconds())

        _RECONCILER_THREAD = threading.Thread(
            target=loop,
            name="sovereign-repository-local-reconciler",
            daemon=True,
        )
        _RECONCILER_THREAD.start()
        return True
