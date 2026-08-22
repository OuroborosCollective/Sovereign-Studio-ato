from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from agent_runtime.fleet_attempts import create_worker_attempt
from agent_runtime.fleet_attempt_worktrees import (
    AttemptWorktreeRelease,
    cleanup_settled_attempt_worktree,
    create_attempt_worktree_release,
    deterministic_attempt_branch,
    provision_attempt_worktree,
    read_active_attempt_draft_pr_handoff,
    resolve_active_attempt_worktree,
)
from agent_runtime.fleet_supervisor import (
    FleetContractError,
    FleetTask,
    build_fleet_plan,
    create_worker_assignment,
)


REPOSITORY_URL = "https://github.com/OuroborosCollective/Sovereign-Studio-ato"
REPOSITORY = "OuroborosCollective/Sovereign-Studio-ato"
CONTROLLER_REF = "f" * 64


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=path,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _base_clone(tmp_path: Path, *, workspace_id: str = "job-worktree") -> tuple[Path, Path, str]:
    root = tmp_path / "workspaces"
    repo = root / workspace_id / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "fleet-worktree@example.invalid")
    _git(repo, "config", "user.name", "Fleet Worktree Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")
    _git(repo, "remote", "add", "origin", REPOSITORY_URL)
    return root, repo, _git(repo, "rev-parse", "HEAD")


def _assignments(base_revision: str, *, workspace_id: str = "job-worktree", tasks: tuple[str, ...] = ("task-alpha",)):
    fleet_tasks = tuple(
        FleetTask(
            task_id=task_id,
            source_type="issue",
            source_id="1524",
            expected_base_revision=base_revision,
            expected_head_revision=base_revision,
            changed_paths=(f"{index}/",),
            architecture_domains=(f"domain-{index}",),
            canonical_owners=(f"owner-{index}",),
            invariant_scopes=(f"scope-{index}",),
            mutation_resources=(f"resource-{index}",),
            lock_scopes=(f"lock-{index}",),
            independence_proven=True,
        )
        for index, task_id in enumerate(tasks, start=1)
    )
    plan = build_fleet_plan(
        integration_id="fleet-worktree-tests",
        repository=REPOSITORY,
        base_revision=base_revision,
        architecture_receipt_hashes=["a" * 64],
        tasks=fleet_tasks,
        max_parallel_lanes=len(tasks),
    )
    assignments = {}
    for task in fleet_tasks:
        lane = next(item for item in plan.lanes if task.task_id in item.task_ids)
        assignments[task.task_id] = create_worker_assignment(
            plan,
            lane_id=lane.lane_id,
            task_id=task.task_id,
            controller_run_id="run-worktree-identity",
            workspace_id=workspace_id,
            workspace_branch="main",
            run_envelope_hash="b" * 64,
            capability_manifest_hash="c" * 64,
        )
    return assignments


def _provision(root: Path, assignment, *, sequence: int = 1, active=None):
    attempt = create_worker_attempt(assignment, attempt_sequence=sequence)
    return attempt, provision_attempt_worktree(
        assignment=assignment,
        attempt=attempt,
        active_attempt=active or attempt,
        repository_url=REPOSITORY_URL,
        root=root,
    )


def test_two_independent_attempts_receive_distinct_physical_worktrees(tmp_path: Path) -> None:
    root, _, base = _base_clone(tmp_path)
    assignments = _assignments(base, tasks=("task-alpha", "task-beta"))
    first, first_workspace = _provision(root, assignments["task-alpha"])
    second, second_workspace = _provision(root, assignments["task-beta"])

    assert first_workspace.worktree_path != second_workspace.worktree_path
    assert first_workspace.worktree_path.samefile(first_workspace.worktree_path)
    assert not first_workspace.worktree_path.samefile(second_workspace.worktree_path)
    assert first_workspace.head_revision == base
    assert second_workspace.head_revision == base
    assert first_workspace.branch_name != second_workspace.branch_name
    assert first_workspace.receipt_binding()["attemptId"] == first.attempt_id
    assert second_workspace.receipt_binding()["worktreeBindingHash"] == second_workspace.binding_hash

    def write(worktree: Path, name: str) -> None:
        (worktree / name).write_text(name + "\n", encoding="utf-8")

    with ThreadPoolExecutor(max_workers=2) as executor:
        tuple(executor.map(lambda item: write(*item), ((first_workspace.worktree_path, "alpha.txt"), (second_workspace.worktree_path, "beta.txt"))))
    assert (first_workspace.worktree_path / "alpha.txt").is_file()
    assert not (first_workspace.worktree_path / "beta.txt").exists()
    assert (second_workspace.worktree_path / "beta.txt").is_file()
    assert not (second_workspace.worktree_path / "alpha.txt").exists()


