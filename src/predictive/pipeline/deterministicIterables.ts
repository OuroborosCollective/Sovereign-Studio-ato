/**
 * Deterministic Iterables - Allowlist Adapter
 *
 * This module provides a curated set of iterator primitives that are safe
 * for deterministic signal processing. Only explicitly approved functions
 * are exported to prevent non-deterministic behavior.
 *
 * Allowed functions:
 * - chunkwise, chunkwiseOverlap, pairwise, zipEqual
 * - groupBy, runningDifference, runningTotal, toMinMax
 *
 * Blocked patterns (not exported):
 * - random.*, infinite.*, unbounded async streams
 * - sort without canonical comparator, wall-clock generators
 *
 * @module predictive/pipeline/deterministicIterables
 */

/**
 * Configuration for the iterable adapter.
 * All settings are deterministic - no wall-clock dependencies.
 */
export interface DeterministicIterableConfig {
  /** Default chunk size for chunkwise operations */
  defaultChunkSize: number;
  /** Default overlap for chunkwiseOverlap operations */
  defaultOverlap: number;
  /** Maximum items allowed (backpressure limit) */
  maxItems: number;
  /** Maximum window items */
  maxWindowItems: number;
}

export const DEFAULT_DETERMINISTIC_CONFIG: DeterministicIterableConfig = {
  defaultChunkSize: 10,
  defaultOverlap: 2,
  maxItems: 10000,
  maxWindowItems: 1000,
};

// ============================================================================
// Core Iterator Types
// ============================================================================

/**
 * Base interface for all signal-like items in the pipeline.
 * Must have deterministic ordering fields.
 */
export interface PipelineItem {
  /** Causal tick counter - not wall-clock */
  tick: number;
  /** Node identifier */
  node: string;
  /** Sequence number for same-tick ordering */
  sequence: number;
  /** Revision hash for cache invalidation */
  revision?: string;
}

/**
 * Result of a chunking operation with metadata.
 */
export interface ChunkResult<T> {
  items: T[];
  startIndex: number;
  endIndex: number;
  isPartial: boolean;
}

/**
 * Result of a pairwise operation.
 */
export interface PairResult<T> {
  previous: T | undefined;
  current: T;
  index: number;
}

/**
 * Result of zipEqual when lengths don't match.
 */
export class LengthMismatchError extends Error {
  constructor(
    public readonly leftLength: number,
    public readonly rightLength: number,
    public readonly operation: string,
  ) {
    super(
      `Length mismatch in ${operation}: left=${leftLength}, right=${rightLength}`,
    );
    this.name = 'LengthMismatchError';
  }
}

// ============================================================================
// Chunkwise Operations
// ============================================================================

/**
 * Generator that yields chunks of the specified size.
 * Deterministic: same input order always produces same chunks.
 *
 * @example
 * const signals = [{tick: 1, node: 'a', sequence: 0}, ...];
 * for (const chunk of chunkwise(signals, 3)) { ... }
 */
export function* chunkwise<T>(
  iterable: Iterable<T>,
  size: number,
): Generator<ChunkResult<T>> {
  if (size <= 0) {
    throw new Error('Chunk size must be positive');
  }

  let buffer: T[] = [];
  let index = 0;

  for (const item of iterable) {
    buffer.push(item);
    if (buffer.length === size) {
      yield {
        items: [...buffer],
        startIndex: index - size + 1,
        endIndex: index,
        isPartial: false,
      };
      buffer = [];
    }
    index++;
  }

  // Yield remaining items as partial chunk
  if (buffer.length > 0) {
    yield {
      items: buffer,
      startIndex: index - buffer.length,
      endIndex: index - 1,
      isPartial: true,
    };
  }
}

/**
 * Generator that yields overlapping chunks.
 * Useful for sliding window analysis with overlap.
 *
 * @example
 * for (const chunk of chunkwiseOverlap(signals, 5, 2)) { ... }
 */
export function* chunkwiseOverlap<T>(
  iterable: Iterable<T>,
  size: number,
  step: number,
): Generator<ChunkResult<T>> {
  if (size <= 0) {
    throw new Error('Chunk size must be positive');
  }
  if (step <= 0) {
    throw new Error('Step must be positive');
  }
  if (step > size) {
    throw new Error('Step cannot be greater than size');
  }

  let buffer: T[] = [];
  let index = 0;
  let startIndex = 0;

  for (const item of iterable) {
    buffer.push(item);
    if (buffer.length === size) {
      yield {
        items: [...buffer],
        startIndex,
        endIndex: startIndex + size - 1,
        isPartial: false,
      };
      startIndex += step;
      buffer = buffer.slice(step);
      index++;
    }
  }

  // Yield remaining items as partial chunk
  if (buffer.length > 0) {
    yield {
      items: buffer,
      startIndex,
      endIndex: startIndex + buffer.length - 1,
      isPartial: true,
    };
  }
}

