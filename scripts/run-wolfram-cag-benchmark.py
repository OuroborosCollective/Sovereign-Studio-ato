#!/usr/bin/env python3
"""Reproducible public Wolfram CAG claim-check benchmark runner (#1464/#1465).

This is a deterministic, stdlib-only runner that turns each public benchmark
case from :mod:`agent_runtime.wolfram_cag_benchmark_cases` into a real,
machine-readable CAG evidence receipt. It exercises the *real* live-path
verifier in :mod:`agent_runtime.wolfram_cag_evidence`; it does not fake a live
Wolfram transport and does not invent a SUPPORTED verdict.

Truth boundary
---------------
Sovereign CAG provisioning (#1458) is not yet available, so no real CAG
transport receipt exists. For every case the runner therefore submits the
claim to :func:`verify_cag_claim` with ``transport_receipt=None``, which is
the honest fail-closed path: the verdict is ``UNAVAILABLE`` and the receipt
carries an ``unavailable_no_transport_receipt`` finding code.

The case fixtures also carry a deterministic *comparison* verdict
(:func:`comparison_verdict`) that expresses what the verifier *would* conclude
about the claim versus the reference value if a real transport result were
present. The runner reports this comparison verdict separately and never
promotes it to the transport receipt. This is the exact truth boundary the
evidence lane documents: CAG comparison logic is reproducibly verified without
ever faking a live API call, while the live path stays honestly UNAVAILABLE.

Usage
-----
    python scripts/run-wolfram-cag-benchmark.py            # all cases
    python scripts/run-wolfram-cag-benchmark.py --case cag-bench-001
    python scripts/run-wolfram-cag-benchmark.py --json     # machine-readable only

Exit status is non-zero if any case's recorded comparison verdict disagrees
with its ``expected_comparison_verdict``. The transport receipt is always
``UNAVAILABLE`` until #1458 provisions real CAG.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from agent_runtime.wolfram_cag_benchmark_cases import (  # noqa: E402
    BENCHMARK_CASES,
    BenchmarkCase,
    case_by_id,
    comparison_verdict,
)
from agent_runtime.wolfram_cag_evidence import (  # noqa: E402
    TRUTH_NOTICE,
    VerificationInput,
    WolframCagReceiptV1,
    verify_cag_claim,
)

SOVEREIGN_RUN_ID = os.environ.get("SOVEREIGN_CAG_RUN_ID", "public-benchmark-run")
RUNTIME_REVISION = os.environ.get(
    "SOVEREIGN_CAG_REVISION", "0" * 40
)
RECORDED_AT = os.environ.get("SOVEREIGN_CAG_RECORDED_AT", "")


def _build_verification_input(case: BenchmarkCase) -> VerificationInput:
    """Build the real verifier input for a benchmark case.

    ``transport_receipt`` is intentionally ``None`` so the live path is the
    honest fail-closed UNAVAILABLE receipt. The case's normalized result is
    still supplied so the receipt binds the real input/result hashes.
    """
    return VerificationInput(
        claim=case.to_claim(
            sovereign_run_id=SOVEREIGN_RUN_ID,
            runtime_revision=RUNTIME_REVISION,
        ),
        input_text=case.claim_text,
        result=case.to_result(),
        tolerance=case.tolerance,
        recorded_at=RECORDED_AT,
        transport_receipt=None,
    )


def _run_case(case: BenchmarkCase) -> dict[str, Any]:
    """Run one benchmark case through the real verifier and report honestly."""
    inputs = _build_verification_input(case)
    receipt: WolframCagReceiptV1 = verify_cag_claim(inputs)
    comparison = comparison_verdict(case)

    return {
        "case_id": case.case_id,
        "title": case.title,
        "component_id": case.component_id,
        "claim_text": case.claim_text,
        "claim_value": case.claim_value,
        "expected_result_type": case.expected_result_type,
        "domain": case.domain,
        "units": case.units,
        "has_real_result": case.has_real_result,
        "expected_comparison_verdict": case.expected_comparison_verdict,
        "comparison_verdict": comparison,
        "transport_receipt": receipt.to_dict(),
        "transport_verdict": receipt.verdict.value,
        "truth_notice": TRUTH_NOTICE,
    }


def _verify_no_secret_markers(receipt: dict[str, Any]) -> list[str]:
    """Scan one emitted receipt for secret-shaped *value* markers.

    Scans receipt values only (not structural key names) so that descriptive
    field names never produce false positives. Returns offending markers.
    """
    secret_markers = (
        "password", "passwd", "token", "authorization",
        "api_key", "apikey", "private_key", "client_secret", "cookie",
        "raw_prompt", "prompt_text", "file_content", "database_row",
    )
    found: list[str] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, str):
            folded = obj.casefold()
            for marker in secret_markers:
                if marker in folded:
                    found.append(marker)
        elif isinstance(obj, dict):
            for value in obj.values():
                _walk(value)
        elif isinstance(obj, (list, tuple)):
            for value in obj:
                _walk(value)

    _walk(receipt)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run reproducible public Wolfram CAG benchmark cases."
    )
    parser.add_argument(
        "--case",
        help="Run a single benchmark case by id (e.g. cag-bench-001).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON only (no human summary).",
    )
    args = parser.parse_args(argv)

    if args.case:
        try:
            cases = (case_by_id(args.case),)
        except KeyError as exc:
            print(json.dumps({"error": str(exc)}))
            return 2
    else:
        cases = BENCHMARK_CASES

    results = []
    mismatches: list[str] = []
    secret_findings: list[str] = []
    transport_regression: list[str] = []

    for case in cases:
        result = _run_case(case)
        results.append(result)

        if result["comparison_verdict"] != result["expected_comparison_verdict"]:
            mismatches.append(
                f"{case.case_id}: comparison {result['comparison_verdict']} "
                f"!= expected {result['expected_comparison_verdict']}"
            )

        leaked = _verify_no_secret_markers(result["transport_receipt"])
        if leaked:
            secret_findings.append(f"{case.case_id}: secret markers {leaked}")

        # The live transport path must be UNAVAILABLE without provisioning.
        if result["transport_verdict"] != "UNAVAILABLE":
            transport_regression.append(
                f"{case.case_id}: transport verdict {result['transport_verdict']} "
                "is not UNAVAILABLE (no real provisioning exists)"
            )

    summary = {
        "schemaVersion": "sovereign.wolfram-cag-benchmark.v1",
        "runId": SOVEREIGN_RUN_ID,
        "runtimeRevision": RUNTIME_REVISION,
        "caseCount": len(results),
        "truthNotice": TRUTH_NOTICE,
        "transportProvisioned": False,
        "transportStatus": "UNAVAILABLE",
        "provisioningBlocker": "#1458 (Wolfram owner provisioning) not available",
        "verdictMismatches": mismatches,
        "secretFindings": secret_findings,
        "transportRegressions": transport_regression,
        "cases": results,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(f"Wolfram CAG public benchmark — {len(results)} case(s)")
        print(f"  transport status: {summary['transportStatus']} "
              f"(provisioning blocked: {summary['provisioningBlocker']})")
        print(f"  run id: {summary['runId']}")
        print(f"  revision: {summary['runtimeRevision']}")
        print()
        for r in results:
            print(f"  [{r['case_id']}] {r['title']}")
            print(f"      claim: {r['claim_text']}")
            print(f"      transport verdict: {r['transport_verdict']}  "
                  f"(comparison would be: {r['comparison_verdict']})")
        print()
        if mismatches:
            print("VERDICT MISMATCHES:")
            for m in mismatches:
                print(f"  - {m}")
        if secret_findings:
            print("SECRET FINDINGS:")
            for s in secret_findings:
                print(f"  - {s}")
        if transport_regression:
            print("TRANSPORT REGRESSIONS:")
            for t in transport_regression:
                print(f"  - {t}")
        if not (mismatches or secret_findings or transport_regression):
            print("All cases: comparison verdicts match, no secrets, transport honestly UNAVAILABLE.")
        print()
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))

    if mismatches or secret_findings or transport_regression:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
