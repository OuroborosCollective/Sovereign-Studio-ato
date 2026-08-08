/**
 * Deterministic Bounded Iterable Primitives
 *
 * Provides bounded, deterministic iteration primitives for the signal pipeline.
 * All operations are deterministic - same input produces same output.
 * Random, infinite, and unbounded operations are explicitly excluded.
 *
 * Allowed primitives:
 * - chunkwise: Split into fixed-size chunks
 * - chunkwiseOverlap: Split into fixed-size chunks with overlap
 * - pairwise: Generate consecutive pairs
 * - zipEqual: Zip two arrays, fail on length mismatch
 * - groupBy: Group by key
 * - runningDifference: Running differences
 * - runningTotal: Running totals
 * - toMinMax: Extract min/max from array
 *
 * @module predictive/pipeline/deterministicIterables
 */

export interface ChunkResult<T> {
  items: T[];
  index: number;
  isFirst: boolean;
  isLast: boolean;
}

export interface PairResult<T> {
  previous: T;
  current: T;
  index: number;
}

export interface GroupResult<K, V> {
  key: K;
  items: V[];
  count: number;
}

export interface MinMaxResult<T> {
  min: T;
  max: T;
  minIndex: number;
  maxIndex: number;
}

/**
 * Error thrown when zipEqual encounters length mismatch.
 */
export class LengthMismatchError extends Error {
  constructor(
    public readonly leftLength: number,
    public readonly rightLength: number,
  ) {
    super(`Length mismatch: left=${leftLength}, right=${rightLength}`);
    this.name = 'LengthMismatchError';
  }
}

/**
 * Options for chunkwise operation.
 */
export interface ChunkOptions {
  /** Chunk size (required) */
  size: number;
  /** Step size for non-overlapping chunks (default: size) */
  step?: number;
}

/**
 * Options for chunkwiseOverlap operation.
 */
export interface ChunkOverlapOptions extends ChunkOptions {
  /** Overlap size (default: size / 2) */
  overlap?: number;
}

/**
 * Splits an array into fixed-size chunks.
 * This operation is deterministic.
 */
export function chunkwise<T>(iterable: T[], options: ChunkOptions): ChunkResult<T>[] {
  const { size, step = options.size } = options;
  if (size <= 0) throw new Error('Chunk size must be positive');
  if (step <= 0) throw new Error('Step must be positive');

  const results: ChunkResult<T>[] = [];
  const length = iterable.length;

  for (let start = 0; start < length; start += step) {
    const end = Math.min(start + size, length);
    const items = iterable.slice(start, end);
    if (items.length > 0) {
      results.push({
        items,
        index: results.length,
        isFirst: start === 0,
        isLast: end >= length,
      });
    }
  }

  return results;
}

/**
 * Splits an array into fixed-size chunks with overlap.
 * This operation is deterministic.
 */
export function chunkwiseOverlap<T>(iterable: T[], options: ChunkOverlapOptions): ChunkResult<T>[] {
  const { size, step = options.size, overlap = Math.floor(size / 2) } = options;
  if (size <= 0) throw new Error('Chunk size must be positive');
  if (overlap < 0 || overlap >= size) throw new Error('Overlap must be in [0, size)');
  if (step <= overlap) throw new Error('Step must be greater than overlap');

  const results: ChunkResult<T>[] = [];
  const length = iterable.length;

  for (let start = 0; start < length; start += step - overlap) {
    const end = Math.min(start + size, length);
    const items = iterable.slice(start, end);
    if (items.length > 0) {
      results.push({
        items,
        index: results.length,
        isFirst: start === 0,
        isLast: end >= length,
      });
    }
  }

  return results;
}

/**
 * Generates consecutive pairs from an array.
 * Returns pairs (a[0], a[1]), (a[1], a[2]), ...
 * This operation is deterministic.
 */
export function pairwise<T>(iterable: T[]): PairResult<T>[] {
  const results: PairResult<T>[] = [];
  for (let i = 1; i < iterable.length; i++) {
    results.push({
      previous: iterable[i - 1],
      current: iterable[i],
      index: i - 1,
    });
  }
  return results;
}

