import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from agent_runtime.cognitive_repository_tools import (
    BoundRepositoryToolset,
    FleetAttemptSnapshotEvidence,
    READ_REPOSITORY_TOOL_NAMES,
    ROLE_PATH_PREFIXES,
    ROLE_WORK_PACKAGES,
    WRITE_REPOSITORY_TOOL_NAMES,
    _path_in_role_scope,
    _redact,
    _safe_path,
    build_repository_fleet_bindings,
)
import agent_runtime.cognitive_repository_tools as repository_tools
from agent_runtime.cognitive_swarm_manifest import WORKER_ROLES
from agent_runtime.fleet_attempts import create_worker_attempt
from agent_runtime.fleet_attempt_worktrees import (
    create_attempt_worktree_release,
    fleet_attempt_worktree_path,
    resolve_active_attempt_worktree,
)
from agent_runtime.fleet_supervisor import FleetContractError
from agent_runtime.job_store import update_agent_job_state
from agent_runtime.tools.file_tool import FileReadTool
from agent_runtime.tools.base import ToolResult


def _toolset(*, write_confirmed: bool) -> BoundRepositoryToolset:
    return BoundRepositoryToolset(
        get_connection=lambda: None,
        user_id="00000000-0000-0000-0000-000000000000",
        run_id="run-test-runtime",
        job_id="agent-test-runtime",
        task_ids_by_agent={role: f"task-{role}" for role in WORKER_ROLES},
        workspace_root=Path("/tmp/sovereign-test-workspaces"),
        write_confirmed=write_confirmed,
    )


def _repository_fleet_bindings():
    return build_repository_fleet_bindings(
        run_id="run-test-runtime",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        workspace_id="agent-test-runtime",
        workspace_branch="main",
        base_revision="a" * 40,
        task_ids_by_agent={role: f"task-{role}" for role in WORKER_ROLES},
    )


def test_six_worker_roles_have_explicit_work_and_path_boundaries() -> None:
    assert all(role in ROLE_WORK_PACKAGES for role in WORKER_ROLES)
    assert all(role in ROLE_PATH_PREFIXES for role in WORKER_ROLES)
    assert all(ROLE_WORK_PACKAGES[role].strip() for role in WORKER_ROLES)
    assert all(ROLE_PATH_PREFIXES[role] for role in WORKER_ROLES)
    assert "pattern" in ROLE_WORK_PACKAGES["data_storage"].lower()
    assert "inference" in ROLE_WORK_PACKAGES["business_core"].lower()
    assert "workspace" in ROLE_WORK_PACKAGES["endpoint_bridge"].lower()
    assert "language" in ROLE_WORK_PACKAGES["chat_cognitive"].lower()
    assert "visible status" in ROLE_WORK_PACKAGES["ui_accessibility"].lower()
    assert "depth three" in ROLE_WORK_PACKAGES["predictive_qa"].lower()


def test_repository_paths_fail_closed_outside_role_scope() -> None:
    assert _safe_path("scripts/sovereign-backend/are_inference.py") == "scripts/sovereign-backend/are_inference.py"
    assert _path_in_role_scope("business_core", "scripts/sovereign-backend/are_inference.py") is True
    assert _path_in_role_scope("data_storage", "scripts/sovereign-backend/are_inference.py") is False
    with pytest.raises(ValueError, match="unsafe"):
        _safe_path("../../.env")
    with pytest.raises(ValueError, match="unsafe"):
        _safe_path("/etc/passwd")


def test_role_scopes_do_not_overlap_between_endpoint_and_ui_mutation_zones() -> None:
    assert set(ROLE_PATH_PREFIXES["endpoint_bridge"]).isdisjoint(ROLE_PATH_PREFIXES["ui_accessibility"])


def test_write_tool_exists_only_after_authenticated_execution_intent() -> None:
    read_only = _toolset(write_confirmed=False)
    mutating = _toolset(write_confirmed=True)

    assert read_only.allowed_tool_names("predictive_qa") == READ_REPOSITORY_TOOL_NAMES
    assert not any(tool in read_only.allowed_tool_names("predictive_qa") for tool in WRITE_REPOSITORY_TOOL_NAMES)
    assert all(tool in mutating.allowed_tool_names("predictive_qa") for tool in WRITE_REPOSITORY_TOOL_NAMES)


