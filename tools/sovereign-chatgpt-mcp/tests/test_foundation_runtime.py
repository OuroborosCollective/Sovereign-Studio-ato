from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
import stat
import threading

import pytest

from foundation_runtime import (
    AUTHORITATIVE_CAUSAL_EVIDENCE_SCHEMA,
    AUTHORITATIVE_EVIDENCE_SCHEMA,
    FOUNDATION_DECISION_SCHEMA,
    FOUNDATION_SQLITE_APPLICATION_ID,
    FOUNDATION_SQLITE_SCHEMA,
    FOUNDATION_SQLITE_USER_VERSION,
    FoundationPersistenceError,
    FoundationRuntime,
    NEURO_ENVELOPE_SCHEMA,
    SQLiteFoundationLedger,
    ZERO_SHA256,
    canonical_sha256,
)
from neuromorphic_runtime import ChangeEvent


REVISION = "a" * 40
POLICY_HASH = "b" * 64


def _binding(
    payload: dict,
    *,
    event_id: str = "event-001",
    sequence: int = 1,
    tick: int | None = None,
    request_id: str = "request-001",
    session_id: str = "session-001",
    source_event_hash: str | None = None,
) -> dict:
    envelope = {
        "canonical": True,
        "causalParentSha256": "d" * 64,
        "eventId": event_id,
        "lane": "deterministic-verification",
        "payloadSha256": canonical_sha256(payload),
        "policySha256": POLICY_HASH,
        "previousEvidenceSha256": "e" * 64,
        "producerIdentity": "sovereign-nmc-router",
        "revisionSha": REVISION,
        "schemaVersion": NEURO_ENVELOPE_SCHEMA,
        "sequence": sequence,
        "sideChannelReference": "",
        "systemId": "sovereign-studio-ato",
        "tick": sequence if tick is None else tick,
    }
    return {
        "requestId": request_id,
        "sessionId": session_id,
        "source": "nmc-router",
        "sourceEventHash": source_event_hash or canonical_sha256(envelope),
        "envelope": envelope,
    }


def _measurement(value: int = 12) -> dict:
    return {
        "method": "calibrated-sensor",
        "observed_at": "2026-08-14T16:00:00Z",
        "scope": "runtime-canary",
        "source": "sensor-a",
        "uncertainty": 1,
        "unit": "ms",
        "value": value,
    }


class _ReceiptResolver:
    def __init__(self, receipts: list[dict]) -> None:
        self.receipts = {
            (receipt["eventId"], receipt["evidenceSha256"]): receipt
            for receipt in receipts
        }

    def resolve_evidence(self, event_id: str, evidence_sha256: str) -> dict | None:
        return self.receipts.get((event_id, evidence_sha256))


def _candidate() -> tuple[dict, str]:
    record = {
        "action": "recommend-toolchain",
        "candidateId": "candidate-001",
        "ruleId": "rule-001",
        "safetyClass": "proposal_only",
        "scope": "mission-001",
        "target": "tool-selection",
    }
    candidate_hash = canonical_sha256(record)
    return {**record, "candidateHash": candidate_hash}, candidate_hash


def _outcome_receipt(
    index: int,
    candidate_hash: str,
    *,
    request_id: str = "request-001",
    session_id: str = "session-001",
) -> dict:
    body = {
        "action": "recommend-toolchain",
        "authoritative": True,
        "candidateHash": candidate_hash,
        "eventId": f"evidence-{index:03d}",
        "outcome": "verified",
        "policySha256": POLICY_HASH,
        "readbackSha256": f"{index:064x}",
        "requestId": request_id,
        "revisionSha": REVISION,
        "ruleId": "rule-001",
        "schemaVersion": AUTHORITATIVE_EVIDENCE_SCHEMA,
        "scope": "mission-001",
        "sessionId": session_id,
        "target": "tool-selection",
    }
    return {**body, "evidenceSha256": canonical_sha256(body)}


