from __future__ import annotations

import ast
import difflib
import hashlib
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL_ROOT = _REPO_ROOT / "backend" / "agent_runtime" / "retrieval"
_PRODUCTION_ROOT = _REPO_ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "retrieval"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _SemanticNormalizer(ast.NodeTransformer):
    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.AST:
        node = self.generic_visit(node)
        if all(isinstance(value, ast.Constant) and isinstance(value.value, str) for value in node.values):
            return ast.copy_location(
                ast.Constant(value="".join(value.value for value in node.values)),
                node,
            )
        return node


def _without_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            del body[0]
    return ast.fix_missing_locations(_SemanticNormalizer().visit(tree))


def _semantic_ast(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return ast.dump(_without_docstrings(tree), annotate_fields=True, include_attributes=False)


def test_byte_identical_package_and_snapshot_export_mirrors() -> None:
    for relative in ("__init__.py", "scann_snapshot_export.py"):
        canonical = _CANONICAL_ROOT / relative
        production = _PRODUCTION_ROOT / relative
        assert production.is_file(), f"missing production mirror: {production}"
        assert _sha256(canonical) == _sha256(production), relative


def test_manifest_mirror_is_byte_identical() -> None:
    canonical = _CANONICAL_ROOT / "scann_manifest.py"
    production = _PRODUCTION_ROOT / "scann_manifest.py"
    assert production.is_file(), f"missing production mirror: {production}"
    canonical_text = canonical.read_text(encoding="utf-8")
    production_text = production.read_text(encoding="utf-8")
    if canonical_text != production_text:
        diff = "".join(
            difflib.unified_diff(
                production_text.splitlines(keepends=True),
                canonical_text.splitlines(keepends=True),
                fromfile=str(production),
                tofile=str(canonical),
            )
        )
        raise AssertionError(diff[:12000])


def test_all_production_retrieval_modules_compile() -> None:
    for path in sorted(_PRODUCTION_ROOT.glob("*.py")):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