// ============================================================================
// Pairwise Operations
// ============================================================================

/**
 * Yields successive pairs from an iterable.
 * First yield has undefined as previous.
 *
 * @example
 * for (const {previous, current} of pairwise([1, 2, 3])) {
 *   // yields: {previous: undefined, current: 1}, {previous: 1, current: 2}, ...
 * }
 */
export function* pairwise<T>(
  iterable: Iterable<T>,
): Generator<PairResult<T>> {
  let previous: T | undefined = undefined;
  let index = 0;

  for (const current of iterable) {
    yield { previous, current, index };
    previous = current;
    index++;
  }
}

// ============================================================================
// Zip Operations
// ============================================================================

/**
 * Zips two iterables together, but throws if lengths don't match.
 * Ensures deterministic pairing without silent failures.
 *
 * @throws {LengthMismatchError} When iterables have different lengths
 *
 * @example
 * for (const [a, b] of zipEqual([1, 2], [3, 4])) { ... }
 */
export function* zipEqual<T, U>(
  left: Iterable<T>,
  right: Iterable<U>,
): Generator<[T, U]> {
  const leftIter = left[Symbol.iterator]();
  const rightIter = right[Symbol.iterator]();

  let leftResult = leftIter.next();
  let rightResult = rightIter.next();

  while (!leftResult.done && !rightResult.done) {
    yield [leftResult.value, rightResult.value];
    leftResult = leftIter.next();
    rightResult = rightIter.next();
  }

  // Check for length mismatch
  if (leftResult.done !== rightResult.done) {
    const leftCount = countUntilDone(left[Symbol.iterator]().next);
    const rightCount = countUntilDone(right[Symbol.iterator]().next);
    throw new LengthMismatchError(
      leftResult.done ? leftCount : leftCount + 1,
      rightResult.done ? rightCount : rightCount + 1,
      'zipEqual',
    );
  }
}

function countUntilDone(
  next: () => IteratorResult<unknown>,
): number {
  let count = 0;
  while (!next().done) {
    count++;
  }
  return count;
}

/**
 * Zips multiple iterables together, throws on mismatch.
 */
export function* zipEqualN<T extends unknown[][]>(
  ...iterables: { [K in keyof T]: Iterable<T[K]> }
): Generator<T> {
  if (iterables.length === 0) return;

  const iterators = iterables.map((i) => i[Symbol.iterator]());
  const results = iterators.map((it) => it.next());

  while (results.every((r) => !r.done)) {
    yield results.map((r) => r.value) as T;
    for (let i = 0; i < iterators.length; i++) {
      results[i] = iterators[i].next();
    }
  }

  // Check all finished at same time
  const doneCount = results.filter((r) => r.done).length;
  if (doneCount !== 0 && doneCount !== results.length) {
    throw new LengthMismatchError(
      results[0].done ? iterables.length : iterables.length + 1,
      results[1].done ? iterables.length : iterables.length + 1,
      `zipEqualN(${iterables.length})`,
    );
  }
}

// ============================================================================
// GroupBy Operations
// ============================================================================

/**
 * Groups items by a key function.
 * Deterministic: preserves insertion order within groups.
 *
 * @example
 * const signals = [{node: 'a', ...}, {node: 'b', ...}, {node: 'a', ...}];
 * const grouped = groupBy(signals, s => s.node);
 * // grouped.get('a') = [items with node 'a']
 */
export function groupBy<T, K extends string | number | symbol>(
  iterable: Iterable<T>,
  keyFn: (item: T) => K,
): Map<K, T[]> {
  const result = new Map<K, T[]>();

  for (const item of iterable) {
    const key = keyFn(item);
    const group = result.get(key);
    if (group) {
      group.push(item);
    } else {
      result.set(key, [item]);
    }
  }

  return result;
}

/**
 * Groups pipeline items by node, then sorts by tick/sequence within each group.
 * Ensures deterministic ordering within groups.
 */
export function groupByNode<T extends PipelineItem>(
  items: Iterable<T>,
): Map<string, T[]> {
  const grouped = groupBy(items, (item) => item.node);

  // Sort each group by tick, then sequence for determinism
  for (const group of grouped.values()) {
    group.sort((a, b) => {
      if (a.tick !== b.tick) return a.tick - b.tick;
      return a.sequence - b.sequence;
    });
  }

  return grouped;
}

// ============================================================================
// Running Statistics
// ============================================================================

/**
 * Yields running difference between consecutive items.
 * First item yields undefined as previous.
 *
 * @example
 * for (const {previous, current, diff} of runningDifference([1, 3, 6])) {
 *   // yields: {diff: undefined}, {diff: 2}, {diff: 3}
 * }
 */
