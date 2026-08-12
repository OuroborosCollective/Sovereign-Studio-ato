"""
Deterministic Signal Pipeline - Python Backend

Implements a deterministic signal and feature pipeline for runtime sensors.
Mirrors the TypeScript implementation in src/predictive/pipeline/.

Pipeline:
    validated signals -> canonical order -> bounded grouping by node
    -> pairwise deltas -> fixed/overlapping tick windows
    -> deterministic feature vectors -> feature-window receipt -> inference lanes

@module agent_runtime.predictive.signal_pipeline
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generator, Iterable, Iterator, List, Optional, Tuple, Set

# ============================================================================
# Signal Types
# ============================================================================


class WindowDropReason(Enum):
    """Reason codes for window drops."""
    MAX_ITEMS_EXCEEDED = "MAX_ITEMS_EXCEEDED"
    MAX_WINDOW_DURATION_EXCEEDED = "MAX_WINDOW_DURATION_EXCEEDED"
    BACKPRESSURE_APPLIED = "BACKPRESSURE_APPLIED"
    ABORT_SIGNALLED = "ABORT_SIGNALLED"
    INCOMPLETE_WINDOW = "INCOMPLETE_WINDOW"


@dataclass
class Signal:
    """Micro-signal emitted when runtime state changes."""
    id: str
    node: str
    value: float
    timestamp: int
    trace_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderedSignal:
    """Signal with explicit ordering metadata."""
    id: str
    node: str
    value: float
    timestamp: int
    trace_id: str
    metadata: Dict[str, Any]
    tick: int
    sequence: int
    revision: str

    @classmethod
    def from_signal(cls, signal: Signal) -> OrderedSignal:
        """Converts a Signal to an OrderedSignal with validation."""
        meta = signal.metadata or {}
        tick = meta.get("tick", 0)
        sequence = meta.get("sequence", 0)
        revision = meta.get("revision", "")

        if not isinstance(tick, int) or tick < 0:
            raise SignalOrderingError(
                f"Signal {signal.id} missing or invalid tick (expected non-negative integer)",
                "MISSING_FIELD",
                {"signal_id": signal.id, "tick": tick}
            )
        if not isinstance(sequence, int) or sequence < 0:
            raise SignalOrderingError(
                f"Signal {signal.id} missing or invalid sequence (expected non-negative integer)",
                "MISSING_FIELD",
                {"signal_id": signal.id, "sequence": sequence}
            )
        if not isinstance(revision, str) or not revision:
            raise SignalOrderingError(
                f"Signal {signal.id} missing or invalid revision",
                "MISSING_FIELD",
                {"signal_id": signal.id, "revision": revision}
            )

        return cls(
            id=signal.id,
            node=signal.node,
            value=signal.value,
            timestamp=signal.timestamp,
            trace_id=signal.trace_id,
            metadata={**signal.metadata, "tick": tick, "sequence": sequence, "revision": revision},
            tick=tick,
            sequence=sequence,
            revision=revision,
        )


class SignalOrderingError(Exception):
    """Error thrown when signals cannot be ordered deterministically."""
    def __init__(self, message: str, code: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


# ============================================================================
# Deterministic Iterator Primitives
# ============================================================================


def chunkwise(iterable: Iterable, size: int, max_items: Optional[int] = None) -> Generator[List]:
    """Yields chunks of the specified size from an iterable."""
    if size <= 0:
        raise ValueError("chunkwise: size must be positive")

    chunk: List = []
    count = 0
    for item in iterable:
        chunk.append(item)
        count += 1
        if len(chunk) == size:
            yield chunk
            chunk = []
        if max_items is not None and count >= max_items:
            break
    if chunk:
        yield chunk


def chunkwise_overlap(
    iterable: Iterable, size: int, overlap: int, max_items: Optional[int] = None
) -> Generator[List]:
    """Yields overlapping chunks with the specified overlap."""
    if size <= 0:
        raise ValueError("chunkwiseOverlap: size must be positive")
    if overlap >= size:
        raise ValueError("chunkwiseOverlap: overlap must be less than size")
    if overlap < 0:
        raise ValueError("chunkwiseOverlap: overlap must be non-negative")

    buffer: List = []
    count = 0

    for item in iterable:
        buffer.append(item)
        count += 1
        if len(buffer) == size:
            yield list(buffer)
            buffer = buffer[size - overlap:]
        if max_items is not None and count >= max_items:
            break


def pairwise(iterable: Iterable) -> Generator[Tuple[Any, Any]]:
    """Yields consecutive pairs from an iterable."""
    prev = None
    has_prev = False
    for item in iterable:
        if has_prev:
            yield (prev, item)
        prev = item
        has_prev = True


def zip_equal(*iterables: Iterable) -> Generator[List]:
    """Zips multiple iterables together, throwing if lengths don't match."""
    iterators = [iter(i) for i in iterables]
    nexts = [it.__next__() for it in iterators]

    while True:
        done_count = sum(1 for n in nexts if n is StopIteration)
        if done_count > 0:
            if done_count != len(nexts):
                raise ValueError(
                    f"zipEqual: iterables have mismatched lengths. "
                    f"{len(nexts) - done_count} remaining but {done_count} exhausted"
                )
            break
        yield [n for n in nexts]
        for i, it in enumerate(iterators):
            try:
                nexts[i] = it.__next__()
            except StopIteration:
                nexts[i] = StopIteration


