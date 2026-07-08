"""Tests for agent internal tools.

Verifies that tools execute correctly within workspace boundaries.
"""

import pytest
import tempfile
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent_runtime.tools.base import ToolResult
from agent_runtime.tools.file_tool import FileReadTool, FileWriteTool, FileListTool
from agent_runtime.tools.shell_tool import ShellTool
from agent_runtime.tools.git_tool import GitStatusTool, GitDiffTool, GitAddTool


class TestFileReadTool:
    """Test FileReadTool execution."""

    def test_read_existing_file(self, tmp_path):
        """Should read existing file content."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        tool = FileReadTool()
        result = tool.execute({"path": "test.txt"}, str(tmp_path))

        assert result.is_ok()
        assert result.output == "Hello, World!"
        assert result.metadata["path"] == "test.txt"

    def test_read_with_max_bytes(self, tmp_path):
        """Should respect max_bytes limit."""
        test_file = tmp_path / "large.txt"
        test_file.write_text("x" * 1000)

        tool = FileReadTool()
        result = tool.execute({"path": "large.txt", "max_bytes": 100}, str(tmp_path))

        assert result.is_blocked()
        assert "max_bytes" in result.blocker.lower()

    def test_read_unicode_content(self, tmp_path):
        """Should handle unicode content."""
        test_file = tmp_path / "unicode.txt"
        test_file.write_text("Héllo, Wörld! 🌍")

        tool = FileReadTool()
        result = tool.execute({"path": "unicode.txt"}, str(tmp_path))

        assert result.is_ok()
        assert "Héllo" in result.output


class TestFileWriteTool:
    """Test FileWriteTool execution."""

    def test_write_new_file(self, tmp_path):
        """Should create new file with content."""
        tool = FileWriteTool()
        result = tool.execute(
            {"path": "new_file.txt", "content": "Test content"},
            str(tmp_path)
        )

        assert result.is_ok()
        assert (tmp_path / "new_file.txt").exists()
        assert (tmp_path / "new_file.txt").read_text() == "Test content"

    def test_write_creates_parent_dirs(self, tmp_path):
        """Should create parent directories if needed."""
        tool = FileWriteTool()
        result = tool.execute(
            {"path": "nested/dir/file.txt", "content": "Nested"},
            str(tmp_path)
        )

        assert result.is_ok()
        assert (tmp_path / "nested" / "dir" / "file.txt").exists()

    def test_write_append_mode(self, tmp_path):
        """Should append to existing file when append=True."""
        test_file = tmp_path / "append.txt"
        test_file.write_text("Original\n")

        tool = FileWriteTool()
        result = tool.execute(
            {"path": "append.txt", "content": "Appended\n", "append": True},
            str(tmp_path)
        )

        assert result.is_ok()
        assert test_file.read_text() == "Original\nAppended\n"


class TestFileListTool:
    """Test FileListTool execution."""

    def test_list_directory(self, tmp_path):
        """Should list files in directory."""
        (tmp_path / "file1.txt").touch()
        (tmp_path / "file2.txt").touch()
        (tmp_path / "file3.log").touch()

        tool = FileListTool()
        result = tool.execute({"path": "."}, str(tmp_path))

        assert result.is_ok()
        assert "file1.txt" in result.output
        assert "file2.txt" in result.output
        assert "file3.log" in result.output

    def test_list_with_pattern(self, tmp_path):
        """Should filter files by pattern."""
        (tmp_path / "a.txt").touch()
        (tmp_path / "b.txt").touch()
        (tmp_path / "c.log").touch()

        tool = FileListTool()
        result = tool.execute({"path": ".", "pattern": "*.txt"}, str(tmp_path))

        assert result.is_ok()
        assert "a.txt" in result.output
        assert "b.txt" in result.output
        assert "c.log" not in result.output


class TestShellTool:
    """Test ShellTool execution."""

    def test_shell_ls_command(self, tmp_path):
        """Should execute ls command."""
        (tmp_path / "file1.txt").touch()
        (tmp_path / "file2.txt").touch()

        tool = ShellTool()
        result = tool.execute({"command": "ls"}, str(tmp_path))

        assert result.is_ok()
        assert "file1.txt" in result.output
        assert result.metadata["exit_code"] == 0

    def test_shell_with_cwd(self, tmp_path):
        """Should respect cwd parameter."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").touch()

        tool = ShellTool()
        result = tool.execute(
            {"command": "ls", "cwd": "subdir"},
            str(tmp_path)
        )

        assert result.is_ok()
        assert "file.txt" in result.output

    def test_shell_timeout(self, tmp_path):
        """Should respect timeout parameter."""
        tool = ShellTool()
        result = tool.execute(
            {"command": "sleep 10", "timeout": 1},
            str(tmp_path)
        )

        assert result.is_blocked()
        assert "timed out" in result.blocker.lower()

    def test_shell_captures_stderr(self, tmp_path):
        """Should capture stderr output."""
        tool = ShellTool()
        result = tool.execute({"command": "ls /nonexistent"}, str(tmp_path))

        assert result.metadata["exit_code"] != 0
        assert "no such file" in result.output.lower()


