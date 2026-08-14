from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

import pytest

from neuromorphic_runtime import (
    ZERO_SHA256,
    CandidateReceipt,
    ChangeEvent,
    ChainIntegrityError,
    ContractError,
    CrossSourceReplayError,
    DeltaDetector,
    NeuromorphicLedger,
    LedgerReadOnlyError,
    LedgerQuota,
    LedgerQuotaExceededError,
    NeuromorphicRuntimeError,
    QuantizedSpikeFilter,
    RelevanceGate,
    ResourceHomeostat,
    SequenceConflictError,
    TemporalEnvelope,
    TemporalOrderError,
    UnknownEventKindError,
    canonical_json,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CANONICAL_CONTRACT_PATH = REPOSITORY_ROOT / "backend" / "agent_runtime" / "neuro_architecture_contract.py"
_CONTRACT_SPEC = importlib.util.spec_from_file_location(
    "sovereign_canonical_neuro_contract_for_test",
    CANONICAL_CONTRACT_PATH,
)
assert _CONTRACT_SPEC is not None and _CONTRACT_SPEC.loader is not None
_CANONICAL_CONTRACT = importlib.util.module_from_spec(_CONTRACT_SPEC)
sys.modules[_CONTRACT_SPEC.name] = _CANONICAL_CONTRACT
_CONTRACT_SPEC.loader.exec_module(_CANONICAL_CONTRACT)
EvidenceEnvelope = _CANONICAL_CONTRACT.EvidenceEnvelope
Lane = _CANONICAL_CONTRACT.Lane


REVISION_SHA = "a" * 40
POLICY_SHA256 = "b" * 64
BASE_TIME = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


def _first_open_worker(database_path: str) -> bool:
    with NeuromorphicLedger(database_path) as ledger:
        return ledger.verify_integrity().ok


def _event(
    *,
    event_id: str,
    source: str,
    sequence: int,
    tick: int,
    previous_hash: str,
    magnitude: int = 5,
    delta_ms: int | None = None,
    event_time: datetime | None = None,
    entity: str = "runtime.agent",
    field: str = "health",
    kind: str = "runtime.change",
) -> ChangeEvent:
    instant = event_time or (BASE_TIME + timedelta(milliseconds=sequence * 100))
    if delta_ms is None:
        delta_ms = 0 if sequence == 0 else 100
    old_hash = (f"{sequence:064x}" if sequence else ZERO_SHA256)[-64:]
    new_hash = f"{sequence + 1:064x}"[-64:]
    return ChangeEvent.create(
        event_id=event_id,
        system_id="sovereign-studio-ato",
        revision_sha=REVISION_SHA,
        policy_sha256=POLICY_SHA256,
        lane="sensory-intake",
        tick=tick,
        sequence=sequence,
        event_time=instant,
        delta_ms=delta_ms,
        kind=kind,
        source=source,
        entity=entity,
        field=field,
        old_hash=old_hash,
        new_hash=new_hash,
        magnitude=magnitude,
        previous_evidence_sha256=previous_hash,
        causal_parent_sha256=ZERO_SHA256,
        producer_identity="sovereign.test-producer",
        canonical=False,
        payload={"boundedEvidence": f"evidence-{sequence}"},
    )


def test_change_event_projects_exact_canonical_neuro_event_identity() -> None:
    event = _event(
        event_id="event.compatibility-000",
        source="runtime.primary",
        sequence=0,
        tick=7,
        previous_hash=ZERO_SHA256,
    )
    canonical = EvidenceEnvelope(
        schema_version="sovereign.neuro-architecture-envelope.v1",
        system_id=event.identity.system_id,
        revision_sha=event.identity.revision_sha,
        policy_sha256=event.identity.policy_sha256,
        event_id=event.event_id,
        lane=Lane(event.identity.lane),
        tick=event.tick,
        sequence=event.sequence,
        payload_sha256=event.identity.payload_sha256,
        causal_parent_sha256=event.identity.causal_parent_sha256,
        previous_evidence_sha256=event.previous_hash,
        producer_identity=event.identity.producer_identity,
        canonical=event.identity.canonical,
        side_channel_reference=event.identity.side_channel_reference,
    )

    assert event.identity.canonical_record() == canonical.canonical_record()
    assert event.event_hash == canonical.evidence_sha256()
    assert ChangeEvent.from_dict(event.to_dict()) == event


def test_contract_fails_closed_for_unknown_kind_time_and_tampered_hash() -> None:
    with pytest.raises(UnknownEventKindError):
        _event(
            event_id="event.unknown-kind",
            source="runtime.primary",
            sequence=0,
            tick=0,
            previous_hash=ZERO_SHA256,
            kind="unknown.change",
        )

    with pytest.raises(ContractError, match="event_time"):
        TemporalEnvelope(tick=0, sequence=0, event_time="2026-08-14T12:00:00", delta_ms=0)

    event = _event(
        event_id="event.tampered-transport",
        source="runtime.primary",
        sequence=0,
        tick=0,
        previous_hash=ZERO_SHA256,
    )
    tampered = event.to_dict()
    tampered["magnitude"] = 99
    with pytest.raises(ContractError, match="payloadSha256"):
        ChangeEvent.from_dict(tampered)

    for field in ("tick", "sequence", "delta_ms", "magnitude"):
        arguments = {
            "event_id": f"event.int64-{field}",
            "source": "runtime.primary",
            "sequence": 0,
            "tick": 0,
            "previous_hash": ZERO_SHA256,
            "event_time": BASE_TIME,
        }
        if field == "delta_ms":
            arguments["delta_ms"] = 2**63
        elif field == "magnitude":
            arguments["magnitude"] = 2**63
        else:
            arguments[field] = 2**63
        with pytest.raises(ContractError, match="64-bit"):
            _event(**arguments)


def test_delta_detector_and_irrelevant_event_create_no_effect_receipt(tmp_path: Path) -> None:
    unchanged = DeltaDetector.detect({"value": 1}, {"value": 1})
    changed = DeltaDetector.detect({"value": 1}, {"value": 2}, magnitude=1)
    assert unchanged.changed is False and unchanged.magnitude == 0
    assert changed.changed is True and changed.old_hash != changed.new_hash

    event = _event(
        event_id="event.irrelevant-000",
        source="runtime.primary",
        sequence=0,
        tick=0,
        previous_hash=ZERO_SHA256,
        magnitude=1,
    )
    with NeuromorphicLedger(tmp_path / "nmc.sqlite") as ledger:
        receipt = ledger.ingest(event, RelevanceGate(default_threshold=2))

        assert isinstance(receipt, CandidateReceipt)
        assert receipt.decision == "discarded"
        assert receipt.relevant is False
        assert receipt.may_execute is False
        assert receipt.external_effects == ()
        assert receipt.projection_updated is False
        assert ledger.read_projection(event.source, event.entity, event.field) is None

        metrics = ledger.metrics()
        assert metrics.observed_events == 1
        assert metrics.relevant_events == 0
        assert metrics.discarded_events == 1
        assert metrics.projection_updates == 0
        assert metrics.reduction_rate_ppm == 1_000_000


def test_relevant_event_updates_projection_incrementally_after_discard(tmp_path: Path) -> None:
    first = _event(
        event_id="event.discarded-000",
        source="runtime.primary",
        sequence=0,
        tick=10,
        previous_hash=ZERO_SHA256,
        magnitude=0,
    )
    second = _event(
        event_id="event.relevant-001",
        source="runtime.primary",
        sequence=1,
        tick=11,
        previous_hash=first.event_hash,
        magnitude=4,
    )
    with NeuromorphicLedger(tmp_path / "nmc.sqlite") as ledger:
        assert ledger.ingest(first, RelevanceGate(default_threshold=1)).decision == "discarded"
        receipt = ledger.ingest(second, RelevanceGate(default_threshold=1))

        assert receipt.decision == "candidate"
        assert receipt.may_execute is False
        projection = ledger.read_projection(second.source, second.entity, second.field)
        assert projection is not None
        assert projection.event_id == second.event_id
        assert projection.value_hash == second.new_hash
        assert projection.sequence == 1
        metrics = ledger.metrics()
        assert metrics.observed_events == 2
        assert metrics.projection_updates == 1


def test_exact_replay_is_idempotent_and_cross_source_or_sequence_replay_fails(tmp_path: Path) -> None:
    event = _event(
        event_id="event.replay-000",
        source="runtime.primary",
        sequence=0,
        tick=0,
        previous_hash=ZERO_SHA256,
    )
    with NeuromorphicLedger(tmp_path / "nmc.sqlite") as ledger:
        original = ledger.ingest(event)
        replay = ledger.ingest(event)
        assert original.replayed is False
        assert replay.replayed is True
        assert replay.receipt_hash == original.receipt_hash
        assert ledger.metrics().observed_events == 1
        assert ledger.metrics().replay_requests == 1

        cross_source = _event(
            event_id=event.event_id,
            source="runtime.secondary",
            sequence=0,
            tick=0,
            previous_hash=ZERO_SHA256,
        )
        with pytest.raises(CrossSourceReplayError):
            ledger.ingest(cross_source)

        sequence_collision = _event(
            event_id="event.sequence-collision",
            source=event.source,
            sequence=0,
            tick=0,
            previous_hash=ZERO_SHA256,
        )
        with pytest.raises(SequenceConflictError):
            ledger.ingest(sequence_collision)


def test_ingest_next_allocates_and_replays_inside_one_transaction(tmp_path: Path) -> None:
    arguments = {
        "event_id": "event.atomic-next",
        "system_id": "sovereign-studio-ato",
        "revision_sha": REVISION_SHA,
        "policy_sha256": POLICY_SHA256,
        "lane": "sensory-intake",
        "tick": 10,
        "event_time": BASE_TIME,
        "kind": "tool.outcome",
        "source": "runtime.tool-outcomes",
        "entity": "tool.repository-read",
        "field": "outcome",
        "old_hash": ZERO_SHA256,
        "new_hash": "c" * 64,
        "magnitude": 1,
        "causal_parent_sha256": ZERO_SHA256,
        "producer_identity": "sovereign.tool-outcome-adapter",
        "canonical": False,
        "payload": {"status": "COMPLETED"},
    }
    with NeuromorphicLedger(tmp_path / "nmc.sqlite") as ledger:
        event, receipt = ledger.ingest_next(**arguments)
        replay_event, replay_receipt = ledger.ingest_next(**arguments)

        assert event.sequence == 0
        assert replay_event == event
        assert replay_receipt.replayed is True
        assert replay_receipt.receipt_hash == receipt.receipt_hash
        assert ledger.metrics().observed_events == 1
        assert ledger.metrics().replay_requests == 1


def test_temporal_window_is_bounded_ordered_and_source_scoped(tmp_path: Path) -> None:
    with NeuromorphicLedger(tmp_path / "nmc.sqlite", max_window_size=4) as ledger:
        previous = ZERO_SHA256
        expected: list[ChangeEvent] = []
        for sequence in range(5):
            event = _event(
                event_id=f"event.window-{sequence:03d}",
                source="runtime.primary",
                sequence=sequence,
                tick=sequence + 20,
                previous_hash=previous,
            )
            ledger.ingest(event)
            previous = event.event_hash
            expected.append(event)

        other = _event(
            event_id="event.other-source",
            source="runtime.secondary",
            sequence=0,
            tick=22,
            previous_hash=ZERO_SHA256,
        )
        ledger.ingest(other)

        window = ledger.query_window("runtime.primary", start_tick=21, end_tick=23, limit=3)
        assert [event.event_id for event in window.events] == [
            expected[1].event_id,
            expected[2].event_id,
            expected[3].event_id,
        ]
        assert window.source == "runtime.primary"
        assert window.window_hash == window.recompute_hash()
        assert all(event.source == "runtime.primary" for event in window.events)

        with pytest.raises(ContractError, match="limit"):
            ledger.query_window("runtime.primary", start_tick=0, end_tick=30, limit=5)
        with pytest.raises(ContractError, match="tick window"):
            ledger.query_window("runtime.primary", start_tick=30, end_tick=20, limit=1)


def test_thread_safe_wal_transactions_preserve_128_event_chains(tmp_path: Path) -> None:
    database_path = tmp_path / "nmc.sqlite"
    with NeuromorphicLedger(database_path) as ledger:
        assert ledger.journal_mode == "wal"

        def append_event(index: int) -> tuple[int, str]:
            event, receipt = ledger.ingest_next(
                event_id=f"event.concurrent-{index:03d}",
                system_id="sovereign-studio-ato",
                revision_sha=REVISION_SHA,
                policy_sha256=POLICY_SHA256,
                lane="sensory-intake",
                tick=50,
                event_time=BASE_TIME,
                kind="tool.outcome",
                source="runtime.concurrent",
                entity=f"tool.worker-{index:03d}",
                field="outcome",
                old_hash=ZERO_SHA256,
                new_hash=f"{index + 1:064x}"[-64:],
                magnitude=1,
                causal_parent_sha256=ZERO_SHA256,
                producer_identity="sovereign.test-producer",
                canonical=False,
                payload={"outcomeIndex": index},
            )
            return event.sequence, receipt.receipt_hash

        with ThreadPoolExecutor(max_workers=16) as pool:
            appended = list(pool.map(append_event, range(128)))

        assert sorted(sequence for sequence, _ in appended) == list(range(128))
        assert len({receipt for _, receipt in appended}) == 128
        metrics = ledger.metrics()
        assert metrics.observed_events == 128
        assert metrics.relevant_events == 128
        assert metrics.projection_updates == 128
        head = ledger.read_head("runtime.concurrent")
        assert head is not None and head.last_sequence == 127
        report = ledger.verify_integrity()
        assert report.ok is True
        assert report.event_count == 128
        assert report.source_count == 1


def test_global_quota_is_transactional_across_connections_and_sources(tmp_path: Path) -> None:
    database_path = tmp_path / "quota-concurrent.sqlite"
    with NeuromorphicLedger(database_path):
        pass
    quota = LedgerQuota(max_events=1, max_bytes=64 * 1024 * 1024)

    def append_from_source(index: int) -> str:
        event = _event(
            event_id=f"event.quota-source-{index:03d}",
            source=f"runtime.quota-source-{index:03d}",
            sequence=0,
            tick=index,
            previous_hash=ZERO_SHA256,
        )
        try:
            with NeuromorphicLedger(database_path) as ledger:
                ledger.ingest(event, quota=quota)
        except LedgerQuotaExceededError:
            return "quota"
        return "committed"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(append_from_source, range(16)))
    assert outcomes.count("committed") == 1
    assert outcomes.count("quota") == 15
    with NeuromorphicLedger(database_path) as ledger:
        assert ledger.verify_integrity().event_count == 1
        assert ledger.metrics().observed_events == 1