def test_stale_attempt_cannot_provision_or_resolve_current_worktree(tmp_path: Path) -> None:
    root, _, base = _base_clone(tmp_path)
    assignment = _assignments(base)["task-alpha"]
    first, workspace = _provision(root, assignment, sequence=1)
    second = create_worker_attempt(assignment, attempt_sequence=2)

    with pytest.raises(FleetContractError, match="stale worker attempt"):
        provision_attempt_worktree(
            assignment=assignment,
            attempt=first,
            active_attempt=second,
            repository_url=REPOSITORY_URL,
            root=root,
        )
    with pytest.raises(FleetContractError, match="stale worker attempt"):
        resolve_active_attempt_worktree(
            assignment=assignment,
            attempt=first,
            active_attempt=second,
            attempt_workspace=workspace,
            repository_url=REPOSITORY_URL,
            root=root,
        )


def test_worktree_readback_tracks_current_diff_but_preserves_static_binding(tmp_path: Path) -> None:
    root, _, base = _base_clone(tmp_path)
    assignment = _assignments(base)["task-alpha"]
    attempt, workspace = _provision(root, assignment)
    (workspace.worktree_path / "evidence.txt").write_text("failed attempt evidence\n", encoding="utf-8")

    refreshed = resolve_active_attempt_worktree(
        assignment=assignment,
        attempt=attempt,
        active_attempt=attempt,
        attempt_workspace=workspace,
        repository_url=REPOSITORY_URL,
        root=root,
    )
    assert refreshed.binding_hash == workspace.binding_hash
    assert refreshed.head_revision == base
    assert refreshed.changed_paths == ("evidence.txt",)
    assert refreshed.worktree_readback_sha256 != workspace.worktree_readback_sha256


def test_committed_attempt_reprovision_and_exact_head_handoff_are_current_only(tmp_path: Path) -> None:
    root, _, base = _base_clone(tmp_path)
    assignment = _assignments(base)["task-alpha"]
    first, workspace = _provision(root, assignment)
    (workspace.worktree_path / "committed-evidence.txt").write_text("exact head\n", encoding="utf-8")
    _git(workspace.worktree_path, "add", "committed-evidence.txt")
    _git(workspace.worktree_path, "commit", "-m", "attempt head")
    committed_head = _git(workspace.worktree_path, "rev-parse", "HEAD")
    assert committed_head != base

    # A process restart can rediscover the same active attempt after it committed;
    # provision is idempotent and validates base ancestry rather than requiring
    # HEAD to remain at the original base.
    replay = provision_attempt_worktree(
        assignment=assignment,
        attempt=first,
        active_attempt=first,
        repository_url=REPOSITORY_URL,
        root=root,
    )
    assert replay.head_revision == committed_head
    assert replay.binding_hash == workspace.binding_hash
    assert "worktreePath" not in replay.to_dict()
    assert "baseRepositoryPath" not in replay.to_dict()

    handoff = read_active_attempt_draft_pr_handoff(
        assignment=assignment,
        attempt=first,
        active_attempt=first,
        attempt_workspace=replay,
        repository_url=REPOSITORY_URL,
        root=root,
    )
    assert handoff.head_revision == committed_head
    assert handoff.branch_name == replay.branch_name
    assert "worktreePath" not in handoff.to_dict()

    second = create_worker_attempt(assignment, attempt_sequence=2)
    with pytest.raises(FleetContractError, match="stale worker attempt"):
        read_active_attempt_draft_pr_handoff(
            assignment=assignment,
            attempt=first,
            active_attempt=second,
            attempt_workspace=replay,
            repository_url=REPOSITORY_URL,
            root=root,
        )


def test_cleanup_rejects_current_attempt_and_retains_failed_evidence_until_superseded(tmp_path: Path) -> None:
    root, _, base = _base_clone(tmp_path)
    assignment = _assignments(base)["task-alpha"]
    first, first_workspace = _provision(root, assignment, sequence=1)
    (first_workspace.worktree_path / "failure-evidence.txt").write_text("retain until explicit cleanup\n", encoding="utf-8")
    release = create_attempt_worktree_release(
        assignment,
        first,
        controller_state="SETTLED",
        controller_state_ref=CONTROLLER_REF,
    )

    with pytest.raises(FleetContractError, match="active/current"):
        cleanup_settled_attempt_worktree(
            assignment=assignment,
            attempt=first,
            active_attempt=first,
            attempt_workspace=first_workspace,
            release=release,
            repository_url=REPOSITORY_URL,
            root=root,
        )
    assert (first_workspace.worktree_path / "failure-evidence.txt").is_file()

    with pytest.raises(FleetContractError, match="current active attempt"):
        cleanup_settled_attempt_worktree(
            assignment=assignment,
            attempt=first,
            active_attempt=None,
            attempt_workspace=first_workspace,
            release=release,
            repository_url=REPOSITORY_URL,
            root=root,
        )
    assert (first_workspace.worktree_path / "failure-evidence.txt").is_file()

    second, second_workspace = _provision(root, assignment, sequence=2)
    cleanup_settled_attempt_worktree(
        assignment=assignment,
        attempt=first,
        active_attempt=second,
        attempt_workspace=first_workspace,
        release=create_attempt_worktree_release(
            assignment,
            first,
            controller_state="SUPERSEDED",
            controller_state_ref=CONTROLLER_REF,
        ),
        repository_url=REPOSITORY_URL,
        root=root,
    )
    assert not first_workspace.worktree_path.exists()
    assert second_workspace.worktree_path.exists()


