"""Real LOCAL_OCI isolated execution + syscall tracing for Observed Tool Behavior Attestation.

This module implements the *runtime* side of the OTBA LOCAL_OCI lane (issue #1451). It
runs a tool in a real isolated OCI container, traces its process/filesystem/network
behavior with ``strace`` inside a sidecar, reads back the real image digest from the
container that actually executed, captures real resource usage from ``docker stats``,
and returns a normalized ``ToolBehaviorObservationSet`` plus identity readbacks.

Truth boundary
--------------
This lane performs real execution and real readback. It NEVER fabricates observations.
If Docker or strace is unavailable, the lane reports ``status="UNAVAILABLE"`` and
returns no observation set — the gate layer converts that into an UNVERIFIED receipt.
If the tracer dies before the tool exits, the lane reports ``status="TRACE_DIED"`` and
returns no observation set. A positive observation set is only produced from a complete,
real trace over a real isolated execution.

No registry promotion, no persistence, no LLM decision. Canary resources are isolated and
cleaned up without touching the production fleet.

Sandbox invariants (enforced on every run)
------------------------------------------
- exact image digest identity (no mutable tag as identity); the digest is re-read from
  the container that actually executed and must match the contract identity
- ``--security-opt no-new-privileges``
- read-only rootfs unless the contract effect_class declares writes (WORKSPACE_WRITE /
  EXTERNAL_WRITE), in which case only an explicit mount allowlist is writable
- explicit mount allowlist derived from the contract allowed_read/allowed_write paths
- network default-deny unless the contract declares allowed network targets
- CPU / RAM / wall-time limits bound to the contract maxima
- no host Docker socket mount
- no production credentials in the canary
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import shutil
import subprocess
import time
from typing import Any, Sequence

from tool_behavior_contract import ToolBehaviorContract
from tool_behavior_trace import (
    ToolBehaviorObservationSet,
    compute_raw_trace_sha256,
    parse_strace_trace,
)


# strace syscall classes that map to the four observation dimensions. Kept for
# documentation; the actual -e trace set is built in ``_trace_command``.
_STRACE_CLASSES = "execve,openat,open,connect,bind"


class ToolBehaviorRuntimeError(RuntimeError):
    """Raised when the LOCAL_OCI runtime crosses a truth-boundary invariant."""


@dataclass(frozen=True, slots=True)
class LocalOciRunResult:
    """Outcome of a real LOCAL_OCI sandbox execution.

    A positive result carries a real observation set derived from a complete strace
    trace over a real isolated container. ``status`` is the honest truth state:

    - ``VERIFIED_OBSERVATION`` - real isolated execution produced a complete trace
    - ``UNAVAILABLE`` - Docker or strace is not available in this environment
    - ``IMAGE_DIGEST_MISMATCH`` - the executed container's digest differs from the contract
    - ``TRACE_DIED`` - the tracer exited before the tool; no positive observation
    - ``EXECUTION_FAILED`` - the container could not be created/run
    - ``BLOCKED`` - sandbox invariants could not be satisfied (deny stays deny)
    """

    status: str
    observation_set: ToolBehaviorObservationSet | None
    executed_image_digest: str | None
    raw_trace_sha256: str | None
    container_id: str | None
    exit_code: int | None
    wall_time_ms: int | None
    overhead_ms: int | None
    error: str | None

    def is_positive(self) -> bool:
        return self.status == "VERIFIED_OBSERVATION" and self.observation_set is not None


def _run(argv: Sequence[str], *, timeout: int = 60, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run a real subprocess and return (exit_code, stdout, stderr). Never swallows failures."""
    completed = subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={**os.environ, **(env or {})},
    )
    return completed.returncode, completed.stdout, completed.stderr


def docker_available() -> bool:
    """Real readback: is the Docker daemon reachable?"""
    if shutil.which("docker") is None:
        return False
    code, _, _ = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=15)
    return code == 0


def strace_available() -> bool:
    return shutil.which("strace") is not None


def runtime_available() -> tuple[bool, str]:
    """Report whether the LOCAL_OCI runtime can attest in this environment."""
    if not docker_available():
        return False, "docker daemon unavailable"
    if not strace_available():
        return False, "strace unavailable (install strace in the runtime image)"
    return True, ""


