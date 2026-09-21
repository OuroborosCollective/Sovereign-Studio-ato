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
from .workspace_policy import repo_dir_for_workspace, validate_workspace_relative_path


ConnectionFactory = Callable[[], Any]
A2AClientFactory = Callable[[], AgentZeroA2AClient]

_REPOSITORY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_A2A_NORMAL_PREFIX: Final[str] = "agent-zero-a2a:"
_A2A_RETRY_PREFIX: Final[str] = "agent-zero-a2a:retry:"
_A2A_PENDING_PREFIX: Final[str] = "agent-zero-a2a:pending:submit:"
_A2A_CLAIM_PREFIX: Final[str] = "agent-zero-a2a:claim:"
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
_A2A_READBACK_INTERVAL_MS: Final[int] = 30_000


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
    # Polling/event writes refresh updated_at, so it cannot be the execution clock.
    # created_at is immutable and guarantees that a stuck external task cannot live forever.
    observed = job.created_at
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


def _pending_submit_ref(job_id: str) -> str:
    digest = hashlib.sha256(job_id.encode("utf-8")).hexdigest()[:24]
    return f"{_A2A_PENDING_PREFIX}{digest}"


def _retry_ref(task_id: str) -> str:
    return f"{_A2A_RETRY_PREFIX}{task_id}"


def _bound_task(external_ref: str) -> tuple[str, bool] | None:
    if external_ref.startswith(_A2A_RETRY_PREFIX):
        task_id = external_ref[len(_A2A_RETRY_PREFIX):]
        return (task_id, True) if task_id else None
    if (
        external_ref.startswith(_A2A_NORMAL_PREFIX)
        and not external_ref.startswith(_A2A_CLAIM_PREFIX)
        and not external_ref.startswith(_A2A_PENDING_PREFIX)
    ):
        task_id = external_ref[len(_A2A_NORMAL_PREFIX):]
        return (task_id, False) if task_id else None
    return None


def is_repository_a2a_job(job: StoredSovereignAgentJob | None) -> bool:
    return bool(job and str(job.external_ref or "").startswith(_A2A_NORMAL_PREFIX))


def cancel_repository_a2a_job(
    conn: Any,
    *,
    job: StoredSovereignAgentJob,
    a2a_client_factory: A2AClientFactory = AgentZeroA2AClient.from_env,
) -> StoredSovereignAgentJob:
    """Cancel the one bound Agent Zero task and only unlock after proven cancellation."""
    binding = _bound_task(str(job.external_ref or ""))
    if binding is None:
        raise RepositoryExecutionError("AGENT_ZERO_A2A_CANCEL_TASK_ID_MISSING")
    task_id, _is_retry = binding
    try:
        task = a2a_client_factory().cancel_task(task_id)
    except AgentZeroA2AError as exc:
        raise RepositoryExecutionError(
            f"{exc.family}: Agent Zero did not confirm cancellation."
        ) from exc
    if task.state != "canceled":
        raise RepositoryExecutionError(
            f"AGENT_ZERO_A2A_CANCEL_NOT_CONFIRMED: task state is {task.state}."
        )
    update_agent_job_state(
        conn,
        job_id=job.job_id,
        status="blocked",
        blocker="Cancelled by owner; Agent Zero A2A confirmed task state canceled.",
    )
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="agent_zero_a2a_cancel_confirmed",
        level="warning",
        message=(
            f"Agent Zero confirmed cancellation for task {task.task_id}. "
            "The persisted run is unlocked and publication remains quarantined."
        ),
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


