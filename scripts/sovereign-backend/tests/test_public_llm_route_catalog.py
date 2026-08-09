from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app.py"


def _function(name: str) -> ast.FunctionDef:
    module = ast.parse(APP.read_text(encoding="utf-8"))
    return next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _load_function(name: str, namespace: dict) -> dict:
    node = _function(name)
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(module, str(APP), "exec"), namespace)
    return namespace


def test_runtime_selectability_requires_a_verified_executor_route() -> None:
    namespace = _load_function(
        "_is_runtime_selectable_llm_route",
        {
            "route_is_verified_free": lambda route: bool(route.get("verifiedFree")),
            "route_is_verified_paid": lambda route: bool(route.get("verifiedPaid")),
        },
    )
    selectable = namespace["_is_runtime_selectable_llm_route"]

    assert selectable({"verifiedFree": True}) is True
    assert selectable({"verifiedPaid": True}) is True
    assert selectable({"verifiedFree": False, "verifiedPaid": False}) is False


def test_public_catalog_excludes_routes_the_executor_would_reject() -> None:
    source = APP.read_text(encoding="utf-8")
    catalog_sql = source[source.index("def public_llm_routes()"):source.index("def public_llm_route(")]
    assert "base_url, runtime_kind, tier, disabled, priority, config" in catalog_sql

    class FakeApp:
        @staticmethod
        def route(_path: str):
            return lambda function: function

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload
            self.headers: dict[str, str] = {}

    rows = [
        {"id": "stale", "selectable": False},
        {"id": "verified-free", "selectable": True},
    ]
    namespace = _load_function(
        "public_llm_routes",
        {
            "app": FakeApp(),
            "query": lambda *_args, **_kwargs: rows,
            "jsonify": lambda payload: payload,
            "make_response": FakeResponse,
            "_public_llm_route_payload": lambda route: {
                "id": route["id"],
                "enabled": True,
            },
            "_is_runtime_selectable_llm_route": lambda route: bool(route["selectable"]),
        },
    )

    response = namespace["public_llm_routes"]()

    assert response.payload["routes"] == [{"id": "verified-free", "enabled": True}]
    assert response.headers["Cache-Control"] == "no-store, max-age=0"


def test_chat_route_resolution_rejects_stale_enabled_rows() -> None:
    stale = {"id": "stale", "model_id": "old-model", "selectable": False}
    verified = {"id": "verified", "model_id": "new-model", "selectable": True}
    namespace = _load_function(
        "_resolve_enabled_llm_route",
        {
            "query": lambda *_args, **_kwargs: [stale],
            "_is_runtime_selectable_llm_route": lambda route: bool(route["selectable"]),
            "route_billing_policy": lambda route: {"billingCategory": "free"},
            "BillingPolicyError": ValueError,
        },
    )
    resolve = namespace["_resolve_enabled_llm_route"]

    assert resolve("old-model") is None
    namespace["query"] = lambda *_args, **_kwargs: [stale, verified]
    assert resolve("new-model") == verified