def test_cleanup_recomputes_release_hash_before_targeted_removal(tmp_path: Path) -> None:
    root, _, base = _base_clone(tmp_path)
    assignment = _assignments(base)["task-alpha"]
    first, first_workspace = _provision(root, assignment, sequence=1)
    second, _ = _provision(root, assignment, sequence=2)
    release = create_attempt_worktree_release(
        assignment,
        first,
        controller_state="SUPERSEDED",
        controller_state_ref=CONTROLLER_REF,
    )
    forged = AttemptWorktreeRelease(
        task_id=release.task_id,
        assignment_hash=release.assignment_hash,
        attempt_id=release.attempt_id,
        attempt_hash=release.attempt_hash,
        controller_state=release.controller_state,
        controller_state_ref=release.controller_state_ref,
        release_hash="0" * 64,
    )
    with pytest.raises(FleetContractError, match="cleanup release"):
        cleanup_settled_attempt_worktree(
            assignment=assignment,
            attempt=first,
            active_attempt=second,
            attempt_workspace=first_workspace,
            release=forged,
            repository_url=REPOSITORY_URL,
            root=root,
        )
    assert first_workspace.worktree_path.exists()


def test_base_drift_and_symlink_worktree_root_fail_closed(tmp_path: Path) -> None:
    root, repo, base = _base_clone(tmp_path)
    assignment = _assignments(base)["task-alpha"]
    (repo / "README.md").write_text("base drift\n", encoding="utf-8")
    with pytest.raises(FleetContractError, match="clean"):
        _provision(root, assignment)

    # Restore the exact base clone before exercising path safety separately.
    _git(repo, "checkout", "--", "README.md")
    external = tmp_path / "outside"
    external.mkdir()
    (root / assignment.workspace_id / "fleet-worktrees").symlink_to(external, target_is_directory=True)
    with pytest.raises(FleetContractError, match="invalid|symlink"):
        _provision(root, assignment)


def test_base_revision_mismatch_and_branch_derivation_fail_closed(tmp_path: Path) -> None:
    root, _, actual_base = _base_clone(tmp_path)
    wrong_base = "d" * 40
    assignment = _assignments(wrong_base)["task-alpha"]
    attempt = create_worker_attempt(assignment, attempt_sequence=1)

    with pytest.raises(FleetContractError, match="HEAD"):
        provision_attempt_worktree(
            assignment=assignment,
            attempt=attempt,
            active_attempt=attempt,
            repository_url=REPOSITORY_URL,
            root=root,
        )
    assert actual_base != wrong_base
    branch = deterministic_attempt_branch(_assignments(actual_base)["task-alpha"], create_worker_attempt(_assignments(actual_base)["task-alpha"], attempt_sequence=1))
    assert branch.startswith("sovereign/fleet/")
    assert "run-worktree-identity" not in branch
    assert "task-alpha" not in branch


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "backend").is_dir() and (candidate / "scripts" / "sovereign-backend").is_dir():
            return candidate
    raise AssertionError("repository root not found")


def test_attempt_worktree_runtime_and_policy_mirrors_are_byte_identical() -> None:
    root = _repo_root()
    assert (root / "backend/agent_runtime/fleet_attempt_worktrees.py").read_bytes() == (
        root / "scripts/sovereign-backend/agent_runtime/fleet_attempt_worktrees.py"
    ).read_bytes()
    assert (root / "backend/agent_runtime/workspace_policy.py").read_bytes() == (
        root / "scripts/sovereign-backend/agent_runtime/workspace_policy.py"
    ).read_bytes()
    assert (root / "backend/agent_runtime/cognitive_repository_tools.py").read_bytes() == (
        root / "scripts/sovereign-backend/agent_runtime/cognitive_repository_tools.py"
    ).read_bytes()
    assert (root / "backend/agent_runtime/cognitive_swarm_routes.py").read_bytes() == (
        root / "scripts/sovereign-backend/agent_runtime/cognitive_swarm_routes.py"
    ).read_bytes()
