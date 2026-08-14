"""Deterministic event/delta runtime for the Sovereign MCP control plane.

This module is a persistence and projection adapter for the canonical
``sovereign.neuro-architecture-envelope.v1`` contract.  It deliberately does
not define another event identity or authorize external effects.  A change
event binds its compact delta payload through the canonical envelope's
``payloadSha256`` and uses the envelope evidence hash as its append-only chain
identity.

The implementation is standard-library only.  SQLite is used in WAL mode with
``BEGIN IMMEDIATE`` transactions, database uniqueness constraints and an
in-process re-entrant lock.  All hot-path metrics and projections are updated
incrementally in the same transaction as the event append; no aggregate table
scan is needed for normal reads.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
from typing import Any, Iterator

from neuro_architecture_contract import EvidenceEnvelope, Lane


CHANGE_EVENT_SCHEMA_VERSION = "sovereign.change-event.v1"
CANDIDATE_RECEIPT_SCHEMA_VERSION = "sovereign.candidate-receipt.v1"
NEUROMORPHIC_LEDGER_SCHEMA_VERSION = "sovereign.neuromorphic-ledger.v1"
NEUROMORPHIC_SQLITE_USER_VERSION = 1
NEUROMORPHIC_SQLITE_APPLICATION_ID = 0x534F564E  # ASCII: SOVN
ZERO_SHA256 = "0" * 64

KNOWN_EVENT_KINDS = frozenset(
    {
        "capability.change",
        "deployment.change",
        "evidence.change",
        "foundation.decision",
        "health.change",
        "knowledge.change",
        "repository.change",
        "resource.change",
        "runtime.change",
        "sensor.change",
        "state.change",
        "tool.outcome",
        "tool.result",
    }
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_STABLE_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,159}$")
_MAX_CANONICAL_BYTES = 65_536
_MAX_JSON_DEPTH = 32
_MAX_JSON_ITEMS = 2_048
_MAX_WINDOW_SIZE = 512
_METRIC_NAMES = (
    "observed_events",
    "relevant_events",
    "discarded_events",
    "replay_requests",
    "projection_updates",
    "receipts_created",
)

_BASE_SCHEMA_SQL = {
    ("table", "ledger_metadata"): """
        CREATE TABLE ledger_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) STRICT
    """,
    ("table", "change_events"): """
        CREATE TABLE change_events (
            event_id TEXT PRIMARY KEY,
            event_hash TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK(sequence >= 0),
            tick INTEGER NOT NULL CHECK(tick >= 0),
            event_time TEXT NOT NULL,
            delta_ms INTEGER NOT NULL CHECK(delta_ms >= 0),
            previous_hash TEXT NOT NULL,
            kind TEXT NOT NULL,
            entity TEXT NOT NULL,
            field TEXT NOT NULL,
            relevant INTEGER NOT NULL CHECK(relevant IN (0, 1)),
            canonical_event TEXT NOT NULL,
            receipt_json TEXT NOT NULL,
            receipt_hash TEXT NOT NULL UNIQUE,
            UNIQUE(source, sequence)
        ) STRICT
    """,
    ("index", "change_events_temporal_idx"): """
        CREATE INDEX change_events_temporal_idx
        ON change_events(source, tick, sequence)
    """,
    ("table", "source_heads"): """
        CREATE TABLE source_heads (
            source TEXT PRIMARY KEY,
            last_sequence INTEGER NOT NULL CHECK(last_sequence >= 0),
            last_tick INTEGER NOT NULL CHECK(last_tick >= 0),
            last_event_time TEXT NOT NULL,
            last_event_hash TEXT NOT NULL,
            last_event_id TEXT NOT NULL,
            FOREIGN KEY(last_event_id) REFERENCES change_events(event_id)
        ) STRICT
    """,
    ("table", "projections"): """
        CREATE TABLE projections (
            source TEXT NOT NULL,
            entity TEXT NOT NULL,
            field TEXT NOT NULL,
            event_id TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            value_hash TEXT NOT NULL,
            tick INTEGER NOT NULL CHECK(tick >= 0),
            sequence INTEGER NOT NULL CHECK(sequence >= 0),
            event_time TEXT NOT NULL,
            PRIMARY KEY(source, entity, field),
            FOREIGN KEY(event_id) REFERENCES change_events(event_id)
        ) STRICT
    """,
    ("table", "ledger_metrics"): """
        CREATE TABLE ledger_metrics (
            name TEXT PRIMARY KEY,
            value INTEGER NOT NULL CHECK(value >= 0)
        ) STRICT
    """,
}

_ADMISSION_SCHEMA_SQL = """
    CREATE TABLE neuro_admissions (
        event_id TEXT PRIMARY KEY,
        event_hash TEXT NOT NULL,
        preview_sha256 TEXT NOT NULL,
        decision_sha256 TEXT NOT NULL,
        registry_sha256 TEXT NOT NULL,
        classification TEXT NOT NULL CHECK(classification IN ('candidate', 'discarded')),
        status TEXT NOT NULL CHECK(status IN ('pending', 'complete')),
        nmc_receipt_sha256 TEXT,
        foundation_evidence_sha256 TEXT,
        admission_receipt_sha256 TEXT UNIQUE
    ) STRICT
