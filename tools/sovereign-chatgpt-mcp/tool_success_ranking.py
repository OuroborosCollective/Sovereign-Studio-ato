from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import functools
import fcntl
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import threading
import time
from typing import Any

_STATE_ROOT = Path(
    os.getenv(
        "SOVEREIGN_TOOL_RANKING_STATE_ROOT",
        str(Path.home() / ".cache" / "sovereign-tool-routing"),
    )
)
_EVENTS_PATH = _STATE_ROOT / "tool-events.jsonl"
_SNAPSHOT_PATH = _STATE_ROOT / "tool-ranking.json"
_MAX_EVENT_BYTES = 8_000_000
_LOCK = threading.RLock()
_MISSION_FINGERPRINT: ContextVar[str] = ContextVar("sovereign_tool_mission_fingerprint", default="")
_INSTALLED = False
_AGGREGATES: dict[str, dict[str, Any]] | None = None
_PROJECTION_CACHE_KEY = ""
_PROJECTION_STATS: dict[str, int] = {}
_SNAPSHOT_MTIME_NS = -1

_BAD_STATUS_MARKERS = (
    "FAILED",
    "FAILURE",
    "ERROR",
    "BLOCKED",
    "INCOMPLETE",
    "UNAVAILABLE",
    "CONFLICT",
    "DRIFT",
    "TIMEOUT",
)
@dataclass(frozen=True)
class Outcome:
    execution_success: bool
    positive_outcome: bool | None
    status: str
    failure_family: str


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def mission_fingerprint(value: str) -> str:
    normalized = " ".join(str(value or "").casefold().split())[:4000]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


@contextmanager
def mission_scope(value: str):
    token = _MISSION_FINGERPRINT.set(mission_fingerprint(value))
    try:
        yield
    finally:
        _MISSION_FINGERPRINT.reset(token)


def _safe_tool_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name or len(name) > 160 or not all(char.isalnum() or char in "_-" for char in name):
        return "unknown_tool"
    return name


def _status_category(value: Any, *, execution_success: bool, positive_outcome: bool | None) -> str:
    """Persist only a bounded semantic category, never tool-controlled status text."""

    text = str(value or "").upper()
    if not execution_success or "EXCEPTION" in text:
        return "EXCEPTION"
    if "TIMEOUT" in text:
        return "TIMEOUT"
    if "CONFLICT" in text or "MISMATCH" in text:
        return "CONFLICT"
    if "UNAVAILABLE" in text or "DEGRADED" in text:
        return "UNAVAILABLE"
    if "BLOCK" in text or "REJECT" in text or "QUARANTIN" in text:
        return "BLOCKED"
    if positive_outcome is True:
        return "SUCCEEDED"
    if positive_outcome is False:
        return "REPORTED_NEGATIVE"
    return "REPORTED_STATUS" if text else "UNSPECIFIED"


def _failure_category(value: Any, *, execution_success: bool, positive_outcome: bool | None) -> str:
    """Coarsen failure families so arbitrary exception/result strings are never durable."""

    text = str(value or "").upper()
    if not text and execution_success and positive_outcome is not False:
        return ""
    if not execution_success or "EXCEPTION" in text or "ERROR" in text:
        return "EXECUTION_FAILURE"
    if "TIMEOUT" in text:
        return "TIMEOUT"
    if "CONFLICT" in text or "MISMATCH" in text or "STALE" in text:
        return "CONFLICT"
    if "UNAVAILABLE" in text or "DEGRADED" in text:
        return "UNAVAILABLE"
    if "AUTH" in text or "PERMISSION" in text or "FORBIDDEN" in text:
        return "AUTHORIZATION_FAILURE"
    if "QUOTA" in text or "RATE" in text:
        return "QUOTA_REACHED"
    if "CONTRACT" in text or "VALIDATION" in text or "INVALID" in text:
        return "CONTRACT_VIOLATION"
    return "REPORTED_FAILURE"


