"""Self-contained workspace provisioner for Sovereign Agent Runtime.

This creates and cleans real filesystem workspaces for agent jobs. It does not
run code, clone repositories, or create success claims. Every operation returns a
state object that can be persisted by the backend runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
import time
from typing import Literal

from .contracts import SovereignAgentEvent, sanitize_agent_text
from .workspace_policy import WorkspacePolicyError, repo_dir_for_workspace, safe_workspace_path

WorkspaceStatus = Literal["created", "exists", "blocked", "cleaned"]


@dataclass(frozen=True)
class WorkspaceProvisionResult:
    workspace_id: str
    status: WorkspaceStatus
    path: str | None = None
    repo_path: str | None = None
    events: tuple[SovereignAgentEvent, ...] = field(default_factory=tuple)
    blocker: str | None = None


def _event(stage: str, level: Literal["info", "warning", "error", "success"], message: str) -> SovereignAgentEvent:
    return SovereignAgentEvent(
        stage=sanitize_agent_text(stage, 80),
        level=level,
        message=sanitize_agent_text(message, 1200),
        at=int(time.time() * 1000),
    )


def create_agent_workspace(workspace_id: str, root: Path | None = None) -> WorkspaceProvisionResult:
    try:
        workspace = safe_workspace_path(workspace_id, root)
        repo_path = repo_dir_for_workspace(workspace_id, root)
        if workspace.exists():
            return WorkspaceProvisionResult(
                workspace_id=workspace_id,
                status="exists",
                path=str(workspace),
                repo_path=str(repo_path),
                events=(
                    _event("workspace_exists", "warning", "Workspace already exists for this job."),
                ),
                blocker="Workspace already exists for this job.",
            )
        repo_path.mkdir(parents=True, exist_ok=False)
        return WorkspaceProvisionResult(
            workspace_id=workspace_id,
            status="created",
            path=str(workspace),
            repo_path=str(repo_path),
            events=(
                _event("workspace_created", "success", "Workspace created."),
            ),
        )
    except Exception as exc:
        return WorkspaceProvisionResult(
            workspace_id=sanitize_agent_text(workspace_id, 120) or "workspace-unknown",
            status="blocked",
            events=(
                _event("workspace_blocked", "warning", str(exc)),
            ),
            blocker=sanitize_agent_text(str(exc), 1200),
        )


def cleanup_agent_workspace(workspace_id: str, root: Path | None = None) -> WorkspaceProvisionResult:
    try:
        workspace = safe_workspace_path(workspace_id, root)
        if not workspace.exists():
            return WorkspaceProvisionResult(
                workspace_id=workspace_id,
                status="cleaned",
                path=str(workspace),
                events=(
                    _event("workspace_cleanup_skipped", "info", "Workspace already absent."),
                ),
            )
        shutil.rmtree(workspace)
        return WorkspaceProvisionResult(
            workspace_id=workspace_id,
            status="cleaned",
            path=str(workspace),
            events=(
                _event("workspace_cleaned", "success", "Workspace cleaned."),
            ),
        )
    except WorkspacePolicyError as exc:
        return WorkspaceProvisionResult(
            workspace_id=sanitize_agent_text(workspace_id, 120) or "workspace-unknown",
            status="blocked",
            events=(
                _event("workspace_cleanup_blocked", "warning", str(exc)),
            ),
            blocker=sanitize_agent_text(str(exc), 1200),
        )
    except Exception as exc:
        return WorkspaceProvisionResult(
            workspace_id=sanitize_agent_text(workspace_id, 120) or "workspace-unknown",
            status="blocked",
            events=(
                _event("workspace_cleanup_failed", "error", str(exc)),
            ),
            blocker=sanitize_agent_text(str(exc), 1200),
        )