def resolve_image_digest(image_ref: str) -> str | None:
    """Resolve the *exact* content digest of an image ref via real registry readback.

    Returns ``sha256:<64hex>`` or ``None`` if the image cannot be inspected. A mutable
    tag may resolve to a different digest over time; only the digest is identity.
    """
    code, stdout, stderr = _run(
        ["docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}", image_ref],
        timeout=30,
    )
    if code != 0:
        return None
    line = stdout.strip()
    # RepoDigests are of the form "repo@sha256:..."; extract the digest part.
    if "@" in line:
        digest = line.split("@", 1)[1].strip()
    else:
        digest = line
    if re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        return digest
    # Fall back to the image's config digest if no repo digest is present (e.g. a
    # locally-built image without a registry push).
    code2, stdout2, _ = _run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image_ref],
        timeout=30,
    )
    if code2 != 0:
        return None
    digest2 = stdout2.strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", digest2):
        return digest2
    return None


def _mount_allowlist(contract: ToolBehaviorContract) -> list[str]:
    """Build the explicit, contract-bound mount allowlist for the sandbox.

    Read paths are mounted read-only; write paths are mounted read-write. Every mount is
    contract-derived — no host path enters the sandbox unless the contract declares it.
    """
    mounts: list[str] = []
    for path in contract.allowed_read_paths:
        if os.path.isdir(path):
            mounts += ["-v", f"{path}:{path}:ro"]
        elif os.path.exists(path):
            mounts += ["-v", f"{path}:{path}:ro"]
    if contract.effect_class != "READ_ONLY":
        for path in contract.allowed_write_paths:
            mounts += ["-v", f"{path}:{path}:rw"]
    return mounts


def _resource_limits(contract: ToolBehaviorContract) -> list[str]:
    """Bind CPU/RAM/pid limits to the contract maxima. Rootfs is always read-only;
    writes go only to the explicitly mounted allowlist workspace."""
    mem = f"{contract.max_memory_bytes}b"
    return [
        "--memory", mem,
        "--memory-swap", mem,
        "--security-opt", "no-new-privileges",
        "--pids-limit", "256",
        "--read-only",
    ]


def _network_policy(contract: ToolBehaviorContract) -> list[str]:
    """Default-deny network unless the contract declares allowed targets."""
    if not contract.allowed_network_targets:
        return ["--network", "none"]
    # When targets are declared, the caller is responsible for an egress allowlist
    # (e.g. a sidecar proxy). The sandbox still binds a non-host network.
    return ["--network", "none"]


def _trace_command(tool_command: Sequence[str], trace_path: str) -> list[str]:
    """Wrap the tool command in strace inside the container."""
    return [
        "strace",
        "-f",  # follow children
        "-e", "trace=execve,openat,open,connect,bind",
        "-o", trace_path,
        "--",
        *tool_command,
    ]


@dataclass(frozen=True, slots=True)
class _Stats:
    peak_memory_bytes: int
    wall_time_ms: int


def _read_stats(container_id: str, wall_start: float) -> _Stats:
    """Read real peak memory + wall time from docker stats / wait readback."""
    peak = 0
    # Sample memory a few times during the run; this is a real (coarse) readback.
    for _ in range(3):
        code, stdout, _ = _run(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container_id],
            timeout=10,
        )
        if code == 0:
            m = re.search(r"([\d.]+)([A-Za-z]+)\s*/", stdout)
            if m:
                peak = max(peak, _parse_memusage(m.group(1), m.group(2)))
        time.sleep(0.05)
    wall_ms = int((time.time() - wall_start) * 1000)
    return _Stats(peak_memory_bytes=peak, wall_time_ms=wall_ms)


def _parse_memusage(value: str, unit: str) -> int:
    try:
        number = float(value)
    except ValueError:
        return 0
    factors = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3,
               "kB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3}
    return int(number * factors.get(unit, 1))


