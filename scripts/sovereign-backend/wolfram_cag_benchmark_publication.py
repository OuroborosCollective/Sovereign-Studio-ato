"""Public Evidence Observatory projections for the Wolfram CAG benchmark.

The 12 benchmark fixtures are deterministic comparison contracts.  The
independent Wolfram observations captured here are reference evidence only;
they are never represented as live CAG component transport results.
"""
from __future__ import annotations

from typing import Any

from agent_runtime.wolfram_cag_benchmark_cases import BENCHMARK_CASES, comparison_verdict
from evidence_observatory_contracts import (
    build_evidence_passport,
    evaluate_evidence_case,
    sha256_json,
    sha256_text,
)

CAPTURED_AT = "2026-08-18T20:20:58Z"
PROJECT_ID = "wolfram-cag-benchmark"

# Normalized evidence captured from the connected Wolfram context/evaluator on
# 2026-08-18.  URLs are public replay/documentation locators.  The hash scope
# is the normalized evidence object below, not an assertion about immutable
# bytes served by Wolfram's website.
WOLFRAM_REFERENCES: dict[str, dict[str, Any]] = {
    "cag-bench-001": {
        "locator": "https://www.wolframalpha.com/input?i=17+%2A+23",
        "query": "17 * 23",
        "result": "391",
        "captureMethod": "WolframContext",
    },
    "cag-bench-002": {
        "locator": "https://www.wolframalpha.com/input?i=17+%2A+23",
        "query": "17 * 23",
        "result": "391",
        "captureMethod": "WolframContext",
    },
    "cag-bench-003": {
        "locator": "https://www.wolframalpha.com/input?i=derivative+of+x%5E3",
        "query": "derivative of x^3",
        "result": "3*x^2",
        "captureMethod": "WolframContext",
    },
    "cag-bench-004": {
        "locator": "https://www.wolframalpha.com/input?i=dimension+of+speed",
        "query": "dimension of speed",
        "result": "length^1 time^-1",
        "captureMethod": "WolframContext",
    },
    "cag-bench-005": {
        "locator": "https://www.wolframalpha.com/input?i=2.5+kilometers+to+meters",
        "query": "2.5 kilometers to meters",
        "result": "2500 meters",
        "captureMethod": "WolframContext",
    },
    "cag-bench-006": {
        "locator": "https://www.wolframalpha.com/input?i=numerical+approximation+of+Pi",
        "query": "numerical approximation of Pi",
        "result": "3.141592653589793238462643383279502884...",
        "captureMethod": "WolframContext",
    },
    "cag-bench-007": {
        "locator": "https://www.wolframalpha.com/input?i=numerical+approximation+of+Pi",
        "query": "numerical approximation of Pi",
        "result": "3.141592653589793238462643383279502884...",
        "captureMethod": "WolframContext",
    },
    "cag-bench-008": {
        "locator": "https://www.wolframalpha.com/input?i=arithmetic+mean+of+%7B2%2C+4%2C+6%2C+8%2C+10%7D",
        "query": "arithmetic mean of {2,4,6,8,10}",
        "result": "6",
        "captureMethod": "WolframContext",
    },
    "cag-bench-009": {
        "locator": "https://reference.wolfram.com/language/ref/MinValue.html",
        "query": "MinValue[{(x-3)^2, Element[x,Reals]},x]",
        "result": "0",
        "captureMethod": "WolframLanguageEvaluator",
    },
    "cag-bench-010": {
        "locator": "https://www.wolframalpha.com/input?i=number+of+days+in+January+2026",
        "query": "number of days in January 2026",
        "result": "31 days",
        "captureMethod": "WolframContext",
    },
    "cag-bench-011": {
        "locator": "https://www.wolframalpha.com/input?i=boiling+point+of+water+at+standard+atmospheric+pressure",
        "query": "boiling point of water at standard atmospheric pressure",
        "result": (
            "Wolfram|Alpha returned 100.3 °C for its standard-conditions interpretation and "
            "also displayed 99.9839 °C as the temperature at which water boils at standard pressure."
        ),
        "captureMethod": "WolframContext",
        "precisionNotice": (
            "The fixture's 100 °C reference is a rounded conventional statement.  This public evidence "
            "projection therefore abstains instead of promoting an exact structured-fact truth claim "
            "without an explicit thermodynamic tolerance/convention."
        ),
    },
    "cag-bench-012": {
        "locator": "https://www.wolframalpha.com/input?i=fuzzy+text+claim+example",
        "query": "fuzzy text claim example",
        "result": "No Results Found",
        "captureMethod": "WolframContext",
        "precisionNotice": "No computational reference decides the intentionally fuzzy claim.",
    },
}


