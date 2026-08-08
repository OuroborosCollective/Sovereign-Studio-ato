/**
 * Signal Ordering Module
 *
 * Provides deterministic canonical ordering for signals based on causal fields
 * (tick, node, sequence) rather than wall-clock time.
 *
 * Guarantees:
 * - Same input always produces same order
 * - No wall-clock dependencies for ordering
 * - Stable sort for equal keys
 *
 * @module predictive/pipeline/signalOrdering
 */

import type { Signal } from '../types';
import type { PipelineItem } from './deterministicIterables';

/**
 * Extended signal with causal ordering fields.
 * These fields drive deterministic ordering, not wall-clock timestamp.
 */
export interface OrderedSignal extends Signal {
  /** Causal tick counter (incremented per pipeline step) */
  tick: number;
  /** Sequence number for same-tick ordering by node */
  sequence: number;
  /** Revision hash for cache invalidation */
  revision: string;
}

/**
 * Options for signal ordering.
 */
export interface SignalOrderingOptions {
  /** Whether to deduplicate by signal ID */
  deduplicate?: boolean;
  /** Maximum signals to process */
  maxSignals?: number;
  /** Signal to abort processing */
  signal?: AbortSignal;
}

/**
 * Default ordering options.
 */
export const DEFAULT_ORDERING_OPTIONS: SignalOrderingOptions = {
  deduplicate: true,
  maxSignals: 10000,
};

/**
 * Ordering key function for canonical sort.
 * Returns a tuple for stable sort: [tick, node, sequence, id]
 */
export function signalOrderingKey(signal: OrderedSignal): [number, string, number, string] {
  return [signal.tick, signal.node, signal.sequence, signal.id];
}

/**
 * Canonical ordering comparator.
 * Sorts by tick, then node (lexicographic), then sequence, then id.
 */
