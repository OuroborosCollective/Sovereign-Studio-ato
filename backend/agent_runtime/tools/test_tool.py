"""Policy-guarded test command tool."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .base import ToolResult, done_tool_result
from .shell_tool import run_workspace_shell_command

TEST_COMMAND_PREFIXES = (
    ("pnpm", "run", "type-check"),
    ("pnpm", "run", "test:release-gate"),
    ("pnpm", "run", "build:web"),
    ("pnpm", "run", "audit:all"),
    ("python", "-m", "pytest"),
    ("python3", "-m", "pytest"),
)


def _is_test_command(argv: Sequence[str]) -> bool:
    command = tuple(str(part) for part in argv)
    return any(command[: len(prefix)] == prefix for prefix in TEST_COMMAND_PREFIXES)


def run_workspace_test_command(workspace_id: str, argv: Sequence[str], root: Path | None = None) -> ToolResult:
    if not _is_test_command(argv):
        from .base import blocked_tool_result

        return blocked_tool_result("test", "Command is not an approved test/gate command.", predictive_signal="agent_test_command_blocked")
    result = run_workspace_shell_command(workspace_id, argv, root, timeout_seconds=300)
    if result.status != "done":
        return result
    summary = result.stdout or "Test command completed."
    return done_tool_result(
        "test",
        stdout=result.stdout,
        stderr=result.stderr,
        test_summary=summary,
        exit_code=result.exit_code,
        predictive_signal="agent_tests_completed",
    )
