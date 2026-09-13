"""Process-local Git trust for one server-resolved Agent workspace.

Callers must first authorize and resolve the workspace through the Job boundary.
This helper neither grants repository access nor changes any Git config file.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


def workspace_git_environment(
    workspace_path: str | Path,
    *,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Trust exactly one directory, including in Git children of test runners.

    An empty entry resets inherited wildcard/directory exceptions for this child
    only. Tests must supply their existing secret-free environment explicitly.
    """
    raw_path = str(workspace_path)
    if not raw_path or "\x00" in raw_path or "*" in raw_path:
        raise ValueError("Git workspace must be one explicit directory")
    root = str(Path(raw_path).resolve())
    if "*" in root or root == str(Path(root).anchor):
        raise ValueError("Git workspace must not be a wildcard or filesystem root")
    env = dict(os.environ if base_env is None else base_env)
    raw_count = env.get("GIT_CONFIG_COUNT", "") or "0"
    if not raw_count.isascii() or not raw_count.isdecimal() or len(raw_count) > 3:
        raise ValueError("Git command configuration count is invalid")
    count = int(raw_count)
    if count > 128:
        raise ValueError("Git command configuration count exceeds its bound")
    for index in range(count):
        if f"GIT_CONFIG_KEY_{index}" not in env or f"GIT_CONFIG_VALUE_{index}" not in env:
            raise ValueError("Git command configuration pair is incomplete")
    # Legacy CLI configuration and sudo identity may override this exact scope.
    env.pop("GIT_CONFIG_PARAMETERS", None)
    env.pop("SUDO_UID", None)
    env[f"GIT_CONFIG_KEY_{count}"] = "safe.directory"
    env[f"GIT_CONFIG_VALUE_{count}"] = ""
    env[f"GIT_CONFIG_KEY_{count + 1}"] = "safe.directory"
    env[f"GIT_CONFIG_VALUE_{count + 1}"] = root
    env["GIT_CONFIG_COUNT"] = str(count + 2)
    return env
