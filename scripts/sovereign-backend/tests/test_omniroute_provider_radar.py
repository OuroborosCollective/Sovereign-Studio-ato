"""Contract tests for the non-authoritative OmniRoute provider radar."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from omniroute_provider_radar import (
    CatalogSource,
    OmniRouteRadarError,
    _git_blob_sha1,
    parse_catalog,
)


REVISION = "a" * 40
BLOB_SHA = "b" * 40
CONTENT_SHA = "c" * 64


def _source(lines: list[str]) -> CatalogSource:
    return CatalogSource(
        revision=REVISION,
        blob_sha=BLOB_SHA,
        content_sha256=CONTENT_SHA,
        curated_at="2026-07-22",
        text="\n".join([
            'export const FREE_CATALOG_CURATED_AT = "2026-07-22";',
            "export const FREE_MODEL_BUDGETS: FreeModelBudget[] = [",
            *lines,
            "];",
        ]),
    )


def test_git_blob_identity_matches_git_hash_object_contract():
    assert _git_blob_sha1(b"hello") == "b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0"


def test_catalog_candidates_are_quarantined_and_tos_avoid_is_blocked():
    source = _source([
        '{ provider: "cerebras", modelId: "llama", displayName: "Llama", monthlyTokens: 1000, creditTokens: 0, freeType: "recurring-daily", poolKey: "cerebras", tos: "caution" },',
        '{ provider: "agy", modelId: "model-x", displayName: "Model X", monthlyTokens: 0, creditTokens: 0, freeType: "keyless", poolKey: "agy", tos: "avoid", trainsOnPrompts: true },',
    ])

    candidates = parse_catalog(source)

    assert len(candidates) == 2
    assert candidates[0].provider_id == "cerebras"
    assert candidates[0].status == "quarantined"
    assert len(candidates[0].candidate_sha256) == 64
    assert candidates[1].provider_id == "agy"
    assert candidates[1].status == "blocked_tos"
    assert candidates[1].trains_on_prompts is True


def test_catalog_duplicate_provider_model_pool_identity_fails_closed():
    duplicate = '{ provider: "cerebras", modelId: "llama", displayName: "Llama", monthlyTokens: 1000, creditTokens: 0, freeType: "recurring-daily", poolKey: "cerebras", tos: "caution" },'
    source = _source([duplicate, duplicate])

    with pytest.raises(OmniRouteRadarError, match="omniroute_catalog_duplicate_identity"):
        parse_catalog(source)


def test_catalog_unknown_free_type_fails_closed():
    source = _source([
        '{ provider: "cerebras", modelId: "llama", displayName: "Llama", monthlyTokens: 1000, creditTokens: 0, freeType: "free-forever-maybe", poolKey: "cerebras", tos: "caution" },',
    ])

    with pytest.raises(OmniRouteRadarError, match="omniroute_catalog_entry_contract_invalid"):
        parse_catalog(source)
