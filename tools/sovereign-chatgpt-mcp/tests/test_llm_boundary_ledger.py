from __future__ import annotations

import copy
from pathlib import Path

from llm_boundary_ledger import discover_review_candidates, load_ledger, validate_ledger


ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / "config" / "architecture" / "llm-tool-boundary-review-ledger.json"


def test_current_review_ledger_is_complete_and_fresh() -> None:
    result = validate_ledger(ROOT, load_ledger(LEDGER))

    assert result["ok"] is True
    assert result["status"] == "LLM_BOUNDARY_LEDGER_VERIFIED"
    assert result["rawCandidateCount"] == 75
    assert result["canonicalCandidateCount"] == 63
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
