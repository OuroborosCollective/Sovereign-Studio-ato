"""Receipt-bound IDE and terminal projection requests.

This module deliberately follows canonical tool execution.  It never invokes a
repository tool, starts a process, opens a shell, changes a worktree, or assigns a
success verdict.  It derives a bounded projection request from an already produced
ToolResult and from a fresh workspace readback.  A UI or desktop adapter may display
that request, but must not upgrade its evidence class.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from .contracts import sanitize_agent_text
from .fleet_supervisor import FleetContractError
from .live_workspace import LiveWorkspaceSessionV1, SessionReconciliationV1, VisualProjectionEventV1
from .tools.base import ToolResult
from .workspace_policy import (
    WorkspacePolicyError,
    repo_dir_for_workspace,
    validate_workspace_relative_path,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


class ProjectionContractError(ValueError):
    """Raised when a projection cannot be bound to a canonical action/readback."""


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return sha256(encoded).hexdigest()


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _head(repo: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            text=True,
            capture_output=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProjectionContractError("workspace Git head is unreadable") from exc
    head = completed.stdout.strip().lower()
    if not _SHA40.fullmatch(head):
        raise ProjectionContractError("workspace Git head is invalid")
    return head


def _repo_for_job(job: Any, workspace_root: Path | None) -> Path:
    workspace_id = str(getattr(job, "workspace_id", "") or "").strip()
    if not workspace_id:
        raise ProjectionContractError("job workspace identity is unavailable")
    try:
        repo = repo_dir_for_workspace(workspace_id, workspace_root).resolve()
    except WorkspacePolicyError as exc:
        raise ProjectionContractError("job workspace identity is invalid") from exc
    if not repo.is_dir() or not (repo / ".git").is_dir():
        raise ProjectionContractError("job workspace repository is unavailable")
    return repo


def _safe_file_readback(repo: Path, raw_path: object) -> tuple[str, str]:
    try:
        relative = validate_workspace_relative_path(str(raw_path or ""))
    except WorkspacePolicyError as exc:
        raise ProjectionContractError("projection file path is invalid") from exc
    target = (repo / relative).resolve()
    if repo not in target.parents or not target.is_file():
        raise ProjectionContractError("projection file path is unavailable in bound worktree")
    return relative, sha256(target.read_bytes()).hexdigest()


def _receipt_ref(result: ToolResult) -> str:
    metadata = result.metadata if isinstance(result.metadata, Mapping) else {}
    value = str(metadata.get("providerNeutralEvidenceSha256") or "").strip().lower()
    if _SHA256.fullmatch(value):
        return value
    payload = {
        "tool": str(result.tool or ""),
        "status": str(result.status or ""),
        "exitCode": result.exit_code,
        "changedFiles": list(result.changed_files or ()),
        "diffSummary": str(result.diff_summary or ""),
        "testSummary": str(result.test_summary or ""),
    }
    return _canonical_hash(payload)


def _action_id(result: ToolResult) -> str:
    metadata = result.metadata if isinstance(result.metadata, Mapping) else {}
    action_id = str(metadata.get("actionId") or metadata.get("callId") or "").strip()
    if not action_id or len(action_id) > 160:
        raise ProjectionContractError("canonical action identity is unavailable")
    return action_id


def _build(
    *,
    session: LiveWorkspaceSessionV1,
    reconciliation: SessionReconciliationV1,
    result: ToolResult,
    event_type: str,
    source_kind: str,
    projection_kind: str,
    projection_state: str,
    repository_head: str | None,
    payload: Mapping[str, Any],
) -> VisualProjectionEventV1:
    try:
        return VisualProjectionEventV1.create_correlated(
            session=session,
            reconciliation=reconciliation,
            event_type=event_type,
            action_id=_action_id(result),
            source_kind=source_kind,
            projection_kind=projection_kind,
            projection_state=projection_state,
            source_receipt_ref=_receipt_ref(result),
            repository_head=repository_head,
            payload=payload,
        )
    except FleetContractError as exc:
        raise ProjectionContractError(str(exc)) from exc


def projection_for_tool_result(
    *,
    job: Any,
    route_action: str,
    parameters: Mapping[str, Any],
    result: ToolResult,
    workspace_root: Path | None,
    session: LiveWorkspaceSessionV1,
    reconciliation: SessionReconciliationV1,
) -> VisualProjectionEventV1:
    """Build one canonical visual event after execution and fresh session reconciliation.

    The bridge cannot create a material projection from a bare Agent Job.  A caller
    must supply the already-bound LiveWorkspaceSession plus a fresh reconciliation
    proving that assignment, attempt, worktree, Git head and controller state still
    match. Projection failure never changes ``result``.
    """
    action = str(route_action or "").strip()
    if session.workspace_id != str(getattr(job, "workspace_id", "") or "").strip():
        raise ProjectionContractError("live workspace session is not bound to this Agent Job workspace")

    executed_test_failure = action == "test" and result.status == "error" and result.exit_code is not None
    if result.status != "done" and not executed_test_failure:
        return _build(
            session=session,
            reconciliation=reconciliation,
            result=result,
            event_type="NO_VISUAL_PROJECTION_AVAILABLE",
            source_kind="PROCESS" if action == "test" else "REPOSITORY",
            projection_kind="TERMINAL" if action == "test" else "WINDOW_FOCUS",
            projection_state="UNAVAILABLE",
            repository_head=None,
            payload={"reason": "canonical_action_not_executed", "canonicalStatus": result.status},
        )

    repo = _repo_for_job(job, workspace_root)
    head = _head(repo)
    if head != session.observed_head_revision:
        raise ProjectionContractError("workspace Git head drifted from the canonical LiveWorkspaceSession")
    if action == "file":
        raw_path = parameters.get("path") or parameters.get("relativePath")
        path, content_sha = _safe_file_readback(repo, raw_path)
        mode = str(parameters.get("mode") or parameters.get("action") or ("write" if "content" in parameters else "read")).lower()
        return _build(
            session=session,
            reconciliation=reconciliation,
            result=result,
            event_type="FILE_VIEW_PROJECTED",
            source_kind="REPOSITORY",
            projection_kind="IDE_FILE",
            projection_state="REQUESTED",
            repository_head=head,
            payload={"path": path, "contentSha256": content_sha, "mode": "write" if mode == "write" else "read"},
        )
    if action == "diff":
        diff_text = str(result.output or result.stdout or "")
        return _build(
            session=session,
            reconciliation=reconciliation,
            result=result,
            event_type="FILE_VIEW_PROJECTED",
            source_kind="GIT",
            projection_kind="IDE_DIFF",
            projection_state="REQUESTED",
            repository_head=head,
            payload={"diffSha256": _hash_text(diff_text), "changedFiles": list(result.changed_files or ())[:64]},
        )
    if action == "test":
        output = sanitize_agent_text(
            str(result.output or result.stdout or result.stderr or result.error or ""),
            16_000,
        )
        return _build(
            session=session,
            reconciliation=reconciliation,
            result=result,
            event_type="TERMINAL_VIEW_PROJECTED",
            source_kind="PROCESS",
            projection_kind="TERMINAL",
            projection_state="REQUESTED",
            repository_head=head,
            payload={
                "streamSequence": 1,
                "channel": "STDOUT" if (result.output or result.stdout) else "STDERR",
                "chunk": output,
                "chunkSha256": _hash_text(output),
                "exitCode": result.exit_code,
                "processState": "EXITED",
                "canonicalStatus": result.status,
                "successful": result.status == "done" and result.exit_code in (None, 0),
            },
        )
    return _build(
        session=session,
        reconciliation=reconciliation,
        result=result,
        event_type="NO_VISUAL_PROJECTION_AVAILABLE",
        source_kind="REPOSITORY",
        projection_kind="WINDOW_FOCUS",
        projection_state="UNAVAILABLE",
        repository_head=head,
        payload={"reason": "projection_not_supported_for_action"},
    )


def public_projection_event(request: VisualProjectionEventV1) -> dict[str, Any]:
    """Return the canonical visual-projection event as a redacted read model."""
    return request.to_dict()


__all__ = [
    "ProjectionContractError",
    "projection_for_tool_result",
    "public_projection_event",
]
