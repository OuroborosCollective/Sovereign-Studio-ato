/**
 * Signal Ordering - Canonical Ordering for Signal Processing
 *
 * Provides deterministic ordering of signals based on tick, node, and sequence.
 * Wall-clock timestamps are metadata only; tick, sequence, revision, and window-hash
 * are the causal ordering primitives.
 *
 * @module predictive/pipeline/signalOrdering
 */

import type { Signal } from '../types';
import { canonicalSignalComparator, canonicalSort } from './deterministicIterables';

// ============================================================================
// Signal Identity Extensions
// ============================================================================

/**
 * Extended signal metadata for ordering.
 */
export interface OrderedSignalMetadata {
  /** Monotonically increasing tick */
  tick: number;
  /** Per-tick sequence number */
  sequence: number;
  /** Repository revision bound */
  revision: string;
  /** Node identifier */
  node: string;
}

/**
 * Signal with explicit ordering metadata.
 */
export interface OrderedSignal extends Signal {
  metadata: OrderedSignalMetadata & Record<string, unknown>;
}

// ============================================================================
// Ordering Errors
// ============================================================================

/**
 * Error thrown when signals cannot be ordered deterministically.
 */
export class SignalOrderingError extends Error {
  constructor(
    message: string,
    public readonly code: 'OUT_OF_ORDER' | 'MISSING_FIELD' | 'SEQUENCE_GAP' | 'REVISION_MISMATCH',
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = 'SignalOrderingError';
  }
}

// ============================================================================
// Canonical Ordering
// ============================================================================

/**
 * Validates that a signal has required ordering metadata.
 */
export function validateOrderingMetadata(signal: Signal): OrderedSignalMetadata {
  const meta = signal.metadata ?? {};
  const tick = meta.tick;
  const sequence = meta.sequence;
  const revision = meta.revision;

  if (typeof tick !== 'number' || !Number.isInteger(tick) || tick < 0) {
    throw new SignalOrderingError(
      `Signal ${signal.id} missing or invalid tick (expected non-negative integer)`,
      'MISSING_FIELD',
      { signalId: signal.id, tick },
    );
  }

  if (typeof sequence !== 'number' || !Number.isInteger(sequence) || sequence < 0) {
    throw new SignalOrderingError(
      `Signal ${signal.id} missing or invalid sequence (expected non-negative integer)`,
      'MISSING_FIELD',
      { signalId: signal.id, sequence },
    );
  }

  if (typeof revision !== 'string' || revision.length === 0) {
    throw new SignalOrderingError(
      `Signal ${signal.id} missing or invalid revision`,
      'MISSING_FIELD',
      { signalId: signal.id, revision },
    );
  }

  return { tick, sequence, revision, node: signal.node };
}

/**
 * Creates an ordered signal from a raw signal with validation.
 */
export function toOrderedSignal(signal: Signal): OrderedSignal {
  const orderingMeta = validateOrderingMetadata(signal);
  return {
    ...signal,
    metadata: {
      ...signal.metadata,
      ...orderingMeta,
    },
  } as OrderedSignal;
}

/**
 * Orders signals into canonical order: by tick, then node, then sequence.
 * This function is stable - same input always produces same output.
 */
export function orderSignals(signals: Signal[]): OrderedSignal[] {
  if (signals.length === 0) return [];

  // First, convert all to ordered signals (validates metadata)
  const ordered = signals.map(toOrderedSignal);

  // Then sort using canonical comparator
  return canonicalSort(ordered) as OrderedSignal[];
}

/**
 * Validates that signals are in canonical order.
 * Throws if any ordering violation is detected.
 */
