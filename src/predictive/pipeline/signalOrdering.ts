/**
 * Canonical Signal Ordering.
 *
 * Issue #1170: validated signals are ordered deterministically before grouping.
 * Order is a pure function of (node, sequence, tick). Wall-clock timestamps are
 * metadata only and never participate in ordering or hashing.
 *
 * @module predictive/pipeline/signalOrdering
 */

/** A validated signal entering the pipeline. */
export interface PipelineSignal {
  /** Stable node identifier. */
  node: string;
  /** Causal sequence number (monotonic per node). */
  sequence: number;
  /** Causal logical tick. */
  tick: number;
  /** Wall-clock metadata only; never used for ordering/hashing. */
  timestamp: number;
  /** Numeric sensory value. */
  value: number;
  /** Optional opaque metadata (does not affect ordering). */
  metadata?: Record<string, unknown>;
}

/** Canonical comparator: node asc, then sequence asc, then tick asc. */
export function canonicalSignalCompare(a: PipelineSignal, b: PipelineSignal): number {
  if (a.node < b.node) return -1;
  if (a.node > b.node) return 1;
  if (a.sequence !== b.sequence) return a.sequence - b.sequence;
  return a.tick - b.tick;
}

/**
 * Sort a signal array into canonical order (returns a new array; input is not
 * mutated). Stability is guaranteed because the comparator is total on the
 * causal fields.
 */
export function canonicalOrder(signals: readonly PipelineSignal[]): PipelineSignal[] {
  return [...signals].sort(canonicalSignalCompare);
}

/**
 * Detect duplicate (node, sequence) keys across the input. Duplicate keys would
 * make the causal chain ambiguous and must be surfaced, not silently dropped.
 */
export function findDuplicateKeys(signals: readonly PipelineSignal[]): string[] {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const s of signals) {
    const key = `${s.node}:${s.sequence}`;
    if (seen.has(key)) {
      duplicates.add(key);
    } else {
      seen.add(key);
    }
  }
  return [...duplicates].sort();
}

/** Group canonically-ordered signals by node (preserves canonical order). */
export function groupByNode(signals: readonly PipelineSignal[]): Map<string, PipelineSignal[]> {
  const ordered = canonicalOrder(signals);
  const groups = new Map<string, PipelineSignal[]>();
  for (const s of ordered) {
    const arr = groups.get(s.node);
    if (arr) {
      arr.push(s);
    } else {
      groups.set(s.node, [s]);
    }
  }
  return groups;
}