def group_by(iterable: Iterable, key_fn: Callable[[Any], Any]) -> Generator[Tuple[Any, List]]:
    """Groups consecutive elements by key."""
    current_key = None
    current_group: List = []

    for item in iterable:
        key = key_fn(item)
        if current_key is None:
            current_key = key
        if current_key == key:
            current_group.append(item)
        else:
            if current_group:
                yield (current_key, current_group)
            current_key = key
            current_group = [item]

    if current_group and current_key is not None:
        yield (current_key, current_group)


def running_difference(iterable: Iterable[float]) -> Generator[float]:
    """Yields running differences between consecutive elements."""
    prev = None
    is_first = True
    for item in iterable:
        if is_first:
            yield item
            is_first = False
        else:
            yield item - (prev if prev is not None else 0)
        prev = item


def running_total(iterable: Iterable[float]) -> Generator[float]:
    """Yields running totals (cumulative sum) of elements."""
    total = 0.0
    for item in iterable:
        total += item
        yield total


def to_min_max(iterable: Iterable[float]) -> Optional[Tuple[float, float]]:
    """Returns the minimum and maximum values from an iterable."""
    values = list(iterable)
    if not values:
        return None
    return (min(values), max(values))


# ============================================================================
# Canonical Ordering
# ============================================================================


def canonical_signal_comparator(a: OrderedSignal, b: OrderedSignal) -> int:
    """Canonical ordering comparator: tick, node, sequence."""
    if a.tick != b.tick:
        return a.tick - b.tick
    if a.node < b.node:
        return -1
    if a.node > b.node:
        return 1
    return a.sequence - b.sequence


def canonical_sort(signals: List[OrderedSignal]) -> List[OrderedSignal]:
    """Sorts signals into canonical order deterministically."""
    return sorted(signals, key=lambda s: (s.tick, s.node, s.sequence))


def order_signals(signals: List[Signal]) -> List[OrderedSignal]:
    """Orders signals into canonical order."""
    if not signals:
        return []
    ordered = [OrderedSignal.from_signal(s) for s in signals]
    return canonical_sort(ordered)


def validate_canonical_order(signals: List[OrderedSignal]) -> None:
    """Validates that signals are in canonical order."""
    for i in range(1, len(signals)):
        prev = signals[i - 1]
        curr = signals[i]

        if curr.tick < prev.tick:
            raise SignalOrderingError(
                f"Tick regression at index {i}: {curr.tick} < {prev.tick}",
                "OUT_OF_ORDER",
                {"prev_signal": prev.id, "curr_signal": curr.id}
            )

        if curr.tick == prev.tick:
            if curr.node < prev.node:
                raise SignalOrderingError(
                    f"Node ordering violation at tick {curr.tick}: {curr.node} < {prev.node}",
                    "OUT_OF_ORDER",
                    {"prev_signal": prev.id, "curr_signal": curr.id}
                )
            if curr.node == prev.node and curr.sequence <= prev.sequence:
                raise SignalOrderingError(
                    f"Sequence non-monotonic at tick {curr.tick}, node {curr.node}: "
                    f"{curr.sequence} <= {prev.sequence}",
                    "OUT_OF_ORDER",
                    {"prev_signal": prev.id, "curr_signal": curr.id}
                )


