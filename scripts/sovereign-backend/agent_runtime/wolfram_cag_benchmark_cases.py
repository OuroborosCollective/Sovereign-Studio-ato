"""Public, reproducible Wolfram CAG claim-check benchmark cases (#1464/#1465).

Each case is a non-sensitive, fully reproducible ``LLM claim -> CAG check ->
evidence verdict`` scenario. The cases exercise the deterministic receipt
machinery in :mod:`wolfram_cag_evidence` across the result types required by
#1460: exact arithmetic, symbolic algebra, unit dimensions/conversions,
numeric approximation with explicit tolerance, statistics, optimization,
datetime calculation and structured facts with provenance.

Truth boundary
--------------
These cases are *deterministic contract fixtures*, not live Wolfram API calls
and not mocks in the truth path. Without real CAG provisioning (#1458) every
case's transport receipt honestly reports ``NOT_ENTITLED`` / ``UNAVAILABLE``,
and the verifier produces an honest ``UNAVAILABLE`` receipt. When a case is
marked ``has_real_result=True`` it carries a normalized reference result that
*would* be compared if a real transport receipt were present; the comparison
helpers are exercised directly in tests against these references so the
``SUPPORTED`` / ``CONTRADICTED`` / ``INCONCLUSIVE`` logic is reproducibly
verified without ever faking a live API call.

No private repositories, prompts, accounts, secrets or commercially restricted
data appear in any case. All values are elementary, public facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Mapping

from .wolfram_cag_evidence import (
    CagClaim,
    DEFAULT_TOLERANCE_RULES,
    NormalizedCagResult,
    ToleranceRule,
    compare_exact_claim,
    compare_numeric_claim,
)


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One public, reproducible claim-check scenario."""

    case_id: str
    title: str
    component_id: str
    claim_text: str
    claim_value: str
    expected_result_type: str
    domain: str
    reference_value: str
    units: str
    assumptions: tuple[str, ...]
    raw_payload: Mapping[str, Any]
    tolerance: ToleranceRule
    # The deterministic verdict the comparison helpers produce for the
    # reference value when a real result is present.
    expected_comparison_verdict: str
    # Whether this case carries a normalized reference result for direct
    # comparison. Cases without a reference stay INCONCLUSIVE/UNAVAILABLE.
    has_real_result: bool = True
    # Boundary classification: "" for normal reference cases,
    # "provider_failure" for degradation cases, "out_of_scope" for claims
    # CAG must never decide. Boundary cases never carry a real result.
    boundary: str = ""
    # Whether the case may enter the owner-confirmed public evidence
    # publication lane. Boundary cases are excluded: they have no
    # independent Wolfram reference and exist to prove honest degradation.
    publishable: bool = True

    def to_claim(self, sovereign_run_id: str, runtime_revision: str) -> CagClaim:
        return CagClaim(
            claim_text=self.claim_text,
            claim_value=self.claim_value,
            expected_result_type=self.expected_result_type,
            domain=self.domain,
            sovereign_run_id=sovereign_run_id,
            runtime_revision=runtime_revision,
        )

    def to_result(self, *, response_status: int = 200, component_ready: bool = True) -> NormalizedCagResult:
        return NormalizedCagResult(
            component_id=self.component_id,
            result_type=self.expected_result_type,
            domain=self.domain,
            assumptions=self.assumptions,
            units=self.units,
            reference_value=self.reference_value,
            claim_value=self.claim_value,
            provider_request_id="public-benchmark",
            provider_response_uuid="",
            response_status=response_status,
            component_ready=component_ready,
            raw_payload=self.raw_payload,
        )


def _case(
    case_id: str,
    title: str,
    component_id: str,
    claim_text: str,
    claim_value: str,
    expected_result_type: str,
    domain: str,
    reference_value: str,
    units: str,
    assumptions: tuple[str, ...],
    raw_payload: Mapping[str, Any],
    tolerance: ToleranceRule | None = None,
    expected_comparison_verdict: str = "SUPPORTED",
    has_real_result: bool = True,
    boundary: str = "",
    publishable: bool = True,
) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        title=title,
        component_id=component_id,
        claim_text=claim_text,
        claim_value=claim_value,
        expected_result_type=expected_result_type,
        domain=domain,
        reference_value=reference_value,
        units=units,
        assumptions=assumptions,
        raw_payload=raw_payload,
        tolerance=tolerance or DEFAULT_TOLERANCE_RULES[expected_result_type],
        expected_comparison_verdict=expected_comparison_verdict,
        has_real_result=has_real_result,
        boundary=boundary,
        publishable=publishable,
    )