def test_repository_fleet_plan_is_hash_bound_and_serial_without_independence_receipts() -> None:
    bindings = _repository_fleet_bindings()

    assert bindings.plan.repository == "OuroborosCollective/Sovereign-Studio-ato"
    assert bindings.plan.base_revision == "a" * 40
    assert tuple(lane.sequence for lane in bindings.plan.lanes) == tuple(range(1, len(WORKER_ROLES) + 1))
    assert all(lane.parallel_safe is False for lane in bindings.plan.lanes)
    assert {task.task_id for task in bindings.plan.tasks} == set(bindings.task_ids_by_role.values())
    assert set(bindings.assignments_by_role) == set(WORKER_ROLES)
    assert "ARCHITECTURE_RECEIPTS_MISSING" in bindings.plan.risk_codes
    assert "UNPROVEN_INDEPENDENCE" in bindings.plan.risk_codes
    assert all(
        assignment.plan_hash == bindings.plan.plan_hash
        and assignment.task_id == bindings.task_ids_by_role[role]
        and assignment.expected_base_revision == bindings.plan.base_revision
        for role, assignment in bindings.assignments_by_role.items()
    )


def test_repository_tool_calls_require_the_current_bound_fleet_lane() -> None:
    toolset = _toolset(write_confirmed=True)
    bindings = _repository_fleet_bindings()
    toolset.bind_fleet_execution(bindings)
    role = WORKER_ROLES[0]
    assignment = bindings.assignments_by_role[role]

    with pytest.raises(FleetContractError, match="active Fleet lane"):
        toolset._assert_fleet_lane_admission(role, assignment.task_id)

    with toolset.activate_fleet_lane(assignment.lane_id, (role,)):
        assert toolset._assert_fleet_lane_admission(role, assignment.task_id) == assignment

    with pytest.raises(FleetContractError, match="active Fleet lane"):
        toolset._assert_fleet_lane_admission(role, assignment.task_id)


def test_circuit_opens_after_three_consecutive_tool_failures() -> None:
    toolset = _toolset(write_confirmed=True)
    for _ in range(3):
        toolset._record_call("predictive_qa", mutation=False, failed=True)

    assert toolset.summary()["openCircuits"] == ["predictive_qa"]
    with pytest.raises(RuntimeError, match="circuit is open"):
        toolset._assert_circuit_closed("predictive_qa")


def test_file_read_returns_sha_for_exact_patch_precondition(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    content = "value = 1\n"
    target.write_text(content, encoding="utf-8")

    result = FileReadTool().execute({"path": "sample.py"}, str(tmp_path))

    assert result.status == "done"
    assert result.output == content
    assert result.metadata["sha256"] == hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_parallel_job_evidence_update_has_matching_sql_parameters() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.query = ""
            self.params = ()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params) -> None:
            self.query = query
            self.params = params

    class Connection:
        def __init__(self) -> None:
            self.cursor_instance = Cursor()
            self.committed = False

        def cursor(self):
            return self.cursor_instance

        def commit(self) -> None:
            self.committed = True

    conn = Connection()
    update_agent_job_state(
        conn,
        job_id="agent-test-runtime",
        status="running",
        changed_files=("a.py", "b.py"),
        diff_summary="diff evidence",
        test_summary="test evidence",
        clear_blocker=True,
    )

    assert conn.committed is True
    assert conn.cursor_instance.query.count("%s") == len(conn.cursor_instance.params)
    assert "jsonb_agg(item ORDER BY item)" in conn.cursor_instance.query
    assert len(conn.cursor_instance.params) == 10
    assert conn.cursor_instance.params[3] == '["a.py","b.py"]'
    assert conn.cursor_instance.params[4] == "diff evidence"
    assert conn.cursor_instance.params[5] == "test evidence"
    assert conn.cursor_instance.params[7] is True
    assert conn.cursor_instance.params[9] == "agent-test-runtime"


def test_tool_output_redacts_known_secret_shapes() -> None:
    output = _redact("Authorization: Bearer secret-value-that-is-long and sk-proj-abcdefghijklmnopqrstuv")
    assert "secret-value-that-is-long" not in output
    assert "sk-proj-" not in output
    assert output.count("[REDACTED]") == 2