def _causal_receipt(
    *,
    cause_event_id: str = "event-cause",
    cause_sequence: int = 10,
    effect_event_id: str = "event-effect",
    effect_sequence: int = 11,
    scope: str = "deployment-001",
    request_id: str = "request-001",
    session_id: str = "session-001",
) -> dict:
    causal_claim_hash = canonical_sha256(
        {
            "causeEventId": cause_event_id,
            "causeSequence": cause_sequence,
            "effectEventId": effect_event_id,
            "effectSequence": effect_sequence,
            "scope": scope,
        }
    )
    body = {
        "authoritative": True,
        "causalClaimHash": causal_claim_hash,
        "causeEventId": cause_event_id,
        "causeSequence": cause_sequence,
        "effectEventId": effect_event_id,
        "effectSequence": effect_sequence,
        "eventId": "causal-evidence-001",
        "outcome": "verified",
        "policySha256": POLICY_HASH,
        "readbackSha256": "9" * 64,
        "requestId": request_id,
        "revisionSha": REVISION,
        "schemaVersion": AUTHORITATIVE_CAUSAL_EVIDENCE_SCHEMA,
        "scope": scope,
        "sessionId": session_id,
    }
    return {**body, "evidenceSha256": canonical_sha256(body)}


def test_unknown_event_kind_fails_closed_without_registry_fallback() -> None:
    payload = {"anything": "cannot become accepted through a generic validator"}

    result = FoundationRuntime().verify("unknown_kind", payload, _binding(payload))

    assert result["schemaVersion"] == FOUNDATION_DECISION_SCHEMA
    assert result["ok"] is False
    assert result["outcome"] == "quarantined"
    assert result["reason"] == "unknown_event_kind"
    assert result["mayExecute"] is False
    assert result["externalEffects"] == []
    assert "unknown_kind" not in result["details"]["allowedKinds"]


def test_contradiction_is_quarantined_and_never_reported_ok() -> None:
    payload = {
        "claims": [
            {"polarity": True, "proposition": "service-is-healthy", "scope": "runtime-a"},
            {"polarity": False, "proposition": "service-is-healthy", "scope": "runtime-a"},
        ]
    }

    result = FoundationRuntime().verify("claim_set", payload, _binding(payload))

    assert result["ok"] is False
    assert result["outcome"] == "quarantined"
    assert result["reason"] == "active_contradiction"
    assert result["details"]["conflicts"] == [
        {
            "propositionSha256": canonical_sha256("service-is-healthy"),
            "scope": "runtime-a",
        }
    ]


def test_incomplete_measurement_is_quarantined() -> None:
    payload = {"value": 42, "unit": "ms"}

    result = FoundationRuntime().verify("measurement", payload, _binding(payload))

    assert result["ok"] is False
    assert result["reason"] == "measurement_context_incomplete"
    assert set(result["details"]["missing"]) == {
        "method",
        "observed_at",
        "scope",
        "source",
    }


def test_causal_sequence_without_bound_evidence_stays_quarantined() -> None:
    payload = {
        "cause_event_id": "event-cause",
        "cause_sequence": 10,
        "effect_event_id": "event-effect",
        "effect_sequence": 11,
        "scope": "deployment-001",
    }

    result = FoundationRuntime().verify("causal_claim", payload, _binding(payload))

    assert result["ok"] is False
    assert result["outcome"] == "quarantined"
    assert result["reason"] == "causal_evidence_missing"
    assert result["details"]["classification"] == "sequence_only"


def test_causal_claim_rejects_self_asserted_hash_without_authoritative_resolution() -> None:
    payload = {
        "cause_event_id": "event-cause",
        "cause_sequence": 10,
        "effect_event_id": "event-effect",
        "effect_sequence": 11,
        "scope": "deployment-001",
        "evidence": [
            {
                "eventId": "causal-evidence-001",
                "evidenceSha256": "9" * 64,
            }
        ],
    }

    result = FoundationRuntime().verify("causal_claim", payload, _binding(payload))

    assert result["ok"] is False
    assert result["outcome"] == "quarantined"
    assert result["reason"] == "authoritative_evidence_resolver_unavailable"
    assert result["details"]["classification"] == "unverified_causal_evidence"


