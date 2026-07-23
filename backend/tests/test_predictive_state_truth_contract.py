from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend" / "agent_runtime"
DEPLOY = ROOT / "scripts" / "sovereign-backend" / "agent_runtime"


class _Cursor:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str, params: tuple):
        self.calls.append((sql, params))


class _Connection:
    def __init__(self):
        self.cursor_value = _Cursor()
        self.commits = 0

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1


def _load_update_state(path: Path):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    selected = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_json", "update_agent_job_state"}
    ]
    namespace = {
        "Any": Any,
        "Sequence": Sequence,
        "json": json,
        "sanitize_agent_text": lambda value, limit: str(value)[:limit],
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["update_agent_job_state"], source


def test_state_store_can_explicitly_clear_a_stale_blocker():
    for path in (BACKEND / "job_store.py", DEPLOY / "job_store.py"):
        update_state, _source = _load_update_state(path)
        conn = _Connection()

        update_state(
            conn,
            job_id="agent-1",
            status="validating",
            clear_blocker=True,
        )

        sql, params = conn.cursor_value.calls[0]
        assert "WHEN input.clear_blocker THEN NULL" in sql
        assert "ELSE COALESCE(input.blocker, sovereign_agent_jobs.blocker)" in sql
        assert params[-3:] == (True, None, "agent-1")
        assert conn.commits == 1


def test_state_store_preserves_explicit_current_blocker_when_not_clearing():
    for path in (BACKEND / "job_store.py", DEPLOY / "job_store.py"):
        update_state, _source = _load_update_state(path)
        conn = _Connection()

        update_state(
            conn,
            job_id="agent-2",
            status="running",
            blocker="No test summary - Draft PR preparation requires test evidence",
        )

        _sql, params = conn.cursor_value.calls[0]
        assert params[-3:] == (
            False,
            "No test summary - Draft PR preparation requires test evidence",
            "agent-2",
        )


def test_predictive_tool_transition_persists_gate_reason_and_clears_only_on_pass():
    for path in (BACKEND / "tool_events.py", DEPLOY / "tool_events.py"):
        source = path.read_text(encoding="utf-8")
        assert "next_blocker = None if gate.passed else gate.reason" in source
        assert "blocker=next_blocker" in source
        assert "clear_blocker=gate.passed" in source


def test_cleanup_explicitly_clears_historical_blocker():
    for path in (BACKEND / "routes.py", DEPLOY / "routes.py"):
        source = path.read_text(encoding="utf-8")
        assert 'status="cleaned",\n                clear_blocker=True' in source


def test_live_and_deploy_predictive_modules_remain_exact_mirrors():
    for name in ("job_store.py", "tool_events.py", "routes.py"):
        assert (BACKEND / name).read_text(encoding="utf-8") == (
            DEPLOY / name
        ).read_text(encoding="utf-8")
