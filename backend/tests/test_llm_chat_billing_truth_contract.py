from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_SOURCES = (
    ROOT / "backend" / "app.py",
    ROOT / "scripts" / "sovereign-backend" / "app.py",
)
HELPERS = {
    "_llm_usage_credit_cost",
    "_estimate_llm_request_tokens",
    "_resolve_enabled_llm_route",
}


def _load_helpers(path: Path, *, active_count: int = 1, restored_route=None):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    selected = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name in HELPERS
    ]
    assert {node.name for node in selected} == HELPERS

    calls: list[tuple[str, tuple | None]] = []
    first_route = None
    reconciles: list[bool] = []

    def query(sql: str, params=None, *, one=False, write=False):
        nonlocal first_route
        normalized = " ".join(sql.split())
        calls.append((normalized, params))
        assert write is False
        if "FROM llm_routes" in normalized and "disabled=false AND" in normalized:
            result = first_route
            first_route = restored_route
            return result
        if normalized.startswith("SELECT COUNT(*)::integer AS count FROM llm_routes"):
            return {"count": active_count}
        raise AssertionError(f"Unexpected SQL: {normalized}")

    def reconcile():
        reconciles.append(True)
        return (1, "")

    namespace = {
        "_json": json,
        "query": query,
        "_reconcile_worker_routes_if_empty": reconcile,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
    return namespace, calls, reconciles, source


def _function_ast(path: Path, name: str) -> str:
    module = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        item for item in module.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.dump(node, include_attributes=False)


def test_credit_cost_and_request_estimate_are_deterministic():
    messages = [{"role": "user", "content": "Hallo Runtime"}]
    for path in APP_SOURCES:
        namespace, _calls, _reconciles, _source = _load_helpers(path)
        cost = namespace["_llm_usage_credit_cost"]
        estimate = namespace["_estimate_llm_request_tokens"]

        assert cost(0.001, 1024) == 1
        assert cost(1.0, 1001) == 2
        assert cost(-5, 1000) == 1
        expected_input = max(
            1,
            (len(json.dumps(messages, ensure_ascii=False, separators=(",", ":"))) + 3) // 4,
        )
        assert estimate(messages, 250) == expected_input + 250


def test_direct_chat_cannot_resolve_unlisted_or_disabled_model():
    for path in APP_SOURCES:
        namespace, calls, reconciles, _source = _load_helpers(path, active_count=3)
        route = namespace["_resolve_enabled_llm_route"]("@cf/unlisted/model")

        assert route is None
        assert reconciles == []
        route_query = calls[0][0]
        assert "WHERE disabled=false AND (model_id=%s OR id::text=%s)" in route_query


def test_empty_catalog_may_resolve_only_after_real_reconciliation():
    restored = {
        "id": "route-1",
        "model_id": "@cf/meta/model",
        "provider": "cloudflare",
        "credits_per_unit": 0.001,
    }
    for path in APP_SOURCES:
        namespace, calls, reconciles, _source = _load_helpers(
            path,
            active_count=0,
            restored_route=restored,
        )
        route = namespace["_resolve_enabled_llm_route"]("@cf/meta/model")

        assert route == restored
        assert reconciles == [True]
        assert sum("disabled=false AND" in sql for sql, _params in calls) == 2


def test_chat_reserves_credits_before_provider_and_refunds_failures():
    for path in APP_SOURCES:
        source = path.read_text(encoding="utf-8")
        start = source.index("def public_llm_chat():")
        end = source.index("\n\nif __name__ == \"__main__\":", start)
        route_source = source[start:end]

        assert "route = _resolve_enabled_llm_route(model)" in route_source
        assert '"blocker": "llm_route_not_enabled"' in route_source
        assert "consume_step_up_approval(" in route_source
        assert "balance = _apply_credit_delta(" in route_source
        assert "fetch_worker_ai(" in route_source
        assert route_source.index("balance = _apply_credit_delta(") < route_source.index("fetch_worker_ai(")
        assert route_source.count("_refund_reserved_llm_credits(") >= 2
        assert '"blocker": "llm_credit_refund_failed"' in route_source
        assert '"chargeBasis": "reserved_request_estimate"' in route_source


def test_separate_deduct_endpoint_uses_same_cost_formula():
    for path in APP_SOURCES:
        source = path.read_text(encoding="utf-8")
        assert "amount = _llm_usage_credit_cost(" in source
        assert "float(route[\"credits_per_unit\"]),\n                token_count," in source


def test_live_and_deploy_billing_helpers_are_semantically_identical():
    names = HELPERS | {"_refund_reserved_llm_credits", "public_llm_chat"}
    for name in names:
        assert _function_ast(APP_SOURCES[0], name) == _function_ast(APP_SOURCES[1], name)
