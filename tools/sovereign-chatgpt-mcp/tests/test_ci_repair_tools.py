from __future__ import annotations

import copy
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

import llm_boundary_ledger as ledger_module
from ci_repair_tools import (
    append_boundary_reconciliation_continuity,
    bounded_text_sources_from_archive,
    extract_workflow_failure_evidence,
    revision_bound_ci_repair,
)
from llm_boundary_ledger import ledger_sha256, load_ledger, reconcile_ledger


ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / "config" / "architecture" / "llm-tool-boundary-review-ledger.json"


def test_failure_extractor_classifies_content_not_workflow_name() -> None:
    log = "\n".join(
        (
            "FAILED tests/test_llm_boundary_ledger.py::test_current_review_ledger_is_complete_and_fresh",
            "MISSING_CANDIDATE:llm-boundary:96acea8d186b6cf800854b8f",
            "1 failed, 531 passed, 12 skipped in 41.23s",
        )
    )
    result = extract_workflow_failure_evidence(
        workflow_run={"id": 30728100603, "name": "Unrelated check name", "head_sha": "b" * 40, "conclusion": "failure"},
        jobs=[
            {
                "id": 91443679876,
                "name": "Unrelated job name",
                "conclusion": "failure",
                "steps": [{"name": "Run policy and runtime tests", "conclusion": "failure"}],
            }
        ],
        sources=[{"name": "mcp-pytest.log", "text": log}],
        artifact_receipts=[{"artifactId": 8827099917, "archiveSha256": "e" * 64}],
    )

    assert result["failureFamily"] == "LLM_BOUNDARY_LEDGER_DRIFT"
    assert result["failedTests"] == 1
    assert result["passedTests"] == 531
    assert result["skippedTests"] == 12
    assert result["causalCandidate"] == "llm-boundary:96acea8d186b6cf800854b8f"
    assert result["codeRollbackRecommended"] is False
    assert result["rawLogsReturned"] is False


def test_failure_extractor_reads_junit_counts_and_first_causal_candidate() -> None:
    junit = """<?xml version="1.0" encoding="utf-8"?>
<testsuite tests="544" failures="1" errors="0" skipped="12">
  <testcase classname="tests.test_llm_boundary_ledger" name="test_current_review_ledger_is_complete_and_fresh">
    <failure>MISSING_CANDIDATE:llm-boundary:ffffffffffffffffffffffff then llm-boundary:000000000000000000000000</failure>
  </testcase>
</testsuite>"""
    result = extract_workflow_failure_evidence(
        workflow_run={"id": 7, "name": "Tests", "head_sha": "a" * 40, "conclusion": "failure"},
        jobs=[
            {
                "id": 9,
                "name": "MCP",
                "conclusion": "failure",
                "steps": [{"name": "Pytest", "conclusion": "failure"}],
            }
        ],
        sources=[{"name": "junit.xml", "text": junit}],
        artifact_receipts=[],
    )

    assert result["failedTests"] == 1
    assert result["passedTests"] == 531
    assert result["skippedTests"] == 12
    assert result["causalCandidate"] == "llm-boundary:ffffffffffffffffffffffff"
    assert result["causalTest"] == "tests.test_llm_boundary_ledger::test_current_review_ledger_is_complete_and_fresh"


def test_artifact_extraction_rejects_parent_traversal() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../pytest.log", "1 failed")

    with pytest.raises(ValueError, match="unsafe path"):
        bounded_text_sources_from_archive(buffer.getvalue(), artifact_name="pytest")


def test_reconciler_preserves_classification_across_candidate_id_drift() -> None:
    payload = copy.deepcopy(load_ledger(LEDGER))
    original = payload["entries"][0]
    original_classification = original["classification"]
    original_rationale = original["rationale"]
    original["candidateId"] = "llm-boundary:" + "0" * 24
    payload["ledgerSha256"] = ledger_sha256(payload)

    result = reconcile_ledger(ROOT, payload)

    match = next(
        item for item in result["bindingDrift"] if item["symbol"] == original["symbol"]
    )
    assert "candidateId" in match["changedFields"]
    assert match["classificationPreserved"] == original_classification
    assert result["ownerDecisionCandidateIds"] == []
    assert original_rationale


def test_reconciler_safely_classifies_exact_sha_guard() -> None:
    payload = copy.deepcopy(load_ledger(LEDGER))
    payload["entries"] = [
        entry for entry in payload["entries"] if entry["symbol"] != "_runtime_revision"
    ]
    payload["ledgerSha256"] = ledger_sha256(payload)

    result = reconcile_ledger(ROOT, payload)

    candidate = next(item for item in result["newCandidates"] if item["symbol"] == "_runtime_revision")
    assert candidate["suggestedClassification"] == "STRUCTURED_POLICY"
    assert candidate["decisionSource"] == "DETERMINISTIC_RULE"
    assert candidate["ownerDecisionRequired"] is False


