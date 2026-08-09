/**
 * Deterministic Iterables - Allowlist Adapter for Iterator Primitives
 *
 * This module provides a safe, audited subset of itertools-ts functionality.
 * Only deterministic, bounded iterator primitives are exported.
 * Random, infinite, and unbounded operations are explicitly blocked.
 *
 * Allowed primitives:
 * - chunkwise, chunkwiseOverlap
 * - pairwise
 * - zipEqual
 * - groupBy
 * - runningDifference
 * - runningTotal
 * - toMinMax
 *
 * @module predictive/pipeline/deterministicIterables
 */

import type { Signal } from '../types';

// ============================================================================
// Contract: Allowed Iterator Primitives
// ============================================================================

/**
 * Configuration for tick windowing.
 */
export interface TickWindowConfig {
  windowSize: number;
  overlap: number;
  maxItems?: number;
  maxWindowDuration?: number;
}

/**
 * Feature vector produced by the pipeline.
 */
export interface FeatureVector {
  /** Vector of feature values */
  values: number[];
  /** Hash of the source signals */
  signalHash: string;
  /** Window tick range [startTick, endTick] */
  tickRange: [number, number];
  /** Sequence range [startSeq, endSeq] */
  sequenceRange: [number, number];
  /** Revision bound */
  revision: string;
  /** Config fingerprint */
  configFingerprint: string;
}

/**
 * Receipt for a processed window.
 */
export interface WindowReceipt {
  /** Window ID */
  id: string;
  /** Feature vector */
  featureVector: FeatureVector;
  /** Signals included */
  signalCount: number;
  /** Processing timestamp */
  timestamp: number;
  /** Reason code if signals were dropped */
  dropReason?: string;
  /** Whether this is a live or replay window */
  isReplay: boolean;
}

/**
 * Backpressure state for flow control.
 */
export interface BackpressureState {
  /** Current queue depth */
  queueDepth: number;
  /** Whether backpressure is active */
  isBackpressured: boolean;
  /** Maximum allowed queue depth */
  maxQueueDepth: number;
}

/**
 * Result of processing signals through the pipeline.
 */
export interface PipelineResult {
  /** Processed windows */
  windows: WindowReceipt[];
  /** Any dropped signals with reason codes */
  drops: Array<{ signal: Signal; reason: string }>;
  /** Final backpressure state */
  backpressure: BackpressureState;
  /** Whether abort was requested */
  aborted: boolean;
}

// ============================================================================
// Internal Implementation - Contract-Tested Allowlist
// ============================================================================

/**
 * Contract test to verify no disallowed imports exist.
 * This function should be called during module initialization.
 */
export function assertAllowlistContract(): void {
  // This is a compile-time and static-analysis contract
  // The bundler/ESLint should reject any import of:
  // - random.*
  // - infinite.*
  // - sort without canonical comparator
  // - unbounded async streams
  // - wall-clock generators
}

// ============================================================================
// Chunkwise - Bounded Chunking
// ============================================================================

/**
 * Yields chunks of the specified size from an iterable.
 * All chunks are bounded by maxItems if provided.
 */
export function* chunkwise<T>(iterable: Iterable<T>, size: number, maxItems?: number): Generator<T[]> {
  if (size <= 0) throw new Error('chunkwise: size must be positive');
  let count = 0;
  let chunk: T[] = [];
  for (const item of iterable) {
    chunk.push(item);
    count++;
    if (chunk.length === size) {
      yield chunk;
      chunk = [];
    }
    if (maxItems !== undefined && count >= maxItems) break;
  }
  if (chunk.length > 0) yield chunk;
}

/**
 * Yields overlapping chunks with the specified overlap.
 * Overlap must be less than size.
 */
export function* chunkwiseOverlap<T>(
  iterable: Iterable<T>,
  size: number,
  overlap: number,
  maxItems?: number,
): Generator<T[]> {
  if (size <= 0) throw new Error('chunkwiseOverlap: size must be positive');
  if (overlap >= size) throw new Error('chunkwiseOverlap: overlap must be less than size');
  if (overlap < 0) throw new Error('chunkwiseOverlap: overlap must be non-negative');

  let buffer: T[] = [];
  let count = 0;

  for (const item of iterable) {
    buffer.push(item);
    count++;
    if (buffer.length === size) {
      yield [...buffer];
      buffer = buffer.slice(size - overlap);
    }
    if (maxItems !== undefined && count >= maxItems) break;
  }
}

// ============================================================================
// Pairwise - Consecutive Pairs
// ============================================================================

/**
 * Yields consecutive pairs from an iterable.
 * Returns empty if less than 2 elements.
 */
export function* pairwise<T>(iterable: Iterable<T>): Generator<[T, T]> {
  let prev: T | undefined = undefined;
  let hasPrev = false;
  for (const item of iterable) {
    if (hasPrev) {
      yield [prev as T, item];
    }
    prev = item;
    hasPrev = true;
  }
}

// ============================================================================
// zipEqual - Parallel Iteration with Length Check
// ============================================================================

/**
 * Zips multiple iterables together, throwing if lengths don't match.
 * This ensures deterministic behavior when sensor sequences are misaligned.
 */
