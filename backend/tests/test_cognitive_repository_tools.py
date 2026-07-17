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
    WRITE_REPOSITORY_TOOL_NAME,
    _path_in_role_scope,
    _redact,
    _safe_path,
)
from agent_runtime.cognitive_swarm_manifest import WORKER_ROLES
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


def test_six_worker_roles_have_explicit_work_and_path_boundaries() -> None:
    assert tuple(ROLE_WORK_PACKAGES) == tuple(WORKER_ROLES)
    assert tuple(ROLE_PATH_PREFIXES) == tuple(WORKER_ROLES)
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
    assert WRITE_REPOSITORY_TOOL_NAME not in read_only.allowed_tool_names("predictive_qa")
    assert WRITE_REPOSITORY_TOOL_NAME in mutating.allowed_tool_names("predictive_qa")


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
