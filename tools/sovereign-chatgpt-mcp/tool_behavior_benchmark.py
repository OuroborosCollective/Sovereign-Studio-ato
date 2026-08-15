"""OTBA 5/5: real, falsifiable E2E benchmark pilot harness.

This module is a *benchmark harness*, not a second evidence truth layer. It consumes
the existing real OTBA surfaces (``tool_behavior_contract``,
``tool_behavior_attestation``, ``tool_behavior_runtime``) and answers the falsifiable
question posed by issue #1454:

> Findet OTBA reale Tool-Verhaltensänderungen oder undeclared Effects, die mit dem
> heutigen Image-/Registry-/Capability-/MCP-Canary-Pfad nicht sichtbar wären?

Design rules (prime directive):

- No mock/stub evidence in the positive truth path. A positive benchmark result only
  exists when a real ``LocalOciRunResult`` from ``run_local_oci_canary`` carried a
  real observation set derived from a real strace trace.
- The **baseline** axis is the pre-OTBA admission path: registry metadata + declared
  capabilities + source/runtime revision evidence + immutable digest evidence + MCP
  initialize/capability canary + existing effect/readback gates. The baseline gate
  inspects *identity* only; it cannot inspect *observed behavior*. That is exactly the
  additional visibility OTBA is supposed to provide.
- Raw measurements are always retained; negative runs are never removed without a
  documented infrastructure cause.
- The Go/No-Go recommendation is derived **only** from measured raw values. No invented
  percentage thresholds. If the data is missing, the recommendation is INCONCLUSIVE with
  the real reason.
- No automatic production-enforcement is enabled by this module. The report is a claim
  surface for a human Go/No-Go decision.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from tool_behavior_attestation import (
    ObservedToolBehaviorReceipt,
    evaluate_verdict,
)
from tool_behavior_contract import ToolBehaviorContract
from tool_behavior_runtime import (
    LocalOciRunResult,
    build_receipt_from_canary,
    run_local_oci_canary,
)

__all__ = [
    "BenchmarkCase",
    "BaselineVerdict",
    "BaselineGate",
    "BenchmarkRun",
    "BenchmarkResult",
    "BenchmarkReport",
    "BenchmarkPilotError",
    "default_baseline_gate",
    "run_benchmark_case",
    "run_pilot",
    "GO",
    "NO_GO",
    "INCONCLUSIVE",
    "BASELINE_PASS",
    "BASELINE_BLOCKED_IDENTITY",
    "BASELINE_UNVERIFIED",
    "SANDBOX_FAILURE_STATUSES",
]


GO = "GO"
NO_GO = "NO_GO"
INCONCLUSIVE = "INCONCLUSIVE"

BASELINE_PASS = "BASELINE_PASS"
BASELINE_BLOCKED_IDENTITY = "BASELINE_BLOCKED_IDENTITY"
BASELINE_UNVERIFIED = "BASELINE_UNVERIFIED"

# LocalOciRunResult statuses that represent an infrastructure/sandbox failure, not tool
# misbehavior. Per #1454 these must be classified separately from tool behavior.
SANDBOX_FAILURE_STATUSES = frozenset({"UNAVAILABLE", "EXECUTION_FAILED", "TRACE_DIED"})


class BenchmarkPilotError(RuntimeError):
    """Raised when a caller crosses an OTBA benchmark truth-boundary invariant."""


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One falsifiable benchmark case: a real contract + real canary inputs.

    ``expected_controlled_violation`` is the human-declared intent for the case, used
    only to *classify* whether an OTBA block was a controlled violation (correct catch)
    or a false block (incorrect catch). It never feeds the OTBA verdict itself.
    """

    label: str
    contract: ToolBehaviorContract
    canary_command: tuple[str, ...]
    canary_workspace: str
    canary_input_sha256: str
    image_ref: str | None = None
    expected_controlled_violation: bool = False
    historical_drift_pair: str | None = None

    def __post_init__(self) -> None:
        if not self.label:
            raise BenchmarkPilotError("BenchmarkCase label must be non-empty")
        if not self.canary_command:
            raise BenchmarkPilotError("BenchmarkCase canary_command must be non-empty")
        if not self.canary_workspace:
            raise BenchmarkPilotError("BenchmarkCase canary_workspace must be non-empty")
        if len(self.canary_input_sha256) != 64:
            raise BenchmarkPilotError("canary_input_sha256 must be a 64-char SHA-256")