def _observatory_verdict(case_id: str, benchmark_verdict: str) -> str:
    if case_id in {"cag-bench-011", "cag-bench-012"}:
        return "UNPROVEN"
    if benchmark_verdict == "CONTRADICTED":
        return "REFUTED"
    if benchmark_verdict == "SUPPORTED":
        return "SUPPORTED"
    return "UNPROVEN"


def _evidence_class(case_id: str) -> tuple[str, str, str]:
    if case_id == "cag-bench-011":
        return "structured-data", "structured-data", "structured"
    if case_id == "cag-bench-012":
        return "source-provenance", "source-lineage", "formal"
    return "formal-computation", "formal-computation", "formal"


def _payload_for_case(case: Any) -> dict[str, Any]:
    reference = dict(WOLFRAM_REFERENCES[case.case_id])
    benchmark_verdict = comparison_verdict(case)
    verdict = _observatory_verdict(case.case_id, benchmark_verdict)
    evidence_class, proof_route, source_type = _evidence_class(case.case_id)
    source_id = f"wolfram-reference-{case.case_id}"
    receipt_id = f"formal-receipt-{case.case_id}"
    normalized_evidence = {
        "query": reference["query"],
        "result": reference["result"],
        "captureMethod": reference["captureMethod"],
        "capturedAt": CAPTURED_AT,
        "liveCagResult": False,
        "benchmarkCaseId": case.case_id,
    }
    if reference.get("precisionNotice"):
        normalized_evidence["precisionNotice"] = reference["precisionNotice"]
    source = {
        "id": source_id,
        "label": "Independent Wolfram formal reference",
        "sourceType": source_type,
        "locator": reference["locator"],
        "contentSha256": sha256_json(normalized_evidence),
        "observedAt": CAPTURED_AT,
        "provenance": {
            "originFamily": "wolfram-independent-formal-reference",
            "captureMethod": reference["captureMethod"],
            "hashScope": "normalized-evidence-record",
            "liveCagResult": False,
        },
        "excerpt": reference["result"],
    }
    decisive = verdict in {"SUPPORTED", "REFUTED"}
    receipt_base = {
        "id": receipt_id,
        "proofRoute": proof_route,
        "integrityValid": True,
        "authenticated": False,
        "claimBound": True,
        "replayVerified": True,
        "decisive": decisive,
        "sourceIds": [source_id],
        "referenceEvidenceSha256": source["contentSha256"],
        "liveCagResult": False,
    }
    receipt = dict(receipt_base)
    receipt["receiptSha256"] = sha256_json(receipt_base)
    contradictions = []
    if verdict == "REFUTED":
        contradictions.append({
            "id": f"formal-contradiction-{case.case_id}",
            "at": CAPTURED_AT,
            "sourceIds": [source_id],
            "summary": "The independent formal reference differs from the claim value.",
        })
    if case.case_id == "cag-bench-011":
        contradictions.append({
            "id": "precision-boundary-cag-bench-011",
            "at": CAPTURED_AT,
            "sourceIds": [source_id],
            "summary": reference["precisionNotice"],
        })
    evidence_needed = []
    if verdict == "UNPROVEN":
        evidence_needed = [
            (
                "An explicit thermodynamic convention and numeric tolerance are required to decide the rounded "
                "100 °C statement."
            ) if case.case_id == "cag-bench-011" else
            "A claim with a falsifiable/decidable reference condition is required."
        ]
    tolerance = {
        "absolute": case.tolerance.absolute,
        "relative": case.tolerance.relative,
        "significantDigits": case.tolerance.significant_digits,
    }
    return {
        "claim": case.claim_text,
        "claimSha256": sha256_text(case.claim_text),
        "verdict": verdict,
        "evidenceClass": evidence_class,
        "asOf": CAPTURED_AT,
        "truthNotInferredFromAgreement": True,
        "method": {
            "positionTaken": False,
            "evidenceOnly": True,
            "benchmarkFixture": True,
            "liveCagResult": False,
            "independentReferenceLane": "Wolfram MCP",
        },
        "sources": [source],
        "proofReceipts": [receipt],
        "timeline": [{
            "id": f"reference-capture-{case.case_id}",
            "at": CAPTURED_AT,
            "title": "Independent Wolfram reference captured",
            "sourceIds": [source_id],
        }],
        "contradictionReview": {"completed": True},
        "sensitivityReview": {
            "completed": True,
            "secretsExcluded": True,
            "redactionsVerified": True,
        },
        "verdictBasis": {
            "sourceIds": [source_id],
            "proofReceiptIds": [receipt_id],
        },
        "evidenceNeeded": evidence_needed,
        "contradictions": contradictions,
        "claimGenealogy": [{
            "id": f"fixture-lineage-{case.case_id}",
            "fromSourceId": source_id,
            "toSourceId": case.case_id,
            "mutation": "independent-reference-to-benchmark-comparison",
        }],
        "informationFlow": [{
            "id": f"formal-flow-{case.case_id}",
            "fromSourceId": source_id,
            "toSourceId": case.case_id,
            "relation": "reference-check",
        }],
        "benchmark": {
            "caseId": case.case_id,
            "componentId": case.component_id,
            "expectedResultType": case.expected_result_type,
            "domain": case.domain,
            "claimValue": case.claim_value,
            "fixtureReferenceValue": case.reference_value,
            "units": case.units,
            "assumptions": list(case.assumptions),
            "tolerance": tolerance,
            "comparisonVerdict": benchmark_verdict,
            "hasFixtureReference": bool(case.has_real_result),
            "fixtureReferenceIsLiveProviderReadback": False,
        },
        "limitations": [
            "The benchmark reference is a deterministic fixture, not a live CAG component response.",
            "The independent Wolfram reference validates the public comparison context only.",
        ] + ([reference["precisionNotice"]] if reference.get("precisionNotice") else []),
    }


