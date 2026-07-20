"""Workspace policy for Sovereign Agent Runtime.

This module owns path and workspace safety. It performs no UI work and does not
claim success; it either returns an allowed path/state or raises a policy error.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
import re
from urllib.parse import urlparse

from .contracts import is_valid_github_repo_url, normalize_agent_path

_DEFAULT_WORKSPACE_ROOT = "/var/lib/sovereign-agent/workspaces"
_DEFAULT_WORKSPACE_UID = 10001
_DEFAULT_WORKSPACE_GID = 10001
_SAFE_WORKSPACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
_SAFE_BRANCH = re.compile(r"^[\w./-]{1,160}$")
_SECRET_URL_TOKENS = ("@", "token=", "password=", "secret=", "api_key=", "apikey=")


class WorkspacePolicyError(ValueError):
    """Raised when a workspace request violates Sovereign runtime policy."""


def workspace_root() -> Path:
    return Path(os.getenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", _DEFAULT_WORKSPACE_ROOT)).expanduser().resolve()


def workspace_runtime_identity() -> tuple[int, int]:
    try:
        uid = int(os.getenv("SOVEREIGN_AGENT_WORKSPACE_UID", str(_DEFAULT_WORKSPACE_UID)))
        gid = int(os.getenv("SOVEREIGN_AGENT_WORKSPACE_GID", str(_DEFAULT_WORKSPACE_GID)))
    except ValueError as exc:
        raise WorkspacePolicyError("workspace runtime identity is invalid") from exc
    if uid < 1 or gid < 1 or uid > 2_147_483_647 or gid > 2_147_483_647:
        raise WorkspacePolicyError("workspace runtime identity is outside the allowed range")
    return uid, gid


def normalize_workspace_permissions(path: Path, root: Path | None = None) -> None:
    base = (root or workspace_root()).resolve()
    target = path.resolve()
    if target != base and base not in target.parents:
        raise WorkspacePolicyError("workspace permission target escapes the workspace root")
    uid, gid = workspace_runtime_identity()
    candidates = [target]
    if target.is_dir():
        candidates.extend(sorted(target.rglob("*")))
    for candidate in candidates:
        if candidate.is_symlink():
            continue
        mode = candidate.stat().st_mode
        if os.geteuid() == 0:
            os.chown(candidate, uid, gid)
        if candidate.is_dir():
            candidate.chmod(0o2770)
        elif candidate.is_file():
            execute_bits = mode & (stat.S_IXUSR | stat.S_IXGRP)
            candidate.chmod(0o660 | execute_bits)


def assert_safe_workspace_id(workspace_id: str) -> str:
    clean = workspace_id.strip()
    if not _SAFE_WORKSPACE_ID.fullmatch(clean):
        raise WorkspacePolicyError("workspace id contains unsafe characters")
    if ".." in clean:
        raise WorkspacePolicyError("workspace id may not contain traversal markers")
    return clean


def safe_workspace_path(workspace_id: str, root: Path | None = None) -> Path:
    safe_id = assert_safe_workspace_id(workspace_id)
    base = (root or workspace_root()).resolve()
    path = (base / safe_id).resolve()
    if path != base and base not in path.parents:
        raise WorkspacePolicyError("workspace path escape blocked")
    return path


def repo_dir_for_workspace(workspace_id: str, root: Path | None = None) -> Path:
    return safe_workspace_path(workspace_id, root) / "repo"


def validate_workspace_branch(branch: str) -> str:
    clean = branch.strip() or "main"
    if not _SAFE_BRANCH.fullmatch(clean) or ".." in clean:
        raise WorkspacePolicyError("workspace branch contains unsafe characters")
    return clean


def validate_workspace_relative_path(path: str) -> str:
    clean = normalize_agent_path(path)
    if not clean:
        raise WorkspacePolicyError("workspace relative path is unsafe")
    if clean.startswith(".git/") or clean == ".git":
        raise WorkspacePolicyError("workspace may not access .git internals directly")
    return clean


def validate_repo_url_for_workspace(repo_url: str) -> str:
    clean = repo_url.strip()
    parsed = urlparse(clean)
    if parsed.username or parsed.password:
        raise WorkspacePolicyError("repo URL may not embed credentials")
    lower = clean.lower()
    if any(token in lower for token in _SECRET_URL_TOKENS if token != "@"):
        raise WorkspacePolicyError("repo URL contains secret-like query or token material")
    if not is_valid_github_repo_url(clean):
        raise WorkspacePolicyError("workspace requires a valid HTTPS GitHub repository URL")
    return clean


def ensure_path_inside_workspace(workspace_id: str, relative_path: str, root: Path | None = None) -> Path:
    clean = validate_workspace_relative_path(relative_path)
    workspace = safe_workspace_path(workspace_id, root)
    target = (workspace / clean).resolve()
    if target != workspace and workspace not in target.parents:
        raise WorkspacePolicyError("workspace target path escape blocked")
    return target