/**
 * Zips two arrays together, throwing if lengths don't match.
 * This operation is deterministic.
 */
export function zipEqual<T, U>(left: T[], right: U[]): Array<[T, U]> {
  if (left.length !== right.length) {
    throw new LengthMismatchError(left.length, right.length);
  }
  const results: Array<[T, U]> = new Array(left.length);
  for (let i = 0; i < left.length; i++) {
    results[i] = [left[i], right[i]];
  }
  return results;
}

/**
 * Groups items by a key function.
 * This operation is deterministic.
 */
export function groupBy<T, K>(
  iterable: T[],
  keyFn: (item: T) => K,
): GroupResult<K, T>[] {
  const groups = new Map<K, T[]>();

  for (const item of iterable) {
    const key = keyFn(item);
    const existing = groups.get(key);
    if (existing) {
      existing.push(item);
    } else {
      groups.set(key, [item]);
    }
  }

  const results: GroupResult<K, T>[] = [];
  // Sort keys for deterministic output
  const sortedKeys = Array.from(groups.keys()).sort((a, b) => {
    if (typeof a === 'string' && typeof b === 'string') return a.localeCompare(b);
    if (a < b) return -1;
    if (a > b) return 1;
    return 0;
  });

  for (const key of sortedKeys) {
    const items = groups.get(key)!;
    results.push({
      key,
      items,
      count: items.length,
    });
  }

  return results;
}

/**
 * Computes running differences between consecutive elements.
 * This operation is deterministic.
 */
export function runningDifference<T>(
  iterable: T[],
  diffFn: (prev: T, curr: T) => number = (a, b) => (b as unknown as number) - (a as unknown as number),
): number[] {
  const results: number[] = [];
  for (let i = 1; i < iterable.length; i++) {
    results.push(diffFn(iterable[i - 1], iterable[i]));
  }
  return results;
}

/**
 * Computes running totals (cumulative sum) of numeric values.
 * This operation is deterministic.
 */
export function runningTotal<T>(
  iterable: T[],
  valueFn: (item: T) => number = (x) => x as unknown as number,
): number[] {
  const results: number[] = [];
  let total = 0;
  for (const item of iterable) {
    total += valueFn(item);
    results.push(total);
  }
  return results;
}

/**
 * Extracts min and max values from an array with their indices.
 * This operation is deterministic.
 */
export function toMinMax<T>(
  iterable: T[],
  compareFn: (a: T, b: T) => number = (a, b) => (a as unknown as number) - (b as unknown as number),
): MinMaxResult<T> {
  if (iterable.length === 0) {
    throw new Error('Cannot compute min/max of empty array');
  }

  let minItem = iterable[0];
  let maxItem = iterable[0];
  let minIndex = 0;
  let maxIndex = 0;

  for (let i = 1; i < iterable.length; i++) {
    const item = iterable[i];
    if (compareFn(item, minItem) < 0) {
      minItem = item;
      minIndex = i;
    }
    if (compareFn(item, maxItem) > 0) {
      maxItem = item;
      maxIndex = i;
    }
  }

  return { min: minItem, max: maxItem, minIndex, maxIndex };
}

/**
 * Validates that an iterable contains no random/infinite operations.
 * This is a placeholder for static analysis - full implementation requires build-time analysis.
 */
export function validateDeterministic(iterable: unknown): boolean {
  // Runtime check: ensure we don't have generators that could be infinite
  if (iterable === null || iterable === undefined) return false;
  if (Array.isArray(iterable)) return true;

  // Check for iterator protocol
  if (typeof iterable === 'object' && Symbol.iterator in iterable) {
    const iterator = (iterable as Iterable<unknown>)[Symbol.iterator]();
    // Try to peek at the iterator
    const result = iterator.next();
    // If it's not immediately done and we can't safely iterate, warn
    return !result.done;
  }

  return false;
}