def test_quota_allows_exact_replay_and_byte_rejection_rolls_back(tmp_path: Path) -> None:
    database_path = tmp_path / "quota-replay.sqlite"
    event = _event(
        event_id="event.quota-replay",
        source="runtime.quota-replay",
        sequence=0,
        tick=0,
        previous_hash=ZERO_SHA256,
    )
    with NeuromorphicLedger(database_path) as ledger:
        quota = LedgerQuota(max_events=1, max_bytes=64 * 1024 * 1024)
        receipt = ledger.ingest(event, quota=quota)
        replay = ledger.ingest(event, quota=quota)
        assert replay.replayed is True
        assert replay.receipt_hash == receipt.receipt_hash
        assert ledger.metrics().observed_events == 1

    byte_path = tmp_path / "quota-bytes.sqlite"
    with NeuromorphicLedger(byte_path) as ledger:
        too_small = LedgerQuota(
            max_events=10,
            max_bytes=ledger._database_family_bytes() + 1,
        )
        with pytest.raises(LedgerQuotaExceededError, match="byte quota"):
            ledger.ingest(event, quota=too_small)
        assert ledger.metrics().observed_events == 0
        assert ledger.verify_integrity().event_count == 0


def test_integrity_readback_detects_persisted_event_tampering(tmp_path: Path) -> None:
    database_path = tmp_path / "nmc.sqlite"
    event = _event(
        event_id="event.integrity-000",
        source="runtime.primary",
        sequence=0,
        tick=0,
        previous_hash=ZERO_SHA256,
    )
    with NeuromorphicLedger(database_path) as ledger:
        ledger.ingest(event)
        record = event.to_dict()
        record["payload"]["boundedEvidence"] = "tampered"
        with sqlite3.connect(database_path) as attacker:
            attacker.execute(
                "UPDATE change_events SET canonical_event = ? WHERE event_id = ?",
                (canonical_json(record), event.event_id),
            )
            attacker.commit()

        with pytest.raises(ChainIntegrityError):
            ledger.verify_integrity()