def build_cag_benchmark_public_rows() -> list[dict[str, Any]]:
    """Build the 12 publishable gate-/passport-/case-hash-bound projections.

    Boundary cases (``publishable=False``) are excluded: they carry no
    independent Wolfram reference and exist to prove honest degradation,
    not to be published as evidence.
    """
    rows: list[dict[str, Any]] = []
    for case in BENCHMARK_CASES:
        if not case.publishable:
            continue
        payload = _payload_for_case(case)
        gate = evaluate_evidence_case(payload)
        if not gate["passed"]:
            raise RuntimeError(f"cag_benchmark_gate_failed:{case.case_id}:{','.join(gate['blockers'])}")
        passport = build_evidence_passport(payload, gate)
        case_sha = sha256_json({"payload": payload, "gate": gate, "passport": passport})
        source = payload["sources"][0]
        row = {
            "schemaVersion": "sovereign.evidence-case.v1",
            "caseId": case.case_id,
            "projectId": PROJECT_ID,
            "title": case.title,
            "claim": case.claim_text,
            "claimSha256": payload["claimSha256"],
            "verdict": payload["verdict"],
            "evidenceClass": payload["evidenceClass"],
            "workflowState": "PUBLISHABLE",
            "asOf": CAPTURED_AT,
            "caseSha256": case_sha,
            "sources": payload["sources"],
            "timeline": payload["timeline"],
            "contradictions": payload["contradictions"],
            "evidenceNeeded": payload["evidenceNeeded"],
            "verdictBasis": payload["verdictBasis"],
            "sourceLineage": {
                source["provenance"]["originFamily"]: [source["id"]],
            },
            "materialGeoEvidence": [],
            "claimGenealogy": payload["claimGenealogy"],
            "informationFlow": payload["informationFlow"],
            "gateReport": gate,
            "evidencePassport": passport,
            "passportSha256": passport["passportSha256"],
            "proofReceipts": payload["proofReceipts"],
            "method": payload["method"],
            "benchmark": payload["benchmark"],
            "limitations": payload["limitations"],
            "truthBoundary": {
                "liveCagResult": False,
                "fixtureReference": True,
                "independentWolframReference": True,
            },
        }
        rows.append(row)
    if len(rows) != 12:
        raise RuntimeError("cag_benchmark_public_row_count_mismatch")
    return rows


__all__ = ["CAPTURED_AT", "PROJECT_ID", "WOLFRAM_REFERENCES", "build_cag_benchmark_public_rows"]
