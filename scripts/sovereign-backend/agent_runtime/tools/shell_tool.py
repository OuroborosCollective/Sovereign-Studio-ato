"""Shell tool for Sovereign Agent Runtime.

Provides safe shell command execution within workspace boundaries.
All commands are validated against workspace policy and blocked
if they attempt to access forbidden paths or commands.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
import re
from typing import Any

from .base import ToolBase, ToolResult, ToolPolicyError


# Forbidden commands that could compromise the runtime
_FORBIDDEN_COMMANDS = frozenset({
    "sudo", "su", "passwd", "chpasswd", "adduser", "useradd", "userdel",
    "curl", "wget", "nc", "netcat", "ncat", "socat",
    "ssh", "scp", "sftp", "rsync",
    "mount", "umount", "fdisk", "mkfs", "dd",
    "shutdown", "reboot", "halt", "poweroff", "init",
    "kill", "killall", "pkill", "killall5",
    "chmod", "chown", "chgrp", "setfacl",
    "iptables", "ip", "ifconfig", "route", "netstat",
    "docker", "podman", "containerd",
    "python", "python3", "node", "ruby", "perl", "php",
})

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

    def _validate_command(self, command: str) -> None:
        """Validate command against security policy."""
        if not command or not command.strip():
            raise ToolPolicyError("Empty command not allowed")

        tokens = command.strip().split()
        if not tokens:
            raise ToolPolicyError("Empty command not allowed")

        first_cmd = tokens[0]
        if first_cmd in _FORBIDDEN_COMMANDS:
            raise ToolPolicyError(f"Forbidden command: {first_cmd}")

        for pattern, message in _FORBIDDEN_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                raise ToolPolicyError(message)

        if re.search(r"\|", command):
            pipe_cmds = command.split("|")
            for cmd in pipe_cmds:
                cmd = cmd.strip().split()[0] if cmd.strip() else ""
                if cmd in _FORBIDDEN_COMMANDS:
                    raise ToolPolicyError(f"Forbidden command in pipeline: {cmd}")

        if re.search(r"&\s*$", command.strip()):
            raise ToolPolicyError("Background commands (&) not allowed")

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace path provided")

        command = params.get("command", "")
        cwd = params.get("cwd", ".")
        timeout = min(params.get("timeout", 60), 300)
        extra_env = params.get("env", {})

        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace provided")

        work_dir = Path(workspace_path)
        if cwd and cwd != ".":
            work_dir = work_dir / cwd
            work_dir = work_dir.resolve()
            if not str(work_dir).startswith(str(Path(workspace_path).resolve())):
                return ToolResult(
                    status="blocked",
                    blocker="Working directory outside workspace",
                )
            if not work_dir.exists():
                return ToolResult(
                    status="error",
                    error=f"Working directory does not exist: {cwd}",
                )

        env = os.environ.copy()
        env["HOME"] = str(work_dir)
        env["USER"] = "agent"
        env["PWD"] = str(work_dir)
        for key, value in extra_env.items():
            if not _contains_secret(key, value):
                env[key] = value

        try:
            result = subprocess.run(
                command,
                shell=True,
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
                    "command": command[:200],
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


def _contains_secret(key: str, value: str) -> bool:
    """Check if a key-value pair looks like a secret."""
    key_lower = key.lower()
    secret_names = {"token", "key", "secret", "password", "passwd", "credential", "auth"}
    return any(s in key_lower for s in secret_names)
