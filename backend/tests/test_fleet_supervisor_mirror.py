"""Mirror parity test for the fleet supervisor contract.

The canonical backend implementation lives under
``backend/agent_runtime/fleet_supervisor.py`` and must remain byte-identical to the
deployment mirror under ``scripts/sovereign-backend/agent_runtime/fleet_supervisor.py``
(see AGENTS.md mirror ownership rules).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL = _REPO_ROOT / "backend" / "agent_runtime" / "fleet_supervisor.py"
_PRODUCTION = _REPO_ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "fleet_supervisor.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fleet_supervisor_mirror_byte_identical() -> None:
    assert _CANONICAL.is_file(), f"canonical fleet supervisor missing: {_CANONICAL}"
    assert _PRODUCTION.is_file(), f"mirror fleet supervisor missing: {_PRODUCTION}"
    assert _sha256(_CANONICAL) == _sha256(_PRODUCTION), (
        "fleet_supervisor.py mirror drift: canonical and mirror must stay byte-identical"
    )
