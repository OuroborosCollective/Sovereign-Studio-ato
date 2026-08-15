"""Pure trace normalization for Observed Tool Behavior Attestation (OTBA) runtime layer.

This module converts a *real* captured syscall trace (``strace`` output, the format
produced by the LOCAL_OCI tracer sidecar) into a normalized, tamper-sensitive
``ToolBehaviorObservationSet``. It performs no execution, sandboxing, network I/O or
LLM decision. It is deliberately parser-only so it can be exhaustively tested against
real captured trace fixtures without a Docker daemon.

Truth boundary
--------------
The normalizer never invents observations. A syscall that does not appear in the
captured trace is not present in the observation set. ``None``-vs-empty is intentionally
not used here (the runtime always collects a trace when it attests); the runtime layer
is responsible for turning a missing/dead trace into an UNVERIFIED verdict before
calling this normalizer.

Baseline classification
----------------------
A read-only OCI rootfs is the immutable image baseline. Loader / resolver / i18n reads
against that baseline (``/usr``, ``/lib``, loader config, ``/proc``, ``/dev``) are
runtime/loader noise, not tool behavior, and are excluded from ``filesystem_reads``.
This classification is conservative: ``/etc`` is NOT wholesale baseline (only specific
loader/resolver files), so reads of ``/etc/passwd`` or ``/etc/shadow`` remain observed.
Writes are never baseline: every write attempt is observed (a read-only rootfs makes
baseline writes fail, but the attempt is still tool behavior).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Iterable

from tool_behavior_contract import canonical_sha256


# --- strace line parsing -----------------------------------------------------

# A strace line begins with an optional "<pid> " prefix when -f is used.
# Syscall name is followed by "(" ... ") = <result>" or ") = ? <unfinished>".
_LINE_RE = re.compile(r"^(?:\d+\s+)?(?P<syscall>[a-zA-Z_][a-zA-Z0-9_]*)\((?P<args>.*)\)\s*=.*$")
# First quoted string in an execve/openat/open argument list is the path.
_QUOTED_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
# Flags token after the path in openat/open: O_RDONLY, O_WRONLY|O_CREAT, O_RDWR ...
_FLAGS_RE = re.compile(r"O_(?:RDONLY|WRONLY|RDWR|CREAT|TRUNC|APPEND|TMPFILE|DSYNC|SYNC|CLOEXEC|EXCL|NOCTTY|NONBLOCK|DIRECTORY|NOFOLLOW|CLOEXEC)")
# Network family + address fields.
_FAMILY_RE = re.compile(r"sa_family=AF_(?P<fam>INET6?|UNIX|NETLINK|LOCAL)")
_INET_PORT_RE = re.compile(r'sin_port=htons\((?P<port>\d+)\)')
_INET_ADDR_RE = re.compile(r'sin_addr=inet_addr\("(?P<addr>[0-9.]+)\"\)')
_INET6_PORT_RE = re.compile(r'sin6_port=htons\((?P<port>\d+)\)')
_INET6_ADDR_RE = re.compile(r'sin6_addr=inet_pton\(AF_INET6,\s*"(?P<addr>[0-9a-fA-F:]+)\"\)')
_UNIX_PATH_RE = re.compile(r'sun_path="(?P<path>[^"]*)"')
# Result signals: ENOENT / EACCES etc. are still observed attempts.
_ACCESSED_RESULT = re.compile(r"=\s*-?\d+\s*(?:\(.*\))?$|=\s*-1\s+ENOENT|=\s*-1\s+EACCES|=\s*-1\s+EPERM")


def _first_quoted(args: str) -> str | None:
    m = _QUOTED_RE.search(args)
    if not m:
        return None
    return _decode_quoted(m.group(1))


def _decode_quoted(value: str) -> str:
    if "\\" not in value:
        return value
    try:
        return value.encode("latin-1", "backslashreplace").decode("unicode_escape", "surrogateescape")
    except Exception:
        return value


# --- baseline path classification -------------------------------------------

# Immutable OCI rootfs baseline (read-only loader/runtime paths). Conservative: only
# these exact prefixes/files are treated as baseline noise for READS.
_BASELINE_READ_PREFIXES = (
    "/usr/",
    "/lib/",
    "/lib64/",
    "/opt/android-sdk/",
    "/proc/",
    "/sys/",
)
_BASELINE_READ_EXACT = frozenset({
    "/dev/null",
    "/dev/zero",
    "/dev/urandom",
    "/dev/random",
    "/dev/tty",
    "/etc/ld.so.cache",
    "/etc/ld.so.preload",
    "/etc/ld.so.conf",
    "/etc/nsswitch.conf",
    "/etc/hosts",
    "/etc/host.conf",
    "/etc/resolv.conf",
    "/etc/gai.conf",
    "/etc/localtime",
    "/etc/timezone",
    "/etc/machine-id",
})
# i18n / gconv baseline lives under /usr but is enumerated explicitly too so the
# intent is self-documenting and survives if /usr rules change.
_BASELINE_READ_REGEXES = (
    re.compile(r"^/usr/(?:lib|share)/(?:locale|zoneinfo|gconv|glibc-hwcaps)/"),
    re.compile(r"^/usr/lib/x86_64-linux-gnu/gconv/"),
    re.compile(r"^/etc/ld\.so\.conf\.d/"),
)

# AF_UNIX resolver-cache sockets are baseline network noise (nscd).
_BASELINE_UNIX_SOCKETS = frozenset({
    "/var/run/nscd/socket",
    "/run/nscd/socket",
    "/dev/log",
})

# Terminal/control devices opened for stdio wiring (e.g. bash opening /dev/tty for
# stderr) are runtime baseline, not tool filesystem writes. A genuine write to an
# arbitrary file is still observed.
_BASELINE_WRITE_EXACT = frozenset({
    "/dev/tty",
    "/dev/null",
    "/dev/stdout",
    "/dev/stderr",
    "/dev/full",
})


def _is_baseline_read(path: str) -> bool:
    if path in _BASELINE_READ_EXACT:
        return True
    if path.startswith(_BASELINE_READ_PREFIXES):
        return True
    for rx in _BASELINE_READ_REGEXES:
        if rx.match(path):
            return True
    return False


def _is_baseline_unix_socket(path: str) -> bool:
    return path in _BASELINE_UNIX_SOCKETS


def _write_flags(flags: str) -> bool:
    return ("O_WRONLY" in flags) or ("O_RDWR" in flags) or ("O_CREAT" in flags and "O_RDONLY" not in flags)


# --- observation set ---------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ToolBehaviorObservationSet:
    """Normalized observations derived from a real captured syscall trace.

    All tuples are sorted and de-duplicated so the set is canonical and the derived
    ``trace_artifact_sha256`` is reproducible from the same captured trace. No raw
    secret-shaped payloads are stored: only normalized paths/exec/targets and aggregate
    resource figures. Full file/network payloads never enter this structure.
    """

    process_exec: tuple[str, ...]
    filesystem_reads: tuple[str, ...]
    filesystem_writes: tuple[str, ...]
    network_connects: tuple[str, ...]
    network_listens: tuple[str, ...]
    peak_memory_bytes: int
    wall_time_ms: int
    exit_code: int
    trace_artifact_sha256: str = field(default="")

    def __post_init__(self) -> None:
        for name in ("process_exec", "filesystem_reads", "filesystem_writes",
                     "network_connects", "network_listens"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple")
            for item in value:
                if not isinstance(item, str) or not item:
                    raise ValueError(f"{name} entries must be non-empty strings")
            object.__setattr__(self, name, tuple(sorted(set(value))))
        for name in ("peak_memory_bytes", "wall_time_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(self.exit_code, int) or isinstance(self.exit_code, bool):
            raise TypeError("exit_code must be an integer")
        # The trace artifact hash is derived from the canonical observation record so a
        # tampered observation field is detectable by recomputation.
        object.__setattr__(self, "trace_artifact_sha256", _derive_trace_artifact_sha256(self))

    def canonical_record(self) -> dict[str, Any]:
        return {
            "processExec": list(self.process_exec),
            "filesystemReads": list(self.filesystem_reads),
            "filesystemWrites": list(self.filesystem_writes),
            "networkConnects": list(self.network_connects),
            "networkListens": list(self.network_listens),
            "peakMemoryBytes": self.peak_memory_bytes,
            "wallTimeMs": self.wall_time_ms,
            "exitCode": self.exit_code,
        }

    def verify(self) -> bool:
        return _derive_trace_artifact_sha256(self) == self.trace_artifact_sha256


def _derive_trace_artifact_sha256(observation_set: "ToolBehaviorObservationSet") -> str:
    return canonical_sha256(observation_set.canonical_record())


def compute_raw_trace_sha256(raw_trace: str) -> str:
    """Content hash over the exact captured raw trace bytes (UTF-8).

    This binds the artifact to the precise trace text the runtime captured, independent
    of the normalized observation set. Both are recorded so a normalizer change cannot
    silently rewrite what the runtime observed.
    """
    return hashlib.sha256(raw_trace.encode("utf-8", "surrogateescape")).hexdigest()


@dataclass(frozen=True, slots=True)
class _ParseAccumulator:
    process_exec: set[str]
    filesystem_reads: set[str]
    filesystem_writes: set[str]
    network_connects: set[str]
    network_listens: set[str]


def _empty_accumulator() -> _ParseAccumulator:
    return _ParseAccumulator(set(), set(), set(), set(), set())


def _parse_network(args: str, acc: _ParseAccumulator, *, is_listen: bool) -> None:
    fam = _FAMILY_RE.search(args)
    if not fam:
        return
    family = fam.group("fam")
    if family in ("INET", "INET6"):
        if family == "INET":
            port_m = _INET_PORT_RE.search(args)
            addr_m = _INET_ADDR_RE.search(args)
        else:
            port_m = _INET6_PORT_RE.search(args)
            addr_m = _INET6_ADDR_RE.search(args)
        port = port_m.group("port") if port_m else "0"
        addr = addr_m.group("addr") if addr_m else "0.0.0.0"
        target = f"{addr.lower()}:{port}"
        if is_listen:
            acc.network_listens.add(target)
        else:
            acc.network_connects.add(target)
    elif family in ("UNIX", "LOCAL"):
        path_m = _UNIX_PATH_RE.search(args)
        if path_m:
            path = path_m.group("path")
            if not _is_baseline_unix_socket(path):
                target = f"unix:{path}"
                if is_listen:
                    acc.network_listens.add(target)
                else:
                    acc.network_connects.add(target)


def parse_strace_trace(
    raw_trace: str,
    *,
    peak_memory_bytes: int,
    wall_time_ms: int,
    exit_code: int,
) -> ToolBehaviorObservationSet:
    """Parse a real captured strace trace into a normalized observation set.

    ``peak_memory_bytes``, ``wall_time_ms`` and ``exit_code`` are supplied by the
    runtime layer (from real docker stats / wait readback); the normalizer only owns
    syscall-derived observations. This keeps the parser pure and the resource truth
    bound to the runtime that actually measured it.
    """
    acc = _empty_accumulator()
    for line in raw_trace.splitlines():
        line = line.strip()
        if not line or line.startswith("+++ exited") or line.startswith("--- "):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        syscall = m.group("syscall")
        args = m.group("args")
        if syscall == "execve":
            path = _first_quoted(args)
            if path:
                acc.process_exec.add(path)
        elif syscall in ("openat", "open"):
            path = _first_quoted(args)
            if not path:
                continue
            flags_match = _FLAGS_RE.findall(args)
            flags = "|".join(flags_match)
            if _write_flags(flags):
                if path not in _BASELINE_WRITE_EXACT:
                    acc.filesystem_writes.add(path)
            else:
                if not _is_baseline_read(path):
                    acc.filesystem_reads.add(path)
        elif syscall == "connect":
            _parse_network(args, acc, is_listen=False)
        elif syscall == "bind":
            _parse_network(args, acc, is_listen=True)
    return ToolBehaviorObservationSet(
        process_exec=tuple(acc.process_exec),
        filesystem_reads=tuple(acc.filesystem_reads),
        filesystem_writes=tuple(acc.filesystem_writes),
        network_connects=tuple(acc.network_connects),
        network_listens=tuple(acc.network_listens),
        peak_memory_bytes=peak_memory_bytes,
        wall_time_ms=wall_time_ms,
        exit_code=exit_code,
    )


def observation_set_from_events(
    events: Iterable[dict[str, Any]],
    *,
    peak_memory_bytes: int,
    wall_time_ms: int,
    exit_code: int,
) -> ToolBehaviorObservationSet:
    """Build an observation set from pre-parsed structured events.

    Used by callers that capture trace events through a different transport (for example
    a runtime that records structured events directly). Each event must carry a ``kind``
    in {execve, openat-read, openat-write, connect, bind} and a normalized ``target``.
    """
    acc = _empty_accumulator()
    for event in events:
        if not isinstance(event, dict):
            continue
        kind = event.get("kind")
        target = event.get("target")
        if not isinstance(target, str) or not target:
            continue
        if kind == "execve":
            acc.process_exec.add(target)
        elif kind == "openat-read":
            if not _is_baseline_read(target):
                acc.filesystem_reads.add(target)
        elif kind == "openat-write":
            if target not in _BASELINE_WRITE_EXACT:
                acc.filesystem_writes.add(target)
        elif kind == "connect":
            _add_network(acc, target, is_listen=False)
        elif kind == "bind":
            _add_network(acc, target, is_listen=True)
    return ToolBehaviorObservationSet(
        process_exec=tuple(acc.process_exec),
        filesystem_reads=tuple(acc.filesystem_reads),
        filesystem_writes=tuple(acc.filesystem_writes),
        network_connects=tuple(acc.network_connects),
        network_listens=tuple(acc.network_listens),
        peak_memory_bytes=peak_memory_bytes,
        wall_time_ms=wall_time_ms,
        exit_code=exit_code,
    )


def _add_network(acc: _ParseAccumulator, target: str, *, is_listen: bool) -> None:
    if is_listen:
        acc.network_listens.add(target)
    else:
        acc.network_connects.add(target)


__all__ = [
    "ToolBehaviorObservationSet",
    "compute_raw_trace_sha256",
    "parse_strace_trace",
    "observation_set_from_events",
]