export function validateCanonicalOrder(signals: OrderedSignal[]): void {
  for (let i = 1; i < signals.length; i++) {
    const prev = signals[i - 1];
    const curr = signals[i];

    // Check tick monotonicity
    if (curr.metadata.tick < prev.metadata.tick) {
      throw new SignalOrderingError(
        `Tick regression at index ${i}: ${curr.metadata.tick} < ${prev.metadata.tick}`,
        'OUT_OF_ORDER',
        { prevSignal: prev.id, currSignal: curr.id },
      );
    }

    // For same tick, check node and sequence (node is the canonical top-level field)
    if (curr.metadata.tick === prev.metadata.tick) {
      if (curr.node < prev.node) {
        throw new SignalOrderingError(
          `Node ordering violation at tick ${curr.metadata.tick}: ${curr.node} < ${prev.node}`,
          'OUT_OF_ORDER',
          { prevSignal: prev.id, currSignal: curr.id },
        );
      }

      if (
        curr.node === prev.node &&
        curr.metadata.sequence <= prev.metadata.sequence
      ) {
        throw new SignalOrderingError(
          `Sequence non-monotonic at tick ${curr.metadata.tick}, node ${curr.node}: ${curr.metadata.sequence} <= ${prev.metadata.sequence}`,
          'OUT_OF_ORDER',
          { prevSignal: prev.id, currSignal: curr.id },
        );
      }
    }
  }
}

/**
 * Checks for sequence gaps in signals.
 * Returns array of gap information.
 */
export function detectSequenceGaps(signals: OrderedSignal[]): Array<{
  tick: number;
  node: string;
  expectedSequence: number;
  actualSequence: number;
  gapSize: number;
}> {
  const gaps: Array<{
    tick: number;
    node: string;
    expectedSequence: number;
    actualSequence: number;
    gapSize: number;
  }> = [];

  // Group by tick and node (node is the canonical top-level field)
  const byTickNode = new Map<string, OrderedSignal[]>();
  for (const signal of signals) {
    const key = `${signal.metadata.tick}:${signal.node}`;
    if (!byTickNode.has(key)) byTickNode.set(key, []);
    byTickNode.get(key)!.push(signal);
  }

  // Check each group for sequence gaps
  for (const [, group] of byTickNode) {
    group.sort((a, b) => a.metadata.sequence - b.metadata.sequence);
    for (let i = 1; i < group.length; i++) {
      const prev = group[i - 1];
      const curr = group[i];
      const expected = prev.metadata.sequence + 1;
      if (curr.metadata.sequence > expected) {
        gaps.push({
          tick: curr.metadata.tick,
          node: curr.node,
          expectedSequence: expected,
          actualSequence: curr.metadata.sequence,
          gapSize: curr.metadata.sequence - expected,
        });
      }
    }
  }

  return gaps;
}

// ============================================================================
// Node Grouping
// ============================================================================

/**
 * Groups signals by node while preserving canonical order within each group.
 */
export function groupByNode(signals: OrderedSignal[]): Map<string, OrderedSignal[]> {
  const groups = new Map<string, OrderedSignal[]>();

  for (const signal of signals) {
    const node = signal.node;
    if (!groups.has(node)) groups.set(node, []);
    groups.get(node)!.push(signal);
  }

  return groups;
}

/**
 * Creates an aligned sequence of signal arrays, one per node.
 * All arrays will have the same length (padding with undefined where needed).
 * Throws if node sets differ between signals.
 */
export function alignByNode(signals: OrderedSignal[]): Map<string, OrderedSignal[]> {
  const groups = groupByNode(signals);

  // Verify all groups have consistent tick ranges
  // Optimized by replacing slow, localization-heavy localeCompare with native lexicographical comparison operators.
  const sortedGroups = Array.from(groups.entries()).sort((a, b) => {
    const keyA = a[0];
    const keyB = b[0];
    return keyA < keyB ? -1 : keyA > keyB ? 1 : 0;
  });

  // Check tick alignment
  for (let i = 1; i < sortedGroups.length; i++) {
    const [, prevSignals] = sortedGroups[i - 1];
    const [, currSignals] = sortedGroups[i];

    if (prevSignals.length !== currSignals.length) {
      throw new SignalOrderingError(
        `Node signal count mismatch: ${sortedGroups[i - 1][0]} has ${prevSignals.length}, ${sortedGroups[i][0]} has ${currSignals.length}`,
        'OUT_OF_ORDER',
      );
    }

    for (let j = 0; j < prevSignals.length; j++) {
      if (prevSignals[j].metadata.tick !== currSignals[j].metadata.tick) {
        throw new SignalOrderingError(
          `Tick mismatch at index ${j}: ${prevSignals[j].metadata.tick} vs ${currSignals[j].metadata.tick}`,
          'OUT_OF_ORDER',
        );
      }
    }
  }

  return groups;
}