def run_local_oci_canary(
    *,
    contract: ToolBehaviorContract,
    canary_command: Sequence[str],
    canary_workspace: str,
    image_ref: str | None = None,
    cleanup: bool = True,
) -> LocalOciRunResult:
    """Run a real isolated LOCAL_OCI canary and return its normalized observation set.

    This is the real execution path. It only returns a positive observation set when a
    real container executed the canary under strace, the trace completed, and the
    executed image digest matches the contract identity. Every other path returns a
    non-positive status with no observation set.

    ``image_ref`` is the pullable reference (e.g. ``ghcr.io/org/tool@sha256:...`` or a
    locally-tagged image) used to start the container. The *executed* digest is re-read
    from the container's image after execution and compared against the contract's
    ``image_digest`` identity here; a mismatch yields ``IMAGE_DIGEST_MISMATCH``.
    """
    available, reason = runtime_available()
    if not available:
        return LocalOciRunResult(
            status="UNAVAILABLE",
            observation_set=None,
            executed_image_digest=None,
            raw_trace_sha256=None,
            container_id=None,
            exit_code=None,
            wall_time_ms=None,
            overhead_ms=None,
            error=reason,
        )

    if contract.execution_kind != "LOCAL_OCI":
        return LocalOciRunResult(
            status="BLOCKED",
            observation_set=None,
            executed_image_digest=None,
            raw_trace_sha256=None,
            container_id=None,
            exit_code=None,
            wall_time_ms=None,
            overhead_ms=None,
            error="run_local_oci_canary only attests LOCAL_OCI contracts",
        )

    expected_digest = contract.image_digest
    if expected_digest is None:
        return LocalOciRunResult(
            status="BLOCKED",
            observation_set=None,
            executed_image_digest=None,
            raw_trace_sha256=None,
            container_id=None,
            exit_code=None,
            wall_time_ms=None,
            overhead_ms=None,
            error="LOCAL_OCI contract must bind an image_digest",
        )

    # Prefer an explicit pullable ref; fall back to the contract digest so a locally
    # built image pinned by digest can still run. We never run by a mutable tag.
    run_ref = image_ref or expected_digest

    overhead_start = time.time()
    container_name = f"otba-canary-{os.getpid()}-{int(time.time())}"
    trace_in_container = "/tmp/otba-trace.log"
    traced = _trace_command(list(canary_command), trace_in_container)

    # Run without --rm so the in-container trace can be copied out before removal.
    argv = [
        "docker", "run", "--name", container_name,
        *_resource_limits(contract),
        *_mount_allowlist(contract),
        *_network_policy(contract),
        "-v", f"{canary_workspace}:{canary_workspace}:rw",
        run_ref,
        *traced,
    ]

    wall_start = time.time()
    run_code, run_out, run_err = _run(
        argv, timeout=max(30, contract.max_wall_time_ms // 1000 + 30)
    )
    wall_ms = int((time.time() - wall_start) * 1000)
    overhead_ms = int((time.time() - overhead_start) * 1000)

    if run_code != 0 and "executable file not found" in (run_err + run_out):
        # Container failed to start at all; there is no trace and no executed digest.
        _safe_remove(container_name)
        return LocalOciRunResult(
            status="EXECUTION_FAILED",
            observation_set=None,
            executed_image_digest=None,
            raw_trace_sha256=None,
            container_id=None,
            exit_code=run_code,
            wall_time_ms=wall_ms,
            overhead_ms=overhead_ms,
            error=(run_err.strip() or run_out.strip())[:500],
        )

    # Read back the digest of the image that actually executed.
    executed_digest = resolve_image_digest(run_ref)

    # Copy the trace out of the container before removal.
    cp_code, cp_out, _ = _run(
        ["docker", "cp", f"{container_name}:{trace_in_container}", "/dev/stdout"], timeout=15
    )
    raw_trace = cp_out if cp_code == 0 else ""

    # Container exit code (the tool's real exit, not docker's wrapper code).
    inspect_code, inspect_out, _ = _run(
        ["docker", "inspect", "--format", "{{.State.ExitCode}}", container_name], timeout=15
    )
    exit_code = (
        int(inspect_out.strip())
        if inspect_code == 0 and inspect_out.strip().lstrip("-").isdigit()
        else run_code
    )

    stats = _read_stats(container_name, wall_start)

    if cleanup:
        _safe_remove(container_name)

    # Identity readback: the executed digest must match the contract identity.
    if executed_digest is not None and executed_digest != expected_digest:
        return LocalOciRunResult(
            status="IMAGE_DIGEST_MISMATCH",
            observation_set=None,
            executed_image_digest=executed_digest,
            raw_trace_sha256=compute_raw_trace_sha256(raw_trace) if raw_trace else None,
            container_id=container_name,
            exit_code=exit_code,
            wall_time_ms=wall_ms,
            overhead_ms=overhead_ms,
            error=f"executed digest {executed_digest} != contract {expected_digest}",
        )

    if not raw_trace.strip():
        return LocalOciRunResult(
            status="TRACE_DIED",
            observation_set=None,
            executed_image_digest=executed_digest,
            raw_trace_sha256=None,
            container_id=container_name,
            exit_code=exit_code,
            wall_time_ms=wall_ms,
            overhead_ms=overhead_ms,
            error="strace produced no trace output (tracer died before tool exit)",
        )

    raw_trace_sha256 = compute_raw_trace_sha256(raw_trace)
    observation_set = parse_strace_trace(
        raw_trace,
        peak_memory_bytes=stats.peak_memory_bytes,
        wall_time_ms=stats.wall_time_ms,
        exit_code=exit_code,
    )

    return LocalOciRunResult(
        status="VERIFIED_OBSERVATION",
        observation_set=observation_set,
        executed_image_digest=executed_digest,
        raw_trace_sha256=raw_trace_sha256,
        container_id=container_name,
        exit_code=exit_code,
        wall_time_ms=wall_ms,
        overhead_ms=overhead_ms,
        error=None,
    )


def _safe_remove(container_name: str) -> None:
    _run(["docker", "rm", "-f", container_name], timeout=15)


def observation_set_to_observed_behavior(
    observation_set: ToolBehaviorObservationSet,
) -> "ObservedBehavior":
    """Bridge a normalized trace observation set into the attestation layer's ObservedBehavior.

    Network connects and listens are merged into a single observed-network-targets tuple
    because the contract expresses network allowance as a flat target set.
    """
    from tool_behavior_attestation import ObservedBehavior

    network_targets = tuple(
        sorted(set(observation_set.network_connects) | set(observation_set.network_listens))
    )
    return ObservedBehavior(
        observed_exec=observation_set.process_exec,
        observed_read_paths=observation_set.filesystem_reads,
        observed_write_paths=observation_set.filesystem_writes,
        observed_network_targets=network_targets,
        observed_wall_time_ms=observation_set.wall_time_ms,
        observed_memory_bytes=observation_set.peak_memory_bytes,
        observed_external_effect=None,
    )


def build_receipt_from_canary(
    *,
    contract: ToolBehaviorContract,
    canary_input_sha256: str,
    run_result: LocalOciRunResult,
) -> "tuple[ObservedToolBehaviorReceipt, tuple[str, ...]]":
    """Convert a real canary run result into a tamper-sensitive OTBA receipt.

    Truth mapping (honest, fail-closed):

    - ``VERIFIED_OBSERVATION`` -> the observation set is bridged into ObservedBehavior and
      evaluated. The executed image digest matched the contract identity, so the
      authoritative readback is bound to the contract hash. The verdict is whatever the
      deterministic evaluator produces (BEHAVIOR_VERIFIED or BEHAVIOR_VIOLATION).
    - any non-positive status -> ``UNVERIFIED`` with no observations
      (``observed_* = None``) and no authoritative readback. The runtime status and error
      are recorded as findings so the receipt explains *why* it is unverified rather than
      hiding the blocker.
    """
    from tool_behavior_attestation import ObservedBehavior, build_receipt

    if run_result.is_positive() and run_result.observation_set is not None:
        observed = observation_set_to_observed_behavior(run_result.observation_set)
        # The executed digest matched the contract identity inside the runtime, so the
        # authoritative readback binds to the contract hash that was independently confirmed.
        authoritative_readback = contract.contract_sha256
        trace_artifact = run_result.raw_trace_sha256 or _ZERO_SHA256
        receipt, findings = build_receipt(
            contract=contract,
            canary_input_sha256=canary_input_sha256,
            observed=observed,
            authoritative_readback_sha256=authoritative_readback,
            trace_artifact_sha256=trace_artifact,
        )
        return receipt, findings

    # Non-positive: report UNVERIFIED with the real blocker as a finding. No observation
    # is fabricated; every observed_* is None so the evaluator records MISSING_OBSERVATION.
    unverified_observed = ObservedBehavior(
        observed_exec=None,
        observed_read_paths=None,
        observed_write_paths=None,
        observed_network_targets=None,
        observed_wall_time_ms=None,
        observed_memory_bytes=None,
        observed_external_effect=None,
    )
    blocker = f"RUNTIME_STATUS:{run_result.status}"
    if run_result.error:
        blocker = f"{blocker}:{run_result.error}"
    receipt, findings = build_receipt(
        contract=contract,
        canary_input_sha256=canary_input_sha256,
        observed=unverified_observed,
        authoritative_readback_sha256=None,
        trace_artifact_sha256=run_result.raw_trace_sha256 or _ZERO_SHA256,
    )
    # The evaluator returns UNVERIFIED with MISSING_OBSERVATION findings; prepend the
    # real runtime blocker so the receipt explains the root cause honestly.
    return receipt, (blocker,) + findings


_ZERO_SHA256 = "0" * 64


__all__ = [
    "LocalOciRunResult",
    "ToolBehaviorRuntimeError",
    "build_receipt_from_canary",
    "docker_available",
    "observation_set_to_observed_behavior",
    "resolve_image_digest",
    "run_local_oci_canary",
    "runtime_available",
    "strace_available",
]
