"""Bounded, fail-closed MCP Git workspace admission and verified cleanup.

The MCP operator has its own workspace root, separate from the backend job
runtime. Only workspace directories explicitly marked by this module are
eligible for deletion; unknown directories are never pruned as a side effect.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Iterator

MAX_WORKSPACES = 12
DISK_RESERVE_PPM = 200_000
MIN_FREE_BYTES = 4 * (1 << 30)
_LOCK_NAME = ".sovereign-workspace-admission.lock"
_OWNERSHIP_MARKER = ".sovereign-mcp-owned"
_OWNERSHIP_VALUE = "mcp-v1\n"
_ID_PATTERN = re.compile(r"job-[0-9a-f]{12}\Z")


class WorkspaceLifecycleError(RuntimeError):
    """Workspace admission or cleanup cannot be verified."""


def _root(root: Path) -> Path:
    directory = Path(root).expanduser()
    if directory.is_symlink() or not directory.is_dir():
        raise WorkspaceLifecycleError("WORKSPACE_ROOT_INVALID")
    return directory.resolve(strict=True)


def _workspace_id(value: str) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise WorkspaceLifecycleError("WORKSPACE_ID_INVALID")
    return value


def workspace_inventory(root: Path) -> dict[str, object]:
    """Read-only inventory: no deletion, no authentication or secret output."""
    directory = _root(root)
    managed: list[str] = []
    total = 0
    for entry in directory.iterdir():
        if entry.name == _LOCK_NAME:
            continue
        if entry.is_symlink() or entry.is_dir():
            total += 1
            if (not entry.is_symlink() and _ID_PATTERN.fullmatch(entry.name)
                    and (entry / _OWNERSHIP_MARKER).is_file()
                    and not (entry / _OWNERSHIP_MARKER).is_symlink()
                    and (entry / _OWNERSHIP_MARKER).read_text("utf-8") == _OWNERSHIP_VALUE):
                managed.append(entry.name)
    return {
        "total_directories": total,
        "managed_workspaces": sorted(managed),
        "maximum_workspaces": MAX_WORKSPACES,
    }


@contextmanager
def _exclusive_lock(root: Path) -> Iterator[Path]:
    directory = _root(root)
    lock_path = directory / _LOCK_NAME
    flags = os.O_RDONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(lock_path, flags, 0o600)
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise WorkspaceLifecycleError("WORKSPACE_LOCK_INVALID")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WorkspaceLifecycleError("WORKSPACE_PROVISION_BUSY") from exc
        try:
            yield directory
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError as exc:
        raise WorkspaceLifecycleError("WORKSPACE_LOCK_UNAVAILABLE") from exc
    finally:
        if "fd" in locals():
            os.close(fd)


@contextmanager
def workspace_creation_guard(root: Path) -> Iterator[dict[str, object]]:
    """Check root, quota and disk reserve while holding cross-process lock."""
    with _exclusive_lock(root) as directory:
        inventory = workspace_inventory(directory)
        if int(inventory["total_directories"]) >= MAX_WORKSPACES:
            raise WorkspaceLifecycleError("WORKSPACE_COUNT_EXHAUSTED")
        try:
            usage = shutil.disk_usage(directory)
        except OSError as exc:
            raise WorkspaceLifecycleError("DISK_PROBE_UNAVAILABLE") from exc
        reserve = max(MIN_FREE_BYTES, (usage.total * DISK_RESERVE_PPM + 999_999) // 1_000_000)
        if usage.free < reserve:
            raise WorkspaceLifecycleError("DISK_RESERVE_EXHAUSTED")
        yield {
            **inventory,
            "free_bytes": usage.free,
            "reserve_bytes": reserve,
        }


def mark_workspace_owned(workspace: Path) -> None:
    """Write an ownership marker before cloning, never overwrite unknown content."""
    if workspace.is_symlink() or not workspace.is_dir():
        raise WorkspaceLifecycleError("WORKSPACE_OWNERSHIP_UNVERIFIED")
    marker = workspace / _OWNERSHIP_MARKER
    with marker.open("x", encoding="utf-8") as handle:
        handle.write(_OWNERSHIP_VALUE)


def cleanup_managed_workspace(
    root: Path,
    workspace_id: str,
    expected_repository: str,
    *,
    abandon_confirmed: bool = False,
) -> dict[str, object]:
    """Delete only a marked workspace after verified publication or owner discard.

    Caller must independently verify the remote Draft PR before setting
    draft_pr_verified in metadata. A local flag alone is not publication
    evidence; this function only enforces the cleanup/discard boundary.
    """
    safe_id = _workspace_id(workspace_id)
    with _exclusive_lock(root) as directory:
        target = directory / safe_id
        if target.is_symlink():
            raise WorkspaceLifecycleError("WORKSPACE_SYMLINK_BLOCKED")
        if not target.exists():
            return {"status": "WORKSPACE_ALREADY_ABSENT", "workspace_id": safe_id, "readback_absent": True}
        if not target.is_dir():
            raise WorkspaceLifecycleError("WORKSPACE_DIRECTORY_INVALID")
        marker = target / _OWNERSHIP_MARKER
        if marker.is_symlink() or not marker.is_file() or marker.read_text("utf-8") != _OWNERSHIP_VALUE:
            raise WorkspaceLifecycleError("WORKSPACE_OWNERSHIP_UNVERIFIED")
        metadata_path = target / "workspace.json"
        if metadata_path.is_symlink() or not metadata_path.is_file():
            raise WorkspaceLifecycleError("WORKSPACE_METADATA_UNVERIFIED")
        try:
            metadata = json.loads(metadata_path.read_text("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise WorkspaceLifecycleError("WORKSPACE_METADATA_UNVERIFIED") from exc
        if not isinstance(metadata, dict) or metadata.get("workspace_id") != safe_id:
            raise WorkspaceLifecycleError("WORKSPACE_METADATA_MISMATCH")
        if metadata.get("repository") != expected_repository:
            raise WorkspaceLifecycleError("WORKSPACE_REPOSITORY_MISMATCH")
        if not abandon_confirmed and metadata.get("draft_pr_verified") is not True:
            raise WorkspaceLifecycleError("WORKSPACE_UNPUBLISHED_REQUIRES_OWNER_CONFIRMATION")
        shutil.rmtree(target)
        absent = not target.exists() and not target.is_symlink()
        if not absent:
            raise WorkspaceLifecycleError("WORKSPACE_CLEANUP_READBACK_FAILED")
        return {"status": "WORKSPACE_CLEANED", "workspace_id": safe_id, "readback_absent": True}
