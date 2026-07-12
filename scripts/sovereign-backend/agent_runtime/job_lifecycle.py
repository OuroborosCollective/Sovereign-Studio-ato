"""Lifecycle orchestration for Sovereign Agent Jobs.

This module is the backend bridge between the neutral job contract, DB store,
workspace provisioner and Git workspace evidence. It never returns a fake success:
invalid requests become blocked results; successful provisioning creates explicit
runtime states and events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
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
from .git_workspace import (
    clone_repo_into_workspace,
    git_diff_check,
    git_diff_summary,
    git_status_changed_files,
    normalize_ephemeral_github_token,
)
from .job_store import (
    append_agent_event,
    create_agent_job_record,
    update_agent_job_state,
)
from .tool_runner import run_agent_job_tool
from .workspace import create_agent_workspace
from .workspace_policy import repo_dir_for_workspace


@dataclass(frozen=True)
class SovereignAgentLifecycleResult:
    job_id: str
    result: SovereignAgentJobResult
    events: tuple[SovereignAgentEvent, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StagedWorkspaceFile:
    path: str
    content: str
    base_content: str | None = None


_MAX_STAGED_FILES = 20
_MAX_STAGED_FILE_BYTES = 500_000
_MAX_STAGED_TOTAL_BYTES = 1_500_000
_DOC_SUFFIXES = (".md", ".markdown", ".mdx", ".mdoc", ".txt")


def _parse_staged_files(payload: dict[str, Any]) -> tuple[tuple[StagedWorkspaceFile, ...], str | None]:
    raw = payload.get("stagedFiles")
    if raw is None:
        return (), None
    if not isinstance(raw, list) or not raw:
        return (), "stagedFiles must be a non-empty array when provided"
    if len(raw) > _MAX_STAGED_FILES:
        return (), f"stagedFiles exceeds {_MAX_STAGED_FILES} files"

    parsed: list[StagedWorkspaceFile] = []
    total_bytes = 0
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            return (), "every staged file must be an object"
        path = str(item.get("path") or "").strip().replace("\\", "/")
        pure = PurePosixPath(path)
        if (
            not path
            or pure.is_absolute()
            or ".." in pure.parts
            or any(part in {".git", ".env", "node_modules", "__pycache__", ".pytest_cache"} for part in pure.parts)
        ):
            return (), f"unsafe staged file path: {path or '<empty>'}"
        normalized_path = pure.as_posix()
        if normalized_path in seen:
            return (), f"duplicate staged file path: {normalized_path}"
        content = item.get("content")
        if not isinstance(content, str):
            return (), f"staged file content must be text: {normalized_path}"
        content_bytes = len(content.encode("utf-8"))
        if content_bytes > _MAX_STAGED_FILE_BYTES:
            return (), f"staged file exceeds {_MAX_STAGED_FILE_BYTES} bytes: {normalized_path}"
        total_bytes += content_bytes
        if total_bytes > _MAX_STAGED_TOTAL_BYTES:
            return (), f"staged files exceed {_MAX_STAGED_TOTAL_BYTES} total bytes"
        base_content = item.get("baseContent")
        if base_content is not None and not isinstance(base_content, str):
            return (), f"baseContent must be text when provided: {normalized_path}"
        seen.add(normalized_path)
        parsed.append(StagedWorkspaceFile(normalized_path, content, base_content))
    return tuple(parsed), None


def _docs_only(files: tuple[StagedWorkspaceFile, ...]) -> bool:
    return bool(files) and all(file.path.lower().endswith(_DOC_SUFFIXES) for file in files)


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
    staged_files, staged_blocker = _parse_staged_files(payload)
    raw_github_token = payload.get("githubAccessToken")
    github_token = normalize_ephemeral_github_token(raw_github_token)
    token_blocker = (
        "githubAccessToken has an invalid format"
        if raw_github_token is not None and github_token is None
        else None
    )
    request_blockers = (
        validation.blockers
        + ((staged_blocker,) if staged_blocker else ())
        + ((token_blocker,) if token_blocker else ())
    )
    if staged_files:
        clone_repo = True

    if not validation.allowed or staged_blocker or token_blocker:
        blocker = _request_blocker(request_blockers)
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
        token=github_token,
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

    staged_events: list[SovereignAgentEvent] = []
    changed_files: tuple[str, ...] = ()
    diff_summary_value: str | None = None
    test_summary_value: str | None = None
    if staged_files:
        repo_path = repo_dir_for_workspace(resolved_job_id, workspace_root)
        for staged_file in staged_files:
            read_result = run_agent_job_tool(
                resolved_job_id,
                "file",
                {"mode": "read", "path": staged_file.path, "maxBytes": _MAX_STAGED_FILE_BYTES},
                repo_path,
            )
            if read_result.status == "done":
                if staged_file.base_content is None:
                    blocker = f"baseContent is required for existing staged file: {staged_file.path}"
                elif read_result.output != staged_file.base_content:
                    blocker = f"staged base content drift detected: {staged_file.path}"
                else:
                    blocker = None
            elif read_result.status == "error" and (read_result.error or "").startswith("File not found:"):
                blocker = None if staged_file.base_content is None else f"staged base content drift detected: {staged_file.path}"
            else:
                blocker = read_result.blocker or read_result.error or f"staged base content could not be verified: {staged_file.path}"
            if blocker:
                update_agent_job_state(
                    conn,
                    job_id=resolved_job_id,
                    status="blocked",
                    workspace_id=resolved_job_id,
                    blocker=blocker,
                )
                blocked = normalize_agent_job_result(SovereignAgentJobResult(
                    job_id=resolved_job_id,
                    status="blocked",
                    executor=request.executor,
                    blocker=blocker,
                    workspace_id=resolved_job_id,
                    events=workspace_result.events + clone_result.events,
                ))
                return SovereignAgentLifecycleResult(resolved_job_id, blocked, blocked.events)
            write_result = run_agent_job_tool(
                resolved_job_id,
                "file",
                {"mode": "write", "path": staged_file.path, "content": staged_file.content},
                repo_path,
            )
            if write_result.status != "done":
                blocker = write_result.blocker or write_result.error or f"staged write failed: {staged_file.path}"
                update_agent_job_state(
                    conn,
                    job_id=resolved_job_id,
                    status="blocked",
                    workspace_id=resolved_job_id,
                    blocker=blocker,
                )
                blocked = normalize_agent_job_result(SovereignAgentJobResult(
                    job_id=resolved_job_id,
                    status="blocked",
                    executor=request.executor,
                    blocker=blocker,
                    workspace_id=resolved_job_id,
                    events=workspace_result.events + clone_result.events,
                ))
                return SovereignAgentLifecycleResult(resolved_job_id, blocked, blocked.events)
            event = SovereignAgentEvent(
                stage="staged_file_written",
                level="success",
                message=f"Staged file written: {staged_file.path}",
            )
            append_agent_event(conn, resolved_job_id, event)
            staged_events.append(event)

        status_result = git_status_changed_files(resolved_job_id, workspace_root)
        diff_result = git_diff_summary(resolved_job_id, workspace_root)
        check_result = git_diff_check(resolved_job_id, workspace_root)
        if status_result.status != "done" or not status_result.changed_files:
            blocker = status_result.blocker or "staged changes produced no Git status evidence"
        elif diff_result.status != "done" or not (diff_result.diff_summary or "").strip():
            blocker = diff_result.blocker or "staged changes produced no Git diff evidence"
        elif check_result.status != "done":
            blocker = check_result.blocker or "git diff --check failed"
        else:
            blocker = None
        if blocker:
            update_agent_job_state(
                conn,
                job_id=resolved_job_id,
                status="blocked",
                workspace_id=resolved_job_id,
                blocker=blocker,
            )
            blocked = normalize_agent_job_result(SovereignAgentJobResult(
                job_id=resolved_job_id,
                status="blocked",
                executor=request.executor,
                blocker=blocker,
                workspace_id=resolved_job_id,
                events=workspace_result.events + clone_result.events + tuple(staged_events),
            ))
            return SovereignAgentLifecycleResult(resolved_job_id, blocked, blocked.events)

        declared_files = tuple(file.path for file in staged_files)
        unexpected_files = tuple(path for path in status_result.changed_files if path not in declared_files)
        if unexpected_files:
            blocker = f"workspace contains undeclared staged changes: {', '.join(unexpected_files[:10])}"
            update_agent_job_state(
                conn,
                job_id=resolved_job_id,
                status="blocked",
                workspace_id=resolved_job_id,
                blocker=blocker,
            )
            blocked = normalize_agent_job_result(SovereignAgentJobResult(
                job_id=resolved_job_id,
                status="blocked",
                executor=request.executor,
                blocker=blocker,
                workspace_id=resolved_job_id,
                events=workspace_result.events + clone_result.events + tuple(staged_events),
            ))
            return SovereignAgentLifecycleResult(resolved_job_id, blocked, blocked.events)

        changed_files = status_result.changed_files
        diff_summary_value = diff_result.diff_summary
        if _docs_only(staged_files):
            test_summary_value = "git diff --check passed for documentation-only staged changes."
        else:
            test_command = payload.get("testCommand")
            if isinstance(test_command, str) and test_command.strip():
                test_result = run_agent_job_tool(
                    resolved_job_id,
                    "test",
                    {"command": test_command.strip(), "timeout": 600, "verbose": True},
                    repo_path,
                )
                if test_result.status != "done":
                    blocker = test_result.blocker or test_result.error or "staged change tests failed"
                    update_agent_job_state(
                        conn,
                        job_id=resolved_job_id,
                        status="blocked",
                        workspace_id=resolved_job_id,
                        changed_files=changed_files,
                        diff_summary=diff_summary_value,
                        blocker=blocker,
                    )
                    blocked = normalize_agent_job_result(SovereignAgentJobResult(
                        job_id=resolved_job_id,
                        status="blocked",
                        executor=request.executor,
                        changed_files=changed_files,
                        diff_summary=diff_summary_value,
                        blocker=blocker,
                        workspace_id=resolved_job_id,
                        events=workspace_result.events + clone_result.events + tuple(staged_events),
                    ))
                    return SovereignAgentLifecycleResult(resolved_job_id, blocked, blocked.events)
                test_summary_value = test_result.output or "Allowlisted test command passed."

    update_agent_job_state(
        conn,
        job_id=resolved_job_id,
        status="running",
        workspace_id=resolved_job_id,
        changed_files=changed_files or None,
        diff_summary=diff_summary_value,
        test_summary=test_summary_value,
    )
    result = normalize_agent_job_result(SovereignAgentJobResult(
        job_id=resolved_job_id,
        status="running",
        executor=request.executor,
        changed_files=changed_files,
        diff_summary=diff_summary_value,
        test_summary=test_summary_value,
        events=workspace_result.events + clone_result.events + tuple(staged_events),
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