def create_config_fingerprint(window_size: int, overlap: int, max_items: Optional[int] = None) -> str:
    """Creates a config fingerprint for window parameters."""
    parts = [f"ws={window_size}", f"ov={overlap}"]
    if max_items is not None:
        parts.append(f"mi={max_items}")
    return "|".join(parts)


# ============================================================================
# Tick Window Types
# ============================================================================


@dataclass
class TickWindowConfig:
    """Configuration for tick windowing."""
    window_size: int
    overlap: int
    max_items: Optional[int] = None
    max_window_duration: Optional[int] = None


@dataclass
class TickWindow:
    """A tick window containing signals within a tick range."""
    id: str
    start_tick: int
    end_tick: int
    signals: List[OrderedSignal]
    nodes: List[str]
    window_index: int
    config_fingerprint: str
    is_complete: bool


@dataclass
class WindowDrop:
    """Window drop event with reason code."""
    signals: List[Signal]
    reason: WindowDropReason
    details: Optional[str] = None


@dataclass
class BackpressureState:
    """Backpressure state for flow control."""
    queue_depth: int
    is_backpressured: bool
    max_queue_depth: int


@dataclass
class WindowResult:
    """Window processing result."""
    windows: List[TickWindow]
    drops: List[WindowDrop]
    backpressure: BackpressureState
    aborted: bool
    ticks_processed: int


# ============================================================================
# Tick Window Generation
# ============================================================================


def _compute_tick_ranges(
    signals: List[OrderedSignal], window_size: int, overlap: int
) -> List[Tuple[int, int]]:
    """Computes the tick ranges for windows given signals and config."""
    if not signals:
        return []

    ticks = sorted(set(s.metadata.get("tick", 0) for s in signals))
    ranges: List[Tuple[int, int]] = []

    i = 0
    while i < len(ticks):
        start_tick = ticks[i]
        end_tick = min(start_tick + window_size - 1, ticks[-1])
        ranges.append((start_tick, end_tick))
        i += window_size - overlap

    return ranges


def generate_tick_windows(
    signals: List[OrderedSignal],
    config: TickWindowConfig,
    abort_signal: Optional[AbortSignalType] = None,
) -> Generator[TickWindow]:
    """Generates fixed-size tick windows from ordered signals."""
    if not signals:
        return

    fingerprint = create_config_fingerprint(config.window_size, config.overlap, config.max_items)
    tick_ranges = _compute_tick_ranges(signals, config.window_size, config.overlap)

    window_index = 0
    for start_tick, end_tick in tick_ranges:
        if abort_signal is not None and abort_signal.aborted:
            return

        window_signals = [s for s in signals if start_tick <= s.tick <= end_tick]
        unique_ticks = set(s.tick for s in window_signals)
        expected_ticks = end_tick - start_tick + 1
        is_complete = len(unique_ticks) == expected_ticks
        nodes = sorted(set(s.node for s in window_signals))

        yield TickWindow(
            id=f"window-{start_tick}-{end_tick}-{window_index}",
            start_tick=start_tick,
            end_tick=end_tick,
            signals=window_signals,
            nodes=nodes,
            window_index=window_index,
            config_fingerprint=fingerprint,
            is_complete=is_complete,
        )
        window_index += 1


class AbortSignalType:
    """Simple abort signal implementation."""
    def __init__(self):
        self._aborted = False

    @property
    def aborted(self) -> bool:
        return self._aborted

    def abort(self):
        self._aborted = True


def process_signals_to_windows(
    signals: List[OrderedSignal],
    config: TickWindowConfig,
    max_queue_depth: int = 100,
    abort_signal: Optional[AbortSignalType] = None,
) -> WindowResult:
    """Processes signals into windows with backpressure control."""
    windows: List[TickWindow] = []
    drops: List[WindowDrop] = []
    aborted = False
    ticks_processed = 0
    queue_depth = 0

    for window in generate_tick_windows(signals, config, abort_signal):
        if abort_signal is not None and abort_signal.aborted:
            aborted = True
            break

        queue_depth = len(window.signals)
        is_backpressured = queue_depth >= max_queue_depth

        if is_backpressured:
            drops.append(WindowDrop(
                signals=[],  # Cannot convert OrderedSignal back to Signal easily
                reason=WindowDropReason.BACKPRESSURE_APPLIED,
                details=f"Queue depth {queue_depth} exceeded max {max_queue_depth}"
            ))
            continue

        if config.max_items is not None and len(window.signals) > config.max_items:
            drops.append(WindowDrop(
                signals=[],
                reason=WindowDropReason.MAX_ITEMS_EXCEEDED,
                details=f"Window has {len(window.signals)} signals, max is {config.max_items}"
            ))
            window.signals = window.signals[:config.max_items]

        windows.append(window)
        ticks_processed = max(ticks_processed, window.end_tick + 1)

    backpressure = BackpressureState(
        queue_depth=queue_depth,
        is_backpressured=queue_depth >= max_queue_depth,
        max_queue_depth=max_queue_depth,
    )

    return WindowResult(
        windows=windows,
        drops=drops,
        backpressure=backpressure,
        aborted=aborted,
        ticks_processed=ticks_processed,
    )


