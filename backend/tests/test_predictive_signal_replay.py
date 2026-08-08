"""
Tests for Predictive Signal Replay

Tests the deterministic signal pipeline replay functionality.
Matches the TypeScript tests in src/predictive/pipeline/replay.test.ts.

@module tests.test_predictive_signal_replay
"""

from __future__ import annotations

import time
import pytest
from typing import Any, Dict, List, Tuple, Optional

from backend.agent_runtime.predictive.signal_pipeline import (
    Signal,
    OrderedSignal,
    SignalOrderingError,
    TickWindowConfig,
    TickWindow,
    BackpressureState,
    DeterministicSignalPipeline,
    RecordedSignalSet,
    ReplayResult,
    FeatureVector,
    WindowReceipt,
    order_signals,
    process_signals_to_windows,
    replay_signals,
    canonical_sort,
    create_config_fingerprint,
    chunkwise,
    chunkwise_overlap,
    pairwise,
    group_by,
    running_difference,
    running_total,
    to_min_max,
)


def make_signal(
    id: str,
    tick: int,
    sequence: int,
    revision: str,
    node: str,
    value: float,
) -> Signal:
    """Helper to create a test signal."""
    return Signal(
        id=id,
        node=node,
        value=value,
        timestamp=0,
        trace_id="trace-1",
        metadata={"tick": tick, "sequence": sequence, "revision": revision},
    )


class TestDeterministicIterables:
    """Tests for deterministic iterator primitives."""

    def test_chunkwise_splits_into_chunks(self):
        input_list = [1, 2, 3, 4, 5]
        result = list(chunkwise(input_list, 2))
        assert result == [[1, 2], [3, 4], [5]]

    def test_chunkwise_respects_max_items(self):
        input_list = [1, 2, 3, 4, 5, 6, 7]
        result = list(chunkwise(input_list, 2, max_items=4))
        assert result == [[1, 2], [3, 4]]

    def test_chunkwise_throws_on_invalid_size(self):
        with pytest.raises(ValueError, match="size must be positive"):
            list(chunkwise([1, 2, 3], 0))

    def test_chunkwise_handles_empty_input(self):
        result = list(chunkwise([], 2))
        assert result == []

    def test_chunkwise_overlap_creates_overlapping_chunks(self):
        input_list = [1, 2, 3, 4, 5]
        result = list(chunkwise_overlap(input_list, 3, 1))
        assert result == [[1, 2, 3], [3, 4, 5]]

    def test_chunkwise_overlap_throws_when_overlap_gte_size(self):
        with pytest.raises(ValueError, match="overlap must be less than size"):
            list(chunkwise_overlap([1, 2, 3], 2, 2))

    def test_pairwise_yields_consecutive_pairs(self):
        input_list = [1, 2, 3, 4]
        result = list(pairwise(input_list))
        assert result == [(1, 2), (2, 3), (3, 4)]

    def test_pairwise_handles_single_element(self):
        result = list(pairwise([1]))
        assert result == []

    def test_zip_equal_zips_equal_length_arrays(self):
        a = [1, 2, 3]
        b = ["a", "b", "c"]
        result = list(zip_equal(a, b))
        assert result == [[1, "a"], [2, "b"], [3, "c"]]

    def test_zip_equal_throws_on_mismatched_lengths(self):
        a = [1, 2, 3]
        b = ["a", "b"]
        with pytest.raises(ValueError, match="mismatched lengths"):
            list(zip_equal(a, b))

    def test_group_by_groups_by_key(self):
        input_list = [
            {"type": "a", "value": 1},
            {"type": "a", "value": 2},
            {"type": "b", "value": 3},
        ]
        result = list(group_by(input_list, lambda x: x["type"]))
        assert result == [
            ("a", [{"type": "a", "value": 1}, {"type": "a", "value": 2}]),
            ("b", [{"type": "b", "value": 3}]),
        ]

    def test_running_difference_computes_differences(self):
        input_list = [10, 15, 12, 20]
        result = list(running_difference(input_list))
        assert result == [10, 5, -3, 8]

    def test_running_total_computes_cumulative_sum(self):
        input_list = [1, 2, 3, 4]
        result = list(running_total(input_list))
        assert result == [1, 3, 6, 10]

    def test_to_min_max_returns_min_max(self):
        input_list = [3, 1, 4, 1, 5, 9, 2, 6]
        result = to_min_max(input_list)
        assert result == (1, 9)

    def test_to_min_max_returns_none_for_empty(self):
        result = to_min_max([])
        assert result is None


