from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# Single source of truth: the live sovereign backend. backend/app.py was
# deliberately removed; contracts must pin the production implementation only.
PRODUCTION_APP = ROOT / "scripts" / "sovereign-backend" / "app.py"
APP_SOURCES = (PRODUCTION_APP,)


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


def test_route_health_ok_is_derived_from_verified_evidence():
    # New truth: "ok" is derived from the provider-aware verification result
    # (bool(result.get("ok"))), never from a literal green constant.
    expected = ast.dump(
        ast.parse('bool(result.get("ok"))', mode="eval").body,
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

        # No literal green: "ok" is never hard-coded True anywhere in the
        # function, and the response derives ok/health from the evidence.
        assert '"ok": True' not in function_source
        assert '"ok": bool(result.get("ok"))' in function_source
        assert '"health": result.get("health") or "degraded"' in function_source

        # Degraded/blocked routes keep explicit blockers instead of a green
        # state: every health value is conditional on verification evidence.
        assert function_source.count('"health": "ready" if verified else') >= 2
        assert '"blocker": "unsupported_llm_transport"' in function_source
        assert '"blocker": "legacy_litellm_replaced_by_openrouter"' in function_source


def test_route_health_function_exists_in_single_production_source():
    # Single source of truth: the removed backend/app.py must stay absent and
    # the healthcheck contract lives in the production backend only.
    assert not (ROOT / "backend" / "app.py").exists()
    assert ast.dump(
        _function(PRODUCTION_APP, "admin_llm_route_healthcheck"),
        include_attributes=False,
    )
