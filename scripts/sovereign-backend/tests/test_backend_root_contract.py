from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app.py"


def test_backend_root_route_redirects_to_canonical_admin_surface() -> None:
    source = APP.read_text("utf-8")
    tree = ast.parse(source)
    root_function = None
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "backend_root":
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "app"
                and func.attr == "route"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and decorator.args[0].value == "/"
            ):
                root_function = node
                break
    assert root_function is not None
    redirects = [
        node for node in ast.walk(root_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "redirect"
    ]
    assert len(redirects) == 1
    call = redirects[0]
    assert isinstance(call.args[0], ast.Constant)
    assert call.args[0].value == "/admin/"
    code_keyword = next((item for item in call.keywords if item.arg == "code"), None)
    assert code_keyword is not None
    assert isinstance(code_keyword.value, ast.Constant)
    assert code_keyword.value.value == 302