@dataclass(frozen=True, slots=True)
class BaselineVerdict:
    """The pre-OTBA admission verdict over identity evidence only.

    The baseline path sees registry metadata, declared capabilities, source/runtime
    revision evidence, immutable digest evidence, and the MCP initialize/capability
    canary. It does **not** inspect observed process/filesystem/network behavior. A
    ``BASELINE_PASS`` therefore means "identity is sound", **not** "behavior is sound".
    """

    verdict: str
    reason: str
    digest_bound: bool
    revision_bound: bool


@dataclass(frozen=True, slots=True)
class BaselineGate:
    """Deterministic baseline admission evaluator (identity-only).

    This is intentionally a pure function over the *contract* (which encodes the
    declared identity: digest, revision, execution kind, effect class). It mirrors what
    the existing Sovereign admission gates can decide *without* OTBA: they can confirm
    the tool identity is bound and sound, but they cannot see what the tool actually did.
    """

    def evaluate(self, contract: ToolBehaviorContract) -> BaselineVerdict:
        if contract.execution_kind == "REMOTE_MCP":
            # The baseline path can only confirm a remote MCP server's declared identity
            # at the registry/capability layer; it has no local runtime view at all.
            return BaselineVerdict(
                verdict=BASELINE_UNVERIFIED,
                reason="REMOTE_MCP: baseline has no local runtime view",
                digest_bound=False,
                revision_bound=bool(contract.repository_revision),
            )
        if contract.image_digest is None:
            return BaselineVerdict(
                verdict=BASELINE_BLOCKED_IDENTITY,
                reason="no immutable image digest bound",
                digest_bound=False,
                revision_bound=bool(contract.repository_revision),
            )
        return BaselineVerdict(
            verdict=BASELINE_PASS,
            reason="identity sound (digest + revision + capability declared)",
            digest_bound=True,
            revision_bound=True,
        )


def default_baseline_gate() -> BaselineGate:
    return BaselineGate()


@dataclass(frozen=True, slots=True)
class BenchmarkRun:
    """Raw measurements captured from a single real canary execution.

    Every field is sourced from a real ``LocalOciRunResult`` and/or the derived
    tamper-sensitive receipt. No value is invented. ``None`` means "not measured"
    because the run did not reach that stage.
    """

    runtime_status: str
    sandbox_failure: bool
    executed_image_digest: str | None
    raw_trace_sha256: str | None
    container_id: str | None
    exit_code: int | None
    tool_execution_wall_time_ms: int | None
    otba_overhead_ms: int | None
    receipt: ObservedToolBehaviorReceipt | None
    receipt_bytes: int | None
    otba_verdict: str
    otba_findings: tuple[str, ...]
    observed_exec: tuple[str, ...] | None
    observed_read_paths: tuple[str, ...] | None
    observed_write_paths: tuple[str, ...] | None
    observed_network_targets: tuple[str, ...] | None
    observed_wall_time_ms: int | None
    observed_memory_bytes: int | None


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """One case's full baseline-vs-OTBA comparison result."""

    case: BenchmarkCase
    run: BenchmarkRun
    baseline: BaselineVerdict
    additional_findings: tuple[str, ...]
    false_block: bool
    controlled_violation_caught: bool
    raw_record: dict[str, Any]


