"""Regression for the real managed MCP workspace lifecycle."""
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workspace_lifecycle import (
    WorkspaceLifecycleError, workspace_creation_guard,
    workspace_inventory, cleanup_managed_workspace,
)

REPOSITORY = "OuroborosCollective/Sovereign-Studio-ato"


def _workspace(root: Path, *, published=False):
    target = root / "job-abcdef123456"
    target.mkdir()
    (target / ".sovereign-mcp-owned").write_text("mcp-v1\n", encoding="utf-8")
    (target / "workspace.json").write_text(json.dumps({
        "workspace_id": target.name, "repository": REPOSITORY,
        "draft_pr_verified": published,
    }), encoding="utf-8")
    return target


def test_unpublished_workspace_requires_explicit_discard(tmp_path):
    target = _workspace(tmp_path)
    with pytest.raises(WorkspaceLifecycleError, match="WORKSPACE_UNPUBLISHED_REQUIRES_OWNER_CONFIRMATION"):
        cleanup_managed_workspace(tmp_path, target.name, REPOSITORY)
    assert target.is_dir()
    cleanup = cleanup_managed_workspace(tmp_path, target.name, REPOSITORY, abandon_confirmed=True)
    assert cleanup["readback_absent"]
    assert not target.exists()


def test_verified_publication_can_be_cleaned_and_rechecked(tmp_path):
    target = _workspace(tmp_path, published=True)
    assert cleanup_managed_workspace(tmp_path, target.name, REPOSITORY)["status"] == "WORKSPACE_CLEANED"
    assert cleanup_managed_workspace(tmp_path, target.name, REPOSITORY)["status"] == "WORKSPACE_ALREADY_ABSENT"


def test_unowned_and_symlink_workspace_never_removed(tmp_path):
    target = _workspace(tmp_path, published=True)
    with pytest.raises(WorkspaceLifecycleError, match="WORKSPACE_REPOSITORY_MISMATCH"):
        cleanup_managed_workspace(tmp_path, target.name, "wrong/repo")
    outside = tmp_path / "other"
    outside.mkdir()
    sentinel = outside / "important"
    sentinel.write_text("preserve")
    (tmp_path / "job-000000000001").symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspaceLifecycleError, match="WORKSPACE_SYMLINK_BLOCKED"):
        cleanup_managed_workspace(tmp_path, "job-000000000001", REPOSITORY, abandon_confirmed=True)
    assert sentinel.read_text() == "preserve"


def test_inventory_does_not_mutate_unknown_workspace(tmp_path):
    unknown = tmp_path / "unknown-project"
    unknown.mkdir()
    assert workspace_inventory(tmp_path)["total_directories"] == 1
    assert unknown.is_dir()


def test_admission_fails_before_creating_at_limit(tmp_path):
    for i in range(12):
        (tmp_path / f"job-{i:012x}").mkdir()
    with pytest.raises(WorkspaceLifecycleError, match="WORKSPACE_COUNT_EXHAUSTED"):
        with workspace_creation_guard(tmp_path):
            (tmp_path / "job-abcdef123456").mkdir()
    assert not (tmp_path / "job-abcdef123456").exists()
