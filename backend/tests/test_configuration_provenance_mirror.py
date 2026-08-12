"""Mirror parity test for the configuration provenance package.

The canonical backend implementation lives under
``backend/agent_runtime/configuration`` and must remain byte-identical to the
deployment mirror under ``scripts/sovereign-backend/agent_runtime/configuration``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL_ROOT = _REPO_ROOT / "backend" / "agent_runtime" / "configuration"
_PRODUCTION_ROOT = _REPO_ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "configuration"

_FILES = (
    "__init__.py",
    "config_sources.py",
    "config_canonicalize.py",
    "resolver.py",
    "receipt.py",
    "runtime_binding.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_configuration_provenance_mirror_byte_identical() -> None:
    missing = []
    mismatches = []
    for relative in _FILES:
        canonical = _CANONICAL_ROOT / relative
        production = _PRODUCTION_ROOT / relative
        if not production.is_file():
            missing.append(str(production))
            continue
        if _sha256(canonical) != _sha256(production):
            mismatches.append(relative)
    assert not missing, f"missing production mirror files: {missing}"
    assert not mismatches, f"byte-drift between canonical and mirror: {mismatches}"
