"""Tests for the Wolfram CAG deterministic claim-verification receipt lane.

These tests exercise the *real* canonical implementation at
``backend/agent_runtime/wolfram_cag_receipts.py`` (no copied logic). They
cover Issue #1460 acceptance criteria:

- versioned and closed receipt schema
- secret-free canonicalisation / hashing of input and result
- per-result-type explicit precision / tolerance
- at least 20 replay / negative tests
- deliberately wrong LLM claims are recognised as ``CONTRADICTED``
- undecidable or provider-missing results stay ``INCONCLUSIVE`` /
  ``UNAVAILABLE``
- CAG evidence never replaces PatchMon / GitHub / DB / container readback
- the receipt can be bound to an OTBA-style attestation (#1450)
- byte-equal mirror parity
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL = _REPO_ROOT / "backend" / "agent_runtime" / "wolfram_cag_receipts.py"
_MIRROR = (
    _REPO_ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "wolfram_cag_receipts.py"
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


receipts = _load_module(_CANONICAL, "wolfram_cag_receipts_canonical")


# ---------------------------------------------------------------------------
# Shared builders
# ---------------------------------------------------------------------------

def _receipt(**over) -> "receipts.WolframCagReceiptV1":
    base = dict(
        sovereign_run="run-1",
        tool_chain="tc",
        step="s1",
        repository_revision=None,
        runtime_revision=None,
        component="cag_compute",
        endpoint_contract_version="cag.compute.v1",
        cag_input=receipts.CagInput(expression="2+2"),
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.EXACT_ARITHMETIC,
            canonical_value="4",
            numeric_value=4.0,
        ),
        claim=receipts.CagClaim(claim_value="4", claim_numeric=4.0),
        evidence_time=1000,
    )
    base.update(over)
    return receipts.build_receipt(**base)


# ---------------------------------------------------------------------------
# Mirror parity
# ---------------------------------------------------------------------------


def test_mirror_byte_identical() -> None:
    assert _CANONICAL.is_file()
    assert _MIRROR.is_file()
    assert (
        hashlib.sha256(_CANONICAL.read_bytes()).hexdigest()
        == hashlib.sha256(_MIRROR.read_bytes()).hexdigest()
    ), "wolfram_cag_receipts.py mirror drift: canonical and mirror must stay byte-identical"


def test_mirror_imports_identically() -> None:
    mirror = _load_module(_MIRROR, "wolfram_cag_receipts_mirror")
    assert mirror.SCHEMA_VERSION == receipts.SCHEMA_VERSION
    assert [n for n in dir(mirror) if not n.startswith("__")] == [
        n for n in dir(receipts) if not n.startswith("__")
    ]


# ---------------------------------------------------------------------------
# Schema version / closed shape
# ---------------------------------------------------------------------------


def test_schema_version_is_v1_and_closed() -> None:
    assert receipts.SCHEMA_VERSION == "sovereign.wolfram-cag-receipt.v1"
    r = _receipt()
    body = r.to_receipt_dict()
    receipts.validate_closed(body)


def test_validate_closed_rejects_extra_keys() -> None:
    r = _receipt()
    body = r.to_receipt_dict()
    body["smuggledTruth"] = "no"
    with pytest.raises(receipts.CagReceiptError, match="unknown keys"):
        receipts.validate_closed(body)


def test_validate_closed_rejects_missing_keys() -> None:
    r = _receipt()
    body = r.to_receipt_dict()
    del body["verdict"]
    with pytest.raises(receipts.CagReceiptError, match="missing closed-schema"):
        receipts.validate_closed(body)


def test_validate_closed_rejects_wrong_schema_version() -> None:
    r = _receipt()
    body = r.to_receipt_dict()
    body["schemaVersion"] = "sovereign.wolfram-cag-receipt.v2"
    with pytest.raises(receipts.CagReceiptError, match="schemaVersion"):
        receipts.validate_closed(body)


def test_receipt_dict_key_set_is_exactly_closed() -> None:
    r = _receipt()
    keys = set(r.to_receipt_dict().keys())
    # The closed key set is fixed; this guards against accidental growth.
    assert keys == {
        "schemaVersion",
        "canonicalization",
        "sovereignRun",
        "toolChain",
        "step",
        "repositoryRevision",
        "runtimeRevision",
        "component",
        "endpointContractVersion",
        "input",
        "inputHash",
        "timeLimitMs",
        "outputLimitBytes",
        "providerRequestId",
        "providerResponseId",
        "result",
        "resultHash",
        "comparableShapeKey",
        "claim",
        "tolerance",
        "cost",
        "verdict",
        "verdictReason",
        "evidenceTime",
        "attestationId",
        "attestationHash",
        "independentSafetyLanesUnaffected",
        "judgeMayNotSmooth",
        "doesNotReplace",
        "receiptHash",
    }


# ---------------------------------------------------------------------------
# Secret-free canonicalisation / hashing
# ---------------------------------------------------------------------------


def test_input_hash_is_secret_free_and_deterministic() -> None:
    a = receipts.CagInput(expression="2+2", assumptions=("x>0",))
    b = receipts.CagInput(expression="2+2", assumptions=("x>0",))
    assert a.input_hash() == b.input_hash()
    assert a.input_hash().startswith("sha256:") or len(a.input_hash()) == 64


def test_input_hash_distinguishes_different_inputs() -> None:
    a = receipts.CagInput(expression="2+2")
    b = receipts.CagInput(expression="3+3")
    assert a.input_hash() != b.input_hash()


def test_input_rejects_secret_shaped_expression() -> None:
    with pytest.raises(receipts.CagReceiptError, match="secret-shaped"):
        receipts.CagInput(expression="api_key=abc123def456hij")


def test_result_hash_excludes_raw_debug_blob() -> None:
    a = receipts.CagResult(
        result_type=receipts.ResultType.EXACT_ARITHMETIC,
        canonical_value="4",
        raw="debug-blob-A",
    )
    b = receipts.CagResult(
        result_type=receipts.ResultType.EXACT_ARITHMETIC,
        canonical_value="4",
        raw="debug-blob-B",
    )
    assert a.result_hash() == b.result_hash()


def test_result_rejects_secret_in_canonical_value() -> None:
    with pytest.raises(receipts.CagReceiptError, match="secret-shaped"):
        receipts.CagResult(
            result_type=receipts.ResultType.STRUCTURED_FACT,
            canonical_value="token=abcdef1234567890",
        )


def test_public_json_is_sorted_and_secret_free() -> None:
    r = _receipt()
    text = r.to_public_json()
    # Sorted keys => reproducible byte order.
    assert text == json.dumps(
        json.loads(text), sort_keys=True, ensure_ascii=True, separators=(",", ":")
    )
    assert "Bearer " not in text
    assert "ghp_" not in text


# ---------------------------------------------------------------------------
# Per-type tolerance / precision
# ---------------------------------------------------------------------------


def test_exact_arithmetic_supported_and_contradicted() -> None:
    assert _receipt().verdict is receipts.CagVerdict.SUPPORTED
    bad = _receipt(claim=receipts.CagClaim(claim_value="5", claim_numeric=5.0))
    assert bad.verdict is receipts.CagVerdict.CONTRADICTED


def test_symbolic_algebra_exact_string() -> None:
    r = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.SYMBOLIC_ALGEBRA,
            canonical_value="(x^3)/3",
        ),
        claim=receipts.CagClaim(claim_value="(x^3)/3"),
    )
    assert r.verdict is receipts.CagVerdict.SUPPORTED
    bad = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.SYMBOLIC_ALGEBRA,
            canonical_value="(x^3)/3",
        ),
        claim=receipts.CagClaim(claim_value="(x^3)/4"),
    )
    assert bad.verdict is receipts.CagVerdict.CONTRADICTED


def test_tolerance_override_honored_only_for_approximation() -> None:
    # A caller-supplied loose tolerance is honoured for numerical.
    loose = receipts.ToleranceRule(
        receipts.ResultType.NUMERICAL_APPROXIMATION,
        absolute=1.0,
        relative=0.0,
        exact=False,
    )
    r = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.NUMERICAL_APPROXIMATION,
            canonical_value="10",
            numeric_value=10.0,
        ),
        claim=receipts.CagClaim(claim_numeric=10.5),
        tolerance_override=loose,
    )
    assert r.verdict is receipts.CagVerdict.SUPPORTED
    # The same loose override is ignored for an exact result type.
    bad_loose = receipts.ToleranceRule(
        receipts.ResultType.EXACT_ARITHMETIC,
        absolute=100.0,
        relative=0.0,
        exact=False,
    )
    exact_bad = _receipt(
        claim=receipts.CagClaim(claim_value="5", claim_numeric=5.0),
        tolerance_override=bad_loose,
    )
    assert exact_bad.verdict is receipts.CagVerdict.CONTRADICTED
    assert exact_bad.tolerance.exact is True


def test_unit_dimension_within_tiny_band() -> None:
    # 1000 m == 1 km; result in m, claim in km with conversion factor 1000.
    r = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.UNIT_DIMENSION,
            canonical_value="1000",
            numeric_value=1000.0,
            units="m",
        ),
        claim=receipts.CagClaim(claim_numeric=1.0, claim_units="km"),
        unit_conversion_factor=1000.0,
    )
    assert r.verdict is receipts.CagVerdict.SUPPORTED
    bad = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.UNIT_DIMENSION,
            canonical_value="1000",
            numeric_value=1000.0,
            units="m",
        ),
        claim=receipts.CagClaim(claim_numeric=2.0, claim_units="km"),
        unit_conversion_factor=1000.0,
    )
    assert bad.verdict is receipts.CagVerdict.CONTRADICTED


def test_unit_dimension_inconclusive_without_conversion_factor() -> None:
    r = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.UNIT_DIMENSION,
            canonical_value="1000",
            numeric_value=1000.0,
            units="m",
        ),
        claim=receipts.CagClaim(claim_numeric=1.0, claim_units="km"),
    )
    assert r.verdict is receipts.CagVerdict.INCONCLUSIVE


def test_statistics_within_default_tolerance() -> None:
    r = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.STATISTICS_DISTRIBUTION,
            canonical_value="0.5",
            numeric_value=0.5,
        ),
        claim=receipts.CagClaim(claim_numeric=0.5000001),
    )
    assert r.verdict is receipts.CagVerdict.SUPPORTED
    bad = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.STATISTICS_DISTRIBUTION,
            canonical_value="0.5",
            numeric_value=0.5,
        ),
        claim=receipts.CagClaim(claim_numeric=0.9),
    )
    assert bad.verdict is receipts.CagVerdict.CONTRADICTED


def test_optimization_feasibility_axis() -> None:
    r = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.OPTIMIZATION_CONSTRAINT,
            canonical_value="feasible",
        ),
        claim=receipts.CagClaim(feasible=True),
    )
    assert r.verdict is receipts.CagVerdict.SUPPORTED
    bad = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.OPTIMIZATION_CONSTRAINT,
            canonical_value="infeasible",
        ),
        claim=receipts.CagClaim(feasible=True),
    )
    assert bad.verdict is receipts.CagVerdict.CONTRADICTED


def test_time_date_exact_normalised_string() -> None:
    r = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.TIME_DATE,
            canonical_value="2026-08-18T00:00:00Z",
        ),
        claim=receipts.CagClaim(claim_value="2026-08-18T00:00:00Z"),
    )
    assert r.verdict is receipts.CagVerdict.SUPPORTED
    bad = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.TIME_DATE,
            canonical_value="2026-08-18T00:00:00Z",
        ),
        claim=receipts.CagClaim(claim_value="2026-08-19T00:00:00Z"),
    )
    assert bad.verdict is receipts.CagVerdict.CONTRADICTED


def test_structured_fact_with_provenance() -> None:
    prov = receipts.Provenance(
        source="WolframAlpha:CountryPopulation",
        retrieved_at=1000,
        source_id="DE-2026",
        extra={"iso": "DE"},
    )
    r = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.STRUCTURED_FACT,
            canonical_value="Germany",
            provenance=prov,
        ),
        claim=receipts.CagClaim(claim_value="Germany"),
    )
    assert r.verdict is receipts.CagVerdict.SUPPORTED
    assert r.cag_result.provenance is not None
    assert r.cag_result.provenance.source == "WolframAlpha:CountryPopulation"


# ---------------------------------------------------------------------------
# Verdict: INCONCLUSIVE / UNAVAILABLE
# ---------------------------------------------------------------------------


def test_unavailable_when_provider_returns_no_result() -> None:
    r = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.EXACT_ARITHMETIC,
            canonical_value=None,
            available=False,
        ),
        claim=receipts.CagClaim(claim_value="42"),
    )
    assert r.verdict is receipts.CagVerdict.UNAVAILABLE


def test_inconclusive_when_claim_not_on_comparable_axis() -> None:
    # Numeric claim against an exact result that has no numeric projection.
    r = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.EXACT_ARITHMETIC,
            canonical_value="4",
            numeric_value=None,
        ),
        claim=receipts.CagClaim(claim_numeric=4.0),
    )
    assert r.verdict is receipts.CagVerdict.INCONCLUSIVE


def test_inconclusive_when_numeric_claim_against_symbolic_only() -> None:
    r = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.SYMBOLIC_ALGEBRA,
            canonical_value="(x^3)/3",
            numeric_value=None,
        ),
        claim=receipts.CagClaim(claim_numeric=3.0),
    )
    assert r.verdict is receipts.CagVerdict.INCONCLUSIVE


# ---------------------------------------------------------------------------
# Determinism: comparable shape, not wall-clock identity
# ---------------------------------------------------------------------------


def test_comparable_shape_key_stable_across_time() -> None:
    a = _receipt(evidence_time=1)
    b = _receipt(evidence_time=99999)
    assert a.comparable_shape_key() == b.comparable_shape_key()
    assert a.input_hash() == b.input_hash()
    # Receipt hash *does* bind evidence_time (it is bound metadata).
    assert a.receipt_hash() != b.receipt_hash()


def test_comparable_shape_key_changes_with_contract() -> None:
    a = _receipt(endpoint_contract_version="cag.compute.v1")
    b = _receipt(endpoint_contract_version="cag.compute.v2")
    assert a.comparable_shape_key() != b.comparable_shape_key()


def test_float_noise_does_not_break_shape_key() -> None:
    # Two results that agree in canonical shape but differ in float noise.
    a = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.NUMERICAL_APPROXIMATION,
            canonical_value="3.141592653589793",
            numeric_value=3.141592653589793,
        ),
        claim=receipts.CagClaim(claim_numeric=3.141592653589793),
        evidence_time=1,
    )
    b = _receipt(
        cag_result=receipts.CagResult(
            result_type=receipts.ResultType.NUMERICAL_APPROXIMATION,
            canonical_value="3.141592653589793",
            numeric_value=3.141592653589794,
        ),
        claim=receipts.CagClaim(claim_numeric=3.141592653589794),
        evidence_time=2,
    )
    assert a.comparable_shape_key() == b.comparable_shape_key()


def test_replay_deterministic_hash() -> None:
    a = _receipt()
    b = _receipt()
    assert a.receipt_hash() == b.receipt_hash()
    assert a.to_public_json() == b.to_public_json()


# ---------------------------------------------------------------------------
# CAG never replaces hard safety readbacks; Judge may not smooth
# ---------------------------------------------------------------------------


def test_cag_does_not_replace_safety_lanes() -> None:
    r = _receipt()
    assert r.independent_safety_lanes_unaffected is True
    assert "patchmon" in r.does_not_replace
    assert "github" in r.does_not_replace
    assert "database" in r.does_not_replace
    assert "container_readback" in r.does_not_replace


def test_judge_may_not_smooth_contradicted() -> None:
    r = _receipt(claim=receipts.CagClaim(claim_value="5", claim_numeric=5.0))
    assert r.verdict is receipts.CagVerdict.CONTRADICTED
    assert r.judge_may_not_smooth is True


def test_verdict_is_computed_not_injected() -> None:
    # build_receipt does not accept a verdict kwarg; the counter-check is
    # derived from (claim, result, tolerance).
    import inspect

    sig = inspect.signature(receipts.build_receipt)
    assert "verdict" not in sig.parameters


# ---------------------------------------------------------------------------
# Attestation binding (#1450 / OTBA-style)
# ---------------------------------------------------------------------------


def test_bind_attestation() -> None:
    r = _receipt()
    bound = r.bind_attestation(
        attestation_id="otba-1", attestation_hash="a" * 64
    )
    assert bound.attestation_id == "otba-1"
    assert bound.attestation_hash == "a" * 64
    # Binding changes the receipt hash (it is part of the closed body).
    assert bound.receipt_hash() != r.receipt_hash()
    receipts.validate_closed(bound.to_receipt_dict())


def test_bind_attestation_rejects_invalid_hash() -> None:
    r = _receipt()
    with pytest.raises(receipts.CagReceiptError, match="attestation_hash"):
        r.bind_attestation(attestation_id="otba-1", attestation_hash="short")


# ---------------------------------------------------------------------------
# Input validation / negative boundaries
# ---------------------------------------------------------------------------


def test_endpoint_contract_version_must_be_valid() -> None:
    with pytest.raises(receipts.CagReceiptError, match="contract revision"):
        _receipt(endpoint_contract_version="Bad Version!")


def test_repository_revision_must_be_sha_or_digest() -> None:
    with pytest.raises(receipts.CagReceiptError, match="repository_revision"):
        _receipt(repository_revision="not-a-sha")


def test_repository_revision_accepts_sha40_and_digest() -> None:
    _receipt(repository_revision="0" * 40)
    _receipt(repository_revision="sha256:" + "0" * 64)


def test_provider_ids_validated() -> None:
    with pytest.raises(receipts.CagReceiptError, match="provider_request_id"):
        _receipt(provider_request_id="bad id with space")


def test_too_many_assumptions_rejected() -> None:
    many = tuple(f"a{i}" for i in range(receipts._MAX_ASSUMPTIONS + 1))
    with pytest.raises(receipts.CagReceiptError, match="too many assumptions"):
        receipts.CagInput(expression="x", assumptions=many)


def test_claim_must_carry_something() -> None:
    with pytest.raises(receipts.CagReceiptError, match="must carry"):
        receipts.CagClaim()


def test_cost_metadata_is_secret_free() -> None:
    cost = receipts.CostMetadata(
        runtime_ms=12, cost_unit="credits", cost_per_unit=0.001, units_consumed=1.0
    )
    d = cost.canonical_dict()
    assert "api_key" not in str(d).lower()
    _receipt(cost=cost)


def test_provenance_rejects_secret_extra() -> None:
    with pytest.raises(receipts.CagReceiptError, match="secret-shaped"):
        receipts.Provenance(
            source="src", extra={"x": "api_key=abcdef1234567890"}
        )
