from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
APP_SOURCES = (
    ROOT / "backend" / "app.py",
    ROOT / "scripts" / "sovereign-backend" / "app.py",
)
TARGET_FUNCTIONS = {
    "_worker_route_fields",
    "_reconcile_worker_routes_if_empty",
}


def _load_reconcile_runtime(path: Path, *, models: list[dict] | None = None, error: str = ""):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    selected = [
        node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in TARGET_FUNCTIONS
    ]
    assert {node.name for node in selected} == TARGET_FUNCTIONS

    rows: dict[str, dict] = {}
    audits: list[tuple[str, object, dict]] = []
    fetch_calls: list[str] = []

    def query(sql: str, params=None, *, one=False, write=False):
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT COUNT(*)::integer AS count FROM llm_routes"):
            return {"count": sum(1 for row in rows.values() if not row["disabled"])}
        if normalized.startswith("INSERT INTO llm_routes"):
            assert write is True
            model_id, model_name, base_url, priority = params
            rows[model_id] = {
                "model_id": model_id,
                "model_name": model_name,
                "base_url": base_url,
                "priority": priority,
                "disabled": False,
            }
            return None
        raise AssertionError(f"Unexpected SQL: {normalized}")

    class Response:
        ok = True
        status_code = 200
        content = b"{}"

        def json(self):
            return {"data": list(models or [])}

    def fetch_worker_ai(path: str):
        fetch_calls.append(path)
        return (None, error) if error else (Response(), "")

    def audit(action: str, target_id, changes: dict):
        audits.append((action, target_id, changes))

    namespace = {
        "query": query,
        "fetch_worker_ai": fetch_worker_ai,
        "WORKER_AI_BASE": "https://worker.example.invalid",
        "audit": audit,
    }
    extracted = ast.Module(body=selected, type_ignores=[])
    exec(compile(extracted, str(path), "exec"), namespace)
    return SimpleNamespace(
        reconcile=namespace["_reconcile_worker_routes_if_empty"],
        fields=namespace["_worker_route_fields"],
        rows=rows,
        audits=audits,
        fetch_calls=fetch_calls,
        source=source,
    )


def test_empty_catalog_is_rebuilt_from_real_worker_models_in_both_backend_sources():
    models = [
        {"id": "@cf/meta/llama-3.1-8b-instruct"},
        {"id": "@cf/qwen/qwen2.5-32b-instruct"},
        {"id": "@cf/meta/llama-3.1-8b-instruct"},
        {"id": ""},
    ]

    for path in APP_SOURCES:
        runtime = _load_reconcile_runtime(path, models=models)
        restored, error = runtime.reconcile()

        assert error == ""
        assert restored == 2
        assert runtime.fetch_calls == ["v1/models"]
        assert set(runtime.rows) == {
            "@cf/meta/llama-3.1-8b-instruct",
            "@cf/qwen/qwen2.5-32b-instruct",
        }
        assert runtime.rows["@cf/meta/llama-3.1-8b-instruct"]["priority"] == 50
        assert runtime.rows["@cf/qwen/qwen2.5-32b-instruct"]["priority"] == 100
        assert runtime.rows["@cf/meta/llama-3.1-8b-instruct"]["model_name"] == "meta-llama-3.1-8b-instruct"
        assert runtime.audits == [
            (
                "system_worker_ai_route_reconcile",
                None,
                {"reason": "empty_route_catalog", "restored": 2, "workerModels": 2},
            )
        ]


def test_existing_active_catalog_does_not_call_worker_or_mutate_routes():
    for path in APP_SOURCES:
        runtime = _load_reconcile_runtime(path, models=[{"id": "@cf/meta/model"}])
        runtime.rows["existing"] = {
            "model_id": "existing",
            "model_name": "Existing",
            "base_url": "https://existing.invalid",
            "priority": 1,
            "disabled": False,
        }

        restored, error = runtime.reconcile()

        assert (restored, error) == (1, "")
        assert runtime.fetch_calls == []
        assert runtime.audits == []
        assert list(runtime.rows) == ["existing"]


def test_worker_failure_remains_an_explicit_blocker_without_fake_routes():
    for path in APP_SOURCES:
        runtime = _load_reconcile_runtime(path, error="upstream unavailable")

        restored, error = runtime.reconcile()

        assert restored == 0
        assert error == "upstream unavailable"
        assert runtime.rows == {}
        assert runtime.audits == []


def test_auto_route_and_health_contract_reject_empty_catalog_green_state():
    for path in APP_SOURCES:
        source = path.read_text(encoding="utf-8")
        assert "_restored_count, reconcile_error = _reconcile_worker_routes_if_empty()" in source
        assert '"blocker": "llm_routes_empty"' in source
        assert '"blocker": "llm_routes_empty_after_reconcile"' in source
        assert "routes_healthy = active_routes > 0" in source
        assert '"status": "healthy" if routes_healthy else "degraded"' in source
        assert '"blocker": None if routes_healthy else "llm_routes_empty"' in source
        assert "ON CONFLICT (model_id) DO UPDATE SET" in source