# ---------------------------------------------------------------------------
# Public benchmark cases. All values are elementary, public, non-sensitive.
# ---------------------------------------------------------------------------

BENCHMARK_CASES: Final[tuple[BenchmarkCase, ...]] = (
    _case(
        "cag-bench-001",
        "Exact integer arithmetic",
        "wolfram.cag.compute",
        "17 * 23 equals 391",
        "391",
        "exact_number",
        "arithmetic",
        "391",
        "",
        ("decimal integers",),
        {"expression": "17*23", "result": 391},
    ),
    _case(
        "cag-bench-002",
        "Deliberately wrong arithmetic is contradicted",
        "wolfram.cag.compute",
        "17 * 23 equals 400",
        "400",
        "exact_number",
        "arithmetic",
        "391",
        "",
        ("decimal integers",),
        {"expression": "17*23", "result": 391},
        expected_comparison_verdict="CONTRADICTED",
    ),
    _case(
        "cag-bench-003",
        "Symbolic derivative",
        "wolfram.cag.compute",
        "derivative of x^3 with respect to x is 3*x^2",
        "3*x^2",
        "symbolic_expression",
        "calculus",
        "3*x^2",
        "",
        ("symbol x is real",),
        {"expression": "D[x^3,x]", "result": "3*x^2"},
    ),
    _case(
        "cag-bench-004",
        "Unit dimension of speed",
        "wolfram.cag.context",
        "speed has dimension length/time",
        "length/time",
        "unit_dimension",
        "physics",
        "length/time",
        "length/time",
        ("SI base dimensions",),
        {"query": "dimension of speed", "dimension": "length/time"},
    ),
    _case(
        "cag-bench-005",
        "Unit conversion kilometers to meters",
        "wolfram.cag.results",
        "2.5 kilometers equals 2500 meters",
        "2500",
        "unit_conversion",
        "units",
        "2500",
        "meters",
        ("1 km = 1000 m",),
        {"query": "2.5 km in m", "result": 2500, "units": "meters"},
    ),
    _case(
        "cag-bench-006",
        "Numeric approximation of pi within tolerance",
        "wolfram.cag.compute",
        "pi is approximately 3.14159265",
        "3.14159265",
        "numeric_approximation",
        "constants",
        "3.14159265358979",
        "",
        ("9 significant digits",),
        {"expression": "N[Pi,15]", "result": "3.14159265358979"},
        tolerance=ToleranceRule("1e-7", "1e-7", 9),
    ),
    _case(
        "cag-bench-007",
        "Numeric approximation outside tolerance is contradicted",
        "wolfram.cag.compute",
        "pi is approximately 3.2",
        "3.2",
        "numeric_approximation",
        "constants",
        "3.14159265358979",
        "",
        ("9 significant digits",),
        {"expression": "N[Pi,15]", "result": "3.14159265358979"},
        tolerance=ToleranceRule("1e-7", "1e-7", 9),
        expected_comparison_verdict="CONTRADICTED",
    ),
    _case(
        "cag-bench-008",
        "Statistical mean of a small set",
        "wolfram.cag.results",
        "the mean of 2, 4, 6, 8, 10 is 6",
        "6",
        "statistic",
        "statistics",
        "6",
        "",
        ("arithmetic mean",),
        {"query": "mean of {2,4,6,8,10}", "result": 6},
    ),
    _case(
        "cag-bench-009",
        "Optimization minimum value",
        "wolfram.cag.compute",
        "the minimum of (x-3)^2 over reals is 0",
        "0",
        "optimization",
        "optimization",
        "0",
        "",
        ("x is real",),
        {"expression": "Minimize[(x-3)^2,x]", "result": 0},
        tolerance=ToleranceRule("1e-9", "1e-6", 9),
    ),
    _case(
        "cag-bench-010",
        "Datetime days between two dates",
        "wolfram.cag.results",
        "there are 31 days in January 2026",
        "31",
        "datetime_calculation",
        "calendar",
        "31",
        "days",
        ("proleptic Gregorian calendar",),
        {"query": "days in January 2026", "result": 31, "units": "days"},
    ),
    _case(
        "cag-bench-011",
        "Structured fact with provenance",
        "wolfram.cag.context",
        "water boils at 100 degrees Celsius at standard pressure",
        "100 degrees celsius",
        "structured_fact",
        "physical_chemistry",
        "100 degrees celsius",
        "degrees celsius",
        ("standard atmospheric pressure 101.325 kPa",),
        {"query": "boiling point of water", "result": "100 degrees Celsius", "provenance": "public reference"},
    ),
    _case(
        "cag-bench-012",
        "Hint text for an unparseable claim is inconclusive",
        "wolfram.cag.hints",
        "the answer to everything is fuzzy",
        "",
        "text_hint",
        "general",
        "",
        "",
        ("no numeric reference available",),
        {"hint": "claim has no verifiable reference"},
        expected_comparison_verdict="INCONCLUSIVE",
        has_real_result=False,
    ),
    # Boundary case: provider failure / quota degradation (#1464). A failed
    # provider response must degrade honestly to UNAVAILABLE — never smoothed
    # into SUPPORTED and never published as if a reference existed.
    _case(
        "cag-bench-013",
        "Provider quota failure degrades honestly to UNAVAILABLE",
        "wolfram.cag.compute",
        "the sum of the first 100 positive integers is 5050",
        "5050",
        "exact_number",
        "arithmetic",
        "",
        "",
        ("provider returned quota exhaustion; no result body",),
        {"expression": "sum i, i=1..100", "provider_status": "quota_exceeded"},
        expected_comparison_verdict="INCONCLUSIVE",
        has_real_result=False,
        boundary="provider_failure",
        publishable=False,
    ),
    # Boundary case: runtime/repository truth is out of CAG scope (#1464).
    # CAG is a supplemental compute counter-check; it must never decide
    # runtime, deployment, PatchMon or repository truth claims.
    _case(
        "cag-bench-014",
        "Runtime truth claim is outside CAG responsibility",
        "wolfram.cag.context",
        "the Sovereign backend deployment is currently healthy",
        "healthy",
        "structured_fact",
        "runtime_state",
        "",
        "",
        ("CAG cannot verify runtime, deployment or repository truth",),
        {"query": "is the deployment healthy", "scope": "runtime_truth"},
        expected_comparison_verdict="INCONCLUSIVE",
        has_real_result=False,
        boundary="out_of_scope",
        publishable=False,
    ),
)


