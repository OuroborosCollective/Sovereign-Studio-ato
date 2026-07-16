from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
APP_SOURCES = (
    ROOT / "backend" / "app.py",
    ROOT / "scripts" / "sovereign-backend" / "app.py",
)


def _function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    node = next(
        item
        for item in module.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


def _load_worker_sync(path: Path, *, models: list[dict], fail_model_id: str = ""):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    node = next(
        item
        for item in module.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_sync_worker_routes_from_live_source"
    )

    rows = {
        "@cf/meta/existing": {"disabled": False},
        "@cf/meta/stale": {"disabled": False},
    }
    audits: list[dict] = []

    class Response:
        ok = True
        status_code = 200
        content = b"{}"

        def json(self):
            return {"data": list(models)}

    class Cursor:
        result = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql: str, params=None):
            normalized = " ".join(sql.split())
            if normalized.startswith("SELECT pg_advisory_xact_lock"):
                self.result = []
                return
            if normalized.startswith("SELECT model_id FROM llm_routes"):
                self.result = [{"model_id": model_id} for model_id in rows]
                return
            if normalized.startswith("INSERT INTO llm_routes"):
                model_id = params[0]
                if model_id == fail_model_id:
                    raise RuntimeError("forced model failure")
                rows[model_id] = {"disabled": False}
                self.result = []
                return
            if normalized.startswith("UPDATE llm_routes SET disabled=true"):
                active_ids = set(params[0])
                disabled = []
                for model_id, row in rows.items():
                    if model_id not in active_ids and not row["disabled"]:
                        row["disabled"] = True
                        disabled.append({"model_id": model_id})
                self.result = disabled
                return
            if normalized.startswith("INSERT INTO audit_log"):
                audits.append(dict(params[0]))
                self.result = []
                return
            raise AssertionError(f"Unexpected SQL: {normalized}")

        def fetchall(self):
            return list(self.result or [])

    class Connection:
        def __init__(self):
            self.before_rows = {key: dict(value) for key, value in rows.items()}
            self.before_audits = list(audits)
            self.commits = 0
            self.rollbacks = 0

        def cursor(self, cursor_factory=None):
            return Cursor()

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1
            rows.clear()
            rows.update({key: dict(value) for key, value in self.before_rows.items()})
            audits[:] = self.before_audits

    class Pool:
        def __init__(self):
            self.connection = Connection()
            self.returned = 0

        def getconn(self):
            return self.connection

        def putconn(self, conn):
            assert conn is self.connection
            self.returned += 1

    pool = Pool()
    namespace = {
        "fetch_worker_ai": lambda _path: (Response(), ""),
        "get_pool": lambda: pool,
        "_worker_route_fields": lambda model_id: (model_id.replace("@cf/", ""), 50),
        "WORKER_AI_BASE": "https://worker.example.invalid",
        "psycopg2": SimpleNamespace(
            extras=SimpleNamespace(
                RealDictCursor=object,
                Json=lambda value: value,
            )
        ),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["_sync_worker_routes_from_live_source"], rows, audits, pool


def test_worker_sync_commits_one_complete_catalog_and_disables_stale_routes():
    live_models = [
        {"id": "@cf/meta/existing"},
        {"id": "@cf/qwen/new"},
        {"id": "@cf/qwen/new"},
        {"id": ""},
    ]
    for path in APP_SOURCES:
        sync, rows, audits, pool = _load_worker_sync(path, models=live_models)

        result = sync()

        assert result == {
            "ok": True,
            "totalModels": 2,
            "created": 1,
            "updated": 1,
            "disabled": 1,
        }
        assert rows["@cf/meta/existing"]["disabled"] is False
        assert rows["@cf/qwen/new"]["disabled"] is False
        assert rows["@cf/meta/stale"]["disabled"] is True
        assert audits == [result]
        assert pool.connection.commits == 1
        assert pool.connection.rollbacks == 0
        assert pool.returned == 1


def test_worker_sync_mid_batch_failure_rolls_back_rows_and_audit():
    live_models = [
        {"id": "@cf/meta/existing"},
        {"id": "@cf/qwen/failing"},
    ]
    for path in APP_SOURCES:
        sync, rows, audits, pool = _load_worker_sync(
            path,
            models=live_models,
            fail_model_id="@cf/qwen/failing",
        )

        try:
            sync()
            raise AssertionError("Expected sync failure")
        except RuntimeError as exc:
            assert str(exc) == "Worker route sync failed (RuntimeError)"

        assert rows == {
            "@cf/meta/existing": {"disabled": False},
            "@cf/meta/stale": {"disabled": False},
        }
        assert audits == []
        assert pool.connection.commits == 0
        assert pool.connection.rollbacks == 1
        assert pool.returned == 1


def test_gateway_sync_uses_only_atomic_worker_helper_and_reports_blockers():
    for path in APP_SOURCES:
        source = _function_source(path, "admin_llm_gateway_sync")
        assert 'results["workerAiSync"] = _sync_worker_routes_from_live_source()' in source
        assert 'results["errors"].append(f"{provider_id}: {message}")' in source
        assert 'results["errors"].append(f"cloudflare: {str(e)}")' in source
        assert 'sync_ok = not results["errors"]' in source
        assert '"ok": sync_ok' in source
        assert '200 if sync_ok else 502' in source
        assert 'w_c, w_u = 0, 0' not in source
        assert 'except: pass' not in source


def test_live_and_deploy_sync_functions_are_semantically_identical():
    for name in ("_sync_worker_routes_from_live_source", "admin_llm_gateway_sync"):
        left = ast.dump(
            ast.parse(_function_source(APP_SOURCES[0], name)),
            include_attributes=False,
        )
        right = ast.dump(
            ast.parse(_function_source(APP_SOURCES[1], name)),
            include_attributes=False,
        )
        assert left == right