export function signalOrderingComparator(
  a: OrderedSignal,
  b: OrderedSignal,
): number {
  // Primary: tick
  if (a.tick !== b.tick) return a.tick - b.tick;

  // Secondary: node (lexicographic for determinism)
  if (a.node !== b.node) {
    return a.node < b.node ? -1 : 1;
  }

  // Tertiary: sequence
  if (a.sequence !== b.sequence) return a.sequence - b.sequence;

  // Final: signal ID for stable sort
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

/**
 * Sorts signals into canonical order deterministically.
 * Same input always produces same output order.
 *
 * @param signals - Array of signals with causal ordering fields
 * @returns Sorted array (does not mutate original)
 */
export function orderSignals(signals: OrderedSignal[]): OrderedSignal[] {
  return [...signals].sort(signalOrderingComparator);
}

/**
 * Creates an ordered signal from a base signal.
 * Adds causal ordering fields if missing.
 */
export function toOrderedSignal(
  signal: Signal,
  tick: number,
  sequence: number,
  revision: string,
): OrderedSignal {
  if ('tick' in signal && 'sequence' in signal && 'revision' in signal) {
    return signal as OrderedSignal;
  }
  return {
    ...signal,
    tick,
    sequence,
    revision,
  };
}

/**
 * Groups signals by node while preserving canonical order within groups.
 *
 * @param signals - Signals in canonical order
 * @returns Map of node -> signals in order
 */
export function groupSignalsByNode(
  signals: OrderedSignal[],
): Map<string, OrderedSignal[]> {
  const result = new Map<string, OrderedSignal[]>();

  for (const signal of signals) {
    const existing = result.get(signal.node);
    if (existing) {
      existing.push(signal);
    } else {
      result.set(signal.node, [signal]);
    }
  }

  return result;
}

/**
 * Merges signals from multiple nodes into canonical order.
 * Uses round-robin by tick, then node, then sequence.
 *
 * @param nodeSignals - Map of node -> signals in order
 * @returns Merged signals in canonical order
 */
export function mergeNodeSignals(
  nodeSignals: Map<string, OrderedSignal[]>,
): OrderedSignal[] {
  // Convert to array of iterators
  const iterators = new Map<string, Iterator<OrderedSignal>>();
  const buffers = new Map<string, OrderedSignal[]>();

  for (const [node, signals] of nodeSignals) {
    iterators.set(node, signals[Symbol.iterator]());
    buffers.set(node, signals);
  }

  const result: OrderedSignal[] = [];

  // Advance each node's iterator
  const current = new Map<string, OrderedSignal>();

  // Prime all iterators
  for (const [node, signals] of buffers) {
    const it = iterators.get(node)!;
    const first = it.next();
    if (!first.done) {
      current.set(node, first.value);
    }
  }

  // Round-robin merge
  while (current.size > 0) {
    // Find earliest by canonical order
    let earliestNode: string | null = null;
    let earliestSignal: OrderedSignal | null = null;

    for (const [node, signal] of current) {
      if (earliestSignal === null) {
        earliestNode = node;
        earliestSignal = signal;
      } else {
        const cmp = signalOrderingComparator(signal, earliestSignal);
        if (cmp < 0) {
          earliestNode = node;
          earliestSignal = signal;
        }
      }
    }

    if (earliestNode && earliestSignal) {
      result.push(earliestSignal);
      current.delete(earliestNode);

      // Advance this node's iterator
      const it = iterators.get(earliestNode)!;
      const next = it.next();
      if (!next.done) {
        current.set(earliestNode, next.value);
      }
    }
  }

  return result;
}

/**
 * Validates that signals are in canonical order.
 * Useful for testing and validation.
 *
 * @param signals - Signals to validate
 * @returns Validation result with any out-of-order signals
 */
export function validateCanonicalOrder(
  signals: OrderedSignal[],
): { valid: boolean; outOfOrder: OrderedSignal[] } {
  const outOfOrder: OrderedSignal[] = [];
  let previous: OrderedSignal | undefined;

  for (const signal of signals) {
    if (previous && signalOrderingComparator(previous, signal) > 0) {
      outOfOrder.push(signal);
    }
    previous = signal;
  }

  return {
    valid: outOfOrder.length === 0,
    outOfOrder,
  };
}

/**
 * Filters and orders signals with options.
 *
 * @param signals - Input signals
 * @param options - Ordering options
 * @returns Ordered signals respecting options
 */
export function processSignals(
  signals: Signal[],
  options: SignalOrderingOptions = DEFAULT_ORDERING_OPTIONS,
): OrderedSignal[] {
  const { maxSignals, signal, deduplicate } = {
    ...DEFAULT_ORDERING_OPTIONS,
    ...options,
  };

  if (signal?.aborted) {
    throw new DOMException('Processing aborted', 'AbortError');
  }

  // Limit signals
  let working = signals.slice(0, maxSignals);

  // Deduplicate
  if (deduplicate) {
    const seen = new Set<string>();
    working = working.filter((s) => {
      if (seen.has(s.id)) return false;
      seen.add(s.id);
      return true;
    });
  }

  // Convert to ordered signals (assign tick, sequence, revision)
  let tick = 0;
  let sequence = 0;
  const revision = 'canonical'; // Default revision

  const ordered: OrderedSignal[] = working.map((s, idx) => {
    if (idx === 0 || s.node !== working[idx - 1].node) {
      sequence = 0;
    }
    const orderedSignal = toOrderedSignal(s, tick, sequence, revision);
    sequence++;
    if (idx > 0 && s.node !== working[idx - 1].node) {
      tick++;
    }
    return orderedSignal;
  });

  return orderSignals(ordered);
}

/**
 * Creates a revision-bound fingerprint for signal ordering.
 * Used for cache invalidation when revision changes.
 */
export function createOrderingFingerprint(
  revision: string,
  signalCount: number,
): string {
  return `order:${revision}:${signalCount}`;
}

/**
 * Interface for pipeline items that can be ordered.
 */
export interface OrderablePipelineItem extends PipelineItem {
  /** Signal ID */
  id: string;
  /** Signal value */
  value: number;
}

/**
 * Converts orderable items to ordered signals.
 */
export function toOrderedSignalFromPipeline(
  items: OrderablePipelineItem[],
): OrderedSignal[] {
  return items.map((item, idx) => ({
    id: item.id,
    node: item.node,
    value: item.value,
    timestamp: 0, // Not used for ordering
    traceId: `pipeline-${idx}`,
    tick: item.tick,
    sequence: item.sequence,
    revision: item.revision || 'unknown',
  }));
}