def test_causal_claim_denies_hash_valid_but_irrelevant_authoritative_evidence() -> None:
    receipt = _causal_receipt(scope="another-deployment")
    payload = {
        "cause_event_id": "event-cause",
        "cause_sequence": 10,
        "effect_event_id": "event-effect",
        "effect_sequence": 11,
        "scope": "deployment-001",
        "evidence": [
            {
                "eventId": receipt["eventId"],
                "evidenceSha256": receipt["evidenceSha256"],
            }
        ],
    }

    result = FoundationRuntime(evidence_resolver=_ReceiptResolver([receipt])).verify(
        "causal_claim", payload, _binding(payload)
    )

    assert result["ok"] is False
    assert result["outcome"] == "quarantined"
    assert result["reason"] == "causal_evidence_irrelevant"
    assert result["details"]["failures"] == [
        {"index": 0, "reason": "evidence_irrelevant"}
    ]


def test_causal_claim_accepts_only_fully_bound_authoritative_evidence() -> None:
    receipt = _causal_receipt()
    payload = {
        "cause_event_id": "event-cause",
        "cause_sequence": 10,
        "effect_event_id": "event-effect",
        "effect_sequence": 11,
        "scope": "deployment-001",
        "evidence": [
            {
                "eventId": receipt["eventId"],
                "evidenceSha256": receipt["evidenceSha256"],
            }
        ],
    }

    result = FoundationRuntime(evidence_resolver=_ReceiptResolver([receipt])).verify(
        "causal_claim", payload, _binding(payload)
    )

    assert result["ok"] is True
    assert result["reason"] == "causal_precedence_and_evidence_bound"
    assert result["details"]["evidenceCount"] == 1
    assert result["mayExecute"] is False
    assert result["externalEffects"] == []


def test_candidate_denies_unrelated_authoritative_evidence() -> None:
    candidate, candidate_hash = _candidate()
    receipts = [
        _outcome_receipt(1, candidate_hash),
        _outcome_receipt(2, candidate_hash),
        _outcome_receipt(3, "f" * 64),
    ]
    payload = {
        "candidate": candidate,
        "evidence": [
            {"eventId": receipt["eventId"], "evidenceSha256": receipt["evidenceSha256"]}
            for receipt in receipts
        ],
    }

    result = FoundationRuntime(
        evidence_resolver=_ReceiptResolver(receipts)
    ).verify("candidate_assessment", payload, _binding(payload))

    assert result["ok"] is False
    assert result["outcome"] == "quarantined"
    assert result["reason"] == "candidate_evidence_irrelevant"
    assert result["details"]["promotionAuthorized"] is False
    assert result["details"]["failures"] == [
        {"index": 2, "reason": "evidence_irrelevant"}
    ]


def test_candidate_relevance_can_be_verified_but_never_promoted_or_executed() -> None:
    candidate, candidate_hash = _candidate()
    receipts = [_outcome_receipt(index, candidate_hash) for index in range(1, 4)]
    payload = {
        "candidate": candidate,
        "evidence": [
            {"eventId": receipt["eventId"], "evidenceSha256": receipt["evidenceSha256"]}
            for receipt in receipts
        ],
    }

    result = FoundationRuntime(
        evidence_resolver=_ReceiptResolver(receipts)
    ).verify("candidate_assessment", payload, _binding(payload))

    assert result["ok"] is True
    assert result["reason"] == "candidate_evidence_relevant"
    assert result["details"]["evidenceCount"] == 3
    assert result["details"]["promotionAuthorized"] is False
    assert result["mayExecute"] is False
    assert result["externalEffects"] == []