# ============================================================================
# Feature Vector Types
# ============================================================================


@dataclass
class FeatureVector:
    """Feature vector produced by the pipeline."""
    values: List[float]
    signal_hash: str
    tick_range: Tuple[int, int]
    sequence_range: Tuple[int, int]
    revision: str
    config_fingerprint: str


@dataclass
class ExtractedFeatures:
    """Extracted features from a window."""
    mean: float
    std_dev: float
    min_val: float
    max_val: float
    range_val: float
    sum: float
    deltas: List[float]
    cumulative_sum: List[float]
    min_max: Optional[Tuple[float, float]]
    histogram: Optional[List[int]]
    node_stats: Dict[str, Dict[str, float]]
    signal_hash: str


@dataclass
class WindowReceipt:
    """Receipt for a processed window."""
    id: str
    feature_vector: FeatureVector
    signal_count: int
    timestamp: int
    is_replay: bool
    drop_reason: Optional[str] = None


# ============================================================================
# Feature Extraction
# ============================================================================


def _compute_signal_hash(signals: List[OrderedSignal]) -> str:
    """Computes a deterministic hash of signal values."""
    if not signals:
        return "empty"

    tuples = [
        f"{s.tick}:{s.sequence}:{s.node}:{s.value}"
        for s in signals
    ]
    combined = "|".join(tuples)

    # FNV-1a inspired hash
    hash_val = 2166136261
    prime = 16777619

    for c in combined:
        hash_val ^= ord(c)
        hash_val = (hash_val * prime) & 0xFFFFFFFF

    hex_str = format(hash_val, '08x')

    # Extend to 64 hex chars
    extended = hex_str
    for i in range(7):
        hash_val ^= (hash_val >> 20) + (hash_val << 5) + i
        extended += format(hash_val, '08x')

    return extended


