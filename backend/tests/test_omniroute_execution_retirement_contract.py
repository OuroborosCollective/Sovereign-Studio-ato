from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from llm_transport import (  # noqa: E402
    FREELLM_BASE_URL,
    FREELLM_BASE_URLS,
    FREELLM_EXECUTION_BASE_URLS,
    FREELLMPOOL_BASE_URL,
    route_is_direct_freellm,
)


def _route(base_url: str) -> dict[str, object]:
    return {
        "provider": "freellm",
        "runtime_kind": "freellm",
        "base_url": base_url,
        "disabled": False,
        "config": {
            "transport": "freellm",
            "executionProfile": "free_single_agent",
            "direct": True,
        },
    }


def test_canonical_transport_retires_freellmpool_from_execution_only() -> None:
    assert FREELLM_BASE_URL in FREELLM_BASE_URLS
    assert FREELLMPOOL_BASE_URL in FREELLM_BASE_URLS
    assert FREELLM_EXECUTION_BASE_URLS == frozenset({FREELLM_BASE_URL})
    assert route_is_direct_freellm(_route(FREELLM_BASE_URL)) is True
    assert route_is_direct_freellm(_route(FREELLMPOOL_BASE_URL)) is False


def test_transport_canonical_and_production_mirror_are_byte_equal() -> None:
    canonical = BACKEND_ROOT / "llm_transport.py"
    mirror = REPO_ROOT / "scripts/sovereign-backend/llm_transport.py"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_omniroute_retirement_migration_canonical_and_production_mirror_are_byte_equal() -> None:
    canonical = BACKEND_ROOT / "migrations/053_omniroute_radar_retire_freellmpool.sql"
    mirror = REPO_ROOT / "scripts/sovereign-backend/migrations/053_omniroute_radar_retire_freellmpool.sql"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_draft_pr_authoritative_readback_gate_is_mirrored() -> None:
    canonical = BACKEND_ROOT / "agent_runtime/draft_pr_create_gate.py"
    mirror = REPO_ROOT / "scripts/sovereign-backend/agent_runtime/draft_pr_create_gate.py"
    assert canonical.read_bytes() == mirror.read_bytes()
    source = canonical.read_text("utf-8")
    assert "readback" in source.casefold()
    assert "draft" in source
    assert "head_sha" in source