"""
_BASE_SCHEMA_SQL[("table", "neuro_admissions")] = _ADMISSION_SCHEMA_SQL


def _normalise_schema_sql(value: str) -> str:
    # SQLite preserves quoted CHECK literals.  Case-folding the whole statement
    # would incorrectly equate e.g. 'candidate' with the incompatible
    # 'CANDIDATE', so only insignificant whitespace is normalized here.
    return re.sub(r"\s+", " ", str(value or "").strip())


class NeuromorphicRuntimeError(RuntimeError):
    """Base error for durable runtime operations."""


class ContractError(ValueError):
    """A supplied event or query violates the versioned contract."""


class UnknownEventKindError(ContractError):
    """The router has no explicitly registered handler for an event kind."""


class ReplayConflictError(NeuromorphicRuntimeError):
    """An identity was replayed with different canonical content."""


class CrossSourceReplayError(ReplayConflictError):
    """An event identity already belongs to another source stream."""


class SequenceConflictError(NeuromorphicRuntimeError):
    """A sequence is duplicated, missing, or not the next source sequence."""


class TemporalOrderError(NeuromorphicRuntimeError):
    """Tick or event-time ordering regressed or delta time is inconsistent."""


class ChainIntegrityError(NeuromorphicRuntimeError):
    """Persisted content does not reproduce its canonical hash chain."""


class LedgerClosedError(NeuromorphicRuntimeError):
    """An operation was attempted after the ledger was closed."""


class LedgerReadOnlyError(NeuromorphicRuntimeError):
    """A mutation was attempted through a read-only ledger handle."""


class LedgerQuotaExceededError(NeuromorphicRuntimeError):
    """A transactional global/source ledger quota rejected a new event."""


def _normalise_json(value: Any, *, depth: int = 0) -> Any:
    """Return a JSON-only value while rejecting ambiguous numeric encodings."""

    if depth > _MAX_JSON_DEPTH:
        raise ContractError("canonical JSON exceeds maximum nesting depth")
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if not -(2**63) <= value <= 2**63 - 1:
            raise ContractError("canonical JSON integer exceeds signed 64-bit range")
        return value
    if isinstance(value, float):
        raise ContractError("canonical JSON requires integer/fixed-point values, not floats")
    if isinstance(value, Mapping):
        if len(value) > _MAX_JSON_ITEMS:
            raise ContractError("canonical JSON mapping exceeds item bound")
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ContractError("canonical JSON mapping keys must be strings")
            result[key] = _normalise_json(child, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > _MAX_JSON_ITEMS:
            raise ContractError("canonical JSON sequence exceeds item bound")
        return [_normalise_json(child, depth=depth + 1) for child in value]
    raise ContractError(f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Encode a bounded JSON value using the repository's canonical settings."""

    normalised = _normalise_json(value)
    encoded = json.dumps(
        normalised,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    if len(encoded.encode("utf-8")) > _MAX_CANONICAL_BYTES:
        raise ContractError("canonical JSON exceeds byte bound")
    return encoded


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ContractError(f"invalid {name}")
    return value


def _require_sha40(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA40.fullmatch(value):
        raise ContractError(f"invalid {name}")
    return value


def _require_stable_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _STABLE_ID.fullmatch(value):
        raise ContractError(f"invalid {name}")
    return value


def _require_non_negative_int(value: Any, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 2**63 - 1
    ):
        raise ContractError(f"{name} must be a non-negative signed 64-bit integer")
    return value


def _normalise_event_time(value: str | datetime) -> str:
    if isinstance(value, datetime):
        instant = value
    elif isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            raise ContractError("event_time must not be empty")
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            instant = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ContractError("event_time must be valid RFC3339") from exc
    else:
        raise ContractError("event_time must be an RFC3339 string or datetime")
    if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
        raise ContractError("event_time must carry an explicit UTC offset")
    instant = instant.astimezone(timezone.utc)
    if instant.microsecond % 1_000:
        raise ContractError("event_time precision must not exceed milliseconds")
    return instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_event_time(value: str) -> datetime:
    normalised = _normalise_event_time(value)
    return datetime.fromisoformat(normalised[:-1] + "+00:00")


def _elapsed_milliseconds(later: datetime, earlier: datetime) -> int:
    delta = later - earlier
    return delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000


def _strict_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    observed = frozenset(value)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise ContractError(f"invalid {label} fields; missing={missing}, extra={extra}")


@dataclass(frozen=True, slots=True)
class LedgerQuota:
    """Fail-closed append bounds evaluated inside the writer transaction."""

    max_events: int
    max_bytes: int
    max_source_events: int | None = None

    def __post_init__(self) -> None:
        _require_non_negative_int(self.max_events, "max_events")
        _require_non_negative_int(self.max_bytes, "max_bytes")
        if self.max_events < 1 or self.max_bytes < 1:
            raise ContractError("ledger quota limits must be positive")
        if self.max_source_events is not None:
            _require_non_negative_int(self.max_source_events, "max_source_events")
            if self.max_source_events < 1:
                raise ContractError("max_source_events must be positive")


@dataclass(frozen=True, slots=True)
class TemporalEnvelope:
    """Deterministic temporal identity; wall time is data, never ordering truth."""

    tick: int
    sequence: int
    event_time: str
    delta_ms: int

    def __post_init__(self) -> None:
        _require_non_negative_int(self.tick, "tick")
        _require_non_negative_int(self.sequence, "sequence")
        _require_non_negative_int(self.delta_ms, "delta_ms")
        object.__setattr__(self, "event_time", _normalise_event_time(self.event_time))

    @classmethod
    def create(
        cls,
        *,
        tick: int,
        sequence: int,
        event_time: str | datetime,
        delta_ms: int,
    ) -> "TemporalEnvelope":
        return cls(
            tick=tick,
            sequence=sequence,
            event_time=_normalise_event_time(event_time),
            delta_ms=delta_ms,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TemporalEnvelope":
        if not isinstance(value, Mapping):
            raise ContractError("temporal must be an object")
        _strict_keys(value, frozenset({"tick", "sequence", "eventTime", "deltaMs"}), "temporal")
        return cls(
            tick=value["tick"],
            sequence=value["sequence"],
            event_time=value["eventTime"],
            delta_ms=value["deltaMs"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "deltaMs": self.delta_ms,
            "eventTime": self.event_time,
            "sequence": self.sequence,
            "tick": self.tick,
        }


def _identity_from_dict(value: Mapping[str, Any]) -> EvidenceEnvelope:
    if not isinstance(value, Mapping):
        raise ContractError("envelope must be an object")
    expected = frozenset(
        {
            "canonical",
            "causalParentSha256",
            "eventId",
            "lane",
            "payloadSha256",
            "policySha256",
            "previousEvidenceSha256",
            "producerIdentity",
            "revisionSha",
            "schemaVersion",
            "sequence",
            "sideChannelReference",
            "systemId",
            "tick",
        }
    )
    _strict_keys(value, expected, "canonical envelope")
    if not isinstance(value["canonical"], bool):
        raise ContractError("canonical envelope canonical must be boolean")
    try:
        lane = Lane(value["lane"])
        return EvidenceEnvelope(
            schema_version=value["schemaVersion"],
            system_id=value["systemId"],
            revision_sha=value["revisionSha"],
            policy_sha256=value["policySha256"],
            event_id=value["eventId"],
            lane=lane,
            tick=_require_non_negative_int(value["tick"], "tick"),
            sequence=_require_non_negative_int(value["sequence"], "sequence"),
            payload_sha256=value["payloadSha256"],
            causal_parent_sha256=value["causalParentSha256"],
            previous_evidence_sha256=value["previousEvidenceSha256"],
            producer_identity=value["producerIdentity"],
            canonical=value["canonical"],
            side_channel_reference=value["sideChannelReference"],
        )
    except (TypeError, ValueError) as exc:
        raise ContractError(f"invalid canonical envelope: {exc}") from exc


def _change_payload_record(
    *,
    kind: str,
    source: str,
    entity: str,
    field: str,
    old_hash: str,
    new_hash: str,
    magnitude: int,
    temporal: TemporalEnvelope,
    payload_json: str,
) -> dict[str, Any]:
    return {
        "entity": entity,
        "field": field,
        "kind": kind,
        "magnitude": magnitude,
        "newHash": new_hash,
        "oldHash": old_hash,
        "payload": json.loads(payload_json),
        "schemaVersion": CHANGE_EVENT_SCHEMA_VERSION,
        "source": source,
        "temporal": temporal.to_dict(),
    }


@dataclass(frozen=True, slots=True)
class ChangeEvent:
    """A compact delta bound to the canonical neuro evidence envelope."""

    identity: EvidenceEnvelope
    temporal: TemporalEnvelope
    kind: str
    source: str
    entity: str
    field: str
    old_hash: str
    new_hash: str
    magnitude: int
    _payload_json: str

    def __post_init__(self) -> None:
        if self.kind not in KNOWN_EVENT_KINDS:
            raise UnknownEventKindError(f"unknown event kind: {self.kind!r}")
        _require_stable_id(self.source, "source")
        _require_stable_id(self.entity, "entity")
        _require_stable_id(self.field, "field")
        _require_sha256(self.old_hash, "old_hash")
        _require_sha256(self.new_hash, "new_hash")
        _require_non_negative_int(self.magnitude, "magnitude")
        if not isinstance(self._payload_json, str):
            raise ContractError("payload must be canonical JSON")
        try:
            payload = json.loads(self._payload_json)
        except json.JSONDecodeError as exc:
            raise ContractError("payload must be canonical JSON") from exc
        if not isinstance(payload, dict):
            raise ContractError("payload must be a JSON object")
        if canonical_json(payload) != self._payload_json:
            raise ContractError("payload JSON is not canonical")
        if self.temporal.tick != self.identity.tick:
            raise ContractError("temporal tick does not match canonical envelope")
        if self.temporal.sequence != self.identity.sequence:
            raise ContractError("temporal sequence does not match canonical envelope")
        expected_payload_hash = canonical_sha256(self._payload_record())
        if self.identity.payload_sha256 != expected_payload_hash:
            raise ContractError("canonical envelope payloadSha256 does not match ChangeEvent")

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        system_id: str,
        revision_sha: str,
        policy_sha256: str,
        lane: str | Lane,
        tick: int,
        sequence: int,
        event_time: str | datetime,
        delta_ms: int,
        kind: str,
        source: str,
        entity: str,
        field: str,
        old_hash: str,
        new_hash: str,
        magnitude: int,
        previous_evidence_sha256: str,
        causal_parent_sha256: str,
        producer_identity: str,
        canonical: bool,
        payload: Mapping[str, Any] | None = None,
        side_channel_reference: str = "",
    ) -> "ChangeEvent":
        if kind not in KNOWN_EVENT_KINDS:
            raise UnknownEventKindError(f"unknown event kind: {kind!r}")
        _require_stable_id(source, "source")
        _require_stable_id(entity, "entity")
        _require_stable_id(field, "field")
        _require_sha256(old_hash, "old_hash")
        _require_sha256(new_hash, "new_hash")
        _require_non_negative_int(magnitude, "magnitude")
        _require_non_negative_int(tick, "tick")
        _require_non_negative_int(sequence, "sequence")
        if not isinstance(canonical, bool):
            raise ContractError("canonical must be boolean")
        temporal = TemporalEnvelope.create(
            tick=tick,
            sequence=sequence,
            event_time=event_time,
            delta_ms=delta_ms,
        )
        payload_json = canonical_json(dict(payload or {}))
        payload_record = _change_payload_record(
            kind=kind,
            source=source,
            entity=entity,
            field=field,
            old_hash=old_hash,
            new_hash=new_hash,
            magnitude=magnitude,
            temporal=temporal,
            payload_json=payload_json,
        )
        try:
            identity = EvidenceEnvelope(
                schema_version="sovereign.neuro-architecture-envelope.v1",
                system_id=system_id,
                revision_sha=revision_sha,
                policy_sha256=policy_sha256,
                event_id=event_id,
                lane=Lane(lane),
                tick=tick,
                sequence=sequence,
                payload_sha256=canonical_sha256(payload_record),
                causal_parent_sha256=causal_parent_sha256,
                previous_evidence_sha256=previous_evidence_sha256,
                producer_identity=producer_identity,
                canonical=canonical,
                side_channel_reference=side_channel_reference,
            )
        except (TypeError, ValueError) as exc:
            raise ContractError(f"invalid canonical envelope: {exc}") from exc
        return cls(
            identity=identity,
            temporal=temporal,
            kind=kind,
            source=source,
            entity=entity,
            field=field,
            old_hash=old_hash,
            new_hash=new_hash,
            magnitude=magnitude,
            _payload_json=payload_json,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ChangeEvent":
        if not isinstance(value, Mapping):
            raise ContractError("ChangeEvent must be an object")
        expected = frozenset(
            {
                "schemaVersion",
                "envelope",
                "kind",
                "source",
                "entity",
                "field",
                "oldHash",
                "newHash",
                "magnitude",
                "temporal",
                "payload",
                "eventHash",
            }
        )
        _strict_keys(value, expected, "ChangeEvent")
        if value["schemaVersion"] != CHANGE_EVENT_SCHEMA_VERSION:
            raise ContractError("unsupported ChangeEvent schemaVersion")
        identity = _identity_from_dict(value["envelope"])
        temporal = TemporalEnvelope.from_dict(value["temporal"])
        payload = value["payload"]
        if not isinstance(payload, Mapping):
            raise ContractError("payload must be an object")
        event = cls(
            identity=identity,
            temporal=temporal,
            kind=value["kind"],
            source=value["source"],
            entity=value["entity"],
            field=value["field"],
            old_hash=value["oldHash"],
            new_hash=value["newHash"],
            magnitude=value["magnitude"],
            _payload_json=canonical_json(payload),
        )
        supplied_hash = _require_sha256(value["eventHash"], "eventHash")
        if supplied_hash != event.event_hash:
            raise ContractError("eventHash does not match canonical envelope")
        return event

    @property
    def event_id(self) -> str:
        return self.identity.event_id

    @property
    def event_hash(self) -> str:
        return self.identity.evidence_sha256()

    @property
    def previous_hash(self) -> str:
        return self.identity.previous_evidence_sha256

    @property
    def tick(self) -> int:
        return self.identity.tick

    @property
    def sequence(self) -> int:
        return self.identity.sequence

    @property
    def event_time(self) -> str:
        return self.temporal.event_time

    @property
    def delta_ms(self) -> int:
        return self.temporal.delta_ms

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self._payload_json)

    def _payload_record(self) -> dict[str, Any]:
        return _change_payload_record(
            kind=self.kind,
            source=self.source,
            entity=self.entity,
            field=self.field,
            old_hash=self.old_hash,
            new_hash=self.new_hash,
            magnitude=self.magnitude,
            temporal=self.temporal,
            payload_json=self._payload_json,
        )

    def to_dict(self) -> dict[str, Any]:
        record = self._payload_record()
        return {
            "entity": record["entity"],
            "envelope": dict(self.identity.canonical_record()),
            "eventHash": self.event_hash,
            "field": record["field"],
            "kind": record["kind"],
            "magnitude": record["magnitude"],
            "newHash": record["newHash"],
            "oldHash": record["oldHash"],
            "payload": record["payload"],
            "schemaVersion": CHANGE_EVENT_SCHEMA_VERSION,
            "source": record["source"],
            "temporal": record["temporal"],
        }

    def canonical_event_json(self) -> str:
        return canonical_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class DeltaObservation:
    old_hash: str
    new_hash: str
    magnitude: int
    changed: bool


class DeltaDetector:
    """Hash complete inputs once, then expose only their compact delta identity."""

    @staticmethod
    def detect(old_value: Any, new_value: Any, *, magnitude: int | None = None) -> DeltaObservation:
        old_hash = canonical_sha256(old_value)
        new_hash = canonical_sha256(new_value)
        changed = old_hash != new_hash
        if magnitude is None:
            if changed and all(isinstance(value, int) and not isinstance(value, bool) for value in (old_value, new_value)):
                magnitude = abs(new_value - old_value)
            else:
                magnitude = 1 if changed else 0
        _require_non_negative_int(magnitude, "magnitude")
        if not changed and magnitude != 0:
            raise ContractError("unchanged values must have zero magnitude")
        return DeltaObservation(
            old_hash=old_hash,
            new_hash=new_hash,
            magnitude=magnitude,
            changed=changed,
        )


@dataclass(frozen=True, slots=True)
class RelevanceDecision:
    relevant: bool
    reason: str
    threshold: int


class RelevanceGate:
    """Cheap deterministic capability gate; it never executes a candidate."""

    def __init__(
        self,
        *,
        default_threshold: int = 1,
        thresholds: Mapping[str, int] | None = None,
    ) -> None:
        self.default_threshold = _require_non_negative_int(default_threshold, "default_threshold")
        configured: dict[str, int] = {}
        for kind, threshold in (thresholds or {}).items():
            if kind not in KNOWN_EVENT_KINDS:
                raise UnknownEventKindError(f"unknown event kind in thresholds: {kind!r}")
            configured[kind] = _require_non_negative_int(threshold, f"threshold[{kind}]")
        self._thresholds = configured

    def evaluate(self, event: ChangeEvent) -> RelevanceDecision:
        if event.kind not in KNOWN_EVENT_KINDS:
            raise UnknownEventKindError(f"unknown event kind: {event.kind!r}")
        threshold = self._thresholds.get(event.kind, self.default_threshold)
        if event.old_hash == event.new_hash:
            return RelevanceDecision(False, "UNCHANGED_HASH", threshold)
        if event.magnitude < threshold:
            return RelevanceDecision(False, "BELOW_THRESHOLD", threshold)
        return RelevanceDecision(True, "THRESHOLD_MET", threshold)


@dataclass(frozen=True, slots=True)
class SpikeDecision:
    sensor_id: str
    tick: int
    input_magnitude: int
    potential_before_input: int
    potential_after_input: int
    retained_potential: int
    threshold: int
    spiked: bool
    uncertain: bool = True
    proposal_only: bool = True
    may_execute: bool = False
    external_effects: tuple[str, ...] = ()


class QuantizedSpikeFilter:
    """Bounded integer integrate/leak/fire sensor pre-filter.

    A spike is only an uncertain relevance proposal.  The filter has no
    persistence or effect adapter and cannot create canonical truth.
    """

    def __init__(
        self,
        *,
        threshold: int,
        leak_per_tick: int = 0,
        reset_potential: int = 0,
        max_potential: int = 2**31 - 1,
    ) -> None:
        self.threshold = _require_non_negative_int(threshold, "threshold")
        if self.threshold < 1:
            raise ContractError("threshold must be positive")
        self.leak_per_tick = _require_non_negative_int(leak_per_tick, "leak_per_tick")
        self.reset_potential = _require_non_negative_int(reset_potential, "reset_potential")
        self.max_potential = _require_non_negative_int(max_potential, "max_potential")
        if self.reset_potential >= self.threshold:
            raise ContractError("reset_potential must remain below threshold")
        if self.max_potential < self.threshold:
            raise ContractError("max_potential must cover threshold")
        self._states: dict[str, tuple[int, int]] = {}
        self._lock = threading.RLock()

    def observe(self, sensor_id: str, *, tick: int, magnitude: int) -> SpikeDecision:
        _require_stable_id(sensor_id, "sensor_id")
        _require_non_negative_int(tick, "tick")
        _require_non_negative_int(magnitude, "magnitude")
        with self._lock:
            previous = self._states.get(sensor_id)
            if previous is None:
                retained_before = 0
            else:
                previous_tick, previous_potential = previous
                if tick <= previous_tick:
                    raise TemporalOrderError("spike sensor tick must increase strictly")
                elapsed_ticks = tick - previous_tick
                leaked = min(previous_potential, self.leak_per_tick * elapsed_ticks)
                retained_before = previous_potential - leaked
            integrated = min(self.max_potential, retained_before + magnitude)
            spiked = integrated >= self.threshold
            retained_after = self.reset_potential if spiked else integrated
            self._states[sensor_id] = (tick, retained_after)
            return SpikeDecision(
                sensor_id=sensor_id,
                tick=tick,
                input_magnitude=magnitude,
                potential_before_input=retained_before,
                potential_after_input=integrated,
                retained_potential=retained_after,
                threshold=self.threshold,
                spiked=spiked,
            )

    def read_state(self, sensor_id: str) -> tuple[int, int] | None:
        _require_stable_id(sensor_id, "sensor_id")
        with self._lock:
            return self._states.get(sensor_id)


@dataclass(frozen=True, slots=True)
class ResourceRecommendation:
    queue_units: int
    active_workers: int
    target_workers: int
    pressure: str
    backpressure_recommended: bool
    reason: str
    advisory_only: bool = True
    may_execute: bool = False
    external_effects: tuple[str, ...] = ()


class ResourceHomeostat:
    """Pure bounded worker/backpressure recommendation with no actuator."""

    def __init__(
        self,
        *,
        units_per_worker: int,
        min_workers: int = 0,
        max_workers: int,
        max_adjustment: int = 1,
    ) -> None:
        self.units_per_worker = _require_non_negative_int(units_per_worker, "units_per_worker")
        self.min_workers = _require_non_negative_int(min_workers, "min_workers")
        self.max_workers = _require_non_negative_int(max_workers, "max_workers")
        self.max_adjustment = _require_non_negative_int(max_adjustment, "max_adjustment")
        if self.units_per_worker < 1:
            raise ContractError("units_per_worker must be positive")
        if self.max_workers < self.min_workers:
            raise ContractError("max_workers must not be below min_workers")
        if self.max_adjustment < 1:
            raise ContractError("max_adjustment must be positive")

    def recommend(self, *, queue_units: int, active_workers: int) -> ResourceRecommendation:
        queue_units = _require_non_negative_int(queue_units, "queue_units")
        active_workers = _require_non_negative_int(active_workers, "active_workers")
        if active_workers > self.max_workers:
            raise ContractError("active_workers exceeds configured maximum")
        required = (
            self.min_workers
            if queue_units == 0
            else max(self.min_workers, (queue_units + self.units_per_worker - 1) // self.units_per_worker)
        )
        bounded_required = min(self.max_workers, required)
        lower_step = max(self.min_workers, active_workers - self.max_adjustment)
        upper_step = min(self.max_workers, active_workers + self.max_adjustment)
        target = min(upper_step, max(lower_step, bounded_required))
        capacity = self.max_workers * self.units_per_worker
        backpressure = queue_units > capacity
        if backpressure:
            pressure = "saturated"
            reason = "QUEUE_EXCEEDS_MAX_CAPACITY"
        elif queue_units == 0:
            pressure = "idle"
            reason = "NO_QUEUED_WORK"
        elif target > active_workers:
            pressure = "high"
            reason = "BOUNDED_SCALE_UP_RECOMMENDATION"
        elif target < active_workers:
            pressure = "low"
            reason = "BOUNDED_SCALE_DOWN_RECOMMENDATION"
        else:
            pressure = "normal"
            reason = "CURRENT_CAPACITY_RECOMMENDED"
        return ResourceRecommendation(
            queue_units=queue_units,
            active_workers=active_workers,
            target_workers=target,
            pressure=pressure,
            backpressure_recommended=backpressure,
            reason=reason,
        )


@dataclass(frozen=True, slots=True)
class CandidateReceipt:
    """A durable routing candidate or discard receipt, never effect authority."""

    event_id: str
    event_hash: str
    source: str
    sequence: int
    decision: str
    relevant: bool
    reason: str
    threshold: int
    projection_updated: bool
    receipt_hash: str
    replayed: bool = False
    may_execute: bool = False
    external_effects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_stable_id(self.event_id, "event_id")
        _require_sha256(self.event_hash, "event_hash")
        _require_stable_id(self.source, "source")
        _require_non_negative_int(self.sequence, "sequence")
        if self.decision not in {"candidate", "discarded"}:
            raise ContractError("invalid candidate receipt decision")
        if not isinstance(self.relevant, bool):
            raise ContractError("candidate receipt relevant must be boolean")
        if self.relevant != (self.decision == "candidate"):
            raise ContractError("candidate receipt relevance contradicts decision")
        if not isinstance(self.reason, str) or not self.reason:
            raise ContractError("candidate receipt reason must not be empty")
        _require_non_negative_int(self.threshold, "threshold")
        _require_sha256(self.receipt_hash, "receipt_hash")
        if not isinstance(self.projection_updated, bool) or not isinstance(self.replayed, bool):
            raise ContractError("candidate receipt projection/replay fields must be boolean")
        if not isinstance(self.may_execute, bool):
            raise ContractError("candidate receipt may_execute must be boolean")
        if self.may_execute:
            raise ContractError("CandidateReceipt cannot authorize execution")
        if self.external_effects:
            raise ContractError("CandidateReceipt cannot contain external effects")
        if self.receipt_hash != canonical_sha256(self._hash_record()):
            raise ContractError("receiptHash does not match CandidateReceipt")

    @classmethod
    def create(
        cls,
        *,
        event: ChangeEvent,
        relevance: RelevanceDecision,
        projection_updated: bool,
    ) -> "CandidateReceipt":
        core = {
            "decision": "candidate" if relevance.relevant else "discarded",
            "eventHash": event.event_hash,
            "eventId": event.event_id,
            "externalEffects": [],
            "mayExecute": False,
            "projectionUpdated": projection_updated,
            "reason": relevance.reason,
            "relevant": relevance.relevant,
            "schemaVersion": CANDIDATE_RECEIPT_SCHEMA_VERSION,
            "sequence": event.sequence,
            "source": event.source,
            "threshold": relevance.threshold,
        }
        return cls(
            event_id=event.event_id,
            event_hash=event.event_hash,
            source=event.source,
            sequence=event.sequence,
            decision=core["decision"],
            relevant=relevance.relevant,
            reason=relevance.reason,
            threshold=relevance.threshold,
            projection_updated=projection_updated,
            may_execute=False,
            external_effects=(),
            receipt_hash=canonical_sha256(core),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CandidateReceipt":
        if not isinstance(value, Mapping):
            raise ContractError("CandidateReceipt must be an object")
        expected = frozenset(
            {
                "schemaVersion",
                "eventId",
                "eventHash",
                "source",
                "sequence",
                "decision",
                "relevant",
                "reason",
                "threshold",
                "projectionUpdated",
                "mayExecute",
                "externalEffects",
                "receiptHash",
                "replayed",
            }
        )
        _strict_keys(value, expected, "CandidateReceipt")
        if value["schemaVersion"] != CANDIDATE_RECEIPT_SCHEMA_VERSION:
            raise ContractError("unsupported CandidateReceipt schemaVersion")
        effects = value["externalEffects"]
        if not isinstance(effects, list) or any(not isinstance(item, str) for item in effects):
            raise ContractError("externalEffects must be a string list")
        return cls(
            event_id=value["eventId"],
            event_hash=value["eventHash"],
            source=value["source"],
            sequence=value["sequence"],
            decision=value["decision"],
            relevant=value["relevant"],
            reason=value["reason"],
            threshold=value["threshold"],
            projection_updated=value["projectionUpdated"],
            receipt_hash=value["receiptHash"],
            replayed=value["replayed"],
            may_execute=value["mayExecute"],
            external_effects=tuple(effects),
        )

    def _hash_record(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "eventHash": self.event_hash,
            "eventId": self.event_id,
            "externalEffects": list(self.external_effects),
            "mayExecute": self.may_execute,
            "projectionUpdated": self.projection_updated,
            "reason": self.reason,
            "relevant": self.relevant,
            "schemaVersion": CANDIDATE_RECEIPT_SCHEMA_VERSION,
            "sequence": self.sequence,
            "source": self.source,
            "threshold": self.threshold,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._hash_record(),
            "receiptHash": self.receipt_hash,
            "replayed": self.replayed,
        }


@dataclass(frozen=True, slots=True)
class ProjectionState:
    source: str
    entity: str
    field: str
    event_id: str
    event_hash: str
    value_hash: str
    tick: int
    sequence: int
    event_time: str


@dataclass(frozen=True, slots=True)
class SourceHead:
    source: str
    last_sequence: int
    last_tick: int
    last_event_time: str
    last_event_hash: str
    last_event_id: str


@dataclass(frozen=True, slots=True)
class LedgerMetrics:
    observed_events: int
    relevant_events: int
    discarded_events: int
    replay_requests: int
    projection_updates: int
    receipts_created: int

    @property
    def reduction_rate_ppm(self) -> int:
        if self.observed_events == 0:
            return 0
        return (self.discarded_events * 1_000_000) // self.observed_events


@dataclass(frozen=True, slots=True)
class TemporalWindow:
    source: str
    start_tick: int
    end_tick: int
    events: tuple[ChangeEvent, ...]
    window_hash: str

    def recompute_hash(self) -> str:
        return canonical_sha256(
            {
                "endTick": self.end_tick,
                "eventHashes": [event.event_hash for event in self.events],
                "source": self.source,
                "startTick": self.start_tick,
            }
        )


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    ok: bool
    event_count: int
    source_count: int
    heads: tuple[tuple[str, str], ...]


def _guarded_database_descriptor(path: Path, *, writable: bool, create: bool) -> tuple[int, int]:
    """Open the state-root and DB basename without following either symlink."""

    try:
        parent_status = os.lstat(path.parent)
    except OSError as exc:
        raise ContractError("neuromorphic ledger parent is unavailable") from exc
    if stat.S_ISLNK(parent_status.st_mode) or not stat.S_ISDIR(parent_status.st_mode):
        raise ContractError("neuromorphic ledger parent must be a non-symlink directory")
    parent_flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        parent_flags |= os.O_NOFOLLOW
    file_flags = os.O_RDWR if writable else os.O_RDONLY
    if create:
        file_flags |= os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        file_flags |= os.O_NOFOLLOW
    parent_descriptor = os.open(path.parent, parent_flags)
    try:
        file_descriptor = os.open(path.name, file_flags, 0o600, dir_fd=parent_descriptor)
    except OSError as exc:
        os.close(parent_descriptor)
        raise ContractError(
            "neuromorphic ledger path must be an available non-symlink regular file"
        ) from exc
    if not stat.S_ISREG(os.fstat(file_descriptor).st_mode):
        os.close(file_descriptor)
        os.close(parent_descriptor)
        raise ContractError("neuromorphic ledger path must be a non-symlink regular file")
    return parent_descriptor, file_descriptor


class NeuromorphicLedger:
    """Thread-safe, append-only SQLite-WAL event ledger and projections."""

    def __init__(self, database_path: str | os.PathLike[str], *, max_window_size: int = _MAX_WINDOW_SIZE) -> None:
        raw_path = os.fspath(database_path)
        if raw_path == ":memory:" or raw_path.startswith("file:"):
            raise ContractError("NeuromorphicLedger requires a filesystem SQLite database for WAL")
        self._path = Path(raw_path).absolute()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._max_window_size = _require_non_negative_int(max_window_size, "max_window_size")
        if self._max_window_size < 1 or self._max_window_size > _MAX_WINDOW_SIZE:
            raise ContractError(f"max_window_size must be between 1 and {_MAX_WINDOW_SIZE}")
        self._lock = threading.RLock()
        self._closed = False
        self._read_only = False
        parent_descriptor, file_descriptor = _guarded_database_descriptor(
            self._path, writable=True, create=True
        )
        guarded_identity = os.fstat(file_descriptor)
        connection_opened = False
        try:
            fcntl.flock(file_descriptor, fcntl.LOCK_EX)
            self._connection = sqlite3.connect(
                self._path,
                timeout=30.0,
                isolation_level=None,
                check_same_thread=False,
            )
            connection_opened = True
            observed_identity = os.lstat(self._path)
            if (
                stat.S_ISLNK(observed_identity.st_mode)
                or observed_identity.st_dev != guarded_identity.st_dev
                or observed_identity.st_ino != guarded_identity.st_ino
            ):
                raise ContractError("neuromorphic ledger inode changed during open")
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._connection.execute("PRAGMA busy_timeout=30000")
            mode = str(self._connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
            if mode != "wal":
                raise NeuromorphicRuntimeError(f"SQLite WAL mode unavailable: {mode}")
            self._journal_mode = mode
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.execute("PRAGMA trusted_schema=OFF")
            self._initialise_schema()
            os.fchmod(file_descriptor, 0o600)
        except BaseException:
            if connection_opened:
                self._connection.close()
            self._closed = True
            raise
        finally:
            try:
                fcntl.flock(file_descriptor, fcntl.LOCK_UN)
            finally:
                os.close(file_descriptor)
                os.close(parent_descriptor)

    @classmethod
    def open_read_only(
        cls,
        database_path: str | os.PathLike[str],
        *,
        max_window_size: int = _MAX_WINDOW_SIZE,
    ) -> "NeuromorphicLedger":
        """Open an existing ledger without initializing or mutating its files.

        The returned handle uses SQLite URI ``mode=ro`` and ``query_only``.  It
        intentionally bypasses ``__init__`` so it never creates a parent
        directory, switches journal mode, creates schema, updates metadata, or
        changes file permissions.  All existing read APIs, including the full
        projection/metrics-aware ``verify_integrity``, remain available.
        """

        raw_path = os.fspath(database_path)
        if raw_path == ":memory:" or raw_path.startswith("file:"):
            raise ContractError("read-only ledger requires a filesystem database path")
        path = Path(raw_path).absolute()
        checked_window_size = _require_non_negative_int(max_window_size, "max_window_size")
        if checked_window_size < 1 or checked_window_size > _MAX_WINDOW_SIZE:
            raise ContractError(f"max_window_size must be between 1 and {_MAX_WINDOW_SIZE}")

        instance = cls.__new__(cls)
        instance._path = path
        instance._max_window_size = checked_window_size
        instance._lock = threading.RLock()
        instance._closed = False
        instance._read_only = True
        parent_descriptor, file_descriptor = _guarded_database_descriptor(
            path, writable=False, create=False
        )
        guarded_identity = os.fstat(file_descriptor)
        connection_opened = False
        try:
            fcntl.flock(file_descriptor, fcntl.LOCK_SH)
            instance._connection = sqlite3.connect(
                f"{path.as_uri()}?mode=ro",
                uri=True,
                timeout=30.0,
                isolation_level=None,
                check_same_thread=False,
            )
            connection_opened = True
            observed_identity = os.lstat(path)
            if (
                stat.S_ISLNK(observed_identity.st_mode)
                or observed_identity.st_dev != guarded_identity.st_dev
                or observed_identity.st_ino != guarded_identity.st_ino
            ):
                raise ContractError("read-only ledger inode changed during open")
            instance._connection.row_factory = sqlite3.Row
            instance._connection.execute("PRAGMA query_only=ON")
            instance._connection.execute("PRAGMA foreign_keys=ON")
            instance._connection.execute("PRAGMA busy_timeout=30000")
            instance._connection.execute("PRAGMA trusted_schema=OFF")
            query_only = int(instance._connection.execute("PRAGMA query_only").fetchone()[0])
            if query_only != 1:
                raise NeuromorphicRuntimeError("SQLite query_only mode unavailable")
            mode = str(instance._connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            if mode != "wal":
                raise NeuromorphicRuntimeError(f"persisted ledger is not in WAL mode: {mode}")
            instance._journal_mode = mode
            instance._verify_schema_identity()
        except BaseException:
            if connection_opened:
                instance._connection.close()
            instance._closed = True
            raise
        finally:
            try:
                fcntl.flock(file_descriptor, fcntl.LOCK_UN)
            finally:
                os.close(file_descriptor)
                os.close(parent_descriptor)
        return instance

    @property
    def journal_mode(self) -> str:
        return self._journal_mode

    @property
    def read_only(self) -> bool:
        return self._read_only

    @staticmethod
    def _pragma_int(connection: sqlite3.Connection, name: str) -> int:
        row = connection.execute(f"PRAGMA {name}").fetchone()
        if row is None:
            raise NeuromorphicRuntimeError(f"SQLite did not report {name}")
        return int(row[0])

    @staticmethod
    def _table_shape(
        connection: sqlite3.Connection, table: str
    ) -> tuple[tuple[str, str, int, int], ...]:
        return tuple(
            (str(row[1]), str(row[2]).upper(), int(row[3]), int(row[5]))
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        )

    def _verify_schema_identity(self) -> None:
        connection = self._connection
        if self._pragma_int(connection, "application_id") != NEUROMORPHIC_SQLITE_APPLICATION_ID:
            raise NeuromorphicRuntimeError("neuromorphic ledger application identity mismatch")
        if self._pragma_int(connection, "user_version") != NEUROMORPHIC_SQLITE_USER_VERSION:
            raise NeuromorphicRuntimeError("neuromorphic ledger schema version mismatch")
        if self._pragma_int(connection, "trusted_schema") != 0:
            raise NeuromorphicRuntimeError("neuromorphic ledger trusted_schema is not disabled")
        if self._pragma_int(connection, "foreign_keys") != 1:
            raise NeuromorphicRuntimeError("neuromorphic ledger foreign keys are disabled")

        rows = connection.execute(
            """
            SELECT type, name, sql FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()
        actual_sql = {
            (str(row["type"]), str(row["name"])): _normalise_schema_sql(str(row["sql"] or ""))
            for row in rows
        }
        expected_sql = {
            identity: _normalise_schema_sql(sql)
            for identity, sql in _BASE_SCHEMA_SQL.items()
        }
        base_objects = set(expected_sql)
        if set(actual_sql) != base_objects:
            raise NeuromorphicRuntimeError("neuromorphic ledger object identity mismatch")
        if actual_sql != expected_sql:
            raise NeuromorphicRuntimeError("neuromorphic ledger SQL schema mismatch")

        expected_shapes = {
            "ledger_metadata": (("key", "TEXT", 1, 1), ("value", "TEXT", 1, 0)),
            "change_events": (
                ("event_id", "TEXT", 1, 1),
                ("event_hash", "TEXT", 1, 0),
                ("source", "TEXT", 1, 0),
                ("sequence", "INTEGER", 1, 0),
                ("tick", "INTEGER", 1, 0),
                ("event_time", "TEXT", 1, 0),
                ("delta_ms", "INTEGER", 1, 0),
                ("previous_hash", "TEXT", 1, 0),
                ("kind", "TEXT", 1, 0),
                ("entity", "TEXT", 1, 0),
                ("field", "TEXT", 1, 0),
                ("relevant", "INTEGER", 1, 0),
                ("canonical_event", "TEXT", 1, 0),
                ("receipt_json", "TEXT", 1, 0),
                ("receipt_hash", "TEXT", 1, 0),
            ),
            "source_heads": (
                ("source", "TEXT", 1, 1),
                ("last_sequence", "INTEGER", 1, 0),
                ("last_tick", "INTEGER", 1, 0),
                ("last_event_time", "TEXT", 1, 0),
                ("last_event_hash", "TEXT", 1, 0),
                ("last_event_id", "TEXT", 1, 0),
            ),
            "projections": (
                ("source", "TEXT", 1, 1),
                ("entity", "TEXT", 1, 2),
                ("field", "TEXT", 1, 3),
                ("event_id", "TEXT", 1, 0),
                ("event_hash", "TEXT", 1, 0),
                ("value_hash", "TEXT", 1, 0),
                ("tick", "INTEGER", 1, 0),
                ("sequence", "INTEGER", 1, 0),
                ("event_time", "TEXT", 1, 0),
            ),
            "ledger_metrics": (("name", "TEXT", 1, 1), ("value", "INTEGER", 1, 0)),
        }
        expected_shapes["neuro_admissions"] = (
            ("event_id", "TEXT", 1, 1),
            ("event_hash", "TEXT", 1, 0),
            ("preview_sha256", "TEXT", 1, 0),
            ("decision_sha256", "TEXT", 1, 0),
            ("registry_sha256", "TEXT", 1, 0),
            ("classification", "TEXT", 1, 0),
            ("status", "TEXT", 1, 0),
            ("nmc_receipt_sha256", "TEXT", 0, 0),
            ("foundation_evidence_sha256", "TEXT", 0, 0),
            ("admission_receipt_sha256", "TEXT", 0, 0),
        )
        for table, expected in expected_shapes.items():
            if self._table_shape(connection, table) != expected:
                raise NeuromorphicRuntimeError(
                    f"neuromorphic ledger table shape mismatch: {table}"
                )

        metadata = connection.execute(
            "SELECT key, value FROM ledger_metadata ORDER BY key"
        ).fetchall()
        if [(row["key"], row["value"]) for row in metadata] != [
            ("schema_version", NEUROMORPHIC_LEDGER_SCHEMA_VERSION)
        ]:
            raise NeuromorphicRuntimeError("neuromorphic ledger metadata identity mismatch")
        metric_names = tuple(
            row["name"]
            for row in connection.execute("SELECT name FROM ledger_metrics ORDER BY name").fetchall()
        )
        if metric_names != tuple(sorted(_METRIC_NAMES)):
            raise NeuromorphicRuntimeError("neuromorphic ledger metric identity mismatch")

    def _initialise_schema(self) -> None:
        application_id = self._pragma_int(self._connection, "application_id")
        user_version = self._pragma_int(self._connection, "user_version")
        objects = self._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1"
        ).fetchone()
        if application_id == NEUROMORPHIC_SQLITE_APPLICATION_ID:
            self._verify_schema_identity()
            return
        if application_id != 0 or user_version != 0 or objects is not None:
            raise NeuromorphicRuntimeError("unrecognized neuromorphic ledger cannot be initialized")

        self._connection.execute("BEGIN IMMEDIATE")
        try:
            locked_application_id = self._pragma_int(self._connection, "application_id")
            locked_user_version = self._pragma_int(self._connection, "user_version")
            locked_objects = self._connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1"
            ).fetchone()
            if locked_application_id == NEUROMORPHIC_SQLITE_APPLICATION_ID:
                self._connection.execute("COMMIT")
                self._verify_schema_identity()
                return
            if locked_application_id != 0 or locked_user_version != 0 or locked_objects is not None:
                raise NeuromorphicRuntimeError(
                    "neuromorphic ledger identity changed during initialization"
                )
            for sql in _BASE_SCHEMA_SQL.values():
                self._connection.execute(sql)
            self._connection.execute(
                "INSERT INTO ledger_metadata(key, value) VALUES('schema_version', ?)",
                (NEUROMORPHIC_LEDGER_SCHEMA_VERSION,),
            )
            for name in _METRIC_NAMES:
                self._connection.execute(
                    "INSERT INTO ledger_metrics(name, value) VALUES(?, 0)", (name,)
                )
            self._connection.execute(
                f"PRAGMA application_id={NEUROMORPHIC_SQLITE_APPLICATION_ID}"
            )
            self._connection.execute(
                f"PRAGMA user_version={NEUROMORPHIC_SQLITE_USER_VERSION}"
            )
            self._connection.execute("COMMIT")
        except BaseException:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise
        self._verify_schema_identity()

    def _ensure_open(self) -> None:
        if self._closed:
            raise LedgerClosedError("neuromorphic ledger is closed")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._ensure_open()
            if self._read_only:
                raise LedgerReadOnlyError("neuromorphic ledger is read-only")
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._verify_schema_identity()
                yield self._connection
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            else:
                self._connection.execute("COMMIT")

    @staticmethod
    def _increment(connection: sqlite3.Connection, name: str, amount: int = 1) -> None:
        if name not in _METRIC_NAMES or amount < 0:
            raise NeuromorphicRuntimeError("invalid incremental metric update")
        cursor = connection.execute(
            "UPDATE ledger_metrics SET value = value + ? WHERE name = ?",
            (amount, name),
        )
        if cursor.rowcount != 1:
            raise NeuromorphicRuntimeError(f"missing incremental metric: {name}")

    def _database_family_bytes(self) -> int:
        family = (
            self._path,
            Path(str(self._path) + "-wal"),
            Path(str(self._path) + "-shm"),
        )
        return sum(path.stat().st_size for path in family if path.is_file())

    def _enforce_append_quota(
        self,
        connection: sqlite3.Connection,
        *,
        event: ChangeEvent,
        canonical_event: str,
        receipt_json: str,
        quota: LedgerQuota | None,
    ) -> None:
        if quota is None:
            return
        if not isinstance(quota, LedgerQuota):
            raise ContractError("quota must be a LedgerQuota")
        total_events = int(connection.execute("SELECT COUNT(*) FROM change_events").fetchone()[0])
        if total_events >= quota.max_events:
            raise LedgerQuotaExceededError("global event quota reached")
        if quota.max_source_events is not None:
            source_events = int(
                connection.execute(
                    "SELECT COUNT(*) FROM change_events WHERE source=?",
                    (event.source,),
                ).fetchone()[0]
            )
            if source_events >= quota.max_source_events:
                raise LedgerQuotaExceededError("source event quota reached")

        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        encoded_bytes = len(canonical_event.encode("utf-8")) + len(receipt_json.encode("utf-8"))
        # Reserve index, head, projection and metrics pages conservatively.  It
        # is intentionally an upper-bound admission check, not a prediction of
        # SQLite's allocator. BEGIN IMMEDIATE makes this check global across
        # connections/processes and the insert either consumes the reservation
        # or rolls back with it.
        append_reservation = max(page_size * 16, encoded_bytes * 2)
        if self._database_family_bytes() + append_reservation > quota.max_bytes:
            raise LedgerQuotaExceededError("global byte quota reached")

    @staticmethod
    def _receipt_from_row(row: sqlite3.Row) -> CandidateReceipt:
        try:
            value = json.loads(row["receipt_json"])
            return CandidateReceipt.from_dict(value)
        except (json.JSONDecodeError, ContractError, TypeError) as exc:
            raise ChainIntegrityError(f"invalid persisted receipt for {row['event_id']}") from exc

    def ingest(
        self,
        event: ChangeEvent,
        gate: RelevanceGate | None = None,
        *,
        quota: LedgerQuota | None = None,
    ) -> CandidateReceipt:
        with self._transaction() as connection:
            return self._ingest_in_transaction(connection, event, gate, quota=quota)

    def _ingest_in_transaction(
        self,
        connection: sqlite3.Connection,
        event: ChangeEvent,
        gate: RelevanceGate | None = None,
        *,
        quota: LedgerQuota | None = None,
    ) -> CandidateReceipt:
        if not isinstance(event, ChangeEvent):
            raise ContractError("ingest requires a ChangeEvent")
        if connection is not self._connection or not connection.in_transaction:
            raise NeuromorphicRuntimeError("event append requires the active ledger transaction")
        relevance = (gate or RelevanceGate()).evaluate(event)
        canonical_event = event.canonical_event_json()

        if connection.in_transaction:
            existing = connection.execute(
                "SELECT event_id, event_hash, source, canonical_event, receipt_json FROM change_events WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()
            if existing is not None:
                if existing["source"] != event.source:
                    raise CrossSourceReplayError(
                        f"event_id {event.event_id!r} already belongs to source {existing['source']!r}"
                    )
                if existing["event_hash"] != event.event_hash or existing["canonical_event"] != canonical_event:
                    raise ReplayConflictError(f"event_id {event.event_id!r} was replayed with different content")
                self._increment(connection, "replay_requests")
                return replace(self._receipt_from_row(existing), replayed=True)

            sequence_owner = connection.execute(
                "SELECT event_id FROM change_events WHERE source = ? AND sequence = ?",
                (event.source, event.sequence),
            ).fetchone()
            if sequence_owner is not None:
                raise SequenceConflictError(
                    f"source sequence already belongs to event {sequence_owner['event_id']!r}"
                )

            hash_owner = connection.execute(
                "SELECT event_id, source FROM change_events WHERE event_hash = ?",
                (event.event_hash,),
            ).fetchone()
            if hash_owner is not None:
                if hash_owner["source"] != event.source:
                    raise CrossSourceReplayError("event hash cannot be reused across source streams")
                raise ReplayConflictError("event hash already belongs to another event identity")

            head = connection.execute(
                "SELECT last_sequence, last_tick, last_event_time, last_event_hash FROM source_heads WHERE source = ?",
                (event.source,),
            ).fetchone()
            if head is None:
                if event.sequence != 0:
                    raise SequenceConflictError("first source event sequence must be zero")
                if event.previous_hash != ZERO_SHA256:
                    raise ChainIntegrityError("first source event must bind the zero predecessor hash")
                if event.delta_ms != 0:
                    raise TemporalOrderError("first source event delta_ms must be zero")
            else:
                expected_sequence = int(head["last_sequence"]) + 1
                if event.sequence != expected_sequence:
                    raise SequenceConflictError(
                        f"expected source sequence {expected_sequence}, received {event.sequence}"
                    )
                if event.previous_hash != head["last_event_hash"]:
                    raise ChainIntegrityError("previousEvidenceSha256 does not match source head")
                if event.tick < int(head["last_tick"]):
                    raise TemporalOrderError("tick regression")
                elapsed_ms = _elapsed_milliseconds(
                    _parse_event_time(event.event_time),
                    _parse_event_time(head["last_event_time"]),
                )
                if elapsed_ms < 0:
                    raise TemporalOrderError("event_time regression")
                if event.delta_ms != elapsed_ms:
                    raise TemporalOrderError(
                        f"delta_ms mismatch: expected {elapsed_ms}, received {event.delta_ms}"
                    )

            projection_updated = relevance.relevant
            receipt = CandidateReceipt.create(
                event=event,
                relevance=relevance,
                projection_updated=projection_updated,
            )
            receipt_json = canonical_json(receipt.to_dict())
            self._enforce_append_quota(
                connection,
                event=event,
                canonical_event=canonical_event,
                receipt_json=receipt_json,
                quota=quota,
            )
            try:
                connection.execute(
                    """
                    INSERT INTO change_events(
                        event_id, event_hash, source, sequence, tick, event_time, delta_ms,
                        previous_hash, kind, entity, field, relevant, canonical_event,
                        receipt_json, receipt_hash
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.event_hash,
                        event.source,
                        event.sequence,
                        event.tick,
                        event.event_time,
                        event.delta_ms,
                        event.previous_hash,
                        event.kind,
                        event.entity,
                        event.field,
                        int(relevance.relevant),
                        canonical_event,
                        receipt_json,
                        receipt.receipt_hash,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO source_heads(
                        source, last_sequence, last_tick, last_event_time, last_event_hash, last_event_id
                    ) VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source) DO UPDATE SET
                        last_sequence=excluded.last_sequence,
                        last_tick=excluded.last_tick,
                        last_event_time=excluded.last_event_time,
                        last_event_hash=excluded.last_event_hash,
                        last_event_id=excluded.last_event_id
                    """,
                    (
                        event.source,
                        event.sequence,
                        event.tick,
                        event.event_time,
                        event.event_hash,
                        event.event_id,
                    ),
                )
                if projection_updated:
                    connection.execute(
                        """
                        INSERT INTO projections(
                            source, entity, field, event_id, event_hash, value_hash,
                            tick, sequence, event_time
                        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(source, entity, field) DO UPDATE SET
                            event_id=excluded.event_id,
                            event_hash=excluded.event_hash,
                            value_hash=excluded.value_hash,
                            tick=excluded.tick,
                            sequence=excluded.sequence,
                            event_time=excluded.event_time
                        """,
                        (
                            event.source,
                            event.entity,
                            event.field,
                            event.event_id,
                            event.event_hash,
                            event.new_hash,
                            event.tick,
                            event.sequence,
                            event.event_time,
                        ),
                    )
            except sqlite3.IntegrityError as exc:
                raise NeuromorphicRuntimeError(f"atomic event append rejected: {exc}") from exc

            self._increment(connection, "observed_events")
            self._increment(connection, "receipts_created")
            if relevance.relevant:
                self._increment(connection, "relevant_events")
                self._increment(connection, "projection_updates")
            else:
                self._increment(connection, "discarded_events")
            return receipt

    def ingest_next(
        self,
        *,
        event_id: str,
        system_id: str,
        revision_sha: str,
        policy_sha256: str,
        lane: str | Lane,
        tick: int,
        event_time: str | datetime,
        kind: str,
        source: str,
        entity: str,
        field: str,
        old_hash: str,
        new_hash: str,
        magnitude: int,
        causal_parent_sha256: str,
        producer_identity: str,
        canonical: bool,
        payload: Mapping[str, Any] | None = None,
        side_channel_reference: str = "",
        gate: RelevanceGate | None = None,
        quota: LedgerQuota | None = None,
    ) -> tuple[ChangeEvent, CandidateReceipt]:
        """Allocate the next source sequence/head and append in one transaction.

        Callers that receive unordered events (for example tool-outcome
        adapters) must use this method rather than reading a head and composing
        a sequence outside the transaction.  ``tick`` remains producer data and
        is never synthesized by the ledger.
        """

        _require_stable_id(event_id, "event_id")
        _require_stable_id(system_id, "system_id")
        _require_sha40(revision_sha, "revision_sha")
        _require_sha256(policy_sha256, "policy_sha256")
        _require_non_negative_int(tick, "tick")
        if kind not in KNOWN_EVENT_KINDS:
            raise UnknownEventKindError(f"unknown event kind: {kind!r}")
        _require_stable_id(source, "source")
        _require_stable_id(entity, "entity")
        _require_stable_id(field, "field")
        _require_sha256(old_hash, "old_hash")
        _require_sha256(new_hash, "new_hash")
        _require_non_negative_int(magnitude, "magnitude")
        _require_sha256(causal_parent_sha256, "causal_parent_sha256")
        if not isinstance(producer_identity, str) or not producer_identity.strip():
            raise ContractError("producer_identity must not be empty")
        if not isinstance(canonical, bool):
            raise ContractError("canonical must be boolean")
        if not isinstance(side_channel_reference, str):
            raise ContractError("side_channel_reference must be a string")
        try:
            lane_value = Lane(lane)
        except ValueError as exc:
            raise ContractError("invalid lane") from exc
        normalised_time = _normalise_event_time(event_time)
        payload_value = dict(payload or {})
        payload_json = canonical_json(payload_value)

        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT canonical_event FROM change_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if existing is not None:
                try:
                    existing_event = ChangeEvent.from_dict(json.loads(existing["canonical_event"]))
                except (json.JSONDecodeError, ContractError, TypeError) as exc:
                    raise ChainIntegrityError(f"invalid persisted event for {event_id}") from exc
                if existing_event.source != source:
                    raise CrossSourceReplayError(
                        f"event_id {event_id!r} already belongs to source {existing_event.source!r}"
                    )
                replay_fields_match = all(
                    (
                        existing_event.identity.system_id == system_id,
                        existing_event.identity.revision_sha == revision_sha,
                        existing_event.identity.policy_sha256 == policy_sha256,
                        existing_event.identity.lane == lane_value,
                        existing_event.tick == tick,
                        existing_event.event_time == normalised_time,
                        existing_event.kind == kind,
                        existing_event.entity == entity,
                        existing_event.field == field,
                        existing_event.old_hash == old_hash,
                        existing_event.new_hash == new_hash,
                        existing_event.magnitude == magnitude,
                        existing_event.identity.causal_parent_sha256 == causal_parent_sha256,
                        existing_event.identity.producer_identity == producer_identity,
                        existing_event.identity.canonical == canonical,
                        existing_event.identity.side_channel_reference == side_channel_reference,
                        existing_event._payload_json == payload_json,
                    )
                )
                if not replay_fields_match:
                    raise ReplayConflictError(
                        f"event_id {event_id!r} was replayed with different next-event content"
                    )
                return existing_event, self._ingest_in_transaction(
                    connection, existing_event, gate, quota=quota
                )

            head = connection.execute(
                """
                SELECT last_sequence, last_tick, last_event_time, last_event_hash
                FROM source_heads WHERE source = ?
                """,
                (source,),
            ).fetchone()
            if head is None:
                sequence = 0
                previous_hash = ZERO_SHA256
                delta_ms = 0
            else:
                sequence = int(head["last_sequence"]) + 1
                previous_hash = head["last_event_hash"]
                delta_ms = _elapsed_milliseconds(
                    _parse_event_time(normalised_time),
                    _parse_event_time(head["last_event_time"]),
                )
                if delta_ms < 0:
                    raise TemporalOrderError("event_time regression")
            event = ChangeEvent.create(
                event_id=event_id,
                system_id=system_id,
                revision_sha=revision_sha,
                policy_sha256=policy_sha256,
                lane=lane_value,
                tick=tick,
                sequence=sequence,
                event_time=normalised_time,
                delta_ms=delta_ms,
                kind=kind,
                source=source,
                entity=entity,
                field=field,
                old_hash=old_hash,
                new_hash=new_hash,
                magnitude=magnitude,
                previous_evidence_sha256=previous_hash,
                causal_parent_sha256=causal_parent_sha256,
                producer_identity=producer_identity,
                canonical=canonical,
                payload=payload_value,
                side_channel_reference=side_channel_reference,
            )
            return event, self._ingest_in_transaction(connection, event, gate, quota=quota)

    def append(
        self,
        event: ChangeEvent,
        gate: RelevanceGate | None = None,
        *,
        quota: LedgerQuota | None = None,
    ) -> CandidateReceipt:
        """Compatibility name for the same atomic ingest operation."""

        return self.ingest(event, gate, quota=quota)

    def read_head(self, source: str) -> SourceHead | None:
        """Read a source head for evidence only; use ``ingest_next`` to allocate."""

        _require_stable_id(source, "source")
        with self._lock:
            self._ensure_open()
            row = self._connection.execute(
                """
                SELECT source, last_sequence, last_tick, last_event_time,
                       last_event_hash, last_event_id
                FROM source_heads WHERE source = ?
                """,
                (source,),
            ).fetchone()
        if row is None:
            return None
        return SourceHead(
            source=row["source"],
            last_sequence=int(row["last_sequence"]),
            last_tick=int(row["last_tick"]),
            last_event_time=row["last_event_time"],
            last_event_hash=row["last_event_hash"],
            last_event_id=row["last_event_id"],
        )

    def metrics(self) -> LedgerMetrics:
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute(
                "SELECT name, value FROM ledger_metrics WHERE name IN (?, ?, ?, ?, ?, ?)",
                _METRIC_NAMES,
            ).fetchall()
        values = {row["name"]: int(row["value"]) for row in rows}
        if set(values) != set(_METRIC_NAMES):
            raise ChainIntegrityError("incremental metrics are incomplete")
        return LedgerMetrics(**values)

    def read_projection(self, source: str, entity: str, field: str) -> ProjectionState | None:
        _require_stable_id(source, "source")
        _require_stable_id(entity, "entity")
        _require_stable_id(field, "field")
        with self._lock:
            self._ensure_open()
            row = self._connection.execute(
                """
                SELECT source, entity, field, event_id, event_hash, value_hash, tick, sequence, event_time
                FROM projections WHERE source = ? AND entity = ? AND field = ?
                """,
                (source, entity, field),
            ).fetchone()
        if row is None:
            return None
        return ProjectionState(
            source=row["source"],
            entity=row["entity"],
            field=row["field"],
            event_id=row["event_id"],
            event_hash=row["event_hash"],
            value_hash=row["value_hash"],
            tick=int(row["tick"]),
            sequence=int(row["sequence"]),
            event_time=row["event_time"],
        )

    def query_window(
        self,
        source: str,
        *,
        start_tick: int,
        end_tick: int,
        limit: int = 100,
        relevant_only: bool = False,
    ) -> TemporalWindow:
        _require_stable_id(source, "source")
        _require_non_negative_int(start_tick, "start_tick")
        _require_non_negative_int(end_tick, "end_tick")
        if start_tick > end_tick:
            raise ContractError("invalid tick window: start_tick exceeds end_tick")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self._max_window_size:
            raise ContractError(f"limit must be between 1 and {self._max_window_size}")
        if not isinstance(relevant_only, bool):
            raise ContractError("relevant_only must be boolean")
        predicate = " AND relevant = 1" if relevant_only else ""
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute(
                f"""
                SELECT canonical_event FROM change_events
                WHERE source = ? AND tick >= ? AND tick <= ?{predicate}
                ORDER BY tick ASC, sequence ASC, event_id ASC
                LIMIT ?
                """,
                (source, start_tick, end_tick, limit),
            ).fetchall()
        events: list[ChangeEvent] = []
        for row in rows:
            try:
                events.append(ChangeEvent.from_dict(json.loads(row["canonical_event"])))
            except (json.JSONDecodeError, ContractError, TypeError) as exc:
                raise ChainIntegrityError("temporal window encountered an invalid persisted event") from exc
        window = TemporalWindow(
            source=source,
            start_tick=start_tick,
            end_tick=end_tick,
            events=tuple(events),
            window_hash="",
        )
        return replace(window, window_hash=window.recompute_hash())

    def verify_integrity(self, source: str | None = None) -> IntegrityReport:
        if source is not None:
            _require_stable_id(source, "source")
        with self._lock:
            self._ensure_open()
            self._verify_schema_identity()
            if source is None:
                sources = [
                    row["source"]
                    for row in self._connection.execute(
                        """
                        SELECT source FROM (
                            SELECT source FROM source_heads
                            UNION
                            SELECT source FROM change_events
                        ) ORDER BY source ASC
                        """
                    ).fetchall()
                ]
            else:
                sources = [source]
            event_count = 0
            relevant_count = 0
            heads: list[tuple[str, str]] = []
            expected_projections: dict[tuple[str, str, str], dict[str, Any]] = {}
            for stream in sources:
                rows = self._connection.execute(
                    """
                    SELECT event_id, event_hash, source, sequence, tick, event_time, delta_ms,
                           previous_hash, relevant, canonical_event, receipt_json, receipt_hash
                    FROM change_events WHERE source = ? ORDER BY sequence ASC
                    """,
                    (stream,),
                ).fetchall()
                if not rows:
                    if source is not None:
                        continue
                    raise ChainIntegrityError(f"source head without events: {stream}")
                previous_hash = ZERO_SHA256
                previous_time: datetime | None = None
                previous_tick = 0
                for expected_sequence, row in enumerate(rows):
                    try:
                        event = ChangeEvent.from_dict(json.loads(row["canonical_event"]))
                    except (json.JSONDecodeError, ContractError, TypeError) as exc:
                        raise ChainIntegrityError(
                            f"invalid canonical event at {stream}:{expected_sequence}"
                        ) from exc
                    if canonical_json(event.to_dict()) != row["canonical_event"]:
                        raise ChainIntegrityError("persisted event JSON is not canonical")
                    if event.source != stream or row["source"] != stream:
                        raise ChainIntegrityError("cross-source persisted event")
                    if event.sequence != expected_sequence or int(row["sequence"]) != expected_sequence:
                        raise ChainIntegrityError("persisted source sequence gap")
                    if event.event_id != row["event_id"] or event.event_hash != row["event_hash"]:
                        raise ChainIntegrityError("persisted event identity/hash mismatch")
                    if event.previous_hash != previous_hash or row["previous_hash"] != previous_hash:
                        raise ChainIntegrityError("persisted predecessor hash mismatch")
                    if event.tick != int(row["tick"]) or event.event_time != row["event_time"]:
                        raise ChainIntegrityError("persisted temporal identity mismatch")
                    if event.delta_ms != int(row["delta_ms"]):
                        raise ChainIntegrityError("persisted delta_ms mismatch")
                    current_time = _parse_event_time(event.event_time)
                    if previous_time is None:
                        if event.delta_ms != 0:
                            raise ChainIntegrityError("first persisted event has non-zero delta_ms")
                    else:
                        elapsed_ms = _elapsed_milliseconds(current_time, previous_time)
                        if elapsed_ms < 0 or event.delta_ms != elapsed_ms:
                            raise ChainIntegrityError("persisted event_time/delta_ms chain mismatch")
                        if event.tick < previous_tick:
                            raise ChainIntegrityError("persisted tick regression")
                    receipt = self._receipt_from_row(row)
                    if receipt.event_id != event.event_id or receipt.event_hash != event.event_hash:
                        raise ChainIntegrityError("persisted receipt/event binding mismatch")
                    if receipt.receipt_hash != row["receipt_hash"]:
                        raise ChainIntegrityError("persisted receipt hash mismatch")
                    if receipt.relevant != bool(row["relevant"]):
                        raise ChainIntegrityError("persisted relevance/receipt mismatch")
                    if receipt.projection_updated != receipt.relevant:
                        raise ChainIntegrityError("persisted receipt projection decision mismatch")
                    if receipt.relevant:
                        expected_projections[(event.source, event.entity, event.field)] = {
                            "source": event.source,
                            "entity": event.entity,
                            "field": event.field,
                            "event_id": event.event_id,
                            "event_hash": event.event_hash,
                            "value_hash": event.new_hash,
                            "tick": event.tick,
                            "sequence": event.sequence,
                            "event_time": event.event_time,
                        }
                    relevant_count += int(receipt.relevant)
                    previous_hash = event.event_hash
                    previous_time = current_time
                    previous_tick = event.tick
                    event_count += 1
                head = self._connection.execute(
                    """
                    SELECT last_sequence, last_tick, last_event_time, last_event_hash, last_event_id
                    FROM source_heads WHERE source = ?
                    """,
                    (stream,),
                ).fetchone()
                last_event = rows[-1]
                if head is None or (
                    int(head["last_sequence"]) != int(last_event["sequence"])
                    or int(head["last_tick"]) != int(last_event["tick"])
                    or head["last_event_time"] != last_event["event_time"]
                    or head["last_event_hash"] != last_event["event_hash"]
                    or head["last_event_id"] != last_event["event_id"]
                ):
                    raise ChainIntegrityError(f"source head mismatch: {stream}")
                heads.append((stream, previous_hash))

            projection_query = """
                SELECT source, entity, field, event_id, event_hash, value_hash,
                       tick, sequence, event_time
                FROM projections
            """
            projection_parameters: tuple[str, ...] = ()
            if source is not None:
                projection_query += " WHERE source = ?"
                projection_parameters = (source,)
            projection_query += " ORDER BY source, entity, field"
            projection_rows = self._connection.execute(
                projection_query, projection_parameters
            ).fetchall()
            observed_projections: dict[tuple[str, str, str], dict[str, Any]] = {}
            for row in projection_rows:
                key = (row["source"], row["entity"], row["field"])
                if key in observed_projections:
                    raise ChainIntegrityError("duplicate persisted projection identity")
                observed_projections[key] = {
                    "source": row["source"],
                    "entity": row["entity"],
                    "field": row["field"],
                    "event_id": row["event_id"],
                    "event_hash": row["event_hash"],
                    "value_hash": row["value_hash"],
                    "tick": row["tick"],
                    "sequence": row["sequence"],
                    "event_time": row["event_time"],
                }
            if set(observed_projections) != set(expected_projections):
                raise ChainIntegrityError("persisted projection identity set mismatch")
            for key, expected_projection in expected_projections.items():
                if observed_projections[key] != expected_projection:
                    raise ChainIntegrityError("persisted projection content mismatch")

            if source is None:
                metrics = self.metrics()
                if (
                    metrics.observed_events != event_count
                    or metrics.receipts_created != event_count
                    or metrics.relevant_events != relevant_count
                    or metrics.discarded_events != event_count - relevant_count
                    or metrics.projection_updates != relevant_count
                ):
                    raise ChainIntegrityError("incremental metrics do not match the durable event ledger")
        return IntegrityReport(
            ok=True,
            event_count=event_count,
            source_count=len(heads),
            heads=tuple(heads),
        )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._connection.close()
            self._closed = True

    def __enter__(self) -> "NeuromorphicLedger":
        self._ensure_open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


__all__ = [
    "CANDIDATE_RECEIPT_SCHEMA_VERSION",
    "CHANGE_EVENT_SCHEMA_VERSION",
    "KNOWN_EVENT_KINDS",
    "NEUROMORPHIC_LEDGER_SCHEMA_VERSION",
    "NEUROMORPHIC_SQLITE_APPLICATION_ID",
    "NEUROMORPHIC_SQLITE_USER_VERSION",
    "ZERO_SHA256",
    "CandidateReceipt",
    "ChainIntegrityError",
    "ChangeEvent",
    "ContractError",
    "CrossSourceReplayError",
    "DeltaDetector",
    "DeltaObservation",
    "IntegrityReport",
    "LedgerClosedError",
    "LedgerQuota",
    "LedgerQuotaExceededError",
    "LedgerReadOnlyError",
    "LedgerMetrics",
    "NeuromorphicLedger",
    "NeuromorphicRuntimeError",
    "ProjectionState",
    "QuantizedSpikeFilter",
    "RelevanceDecision",
    "RelevanceGate",
    "ReplayConflictError",
    "ResourceHomeostat",
    "ResourceRecommendation",
    "SequenceConflictError",
    "SourceHead",
    "SpikeDecision",
    "TemporalEnvelope",
    "TemporalOrderError",
    "TemporalWindow",
    "UnknownEventKindError",
    "canonical_json",
    "canonical_sha256",
]
