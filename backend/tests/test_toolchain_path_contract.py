"""Dependency-free contract tests for the exact production path validator."""

from __future__ import annotations

import ast
from pathlib import Path
import urllib.parse

import pytest


ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "scripts" / "sovereign-backend" / "app.py"


def _production_validator():
    source = APP_PATH.read_text("utf-8")
    tree = ast.parse(source, filename=str(APP_PATH))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_tc_validate_path"
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"urllib": type("Urllib", (), {"parse": urllib.parse})}
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace["_tc_validate_path"]


@pytest.mark.parametrize(
    "candidate",
    [
        "../secret.txt",
        "docs/../secret.txt",
        "%2e%2e/%2e%2e/other-owner/other-repo/contents/file",
        "docs/%2E%2E/secret.txt",
        "docs%5c..%5csecret.txt",
        "/etc/passwd",
        "%2Fetc/passwd",
        "docs/%00secret.txt",
    ],
)
def test_production_validator_rejects_unsafe_paths(candidate: str) -> None:
    with pytest.raises(PermissionError):
        _production_validator()(candidate)


def test_production_validator_preserves_valid_double_dot_filename() -> None:
    validate = _production_validator()
    assert validate("docs/v1..v2.md") == "docs/v1..v2.md"
    assert validate("docs/%E2%9C%93.md") == "docs/✓.md"
    assert validate("", allow_empty=True) == ""
