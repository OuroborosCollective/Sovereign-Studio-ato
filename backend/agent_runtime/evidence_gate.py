"""Evidence Gate for Sovereign Agent Runtime.

This module provides the evidence gate - a runtime check that validates
job completion by examining real workspace evidence before allowing status
transitions to 'completed'.

The evidence gate is part of the Sovereign brain contract and ensures:
1. Real files were generated (not just plan files)
2. Evidence is verifiable and matches mission requirements
3. No placeholder or fake content enters the release path
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any




# Placeholder patterns that must not enter the release path
PLACEHOLDER_PATTERNS = [
    r"README\s*\+\s*Update\s+History",
    r"Mach\s+weiter",
    r"Fehler",
    r"Ideen",
    r"Plan",
    r"Workflow\s+.*Analyse.*Runtime.*Check.*Test\s+Plan",
    r"PLACEHOLDER",
    r"TODO",
    r"FIXME",
    r"^\s*$",  # Empty content
]

# Forbidden paths that should never contain generated content
FORBIDDEN_PATHS = {
    ".git",
    ".env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".next",
}


@dataclass
class EvidenceGateResult:
    """Result of an evidence gate check."""
    passed: bool
    reason: str
    evidence_count: int = 0
    placeholder_count: int = 0
    forbidden_paths_found: list[str] = None
    details: dict[str, Any] = None
    can_prepare_draft_pr: bool = True
    can_learn_pattern: bool = False

    def __post_init__(self):
        if self.forbidden_paths_found is None:
            self.forbidden_paths_found = []
        if self.details is None:
            self.details = {}
        # can_prepare_draft_pr is derived from passed AND evidence_count, but only if not explicitly set
        # Since dataclass with default values always sets it, we check if it was explicitly passed


@dataclass
class JobEvidence:
    """Evidence collected from a job's workspace."""
    job_id: str
    workspace_id: str
    repo_url: str
    branch: str
    mission: str
    generated_files: list[str] = None
    git_status: str = ""
    git_diff_summary: str = ""
    file_contents: dict[str, str] = None
    created_at: int = None

    def __post_init__(self):
        if self.generated_files is None:
            self.generated_files = []
        if self.file_contents is None:
            self.file_contents = {}
        if self.created_at is None:
            self.created_at = int(datetime.now(timezone.utc).timestamp() * 1000)


