"""Tests for Agent Evidence Gate.

Verifies that the evidence gate validates job completion properly.
"""

import pytest
from unittest.mock import MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent_runtime.evidence_gate import (
    EvidenceGate,
    EvidenceGateResult,
    JobEvidence,
    PLACEHOLDER_PATTERNS,
    FORBIDDEN_PATHS,
)


class TestEvidenceGateResult:
    """Test EvidenceGateResult dataclass."""

    def test_passed_result(self):
        """Should create a passed result."""
        result = EvidenceGateResult(
            passed=True,
            reason="All checks passed",
        )
        assert result.passed is True
        assert result.placeholder_count == 0
        assert result.forbidden_paths_found == []

    def test_failed_result(self):
        """Should create a failed result."""
        result = EvidenceGateResult(
            passed=False,
            reason="Check failed",
            placeholder_count=3,
        )
        assert result.passed is False
        assert result.placeholder_count == 3


class TestJobEvidence:
    """Test JobEvidence dataclass."""

    def test_creation(self):
        """Should create evidence with defaults."""
        evidence = JobEvidence(
            job_id="job-123",
            workspace_id="ws-456",
            repo_url="https://github.com/test/repo",
            branch="main",
            mission="Implement feature X",
        )
        assert evidence.job_id == "job-123"
        assert evidence.generated_files == []
        assert evidence.file_contents == {}


class TestPlaceholderPatterns:
    """Test placeholder pattern detection."""

    def test_placeholder_patterns_defined(self):
        """Should have placeholder patterns defined."""
        assert len(PLACEHOLDER_PATTERNS) > 0
        # Check patterns exist for common placeholders
        patterns_str = " ".join(PLACEHOLDER_PATTERNS)
        assert "Mach" in patterns_str or "TODO" in patterns_str

    def test_mission_blocks_placeholder(self):
        """Should block placeholder missions."""
        import re
        patterns = [re.compile(p, re.IGNORECASE) for p in PLACEHOLDER_PATTERNS]

        placeholders = [
            "README + Update History",
            "Mach weiter",
            "Plan",
            "Ideen",
        ]

        for ph in placeholders:
            matched = any(p.search(ph) for p in patterns)
            assert matched, f"Should detect placeholder: {ph}"


class TestForbiddenPaths:
    """Test forbidden path detection."""

    def test_forbidden_paths_defined(self):
        """Should have forbidden paths defined."""
        assert ".git" in FORBIDDEN_PATHS
        assert ".env" in FORBIDDEN_PATHS
        assert "node_modules" in FORBIDDEN_PATHS

    def test_detects_forbidden_in_path(self):
        """Should detect forbidden paths in file paths."""
        forbidden_paths = [
            ".git/config",
            ".env",
            "src/node_modules/package/index.js",
        ]

        for path in forbidden_paths:
            found = any(fp in path.split("/") for fp in FORBIDDEN_PATHS)
            assert found, f"Should detect forbidden: {path}"


class TestEvidenceGate:
    """Test EvidenceGate functionality."""

    def test_initialization(self):
        """Should initialize with workspace."""
        mock_workspace = MagicMock()
        gate = EvidenceGate(mock_workspace)
        assert gate.workspace is mock_workspace

    def test_validate_mission_empty(self):
        """Should block empty missions."""
        mock_workspace = MagicMock()
        gate = EvidenceGate(mock_workspace)

        result = gate.validate_mission_content("")
        assert result.passed is False

    def test_validate_mission_short(self):
        """Should block very short missions."""
        mock_workspace = MagicMock()
        gate = EvidenceGate(mock_workspace)

        result = gate.validate_mission_content("abc")
        assert result.passed is False

    def test_validate_mission_placeholder(self):
        """Should block placeholder missions."""
        mock_workspace = MagicMock()
        gate = EvidenceGate(mock_workspace)

        result = gate.validate_mission_content("Mach weiter")
        assert result.passed is False

    def test_validate_mission_concrete(self):
        """Should allow concrete missions."""
        mock_workspace = MagicMock()
        gate = EvidenceGate(mock_workspace)

        result = gate.validate_mission_content(
            "Implement user authentication with JWT tokens for the API"
        )
        assert result.passed is True


class TestEvidenceGateChecks:
    """Test individual evidence gate checks."""

    def test_empty_snapshot_blocks(self):
        """Empty workspace should fail."""
        mock_workspace = MagicMock()
        gate = EvidenceGate(mock_workspace)

        evidence = JobEvidence(
            job_id="job-1",
            workspace_id="ws-1",
            repo_url="",
            branch="",
            mission="",
            generated_files=[],  # Empty!
        )

        result = gate._check_empty_snapshot(evidence)
        assert result.passed is False
        assert "no files" in result.reason.lower()

    def test_folder_only_blocks(self):
        """Folders without files should fail."""
        mock_workspace = MagicMock()
        gate = EvidenceGate(mock_workspace)

        evidence = JobEvidence(
            job_id="job-1",
            workspace_id="ws-1",
            repo_url="",
            branch="",
            mission="",
            generated_files=["src/", "lib/", "docs/"],  # Only folders!
        )

        result = gate._check_empty_snapshot(evidence)
        assert result.passed is False

    def test_real_files_pass(self):
        """Real files should pass."""
        mock_workspace = MagicMock()
        gate = EvidenceGate(mock_workspace)

        evidence = JobEvidence(
            job_id="job-1",
            workspace_id="ws-1",
            repo_url="",
            branch="",
            mission="",
            generated_files=["src/main.py", "src/utils.py", "README.md"],
        )

        result = gate._check_empty_snapshot(evidence)
        assert result.passed is True

    def test_forbidden_paths_blocks(self):
        """Modifying forbidden paths should fail."""
        mock_workspace = MagicMock()
        gate = EvidenceGate(mock_workspace)

        evidence = JobEvidence(
            job_id="job-1",
            workspace_id="ws-1",
            repo_url="",
            branch="",
            mission="",
            generated_files=[".git/config", "src/main.py"],
        )

        result = gate._check_forbidden_paths(evidence)
        assert result.passed is False
        assert ".git/config" in result.forbidden_paths_found

    def test_no_forbidden_paths_pass(self):
        """Normal paths should pass."""
        mock_workspace = MagicMock()
        gate = EvidenceGate(mock_workspace)

        evidence = JobEvidence(
            job_id="job-1",
            workspace_id="ws-1",
            repo_url="",
            branch="",
            mission="",
            generated_files=["src/main.py", "tests/test_main.py"],
        )

        result = gate._check_forbidden_paths(evidence)
        assert result.passed is True

    def test_git_diff_too_small_blocks(self):
        """Very small diffs should fail."""
        mock_workspace = MagicMock()
        gate = EvidenceGate(mock_workspace)

        evidence = JobEvidence(
            job_id="job-1",
            workspace_id="ws-1",
            repo_url="",
            branch="",
            mission="",
            git_diff_summary="+a",  # Too small!
        )

        result = gate._check_git_diff(evidence)
        assert result.passed is False

    def test_git_diff_with_code_passes(self):
        """Diff with code patterns should pass."""
        mock_workspace = MagicMock()
        gate = EvidenceGate(mock_workspace)

        evidence = JobEvidence(
            job_id="job-1",
            workspace_id="ws-1",
            repo_url="",
            branch="",
            mission="",
            git_diff_summary="""
+def hello_world():
+    print("Hello")
+    return True
""",
        )

        result = gate._check_git_diff(evidence)
        assert result.passed is True
