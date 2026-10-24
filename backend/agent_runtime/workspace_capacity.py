"""Fail-closed resource admission for Sovereign agent workspaces and Git clones.

A shared filesystem lock serializes provisioning across backend processes.
The quota is applied before directory creation AND before every Git clone.
This is a safety gate, not a garbage collector or a per-container storage limit.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import shutil
import stat
from typing import Iterator

MAX_WORKSPACES = 12
DISK_RESERVE_PPM = 200_000  # always keep at least 20% available
MIN_FREE_BYTES = 4 * (1 << 30)
_LOCK_NAME = ".sovereign-workspace-admission.lock"


class WorkspaceCapacityError(RuntimeError):
    """No new disk-consuming Agent Job may be admitted."""


def _verify_capacity(root: Path, *, creates_workspace: bool) -> None:
    try:
        disk = shutil.disk_usage(root)
    except OSError as exc:
        raise WorkspaceCapacityError("DISK_PROBE_UNAVAILABLE") from exc
    reserve = max(MIN_FREE_BYTES, (disk.total * DISK_RESERVE_PPM + 999_999) // 1_000_000)
    if disk.free < reserve:
        raise WorkspaceCapacityError("DISK_RESERVE_EXHAUSTED")
    if creates_workspace:
        try:
            count = 0
            for entry in root.iterdir():
                if entry.name == _LOCK_NAME:
                    continue
                if entry.is_dir() or entry.is_symlink():
                    count += 1
                    if count >= MAX_WORKSPACES:
                        raise WorkspaceCapacityError("WORKSPACE_COUNT_EXHAUSTED")
        except OSError as exc:
            raise WorkspaceCapacityError("WORKSPACE_INVENTORY_UNAVAILABLE") from exc


@contextmanager
def admit_workspace_operation(root: Path, *, creates_workspace: bool) -> Iterator[None]:
    """Hold a single cross-process lock during one workspace creation or Git clone.

    Busy or unhealthy hosts reject new work immediately; never queue unbounded
    clone processes and never prune unknown or user-authored directories.
    """
    directory = Path(root).expanduser()
    if directory.is_symlink():
        raise WorkspaceCapacityError("WORKSPACE_ROOT_SYMLINK")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        directory = directory.resolve(strict=True)
    except OSError as exc:
        raise WorkspaceCapacityError("WORKSPACE_ROOT_UNAVAILABLE") from exc
    lock = directory / _LOCK_NAME
    if lock.is_symlink():
        raise WorkspaceCapacityError("WORKSPACE_LOCK_INVALID")
    flags = os.O_RDONLY | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(lock, flags, 0o644)
    except OSError as exc:
        raise WorkspaceCapacityError("WORKSPACE_LOCK_INVALID") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
            raise WorkspaceCapacityError("WORKSPACE_LOCK_INVALID")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WorkspaceCapacityError("WORKSPACE_PROVISION_BUSY") from exc
        except OSError as exc:
            raise WorkspaceCapacityError("WORKSPACE_LOCK_UNAVAILABLE") from exc
        _verify_capacity(directory, creates_workspace=creates_workspace)
        yield
    finally:
        os.close(fd)
