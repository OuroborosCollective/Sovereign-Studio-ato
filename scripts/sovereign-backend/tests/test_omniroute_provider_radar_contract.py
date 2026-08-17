from __future__ import annotations

from pathlib import Path
import sys

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from llm_transport import (  # noqa: E402
    FREELLM_BASE_URL,
    FREELLM_BASE_URLS,
    FREELLM_EXECUTION_BASE_URLS,
    FREELLMPOOL_BASE_URL,
    route_is_direct_freellm,
)
from omniroute_provider_radar import (  # noqa: E402
    CatalogSource,
    OmniRouteRadarError,
    parse_catalog,
)


def _freellm_route(base_url: str) -> dict[str, object]:
    return {
        "id": "route-test",
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


def _source(*entries: str) -> CatalogSource:
    return CatalogSource(
        revision="a" * 40,
        blob_sha="b" * 40,
        content_sha256="c" * 64,
        curated_at="2026-08-17",
        text=(
            'export const FREE_CATALOG_CURATED_AT = "2026-08-17";\n'
            + "\n".join(entries)
        ),
    )


def test_freellmpool_remains_known_metadata_but_is_not_execution_eligible() -> None:
    assert FREELLMPOOL_BASE_URL in FREELLM_BASE_URLS
    assert FREELLMPOOL_BASE_URL not in FREELLM_EXECUTION_BASE_URLS
    assert FREELLM_BASE_URL in FREELLM_EXECUTION_BASE_URLS
    assert route_is_direct_freellm(_freellm_route(FREELLM_BASE_URL)) is True
    assert route_is_direct_freellm(_freellm_route(FREELLMPOOL_BASE_URL)) is False


def test_omniroute_catalog_candidates_are_quarantined_and_tos_avoid_is_blocked() -> None:
    candidates = parse_catalog(_source(
        '{ provider: "llm7", modelId: "default", displayName: "LLM7 Default", monthlyTokens: 60000, creditTokens: 0, freeType: "keyless", poolKey: "llm7-free", tos: "ok" },',
        '{ provider: "example", modelId: "unsafe", displayName: "Avoid Example", monthlyTokens: 1000, creditTokens: 0, freeType: "recurring-daily", poolKey: null, tos: "avoid", trainsOnPrompts: true },',
    ))

    assert [item.status for item in candidates] == ["quarantined", "blocked_tos"]
    assert candidates[0].provider_id == "llm7"
    assert candidates[0].model_id == "default"
    assert candidates[1].trains_on_prompts is True
    assert all(len(item.candidate_sha256) == 64 for item in candidates)


def test_omniroute_catalog_duplicate_identity_fails_closed() -> None:
    row = '{ provider: "llm7", modelId: "default", displayName: "LLM7 Default", monthlyTokens: 60000, creditTokens: 0, freeType: "keyless", poolKey: "llm7-free", tos: "ok" },'
    with pytest.raises(OmniRouteRadarError, match="omniroute_catalog_duplicate_identity"):
        parse_catalog(_source(row, row))


def test_omniroute_catalog_format_drift_fails_closed_instead_of_guessing() -> None:
    multiline = """{
  provider: \"llm7\",
  modelId: \"default\",
  displayName: \"LLM7 Default\",
  monthlyTokens: 60000,
  creditTokens: 0,
  freeType: \"keyless\",
  poolKey: \"llm7-free\",
  tos: \"ok\"
},"""
    with pytest.raises(OmniRouteRadarError, match="omniroute_catalog_candidate_count_invalid"):
        parse_catalog(_source(multiline))


def test_radar_migration_is_mirrored_and_permanently_candidate_only() -> None:
    migration = BACKEND_ROOT / "migrations/053_omniroute_radar_retire_freellmpool.sql"
    mirror = REPO_ROOT / "backend/migrations/053_omniroute_radar_retire_freellmpool.sql"
    assert migration.read_bytes() == mirror.read_bytes()

    sql = migration.read_text("utf-8")
    assert "freellmpool_retired_from_execution" in sql
    assert "routing_eligible BOOLEAN NOT NULL DEFAULT false CHECK (routing_eligible = false)" in sql
    assert "promotion_requires_direct_canary BOOLEAN NOT NULL DEFAULT true" in sql
    assert "CHECK (promotion_requires_direct_canary = true)" in sql
    assert "status IN ('quarantined', 'blocked_tos', 'stale')" in sql


def test_production_entrypoint_registers_radar_without_making_it_an_execution_transport() -> None:
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text("utf-8")
    production_app = (BACKEND_ROOT / "production_app.py").read_text("utf-8")

    assert "production_app:app" in dockerfile
    assert "register_omniroute_provider_radar" in production_app
    assert "omniroute_provider_radar_service" in production_app
    assert "OmniRoute" not in (BACKEND_ROOT / "llm_transport.py").read_text("utf-8")
