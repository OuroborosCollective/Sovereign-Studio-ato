from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_SOURCES = (
    ROOT / "backend" / "app.py",
    ROOT / "scripts" / "sovereign-backend" / "app.py",
)


def _function(path: Path, name: str) -> ast.FunctionDef:
    module = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _route_health_ok_expression(path: Path) -> ast.expr:
    function = _function(path, "admin_llm_route_healthcheck")
    for node in ast.walk(function):
        if not isinstance(node, ast.Dict):
            continue
        keys = [key.value if isinstance(key, ast.Constant) else None for key in node.keys]
        if "ok" not in keys or "routeId" not in keys or "health" not in keys:
            continue
        return node.values[keys.index("ok")]
    raise AssertionError("Route health response dictionary not found")


def test_route_health_ok_is_derived_from_real_health_status():
    expected = ast.dump(
        ast.parse('health_status == "healthy"', mode="eval").body,
        include_attributes=False,
    )
    for path in APP_SOURCES:
        actual = ast.dump(_route_health_ok_expression(path), include_attributes=False)
        assert actual == expected


def test_degraded_route_cannot_share_a_literal_green_response():
    for path in APP_SOURCES:
        source = path.read_text(encoding="utf-8")
        function_start = source.index("def admin_llm_route_healthcheck")
        next_route = source.index("\n@app.route", function_start + 1)
        function_source = source[function_start:next_route]
        assert '"ok": True,\n        "routeId": rid' not in function_source
        assert '"ok": health_status == "healthy"' in function_source
        assert '"status": health_status' in function_source
        assert '"health": health_status' in function_source


def test_live_and_deploy_route_health_functions_are_semantically_identical():
    assert ast.dump(
        _function(APP_SOURCES[0], "admin_llm_route_healthcheck"),
        include_attributes=False,
    ) == ast.dump(
        _function(APP_SOURCES[1], "admin_llm_route_healthcheck"),
        include_attributes=False,
    )
