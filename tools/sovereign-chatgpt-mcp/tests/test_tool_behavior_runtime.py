"""Tests for the LOCAL_OCI canary runtime and the OTBA gate (issue #1450).

The runtime cannot run a real Docker canary in this environment (no Docker daemon).
Per the truth rules, those tests are skipped honestly rather than faked. What *can* be
verified deterministically here is:

- the runtime availability probes (docker_available / strace_available / runtime_available)
- the honest non-positive status paths (UNAVAILABLE / BLOCKED / EXECUTION_FAILED)
- the gate layer that bridges a real observation set into an ObservedBehavior and a
  tamper-sensitive receipt, including the fail-closed UNVERIFIED path for non-positive runs
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tool_behavior_attestation import (
    ObservedBehavior,
    ObservedToolBehaviorReceipt,
    receipt_from_mapping,
)
from tool_behavior_contract import ToolBehaviorContract
from tool_behavior_runtime import (
    LocalOciRunResult,
    build_receipt_from_canary,
    docker_available,
    observation_set_to_observed_behavior,
    run_local_oci_canary,
    runtime_available,
    strace_available,
)
from tool_behavior_trace import (
    ToolBehaviorObservationSet,
    compute_raw_trace_sha256,
    parse_strace_trace,
)

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


# ---------------------------------------------------------------------------
# Availability probes: honest about the real environment.
# ---------------------------------------------------------------------------

def test_runtime_available_reflects_real_environment():
    """runtime_available is a real probe of docker + strace, returning (ok, reason)."""
    ok, reason = runtime_available()
    assert isinstance(ok, bool)
    assert isinstance(reason, str)
    if ok:
        assert docker_available() and strace_available()
    else:
        # When unavailable, the reason must explain the real blocker, never empty.
        assert reason.strip()


def test_docker_and_strace_probes_are_booleans():
    assert isinstance(docker_available(), bool)
    assert isinstance(strace_available(), bool)


# ---------------------------------------------------------------------------
# Honest non-positive runtime paths.
# ---------------------------------------------------------------------------

def _runtime_ok() -> bool:
    ok, _ = runtime_available()
    return ok


@pytest.mark.skipif(not _runtime_ok(), reason="Docker/strace unavailable: cannot run a real canary container")
def test_canary_runs_when_runtime_available():
    # When docker + strace ARE available the runtime must run the real canary.
    contract = _local_oci_contract()
    result = run_local_oci_canary(contract=contract, canary_command=["/usr/bin/true"], canary_workspace="/tmp/otba-ws")
    # We do not assert a positive verdict (the image may not match); we assert it did
    # not short-circuit to UNAVAILABLE just because a button exists.
    assert result.status != "UNAVAILABLE"


def test_canary_blocks_non_local_oci_contract():
    """A REMOTE_MCP contract cannot be attested by the local OCI canary.

    When the runtime is available, execution_kind is rejected as BLOCKED. When the
    runtime itself is unavailable, UNAVAILABLE wins (no container can run at all) — both
    are non-positive and never fake success.
    """
    contract = _local_oci_contract(
        execution_kind="REMOTE_MCP",
        image_digest=None,
        effect_class="READ_ONLY",
        allowed_write_paths=(),
    )
    result = run_local_oci_canary(contract=contract, canary_command=["/usr/bin/true"], canary_workspace="/tmp/otba-ws")
    assert result.is_positive() is False
    assert result.error is not None
    ok, _ = runtime_available()
    assert result.status == ("BLOCKED" if ok else "UNAVAILABLE")


def test_canary_blocks_local_oci_without_image_digest():
    """A LOCAL_OCI contract without an image_digest is rejected at construction (fail-closed)."""
    from tool_behavior_contract import ToolBehaviorContractError

    with pytest.raises(ToolBehaviorContractError):
        _local_oci_contract(image_digest=None)


# ---------------------------------------------------------------------------
# Bridge: observation set -> ObservedBehavior.
# ---------------------------------------------------------------------------

def test_observation_set_bridge_maps_all_dimensions():
    """The bridge preserves exec/read/write/network/resource from the trace."""
    obs_set = parse_strace_trace(_read("trace_C.log"), peak_memory_bytes=4096, wall_time_ms=12, exit_code=0)
    observed = observation_set_to_observed_behavior(obs_set)
    assert observed.observed_exec == obs_set.process_exec
    assert observed.observed_read_paths == obs_set.filesystem_reads
    assert observed.observed_write_paths == obs_set.filesystem_writes
    # network connects and listens are merged into the flat target set.
    expected_network = tuple(sorted(set(obs_set.network_connects) | set(obs_set.network_listens)))
    assert observed.observed_network_targets == expected_network
    assert observed.observed_wall_time_ms == obs_set.wall_time_ms
    assert observed.observed_memory_bytes == obs_set.peak_memory_bytes
    assert observed.observed_external_effect is None


def test_observation_set_bridge_sorts_network_targets():
    """Merged network targets are deterministically sorted for a stable hash."""
    obs_set = ToolBehaviorObservationSet(
        process_exec=("/usr/bin/curl",),
        filesystem_reads=(),
        filesystem_writes=(),
        network_connects=("registry.example.invalid:443", "10.3.0.10:53"),
        network_listens=(),
        peak_memory_bytes=0,
        wall_time_ms=0,
        exit_code=0,
    )
    observed = observation_set_to_observed_behavior(obs_set)
    assert observed.observed_network_targets == ("10.3.0.10:53", "registry.example.invalid:443")


# ---------------------------------------------------------------------------
# Gate: build_receipt_from_canary — the core OTBA receipt bridge.
# ---------------------------------------------------------------------------

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


def test_gate_positive_within_contract_yields_behavior_verified():
    """A real canary whose observed writes are all declared -> BEHAVIOR_VERIFIED."""
    # The contract declares the exact observed write path (matching is set-membership, not prefix).
    contract = _local_oci_contract(
        allowed_write_paths=("/tmp/strace_fix/out/allowed.txt",),
        allowed_exec=("/usr/bin/bash",),
    )
    result = _positive_result_with_trace("trace_A.log")
    receipt, findings = build_receipt_from_canary(contract=contract, canary_input_sha256=CANARY_INPUT_SHA, run_result=result)
    assert receipt.verdict == "BEHAVIOR_VERIFIED"
    assert receipt.verify() is True
    assert "BEHAVIOR_WITHIN_CONTRACT" in findings
    # The authoritative readback is bound to the contract hash (identity was confirmed).
    assert receipt.authoritative_readback_sha256 == contract.contract_sha256
    # The gate binds the trace artifact to the raw trace content hash (the captured bytes).
    assert receipt.trace_artifact_sha256 == result.raw_trace_sha256


def test_gate_positive_violation_yields_behavior_violation():
    """A real canary writing an undeclared path -> BEHAVIOR_VIOLATION (not hidden)."""
    # Contract declares NO write paths, but trace_A wrote /tmp/strace_fix/out/allowed.txt.
    contract = _local_oci_contract(allowed_write_paths=(), allowed_exec=("/usr/bin/bash",))
    result = _positive_result_with_trace("trace_A.log")
    receipt, findings = build_receipt_from_canary(contract=contract, canary_input_sha256=CANARY_INPUT_SHA, run_result=result)
    assert receipt.verdict == "BEHAVIOR_VIOLATION"
    assert receipt.verify() is True
    assert any(f.startswith("WRITE_PATH_NOT_DECLARED:") for f in findings)


def test_gate_positive_undeclared_network_is_violation():
    """A real DNS connect not in the contract's allowed network targets -> violation."""
    contract = _local_oci_contract(
        allowed_exec=("/usr/bin/getent",),
        allowed_network_targets=(),
    )
    result = _positive_result_with_trace("trace_C.log")
    receipt, findings = build_receipt_from_canary(contract=contract, canary_input_sha256=CANARY_INPUT_SHA, run_result=result)
    assert receipt.verdict == "BEHAVIOR_VIOLATION"
    assert any(f.startswith("NETWORK_TARGET_NOT_DECLARED:") for f in findings)