def _bound_real_fleet_toolset(monkeypatch, tmp_path: Path, *, install_snapshot_observer: bool = True):
    root = tmp_path / "workspaces"
    workspace_id = "agent-fleet-worktree"
    repo = root / workspace_id / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, text=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "fleet@example.invalid"], cwd=repo, check=True, text=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Fleet Test"], cwd=repo, check=True, text=True, capture_output=True)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, text=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, text=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/OuroborosCollective/Sovereign-Studio-ato"],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    )
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True).stdout.strip()
    bindings = build_repository_fleet_bindings(
        run_id="run-test-runtime",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        workspace_id=workspace_id,
        workspace_branch="main",
        base_revision=head,
        task_ids_by_agent={role: f"task-{role}" for role in WORKER_ROLES},
    )
    job = SimpleNamespace(
        workspace_id=workspace_id,
        repo_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
        changed_files=(),
        diff_summary=None,
        test_summary=None,
    )
    toolset = BoundRepositoryToolset(
        get_connection=lambda: SimpleNamespace(close=lambda: None),
        user_id="00000000-0000-0000-0000-000000000000",
        run_id="run-test-runtime",
        job_id="agent-fleet-worktree",
        task_ids_by_agent={role: f"task-{role}" for role in WORKER_ROLES},
        workspace_root=root,
        write_confirmed=True,
    )
    toolset.bind_fleet_execution(bindings)
    monkeypatch.setattr(repository_tools, "read_agent_job", lambda *_args, **_kwargs: job)
    workspaces = toolset.provision_fleet_attempt_workspaces()
    if install_snapshot_observer:
        toolset.set_fleet_attempt_workspace_snapshot_observer(
            lambda snapshot: FleetAttemptSnapshotEvidence(
                fleet_plan_hash=snapshot.fleet_plan_hash,
                controller_run_id=snapshot.controller_run_id,
                snapshot_hash=snapshot.snapshot_hash,
                evidence_id="evidence-rebind-test",
                evidence_sha256="a" * 64,
            )
        )
    return root, repo, head, bindings, toolset, workspaces


def test_fleet_repository_tool_receipt_uses_only_its_active_attempt_worktree(monkeypatch, tmp_path: Path) -> None:
    _, repo, head, bindings, toolset, workspaces = _bound_real_fleet_toolset(monkeypatch, tmp_path)
    assert toolset.read_fleet_workspace_head() == head
    role = WORKER_ROLES[0]
    captured: dict[str, object] = {}

    monkeypatch.setattr(repository_tools, "read_mcp_runtime_identity", lambda **_kwargs: SimpleNamespace(
        revision=head,
        image_digest="sha256:" + ("a" * 64),
        revision_verified=True,
    ))
    def fake_start(*_args, **kwargs):
        captured["arguments"] = kwargs["arguments"]
        return "tool-call-worktree"

    monkeypatch.setattr(repository_tools, "start_agent_tool_call", fake_start)
    monkeypatch.setattr(repository_tools, "append_tool_result_to_job", lambda *_args, **_kwargs: SimpleNamespace(
        passed=True,
        reason="evidence accepted",
        can_prepare_draft_pr=False,
        can_learn_pattern=False,
    ))

    def fake_tool(_job_id, action, _parameters, workspace_path):
        captured["action"] = action
        captured["workspace"] = Path(workspace_path)
        return ToolResult(status="done", tool=action, output="clean", predictive_signal="agent_git_status_completed")

    monkeypatch.setattr(repository_tools, "run_agent_job_tool", fake_tool)
    monkeypatch.setattr(repository_tools, "finish_agent_tool_call", lambda *_args, **kwargs: captured.setdefault("finished", kwargs))

    assignment = bindings.assignments_by_role[role]
    with toolset.activate_fleet_lane(assignment.lane_id, (role,)):
        payload = json.loads(toolset._execute(role, "git-status", {}))

    assert captured["workspace"] == workspaces[role].worktree_path
    assert captured["workspace"] != repo
    arguments = captured["arguments"]
    assert arguments["fleetAttempt"]["attemptId"] == workspaces[role].attempt_id
    assert arguments["attemptWorktree"]["worktreeBindingHash"] == workspaces[role].binding_hash
    assert str(workspaces[role].worktree_path) not in json.dumps(arguments, sort_keys=True)
    finished = captured["finished"]
    assert finished["result_summary"]["attemptWorktree"]["attemptId"] == workspaces[role].attempt_id
    assert f"attempt:{workspaces[role].attempt_id}" in finished["operation_identity"]
    assert payload["attemptWorktree"]["worktreePathSha256"]

    # The preflight is deliberately a worktree readback, not a read of the outer
    # job clone.  A committed attempt cannot silently become a later lane's base.
    (workspaces[role].worktree_path / "committed.txt").write_text("head drift\n", encoding="utf-8")
    subprocess.run(["git", "add", "committed.txt"], cwd=workspaces[role].worktree_path, check=True, text=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "attempt commit"], cwd=workspaces[role].worktree_path, check=True, text=True, capture_output=True)
    with pytest.raises(FleetContractError, match="heads no longer match"):
        toolset.read_fleet_workspace_head()


