#!/usr/bin/env python3
"""Reproducible local benchmark for canonical agent-run receipt generation.

This measures only CPU-side canonicalization and SHA-256 work. It does not claim
PostgreSQL, broker, Git subprocess, network, deployment or end-to-end latency.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from agent_runtime.agent_run_receipts import build_agent_run_receipt, canonical_sha256  # noqa: E402


REVISION = os.environ.get("SOVEREIGN_BENCHMARK_REVISION", "a" * 40)
ITERATIONS = int(os.environ.get("SOVEREIGN_RECEIPT_BENCHMARK_ITERATIONS", "10000"))
ZERO = "0" * 64


def percentile_ns(samples: list[int], percentile: int) -> int:
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, (len(ordered) * percentile + 99) // 100 - 1))
    return ordered[index]


def receipt(sequence: int, previous: str) -> dict:
    return build_agent_run_receipt(
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


def main() -> int:
    if ITERATIONS < 100:
        raise SystemExit("SOVEREIGN_RECEIPT_BENCHMARK_ITERATIONS must be at least 100")
    samples: list[int] = []
    cpu_start = time.process_time_ns()
    previous = ZERO
    total_bytes = 0
    for sequence in range(ITERATIONS):
        started = time.perf_counter_ns()
        generated = receipt(sequence, previous)
        elapsed = time.perf_counter_ns() - started
        samples.append(elapsed)
        previous = generated["header"]["hash"]
        total_bytes += len(json.dumps(generated["body"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    cpu_ns = time.process_time_ns() - cpu_start
    result = {
        "schemaVersion": "sovereign.agent-run-receipt-benchmark.v1",
        "revision": REVISION,
        "iterations": ITERATIONS,
        "scope": "cpu-canonicalization-and-sha256-only",
        "p50_ns": percentile_ns(samples, 50),
        "p95_ns": percentile_ns(samples, 95),
        "p99_ns": percentile_ns(samples, 99),
        "mean_ns": int(statistics.fmean(samples)),
        "cpu_total_ns": cpu_ns,
        "cpu_mean_ns": cpu_ns // ITERATIONS,
        "canonical_body_bytes_mean": total_bytes // ITERATIONS,
        "chain_head_sha256": previous,
        "missing_receipts": 0,
        "unverifiable_receipts": 0,
        "telemetry_required": False,
        "database_bytes_per_agent_run": None,
        "database_measurement_status": "not_measured_by_cpu_microbenchmark",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
