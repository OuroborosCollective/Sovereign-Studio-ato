"""Deterministic, fail-closed verification lane for Sovereign MCP events.

This module is deliberately a policy/verification boundary, not a second event
authority.  The canonical event identity remains the neuro architecture
``EvidenceEnvelope`` defined in ``backend/agent_runtime``.  Callers pass its
``canonical_record()`` output together with the MCP request/session identity and
the hash of the source ``ChangeEvent``.  No import of either runtime is required.

The pure :meth:`FoundationRuntime.verify` operation never persists state and can
never execute an external effect.  Persistence is an explicit second operation
through the small :class:`FoundationLedger` protocol.  The provided SQLite
adapter uses one immediate transaction per append and maintains an independently
verifiable evidence hash chain.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
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
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, runtime_checkable


FOUNDATION_DECISION_SCHEMA = "sovereign.foundation-decision.v1"
FOUNDATION_LEDGER_SCHEMA = "sovereign.foundation-ledger-entry.v1"
FOUNDATION_SQLITE_SCHEMA = "sovereign.foundation-sqlite.v1"
FOUNDATION_SQLITE_USER_VERSION = 1
FOUNDATION_SQLITE_APPLICATION_ID = 0x534F5646  # ASCII: SOVF
NEURO_ENVELOPE_SCHEMA = "sovereign.neuro-architecture-envelope.v1"
CHANGE_EVENT_SCHEMA = "sovereign.change-event.v1"
AUTHORITATIVE_EVIDENCE_SCHEMA = "sovereign.authoritative-outcome-evidence.v1"
AUTHORITATIVE_CAUSAL_EVIDENCE_SCHEMA = "sovereign.authoritative-causal-evidence.v1"
DETERMINISTIC_VERIFICATION_LANE = "deterministic-verification"
ZERO_SHA256 = "0" * 64

MAX_PAYLOAD_BYTES = 16_384
MAX_CLAIMS = 512
MAX_EVIDENCE_REFERENCES = 64
MIN_CANDIDATE_EVIDENCE = 3
MAX_JSON_DEPTH = 32
MAX_JSON_ITEMS = 2_048

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,159}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_UNIT = re.compile(r"^[A-Za-z][A-Za-z0-9*/^(). -]{0,80}$")

_FOUNDATION_METADATA_SQL = """
    CREATE TABLE foundation_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
"""
_FOUNDATION_EVIDENCE_SQL = """
    CREATE TABLE foundation_evidence (
        sequence INTEGER PRIMARY KEY,
        schema_version TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        request_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        event_id TEXT NOT NULL,
        decision_sha256 TEXT NOT NULL,
        decision_json TEXT NOT NULL,
        previous_evidence_sha256 TEXT NOT NULL,
        evidence_sha256 TEXT NOT NULL UNIQUE,
        UNIQUE(request_id, session_id, event_id)
    )