class TestCanonicalOrdering:
    """Tests for canonical signal ordering."""

    def test_order_signals_orders_by_tick_node_sequence(self):
        signals = [
            make_signal("3", tick=1, sequence=1, revision="rev-1", node="node-b", value=3),
            make_signal("1", tick=1, sequence=0, revision="rev-1", node="node-a", value=1),
            make_signal("2", tick=0, sequence=0, revision="rev-1", node="node-a", value=2),
        ]

        ordered = order_signals(signals)
        assert [s.id for s in ordered] == ["2", "1", "3"]

    def test_order_signals_handles_empty_list(self):
        result = order_signals([])
        assert result == []

    def test_canonical_sort_maintains_order(self):
        signals = [
            make_signal("1", tick=0, sequence=0, revision="rev-1", node="node-a", value=1),
            make_signal("2", tick=0, sequence=1, revision="rev-1", node="node-a", value=2),
        ]
        ordered = [OrderedSignal.from_signal(s) for s in signals]
        sorted_signals = canonical_sort(ordered)
        assert [s.id for s in sorted_signals] == ["1", "2"]

    def test_create_config_fingerprint(self):
        fp = create_config_fingerprint(10, 5)
        assert fp == "ws=10|ov=5"

    def test_create_config_fingerprint_with_max_items(self):
        fp = create_config_fingerprint(10, 5, 100)
        assert fp == "ws=10|ov=5|mi=100"


class TestSignalOrderingErrors:
    """Tests for signal ordering error handling."""

    def test_invalid_tick_raises_error(self):
        signal = make_signal("1", tick=-1, sequence=0, revision="rev-1", node="node-a", value=1)
        with pytest.raises(SignalOrderingError) as exc_info:
            OrderedSignal.from_signal(signal)
        assert "non-negative integer" in str(exc_info.value)

    def test_missing_revision_raises_error(self):
        signal = Signal(
            id="1",
            node="node-a",
            value=1,
            timestamp=0,
            trace_id="trace-1",
            metadata={"tick": 0, "sequence": 0},  # No revision
        )
        with pytest.raises(SignalOrderingError) as exc_info:
            OrderedSignal.from_signal(signal)
        assert "revision" in str(exc_info.value)


class TestTickWindow:
    """Tests for tick window processing."""

    def test_process_signals_to_windows_creates_windows(self):
        signals = [
            make_signal("1", tick=0, sequence=0, revision="rev-1", node="node-a", value=10),
            make_signal("2", tick=1, sequence=0, revision="rev-1", node="node-a", value=20),
            make_signal("3", tick=2, sequence=0, revision="rev-1", node="node-a", value=30),
        ]

        ordered = order_signals(signals)
        config = TickWindowConfig(window_size=2, overlap=0)
        result = process_signals_to_windows(ordered, config)

        assert len(result.windows) > 0
        assert len(result.drops) == 0
        assert result.aborted is False

    def test_process_signals_to_windows_respects_max_items(self):
        signals = [
            make_signal(str(i), tick=i, sequence=0, revision="rev-1", node="node-a", value=float(i))
            for i in range(100)
        ]

        ordered = order_signals(signals)
        config = TickWindowConfig(window_size=10, overlap=0, max_items=5)
        result = process_signals_to_windows(ordered, config)

        assert any(d.reason.value == "MAX_ITEMS_EXCEEDED" for d in result.drops)