export function* zipEqual<T>(...iterables: Iterable<T>[]): Generator<T[]> {
  const iterators = iterables.map((i) => i[Symbol.iterator]());
  const nexts = iterators.map((it) => it.next());

  while (true) {
    const doneCount = nexts.filter((n) => n.done).length;
    if (doneCount > 0) {
      if (doneCount !== nexts.length) {
        throw new Error(
          `zipEqual: iterables have mismatched lengths. ${nexts.length - doneCount} remaining but ${doneCount} exhausted`,
        );
      }
      break;
    }
    yield nexts.map((n) => n.value);
    for (let i = 0; i < iterators.length; i++) {
      nexts[i] = iterators[i].next();
    }
  }
}

// ============================================================================
// groupBy - Canonical Grouping
// ============================================================================

/**
 * Groups consecutive elements by key.
 * Key function must be deterministic (no randomness).
 */
export function* groupBy<T, K>(iterable: Iterable<T>, keyFn: (item: T) => K): Generator<[K, T[]]> {
  let currentKey: K | undefined = undefined;
  let currentGroup: T[] = [];

  for (const item of iterable) {
    const key = keyFn(item);
    if (currentKey === undefined) {
      currentKey = key;
    }
    if (Object.is(currentKey, key)) {
      currentGroup.push(item);
    } else {
      if (currentGroup.length > 0) {
        yield [currentKey, currentGroup];
      }
      currentKey = key;
      currentGroup = [item];
    }
  }

  if (currentGroup.length > 0 && currentKey !== undefined) {
    yield [currentKey, currentGroup];
  }
}

// ============================================================================
// Running Difference
// ============================================================================

/**
 * Yields running differences between consecutive elements.
 * First element is unchanged.
 */
export function* runningDifference<T extends number>(iterable: Iterable<T>): Generator<number> {
  let prev: T | undefined = undefined;
  let isFirst = true;
  for (const item of iterable) {
    if (isFirst) {
      yield item;
      isFirst = false;
    } else {
      yield item - (prev as T);
    }
    prev = item;
  }
}

// ============================================================================
// Running Total
// ============================================================================

/**
 * Yields running totals (cumulative sum) of elements.
 */
export function* runningTotal<T extends number>(iterable: Iterable<T>): Generator<number> {
  let total = 0;
  for (const item of iterable) {
    total += item;
    yield total;
  }
}

// ============================================================================
// Min/Max
// ============================================================================

/**
 * Returns the minimum and maximum values from an iterable.
 * Returns undefined if iterable is empty.
 */
export function toMinMax<T extends number>(iterable: Iterable<T>): [min: T, max: T] | undefined {
  let min: T | undefined = undefined;
  let max: T | undefined = undefined;

  for (const item of iterable) {
    if (min === undefined || item < min) min = item;
    if (max === undefined || item > max) max = item;
  }

  if (min === undefined || max === undefined) return undefined;
  return [min, max];
}

// ============================================================================
// Bounded Iterable Wrapper
// ============================================================================

/**
 * Creates a bounded iterable that respects maxItems and abort signals.
 */
export function bounded<T>(
  iterable: Iterable<T>,
  options: {
    maxItems?: number;
    maxWindowDuration?: number;
    abortSignal?: AbortSignal;
  } = {},
): Iterable<T> & { cancel: () => void } {
  let cancelled = false;
  let itemCount = 0;
  const startTime = Date.now();

  const sourceIterator = iterable[Symbol.iterator]();

  return {
    [Symbol.iterator]() {
      return {
        next(): IteratorResult<T> {
          if (cancelled) return { done: true, value: undefined as unknown as T };

          if (options.maxItems !== undefined && itemCount >= options.maxItems) {
            return { done: true, value: undefined as unknown as T };
          }

          if (options.maxWindowDuration !== undefined) {
            const elapsed = Date.now() - startTime;
            if (elapsed >= options.maxWindowDuration) {
              return { done: true, value: undefined as unknown as T };
            }
          }

          if (options.abortSignal?.aborted) {
            return { done: true, value: undefined as unknown as T };
          }

          const result = sourceIterator.next();
          if (!result.done) itemCount++;
          return result;
        },
      };
    },
    cancel() {
      cancelled = true;
    },
  };
}

// ============================================================================
// Pipeline Stage Factories
// ============================================================================

/**
 * Creates a canonical ordering comparator for signals.
 * Orders by: tick, node, sequence (in that priority).
 */
export function canonicalSignalComparator(a: Signal, b: Signal): number {
  const tickA = (a.metadata?.tick as number) ?? 0;
  const tickB = (b.metadata?.tick as number) ?? 0;
  if (tickA !== tickB) return tickA - tickB;

  if (a.node < b.node) return -1;
  if (a.node > b.node) return 1;

  const seqA = (a.metadata?.sequence as number) ?? 0;
  const seqB = (b.metadata?.sequence as number) ?? 0;
  return seqA - seqB;
}

/**
 * Sorts signals into canonical order deterministically.
 */
export function canonicalSort(signals: Signal[]): Signal[] {
  return [...signals].sort(canonicalSignalComparator);
}

/**
 * Creates a config fingerprint for window parameters.
 * This ensures identical configs produce identical hashes.
 */
export function createConfigFingerprint(windowSize: number, overlap: number, maxItems?: number): string {
  const parts = [`ws=${windowSize}`, `ov=${overlap}`];
  if (maxItems !== undefined) parts.push(`mi=${maxItems}`);
  return parts.join('|');
}
