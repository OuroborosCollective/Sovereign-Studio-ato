"""Tests for the strace trace normalizer (issue #1451).

These tests exercise the real ``parse_strace_trace`` against authentic strace fixtures
captured from real isolated executions (bash echo, whoami, getent DNS, forbidden write).
They assert that the normalizer produces the exact expected observations for each real
scenario and that baseline runtime noise (loader reads, nscd sockets, /dev/tty stdio
wiring) is correctly excluded so a tool is not blamed for runtime overhead.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tool_behavior_trace import (
    ToolBehaviorObservationSet,
    compute_raw_trace_sha256,
    parse_strace_trace,
    observation_set_from_events,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text("utf-8")


# ---------------------------------------------------------------------------
# Real-fixture parse tests: each scenario is a real strace capture.
# ---------------------------------------------------------------------------

def test_trace_a_allowed_write_observed():
    """Scenario A: bash echo -> allowed.txt. The single workspace write is observed."""
    obs = parse_strace_trace(_read("trace_A.log"), peak_memory_bytes=1000, wall_time_ms=10, exit_code=0)
    assert obs.process_exec == ("/usr/bin/bash",)
    assert "/tmp/strace_fix/out/allowed.txt" in obs.filesystem_writes
    # /dev/tty (bash stderr wiring) is baseline stdio, NOT a filesystem write.
    assert "/dev/tty" not in obs.filesystem_writes
    assert obs.network_connects == ()
    assert obs.network_listens == ()
    assert obs.verify() is True


def test_trace_b_read_only_no_writes():
    """Scenario B: whoami. A read-only tool produces no writes and no network."""
    obs = parse_strace_trace(_read("trace_B.log"), peak_memory_bytes=1000, wall_time_ms=10, exit_code=0)
    assert obs.process_exec == ("/usr/bin/whoami",)
    assert obs.filesystem_writes == ()
    assert obs.network_connects == ()
    assert obs.verify() is True


def test_trace_c_dns_connect_observed():
    """Scenario C: getent. A real DNS connect to the resolver is observed."""
    obs = parse_strace_trace(_read("trace_C.log"), peak_memory_bytes=1000, wall_time_ms=10, exit_code=0)
    assert obs.process_exec == ("/usr/bin/getent",)
    assert "10.3.0.10:53" in obs.network_connects
    assert obs.filesystem_writes == ()
    assert obs.verify() is True


def test_trace_d_forbidden_write_observed():
    """Scenario D: bash echo -> forbidden.txt. The forbidden write is observed (not hidden)."""
    obs = parse_strace_trace(_read("trace_D.log"), peak_memory_bytes=1000, wall_time_ms=10, exit_code=0)
    assert obs.process_exec == ("/usr/bin/bash",)
    assert "/tmp/strace_fix/out/forbidden.txt" in obs.filesystem_writes
    assert obs.verify() is True


# ---------------------------------------------------------------------------
# Baseline-exclusion invariants: runtime noise must never be blamed on the tool.
# ---------------------------------------------------------------------------

def test_baseline_loader_reads_excluded():
    """glibc loader reads (/lib, /etc/ld.so.cache) are baseline, not tool reads."""
    raw = (
        '123 openat(AT_FDCWD, "/lib/x86_64-linux-gnu/libc.so.6", O_RDONLY|O_CLOEXEC) = 3\n'
        '123 openat(AT_FDCWD, "/etc/ld.so.cache", O_RDONLY|O_CLOEXEC) = 3\n'
        '123 execve("/usr/bin/true", ["true"], 0x7fff /* 80 vars */) = 0\n'
    )
    obs = parse_strace_trace(raw, peak_memory_bytes=0, wall_time_ms=1, exit_code=0)
    assert obs.process_exec == ("/usr/bin/true",)
    assert obs.filesystem_reads == ()
    assert obs.filesystem_writes == ()


def test_baseline_nscd_socket_excluded():
    """AF_UNIX nscd resolver sockets are baseline network noise, not tool connects."""
    raw = (
        '123 connect(3, {sa_family=AF_UNIX, sun_path="/var/run/nscd/socket"}, 110) = -1 ENOENT (No such file or directory)\n'
        '123 execve("/usr/bin/true", ["true"], 0x7fff /* 80 vars */) = 0\n'
    )
    obs = parse_strace_trace(raw, peak_memory_bytes=0, wall_time_ms=1, exit_code=0)
    assert obs.network_connects == ()
    assert obs.network_listens == ()


def test_baseline_dev_tty_write_excluded():
    """bash opening /dev/tty for stderr is stdio wiring, not a filesystem write."""
    raw = (
        '123 openat(AT_FDCWD, "/dev/tty", O_RDWR|O_NONBLOCK) = 3\n'
        '123 execve("/usr/bin/bash", ["bash"], 0x7fff /* 80 vars */) = 0\n'
    )
    obs = parse_strace_trace(raw, peak_memory_bytes=0, wall_time_ms=1, exit_code=0)
    assert "/dev/tty" not in obs.filesystem_writes
    assert obs.filesystem_writes == ()


# ---------------------------------------------------------------------------
# Normalization + determinism invariants.
# ---------------------------------------------------------------------------

def test_observation_set_is_frozen_and_hashed():
    obs = parse_strace_trace(_read("trace_A.log"), peak_memory_bytes=1000, wall_time_ms=10, exit_code=0)
    assert obs.trace_artifact_sha256 != ""
    with pytest.raises((AttributeError, Exception)):
        obs.process_exec = ("tampered",)


def test_trace_artifact_sha256_is_reproducible():
    """trace_artifact_sha256 is the canonical hash over the observation set (reproducible)."""
    raw = _read("trace_A.log")
    obs = parse_strace_trace(raw, peak_memory_bytes=1000, wall_time_ms=10, exit_code=0)
    assert obs.verify() is True
    # The canonical observation hash is distinct from the raw-bytes content hash.
    assert obs.trace_artifact_sha256 != compute_raw_trace_sha256(raw)


def test_compute_raw_trace_sha256_is_deterministic():
    """The raw-bytes hash binds the exact captured trace text."""
    raw = _read("trace_A.log")
    assert compute_raw_trace_sha256(raw) == compute_raw_trace_sha256(raw)


def test_same_trace_produces_same_observations():
    raw = _read("trace_C.log")
    a = parse_strace_trace(raw, peak_memory_bytes=1000, wall_time_ms=10, exit_code=0)
    b = parse_strace_trace(raw, peak_memory_bytes=1000, wall_time_ms=10, exit_code=0)
    assert a == b
    assert a.trace_artifact_sha256 == b.trace_artifact_sha256


def test_different_trace_produces_different_artifact_hash():
    a = parse_strace_trace(_read("trace_A.log"), peak_memory_bytes=0, wall_time_ms=1, exit_code=0)
    b = parse_strace_trace(_read("trace_D.log"), peak_memory_bytes=0, wall_time_ms=1, exit_code=0)
    assert a.trace_artifact_sha256 != b.trace_artifact_sha256


# ---------------------------------------------------------------------------
# Invalid / empty input.
# ---------------------------------------------------------------------------

def test_empty_trace_produces_empty_observations():
    obs = parse_strace_trace("", peak_memory_bytes=0, wall_time_ms=0, exit_code=0)
    assert obs.process_exec == ()
    assert obs.filesystem_writes == ()
    assert obs.network_connects == ()
    assert obs.verify() is True


def test_compute_raw_trace_sha256_is_sha256():
    digest = compute_raw_trace_sha256("hello\n")
    assert digest == hashlib.sha256(b"hello\n").hexdigest()


# ---------------------------------------------------------------------------
# Structured-event bridge (for runtimes that capture events directly).
# ---------------------------------------------------------------------------

def test_observation_set_from_events_exec_and_write():
    events = [
        {"kind": "execve", "target": "/usr/bin/true"},
        {"kind": "openat-write", "target": "/workspace/repo/out"},
        {"kind": "openat-read", "target": "/lib/libc.so.6"},  # baseline -> excluded
        {"kind": "connect", "target": "registry.example.invalid:443"},
    ]
    obs = observation_set_from_events(
        events, peak_memory_bytes=1024, wall_time_ms=5, exit_code=0
    )
    assert obs.process_exec == ("/usr/bin/true",)
    assert obs.filesystem_writes == ("/workspace/repo/out",)
    assert obs.filesystem_reads == ()
    assert obs.network_connects == ("registry.example.invalid:443",)


def test_observation_set_from_events_ignores_garbage():
    events = [
        "not-a-dict",
        {"kind": "execve"},  # missing target
        {"kind": "unknown", "target": "/x"},
        {"kind": "execve", "target": "/usr/bin/true"},
    ]
    obs = observation_set_from_events(
        events, peak_memory_bytes=0, wall_time_ms=0, exit_code=0
    )
    assert obs.process_exec == ("/usr/bin/true",)


def test_observation_set_from_events_bind_is_listen():
    events = [{"kind": "bind", "target": "0.0.0.0:8080"}]
    obs = observation_set_from_events(
        events, peak_memory_bytes=0, wall_time_ms=0, exit_code=0
    )
    assert obs.network_listens == ("0.0.0.0:8080",)
    assert obs.network_connects == ()


def test_observation_set_from_events_excludes_baseline_write():
    events = [{"kind": "openat-write", "target": "/dev/tty"}]
    obs = observation_set_from_events(
        events, peak_memory_bytes=0, wall_time_ms=0, exit_code=0
    )
    assert obs.filesystem_writes == ()
