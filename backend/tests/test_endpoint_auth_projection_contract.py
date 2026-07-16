from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SURFACES = (
    ROOT / "backend",
    ROOT / "scripts" / "sovereign-backend",
)


def _route_path(decorator: ast.expr) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    function = decorator.func
    if not isinstance(function, ast.Attribute) or function.attr != "route":
        return None
    if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
        return None
    value = decorator.args[0].value
    return value if isinstance(value, str) else None


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


def _protected_routes(root: Path):
    for path in sorted(root.rglob("*.py")):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            paths = [value for value in map(_route_path, node.decorator_list) if value]
            for route in paths:
                yield path, node, route


def test_user_and_inference_routes_require_authenticated_session():
    violations: list[str] = []
    for root in SURFACES:
        for path, node, route in _protected_routes(root):
            requires_session = (
                route.startswith("/api/user/")
                or route.startswith("/api/inference/")
                or route == "/api/llm/auto-route"
            )
            if requires_session and "require_session" not in _decorator_names(node):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{route}")
    assert violations == []


def test_admin_routes_require_admin_gate():
    violations: list[str] = []
    for root in SURFACES:
        for path, node, route in _protected_routes(root):
            if route.startswith("/api/admin/") and "require_admin" not in _decorator_names(node):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{route}")
    assert violations == []


def test_live_and_deploy_endpoint_modules_are_mirrored():
    mirrored = (
        "are_inference.py",
        "agent_runtime/routes.py",
        "agent_runtime/cognitive_swarm_routes.py",
    )
    for relative in mirrored:
        assert (SURFACES[0] / relative).read_text(encoding="utf-8") == (
            SURFACES[1] / relative
        ).read_text(encoding="utf-8")
