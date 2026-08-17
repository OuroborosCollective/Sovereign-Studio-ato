from __future__ import annotations

import ast
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from evidence_observatory_contracts import (  # noqa: E402
    build_evidence_passport,
    evaluate_evidence_case,
    public_case_projection,
    score_arena_response,
    sha256_text,
    source_dependency_analysis,
)
import evidence_observatory_integrations as observatory_integrations  # noqa: E402
from evidence_observatory_integrations import (  # noqa: E402
    NOTION_VERSION,
    normalize_notion_page,
    publish_huggingface_batch,
    sync_notion_research,
)


def valid_unproven_case():
    claim = "The available evidence cannot yet decide the claim."
    return {
        "claim": claim,
        "claimSha256": sha256_text(claim),
        "verdict": "UNPROVEN",
        "evidenceClass": "source-provenance",
        "asOf": "2026-08-17T07:00:00Z",
        "truthNotInferredFromAgreement": True,
        "method": {"positionTaken": False, "evidenceOnly": True},
        "sources": [
            {
                "id": "source-1",
                "label": "Primary source",
                "sourceType": "primary",
                "locator": "https://example.org/primary",
                "contentSha256": "a" * 64,
                "observedAt": "2026-08-16T08:00:00Z",
                "provenance": {"originFamily": "origin-a"},
                "geo": {"lat": 52.52, "lon": 13.405, "evidenceRole": "material"},
            }
        ],
        "proofReceipts": [
            {
                "id": "receipt-1",
                "proofRoute": "source-lineage",
                "receiptSha256": "b" * 64,
                "integrityValid": True,
                "authenticated": False,
                "claimBound": True,
                "replayVerified": True,
                "decisive": False,
                "sourceIds": ["source-1"],
            }
        ],
        "timeline": [
            {
                "id": "event-1",
                "at": "2026-08-16T08:00:00Z",
                "title": "Source observed",
                "sourceIds": ["source-1"],
            }
        ],
        "contradictionReview": {"completed": True},
        "sensitivityReview": {
            "completed": True,
            "secretsExcluded": True,
            "redactionsVerified": True,
        },
        "verdictBasis": {
            "sourceIds": ["source-1"],
            "proofReceiptIds": ["receipt-1"],
        },
        "evidenceNeeded": ["An independently authenticated primary receipt that decides the claim."],
        "contradictions": [{"id": "contra-1", "at": "2026-08-16T09:00:00Z"}],
        "claimGenealogy": [{"id": "g1", "fromSourceId": "source-1", "toSourceId": "derived-1", "mutation": "may -> is"}],
        "informationFlow": [{"id": "f1", "fromSourceId": "source-1", "toSourceId": "derived-1", "relation": "quoted-by"}],
    }


def test_route_module_is_syntactically_valid_without_importing_flask_runtime():
    source = (BACKEND / "evidence_observatory.py").read_text(encoding="utf-8")
    ast.parse(source)


def test_unproven_is_publishable_when_the_uncertainty_is_reproducible():
    payload = valid_unproven_case()
    gate = evaluate_evidence_case(payload)
    assert gate["passed"] is True
    assert gate["blockers"] == []
    assert gate["independentOriginCount"] == 1
    passport = build_evidence_passport(payload, gate)
    assert passport["verdict"] == "UNPROVEN"
    assert passport["truthNotInferredFromAgreement"] is True
    assert len(passport["passportSha256"]) == 64


def test_supported_claim_requires_decisive_receipt():
    payload = valid_unproven_case()
    payload["verdict"] = "SUPPORTED"
    payload["evidenceNeeded"] = []
    gate = evaluate_evidence_case(payload)
    assert gate["passed"] is False
    assert "decisive_receipt_required" in gate["blockers"]


def test_time_machine_hides_future_sources_and_nonmaterial_geo():
    payload = valid_unproven_case()
    payload["sources"].append(
        {
            "id": "source-future",
            "label": "Future context",
            "sourceType": "secondary",
            "locator": "https://example.org/future",
            "contentSha256": "c" * 64,
            "observedAt": "2026-08-18T08:00:00Z",
            "provenance": {"originFamily": "origin-b"},
            "geo": {"lat": 40.7, "lon": -74.0, "evidenceRole": "material"},
        }
    )
    payload["sources"].append(
        {
            "id": "source-context",
            "label": "Context only",
            "sourceType": "secondary",
            "locator": "https://example.org/context",
            "contentSha256": "d" * 64,
            "observedAt": "2026-08-16T08:30:00Z",
            "provenance": {"originFamily": "origin-a"},
            "geo": {"lat": 48.1, "lon": 11.5, "evidenceRole": "context"},
        }
    )
    row = {
        "id": "case-1",
        "project_id": "atlas",
        "title": "Temporal evidence",
        "claim": payload["claim"],
        "claim_sha256": payload["claimSha256"],
        "verdict": "UNPROVEN",
        "evidence_class": "source-provenance",
        "workflow_state": "PUBLISHABLE",
        "case_sha256": "e" * 64,
        "passport_sha256": "f" * 64,
        "case_payload": payload,
        "gate_report": {},
        "passport": {},
        "as_of": datetime(2026, 8, 17, tzinfo=timezone.utc),
    }
    projected = public_case_projection(row, as_of=datetime(2026, 8, 17, tzinfo=timezone.utc))
    assert {source["id"] for source in projected["sources"]} == {"source-1", "source-context"}
    assert [point["sourceId"] for point in projected["materialGeoEvidence"]] == ["source-1"]
    assert projected["sourceLineage"]["origin-a"] == ["source-1", "source-context"]
    assert projected["claimGenealogy"][0]["mutation"] == "may -> is"
    assert projected["informationFlow"][0]["relation"] == "quoted-by"