def test_reconciler_does_not_write_unreviewed_candidate(tmp_path: Path, monkeypatch) -> None:
    candidate = {
        "candidateId": "llm-boundary:" + "1" * 24,
        "canonicalPath": "src/runtime/free_language.ts",
        "mirrorPaths": [],
        "symbol": "routeText",
        "line": 1,
        "patternFamily": "javascript_keyword_intent",
        "fileSha256": "2" * 64,
        "anchorSha256": "3" * 64,
        "reopenOnChange": True,
    }
    monkeypatch.setattr(
        ledger_module,
        "discover_review_candidates",
        lambda _repo: {
            "sourceRevision": "a" * 40,
            "rawCandidateCount": 1,
            "canonicalCandidateCount": 1,
            "entries": [candidate],
        },
    )
    target = tmp_path / "ledger.json"
    target.write_text("unchanged\n", "utf-8")
    payload = {
        "schemaVersion": ledger_module.LEDGER_SCHEMA,
        "detector": "tools/sovereign-chatgpt-mcp/llm_boundary_contract.py",
        "entries": [],
    }

    with pytest.raises(RuntimeError, match="OWNER_REVIEW_REQUIRED"):
        reconcile_ledger(tmp_path, payload, write_path=target)

    assert target.read_text("utf-8") == "unchanged\n"


def test_reconciliation_report_is_json_serializable() -> None:
    result = reconcile_ledger(ROOT, load_ledger(LEDGER))

    assert json.loads(json.dumps(result))["schemaVersion"] == "sovereign.boundary-ledger-reconciliation.v1"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def test_continuity_append_is_mirrored_and_idempotent(tmp_path: Path) -> None:
    policy_path = tmp_path / "tools/sovereign-chatgpt-mcp/config/sovereign-continuity-policy.json"
    canonical = tmp_path / "docs/sovereign-continuity/LEDGER.jsonl"
    runtime = tmp_path / "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl"
    context = tmp_path / "docs/sovereign-continuity/CONTEXT.md"
    for path in (policy_path, canonical, runtime, context):
        path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(
            {
                "canonicalPaths": {
                    "context": "docs/sovereign-continuity/CONTEXT.md",
                    "ledger": "docs/sovereign-continuity/LEDGER.jsonl",
                    "runtimeLedger": "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl",
                },
                "identity": {"canonicalName": "Sovereign", "spokenName": "Sovereign", "familyDesignation": "Family"},
            }
        ),
        "utf-8",
    )
    canonical.write_text("", "utf-8")
    runtime.write_text("", "utf-8")
    context.write_text("bounded context", "utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    (tmp_path / "change.txt").write_text("changed", "utf-8")
    reconciliation = {
        "ledgerSha256": "b" * 64,
        "preservedCandidates": 71,
        "newCandidates": [{"candidateId": "llm-boundary:" + "c" * 24}],
        "rawCandidateCount": 91,
        "canonicalCandidateCount": 72,
    }

    first = append_boundary_reconciliation_continuity(
        tmp_path,
        source_revision="a" * 40,
        reconciliation=reconciliation,
    )
    second = append_boundary_reconciliation_continuity(
        tmp_path,
        source_revision="a" * 40,
        reconciliation=reconciliation,
    )

    assert first["status"] == "CONTINUITY_ENTRY_APPENDED"
    assert second["status"] == "CONTINUITY_ENTRY_ALREADY_PRESENT"
    assert canonical.read_bytes() == runtime.read_bytes()
    assert len(canonical.read_text("utf-8").splitlines()) == 1


def test_orchestrator_stops_before_broker_read_on_revision_conflict(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "tracked.txt").write_text("baseline", "utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")

    class Runtime:
        def _repo(self, _workspace_id: str) -> Path:
            return tmp_path

    class Broker:
        def call(self, *_args, **_kwargs):
            raise AssertionError("broker must not be called for a conflicting workspace revision")

    result = revision_bound_ci_repair(
        runtime=Runtime(),
        broker=Broker(),
        workspace_id="workspace",
        pr_number=7,
        workflow_run_id=8,
        expected_pr_head_sha="f" * 40,
    )

    assert result["status"] == "REVISION_CONFLICT"
    assert result["mutationPerformed"] is False
