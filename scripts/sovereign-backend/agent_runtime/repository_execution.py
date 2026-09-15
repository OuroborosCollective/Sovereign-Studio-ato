"""Single-Agent repository execution through one Agent Zero A2A task.

This is intentionally not a cognitive-swarm adapter.  Sovereign owns the
persisted job, repository clone, shared workspace, evidence closeout and Draft-PR
gates. Agent Zero is one bounded external implementation worker only.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Final
import uuid

from .agent_zero_a2a import (
    AgentZeroA2AClient,
    AgentZeroA2AError,
    AgentZeroA2ASubmitOutcomeUnknown,
    AgentZeroA2ATaskLost,
)
from .contracts import SovereignAgentEvent, sanitize_agent_text
from .draft_pr_gate import draft_pr_input_from_job, prepare_draft_pr
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


ConnectionFactory = Callable[[], Any]
A2AClientFactory = Callable[[], AgentZeroA2AClient]

_REPOSITORY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_A2A_NORMAL_PREFIX: Final[str] = "agent-zero-a2a:"
_A2A_RETRY_PREFIX: Final[str] = "agent-zero-a2a:retry:"
_A2A_CLAIM_PREFIX: Final[str] = "agent-zero-a2a:claim:"
_MAX_CLOSEOUT_DIFF_BYTES: Final[int] = 2_000_000
_MAX_CLOSEOUT_CHANGED_FILES: Final[int] = 50

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
_DOCUMENTATION_ONLY_SUFFIXES: Final[frozenset[str]] = frozenset({".md", ".mdx", ".rst", ".txt"})
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


def _repository_stall_seconds() -> float:
    return _bounded_env_seconds("SOVEREIGN_REPOSITORY_STALL_SECONDS", 1800.0, 300.0, 86400.0)


def _job_age_seconds(job: StoredSovereignAgentJob) -> float | None:
    observed = job.updated_at or job.created_at
    if not isinstance(observed, datetime):
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds())


def _configured_repository_url() -> str:
    value = os.getenv(
        "SOVEREIGN_CONTROLLER_REPOSITORY",
        "OuroborosCollective/Sovereign-Studio-ato",
    ).strip()
    if not _REPOSITORY_PATTERN.fullmatch(value):
        raise RepositoryExecutionError("SOVEREIGN_CONTROLLER_REPOSITORY is invalid")
    return f"https://github.com/{value}"


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
    return f"{_A2A_CLAIM_PREFIX}{kind}:{digest}:{uuid.uuid4().hex}"


def _normal_ref(task_id: str) -> str:
    return f"{_A2A_NORMAL_PREFIX}{task_id}"


def _retry_ref(task_id: str) -> str:
    return f"{_A2A_RETRY_PREFIX}{task_id}"


def _bound_task(external_ref: str) -> tuple[str, bool] | None:
    if external_ref.startswith(_A2A_RETRY_PREFIX):
        task_id = external_ref[len(_A2A_RETRY_PREFIX):]
        return (task_id, True) if task_id else None
    if external_ref.startswith(_A2A_NORMAL_PREFIX) and not external_ref.startswith(_A2A_CLAIM_PREFIX):
        task_id = external_ref[len(_A2A_NORMAL_PREFIX):]
        return (task_id, False) if task_id else None
    return None


def is_repository_a2a_job(job: StoredSovereignAgentJob | None) -> bool:
    return bool(job and str(job.external_ref or "").startswith(_A2A_NORMAL_PREFIX))


def _block_job(conn: Any, job: StoredSovereignAgentJob, reason: str, stage: str) -> StoredSovereignAgentJob:
    blocker = sanitize_agent_text(reason, 1200) or "Repository execution blocked."
    update_agent_job_state(conn, job_id=job.job_id, status="blocked", blocker=blocker)
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage=stage,
        level="warning",
        message=blocker,
    ))
    return read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job


def _submit_after_claim(
    conn: Any,
    *,
    job: StoredSovereignAgentJob,
    claim_ref: str,
    retry: bool,
    a2a_client_factory: A2AClientFactory,
) -> StoredSovereignAgentJob:
    try:
        task = a2a_client_factory().submit_repository_task(
            workspace_id=str(job.workspace_id or job.job_id),
            mission=job.mission,
        )
    except AgentZeroA2ASubmitOutcomeUnknown as exc:
        return _block_job(
            conn,
            job,
            f"{exc.family}: task acceptance is unknown; automatic resubmit is forbidden.",
            "agent_zero_a2a_submit_outcome_unknown",
        )
    except AgentZeroA2AError as exc:
        return _block_job(
            conn,
            job,
            f"{exc.family}: {exc.next_action}",
            "agent_zero_a2a_submit_failed",
        )

    target_ref = _retry_ref(task.task_id) if retry else _normal_ref(task.task_id)
    if not compare_and_swap_agent_job_external_ref(
        conn,
        job_id=job.job_id,
        expected_ref=claim_ref,
        new_ref=target_ref,
    ):
        return _block_job(
            conn,
            job,
            "Agent Zero task was submitted but its persisted binding could not be finalized; refusing any resubmit.",
            "agent_zero_a2a_binding_finalize_failed",
        )
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="agent_zero_a2a_retry_submitted" if retry else "agent_zero_a2a_submitted",
        level="success",
        message=(
            "Exactly one restart-recovery Agent Zero A2A task was submitted nonblocking."
            if retry
            else "Exactly one Agent Zero A2A task was submitted nonblocking."
        ),
    ))
    return read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job


def start_repository_execution(
    conn: Any,
    *,
    user_id: str,
    body: dict[str, Any],
    github_access_token: object = None,
    workspace_root: Path | None = None,
    a2a_client_factory: A2AClientFactory = AgentZeroA2AClient.from_env,
) -> StoredSovereignAgentJob:
    """Persist/clone one repository job, then submit exactly one A2A task."""

    payload = _normalized_repository_payload(body)
    lifecycle = create_sovereign_agent_job(
        conn,
        user_id=user_id,
        payload=payload,
        github_access_token=github_access_token,
        workspace_root=workspace_root,
        provision_workspace=True,
        clone_repo=True,
    )
    job = read_agent_job(conn, user_id=user_id, job_id=lifecycle.job_id)
    if job is None:
        raise RepositoryExecutionError("persisted repository job readback is missing")
    if job.status != "running":
        return job

    claim_ref = _claim("submit", job.job_id)
    if not compare_and_swap_agent_job_external_ref(
        conn,
        job_id=job.job_id,
        expected_ref=None,
        new_ref=claim_ref,
    ):
        # Another caller already owns the external-effect boundary. Never submit.
        return read_agent_job(conn, user_id=user_id, job_id=job.job_id) or job
    claimed = read_agent_job(conn, user_id=user_id, job_id=job.job_id) or job
    return _submit_after_claim(
        conn,
        job=claimed,
        claim_ref=claim_ref,
        retry=False,
        a2a_client_factory=a2a_client_factory,
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


def _documentation_only_changes(changed_files: tuple[str, ...]) -> bool:
    return bool(changed_files) and all(
        Path(path).suffix.casefold() in _DOCUMENTATION_ONLY_SUFFIXES
        for path in changed_files
    )


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
            status_result.blocker or status_result.error or "Agent Zero completed without workspace changes.",
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

    documentation_only = _documentation_only_changes(tuple(status_result.changed_files))
    commands = () if documentation_only else _safe_regression_commands(
        janitor.metadata.get("recommendedTestCommand") if isinstance(janitor.metadata, dict) else None
    )
    test_outputs: list[str] = []
    if documentation_only:
        # ``git_diff_check`` above already executed against the canonical repository
        # worktree. For documentation-only mutations that real result is the
        # appropriate regression evidence; do not route Git through TestTool's
        # workspace-shell cwd or require an unrelated Node toolchain.
        test_outputs.append("git diff --check: passed")
    elif commands:
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

    diff_summary = sanitize_agent_text(patch.decode("utf-8", errors="replace"), 4000)
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
            "Draft-PR preparation succeeded but the Agent Zero closeout binding could not be restored.",
            "repository_closeout_binding_restore_failed",
        )
    append_agent_event(conn, evidenced.job_id, SovereignAgentEvent(
        stage="repository_ready_for_draft_pr",
        level="success",
        message="Sovereign independently verified workspace diff, regression, Janitor and Evidence Gate. Draft PR creation still requires the explicit user action.",
    ))
    return read_agent_job(conn, user_id=evidenced.user_id, job_id=evidenced.job_id) or evidenced


def _recover_lost_original_task(
    conn: Any,
    *,
    job: StoredSovereignAgentJob,
    bound_ref: str,
    task_id: str,
    workspace_root: Path | None,
    a2a_client_factory: A2AClientFactory,
) -> StoredSovereignAgentJob:
    claim_ref = _claim("retry", task_id)
    if not compare_and_swap_agent_job_external_ref(
        conn,
        job_id=job.job_id,
        expected_ref=bound_ref,
        new_ref=claim_ref,
    ):
        return read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job
    claimed = read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="agent_zero_a2a_original_task_lost",
        level="warning",
        message="The persisted original Agent Zero task is gone; Sovereign must inspect the shared workspace before any one-time recovery submit.",
    ))

    workspace_status = run_agent_job_tool(claimed, "git-status", {}, workspace_root)
    if workspace_status.status != "done":
        return _block_job(
            conn,
            claimed,
            workspace_status.blocker
            or workspace_status.error
            or "The lost Agent Zero task workspace could not be read safely; automatic resubmit is forbidden.",
            "agent_zero_a2a_lost_task_workspace_unverified",
        )
    if workspace_status.changed_files:
        append_agent_event(conn, job.job_id, SovereignAgentEvent(
            stage="agent_zero_a2a_lost_task_workspace_recovered",
            level="success",
            message="The lost Agent Zero task already left real workspace changes; Sovereign will verify those changes instead of submitting a duplicate task.",
        ))
        return _closeout_repository_job(
            conn,
            job=claimed,
            claim_ref=claim_ref,
            bound_ref=bound_ref,
            workspace_root=workspace_root,
        )

    return _submit_after_claim(
        conn,
        job=claimed,
        claim_ref=claim_ref,
        retry=True,
        a2a_client_factory=a2a_client_factory,
    )


def reconcile_repository_execution(
    conn: Any,
    *,
    user_id: str,
    job_id: str,
    workspace_root: Path | None = None,
    a2a_client_factory: A2AClientFactory = AgentZeroA2AClient.from_env,
) -> StoredSovereignAgentJob | None:
    """Read/reconcile one persisted repository job without spawning duplicates."""

    job = read_agent_job(conn, user_id=user_id, job_id=job_id)
    if job is None or job.status != "running" or not is_repository_a2a_job(job):
        return job
    external_ref = str(job.external_ref or "")
    if external_ref.startswith(_A2A_CLAIM_PREFIX):
        # Another request owns the side-effect boundary. A stale claim requires
        # operator evidence rather than an automatic duplicate submit.
        return job
    binding = _bound_task(external_ref)
    if binding is None:
        return _block_job(
            conn,
            job,
            "Persisted Agent Zero A2A binding is invalid.",
            "agent_zero_a2a_binding_invalid",
        )
    task_id, is_retry = binding
    try:
        task = a2a_client_factory().get_task(task_id)
    except AgentZeroA2ATaskLost:
        if is_retry:
            return _block_job(
                conn,
                job,
                "The one restart-recovery Agent Zero task is also lost; no further resubmit is allowed.",
                "agent_zero_a2a_retry_task_lost",
            )
        return _recover_lost_original_task(
            conn,
            job=job,
            bound_ref=external_ref,
            task_id=task_id,
            workspace_root=workspace_root,
            a2a_client_factory=a2a_client_factory,
        )
    except AgentZeroA2AError as exc:
        raise RepositoryExecutionTransientError(
            f"{exc.family}: task readback is unavailable; no resubmit was performed"
        ) from exc

    if task.active:
        age_seconds = _job_age_seconds(job)
        if age_seconds is not None and age_seconds >= _repository_stall_seconds():
            return _block_job(
                conn,
                job,
                (
                    "AGENT_ZERO_A2A_STALLED: the external task remained active beyond the "
                    "bounded server reconciliation window; workspace publication is quarantined "
                    "and automatic resubmit is forbidden."
                ),
                "agent_zero_a2a_task_stalled",
            )
        return job
    if task.interrupted:
        return _block_job(
            conn,
            job,
            f"Agent Zero A2A task requires unsupported external input/state: {task.state}.",
            "agent_zero_a2a_task_interrupted",
        )
    if task.failed:
        return _block_job(
            conn,
            job,
            f"Agent Zero A2A task terminated without successful completion: {task.state}.",
            "agent_zero_a2a_task_failed",
        )
    if not task.completed:
        return _block_job(
            conn,
            job,
            f"Agent Zero A2A task returned unsupported state: {task.state}.",
            "agent_zero_a2a_task_state_invalid",
        )

    claim_ref = _claim("closeout", task_id)
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
    """Reconcile persisted A2A repository jobs without any client polling.

    The scan only discovers already-bound tasks. ``reconcile_repository_execution``
    retains the CAS ownership for retry and closeout, so this worker cannot create a
    second Agent Zero task or duplicate Draft-PR preparation.
    """

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
                "repository A2A reconcile failed job=%s type=%s",
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
    """Start one process-local daemon that owns A2A lifecycle reconciliation.

    Multiple backend processes remain safe: active-task reads are side-effect free
    and every retry/closeout effect is still protected by the existing persisted
    ``external_ref`` compare-and-swap boundary. On process restart the fresh daemon
    scans the database again, so client presence is never required for completion.
    """

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
                        "repository A2A reconcile cycle failed type=%s",
                        type(exc).__name__,
                    )
                time.sleep(_repository_reconciler_poll_seconds())

        _RECONCILER_THREAD = threading.Thread(
            target=loop,
            name="sovereign-repository-a2a-reconciler",
            daemon=True,
        )
        _RECONCILER_THREAD.start()
        return True
