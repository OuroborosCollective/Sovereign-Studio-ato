from __future__ import annotations

import copy
import json
from pathlib import Path

from llm_boundary_ledger import discover_review_candidates, load_ledger, validate_ledger


ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / "config" / "architecture" / "llm-tool-boundary-review-ledger.json"


def test_current_review_ledger_is_complete_and_fresh() -> None:
    payload = load_ledger(LEDGER)
    result = validate_ledger(ROOT, payload)
    discovery = discover_review_candidates(ROOT)
    expected_by_id = {entry["candidateId"]: entry for entry in discovery["entries"]}
    actual_by_id = {entry["candidateId"]: entry for entry in payload["entries"]}
    relevant_ids: set[str] = set()
    for finding in result["findings"]:
        if finding.startswith(("MISSING_CANDIDATE:", "STALE_OR_REMOVED_CANDIDATE:")):
            relevant_ids.add(finding.split(":", 1)[1])
        elif finding.startswith("BINDING_DRIFT:"):
            relevant_ids.add(finding.removeprefix("BINDING_DRIFT:").rsplit(":", 1)[0])
    diagnostics = {
        candidate_id: {
            "expected": expected_by_id.get(candidate_id),
            "actual": actual_by_id.get(candidate_id),
        }
        for candidate_id in sorted(relevant_ids)
    }

    assert result["ok"] is True, json.dumps(
        {
            "findings": result["findings"],
            "candidates": diagnostics,
            "expectedLedgerSha256": result["ledgerSha256"],
            "actualLedgerSha256": payload.get("ledgerSha256"),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    assert result["status"] == "LLM_BOUNDARY_LEDGER_VERIFIED"
    # validate_ledger already rejects a ledger whose counts drift from discovery.
    # Bind this regression assertion to the reviewed ledger, not stale literals.
    assert result["rawCandidateCount"] == payload["rawCandidateCount"]
    assert result["canonicalCandidateCount"] == payload["canonicalCandidateCount"]
    assert result["findings"] == []


def test_mirror_pairs_are_classified_once() -> None:
    discovery = discover_review_candidates(ROOT)
    canonical = {
        entry["canonicalPath"]: entry
        for entry in discovery["entries"]
        if entry["canonicalPath"].startswith("scripts/sovereign-backend/agent_runtime/")
    }

    assert canonical
    assert all(entry["mirrorPaths"] for entry in canonical.values())
    assert not any(
        entry["canonicalPath"].startswith("backend/agent_runtime/")
        for entry in discovery["entries"]
    )


def test_file_sha_change_reopens_the_review() -> None:
    payload = copy.deepcopy(load_ledger(LEDGER))
    payload["entries"][0]["fileSha256"] = "0" * 64

    result = validate_ledger(ROOT, payload)

    assert result["ok"] is False
    assert any(item.endswith(":fileSha256") for item in result["findings"])


def test_unreviewed_classification_is_rejected() -> None:
    payload = copy.deepcopy(load_ledger(LEDGER))
    payload["entries"][0]["classification"] = "UNREVIEWED"

    result = validate_ledger(ROOT, payload)

    assert result["ok"] is False
    assert any(item.startswith("UNREVIEWED_OR_INVALID_CLASSIFICATION:") for item in result["findings"])
