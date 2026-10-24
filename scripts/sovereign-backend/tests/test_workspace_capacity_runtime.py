"""Exercise the actual Sovereign clone, admission and cleanup entrypoints."""

from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "sovereign-backend"))

from agent_runtime import git_workspace, repository_execution, workspace, workspace_capacity


def _disk(total_gib=400, free_gib=35):
    return shutil._ntuple_diskusage(total_gib * (1 << 30), (total_gib - free_gib) * (1 << 30), free_gib * (1 << 30))


def test_workspace_creator_blocks_disk_pressure_before_mkdir(tmp_path):
    with patch.object(workspace_capacity.shutil, "disk_usage", return_value=_disk()):
        result = workspace.create_agent_workspace("job-budget", tmp_path)
    assert result.status == "blocked"
    assert "DISK_RESERVE_EXHAUSTED" in str(result.blocker)
    assert not (tmp_path / "job-budget").exists()


def test_clone_is_blocked_without_starting_git_when_disk_is_critical(tmp_path):
    repo = tmp_path / "job-budget" / "repo"
    repo.mkdir(parents=True)
    with patch.object(workspace_capacity.shutil, "disk_usage", return_value=_disk()):
        with patch.object(git_workspace, "run_git_command") as subprocess_gate:
            result = git_workspace.clone_repo_into_workspace(
                "job-budget", "https://github.com/OuroborosCollective/Sovereign-Studio-ato",
                root=tmp_path,
            )
            subprocess_gate.assert_not_called()
    assert result.status == "blocked"
    assert "DISK_RESERVE_EXHAUSTED" in str(result.blocker)
    assert list(repo.iterdir()) == []


def test_clone_is_blocked_while_another_operation_holds_lock(tmp_path):
    repo = tmp_path / "job-budget" / "repo"
    repo.mkdir(parents=True)
    with patch.object(workspace_capacity.shutil, "disk_usage", return_value=_disk(free_gib=250)):
        with workspace_capacity.admit_workspace_operation(tmp_path, creates_workspace=False):
            with patch.object(git_workspace, "run_git_command") as subprocess_gate:
                result = git_workspace.clone_repo_into_workspace(
                    "job-budget", "https://github.com/OuroborosCollective/Sovereign-Studio-ato",
                    root=tmp_path,
                )
                subprocess_gate.assert_not_called()
    assert result.status == "blocked"
    assert "WORKSPACE_PROVISION_BUSY" in str(result.blocker)


def test_repository_job_rejected_before_external_lookup_or_db_record(tmp_path):
    with patch.object(workspace_capacity.shutil, "disk_usage", return_value=_disk()):
        with patch.object(repository_execution, "create_sovereign_agent_job") as create:
            with patch.object(repository_execution, "_resolve_expected_head_sha") as lookup:
                with pytest.raises(repository_execution.RepositoryExecutionError, match="HOST_WORKSPACE_ADMISSION_BLOCKED:DISK_RESERVE_EXHAUSTED"):
                    repository_execution.start_repository_execution(
                        None, user_id="owner-test",
                        body={"repoUrl": "https://github.com/OuroborosCollective/Sovereign-Studio-ato", "branch": "main", "mission": "Run a safe test"},
                        workspace_root=tmp_path,
                    )
                create.assert_not_called()
                lookup.assert_not_called()


def test_cleanup_rejects_symlink_to_another_workspace(tmp_path):
    real = tmp_path / "job-active"
    real.mkdir()
    sentinel = real / "do-not-delete.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    (tmp_path / "job-stale").symlink_to(real, target_is_directory=True)
    result = workspace.cleanup_agent_workspace("job-stale", tmp_path)
    assert result.status == "blocked"
    assert "WORKSPACE_CLEANUP_SYMLINK_BLOCKED" in str(result.blocker)
    assert sentinel.read_text(encoding="utf-8") == "preserve"
