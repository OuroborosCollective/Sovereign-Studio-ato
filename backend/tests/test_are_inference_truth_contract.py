from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    ROOT / "backend" / "are_inference.py",
    ROOT / "scripts" / "sovereign-backend" / "are_inference.py",
)


def _load_quarantine_status(path: Path):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    node = next(
        item
        for item in module.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_quarantine_response_status"
    )
    namespace: dict[str, object] = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_quarantine_response_status"], source


def test_quarantine_reports_created_only_for_new_persisted_candidate():
    for path in SOURCES:
        status, _source = _load_quarantine_status(path)
        assert status({"duplicate": False}) == 201
        assert status({"duplicate": True}) == 200


def test_quarantine_promotion_requires_causally_bound_accepted_pattern_for_same_user():
    for path in SOURCES:
        _status, source = _load_quarantine_status(path)
        assert "FROM are_learning_quarantine q" in source
        assert "JOIN sovereign_agent_pattern_vectors v" in source
        assert "v.candidate_id=c.candidate_id AND v.user_id=c.user_id" in source
        assert "q.status='pending'" in source
        assert "c.decision='accepted'" in source
        assert "c.remote_memory_allowed=true" in source
        assert "c.payload->>'missionSha256'=BTRIM(q.prompt_sha256)" in source


def test_embedding_repair_persists_actual_batch_model_truth():
    for path in SOURCES:
        _status, source = _load_quarantine_status(path)
        assert '(vector_literal(vector), batch.model, row["id"], user_id)' in source
        assert 'json.dumps({"embeddingModel": batch.model, "repairProvider": batch.provider})' in source
        assert '"embeddingModel": batch.model' in source


def test_quarantine_route_projects_duplicate_truth_without_fake_creation():
    for path in SOURCES:
        _status, source = _load_quarantine_status(path)
        assert '"created": not result["duplicate"]' in source
        assert "_quarantine_response_status(result)" in source


def test_live_and_deploy_inference_modules_remain_exact_mirrors():
    assert SOURCES[0].read_text(encoding="utf-8") == SOURCES[1].read_text(encoding="utf-8")
