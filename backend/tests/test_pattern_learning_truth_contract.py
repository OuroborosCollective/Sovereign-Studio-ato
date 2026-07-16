from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    ROOT / "backend" / "agent_runtime" / "routes.py",
    ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "routes.py",
)


def _load_state_function(path: Path):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    node = next(
        item
        for item in module.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_pattern_learning_response_state"
    )
    namespace: dict[str, object] = {"Any": object}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_pattern_learning_response_state"], source


def test_accepted_pattern_is_success_only_after_pgvector_storage():
    for path in SOURCES:
        state, _source = _load_state_function(path)
        assert state(SimpleNamespace(allowed=True), {"stored": True}) == (True, 200, None)
        assert state(
            SimpleNamespace(allowed=True),
            {"stored": False, "reason": "embedding_unavailable"},
        ) == (False, 503, "embedding_unavailable")


def test_blocked_candidate_remains_client_rejection_not_runtime_success():
    for path in SOURCES:
        state, _source = _load_state_function(path)
        assert state(SimpleNamespace(allowed=False), {"stored": False}) == (
            False,
            400,
            "pattern_not_accepted",
        )


def test_pattern_route_projects_combined_candidate_and_vector_truth():
    for path in SOURCES:
        _state, source = _load_state_function(path)
        assert "response_ok, status_code, blocker = _pattern_learning_response_state(" in source
        assert '"ok": response_ok' in source
        assert '"vectorMemory": vector_memory' in source
        assert '"blocker": blocker' in source
        assert "), status_code" in source


def test_live_and_deploy_route_modules_remain_exact_mirrors():
    left = SOURCES[0].read_text(encoding="utf-8")
    right = SOURCES[1].read_text(encoding="utf-8")
    assert left == right
