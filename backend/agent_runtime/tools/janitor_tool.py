"""Deterministic, user-invoked repository janitor.

The tool scans an isolated repository with deterministic rules. Optional Ollama
is explanation-only. Writes require explicit confirmation and an exact SHA-bound
SEARCH/REPLACE; the tool never commits, pushes, opens a PR, or runs tests.
"""

from __future__ import annotations

import difflib
import os
from pathlib import Path
import re
from typing import Any

from .base import ToolBase, ToolPolicyError, ToolResult
from .janitor_rules import (
    _DANGEROUS_REPLACEMENT_PATTERNS,
    MAX_DIFF_OUTPUT,
    MAX_FILE_BYTES,
    MAX_PATCH_TEXT,
    MAX_SCAN_FILES,
    SUPPORTED_EXTENSIONS,
    _scan_python,
    _scan_text,
    _secret_like_match,
    _sha256_text,
)
from .janitor_support import (
    _detect_test_command,
    _iter_source_files,
    _optional_ollama_explanation,
    _safe_target,
)


class DynamicJanitorTool(ToolBase):
    """Scan a repo deterministically or apply one confirmed exact replacement."""

    name = "janitor"
    description = (
        "Scan an isolated repository with AST/regex rules or apply one explicit, "
        "SHA-256-bound SEARCH/REPLACE after user confirmation"
    )
    parameters = {
        "mode": {
            "type": "string",
            "required": False,
            "default": "scan",
            "description": "scan or apply",
        },
        "family": {
            "type": "string",
            "required": False,
            "description": "User-described error family, used as report context",
        },
        "paths": {
            "type": "array",
            "required": False,
            "description": "Optional relative files/directories to scan",
        },
        "maxFindings": {
            "type": "integer",
            "required": False,
            "default": 10,
            "description": "Maximum returned findings (1-50)",
        },
        "maxFiles": {
            "type": "integer",
            "required": False,
            "default": 200,
            "description": "Maximum scanned files (1-500)",
        },
        "includeDocs": {
            "type": "boolean",
            "required": False,
            "default": False,
            "description": "Include Markdown documentation in the scan",
        },
        "explainWithLocalModel": {
            "type": "boolean",
            "required": False,
            "default": False,
            "description": "Optional explanation-only Ollama call; never used for patches",
        },
        "path": {"type": "string", "required": False},
        "searchText": {"type": "string", "required": False},
        "replacementText": {"type": "string", "required": False},
        "expectedSha256": {"type": "string", "required": False},
        "confirm": {
            "type": "boolean",
            "required": False,
            "default": False,
            "description": "Must be true for apply mode",
        },
    }
    requires_workspace = True

    def validate(self, params: dict[str, Any]) -> None:
        super().validate(params)
        mode = str(params.get("mode") or "scan").strip().lower()
        if mode not in {"scan", "apply"}:
            raise ToolPolicyError("Janitor mode must be 'scan' or 'apply'.")
        for key, minimum, maximum in (("maxFindings", 1, 50), ("maxFiles", 1, MAX_SCAN_FILES)):
            value = params.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum):
                raise ToolPolicyError(f"{key} must be an integer between {minimum} and {maximum}.")
        paths = params.get("paths")
        if paths is not None:
            if not isinstance(paths, list) or len(paths) > 50:
                raise ToolPolicyError("Janitor paths must be an array with at most 50 entries.")
            for value in paths:
                if not isinstance(value, str) or not value.strip() or value.startswith("/") or ".." in Path(value).parts:
                    raise ToolPolicyError("Janitor paths must be safe relative paths.")
        family = params.get("family")
        if family is not None and (not isinstance(family, str) or len(family) > 300):
            raise ToolPolicyError("Janitor family must be a string with at most 300 characters.")
        if mode == "apply":
            if params.get("confirm") is not True:
                raise ToolPolicyError("Janitor apply requires explicit user confirmation.")
            for key in ("path", "searchText", "replacementText", "expectedSha256"):
                if not isinstance(params.get(key), str) or not str(params.get(key)).strip():
                    raise ToolPolicyError(f"Janitor apply requires {key}.")
            if len(params["searchText"]) > MAX_PATCH_TEXT or len(params["replacementText"]) > MAX_PATCH_TEXT:
                raise ToolPolicyError("Janitor patch text exceeds the safety limit.")
            if not re.fullmatch(r"[a-fA-F0-9]{64}", params["expectedSha256"].strip()):
                raise ToolPolicyError("expectedSha256 must be a 64-character SHA-256 digest.")

    def execute(self, params: dict[str, Any], workspace_path: str | None = None) -> ToolResult:
        if not workspace_path:
            return ToolResult(status="blocked", blocker="No repository workspace provided.")
        root = Path(workspace_path).resolve()
        if not root.is_dir():
            return ToolResult(status="blocked", blocker="Repository workspace does not exist.")
        mode = str(params.get("mode") or "scan").strip().lower()
        return self._apply(params, root) if mode == "apply" else self._scan(params, root)

    def _scan(self, params: dict[str, Any], root: Path) -> ToolResult:
        max_findings = min(max(int(params.get("maxFindings", 10)), 1), 50)
        max_files = min(max(int(params.get("maxFiles", 200)), 1), MAX_SCAN_FILES)
        paths = params.get("paths") if isinstance(params.get("paths"), list) else []
        family = str(params.get("family") or "runtime truth and repository defects").strip()[:300]

        findings: list[dict[str, Any]] = []
        scanned_files = 0
        skipped_large_files = 0
        parseable_python_files = 0
        for source_path in _iter_source_files(
            root,
            paths,
            max_files,
            include_docs=params.get("includeDocs") is True,
        ):
            try:
                relative = source_path.relative_to(root).as_posix()
                size = source_path.stat().st_size
                if size > MAX_FILE_BYTES:
                    skipped_large_files += 1
                    continue
                content = source_path.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeError):
                continue
            scanned_files += 1
            digest = _sha256_text(content)
            if source_path.suffix.lower() == ".py":
                parseable_python_files += 1
                findings.extend(_scan_python(relative, content, digest))
            findings.extend(_scan_text(relative, content, digest))
            if len(findings) >= max_findings:
                break

        findings = findings[:max_findings]
        explanation = None
        explanation_blocker = None
        if params.get("explainWithLocalModel") is True:
            explanation, explanation_blocker = _optional_ollama_explanation(findings, family)

        severity_counts: dict[str, int] = {}
        for item in findings:
            severity = str(item["severity"])
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        recommended_test = _detect_test_command(root)
        summary = (
            f"Janitor scan completed: {len(findings)} finding(s) in {scanned_files} file(s). "
            "No files were changed."
        )
        return ToolResult(
            status="done",
            output=summary,
            metadata={
                "mode": "scan",
                "family": family,
                "findings": findings,
                "findingCount": len(findings),
                "severityCounts": severity_counts,
                "scannedFiles": scanned_files,
                "pythonAstFiles": parseable_python_files,
                "skippedLargeFiles": skipped_large_files,
                "recommendedTestCommand": recommended_test,
                "localModelExplanation": explanation,
                "localModelBlocker": explanation_blocker,
                "writeAction": False,
                "requiresConfirm": False,
            },
            predictive_signal="agent_janitor_scan_completed",
        )

    def _apply(self, params: dict[str, Any], root: Path) -> ToolResult:
        if params.get("confirm") is not True:
            return ToolResult(status="blocked", blocker="Janitor apply requires explicit user confirmation.")
        required = ("path", "searchText", "replacementText", "expectedSha256")
        if any(not isinstance(params.get(key), str) or not str(params.get(key)).strip() for key in required):
            return ToolResult(status="blocked", blocker="Janitor apply request is incomplete.")
        relative_path = str(params["path"]).strip().replace("\\", "/")
        target = _safe_target(root, relative_path)
        if target is None or not target.is_file():
            return ToolResult(status="blocked", blocker="Janitor patch target is unsafe or missing.")
        if target.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return ToolResult(status="blocked", blocker="Janitor may patch only supported source files.")
        try:
            current = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            return ToolResult(status="error", error=f"Janitor could not read patch target: {type(exc).__name__}.")
        expected = str(params["expectedSha256"]).strip().lower()
        current_digest = _sha256_text(current)
        if current_digest != expected:
            return ToolResult(
                status="blocked",
                blocker="Janitor patch blocked because the file changed after review.",
                metadata={"mode": "apply", "path": relative_path, "currentSha256": current_digest},
            )
        search_text = str(params["searchText"])
        replacement_text = str(params["replacementText"])
        occurrence_count = current.count(search_text)
        if occurrence_count != 1:
            return ToolResult(
                status="blocked",
                blocker=f"Janitor SEARCH must match exactly once; matched {occurrence_count} times.",
            )
        if any(pattern.search(replacement_text) for pattern in _DANGEROUS_REPLACEMENT_PATTERNS):
            return ToolResult(
                status="blocked",
                blocker="Janitor replacement contains a forbidden security or workflow pattern.",
            )
        if _secret_like_match(replacement_text):
            return ToolResult(status="blocked", blocker="Janitor replacement contains secret-like material.")

        updated = current.replace(search_text, replacement_text, 1)
        if updated == current:
            return ToolResult(status="blocked", blocker="Janitor replacement produced no change.")
        diff = "".join(difflib.unified_diff(
            current.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            n=3,
        ))
        try:
            temporary = target.with_name(f".{target.name}.janitor-tmp")
            temporary.write_text(updated, encoding="utf-8")
            os.replace(temporary, target)
        except OSError as exc:
            return ToolResult(status="error", error=f"Janitor patch write failed: {type(exc).__name__}.")

        new_digest = _sha256_text(updated)
        return ToolResult(
            status="done",
            output=f"Applied one confirmed exact replacement to {relative_path}.",
            metadata={
                "mode": "apply",
                "path": relative_path,
                "beforeSha256": current_digest,
                "afterSha256": new_digest,
                "recommendedTestCommand": _detect_test_command(root),
                "writeAction": True,
                "requiresConfirm": True,
            },
            changed_files=(relative_path,),
            diff_summary=diff[:MAX_DIFF_OUTPUT],
            predictive_signal="agent_janitor_patch_applied",
        )
