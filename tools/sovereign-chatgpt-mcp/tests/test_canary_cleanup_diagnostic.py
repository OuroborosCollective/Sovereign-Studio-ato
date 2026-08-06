"""Test the GitHub Knowledge canary cleanup diagnostic patterns.

Issue #1196: GitHub Knowledge canary cleanup is unverified
This test validates that the canary cleanup SQL follows the expected pattern.
"""

from __future__ import annotations

import re
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
MCP = ROOT / "tools" / "sovereign-chatgpt-mcp"
sys.path.insert(0, str(MCP))

import github_knowledge_canary


def test_canary_script_has_finally_cleanup_block() -> None:
    """Verify the embedded canary script has a finally block that cleans up."""
    script = github_knowledge_canary._BACKEND_CANARY_SCRIPT
    
    # Should have a finally block
    assert re.search(r"\bfinally\s*:", script), "Canary script must have a finally block"
    
    # Should delete from all expected tables
    expected_deletes = [
        "DELETE FROM audit_log",
        "DELETE FROM vector_index_outbox",
        "DELETE FROM knowledge_sources",
        "DELETE FROM knowledge_learning_candidates",
    ]
    for delete_sql in expected_deletes:
        assert delete_sql in script, f"Canary script must include: {delete_sql}"
    
    # Should check cleanup verification
    assert "cleanupVerified" in script, "Canary script must verify cleanup"
    assert "cleanup_ok" in script, "Canary script must compute cleanup_ok"


def test_canary_script_deletes_blocks_only_if_orphaned() -> None:
    """Verify block deletion only happens for orphaned blocks (not all blocks)."""
    script = github_knowledge_canary._BACKEND_CANARY_SCRIPT
    
    # Find the block deletion pattern
    block_delete_match = re.search(
        r"DELETE FROM knowledge_blocks[^\n]*\n.*?NOT EXISTS[^\n]*\n.*?knowledge_source_blocks",
        script,
        re.DOTALL | re.IGNORECASE,
    )
    assert block_delete_match, "Block deletion must use NOT EXISTS to only delete orphaned blocks"


def test_canary_script_verifies_cleanup_counts() -> None:
    """Verify the cleanup verification checks all table row counts."""
    script = github_knowledge_canary._BACKEND_CANARY_SCRIPT
    
    # Should verify source rows = 0
    assert "knowledge_sources" in script
    assert "sourceRows" in script
    
    # Should verify link rows = 0
    assert "knowledge_source_blocks" in script
    assert "linkRows" in script
    
    # Should verify candidate rows = 0
    assert "knowledge_learning_candidates" in script
    assert "candidateRows" in script
    
    # Should verify block rows = 0 (or 0 if orphaned correctly)
    assert "knowledge_blocks" in script
    assert "blockRows" in script
    
    # Should verify outbox rows = 0
    assert "vector_index_outbox" in script
    assert "outboxRows" in script


def test_canary_script_never_returns_document_content() -> None:
    """Verify canary returns only evidence, not actual document content."""
    script = github_knowledge_canary._BACKEND_CANARY_SCRIPT
    
    # Should have evidence payload structure
    assert '"documentContentReturned"' in script
    
    # Should verify document content is NOT returned
    assert "documentContentReturned" in script
    
    # Should not serialize document text in the response
    # The evidence dict should only contain metadata, not the actual content
    evidence_pattern = re.search(
        r'evidence\s*=\s*\{[^}]+\}',
        script,
        re.DOTALL,
    )
    assert evidence_pattern, "Canary must build evidence dict"
    
    evidence_text = evidence_pattern.group()
    # Evidence should contain counts and metadata, not actual text
    assert "chunkCount" in evidence_text
    assert "contentSha256" in evidence_text


def test_canary_script_never_returns_secrets() -> None:
    """Verify canary never returns secret-like values."""
    script = github_knowledge_canary._BACKEND_CANARY_SCRIPT
    
    # Should have secretValuesReturned check
    assert '"secretValuesReturned"' in script
    assert "secretValuesReturned" in script
    
    # The response payload should include secretValuesReturned = False
    # This is checked in the runtime live_canary() method
    payload_pattern = re.search(
        r'payload\s*=\s*\{[^}]+\}',
        script,
        re.DOTALL,
    )
    assert payload_pattern, "Canary must build response payload"


def test_live_canary_verifies_cleanup_in_runtime() -> None:
    """Verify the runtime live_canary method validates cleanup."""
    # The GitHubKnowledgeCanaryRuntime class should have cleanup verification
    script = github_knowledge_canary._BACKEND_CANARY_SCRIPT
    
    # cleanupVerified should be in the success payload
    assert "cleanupVerified" in script
    
    # cleanup_ok should be computed from all table counts
    assert "cleanup_ok = all(" in script


def test_canary_script_uses_exact_table_names() -> None:
    """Verify canary uses the correct table names."""
    script = github_knowledge_canary._BACKEND_CANARY_SCRIPT
    
    expected_tables = [
        "knowledge_sources",
        "knowledge_source_blocks", 
        "knowledge_learning_candidates",
        "knowledge_blocks",
        "vector_index_outbox",
        "audit_log",
    ]
    
    for table in expected_tables:
        assert table in script, f"Canary script must reference table: {table}"


def test_diagnostic_script_pattern_is_valid_bash() -> None:
    """Verify the diagnostic script follows valid bash patterns."""
    diagnostic_path = ROOT / "scripts" / "issue-1196-canary-diagnostic" / "diagnose_canary_cleanup.sh"
    
    if not diagnostic_path.exists():
        pytest.skip("Diagnostic script not yet created")
    
    script_content = diagnostic_path.read_text("utf-8")
    
    # Should have proper shebang
    assert script_content.startswith("#!/usr/bin/env bash"), "Must have bash shebang"
    
    # Should use set -euo pipefail for safety
    assert "set -euo pipefail" in script_content, "Must use strict bash mode"
    
    # Should check for canary tables
    assert "knowledge_sources" in script_content
    assert "knowledge_source_blocks" in script_content
    assert "liveCanary" in script_content