"""


def _normalise_schema_sql(value: str) -> str:
    # Keep quoted literal case significant; only whitespace is non-semantic for
    # the canonical statements created by this runtime.
    return re.sub(r"\s+", " ", str(value or "").strip())


class FoundationContractError(ValueError):
    """Raised when a caller violates a structural adapter contract."""


class FoundationPersistenceError(RuntimeError):
    """Raised when evidence cannot be persisted without ambiguity."""


def _normalise_json(value: Any, *, depth: int = 0) -> Any:
    if depth > MAX_JSON_DEPTH:
        raise FoundationContractError("canonical JSON exceeds maximum nesting depth")
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if not -(2**63) <= value <= 2**63 - 1:
            raise FoundationContractError("canonical JSON integer exceeds signed 64-bit range")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FoundationContractError("canonical JSON number must be finite")
        return value
    if isinstance(value, Mapping):
        if len(value) > MAX_JSON_ITEMS:
            raise FoundationContractError("canonical JSON mapping exceeds item bound")
        normalised: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise FoundationContractError("canonical JSON mapping keys must be strings")
            normalised[key] = _normalise_json(child, depth=depth + 1)
        return normalised
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_JSON_ITEMS:
            raise FoundationContractError("canonical JSON sequence exceeds item bound")
        return [_normalise_json(child, depth=depth + 1) for child in value]
    raise FoundationContractError(f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return the single JSON encoding used for every Foundation hash."""

    normalised = _normalise_json(value)
    try:
        return json.dumps(
            normalised,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise FoundationContractError("value is not canonical JSON") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _field(value: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in value:
            return value[name]
    return default


def _required_text(value: Any, name: str, *, canonical_id: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise FoundationContractError(f"invalid {name}")
    matcher = _CANONICAL_ID if canonical_id else _TOKEN
    if not matcher.fullmatch(value):
        raise FoundationContractError(f"invalid {name}")
    return value


def _required_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise FoundationContractError(f"invalid {name}")
    return value


def _required_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FoundationContractError(f"invalid {name}")
    return value


def _as_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    converter = getattr(value, "canonical_record", None)
    if callable(converter):
        converted = converter()
        if isinstance(converted, Mapping):
            return converted
    converter = getattr(value, "to_dict", None)
    if callable(converter):
        converted = converter()
        if isinstance(converted, Mapping):
            return converted
    raise FoundationContractError(f"invalid {name}")


@dataclass(frozen=True, slots=True)
class FoundationBinding:
    """Request/session binding to one canonical neuro evidence envelope."""

    request_id: str
    session_id: str
    source: str
    source_event_hash: str
    event_id: str
    system_id: str
    revision_sha: str
    policy_sha256: str
    foundation_payload_sha256: str
    source_payload_sha256: str
    tick: int
    sequence: int
    producer_identity: str
    envelope_sha256: str

    @classmethod
    def from_value(cls, value: Any, *, payload_sha256: str) -> "FoundationBinding":
        if isinstance(value, cls):
            if value.foundation_payload_sha256 != payload_sha256:
                raise FoundationContractError("payload hash does not match binding")
            return value

        outer = _as_mapping(value, "foundation binding")
        envelope_value = _field(outer, "envelope", "neuroEnvelope")
        envelope = _as_mapping(envelope_value if envelope_value is not None else outer, "neuro envelope")

        schema_version = _field(envelope, "schemaVersion", "schema_version")
        if schema_version != NEURO_ENVELOPE_SCHEMA:
            raise FoundationContractError("unsupported neuro envelope schema")

        system_id = _required_text(
            _field(envelope, "systemId", "system_id"), "systemId", canonical_id=True
        )
        revision_sha = _field(envelope, "revisionSha", "revision_sha")
        if not isinstance(revision_sha, str) or not _SHA40.fullmatch(revision_sha):
            raise FoundationContractError("invalid revisionSha")
        policy_sha256 = _required_sha256(
            _field(envelope, "policySha256", "policy_sha256"), "policySha256"
        )
        event_id = _required_text(
            _field(envelope, "eventId", "event_id"), "eventId", canonical_id=True
        )
        lane = _field(envelope, "lane")
        if lane != DETERMINISTIC_VERIFICATION_LANE:
            raise FoundationContractError("foundation requires deterministic-verification lane")
        tick = _required_int(_field(envelope, "tick"), "tick")
        sequence = _required_int(_field(envelope, "sequence"), "sequence")
        envelope_payload_hash = _required_sha256(
            _field(envelope, "payloadSha256", "payload_sha256"), "payloadSha256"
        )
        source_payload_hash = _field(
            outer, "sourcePayloadSha256", "source_payload_sha256", default=payload_sha256
        )
        source_payload_hash = _required_sha256(source_payload_hash, "sourcePayloadSha256")
        if envelope_payload_hash != source_payload_hash:
            raise FoundationContractError("source payload hash does not match neuro envelope")
        asserted_foundation_payload_hash = _field(
            outer, "foundationPayloadSha256", "foundation_payload_sha256"
        )
        if (
            asserted_foundation_payload_hash is not None
            and asserted_foundation_payload_hash != payload_sha256
        ):
            raise FoundationContractError("foundation payload hash mismatch")
        causal_parent = _required_sha256(
            _field(envelope, "causalParentSha256", "causal_parent_sha256"),
            "causalParentSha256",
        )
        previous_evidence = _required_sha256(
            _field(envelope, "previousEvidenceSha256", "previous_evidence_sha256"),
            "previousEvidenceSha256",
        )
        producer_identity = _field(envelope, "producerIdentity", "producer_identity")
        if not isinstance(producer_identity, str) or not producer_identity.strip() or len(producer_identity) > 256:
            raise FoundationContractError("invalid producerIdentity")
        canonical = _field(envelope, "canonical")
        if canonical is not True:
            raise FoundationContractError("deterministic verification envelope must be canonical")
        side_channel_reference = _field(
            envelope, "sideChannelReference", "side_channel_reference", default=""
        )
        if not isinstance(side_channel_reference, str) or len(side_channel_reference) > 512:
            raise FoundationContractError("invalid sideChannelReference")

        canonical_envelope = {
            "canonical": True,
            "causalParentSha256": causal_parent,
            "eventId": event_id,
            "lane": DETERMINISTIC_VERIFICATION_LANE,
            "payloadSha256": envelope_payload_hash,
            "policySha256": policy_sha256,
            "previousEvidenceSha256": previous_evidence,
            "producerIdentity": producer_identity,
            "revisionSha": revision_sha,
            "schemaVersion": NEURO_ENVELOPE_SCHEMA,
            "sequence": sequence,
            "sideChannelReference": side_channel_reference,
            "systemId": system_id,
            "tick": tick,
        }
        envelope_sha256 = canonical_sha256(canonical_envelope)

        asserted_envelope_hash = _field(outer, "envelopeSha256", "envelope_sha256")
        if asserted_envelope_hash is not None and asserted_envelope_hash != envelope_sha256:
            raise FoundationContractError("neuro envelope hash mismatch")

        duplicate_event_id = _field(outer, "eventId", "event_id")
        if envelope_value is not None and duplicate_event_id is not None and duplicate_event_id != event_id:
            raise FoundationContractError("event binding mismatch")

        source_event_hash = _required_sha256(
            _field(outer, "sourceEventHash", "source_event_hash"), "sourceEventHash"
        )
        if source_event_hash != envelope_sha256:
            raise FoundationContractError("source event hash does not match neuro envelope")

        return cls(
            request_id=_required_text(
                _field(outer, "requestId", "request_id"), "requestId", canonical_id=True
            ),
            session_id=_required_text(
                _field(outer, "sessionId", "session_id"), "sessionId", canonical_id=True
            ),
            source=_required_text(_field(outer, "source"), "source", canonical_id=True),
            source_event_hash=source_event_hash,
            event_id=event_id,
            system_id=system_id,
            revision_sha=revision_sha,
            policy_sha256=policy_sha256,
            foundation_payload_sha256=payload_sha256,
            source_payload_sha256=envelope_payload_hash,
            tick=tick,
            sequence=sequence,
            producer_identity=producer_identity,
            envelope_sha256=envelope_sha256,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelopeSha256": self.envelope_sha256,
            "eventId": self.event_id,
            "foundationPayloadSha256": self.foundation_payload_sha256,
            "policySha256": self.policy_sha256,
            "producerIdentity": self.producer_identity,
            "requestId": self.request_id,
            "revisionSha": self.revision_sha,
            "sequence": self.sequence,
            "sessionId": self.session_id,
            "source": self.source,
            "sourceEventHash": self.source_event_hash,
            "sourcePayloadSha256": self.source_payload_sha256,
            "systemId": self.system_id,
            "tick": self.tick,
        }


@runtime_checkable
class EvidenceResolver(Protocol):
    """Read-only adapter for hash-bound authoritative evidence receipts."""

    def resolve_evidence(self, event_id: str, evidence_sha256: str) -> Mapping[str, Any] | None:
        """Return the exact hash-bound receipt, or ``None`` when unavailable."""


@runtime_checkable
class FoundationLedger(Protocol):
    """Minimal explicit persistence boundary used by ``FoundationRuntime``."""

    def append_decision(self, decision: Mapping[str, Any]) -> Mapping[str, Any]:
        """Persist exactly one hash-bound decision transactionally."""

    def verify_chain(self) -> Mapping[str, Any]:
        """Read and verify persisted evidence without changing it."""


class SQLiteFoundationLedger:
    """Thread-safe, transactional stdlib evidence ledger.

    This ledger preserves Foundation decisions; it does not become the canonical
    source event stream.  A repeated identical event is returned idempotently,
    while the same request/session/event identity with a different decision is
    rejected as an ambiguous replay.
    """

    def __init__(self, database_path: str) -> None:
        if not isinstance(database_path, str) or not database_path:
            raise FoundationPersistenceError("database_path is required")
        if database_path == ":memory:":
            raise FoundationPersistenceError("Foundation evidence requires a durable database file")
        self.database_path = database_path
        self._lock = threading.RLock()
        self._read_only = False
        self._secure_database_file()
        self._initialize()

    @classmethod
    def open_read_only(cls, database_path: str) -> "SQLiteFoundationLedger":
        """Open and verify an existing ledger without initializing or mutating it."""

        if not isinstance(database_path, str) or not database_path or database_path == ":memory:":
            raise FoundationPersistenceError("a durable Foundation database path is required")
        try:
            file_status = os.lstat(database_path)
        except OSError as exc:
            raise FoundationPersistenceError("Foundation database file is unavailable") from exc
        if stat.S_ISLNK(file_status.st_mode) or not stat.S_ISREG(file_status.st_mode):
            raise FoundationPersistenceError("Foundation database path is not a regular file")

        instance = cls.__new__(cls)
        instance.database_path = database_path
        instance._lock = threading.RLock()
        instance._read_only = True
        with closing(instance._connect()):
            pass
        return instance

    def _secure_database_file(self) -> None:
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.database_path, flags, 0o600)
        except OSError as exc:
            raise FoundationPersistenceError("Foundation database file cannot be opened safely") from exc
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise FoundationPersistenceError("Foundation database path is not a regular file")
            os.fchmod(descriptor, 0o600)
        except OSError as exc:
            raise FoundationPersistenceError("Foundation database permissions cannot be secured") from exc
        finally:
            os.close(descriptor)

    @staticmethod
    def _pragma_int(connection: sqlite3.Connection, name: str) -> int:
        row = connection.execute(f"PRAGMA {name}").fetchone()
        if row is None:
            raise FoundationPersistenceError(f"SQLite did not report {name}")
        return int(row[0])

    @staticmethod
    def _table_shape(
        connection: sqlite3.Connection, table: str
    ) -> tuple[tuple[str, str, int, int], ...]:
        return tuple(
            (str(row[1]), str(row[2]).upper(), int(row[3]), int(row[5]))
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        )

    def _verify_schema_identity(self, connection: sqlite3.Connection) -> None:
        mode_row = connection.execute("PRAGMA journal_mode").fetchone()
        mode = str(mode_row[0]).casefold() if mode_row is not None else ""
        if mode != "wal":
            raise FoundationPersistenceError("Foundation database journal mode is not WAL")
        if self._pragma_int(connection, "synchronous") != 2:
            raise FoundationPersistenceError("Foundation database synchronous mode is not FULL")
        if self._pragma_int(connection, "trusted_schema") != 0:
            raise FoundationPersistenceError("Foundation database trusted_schema is not disabled")
        if self._pragma_int(connection, "application_id") != FOUNDATION_SQLITE_APPLICATION_ID:
            raise FoundationPersistenceError("Foundation database application identity mismatch")
        if self._pragma_int(connection, "user_version") != FOUNDATION_SQLITE_USER_VERSION:
            raise FoundationPersistenceError("Foundation database schema version mismatch")

        objects = {
            (str(row[0]), str(row[1])): _normalise_schema_sql(str(row[2] or ""))
            for row in connection.execute(
                "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        expected_objects = {
            ("table", "foundation_evidence"): _normalise_schema_sql(
                _FOUNDATION_EVIDENCE_SQL
            ),
            ("table", "foundation_metadata"): _normalise_schema_sql(
                _FOUNDATION_METADATA_SQL
            ),
        }
        if objects != expected_objects:
            raise FoundationPersistenceError(
                "Foundation database object or SQL identity mismatch"
            )

        expected_metadata_shape = (
            ("key", "TEXT", 0, 1),
            ("value", "TEXT", 1, 0),
        )
        expected_evidence_shape = (
            ("sequence", "INTEGER", 0, 1),
            ("schema_version", "TEXT", 1, 0),
            ("recorded_at", "TEXT", 1, 0),
            ("request_id", "TEXT", 1, 0),
            ("session_id", "TEXT", 1, 0),
            ("event_id", "TEXT", 1, 0),
            ("decision_sha256", "TEXT", 1, 0),
            ("decision_json", "TEXT", 1, 0),
            ("previous_evidence_sha256", "TEXT", 1, 0),
            ("evidence_sha256", "TEXT", 1, 0),
        )
        if self._table_shape(connection, "foundation_metadata") != expected_metadata_shape:
            raise FoundationPersistenceError("Foundation metadata table shape mismatch")
        if self._table_shape(connection, "foundation_evidence") != expected_evidence_shape:
            raise FoundationPersistenceError("Foundation evidence table shape mismatch")

        metadata = connection.execute(
            "SELECT value FROM foundation_metadata WHERE key = 'schema_identity'"
        ).fetchone()
        if metadata is None or metadata[0] != FOUNDATION_SQLITE_SCHEMA:
            raise FoundationPersistenceError("Foundation database schema identity mismatch")

        def index_contract(table: str) -> set[tuple[tuple[str, ...], int, str, int]]:
            contract: set[tuple[tuple[str, ...], int, str, int]] = set()
            for index in connection.execute(f"PRAGMA index_list({table})").fetchall():
                columns = tuple(
                    str(row[2])
                    for row in connection.execute(f"PRAGMA index_info({index[1]})").fetchall()
                )
                contract.add((columns, int(index[2]), str(index[3]), int(index[4])))
            return contract

        if index_contract("foundation_metadata") != {(('key',), 1, 'pk', 0)}:
            raise FoundationPersistenceError("Foundation metadata index contract mismatch")
        if index_contract("foundation_evidence") != {
            (("evidence_sha256",), 1, "u", 0),
            (("request_id", "session_id", "event_id"), 1, "u", 0),
        }:
            raise FoundationPersistenceError("Foundation evidence index contract mismatch")

    def _connect(self, *, require_identity: bool = True) -> sqlite3.Connection:
        read_only = bool(getattr(self, "_read_only", False))
        if not read_only:
            self._secure_database_file()
        connection: sqlite3.Connection | None = None
        try:
            if read_only:
                database_uri = Path(self.database_path).absolute().as_uri() + "?mode=ro"
                connection = sqlite3.connect(
                    database_uri,
                    uri=True,
                    timeout=30.0,
                    isolation_level=None,
                    check_same_thread=False,
                )
                connection.execute("PRAGMA query_only = ON")
            else:
                connection = sqlite3.connect(
                    self.database_path,
                    timeout=30.0,
                    isolation_level=None,
                    check_same_thread=False,
                )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 30000")
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute("PRAGMA synchronous = FULL")
            if read_only and self._pragma_int(connection, "query_only") != 1:
                raise FoundationPersistenceError("Foundation read-only connection is not query-only")
            if self._pragma_int(connection, "foreign_keys") != 1:
                raise FoundationPersistenceError("Foundation database foreign keys are disabled")
            if require_identity:
                self._verify_schema_identity(connection)
            return connection
        except Exception:
            if connection is not None:
                connection.close()
            raise

    def _initialize(self) -> None:
        flags = os.O_RDWR
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.database_path, flags)
        except OSError as exc:
            raise FoundationPersistenceError(
                "Foundation database initialization lock is unavailable"
            ) from exc
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            self._initialize_locked()
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _initialize_locked(self) -> None:
        with self._lock, closing(self._connect(require_identity=False)) as connection:
            application_id = self._pragma_int(connection, "application_id")
            user_version = self._pragma_int(connection, "user_version")
            objects = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1"
            ).fetchone()
            is_new = application_id == 0 and user_version == 0 and objects is None
            if not is_new:
                if application_id != FOUNDATION_SQLITE_APPLICATION_ID:
                    raise FoundationPersistenceError(
                        "Foundation database application identity mismatch"
                    )
                if user_version != FOUNDATION_SQLITE_USER_VERSION:
                    raise FoundationPersistenceError(
                        "Foundation database schema version mismatch"
                    )
                self._verify_schema_identity(connection)
                return

            mode_row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
            mode = str(mode_row[0]).casefold() if mode_row is not None else ""
            if mode != "wal":
                raise FoundationPersistenceError("SQLite refused Foundation WAL journal mode")
            try:
                connection.execute("BEGIN IMMEDIATE")
                # Another process may have initialized the empty file while
                # this connection waited for the write lock.  Re-read the
                # durable header under the transaction before creating tables.
                locked_application_id = self._pragma_int(connection, "application_id")
                locked_user_version = self._pragma_int(connection, "user_version")
                locked_objects = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1"
                ).fetchone()
                if (
                    locked_application_id == FOUNDATION_SQLITE_APPLICATION_ID
                    and locked_user_version == FOUNDATION_SQLITE_USER_VERSION
                ):
                    connection.commit()
                    self._verify_schema_identity(connection)
                    return
                if not (
                    locked_application_id == 0
                    and locked_user_version == 0
                    and locked_objects is None
                ):
                    raise FoundationPersistenceError(
                        "Foundation database identity changed during initialization"
                    )
                connection.execute(_FOUNDATION_METADATA_SQL)
                connection.execute(
                    "INSERT INTO foundation_metadata(key, value) VALUES('schema_identity', ?)",
                    (FOUNDATION_SQLITE_SCHEMA,),
                )
                connection.execute(_FOUNDATION_EVIDENCE_SQL)
                connection.execute(f"PRAGMA application_id = {FOUNDATION_SQLITE_APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version = {FOUNDATION_SQLITE_USER_VERSION}")
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            self._verify_schema_identity(connection)

    @staticmethod
    def _validated_decision(decision: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(decision, Mapping):
            raise FoundationPersistenceError("decision must be a mapping")
        copied = json.loads(canonical_json(decision))
        if copied.get("schemaVersion") != FOUNDATION_DECISION_SCHEMA:
            raise FoundationPersistenceError("unsupported decision schema")
        asserted = copied.get("decisionSha256")
        if not isinstance(asserted, str) or not _SHA256.fullmatch(asserted):
            raise FoundationPersistenceError("invalid decision hash")
        hash_body = {key: value for key, value in copied.items() if key != "decisionSha256"}
        if canonical_sha256(hash_body) != asserted:
            raise FoundationPersistenceError("decision hash mismatch")
        binding = copied.get("binding")
        if not isinstance(binding, dict):
            raise FoundationPersistenceError("unbound decisions cannot be persisted")
        return copied, binding

    def append_decision(self, decision: Mapping[str, Any]) -> dict[str, Any]:
        if self._read_only:
            raise FoundationPersistenceError("Foundation ledger is read-only")
        copied, binding = self._validated_decision(decision)
        request_id = _required_text(binding.get("requestId"), "requestId", canonical_id=True)
        session_id = _required_text(binding.get("sessionId"), "sessionId", canonical_id=True)
        event_id = _required_text(binding.get("eventId"), "eventId", canonical_id=True)
        decision_sha256 = copied["decisionSha256"]

        with self._lock, closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """
                    SELECT sequence, schema_version, recorded_at,
                           previous_evidence_sha256, evidence_sha256,
                           decision_sha256, decision_json
                    FROM foundation_evidence
                    WHERE request_id = ? AND session_id = ? AND event_id = ?
                    """,
                    (request_id, session_id, event_id),
                ).fetchone()
                if existing is not None:
                    if existing["decision_sha256"] != decision_sha256:
                        raise FoundationPersistenceError("event identity already binds another decision")
                    try:
                        stored_decision = json.loads(existing["decision_json"])
                    except json.JSONDecodeError as exc:
                        raise FoundationPersistenceError(
                            "existing ledger decision is not valid JSON"
                        ) from exc
                    stored_body = {
                        key: value
                        for key, value in stored_decision.items()
                        if key != "decisionSha256"
                    }
                    existing_entry_body = {
                        "decisionSha256": decision_sha256,
                        "eventId": event_id,
                        "previousEvidenceSha256": existing["previous_evidence_sha256"],
                        "recordedAt": existing["recorded_at"],
                        "requestId": request_id,
                        "schemaVersion": existing["schema_version"],
                        "sequence": int(existing["sequence"]),
                        "sessionId": session_id,
                    }
                    if (
                        stored_decision.get("decisionSha256") != decision_sha256
                        or canonical_sha256(stored_body) != decision_sha256
                        or existing["schema_version"] != FOUNDATION_LEDGER_SCHEMA
                        or canonical_sha256(existing_entry_body) != existing["evidence_sha256"]
                    ):
                        raise FoundationPersistenceError(
                            "existing ledger entry fails integrity verification"
                        )
                    connection.commit()
                    return {
                        "schemaVersion": FOUNDATION_LEDGER_SCHEMA,
                        "sequence": int(existing["sequence"]),
                        "recordedAt": existing["recorded_at"],
                        "previousEvidenceSha256": existing["previous_evidence_sha256"],
                        "evidenceSha256": existing["evidence_sha256"],
                        "decisionSha256": decision_sha256,
                        "replayed": True,
                    }

                head = connection.execute(
                    "SELECT sequence, evidence_sha256 FROM foundation_evidence ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                sequence = int(head["sequence"]) + 1 if head else 1
                previous_hash = head["evidence_sha256"] if head else ZERO_SHA256
                recorded_at = _utc_now()
                entry_body = {
                    "decisionSha256": decision_sha256,
                    "eventId": event_id,
                    "previousEvidenceSha256": previous_hash,
                    "recordedAt": recorded_at,
                    "requestId": request_id,
                    "schemaVersion": FOUNDATION_LEDGER_SCHEMA,
                    "sequence": sequence,
                    "sessionId": session_id,
                }
                evidence_sha256 = canonical_sha256(entry_body)
                connection.execute(
                    """
                    INSERT INTO foundation_evidence(
                        sequence, schema_version, recorded_at, request_id,
                        session_id, event_id, decision_sha256, decision_json,
                        previous_evidence_sha256, evidence_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sequence,
                        FOUNDATION_LEDGER_SCHEMA,
                        recorded_at,
                        request_id,
                        session_id,
                        event_id,
                        decision_sha256,
                        canonical_json(copied),
                        previous_hash,
                        evidence_sha256,
                    ),
                )
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise

        return {
            **entry_body,
            "evidenceSha256": evidence_sha256,
            "replayed": False,
        }

    def verify_chain(self) -> dict[str, Any]:
        """Pure, read-only verification of the persisted evidence chain."""

        with self._lock, closing(self._connect()) as connection:
            connection.execute("PRAGMA query_only = ON")
            rows = connection.execute(
                """
                SELECT sequence, schema_version, recorded_at, request_id,
                       session_id, event_id, decision_sha256, decision_json,
                       previous_evidence_sha256, evidence_sha256
                FROM foundation_evidence ORDER BY sequence
                """
            ).fetchall()

        previous_hash = ZERO_SHA256
        for expected_sequence, row in enumerate(rows, start=1):
            try:
                decision = json.loads(row["decision_json"])
            except json.JSONDecodeError:
                return {
                    "valid": False,
                    "entries": expected_sequence - 1,
                    "head": previous_hash,
                    "reason": "decision_json_invalid",
                    "sequence": expected_sequence,
                }
            if row["schema_version"] != FOUNDATION_LEDGER_SCHEMA:
                reason = "ledger_schema_mismatch"
            elif int(row["sequence"]) != expected_sequence:
                reason = "ledger_sequence_gap"
            elif row["previous_evidence_sha256"] != previous_hash:
                reason = "previous_evidence_hash_mismatch"
            elif decision.get("decisionSha256") != row["decision_sha256"]:
                reason = "stored_decision_hash_mismatch"
            else:
                decision_body = {
                    key: value for key, value in decision.items() if key != "decisionSha256"
                }
                if canonical_sha256(decision_body) != row["decision_sha256"]:
                    reason = "decision_content_hash_mismatch"
                else:
                    entry_body = {
                        "decisionSha256": row["decision_sha256"],
                        "eventId": row["event_id"],
                        "previousEvidenceSha256": row["previous_evidence_sha256"],
                        "recordedAt": row["recorded_at"],
                        "requestId": row["request_id"],
                        "schemaVersion": row["schema_version"],
                        "sequence": int(row["sequence"]),
                        "sessionId": row["session_id"],
                    }
                    reason = (
                        "verified"
                        if canonical_sha256(entry_body) == row["evidence_sha256"]
                        else "evidence_content_hash_mismatch"
                    )
            if reason != "verified":
                return {
                    "valid": False,
                    "entries": expected_sequence - 1,
                    "head": previous_hash,
                    "reason": reason,
                    "sequence": expected_sequence,
                }
            previous_hash = row["evidence_sha256"]

        return {
            "valid": True,
            "entries": len(rows),
            "head": previous_hash,
            "reason": "verified",
        }

    def count(self) -> int:
        with self._lock, closing(self._connect()) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM foundation_evidence").fetchone()[0])


ValidatorResult = tuple[str, str, dict[str, Any]]


class FoundationRuntime:
    """Immutable validator registry plus explicit evidence persistence."""

    _VALIDATOR_NAMES = MappingProxyType(
        {
            "artifact": "_validate_artifact",
            "candidate_assessment": "_validate_candidate_assessment",
            "causal_claim": "_validate_causal_claim",
            "claim_set": "_validate_claim_set",
            "empirical_claim": "_validate_empirical_claim",
            "measurement": "_validate_measurement",
            "person_claim": "_validate_person_claim",
            "resource_ledger": "_validate_resource_ledger",
            "rollback": "_validate_rollback",
            "speech_request": "_validate_speech_request",
            "work_request": "_validate_work_request",
        }
    )

    def __init__(
        self,
        *,
        ledger: FoundationLedger | None = None,
        evidence_resolver: EvidenceResolver | None = None,
    ) -> None:
        self.ledger = ledger
        self.evidence_resolver = evidence_resolver

    @classmethod
    def registered_event_kinds(cls) -> tuple[str, ...]:
        return tuple(sorted(cls._VALIDATOR_NAMES))

    @staticmethod
    def _decision(
        *,
        event_kind: str,
        payload_sha256: str,
        binding: FoundationBinding | None,
        outcome: str,
        reason: str,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "authoritativeLane": DETERMINISTIC_VERIFICATION_LANE,
            "binding": binding.to_dict() if binding is not None else None,
            "details": dict(details or {}),
            "eventKind": event_kind,
            "externalEffects": [],
            "mayExecute": False,
            "ok": outcome == "accepted",
            "outcome": outcome,
            "payloadSha256": payload_sha256,
            "reason": reason,
            "schemaVersion": FOUNDATION_DECISION_SCHEMA,
        }
        record["decisionSha256"] = canonical_sha256(record)
        return record

    def verify(
        self,
        event_kind: Any,
        payload: Any,
        binding: Any,
    ) -> dict[str, Any]:
        """Purely verify one payload; no ledger write or external effect occurs."""

        try:
            payload_mapping = _as_mapping(payload, "foundation payload")
            payload_copy = json.loads(canonical_json(payload_mapping))
            payload_encoded = canonical_json(payload_copy).encode("utf-8")
            if len(payload_encoded) > MAX_PAYLOAD_BYTES:
                raise FoundationContractError("payload exceeds size limit")
            payload_sha256 = hashlib.sha256(payload_encoded).hexdigest()
        except FoundationContractError as exc:
            return self._decision(
                event_kind=event_kind if isinstance(event_kind, str) else "",
                payload_sha256=ZERO_SHA256,
                binding=None,
                outcome="rejected",
                reason="invalid_payload",
                details={"contractError": str(exc)},
            )

        try:
            checked_binding = FoundationBinding.from_value(
                binding, payload_sha256=payload_sha256
            )
        except FoundationContractError as exc:
            return self._decision(
                event_kind=event_kind if isinstance(event_kind, str) else "",
                payload_sha256=payload_sha256,
                binding=None,
                outcome="quarantined",
                reason="binding_invalid",
                details={"contractError": str(exc)},
            )

        if not isinstance(event_kind, str) or not event_kind:
            return self._decision(
                event_kind="",
                payload_sha256=payload_sha256,
                binding=checked_binding,
                outcome="quarantined",
                reason="invalid_event_kind",
            )

        validator_name = self._VALIDATOR_NAMES.get(event_kind)
        if validator_name is None:
            return self._decision(
                event_kind=event_kind,
                payload_sha256=payload_sha256,
                binding=checked_binding,
                outcome="quarantined",
                reason="unknown_event_kind",
                details={"allowedKinds": list(self.registered_event_kinds())},
            )

        validator: Callable[[Mapping[str, Any], FoundationBinding], ValidatorResult] = getattr(
            self, validator_name
        )
        outcome, reason, details = validator(payload_copy, checked_binding)
        if outcome not in {"accepted", "quarantined", "rejected"}:
            raise FoundationContractError("validator returned an invalid outcome")
        return self._decision(
            event_kind=event_kind,
            payload_sha256=payload_sha256,
            binding=checked_binding,
            outcome=outcome,
            reason=reason,
            details=details,
        )

    def verify_change_event(
        self,
        change_event: Any,
        *,
        foundation_kind: str,
        request_id: str,
        session_id: str,
        envelope: Any = None,
    ) -> dict[str, Any]:
        """Verify a ``neuromorphic_runtime.ChangeEvent`` through a structural port.

        ``change_event`` may be a mapping or expose ``to_dict()``.  Its own hash,
        event identity and temporal coordinates are checked against the canonical
        neuro envelope before the Foundation validator is entered.  The explicit
        ``foundation_kind`` is intentionally separate from ``ChangeEvent.kind``:
        the latter classifies a delta (for example ``state.change``), while the
        former selects a bounded Foundation domain validator (for example
        ``measurement``).
        """

        try:
            event = _as_mapping(change_event, "change event")
            event_copy = json.loads(canonical_json(event))
            try:
                # This is deliberately lazy: Foundation remains independently
                # importable, but this adapter never invents a second partial
                # ChangeEvent validator when the canonical runtime is absent.
                from neuromorphic_runtime import ChangeEvent as CanonicalChangeEvent
            except (ImportError, AttributeError) as exc:
                raise FoundationContractError(
                    "canonical ChangeEvent runtime is unavailable"
                ) from exc
            try:
                canonical_event = CanonicalChangeEvent.from_dict(event_copy)
            except Exception as exc:
                raise FoundationContractError(f"invalid canonical ChangeEvent: {exc}") from exc
            if canonical_event.to_dict() != event_copy:
                raise FoundationContractError("ChangeEvent is not in canonical form")

            embedded_envelope = _as_mapping(event_copy.get("envelope"), "change event envelope")
            embedded_envelope = json.loads(canonical_json(embedded_envelope))
            if envelope is not None:
                asserted_envelope = json.loads(
                    canonical_json(_as_mapping(envelope, "asserted neuro envelope"))
                )
                if asserted_envelope != embedded_envelope:
                    raise FoundationContractError("embedded and asserted neuro envelopes differ")
            asserted_event_hash = _required_sha256(event_copy.get("eventHash"), "eventHash")
            if canonical_sha256(embedded_envelope) != asserted_event_hash:
                raise FoundationContractError("change event hash mismatch")
            source_payload_record = {
                key: value
                for key, value in event_copy.items()
                if key not in {"envelope", "eventHash"}
            }
            source_payload_sha256 = canonical_sha256(source_payload_record)
            if embedded_envelope.get("payloadSha256") != source_payload_sha256:
                raise FoundationContractError("change event payload hash mismatch")
            payload = canonical_event.payload
            temporal = _as_mapping(event_copy.get("temporal"), "change event temporal envelope")
            event_id = _required_text(
                embedded_envelope.get("eventId"), "eventId", canonical_id=True
            )
            source = _required_text(event_copy.get("source"), "source", canonical_id=True)
            change_kind = event_copy.get("kind")
            if not isinstance(change_kind, str) or not change_kind:
                raise FoundationContractError("invalid change event kind")
            if not isinstance(foundation_kind, str) or not foundation_kind:
                raise FoundationContractError("invalid foundation event kind")

            binding = {
                "requestId": request_id,
                "sessionId": session_id,
                "source": source,
                "sourceEventHash": asserted_event_hash,
                "sourcePayloadSha256": source_payload_sha256,
                "eventId": event_id,
                "envelope": embedded_envelope,
            }
            decision = self.verify(foundation_kind, payload, binding)
            checked = decision.get("binding")
            if not isinstance(checked, dict):
                return decision
            if checked["eventId"] != event_id:
                raise FoundationContractError("change event and neuro envelope event IDs differ")
            if checked["tick"] != _required_int(temporal.get("tick"), "temporal.tick"):
                raise FoundationContractError("change event and neuro envelope ticks differ")
            if checked["sequence"] != _required_int(
                temporal.get("sequence"), "temporal.sequence"
            ):
                raise FoundationContractError("change event and neuro envelope sequences differ")
            return decision
        except FoundationContractError as exc:
            payload_value = event_copy.get("payload") if "event_copy" in locals() else {}
            try:
                payload_hash = canonical_sha256(payload_value)
            except FoundationContractError:
                payload_hash = ZERO_SHA256
            return self._decision(
                event_kind=foundation_kind if isinstance(foundation_kind, str) else "",
                payload_sha256=payload_hash,
                binding=None,
                outcome="quarantined",
                reason="change_event_binding_invalid",
                details={"contractError": str(exc)},
            )

    def record(self, decision: Mapping[str, Any]) -> dict[str, Any]:
        if self.ledger is None:
            raise FoundationPersistenceError("no Foundation ledger configured")
        return dict(self.ledger.append_decision(decision))

    def verify_and_record(self, event_kind: Any, payload: Any, binding: Any) -> dict[str, Any]:
        decision = self.verify(event_kind, payload, binding)
        evidence = self.record(decision)
        return {"decision": decision, "evidence": evidence}

    @staticmethod
    def _missing(payload: Mapping[str, Any], names: tuple[str, ...]) -> list[str]:
        return [name for name in names if payload.get(name) in (None, "")]

    @staticmethod
    def _validate_claim_set(
        payload: Mapping[str, Any], _binding: FoundationBinding
    ) -> ValidatorResult:
        claims = payload.get("claims")
        if not isinstance(claims, list) or not claims or len(claims) > MAX_CLAIMS:
            return "rejected", "claims_list_required", {}
        polarities: dict[tuple[str, str], set[bool]] = {}
        for index, claim in enumerate(claims):
            if not isinstance(claim, Mapping):
                return "rejected", "claim_schema_invalid", {"index": index}
            proposition = claim.get("proposition")
            scope = claim.get("scope")
            polarity = claim.get("polarity")
            if (
                not isinstance(proposition, str)
                or not proposition.strip()
                or len(proposition) > 2_048
                or not isinstance(scope, str)
                or not scope.strip()
                or len(scope) > 256
                or not isinstance(polarity, bool)
            ):
                return "rejected", "claim_schema_invalid", {"index": index}
            polarities.setdefault((proposition, scope), set()).add(polarity)
        conflicts = [
            {"propositionSha256": canonical_sha256(proposition), "scope": scope}
            for (proposition, scope), values in sorted(polarities.items())
            if values == {False, True}
        ]
        if conflicts:
            return "quarantined", "active_contradiction", {"conflicts": conflicts}
        return "accepted", "no_active_contradiction", {"claimCount": len(claims)}

    @staticmethod
    def _validate_artifact(
        payload: Mapping[str, Any], _binding: FoundationBinding
    ) -> ValidatorResult:
        missing = FoundationRuntime._missing(payload, ("content", "content_hash", "source"))
        if (
            missing
            or not isinstance(payload.get("content"), str)
            or not isinstance(payload.get("content_hash"), str)
            or not isinstance(payload.get("source"), str)
        ):
            return "rejected", "artifact_schema_invalid", {"missing": missing}
        content_hash = payload.get("content_hash")
        expected = hashlib.sha256(payload["content"].encode("utf-8")).hexdigest()
        if content_hash not in {expected, f"sha256:{expected}"}:
            return "quarantined", "content_hash_mismatch", {"actualSha256": expected}
        return "accepted", "content_hash_matches_payload", {"contentSha256": expected}

    @staticmethod
    def _valid_number(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and (not isinstance(value, float) or math.isfinite(value))
        )

    @staticmethod
    def _validate_measurement(
        payload: Mapping[str, Any], _binding: FoundationBinding
    ) -> ValidatorResult:
        required = ("value", "unit", "method", "scope", "observed_at", "source")
        missing = FoundationRuntime._missing(payload, required)
        if missing or not FoundationRuntime._valid_number(payload.get("value")):
            return "quarantined", "measurement_context_incomplete", {"missing": missing}
        for field_name in ("method", "scope", "observed_at", "source"):
            value = payload[field_name]
            if not isinstance(value, str) or not value.strip() or len(value) > 512:
                return "quarantined", "measurement_context_invalid", {
                    "field": field_name
                }
        observed_at = payload["observed_at"].replace("Z", "+00:00")
        try:
            observed_instant = datetime.fromisoformat(observed_at)
        except ValueError:
            return "quarantined", "measurement_observed_at_invalid", {}
        if observed_instant.tzinfo is None:
            return "quarantined", "measurement_observed_at_invalid", {}
        if not isinstance(payload["unit"], str) or not _UNIT.fullmatch(payload["unit"]):
            return "quarantined", "measurement_unit_invalid", {}
        uncertainty = payload.get("uncertainty")
        if uncertainty is not None and (
            not FoundationRuntime._valid_number(uncertainty) or float(uncertainty) < 0
        ):
            return "quarantined", "measurement_uncertainty_invalid", {}
        return "accepted", "measurement_context_bound", {
            "scope": payload["scope"],
            "unit": payload["unit"],
        }

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise FoundationContractError("invalid ledger number")
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise FoundationContractError("invalid ledger number") from exc
        if not result.is_finite():
            raise FoundationContractError("invalid ledger number")
        return result

    @staticmethod
    def _validate_resource_ledger(
        payload: Mapping[str, Any], _binding: FoundationBinding
    ) -> ValidatorResult:
        required = ("scope", "initial", "inputs", "outputs", "final")
        missing = FoundationRuntime._missing(payload, required)
        if missing:
            return "quarantined", "ledger_context_incomplete", {"missing": missing}
        if not isinstance(payload["scope"], str) or not payload["scope"].strip():
            return "quarantined", "ledger_scope_invalid", {}
        if payload.get("unknown") is True:
            return "quarantined", "ledger_contains_unknowns", {"scope": payload["scope"]}
        try:
            initial = FoundationRuntime._decimal(payload["initial"])
            inputs = FoundationRuntime._decimal(payload["inputs"])
            outputs = FoundationRuntime._decimal(payload["outputs"])
            final = FoundationRuntime._decimal(payload["final"])
            tolerance = FoundationRuntime._decimal(payload.get("tolerance", 0))
        except FoundationContractError:
            return "rejected", "ledger_values_invalid", {}
        if tolerance < 0:
            return "rejected", "ledger_tolerance_invalid", {}
        residual = initial + inputs - outputs - final
        if abs(residual) > tolerance:
            return "quarantined", "ledger_not_balanced", {
                "residual": str(residual),
                "scope": payload["scope"],
            }
        return "accepted", "resource_ledger_balanced", {
            "residual": str(residual),
            "scope": payload["scope"],
        }

    def _validate_causal_claim(
        self, payload: Mapping[str, Any], binding: FoundationBinding
    ) -> ValidatorResult:
        cause_sequence = _field(payload, "cause_sequence", "cause_seq")
        effect_sequence = _field(payload, "effect_sequence", "effect_seq")
        scope = payload.get("scope")
        if (
            isinstance(cause_sequence, bool)
            or not isinstance(cause_sequence, int)
            or isinstance(effect_sequence, bool)
            or not isinstance(effect_sequence, int)
            or not isinstance(scope, str)
            or not scope
        ):
            return "quarantined", "causal_order_incomplete", {}
        if cause_sequence >= effect_sequence:
            return "quarantined", "causal_precedence_failed", {}
        cause_event_id = _field(payload, "cause_event_id", "causeEventId")
        effect_event_id = _field(payload, "effect_event_id", "effectEventId")
        evidence = payload.get("evidence")
        if (
            not isinstance(cause_event_id, str)
            or not _CANONICAL_ID.fullmatch(cause_event_id)
            or not isinstance(effect_event_id, str)
            or not _CANONICAL_ID.fullmatch(effect_event_id)
            or not isinstance(evidence, list)
            or not evidence
        ):
            return "quarantined", "causal_evidence_missing", {
                "classification": "sequence_only"
            }
        if len(evidence) > MAX_EVIDENCE_REFERENCES:
            return "quarantined", "causal_evidence_count_invalid", {
                "maximum": MAX_EVIDENCE_REFERENCES
            }
        causal_record = {
            "causeEventId": cause_event_id,
            "causeSequence": cause_sequence,
            "effectEventId": effect_event_id,
            "effectSequence": effect_sequence,
            "scope": scope,
        }
        causal_claim_hash = canonical_sha256(causal_record)
        if self.evidence_resolver is None:
            return "quarantined", "authoritative_evidence_resolver_unavailable", {
                "causalClaimHash": causal_claim_hash,
                "classification": "unverified_causal_evidence",
            }

        resolved_ids: set[str] = set()
        failures: list[dict[str, Any]] = []
        for index, reference in enumerate(evidence):
            if not isinstance(reference, Mapping):
                failures.append({"index": index, "reason": "reference_not_object"})
                continue
            event_id = _field(reference, "eventId", "event_id")
            evidence_sha256 = _field(reference, "evidenceSha256", "evidence_sha256")
            try:
                event_id = _required_text(event_id, "eventId", canonical_id=True)
                evidence_sha256 = _required_sha256(evidence_sha256, "evidenceSha256")
            except FoundationContractError:
                failures.append({"index": index, "reason": "reference_invalid"})
                continue
            if event_id in resolved_ids:
                failures.append({"index": index, "reason": "duplicate_event"})
                continue
            resolved_ids.add(event_id)
            try:
                resolved = self.evidence_resolver.resolve_evidence(event_id, evidence_sha256)
            except Exception:
                failures.append({"index": index, "reason": "evidence_resolver_failed"})
                continue
            if not isinstance(resolved, Mapping):
                failures.append({"index": index, "reason": "evidence_not_found"})
                continue
            try:
                receipt = json.loads(canonical_json(resolved))
            except FoundationContractError:
                failures.append({"index": index, "reason": "evidence_contract_invalid"})
                continue
            receipt_hash = receipt.get("evidenceSha256")
            receipt_body = {
                key: value for key, value in receipt.items() if key != "evidenceSha256"
            }
            if (
                receipt.get("schemaVersion") != AUTHORITATIVE_CAUSAL_EVIDENCE_SCHEMA
                or receipt_hash != evidence_sha256
                or canonical_sha256(receipt_body) != evidence_sha256
                or receipt.get("eventId") != event_id
                or receipt.get("causalClaimHash") != causal_claim_hash
                or receipt.get("causeEventId") != cause_event_id
                or receipt.get("causeSequence") != cause_sequence
                or receipt.get("effectEventId") != effect_event_id
                or receipt.get("effectSequence") != effect_sequence
                or receipt.get("scope") != scope
                or receipt.get("requestId") != binding.request_id
                or receipt.get("sessionId") != binding.session_id
                or receipt.get("revisionSha") != binding.revision_sha
                or receipt.get("policySha256") != binding.policy_sha256
                or receipt.get("outcome") != "verified"
                or receipt.get("authoritative") is not True
                or not isinstance(receipt.get("readbackSha256"), str)
                or not _SHA256.fullmatch(receipt["readbackSha256"])
            ):
                failures.append({"index": index, "reason": "evidence_irrelevant"})
        if failures:
            return "quarantined", "causal_evidence_irrelevant", {
                "causalClaimHash": causal_claim_hash,
                "failures": failures,
            }
        return "accepted", "causal_precedence_and_evidence_bound", {
            "causalClaimHash": causal_claim_hash,
            "evidenceCount": len(resolved_ids),
            "scope": scope,
        }

    @staticmethod
    def _validate_rollback(
        payload: Mapping[str, Any], _binding: FoundationBinding
    ) -> ValidatorResult:
        missing = FoundationRuntime._missing(payload, ("origin_event_hash", "compensation"))
        if missing:
            return "rejected", "rollback_binding_missing", {"missing": missing}
        if not isinstance(payload["compensation"], str) or not payload["compensation"].strip():
            return "rejected", "rollback_compensation_invalid", {}
        if payload.get("erase_history") is True:
            return "rejected", "history_erasure_forbidden", {}
        try:
            origin = str(payload["origin_event_hash"])
            _required_sha256(origin.removeprefix("sha256:"), "origin_event_hash")
        except FoundationContractError:
            return "rejected", "rollback_origin_hash_invalid", {}
        return "accepted", "compensation_only", {"originEventHash": origin}

    @staticmethod
    def _validate_work_request(
        payload: Mapping[str, Any], _binding: FoundationBinding
    ) -> ValidatorResult:
        units = payload.get("units")
        max_units = payload.get("max_units")
        missing = FoundationRuntime._missing(payload, ("units", "max_units", "scope"))
        if (
            missing
            or isinstance(units, bool)
            or not isinstance(units, int)
            or isinstance(max_units, bool)
            or not isinstance(max_units, int)
        ):
            return "rejected", "work_budget_schema_invalid", {"missing": missing}
        if units < 0 or max_units < 1:
            return "rejected", "work_budget_invalid", {}
        if not isinstance(payload["scope"], str) or not payload["scope"].strip():
            return "rejected", "work_scope_invalid", {}
        if units > max_units:
            return "quarantined", "work_budget_exceeded", {
                "maximum": max_units,
                "requested": units,
            }
        return "accepted", "work_budget_admitted", {
            "maximum": max_units,
            "requested": units,
        }

    @staticmethod
    def _validate_empirical_claim(
        payload: Mapping[str, Any], _binding: FoundationBinding
    ) -> ValidatorResult:
        missing = FoundationRuntime._missing(payload, ("claim", "source", "scope", "confidence"))
        confidence = payload.get("confidence")
        if missing or not FoundationRuntime._valid_number(confidence):
            return "quarantined", "empirical_claim_context_incomplete", {"missing": missing}
        if any(
            not isinstance(payload[field_name], str) or not payload[field_name].strip()
            for field_name in ("claim", "source", "scope")
        ):
            return "quarantined", "empirical_claim_context_invalid", {}
        if not 0.0 <= float(confidence) <= 1.0:
            return "quarantined", "empirical_claim_confidence_invalid", {}
        return "accepted", "empirical_claim_scoped", {
            "confidence": float(confidence),
            "scope": payload["scope"],
        }

    @staticmethod
    def _validate_person_claim(
        payload: Mapping[str, Any], _binding: FoundationBinding
    ) -> ValidatorResult:
        if payload.get("external_action") is True:
            return "rejected", "external_person_action_forbidden", {"proposalOnly": True}
        assertions = payload.get("assertions", [])
        if not isinstance(assertions, list) or any(not isinstance(item, str) for item in assertions):
            return "rejected", "person_claim_schema_invalid", {"proposalOnly": True}
        protected = {"diagnosis", "identity", "personality", "dialect_classification"}
        if protected.intersection(assertions) or payload.get("evidence_level") in {
            "thin",
            "unknown",
            None,
        }:
            return "quarantined", "personal_certainty_forbidden", {"proposalOnly": True}
        return "accepted", "person_claim_scoped", {"proposalOnly": True}

    @staticmethod
    def _validate_speech_request(
        payload: Mapping[str, Any], _binding: FoundationBinding
    ) -> ValidatorResult:
        if payload.get("external_action") is True:
            return "rejected", "external_speech_action_forbidden", {"proposalOnly": True}
        missing = FoundationRuntime._missing(payload, ("text_hash", "voice_scope", "consent_scope"))
        if missing:
            return "quarantined", "speech_request_context_incomplete", {
                "missing": missing,
                "proposalOnly": True,
            }
        if any(
            not isinstance(payload[field_name], str) or not payload[field_name].strip()
            for field_name in ("voice_scope", "consent_scope")
        ):
            return "quarantined", "speech_request_context_invalid", {
                "proposalOnly": True
            }
        try:
            _required_sha256(str(payload["text_hash"]).removeprefix("sha256:"), "text_hash")
        except FoundationContractError:
            return "quarantined", "speech_text_hash_invalid", {"proposalOnly": True}
        return "accepted", "speech_request_reviewable", {"proposalOnly": True}

    def _validate_candidate_assessment(
        self, payload: Mapping[str, Any], binding: FoundationBinding
    ) -> ValidatorResult:
        if any(payload.get(name) is True for name in ("promote", "activate", "external_action")):
            return "quarantined", "candidate_promotion_forbidden", {
                "promotionAuthorized": False
            }
        candidate = payload.get("candidate")
        references = payload.get("evidence")
        if not isinstance(candidate, Mapping) or not isinstance(references, list):
            return "rejected", "candidate_schema_invalid", {"promotionAuthorized": False}
        if not MIN_CANDIDATE_EVIDENCE <= len(references) <= MAX_EVIDENCE_REFERENCES:
            return "quarantined", "candidate_evidence_count_invalid", {
                "minimum": MIN_CANDIDATE_EVIDENCE,
                "promotionAuthorized": False,
            }

        candidate_record = {
            "action": _field(candidate, "action"),
            "candidateId": _field(candidate, "candidateId", "candidate_id"),
            "ruleId": _field(candidate, "ruleId", "rule_id"),
            "safetyClass": _field(candidate, "safetyClass", "safety_class"),
            "scope": _field(candidate, "scope"),
            "target": _field(candidate, "target"),
        }
        try:
            for field_name, value in candidate_record.items():
                _required_text(value, field_name)
        except FoundationContractError:
            return "rejected", "candidate_schema_invalid", {"promotionAuthorized": False}
        if candidate_record["safetyClass"] != "proposal_only":
            return "rejected", "candidate_must_remain_proposal_only", {
                "promotionAuthorized": False
            }
        candidate_hash = canonical_sha256(candidate_record)
        asserted_candidate_hash = _field(candidate, "candidateHash", "candidate_hash")
        if asserted_candidate_hash != candidate_hash:
            return "quarantined", "candidate_hash_mismatch", {
                "candidateHash": candidate_hash,
                "promotionAuthorized": False,
            }
        if self.evidence_resolver is None:
            return "quarantined", "authoritative_evidence_resolver_unavailable", {
                "candidateHash": candidate_hash,
                "promotionAuthorized": False,
            }

        resolved_ids: set[str] = set()
        failures: list[dict[str, Any]] = []
        for index, reference in enumerate(references):
            if not isinstance(reference, Mapping):
                failures.append({"index": index, "reason": "reference_not_object"})
                continue
            event_id = _field(reference, "eventId", "event_id")
            evidence_sha256 = _field(reference, "evidenceSha256", "evidence_sha256")
            try:
                event_id = _required_text(event_id, "eventId", canonical_id=True)
                evidence_sha256 = _required_sha256(evidence_sha256, "evidenceSha256")
            except FoundationContractError:
                failures.append({"index": index, "reason": "reference_invalid"})
                continue
            if event_id in resolved_ids:
                failures.append({"index": index, "reason": "duplicate_event"})
                continue
            resolved_ids.add(event_id)
            try:
                resolved = self.evidence_resolver.resolve_evidence(event_id, evidence_sha256)
            except Exception:
                failures.append({"index": index, "reason": "evidence_resolver_failed"})
                continue
            if not isinstance(resolved, Mapping):
                failures.append({"index": index, "reason": "evidence_not_found"})
                continue
            try:
                receipt = json.loads(canonical_json(resolved))
            except FoundationContractError:
                failures.append({"index": index, "reason": "evidence_contract_invalid"})
                continue
            receipt_hash = receipt.get("evidenceSha256")
            receipt_body = {key: value for key, value in receipt.items() if key != "evidenceSha256"}
            if (
                receipt.get("schemaVersion") != AUTHORITATIVE_EVIDENCE_SCHEMA
                or receipt_hash != evidence_sha256
                or canonical_sha256(receipt_body) != evidence_sha256
                or receipt.get("eventId") != event_id
                or receipt.get("candidateHash") != candidate_hash
                or receipt.get("ruleId") != candidate_record["ruleId"]
                or receipt.get("scope") != candidate_record["scope"]
                or receipt.get("target") != candidate_record["target"]
                or receipt.get("action") != candidate_record["action"]
                or receipt.get("requestId") != binding.request_id
                or receipt.get("sessionId") != binding.session_id
                or receipt.get("revisionSha") != binding.revision_sha
                or receipt.get("policySha256") != binding.policy_sha256
                or receipt.get("outcome") != "verified"
                or receipt.get("authoritative") is not True
                or not isinstance(receipt.get("readbackSha256"), str)
                or not _SHA256.fullmatch(receipt["readbackSha256"])
            ):
                failures.append({"index": index, "reason": "evidence_irrelevant"})

        if failures:
            return "quarantined", "candidate_evidence_irrelevant", {
                "candidateHash": candidate_hash,
                "failures": failures,
                "promotionAuthorized": False,
            }
        return "accepted", "candidate_evidence_relevant", {
            "candidateHash": candidate_hash,
            "evidenceCount": len(resolved_ids),
            "promotionAuthorized": False,
        }


__all__ = [
    "AUTHORITATIVE_CAUSAL_EVIDENCE_SCHEMA",
    "AUTHORITATIVE_EVIDENCE_SCHEMA",
    "CHANGE_EVENT_SCHEMA",
    "DETERMINISTIC_VERIFICATION_LANE",
    "EvidenceResolver",
    "FOUNDATION_DECISION_SCHEMA",
    "FOUNDATION_LEDGER_SCHEMA",
    "FOUNDATION_SQLITE_APPLICATION_ID",
    "FOUNDATION_SQLITE_SCHEMA",
    "FOUNDATION_SQLITE_USER_VERSION",
    "FoundationBinding",
    "FoundationContractError",
    "FoundationLedger",
    "FoundationPersistenceError",
    "FoundationRuntime",
    "NEURO_ENVELOPE_SCHEMA",
    "SQLiteFoundationLedger",
    "ZERO_SHA256",
    "canonical_json",
    "canonical_sha256",
]