class TestGitStatusTool:
    """Test GitStatusTool execution."""

    def test_status_requires_git_repo(self, tmp_path):
        """Should block if not a git repository."""
        tool = GitStatusTool()
        result = tool.execute({}, str(tmp_path))

        assert result.is_blocked()
        assert "git" in result.blocker.lower()

    def test_status_clean_repo(self, tmp_path):
        """Should report clean status for clean repo."""
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, check=True)

        tool = GitStatusTool()
        result = tool.execute({}, str(tmp_path))

        assert result.is_ok()
        assert "clean" in result.output.lower() or result.output == ""

    def test_status_with_changes(self, tmp_path):
        """Should report changed files."""
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)

        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        subprocess.run(["git", "add", "test.txt"], cwd=tmp_path, check=True)

        tool = GitStatusTool()
        result = tool.execute({}, str(tmp_path))

        assert result.is_ok()
        assert result.metadata["changed_files"] > 0


class TestGitDiffTool:
    """Test GitDiffTool execution."""

    def test_diff_requires_git_repo(self, tmp_path):
        """Should block if not a git repository."""
        tool = GitDiffTool()
        result = tool.execute({}, str(tmp_path))

        assert result.is_blocked()
        assert "git" in result.blocker.lower()

    def test_diff_with_staged_changes(self, tmp_path):
        """Should show staged diff."""
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)

        test_file = tmp_path / "test.txt"
        test_file.write_text("original")
        subprocess.run(["git", "add", "test.txt"], cwd=tmp_path, check=True)
        test_file.write_text("modified")

        tool = GitDiffTool()
        result = tool.execute({"staged": True}, str(tmp_path))

        assert result.is_ok()


class TestToolExecutionIntegration:
    """Integration tests for tool execution."""

    def test_file_write_then_read(self, tmp_path):
        """Should be able to write then read a file."""
        write_tool = FileWriteTool()
        write_result = write_tool.execute(
            {"path": "integration.txt", "content": "Integration test"},
            str(tmp_path)
        )
        assert write_result.is_ok()

        read_tool = FileReadTool()
        read_result = read_tool.execute({"path": "integration.txt"}, str(tmp_path))
        assert read_result.is_ok()
        assert read_result.output == "Integration test"

    def test_shell_and_file_integration(self, tmp_path):
        """Should integrate shell and file tools."""
        shell_tool = ShellTool()
        shell_result = shell_tool.execute(
            {"command": "echo 'Shell content' > shell_test.txt"},
            str(tmp_path)
        )
        assert shell_result.is_ok()

        read_tool = FileReadTool()
        read_result = read_tool.execute({"path": "shell_test.txt"}, str(tmp_path))
        assert read_result.is_ok()
        assert "Shell content" in read_result.output