def _record_task_readback(
    conn: Any, job: StoredSovereignAgentJob, *, message: str, unavailable: bool = False,
) -> StoredSovereignAgentJob:
    """Persist observations without turning polling into execution progress.

    Event writes leave updated_at unchanged: polling must not reset the execution
    deadline. Throttle from persisted events, not a process-local heartbeat cache.
    """
    current = read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job
    if current.status != "running" or current.external_ref != job.external_ref:
        return current
    stage = "agent_zero_a2a_readback_unavailable" if unavailable else "agent_zero_a2a_task_observed"
    event = SovereignAgentEvent(stage=stage, level="warning" if unavailable else "info", message=message)
    for previous in reversed(current.events):
        if previous.get("stage") not in {"agent_zero_a2a_task_observed", "agent_zero_a2a_readback_unavailable"}:
            continue
        if previous.get("stage") == stage and previous.get("message") == event.message:
            # Identical tasks/get observations are heartbeat noise, not new evidence.
            # Keep one persisted observation until the external state/message changes.
            return current
        break
    append_agent_event(conn, current.job_id, event)
    return read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or current


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
            repository_url=job.repo_url,
            branch=job.branch,
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
    workspace_root: Path | None = None,
    a2a_client_factory: A2AClientFactory = AgentZeroA2AClient.from_env,
) -> StoredSovereignAgentJob:
    """Persist one Agent-Zero-only repository job and queue its A2A submit.

    Sovereign provisions only the shared filesystem slot. It never resolves a
    GitHub OAuth credential and never clones the implementation repository on
    the execution path. The server-owned reconciler submits exactly one A2A task;
    Agent Zero owns repository access and checkout through its own configured
    repository/GitHub capability.
    """

    if "githubAccessToken" in body:
        raise RepositoryExecutionError("GITHUB_CREDENTIAL_FORBIDDEN_ON_EXECUTION")

    payload = _normalized_repository_payload(body)
    lifecycle = create_sovereign_agent_job(
        conn,
        user_id=user_id,
        payload=payload,
        workspace_root=workspace_root,
        provision_workspace=True,
        clone_repo=False,
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
            stage="agent_zero_repository_access_delegated",
            level="success",
            message=(
                "Sovereign provisioned only the shared workspace; repository checkout "
                "is delegated exclusively to Agent Zero without Sovereign GitHub OAuth."
            ),
        ))
        job = read_agent_job(conn, user_id=user_id, job_id=job.job_id) or job
    if job.status != "running":
        return job

    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="repository_execution_contract_bound",
        level="success",
        message=(
            "Repository execution contract bound: Sovereign persists the job and evidence; exactly one "
            "Agent Zero A2A task owns implementation; the current repository path is free and may not "
            "create a paid usage settlement."
        ),
    ))
    job = read_agent_job(conn, user_id=user_id, job_id=job.job_id) or job

    pending_ref = _pending_submit_ref(job.job_id)
    if not compare_and_swap_agent_job_external_ref(
        conn,
        job_id=job.job_id,
        expected_ref=None,
        new_ref=pending_ref,
    ):
        # Another caller already owns or queued the external-effect boundary.
        return read_agent_job(conn, user_id=user_id, job_id=job.job_id) or job
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="agent_zero_a2a_submit_queued",
        level="info",
        message="Agent Zero A2A submission was durably queued for the server-owned reconciler.",
    ))
    return read_agent_job(conn, user_id=user_id, job_id=job.job_id) or job


