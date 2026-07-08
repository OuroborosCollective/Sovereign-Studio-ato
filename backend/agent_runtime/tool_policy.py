"""Hard policies for Sovereign internal agent tools.

Tools may read, write or execute only after this policy layer approves the
request. A blocked policy is a valid runtime result, not an exception to hide.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from .contracts import normalize_agent_path, sanitize_agent_text
from .workspace_policy import repo_dir_for_workspace, safe_workspace_path

ToolName = Literal["file", "shell", "git", "diff", "test"]
ToolStatus = Literal["done", "blocked", "failed"]
ToolPolicyCode = Literal[
    "tool_requires_workspace",
    "tool_requires_repo",
    "tool_path_required",
    "tool_path_escape_blocked",
    "tool_path_forbidden",
    "tool_secret_path_blocked",
    "tool_command_required",
    "tool_command_forbidden",
    "tool_command_not_allowlisted",
    "tool_output_sanitized",
]

SECRET_PATH_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}

SECRET_PATH_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".keystore",
    ".jks",
)

FORBIDDEN_PATH_PREFIXES = (
    ".git/",
    "node_modules/",
    "dist/",
    "build/",
    "android/app/release/",
)

FORBIDDEN_COMMAND_PARTS = (
    "sudo",
    "rm -rf /",
    "curl ",
    "| sh",
    "wget ",
    "cat .env",
    "id_rsa",
    "BEGIN PRIVATE KEY",
    "git push origin main",
    "git push",
    "scp ",
    "ssh ",
    "chmod 777",
)

ALLOWED_COMMAND_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("pnpm", "install", "--frozen-lockfile"),
    ("pnpm", "run", "type-check"),
    ("pnpm", "run", "test:release-gate"),
    ("pnpm", "run", "build:web"),
    ("pnpm", "run", "audit:all"),
    ("python", "-m", "pytest"),
    ("python3", "-m", "pytest"),
    ("git", "status"),
    ("git", "diff"),
    ("git", "add"),
    ("git", "commit"),
)


@dataclass(frozen=True)
class ToolPolicyResult:
    allowed: bool
    blockers: tuple[ToolPolicyCode, ...] = ()
    messages: tuple[str, ...] = ()


def _blocked(code: ToolPolicyCode, message: str) -> ToolPolicyResult:
    return ToolPolicyResult(False, (code,), (sanitize_agent_text(message, 600),))


def _merge(results: Sequence[ToolPolicyResult]) -> ToolPolicyResult:
    blockers: list[ToolPolicyCode] = []
    messages: list[str] = []
    for result in results:
        blockers.extend(result.blockers)
        messages.extend(result.messages)
    return ToolPolicyResult(not blockers, tuple(dict.fromkeys(blockers)), tuple(messages))


def validate_workspace_ready(workspace_id: str, root: Path | None = None) -> ToolPolicyResult:
    workspace = safe_workspace_path(workspace_id, root)
    if not workspace.exists():
        return _blocked("tool_requires_workspace", "Workspace does not exist.")
    return ToolPolicyResult(True)


def validate_repo_ready(workspace_id: str, root: Path | None = None) -> ToolPolicyResult:
    workspace_result = validate_workspace_ready(workspace_id, root)
    if not workspace_result.allowed:
        return workspace_result
    repo_path = repo_dir_for_workspace(workspace_id, root)
    if not repo_path.exists():
        return _blocked("tool_requires_repo", "Repo directory does not exist.")
    return ToolPolicyResult(True)


def normalize_tool_path(path: str) -> str | None:
    return normalize_agent_path(path)


def validate_tool_path(path: str, *, write: bool = False) -> ToolPolicyResult:
    normalized = normalize_tool_path(path)
    if not normalized:
        return _blocked("tool_path_required", "Tool path is required and must be relative.")
    lower = normalized.lower()
    name = lower.rsplit("/", 1)[-1]
    if name in SECRET_PATH_NAMES or lower.endswith(SECRET_PATH_SUFFIXES):
        return _blocked("tool_secret_path_blocked", f"Secret-like path is blocked: {normalized}")
    if lower == ".git" or lower.startswith(FORBIDDEN_PATH_PREFIXES):
        return _blocked("tool_path_forbidden", f"Forbidden tool path: {normalized}")
    if write and (lower.startswith("dist/") or lower.startswith("build/")):
        return _blocked("tool_path_forbidden", f"Generated output path may not be primary write target: {normalized}")
    return ToolPolicyResult(True)


def resolve_repo_tool_path(workspace_id: str, path: str, root: Path | None = None, *, write: bool = False) -> tuple[Path | None, ToolPolicyResult]:
    policy = _merge((validate_repo_ready(workspace_id, root), validate_tool_path(path, write=write)))
    if not policy.allowed:
        return None, policy
    normalized = normalize_tool_path(path)
    assert normalized is not None
    repo_path = repo_dir_for_workspace(workspace_id, root).resolve()
    target = (repo_path / normalized).resolve()
    if target != repo_path and repo_path not in target.parents:
        return None, _blocked("tool_path_escape_blocked", "Tool path escapes repo workspace.")
    return target, ToolPolicyResult(True)


def validate_shell_command(argv: Sequence[str]) -> ToolPolicyResult:
    if not argv:
        return _blocked("tool_command_required", "Tool command is required.")
    text = " ".join(str(part) for part in argv)
    if any(part in text for part in FORBIDDEN_COMMAND_PARTS):
        return _blocked("tool_command_forbidden", "Shell command contains a forbidden pattern.")
    command = tuple(str(part) for part in argv)
    if not any(command[: len(prefix)] == prefix for prefix in ALLOWED_COMMAND_PREFIXES):
        return _blocked("tool_command_not_allowlisted", "Shell command is not allowlisted.")
    return ToolPolicyResult(True)
