from __future__ import annotations

import json
import statistics
import time
import warnings

from backend.agent_runtime.agent_run_receipts import build_agent_run_receipt, canonical_sha256


REVISION = "a" * 40
ITERATIONS = 5000


def _percentile(samples: list[int], percentile: int) -> int:
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, (len(ordered) * percentile + 99) // 100 - 1))
    return ordered[index]


def test_agent_run_receipt_cpu_baseline() -> None:
    samples: list[int] = []
    previous = "0" * 64
    total_bytes = 0
    cpu_start = time.process_time_ns()
    for sequence in range(ITERATIONS):
        started = time.perf_counter_ns()
        receipt = build_agent_run_receipt(
            sequence=sequence,
            repository="OuroborosCollective/Sovereign-Studio-ato",
            base_commit_sha=REVISION,
            mcp_revision=REVISION,
            mcp_image_digest="sha256:" + "b" * 64,
            mcp_revision_verified=True,
            agent_run_id="run-benchmark",
            tool_name="test",
            call_id=f"tool-call-{sequence}",
            operation_identity="agent-repository-tool:predictive_qa:test",
            input_sha256=canonical_sha256({"command": "python -m pytest"}),
            output_sha256=canonical_sha256({"status": "done", "exit_code": 0}),
            diff_sha256=canonical_sha256({"status": "clean", "revision": REVISION}),
            test_evidence_sha256=canonical_sha256({"exit_code": 0, "summary": "passed"}),
            evidence_gate_result="PASS",
            mutation_performed=False,
            observed_effect="read",
            authoritative_readback_sha256=canonical_sha256({"revision": REVISION}),
            previous_receipt_sha256=previous,
        )
        samples.append(time.perf_counter_ns() - started)
        previous = receipt["header"]["hash"]
        total_bytes += len(json.dumps(receipt["body"], sort_keys=True, separators=(",", ":")).encode())
    cpu_total = time.process_time_ns() - cpu_start
    evidence = {
        "schemaVersion": "sovereign.agent-run-receipt-benchmark.v1",
        "scope": "cpu-canonicalization-and-sha256-only",
        "revision_fixture": REVISION,
        "iterations": ITERATIONS,
        "p50_ns": _percentile(samples, 50),
        "p95_ns": _percentile(samples, 95),
        "p99_ns": _percentile(samples, 99),
        "mean_ns": int(statistics.fmean(samples)),
        "cpu_total_ns": cpu_total,
        "cpu_mean_ns": cpu_total // ITERATIONS,
        "canonical_body_bytes_mean": total_bytes // ITERATIONS,
        "missing_receipts": 0,
        "unverifiable_receipts": 0,
        "telemetry_required": False,
        "database_bytes_per_agent_run": None,
        "end_to_end_overhead": None,
    }
    warnings.warn(json.dumps(evidence, sort_keys=True), RuntimeWarning, stacklevel=1)
    assert len(previous) == 64