def _status_from(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("status") or "")[:160]
    status = getattr(value, "status", "")
    return str(status or "")[:160]


def _field(value: Any, *names: str) -> Any:
    if isinstance(value, dict):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def classify_result(value: Any, exception: BaseException | None = None) -> Outcome:
    if exception is not None:
        return Outcome(False, False, "EXCEPTION", type(exception).__name__[:160])
    status = _status_from(value)
    failure_family = str(_field(value, "failureFamily", "failure_family") or "")[:160]
    explicit_ok = _field(value, "ok")
    if isinstance(explicit_ok, bool):
        positive = explicit_ok
    elif status:
        positive = not any(marker in status.upper() for marker in _BAD_STATUS_MARKERS)
    else:
        positive = None
    return Outcome(True, positive, status, failure_family)


def _ensure_state_root() -> None:
    _STATE_ROOT.mkdir(parents=True, exist_ok=True)
    status = os.lstat(_STATE_ROOT)
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        raise RuntimeError("tool ranking state root must be a non-symlink directory")
    os.chmod(_STATE_ROOT, 0o750)


def _regular_status(path: Path, *, allow_missing: bool = True) -> os.stat_result | None:
    if not os.path.lexists(path):
        if allow_missing:
            return None
        raise FileNotFoundError(path.name)
    status = os.lstat(path)
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
        raise RuntimeError("tool ranking state child must be a non-symlink, singly-linked regular file")
    return status


