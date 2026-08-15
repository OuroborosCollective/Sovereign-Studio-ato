"""Mirror parity test for the operator projection package (Issue #1174).

The canonical implementation lives under
``backend/agent_runtime/operator_projection`` and must remain byte-identical to
the deployment mirror under
``scripts/sovereign-backend/agent_runtime/operator_projection``. The strict
command-request schema must likewise match its mirror copy under both
``contracts`` trees.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL_PACKAGE = _REPO_ROOT / "backend" / "agent_runtime" / "operator_projection"
_PRODUCTION_PACKAGE = _REPO_ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "operator_projection"
_CANONICAL_SCHEMA = (
    _REPO_ROOT / "backend" / "agent_runtime" / "contracts" / "operator_command_request.v1.schema.json"
)
_PRODUCTION_SCHEMA = (
    _REPO_ROOT
    / "scripts"
    / "sovereign-backend"
    / "agent_runtime"
    / "contracts"
    / "operator_command_request.v1.schema.json"
)

_PACKAGE_FILES = ("__init__.py", "read_models.py", "command_gateway.py")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_operator_projection_package_mirror_byte_identical() -> None:
    missing = []
    mismatches = []
    for relative in _PACKAGE_FILES:
        canonical = _CANONICAL_PACKAGE / relative
        production = _PRODUCTION_PACKAGE / relative
        if not canonical.is_file():
            missing.append(str(canonical))
            continue
        if not production.is_file():
            missing.append(str(production))
            continue
        if _sha256(canonical) != _sha256(production):
            mismatches.append(relative)
    assert not missing, f"missing mirror files: {missing}"
    assert not mismatches, f"byte-drift between canonical and mirror: {mismatches}"


def test_operator_command_request_schema_mirror_byte_identical() -> None:
    assert _CANONICAL_SCHEMA.is_file(), "canonical schema missing"
    assert _PRODUCTION_SCHEMA.is_file(), "production mirror schema missing"
    assert _sha256(_CANONICAL_SCHEMA) == _sha256(
        _PRODUCTION_SCHEMA
    ), "operator_command_request.v1.schema.json byte-drift between canonical and mirror"
