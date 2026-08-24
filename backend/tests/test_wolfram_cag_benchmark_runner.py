"""Tests for the public Wolfram CAG benchmark runner (#1457/#1464).

These tests exercise the real, live-path implementation in
``backend/agent_runtime/wolfram_cag_benchmark_runner.py`` against the real
public fixtures (``wolfram_cag_benchmark_cases.py``) and the real evidence
verifier (``wolfram_cag_evidence.py``). No mocks live in the truth path:
the fail-closed ``UNAVAILABLE`` path is asserted whenever no real #1458
provisioning evidence is present, and fixture values are never promoted to
``SUPPORTED``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from backend.agent_runtime.wolfram_cag_benchmark_cases import (  # noqa: E402
    BENCHMARK_CASES,
    case_by_id,
    comparison_verdict,
)
from backend.agent_runtime.wolfram_cag_benchmark_runner import (  # noqa: E402
    REPORT_SCHEMA_VERSION,
    BenchmarkReport,
    render_markdown_report,
    run_benchmark_case,
    run_benchmark_suite,
)
from backend.agent_runtime.wolfram_cag_evidence import (  # noqa: E402
    CagEvidenceError,
    CagEvidenceVerdict,
    TRUTH_NOTICE,
)

CANONICAL_PATH = ROOT / "backend" / "agent_runtime" / "wolfram_cag_benchmark_runner.py"
MIRROR_PATH = ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "wolfram_cag_benchmark_runner.py"

RUN_ID = "cag-bench-test"
REVISION = "7b3e60de39e2c5d52ba8da5086a7c234c38106fb"

# The public fixtures deliberately include refuted and unverifiable claims so
# the demo can never render an all-green wall.
EXPECTED_COMPARISON = {
    "cag-bench-002": CagEvidenceVerdict.CONTRADICTED,
    "cag-bench-007": CagEvidenceVerdict.CONTRADICTED,
    "cag-bench-012": CagEvidenceVerdict.INCONCLUSIVE,
}


def _run_suite(**kwargs) -> BenchmarkReport:
    params = {"sovereign_run_id": RUN_ID, "runtime_revision": REVISION}
    params.update(kwargs)
    return run_benchmark_suite(**params)


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


def test_suite_runs_all_public_fixtures_in_order():
    report = _run_suite()
    assert [p.case_id for p in report.projections] == [c.case_id for c in BENCHMARK_CASES]
    body = report.canonical_body()
    assert body["contract_version"] == "wolfram-cag-transport.v1"
    assert body["schema_version"] == REPORT_SCHEMA_VERSION
    assert report.to_dict()["truth_notice"] == TRUTH_NOTICE


def test_suite_is_deterministic_for_same_parameters():
    first = _run_suite()
    second = _run_suite()
    assert first.report_sha256 == second.report_sha256
    assert first.canonical_body() == second.canonical_body()
    assert render_markdown_report(first) == render_markdown_report(second)


def test_canonical_body_is_json_serializable_with_stable_sha():
    report = _run_suite()
    payload = json.dumps(report.canonical_body(), sort_keys=True, separators=(",", ":"))
    assert json.loads(payload) == report.canonical_body()
    assert len(report.report_sha256) == 64
    int(report.report_sha256, 16)


def test_projection_shows_claim_input_reference_and_both_verdicts():
    report = _run_suite()
    case = case_by_id("cag-bench-001")
    projection = report.projections[0]
    assert projection.case_id == case.case_id
    assert projection.claim_text == case.claim_text
    assert projection.receipt.input_text == f"verify claim: {case.claim_text}"
    assert projection.receipt.component_id == case.component_id
    assert projection.receipt.result_hash == case.to_result().result_hash
    assert projection.comparison_verdict == CagEvidenceVerdict(comparison_verdict(case))
    assert len(projection.claim_hash) == 64
    assert len(projection.receipt.receipt_sha256) == 64


def test_every_fixture_comparison_verdict_matches_contract():
    report = _run_suite()
    for projection in report.projections:
        assert projection.comparison_verdict.value == comparison_verdict(case_by_id(projection.case_id))


def test_demo_is_never_all_green():
    report = _run_suite()
    verdicts = {p.case_id: p.comparison_verdict for p in report.projections}
    for case_id, expected in EXPECTED_COMPARISON.items():
        assert verdicts[case_id] == expected
    assert any(v == CagEvidenceVerdict.CONTRADICTED for v in verdicts.values())
    assert any(v == CagEvidenceVerdict.INCONCLUSIVE for v in verdicts.values())


def test_case_subset_selection_and_unknown_case():
    report = _run_suite(case_ids=("cag-bench-003", "cag-bench-001"))
    assert [p.case_id for p in report.projections] == ["cag-bench-003", "cag-bench-001"]
    with pytest.raises(KeyError):
        _run_suite(case_ids=("cag-bench-999",))


def test_empty_case_selection_fails_closed():
    with pytest.raises(CagEvidenceError):
        _run_suite(case_ids=())


# ---------------------------------------------------------------------------
# Truth boundary: fail-closed without real provisioning evidence
# ---------------------------------------------------------------------------


def test_evidence_verdict_is_unavailable_without_transport_receipt():
    report = _run_suite()
    for projection in report.projections:
        assert projection.receipt.verdict == CagEvidenceVerdict.UNAVAILABLE
        assert "unavailable_no_transport_receipt" in projection.receipt.finding_codes


def test_fixture_value_is_never_promoted_to_supported():
    report = _run_suite()
    for projection in report.projections:
        assert projection.receipt.verdict != CagEvidenceVerdict.SUPPORTED


def test_verdict_enum_has_no_verified_member():
    # VERIFIED is reserved for the Sovereign proof-verdict lane; a CAG result
    # must never be able to produce it.
    assert "VERIFIED" not in CagEvidenceVerdict.__members__
    report = _run_suite()
    for projection in report.projections:
        assert projection.comparison_verdict.value != "VERIFIED"
        assert projection.receipt.verdict.value != "VERIFIED"


def test_projection_is_immutable():
    report = _run_suite()
    with pytest.raises(FrozenInstanceError):
        report.projections[0].comparison_verdict = CagEvidenceVerdict.SUPPORTED


# ---------------------------------------------------------------------------
# Expected failure / invalid input
# ---------------------------------------------------------------------------


def test_invalid_runtime_revision_fails_closed():
    with pytest.raises(CagEvidenceError):
        _run_suite(runtime_revision="not-a-revision")


def test_invalid_sovereign_run_id_fails_closed():
    with pytest.raises(CagEvidenceError):
        _run_suite(sovereign_run_id="   ")


def test_run_benchmark_case_rejects_non_case_input():
    with pytest.raises(CagEvidenceError):
        run_benchmark_case("cag-bench-001", sovereign_run_id=RUN_ID, runtime_revision=REVISION)


# ---------------------------------------------------------------------------
# Markdown report projection
# ---------------------------------------------------------------------------


def test_markdown_report_renders_all_cases_with_truth_notice():
    report = _run_suite()
    markdown = render_markdown_report(report)
    assert TRUTH_NOTICE in markdown
    assert report.report_sha256 in markdown
    assert REVISION in markdown
    for projection in report.projections:
        assert projection.case_id in markdown
        assert projection.receipt.receipt_sha256 in markdown
        assert projection.claim_text in markdown
    assert "CONTRADICTED" in markdown
    assert "INCONCLUSIVE" in markdown
    assert "UNAVAILABLE" in markdown


def test_markdown_report_rejects_foreign_report():
    with pytest.raises(CagEvidenceError):
        render_markdown_report({"case_results": []})


# ---------------------------------------------------------------------------
# Mirror parity
# ---------------------------------------------------------------------------


def test_canonical_and_deployment_mirror_are_byte_equal():
    canonical = CANONICAL_PATH.read_bytes()
    mirror = MIRROR_PATH.read_bytes()
    assert canonical == mirror
    compile(mirror, str(MIRROR_PATH), "exec")