def _receipt_bytes(receipt: ObservedToolBehaviorReceipt) -> int:
    return len(json.dumps(receipt.canonical_record(), sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _observed_from_receipt(receipt: ObservedToolBehaviorReceipt) -> dict[str, Any]:
    # The receipt stores hashes of observations, not the raw sets. We expose the
    # canonical hashes as the raw identity of what was observed; the raw sets live in
    # the trace artifact (bound by raw_trace_sha256), not in the receipt.
    return {
        "observed_exec_sha256": receipt.observed_exec_sha256,
        "observed_filesystem_sha256": receipt.observed_filesystem_sha256,
        "observed_network_sha256": receipt.observed_network_sha256,
        "observed_resource_usage_sha256": receipt.observed_resource_usage_sha256,
        "external_effect_sha256": receipt.external_effect_sha256,
    }


def run_benchmark_case(
    *,
    case: BenchmarkCase,
    baseline_gate: BaselineGate | None = None,
    runner: Callable[[BenchmarkCase], LocalOciRunResult] | None = None,
) -> BenchmarkResult:
    """Run one real benchmark case and produce a baseline-vs-OTBA comparison.

    ``runner`` defaults to the real ``run_local_oci_canary`` execution path. It is
    injectable **only** so tests can feed real ``LocalOciRunResult`` objects built from
    real strace trace fixtures (the live path). A test runner must never synthesize a
    positive observation set without a real trace; that invariant is enforced by the
    runtime module itself (``VERIFIED_OBSERVATION`` only exists when a real trace parsed).
    """
    gate = baseline_gate or default_baseline_gate()
    baseline = gate.evaluate(case.contract)

    real_runner = runner if runner is not None else _real_runner
    run_result = real_runner(case)

    receipt, findings = build_receipt_from_canary(
        contract=case.contract,
        canary_input_sha256=case.canary_input_sha256,
        run_result=run_result,
    )

    sandbox_failure = run_result.status in SANDBOX_FAILURE_STATUSES
    is_positive = run_result.is_positive()

    observed_exec = None
    observed_read = None
    observed_write = None
    observed_net = None
    observed_wall = None
    observed_mem = None
    if is_positive and run_result.observation_set is not None:
        obs = run_result.observation_set
        observed_exec = obs.process_exec
        observed_read = obs.filesystem_reads
        observed_write = obs.filesystem_writes
        observed_net = tuple(sorted(set(obs.network_connects) | set(obs.network_listens)))
        observed_wall = obs.wall_time_ms
        observed_mem = obs.peak_memory_bytes

    run = BenchmarkRun(
        runtime_status=run_result.status,
        sandbox_failure=sandbox_failure,
        executed_image_digest=run_result.executed_image_digest,
        raw_trace_sha256=run_result.raw_trace_sha256,
        container_id=run_result.container_id,
        exit_code=run_result.exit_code,
        tool_execution_wall_time_ms=run_result.wall_time_ms,
        otba_overhead_ms=run_result.overhead_ms,
        receipt=receipt,
        receipt_bytes=_receipt_bytes(receipt),
        otba_verdict=receipt.verdict,
        otba_findings=findings,
        observed_exec=observed_exec,
        observed_read_paths=observed_read,
        observed_write_paths=observed_write,
        observed_network_targets=observed_net,
        observed_wall_time_ms=observed_wall,
        observed_memory_bytes=observed_mem,
    )

    # additional_findings: OTBA findings the baseline path cannot produce. The baseline
    # only sees identity, so every *behavioral* finding (process/fs/network/resource
    # violation) is additional visibility. Missing-observation and identity-contradiction
    # findings are not "additional" over baseline in the same sense, so we keep only the
    # behavioral findings here while still retaining all findings in run.otba_findings.
    additional = tuple(
        f for f in findings
        if any(f.startswith(prefix) for prefix in (
            "EXEC_NOT_DECLARED",
            "READ_PATH_NOT_DECLARED",
            "WRITE_PATH_NOT_DECLARED",
            "NETWORK_TARGET_NOT_DECLARED",
            "WALL_TIME_EXCEEDED",
            "MEMORY_EXCEEDED",
            "EXTERNAL_EFFECT_NOT_PERMITTED",
            "EXTERNAL_EFFECT_MISSING",
        ))
    )

    # controlled_violation_caught: the case declared a controlled violation intent AND
    # OTBA returned a behavioral violation verdict. This is a correct catch, not a false
    # block.
    controlled_violation_caught = (
        case.expected_controlled_violation
        and run.otba_verdict == "BEHAVIOR_VIOLATION"
        and bool(additional)
    )

    # false_block: OTBA blocked a case that was *not* intended as a controlled
    # violation. This is only meaningful for positive canaries (real legitimate
    # behavior). A sandbox failure is never a false block (it is infrastructure).
    false_block = (
        not case.expected_controlled_violation
        and not sandbox_failure
        and run.otba_verdict in {"BEHAVIOR_VIOLATION", "CONTRADICTED"}
    )

    raw_record = _build_raw_record(
        case=case,
        baseline=baseline,
        run=run,
        receipt=receipt,
        additional_findings=additional,
        false_block=false_block,
        controlled_violation_caught=controlled_violation_caught,
    )

    return BenchmarkResult(
        case=case,
        run=run,
        baseline=baseline,
        additional_findings=additional,
        false_block=false_block,
        controlled_violation_caught=controlled_violation_caught,
        raw_record=raw_record,
    )


def _real_runner(case: BenchmarkCase) -> LocalOciRunResult:
    """The default real execution path: run_local_oci_canary."""
    return run_local_oci_canary(
        contract=case.contract,
        canary_command=case.canary_command,
        canary_workspace=case.canary_workspace,
        image_ref=case.image_ref,
    )


def _build_raw_record(
    *,
    case: BenchmarkCase,
    baseline: BaselineVerdict,
    run: BenchmarkRun,
    receipt: ObservedToolBehaviorReceipt,
    additional_findings: tuple[str, ...],
    false_block: bool,
    controlled_violation_caught: bool,
) -> dict[str, Any]:
    """The complete raw measurement record for one case (#1454 Rohmesswerte)."""
    contract = case.contract
    record: dict[str, Any] = {
        "case_label": case.label,
        "historical_drift_pair": case.historical_drift_pair,
        "repository_revision": contract.repository_revision,
        "tool_id": contract.tool_id,
        "tool_image_digest": run.executed_image_digest or contract.image_digest,
        "contract_hash": contract.contract_sha256,
        "canary_input_sha256": case.canary_input_sha256,
        "trace_artifact_sha256": run.raw_trace_sha256,
        "runtime_status": run.runtime_status,
        "sandbox_failure": run.sandbox_failure,
        "tool_execution_wall_time_ms": run.tool_execution_wall_time_ms,
        "otba_overhead_ms": run.otba_overhead_ms,
        "receipt_bytes": run.receipt_bytes,
        "observed_exec": list(run.observed_exec) if run.observed_exec is not None else None,
        "observed_read_paths": list(run.observed_read_paths) if run.observed_read_paths is not None else None,
        "observed_write_paths": list(run.observed_write_paths) if run.observed_write_paths is not None else None,
        "observed_network_targets": list(run.observed_network_targets) if run.observed_network_targets is not None else None,
        "observed_wall_time_ms": run.observed_wall_time_ms,
        "observed_memory_bytes": run.observed_memory_bytes,
        "baseline_gate_verdict": baseline.verdict,
        "baseline_reason": baseline.reason,
        "otba_verdict": run.otba_verdict,
        "otba_findings": list(run.otba_findings),
        "additional_findings": list(additional_findings),
        "false_block": false_block,
        "controlled_violation_caught": controlled_violation_caught,
        "authoritative_readback_sha256": receipt.authoritative_readback_sha256,
        "receipt_sha256": receipt.receipt_sha256,
    }
    return record


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Aggregate pilot report over a set of real benchmark results."""

    source_revision: str
    results: tuple[BenchmarkResult, ...]
    generated_at_iso: str
    raw_records: tuple[dict[str, Any], ...]
    aggregate: dict[str, Any]
    recommendation: str
    recommendation_reason: str

    def to_json(self) -> str:
        payload = {
            "sourceRevision": self.source_revision,
            "generatedAtIso": self.generated_at_iso,
            "results": [r.raw_record for r in self.results],
            "aggregate": self.aggregate,
            "recommendation": self.recommendation,
            "recommendationReason": self.recommendation_reason,
        }
        return json.dumps(payload, sort_keys=True, indent=2)


def run_pilot(
    *,
    cases: Sequence[BenchmarkCase],
    source_revision: str,
    baseline_gate: BaselineGate | None = None,
    runner: Callable[[BenchmarkCase], LocalOciRunResult] | None = None,
) -> BenchmarkReport:
    """Run the full falsifiable benchmark pilot over a set of real cases.

    The Go/No-Go recommendation is derived **only** from measured raw values:

    - GO requires: at least one controlled violation caught by OTBA that the baseline
      could not see, zero false blocks on legitimate canaries, at least one real
      positive canary reproduced, and overhead actually measured.
    - NO_GO when false blocks exist or no controlled violations were caught.
    - INCONCLUSIVE when the data is missing to decide (e.g. all runs sandbox-failed,
      or no positive canary reproduced).

    No invented percentage thresholds. The human reads the raw records.
    """
    if len(source_revision) != 40:
        raise BenchmarkPilotError("source_revision must be a 40-char Git SHA")
    if not cases:
        raise BenchmarkPilotError("pilot requires at least one BenchmarkCase")

    results = tuple(
        run_benchmark_case(case=case, baseline_gate=baseline_gate, runner=runner)
        for case in cases
    )
    raw_records = tuple(r.raw_record for r in results)

    aggregate = _aggregate(results)
    recommendation, reason = _recommendation(results=results, aggregate=aggregate)

    return BenchmarkReport(
        source_revision=source_revision,
        results=results,
        generated_at_iso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        raw_records=raw_records,
        aggregate=aggregate,
        recommendation=recommendation,
        recommendation_reason=reason,
    )


def _aggregate(results: Sequence[BenchmarkResult]) -> dict[str, Any]:
    total = len(results)
    sandbox_failures = sum(1 for r in results if r.run.sandbox_failure)
    positive_canaries = sum(1 for r in results if r.run.runtime_status == "VERIFIED_OBSERVATION")
    controlled_caught = sum(1 for r in results if r.controlled_violation_caught)
    false_blocks = sum(1 for r in results if r.false_block)
    otba_verified = sum(1 for r in results if r.run.otba_verdict == "BEHAVIOR_VERIFIED")
    otba_violation = sum(1 for r in results if r.run.otba_verdict == "BEHAVIOR_VIOLATION")
    otba_unverified = sum(1 for r in results if r.run.otba_verdict == "UNVERIFIED")
    otba_contradicted = sum(1 for r in results if r.run.otba_verdict == "CONTRADICTED")
    otba_remote_partial = sum(1 for r in results if r.run.otba_verdict == "REMOTE_PARTIAL")
    baseline_pass = sum(1 for r in results if r.baseline.verdict == BASELINE_PASS)
    baseline_blocked = sum(1 for r in results if r.baseline.verdict == BASELINE_BLOCKED_IDENTITY)
    baseline_unverified = sum(1 for r in results if r.baseline.verdict == BASELINE_UNVERIFIED)
    additional_findings_total = sum(len(r.additional_findings) for r in results)
    # Additional visibility: violations OTBA caught where the baseline still said PASS.
    additional_over_baseline = sum(
        1 for r in results
        if r.additional_findings and r.baseline.verdict == BASELINE_PASS
    )
    measured_overhead_ms = [
        r.run.otba_overhead_ms for r in results
        if r.run.otba_overhead_ms is not None
    ]
    return {
        "total_cases": total,
        "sandbox_failures": sandbox_failures,
        "positive_canaries_reproduced": positive_canaries,
        "controlled_violations_caught": controlled_caught,
        "false_blocks": false_blocks,
        "otba_verdict_counts": {
            "BEHAVIOR_VERIFIED": otba_verified,
            "BEHAVIOR_VIOLATION": otba_violation,
            "UNVERIFIED": otba_unverified,
            "CONTRADICTED": otba_contradicted,
            "REMOTE_PARTIAL": otba_remote_partial,
        },
        "baseline_verdict_counts": {
            "BASELINE_PASS": baseline_pass,
            "BASELINE_BLOCKED_IDENTITY": baseline_blocked,
            "BASELINE_UNVERIFIED": baseline_unverified,
        },
        "additional_findings_total": additional_findings_total,
        "additional_findings_over_baseline_pass": additional_over_baseline,
        "otba_overhead_ms_measured": measured_overhead_ms,
        "otba_overhead_ms_max": max(measured_overhead_ms) if measured_overhead_ms else None,
    }


def _recommendation(
    *,
    results: Sequence[BenchmarkResult],
    aggregate: Mapping[str, Any],
) -> tuple[str, str]:
    positive = aggregate["positive_canaries_reproduced"]
    controlled_declared = sum(1 for r in results if r.case.expected_controlled_violation)
    controlled_caught = aggregate["controlled_violations_caught"]
    false_blocks = aggregate["false_blocks"]
    sandbox_failures = aggregate["sandbox_failures"]
    additional_over_baseline = aggregate["additional_findings_over_baseline_pass"]
    overhead_measured = aggregate["otba_overhead_ms_max"] is not None

    # INCONCLUSIVE: the data is missing to decide.
    if positive == 0 and sandbox_failures == len(results):
        return INCONCLUSIVE, "all runs sandbox-failed; no real behavior data collected"
    if positive == 0:
        return INCONCLUSIVE, "no positive canary reproduced; behavior visibility not demonstrated"
    if not overhead_measured:
        return INCONCLUSIVE, "OTBA overhead was not measured on any run"

    # NO_GO: real evidence against enabling enforcement. False blocks are real harm
    # regardless of whether the controlled-violation axis was tested.
    if false_blocks > 0:
        return NO_GO, f"{false_blocks} false block(s) on legitimate canaries; enforcement would block correct tools"

    # When no controlled-violation cases were declared at all, the pilot simply did not
    # test that axis. That is missing evidence, not evidence of harm.
    if controlled_declared == 0:
        return INCONCLUSIVE, "no controlled-violation case declared; additional visibility over baseline not tested"
    if controlled_caught == 0:
        return NO_GO, "declared controlled violations were not caught by OTBA; no additional visibility demonstrated"

    # GO: OTBA caught behavior the baseline could not see, with no false blocks.
    if additional_over_baseline > 0:
        return GO, (
            f"{controlled_caught} controlled violation(s) caught by OTBA that baseline "
            f"(identity-only) could not see; {false_blocks} false block(s); "
            f"{positive} positive canary/canaries reproduced; overhead measured"
        )

    # Edge: controlled violations caught but none while baseline said PASS. This means
    # the baseline already blocked those cases on identity, so OTBA added no visibility.
    return INCONCLUSIVE, (
        "controlled violations caught but none over a baseline-PASS case; "
        "additional visibility over baseline not demonstrated"
    )