def test_gate_unavailable_yields_unverified_with_blocker():
    """An UNAVAILABLE runtime result -> UNVERIFIED receipt naming the real blocker."""
    contract = _local_oci_contract()
    result = LocalOciRunResult(
        status="UNAVAILABLE",
        observation_set=None,
        executed_image_digest=None,
        raw_trace_sha256=None,
        container_id=None,
        exit_code=None,
        wall_time_ms=None,
        overhead_ms=None,
        error="docker daemon unavailable",
    )
    receipt, findings = build_receipt_from_canary(contract=contract, canary_input_sha256=CANARY_INPUT_SHA, run_result=result)
    assert receipt.verdict == "UNVERIFIED"
    assert receipt.verify() is True
    assert receipt.authoritative_readback_sha256 is None
    assert any(f.startswith("RUNTIME_STATUS:UNAVAILABLE") for f in findings)
    assert "RUNTIME_STATUS:UNAVAILABLE:docker daemon unavailable" in findings


def test_gate_digest_mismatch_yields_unverified_with_blocker():
    """An IMAGE_DIGEST_MISMATCH result -> UNVERIFIED with the mismatch recorded."""
    contract = _local_oci_contract()
    result = LocalOciRunResult(
        status="IMAGE_DIGEST_MISMATCH",
        observation_set=None,
        executed_image_digest="sha256:" + "c" * 64,
        raw_trace_sha256=None,
        container_id=None,
        exit_code=None,
        wall_time_ms=None,
        overhead_ms=None,
        error="executed digest differs from contract",
    )
    receipt, findings = build_receipt_from_canary(contract=contract, canary_input_sha256=CANARY_INPUT_SHA, run_result=result)
    assert receipt.verdict == "UNVERIFIED"
    assert any(f.startswith("RUNTIME_STATUS:IMAGE_DIGEST_MISMATCH") for f in findings)


