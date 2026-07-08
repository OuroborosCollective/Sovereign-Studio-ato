"""Policy-guarded file tool for Sovereign Agent Runtime."""

from __future__ import annotations

from pathlib import Path

from ..contracts import sanitize_agent_text
from ..tool_policy import resolve_repo_tool_path
from .base import ToolResult, blocked_tool_result, done_tool_result, failed_tool_result

MAX_READ_BYTES = 200_000
MAX_WRITE_BYTES = 500_000


def read_workspace_file(workspace_id: str, relative_path: str, root: Path | None = None) -> ToolResult:
    target, policy = resolve_repo_tool_path(workspace_id, relative_path, root, write=False)
    if not policy.allowed or target is None:
        return blocked_tool_result("file", "; ".join(policy.messages), predictive_signal="agent_file_read_blocked")
    if not target.exists() or not target.is_file():
        return blocked_tool_result("file", "File does not exist.", predictive_signal="agent_file_missing")
    try:
        raw = target.read_bytes()
        if len(raw) > MAX_READ_BYTES:
            return blocked_tool_result("file", "File is too large for agent read tool.", predictive_signal="agent_file_too_large")
        return done_tool_result(
            "file",
            stdout=sanitize_agent_text(raw.decode("utf-8", errors="replace"), MAX_READ_BYTES),
            predictive_signal="agent_file_read_completed",
        )
    except Exception as exc:
        return failed_tool_result("file", str(exc), predictive_signal="agent_file_read_failed")


def write_workspace_file(
    workspace_id: str,
    relative_path: str,
    content: str,
    root: Path | None = None,
    *,
    create_parent: bool = True,
) -> ToolResult:
    target, policy = resolve_repo_tool_path(workspace_id, relative_path, root, write=True)
    if not policy.allowed or target is None:
        return blocked_tool_result("file", "; ".join(policy.messages), predictive_signal="agent_file_write_blocked")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_WRITE_BYTES:
        return blocked_tool_result("file", "File content is too large for agent write tool.", predictive_signal="agent_file_too_large")
    try:
        if create_parent:
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return done_tool_result(
            "file",
            changed_files=(relative_path.replace("\\", "/").removeprefix("./"),),
            predictive_signal="agent_file_changed",
        )
    except Exception as exc:
        return failed_tool_result("file", str(exc), predictive_signal="agent_file_write_failed")