def test_verify_is_pure_deterministic_and_does_not_implicitly_persist(tmp_path: Path) -> None:
    ledger = SQLiteFoundationLedger(str(tmp_path / "foundation.sqlite"))
    runtime = FoundationRuntime(ledger=ledger)
    payload = _measurement()
    binding = _binding(payload)

    first = runtime.verify("measurement", payload, binding)
    second = runtime.verify("measurement", payload, binding)

    assert first == second
    assert first["ok"] is True
    assert first["payloadSha256"] == canonical_sha256(payload)
    assert ledger.count() == 0
    assert ledger.verify_chain() == {
        "valid": True,
        "entries": 0,
        "head": ZERO_SHA256,
        "reason": "verified",
    }

    persisted = runtime.record(first)
    assert persisted["replayed"] is False
    assert ledger.count() == 1
    replay = runtime.record(second)
    assert replay["replayed"] is True
    assert replay["evidenceSha256"] == persisted["evidenceSha256"]
    assert ledger.count() == 1


def test_sqlite_storage_contract_is_hardened_and_schema_bound(tmp_path: Path) -> None:
    database = tmp_path / "foundation.sqlite"
    database.touch(mode=0o666)

    ledger = SQLiteFoundationLedger(str(database))

    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    connection = ledger._connect()
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert connection.execute("PRAGMA trusted_schema").fetchone()[0] == 0
        assert connection.execute("PRAGMA application_id").fetchone()[0] == FOUNDATION_SQLITE_APPLICATION_ID
        assert connection.execute("PRAGMA user_version").fetchone()[0] == FOUNDATION_SQLITE_USER_VERSION
        assert connection.execute(
            "SELECT value FROM foundation_metadata WHERE key='schema_identity'"
        ).fetchone()[0] == FOUNDATION_SQLITE_SCHEMA
    finally:
        connection.close()


def test_sqlite_read_only_open_verifies_without_chmod_or_file_mutation(tmp_path: Path) -> None:
    database = tmp_path / "foundation.sqlite"
    writable = SQLiteFoundationLedger(str(database))
    runtime = FoundationRuntime(ledger=writable)
    payload = _measurement()
    runtime.verify_and_record("measurement", payload, _binding(payload))
    os.chmod(database, 0o640)
    before = database.read_bytes()
    before_status = database.stat()

    readonly = SQLiteFoundationLedger.open_read_only(str(database))

    assert readonly.verify_chain()["valid"] is True
    assert readonly.count() == 1
    assert database.read_bytes() == before
    after_status = database.stat()
    assert after_status.st_mtime_ns == before_status.st_mtime_ns
    assert stat.S_IMODE(after_status.st_mode) == 0o640
    with pytest.raises(FoundationPersistenceError, match="read-only"):
        readonly.append_decision(runtime.verify("measurement", payload, _binding(payload)))


def test_sqlite_rejects_unidentified_existing_database(tmp_path: Path) -> None:
    database = tmp_path / "foreign.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE unrelated(value TEXT)")

    with pytest.raises(FoundationPersistenceError, match="identity|schema"):
        SQLiteFoundationLedger(str(database))


def test_sqlite_rejects_schema_version_or_identity_tamper(tmp_path: Path) -> None:
    database = tmp_path / "foundation.sqlite"
    SQLiteFoundationLedger(str(database))
    with sqlite3.connect(database) as connection:
        connection.execute(f"PRAGMA user_version = {FOUNDATION_SQLITE_USER_VERSION + 1}")

    with pytest.raises(FoundationPersistenceError, match="schema version"):
        SQLiteFoundationLedger(str(database))

    with sqlite3.connect(database) as connection:
        connection.execute(f"PRAGMA user_version = {FOUNDATION_SQLITE_USER_VERSION}")
        connection.execute(
            "UPDATE foundation_metadata SET value='foreign.schema' WHERE key='schema_identity'"
        )

    with pytest.raises(FoundationPersistenceError, match="schema identity"):
        SQLiteFoundationLedger(str(database))


