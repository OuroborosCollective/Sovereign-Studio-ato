"""Regression for fail-closed admission of Sovereign agent workspaces."""

import importlib
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "sovereign-backend"))
capacity = importlib.import_module("agent_runtime.workspace_capacity")


def _disk(total_gib=400, free_gib=200):
    return shutil._ntuple_diskusage(total_gib * (1 << 30), (total_gib - free_gib) * (1 << 30), free_gib * (1 << 30))


def test_disk_pressure_blocks_new_workspace_without_creating_job_folder(tmp_path):
    with patch.object(capacity.shutil, "disk_usage", return_value=_disk(free_gib=35)):
        with pytest.raises(capacity.WorkspaceCapacityError, match="DISK_RESERVE_EXHAUSTED"):
            with capacity.admit_workspace_operation(tmp_path, creates_workspace=True):
                (tmp_path / "job-1").mkdir()
    assert not (tmp_path / "job-1").exists()


def test_limit_caps_new_workspace_count(tmp_path):
    for i in range(capacity.MAX_WORKSPACES):
        (tmp_path / f"job-{i}").mkdir()
    with patch.object(capacity.shutil, "disk_usage", return_value=_disk()):
        with pytest.raises(capacity.WorkspaceCapacityError, match="WORKSPACE_COUNT_EXHAUSTED"):
            with capacity.admit_workspace_operation(tmp_path, creates_workspace=True):
                (tmp_path / "job-extra").mkdir()
    assert not (tmp_path / "job-extra").exists()


def test_workspace_count_does_not_block_existing_job_clone(tmp_path):
    for i in range(capacity.MAX_WORKSPACES):
        (tmp_path / f"job-{i}").mkdir()
    with patch.object(capacity.shutil, "disk_usage", return_value=_disk()):
        with capacity.admit_workspace_operation(tmp_path, creates_workspace=False):
            assert (tmp_path / "job-0").is_dir()


def test_lock_prevents_parallel_clone_or_provision(tmp_path):
    with patch.object(capacity.shutil, "disk_usage", return_value=_disk()):
        with capacity.admit_workspace_operation(tmp_path, creates_workspace=False):
            with pytest.raises(capacity.WorkspaceCapacityError, match="WORKSPACE_PROVISION_BUSY"):
                with capacity.admit_workspace_operation(tmp_path, creates_workspace=True):
                    pass


def test_lost_disk_measurement_blocks_closed(tmp_path):
    with patch.object(capacity.shutil, "disk_usage", side_effect=OSError("disk not mounted")):
        with pytest.raises(capacity.WorkspaceCapacityError, match="DISK_PROBE_UNAVAILABLE"):
            with capacity.admit_workspace_operation(tmp_path, creates_workspace=True):
                pass


def test_exact_capacity_floor_is_allowed(tmp_path):
    with patch.object(capacity.shutil, "disk_usage", return_value=_disk(total_gib=400, free_gib=80)):
        with capacity.admit_workspace_operation(tmp_path, creates_workspace=True):
            (tmp_path / "job-okay").mkdir()
    assert (tmp_path / "job-okay").is_dir()


def test_symlinked_root_or_lock_is_rejected(tmp_path):
    root = tmp_path / "real"
    root.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(root, target_is_directory=True)
    with pytest.raises(capacity.WorkspaceCapacityError, match="WORKSPACE_ROOT_SYMLINK"):
        with capacity.admit_workspace_operation(linked, creates_workspace=True):
            pass
    lock = root / capacity._LOCK_NAME
    lock.symlink_to(tmp_path / "other")
    with pytest.raises(capacity.WorkspaceCapacityError, match="WORKSPACE_LOCK_INVALID"):
        with capacity.admit_workspace_operation(root, creates_workspace=True):
            pass


def test_directories_are_bounded_not_lock_file(tmp_path):
    with patch.object(capacity.shutil, "disk_usage", return_value=_disk()):
        for i in range(capacity.MAX_WORKSPACES):
            with capacity.admit_workspace_operation(tmp_path, creates_workspace=True):
                (tmp_path / f"job-{i}").mkdir()
    assert len([x for x in tmp_path.iterdir() if x.is_dir()]) == capacity.MAX_WORKSPACES


def test_disk_probe_rejects_tiny_free_even_when_ratio_is_fine(tmp_path):
    with patch.object(capacity.shutil, "disk_usage", return_value=_disk(total_gib=8, free_gib=2)):
        with pytest.raises(capacity.WorkspaceCapacityError, match="DISK_RESERVE_EXHAUSTED"):
            with capacity.admit_workspace_operation(tmp_path, creates_workspace=True):
                pass
