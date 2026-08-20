"""Tests for the Wolfram CAG claim-verification evidence lane (#1457/#1460).

These tests exercise the real, live-path implementation in
``backend/agent_runtime/wolfram_cag_evidence.py`` and the public benchmark
cases in ``wolfram_cag_benchmark_cases.py``. No mocks live in the truth path:
the verifier is exercised against canonical inputs, and the fail-closed
``UNAVAILABLE`` path is asserted whenever no real provisioning evidence is
present.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime.wolfram_cag_evidence import (
    CagClaim,
    CagEvidenceError,
    CagEvidenceVerdict,
    DEFAULT_TOLERANCE_RULES,
    NormalizedCagResult,
    RECEIPT_SCHEMA_VERSION,
    ToleranceRule,
    VerificationInput,
    WolframCagReceiptV1,
    canonical_cag_sha256,
    canonical_cag_value,
    compare_exact_claim,
    compare_numeric_claim,
    unavailable_receipt,
    verify_cag_claim,
)
from backend.agent_runtime.wolfram_cag_benchmark_cases import (
    BENCHMARK_CASES,
    case_by_id,
    comparison_verdict,
)

REVISION = "a" * 40
RUN_ID = "cag-evidence-test-run"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _claim(
    *,
    claim_text: str = "17 * 23 equals 391",
    claim_value: str = "391",
    expected_result_type: str = "exact_number",
    domain: str = "arithmetic",
    runtime_revision: str = REVISION,
    sovereign_run_id: str = RUN_ID,
) -> CagClaim:
    return CagClaim(
        claim_text=claim_text,
        claim_value=claim_value,
        expected_result_type=expected_result_type,
        domain=domain,
        sovereign_run_id=sovereign_run_id,
        runtime_revision=runtime_revision,
    )


def _result(
    *,
    component_id: str = "wolfram.cag.compute",
    result_type: str = "exact_number",
    domain: str = "arithmetic",
    reference_value: str = "391",
    claim_value: str = "391",
    units: str = "",
    assumptions: tuple[str, ...] = ("decimal integers",),
    raw_payload: dict | None = None,
    response_status: int = 200,
    component_ready: bool = True,
) -> NormalizedCagResult:
    return NormalizedCagResult(
        component_id=component_id,
        result_type=result_type,
        domain=domain,
        assumptions=assumptions,
        units=units,
        reference_value=reference_value,
        claim_value=claim_value,
        provider_request_id="test-request",
        provider_response_uuid="test-response-uuid",
        response_status=response_status,
        component_ready=component_ready,
        raw_payload=raw_payload if raw_payload is not None else {"expression": "17*23", "result": 391},
    )


def _transport_receipt(
    *,
    component_status: str = "READY",
    verdict: str = "SUPPORTED",
    response_status: int = 200,
) -> dict:
    return {
        "capability_id": "wolfram.cag.compute",
        "component_status": component_status,
        "verdict": verdict,
        "response_status": response_status,
        "request_hash": "0" * 64,
        "response_hash": "1" * 64,
    }


_SENTINEL = object()


def _input(
    *,
    claim: CagClaim | None = None,
    result: NormalizedCagResult | None = None,
    transport_receipt=_SENTINEL,
    tolerance: ToleranceRule | None = None,
) -> VerificationInput:
    return VerificationInput(
        claim=claim or _claim(),
        input_text="evaluate 17*23",
        result=result or _result(),
        tolerance=tolerance or DEFAULT_TOLERANCE_RULES["exact_number"],
        transport_receipt=_transport_receipt() if transport_receipt is _SENTINEL else transport_receipt,
    )


# ---------------------------------------------------------------------------
# Canonicalization and secret safety
# ---------------------------------------------------------------------------

class TestCanonicalization:
    def test_canonical_value_roundtrips_safe_payload(self):
        canonical = canonical_cag_value({"a": 1, "b": ["x", True, None]})
        assert canonical == {"a": 1, "b": ["x", True, None]}

    def test_floats_are_forbidden(self):
        with pytest.raises(CagEvidenceError):
            canonical_cag_value(1.5)

    def test_secret_shaped_key_is_rejected(self):
        with pytest.raises(CagEvidenceError):
            canonical_cag_value({"api_key": "abc"})

    def test_safe_boolean_secret_key_is_allowed(self):
        assert canonical_cag_value({"mcp_revision_verified": True}) == {"mcp_revision_verified": True}

    def test_implicit_time_key_is_rejected(self):
        with pytest.raises(CagEvidenceError):
            canonical_cag_value({"timestamp": "now"})

    def test_nested_secret_is_rejected(self):
        with pytest.raises(CagEvidenceError):
            canonical_cag_value({"outer": {"token": "leak"}})

    def test_bytes_are_redacted_to_hash(self):
        out = canonical_cag_value(b"secret-bytes")
        assert set(out) == {"bytes", "sha256"}
        assert out["bytes"] == len(b"secret-bytes")


# ---------------------------------------------------------------------------
# Tolerance rules
# ---------------------------------------------------------------------------

class TestToleranceRule:
    def test_default_exact_tolerance_supports_equal_value(self):
        rule = DEFAULT_TOLERANCE_RULES["exact_number"]
        assert rule.within(391.0, 391.0)

    def test_relative_tolerance_admits_small_drift(self):
        rule = ToleranceRule("0", "1e-3", 9)
        assert rule.within(100.1, 100.0)

    def test_relative_tolerance_rejects_large_drift(self):
        rule = ToleranceRule("0", "1e-3", 9)
        assert not rule.within(105.0, 100.0)

    def test_absolute_tolerance(self):
        rule = ToleranceRule("1", "0", 9)
        assert rule.within(5.5, 6.0)
        assert not rule.within(5.0, 7.0)

    def test_nan_and_inf_fail_closed(self):
        rule = ToleranceRule("1", "1", 9)
        import math
        assert not rule.within(float("nan"), 1.0)
        assert not rule.within(float("inf"), 1.0)

    def test_negative_tolerance_rejected(self):
        with pytest.raises(CagEvidenceError):
            ToleranceRule("-1", "0", 9)

    def test_significant_digits_bounds(self):
        with pytest.raises(CagEvidenceError):
            ToleranceRule("0", "0", 0)
        with pytest.raises(CagEvidenceError):
            ToleranceRule("0", "0", 19)

    def test_non_decimal_rejected(self):
        with pytest.raises(CagEvidenceError):
            ToleranceRule("not-a-number", "0", 9)


# ---------------------------------------------------------------------------
# Claim and result contracts
# ---------------------------------------------------------------------------

class TestClaimContract:
    def test_valid_claim_hashes_stably(self):
        claim = _claim()
        assert claim.claim_hash == canonical_cag_sha256(claim.canonical_body())
        assert len(claim.claim_hash) == 64

    def test_empty_claim_text_rejected(self):
        with pytest.raises(CagEvidenceError):
            _claim(claim_text="   ")

    def test_invalid_result_type_rejected(self):
        with pytest.raises(CagEvidenceError):
            _claim(expected_result_type="bogus_type")

    def test_invalid_revision_rejected(self):
        with pytest.raises(CagEvidenceError):
            _claim(runtime_revision="not-a-sha")

    def test_empty_revision_allowed(self):
        claim = _claim(runtime_revision="")
        assert claim.runtime_revision == ""

    def test_claim_is_frozen(self):
        claim = _claim()
        with pytest.raises(FrozenInstanceError):
            claim.claim_text = "mutated"  # type: ignore[misc]


class TestNormalizedResult:
    def test_valid_result_hashes_stably(self):
        result = _result()
        assert result.result_hash == canonical_cag_sha256(result.canonical_body())

    def test_invalid_component_rejected(self):
        with pytest.raises(CagEvidenceError):
            _result(component_id="wolfram.cag.bogus")

    def test_secret_in_raw_payload_rejected(self):
        with pytest.raises(CagEvidenceError):
            _result(raw_payload={"token": "leak"})

    def test_float_in_raw_payload_rejected(self):
        with pytest.raises(CagEvidenceError):
            _result(raw_payload={"result": 1.5})

    def test_response_status_bounds(self):
        with pytest.raises(CagEvidenceError):
            _result(response_status=999)
        with pytest.raises(CagEvidenceError):
            _result(response_status=-1)


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

class TestComparison:
    def test_numeric_supported(self):
        assert compare_numeric_claim("391", "391", DEFAULT_TOLERANCE_RULES["exact_number"]) is CagEvidenceVerdict.SUPPORTED

    def test_numeric_contradicted(self):
        assert compare_numeric_claim("400", "391", DEFAULT_TOLERANCE_RULES["exact_number"]) is CagEvidenceVerdict.CONTRADICTED

    def test_numeric_non_parseable_is_inconclusive(self):
        assert compare_numeric_claim("fuzzy", "391", DEFAULT_TOLERANCE_RULES["exact_number"]) is CagEvidenceVerdict.INCONCLUSIVE

    def test_exact_supported(self):
        assert compare_exact_claim("3*x^2", "3*X^2") is CagEvidenceVerdict.SUPPORTED

    def test_exact_contradicted(self):
        assert compare_exact_claim("3*x^2", "2*x^2") is CagEvidenceVerdict.CONTRADICTED

    def test_exact_empty_is_inconclusive(self):
        assert compare_exact_claim("", "3*x^2") is CagEvidenceVerdict.INCONCLUSIVE


# ---------------------------------------------------------------------------
# Verification verdicts
# ---------------------------------------------------------------------------

class TestVerifyCagClaim:
    def test_supported_with_real_transport(self):
        receipt = verify_cag_claim(_input())
        assert receipt.verdict is CagEvidenceVerdict.SUPPORTED
        assert receipt.finding_codes == ()
        assert receipt.schema_version == RECEIPT_SCHEMA_VERSION

    def test_contradicted_value_mismatch(self):
        receipt = verify_cag_claim(_input(
            claim=_claim(claim_value="400", claim_text="17*23 equals 400"),
        ))
        assert receipt.verdict is CagEvidenceVerdict.CONTRADICTED
        assert "contradicted_value_mismatch" in receipt.finding_codes

    def test_unavailable_without_transport_receipt(self):
        receipt = verify_cag_claim(_input(transport_receipt=None))
        assert receipt.verdict is CagEvidenceVerdict.UNAVAILABLE
        assert "unavailable_no_transport_receipt" in receipt.finding_codes

    def test_unavailable_when_not_entitled(self):
        receipt = verify_cag_claim(_input(transport_receipt=_transport_receipt(component_status="NOT_ENTITLED")))
        assert receipt.verdict is CagEvidenceVerdict.UNAVAILABLE
        assert any(code.startswith("unavailable_component_status") for code in receipt.finding_codes)

    def test_unavailable_when_transport_verdict_unavailable(self):
        receipt = verify_cag_claim(_input(transport_receipt=_transport_receipt(verdict="UNAVAILABLE")))
        assert receipt.verdict is CagEvidenceVerdict.UNAVAILABLE

    def test_unavailable_when_non_2xx(self):
        receipt = verify_cag_claim(_input(transport_receipt=_transport_receipt(response_status=503)))
        assert receipt.verdict is CagEvidenceVerdict.UNAVAILABLE

    def test_inconclusive_result_type_mismatch(self):
        receipt = verify_cag_claim(_input(
            claim=_claim(expected_result_type="exact_number"),
            result=_result(result_type="symbolic_expression"),
        ))
        assert receipt.verdict is CagEvidenceVerdict.INCONCLUSIVE
        assert "inconclusive_result_type_mismatch" in receipt.finding_codes

    def test_inconclusive_domain_mismatch(self):
        receipt = verify_cag_claim(_input(
            claim=_claim(domain="arithmetic"),
            result=_result(domain="physics"),
            transport_receipt=_transport_receipt(),
        ))
        assert receipt.verdict is CagEvidenceVerdict.INCONCLUSIVE

    def test_inconclusive_missing_values(self):
        receipt = verify_cag_claim(_input(
            claim=_claim(claim_value=""),
            result=_result(reference_value="391"),
            transport_receipt=_transport_receipt(),
        ))
        assert receipt.verdict is CagEvidenceVerdict.INCONCLUSIVE

    def test_numeric_approximation_within_tolerance(self):
        receipt = verify_cag_claim(_input(
            claim=_claim(
                claim_text="pi ~ 3.14159265",
                claim_value="3.14159265",
                expected_result_type="numeric_approximation",
                domain="constants",
            ),
            result=_result(
                result_type="numeric_approximation",
                domain="constants",
                reference_value="3.14159265358979",
                raw_payload={"expression": "N[Pi,15]"},
            ),
            tolerance=ToleranceRule("1e-7", "1e-7", 9),
        ))
        assert receipt.verdict is CagEvidenceVerdict.SUPPORTED

    def test_numeric_approximation_outside_tolerance_is_contradicted(self):
        receipt = verify_cag_claim(_input(
            claim=_claim(
                claim_text="pi ~ 3.2",
                claim_value="3.2",
                expected_result_type="numeric_approximation",
                domain="constants",
            ),
            result=_result(
                result_type="numeric_approximation",
                domain="constants",
                reference_value="3.14159265358979",
                raw_payload={"expression": "N[Pi,15]"},
            ),
            tolerance=ToleranceRule("1e-7", "1e-7", 9),
        ))
        assert receipt.verdict is CagEvidenceVerdict.CONTRADICTED

    def test_symbolic_exact_comparison(self):
        receipt = verify_cag_claim(_input(
            claim=_claim(
                claim_text="d/dx x^3 = 3*x^2",
                claim_value="3*x^2",
                expected_result_type="symbolic_expression",
                domain="calculus",
            ),
            result=_result(
                component_id="wolfram.cag.compute",
                result_type="symbolic_expression",
                domain="calculus",
                reference_value="3*x^2",
                claim_value="3*x^2",
                raw_payload={"expression": "D[x^3,x]"},
            ),
            tolerance=DEFAULT_TOLERANCE_RULES["symbolic_expression"],
        ))
        assert receipt.verdict is CagEvidenceVerdict.SUPPORTED


# ---------------------------------------------------------------------------
# Receipt contract
# ---------------------------------------------------------------------------

class TestReceiptContract:
    def test_receipt_hashes_stably_and_excludes_recorded_at(self):
        receipt = verify_cag_claim(_input())
        body_a = receipt.canonical_body()
        # recorded_at is non-canonical provenance.
        assert "recorded_at" not in body_a
        assert receipt.receipt_sha256 == canonical_cag_sha256(body_a)
        assert len(receipt.receipt_sha256) == 64

    def test_receipt_to_dict_includes_provenance(self):
        receipt = verify_cag_claim(_input())
        rendered = receipt.to_dict()
        assert rendered["recorded_at"] == receipt.recorded_at
        assert rendered["receipt_sha256"] == receipt.receipt_sha256
        assert rendered["verdict"] == receipt.verdict.value

    def test_receipt_binds_claim_and_result_hashes(self):
        receipt = verify_cag_claim(_input())
        assert receipt.claim_hash == _claim().claim_hash
        assert receipt.result_hash == _result().result_hash

    def test_receipt_is_frozen(self):
        receipt = verify_cag_claim(_input())
        with pytest.raises(FrozenInstanceError):
            receipt.verdict = CagEvidenceVerdict.CONTRADICTED  # type: ignore[misc]

    def test_supported_with_finding_codes_rejected(self):
        with pytest.raises(CagEvidenceError):
            WolframCagReceiptV1(
                schema_version=RECEIPT_SCHEMA_VERSION,
                sovereign_run_id=RUN_ID,
                claim_hash="0" * 64,
                runtime_revision=REVISION,
                component_id="wolfram.cag.compute",
                contract_version="wolfram-cag-transport.v1",
                input_text="x",
                input_hash="0" * 64,
                domain="arithmetic",
                units="",
                assumptions=(),
                timeout_seconds=15,
                max_output_bytes=1_000_000,
                provider_request_id="",
                provider_response_uuid="",
                response_status=200,
                component_ready=True,
                result_type="exact_number",
                result_hash="0" * 64,
                tolerance=DEFAULT_TOLERANCE_RULES["exact_number"],
                latency_ms=0,
                quota_class="UNKNOWN",
                cost_class="UNKNOWN",
                verdict=CagEvidenceVerdict.SUPPORTED,
                finding_codes=("bogus",),
                bounded_summary="",
                recorded_at="",
            )

    def test_contradicted_requires_contradicted_finding(self):
        with pytest.raises(CagEvidenceError):
            WolframCagReceiptV1(
                schema_version=RECEIPT_SCHEMA_VERSION,
                sovereign_run_id=RUN_ID,
                claim_hash="0" * 64,
                runtime_revision=REVISION,
                component_id="wolfram.cag.compute",
                contract_version="wolfram-cag-transport.v1",
                input_text="x",
                input_hash="0" * 64,
                domain="arithmetic",
                units="",
                assumptions=(),
                timeout_seconds=15,
                max_output_bytes=1_000_000,
                provider_request_id="",
                provider_response_uuid="",
                response_status=200,
                component_ready=True,
                result_type="exact_number",
                result_hash="0" * 64,
                tolerance=DEFAULT_TOLERANCE_RULES["exact_number"],
                latency_ms=0,
                quota_class="UNKNOWN",
                cost_class="UNKNOWN",
                verdict=CagEvidenceVerdict.CONTRADICTED,
                finding_codes=(),
                bounded_summary="",
                recorded_at="",
            )

    def test_unavailable_requires_finding(self):
        with pytest.raises(CagEvidenceError):
            WolframCagReceiptV1(
                schema_version=RECEIPT_SCHEMA_VERSION,
                sovereign_run_id=RUN_ID,
                claim_hash="0" * 64,
                runtime_revision=REVISION,
                component_id="wolfram.cag.compute",
                contract_version="wolfram-cag-transport.v1",
                input_text="x",
                input_hash="0" * 64,
                domain="arithmetic",
                units="",
                assumptions=(),
                timeout_seconds=15,
                max_output_bytes=1_000_000,
                provider_request_id="",
                provider_response_uuid="",
                response_status=200,
                component_ready=True,
                result_type="exact_number",
                result_hash="0" * 64,
                tolerance=DEFAULT_TOLERANCE_RULES["exact_number"],
                latency_ms=0,
                quota_class="UNKNOWN",
                cost_class="UNKNOWN",
                verdict=CagEvidenceVerdict.UNAVAILABLE,
                finding_codes=(),
                bounded_summary="",
                recorded_at="",
            )

    def test_invalid_contract_version_rejected(self):
        with pytest.raises(CagEvidenceError):
            WolframCagReceiptV1(
                schema_version=RECEIPT_SCHEMA_VERSION,
                sovereign_run_id=RUN_ID,
                claim_hash="0" * 64,
                runtime_revision=REVISION,
                component_id="wolfram.cag.compute",
                contract_version="bogus-version",
                input_text="x",
                input_hash="0" * 64,
                domain="arithmetic",
                units="",
                assumptions=(),
                timeout_seconds=15,
                max_output_bytes=1_000_000,
                provider_request_id="",
                provider_response_uuid="",
                response_status=200,
                component_ready=True,
                result_type="exact_number",
                result_hash="0" * 64,
                tolerance=DEFAULT_TOLERANCE_RULES["exact_number"],
                latency_ms=0,
                quota_class="UNKNOWN",
                cost_class="UNKNOWN",
                verdict=CagEvidenceVerdict.UNAVAILABLE,
                finding_codes=("unavailable_test",),
                bounded_summary="",
                recorded_at="",
            )

    def test_no_verified_verdict_exists(self):
        # CAG evidence may never self-assert VERIFIED.
        assert not hasattr(CagEvidenceVerdict, "VERIFIED")
        assert {v.value for v in CagEvidenceVerdict} == {"SUPPORTED", "CONTRADICTED", "INCONCLUSIVE", "UNAVAILABLE"}


# ---------------------------------------------------------------------------
# Fail-closed path
# ---------------------------------------------------------------------------

class TestFailClosed:
    def test_unavailable_receipt_without_provisioning(self):
        receipt = unavailable_receipt(_input(transport_receipt=None))
        assert receipt.verdict is CagEvidenceVerdict.UNAVAILABLE
        assert "unavailable_no_provisioning_evidence" in receipt.finding_codes

    def test_fail_closed_does_not_promote_to_supported(self):
        receipt = verify_cag_claim(_input(transport_receipt=None))
        assert receipt.verdict is not CagEvidenceVerdict.SUPPORTED

    def test_degraded_component_is_unavailable(self):
        receipt = verify_cag_claim(_input(transport_receipt=_transport_receipt(component_status="DEGRADED")))
        assert receipt.verdict is CagEvidenceVerdict.UNAVAILABLE


# ---------------------------------------------------------------------------
# Replay determinism (>=20 replay/negative tests for #1460)
# ---------------------------------------------------------------------------

class TestReplayDeterminism:
    def test_same_inputs_produce_same_receipt_hash(self):
        r1 = verify_cag_claim(_input())
        r2 = verify_cag_claim(_input())
        assert r1.receipt_sha256 == r2.receipt_sha256

    def test_different_claim_value_changes_hash(self):
        r1 = verify_cag_claim(_input(claim=_claim(claim_value="391")))
        r2 = verify_cag_claim(_input(claim=_claim(claim_value="400")))
        assert r1.receipt_sha256 != r2.receipt_sha256

    def test_different_reference_changes_hash(self):
        r1 = verify_cag_claim(_input(result=_result(reference_value="391")))
        r2 = verify_cag_claim(_input(result=_result(reference_value="392")))
        assert r1.receipt_sha256 != r2.receipt_sha256

    def test_recorded_at_does_not_change_hash(self):
        i1 = _input()
        from dataclasses import replace
        i2 = replace(i1, recorded_at="2026-08-16T00:00:00Z")
        r1 = verify_cag_claim(i1)
        r2 = verify_cag_claim(i2)
        assert r1.receipt_sha256 == r2.receipt_sha256

    def test_different_component_changes_hash(self):
        r1 = verify_cag_claim(_input(result=_result(component_id="wolfram.cag.compute")))
        r2 = verify_cag_claim(_input(result=_result(component_id="wolfram.cag.results")))
        assert r1.receipt_sha256 != r2.receipt_sha256

    def test_different_tolerance_changes_hash(self):
        r1 = verify_cag_claim(_input(tolerance=ToleranceRule("0", "0", 18)))
        r2 = verify_cag_claim(_input(tolerance=ToleranceRule("1", "0", 18)))
        assert r1.receipt_sha256 != r2.receipt_sha256

    def test_replay_of_contradiction_stays_contradiction(self):
        r1 = verify_cag_claim(_input(claim=_claim(claim_value="400")))
        r2 = verify_cag_claim(_input(claim=_claim(claim_value="400")))
        assert r1.verdict is CagEvidenceVerdict.CONTRADICTED
        assert r1.verdict == r2.verdict
        assert r1.receipt_sha256 == r2.receipt_sha256

    def test_secret_value_never_in_receipt(self):
        receipt = verify_cag_claim(_input())
        rendered = str(receipt.to_dict())
        assert "secret" not in rendered.lower()
        assert "token" not in rendered.lower()
        assert "password" not in rendered.lower()

    def test_secret_payload_rejected_before_receipt(self):
        with pytest.raises(CagEvidenceError):
            _result(raw_payload={"api_key": "leak"})

    def test_contradiction_not_smoothed_by_judge(self):
        receipt = verify_cag_claim(_input(claim=_claim(claim_value="400")))
        assert receipt.verdict is CagEvidenceVerdict.CONTRADICTED

    def test_unit_conversion_supported(self):
        receipt = verify_cag_claim(_input(
            claim=_claim(
                claim_text="2.5 km = 2500 m",
                claim_value="2500",
                expected_result_type="unit_conversion",
                domain="units",
            ),
            result=_result(
                component_id="wolfram.cag.results",
                result_type="unit_conversion",
                domain="units",
                reference_value="2500",
                claim_value="2500",
                units="meters",
                raw_payload={"query": "2.5 km in m", "result": 2500},
            ),
            tolerance=DEFAULT_TOLERANCE_RULES["unit_conversion"],
        ))
        assert receipt.verdict is CagEvidenceVerdict.SUPPORTED

    def test_statistic_supported(self):
        receipt = verify_cag_claim(_input(
            claim=_claim(
                claim_text="mean of {2,4,6,8,10} = 6",
                claim_value="6",
                expected_result_type="statistic",
                domain="statistics",
            ),
            result=_result(
                component_id="wolfram.cag.results",
                result_type="statistic",
                domain="statistics",
                reference_value="6",
                claim_value="6",
                raw_payload={"query": "mean"},
            ),
            tolerance=DEFAULT_TOLERANCE_RULES["statistic"],
        ))
        assert receipt.verdict is CagEvidenceVerdict.SUPPORTED

    def test_optimization_supported(self):
        receipt = verify_cag_claim(_input(
            claim=_claim(
                claim_text="min (x-3)^2 = 0",
                claim_value="0",
                expected_result_type="optimization",
                domain="optimization",
            ),
            result=_result(
                component_id="wolfram.cag.compute",
                result_type="optimization",
                domain="optimization",
                reference_value="0",
                claim_value="0",
                raw_payload={"expression": "Minimize"},
            ),
            tolerance=DEFAULT_TOLERANCE_RULES["optimization"],
        ))
        assert receipt.verdict is CagEvidenceVerdict.SUPPORTED

    def test_datetime_supported(self):
        receipt = verify_cag_claim(_input(
            claim=_claim(
                claim_text="January 2026 has 31 days",
                claim_value="31",
                expected_result_type="datetime_calculation",
                domain="calendar",
            ),
            result=_result(
                component_id="wolfram.cag.results",
                result_type="datetime_calculation",
                domain="calendar",
                reference_value="31",
                claim_value="31",
                units="days",
                raw_payload={"query": "days in January 2026"},
            ),
            tolerance=DEFAULT_TOLERANCE_RULES["datetime_calculation"],
        ))
        assert receipt.verdict is CagEvidenceVerdict.SUPPORTED

    def test_structured_fact_supported(self):
        receipt = verify_cag_claim(_input(
            claim=_claim(
                claim_text="water boils at 100 degrees celsius",
                claim_value="100 degrees celsius",
                expected_result_type="structured_fact",
                domain="physical_chemistry",
            ),
            result=_result(
                component_id="wolfram.cag.context",
                result_type="structured_fact",
                domain="physical_chemistry",
                reference_value="100 degrees celsius",
                claim_value="100 degrees celsius",
                units="degrees celsius",
                raw_payload={"query": "boiling point of water"},
            ),
            tolerance=DEFAULT_TOLERANCE_RULES["structured_fact"],
        ))
        assert receipt.verdict is CagEvidenceVerdict.SUPPORTED

    def test_invalid_input_text_rejected(self):
        with pytest.raises(CagEvidenceError):
            VerificationInput(claim=_claim(), input_text="", result=_result(), tolerance=DEFAULT_TOLERANCE_RULES["exact_number"])

    def test_timeout_bounds_enforced(self):
        with pytest.raises(CagEvidenceError):
            VerificationInput(claim=_claim(), input_text="x", result=_result(), tolerance=DEFAULT_TOLERANCE_RULES["exact_number"], timeout_seconds=0)
        with pytest.raises(CagEvidenceError):
            VerificationInput(claim=_claim(), input_text="x", result=_result(), tolerance=DEFAULT_TOLERANCE_RULES["exact_number"], timeout_seconds=61)

    def test_max_output_bounds_enforced(self):
        with pytest.raises(CagEvidenceError):
            VerificationInput(claim=_claim(), input_text="x", result=_result(), tolerance=DEFAULT_TOLERANCE_RULES["exact_number"], max_output_bytes=0)
        with pytest.raises(CagEvidenceError):
            VerificationInput(claim=_claim(), input_text="x", result=_result(), tolerance=DEFAULT_TOLERANCE_RULES["exact_number"], max_output_bytes=2_000_000)

    def test_replay_across_all_benchmarks_deterministic(self):
        for case in BENCHMARK_CASES:
            i1 = _input(
                claim=case.to_claim(RUN_ID, REVISION),
                result=case.to_result(),
                tolerance=case.tolerance,
            )
            i2 = _input(
                claim=case.to_claim(RUN_ID, REVISION),
                result=case.to_result(),
                tolerance=case.tolerance,
            )
            assert verify_cag_claim(i1).receipt_sha256 == verify_cag_claim(i2).receipt_sha256


# ---------------------------------------------------------------------------
# Public benchmark cases (#1464)
# ---------------------------------------------------------------------------

class TestBenchmarkCases:
    def test_at_least_ten_public_cases(self):
        assert len(BENCHMARK_CASES) >= 10

    def test_case_ids_unique(self):
        ids = [c.case_id for c in BENCHMARK_CASES]
        assert len(ids) == len(set(ids))

    def test_case_by_id_resolves(self):
        assert case_by_id("cag-bench-001").title.startswith("Exact")

    def test_unknown_case_raises(self):
        with pytest.raises(KeyError):
            case_by_id("nope")

    def test_comparison_verdicts_match_expected(self):
        for case in BENCHMARK_CASES:
            assert comparison_verdict(case) == case.expected_comparison_verdict, case.case_id

    def test_benchmark_cases_are_secret_free(self):
        for case in BENCHMARK_CASES:
            # canonical_cag_value raises on secret-shaped fields.
            canonical_cag_value(case.raw_payload)
            rendered = str(case.raw_payload)
            assert "secret" not in rendered.lower()
            assert "token" not in rendered.lower()

    def test_benchmark_covers_all_components(self):
        components = {c.component_id for c in BENCHMARK_CASES}
        assert components == {
            "wolfram.cag.hints",
            "wolfram.cag.compute",
            "wolfram.cag.results",
            "wolfram.cag.context",
        }

    def test_benchmark_includes_contradicted_case(self):
        assert any(c.expected_comparison_verdict == "CONTRADICTED" for c in BENCHMARK_CASES)

    def test_benchmark_includes_inconclusive_case(self):
        assert any(c.expected_comparison_verdict == "INCONCLUSIVE" for c in BENCHMARK_CASES)

    def test_benchmark_cases_produce_unavailable_without_provisioning(self):
        # Without real provisioning evidence every public benchmark case must
        # honestly resolve to UNAVAILABLE, never SUPPORTED.
        for case in BENCHMARK_CASES:
            inputs = _input(
                claim=case.to_claim(RUN_ID, REVISION),
                result=case.to_result(),
                tolerance=case.tolerance,
                transport_receipt=None,
            )
            receipt = verify_cag_claim(inputs)
            assert receipt.verdict is CagEvidenceVerdict.UNAVAILABLE, case.case_id

    def test_benchmark_includes_provider_failure_case(self):
        # #1464 requires at least one provider-failure/degradation case.
        cases = [c for c in BENCHMARK_CASES if c.boundary == "provider_failure"]
        assert cases, "benchmark set must include a provider-failure case"

    def test_benchmark_includes_out_of_scope_case(self):
        # #1464 requires a case where CAG is correctly not responsible for
        # runtime/repository truth.
        cases = [c for c in BENCHMARK_CASES if c.boundary == "out_of_scope"]
        assert cases, "benchmark set must include an out-of-scope case"

    def test_boundary_cases_never_carry_reference_or_publish(self):
        for case in BENCHMARK_CASES:
            if not case.boundary:
                continue
            assert case.has_real_result is False, case.case_id
            assert case.publishable is False, case.case_id
            assert case.expected_comparison_verdict == "INCONCLUSIVE", case.case_id

    def test_provider_failure_case_degrades_to_unavailable(self):
        # A quota-exhausted/degraded provider must degrade honestly; the
        # verdict must never be smoothed into SUPPORTED.
        for case in BENCHMARK_CASES:
            if case.boundary != "provider_failure":
                continue
            for receipt_kwargs in (
                {"component_status": "DEGRADED", "response_status": 200},
                {"component_status": "READY", "response_status": 429},
                {"component_status": "READY", "response_status": 503},
            ):
                inputs = _input(
                    claim=case.to_claim(RUN_ID, REVISION),
                    result=case.to_result(),
                    tolerance=case.tolerance,
                    transport_receipt=_transport_receipt(**receipt_kwargs),
                )
                receipt = verify_cag_claim(inputs)
                assert receipt.verdict is CagEvidenceVerdict.UNAVAILABLE, (case.case_id, receipt_kwargs)

    def test_out_of_scope_case_never_supported(self):
        # Even with a fabricated READY transport receipt, CAG must never
        # support a runtime/repository truth claim: with no reference value
        # the honest verdict stays INCONCLUSIVE.
        for case in BENCHMARK_CASES:
            if case.boundary != "out_of_scope":
                continue
            inputs = _input(
                claim=case.to_claim(RUN_ID, REVISION),
                result=case.to_result(),
                tolerance=case.tolerance,
                transport_receipt=_transport_receipt(),
            )
            receipt = verify_cag_claim(inputs)
            assert receipt.verdict is CagEvidenceVerdict.INCONCLUSIVE, case.case_id
            assert receipt.verdict is not CagEvidenceVerdict.SUPPORTED, case.case_id


# ---------------------------------------------------------------------------
# Mirror parity
# ---------------------------------------------------------------------------

class TestMirrorParity:
    def test_canonical_and_mirror_evidence_modules_are_byte_equal(self):
        canonical = (ROOT / "backend" / "agent_runtime" / "wolfram_cag_evidence.py").read_bytes()
        mirror = (ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "wolfram_cag_evidence.py").read_bytes()
        assert canonical == mirror

    def test_canonical_and_mirror_benchmark_modules_are_byte_equal(self):
        canonical = (ROOT / "backend" / "agent_runtime" / "wolfram_cag_benchmark_cases.py").read_bytes()
        mirror = (ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "wolfram_cag_benchmark_cases.py").read_bytes()
        assert canonical == mirror
