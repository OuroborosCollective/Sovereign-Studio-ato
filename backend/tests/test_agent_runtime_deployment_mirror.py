"""Deployment-mirror parity guard for the whole agent_runtime tree.

The canonical backend agent code lives under ``backend/agent_runtime/`` and the
deployment mirror lives under ``scripts/sovereign-backend/agent_runtime/``.
Repository rules require both paths to remain byte-equivalent and tests to
verify parity. Individual modules already have dedicated mirror tests (for
example ``test_scann_production_mirror.py`` for the retrieval package); this
test guards the entire tree so any module — including
``predictive/signal_pipeline.py`` — cannot drift silently.
"""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL_ROOT = _REPO_ROOT / "backend" / "agent_runtime"
_PRODUCTION_ROOT = _REPO_ROOT / "scripts" / "sovereign-backend" / "agent_runtime"


def _python_files(root: Path) -> dict[str, Path]:
    return {
        str(path.relative_to(root)): path
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_mirror_file_sets_match() -> None:
    canonical = _python_files(_CANONICAL_ROOT)
    production = _python_files(_PRODUCTION_ROOT)
    missing = sorted(set(canonical) - set(production))
    extra = sorted(set(production) - set(canonical))
    assert not missing, f"missing production mirrors: {missing}"
    assert not extra, f"unexpected production-only files: {extra}"


def test_mirror_files_are_byte_identical() -> None:
    canonical = _python_files(_CANONICAL_ROOT)
    production = _python_files(_PRODUCTION_ROOT)
    mismatched = [
        relative
        for relative in canonical
        if relative in production
        and _sha256(canonical[relative]) != _sha256(production[relative])
    ]
    if not mismatched:
        return
    relative = mismatched[0]
    canonical_text = canonical[relative].read_text(encoding="utf-8")
    production_text = production[relative].read_text(encoding="utf-8")
    diff = "".join(
        difflib.unified_diff(
            production_text.splitlines(keepends=True),
            canonical_text.splitlines(keepends=True),
            fromfile=str(production[relative]),
            tofile=str(canonical[relative]),
        )
    )
    raise AssertionError(
        f"mirror drift in {mismatched}\nfirst mismatch {relative}:\n{diff[:12000]}"
    )


def test_all_production_mirror_modules_compile() -> None:
    for path in sorted(_python_files(_PRODUCTION_ROOT).values()):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
