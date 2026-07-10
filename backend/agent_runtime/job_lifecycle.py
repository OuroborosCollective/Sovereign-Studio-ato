"""Lifecycle orchestration for Sovereign Agent Jobs.

This module is the backend bridge between the neutral job contract, DB store,
workspace provisioner and Git workspace evidence. It never returns a fake success:
invalid requests become blocked results; successful provisioning creates explicit
runtime states and events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import uuid

from .contracts import (
    SovereignAgentEvent,
    SovereignAgentJobRequest,
    SovereignAgentJobResult,
    build_blocked_agent_result,
    build_sovereign_agent_job_request,
    normalize_agent_job_result,
    validate_agent_job_request,
)
from .git_workspace import clone_repo_into_workspace
from .job_store import (
    append_agent_event,
    create_agent_job_record,
    update_agent_job_state,
)
from .workspace import create_agent_workspace


@dataclass(frozen=True)
class SovereignAgentLifecycleResult:
    job_id: str
    result: SovereignAgentJobResult
    events: tuple[SovereignAgentEvent, ...] = field(default_factory=tuple)


def generate_agent_job_id() -> str:
    return f"agent-{uuid.uuid4().hex}"


def _request_blocker(blockers: tuple[str, ...]) -> str:
    return "; ".join(blockers) if blockers else "Agent request blocked."


def create_sovereign_agent_job(
    conn,
    *,
    user_id: str,
    payload: dict,
    workspace_root: Path | None = None,
    provision_workspace: bool = True,
    clone_repo: bool = False,
    job_id: str | None = None,
) -> SovereignAgentLifecycleResult:
    request = build_sovereign_agent_job_request(payload)
    resolved_job_id = job_id or generate_agent_job_id()
    validation = validate_agent_job_request(request)

    if not validation.allowed:
        blocker = _request_blocker(validation.blockers)
        result = build_blocked_agent_result(resolved_job_id, blocker, _safe_executor(request))
        create_agent_job_record(
            conn,
            user_id=user_id,
            job_id=resolved_job_id,
            request=_safe_blocked_request(request),
            status="blocked",
            events=result.events,
            blocker=result.blocker,
        )
        return SovereignAgentLifecycleResult(
            job_id=resolved_job_id,
            result=result,
            events=result.events,
        )

    create_agent_job_record(
        conn,
        user_id=user_id,
        job_id=resolved_job_id,
        request=request,
        status="queued",
        events=(SovereignAgentEvent(stage="agent_job_created", level="success", message="Sovereign agent job created."),),
    )

    if not provision_workspace:
        result = normalize_agent_job_result(SovereignAgentJobResult(
            job_id=resolved_job_id,
            status="queued",
            executor=request.executor,
            events=(SovereignAgentEvent(stage="agent_job_queued", level="info", message="Agent job queued."),),
        ))
        return SovereignAgentLifecycleResult(job_id=resolved_job_id, result=result, events=result.events)

    workspace_result = create_agent_workspace(resolved_job_id, workspace_root)
    for event in workspace_result.events:
        append_agent_event(conn, resolved_job_id, event)

    if workspace_result.status not in ("created", "exists"):
        update_agent_job_state(
            conn,
            job_id=resolved_job_id,
            status="blocked",
            blocker=workspace_result.blocker or "Workspace provisioning blocked.",
        )
        result = normalize_agent_job_result(SovereignAgentJobResult(
            job_id=resolved_job_id,
            status="blocked",
            executor=request.executor,
            events=workspace_result.events,
            blocker=workspace_result.blocker or "Workspace provisioning blocked.",
            workspace_id=resolved_job_id,
        ))
        return SovereignAgentLifecycleResult(job_id=resolved_job_id, result=result, events=result.events)

    update_agent_job_state(
        conn,
        job_id=resolved_job_id,
        status="provisioning",
        workspace_id=resolved_job_id,
    )

    if not clone_repo:
        result = normalize_agent_job_result(SovereignAgentJobResult(
            job_id=resolved_job_id,
            status="provisioning",
            executor=request.executor,
            events=workspace_result.events,
            workspace_id=resolved_job_id,
        ))
        return SovereignAgentLifecycleResult(job_id=resolved_job_id, result=result, events=result.events)

    clone_result = clone_repo_into_workspace(
        resolved_job_id,
        request.repo_url,
        request.branch,
        workspace_root,
    )
    for event in clone_result.events:
        append_agent_event(conn, resolved_job_id, event)

    if clone_result.status != "done":
        update_agent_job_state(
            conn,
            job_id=resolved_job_id,
            status="blocked" if clone_result.status == "blocked" else "failed",
            workspace_id=resolved_job_id,
            blocker=clone_result.blocker or "Repository clone failed.",
        )
        result = normalize_agent_job_result(SovereignAgentJobResult(
            job_id=resolved_job_id,
            status="blocked" if clone_result.status == "blocked" else "failed",
            executor=request.executor,
            events=workspace_result.events + clone_result.events,
            blocker=clone_result.blocker or "Repository clone failed.",
            workspace_id=resolved_job_id,
        ))
        return SovereignAgentLifecycleResult(job_id=resolved_job_id, result=result, events=result.events)

    update_agent_job_state(
        conn,
        job_id=resolved_job_id,
        status="running",
        workspace_id=resolved_job_id,
    )
    result = normalize_agent_job_result(SovereignAgentJobResult(
        job_id=resolved_job_id,
        status="running",
        executor=request.executor,
        events=workspace_result.events + clone_result.events,
        workspace_id=resolved_job_id,
    ))
    return SovereignAgentLifecycleResult(job_id=resolved_job_id, result=result, events=result.events)


def _safe_executor(request: SovereignAgentJobRequest) -> str:
    return "sovereign-local-runner"


def _safe_blocked_request(request: SovereignAgentJobRequest) -> SovereignAgentJobRequest:
    executor = _safe_executor(request)
    return SovereignAgentJobRequest(
        repo_url=request.repo_url or "https://github.com/invalid/blocked",
        mission=request.mission or "Blocked invalid agent request.",
        executor=executor,  # type: ignore[arg-type]
        branch=request.branch or "main",
        draft_pr_only=True,
        allow_auto_merge=False,
        allowed_paths=request.allowed_paths,
        forbidden_paths=request.forbidden_paths,
        memory_hints=request.memory_hints,
        max_runtime_ms=request.max_runtime_ms if isinstance(request.max_runtime_ms, int) else None,
        max_workspace_bytes=request.max_workspace_bytes if isinstance(request.max_workspace_bytes, int) else None,
    )
