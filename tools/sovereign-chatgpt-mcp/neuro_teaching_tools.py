"""FastMCP adapters for the canonical neuro runtime and evidence-bound teaching.

This module deliberately adds no second server, tool registry, router, event
contract, or execution lane.  It adapts the existing canonical neuro contract,
``neuromorphic_runtime``, ``foundation_runtime``, the live FastMCP registry and
the existing predictive router.  Every proposal is advisory-only; the module
contains no tool-execution path.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
from typing import Annotated, Any, Callable, Literal, Mapping, Sequence

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from policy import (
    mapping_key_is_secret_shaped,
    normalized_argument_key,
    string_is_secret_shaped,
    validate_workspace_id,
)


try:  # Keep launcher importable while deployment mirrors are assembled.
    import neuromorphic_runtime as _nmc
except ImportError as _error:  # pragma: no cover - exercised by deployment canary
    _nmc = None
    _NMC_IMPORT_ERROR = f"{type(_error).__name__}: {_error}"
else:
    _NMC_IMPORT_ERROR = ""

try:
    import foundation_runtime as _foundation
except ImportError as _error:  # pragma: no cover - exercised by deployment canary
    _foundation = None
    _FOUNDATION_IMPORT_ERROR = f"{type(_error).__name__}: {_error}"
else:
    _FOUNDATION_IMPORT_ERROR = ""

try:
    import neuro_architecture_contract as _neuro_contract
except ImportError as _error:  # pragma: no cover - exercised by deployment canary
    _neuro_contract = None
    _CONTRACT_IMPORT_ERROR = f"{type(_error).__name__}: {_error}"
else:
    _CONTRACT_IMPORT_ERROR = ""


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
LOCAL_IDEMPOTENT_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

OUTPUT_SCHEMA_VERSION = "sovereign.neuro-teaching-tool-output.v1"
PREVIEW_SCHEMA_VERSION = "sovereign.neuro-event-preview.v1"
ASSESSMENT_SCHEMA_VERSION = "sovereign.teaching-assessment-receipt.v1"
GRAMMAR_ATLAS_SCHEMA_VERSION = "sovereign.private-grammar-atlas.v1"
ZERO_SHA256 = "0" * 64
DISCARDED_NO_REGISTRY_SHA256 = hashlib.sha256(
    b"sovereign.no-live-registry.discarded-before-routing.v1"
).hexdigest()

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,159}$")
_MAX_PACKAGE_BYTES = 512_000
_MAX_PREVIEW_BYTES = 192_000
_MAX_ERRORS = 64
_MAX_TEXT_FIELD = 4_000
_MAX_GRAMMAR_TILES = 96
_MAX_GRAMMAR_SOURCE_CHARS = 64_000
_MAX_SENSOR_FEATURES = 64
_MAX_LEDGER_VERIFY_EVENTS = 100_000
_ALLOWED_EFFECTS = frozenset({"read", "workspace-write", "external-write"})
_ALLOWED_LICENSE_POLICIES = frozenset(
    {
        "repository-owner-policy",
        "owner-approved-internal",
        "proprietary-owner-policy",
        "public-domain",
        "cc0-1.0",
        "cc-by-4.0",
        "cc-by-sa-4.0",
        "mit",
        "apache-2.0",
        "bsd-2-clause",
        "bsd-3-clause",
        "mpl-2.0",
        "gpl-2.0-only",
        "gpl-2.0-or-later",
        "gpl-3.0-only",
        "gpl-3.0-or-later",
        "lgpl-2.1-only",
        "lgpl-2.1-or-later",
        "lgpl-3.0-only",
        "agpl-3.0-only",
    }
)
_ALLOWED_SOURCE_TYPES = frozenset(
    {"files", "web", "api", "relational", "document", "graph", "vector", "search", "hybrid"}
)
_ALLOWED_TRUST_POLICIES = frozenset(
    {
        "repository",
        "repository-local",
        "public-primary-source",
        "public-secondary-source",
    }
)
_ALLOWED_EVIDENCE_CLASSIFICATIONS = frozenset({"public", "internal"})
_OUTCOME_THREAD_LOCK = threading.RLock()
_FALSE_SECRET_ATTESTATION_KEYS = frozenset(
    {"argumentvaluesrecorded", "secretvaluesrecorded", "secretvaluesreturned"}
)

_RUNTIME: Any = None
_MCP: Any = None
_REGISTERED = False
_REGISTRY_PROVIDER: Callable[[], Any] | None = None


class NeuroTeachingOutput(BaseModel):
    """Strict output compatible with the server-wide output envelope."""

    model_config = ConfigDict(extra="forbid")

    schemaVersion: Literal["sovereign.neuro-teaching-tool-output.v1"]
    ok: bool
    status: str
    failureFamily: str | None
    blocker: str | None
    mutationPerformed: bool
    nextAction: str | None
    evidence: dict[str, Any]
    data: dict[str, Any]
    secretValuesReturned: Literal[False] = False


def _output(
    *,
    ok: bool,
    status: str,
    mutation_performed: bool = False,
    failure_family: str | None = None,
    blocker: str | None = None,
    next_action: str | None = None,
    evidence: Mapping[str, Any] | None = None,
    data: Mapping[str, Any] | None = None,
) -> NeuroTeachingOutput:
    return NeuroTeachingOutput(
        schemaVersion=OUTPUT_SCHEMA_VERSION,
        ok=ok,
        status=status,
        failureFamily=failure_family,
        blocker=blocker,
        mutationPerformed=mutation_performed,
        nextAction=next_action,
        evidence=dict(evidence or {}),
        data=dict(data or {}),
        secretValuesReturned=False,
    )


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("value is not canonical JSON") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bounded(value: Any, limit: int = _MAX_TEXT_FIELD) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return dict(value)
    dumper = getattr(value, "model_dump", None)
    if callable(dumper):
        return dumper(mode="json")
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return value


def _reject_secret_shaped(value: Any, *, pointer: str = "$", depth: int = 0) -> None:
    if depth > 24:
        raise ValueError("input nesting exceeds the bounded limit")
    if isinstance(value, Mapping):
        if len(value) > 512:
            raise ValueError("input mapping exceeds the bounded item limit")
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("input keys must be strings")
            normalized = normalized_argument_key(key)
            if mapping_key_is_secret_shaped(key, child):
                if normalized in _FALSE_SECRET_ATTESTATION_KEYS:
                    raise ValueError(f"security attestation must be false at {pointer}.{key}")
                raise ValueError(f"secret-shaped field is forbidden at {pointer}.{key}")
            _reject_secret_shaped(child, pointer=f"{pointer}.{key}", depth=depth + 1)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > 2_048:
            raise ValueError("input sequence exceeds the bounded item limit")
        for index, child in enumerate(value):
            _reject_secret_shaped(child, pointer=f"{pointer}[{index}]", depth=depth + 1)
    elif isinstance(value, str) and string_is_secret_shaped(value):
        raise ValueError(f"secret-like literal is forbidden at {pointer}")


def _state_root() -> Path:
    explicit = os.getenv("SOVEREIGN_NEURO_RUNTIME_STATE_ROOT", "").strip()
    if explicit:
        return Path(explicit)
    ranking_root = Path(
        os.getenv(
            "SOVEREIGN_TOOL_RANKING_STATE_ROOT",
            str(Path.home() / ".cache" / "sovereign-tool-routing"),
        )
    )
    return ranking_root / "neuro-runtime"


def _ledger_path() -> Path:
    return _state_root() / "neuromorphic-runtime.sqlite3"


def _foundation_ledger_path() -> Path:
    return _state_root() / "foundation-runtime.sqlite3"


def _ensure_private_state_root() -> Path:
    state_root = _state_root()
    try:
        state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        status = os.lstat(state_root)
    except OSError as exc:
        raise RuntimeError("neuro runtime state root is unavailable") from exc
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        raise RuntimeError("neuro runtime state root must be a non-symlink directory")
    try:
        os.chmod(state_root, 0o700)
    except OSError as exc:
        raise RuntimeError("neuro runtime state root permissions cannot be secured") from exc
    return state_root


def _bounded_env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} is outside the safe bound")
    return value


def _database_family_bytes(path: Path) -> int:
    family = (path, Path(str(path) + "-wal"), Path(str(path) + "-shm"))
    total = 0
    for item in family:
        if not os.path.lexists(item):
            continue
        status = os.lstat(item)
        if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
            raise RuntimeError("neuro database family must contain only non-symlink regular files")
        total += status.st_size
    return total


def _read_total_events(path: Path) -> int:
    if not os.path.lexists(path):
        return 0
    with _readonly_connection(path) as connection:
        try:
            return int(connection.execute("SELECT COUNT(*) FROM change_events").fetchone()[0])
        except sqlite3.OperationalError as exc:
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if "no such table: change_events" in str(exc) and user_version == 0:
                return 0
            raise


def _global_quota(path: Path) -> dict[str, Any]:
    max_events = _bounded_env_int(
        "SOVEREIGN_NEURO_GLOBAL_MAX_EVENTS",
        _MAX_LEDGER_VERIFY_EVENTS,
        minimum=1,
        maximum=10_000_000,
    )
    max_bytes = _bounded_env_int(
        "SOVEREIGN_NEURO_GLOBAL_MAX_BYTES",
        256 * 1024 * 1024,
        minimum=1024 * 1024,
        maximum=2 * 1024 * 1024 * 1024,
    )
    used_events = _read_total_events(path)
    used_bytes = _database_family_bytes(path)
    return {
        "usedEvents": used_events,
        "maxEvents": max_events,
        "usedBytes": used_bytes,
        "maxBytes": max_bytes,
        "eventsRemaining": max(0, max_events - used_events),
        "bytesRemaining": max(0, max_bytes - used_bytes),
        "exceeded": used_events >= max_events or used_bytes >= max_bytes,
        "pathExposed": False,
    }


def _outcome_quota(path: Path) -> dict[str, Any]:
    max_events = _bounded_env_int(
        "SOVEREIGN_NEURO_OUTCOME_MAX_EVENTS",
        90_000,
        minimum=1,
        maximum=10_000_000,
    )
    max_bytes = _bounded_env_int(
        "SOVEREIGN_NEURO_OUTCOME_MAX_BYTES",
        256 * 1024 * 1024,
        minimum=1024 * 1024,
        maximum=2 * 1024 * 1024 * 1024,
    )
    used_bytes = _database_family_bytes(path)
    head = _read_source_head(path, "tool-success-ranking")
    used_events = int(head["nextSequence"])
    exceeded = used_events >= max_events or used_bytes >= max_bytes
    return {
        "source": "tool-success-ranking",
        "usedEvents": used_events,
        "maxEvents": max_events,
        "usedBytes": used_bytes,
        "maxBytes": max_bytes,
        "eventsRemaining": max(0, max_events - used_events),
        "bytesRemaining": max(0, max_bytes - used_bytes),
        "exceeded": exceeded,
        "pathExposed": False,
    }


def _require_runtime_modules() -> None:
    missing = []
    if _nmc is None:
        missing.append(f"neuromorphic_runtime ({_NMC_IMPORT_ERROR})")
    if _foundation is None:
        missing.append(f"foundation_runtime ({_FOUNDATION_IMPORT_ERROR})")
    if _neuro_contract is None:
        missing.append(f"neuro_architecture_contract ({_CONTRACT_IMPORT_ERROR})")
    if missing:
        raise RuntimeError("runtime module unavailable: " + "; ".join(missing))


@contextmanager
def _readonly_connection(path: Path):
    if not os.path.lexists(path):
        raise FileNotFoundError(path.name)
    status = os.lstat(path)
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
        raise RuntimeError("neuro database must be a non-symlink regular file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    connection: sqlite3.Connection | None = None
    locked = False
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_dev != status.st_dev
            or opened.st_ino != status.st_ino
        ):
            raise RuntimeError("neuro database identity changed before read lock")
        fcntl.flock(descriptor, fcntl.LOCK_SH)
        locked = True
        observed = os.lstat(path)
        if (
            stat.S_ISLNK(observed.st_mode)
            or not stat.S_ISREG(observed.st_mode)
            or observed.st_dev != opened.st_dev
            or observed.st_ino != opened.st_ino
        ):
            raise RuntimeError("neuro database identity changed during read lock")
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        yield connection
    finally:
        if connection is not None:
            connection.close()
        try:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _read_source_head(path: Path, source: str) -> dict[str, Any]:
    empty = {
            "exists": False,
            "source": source,
            "lastSequence": -1,
            "nextSequence": 0,
            "lastTick": -1,
            "lastEventTime": None,
            "lastEventHash": ZERO_SHA256,
            "lastEventId": None,
        }
    if not os.path.lexists(path):
        return empty
    with _readonly_connection(path) as connection:
        try:
            row = connection.execute(
                """
                SELECT last_sequence, last_tick, last_event_time, last_event_hash, last_event_id
                FROM source_heads WHERE source = ?
                """,
                (source,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            # A concurrent first initializer creates the file before its schema
            # transaction publishes.  Version 0 is the only state treated as
            # not-yet-initialized; a missing table in v1 remains hard failure.
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if "no such table: source_heads" in str(exc) and user_version == 0:
                return empty
            raise
    if row is None:
        return empty
    return {
        "exists": True,
        "source": source,
        "lastSequence": int(row["last_sequence"]),
        "nextSequence": int(row["last_sequence"]) + 1,
        "lastTick": int(row["last_tick"]),
        "lastEventTime": row["last_event_time"],
        "lastEventHash": row["last_event_hash"],
        "lastEventId": row["last_event_id"],
    }


def _existing_event(path: Path, event_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if not os.path.lexists(path):
        return None
    with _readonly_connection(path) as connection:
        try:
            row = connection.execute(
                "SELECT canonical_event, receipt_json FROM change_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if "no such table: change_events" in str(exc) and user_version == 0:
                return None
            raise
    if row is None:
        return None
    try:
        event = json.loads(row["canonical_event"])
        receipt = json.loads(row["receipt_json"])
    except json.JSONDecodeError as exc:
        raise RuntimeError("persisted neuro event is not valid JSON") from exc
    if not isinstance(event, dict) or not isinstance(receipt, dict):
        raise RuntimeError("persisted neuro event has an invalid shape")
    return event, receipt


def _module_sha256(module: Any) -> str | None:
    path_value = getattr(module, "__file__", None)
    if not path_value:
        return None
    path = Path(path_value)
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return None


def _registry_snapshot() -> dict[str, Any]:
    if _REGISTRY_PROVIDER is not None:
        raw = _REGISTRY_PROVIDER()
    else:
        import operational_governance_tools

        raw = operational_governance_tools.mcp_tool_contract_registry(
            include_schemas=True,
            max_tools=1000,
        )
    value = _plain(raw)
    if not isinstance(value, Mapping):
        raise RuntimeError("live registry returned no object")
    tools = value.get("tools")
    snapshot_sha = value.get("registrySnapshotSha256")
    if value.get("ok") is not True or value.get("truncated") is True:
        raise RuntimeError("live registry is not complete")
    if not isinstance(tools, list) or not isinstance(snapshot_sha, str) or not _SHA256.fullmatch(snapshot_sha):
        raise RuntimeError("live registry contract is invalid")

    normalized: list[dict[str, Any]] = []
    snapshot_payload: list[dict[str, Any]] = []
    for index, item in enumerate(tools):
        if not isinstance(item, Mapping):
            raise RuntimeError(f"live registry tool {index} is invalid")
        contract = {
            "name": item.get("name"),
            "description": item.get("description", ""),
            "capabilities": item.get("capabilities", []),
            "effect": item.get("effect"),
            "annotations": item.get("annotations", {}),
            "parameters": item.get("parameters", {}),
            "outputSchema": item.get("outputSchema", {}),
        }
        if not isinstance(contract["name"], str) or not contract["name"]:
            raise RuntimeError(f"live registry tool {index} has no name")
        if contract["effect"] not in _ALLOWED_EFFECTS:
            raise RuntimeError(f"live registry tool {contract['name']} has an invalid effect")
        contract_sha = item.get("contractSha256")
        if contract_sha != _sha256(contract):
            raise RuntimeError(f"live registry tool {contract['name']} contract hash mismatch")
        normalized.append({**contract, "contractSha256": contract_sha})
        snapshot_payload.append(contract)
    if _sha256(snapshot_payload) != snapshot_sha:
        raise RuntimeError("live registry snapshot hash mismatch")
    if int(value.get("toolCount", -1)) != len(normalized):
        raise RuntimeError("live registry tool count mismatch")
    return {
        "schemaVersion": str(value.get("schemaVersion") or ""),
        "registrySnapshotSha256": snapshot_sha,
        "toolCount": len(normalized),
        "tools": normalized,
    }


def _route(
    registry: Mapping[str, Any],
    *,
    mission_summary: str,
    required_capabilities: list[str],
    allowed_effects: list[str],
    max_tools: int,
) -> dict[str, Any]:
    from predictive_tool_router import predict_tool_route

    return predict_tool_route(
        catalog=list(registry["tools"]),
        mission_summary=mission_summary,
        required_capabilities=set(required_capabilities),
        allowed_effects=set(allowed_effects),
        required_evidence=[],
        excluded_tools={"neuro_event_route_preview", "neuro_event_commit"},
        max_tools=max_tools,
        historical_bonuses={},
    )


def _validate_optional_toolchain(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        import toolchain_composition

        chain = toolchain_composition.McpToolChain.model_validate(value)
        report = toolchain_composition.mcp_toolchain_validate(chain)
        payload = _plain(report)
    except Exception as exc:
        return {
            "ok": False,
            "status": "MCP_TOOLCHAIN_VALIDATION_FAILED",
            "failureFamily": type(exc).__name__,
        }
    return {
        "ok": bool(payload.get("ok")),
        "status": str(payload.get("status") or "MCP_TOOLCHAIN_VALIDATION_UNKNOWN"),
        "registrySnapshotSha256": payload.get("registrySnapshotSha256"),
        "findings": list(payload.get("findings") or [])[:32],
        "autoExecute": False,
    }


def _lane_path_valid(lane: Any) -> bool:
    if _neuro_contract is None:
        return False
    return _neuro_contract.Lane(lane) == _neuro_contract.Lane.DETERMINISTIC_VERIFICATION


def _sensor_spikes(
    event: Any,
    features: list[dict[str, Any]] | None,
    *,
    threshold: int,
) -> tuple[bool | None, dict[str, Any]]:
    if features is None:
        return None, {
            "enabled": False,
            "privatePrototype": True,
            "proposalOnly": True,
            "mayExecute": False,
            "externalEffects": [],
        }
    if event.kind != "sensor.change":
        raise ValueError("sensor_features are only valid for sensor.change")
    if not isinstance(features, list) or not 1 <= len(features) <= _MAX_SENSOR_FEATURES:
        raise ValueError("sensor_features must contain 1 to 64 items")
    spike_filter = _nmc.QuantizedSpikeFilter(threshold=max(1, threshold))
    spikes: list[dict[str, Any]] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, Mapping):
            raise ValueError(f"sensor_features[{index}] must be an object")
        if set(feature) != {"sensorId", "tick", "magnitude"}:
            raise ValueError(f"sensor_features[{index}] fields are invalid")
        sensor_id = feature["sensorId"]
        tick = feature["tick"]
        magnitude = feature["magnitude"]
        if not isinstance(sensor_id, str) or not _SAFE_NAME.fullmatch(sensor_id):
            raise ValueError(f"sensor_features[{index}].sensorId is invalid")
        if (
            isinstance(tick, bool)
            or not isinstance(tick, int)
            or not 0 <= tick <= 2**63 - 1
            or isinstance(magnitude, bool)
            or not isinstance(magnitude, int)
            or not 0 <= magnitude <= 2**31 - 1
        ):
            raise ValueError(f"sensor_features[{index}] requires bounded non-negative integers")
        decision = spike_filter.observe(sensor_id, tick=tick, magnitude=magnitude)
        if decision.spiked:
            spikes.append(asdict(decision))
    return bool(spikes), {
        "enabled": True,
        "privatePrototype": True,
        "proposalOnly": True,
        "mayExecute": False,
        "externalEffects": [],
        "featureCount": len(features),
        "spikeCount": len(spikes),
        "spikeEvidence": spikes,
        "nonSpikeFeaturesRetainedAsCandidateEvidence": False,
    }


def _resource_advisory(pressure: Mapping[str, Any] | None) -> dict[str, Any]:
    if pressure is None:
        return {
            "enabled": False,
            "privatePrototype": True,
            "advisoryOnly": True,
            "mayExecute": False,
            "externalEffects": [],
            "actuatorAvailable": False,
        }
    expected = {
        "queueUnits",
        "activeWorkers",
        "unitsPerWorker",
        "minWorkers",
        "maxWorkers",
        "maxAdjustment",
    }
    if not isinstance(pressure, Mapping) or set(pressure) != expected:
        raise ValueError("resource_pressure fields are invalid")
    values: dict[str, int] = {}
    for key in expected:
        value = pressure[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
            raise ValueError(f"resource_pressure.{key} must be a bounded non-negative integer")
        values[key] = value
    homeostat = _nmc.ResourceHomeostat(
        units_per_worker=values["unitsPerWorker"],
        min_workers=values["minWorkers"],
        max_workers=values["maxWorkers"],
        max_adjustment=values["maxAdjustment"],
    )
    recommendation = asdict(
        homeostat.recommend(
            queue_units=values["queueUnits"],
            active_workers=values["activeWorkers"],
        )
    )
    return {
        "enabled": True,
        "privatePrototype": True,
        **recommendation,
        "advisoryOnly": True,
        "mayExecute": False,
        "externalEffects": [],
        "actuatorAvailable": False,
    }


def _foundation_decision(
    event: Any,
    *,
    event_kind: str,
    request_id: str,
    session_id: str,
) -> dict[str, Any]:
    return _foundation.FoundationRuntime().verify_change_event(
        event,
        foundation_kind=event_kind,
        request_id=request_id,
        session_id=session_id,
    )


def _preview_request(
    *,
    change_event: Mapping[str, Any],
    foundation_event_kind: str,
    request_id: str,
    session_id: str,
    mission_summary: str,
    required_capabilities: list[str],
    allowed_effects: list[str],
    relevance_threshold: int,
    max_tools: int,
    sensor_features: list[dict[str, Any]] | None,
    resource_pressure: Mapping[str, Any] | None,
    toolchain: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "changeEvent": dict(change_event),
        "foundationEventKind": foundation_event_kind,
        "requestId": request_id,
        "sessionId": session_id,
        "missionSummary": mission_summary,
        "requiredCapabilities": list(required_capabilities),
        "allowedEffects": list(allowed_effects),
        "relevanceThreshold": relevance_threshold,
        "maxTools": max_tools,
        "sensorFeatures": sensor_features,
        "resourcePressure": dict(resource_pressure) if resource_pressure is not None else None,
        "toolchain": dict(toolchain) if toolchain is not None else None,
    }


def _assert_temporal_head_binding(event: Any, head: Mapping[str, Any]) -> None:
    if not head.get("exists"):
        if event.delta_ms != 0:
            raise ValueError("first source event delta_ms must be zero")
        return
    if event.tick < int(head["lastTick"]):
        raise ValueError("ChangeEvent tick regresses behind the source head")
    previous_time = datetime.fromisoformat(str(head["lastEventTime"]).replace("Z", "+00:00"))
    current_time = datetime.fromisoformat(str(event.event_time).replace("Z", "+00:00"))
    delta = current_time - previous_time
    elapsed_ms = delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000
    if elapsed_ms < 0:
        raise ValueError("ChangeEvent eventTime regresses behind the source head")
    if event.delta_ms != elapsed_ms:
        raise ValueError("ChangeEvent deltaMs does not match the source-head time delta")


def _assert_event_time_not_future(event: Any) -> None:
    event_time = datetime.fromisoformat(str(event.event_time).replace("Z", "+00:00"))
    validation_now = datetime.now(timezone.utc)
    if event_time > validation_now + timedelta(minutes=5):
        raise ValueError("ChangeEvent eventTime exceeds the bounded clock skew")


def _build_preview(request: Mapping[str, Any], *, enforce_head: bool = True) -> dict[str, Any]:
    _require_runtime_modules()
    encoded = _canonical_json(request).encode("utf-8")
    if len(encoded) > _MAX_PREVIEW_BYTES:
        raise ValueError("preview request exceeds byte limit")
    _reject_secret_shaped(request)

    event = _nmc.ChangeEvent.from_dict(request["changeEvent"])
    if not _lane_path_valid(event.identity.lane) or event.identity.canonical is not True:
        raise ValueError("Foundation requires a canonical deterministic-verification ChangeEvent")
    _assert_deployment_binding(event)
    _assert_event_time_not_future(event)
    threshold = request["relevanceThreshold"]
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 0 <= threshold <= 2**31 - 1:
        raise ValueError("relevanceThreshold is invalid")
    max_tools = request["maxTools"]
    if isinstance(max_tools, bool) or not isinstance(max_tools, int) or not 1 <= max_tools <= 8:
        raise ValueError("maxTools must be between 1 and 8")
    mission_summary = request["missionSummary"]
    if not isinstance(mission_summary, str) or not 3 <= len(mission_summary) <= 2_000:
        raise ValueError("missionSummary length is invalid")
    required = request["requiredCapabilities"]
    allowed = request["allowedEffects"]
    if (
        not isinstance(required, list)
        or not 1 <= len(required) <= 12
        or any(not isinstance(item, str) or not item for item in required)
    ):
        raise ValueError("requiredCapabilities are invalid")
    if (
        not isinstance(allowed, list)
        or not 1 <= len(allowed) <= 3
        or any(item not in _ALLOWED_EFFECTS for item in allowed)
    ):
        raise ValueError("allowedEffects are invalid")

    head = _read_source_head(_ledger_path(), event.source)
    head_matches = event.sequence == head["nextSequence"] and event.previous_hash == head["lastEventHash"]
    if enforce_head and not head_matches:
        raise ValueError("ChangeEvent sequence or predecessor does not match the current source head")
    if enforce_head:
        _assert_temporal_head_binding(event, head)

    foundation_decision = _foundation_decision(
        event,
        event_kind=str(request["foundationEventKind"]),
        request_id=str(request["requestId"]),
        session_id=str(request["sessionId"]),
    )
    base_relevance = _nmc.RelevanceGate(default_threshold=threshold).evaluate(event)
    spike_relevant, spike = _sensor_spikes(
        event,
        request.get("sensorFeatures"),
        threshold=max(1, threshold),
    )
    homeostat = _resource_advisory(request.get("resourcePressure"))
    relevant = base_relevance.relevant and (spike_relevant is not False)
    relevance_reason = (
        "SPIKE_THRESHOLD_MET"
        if relevant and spike_relevant is True
        else "NO_SPIKE_EVIDENCE"
        if base_relevance.relevant and spike_relevant is False
        else base_relevance.reason
    )

    registry: dict[str, Any] | None = None
    route: dict[str, Any] = {
        "routeComplete": False,
        "selectedTools": [],
        "missingCapabilities": list(required),
        "predictiveAdvisoryOnly": True,
        "deterministicGatesRequired": True,
    }
    if foundation_decision.get("outcome") == "accepted" and relevant:
        registry = _registry_snapshot()
        route = _route(
            registry,
            mission_summary=mission_summary,
            required_capabilities=required,
            allowed_effects=allowed,
            max_tools=max_tools,
        )

    registry_by_name = {
        item["name"]: item for item in (registry["tools"] if registry is not None else [])
    }
    selected_contracts: list[dict[str, Any]] = []
    for selected in list(route.get("selectedTools") or [])[:max_tools]:
        name = str(selected.get("name") or "") if isinstance(selected, Mapping) else ""
        contract = registry_by_name.get(name)
        if contract is None:
            raise RuntimeError("router selected a tool outside the live registry snapshot")
        selected_contracts.append(
            {
                "name": name,
                "contractSha256": contract["contractSha256"],
                "effect": contract["effect"],
            }
        )

    toolchain_report = _validate_optional_toolchain(request.get("toolchain"))
    if toolchain_report is not None and registry is not None:
        if toolchain_report.get("registrySnapshotSha256") not in {None, registry["registrySnapshotSha256"]}:
            toolchain_report = {
                **toolchain_report,
                "ok": False,
                "status": "MCP_TOOLCHAIN_REGISTRY_DRIFT",
            }

    foundation_ok = foundation_decision.get("outcome") == "accepted" and foundation_decision.get("ok") is True
    route_ok = not relevant or bool(route.get("routeComplete"))
    toolchain_ok = toolchain_report is None or toolchain_report.get("ok") is True
    admitted = foundation_ok and route_ok and toolchain_ok
    if not foundation_ok:
        classification = "quarantined"
        status = "NEURO_EVENT_QUARANTINED"
    elif not relevant:
        classification = "discarded"
        status = "NEURO_EVENT_DISCARDED"
    elif not route_ok:
        classification = "quarantined"
        status = "NEURO_ROUTE_INCOMPLETE"
    elif not toolchain_ok:
        classification = "quarantined"
        status = "NEURO_TOOLCHAIN_INVALID"
    else:
        classification = "candidate"
        status = "NEURO_EVENT_CANDIDATE"

    artifact = {
        "schemaVersion": PREVIEW_SCHEMA_VERSION,
        "admitted": admitted,
        "classification": classification,
        "status": status,
        "request": dict(request),
        "eventIdentity": {
            "eventId": event.event_id,
            "eventHash": event.event_hash,
            "source": event.source,
            "sequence": event.sequence,
            "tick": event.tick,
            "previousEvidenceSha256": event.previous_hash,
        },
        "expectedHead": head,
        "headMatchedAtPreview": head_matches,
        "foundationDecision": foundation_decision,
        "relevance": {
            "relevant": relevant,
            "reason": relevance_reason,
            "threshold": threshold,
            "baseRelevant": base_relevance.relevant,
        },
        "spikeFilter": spike,
        "resourceHomeostat": homeostat,
        "route": {
            "routeComplete": bool(route.get("routeComplete")),
            "confidence": route.get("confidence"),
            "missingCapabilities": list(route.get("missingCapabilities") or []),
            "missingFunctionalActions": list(route.get("missingFunctionalActions") or []),
            "missingFunctionalObjects": list(route.get("missingFunctionalObjects") or []),
            "missingFunctionalStages": list(route.get("missingFunctionalStages") or []),
            "predictiveAdvisoryOnly": True,
        },
        "proposal": {
            "schemaVersion": "sovereign.neuro-proposal-only.v1",
            "registrySnapshotSha256": (
                registry["registrySnapshotSha256"]
                if registry is not None
                else DISCARDED_NO_REGISTRY_SHA256
            ),
            "registrySnapshotKind": "live" if registry is not None else "discarded-not-routed",
            "selectedToolContracts": selected_contracts,
            "proposalOnly": True,
            "mayExecute": False,
            "autoExecute": False,
            "externalEffects": [],
            "staticRulesLoaded": False,
            "promotionAvailable": False,
            "feedbackPersisted": False,
        },
        "toolchainValidation": toolchain_report,
        "mutationPerformed": False,
        "externalEffects": [],
    }
    artifact["previewSha256"] = _sha256(artifact)
    return artifact


def _ledger_readback(path: Path) -> dict[str, Any]:
    if not os.path.lexists(path):
        return {
            "initialized": False,
            "pathExposed": False,
            "schemaVersion": None,
            "eventCount": 0,
            "sourceCount": 0,
            "integrityVerified": False,
            "integrityStatus": "NOT_INITIALIZED",
        }
    try:
        with _nmc.NeuromorphicLedger.open_read_only(path) as ledger:
            report = ledger.verify_integrity()
            if ledger.read_only is not True:
                raise RuntimeError("canonical ledger verifier is not read-only")
        if report.event_count > _MAX_LEDGER_VERIFY_EVENTS:
            return {
                "initialized": True,
                "pathExposed": False,
                "schemaVersion": "sovereign.neuromorphic-ledger.v1",
                "eventCount": report.event_count,
                "sourceCount": report.source_count,
                "integrityVerified": False,
                "integrityStatus": "BOUNDED_READBACK_LIMIT_REACHED",
                "canonicalVerifierUsed": True,
            }
        return {
            "initialized": True,
            "pathExposed": False,
            "schemaVersion": "sovereign.neuromorphic-ledger.v1",
            "eventCount": report.event_count,
            "sourceCount": report.source_count,
            "integrityVerified": report.ok is True,
            "integrityStatus": "VERIFIED" if report.ok is True else "FAILED",
            "canonicalVerifierUsed": True,
        }
    except Exception as exc:
        return {
            "initialized": True,
            "pathExposed": False,
            "integrityVerified": False,
            "integrityStatus": "FAILED",
            "failureFamily": type(exc).__name__,
            "canonicalVerifierUsed": True,
        }


def _admission_readback(nmc_path: Path, foundation_path: Path) -> dict[str, Any]:
    """Verify durable preview admissions and both ledger bindings read-only."""

    if not os.path.lexists(nmc_path):
        try:
            foundation_count = 0
            if os.path.lexists(foundation_path):
                foundation_ledger = _foundation.SQLiteFoundationLedger.open_read_only(
                    str(foundation_path)
                )
                foundation_count = foundation_ledger.count()
            if foundation_count:
                raise RuntimeError("Foundation evidence exists without the NMC authority ledger")
        except Exception as exc:
            return {
                "initialized": True,
                "pending": 0,
                "complete": 0,
                "integrityVerified": False,
                "integrityStatus": "FAILED",
                "failureFamily": type(exc).__name__,
                "orphanFoundationEntries": foundation_count if "foundation_count" in locals() else None,
                "pathExposed": False,
            }
        return {
            "initialized": False,
            "pending": 0,
            "complete": 0,
            "integrityVerified": True,
            "integrityStatus": "NOT_PRESENT",
            "pathExposed": False,
        }
    try:
        with _readonly_connection(nmc_path) as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='neuro_admissions'"
            ).fetchone()
            if table is None:
                return {
                    "initialized": False,
                    "pending": 0,
                    "complete": 0,
                    "integrityVerified": True,
                    "integrityStatus": "NOT_PRESENT",
                    "pathExposed": False,
                }
            rows = connection.execute(
                """
                SELECT event_id, event_hash, preview_sha256, decision_sha256,
                       registry_sha256, classification, status, nmc_receipt_sha256,
                       foundation_evidence_sha256, admission_receipt_sha256
                FROM neuro_admissions ORDER BY event_id
                """
            ).fetchall()
            events = {
                row["event_id"]: {
                    "eventHash": row["event_hash"],
                    "receiptSha256": row["receipt_hash"],
                    "kind": row["kind"],
                    "source": row["source"],
                }
                for row in connection.execute(
                    "SELECT event_id, event_hash, receipt_hash, kind, source FROM change_events"
                ).fetchall()
            }
        foundation_entries: dict[str, dict[str, str]] = {}
        if os.path.lexists(foundation_path):
            with _readonly_connection(foundation_path) as connection:
                foundation_entries = {
                    row["decision_sha256"]: {
                        "eventId": row["event_id"],
                        "evidenceSha256": row["evidence_sha256"],
                    }
                    for row in connection.execute(
                        "SELECT event_id, decision_sha256, evidence_sha256 FROM foundation_evidence"
                    ).fetchall()
                }

        counts = {"pending": 0, "complete": 0}
        pending_event_persisted = 0
        pending_foundation_persisted = 0
        admission_event_ids: set[str] = set()
        bound_foundation_decisions: set[str] = set()
        for row in rows:
            status = str(row["status"])
            if status not in counts:
                raise RuntimeError("admission has an invalid saga status")
            counts[status] += 1
            event_id = str(row["event_id"])
            admission_event_ids.add(event_id)
            if not _SAFE_NAME.fullmatch(event_id):
                raise RuntimeError("admission event identity is invalid")
            required_hashes = (
                row["event_hash"],
                row["preview_sha256"],
                row["decision_sha256"],
                row["registry_sha256"],
            )
            if any(not isinstance(value, str) or not _SHA256.fullmatch(value) or value == ZERO_SHA256 for value in required_hashes):
                raise RuntimeError("admission contains an invalid required hash binding")
            classification = str(row["classification"])
            if classification not in {"candidate", "discarded"}:
                raise RuntimeError("admission classification is invalid")
            if (
                classification == "discarded"
                and row["registry_sha256"] != DISCARDED_NO_REGISTRY_SHA256
            ):
                raise RuntimeError("discarded admission has an invalid no-registry binding")
            if (
                classification == "candidate"
                and row["registry_sha256"] == DISCARDED_NO_REGISTRY_SHA256
            ):
                raise RuntimeError("candidate admission cannot use the no-registry binding")
            nmc_entry = events.get(event_id)
            foundation_entry = foundation_entries.get(str(row["decision_sha256"]))
            if status == "pending":
                pending_event_persisted += int(nmc_entry is not None)
                pending_foundation_persisted += int(foundation_entry is not None)
                if foundation_entry is not None:
                    bound_foundation_decisions.add(str(row["decision_sha256"]))
                if any(
                    row[field] is not None
                    for field in (
                        "nmc_receipt_sha256",
                        "foundation_evidence_sha256",
                        "admission_receipt_sha256",
                    )
                ):
                    raise RuntimeError("pending admission contains premature completion hashes")
                continue

            completed_hashes = (
                row["nmc_receipt_sha256"],
                row["foundation_evidence_sha256"],
                row["admission_receipt_sha256"],
            )
            if any(not isinstance(value, str) or not _SHA256.fullmatch(value) or value == ZERO_SHA256 for value in completed_hashes):
                raise RuntimeError("complete admission has an invalid completion hash")
            if (
                nmc_entry is None
                or nmc_entry["eventHash"] != row["event_hash"]
                or nmc_entry["receiptSha256"] != row["nmc_receipt_sha256"]
            ):
                raise RuntimeError("admission NMC receipt binding mismatch")
            if (
                foundation_entry is None
                or foundation_entry["eventId"] != event_id
                or foundation_entry["evidenceSha256"] != row["foundation_evidence_sha256"]
            ):
                raise RuntimeError("admission Foundation evidence binding mismatch")
            bound_foundation_decisions.add(str(row["decision_sha256"]))
            receipt = {
                "schemaVersion": "sovereign.neuro-admission-receipt.v1",
                "eventId": event_id,
                "eventHash": row["event_hash"],
                "previewSha256": row["preview_sha256"],
                "foundationDecisionSha256": row["decision_sha256"],
                "foundationEvidenceSha256": row["foundation_evidence_sha256"],
                "registrySnapshotSha256": row["registry_sha256"],
                "classification": classification,
                "nmcReceiptSha256": row["nmc_receipt_sha256"],
                "proposalOnly": True,
                "mayExecute": False,
                "autoExecute": False,
            }
            if _sha256(receipt) != row["admission_receipt_sha256"]:
                raise RuntimeError("admission receipt hash mismatch")
        orphan_foundation = sorted(set(foundation_entries) - bound_foundation_decisions)
        if orphan_foundation:
            raise RuntimeError("Foundation evidence is not bound by an admission")
        for event_id, event in events.items():
            if event_id in admission_event_ids:
                continue
            if event["kind"] != "tool.outcome" or event["source"] != "tool-success-ranking":
                raise RuntimeError("NMC commit event is not bound by an admission")
        return {
            "initialized": True,
            **counts,
            "pendingEventPersisted": pending_event_persisted,
            "pendingFoundationPersisted": pending_foundation_persisted,
            "integrityVerified": True,
            "integrityStatus": "RECOVERY_PENDING" if counts["pending"] else "VERIFIED",
            "pathExposed": False,
        }
    except Exception as exc:
        return {
            "initialized": True,
            "integrityVerified": False,
            "integrityStatus": "FAILED",
            "failureFamily": type(exc).__name__,
            "pathExposed": False,
        }


def _foundation_ledger_readback(path: Path) -> dict[str, Any]:
    if not os.path.lexists(path):
        return {
            "initialized": False,
            "entryCount": 0,
            "integrityVerified": False,
            "integrityStatus": "NOT_INITIALIZED",
            "pathExposed": False,
        }
    try:
        ledger = _foundation.SQLiteFoundationLedger.open_read_only(str(path))
        chain = ledger.verify_chain()
        count = ledger.count()
        if count > _MAX_LEDGER_VERIFY_EVENTS:
            return {
                "initialized": True,
                "entryCount": count,
                "integrityVerified": False,
                "integrityStatus": "BOUNDED_READBACK_LIMIT_REACHED",
                "canonicalVerifierUsed": True,
                "pathExposed": False,
            }
        return {
            "initialized": True,
            "entryCount": count,
            "headSha256": chain.get("head"),
            "integrityVerified": chain.get("valid") is True,
            "integrityStatus": "VERIFIED" if chain.get("valid") is True else "FAILED",
            "chainReason": chain.get("reason"),
            "canonicalVerifierUsed": True,
            "pathExposed": False,
        }
    except Exception as exc:
        return {
            "initialized": True,
            "integrityVerified": False,
            "integrityStatus": "FAILED",
            "failureFamily": type(exc).__name__,
            "canonicalVerifierUsed": True,
            "pathExposed": False,
        }


def neuro_runtime_contract_status() -> NeuroTeachingOutput:
    """Read the canonical contract/ledger/registry state without initializing it."""

    module_status = {
        "canonicalContract": _neuro_contract is not None,
        "neuromorphicRuntime": _nmc is not None,
        "foundationRuntime": _foundation is not None,
        "errors": [
            value
            for value in (_CONTRACT_IMPORT_ERROR, _NMC_IMPORT_ERROR, _FOUNDATION_IMPORT_ERROR)
            if value
        ],
    }
    try:
        deployment_revision = _source_revision({})
        deployment_policy = _policy_sha256()
        deployment_binding = {
            "ready": True,
            "revisionSha": deployment_revision,
            "policySha256": deployment_policy,
            "embeddedPolicyVerified": True,
        }
    except Exception as exc:
        deployment_binding = {
            "ready": False,
            "revisionSha": None,
            "policySha256": None,
            "embeddedPolicyVerified": False,
            "failureFamily": type(exc).__name__,
        }
    ledger = _ledger_readback(_ledger_path()) if _nmc is not None else {
        "initialized": False,
        "integrityVerified": False,
        "integrityStatus": "RUNTIME_MODULE_UNAVAILABLE",
        "pathExposed": False,
    }
    foundation_ledger = _foundation_ledger_readback(_foundation_ledger_path()) if _foundation is not None else {
        "initialized": False,
        "integrityVerified": False,
        "integrityStatus": "RUNTIME_MODULE_UNAVAILABLE",
        "pathExposed": False,
    }
    admissions = _admission_readback(_ledger_path(), _foundation_ledger_path())
    try:
        outcome_quota = _outcome_quota(_ledger_path())
    except Exception as exc:
        outcome_quota = {
            "exceeded": True,
            "failureFamily": type(exc).__name__,
            "pathExposed": False,
        }
    try:
        global_quota = _global_quota(_ledger_path())
    except Exception as exc:
        global_quota = {
            "exceeded": True,
            "failureFamily": type(exc).__name__,
            "pathExposed": False,
        }
    try:
        registry = _registry_snapshot()
        registry_evidence = {
            "registrySnapshotSha256": registry["registrySnapshotSha256"],
            "toolCount": registry["toolCount"],
            "liveRegistryUsed": True,
        }
        registry_ok = True
    except Exception as exc:
        registry_evidence = {
            "registrySnapshotSha256": None,
            "toolCount": 0,
            "liveRegistryUsed": True,
            "failureFamily": type(exc).__name__,
        }
        registry_ok = False
    modules_ok = all(module_status[key] for key in ("canonicalContract", "neuromorphicRuntime", "foundationRuntime"))
    ledger_ok = not ledger.get("initialized") or ledger.get("integrityVerified") is True
    foundation_ledger_ok = not foundation_ledger.get("initialized") or foundation_ledger.get("integrityVerified") is True
    admissions_ok = (
        admissions.get("integrityVerified") is True
        and int(admissions.get("pending", 0)) == 0
    )
    quota_ok = outcome_quota.get("exceeded") is False
    global_quota_ok = global_quota.get("exceeded") is False
    ok = (
        modules_ok
        and deployment_binding["ready"] is True
        and registry_ok
        and ledger_ok
        and foundation_ledger_ok
        and admissions_ok
        and quota_ok
        and global_quota_ok
    )
    return _output(
        ok=ok,
        status="NEURO_RUNTIME_CONTRACT_READY" if ok else "NEURO_RUNTIME_CONTRACT_DEGRADED",
        failure_family=None if ok else "NEURO_RUNTIME_CONTRACT_INCOMPLETE",
        blocker=None if ok else "module, registry, or ledger readback is incomplete",
        next_action=None if ok else "repair the reported contract or readback gap before commit",
        evidence={
            **registry_evidence,
            "contractSha256": _module_sha256(_neuro_contract),
            "neuromorphicRuntimeSha256": _module_sha256(_nmc),
            "foundationRuntimeSha256": _module_sha256(_foundation),
        },
        data={
            "modules": module_status,
            "deploymentBinding": deployment_binding,
            "ledger": ledger,
            "foundationLedger": foundation_ledger,
            "admissions": admissions,
            "globalLedgerQuota": global_quota,
            "toolOutcomeQuota": outcome_quota,
            "privatePrototypes": {
                "quantizedSpikeFilter": {
                    "active": bool(_nmc is not None and hasattr(_nmc, "QuantizedSpikeFilter")),
                    "proposalOnly": True,
                    "persistent": False,
                    "mayExecute": False,
                },
                "resourceHomeostat": {
                    "active": bool(_nmc is not None and hasattr(_nmc, "ResourceHomeostat")),
                    "advisoryOnly": True,
                    "hasActuator": False,
                    "mayExecute": False,
                },
                "grammarAtlas": {
                    "active": True,
                    "private": True,
                    "hashBound": True,
                },
                "proposalOnlyLearning": {
                    "active": True,
                    "staticRulesLoaded": False,
                    "promotionAvailable": False,
                    "feedbackPersistence": False,
                },
            },
            "stateInitializedByThisCall": False,
        },
    )


def neuro_event_route_preview(
    change_event: dict[str, Any],
    foundation_event_kind: Annotated[str, Field(min_length=1, max_length=80)],
    request_id: Annotated[str, Field(min_length=2, max_length=160)],
    session_id: Annotated[str, Field(min_length=2, max_length=160)],
    mission_summary: Annotated[str, Field(min_length=3, max_length=2_000)],
    required_capabilities: Annotated[list[str], Field(min_length=1, max_length=12)],
    allowed_effects: Annotated[list[str], Field(min_length=1, max_length=3)] = ["read"],
    relevance_threshold: Annotated[int, Field(ge=0, le=2**31 - 1)] = 1,
    max_tools: Annotated[int, Field(ge=1, le=8)] = 5,
    sensor_features: Annotated[list[dict[str, Any]] | None, Field(max_length=_MAX_SENSOR_FEATURES)] = None,
    resource_pressure: dict[str, Any] | None = None,
    toolchain: dict[str, Any] | None = None,
) -> NeuroTeachingOutput:
    """Validate, relevance-gate and route one event without persistence or execution."""

    request = _preview_request(
        change_event=change_event,
        foundation_event_kind=foundation_event_kind,
        request_id=request_id,
        session_id=session_id,
        mission_summary=mission_summary,
        required_capabilities=required_capabilities,
        allowed_effects=allowed_effects,
        relevance_threshold=relevance_threshold,
        max_tools=max_tools,
        sensor_features=sensor_features,
        resource_pressure=resource_pressure,
        toolchain=toolchain,
    )
    try:
        artifact = _build_preview(request)
    except Exception as exc:
        return _output(
            ok=False,
            status="NEURO_EVENT_QUARANTINED",
            failure_family=type(exc).__name__,
            blocker=_bounded(exc, 300),
            next_action="correct the canonical envelope, delta, Foundation binding, or live route contract",
            evidence={"eventPersisted": False, "externalEffectPerformed": False},
            data={
                "classification": "quarantined",
                "mayExecute": False,
                "autoExecute": False,
                "proposalOnly": True,
            },
        )
    admitted = bool(artifact["admitted"])
    return _output(
        ok=admitted,
        status=artifact["status"],
        failure_family=None if admitted else "NEURO_EVENT_NOT_ADMITTED",
        blocker=None if admitted else str(artifact["foundationDecision"].get("reason") or artifact["status"]),
        next_action=(
            "commit the exact preview hash with source-head CAS"
            if admitted
            else "resolve quarantine or routing findings; do not commit or execute"
        ),
        evidence={
            "previewSha256": artifact["previewSha256"],
            "eventHash": artifact["eventIdentity"]["eventHash"],
            "registrySnapshotSha256": artifact["proposal"]["registrySnapshotSha256"],
            "eventPersisted": False,
            "externalEffectPerformed": False,
        },
        data={"previewArtifact": artifact},
    )


class _FixedPreviewGate:
    def __init__(self, relevance: Mapping[str, Any]) -> None:
        self._relevance = relevance

    def evaluate(self, _event: Any) -> Any:
        return _nmc.RelevanceDecision(
            relevant=bool(self._relevance["relevant"]),
            reason=str(self._relevance["reason"]),
            threshold=int(self._relevance["threshold"]),
        )


def _ensure_commit_intent(
    path: Path,
    *,
    event_id: str,
    event_hash: str,
    preview_sha256: str,
    decision_sha256: str,
    registry_sha256: str,
    classification: str,
) -> dict[str, Any]:
    """Durably create or read the cross-ledger recovery intent.

    NMC and Foundation keep their own transactional ledgers.  This intent is
    written before either append, so a process crash leaves a detectable and
    idempotently resumable operation instead of an unreported partial success.
    """

    with sqlite3.connect(path, timeout=30.0, isolation_level=None) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute(
                "SELECT * FROM neuro_admissions WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO neuro_admissions(
                        event_id, event_hash, preview_sha256, decision_sha256,
                        registry_sha256, classification, status
                    ) VALUES(?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (
                        event_id,
                        event_hash,
                        preview_sha256,
                        decision_sha256,
                        registry_sha256,
                        classification,
                    ),
                )
                connection.commit()
                return {
                    "status": "pending",
                    "nmcReceiptSha256": None,
                    "foundationEvidenceSha256": None,
                    "admissionReceiptSha256": None,
                    "created": True,
                }
            if (
                row["event_hash"] != event_hash
                or row["preview_sha256"] != preview_sha256
                or row["decision_sha256"] != decision_sha256
                or row["registry_sha256"] != registry_sha256
                or row["classification"] != classification
            ):
                raise ValueError("commit event identity already binds another preview or decision")
            connection.commit()
            return {
                "status": row["status"],
                "nmcReceiptSha256": row["nmc_receipt_sha256"],
                "foundationEvidenceSha256": row["foundation_evidence_sha256"],
                "admissionReceiptSha256": row["admission_receipt_sha256"],
                "created": False,
            }
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise


def _commit_intent_state(path: Path, event_id: str) -> dict[str, Any] | None:
    """Read one recovery intent without creating or migrating state."""

    if not os.path.lexists(path):
        return None
    with _readonly_connection(path) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='neuro_admissions'"
        ).fetchone()
        if table is None:
            return None
        row = connection.execute(
            "SELECT status FROM neuro_admissions WHERE event_id=?",
            (event_id,),
        ).fetchone()
    return None if row is None else {"status": str(row["status"]), "retained": True}


def _cancel_uncommitted_intent(path: Path, event_id: str) -> bool:
    """Compensate a handled CAS/quota rejection that appended no event."""

    if not os.path.lexists(path):
        return False
    status = os.lstat(path)
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
        raise RuntimeError("neuro ledger path is unsafe during compensation")
    with sqlite3.connect(path, timeout=30.0, isolation_level=None) as connection:
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("BEGIN IMMEDIATE")
        try:
            if connection.execute(
                "SELECT 1 FROM change_events WHERE event_id=?",
                (event_id,),
            ).fetchone() is not None:
                connection.commit()
                return False
            foundation_path = _foundation_ledger_path()
            if os.path.lexists(foundation_path):
                foundation_status = os.lstat(foundation_path)
                if stat.S_ISLNK(foundation_status.st_mode) or not stat.S_ISREG(
                    foundation_status.st_mode
                ):
                    raise RuntimeError("Foundation ledger path is unsafe during compensation")
                with _readonly_connection(foundation_path) as foundation_connection:
                    evidence_table = foundation_connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='foundation_evidence'"
                    ).fetchone()
                    if evidence_table is not None and foundation_connection.execute(
                        "SELECT 1 FROM foundation_evidence WHERE event_id=? LIMIT 1", (event_id,)
                    ).fetchone() is not None:
                        connection.commit()
                        return False
            cursor = connection.execute(
                "DELETE FROM neuro_admissions WHERE event_id=? AND status='pending'",
                (event_id,),
            )
            connection.commit()
            return cursor.rowcount == 1
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise


def _complete_commit_intent(
    path: Path,
    *,
    event_id: str,
    event_hash: str,
    preview_sha256: str,
    foundation_decision_sha256: str,
    registry_sha256: str,
    classification: str,
    nmc_receipt_sha256: str,
    foundation_evidence_sha256: str,
) -> dict[str, Any]:
    admission = {
        "schemaVersion": "sovereign.neuro-admission-receipt.v1",
        "eventId": event_id,
        "eventHash": event_hash,
        "previewSha256": preview_sha256,
        "foundationDecisionSha256": foundation_decision_sha256,
        "foundationEvidenceSha256": foundation_evidence_sha256,
        "registrySnapshotSha256": registry_sha256,
        "classification": classification,
        "nmcReceiptSha256": nmc_receipt_sha256,
        "proposalOnly": True,
        "mayExecute": False,
        "autoExecute": False,
    }
    admission["admissionReceiptSha256"] = _sha256(admission)
    with sqlite3.connect(path, timeout=30.0, isolation_level=None) as connection:
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = connection.execute(
                """
                SELECT status, nmc_receipt_sha256, foundation_evidence_sha256,
                       admission_receipt_sha256
                FROM neuro_admissions WHERE event_id=?
                """,
                (event_id,),
            ).fetchone()
            if existing is not None and existing[0] == "complete":
                if (
                    existing[1] != nmc_receipt_sha256
                    or existing[2] != foundation_evidence_sha256
                    or existing[3] != admission["admissionReceiptSha256"]
                ):
                    raise ValueError("completed admission receipt conflicts with replay")
                connection.commit()
                return {
                    **admission,
                    "replayed": True,
                    "transitionPerformed": False,
                }
            cursor = connection.execute(
                """
                UPDATE neuro_admissions
                SET status='complete', nmc_receipt_sha256=?,
                    foundation_evidence_sha256=?, admission_receipt_sha256=?
                WHERE event_id=? AND status IN ('pending', 'complete')
                """,
                (
                    nmc_receipt_sha256,
                    foundation_evidence_sha256,
                    admission["admissionReceiptSha256"],
                    event_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("cross-ledger commit intent is missing")
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
    return {
        **admission,
        "replayed": False,
        "transitionPerformed": True,
    }


def _record_foundation_decision(decision: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger = _foundation.SQLiteFoundationLedger(str(_foundation_ledger_path()))
    evidence = _foundation.FoundationRuntime(ledger=ledger).record(decision)
    chain = ledger.verify_chain()
    if chain.get("valid") is not True:
        raise RuntimeError("Foundation evidence chain verification failed")
    return evidence, chain


def _verify_commit_state_preflight() -> None:
    """Reject malformed or orphaned durable state before any commit mutation."""

    foundation_path = _foundation_ledger_path()
    if os.path.lexists(foundation_path):
        ledger = _foundation.SQLiteFoundationLedger.open_read_only(str(foundation_path))
        chain = ledger.verify_chain()
        if chain.get("valid") is not True:
            raise RuntimeError("Foundation evidence chain preflight failed")
    admissions = _admission_readback(_ledger_path(), foundation_path)
    if admissions.get("integrityVerified") is not True:
        raise RuntimeError("cross-ledger admission preflight failed")


def _validate_replay_artifact(
    artifact: Mapping[str, Any],
    *,
    event: Any,
) -> dict[str, Any]:
    _assert_deployment_binding(event)
    if artifact.get("admitted") is not True or artifact.get("classification") not in {"candidate", "discarded"}:
        raise ValueError("only an admitted preview can be replayed")
    proposal = artifact.get("proposal")
    if (
        not isinstance(proposal, Mapping)
        or proposal.get("proposalOnly") is not True
        or proposal.get("mayExecute") is not False
        or proposal.get("autoExecute") is not False
        or proposal.get("externalEffects") != []
    ):
        raise ValueError("preview proposal safety contract is invalid")
    request = artifact.get("request")
    if not isinstance(request, Mapping):
        raise ValueError("preview request is missing")
    decision = _foundation_decision(
        event,
        event_kind=str(request.get("foundationEventKind") or ""),
        request_id=str(request.get("requestId") or ""),
        session_id=str(request.get("sessionId") or ""),
    )
    asserted = artifact.get("foundationDecision")
    if not isinstance(asserted, Mapping) or asserted.get("decisionSha256") != decision.get("decisionSha256"):
        raise ValueError("preview Foundation decision no longer reproduces")
    if decision.get("outcome") != "accepted" or decision.get("ok") is not True:
        raise ValueError("Foundation decision is not accepted")
    return decision


def neuro_event_commit(
    preview_artifact: dict[str, Any],
    preview_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")],
    expected_head_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")],
    expected_sequence: Annotated[int, Field(ge=0, le=2**63 - 1)],
) -> NeuroTeachingOutput:
    """Idempotently persist or recover an admitted preview without executing it."""

    try:
        _require_runtime_modules()
        supplied = dict(preview_artifact)
        _reject_secret_shaped(supplied, pointer="$.previewArtifact")
        embedded_hash = supplied.pop("previewSha256", None)
        recomputed_supplied_hash = _sha256(supplied)
        if embedded_hash != preview_sha256 or recomputed_supplied_hash != preview_sha256:
            raise ValueError("preview hash mismatch")
        if supplied.get("schemaVersion") != PREVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported preview schema")
        request = supplied.get("request")
        if not isinstance(request, Mapping):
            raise ValueError("preview request is missing")
        event = _nmc.ChangeEvent.from_dict(request["changeEvent"])
        if event.sequence != expected_sequence or event.previous_hash != expected_head_sha256:
            raise ValueError("commit CAS does not match preview event identity")

        decision = _validate_replay_artifact(preview_artifact, event=event)
        _verify_commit_state_preflight()
        existing = _existing_event(_ledger_path(), event.event_id)

        if existing is None:
            global_quota = _global_quota(_ledger_path())
            if global_quota["exceeded"]:
                return _output(
                    ok=False,
                    status="NEURO_EVENT_COMMIT_QUOTA_REACHED",
                    failure_family="NEURO_GLOBAL_LEDGER_QUOTA_REACHED",
                    blocker="the bounded global neuro ledger quota is exhausted",
                    next_action="retain the preview as non-persisted evidence and rotate state under owner policy",
                    mutation_performed=False,
                    evidence={
                        "globalQuota": global_quota,
                        "eventPersisted": False,
                        "recoveryIntentRetained": False,
                        "externalEffectPerformed": False,
                    },
                    data={"proposalExecuted": False},
                )

        head = _read_source_head(_ledger_path(), event.source)
        if existing is None and (
            head["lastEventHash"] != expected_head_sha256 or head["nextSequence"] != expected_sequence
        ):
            return _output(
                ok=False,
                status="NEURO_EVENT_COMMIT_CONFLICT",
                failure_family="NEURO_SOURCE_HEAD_CAS_MISMATCH",
                blocker="the source head advanced after preview",
                next_action="create a new preview from the current source head",
                evidence={
                    "expectedHeadSha256": expected_head_sha256,
                    "actualHeadSha256": head["lastEventHash"],
                    "expectedSequence": expected_sequence,
                    "actualNextSequence": head["nextSequence"],
                    "externalEffectPerformed": False,
                },
                data={"proposalExecuted": False},
            )

        if existing is None:
            rebuilt = _build_preview(request)
            if rebuilt["previewSha256"] != preview_sha256 or rebuilt != preview_artifact:
                raise ValueError("preview no longer matches current contracts or registry snapshot")
            if rebuilt.get("admitted") is not True:
                raise ValueError("quarantined preview cannot be committed")
        else:
            rebuilt = preview_artifact

        _ensure_private_state_root()
        with _nmc.NeuromorphicLedger(_ledger_path()) as ledger:
            registry_sha256 = str(rebuilt["proposal"].get("registrySnapshotSha256") or ZERO_SHA256)
            intent = _ensure_commit_intent(
                _ledger_path(),
                event_id=event.event_id,
                event_hash=event.event_hash,
                preview_sha256=preview_sha256,
                decision_sha256=decision["decisionSha256"],
                registry_sha256=registry_sha256,
                classification=str(rebuilt["classification"]),
            )
            if existing is None:
                receipt = ledger.ingest(
                    event,
                    _FixedPreviewGate(rebuilt["relevance"]),
                    quota=_nmc.LedgerQuota(
                        max_events=int(global_quota["maxEvents"]),
                        max_bytes=int(global_quota["maxBytes"]),
                    ),
                )
            else:
                persisted = _nmc.ChangeEvent.from_dict(existing[0])
                receipt = replace(
                    _nmc.CandidateReceipt.from_dict(existing[1]),
                    replayed=True,
                )
                if persisted.event_hash != event.event_hash:
                    raise ValueError("event identity was already committed with different content")
            integrity = ledger.verify_integrity(event.source)
        foundation_evidence, foundation_chain = _record_foundation_decision(decision)
        admission = _complete_commit_intent(
            _ledger_path(),
            event_id=event.event_id,
            event_hash=event.event_hash,
            preview_sha256=preview_sha256,
            foundation_decision_sha256=decision["decisionSha256"],
            registry_sha256=registry_sha256,
            classification=str(rebuilt["classification"]),
            nmc_receipt_sha256=receipt.receipt_hash,
            foundation_evidence_sha256=foundation_evidence["evidenceSha256"],
        )
        component_writes = {
            "admissionIntentCreated": bool(intent["created"]),
            "nmcEventAppended": receipt.replayed is not True,
            "foundationEvidenceAppended": foundation_evidence.get("replayed") is not True,
            "admissionCompleted": admission.get("transitionPerformed") is True,
        }
        replayed = bool(
            receipt.replayed is True
            and foundation_evidence.get("replayed") is True
            and admission.get("replayed") is True
        )
        mutation_performed = any(component_writes.values())
        return _output(
            ok=True,
            status="NEURO_EVENT_ALREADY_COMMITTED" if replayed else "NEURO_EVENT_COMMITTED",
            mutation_performed=mutation_performed,
            next_action="treat the persisted candidate as proposal-only evidence; execute no tool automatically",
            evidence={
                "previewSha256": preview_sha256,
                "eventHash": event.event_hash,
                "receiptHash": receipt.receipt_hash,
                "registrySnapshotSha256": rebuilt["proposal"]["registrySnapshotSha256"],
                "sourceChainVerified": bool(integrity.ok),
                "foundationDecisionSha256": decision["decisionSha256"],
                "foundationEvidenceSha256": foundation_evidence["evidenceSha256"],
                "foundationChainVerified": foundation_chain.get("valid") is True,
                "admissionReceiptSha256": admission["admissionReceiptSha256"],
                "crossLedgerCommitComplete": True,
                "replayed": replayed,
                "componentWrites": component_writes,
                "externalEffectPerformed": False,
            },
            data={
                "receipt": receipt.to_dict(),
                "foundationReceipt": foundation_evidence,
                "admissionReceipt": admission,
                "proposal": rebuilt["proposal"],
                "proposalOnly": True,
                "mayExecute": False,
                "autoExecute": False,
            },
        )
    except Exception as exc:
        event_persisted = False
        intent_retained = False
        if "event" in locals():
            try:
                event_persisted = _existing_event(_ledger_path(), event.event_id) is not None
            except Exception:
                event_persisted = False
            try:
                intent_retained = _commit_intent_state(_ledger_path(), event.event_id) is not None
            except Exception:
                intent_retained = False
        compensated = False
        safe_preappend_rejection = bool(
            _nmc is not None
            and isinstance(
                exc,
                (
                    _nmc.SequenceConflictError,
                    _nmc.LedgerQuotaExceededError,
                    _nmc.TemporalOrderError,
                    _nmc.ChainIntegrityError,
                ),
            )
        )
        if safe_preappend_rejection and not event_persisted and intent_retained:
            try:
                compensated = _cancel_uncommitted_intent(_ledger_path(), event.event_id)
            except Exception:
                compensated = False
            if compensated:
                intent_retained = False
        partial = event_persisted or intent_retained
        return _output(
            ok=False,
            status=(
                "NEURO_EVENT_COMMIT_QUOTA_REACHED"
                if _nmc is not None and isinstance(exc, _nmc.LedgerQuotaExceededError)
                else "NEURO_EVENT_COMMIT_CONFLICT"
                if _nmc is not None and isinstance(exc, _nmc.SequenceConflictError)
                else "NEURO_EVENT_COMMIT_REJECTED"
            ),
            failure_family=type(exc).__name__,
            blocker=_bounded(exc, 300),
            next_action="obtain a fresh admitted preview and retry with its exact source-head CAS",
            mutation_performed=partial,
            evidence={
                "eventPersisted": event_persisted,
                "crossLedgerCommitComplete": False,
                "recoveryIntentRetained": intent_retained,
                "intentCompensated": compensated,
                "externalEffectPerformed": False,
            },
            data={"proposalExecuted": False, "retryIsRecoverySafe": True},
        )


def _ids(items: Any, section: str, errors: list[str]) -> set[str]:
    found: set[str] = set()
    if not isinstance(items, list):
        errors.append(f"{section} must be a list")
        return found
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            errors.append(f"{section}[{index}] must be an object")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id or len(item_id) > 160:
            errors.append(f"{section}[{index}] has no bounded id")
        elif item_id in found:
            errors.append(f"duplicate id in {section}: {item_id}")
        else:
            found.add(item_id)
    return found


def _require_fields(item: Mapping[str, Any], fields: Sequence[str], pointer: str, errors: list[str]) -> None:
    for field in fields:
        if item.get(field) in (None, "", []):
            errors.append(f"{pointer}.{field} is required")


def _is_canonical_utc_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not 20 <= len(value) <= 32:
        return False
    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z",
        value,
    ) is None:
        return False
    try:
        instant = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return instant.tzinfo is not None and instant.utcoffset() == timedelta(0)


def _timestamp_not_future(
    value: Any,
    *,
    validation_now: datetime,
    clock_skew: timedelta = timedelta(minutes=5),
) -> bool:
    if not _is_canonical_utc_timestamp(value):
        return False
    instant = datetime.fromisoformat(str(value)[:-1] + "+00:00")
    return instant <= validation_now + clock_skew


def _tool_reference(step: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = step.get("tool_ref", step.get("toolRef"))
    return value if isinstance(value, Mapping) else None


def _schema_type_matches(value: Any, kind: str) -> bool:
    if kind == "object":
        return isinstance(value, Mapping)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    return False


def _validate_supported_schema(
    schema: Any,
    *,
    pointer: str,
    errors: list[str],
    depth: int = 0,
) -> None:
    if depth > 8 or not isinstance(schema, Mapping):
        errors.append(f"{pointer} must be a bounded supported JSON schema object")
        return
    kind = schema.get("type")
    if kind not in {"object", "array", "string", "boolean", "integer", "number"}:
        errors.append(f"{pointer}.type is unsupported")
        return
    allowed = {"type", "enum", "title", "description"}
    if kind == "object":
        allowed |= {"properties", "required", "additionalProperties"}
    elif kind == "array":
        allowed |= {"items", "minItems", "maxItems"}
    elif kind == "string":
        allowed |= {"minLength", "maxLength"}
    elif kind in {"integer", "number"}:
        allowed |= {"minimum", "maximum"}
    unsupported = sorted(set(schema) - allowed)
    if unsupported:
        errors.append(f"{pointer} contains unsupported keywords: {', '.join(unsupported[:16])}")

    enum = schema.get("enum")
    if enum is not None:
        if not isinstance(enum, list) or not 1 <= len(enum) <= 64:
            errors.append(f"{pointer}.enum must be a bounded non-empty list")
        elif any(not _schema_type_matches(value, kind) for value in enum):
            errors.append(f"{pointer}.enum contains a value of the wrong type")
        elif len({_canonical_json(value) for value in enum}) != len(enum):
            errors.append(f"{pointer}.enum contains duplicates")

    if kind == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        additional = schema.get("additionalProperties", True)
        if not isinstance(properties, Mapping) or len(properties) > 64:
            errors.append(f"{pointer}.properties must be a bounded object")
            properties = {}
        if (
            not isinstance(required, list)
            or any(not isinstance(name, str) for name in required)
            or len(set(required)) != len(required)
        ):
            errors.append(f"{pointer}.required must be a unique string list")
            required = []
        elif any(name not in properties for name in required):
            errors.append(f"{pointer}.required contains undeclared properties")
        if not isinstance(additional, bool):
            errors.append(f"{pointer}.additionalProperties must be boolean")
        for name, child in properties.items():
            if not isinstance(name, str) or not name or len(name) > 160:
                errors.append(f"{pointer}.properties contains an invalid name")
                continue
            _validate_supported_schema(
                child,
                pointer=f"{pointer}.properties.{name}",
                errors=errors,
                depth=depth + 1,
            )
    elif kind == "array":
        if "items" not in schema:
            errors.append(f"{pointer}.items is required")
        else:
            _validate_supported_schema(
                schema["items"], pointer=f"{pointer}.items", errors=errors, depth=depth + 1
            )
        minimum = schema.get("minItems", 0)
        maximum = schema.get("maxItems", 2_048)
        if (
            isinstance(minimum, bool)
            or isinstance(maximum, bool)
            or not isinstance(minimum, int)
            or not isinstance(maximum, int)
            or not 0 <= minimum <= maximum <= 2_048
        ):
            errors.append(f"{pointer} has invalid array bounds")
    elif kind == "string":
        minimum = schema.get("minLength", 0)
        maximum = schema.get("maxLength", _MAX_TEXT_FIELD)
        if (
            isinstance(minimum, bool)
            or isinstance(maximum, bool)
            or not isinstance(minimum, int)
            or not isinstance(maximum, int)
            or not 0 <= minimum <= maximum <= _MAX_GRAMMAR_SOURCE_CHARS
        ):
            errors.append(f"{pointer} has invalid string bounds")
    elif kind in {"integer", "number"}:
        minimum = schema.get("minimum", -1_000_000_000)
        maximum = schema.get("maximum", 1_000_000_000)
        if (
            not _schema_type_matches(minimum, kind)
            or not _schema_type_matches(maximum, kind)
            or minimum > maximum
        ):
            errors.append(f"{pointer} has invalid numeric bounds")


def _validate_schema_value(schema: Mapping[str, Any], value: Any, *, pointer: str) -> None:
    kind = str(schema["type"])
    if not _schema_type_matches(value, kind):
        raise ValueError(f"{pointer} must be {kind}")
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        raise ValueError(f"{pointer} is outside the allowed enum")
    if kind == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = [name for name in required if name not in value]
        if missing:
            raise ValueError(f"{pointer} misses required fields: {', '.join(missing[:16])}")
        if schema.get("additionalProperties", True) is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise ValueError(f"{pointer} contains undeclared fields: {', '.join(extra[:16])}")
        for name, child in properties.items():
            if name in value:
                _validate_schema_value(child, value[name], pointer=f"{pointer}.{name}")
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 2_048):
            raise ValueError(f"{pointer} violates array bounds")
        for index, child in enumerate(value):
            _validate_schema_value(schema["items"], child, pointer=f"{pointer}[{index}]")
    elif kind == "string":
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", _MAX_TEXT_FIELD):
            raise ValueError(f"{pointer} violates string bounds")
    elif kind in {"integer", "number"}:
        if not schema.get("minimum", -1_000_000_000) <= value <= schema.get("maximum", 1_000_000_000):
            raise ValueError(f"{pointer} violates numeric bounds")


def _read_repository_regular_file(
    repository: Path,
    *,
    locator: Any,
    maximum_bytes: int,
    minimum_bytes: int = 0,
) -> tuple[bytes | None, str | None, str | None]:
    """Read one repository file through no-follow directory descriptors.

    The returned locator is canonical and relative.  File bytes remain private
    to validation and are never included in a tool result.
    """

    if not isinstance(locator, str) or not locator or len(locator) > 512:
        return None, None, "locator must be a bounded repository-relative file path"
    relative = Path(locator)
    canonical = relative.as_posix()
    if (
        relative.is_absolute()
        or not relative.parts
        or canonical != locator
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        return None, None, "locator must be a canonical repository-relative file path"
    descriptors: list[int] = []
    try:
        root_status = os.lstat(repository)
        if stat.S_ISLNK(root_status.st_mode) or not stat.S_ISDIR(root_status.st_mode):
            return None, None, "repository root must be a non-symlink directory"
        directory_flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            directory_flags |= os.O_DIRECTORY
        if hasattr(os, "O_NOFOLLOW"):
            directory_flags |= os.O_NOFOLLOW
        directory = os.open(repository, directory_flags)
        descriptors.append(directory)
        for component in relative.parts[:-1]:
            directory = os.open(component, directory_flags, dir_fd=directory)
            descriptors.append(directory)
            opened_directory = os.fstat(directory)
            if not stat.S_ISDIR(opened_directory.st_mode):
                return None, None, "locator path components must be non-symlink directories"

        file_flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        descriptor = os.open(relative.parts[-1], file_flags, dir_fd=directory)
        descriptors.append(descriptor)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            return None, None, "locator must identify a non-symlink regular file"
        if opened.st_size < minimum_bytes or opened.st_size > maximum_bytes:
            return None, None, "repository file size is outside the bounded read limit"
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
            return None, None, "repository file identity changed during verification"
        return content, canonical, None
    except (OSError, ValueError):
        return None, None, "locator does not resolve to an approved repository file"
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _verify_local_provenance_file(
    repository: Path,
    *,
    locator: Any,
    expected_sha256: Any,
) -> tuple[str | None, bytes | None, str | None]:
    content, canonical_locator, error = _read_repository_regular_file(
        repository,
        locator=locator,
        maximum_bytes=_MAX_PACKAGE_BYTES,
    )
    if error:
        return error, None, None
    assert content is not None
    if not isinstance(expected_sha256, str) or _sha256_bytes(content) != expected_sha256:
        return "content_hash does not match the repository source bytes", None, None
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return "repository source must be valid UTF-8 for textual evidence", None, None
    return None, content, canonical_locator


def _evidence_locator_matches_source(
    locator: Any,
    *,
    source_locator: str,
    source_bytes: bytes,
    excerpt: str,
) -> bool:
    if locator == source_locator:
        return True
    if not isinstance(locator, str) or len(locator) > 640:
        return False
    fragment = re.fullmatch(
        re.escape(source_locator) + r"#L([1-9]\d*)(?:-L?([1-9]\d*))?",
        locator,
    )
    if fragment is None:
        return False
    start = int(fragment.group(1))
    end = int(fragment.group(2) or start)
    lines = source_bytes.decode("utf-8").splitlines()
    if end < start or end > len(lines) or end - start > 256:
        return False
    selected = "\n".join(lines[start - 1 : end])
    return excerpt in selected


def _validate_package(
    package: Mapping[str, Any],
    registry: Mapping[str, Any],
    *,
    repository: Path,
    validation_now: datetime | None = None,
) -> tuple[list[str], list[str], list[dict[str, Any]], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    resolved_tools: list[dict[str, Any]] = []
    checked_now = validation_now or datetime.now(timezone.utc)
    if checked_now.tzinfo is None or checked_now.utcoffset() != timedelta(0):
        raise ValueError("validation_now must be timezone-aware UTC")
    if package.get("schema_version") != "1.0":
        errors.append("schema_version must equal '1.0'")
    root = package.get("package")
    if not isinstance(root, Mapping):
        errors.append("package must be an object")
    else:
        _require_fields(
            root,
            ("id", "title", "version", "created_at", "language", "scope", "source_profile_ref", "limitations"),
            "package",
            errors,
        )
        if not _timestamp_not_future(root.get("created_at"), validation_now=checked_now):
            errors.append("package.created_at must be canonical UTC and not in the future")

    provenance_ids = _ids(package.get("provenance"), "provenance", errors)
    evidence_ids = _ids(package.get("evidence"), "evidence", errors)
    knowledge_ids = _ids(package.get("knowledge_units"), "knowledge_units", errors)
    skill_ids = _ids(package.get("skills"), "skills", errors)
    assessment_ids = _ids(package.get("assessments"), "assessments", errors)
    adapter_ids = _ids(package.get("target_adapters"), "target_adapters", errors)
    groups = (provenance_ids, evidence_ids, knowledge_ids, skill_ids, assessment_ids, adapter_ids)
    if len(set().union(*groups)) != sum(len(group) for group in groups):
        errors.append("ids must be globally unique")

    verified_source_bytes: dict[str, bytes] = {}
    verified_source_locators: dict[str, str] = {}
    provenance_by_id: dict[str, Mapping[str, Any]] = {}
    for item in package.get("provenance", []) if isinstance(package.get("provenance"), list) else []:
        if not isinstance(item, Mapping):
            continue
        provenance_id = item.get("id")
        if isinstance(provenance_id, str):
            provenance_by_id[provenance_id] = item
        pointer = f"provenance[{item.get('id', '?')}]"
        _require_fields(
            item,
            ("id", "source_type", "locator", "retrieved_at", "content_hash", "trust_level", "license_or_policy"),
            pointer,
            errors,
        )
        if not isinstance(item.get("content_hash"), str) or not _SHA256.fullmatch(item.get("content_hash", "")):
            errors.append(f"{pointer}.content_hash must be lowercase SHA-256")
        if item.get("source_type") not in _ALLOWED_SOURCE_TYPES:
            errors.append(f"{pointer}.source_type is not in the canonical archive allowlist")
        if not _timestamp_not_future(item.get("retrieved_at"), validation_now=checked_now):
            errors.append(
                f"{pointer}.retrieved_at must be bounded canonical RFC3339 UTC and not in the future"
            )
        if item.get("trust_level") not in _ALLOWED_TRUST_POLICIES:
            errors.append(f"{pointer}.trust_level is not a recognized non-authority trust policy")
        license_value = str(item.get("license_or_policy") or "").strip().casefold()
        if license_value not in _ALLOWED_LICENSE_POLICIES:
            errors.append(
                f"{pointer}.license_or_policy is not an explicitly supported license or owner policy"
            )
        source_type = item.get("source_type")
        trust_level = item.get("trust_level")
        if source_type == "files":
            if trust_level not in {"repository", "repository-local"}:
                errors.append(f"{pointer} local files require repository-scoped trust")
            if license_value not in {"repository-owner-policy", "proprietary-owner-policy"}:
                errors.append(f"{pointer} local files require an explicit repository owner policy")
            file_error, source_bytes, source_locator = _verify_local_provenance_file(
                repository,
                locator=item.get("locator"),
                expected_sha256=item.get("content_hash"),
            )
            if file_error:
                errors.append(f"{pointer}.{file_error}")
            elif (
                isinstance(provenance_id, str)
                and source_bytes is not None
                and source_locator is not None
            ):
                verified_source_bytes[provenance_id] = source_bytes
                verified_source_locators[provenance_id] = source_locator
        elif source_type in _ALLOWED_SOURCE_TYPES:
            if trust_level in {"repository", "repository-local"}:
                errors.append(f"{pointer} external sources cannot assert repository trust")
            if license_value in {
                "repository-owner-policy",
                "owner-approved-internal",
                "proprietary-owner-policy",
            }:
                errors.append(f"{pointer} external sources cannot assert an internal owner policy")
            errors.append(
                f"{pointer} external archive source is not locally verifiable and cannot be assessed"
            )

    for item in package.get("evidence", []) if isinstance(package.get("evidence"), list) else []:
        if not isinstance(item, Mapping):
            continue
        pointer = f"evidence[{item.get('id', '?')}]"
        _require_fields(item, ("id", "provenance_ref", "locator", "excerpt", "content_hash", "classification"), pointer, errors)
        provenance_ref = item.get("provenance_ref")
        if provenance_ref not in provenance_ids:
            errors.append(f"{pointer}.provenance_ref does not resolve")
        excerpt = item.get("excerpt")
        if not isinstance(excerpt, str) or len(excerpt) > 16_384:
            errors.append(f"{pointer}.excerpt is not bounded text")
        elif _sha256_bytes(excerpt.encode("utf-8")) != item.get("content_hash"):
            errors.append(f"{pointer}.content_hash does not match excerpt")
        elif provenance_ref in verified_source_bytes:
            encoded_excerpt = excerpt.encode("utf-8")
            if encoded_excerpt not in verified_source_bytes[provenance_ref]:
                errors.append(f"{pointer}.excerpt is not present byte-exactly in the verified source")
            elif not _evidence_locator_matches_source(
                item.get("locator"),
                source_locator=verified_source_locators[provenance_ref],
                source_bytes=verified_source_bytes[provenance_ref],
                excerpt=excerpt,
            ):
                errors.append(f"{pointer}.locator is not bound to the verified source or fragment")
        classification = item.get("classification")
        if classification not in _ALLOWED_EVIDENCE_CLASSIFICATIONS:
            errors.append(f"{pointer}.classification must be public or internal")
        provenance = provenance_by_id.get(str(provenance_ref))
        if (
            isinstance(provenance, Mapping)
            and provenance.get("source_type") != "files"
            and classification == "internal"
        ):
            errors.append(f"{pointer} external evidence cannot self-assert internal classification")

    knowledge_text: list[str] = []
    for item in package.get("knowledge_units", []) if isinstance(package.get("knowledge_units"), list) else []:
        if not isinstance(item, Mapping):
            continue
        pointer = f"knowledge_units[{item.get('id', '?')}]"
        _require_fields(
            item,
            ("id", "claim", "explanation", "scope", "assumptions", "evidence_refs", "confidence"),
            pointer,
            errors,
        )
        refs = item.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{pointer}.evidence_refs must be non-empty")
        elif any(ref not in evidence_ids for ref in refs):
            errors.append(f"{pointer}.evidence_refs do not resolve")
        if item.get("confidence") == "needs_human_review":
            errors.append(f"{pointer} remains needs_human_review")
        knowledge_text.append(f"{_bounded(item.get('claim'))}\n{_bounded(item.get('explanation'))}\n")

    registry_by_name = {item["name"]: item for item in registry["tools"]}
    seen_tools: set[tuple[str, str, str]] = set()
    for item in package.get("skills", []) if isinstance(package.get("skills"), list) else []:
        if not isinstance(item, Mapping):
            continue
        pointer = f"skills[{item.get('id', '?')}]"
        _require_fields(
            item,
            ("id", "title", "outcome", "preconditions", "inputs_schema", "steps", "verification", "safety_boundaries"),
            pointer,
            errors,
        )
        schema = item.get("inputs_schema")
        if not isinstance(schema, Mapping) or schema.get("type") != "object":
            errors.append(f"{pointer}.inputs_schema must be an object JSON schema")
        else:
            _validate_supported_schema(
                schema,
                pointer=f"{pointer}.inputs_schema",
                errors=errors,
            )
        steps = item.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"{pointer}.steps must be non-empty")
            continue
        for index, step in enumerate(steps):
            step_pointer = f"{pointer}.steps[{index}]"
            if not isinstance(step, Mapping):
                errors.append(f"{step_pointer} must be an object")
                continue
            _require_fields(step, ("id", "action", "why"), step_pointer, errors)
            ref = _tool_reference(step)
            if ref is None:
                errors.append(f"{step_pointer}.tool_ref is required for live-registry binding")
                continue
            name = ref.get("name")
            expected_contract = ref.get("contractSha256", ref.get("contract_sha256"))
            expected_effect = ref.get("effect")
            live = registry_by_name.get(name) if isinstance(name, str) else None
            if live is None:
                errors.append(f"{step_pointer}.tool_ref is not registered: {_bounded(name, 160)}")
                continue
            if expected_contract != live["contractSha256"]:
                errors.append(f"{step_pointer}.tool_ref contract is stale")
            if expected_effect != live["effect"]:
                errors.append(f"{step_pointer}.tool_ref effect mismatch")
            key = (live["name"], live["contractSha256"], live["effect"])
            if key not in seen_tools:
                seen_tools.add(key)
                resolved_tools.append(
                    {"name": key[0], "contractSha256": key[1], "effect": key[2]}
                )
        verification = item.get("verification")
        if not isinstance(verification, Mapping):
            errors.append(f"{pointer}.verification must be an object")
        else:
            _require_fields(verification, ("success_conditions", "failure_signals", "fallback"), f"{pointer}.verification", errors)

    assessed: set[str] = set()
    for item in package.get("assessments", []) if isinstance(package.get("assessments"), list) else []:
        if not isinstance(item, Mapping):
            continue
        pointer = f"assessments[{item.get('id', '?')}]"
        _require_fields(item, ("id", "skill_or_knowledge_ref", "type", "prompt", "rubric"), pointer, errors)
        target = item.get("skill_or_knowledge_ref")
        if target not in skill_ids and target not in knowledge_ids:
            errors.append(f"{pointer}.skill_or_knowledge_ref does not resolve")
        if target in skill_ids:
            assessed.add(str(target))
    missing_assessments = sorted(skill_ids - assessed)
    if missing_assessments:
        errors.append("skills without assessment: " + ", ".join(missing_assessments))

    for item in package.get("target_adapters", []) if isinstance(package.get("target_adapters"), list) else []:
        if not isinstance(item, Mapping):
            continue
        pointer = f"target_adapters[{item.get('id', '?')}]"
        _require_fields(item, ("id", "target_kind", "format", "mapping", "write_mode", "approval_required"), pointer, errors)
        mode = item.get("write_mode")
        if mode not in {"read_only", "preview_only", "write_after_approval"}:
            errors.append(f"{pointer}.write_mode is invalid")
        if mode == "write_after_approval" and item.get("approval_required") is not True:
            errors.append(f"{pointer} must require approval")
    if not evidence_ids:
        errors.append("at least one evidence object is required")
    if not knowledge_ids:
        errors.append("at least one knowledge unit is required")
    if not skill_ids:
        errors.append("at least one skill is required")

    atlas = _segment_text("".join(knowledge_text), tile_chars=768)
    return errors[:_MAX_ERRORS], warnings[:_MAX_ERRORS], resolved_tools, atlas


def _segment_text(text: str, *, tile_chars: int = 768) -> dict[str, Any]:
    """Create private grammar-like tiles and verify exact reconstruction."""

    if not isinstance(text, str):
        raise ValueError("grammar source must be text")
    if not 64 <= tile_chars <= 2_048:
        raise ValueError("tile_chars must be between 64 and 2048")
    if len(text) > _MAX_GRAMMAR_SOURCE_CHARS:
        raise ValueError("grammar source exceeds character bound")

    pieces: list[str] = []
    start = 0
    for match in re.finditer(r"(?:[.!?](?=\s|$)|\n)", text):
        end = match.end()
        pieces.append(text[start:end])
        start = end
    if start < len(text):
        pieces.append(text[start:])
    if not pieces and text:
        pieces = [text]

    mode = "grammar-boundary"
    packed: list[str] = []
    current = ""
    for piece in pieces:
        if len(piece) > tile_chars:
            mode = "fixed-width-fallback"
            if current:
                packed.append(current)
                current = ""
            packed.extend(piece[index : index + tile_chars] for index in range(0, len(piece), tile_chars))
        elif current and len(current) + len(piece) > tile_chars:
            packed.append(current)
            current = piece
        else:
            current += piece
    if current or not packed:
        packed.append(current)
    if len(packed) > _MAX_GRAMMAR_TILES:
        raise ValueError("grammar tile count exceeds bound")

    tiles: list[dict[str, Any]] = []
    offset = 0
    for index, tile in enumerate(packed):
        encoded = tile.encode("utf-8")
        tiles.append(
            {
                "id": f"tile-{index:03d}",
                "start": offset,
                "end": offset + len(tile),
                "byteLength": len(encoded),
                "tileSha256": _sha256_bytes(encoded),
            }
        )
        offset += len(tile)
    reconstructed = "".join(packed)
    source_hash = _sha256_bytes(text.encode("utf-8"))
    verified = reconstructed == text and _sha256_bytes(reconstructed.encode("utf-8")) == source_hash
    atlas = {
        "schemaVersion": GRAMMAR_ATLAS_SCHEMA_VERSION,
        "mode": mode,
        "sourceSha256": source_hash,
        "sourceCharacters": len(text),
        "tileCount": len(tiles),
        "tiles": tiles,
        "reconstructionVerified": verified,
        "sourceReturned": False,
    }
    # The hash is deliberately computed only after fallback tiles are final.
    atlas["atlasSha256"] = _sha256(atlas)
    if not verified:
        raise RuntimeError("grammar tile reconstruction failed")
    return atlas


def _read_package(
    workspace_id: str,
    relative_path: str,
    expected_sha256: str,
) -> tuple[dict[str, Any], str, str, Path]:
    if _RUNTIME is None:
        raise RuntimeError("teaching tools are not registered")
    validate_workspace_id(workspace_id)
    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        raise ValueError("expected_sha256 must be lowercase SHA-256")
    repository = Path(_RUNTIME._repo(workspace_id))
    raw, canonical_locator, error = _read_repository_regular_file(
        repository,
        locator=relative_path,
        maximum_bytes=_MAX_PACKAGE_BYTES,
        minimum_bytes=2,
    )
    if error or raw is None or canonical_locator is None:
        raise ValueError(error or "knowledge package is not a safe repository file")
    actual = _sha256_bytes(raw)
    if actual != expected_sha256:
        raise ValueError("knowledge package hash mismatch")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("knowledge package is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("knowledge package root must be an object")
    _reject_secret_shaped(value)
    return value, actual, canonical_locator, repository


def _assessment_receipt(
    package: Mapping[str, Any],
    *,
    package_sha256: str,
    package_locator: str,
    registry: Mapping[str, Any],
    errors: list[str],
    warnings: list[str],
    resolved_tools: list[dict[str, Any]],
    knowledge_atlas: Mapping[str, Any],
) -> dict[str, Any]:
    root = package.get("package") if isinstance(package.get("package"), Mapping) else {}
    body = {
        "schemaVersion": ASSESSMENT_SCHEMA_VERSION,
        "ok": not errors,
        "status": "TEACHING_PACKAGE_ASSESSED" if not errors else "TEACHING_PACKAGE_REJECTED",
        "packageId": root.get("id"),
        "packageSha256": package_sha256,
        "packageLocator": package_locator,
        "registrySnapshotSha256": registry["registrySnapshotSha256"],
        "toolContracts": resolved_tools,
        "skillIds": sorted(
            str(item["id"])
            for item in package.get("skills", [])
            if isinstance(item, Mapping) and item.get("id")
        ),
        "assessmentIds": sorted(
            str(item["id"])
            for item in package.get("assessments", [])
            if isinstance(item, Mapping) and item.get("id")
        ),
        "errors": [_bounded(item, 320) for item in errors[:_MAX_ERRORS]],
        "warnings": [_bounded(item, 320) for item in warnings[:_MAX_ERRORS]],
        "knowledgeAtlasSha256": knowledge_atlas["atlasSha256"],
        "mutationPerformed": False,
        "externalEffects": [],
    }
    body["receiptSha256"] = _sha256(body)
    return body


def teaching_package_assess(
    workspace_id: Annotated[str, Field(min_length=6, max_length=64)],
    relative_path: Annotated[str, Field(min_length=1, max_length=500)],
    expected_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")],
) -> NeuroTeachingOutput:
    """Fail-closed validation of a hash-bound package against the live registry."""

    try:
        package, actual_sha, package_locator, repository = _read_package(
            workspace_id, relative_path, expected_sha256
        )
        registry = _registry_snapshot()
        errors, warnings, resolved_tools, atlas = _validate_package(
            package, registry, repository=repository
        )
        receipt = _assessment_receipt(
            package,
            package_sha256=actual_sha,
            package_locator=package_locator,
            registry=registry,
            errors=errors,
            warnings=warnings,
            resolved_tools=resolved_tools,
            knowledge_atlas=atlas,
        )
        ok = not errors
        return _output(
            ok=ok,
            status=receipt["status"],
            failure_family=None if ok else "TEACHING_PACKAGE_CONTRACT_VIOLATION",
            blocker=None if ok else "knowledge package failed one or more deterministic gates",
            next_action=(
                "use the assessment receipt for a bounded lesson simulation"
                if ok
                else "repair every reported package or live-tool contract error"
            ),
            evidence={
                "packageSha256": actual_sha,
                "registrySnapshotSha256": registry["registrySnapshotSha256"],
                "assessmentReceiptSha256": receipt["receiptSha256"],
                "packageWritten": False,
                "externalEffectPerformed": False,
            },
            data={
                "assessmentReceipt": receipt,
                "knowledgeAtlas": atlas,
                "resolvedToolContracts": resolved_tools,
                "relativePath": relative_path,
            },
        )
    except Exception as exc:
        return _output(
            ok=False,
            status="TEACHING_PACKAGE_REJECTED",
            failure_family=type(exc).__name__,
            blocker=_bounded(exc, 300),
            next_action="supply a bounded repository-local package with its exact SHA-256",
            evidence={"packageWritten": False, "externalEffectPerformed": False},
            data={"relativePath": relative_path},
        )


def _verify_assessment_receipt(
    receipt: Mapping[str, Any],
    *,
    package_sha256: str,
    package_locator: str,
    registry_sha256: str,
) -> None:
    if receipt.get("schemaVersion") != ASSESSMENT_SCHEMA_VERSION:
        raise ValueError("assessment receipt schema is invalid")
    asserted = receipt.get("receiptSha256")
    unsigned = {key: value for key, value in receipt.items() if key != "receiptSha256"}
    if asserted != _sha256(unsigned):
        raise ValueError("assessment receipt hash mismatch")
    if receipt.get("ok") is not True or receipt.get("status") != "TEACHING_PACKAGE_ASSESSED":
        raise ValueError("assessment receipt is not successful")
    if receipt.get("packageSha256") != package_sha256:
        raise ValueError("assessment receipt package hash mismatch")
    if receipt.get("packageLocator") != package_locator:
        raise ValueError("assessment receipt package locator mismatch")
    if receipt.get("registrySnapshotSha256") != registry_sha256:
        raise ValueError("assessment receipt registry snapshot is stale")


def _index(items: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    return {
        str(item["id"]): dict(item)
        for item in items
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }


def _validate_lesson_inputs(schema: Mapping[str, Any], values: Mapping[str, Any]) -> list[str]:
    encoded = _canonical_json(values).encode("utf-8")
    if len(encoded) > 8_192 or len(values) > 32:
        raise ValueError("lesson inputs exceed the bounded limit")
    _reject_secret_shaped(values, pointer="$.lessonInputs")
    schema_errors: list[str] = []
    _validate_supported_schema(schema, pointer="$.lessonSchema", errors=schema_errors)
    if schema_errors:
        raise ValueError("lesson schema is unsupported: " + "; ".join(schema_errors[:8]))
    _validate_schema_value(schema, values, pointer="$.lessonInputs")
    return sorted(str(key) for key in values)


def _render_lesson(
    skill: Mapping[str, Any],
    knowledge: Mapping[str, Mapping[str, Any]],
    input_keys: list[str],
) -> str:
    lines = [
        f"# Lektion: {_bounded(skill.get('title', skill.get('id')), 240)}",
        "",
        f"Ziel: {_bounded(skill.get('outcome'), 1_000)}",
        "",
    ]
    refs = skill.get("knowledge_refs", [])
    if isinstance(refs, list) and refs:
        lines.extend(["## Fachliche Grundlage", ""])
        for reference in refs[:24]:
            unit = knowledge.get(str(reference))
            if unit is None:
                lines.append(f"- Fehlende Wissenseinheit: {_bounded(reference, 160)}")
                continue
            lines.append(f"- {_bounded(unit.get('claim', reference), 1_000)}")
            lines.append(f"  {_bounded(unit.get('explanation'), 2_000)}")
            evidence_refs = unit.get("evidence_refs", [])
            if isinstance(evidence_refs, list):
                lines.append("  Evidenz: " + ", ".join(_bounded(item, 120) for item in evidence_refs[:16]))
    lines.extend(["", "## Vorbedingungen", ""])
    for value in list(skill.get("preconditions") or [])[:32]:
        lines.append(f"- {_bounded(value, 600)}")
    lines.extend(["", "## Sicherer Dry-Run", ""])
    lines.append("Eingabefelder: " + (", ".join(input_keys) if input_keys else "keine"))
    for number, step in enumerate(list(skill.get("steps") or [])[:48], start=1):
        if not isinstance(step, Mapping):
            continue
        ref = _tool_reference(step) or {}
        lines.append(
            f"{number}. {_bounded(step.get('action'), 800)} — Warum: {_bounded(step.get('why'), 800)} "
            f"[Toolvertrag: {_bounded(ref.get('name'), 160)}]"
        )
    verification = skill.get("verification") if isinstance(skill.get("verification"), Mapping) else {}
    lines.extend(["", "## Prüfung und Rückfallweg", ""])
    lines.append(
        "Erfolgsbedingungen: "
        + "; ".join(_bounded(item, 400) for item in list(verification.get("success_conditions") or [])[:24])
    )
    lines.append(
        "Fehlersignale: "
        + "; ".join(_bounded(item, 400) for item in list(verification.get("failure_signals") or [])[:24])
    )
    lines.append(f"Rückfallweg: {_bounded(verification.get('fallback'), 1_000)}")
    lines.extend(["", "## Sicherheitsgrenzen", ""])
    for boundary in list(skill.get("safety_boundaries") or [])[:32]:
        lines.append(f"- {_bounded(boundary, 600)}")
    lines.extend(
        [
            "",
            "> Diese Simulation führt kein Tool aus, schreibt keine Daten und verändert weder Regeln noch Modellgewichte.",
        ]
    )
    return "\n".join(lines) + "\n"


def teaching_lesson_simulate(
    workspace_id: Annotated[str, Field(min_length=6, max_length=64)],
    relative_path: Annotated[str, Field(min_length=1, max_length=500)],
    package_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")],
    assessment_receipt: dict[str, Any],
    skill_id: Annotated[str, Field(min_length=1, max_length=160)],
    exercise_inputs: dict[str, Any] | None = None,
    max_output_chars: Annotated[int, Field(ge=512, le=16_000)] = 8_000,
) -> NeuroTeachingOutput:
    """Render a bounded, hash-bound lesson; no package step is executed."""

    try:
        package, actual_sha, package_locator, repository = _read_package(
            workspace_id, relative_path, package_sha256
        )
        registry = _registry_snapshot()
        _verify_assessment_receipt(
            assessment_receipt,
            package_sha256=actual_sha,
            package_locator=package_locator,
            registry_sha256=registry["registrySnapshotSha256"],
        )
        errors, _warnings, resolved_tools, knowledge_atlas = _validate_package(
            package, registry, repository=repository
        )
        if errors:
            raise ValueError("knowledge package no longer passes assessment")
        skills = _index(package.get("skills"))
        skill = skills.get(skill_id)
        if skill is None:
            raise ValueError("skill is not present in the assessed package")
        receipt_skills = assessment_receipt.get("skillIds")
        if not isinstance(receipt_skills, list) or skill_id not in receipt_skills:
            raise ValueError("skill is not bound by the assessment receipt")
        inputs = dict(exercise_inputs or {})
        schema = skill.get("inputs_schema") if isinstance(skill.get("inputs_schema"), Mapping) else {}
        input_keys = _validate_lesson_inputs(schema, inputs)
        lesson = _render_lesson(skill, _index(package.get("knowledge_units")), input_keys)
        truncated = len(lesson) > max_output_chars
        if truncated:
            marker = "\n\n[Lesson output truncated at the configured bound]\n"
            lesson = lesson[: max(0, max_output_chars - len(marker))] + marker
        atlas = _segment_text(lesson, tile_chars=min(768, max(64, max_output_chars // 4)))
        return _output(
            ok=True,
            status="TEACHING_LESSON_SIMULATED",
            next_action="use the lesson as dry-run guidance; invoke any selected tool separately under its own contract",
            evidence={
                "packageSha256": actual_sha,
                "assessmentReceiptSha256": assessment_receipt["receiptSha256"],
                "registrySnapshotSha256": registry["registrySnapshotSha256"],
                "lessonSha256": _sha256_bytes(lesson.encode("utf-8")),
                "grammarAtlasSha256": atlas["atlasSha256"],
                "packageWritten": False,
                "toolExecuted": False,
                "externalEffectPerformed": False,
            },
            data={
                "mode": "dry_run",
                "skillId": skill_id,
                "lesson": lesson,
                "characterCount": len(lesson),
                "truncated": truncated,
                "inputKeys": input_keys,
                "resolvedToolContracts": resolved_tools,
                "grammarAtlas": atlas,
                "knowledgeAtlasSha256": knowledge_atlas["atlasSha256"],
                "proposalOnly": True,
                "mayExecute": False,
                "autoExecute": False,
            },
        )
    except Exception as exc:
        return _output(
            ok=False,
            status="TEACHING_LESSON_REJECTED",
            failure_family=type(exc).__name__,
            blocker=_bounded(exc, 300),
            next_action="obtain a fresh successful assessment receipt for the exact package and registry snapshot",
            evidence={"packageWritten": False, "toolExecuted": False, "externalEffectPerformed": False},
            data={"mode": "dry_run", "skillId": skill_id},
        )


def _policy_sha256() -> str:
    policy = Path(__file__).resolve().parent / "config" / "sovereign-continuity-policy.json"
    try:
        embedded = _sha256_bytes(policy.read_bytes())
    except OSError as exc:
        raise RuntimeError("canonical continuity policy is unavailable") from exc
    configured = os.getenv("SOVEREIGN_NEURO_POLICY_SHA256", "").strip()
    if configured and (not _SHA256.fullmatch(configured) or configured != embedded):
        raise ValueError("configured neuro policy hash does not match the embedded policy")
    return embedded


def _source_revision(event: Mapping[str, Any]) -> str:
    expected = os.getenv("SOVEREIGN_SOURCE_REVISION", "").strip()
    if not _SHA40.fullmatch(expected):
        raise ValueError("runtime has no exact source revision binding")
    asserted = str(event.get("revisionSha") or "").strip()
    if asserted and asserted != expected:
        raise ValueError("event source revision does not match the running image")
    return expected


def _assert_deployment_binding(event: Any) -> None:
    expected_revision = _source_revision({})
    expected_policy = _policy_sha256()
    if event.identity.revision_sha != expected_revision:
        raise ValueError("ChangeEvent revision does not match the running image")
    if event.identity.policy_sha256 != expected_policy:
        raise ValueError("ChangeEvent policy does not match the embedded continuity policy")


@contextmanager
def _outcome_write_lock():
    """Serialize replay/quota/append across threads and container workers."""

    state_root = _ensure_private_state_root()
    lock_path = state_root / "tool-outcome-neuro.lock"
    with _OUTCOME_THREAD_LOCK:
        expected = os.lstat(lock_path) if os.path.lexists(lock_path) else None
        if expected is not None and (
            stat.S_ISLNK(expected.st_mode)
            or not stat.S_ISREG(expected.st_mode)
            or expected.st_nlink != 1
        ):
            raise RuntimeError("tool outcome lock must be a non-symlink regular file")
        flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(lock_path, flags, 0o600)
        try:
            opened = os.fstat(descriptor)
            observed = os.lstat(lock_path)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or stat.S_ISLNK(observed.st_mode)
                or not stat.S_ISREG(observed.st_mode)
                or opened.st_dev != observed.st_dev
                or opened.st_ino != observed.st_ino
                or (
                    expected is not None
                    and (opened.st_dev != expected.st_dev or opened.st_ino != expected.st_ino)
                )
            ):
                raise RuntimeError("tool outcome lock identity changed during acquisition")
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def record_tool_outcome_event(event: dict[str, Any]) -> dict[str, Any]:
    """Project one bounded tool outcome into the shared neuro ledger.

    This is an internal adapter for ``tool_success_ranking.record_event`` and is
    intentionally not registered as an MCP tool.  Exceptions propagate so the
    caller can count degraded telemetry.  No tool is ever invoked here.
    """

    _require_runtime_modules()
    _validate_tool_outcome_boundary(event)
    with _outcome_write_lock():
        return _record_tool_outcome_event_serialized(event)


_TOOL_OUTCOME_KEYS = frozenset(
    {
        "schemaVersion",
        "eventId",
        "sequence",
        "tool",
        "recordedAtEpoch",
        "recordedAtEpochMs",
        "durationMs",
        "executionSuccess",
        "positiveOutcome",
        "status",
        "failureFamily",
        "missionFingerprint",
        "recommended",
        "argumentValuesRecorded",
        "secretValuesRecorded",
        "revisionSha",
        "policySha256",
    }
)
_TOOL_OUTCOME_STATUSES = frozenset(
    {
        "EXCEPTION",
        "TIMEOUT",
        "CONFLICT",
        "UNAVAILABLE",
        "BLOCKED",
        "SUCCEEDED",
        "REPORTED_NEGATIVE",
        "REPORTED_STATUS",
        "UNSPECIFIED",
    }
)
_TOOL_OUTCOME_FAILURES = frozenset(
    {
        "",
        "EXECUTION_FAILURE",
        "TIMEOUT",
        "CONFLICT",
        "UNAVAILABLE",
        "AUTHORIZATION_FAILURE",
        "QUOTA_REACHED",
        "CONTRACT_VIOLATION",
        "REPORTED_FAILURE",
    }
)


def _validate_tool_outcome_boundary(event: Mapping[str, Any]) -> None:
    """Validate the private ranking adapter before creating lock or ledger state."""

    if not isinstance(event, Mapping) or event.get("schemaVersion") != "sovereign.tool-event.v1":
        raise ValueError("unsupported tool outcome event")
    unexpected = set(event) - _TOOL_OUTCOME_KEYS
    if unexpected:
        raise ValueError("tool outcome event contains unsupported fields")
    _reject_secret_shaped(event, pointer="$.toolOutcome")
    if event.get("argumentValuesRecorded") is not False or event.get("secretValuesRecorded") is not False:
        raise ValueError("tool outcome event is not secret-free")
    if not isinstance(event.get("executionSuccess"), bool):
        raise ValueError("tool outcome executionSuccess must be boolean")
    if event.get("recommended") is not False:
        raise ValueError("mutable-only outcome telemetry cannot persist recommendations")
    positive = event.get("positiveOutcome")
    if positive is not None and not isinstance(positive, bool):
        raise ValueError("tool outcome positiveOutcome must be boolean or null")
    sequence = event.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ValueError("tool outcome sequence must be a non-negative integer")
    duration = event.get("durationMs")
    if isinstance(duration, bool) or not isinstance(duration, int) or not 0 <= duration <= 86_400_000:
        raise ValueError("tool outcome durationMs is invalid")
    status = event.get("status")
    failure = event.get("failureFamily")
    if status not in _TOOL_OUTCOME_STATUSES or failure not in _TOOL_OUTCOME_FAILURES:
        raise ValueError("tool outcome status/failure category is not canonical")
    fingerprint = event.get("missionFingerprint")
    if fingerprint != "" and (not isinstance(fingerprint, str) or not _SHA256.fullmatch(fingerprint)):
        raise ValueError("tool outcome missionFingerprint must be empty or SHA-256")
    recorded_ms = event.get("recordedAtEpochMs")
    recorded_epoch = event.get("recordedAtEpoch")
    if (
        isinstance(recorded_ms, bool)
        or not isinstance(recorded_ms, int)
        or recorded_ms < 0
        or isinstance(recorded_epoch, bool)
        or not isinstance(recorded_epoch, int)
        or recorded_epoch < 0
        or recorded_ms // 1_000 != recorded_epoch
    ):
        raise ValueError("tool outcome timestamp is invalid")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1_000)
    if recorded_ms > now_ms + 300_000:
        raise ValueError("tool outcome timestamp is in the future")
    tool = event.get("tool")
    if not isinstance(tool, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,159}", tool):
        raise ValueError("tool outcome tool name is invalid")
    event_id = event.get("eventId")
    if not isinstance(event_id, str) or not _SHA256.fullmatch(event_id):
        raise ValueError("tool outcome eventId must be a SHA-256 identity")
    _source_revision(event)
    expected_policy = _policy_sha256()
    asserted_policy = str(event.get("policySha256") or "").strip()
    if asserted_policy and asserted_policy != expected_policy:
        raise ValueError("tool outcome policy does not match the embedded continuity policy")


def _record_tool_outcome_event_serialized(event: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist while the cross-process outcome lock is held."""

    _require_runtime_modules()
    _validate_tool_outcome_boundary(event)
    if event.get("argumentValuesRecorded") is not False or event.get("secretValuesRecorded") is not False:
        raise ValueError("tool outcome event is not secret-free")
    tool = str(event.get("tool") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,159}", tool):
        raise ValueError("tool outcome tool name is invalid")
    event_id_seed = str(event.get("eventId") or "")
    if not _SHA256.fullmatch(event_id_seed):
        raise ValueError("tool outcome eventId must be a SHA-256 identity")
    recorded_ms = event.get("recordedAtEpochMs")
    if isinstance(recorded_ms, bool) or not isinstance(recorded_ms, int) or recorded_ms < 0:
        recorded_epoch = event.get("recordedAtEpoch")
        if isinstance(recorded_epoch, bool) or not isinstance(recorded_epoch, int) or recorded_epoch < 0:
            raise ValueError("tool outcome timestamp is invalid")
        recorded_ms = recorded_epoch * 1_000
    positive_outcome = event.get("positiveOutcome")
    if positive_outcome is not None and not isinstance(positive_outcome, bool):
        raise ValueError("tool outcome positiveOutcome must be boolean or null")
    safe_payload = {
        "schemaVersion": "sovereign.tool-outcome-projection.v1",
        "tool": tool,
        "observedAtEpochMs": recorded_ms,
        "durationMs": max(0, min(int(event.get("durationMs") or 0), 86_400_000)),
        "executionSuccess": bool(event.get("executionSuccess")),
        "positiveOutcome": positive_outcome,
        "status": _bounded(event.get("status"), 160),
        "failureFamily": _bounded(event.get("failureFamily"), 160),
        "missionFingerprint": _bounded(event.get("missionFingerprint"), 64),
        "recommended": bool(event.get("recommended")),
        "argumentValuesRecorded": False,
        "secretValuesRecorded": False,
    }
    event_time = datetime.fromtimestamp(recorded_ms // 1_000, tz=timezone.utc) + timedelta(
        milliseconds=recorded_ms % 1_000
    )
    new_hash = _sha256(safe_payload)
    event_id = f"tool.outcome.{event_id_seed}"
    revision_sha = _source_revision(event)
    expected_policy_sha256 = _policy_sha256()
    asserted_policy_sha256 = str(event.get("policySha256") or "").strip()
    if asserted_policy_sha256 and asserted_policy_sha256 != expected_policy_sha256:
        raise ValueError("tool outcome policy does not match the embedded continuity policy")
    policy_sha256 = expected_policy_sha256

    existing = _existing_event(_ledger_path(), event_id)
    if existing is not None:
        persisted = _nmc.ChangeEvent.from_dict(existing[0])
        receipt = _nmc.CandidateReceipt.from_dict(existing[1])
        if (
            persisted.kind != "tool.outcome"
            or persisted.source != "tool-success-ranking"
            or persisted.entity != f"tool.{tool.casefold()}"
            or persisted.field != "outcome"
            or persisted.identity.revision_sha != revision_sha
            or persisted.identity.policy_sha256 != policy_sha256
            or persisted.new_hash != new_hash
            or persisted.payload != safe_payload
        ):
            raise ValueError("tool outcome replay conflicts with persisted event")
        with _nmc.NeuromorphicLedger(_ledger_path()) as ledger:
            head = ledger.read_head("tool-success-ranking")
        if head is None or head.last_sequence < persisted.sequence:
            raise RuntimeError("tool outcome source head readback failed")
        return {
            "schemaVersion": "sovereign.tool-outcome-neuro-receipt.v1",
            "ok": True,
            "status": "TOOL_OUTCOME_NEURO_PROJECTED",
            "eventId": persisted.event_id,
            "eventHash": persisted.event_hash,
            "receiptHash": receipt.receipt_hash,
            "replayed": True,
            "sourceHeadReadback": True,
            "proposalOnly": True,
            "mayExecute": False,
            "autoExecute": False,
            "externalEffects": [],
            "mutationPerformed": False,
            "secretValuesReturned": False,
        }

    quota = _outcome_quota(_ledger_path())
    global_quota = _global_quota(_ledger_path())
    if quota["exceeded"] or global_quota["exceeded"]:
        raise RuntimeError("tool outcome neuro quota reached")
    _ensure_private_state_root()
    source_head = _read_source_head(_ledger_path(), "tool-success-ranking")
    ledger_tick = max(recorded_ms, int(source_head["lastTick"]))
    ledger_event_time = event_time
    if source_head["lastEventTime"] is not None:
        previous_time = datetime.fromisoformat(
            str(source_head["lastEventTime"]).replace("Z", "+00:00")
        )
        if ledger_event_time < previous_time:
            # Arrival order is authoritative for this source sequence.  Preserve
            # producer time in the payload while clamping ledger time so
            # concurrent completion callbacks cannot regress the durable lane.
            ledger_event_time = previous_time
    with _nmc.NeuromorphicLedger(_ledger_path()) as ledger:
        projection = ledger.read_projection("tool-success-ranking", f"tool.{tool.casefold()}", "outcome")
        old_hash = projection.value_hash if projection is not None else ZERO_SHA256
        neuro_event, receipt = ledger.ingest_next(
            event_id=event_id,
            system_id="sovereign-studio-ato",
            revision_sha=revision_sha,
            policy_sha256=policy_sha256,
            lane="sensory-intake",
            tick=ledger_tick,
            event_time=ledger_event_time,
            kind="tool.outcome",
            source="tool-success-ranking",
            entity=f"tool.{tool.casefold()}",
            field="outcome",
            old_hash=old_hash,
            new_hash=new_hash,
            magnitude=1,
            causal_parent_sha256=ZERO_SHA256,
            producer_identity="sovereign.tool-success-ranking",
            canonical=False,
            payload=safe_payload,
            gate=_nmc.RelevanceGate(default_threshold=1),
            quota=_nmc.LedgerQuota(
                max_events=int(global_quota["maxEvents"]),
                max_bytes=min(
                    int(global_quota["maxBytes"]),
                    int(quota["maxBytes"]),
                ),
                max_source_events=int(quota["maxEvents"]),
            ),
        )
        head = ledger.read_head("tool-success-ranking")
        if (
            head is None
            or head.last_event_id != neuro_event.event_id
            or head.last_event_hash != neuro_event.event_hash
            or head.last_sequence != neuro_event.sequence
        ):
            raise RuntimeError("tool outcome source head readback failed")
    return {
        "schemaVersion": "sovereign.tool-outcome-neuro-receipt.v1",
        "ok": True,
        "status": "TOOL_OUTCOME_NEURO_PROJECTED",
        "eventId": neuro_event.event_id,
        "eventHash": neuro_event.event_hash,
        "receiptHash": receipt.receipt_hash,
        "replayed": receipt.replayed,
        "sourceHeadReadback": True,
        "proposalOnly": True,
        "mayExecute": False,
        "autoExecute": False,
        "externalEffects": [],
        "mutationPerformed": not receipt.replayed,
        "secretValuesReturned": False,
    }


