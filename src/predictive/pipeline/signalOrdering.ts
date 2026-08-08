/**
 * Deterministic Signal Ordering Pipeline
 *
 * Provides canonical ordering of signals by tick, node, and sequence.
 * All operations are deterministic - same input always produces same output.
 *
 * @module predictive/pipeline/signalOrdering
 */

import type { Signal, TraceId } from '../types';

export interface SignalOrderKey {
  /** Causal tick - derived from revision-bound sequence, not wall-clock */
  tick: number;
  /** Node identifier for stable ordering */
  node: string;
  /** Per-node sequence number */
  sequence: number;
}

export interface OrderedSignal extends Signal {
  /** Canonical ordering key */
  orderKey: SignalOrderKey;
}

/**
 * Options for signal ordering
 */
export interface SignalOrderingOptions {
  /** Field name in metadata containing the tick value */
  tickField?: string;
  /** Field name in metadata containing the sequence value */
  sequenceField?: string;
}

/**
 * Extracts the causal tick from a signal.
 * Uses metadata tick if available, otherwise derives from timestamp.
 */
export function extractTick(signal: Signal, options: SignalOrderingOptions = {}): number {
  const tickField = options.tickField ?? '_tick';
  const metadata = signal.metadata as Record<string, unknown> | undefined;
  if (metadata && typeof metadata[tickField] === 'number') {
    return metadata[tickField] as number;
  }
  // Fallback: derive deterministic tick from timestamp
  // This is not truly causal but provides stable ordering
  return Math.floor(signal.timestamp / 1000);
}

/**
 * Extracts the sequence from a signal metadata.
 */
export function extractSequence(signal: Signal, options: SignalOrderingOptions = {}): number {
  const sequenceField = options.sequenceField ?? '_seq';
  const metadata = signal.metadata as Record<string, unknown> | undefined;
  if (metadata && typeof metadata[sequenceField] === 'number') {
    return metadata[sequenceField] as number;
  }
  // Fallback: use 0 as default sequence
  return 0;
}

/**
 * Creates a canonical ordering key for a signal.
 * The ordering is deterministic: same tick/node/sequence always produces same key.
 */
export function createOrderKey(signal: Signal, options: SignalOrderingOptions = {}): SignalOrderKey {
  return {
    tick: extractTick(signal, options),
    node: signal.node,
    sequence: extractSequence(signal, options),
  };
}

/**
 * Compares two ordering keys for deterministic sorting.
 * Returns negative if a < b, positive if a > b, 0 if equal.
 */
export function compareOrderKeys(a: SignalOrderKey, b: SignalOrderKey): number {
  // Primary: tick (ascending)
  if (a.tick !== b.tick) return a.tick - b.tick;
  // Secondary: node (lexicographic for determinism)
  if (a.node !== b.node) return a.node < b.node ? -1 : 1;
  // Tertiary: sequence (ascending)
  if (a.sequence !== b.sequence) return a.sequence - b.sequence;
  return 0;
}

/**
 * Attaches a canonical order key to a signal without mutation.
 */
export function withOrderKey(signal: Signal, options: SignalOrderingOptions = {}): OrderedSignal {
  return {
    ...signal,
    orderKey: createOrderKey(signal, options),
  };
}

/**
 * Sorts signals into canonical order by tick, node, sequence.
 * This operation is deterministic - same input always produces same output.
 */
export function orderSignals(signals: Signal[], options: SignalOrderingOptions = {}): OrderedSignal[] {
  const ordered: OrderedSignal[] = signals.map((s) => withOrderKey(s, options));
  return ordered.sort((a, b) => compareOrderKeys(a.orderKey, b.orderKey));
}

/**
 * Groups signals by node while preserving canonical order within each group.
 * Returns a Map of node -> ordered signals.
 */
export function groupByNode(signals: OrderedSignal[]): Map<string, OrderedSignal[]> {
  const groups = new Map<string, OrderedSignal[]>();
  for (const signal of signals) {
    const existing = groups.get(signal.node);
    if (existing) {
      existing.push(signal);
    } else {
      groups.set(signal.node, [signal]);
    }
  }
  return groups;
}

/**
 * Verifies that a list of ordered signals maintains canonical ordering.
 * Returns true if ordered correctly, false otherwise.
 */
export function verifyOrder(signals: OrderedSignal[]): boolean {
  for (let i = 1; i < signals.length; i++) {
    if (compareOrderKeys(signals[i - 1].orderKey, signals[i].orderKey) > 0) {
      return false;
    }
  }
  return true;
}

/**
 * Default options for signal ordering.
 */
export const DEFAULT_ORDERING_OPTIONS: SignalOrderingOptions = {
  tickField: '_tick',
  sequenceField: '_seq',
};