_BOUNDARY_KINDS: Final[frozenset[str]] = frozenset({"provider_failure", "out_of_scope"})


def _validate_cases() -> None:
    """Fail-closed invariants for the benchmark fixture set."""
    seen: set[str] = set()
    for case in BENCHMARK_CASES:
        if case.case_id in seen:
            raise ValueError(f"duplicate benchmark case id: {case.case_id}")
        seen.add(case.case_id)
        if case.boundary and case.boundary not in _BOUNDARY_KINDS:
            raise ValueError(f"unknown boundary kind {case.boundary!r} for {case.case_id}")
        if case.boundary:
            # Boundary cases must never pretend a real reference exists.
            if case.has_real_result:
                raise ValueError(f"boundary case {case.case_id} must not carry a real result")
            if case.publishable:
                raise ValueError(f"boundary case {case.case_id} must not be publishable")
            if case.expected_comparison_verdict != "INCONCLUSIVE":
                raise ValueError(f"boundary case {case.case_id} must expect INCONCLUSIVE")


_validate_cases()


def case_by_id(case_id: str) -> BenchmarkCase:
    for case in BENCHMARK_CASES:
        if case.case_id == case_id:
            return case
    raise KeyError(f"unknown benchmark case: {case_id}")


def comparison_verdict(case: BenchmarkCase) -> str:
    """Deterministically evaluate a case's comparison verdict from its values.

    Mirrors the verifier's comparison logic without requiring a live transport
    receipt, so the public benchmark is reproducible from the fixtures alone.
    """
    if not case.has_real_result:
        return "INCONCLUSIVE"
    numeric_types = {"numeric_approximation", "statistic", "optimization", "exact_number", "unit_conversion"}
    if case.expected_result_type in numeric_types:
        return compare_numeric_claim(case.claim_value, case.reference_value, case.tolerance).value
    return compare_exact_claim(case.claim_value, case.reference_value).value


__all__ = [
    "BENCHMARK_CASES",
    "BenchmarkCase",
    "case_by_id",
    "comparison_verdict",
]
