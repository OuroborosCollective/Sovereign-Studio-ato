from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import functools
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
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
    try:
        os.chmod(_STATE_ROOT, 0o750)
    except OSError:
        pass


def _read_events() -> list[dict[str, Any]]:
    if not _EVENTS_PATH.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in _EVENTS_PATH.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if isinstance(payload, dict) and payload.get("schemaVersion") == "sovereign.tool-event.v1":
                events.append(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    return events[-100_000:]


def _bounded_rotate() -> None:
    if not _EVENTS_PATH.is_file() or _EVENTS_PATH.stat().st_size <= _MAX_EVENT_BYTES:
        return
    lines = _EVENTS_PATH.read_text("utf-8").splitlines()
    temporary = _EVENTS_PATH.with_suffix(".tmp")
    temporary.write_text("\n".join(lines[-25_000:]) + "\n", "utf-8")
    os.chmod(temporary, 0o640)
    temporary.replace(_EVENTS_PATH)


def record_event(
    tool_name: str,
    *,
    outcome: Outcome,
    duration_ms: int,
    mission_hash: str = "",
    recommended: bool = False,
) -> None:
    event = {
        "schemaVersion": "sovereign.tool-event.v1",
        "tool": _safe_tool_name(tool_name),
        "recordedAtEpoch": int(time.time()),
        "durationMs": max(0, min(int(duration_ms), 86_400_000)),
        "executionSuccess": bool(outcome.execution_success),
        "positiveOutcome": outcome.positive_outcome,
        "status": str(outcome.status or "")[:160],
        "failureFamily": str(outcome.failure_family or "")[:160],
        "missionFingerprint": str(mission_hash or _MISSION_FINGERPRINT.get() or "")[:64],
        "recommended": bool(recommended),
        "argumentValuesRecorded": False,
        "secretValuesRecorded": False,
    }
    with _LOCK:
        _ensure_state_root()
        with _EVENTS_PATH.open("a", encoding="utf-8") as handle:
            handle.write(_canonical(event) + "\n")
        try:
            os.chmod(_EVENTS_PATH, 0o640)
        except OSError:
            pass
        _bounded_rotate()
        _write_snapshot(_aggregate(_read_events()))


def record_recommendations(tool_names: list[str], mission_summary: str) -> None:
    fingerprint = mission_fingerprint(mission_summary)
    for name in tool_names[:50]:
        record_event(
            name,
            outcome=Outcome(True, None, "RECOMMENDED", ""),
            duration_ms=0,
            mission_hash=fingerprint,
            recommended=True,
        )


def _aggregate(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    now = int(time.time())
    aggregates: dict[str, dict[str, Any]] = {}
    for event in events:
        name = _safe_tool_name(event.get("tool"))
        item = aggregates.setdefault(
            name,
            {
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
            },
        )
        recorded_at = int(event.get("recordedAtEpoch") or 0)
        item["lastUsedAtEpoch"] = max(item["lastUsedAtEpoch"], recorded_at)
        mission_hash = str(event.get("missionFingerprint") or "")
        if mission_hash:
            item["missionFingerprints"].add(mission_hash)
        if event.get("recommended") is True:
            item["recommendations"] += 1
            continue
        item["invocations"] += 1
        item["totalDurationMs"] += int(event.get("durationMs") or 0)
        if event.get("executionSuccess") is True:
            item["executionSuccesses"] += 1
            item["lastSuccessAtEpoch"] = max(item["lastSuccessAtEpoch"], recorded_at)
        else:
            item["executionFailures"] += 1
        positive = event.get("positiveOutcome")
        if positive is True:
            item["positiveOutcomes"] += 1
        elif positive is False:
            item["negativeOutcomes"] += 1
        family = str(event.get("failureFamily") or "")[:160]
        if family:
            item["failureFamilies"][family] = int(item["failureFamilies"].get(family, 0)) + 1

    for item in aggregates.values():
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
    return aggregates


def _write_snapshot(aggregates: dict[str, dict[str, Any]]) -> None:
    ranked = sorted(aggregates.values(), key=lambda item: (-int(item["score"]), -int(item["invocations"]), item["tool"]))
    payload = {
        "schemaVersion": "sovereign.tool-success-ranking.v1",
        "generatedAtEpoch": int(time.time()),
        "tools": ranked,
        "toolCount": len(ranked),
        "argumentValuesRecorded": False,
        "secretValuesRecorded": False,
        "rankingIsAdvisory": True,
        "safetyAndFunctionalFitRemainAuthoritative": True,
    }
    payload["evidenceSha256"] = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    temporary = _SNAPSHOT_PATH.with_suffix(".tmp")
    temporary.write_text(_canonical(payload) + "\n", "utf-8")
    os.chmod(temporary, 0o640)
    temporary.replace(_SNAPSHOT_PATH)


def ranking_snapshot(limit: int = 50) -> dict[str, Any]:
    with _LOCK:
        _ensure_state_root()
        aggregates = _aggregate(_read_events())
        _write_snapshot(aggregates)
        ranked = sorted(aggregates.values(), key=lambda item: (-int(item["score"]), -int(item["invocations"]), item["tool"]))
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
    if getattr(function, "__sovereign_success_tracking__", False):
        return function

    if inspect.iscoroutinefunction(function):
        @functools.wraps(function)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.monotonic_ns()
            try:
                result = await function(*args, **kwargs)
            except BaseException as exc:
                record_event(tool_name, outcome=classify_result(None, exc), duration_ms=(time.monotonic_ns() - started) // 1_000_000)
                raise
            record_event(tool_name, outcome=classify_result(result), duration_ms=(time.monotonic_ns() - started) // 1_000_000)
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
                        record_event(tool_name, outcome=classify_result(None, exc), duration_ms=(time.monotonic_ns() - started) // 1_000_000)
                        raise
                    record_event(tool_name, outcome=classify_result(resolved), duration_ms=(time.monotonic_ns() - started) // 1_000_000)
                    return resolved
                return await_and_record()
        except BaseException as exc:
            record_event(tool_name, outcome=classify_result(None, exc), duration_ms=(time.monotonic_ns() - started) // 1_000_000)
            raise
        record_event(tool_name, outcome=classify_result(result), duration_ms=(time.monotonic_ns() - started) // 1_000_000)
        return result
    setattr(sync_wrapper, "__sovereign_success_tracking__", True)
    return sync_wrapper


def install_success_tracking(mcp: Any) -> dict[str, Any]:
    global _INSTALLED
    tracked = 0
    for tool in mcp._tool_manager.list_tools():
        name = _safe_tool_name(getattr(tool, "name", ""))
        function = getattr(tool, "fn", None)
        if not callable(function):
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
        "argumentValuesRecorded": False,
        "secretValuesRecorded": False,
    }