class TestFeatureExtraction:
    """Tests for feature extraction."""

    def test_replay_produces_feature_vectors(self):
        signals = [
            make_signal("1", tick=0, sequence=0, revision="rev-abc", node="node-a", value=10),
            make_signal("2", tick=0, sequence=1, revision="rev-abc", node="node-b", value=20),
            make_signal("3", tick=1, sequence=0, revision="rev-abc", node="node-a", value=15),
            make_signal("4", tick=1, sequence=1, revision="rev-abc", node="node-b", value=25),
        ]

        recorded_set = RecordedSignalSet(
            signals=signals,
            revision="rev-abc",
            recorded_at=0,
            config_fingerprint="ws=3|ov=0",
            feature_vectors=[],
        )

        config = TickWindowConfig(window_size=3, overlap=0)
        result = replay_signals(recorded_set, config)

        assert len(result.replay_vectors) > 0
        assert len(result.errors) == 0


class TestSignalRecorder:
    """Tests for the DeterministicSignalPipeline recorder."""

    def test_start_and_finish_recording(self):
        pipeline = DeterministicSignalPipeline(TickWindowConfig(window_size=3, overlap=0))

        pipeline.start_recording("rev-abc")
        pipeline.record_signals([
            make_signal("1", tick=0, sequence=0, revision="rev-abc", node="node-a", value=1),
            make_signal("2", tick=1, sequence=0, revision="rev-abc", node="node-a", value=2),
        ])

        recorded = pipeline.finish_recording()

        assert recorded.revision == "rev-abc"
        assert len(recorded.signals) == 2

    def test_process_signals_live_mode(self):
        pipeline = DeterministicSignalPipeline(TickWindowConfig(window_size=3, overlap=0))

        signals = [
            make_signal("1", tick=0, sequence=0, revision="rev-1", node="node-a", value=10),
            make_signal("2", tick=1, sequence=0, revision="rev-1", node="node-a", value=20),
        ]

        vectors, receipts = pipeline.process_signals(signals, "rev-1")

        assert len(vectors) > 0
        assert len(receipts) > 0

    def test_record_and_replay_parity(self):
        pipeline = DeterministicSignalPipeline(TickWindowConfig(window_size=3, overlap=0))

        signals = [
            make_signal("1", tick=0, sequence=0, revision="rev-abc", node="node-a", value=10),
            make_signal("2", tick=0, sequence=1, revision="rev-abc", node="node-b", value=20),
        ]

        # Process live to get feature vectors
        live_vectors, _ = pipeline.process_signals(signals, "rev-abc")

        # Record
        pipeline.start_recording("rev-abc")
        pipeline.record_signals(signals)
        recorded = pipeline.finish_recording(live_vectors)

        # Replay
        replay_result = pipeline.replay_recorded(recorded)

        assert replay_result.parity_verified is True


class TestReplayParity:
    """Tests for replay parity verification."""

    def test_identical_signals_produce_identical_hashes(self):
        signals = [
            make_signal("1", tick=0, sequence=0, revision="rev-1", node="node-a", value=42),
        ]

        # Process twice
        pipeline = DeterministicSignalPipeline(TickWindowConfig(window_size=3, overlap=0))

        vectors1, _ = pipeline.process_signals(signals, "rev-1")
        vectors2, _ = pipeline.process_signals(signals, "rev-1")

        # Signal hashes should match
        assert len(vectors1) == len(vectors2)
        for v1, v2 in zip(vectors1, vectors2):
            assert v1.signal_hash == v2.signal_hash

    def test_different_values_produce_different_hashes(self):
        signals1 = [make_signal("1", tick=0, sequence=0, revision="rev-1", node="node-a", value=10)]
        signals2 = [make_signal("1", tick=0, sequence=0, revision="rev-1", node="node-a", value=20)]

        pipeline = DeterministicSignalPipeline(TickWindowConfig(window_size=3, overlap=0))

        vectors1, _ = pipeline.process_signals(signals1, "rev-1")
        vectors2, _ = pipeline.process_signals(signals2, "rev-1")

        assert vectors1[0].signal_hash != vectors2[0].signal_hash


class TestBackpressure:
    """Tests for backpressure handling."""

    def test_backpressure_state_tracking(self):
        state = BackpressureState(
            queue_depth=50,
            is_backpressured=False,
            max_queue_depth=100,
        )
        assert state.is_backpressured is False

        state = BackpressureState(
            queue_depth=100,
            is_backpressured=True,
            max_queue_depth=100,
        )
        assert state.is_backpressured is True