@pytest.mark.parametrize("mutation", ["missing", "extra", "tampered"])
def test_integrity_readback_detects_projection_drift(tmp_path: Path, mutation: str) -> None:
    database_path = tmp_path / f"projection-{mutation}.sqlite"
    event = _event(
        event_id=f"event.projection-{mutation}",
        source="runtime.primary",
        sequence=0,
        tick=3,
        previous_hash=ZERO_SHA256,
    )
    with NeuromorphicLedger(database_path) as ledger:
        ledger.ingest(event)
        with sqlite3.connect(database_path) as attacker:
            if mutation == "missing":
                attacker.execute(
                    "DELETE FROM projections WHERE source = ? AND entity = ? AND field = ?",
                    (event.source, event.entity, event.field),
                )
            elif mutation == "extra":
                attacker.execute(
                    """
                    INSERT INTO projections(
                        source, entity, field, event_id, event_hash, value_hash,
                        tick, sequence, event_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.source,
                        "runtime.extra",
                        event.field,
                        event.event_id,
                        event.event_hash,
                        event.new_hash,
                        event.tick,
                        event.sequence,
                        event.event_time,
                    ),
                )
            else:
                attacker.execute(
                    """
                    UPDATE projections SET value_hash = ?
                    WHERE source = ? AND entity = ? AND field = ?
                    """,
                    ("f" * 64, event.source, event.entity, event.field),
                )
            attacker.commit()

        with pytest.raises(ChainIntegrityError, match="projection"):
            ledger.verify_integrity()


def test_read_only_ledger_verifies_without_mutating_database_or_wal(tmp_path: Path) -> None:
    database_path = tmp_path / "read-only.sqlite"
    writer = NeuromorphicLedger(database_path)
    try:
        event = _event(
            event_id="event.read-only-000",
            source="runtime.read-only",
            sequence=0,
            tick=9,
            previous_hash=ZERO_SHA256,
        )
        writer.ingest(event)
        wal_path = Path(str(database_path) + "-wal")
        assert wal_path.is_file()
        before = {
            path: (path.stat().st_mtime_ns, path.read_bytes())
            for path in (database_path, wal_path)
        }

        with NeuromorphicLedger.open_read_only(database_path) as reader:
            assert reader.read_only is True
            assert reader.journal_mode == "wal"
            assert reader.verify_integrity().ok is True
            assert reader.read_projection(event.source, event.entity, event.field) is not None
            with pytest.raises(LedgerReadOnlyError, match="read-only"):
                reader.ingest(event)
            with pytest.raises(sqlite3.OperationalError):
                reader._connection.execute("DELETE FROM change_events")

        after = {
            path: (path.stat().st_mtime_ns, path.read_bytes())
            for path in (database_path, wal_path)
        }
        assert after == before
    finally:
        writer.close()


def test_read_only_integrity_detects_tampered_projection(tmp_path: Path) -> None:
    database_path = tmp_path / "read-only-tampered.sqlite"
    event = _event(
        event_id="event.read-only-tampered",
        source="runtime.read-only",
        sequence=0,
        tick=2,
        previous_hash=ZERO_SHA256,
    )
    with NeuromorphicLedger(database_path) as ledger:
        ledger.ingest(event)
    with sqlite3.connect(database_path) as attacker:
        attacker.execute(
            "UPDATE projections SET event_hash = ? WHERE source = ? AND entity = ? AND field = ?",
            ("f" * 64, event.source, event.entity, event.field),
        )
        attacker.commit()

    before = (database_path.stat().st_mtime_ns, database_path.read_bytes())
    with NeuromorphicLedger.open_read_only(database_path) as reader:
        with pytest.raises(ChainIntegrityError, match="projection"):
            reader.verify_integrity()
    after = (database_path.stat().st_mtime_ns, database_path.read_bytes())
    assert after == before


def test_writer_and_read_only_reject_symlink_database_path(tmp_path: Path) -> None:
    external = tmp_path / "external.sqlite"
    with NeuromorphicLedger(external):
        pass
    link = tmp_path / "state-root" / "neuromorphic-runtime.sqlite3"
    link.parent.mkdir()
    link.symlink_to(external)

    with pytest.raises(ContractError, match="non-symlink regular file"):
        NeuromorphicLedger(link)
    with pytest.raises(ContractError, match="non-symlink regular file"):
        NeuromorphicLedger.open_read_only(link)

    real_root = tmp_path / "real-state-root"
    real_root.mkdir()
    real_database = real_root / "neuromorphic-runtime.sqlite3"
    with NeuromorphicLedger(real_database):
        pass
    linked_root = tmp_path / "linked-state-root"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(ContractError, match="parent must be a non-symlink directory"):
        NeuromorphicLedger(linked_root / "another.sqlite3")
    with pytest.raises(ContractError, match="parent must be a non-symlink directory"):
        NeuromorphicLedger.open_read_only(linked_root / real_database.name)


def test_schema_identity_rejects_shadow_table_and_trigger_before_writer_mutation(tmp_path: Path) -> None:
    database = tmp_path / "schema-tampered.sqlite3"
    with NeuromorphicLedger(database):
        pass
    with sqlite3.connect(database) as attacker:
        attacker.executescript(
            """
            CREATE TABLE shadow_events(canonical_event TEXT NOT NULL);
            CREATE TRIGGER copy_change_event
            AFTER INSERT ON change_events
            BEGIN
                INSERT INTO shadow_events(canonical_event) VALUES(NEW.canonical_event);
            END;
            """
        )

    with pytest.raises(NeuromorphicRuntimeError, match="object identity|SQL schema"):
        NeuromorphicLedger.open_read_only(database)
    with pytest.raises(NeuromorphicRuntimeError, match="object identity|SQL schema"):
        NeuromorphicLedger(database)
    with sqlite3.connect(database) as check:
        assert check.execute("SELECT COUNT(*) FROM change_events").fetchone()[0] == 0
        assert check.execute("SELECT COUNT(*) FROM shadow_events").fetchone()[0] == 0


def test_schema_identity_keeps_quoted_check_literal_case_significant(tmp_path: Path) -> None:
    database = tmp_path / "schema-literal-tampered.sqlite3"
    with NeuromorphicLedger(database):
        pass
    with sqlite3.connect(database) as attacker:
        schema_version = int(attacker.execute("PRAGMA schema_version").fetchone()[0])
        attacker.execute("PRAGMA writable_schema=ON")
        attacker.execute(
            """
            UPDATE sqlite_master
            SET sql=replace(sql, '''candidate''', '''CANDIDATE''')
            WHERE type='table' AND name='neuro_admissions'
            """
        )
        attacker.execute("PRAGMA writable_schema=OFF")
        attacker.execute(f"PRAGMA schema_version={schema_version + 1}")

    with pytest.raises(NeuromorphicRuntimeError, match="object identity|SQL schema"):
        NeuromorphicLedger.open_read_only(database)
    with pytest.raises(NeuromorphicRuntimeError, match="object identity|SQL schema"):
        NeuromorphicLedger(database)


def test_concurrent_first_open_is_serialized_across_threads_and_processes(tmp_path: Path) -> None:
    thread_database = tmp_path / "thread-first-open.sqlite3"
    with ThreadPoolExecutor(max_workers=24) as pool:
        thread_results = list(
            pool.map(_first_open_worker, [str(thread_database)] * 96)
        )
    assert thread_results == [True] * 96

    process_database = tmp_path / "process-first-open.sqlite3"
    with ProcessPoolExecutor(max_workers=8) as pool:
        process_results = list(
            pool.map(_first_open_worker, [str(process_database)] * 24)
        )
    assert process_results == [True] * 24


def test_spike_filter_and_homeostat_are_deterministic_proposal_only() -> None:
    left = QuantizedSpikeFilter(threshold=5, leak_per_tick=1, reset_potential=0)
    right = QuantizedSpikeFilter(threshold=5, leak_per_tick=1, reset_potential=0)

    left_first = left.observe("sensor.patchmon", tick=1, magnitude=2)
    right_first = right.observe("sensor.patchmon", tick=1, magnitude=2)
    left_spike = left.observe("sensor.patchmon", tick=2, magnitude=4)
    right_spike = right.observe("sensor.patchmon", tick=2, magnitude=4)

    assert left_first == right_first
    assert left_first.spiked is False and left_first.retained_potential == 2
    assert left_spike == right_spike
    assert left_spike.potential_before_input == 1
    assert left_spike.potential_after_input == 5
    assert left_spike.spiked is True
    assert left_spike.uncertain is True
    assert left_spike.proposal_only is True
    assert left_spike.may_execute is False
    assert left_spike.external_effects == ()
    with pytest.raises(TemporalOrderError, match="tick must increase"):
        left.observe("sensor.patchmon", tick=2, magnitude=1)

    homeostat = ResourceHomeostat(
        units_per_worker=10,
        min_workers=1,
        max_workers=4,
        max_adjustment=1,
    )
    recommendation = homeostat.recommend(queue_units=100, active_workers=2)
    assert recommendation.target_workers == 3
    assert recommendation.pressure == "saturated"
    assert recommendation.backpressure_recommended is True
    assert recommendation.advisory_only is True
    assert recommendation.may_execute is False
    assert recommendation.external_effects == ()