@pytest.mark.parametrize(
    ("pragma", "tampered_value", "message"),
    [
        ("user_version", FOUNDATION_SQLITE_USER_VERSION + 1, "schema version"),
        ("application_id", FOUNDATION_SQLITE_APPLICATION_ID + 1, "application identity"),
    ],
)
def test_sqlite_read_only_open_rejects_header_identity_tamper(
    tmp_path: Path,
    pragma: str,
    tampered_value: int,
    message: str,
) -> None:
    database = tmp_path / "foundation.sqlite"
    SQLiteFoundationLedger(str(database))
    with sqlite3.connect(database) as connection:
        connection.execute(f"PRAGMA {pragma} = {tampered_value}")

    before = database.read_bytes()
    before_mtime = database.stat().st_mtime_ns
    with pytest.raises(FoundationPersistenceError, match=message):
        SQLiteFoundationLedger.open_read_only(str(database))
    assert database.read_bytes() == before
    assert database.stat().st_mtime_ns == before_mtime


@pytest.mark.parametrize("tamper", ["extra-check", "changed-unique", "trigger", "view"])
def test_sqlite_rejects_exact_schema_and_object_tamper(
    tmp_path: Path,
    tamper: str,
) -> None:
    database = tmp_path / f"foundation-{tamper}.sqlite"
    if tamper in {"trigger", "view"}:
        SQLiteFoundationLedger(str(database))
        with sqlite3.connect(database) as attacker:
            if tamper == "trigger":
                attacker.execute(
                    """
                    CREATE TRIGGER foundation_shadow_trigger
                    AFTER INSERT ON foundation_evidence BEGIN SELECT 1; END
                    """
                )
            else:
                attacker.execute(
                    "CREATE VIEW foundation_shadow_view AS SELECT * FROM foundation_evidence"
                )
    else:
        extra_check = ", CHECK(event_id='forged-only')" if tamper == "extra-check" else ""
        unique_columns = (
            "UNIQUE(event_id, session_id, request_id)"
            if tamper == "changed-unique"
            else "UNIQUE(request_id, session_id, event_id)"
        )
        with sqlite3.connect(database) as attacker:
            attacker.execute("PRAGMA journal_mode=WAL")
            attacker.execute(
                "CREATE TABLE foundation_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            attacker.execute(
                "INSERT INTO foundation_metadata(key,value) VALUES('schema_identity', ?)",
                (FOUNDATION_SQLITE_SCHEMA,),
            )
            attacker.execute(
                f"""
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
                    {unique_columns}{extra_check}
                )
                """
            )
            attacker.execute(f"PRAGMA application_id={FOUNDATION_SQLITE_APPLICATION_ID}")
            attacker.execute(f"PRAGMA user_version={FOUNDATION_SQLITE_USER_VERSION}")

    with pytest.raises(FoundationPersistenceError, match="object|SQL|index"):
        SQLiteFoundationLedger.open_read_only(str(database))
    with pytest.raises(FoundationPersistenceError, match="object|SQL|index"):
        SQLiteFoundationLedger(str(database))


def test_same_bound_event_cannot_be_replayed_with_another_decision(tmp_path: Path) -> None:
    ledger = SQLiteFoundationLedger(str(tmp_path / "foundation.sqlite"))
    runtime = FoundationRuntime(ledger=ledger)
    accepted_payload = _measurement()
    quarantined_payload = {"value": 7, "unit": "ms"}
    # The mismatch is deliberately forged after verification to exercise the
    # ledger's final event-identity boundary, not an application-level shortcut.
    first = runtime.verify("measurement", accepted_payload, _binding(accepted_payload))
    second = runtime.verify(
        "measurement",
        quarantined_payload,
        _binding(quarantined_payload),
    )
    runtime.record(first)

    with pytest.raises(FoundationPersistenceError, match="another decision"):
        runtime.record(second)


def test_sqlite_append_is_transactional_under_concurrency(tmp_path: Path) -> None:
    ledger = SQLiteFoundationLedger(str(tmp_path / "foundation.sqlite"))
    runtime = FoundationRuntime(ledger=ledger)

    def write(index: int) -> dict:
        payload = _measurement(index)
        binding = _binding(
            payload,
            event_id=f"event-{index:03d}",
            sequence=index,
            tick=index,
        )
        return runtime.verify_and_record("measurement", payload, binding)

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(write, range(1, 65)))

    assert all(item["decision"]["ok"] is True for item in results)
    assert ledger.count() == 64
    chain = ledger.verify_chain()
    assert chain["valid"] is True
    assert chain["entries"] == 64
    assert chain["reason"] == "verified"


