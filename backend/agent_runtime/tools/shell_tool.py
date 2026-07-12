"""Shell tool for Sovereign Agent Runtime.

Provides safe shell command execution within workspace boundaries.
All commands are validated against workspace policy and blocked
if they attempt to access forbidden paths or commands.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
import re
from typing import Any

from .base import ToolBase, ToolResult, ToolPolicyError


# Only read-only inspection commands are allowed. Mutation uses dedicated tools.
_ALLOWED_COMMANDS = frozenset({"ls", "pwd"})
_SHELL_CONTROL_TOKENS = frozenset({"&&", "||", ";", "|", ">", ">>", "<", "<<", "&"})

# Forbidden patterns in command arguments
_FORBIDDEN_PATTERNS = [
    (r"/etc/passwd", "Access to /etc/passwd blocked"),
    (r"/etc/shadow", "Access to /etc/shadow blocked"),
    (r"\.env(?:\s|$)", "Direct .env access blocked"),
    (r">\s*/dev/", "Device file write blocked"),
    (r"2>&1\s*&\s*$", "Background redirect to /dev blocked"),
    (r"\$\([^)]*\)", "Command substitution blocked"),
    (r"`[^`]+`", "Backtick command substitution blocked"),
]


class ShellTool(ToolBase):
    """Execute shell commands within workspace boundaries."""

    name = "shell"
    description = "Execute a shell command in the workspace"
    parameters = {
        "command": {
            "type": "string",
            "required": True,
            "description": "Shell command to execute",
        },
        "cwd": {
            "type": "string",
            "required": False,
            "description": "Working directory (relative to workspace)",
        },
        "timeout": {
            "type": "integer",
            "required": False,
            "default": 60,
            "description": "Command timeout in seconds (default: 60)",
        },
        "env": {
            "type": "object",
            "required": False,
            "description": "Additional environment variables",
        },
    }
    requires_workspace = True

    def validate(self, params: dict[str, Any]) -> None:
        super().validate(params)
        command = params.get("command", "")
        self._validate_command(command)

    def _parse_command(self, command: str) -> list[str]:
        if not command or not command.strip():
            raise ToolPolicyError("Empty command not allowed")
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            raise ToolPolicyError(f"Invalid command: {exc}") from exc
        if not tokens:
            raise ToolPolicyError("Empty command not allowed")
        for pattern, message in _FORBIDDEN_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                raise ToolPolicyError(message)
        if tokens[-1] == "&":
            raise ToolPolicyError("Background commands (&) not allowed")
        first_cmd = tokens[0]
        if first_cmd not in _ALLOWED_COMMANDS:
            raise ToolPolicyError(f"Forbidden command: {first_cmd}")
        if any(token in _SHELL_CONTROL_TOKENS for token in tokens):
            raise ToolPolicyError("Shell control operators are not allowed")
        if first_cmd == "ls":
            for token in tokens[1:]:
                if token.startswith("-"):
                    continue
                candidate = Path(token)
                if candidate.is_absolute() or ".." in candidate.parts:
                    raise ToolPolicyError("ls path must stay inside workspace")
        return tokens

    def _validate_command(self, command: str) -> None:
        """Validate command against the read-only argv policy."""
        self._parse_command(command)

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace path provided")

        command = params.get("command", "")
        cwd = params.get("cwd", ".")
        timeout = min(params.get("timeout", 60), 300)
        try:
            args = self._parse_command(command)
        except ToolPolicyError as exc:
            return ToolResult(status="blocked", blocker=str(exc))

        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace provided")

        work_dir = Path(workspace_path)
        if cwd and cwd != ".":
            work_dir = work_dir / cwd
            work_dir = work_dir.resolve()
            if not work_dir.is_relative_to(Path(workspace_path).resolve()):
                return ToolResult(
                    status="blocked",
                    blocker="Working directory outside workspace",
                )
            if not work_dir.exists():
                return ToolResult(
                    status="error",
                    error=f"Working directory does not exist: {cwd}",
                )

        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(work_dir),
            "USER": "agent",
            "PWD": str(work_dir),
            "GIT_TERMINAL_PROMPT": "0",
        }

        try:
            result = subprocess.run(
                args,
                shell=False,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )

            output = result.stdout
            if result.stderr:
                output = output + "\n" + result.stderr if output else result.stderr

            normalized_output = output.strip() if output else ""
            succeeded = result.returncode == 0

            return ToolResult(
                status="done" if succeeded else "error",
                output=normalized_output,
                error=None if succeeded else (
                    normalized_output or f"Command failed with exit code {result.returncode}"
                ),
                metadata={
                    "exit_code": result.returncode,
                    "command": " ".join(args)[:200],
                    "timeout": timeout,
                },
                exit_code=result.returncode,
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                status="blocked",
                blocker=f"Command timed out after {timeout}s",
            )
        except Exception as e:
            return ToolResult(
                status="error",
                error=f"Execution failed: {e}",
            )
