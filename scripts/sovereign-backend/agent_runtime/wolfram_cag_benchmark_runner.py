"""Deterministic public benchmark runner for the Wolfram CAG evidence lane.

Turns the public benchmark fixtures
(``wolfram_cag_benchmark_cases.BENCHMARK_CASES``) into reproducible,
secret-free, hash-bound receipt projections. This is the production runner
behind the #1464 public evidence demo and the #1465 developer quickstart:
a human or CI job can run one bounded call and obtain the same report a
deployed Sovereign instance derives.

Determinism contract: no network, no filesystem, no wall-clock, no
randomness. A report built from the same fixture revision, the same
``sovereign_run_id`` / ``runtime_revision`` and the same case selection is
byte-identical. ``recorded_at`` stays empty so the receipt hashes are pure
content identity.

Truth boundaries:

- ``comparison_verdict`` is the deterministic fixture comparison contract
  (``comparison_verdict(case)``). It is an honest statement about the public
  reference fixtures, never a live Wolfram API result.
- ``evidence_verdict`` comes from the real #1460 evidence lane
  (``verify_cag_claim``). Without a real transport receipt backed by #1458
  provisioning it is honestly ``UNAVAILABLE`` and stays that way.
- Nothing here asserts ``VERIFIED`` and nothing replaces runtime, repository
  or deployment readbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Mapping

from .wolfram_cag_benchmark_cases import (
    BENCHMARK_CASES,
    BenchmarkCase,
    case_by_id,
    comparison_verdict,
)
from .wolfram_cag_evidence import (
    CONTRACT_VERSION,
    TRUTH_NOTICE,
    CagClaim,
    CagEvidenceError,
    CagEvidenceVerdict,
    VerificationInput,
    WolframCagReceiptV1,
    canonical_cag_sha256,
    verify_cag_claim,
)

REPORT_SCHEMA_VERSION: Final = "sovereign.wolfram-cag-benchmark-report.v1"


@dataclass(frozen=True, slots=True)
class BenchmarkReceiptProjection:
    """One benchmark case bound to its deterministic and evidence verdicts.

    ``receipt`` is a real ``WolframCagReceiptV1`` produced by
    ``verify_cag_claim`` on the live code path. ``comparison_verdict`` is the
    fixture comparison contract; ``receipt.verdict`` is the honest evidence
    verdict. They answer different questions and are never merged into a
    single synthetic "green" state.
    """

    case_id: str
    title: str
    component_id: str
    claim_text: str
    claim_hash: str
    comparison_verdict: CagEvidenceVerdict
    receipt: WolframCagReceiptV1

    def canonical_body(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "claim_hash": self.claim_hash,
            "claim_text": self.claim_text,
            "comparison_verdict": self.comparison_verdict.value,
            "component_id": self.component_id,
            "evidence_verdict": self.receipt.verdict.value,
            "finding_codes": list(self.receipt.finding_codes),
            "receipt_sha256": self.receipt.receipt_sha256,
            "title": self.title,
        }

    def to_dict(self) -> dict[str, Any]:
        body = self.canonical_body()
        body["receipt"] = self.receipt.to_dict()
        body["truth_notice"] = TRUTH_NOTICE
        return body


def run_benchmark_case(
    case: BenchmarkCase,
    *,
    sovereign_run_id: str,
    runtime_revision: str,
    transport_receipt: Mapping[str, Any] | None = None,
) -> BenchmarkReceiptProjection:
    """Run one public fixture through the real evidence lane.

    Without a real transport receipt (the default until #1458 supplies
    provisioning evidence) the evidence verdict is honestly ``UNAVAILABLE``;
    no fixture value is ever promoted to ``SUPPORTED``.
    """
    if not isinstance(case, BenchmarkCase):
        raise CagEvidenceError("run_benchmark_case requires a public BenchmarkCase fixture")
    claim: CagClaim = case.to_claim(
        sovereign_run_id=sovereign_run_id,
        runtime_revision=runtime_revision,
    )
    inputs = VerificationInput(
        claim=claim,
        input_text=f"verify claim: {case.claim_text}",
        result=case.to_result(),
        tolerance=case.tolerance,
        transport_receipt=transport_receipt,
    )
    receipt = verify_cag_claim(inputs)
    return BenchmarkReceiptProjection(
        case_id=case.case_id,
        title=case.title,
        component_id=case.component_id,
        claim_text=case.claim_text,
        claim_hash=claim.claim_hash,
        comparison_verdict=CagEvidenceVerdict(comparison_verdict(case)),
        receipt=receipt,
    )


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """A deterministic, hash-bound projection of the public benchmark suite."""

    sovereign_run_id: str
    runtime_revision: str
    projections: tuple[BenchmarkReceiptProjection, ...]

    def __post_init__(self) -> None:
        if not self.projections:
            raise CagEvidenceError("a benchmark report needs at least one case")
        case_ids = [projection.case_id for projection in self.projections]
        if len(set(case_ids)) != len(case_ids):
            raise CagEvidenceError("benchmark case ids must be unique within a report")

    def canonical_body(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "projections": [projection.canonical_body() for projection in self.projections],
            "runtime_revision": self.runtime_revision,
            "schema_version": REPORT_SCHEMA_VERSION,
            "sovereign_run_id": self.sovereign_run_id,
        }

    @property
    def report_sha256(self) -> str:
        """Tamper-evident hash of the complete ordered report."""
        return canonical_cag_sha256(self.canonical_body())

    def to_dict(self) -> dict[str, Any]:
        body = self.canonical_body()
        body["projections"] = [projection.to_dict() for projection in self.projections]
        body["report_sha256"] = self.report_sha256
        body["truth_notice"] = TRUTH_NOTICE
        return body


def run_benchmark_suite(
    *,
    sovereign_run_id: str,
    runtime_revision: str,
    case_ids: tuple[str, ...] | None = None,
    transport_receipt: Mapping[str, Any] | None = None,
) -> BenchmarkReport:
    """Run the public benchmark fixtures in deterministic fixture order."""
    selected = (
        tuple(case_by_id(case_id) for case_id in case_ids)
        if case_ids is not None
        else tuple(BENCHMARK_CASES)
    )
    projections = tuple(
        run_benchmark_case(
            case,
            sovereign_run_id=sovereign_run_id,
            runtime_revision=runtime_revision,
            transport_receipt=transport_receipt,
        )
        for case in selected
    )
    return BenchmarkReport(
        sovereign_run_id=sovereign_run_id,
        runtime_revision=runtime_revision,
        projections=projections,
    )


def render_markdown_report(report: BenchmarkReport) -> str:
    """Render a deterministic, shareable, truth-bounded markdown report.

    The report is safe to publish: it contains only public fixture text,
    hashes and honest verdicts. It must never be edited into claiming live
    CAG transport or ``VERIFIED`` state.
    """
    if not isinstance(report, BenchmarkReport):
        raise CagEvidenceError("render_markdown_report requires a BenchmarkReport")
    lines = [
        "# Sovereign Wolfram CAG Public Benchmark Report",
        "",
        f"- Schema: `{REPORT_SCHEMA_VERSION}` (contract `{CONTRACT_VERSION}`)",
        f"- Sovereign run id: `{report.sovereign_run_id}`",
        f"- Runtime revision: `{report.runtime_revision or 'unbound'}`",
        f"- Report SHA-256: `{report.report_sha256}`",
        "",
        "## Truth boundary",
        "",
        "- `comparison_verdict` is the deterministic comparison contract of the",
        "  public reference fixtures, not a live Wolfram API result.",
        "- `evidence_verdict` comes from the real #1460 evidence lane. Without",
        "  real #1458 provisioning it is honestly `UNAVAILABLE`.",
        "- No verdict here is `VERIFIED`; CAG evidence never replaces runtime,",
        "  repository or deployment readbacks.",
        f"- {TRUTH_NOTICE}",
        "",
        "## Cases",
        "",
        "| Case | Component | Comparison | Evidence | Receipt SHA-256 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for projection in report.projections:
        lines.append(
            "| {case} | {component} | {comparison} | {evidence} | `{sha}` |".format(
                case=projection.case_id,
                component=projection.component_id,
                comparison=projection.comparison_verdict.value,
                evidence=projection.receipt.verdict.value,
                sha=projection.receipt.receipt_sha256[:16],
            )
        )
    lines.append("")
    for projection in report.projections:
        receipt = projection.receipt
        lines.extend(
            [
                f"### {projection.case_id} — {projection.title}",
                "",
                f"- Claim: {projection.claim_text}",
                f"- Normalized input: {receipt.input_text}",
                f"- Claim SHA-256: `{projection.claim_hash}`",
                f"- Result SHA-256: `{receipt.result_hash}`",
                f"- Comparison verdict: `{projection.comparison_verdict.value}`",
                f"- Evidence verdict: `{receipt.verdict.value}`",
                f"- Finding codes: `{', '.join(receipt.finding_codes) or 'none'}`",
                f"- Receipt SHA-256: `{receipt.receipt_sha256}`",
                "",
                "Reproduce:",
                "",
                "```python",
                "from backend.agent_runtime.wolfram_cag_benchmark_cases import case_by_id",
                "from backend.agent_runtime.wolfram_cag_benchmark_runner import run_benchmark_case",
                "",
                f"projection = run_benchmark_case(case_by_id(\"{projection.case_id}\"),",
                f"    sovereign_run_id=\"{report.sovereign_run_id}\",",
                f"    runtime_revision=\"{report.runtime_revision}\")",
                "assert projection.receipt.receipt_sha256 == "
                f"\"{receipt.receipt_sha256}\"",
                "```",
                "",
            ]
        )
    return "\n".join(lines)


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "BenchmarkReceiptProjection",
    "BenchmarkReport",
    "render_markdown_report",
    "run_benchmark_case",
    "run_benchmark_suite",
]
