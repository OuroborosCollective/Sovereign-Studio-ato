/**
 * Deterministic Iterable Primitives - internal allowlist adapter.
 *
 * Issue #1170: the only iterator primitives permitted on the signal truth
 * path are a bounded, deterministic subset. Random, infinite, wall-clock and
 * unbounded async generators MUST NOT be reachable from this module.
 *
 * The primitives are implemented natively (stdlib-only) instead of importing an
 * external package, so that no unknown supply-chain dependency enters the
 * runtime truth path. The documented candidate (`itertools-ts`) was evaluated:
 * it is MIT-licensed and browser/Node compatible, but adding it would introduce
 * an extra runtime dependency whose surface exceeds the allowlist below. Only
 * the allowlisted functions are exported; nothing else is re-exported.
 *
 * @module predictive/pipeline/deterministicIterables
 */

/**
 * Allowed primitive names exported by this module. A contract test asserts that
 * the module's exported keys equal exactly this set.
 */
export const DETERMINISTIC_ITERABLE_ALLOWLIST = [
  'chunkwise',
  'chunkwiseOverlap',
  'pairwise',
  'zipEqual',
  'groupBy',
  'runningDifference',
  'runningTotal',
  'toMinMax',
] as const;

/** Yield successive fixed-size chunks from an iterable. */
export function* chunkwise<T>(items: Iterable<T>, size: number): Generator<T[]> {
  if (!Number.isInteger(size) || size <= 0) {
    throw new RangeError('chunk size must be a positive integer');
  }
  let chunk: T[] = [];
  for (const item of items) {
    chunk.push(item);
    if (chunk.length === size) {
      yield chunk;
      chunk = [];
    }
  }
  if (chunk.length > 0) {
    yield chunk;
  }
}

/** Yield overlapping windows of the given size, advancing by `step`. */
export function* chunkwiseOverlap<T>(items: Iterable<T>, size: number, step: number): Generator<T[]> {
  if (!Number.isInteger(size) || size <= 0) {
    throw new RangeError('window size must be a positive integer');
  }
  if (!Number.isInteger(step) || step <= 0) {
    throw new RangeError('step must be a positive integer');
  }
  const buffer: T[] = [];
  for (const item of items) {
    buffer.push(item);
    if (buffer.length >= size) {
      yield buffer.slice(buffer.length - size, buffer.length);
      const drop = step;
      if (drop >= buffer.length) {
        buffer.length = 0;
      } else {
        buffer.splice(0, drop);
      }
    }
  }
}

/** Yield consecutive (prev, curr) pairs. Empty/single inputs yield nothing. */
export function* pairwise<T>(items: Iterable<T>): Generator<[T, T]> {
  let prev: T | undefined;
  let hasPrev = false;
  for (const item of items) {
    if (hasPrev) {
      yield [prev as T, item];
    }
    prev = item;
    hasPrev = true;
  }
}

/** Zip iterables element-wise. Throws if lengths differ (parity contract). */
export function* zipEqual<T>(...iterables: Iterable<T>[]): Generator<T[]> {
  if (iterables.length === 0) {
    return;
  }
  const iterators = iterables.map(it => it[Symbol.iterator]());
  try {
    while (true) {
      const results = iterators.map(it => it.next());
      const anyDone = results.some(r => r.done);
      const allDone = results.every(r => r.done);
      if (anyDone !== allDone) {
        throw new RangeError('zipEqual: iterables have unequal lengths');
      }
      if (allDone) {
        return;
      }
      yield results.map(r => r.value);
    }
  } finally {
    for (const it of iterators) {
      it.return?.();
    }
  }
}

/** Group consecutive equal elements (by key) into [key, values[]] pairs. */
export function* groupBy<T, K>(items: Iterable<T>, keyFn: (item: T) => K): Generator<[K, T[]]> {
  let currentKey: K | undefined;
  let currentGroup: T[] = [];
  let hasGroup = false;
  for (const item of items) {
    const key = keyFn(item);
    if (!hasGroup) {
      currentKey = key;
      currentGroup = [item];
      hasGroup = true;
    } else if (Object.is(key, currentKey)) {
      currentGroup.push(item);
    } else {
      yield [currentKey as K, currentGroup];
      currentKey = key;
      currentGroup = [item];
    }
  }
  if (hasGroup) {
    yield [currentKey as K, currentGroup];
  }
}

/** Yield the running difference between consecutive elements. */
export function* runningDifference(items: Iterable<number>): Generator<number> {
  let prev: number | undefined;
  let hasPrev = false;
  for (const item of items) {
    if (hasPrev) {
      yield item - (prev as number);
    }
    prev = item;
    hasPrev = true;
  }
}

/** Yield the running total (prefix sum). */
export function* runningTotal(items: Iterable<number>): Generator<number> {
  let total = 0;
  for (const item of items) {
    total += item;
    yield total;
  }
}

/** Reduce an iterable to its [min, max] bounds. Empty input returns undefined. */
export function toMinMax(items: Iterable<number>): [number, number] | undefined {
  let min: number | undefined;
  let max: number | undefined;
  for (const item of items) {
    if (min === undefined || item < min) {
      min = item;
    }
    if (max === undefined || item > max) {
      max = item;
    }
  }
  if (min === undefined || max === undefined) {
    return undefined;
  }
  return [min, max];
}