# These four contracts promise filesystem/ledger immutability.  The global
# success tracker is intentionally bypassed only for them; otherwise its JSONL
# ranking event and neuro outcome projection would contradict readOnlyHint.
for _read_only_tool in (
    neuro_runtime_contract_status,
    neuro_event_route_preview,
    teaching_package_assess,
    teaching_lesson_simulate,
):
    setattr(_read_only_tool, "__sovereign_success_tracking_opt_out__", True)


def register(mcp: Any, runtime: Any) -> None:
    """Register exactly five tools on the existing FastMCP instance."""

    global _MCP, _RUNTIME, _REGISTERED
    if _REGISTERED:
        return
    _MCP = mcp
    _RUNTIME = runtime
    mcp.tool(annotations=READ_ONLY)(neuro_runtime_contract_status)
    mcp.tool(annotations=READ_ONLY)(neuro_event_route_preview)
    mcp.tool(annotations=LOCAL_IDEMPOTENT_WRITE)(neuro_event_commit)
    mcp.tool(annotations=READ_ONLY)(teaching_package_assess)
    mcp.tool(annotations=READ_ONLY)(teaching_lesson_simulate)
    _REGISTERED = True


__all__ = [
    "NeuroTeachingOutput",
    "neuro_runtime_contract_status",
    "neuro_event_route_preview",
    "neuro_event_commit",
    "teaching_package_assess",
    "teaching_lesson_simulate",
    "record_tool_outcome_event",
    "register",
]