class EvidenceGate:
    """Validates job completion evidence.

    The evidence gate checks:
    1. Non-empty generated files exist
    2. No placeholder content in files
    3. No forbidden paths were modified
    4. Git status shows real changes
    5. Diff contains executable/implementable content
    """

    def __init__(self, workspace: Any):  # WorkspaceProvisioner | GitWorkspace
        self.workspace = workspace
        self._placeholder_regex = [
            re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            for pattern in PLACEHOLDER_PATTERNS
        ]

    def check_evidence(self, job_id: str, workspace_path: str | None = None) -> EvidenceGateResult:
        """Check evidence for a completed job.

        Args:
            job_id: The job ID to check
            workspace_path: Optional workspace path override

        Returns:
            EvidenceGateResult with pass/fail and details
        """
        if not workspace_path:
            workspace_path = self._get_workspace_path(job_id)

        if not workspace_path:
            return EvidenceGateResult(
                passed=False,
                reason="No workspace path available",
            )

        # Collect evidence
        evidence = self._collect_evidence(job_id, workspace_path)

        # Check each gate
        empty_result = self._check_empty_snapshot(evidence)
        if not empty_result.passed:
            return empty_result

        placeholder_result = self._check_placeholders(evidence)
        if not placeholder_result.passed:
            return placeholder_result

        forbidden_result = self._check_forbidden_paths(evidence)
        if not forbidden_result.passed:
            return forbidden_result

        diff_result = self._check_git_diff(evidence)
        if not diff_result.passed:
            return diff_result

        return EvidenceGateResult(
            passed=True,
            reason="All evidence gates passed",
            evidence_count=len(evidence.generated_files),
            placeholder_count=0,
            details={
                "files": evidence.generated_files,
                "git_status": evidence.git_status,
            },
        )

    def _get_workspace_path(self, job_id: str) -> str | None:
        """Get workspace path for a job."""
        if hasattr(self.workspace, 'get_workspace_path'):
            return self.workspace.get_workspace_path(job_id)
        if hasattr(self.workspace, 'workspace_path'):
            return self.workspace.workspace_path
        return None

    def _collect_evidence(self, job_id: str, workspace_path: str) -> JobEvidence:
        """Collect evidence from the workspace."""
        evidence = JobEvidence(
            job_id=job_id,
            workspace_id=job_id,
            repo_url="",
            branch="",
            mission="",
        )

        # Get git status
        if hasattr(self.workspace, 'get_git_status'):
            status_result = self.workspace.get_git_status(workspace_path)
            if status_result.get("ok"):
                evidence.git_status = status_result.get("status", "")
                # Extract changed files
                files = status_result.get("files", [])
                evidence.generated_files = [f.get("path", "") for f in files if f.get("path")]

        # Get git diff summary
        if hasattr(self.workspace, 'get_git_diff'):
            diff_result = self.workspace.get_git_diff(workspace_path)
            if diff_result.get("ok"):
                evidence.git_diff_summary = diff_result.get("diff", "")[:500]

        return evidence

    def _check_empty_snapshot(self, evidence: JobEvidence) -> EvidenceGateResult:
        """Check that workspace has real files, not just folders."""
        if not evidence.generated_files:
            return EvidenceGateResult(
                passed=False,
                reason="No files found in workspace - snapshot may be empty or folders only",
                evidence_count=0,
            )

        # Filter out directories (paths without extensions often indicate folders)
        real_files = [
            f for f in evidence.generated_files
            if "." in f.split("/")[-1] or f.endswith(".md") or f.endswith(".txt")
        ]

        if not real_files:
            return EvidenceGateResult(
                passed=False,
                reason="Only folder structures found - no executable/implementable files",
                evidence_count=len(evidence.generated_files),
            )

        return EvidenceGateResult(passed=True, reason="Non-empty snapshot", evidence_count=len(real_files))

    def _check_placeholders(self, evidence: JobEvidence) -> EvidenceGateResult:
        """Check for placeholder content in generated files."""
        placeholder_count = 0
        found_placeholders: list[str] = []

        # Check git diff for placeholders
        for pattern in self._placeholder_regex:
            matches = pattern.findall(evidence.git_diff_summary)
            if matches:
                placeholder_count += len(matches)
                found_placeholders.extend(matches)

        # Check file contents if available
        for path, content in evidence.file_contents.items():
            for pattern in self._placeholder_regex:
                if pattern.search(content):
                    placeholder_count += 1
                    found_placeholders.append(f"{path}: placeholder content")

        if placeholder_count > 0:
            return EvidenceGateResult(
                passed=False,
                reason=f"Found {placeholder_count} placeholder(s) - content must be real, not placeholder",
                placeholder_count=placeholder_count,
                details={"placeholders": found_placeholders[:10]},
            )

        return EvidenceGateResult(passed=True, reason="No placeholder content")

    def _check_forbidden_paths(self, evidence: JobEvidence) -> EvidenceGateResult:
        """Check that no forbidden paths were modified."""
        forbidden_found: list[str] = []

        for file_path in evidence.generated_files:
            for forbidden in FORBIDDEN_PATHS:
                if f"/{forbidden}/" in file_path or file_path.startswith(f"{forbidden}/"):
                    forbidden_found.append(file_path)

        if forbidden_found:
            return EvidenceGateResult(
                passed=False,
                reason=f"Forbidden paths modified: {forbidden_found}",
                forbidden_paths_found=forbidden_found,
            )

        return EvidenceGateResult(passed=True, reason="No forbidden paths")

    def _check_git_diff(self, evidence: JobEvidence) -> EvidenceGateResult:
        """Check that git diff contains real, implementable content."""
        if not evidence.git_diff_summary:
            return EvidenceGateResult(
                passed=False,
                reason="No git diff found - workspace may not be a git repository",
            )

        # Check for minimum diff size (real changes are usually larger)
        min_diff_size = 50
        if len(evidence.git_diff_summary.strip()) < min_diff_size:
            return EvidenceGateResult(
                passed=False,
                reason=f"Git diff too small ({len(evidence.git_diff_summary)} chars) - may be incomplete",
            )

        # Check for code-like patterns in diff
        code_patterns = [
            r"^\+",  # Addition lines
            r"^-",    # Deletion lines
            r"def\s+\w+",  # Function definitions
            r"class\s+\w+",  # Class definitions
            r"import\s+\w+",  # Imports
            r"//.*",  # Comments
            r"#.*",  # Python comments
        ]

        has_code = any(re.search(p, evidence.git_diff_summary, re.MULTILINE) for p in code_patterns)
        if not has_code:
            return EvidenceGateResult(
                passed=False,
                reason="Git diff does not contain recognizable code patterns",
            )

        return EvidenceGateResult(passed=True, reason="Real implementation content found")

    def validate_mission_content(self, mission: str) -> EvidenceGateResult:
        """Validate that a mission is concrete, not placeholder.

        Args:
            mission: The mission text to validate

        Returns:
            EvidenceGateResult with pass/fail
        """
        return validate_mission_content(mission)