def _submit_pending_repository_job(
    conn: Any,
    *,
    job: StoredSovereignAgentJob,
    a2a_client_factory: A2AClientFactory = AgentZeroA2AClient.from_env,
) -> StoredSovereignAgentJob:
    """Claim and execute one durable initial submit outside the HTTP request."""

    pending_ref = str(job.external_ref or "")
    if job.status != "running" or not pending_ref.startswith(_A2A_PENDING_PREFIX):
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
    # A2A task storage is not the repository truth boundary. A missing task may
    # follow an Agent Zero restart or an in-memory task-store loss after the
    # shared workspace was already mutated. Inspect the owned workspace first;
    # never duplicate repository work merely because tasks/get returned 404.
    status_result = run_agent_job_tool(job, "git-status", {}, workspace_root)
    if status_result.status != "done":
        return _block_job(
            conn,
            job,
            (
                "AGENT_ZERO_A2A_TASK_LOST: the original task is no longer readable and "
                "workspace mutation state could not be verified; recovery submit is quarantined."
            ),
            "agent_zero_a2a_lost_workspace_unverified",
        )

    if status_result.changed_files:
        claim_ref = _claim("closeout-lost", task_id)
        if not compare_and_swap_agent_job_external_ref(
            conn,
            job_id=job.job_id,
            expected_ref=bound_ref,
            new_ref=claim_ref,
        ):
            return read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job
        claimed = read_agent_job(conn, user_id=job.user_id, job_id=job.job_id) or job
        append_agent_event(conn, job.job_id, SovereignAgentEvent(
            stage="agent_zero_a2a_lost_workspace_changes_detected",
            level="warning",
            message=(
                "The original Agent Zero task is no longer readable, but the owned shared workspace "
                "contains real changes; Sovereign will close out those changes without resubmitting."
            ),
        ))
        return _closeout_repository_job(
            conn,
            job=claimed,
            claim_ref=claim_ref,
            bound_ref=bound_ref,
            workspace_root=workspace_root,
        )

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
        message=(
            "The persisted original Agent Zero task is gone and the owned workspace has no changes; "
            "one atomic recovery submit is allowed."
        ),
    ))
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
    if external_ref.startswith(_A2A_PENDING_PREFIX):
        # Pending submission is server-worker-owned. User/client polling must be
        # read-only and must never perform the outbound Agent Zero side effect.
        return job
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
        _record_task_readback(
            conn, job,
            message=f"{exc.family}: Agent Zero task readback is unavailable; no task was resubmitted.",
            unavailable=True,
        )
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
        return _record_task_readback(
            conn, job,
            message=(
                f"Agent Zero tasks/get observed task {task.task_id} in state {task.state}. "
                "This confirms a task readback, not new file changes or completed work."
            ),
        )
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

def recover_stalled_repository_job_from_verified_readback(
    conn: Any,
    *,
    user_id: str,
    job_id: str,
    workspace_root: Path | None = None,
    a2a_client_factory: A2AClientFactory = AgentZeroA2AClient.from_env,
) -> tuple[StoredSovereignAgentJob | None, bool]:
    """Recover only a proven completed stalled task; never resubmit external work.

    This is the bounded self-healing action for HANDOFF_TIMEOUT_WITH_READBACK.
    The task identity must already be persisted, tasks/get must prove completion,
    and the canonical closeout path still owns all workspace/test/evidence gates.
    """
    job = read_agent_job(conn, user_id=user_id, job_id=job_id)
    if job is None:
        return None, False
    if job.status != "blocked" or "AGENT_ZERO_A2A_STALLED" not in str(job.blocker or ""):
        return job, False
    binding = _bound_task(str(job.external_ref or ""))
    if binding is None:
        return job, False
    task_id, _is_retry = binding
    try:
        task = a2a_client_factory().get_task(task_id)
    except (AgentZeroA2AError, AgentZeroA2ATaskLost):
        return job, False
    if not task.completed:
        return job, False

    update_agent_job_state(
        conn,
        job_id=job.job_id,
        status="running",
        clear_blocker=True,
    )
    append_agent_event(conn, job.job_id, SovereignAgentEvent(
        stage="self_healing_handoff_readback_recovered",
        level="success",
        message=(
            "Self-healing readback proved the already-bound Agent Zero task completed; "
            "the job was resumed for canonical closeout without any resubmit."
        ),
    ))
    recovered = reconcile_repository_execution(
        conn,
        user_id=user_id,
        job_id=job_id,
        workspace_root=workspace_root,
        a2a_client_factory=a2a_client_factory,
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
    """Reconcile persisted A2A repository jobs without any client polling.

    Pending initial submits are claimed and executed here, never in a user HTTP
    request. Bound tasks retain the existing CAS ownership for retry and closeout,
    so multiple backend processes cannot duplicate the external task or Draft-PR
    preparation.
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
            if str(candidate.external_ref or "").startswith(_A2A_PENDING_PREFIX):
                _submit_pending_repository_job(conn, job=candidate)
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