def test_gate_trace_died_yields_unverified_with_blocker():
    result = LocalOciRunResult(
        status="TRACE_DIED",
        observation_set=None,
        executed_image_digest=DIGEST,
        raw_trace_sha256="0" * 64,
        container_id="abc",
        exit_code=0,
        wall_time_ms=5,
        overhead_ms=1,
        error="tracer exited before tool",
    )
    contract = _local_oci_contract()
    receipt, findings = build_receipt_from_canary(contract=contract, canary_input_sha256=CANARY_INPUT_SHA, run_result=result)
    assert receipt.verdict == "UNVERIFIED"
    assert any(f.startswith("RUNTIME_STATUS:TRACE_DIED") for f in findings)


# ---------------------------------------------------------------------------
# Receipt tamper-resistance across serialization.
# ---------------------------------------------------------------------------

def test_receipt_round_trips_through_mapping():
    contract = _local_oci_contract(allowed_write_paths=("/tmp/strace_fix/out/allowed.txt",))
    result = _positive_result_with_trace("trace_A.log")
    receipt, _ = build_receipt_from_canary(contract=contract, canary_input_sha256=CANARY_INPUT_SHA, run_result=result)
    record = receipt.canonical_record()
    restored = receipt_from_mapping(record)
    assert restored == receipt
    assert restored.verify() is True


def test_receipt_rejects_tampered_mapping():
    contract = _local_oci_contract(allowed_write_paths=("/tmp/strace_fix/out/allowed.txt",))
    result = _positive_result_with_trace("trace_A.log")
    receipt, _ = build_receipt_from_canary(contract=contract, canary_input_sha256=CANARY_INPUT_SHA, run_result=result)
    record = receipt.canonical_record()
    record["receiptSha256"] = "0" * 64
    with pytest.raises(Exception):
        receipt_from_mapping(record)


def test_positive_receipt_binds_canary_input_hash():
    contract = _local_oci_contract(allowed_write_paths=("/tmp/strace_fix/out/allowed.txt",))
    result = _positive_result_with_trace("trace_A.log")
    receipt, _ = build_receipt_from_canary(contract=contract, canary_input_sha256=CANARY_INPUT_SHA, run_result=result)
    assert receipt.canary_input_sha256 == CANARY_INPUT_SHA


def test_positive_receipt_binds_contract_hash():
    contract = _local_oci_contract(allowed_write_paths=("/tmp/strace_fix/out/allowed.txt",))
    result = _positive_result_with_trace("trace_A.log")
    receipt, _ = build_receipt_from_canary(contract=contract, canary_input_sha256=CANARY_INPUT_SHA, run_result=result)
    assert receipt.behavior_contract_sha256 == contract.contract_sha256
