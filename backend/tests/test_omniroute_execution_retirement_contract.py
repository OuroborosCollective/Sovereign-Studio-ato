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
    OMNIROUTE_BASE_URL,
    route_is_direct_freellm,
    route_is_omniroute_source,
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


def test_free_llm_api_stays_live_while_omniroute_replaces_pool_routes() -> None:
    assert FREELLM_BASE_URL in FREELLM_BASE_URLS
    assert FREELLMPOOL_BASE_URL in FREELLM_BASE_URLS
    assert FREELLM_BASE_URL in FREELLM_EXECUTION_BASE_URLS
    assert OMNIROUTE_BASE_URL in FREELLM_EXECUTION_BASE_URLS
    assert FREELLMPOOL_BASE_URL not in FREELLM_EXECUTION_BASE_URLS
    assert route_is_direct_freellm(_route(FREELLM_BASE_URL)) is True
    assert route_is_direct_freellm(_route(OMNIROUTE_BASE_URL)) is True
    assert route_is_omniroute_source(_route(OMNIROUTE_BASE_URL)) is True
    assert route_is_direct_freellm(_route(FREELLMPOOL_BASE_URL)) is False


def test_transport_canonical_and_production_mirror_are_byte_equal() -> None:
    canonical = BACKEND_ROOT / "llm_transport.py"
    mirror = REPO_ROOT / "scripts/sovereign-backend/llm_transport.py"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_omniroute_retirement_migration_canonical_and_production_mirror_are_byte_equal() -> None:
    canonical = BACKEND_ROOT / "migrations/053_omniroute_radar_retire_freellmpool.sql"
    mirror = REPO_ROOT / "scripts/sovereign-backend/migrations/053_omniroute_radar_retire_freellmpool.sql"
    assert canonical.read_bytes() == mirror.read_bytes()


def test_omniroute_route_replacement_migration_is_mirrored_and_preserves_freellmapi() -> None:
    canonical = BACKEND_ROOT / "migrations/055_omniroute_replaces_freellmpool_routes.sql"
    mirror = REPO_ROOT / "scripts/sovereign-backend/migrations/055_omniroute_replaces_freellmpool_routes.sql"
    assert canonical.read_bytes() == mirror.read_bytes()
    sql = canonical.read_text("utf-8")
    assert "http://freellmpool:8080/v1" in sql
    assert "http://omniroute:20128/v1" in sql
    assert "http://freellmapi:3001/v1" not in sql
    assert "freellmpool_replaced_by_omniroute" in sql
    assert "runtime-double-canary-required" in sql


def test_draft_pr_authoritative_readback_gate_is_mirrored() -> None:
    canonical = BACKEND_ROOT / "agent_runtime/draft_pr_create_gate.py"
    mirror = REPO_ROOT / "scripts/sovereign-backend/agent_runtime/draft_pr_create_gate.py"
    assert canonical.read_bytes() == mirror.read_bytes()
    source = canonical.read_text("utf-8")
    assert "readback" in source.casefold()
    assert "draft" in source
    assert "head_sha" in source