def test_fleet_attempt_rebind_requires_a_higher_server_attempt_and_retains_old_worktree(monkeypatch, tmp_path: Path) -> None:
    root, _, head, bindings, toolset, workspaces = _bound_real_fleet_toolset(monkeypatch, tmp_path)
    role = WORKER_ROLES[0]
    assignment = bindings.assignments_by_role[role]
    first_attempt = create_worker_attempt(assignment, attempt_sequence=1)
    retry_attempt = create_worker_attempt(assignment, attempt_sequence=2)
    original = workspaces[role]

    with toolset.activate_fleet_lane(assignment.lane_id, (role,)):
        with pytest.raises(FleetContractError, match="active lane"):
            toolset.rebind_fleet_attempt_workspace(role, retry_attempt)

    replacement = toolset.rebind_fleet_attempt_workspace(role, retry_attempt)
    assert replacement.attempt_id == retry_attempt.attempt_id
    assert replacement.worktree_path != original.worktree_path
    assert original.attempt_id in toolset.settled_fleet_attempt_receipts()
    assert str(original.worktree_path) not in json.dumps(toolset.settled_fleet_attempt_receipts(), sort_keys=True)

    with pytest.raises(FleetContractError, match="higher"):
        toolset.rebind_fleet_attempt_workspace(role, retry_attempt)
    with pytest.raises(FleetContractError, match="higher"):
        toolset.rebind_fleet_attempt_workspace(role, first_attempt)
    with pytest.raises(FleetContractError, match="stale worker attempt"):
        resolve_active_attempt_worktree(
            assignment=assignment,
            attempt=first_attempt,
            active_attempt=retry_attempt,
            attempt_workspace=original,
            repository_url="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
            root=root,
        )

    # Re-provision is idempotent after rebind and preserves the higher active retry.
    replayed = toolset.provision_fleet_attempt_workspaces()
    assert replayed[role].attempt_id == retry_attempt.attempt_id
    assert toolset.read_fleet_workspace_head() == head

    release = create_attempt_worktree_release(
        assignment,
        first_attempt,
        controller_state="SUPERSEDED",
        controller_state_ref="f" * 64,
    )
    toolset.cleanup_released_fleet_attempt_workspace(release)
    assert not original.worktree_path.exists()
    assert original.attempt_id not in toolset.settled_fleet_attempt_receipts()


def test_fleet_rebind_observer_failure_does_not_switch_or_orphan_candidate(monkeypatch, tmp_path: Path) -> None:
    root, _, _head, bindings, toolset, workspaces = _bound_real_fleet_toolset(
        monkeypatch,
        tmp_path,
        install_snapshot_observer=False,
    )
    role = WORKER_ROLES[0]
    assignment = bindings.assignments_by_role[role]
    retry_attempt = create_worker_attempt(assignment, attempt_sequence=2)
    toolset.set_fleet_attempt_workspace_snapshot_observer(
        lambda _snapshot: (_ for _ in ()).throw(RuntimeError("store unavailable"))
    )

    with pytest.raises(RuntimeError, match="store unavailable"):
        toolset.rebind_fleet_attempt_workspace(role, retry_attempt)

    candidate = fleet_attempt_worktree_path(assignment.workspace_id, retry_attempt.attempt_id, root)
    assert not candidate.exists()
    assert toolset._active_fleet_attempts_by_role[role].attempt_id == workspaces[role].attempt_id


def test_fleet_rebind_snapshot_observer_is_immutable_after_install(monkeypatch, tmp_path: Path) -> None:
    _root, _repo, _head, _bindings, toolset, _workspaces = _bound_real_fleet_toolset(monkeypatch, tmp_path)

    with pytest.raises(FleetContractError, match="immutable"):
        toolset.set_fleet_attempt_workspace_snapshot_observer(lambda _snapshot: None)
