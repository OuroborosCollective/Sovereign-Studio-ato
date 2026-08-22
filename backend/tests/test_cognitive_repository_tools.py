import hashlib
from pathlib import Path
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from agent_runtime.cognitive_repository_tools import (
    BoundRepositoryToolset,
    READ_REPOSITORY_TOOL_NAMES,
    ROLE_PATH_PREFIXES,
    ROLE_WORK_PACKAGES,
    WRITE_REPOSITORY_TOOL_NAMES,
    _path_in_role_scope,
    _redact,
    _safe_path,
    build_repository_fleet_bindings,
)
from agent_runtime.cognitive_swarm_manifest import WORKER_ROLES
from agent_runtime.fleet_supervisor import FleetContractError
from agent_runtime.job_store import update_agent_job_state
from agent_runtime.tools.file_tool import FileReadTool


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
