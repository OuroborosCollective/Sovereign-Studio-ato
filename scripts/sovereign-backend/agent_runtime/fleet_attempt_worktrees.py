"""Physical Git worktree isolation for bounded Fleet worker attempts.

The Agent Job clone remains the outer repository/provenance boundary.  This module
creates a separate Git worktree below that job workspace for one *server-bound*
Fleet assignment attempt.  It neither schedules workers nor grants an attempt any
additional authority: callers must supply both the selected attempt and the
currently active server-side attempt, which are checked with
``require_active_attempt`` before a filesystem path is resolved.

All Git invocation is argv-only through :mod:`git_workspace`; no global prune,
shell interpolation, caller-selected path, or caller-selected branch is allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import Any, Mapping

from .agent_run_receipts import GitWorkspaceIdentity, read_git_workspace_identity
from .fleet_attempts import FleetWorkerAttempt, require_active_attempt
from .fleet_supervisor import FleetContractError, FleetWorkerAssignment, stable_hash
from .git_workspace import run_git_command
from .workspace_policy import (
    WorkspacePolicyError,
    fleet_attempt_worktree_path,
    fleet_worktree_root_for_workspace,
    repo_dir_for_workspace,
    safe_workspace_path,
    validate_repo_url_for_workspace,
    validate_workspace_branch,
)


ATTEMPT_WORKTREE_SCHEMA_VERSION = "sovereign.fleet.attempt-worktree.v1"
ATTEMPT_WORKTREE_RELEASE_SCHEMA_VERSION = "sovereign.fleet.attempt-worktree-release.v1"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_RELEASE_STATES = frozenset({"SETTLED", "RELEASABLE", "SUPERSEDED"})


def _path_hash(path: Path) -> str:
    return sha256(str(path).encode("utf-8")).hexdigest()


def _normalized_origin(value: str) -> str:
    return str(value or "").strip().removesuffix("/").removesuffix(".git")


def _ensure_inside(child: Path, parent: Path, message: str) -> None:
    try:
        child.relative_to(parent)
    except ValueError as exc:
        raise FleetContractError(message) from exc


def _require_sha40(value: object, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA40.fullmatch(normalized):
        raise FleetContractError(f"{field} must be an exact Git revision")
    return normalized


def _require_sha64(value: object, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA64.fullmatch(normalized):
        raise FleetContractError(f"{field} must be an exact SHA-256 value")
    return normalized


def _verified_attempt(value: FleetWorkerAttempt | Mapping[str, Any]) -> FleetWorkerAttempt:
    """Reparse even dataclass values so a caller cannot forge attempt fields."""

    return FleetWorkerAttempt.from_dict(value.to_dict() if isinstance(value, FleetWorkerAttempt) else value)


def _active_attempt(
    assignment: FleetWorkerAssignment,
    attempt: FleetWorkerAttempt | Mapping[str, Any],
    active_attempt: FleetWorkerAttempt | Mapping[str, Any],
) -> FleetWorkerAttempt:
    selected = _verified_attempt(attempt)
    active = _verified_attempt(active_attempt)
    require_active_attempt(selected, active, assignment)
    if selected.controller_run_id != assignment.controller_run_id:
        raise FleetContractError("worker attempt run identity does not match the assignment")
    if selected.expected_base_revision != assignment.expected_base_revision:
        raise FleetContractError("worker attempt base revision does not match the assignment")
    if selected.capability_manifest_hash != assignment.capability_manifest_hash:
        raise FleetContractError("worker attempt capability manifest does not match the assignment")
    return selected


def deterministic_attempt_branch(
    assignment: FleetWorkerAssignment,
    attempt: FleetWorkerAttempt | Mapping[str, Any],
) -> str:
    """Derive an opaque branch name without trusting raw run/task fragments."""

    selected = _verified_attempt(attempt)
    if selected.task_id != assignment.task_id or selected.assignment_hash != assignment.assignment_hash:
        raise FleetContractError("attempt branch identity is not bound to the assignment")
    run_short = sha256(assignment.controller_run_id.encode("utf-8")).hexdigest()[:12]
    task_short = sha256(assignment.task_id.encode("utf-8")).hexdigest()[:12]
    assignment_short = assignment.assignment_hash[:12]
    derived = f"sovereign/fleet/{run_short}/{task_short}/{assignment_short}/a-{selected.attempt_sequence}"
    try:
        return validate_workspace_branch(derived)
    except WorkspacePolicyError as exc:
        raise FleetContractError("derived Fleet attempt branch is invalid") from exc


@dataclass(frozen=True, slots=True)
class AttemptWorkspace:
    """Read-back-bound physical location for exactly one active Fleet attempt."""

    repository_url: str
    workspace_id: str
    run_id: str
    task_id: str
    assignment_hash: str
    attempt_id: str
    attempt_sequence: int
    attempt_hash: str
    base_repository_path: Path
    worktree_path: Path
    branch_name: str
    base_revision: str
    head_revision: str
    worktree_readback_sha256: str
    changed_paths: tuple[str, ...]
    binding_hash: str

    def _payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": ATTEMPT_WORKTREE_SCHEMA_VERSION,
            "repositoryUrl": self.repository_url,
            "workspaceId": self.workspace_id,
            "runId": self.run_id,
            "taskId": self.task_id,
            "assignmentHash": self.assignment_hash,
            "attemptId": self.attempt_id,
            "attemptSequence": self.attempt_sequence,
            "attemptHash": self.attempt_hash,
            "baseRepositoryPath": str(self.base_repository_path),
            "worktreePath": str(self.worktree_path),
            "branchName": self.branch_name,
            "baseRevision": self.base_revision,
        }

    def receipt_binding(self) -> dict[str, Any]:
        """Return secret-free attempt/worktree fields for a tool receipt."""

        return {
            "schemaVersion": ATTEMPT_WORKTREE_SCHEMA_VERSION,
            "workspaceId": self.workspace_id,
            "runId": self.run_id,
            "taskId": self.task_id,
            "assignmentHash": self.assignment_hash,
            "attemptId": self.attempt_id,
            "attemptSequence": self.attempt_sequence,
            "attemptHash": self.attempt_hash,
            "branchName": self.branch_name,
            "baseRevision": self.base_revision,
            "headRevision": self.head_revision,
            "worktreePathSha256": _path_hash(self.worktree_path),
            "worktreeReadbackSha256": self.worktree_readback_sha256,
            "worktreeBindingHash": self.binding_hash,
            "changedPaths": list(self.changed_paths),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": ATTEMPT_WORKTREE_SCHEMA_VERSION,
            "repositoryUrl": self.repository_url,
            "workspaceId": self.workspace_id,
            "runId": self.run_id,
            "taskId": self.task_id,
            "assignmentHash": self.assignment_hash,
            "attemptId": self.attempt_id,
            "attemptSequence": self.attempt_sequence,
            "attemptHash": self.attempt_hash,
            "branchName": self.branch_name,
            "baseRevision": self.base_revision,
            "headRevision": self.head_revision,
            "baseRepositoryPathSha256": _path_hash(self.base_repository_path),
            "worktreePathSha256": _path_hash(self.worktree_path),
            "worktreeReadbackSha256": self.worktree_readback_sha256,
            "changedPaths": list(self.changed_paths),
            "bindingHash": self.binding_hash,
            "authoritative": False,
        }


@dataclass(frozen=True, slots=True)
class AttemptWorktreeRelease:
    """A controller-issued authorization for one exact settled worktree cleanup."""

    task_id: str
    assignment_hash: str
    attempt_id: str
    attempt_hash: str
    controller_state: str
    controller_state_ref: str
    release_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": ATTEMPT_WORKTREE_RELEASE_SCHEMA_VERSION,
            "taskId": self.task_id,
            "assignmentHash": self.assignment_hash,
            "attemptId": self.attempt_id,
            "attemptHash": self.attempt_hash,
            "controllerState": self.controller_state,
            "controllerStateRef": self.controller_state_ref,
            "releaseHash": self.release_hash,
        }


@dataclass(frozen=True, slots=True)
class AttemptWorktreeDraftHandoff:
    """The only server-side, exact-head handoff eligible for a Fleet Draft PR."""

    run_id: str
    task_id: str
    assignment_hash: str
    attempt_id: str
    attempt_sequence: int
    attempt_hash: str
    branch_name: str
    base_revision: str
    head_revision: str
    worktree_path_sha256: str
    worktree_readback_sha256: str
    worktree_binding_hash: str
    changed_paths: tuple[str, ...]
    handoff_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": ATTEMPT_WORKTREE_SCHEMA_VERSION,
            "runId": self.run_id,
            "taskId": self.task_id,
            "assignmentHash": self.assignment_hash,
            "attemptId": self.attempt_id,
            "attemptSequence": self.attempt_sequence,
            "attemptHash": self.attempt_hash,
            "branchName": self.branch_name,
            "baseRevision": self.base_revision,
            "headRevision": self.head_revision,
            "worktreePathSha256": self.worktree_path_sha256,
            "worktreeReadbackSha256": self.worktree_readback_sha256,
            "worktreeBindingHash": self.worktree_binding_hash,
            "changedPaths": list(self.changed_paths),
            "handoffHash": self.handoff_hash,
            "authoritative": False,
        }


def _release_payload(
    *,
    task_id: str,
    assignment_hash: str,
    attempt_id: str,
    attempt_hash: str,
    controller_state: str,
    controller_state_ref: str,
) -> dict[str, str]:
    return {
        "schemaVersion": ATTEMPT_WORKTREE_RELEASE_SCHEMA_VERSION,
        "taskId": task_id,
        "assignmentHash": assignment_hash,
        "attemptId": attempt_id,
        "attemptHash": attempt_hash,
        "controllerState": controller_state,
        "controllerStateRef": controller_state_ref,
    }


def create_attempt_worktree_release(
    assignment: FleetWorkerAssignment,
    attempt: FleetWorkerAttempt | Mapping[str, Any],
    *,
    controller_state: str,
    controller_state_ref: str,
) -> AttemptWorktreeRelease:
    """Build a bounded controller receipt; callers must use real state readback."""

    selected = _verified_attempt(attempt)
    if selected.task_id != assignment.task_id or selected.assignment_hash != assignment.assignment_hash:
        raise FleetContractError("release attempt is not bound to the assignment")
    state = str(controller_state or "").strip().upper()
    if state not in _RELEASE_STATES:
        raise FleetContractError("attempt worktree cleanup requires a settled controller state")
    state_ref = _require_sha64(controller_state_ref, "controller_state_ref")
    payload = _release_payload(
        task_id=selected.task_id,
        assignment_hash=selected.assignment_hash,
        attempt_id=selected.attempt_id,
        attempt_hash=selected.attempt_hash,
        controller_state=state,
        controller_state_ref=state_ref,
    )
    return AttemptWorktreeRelease(
        task_id=selected.task_id,
        assignment_hash=selected.assignment_hash,
        attempt_id=selected.attempt_id,
        attempt_hash=selected.attempt_hash,
        controller_state=state,
        controller_state_ref=state_ref,
        release_hash=stable_hash(payload),
    )


def _base_clone(
    *,
    assignment: FleetWorkerAssignment,
    repository_url: str,
    root: Path | None,
) -> tuple[Path, str]:
    try:
        safe_url = validate_repo_url_for_workspace(repository_url)
        workspace = safe_workspace_path(assignment.workspace_id, root)
        base_repo = repo_dir_for_workspace(assignment.workspace_id, root).resolve()
    except WorkspacePolicyError as exc:
        raise FleetContractError("Fleet attempt workspace identity is invalid") from exc
    if workspace.is_symlink() or base_repo.is_symlink() or not base_repo.is_dir():
        raise FleetContractError("Fleet base clone path is unavailable or unsafe")
    _ensure_inside(base_repo, workspace, "Fleet base clone escapes the Agent Job workspace")
    git_dir = base_repo / ".git"
    if git_dir.is_symlink() or not git_dir.is_dir():
        raise FleetContractError("Fleet base clone has an unsafe Git directory")
    origin = run_git_command(("git", "remote", "get-url", "origin"), base_repo, 30)
    if origin.returncode != 0 or _normalized_origin(origin.stdout) != _normalized_origin(safe_url):
        raise FleetContractError("Fleet base clone origin does not match the bound repository")
    base_identity = read_git_workspace_identity(base_repo, repository=safe_url)
    expected_base = _require_sha40(assignment.expected_base_revision, "assignment expected_base_revision")
    if base_identity.base_commit_sha != expected_base:
        raise FleetContractError("Fleet base clone HEAD does not match the assignment base revision")
    if base_identity.changed_paths:
        raise FleetContractError("Fleet base clone must be clean before attempt worktree assignment")
    return base_repo, safe_url


def _worktree_records(base_repo: Path) -> dict[Path, dict[str, str]]:
    completed = run_git_command(("git", "worktree", "list", "--porcelain"), base_repo, 30)
    if completed.returncode != 0:
        raise FleetContractError("Fleet worktree inventory is unavailable")
    records: dict[Path, dict[str, str]] = {}
    current: dict[str, str] = {}
    for line in (completed.stdout or "").splitlines():
        if not line.strip():
            if current.get("worktree"):
                try:
                    records[Path(current["worktree"]).resolve()] = current
                except OSError as exc:
                    raise FleetContractError("Fleet worktree inventory contains an invalid path") from exc
            current = {}
            continue
        key, separator, value = line.partition(" ")
        if not separator:
            continue
        current[key] = value.strip()
    if current.get("worktree"):
        try:
            records[Path(current["worktree"]).resolve()] = current
        except OSError as exc:
            raise FleetContractError("Fleet worktree inventory contains an invalid path") from exc
    return records


def _validate_gitdir_link(base_repo: Path, worktree: Path) -> None:
    git_file = worktree / ".git"
    if git_file.is_symlink() or not git_file.is_file():
        raise FleetContractError("Fleet attempt worktree has an unsafe Git link")
    try:
        payload = git_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise FleetContractError("Fleet attempt worktree Git link is unreadable") from exc
    if len(payload) > 1_024 or not payload.startswith("gitdir: "):
        raise FleetContractError("Fleet attempt worktree Git link is invalid")
    location = payload.removeprefix("gitdir: ").strip()
    if not location or "\x00" in location:
        raise FleetContractError("Fleet attempt worktree Git link is invalid")
    raw_metadata = Path(location)
    metadata = (raw_metadata if raw_metadata.is_absolute() else git_file.parent / raw_metadata).resolve()
    metadata_root = (base_repo / ".git" / "worktrees").resolve()
    _ensure_inside(metadata, metadata_root, "Fleet attempt worktree Git link escapes base clone metadata")
    if metadata.is_symlink() or not metadata.is_dir():
        raise FleetContractError("Fleet attempt worktree Git metadata is unavailable")


def _validate_registered_worktree(
    *,
    base_repo: Path,
    worktree: Path,
    branch_name: str,
    repository_url: str,
    expected_base_revision: str,
    require_head_at_base: bool,
) -> GitWorkspaceIdentity:
    records = _worktree_records(base_repo)
    record = records.get(worktree)
    if record is None:
        raise FleetContractError("Fleet attempt worktree is not registered with the bound base clone")
    if record.get("branch") != f"refs/heads/{branch_name}":
        raise FleetContractError("Fleet attempt worktree branch does not match its deterministic binding")
    if worktree.is_symlink() or not worktree.is_dir():
        raise FleetContractError("Fleet attempt worktree path is unavailable or unsafe")
    _validate_gitdir_link(base_repo, worktree)
    branch = run_git_command(("git", "symbolic-ref", "--quiet", "--short", "HEAD"), worktree, 30)
    if branch.returncode != 0 or branch.stdout.strip() != branch_name:
        raise FleetContractError("Fleet attempt worktree HEAD is not on its bound branch")
    identity = read_git_workspace_identity(worktree, repository=repository_url)
    if require_head_at_base and identity.base_commit_sha != expected_base_revision:
        raise FleetContractError("new Fleet attempt worktree HEAD does not match the assigned base revision")
    ancestry = run_git_command(
        ("git", "merge-base", "--is-ancestor", expected_base_revision, identity.base_commit_sha),
        worktree,
        30,
    )
    if ancestry.returncode != 0:
        raise FleetContractError("Fleet attempt worktree head does not descend from the assigned base revision")
    return identity


def _attempt_workspace(
    *,
    assignment: FleetWorkerAssignment,
    attempt: FleetWorkerAttempt,
    repository_url: str,
    base_repo: Path,
    worktree: Path,
    branch_name: str,
    identity: GitWorkspaceIdentity,
) -> AttemptWorkspace:
    payload = {
        "schemaVersion": ATTEMPT_WORKTREE_SCHEMA_VERSION,
        "repositoryUrl": repository_url,
        "workspaceId": assignment.workspace_id,
        "runId": assignment.controller_run_id,
        "taskId": assignment.task_id,
        "assignmentHash": assignment.assignment_hash,
        "attemptId": attempt.attempt_id,
        "attemptSequence": attempt.attempt_sequence,
        "attemptHash": attempt.attempt_hash,
        "baseRepositoryPath": str(base_repo),
        "worktreePath": str(worktree),
        "branchName": branch_name,
        "baseRevision": assignment.expected_base_revision,
    }
    return AttemptWorkspace(
        repository_url=repository_url,
        workspace_id=assignment.workspace_id,
        run_id=assignment.controller_run_id,
        task_id=assignment.task_id,
        assignment_hash=assignment.assignment_hash,
        attempt_id=attempt.attempt_id,
        attempt_sequence=attempt.attempt_sequence,
        attempt_hash=attempt.attempt_hash,
        base_repository_path=base_repo,
        worktree_path=worktree,
        branch_name=branch_name,
        base_revision=assignment.expected_base_revision,
        head_revision=identity.base_commit_sha,
        worktree_readback_sha256=identity.authoritative_readback_sha256,
        changed_paths=identity.changed_paths,
        binding_hash=stable_hash(payload),
    )


def provision_attempt_worktree(
    *,
    assignment: FleetWorkerAssignment,
    attempt: FleetWorkerAttempt | Mapping[str, Any],
    active_attempt: FleetWorkerAttempt | Mapping[str, Any],
    repository_url: str,
    root: Path | None = None,
) -> AttemptWorkspace:
    """Create or read back the only worktree admissible for one active attempt."""

    selected = _active_attempt(assignment, attempt, active_attempt)
    base_repo, safe_url = _base_clone(
        assignment=assignment,
        repository_url=repository_url,
        root=root,
    )
    branch_name = deterministic_attempt_branch(assignment, selected)
    try:
        worktree_root = fleet_worktree_root_for_workspace(assignment.workspace_id, root)
        worktree = fleet_attempt_worktree_path(assignment.workspace_id, selected.attempt_id, root)
    except WorkspacePolicyError as exc:
        raise FleetContractError("Fleet attempt worktree path is invalid") from exc
    if worktree_root.is_symlink() or worktree.is_symlink():
        raise FleetContractError("Fleet attempt worktree path may not be a symlink")
    _ensure_inside(worktree, worktree_root, "Fleet attempt worktree path escapes its workspace root")
    records = _worktree_records(base_repo)
    registered = records.get(worktree)
    created_now = False
    if worktree.exists():
        if registered is None:
            raise FleetContractError("Fleet attempt worktree path is occupied outside the base clone registry")
    elif registered is not None:
        raise FleetContractError("Fleet attempt worktree is registered but missing; global prune is forbidden")
    else:
        worktree_root.mkdir(parents=True, exist_ok=True)
        if worktree_root.is_symlink() or not worktree_root.is_dir():
            raise FleetContractError("Fleet worktree root is unavailable or unsafe")
        created = run_git_command(
            ("git", "worktree", "add", "-b", branch_name, str(worktree), assignment.expected_base_revision),
            base_repo,
            120,
        )
        if created.returncode != 0:
            raise FleetContractError("Fleet attempt worktree creation failed")
        created_now = True
    identity = _validate_registered_worktree(
        base_repo=base_repo,
        worktree=worktree,
        branch_name=branch_name,
        repository_url=safe_url,
        expected_base_revision=assignment.expected_base_revision,
        require_head_at_base=created_now,
    )
    return _attempt_workspace(
        assignment=assignment,
        attempt=selected,
        repository_url=safe_url,
        base_repo=base_repo,
        worktree=worktree,
        branch_name=branch_name,
        identity=identity,
    )


def resolve_active_attempt_worktree(
    *,
    assignment: FleetWorkerAssignment,
    attempt: FleetWorkerAttempt | Mapping[str, Any],
    active_attempt: FleetWorkerAttempt | Mapping[str, Any],
    attempt_workspace: AttemptWorkspace,
    repository_url: str,
    root: Path | None = None,
) -> AttemptWorkspace:
    """Re-read a bound active worktree and reject stale path/branch/revision drift."""

    selected = _active_attempt(assignment, attempt, active_attempt)
    base_repo, safe_url = _base_clone(
        assignment=assignment,
        repository_url=repository_url,
        root=root,
    )
    branch_name = deterministic_attempt_branch(assignment, selected)
    try:
        expected_path = fleet_attempt_worktree_path(assignment.workspace_id, selected.attempt_id, root)
    except WorkspacePolicyError as exc:
        raise FleetContractError("Fleet attempt worktree path is invalid") from exc
    if (
        attempt_workspace.workspace_id != assignment.workspace_id
        or attempt_workspace.run_id != assignment.controller_run_id
        or attempt_workspace.task_id != assignment.task_id
        or attempt_workspace.assignment_hash != assignment.assignment_hash
        or attempt_workspace.attempt_id != selected.attempt_id
        or attempt_workspace.attempt_sequence != selected.attempt_sequence
        or attempt_workspace.attempt_hash != selected.attempt_hash
        or attempt_workspace.base_repository_path != base_repo
        or attempt_workspace.worktree_path != expected_path
        or attempt_workspace.branch_name != branch_name
        or attempt_workspace.base_revision != assignment.expected_base_revision
    ):
        raise FleetContractError("Fleet attempt worktree binding no longer matches the active attempt")
    identity = _validate_registered_worktree(
        base_repo=base_repo,
        worktree=expected_path,
        branch_name=branch_name,
        repository_url=safe_url,
        expected_base_revision=assignment.expected_base_revision,
        require_head_at_base=False,
    )
    refreshed = _attempt_workspace(
        assignment=assignment,
        attempt=selected,
        repository_url=safe_url,
        base_repo=base_repo,
        worktree=expected_path,
        branch_name=branch_name,
        identity=identity,
    )
    if refreshed.binding_hash != attempt_workspace.binding_hash:
        raise FleetContractError("Fleet attempt worktree static binding changed during readback")
    return refreshed


def read_active_attempt_draft_pr_handoff(
    *,
    assignment: FleetWorkerAssignment,
    attempt: FleetWorkerAttempt | Mapping[str, Any],
    active_attempt: FleetWorkerAttempt | Mapping[str, Any],
    attempt_workspace: AttemptWorkspace,
    repository_url: str,
    root: Path | None = None,
) -> AttemptWorktreeDraftHandoff:
    """Read an exact active-attempt branch/HEAD without exposing server paths.

    This is intentionally a handoff gate, not a GitHub mutation.  Any publisher
    must consume this exact branch/head/readback binding and re-read it after
    publication; the generic legacy Agent Job publisher is not treated as proof.
    """

    current = resolve_active_attempt_worktree(
        assignment=assignment,
        attempt=attempt,
        active_attempt=active_attempt,
        attempt_workspace=attempt_workspace,
        repository_url=repository_url,
        root=root,
    )
    payload = {
        "schemaVersion": ATTEMPT_WORKTREE_SCHEMA_VERSION,
        "runId": current.run_id,
        "taskId": current.task_id,
        "assignmentHash": current.assignment_hash,
        "attemptId": current.attempt_id,
        "attemptSequence": current.attempt_sequence,
        "attemptHash": current.attempt_hash,
        "branchName": current.branch_name,
        "baseRevision": current.base_revision,
        "headRevision": current.head_revision,
        "worktreePathSha256": _path_hash(current.worktree_path),
        "worktreeReadbackSha256": current.worktree_readback_sha256,
        "worktreeBindingHash": current.binding_hash,
        "changedPaths": list(current.changed_paths),
    }
    return AttemptWorktreeDraftHandoff(
        run_id=current.run_id,
        task_id=current.task_id,
        assignment_hash=current.assignment_hash,
        attempt_id=current.attempt_id,
        attempt_sequence=current.attempt_sequence,
        attempt_hash=current.attempt_hash,
        branch_name=current.branch_name,
        base_revision=current.base_revision,
        head_revision=current.head_revision,
        worktree_path_sha256=payload["worktreePathSha256"],
        worktree_readback_sha256=current.worktree_readback_sha256,
        worktree_binding_hash=current.binding_hash,
        changed_paths=current.changed_paths,
        handoff_hash=stable_hash(payload),
    )


def cleanup_settled_attempt_worktree(
    *,
    assignment: FleetWorkerAssignment,
    attempt: FleetWorkerAttempt | Mapping[str, Any],
    active_attempt: FleetWorkerAttempt | Mapping[str, Any] | None,
    attempt_workspace: AttemptWorkspace,
    release: AttemptWorktreeRelease,
    repository_url: str,
    root: Path | None = None,
) -> None:
    """Remove only one explicitly released, non-current attempt worktree.

    A failed attempt can remain intact for evidence.  This operation is deliberately
    not a global cleanup and never invokes ``git worktree prune``.
    """

    selected = _verified_attempt(attempt)
    if selected.task_id != assignment.task_id or selected.assignment_hash != assignment.assignment_hash:
        raise FleetContractError("cleanup attempt is not bound to the assignment")
    if (
        release.task_id != selected.task_id
        or release.assignment_hash != selected.assignment_hash
        or release.attempt_id != selected.attempt_id
        or release.attempt_hash != selected.attempt_hash
        or release.controller_state not in _RELEASE_STATES
        or not _SHA64.fullmatch(release.controller_state_ref)
        or release.release_hash
        != stable_hash(_release_payload(
            task_id=release.task_id,
            assignment_hash=release.assignment_hash,
            attempt_id=release.attempt_id,
            attempt_hash=release.attempt_hash,
            controller_state=release.controller_state,
            controller_state_ref=release.controller_state_ref,
        ))
    ):
        raise FleetContractError("attempt worktree cleanup release is not bound to the selected attempt")
    if active_attempt is None:
        raise FleetContractError("cleanup requires a current active attempt readback")
    current = _verified_attempt(active_attempt)
    _active_attempt(assignment, current, current)
    if current.attempt_id == selected.attempt_id or current.attempt_hash == selected.attempt_hash:
        raise FleetContractError("cleanup of the active/current attempt worktree is forbidden")
    if selected.attempt_sequence >= current.attempt_sequence:
        raise FleetContractError("cleanup attempt is not an older settled retry")
    base_repo, safe_url = _base_clone(
        assignment=assignment,
        repository_url=repository_url,
        root=root,
    )
    expected_branch = deterministic_attempt_branch(assignment, selected)
    try:
        expected_path = fleet_attempt_worktree_path(assignment.workspace_id, selected.attempt_id, root)
    except WorkspacePolicyError as exc:
        raise FleetContractError("Fleet attempt worktree cleanup path is invalid") from exc
    if (
        attempt_workspace.worktree_path != expected_path
        or attempt_workspace.base_repository_path != base_repo
        or attempt_workspace.branch_name != expected_branch
        or attempt_workspace.binding_hash
        != _attempt_workspace(
            assignment=assignment,
            attempt=selected,
            repository_url=safe_url,
            base_repo=base_repo,
            worktree=expected_path,
            branch_name=expected_branch,
            identity=_validate_registered_worktree(
                base_repo=base_repo,
                worktree=expected_path,
                branch_name=expected_branch,
                repository_url=safe_url,
                expected_base_revision=assignment.expected_base_revision,
                require_head_at_base=False,
            ),
        ).binding_hash
    ):
        raise FleetContractError("attempt worktree cleanup binding changed before removal")
    removed = run_git_command(("git", "worktree", "remove", "--force", str(expected_path)), base_repo, 120)
    if removed.returncode != 0:
        raise FleetContractError("attempt worktree cleanup failed")
    if expected_path.exists() or expected_path in _worktree_records(base_repo):
        raise FleetContractError("attempt worktree cleanup readback failed")


__all__ = [
    "ATTEMPT_WORKTREE_RELEASE_SCHEMA_VERSION",
    "ATTEMPT_WORKTREE_SCHEMA_VERSION",
    "AttemptWorkspace",
    "AttemptWorktreeDraftHandoff",
    "AttemptWorktreeRelease",
    "cleanup_settled_attempt_worktree",
    "create_attempt_worktree_release",
    "deterministic_attempt_branch",
    "provision_attempt_worktree",
    "read_active_attempt_draft_pr_handoff",
    "resolve_active_attempt_worktree",
]