def test_sqlite_initialization_is_safe_across_concurrent_instances(tmp_path: Path) -> None:
    database = tmp_path / "foundation.sqlite"
    workers = 8
    barrier = threading.Barrier(workers)

    def initialize(_index: int) -> int:
        barrier.wait()
        return SQLiteFoundationLedger(str(database)).count()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        counts = list(executor.map(initialize, range(workers)))

    assert counts == [0] * workers
    assert SQLiteFoundationLedger.open_read_only(str(database)).verify_chain()["valid"] is True


def test_chain_verification_detects_persisted_content_tamper(tmp_path: Path) -> None:
    database = tmp_path / "foundation.sqlite"
    ledger = SQLiteFoundationLedger(str(database))
    runtime = FoundationRuntime(ledger=ledger)
    payload = _measurement()
    runtime.verify_and_record("measurement", payload, _binding(payload))

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE foundation_evidence SET decision_json = ? WHERE sequence = 1",
            ('{"tampered":true}',),
        )
        connection.commit()

    result = ledger.verify_chain()
    assert result["valid"] is False
    assert result["sequence"] == 1
    assert result["reason"] == "stored_decision_hash_mismatch"


def _valid_change_event() -> dict:
    payload = _measurement()
    return ChangeEvent.create(
        event_id="event-001",
        system_id="sovereign-studio-ato",
        revision_sha=REVISION,
        policy_sha256=POLICY_HASH,
        lane="deterministic-verification",
        tick=1,
        sequence=1,
        event_time="2026-08-14T16:00:00Z",
        delta_ms=100,
        kind="sensor.change",
        source="nmc-router",
        entity="sensor-a",
        field="latency",
        old_hash="2" * 64,
        new_hash="1" * 64,
        magnitude=12,
        previous_evidence_sha256="3" * 64,
        causal_parent_sha256="4" * 64,
        producer_identity="sovereign-nmc-router",
        canonical=True,
        payload=payload,
    ).to_dict()


def test_change_event_port_binds_hash_tick_sequence_and_payload_without_kind_collision() -> None:
    event = _valid_change_event()

    result = FoundationRuntime().verify_change_event(
        event,
        foundation_kind="measurement",
        request_id="request-001",
        session_id="session-001",
    )

    assert result["ok"] is True
    assert result["eventKind"] == "measurement"
    assert result["binding"]["sourceEventHash"] == event["eventHash"]
    assert result["binding"]["tick"] == event["temporal"]["tick"]
    assert result["binding"]["sequence"] == event["temporal"]["sequence"]


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("kind", "unknown.change"),
        ("oldHash", "not-a-sha256"),
        ("temporal.eventTime", "not-an-rfc3339-time"),
        ("magnitude", -1),
    ],
)
def test_change_event_port_rejects_self_consistent_but_structurally_invalid_events(
    field: str,
    invalid_value: object,
) -> None:
    event = _valid_change_event()
    if field.startswith("temporal."):
        event["temporal"][field.removeprefix("temporal.")] = invalid_value
    else:
        event[field] = invalid_value

    # Recompute both hashes to prove the port is using the canonical ChangeEvent
    # parser rather than accepting any merely self-consistent JSON mapping.
    source_payload = {
        key: value for key, value in event.items() if key not in {"envelope", "eventHash"}
    }
    event["envelope"]["payloadSha256"] = canonical_sha256(source_payload)
    event["eventHash"] = canonical_sha256(event["envelope"])

    result = FoundationRuntime().verify_change_event(
        event,
        foundation_kind="measurement",
        request_id="request-001",
        session_id="session-001",
    )

    assert result["ok"] is False
    assert result["outcome"] == "quarantined"
    assert result["reason"] == "change_event_binding_invalid"
    assert result["binding"] is None
    assert "invalid canonical ChangeEvent" in result["details"]["contractError"]
