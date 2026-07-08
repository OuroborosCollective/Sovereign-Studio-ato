"""Workspace policy for Sovereign Agent Runtime.

This module owns path and workspace safety. It performs no UI work and does not
claim success; it either returns an allowed path/state or raises a policy error.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
from urllib.parse import urlparse

from .contracts import is_valid_github_repo_url, normalize_agent_path

_DEFAULT_WORKSPACE_ROOT = "/tmp/sovereign-agent/workspaces"
_SAFE_WORKSPACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
_SAFE_BRANCH = re.compile(r"^[\w./-]{1,160}$")
_SECRET_URL_TOKENS = ("@", "token=", "password=", "secret=", "api_key=", "apikey=")


class WorkspacePolicyError(ValueError):
    """Raised when a workspace request violates Sovereign runtime policy."""


def workspace_root() -> Path:
    return Path(os.getenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", _DEFAULT_WORKSPACE_ROOT)).expanduser().resolve()


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
