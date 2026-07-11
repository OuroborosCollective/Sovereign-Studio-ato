"""Test tool for Sovereign Agent Runtime.

Provides test execution within workspace boundaries.
Supports running tests for various test frameworks.
"""

from __future__ import annotations

import os
import subprocess
import json
from pathlib import Path
from typing import Any

from .base import ToolBase, ToolResult, ToolPolicyError


class TestTool(ToolBase):
    """Run tests in the workspace repository."""

    name = "test"
    description = "Run tests in the workspace repository"
    parameters = {
        "command": {
            "type": "string",
            "required": False,
            "description": "Test command to run (auto-detected if not specified)",
        },
        "path": {
            "type": "string",
            "required": False,
            "description": "Specific path to run tests for",
        },
        "framework": {
            "type": "string",
            "required": False,
            "description": "Force specific test framework (pytest, jest, go test, etc.)",
        },
        "timeout": {
            "type": "integer",
            "required": False,
            "default": 120,
            "description": "Test timeout in seconds (default: 120)",
        },
        "verbose": {
            "type": "boolean",
            "required": False,
            "default": True,
            "description": "Verbose output (default: True)",
        },
    }
    requires_workspace = True

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No workspace path provided")

        command = params.get("command")
        test_path = params.get("path")
        framework = params.get("framework")
        timeout = min(params.get("timeout", 120), 600)
        verbose = params.get("verbose", True)

        work_dir = Path(workspace_path)
        if test_path:
            work_dir = work_dir / test_path
            work_dir = work_dir.resolve()
            if not str(work_dir).startswith(str(Path(workspace_path).resolve())):
                return ToolResult(
                    status="blocked",
                    blocker="Test path outside workspace",
                )

        if command:
            return self._run_custom_command(command, str(work_dir), timeout, verbose)

        if framework:
            return self._run_framework(framework, str(work_dir), timeout, verbose)

        detected = self._detect_framework(workspace_path)
        if not detected:
            return ToolResult(
                status="blocked",
                blocker="No test framework detected. Specify 'command' or 'framework' parameter.",
            )

        return self._run_framework(detected, str(work_dir), timeout, verbose)

    def _detect_framework(self, workspace_path: str) -> str | None:
        """Auto-detect test framework from project files."""
        base = Path(workspace_path)

        if (base / "pytest.ini").exists():
            return "pytest"
        if (base / "pyproject.toml").exists():
            content = (base / "pyproject.toml").read_text(errors="replace")
            if "[tool.pytest" in content or "[tool.unittest" in content:
                return "pytest"
        if (base / "setup.py").exists():
            return "pytest"

        if (base / "package.json").exists():
            content = (base / "package.json").read_text(errors="replace")
            try:
                pkg = json.loads(content)
                if "jest" in str(pkg.get("dependencies", {})):
                    return "jest"
                if "vitest" in str(pkg.get("dependencies", {})):
                    return "vitest"
                if "scripts" in pkg:
                    scripts = pkg["scripts"]
                    if "test" in scripts:
                        return "npm"
            except Exception:
                pass

        if (base / "go.mod").exists():
            return "go test"

        if (base / "Cargo.toml").exists():
            return "cargo test"

        return None

    def _run_framework(
        self,
        framework: str,
        cwd: str,
        timeout: int,
        verbose: bool,
    ) -> ToolResult:
        """Run tests with a specific framework."""
        framework = framework.lower()

        if framework == "pytest":
            args = ["pytest", "-v"] if verbose else ["pytest"]
            args.extend(["--tb=short", "--color=no"])
        elif framework == "jest":
            args = ["npx", "jest", "--passWithNoTests"] if verbose else ["npx", "jest"]
        elif framework == "vitest":
            args = ["npx", "vitest", "run"] if not verbose else ["npx", "vitest"]
        elif framework == "go test":
            args = ["go", "test", "-v"] if verbose else ["go", "test"]
            args.extend(["./..."])
        elif framework == "cargo test":
            args = ["cargo", "test", "--", "--nocapture"] if verbose else ["cargo", "test"]
        elif framework == "npm":
            args = ["npm", "test"]
        else:
            return ToolResult(
                status="blocked",
                blocker=f"Unknown test framework: {framework}",
            )

        return self._run_command(args, cwd, timeout)

    def _run_custom_command(
        self,
        command: str,
        cwd: str,
        timeout: int,
        verbose: bool,
    ) -> ToolResult:
        """Run a custom test command."""
        if verbose:
            print(f"Running: {command}")

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "FORCE_COLOR": "0",
                },
            )

            output = result.stdout + "\n" + result.stderr if result.stderr else result.stdout
            normalized_output = output.strip()
            passed = result.returncode == 0

            return ToolResult(
                status="done" if passed else "error",
                output=normalized_output,
                error=None if passed else (
                    normalized_output or f"Test command failed with exit code {result.returncode}"
                ),
                metadata={
                    "exit_code": result.returncode,
                    "passed": passed,
                    "framework": "custom",
                },
                exit_code=result.returncode,
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                status="blocked",
                blocker=f"Test command timed out after {timeout}s",
            )
        except Exception as e:
            return ToolResult(
                status="error",
                error=f"Test execution failed: {e}",
            )

    def _run_command(
        self,
        args: list[str],
        cwd: str,
        timeout: int,
    ) -> ToolResult:
        """Run a test command with arguments."""
        try:
            result = subprocess.run(
                args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "FORCE_COLOR": "0",
                },
            )

            output = result.stdout + "\n" + result.stderr if result.stderr else result.stdout
            normalized_output = output.strip()
            passed = result.returncode == 0

            return ToolResult(
                status="done" if passed else "error",
                output=normalized_output,
                error=None if passed else (
                    normalized_output or f"Tests failed with exit code {result.returncode}"
                ),
                metadata={
                    "exit_code": result.returncode,
                    "passed": passed,
                    "command": " ".join(args),
                },
                exit_code=result.returncode,
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                status="blocked",
                blocker=f"Tests timed out after {timeout}s",
            )
        except FileNotFoundError as e:
            return ToolResult(
                status="blocked",
                blocker=f"Test command not found: {e}",
            )
        except Exception as e:
            return ToolResult(
                status="error",
                error=f"Test execution failed: {e}",
            )