def test_source_dependency_analysis_never_recomputes_truth():
    payload = valid_unproven_case()
    analysis = source_dependency_analysis({"case_payload": payload}, "source-1")
    assert analysis["simulationOnly"] is True
    assert analysis["verdictRecomputed"] is False
    assert analysis["verdictBasisSourceRemoved"] is True
    assert analysis["verdictBasisReceiptDependencyBroken"] is True
    assert analysis["remainingIndependentOriginCount"] == 0
    assert analysis["timelineEventsAffected"] == 1
    assert len(analysis["analysisSha256"]) == 64


def test_arena_penalizes_unknown_citations_and_rewards_correct_abstention():
    payload = valid_unproven_case()
    case = {"verdict": "UNPROVEN", "case_payload": payload}
    metrics = score_arena_response(case, {
        "verdict": "UNPROVEN",
        "citations": ["source-1", "invented-source"],
        "claims": [
            {"text": "Bound", "sourceIds": ["source-1"]},
            {"text": "Unbound", "sourceIds": ["invented-source"]},
        ],
        "contradictionIds": ["contra-1"],
    })
    assert metrics["abstentionCorrect"] is True
    assert metrics["citationPrecision"] == 0.5
    assert metrics["unsupportedClaimRate"] == 0.5
    assert metrics["truthfulnessRanked"] is False


def test_notion_claim_mutation_creates_a_new_external_candidate_identity():
    base = {
        "id": "page-123",
        "url": "https://www.notion.so/page-123",
        "last_edited_time": "2026-08-17T07:00:00Z",
        "properties": {
            "Claim": {"type": "rich_text", "rich_text": [{"plain_text": "First claim"}]},
            "Name": {"type": "title", "title": [{"plain_text": "Research"}]},
        },
    }
    first = normalize_notion_page(base)
    changed = {**base, "properties": {**base["properties"], "Claim": {"type": "rich_text", "rich_text": [{"plain_text": "Changed claim"}]}}}
    second = normalize_notion_page(changed)
    assert first["externalKey"] != second["externalKey"]
    assert first["sourceKind"] == "notion"


def test_notion_direct_sync_combines_search_and_data_source_without_truth_promotion(monkeypatch):
    search_page = {
        "object": "page",
        "id": "1" * 32,
        "url": "https://www.notion.so/search-page",
        "last_edited_time": "2026-08-17T07:00:00Z",
        "properties": {
            "Claim": {"type": "rich_text", "rich_text": [{"plain_text": "Search claim"}]},
            "Name": {"type": "title", "title": [{"plain_text": "Search research"}]},
        },
    }
    data_page = {
        "object": "page",
        "id": "2" * 32,
        "url": "https://www.notion.so/data-page",
        "last_edited_time": "2026-08-17T08:00:00Z",
        "properties": {
            "Claim": {"type": "rich_text", "rich_text": [{"plain_text": "Data source claim"}]},
            "Name": {"type": "title", "title": [{"plain_text": "Data research"}]},
        },
    }
    calls = []

    def fake_notion_request(method, path, *, json_body=None):
        calls.append((method, path, dict(json_body or {})))
        if path == "/search":
            return {"results": [search_page], "has_more": False, "next_cursor": None}
        assert path == f"/data_sources/{'a' * 32}/query"
        return {"results": [data_page], "has_more": False, "next_cursor": None}

    monkeypatch.setattr(observatory_integrations, "_notion_request", fake_notion_request)
    result = sync_notion_research({
        "query": "evidence",
        "dataSourceIds": ["a" * 32],
        "maxResults": 10,
    })

    assert NOTION_VERSION == "2026-03-11"
    assert result["normalizedCount"] == 2
    assert result["searchPageCount"] == 1
    assert result["dataSourcePageCount"] == 1
    assert result["dataSourceIdsQueried"] == 1
    assert result["truthPromotions"] == 0
    assert result["protectedValueReturned"] is False
    assert all(page["sourceKind"] == "notion" for page in result["pages"])
    assert calls[0][1] == "/search"


def test_hugging_face_publisher_never_writes_directly_to_main():
    with pytest.raises(RuntimeError, match="huggingface_direct_main_publish_forbidden"):
        publish_huggingface_batch(rows=[{"caseId": "case-1"}], repo_id="owner/repo", revision="main")
