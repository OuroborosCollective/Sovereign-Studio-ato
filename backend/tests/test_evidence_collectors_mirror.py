"""Mirror parity test for ``evidence_collectors.py``.

The canonical collector module lives under
``backend/agent_runtime/evidence_collectors.py`` and must remain byte-identical
to the deployment mirror under
``scripts/sovereign-backend/agent_runtime/evidence_collectors.py``.

Per the repository change rules, when mirror ownership applies both paths must
remain byte-equivalent and tests must verify parity. This test guards against a
patch landing on only one copy (the canonical or the mirror), which would
silently desync the deployment from repository truth.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL = _REPO_ROOT / "backend" / "agent_runtime" / "evidence_collectors.py"
_PRODUCTION = (
    _REPO_ROOT
    / "scripts"
    / "sovereign-backend"
    / "agent_runtime"
    / "evidence_collectors.py"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_evidence_collectors_mirror_byte_identical() -> None:
    assert _CANONICAL.is_file(), f"canonical module missing: {_CANONICAL}"
    assert _PRODUCTION.is_file(), f"production mirror missing: {_PRODUCTION}"
    assert _sha256(_CANONICAL) == _sha256(_PRODUCTION), (
        "byte-drift between canonical and mirror evidence_collectors.py"
    )