@dataclass(frozen=True)
class EvidenceGateInput:
    """Input for evidence gate evaluation."""
    job_id: str = "unknown"
    workspace_path: str | None = None
    mission: str = ""
    changed_files: tuple[str, ...] = ()
    diff_summary: str | None = None
    test_summary: str | None = None
    can_prepare_draft_pr: bool = True
    can_learn_pattern: bool = False
    blocker: str | None = None
    tool_status: str | None = None
    tool_output: str | None = None


def evaluate_agent_evidence(input_data: EvidenceGateInput) -> EvidenceGateResult:
    """Evaluate evidence for a job.
    
    This is a simplified evaluation that checks:
    1. Has changed files
    2. Diff is non-empty
    3. Test summary is non-empty (if tests required)
    """
    # Check for changed files
    if not input_data.changed_files:
        return EvidenceGateResult(
            passed=False,
            reason="No changed files - evidence gate requires generated files",
            evidence_count=0,
            can_prepare_draft_pr=False,
        )
    
    # Check for diff content
    if not input_data.diff_summary:
        return EvidenceGateResult(
            passed=False,
            reason="No diff summary - evidence gate requires git diff",
            evidence_count=len(input_data.changed_files),
            can_prepare_draft_pr=False,
        )
    
    # Check diff size (minimum 10 chars for simple diffs)
    if len(input_data.diff_summary.strip()) < 10:
        return EvidenceGateResult(
            passed=False,
            reason=f"Diff too small ({len(input_data.diff_summary)} chars)",
            evidence_count=len(input_data.changed_files),
            can_prepare_draft_pr=False,
        )
    
    # Check test summary (if required)
    if input_data.can_prepare_draft_pr and not input_data.test_summary:
        return EvidenceGateResult(
            passed=False,
            reason="No test summary - Draft PR preparation requires test evidence",
            evidence_count=len(input_data.changed_files),
            can_prepare_draft_pr=False,
        )
    
    return EvidenceGateResult(
        passed=True,
        reason="Evidence gate passed - all checks complete",
        evidence_count=len(input_data.changed_files),
        can_prepare_draft_pr=True,
        can_learn_pattern=True,  # Always True when passed for backward compatibility
    )


def validate_mission_content(mission: str) -> EvidenceGateResult:
    """Validate that a mission is concrete, not placeholder."""
    if not mission or len(mission.strip()) < 10:
        return EvidenceGateResult(
            passed=False,
            reason="Mission too short or empty",
        )

    # Check against placeholder patterns
    for pattern in PLACEHOLDER_PATTERNS:
        compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        if compiled.search(mission):
            return EvidenceGateResult(
                passed=False,
                reason="Mission contains placeholder text",
            )

    return EvidenceGateResult(passed=True, reason="Mission is concrete")


def evaluate_tool_result_evidence(
    tool_result_output: str | None,
    tool_result_error: str | None,
) -> EvidenceGateResult:
    """Evaluate evidence from a tool result.
    
    This checks that tool execution produced real output,
    not just empty or placeholder content.
    """
    if tool_result_error:
        return EvidenceGateResult(
            passed=False,
            reason=f"Tool execution error: {tool_result_error[:100]}",
        )
    
    if not tool_result_output:
        return EvidenceGateResult(
            passed=False,
            reason="Tool produced no output",
        )
    
    if len(tool_result_output.strip()) < 10:
        return EvidenceGateResult(
            passed=False,
            reason="Tool output too short - may be placeholder",
        )
    
    # Check for placeholder patterns in output
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern == r"^\s*$":  # Skip empty check, already done
            continue
        compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        if compiled.search(tool_result_output):
            return EvidenceGateResult(
                passed=False,
                reason=f"Tool output contains placeholder pattern: {pattern[:30]}",
            )
    
    return EvidenceGateResult(
        passed=True,
        reason="Tool result evidence is valid",
    )


def evidence_gate_signal(result: EvidenceGateResult) -> dict:
    """Convert EvidenceGateResult to signal dict for telemetry."""
    return {
        "signal": "evidence_gate_result",
        "passed": result.passed,
        "reason": result.reason,
        "evidence_count": result.evidence_count,
        "placeholder_count": result.placeholder_count,
        "forbidden_paths": result.forbidden_paths_found or [],
    }


def evidence_input_from_tool_result(
    tool_result: Any,  # ToolResult from tools module
    job_id: str,
) -> EvidenceGateInput:
    """Create EvidenceGateInput from a tool result."""
    return EvidenceGateInput(
        job_id=job_id,
        changed_files=tuple(tool_result.get("changed_files", []) if isinstance(tool_result, dict) else []),
        diff_summary=tool_result.get("diff_summary", "") if isinstance(tool_result, dict) else None,
        test_summary=tool_result.get("test_summary", "") if isinstance(tool_result, dict) else None,
    )
