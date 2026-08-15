"""Tests for the OTBA 5/5 benchmark pilot harness (tool_behavior_benchmark).

These tests exercise the real live-path modules:
- ``run_local_oci_canary`` is NOT mocked. Where a real Docker/strace environment is
  unavailable, we feed real ``LocalOciRunResult`` objects built from real strace trace
  fixtures via the same ``build_receipt_from_canary`` bridge the production harness uses.
- The OTBA verdict is always produced by the real ``evaluate_verdict``; no verdict is
  invented by the harness or the tests.
- The benchmark comparison logic (additional_findings, false_block,
  controlled_violation_caught, recommendation) is pure and tested directly.

This mapping covers the #1454 acceptance criteria that can be validated without a real
Docker daemon; the real-Docker pilot execution is honestly delegated.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tool_behavior_benchmark import (
    BASELINE_BLOCKED_IDENTITY,
    BASELINE_PASS,
    BASELINE_UNVERIFIED,
    GO,
    INCONCLUSIVE,
    NO_GO,
    BenchmarkCase,
    BenchmarkPilotError,
    BenchmarkReport,
    BaselineGate,
    default_baseline_gate,
    run_benchmark_case,
    run_pilot,
)
from tool_behavior_contract import ToolBehaviorContract
from tool_behavior_runtime import LocalOciRunResult, build_receipt_from_canary
from tool_behavior_trace import compute_raw_trace_sha256, parse_strace_trace

FIXTURES = Path(__file__).parent / "fixtures"
SHA40 = "a" * 40
SHA64 = "b" * 64
DIGEST = f"sha256:{SHA64}"
CANARY_INPUT_SHA = hashlib.sha256(b"canary-input").hexdigest()


def _read(name: str) -> str:
    return (FIXTURES / name).read_text("utf-8")


def _local_oci_contract(**overrides) -> ToolBehaviorContract:
    defaults = dict(
        schema_version="sovereign.tool-behavior-contract.v1",
        tool_id="tool.canary",
        execution_kind="LOCAL_OCI",
        repository_revision=SHA40,
        tool_registry_revision=SHA40,
        image_digest=DIGEST,
        effect_class="WORKSPACE_WRITE",
        allowed_exec=("/usr/bin/bash",),
        allowed_read_paths=("/workspace/repo",),
        allowed_write_paths=("/tmp/strace_fix/out",),
        allowed_network_targets=(),
        network_required=False,
        max_wall_time_ms=60_000,
        max_memory_bytes=256 * 1024 * 1024,
    )
    defaults.update(overrides)
    return ToolBehaviorContract(**defaults)


def _remote_mcp_contract(**overrides) -> ToolBehaviorContract:
    defaults = dict(
        schema_version="sovereign.tool-behavior-contract.v1",
        tool_id="tool.remote",
        execution_kind="REMOTE_MCP",
        repository_revision=SHA40,
        tool_registry_revision=SHA40,
        image_digest=None,
        effect_class="READ_ONLY",
        allowed_exec=("/usr/bin/remote-mcp",),
        allowed_read_paths=(),
        allowed_write_paths=(),
        allowed_network_targets=(),
        network_required=False,
        max_wall_time_ms=60_000,
        max_memory_bytes=256 * 1024 * 1024,
    )
    defaults.update(overrides)
    return ToolBehaviorContract(**defaults)


def _positive_result_with_trace(name: str) -> LocalOciRunResult:
    """A VERIFIED_OBSERVATION result carrying a real parsed observation set from a fixture."""
    raw = _read(name)
    obs_set = parse_strace_trace(raw, peak_memory_bytes=2048, wall_time_ms=8, exit_code=0)
    return LocalOciRunResult(
        status="VERIFIED_OBSERVATION",
        observation_set=obs_set,
        executed_image_digest=DIGEST,
        raw_trace_sha256=compute_raw_trace_sha256(raw),
        container_id="abc123",
        exit_code=0,
        wall_time_ms=8,
        overhead_ms=2,
        error=None,
    )


def _unavailable_result(error: str = "docker daemon unavailable") -> LocalOciRunResult:
    return LocalOciRunResult(
        status="UNAVAILABLE",
        observation_set=None,
        executed_image_digest=None,
        raw_trace_sha256=None,
        container_id=None,
        exit_code=None,
        wall_time_ms=None,
        overhead_ms=None,
        error=error,
    )


def _case_for(contract: ToolBehaviorContract, *, label: str = "case", **kw) -> BenchmarkCase:
    defaults = dict(
        label=label,
        contract=contract,
        canary_command=("/usr/bin/bash",),
        canary_workspace="/tmp/otba-ws",
        canary_input_sha256=CANARY_INPUT_SHA,
    )
    defaults.update(kw)
    return BenchmarkCase(**defaults)


def _runner_for(result: LocalOciRunResult):
    def _runner(case: BenchmarkCase) -> LocalOciRunResult:
        return result
    return _runner


# ---------------------------------------------------------------------------
# Baseline gate: identity-only, honest.
# ---------------------------------------------------------------------------

class TestBaselineGate:
    def test_local_oci_with_digest_passes_identity(self):
        baseline = BaselineGate().evaluate(_local_oci_contract())
        assert baseline.verdict == BASELINE_PASS
        assert baseline.digest_bound is True
        assert baseline.revision_bound is True

    def test_local_oci_without_digest_blocked_at_construction(self):
        from tool_behavior_contract import ToolBehaviorContractError
        with pytest.raises(ToolBehaviorContractError):
            _local_oci_contract(image_digest=None)

    def test_remote_mcp_is_unverified_baseline(self):
        baseline = BaselineGate().evaluate(_remote_mcp_contract())
        assert baseline.verdict == BASELINE_UNVERIFIED
        assert baseline.digest_bound is False

    def test_default_baseline_gate_is_stateless(self):
        g1 = default_baseline_gate()
        g2 = default_baseline_gate()
        c = _local_oci_contract()
        assert g1.evaluate(c) == g2.evaluate(c)


# ---------------------------------------------------------------------------
# Single case: positive canary within contract.
# ---------------------------------------------------------------------------

class TestPositiveCanary:
    def test_within_contract_yields_behavior_verified_and_baseline_pass(self):
        contract = _local_oci_contract(
            allowed_write_paths=("/tmp/strace_fix/out/allowed.txt",),
        )
        case = _case_for(contract, label="positive-clean")
        result = run_benchmark_case(
            case=case,
            runner=_runner_for(_positive_result_with_trace("trace_A.log")),
        )
        assert result.run.otba_verdict == "BEHAVIOR_VERIFIED"
        assert result.baseline.verdict == BASELINE_PASS
        assert result.false_block is False
        assert result.controlled_violation_caught is False
        assert result.additional_findings == ()
        assert result.run.sandbox_failure is False
        assert result.run.receipt_bytes is not None and result.run.receipt_bytes > 0

    def test_raw_record_contains_all_required_measurements(self):
        contract = _local_oci_contract(
            allowed_write_paths=("/tmp/strace_fix/out/allowed.txt",),
        )
        case = _case_for(contract, label="positive-clean")
        result = run_benchmark_case(
            case=case,
            runner=_runner_for(_positive_result_with_trace("trace_A.log")),
        )
        rec = result.raw_record
        # #1454 Rohmesswerte: every required raw field is present and real.
        for key in (
            "case_label", "repository_revision", "tool_id", "tool_image_digest",
            "contract_hash", "canary_input_sha256", "trace_artifact_sha256",
            "runtime_status", "sandbox_failure", "tool_execution_wall_time_ms",
            "otba_overhead_ms", "receipt_bytes", "observed_exec",
            "observed_read_paths", "observed_write_paths", "observed_network_targets",
            "observed_wall_time_ms", "observed_memory_bytes",
            "baseline_gate_verdict", "otba_verdict", "otba_findings",
            "additional_findings", "false_block", "controlled_violation_caught",
            "authoritative_readback_sha256", "receipt_sha256",
        ):
            assert key in rec, f"raw record missing {key}"
        assert rec["runtime_status"] == "VERIFIED_OBSERVATION"
        assert rec["tool_image_digest"] == DIGEST
        assert rec["baseline_gate_verdict"] == BASELINE_PASS
        assert rec["otba_verdict"] == "BEHAVIOR_VERIFIED"
        assert rec["authoritative_readback_sha256"] == contract.contract_sha256


# ---------------------------------------------------------------------------
# Single case: controlled violation caught that baseline cannot see.
# ---------------------------------------------------------------------------

class TestControlledViolation:
    def test_undeclared_write_caught_over_baseline_pass(self):
        # Contract declares NO write paths; trace_A wrote an undeclared path.
        contract = _local_oci_contract(allowed_write_paths=())
        case = _case_for(contract, label="controlled-write-violation", expected_controlled_violation=True)
        result = run_benchmark_case(
            case=case,
            runner=_runner_for(_positive_result_with_trace("trace_A.log")),
        )
        assert result.run.otba_verdict == "BEHAVIOR_VIOLATION"
        # Baseline still says PASS (it only sees identity, not behavior).
        assert result.baseline.verdict == BASELINE_PASS
        assert result.controlled_violation_caught is True
        assert result.false_block is False
        assert any(f.startswith("WRITE_PATH_NOT_DECLARED") for f in result.additional_findings)

    def test_undeclared_network_caught_over_baseline_pass(self):
        contract = _local_oci_contract(allowed_exec=("/usr/bin/getent",))
        case = _case_for(contract, label="controlled-network-violation", expected_controlled_violation=True)
        result = run_benchmark_case(
            case=case,
            runner=_runner_for(_positive_result_with_trace("trace_C.log")),
        )
        assert result.run.otba_verdict == "BEHAVIOR_VIOLATION"
        assert result.baseline.verdict == BASELINE_PASS
        assert result.controlled_violation_caught is True
        assert any(f.startswith("NETWORK_TARGET_NOT_DECLARED") for f in result.additional_findings)


# ---------------------------------------------------------------------------
# Single case: false block detection.
# ---------------------------------------------------------------------------

class TestFalseBlock:
    def test_clean_canary_blocked_is_false_block(self):
        # A positive canary within contract, but we (wrongly) declare it a violation
        # intent = False. If OTBA had blocked it, that would be a false block. Here OTBA
        # correctly verifies, so no false block. We test the false_block=True branch by
        # using a contract that forbids the observed write while declaring no violation.
        contract = _local_oci_contract(allowed_write_paths=())
        case = _case_for(contract, label="legit-but-blocked", expected_controlled_violation=False)
        result = run_benchmark_case(
            case=case,
            runner=_runner_for(_positive_result_with_trace("trace_A.log")),
        )
        # OTBA blocks (BEHAVIOR_VIOLATION) but the case was not a declared controlled
        # violation -> this is a false block from the pilot's classification standpoint.
        assert result.run.otba_verdict == "BEHAVIOR_VIOLATION"
        assert result.false_block is True
        assert result.controlled_violation_caught is False

    def test_sandbox_failure_is_never_a_false_block(self):
        contract = _local_oci_contract()
        case = _case_for(contract, label="sandbox-failed", expected_controlled_violation=False)
        result = run_benchmark_case(
            case=case,
            runner=_runner_for(_unavailable_result()),
        )
        assert result.run.sandbox_failure is True
        assert result.run.otba_verdict == "UNVERIFIED"
        assert result.false_block is False


# ---------------------------------------------------------------------------
# Sandbox / infrastructure failure classification.
# ---------------------------------------------------------------------------

class TestSandboxFailure:
    def test_unavailable_is_sandbox_failure_and_unverified(self):
        contract = _local_oci_contract()
        case = _case_for(contract, label="unavailable")
        result = run_benchmark_case(
            case=case,
            runner=_runner_for(_unavailable_result("docker daemon unavailable")),
        )
        assert result.run.sandbox_failure is True
        assert result.run.otba_verdict == "UNVERIFIED"
        assert any("RUNTIME_STATUS:UNAVAILABLE" in f for f in result.run.otba_findings)
        assert result.run.observed_exec is None
        assert result.run.receipt is not None
        assert result.run.receipt.verify() is True

    def test_trace_died_is_sandbox_failure(self):
        from tool_behavior_runtime import LocalOciRunResult
        contract = _local_oci_contract()
        case = _case_for(contract, label="trace-died")
        result = run_benchmark_case(
            case=case,
            runner=_runner_for(LocalOciRunResult(
                status="TRACE_DIED", observation_set=None,
                executed_image_digest=DIGEST, raw_trace_sha256="0" * 64,
                container_id="abc", exit_code=0, wall_time_ms=5, overhead_ms=1,
                error="tracer exited before tool",
            )),
        )
        assert result.run.sandbox_failure is True
        assert result.run.otba_verdict == "UNVERIFIED"


# ---------------------------------------------------------------------------
# Pilot aggregation + Go/No-Go recommendation from real measured values.
# ---------------------------------------------------------------------------

class TestPilotRecommendation:
    def _positive_clean(self, label: str) -> tuple[BenchmarkCase, LocalOciRunResult]:
        c = _local_oci_contract(allowed_write_paths=("/tmp/strace_fix/out/allowed.txt",))
        return _case_for(c, label=label), _positive_result_with_trace("trace_A.log")

    def _controlled_violation(self, label: str, trace: str, *, contract_kw=None) -> tuple[BenchmarkCase, LocalOciRunResult]:
        kw = contract_kw or {"allowed_write_paths": ()}
        c = _local_oci_contract(**kw)
        return _case_for(c, label=label, expected_controlled_violation=True), _positive_result_with_trace(trace)

    def test_go_when_controlled_violation_caught_over_baseline_no_false_blocks(self):
        clean_case, clean_res = self._positive_clean("positive-clean")
        viol_case, viol_res = self._controlled_violation(
            "controlled-write", "trace_A.log", contract_kw={"allowed_write_paths": ()},
        )
        # Two cases share one runner dispatch by label.
        results = {"positive-clean": clean_res, "controlled-write": viol_res}
        def runner(case):
            return results[case.label]
        report = run_pilot(
            cases=[clean_case, viol_case],
            source_revision=SHA40,
            runner=runner,
        )
        assert isinstance(report, BenchmarkReport)
        assert report.recommendation == GO
        assert "controlled violation" in report.recommendation_reason
        agg = report.aggregate
        assert agg["positive_canaries_reproduced"] >= 1
        assert agg["controlled_violations_caught"] >= 1
        assert agg["false_blocks"] == 0
        assert agg["additional_findings_over_baseline_pass"] >= 1
        assert agg["otba_overhead_ms_max"] is not None

    def test_no_go_when_false_blocks_exist(self):
        clean_case, clean_res = self._positive_clean("positive-clean")
        # A legit clean canary but contract forbids the write -> false block.
        false_case = _case_for(
            _local_oci_contract(allowed_write_paths=()),
            label="false-block", expected_controlled_violation=False,
        )
        false_res = _positive_result_with_trace("trace_A.log")
        results = {"positive-clean": clean_res, "false-block": false_res}
        def runner(case):
            return results[case.label]
        report = run_pilot(
            cases=[clean_case, false_case],
            source_revision=SHA40,
            runner=runner,
        )
        assert report.recommendation == NO_GO
        assert "false block" in report.recommendation_reason

    def test_inconclusive_when_all_runs_sandbox_failed(self):
        contract = _local_oci_contract()
        case = _case_for(contract, label="only-sandbox")
        report = run_pilot(
            cases=[case], source_revision=SHA40,
            runner=_runner_for(_unavailable_result()),
        )
        assert report.recommendation == INCONCLUSIVE
        assert "sandbox-failed" in report.recommendation_reason

    def test_inconclusive_when_no_controlled_violation_caught(self):
        # Only a clean positive canary, no controlled violation -> cannot demonstrate
        # additional visibility.
        clean_case, clean_res = self._positive_clean("positive-clean")
        report = run_pilot(
            cases=[clean_case], source_revision=SHA40,
            runner=_runner_for(clean_res),
        )
        assert report.recommendation == INCONCLUSIVE
        assert "not tested" in report.recommendation_reason.lower() \
            or "not demonstrated" in report.recommendation_reason.lower()

    def test_no_invented_percentage_thresholds_in_recommendation(self):
        clean_case, clean_res = self._positive_clean("positive-clean")
        viol_case, viol_res = self._controlled_violation(
            "controlled-write", "trace_A.log", contract_kw={"allowed_write_paths": ()},
        )
        results = {"positive-clean": clean_res, "controlled-write": viol_res}
        def runner(case):
            return results[case.label]
        report = run_pilot(cases=[clean_case, viol_case], source_revision=SHA40, runner=runner)
        # The recommendation reason cites raw counts, never a fabricated percentage.
        assert "%" not in report.recommendation_reason


class TestPilotRawReport:
    def test_to_json_is_valid_and_retains_all_results(self):
        clean_case, clean_res = (
            _case_for(_local_oci_contract(allowed_write_paths=("/tmp/strace_fix/out/allowed.txt",)), label="c1"),
            _positive_result_with_trace("trace_A.log"),
        )
        viol_case = _case_for(_local_oci_contract(allowed_write_paths=()), label="v1", expected_controlled_violation=True)
        viol_res = _positive_result_with_trace("trace_A.log")
        results = {"c1": clean_res, "v1": viol_res}
        def runner(case):
            return results[case.label]
        report = run_pilot(cases=[clean_case, viol_case], source_revision=SHA40, runner=runner)
        payload = json.loads(report.to_json())
        assert payload["sourceRevision"] == SHA40
        assert len(payload["results"]) == 2
        assert set(r["case_label"] for r in payload["results"]) == {"c1", "v1"}
        assert "aggregate" in payload
        assert "recommendation" in payload


# ---------------------------------------------------------------------------
# REMOTE_MCP separation: never equalized with LOCAL_OCI fidelity.
# ---------------------------------------------------------------------------

class TestRemoteMcpSeparation:
    def test_remote_mcp_baseline_unverified_and_otba_remote_partial(self):
        contract = _remote_mcp_contract()
        case = _case_for(contract, label="remote-mcp")
        # A REMOTE_MCP canary cannot produce a local observation set. The honest runtime
        # status for a remote tool with no local container is UNAVAILABLE -> UNVERIFIED.
        result = run_benchmark_case(
            case=case,
            runner=_runner_for(_unavailable_result("no local container for remote MCP")),
        )
        assert result.baseline.verdict == BASELINE_UNVERIFIED
        assert result.run.otba_verdict == "UNVERIFIED"
        assert result.run.sandbox_failure is True
        # A remote MCP case is never classified as a false block or controlled violation.
        assert result.false_block is False
        assert result.controlled_violation_caught is False


# ---------------------------------------------------------------------------
# Historical drift: two real revisions compared with identical canary input.
# ---------------------------------------------------------------------------

class TestHistoricalDrift:
    def test_drift_pair_carried_in_raw_record(self):
        rev_a = "a" * 40
        rev_b = "b" * 40
        contract_a = _local_oci_contract(
            repository_revision=rev_a,
            tool_registry_revision=rev_a,
            allowed_write_paths=("/tmp/strace_fix/out/allowed.txt",),
        )
        case_a = _case_for(
            contract_a, label="drift-rev-A", historical_drift_pair="A-vs-B",
        )
        result = run_benchmark_case(
            case=case_a,
            runner=_runner_for(_positive_result_with_trace("trace_A.log")),
        )
        assert result.raw_record["historical_drift_pair"] == "A-vs-B"
        assert result.raw_record["repository_revision"] == rev_a
        # The drift comparison itself requires two real executed revisions; here we
        # validate that the harness retains the binding so a real pilot can compare them.


# ---------------------------------------------------------------------------
# Invariants / truth boundaries.
# ---------------------------------------------------------------------------

class TestTruthBoundaries:
    def test_case_requires_64_char_canary_input_hash(self):
        contract = _local_oci_contract()
        with pytest.raises(BenchmarkPilotError):
            BenchmarkCase(
                label="x", contract=contract, canary_command=("/usr/bin/bash",),
                canary_workspace="/tmp/otba-ws", canary_input_sha256="short",
            )

    def test_pilot_requires_40_char_source_revision(self):
        contract = _local_oci_contract()
        case = _case_for(contract)
        with pytest.raises(BenchmarkPilotError):
            run_pilot(cases=[case], source_revision="short", runner=_runner_for(_unavailable_result()))

    def test_pilot_requires_at_least_one_case(self):
        with pytest.raises(BenchmarkPilotError):
            run_pilot(cases=[], source_revision=SHA40)

    def test_no_mock_positive_when_runtime_unavailable(self):
        # The default runner is the REAL run_local_oci_canary. With no Docker, it returns
        # UNAVAILABLE honestly; the harness never fabricates a positive observation.
        contract = _local_oci_contract()
        case = _case_for(contract, label="real-env")
        result = run_benchmark_case(case=case)  # no runner injected -> real path
        # Whatever the real environment is, a positive result is only possible if a real
        # trace parsed. We assert the honest invariant: sandbox_failure or verified.
        assert result.run.runtime_status in {
            "VERIFIED_OBSERVATION", "UNAVAILABLE", "BLOCKED",
            "IMAGE_DIGEST_MISMATCH", "TRACE_DIED", "EXECUTION_FAILED",
        }
        if result.run.sandbox_failure:
            assert result.run.otba_verdict == "UNVERIFIED"
            assert result.run.observed_exec is None

    def test_recommendation_never_green_without_real_data(self):
        # All-unavailable pilot cannot be GO.
        contract = _local_oci_contract()
        case = _case_for(contract, label="unavailable")
        report = run_pilot(
            cases=[case], source_revision=SHA40,
            runner=_runner_for(_unavailable_result()),
        )
        assert report.recommendation != GO

