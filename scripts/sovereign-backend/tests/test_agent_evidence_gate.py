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


class TestEvaluateAgentEvidence:
    """Test the evaluate_agent_evidence function."""

    def test_no_changed_files_fails(self):
        """Should fail when no changed files."""
        from agent_runtime.evidence_gate import EvidenceGateInput, evaluate_agent_evidence

        evidence = EvidenceGateInput(
            job_id="job-1",
            changed_files=(),
        )
        result = evaluate_agent_evidence(evidence)
        assert result.passed is False
        assert "No changed files" in result.reason
        assert result.can_prepare_draft_pr is False

    def test_no_diff_summary_fails(self):
        """Should fail when no diff summary."""
        from agent_runtime.evidence_gate import EvidenceGateInput, evaluate_agent_evidence

        evidence = EvidenceGateInput(
            job_id="job-1",
            changed_files=("src/main.py",),
            diff_summary="",
        )
        result = evaluate_agent_evidence(evidence)
        assert result.passed is False
        assert "No diff summary" in result.reason
        assert result.can_prepare_draft_pr is False

    def test_diff_too_small_fails(self):
        """Should fail when diff is too small."""
        from agent_runtime.evidence_gate import EvidenceGateInput, evaluate_agent_evidence

        evidence = EvidenceGateInput(
            job_id="job-1",
            changed_files=("src/main.py",),
            diff_summary="+a",  # Too small
        )
        result = evaluate_agent_evidence(evidence)
        assert result.passed is False
        assert "Diff too small" in result.reason
        assert result.can_prepare_draft_pr is False

    def test_no_test_summary_fails(self):
        """Should fail when test summary is missing for draft PR."""
        from agent_runtime.evidence_gate import EvidenceGateInput, evaluate_agent_evidence

        evidence = EvidenceGateInput(
            job_id="job-1",
            changed_files=("src/main.py",),
            diff_summary="+def hello(): pass",
            can_prepare_draft_pr=True,  # Draft PR requested
            test_summary="",  # But no test evidence
        )
        result = evaluate_agent_evidence(evidence)
        assert result.passed is False
        assert "No test summary" in result.reason
        assert result.can_prepare_draft_pr is False

    def test_valid_evidence_passes(self):
        """Should pass when all evidence is valid."""
        from agent_runtime.evidence_gate import EvidenceGateInput, evaluate_agent_evidence

        evidence = EvidenceGateInput(
            job_id="job-1",
            changed_files=("src/main.py", "tests/test_main.py"),
            diff_summary="+def hello(): pass",
            test_summary="2 tests passed",
        )
        result = evaluate_agent_evidence(evidence)
        assert result.passed is True
        assert result.evidence_count == 2
        assert result.can_prepare_draft_pr is True
        assert result.can_learn_pattern is True


class TestEvaluateToolResultEvidence:
    """Test the evaluate_tool_result_evidence function."""

    def test_error_fails(self):
        """Should fail when tool has error."""
        from agent_runtime.evidence_gate import evaluate_tool_result_evidence

        result = evaluate_tool_result_evidence(
            tool_result_output="some output",
            tool_result_error="Command failed",
        )
        assert result.passed is False
        assert "Command failed" in result.reason

    def test_no_output_fails(self):
        """Should fail when tool has no output."""
        from agent_runtime.evidence_gate import evaluate_tool_result_evidence

        result = evaluate_tool_result_evidence(
            tool_result_output="",
            tool_result_error=None,
        )
        assert result.passed is False
        assert "no output" in result.reason

    def test_output_too_small_fails(self):
        """Should fail when output is too short."""
        from agent_runtime.evidence_gate import evaluate_tool_result_evidence

        result = evaluate_tool_result_evidence(
            tool_result_output="ok",
            tool_result_error=None,
        )
        assert result.passed is False
        assert "too short" in result.reason

    def test_placeholder_output_fails(self):
        """Should fail when output contains placeholder."""
        from agent_runtime.evidence_gate import evaluate_tool_result_evidence

        result = evaluate_tool_result_evidence(
            tool_result_output="PLACEHOLDER content here",
            tool_result_error=None,
        )
        assert result.passed is False
        assert "placeholder" in result.reason

    def test_valid_output_passes(self):
        """Should pass when output is valid."""
        from agent_runtime.evidence_gate import evaluate_tool_result_evidence

        result = evaluate_tool_result_evidence(
            tool_result_output="File created successfully at /workspace/src/main.py",
            tool_result_error=None,
        )
        assert result.passed is True


class TestEvidenceGateSignal:
    """Test the evidence_gate_signal function."""

    def test_signal_format(self):
        """Should produce correct signal format."""
        from agent_runtime.evidence_gate import EvidenceGateResult, evidence_gate_signal

        result = EvidenceGateResult(
            passed=True,
            reason="Test passed",
            evidence_count=3,
            placeholder_count=0,
            forbidden_paths_found=[],
        )
        signal = evidence_gate_signal(result)

        assert signal["signal"] == "evidence_gate_result"
        assert signal["passed"] is True
        assert signal["reason"] == "Test passed"
        assert signal["evidence_count"] == 3
        assert signal["placeholder_count"] == 0
        assert signal["forbidden_paths"] == []


class TestEvidenceInputFromToolResult:
    """Test the evidence_input_from_tool_result function."""

    def test_from_dict(self):
        """Should extract input from dict tool result."""
        from agent_runtime.evidence_gate import evidence_input_from_tool_result

        tool_result = {
            "changed_files": ["src/a.py", "src/b.py"],
            "diff_summary": "+def foo()",
            "test_summary": "1 test passed",
        }
        result = evidence_input_from_tool_result(tool_result, "job-123")

        assert result.job_id == "job-123"
        assert result.changed_files == ("src/a.py", "src/b.py")
        assert result.diff_summary == "+def foo()"
        assert result.test_summary == "1 test passed"

    def test_from_empty_dict(self):
        """Should handle empty dict gracefully."""
        from agent_runtime.evidence_gate import evidence_input_from_tool_result

        result = evidence_input_from_tool_result({}, "job-123")

        assert result.job_id == "job-123"
        assert result.changed_files == ()
        # Empty strings are returned, not None
        assert result.diff_summary == ""
        assert result.test_summary == ""

    def test_from_non_dict(self):
        """Should handle non-dict input gracefully."""
        from agent_runtime.evidence_gate import evidence_input_from_tool_result

        result = evidence_input_from_tool_result("not a dict", "job-123")

        assert result.job_id == "job-123"
        assert result.changed_files == ()
        assert result.diff_summary is None