export interface RunningDiffResult<T, V = number> {
  previous: T | undefined;
  current: T;
  diff: V | undefined;
  index: number;
}

export function* runningDifference<T>(
  iterable: Iterable<T>,
  valueFn: (item: T) => number = (item) => item as unknown as number,
): Generator<RunningDiffResult<T, number>> {
  let previous: T | undefined = undefined;
  let previousValue: number | undefined = undefined;
  let index = 0;

  for (const current of iterable) {
    const currentValue = valueFn(current);
    const diff = previousValue !== undefined ? currentValue - previousValue : undefined;

    yield { previous, current, diff, index };
    previous = current;
    previousValue = currentValue;
    index++;
  }
}

/**
 * Yields running total (cumulative sum) of values.
 */
export interface RunningTotalResult<T> {
  item: T;
  total: number;
  index: number;
}

export function* runningTotal<T>(
  iterable: Iterable<T>,
  valueFn: (item: T) => number = (item) => item as unknown as number,
): Generator<RunningTotalResult<T>> {
  let total = 0;
  let index = 0;

  for (const item of iterable) {
    total += valueFn(item);
    yield { item, total, index };
    index++;
  }
}

/**
 * Yields min/max as sliding window advances.
 */
export interface MinMaxResult<T> {
  min: T;
  max: T;
  minValue: number;
  maxValue: number;
  windowSize: number;
  index: number;
}

export function* toMinMax<T>(
  iterable: Iterable<T>,
  valueFn: (item: T) => number = (item) => item as unknown as number,
): Generator<MinMaxResult<T>> {
  const buffer: T[] = [];
  let index = 0;

  for (const item of iterable) {
    buffer.push(item);

    if (buffer.length > 0) {
      let minItem = buffer[0];
      let maxItem = buffer[0];
      let minVal = valueFn(minItem);
      let maxVal = valueFn(maxItem);

      for (let i = 1; i < buffer.length; i++) {
        const val = valueFn(buffer[i]);
        if (val < minVal) {
          minVal = val;
          minItem = buffer[i];
        }
        if (val > maxVal) {
          maxVal = val;
          maxItem = buffer[i];
        }
      }

      yield {
        min: minItem,
        max: maxItem,
        minValue: minVal,
        maxValue: maxVal,
        windowSize: buffer.length,
        index,
      };
    }
    index++;
  }
}

// ============================================================================
// Bounded Iterable Wrapper
// ============================================================================

/**
 * Options for bounded iteration with backpressure.
 */
export interface BoundedIterationOptions {
  /** Maximum items to process */
  maxItems?: number;
  /** Maximum window size */
  maxWindowItems?: number;
  /** Abort signal for cancellation */
  signal?: AbortSignal;
  /** Called with progress updates */
  onProgress?: (processed: number, total: number) => void;
}

/**
 * Creates a bounded wrapper around an iterable with backpressure control.
 * Respects AbortSignal for cancellation.
 */
export function withBoundedIteration<T>(
  iterable: Iterable<T>,
  options: BoundedIterationOptions = {},
): Generator<T> {
  const {
    maxItems = DEFAULT_DETERMINISTIC_CONFIG.maxItems,
    maxWindowItems = DEFAULT_DETERMINISTIC_CONFIG.maxWindowItems,
    signal,
    onProgress,
  } = options;

  let processed = 0;
  const iterator = iterable[Symbol.iterator]();

  return (function* boundedGenerator(): Generator<T> {
    if (signal?.aborted) return;

    let result = iterator.next();

    while (!result.done) {
      // Check abort signal
      if (signal?.aborted) {
        throw new DOMException('Iteration aborted', 'AbortError');
      }

      // Check max items
      if (processed >= maxItems) {
        throw new Error(`Max items limit reached: ${maxItems}`);
      }

      yield result.value;
      processed++;

      if (onProgress) {
        onProgress(processed, maxItems);
      }

      result = iterator.next();
    }
  })();
}

// ============================================================================
// Export Registry for Contract Testing
// ============================================================================

/**
 * Registry of all exported functions for contract testing.
 * Used to verify no random/infinite functions are accidentally added.
 */
export const DETERMINISTIC_ITERABLE_EXPORTS = [
  'chunkwise',
  'chunkwiseOverlap',
  'pairwise',
  'zipEqual',
  'zipEqualN',
  'groupBy',
  'groupByNode',
  'runningDifference',
  'runningTotal',
  'toMinMax',
  'withBoundedIteration',
  'LengthMismatchError',
  'DEFAULT_DETERMINISTIC_CONFIG',
] as const;

/**
 * Blocked patterns that should NEVER appear in exports.
 * Used by contract tests.
 */
export const BLOCKED_PATTERNS = [
  'random',
  'Random',
  'infinite',
  'Infinite',
  'shuffle',
  'Shuffle',
] as const;