// ============================================================================
// Revision Binding
// ============================================================================

/**
 * Validates that all signals in a sequence are bound to the same revision.
 */
export function validateRevisionBound(signals: OrderedSignal[], expectedRevision?: string): void {
  const revisions = new Set<string>();
  for (const signal of signals) {
    revisions.add(signal.metadata.revision);
  }

  if (revisions.size > 1) {
    throw new SignalOrderingError(
      `Multiple revisions in signal set: ${Array.from(revisions).join(', ')}`,
      'REVISION_MISMATCH',
      { revisions: Array.from(revisions) },
    );
  }

  if (expectedRevision !== undefined) {
    const actualRevision = signals[0]?.metadata.revision;
    if (actualRevision !== expectedRevision) {
      throw new SignalOrderingError(
        `Revision mismatch: expected ${expectedRevision}, got ${actualRevision}`,
        'REVISION_MISMATCH',
        { expected: expectedRevision, actual: actualRevision },
      );
    }
  }
}

/**
 * Extracts the revision bound from a sequence of signals.
 */
export function getRevisionBound(signals: OrderedSignal[]): string | undefined {
  return signals[0]?.metadata.revision;
}

// ============================================================================
// Pairwise Deltas for Aligned Signals
// ============================================================================

/**
 * Computes pairwise value deltas between consecutive signals for each node.
 */
export function computePairwiseDeltas(
  signals: OrderedSignal[],
): Map<string, Array<{ from: number; to: number; delta: number }>> {
  const byNode = groupByNode(signals);
  const deltas = new Map<string, Array<{ from: number; to: number; delta: number }>>();

  for (const [node, nodeSignals] of byNode) {
    const nodeDeltas: Array<{ from: number; to: number; delta: number }> = [];
    for (let i = 1; i < nodeSignals.length; i++) {
      const from = nodeSignals[i - 1].value;
      const to = nodeSignals[i].value;
      nodeDeltas.push({ from, to, delta: to - from });
    }
    deltas.set(node, nodeDeltas);
  }

  return deltas;
}

// ============================================================================
// Receipt Generation
// ============================================================================

/**
 * Receipt for an ordered signal batch.
 */
export interface OrderingReceipt {
  /** Ordered signals */
  signals: OrderedSignal[];
  /** Tick range [minTick, maxTick] */
  tickRange: [number, number];
  /** Sequence range [minSeq, maxSeq] */
  sequenceRange: [number, number];
  /** Revision bound */
  revision: string;
  /** Nodes included */
  nodes: string[];
  /** Signal count */
  signalCount: number;
  /** Processing timestamp */
  timestamp: number;
  /** Any gaps detected */
  gaps: ReturnType<typeof detectSequenceGaps>;
}

/**
 * Generates a receipt for an ordered signal batch.
 */
export function generateOrderingReceipt(signals: OrderedSignal[]): OrderingReceipt {
  if (signals.length === 0) {
    return {
      signals: [],
      tickRange: [0, 0],
      sequenceRange: [0, 0],
      revision: '',
      nodes: [],
      signalCount: 0,
      timestamp: Date.now(),
      gaps: [],
    };
  }

  const ticks = signals.map((s) => s.metadata.tick);
  const sequences = signals.map((s) => s.metadata.sequence);
  const nodes = [...new Set(signals.map((s) => s.node))].sort();
  const revision = signals[0].metadata.revision;
  const gaps = detectSequenceGaps(signals);

  return {
    signals,
    tickRange: [Math.min(...ticks), Math.max(...ticks)],
    sequenceRange: [Math.min(...sequences), Math.max(...sequences)],
    revision,
    nodes,
    signalCount: signals.length,
    timestamp: Date.now(),
    gaps,
  };
}