def _compute_mean(values: List[float]) -> float:
    """Computes mean of values."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _compute_std_dev(values: List[float]) -> float:
    """Computes standard deviation of values."""
    if len(values) < 2:
        return 0.0
    mean = _compute_mean(values)
    squared_diffs = [(v - mean) ** 2 for v in values]
    variance = sum(squared_diffs) / (len(values) - 1)
    return variance ** 0.5


def extract_features(window: TickWindow) -> ExtractedFeatures:
    """Extracts features from a tick window."""
    signals = window.signals

    if not signals:
        return ExtractedFeatures(
            mean=0.0,
            std_dev=0.0,
            min_val=0.0,
            max_val=0.0,
            range_val=0.0,
            sum=0.0,
            deltas=[],
            cumulative_sum=[],
            min_max=None,
            histogram=None,
            node_stats={},
            signal_hash="empty",
        )

    sorted_signals = sorted(
        signals, key=lambda s: (s.tick, s.node, s.sequence)
    )
    values = [s.value for s in sorted_signals]

    mean = _compute_mean(values)
    std_dev = _compute_std_dev(values)
    min_val = min(values)
    max_val = max(values)
    range_val = max_val - min_val
    total = sum(values)

    deltas = list(running_difference(values))
    cumulative_sum = list(running_total(values))
    min_max = (min_val, max_val)

    # Per-node statistics
    node_stats: Dict[str, Dict[str, float]] = {}
    by_node: Dict[str, List[float]] = {}
    for signal in signals:
        node = signal.node
        if node not in by_node:
            by_node[node] = []
        by_node[node].append(signal.value)

    for node, node_values in by_node.items():
        node_stats[node] = {
            "mean": _compute_mean(node_values),
            "std_dev": _compute_std_dev(node_values),
            "count": len(node_values),
        }

    signal_hash = _compute_signal_hash(sorted_signals)

    return ExtractedFeatures(
        mean=mean,
        std_dev=std_dev,
        min_val=min_val,
        max_val=max_val,
        range_val=range_val,
        sum=total,
        deltas=deltas,
        cumulative_sum=cumulative_sum,
        min_max=min_max,
        histogram=None,
        node_stats=node_stats,
        signal_hash=signal_hash,
    )


def create_feature_vector(features: ExtractedFeatures, window: TickWindow) -> FeatureVector:
    """Creates a FeatureVector from extracted features."""
    vector: List[float] = [
        features.mean,
        features.std_dev,
        features.min_val,
        features.max_val,
        features.range_val,
        features.sum,
    ]

    # Add deltas (first 10)
    for i in range(min(len(features.deltas), 10)):
        vector.append(features.deltas[i])
    for i in range(len(features.deltas), 10):
        vector.append(0.0)

    # Add cumulative sum (first 10)
    for i in range(min(len(features.cumulative_sum), 10)):
        vector.append(features.cumulative_sum[i])
    for i in range(len(features.cumulative_sum), 10):
        vector.append(0.0)

    seq_range = (
        window.signals[0].sequence if window.signals else 0,
        window.signals[-1].sequence if window.signals else 0,
    )

    return FeatureVector(
        values=vector,
        signal_hash=features.signal_hash,
        tick_range=(window.start_tick, window.end_tick),
        sequence_range=seq_range,
        revision=window.signals[0].revision if window.signals else "",
        config_fingerprint=window.config_fingerprint,
    )


def process_window_to_features(window: TickWindow, is_replay: bool = False) -> Tuple[ExtractedFeatures, FeatureVector, WindowReceipt]:
    """Processes a window to extract features."""
    features = extract_features(window)
    feature_vector = create_feature_vector(features, window)

    receipt = WindowReceipt(
        id=f"receipt-{window.id}",
        feature_vector=feature_vector,
        signal_count=len(window.signals),
        timestamp=int(time.time() * 1000),
        is_replay=is_replay,
    )

    return features, feature_vector, receipt


# ============================================================================
# Replay Types
# ============================================================================


@dataclass
class RecordedSignalSet:
    """Recorded signal set for replay."""
    signals: List[Signal]
    revision: str
    recorded_at: int
    config_fingerprint: str
    feature_vectors: List[FeatureVector] = field(default_factory=list)


@dataclass
class ParityResult:
    """Result of parity verification."""
    index: int
    equal: bool
    diff: Optional[str] = None


@dataclass
class ReplayResult:
    """Result of replay operation."""
    original_vectors: List[FeatureVector]
    replay_vectors: List[FeatureVector]
    parity_results: List[ParityResult]
    parity_verified: bool
    window_count: int
    duration_ms: float
    errors: List[str]


# ============================================================================
# Replay Implementation
# ============================================================================


def _verify_feature_parity(a: FeatureVector, b: FeatureVector) -> Tuple[bool, Optional[str]]:
    """Verifies that two feature vectors are identical."""
    if a.signal_hash != b.signal_hash:
        return False, f"Signal hash mismatch: {a.signal_hash} vs {b.signal_hash}"
    if a.tick_range != b.tick_range:
        return False, f"Tick range mismatch: {a.tick_range} vs {b.tick_range}"
    if a.revision != b.revision:
        return False, f"Revision mismatch: {a.revision} vs {b.revision}"
    if len(a.values) != len(b.values):
        return False, f"Value length mismatch: {len(a.values)} vs {len(b.values)}"

    for i, (va, vb) in enumerate(zip(a.values, b.values)):
        if va != vb:
            return False, f"Value mismatch at index {i}: {va} vs {vb}"

    return True, None


def replay_signals(recorded_set: RecordedSignalSet, config: TickWindowConfig) -> ReplayResult:
    """Replays a recorded signal set through the pipeline."""
    start_time = time.time()
    errors: List[str] = []

    try:
        ordered_signals = order_signals(recorded_set.signals)
    except SignalOrderingError as e:
        errors.append(f"Signal ordering failed: {e}")
        return ReplayResult(
            original_vectors=recorded_set.feature_vectors,
            replay_vectors=[],
            parity_results=[
                ParityResult(index=i, equal=False, diff="Replay failed before vector generation")
                for i in range(len(recorded_set.feature_vectors))
            ],
            parity_verified=False,
            window_count=0,
            duration_ms=(time.time() - start_time) * 1000,
            errors=errors,
        )

    try:
        window_result = process_signals_to_windows(ordered_signals, config)
    except Exception as e:
        errors.append(f"Window processing failed: {e}")
        return ReplayResult(
            original_vectors=recorded_set.feature_vectors,
            replay_vectors=[],
            parity_results=[
                ParityResult(index=i, equal=False, diff="Replay failed before vector generation")
                for i in range(len(recorded_set.feature_vectors))
            ],
            parity_verified=False,
            window_count=0,
            duration_ms=(time.time() - start_time) * 1000,
            errors=errors,
        )

    replay_vectors: List[FeatureVector] = []
    for window in window_result.windows:
        _, feature_vector, _ = process_window_to_features(window, True)
        replay_vectors.append(feature_vector)

    parity_results: List[ParityResult] = []
    max_len = max(len(recorded_set.feature_vectors), len(replay_vectors))

    for i in range(max_len):
        if i < len(recorded_set.feature_vectors) and i < len(replay_vectors):
            equal, diff = _verify_feature_parity(
                recorded_set.feature_vectors[i], replay_vectors[i]
            )
            parity_results.append(ParityResult(index=i, equal=equal, diff=diff))
        else:
            parity_results.append(
                ParityResult(
                    index=i,
                    equal=False,
                    diff=f"Length mismatch at index {i}: original has {len(recorded_set.feature_vectors)}, replay has {len(replay_vectors)}"
                )
            )

    parity_verified = all(r.equal for r in parity_results)

    return ReplayResult(
        original_vectors=recorded_set.feature_vectors,
        replay_vectors=replay_vectors,
        parity_results=parity_results,
        parity_verified=parity_verified,
        window_count=len(window_result.windows),
        duration_ms=(time.time() - start_time) * 1000,
        errors=errors,
    )


# ============================================================================
# Full Pipeline
# ============================================================================


class DeterministicSignalPipeline:
    """Full signal pipeline that can run in both live and replay modes."""

    def __init__(self, window_config: TickWindowConfig, abort_signal: Optional[AbortSignalType] = None):
        self.window_config = window_config
        self.abort_signal = abort_signal
        self._recorder: Optional[List[Signal]] = None
        self._recording_revision: Optional[str] = None
        self._recording_started_at: Optional[int] = None

    def process_signals(self, signals: List[Signal], revision: str) -> Tuple[List[FeatureVector], List[WindowReceipt]]:
        """Processes signals through the pipeline (live mode)."""
        ordered_signals = order_signals(signals)
        window_result = process_signals_to_windows(ordered_signals, self.window_config, abort_signal=self.abort_signal)

        feature_vectors: List[FeatureVector] = []
        receipts: List[WindowReceipt] = []

        for window in window_result.windows:
            _, feature_vector, receipt = process_window_to_features(window, False)
            feature_vectors.append(feature_vector)
            receipts.append(receipt)

        return feature_vectors, receipts

    def start_recording(self, revision: str) -> None:
        """Starts recording for replay."""
        self._recorder = []
        self._recording_revision = revision
        self._recording_started_at = int(time.time() * 1000)

    def record_signals(self, signals: List[Signal]) -> None:
        """Records signals for later replay."""
        if self._recorder is not None:
            self._recorder.extend(signals)

    def finish_recording(self, feature_vectors: Optional[List[FeatureVector]] = None) -> RecordedSignalSet:
        """Finalizes recording and returns a replayable signal set."""
        if self._recorder is None:
            raise RuntimeError("Recording not started")

        fingerprint = create_config_fingerprint(
            self.window_config.window_size, self.window_config.overlap, self.window_config.max_items
        )

        recorded_set = RecordedSignalSet(
            signals=list(self._recorder),
            revision=self._recording_revision or "",
            recorded_at=self._recording_started_at or 0,
            config_fingerprint=fingerprint,
            feature_vectors=feature_vectors or [],
        )

        self._recorder = None
        self._recording_revision = None
        self._recording_started_at = None

        return recorded_set

    def replay_recorded(self, recorded_set: RecordedSignalSet) -> ReplayResult:
        """Replays a recorded signal set through the pipeline."""
        return replay_signals(recorded_set, self.window_config)