def _read_regular_bytes(path: Path, *, maximum_bytes: int) -> bytes | None:
    expected = _regular_status(path)
    if expected is None:
        return None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_dev != expected.st_dev
            or opened.st_ino != expected.st_ino
            or opened.st_size != expected.st_size
            or opened.st_size > maximum_bytes
        ):
            raise RuntimeError("tool ranking state child failed bounded identity verification")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            after.st_dev != opened.st_dev
            or after.st_ino != opened.st_ino
            or after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
            or len(content) != opened.st_size
        ):
            raise RuntimeError("tool ranking state child changed during readback")
        return content
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, content: bytes) -> None:
    _ensure_state_root()
    _regular_status(path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=_STATE_ROOT
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o640)
        offset = 0
        while offset < len(content):
            offset += os.write(descriptor, content[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _regular_status(path)
        os.replace(temporary, path)
        directory_descriptor = os.open(_STATE_ROOT, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if os.path.lexists(temporary):
            os.unlink(temporary)


def _append_event(content: bytes) -> None:
    _ensure_state_root()
    expected = _regular_status(_EVENTS_PATH)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(_EVENTS_PATH, flags, 0o640)
    try:
        opened = os.fstat(descriptor)
        observed = _regular_status(_EVENTS_PATH, allow_missing=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or observed is None
            or opened.st_dev != observed.st_dev
            or opened.st_ino != observed.st_ino
            or (
                expected is not None
                and (opened.st_dev != expected.st_dev or opened.st_ino != expected.st_ino)
            )
        ):
            raise RuntimeError("tool event path is not a safe regular file")
        offset = 0
        while offset < len(content):
            offset += os.write(descriptor, content[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _process_lock():
    """Serialize the JSONL/projection pair across MCP worker processes."""

    _ensure_state_root()
    lock_path = _STATE_ROOT / ".tool-ranking.lock"
    expected = _regular_status(lock_path)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o640)
    try:
        opened = os.fstat(descriptor)
        observed = _regular_status(lock_path, allow_missing=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or observed is None
            or opened.st_dev != observed.st_dev
            or opened.st_ino != observed.st_ino
            or (
                expected is not None
                and (opened.st_dev != expected.st_dev or opened.st_ino != expected.st_ino)
            )
        ):
            raise RuntimeError("tool ranking lock is not a safe regular file")
        os.fchmod(descriptor, 0o640)
        with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
            descriptor = -1
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_events() -> list[dict[str, Any]]:
    raw = _read_regular_bytes(_EVENTS_PATH, maximum_bytes=_MAX_EVENT_BYTES * 2)
    if raw is None:
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in raw.decode("utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict) and payload.get("schemaVersion") == "sovereign.tool-event.v1":
                events.append(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    return events[-100_000:]


def _bounded_rotate() -> None:
    status = _regular_status(_EVENTS_PATH)
    if status is None or status.st_size <= _MAX_EVENT_BYTES:
        return
    raw = _read_regular_bytes(_EVENTS_PATH, maximum_bytes=_MAX_EVENT_BYTES * 2)
    if raw is None:
        return
    lines = raw.decode("utf-8").splitlines()
    _atomic_write(_EVENTS_PATH, ("\n".join(lines[-25_000:]) + "\n").encode("utf-8"))


def _projection_key() -> str:
    return f"{_EVENTS_PATH.absolute()}|{_SNAPSHOT_PATH.absolute()}"


def _refresh_projection_if_changed() -> None:
    """Invalidate only when another process atomically replaced the snapshot."""

    global _AGGREGATES, _SNAPSHOT_MTIME_NS
    status = _regular_status(_SNAPSHOT_PATH)
    observed = -1 if status is None else status.st_mtime_ns
    if _AGGREGATES is not None and observed != _SNAPSHOT_MTIME_NS:
        _AGGREGATES = None
    _SNAPSHOT_MTIME_NS = observed


def _empty_aggregate(name: str) -> dict[str, Any]:
    return {
        "tool": name,
        "invocations": 0,
        "executionSuccesses": 0,
        "executionFailures": 0,
        "positiveOutcomes": 0,
        "negativeOutcomes": 0,
        "recommendations": 0,
        "totalDurationMs": 0,
        "lastUsedAtEpoch": 0,
        "lastSuccessAtEpoch": 0,
        "missionFingerprints": set(),
        "failureFamilies": {},
    }


def _apply_event(aggregates: dict[str, dict[str, Any]], event: dict[str, Any]) -> None:
    name = _safe_tool_name(event.get("tool"))
    item = aggregates.setdefault(name, _empty_aggregate(name))
    recorded_at = int(event.get("recordedAtEpoch") or 0)
    item["lastUsedAtEpoch"] = max(int(item["lastUsedAtEpoch"]), recorded_at)
    mission_hash = str(event.get("missionFingerprint") or "")
    if mission_hash:
        fingerprints = item["missionFingerprints"]
        if not isinstance(fingerprints, set):
            fingerprints = set(fingerprints or [])
            item["missionFingerprints"] = fingerprints
        fingerprints.add(mission_hash)
    if event.get("recommended") is True:
        item["recommendations"] = int(item["recommendations"]) + 1
        return
    item["invocations"] = int(item["invocations"]) + 1
    item["totalDurationMs"] = int(item["totalDurationMs"]) + int(event.get("durationMs") or 0)
    if event.get("executionSuccess") is True:
        item["executionSuccesses"] = int(item["executionSuccesses"]) + 1
        item["lastSuccessAtEpoch"] = max(int(item["lastSuccessAtEpoch"]), recorded_at)
    else:
        item["executionFailures"] = int(item["executionFailures"]) + 1
    positive = event.get("positiveOutcome")
    if positive is True:
        item["positiveOutcomes"] = int(item["positiveOutcomes"]) + 1
    elif positive is False:
        item["negativeOutcomes"] = int(item["negativeOutcomes"]) + 1
    family = str(event.get("failureFamily") or "")[:160]
    if family:
        families = item["failureFamilies"]
        if not isinstance(families, dict):
            families = {}
            item["failureFamilies"] = families
        families[family] = int(families.get(family, 0)) + 1


def _raw_aggregates_from_snapshot(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    aggregates: dict[str, dict[str, Any]] = {}
    tools = payload.get("tools")
    if not isinstance(tools, list):
        raise ValueError("snapshot tools must be a list")
    for raw in tools:
        if not isinstance(raw, dict):
            raise ValueError("snapshot tool must be an object")
        name = _safe_tool_name(raw.get("tool"))
        item = _empty_aggregate(name)
        for field in (
            "invocations",
            "executionSuccesses",
            "executionFailures",
            "positiveOutcomes",
            "negativeOutcomes",
            "recommendations",
            "totalDurationMs",
            "lastUsedAtEpoch",
            "lastSuccessAtEpoch",
        ):
            item[field] = max(0, int(raw.get(field) or 0))
        item["missionFingerprints"] = set(str(value)[:64] for value in raw.get("missionFingerprints", []) if value)
        families = raw.get("failureFamilies")
        item["failureFamilies"] = {
            str(key)[:160]: max(0, int(value))
            for key, value in (families.items() if isinstance(families, dict) else [])
        }
        aggregates[name] = item
    return aggregates


def _snapshot_digest(payload: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "evidenceSha256"}
    return hashlib.sha256(_canonical(unsigned).encode("utf-8")).hexdigest()


def _load_projection() -> dict[str, dict[str, Any]]:
    global _AGGREGATES, _PROJECTION_CACHE_KEY, _PROJECTION_STATS
    key = _projection_key()
    if _AGGREGATES is not None and _PROJECTION_CACHE_KEY == key:
        return _AGGREGATES
    _PROJECTION_CACHE_KEY = key
    _PROJECTION_STATS = {
        "processedEventCount": 0,
        "incrementalUpdateCount": 0,
        "recoveryFullScanCount": 0,
        "startupTailScanCount": 0,
        "recoveredTailEventCount": 0,
        "historyGapCount": 0,
        "neuroProjectionSuccessCount": 0,
        "neuroProjectionFailureCount": 0,
    }
    try:
        snapshot_bytes = _read_regular_bytes(_SNAPSHOT_PATH, maximum_bytes=_MAX_EVENT_BYTES)
        if snapshot_bytes is None:
            raise FileNotFoundError(_SNAPSHOT_PATH.name)
        payload = json.loads(snapshot_bytes.decode("utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("schemaVersion") != "sovereign.tool-success-ranking.v1"
            or payload.get("evidenceSha256") != _snapshot_digest(payload)
        ):
            raise ValueError("ranking snapshot integrity mismatch")
        _AGGREGATES = _raw_aggregates_from_snapshot(payload)
        projection = payload.get("projection") if isinstance(payload.get("projection"), dict) else {}
        for field in _PROJECTION_STATS:
            _PROJECTION_STATS[field] = max(0, int(projection.get(field) or 0))
        if "processedEventCount" not in projection:
            _PROJECTION_STATS["processedEventCount"] = sum(
                int(item["invocations"]) + int(item["recommendations"])
                for item in _AGGREGATES.values()
            )
        # A process can stop after the durable JSONL append but before the
        # atomic projection replace.  Reconcile only the bounded log tail once
        # on cold start; normal event ingestion remains O(1) and never rescans
        # history.  Sequence gaps are not silently invented as successful
        # recovery because the ranking is advisory evidence, not an authority.
        events = _read_events()
        _PROJECTION_STATS["startupTailScanCount"] += 1
        expected_sequence = _PROJECTION_STATS["processedEventCount"]
        recovered = 0
        for event in events:
            raw_sequence = event.get("sequence")
            if isinstance(raw_sequence, bool) or not isinstance(raw_sequence, int):
                continue
            if raw_sequence < expected_sequence:
                continue
            if raw_sequence != expected_sequence:
                _PROJECTION_STATS["historyGapCount"] += 1
                break
            _apply_event(_AGGREGATES, event)
            expected_sequence += 1
            recovered += 1
        _PROJECTION_STATS["processedEventCount"] = expected_sequence
        _PROJECTION_STATS["recoveredTailEventCount"] += recovered
        return _AGGREGATES
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        events = _read_events()
        _AGGREGATES = _aggregate(events)
        sequenced = [
            int(event["sequence"])
            for event in events
            if isinstance(event.get("sequence"), int)
            and not isinstance(event.get("sequence"), bool)
            and int(event["sequence"]) >= 0
        ]
        _PROJECTION_STATS["processedEventCount"] = (
            max(sequenced) + 1 if sequenced else len(events)
        )
        if sequenced and min(sequenced) > 0:
            _PROJECTION_STATS["historyGapCount"] = 1
        _PROJECTION_STATS["recoveryFullScanCount"] = 1
        return _AGGREGATES


def record_event(
    tool_name: str,
    *,
    outcome: Outcome,
    duration_ms: int,
    mission_hash: str = "",
    recommended: bool = False,
) -> None:
    with _LOCK, _process_lock():
        _refresh_projection_if_changed()
        aggregates = _load_projection()
        recorded_ns = time.time_ns()
        event = {
            "schemaVersion": "sovereign.tool-event.v1",
            "eventId": hashlib.sha256(
                f"{recorded_ns}|{os.getpid()}|{threading.get_ident()}|{_PROJECTION_STATS['processedEventCount']}|{_safe_tool_name(tool_name)}".encode("utf-8")
            ).hexdigest(),
            "sequence": _PROJECTION_STATS["processedEventCount"],
            "tool": _safe_tool_name(tool_name),
            "recordedAtEpoch": recorded_ns // 1_000_000_000,
            "recordedAtEpochMs": recorded_ns // 1_000_000,
            "durationMs": max(0, min(int(duration_ms), 86_400_000)),
            "executionSuccess": bool(outcome.execution_success),
            "positiveOutcome": outcome.positive_outcome,
            "status": _status_category(
                outcome.status,
                execution_success=bool(outcome.execution_success),
                positive_outcome=outcome.positive_outcome,
            ),
            "failureFamily": _failure_category(
                outcome.failure_family,
                execution_success=bool(outcome.execution_success),
                positive_outcome=outcome.positive_outcome,
            ),
            "missionFingerprint": str(mission_hash or _MISSION_FINGERPRINT.get() or "")[:64],
            "recommended": bool(recommended),
            "argumentValuesRecorded": False,
            "secretValuesRecorded": False,
        }
        _append_event((_canonical(event) + "\n").encode("utf-8"))
        _bounded_rotate()
        _apply_event(aggregates, event)
        _PROJECTION_STATS["processedEventCount"] += 1
        _PROJECTION_STATS["incrementalUpdateCount"] += 1
        _write_snapshot(aggregates)
    if os.getenv("SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED", "1").strip() == "1":
        try:
            from neuro_teaching_tools import record_tool_outcome_event

            record_tool_outcome_event(event)
        except Exception:
            with _LOCK, _process_lock():
                _refresh_projection_if_changed()
                _PROJECTION_STATS["neuroProjectionFailureCount"] += 1
                _write_snapshot(_load_projection())
        else:
            with _LOCK, _process_lock():
                _refresh_projection_if_changed()
                _PROJECTION_STATS["neuroProjectionSuccessCount"] += 1
                _write_snapshot(_load_projection())


def _record_event_best_effort(
    tool_name: str,
    *,
    outcome: Outcome,
    duration_ms: int,
    mission_hash: str = "",
    recommended: bool = False,
) -> None:
    """Keep advisory telemetry failures isolated from the primary tool call."""

    try:
        record_event(
            tool_name,
            outcome=outcome,
            duration_ms=duration_ms,
            mission_hash=mission_hash,
            recommended=recommended,
        )
    except Exception:
        # Runtime/tool outcomes remain authoritative.  A tracking write must
        # neither convert success into failure nor replace the original error.
        return


def record_recommendations(tool_names: list[str], mission_summary: str) -> None:
    """Keep read-only recommendations non-persistent.

    Historical weighting is derived solely from actual mutating-tool outcomes;
    a recommendation must not create state as a side effect of a read-only MCP
    call.  The arguments are intentionally consumed without recording values.
    """

    del tool_names, mission_summary


def _aggregate(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    aggregates: dict[str, dict[str, Any]] = {}
    for event in events:
        _apply_event(aggregates, event)
    return aggregates


def _scored_aggregates(aggregates: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    now = int(time.time())
    scored: list[dict[str, Any]] = []
    for raw in aggregates.values():
        item = dict(raw)
        calls = int(item["invocations"])
        successes = int(item["executionSuccesses"])
        positive = int(item["positiveOutcomes"])
        negative = int(item["negativeOutcomes"])
        reliability = (successes + 3) / (calls + 4)
        total_outcomes = positive + negative
        quality = (positive + 1) / (total_outcomes + 2) if total_outcomes else 0.5
        usage = min(1.0, math.log2(calls + 1) / 8.0)
        age = max(0, now - int(item["lastSuccessAtEpoch"] or 0))
        recency = 0.0 if not item["lastSuccessAtEpoch"] else max(0.0, 1.0 - age / (30 * 86_400))
        item["score"] = max(0, min(round(1000 * (0.64 * reliability + 0.12 * quality + 0.14 * usage + 0.10 * recency)), 1000))
        item["executionReliabilityPpm"] = round(reliability * 1_000_000)
        item["positiveOutcomeRatePpm"] = round(quality * 1_000_000)
        item["averageDurationMs"] = round(item["totalDurationMs"] / calls) if calls else 0
        item["distinctMissionCount"] = len(item["missionFingerprints"])
        item["missionFingerprints"] = sorted(item["missionFingerprints"])[-100:]
        item["failureFamilies"] = dict(sorted(item["failureFamilies"].items(), key=lambda pair: (-pair[1], pair[0]))[:20])
        scored.append(item)
    return sorted(scored, key=lambda item: (-int(item["score"]), -int(item["invocations"]), item["tool"]))


def _write_snapshot(aggregates: dict[str, dict[str, Any]]) -> None:
    global _SNAPSHOT_MTIME_NS
    ranked = _scored_aggregates(aggregates)
    payload = {
        "schemaVersion": "sovereign.tool-success-ranking.v1",
        "generatedAtEpoch": int(time.time()),
        "tools": ranked,
        "toolCount": len(ranked),
        "argumentValuesRecorded": False,
        "secretValuesRecorded": False,
        "rankingIsAdvisory": True,
        "safetyAndFunctionalFitRemainAuthoritative": True,
        "telemetryScope": "mutable-tool-outcomes-only",
        "recommendationsPersisted": False,
        "projection": {
            "mode": "event-driven-incremental",
            **_PROJECTION_STATS,
        },
    }
    payload["evidenceSha256"] = _snapshot_digest(payload)
    _atomic_write(_SNAPSHOT_PATH, (_canonical(payload) + "\n").encode("utf-8"))
    status = _regular_status(_SNAPSHOT_PATH, allow_missing=False)
    assert status is not None
    _SNAPSHOT_MTIME_NS = status.st_mtime_ns


def ranking_snapshot(limit: int = 50) -> dict[str, Any]:
    with _LOCK:
        _refresh_projection_if_changed()
        aggregates = _load_projection()
        ranked = _scored_aggregates(aggregates)
    return {
        "schemaVersion": "sovereign.tool-success-ranking.v1",
        "ok": True,
        "status": "TOOL_SUCCESS_RANKING_READY",
        "tools": ranked[: max(1, min(int(limit), 500))],
        "toolCount": len(ranked),
        "argumentValuesRecorded": False,
        "secretValuesRecorded": False,
        "rankingIsAdvisory": True,
        "safetyAndFunctionalFitRemainAuthoritative": True,
        "telemetryScope": "mutable-tool-outcomes-only",
        "projection": {
            "mode": "event-driven-incremental",
            **_PROJECTION_STATS,
        },
    }


def historical_bonus_map() -> dict[str, int]:
    snapshot = ranking_snapshot(limit=500)
    return {
        str(item["tool"]): max(0, min(80, round(int(item["score"]) * 0.08)))
        for item in snapshot["tools"]
        if int(item["invocations"]) > 0
    }


def historical_bonus(tool_name: str) -> int:
    return int(historical_bonus_map().get(tool_name, 0))


def _wrap_callable(tool_name: str, function: Callable[..., Any]) -> Callable[..., Any]:
    if getattr(function, "__sovereign_success_tracking_opt_out__", False):
        return function
    if getattr(function, "__sovereign_success_tracking__", False):
        return function

    if inspect.iscoroutinefunction(function):
        @functools.wraps(function)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.monotonic_ns()
            try:
                result = await function(*args, **kwargs)
            except BaseException as exc:
                _record_event_best_effort(tool_name, outcome=classify_result(None, exc), duration_ms=(time.monotonic_ns() - started) // 1_000_000)
                raise
            _record_event_best_effort(tool_name, outcome=classify_result(result), duration_ms=(time.monotonic_ns() - started) // 1_000_000)
            return result
        setattr(async_wrapper, "__sovereign_success_tracking__", True)
        return async_wrapper

    @functools.wraps(function)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        started = time.monotonic_ns()
        try:
            result = function(*args, **kwargs)
            if inspect.isawaitable(result):
                async def await_and_record() -> Any:
                    try:
                        resolved = await result
                    except BaseException as exc:
                        _record_event_best_effort(tool_name, outcome=classify_result(None, exc), duration_ms=(time.monotonic_ns() - started) // 1_000_000)
                        raise
                    _record_event_best_effort(tool_name, outcome=classify_result(resolved), duration_ms=(time.monotonic_ns() - started) // 1_000_000)
                    return resolved
                return await_and_record()
        except BaseException as exc:
            _record_event_best_effort(tool_name, outcome=classify_result(None, exc), duration_ms=(time.monotonic_ns() - started) // 1_000_000)
            raise
        _record_event_best_effort(tool_name, outcome=classify_result(result), duration_ms=(time.monotonic_ns() - started) // 1_000_000)
        return result
    setattr(sync_wrapper, "__sovereign_success_tracking__", True)
    return sync_wrapper


def install_success_tracking(mcp: Any) -> dict[str, Any]:
    global _INSTALLED
    tracked = 0
    opted_out = 0
    for tool in mcp._tool_manager.list_tools():
        name = _safe_tool_name(getattr(tool, "name", ""))
        function = getattr(tool, "fn", None)
        if not callable(function):
            continue
        annotations = getattr(tool, "annotations", None)
        read_only = bool(
            annotations.get("readOnlyHint", False)
            if isinstance(annotations, dict)
            else getattr(annotations, "readOnlyHint", False)
        )
        if read_only or getattr(function, "__sovereign_success_tracking_opt_out__", False):
            opted_out += 1
            continue
        wrapped = _wrap_callable(name, function)
        if wrapped is not function:
            setattr(tool, "fn", wrapped)
            tracked += 1
    _INSTALLED = True
    return {
        "schemaVersion": "sovereign.tool-success-tracking-installation.v1",
        "ok": True,
        "status": "TOOL_SUCCESS_TRACKING_INSTALLED",
        "trackedToolCount": tracked,
        "optedOutToolCount": opted_out,
        "telemetryScope": "mutable-tool-outcomes-only",
        "readOnlyCallsPersisted": False,
        "argumentValuesRecorded": False,
        "secretValuesRecorded": False,
    }
