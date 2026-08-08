/**
 * Deterministic Iterables Tests
 *
 * Tests for bounded, deterministic iteration primitives.
 *
 * @module predictive/pipeline/deterministicIterables.test
 */

import { describe, it, expect } from 'vitest';
import {
  chunkwise,
  chunkwiseOverlap,
  pairwise,
  zipEqual,
  groupBy,
  runningDifference,
  runningTotal,
  toMinMax,
  LengthMismatchError,
} from './deterministicIterables';
import { orderSignals } from './signalOrdering';

describe('chunkwise', () => {
  it('should split array into chunks', () => {
    const input = [1, 2, 3, 4, 5, 6, 7];
    const result = chunkwise(input, { size: 3 });

    expect(result.length).toBe(3);
    expect(result[0].items).toEqual([1, 2, 3]);
    expect(result[1].items).toEqual([4, 5, 6]);
    expect(result[2].items).toEqual([7]);
  });

  it('should mark first and last chunks', () => {
    const input = [1, 2, 3, 4];
    const result = chunkwise(input, { size: 2 });

    expect(result[0].isFirst).toBe(true);
    expect(result[0].isLast).toBe(false);
    expect(result[1].isFirst).toBe(false);
    expect(result[1].isLast).toBe(true);
  });

  it('should use custom step size', () => {
    const input = [1, 2, 3, 4, 5, 6];
    const result = chunkwise(input, { size: 3, step: 2 });

    expect(result[0].items).toEqual([1, 2, 3]);
    expect(result[1].items).toEqual([3, 4, 5]); // overlaps with previous
    expect(result[2].items).toEqual([5, 6]);
  });

  it('should handle empty array', () => {
    const result = chunkwise([], { size: 3 });
    expect(result).toEqual([]);
  });

  it('should handle array smaller than chunk size', () => {
    const input = [1, 2];
    const result = chunkwise(input, { size: 5 });

    expect(result.length).toBe(1);
    expect(result[0].items).toEqual([1, 2]);
    expect(result[0].isFirst).toBe(true);
    expect(result[0].isLast).toBe(true);
  });

  it('should be deterministic', () => {
    const input = [10, 20, 30, 40, 50];
    const result1 = chunkwise(input, { size: 2 });
    const result2 = chunkwise(input, { size: 2 });

    expect(result1.map((c) => c.items)).toEqual(result2.map((c) => c.items));
  });

  it('should throw on invalid size', () => {
    expect(() => chunkwise([1, 2, 3], { size: 0 })).toThrow('Chunk size must be positive');
    expect(() => chunkwise([1, 2, 3], { size: -1 })).toThrow('Chunk size must be positive');
  });
});

describe('chunkwiseOverlap', () => {
  it('should create overlapping chunks', () => {
    const input = [1, 2, 3, 4, 5, 6, 7, 8];
    const result = chunkwiseOverlap(input, { size: 4, overlap: 2 });

    expect(result[0].items).toEqual([1, 2, 3, 4]);
    expect(result[1].items).toEqual([3, 4, 5, 6]);
    expect(result[2].items).toEqual([5, 6, 7, 8]);
  });

  it('should use default overlap of size/2', () => {
    const input = [1, 2, 3, 4, 5, 6, 7, 8];
    const result = chunkwiseOverlap(input, { size: 4 });

    expect(result[0].items).toEqual([1, 2, 3, 4]);
    expect(result[1].items).toEqual([3, 4, 5, 6]);
  });

  it('should be deterministic', () => {
    const input = [1, 2, 3, 4, 5, 6];
    const result1 = chunkwiseOverlap(input, { size: 3, overlap: 1 });
    const result2 = chunkwiseOverlap(input, { size: 3, overlap: 1 });

    expect(result1.map((c) => c.items)).toEqual(result2.map((c) => c.items));
  });
});

describe('pairwise', () => {
  it('should generate consecutive pairs', () => {
    const input = [1, 2, 3, 4, 5];
    const result = pairwise(input);

    expect(result.length).toBe(4);
    expect(result[0]).toEqual({ previous: 1, current: 2, index: 0 });
    expect(result[1]).toEqual({ previous: 2, current: 3, index: 1 });
    expect(result[2]).toEqual({ previous: 3, current: 4, index: 2 });
    expect(result[3]).toEqual({ previous: 4, current: 5, index: 3 });
  });

  it('should handle empty array', () => {
    expect(pairwise([])).toEqual([]);
  });

  it('should handle single element', () => {
    expect(pairwise([1])).toEqual([]);
  });

  it('should be deterministic', () => {
    const input = [10, 20, 30, 40];
    const result1 = pairwise(input);
    const result2 = pairwise(input);

    expect(result1).toEqual(result2);
  });
});

describe('zipEqual', () => {
  it('should zip arrays of equal length', () => {
    const left = [1, 2, 3];
    const right = ['a', 'b', 'c'];
    const result = zipEqual(left, right);

    expect(result).toEqual([[1, 'a'], [2, 'b'], [3, 'c']]);
  });

  it('should throw LengthMismatchError on length mismatch', () => {
    const left = [1, 2, 3];
    const right = ['a', 'b'];

    expect(() => zipEqual(left, right)).toThrow(LengthMismatchError);
    expect(() => zipEqual(left, right)).toThrow('Length mismatch: left=3, right=2');
  });

  it('should throw on empty arrays with mismatch', () => {
    expect(() => zipEqual([], [1])).toThrow(LengthMismatchError);
    expect(() => zipEqual([1], [])).toThrow(LengthMismatchError);
  });

  it('should be deterministic', () => {
    const left = [1, 2, 3];
    const right = ['a', 'b', 'c'];
    const result1 = zipEqual(left, right);
    const result2 = zipEqual(left, right);

    expect(result1).toEqual(result2);
  });
});

describe('groupBy', () => {
  it('should group by key', () => {
    const input = [
      { type: 'a', value: 1 },
      { type: 'b', value: 2 },
      { type: 'a', value: 3 },
    ];
    const result = groupBy(input, (item) => item.type);

    expect(result.length).toBe(2);
    expect(result.find((g) => g.key === 'a')?.items).toEqual([
      { type: 'a', value: 1 },
      { type: 'a', value: 3 },
    ]);
    expect(result.find((g) => g.key === 'b')?.items).toEqual([
      { type: 'b', value: 2 },
    ]);
  });

  it('should sort keys for deterministic output', () => {
    const input = [
      { type: 'z', value: 1 },
      { type: 'a', value: 2 },
      { type: 'm', value: 3 },
    ];
    const result = groupBy(input, (item) => item.type);

    expect(result[0].key).toBe('a');
    expect(result[1].key).toBe('m');
    expect(result[2].key).toBe('z');
  });

  it('should include count in result', () => {
    const input = [1, 2, 3, 4, 5];
    const result = groupBy(input, (n) => n % 2 === 0 ? 'even' : 'odd');

    const even = result.find((g) => g.key === 'even');
    const odd = result.find((g) => g.key === 'odd');

    expect(even?.count).toBe(2);
    expect(odd?.count).toBe(3);
  });

  it('should be deterministic', () => {
    const input = [
      { category: 'x', name: 'first' },
      { category: 'a', name: 'second' },
      { category: 'x', name: 'third' },
    ];
    const result1 = groupBy(input, (item) => item.category);
    const result2 = groupBy(input, (item) => item.category);

    expect(result1.map((g) => g.key)).toEqual(result2.map((g) => g.key));
    expect(result1.map((g) => g.items.length)).toEqual(result2.map((g) => g.items.length));
  });
});

describe('runningDifference', () => {
  it('should compute differences between consecutive elements', () => {
    const input = [10, 15, 12, 20];
    const result = runningDifference(input);

    expect(result).toEqual([5, -3, 8]);
  });

  it('should use default numeric subtraction', () => {
    const input = [100, 105, 103];
    expect(runningDifference(input)).toEqual([5, -2]);
  });

  it('should handle empty array', () => {
    expect(runningDifference([])).toEqual([]);
  });

  it('should handle single element', () => {
    expect(runningDifference([42])).toEqual([]);
  });

  it('should be deterministic', () => {
    const input = [10, 20, 30, 40];
    const result1 = runningDifference(input);
    const result2 = runningDifference(input);

    expect(result1).toEqual(result2);
  });
});

describe('runningTotal', () => {
  it('should compute cumulative sum', () => {
    const input = [10, 20, 30, 40];
    const result = runningTotal(input);

    expect(result).toEqual([10, 30, 60, 100]);
  });

  it('should handle empty array', () => {
    expect(runningTotal([])).toEqual([]);
  });

  it('should handle single element', () => {
    expect(runningTotal([42])).toEqual([42]);
  });

  it('should be deterministic', () => {
    const input = [1, 2, 3, 4, 5];
    const result1 = runningTotal(input);
    const result2 = runningTotal(input);

    expect(result1).toEqual(result2);
  });
});

describe('toMinMax', () => {
  it('should find min and max', () => {
    const input = [5, 2, 8, 1, 9, 3];
    const result = toMinMax(input);

    expect(result.min).toBe(1);
    expect(result.max).toBe(9);
    expect(result.minIndex).toBe(3);
    expect(result.maxIndex).toBe(4);
  });

  it('should throw on empty array', () => {
    expect(() => toMinMax([])).toThrow('Cannot compute min/max of empty array');
  });

  it('should be deterministic', () => {
    const input = [3, 1, 4, 1, 5, 9, 2, 6];
    const result1 = toMinMax(input);
    const result2 = toMinMax(input);

    expect(result1.min).toEqual(result2.min);
    expect(result1.max).toEqual(result2.max);
    expect(result1.minIndex).toBe(result2.minIndex);
    expect(result1.maxIndex).toBe(result2.maxIndex);
  });
});

describe('Determinism Contract', () => {
  it('should produce identical results across multiple runs', () => {
    const signals = Array.from({ length: 100 }, (_, i) => ({
      id: `sig-${i}`,
      node: i % 2 === 0 ? 'node-a' : 'node-b',
      value: i * 0.01, // deterministic, not random
      timestamp: 1000 + i * 100,
      traceId: `trace-${i}`,
      metadata: { _tick: Math.floor(i / 10), _seq: i % 10 },
    }));

    // Run ordering multiple times
    const results = Array.from({ length: 5 }, () => {
      return orderSignals(signals).map((s) => s.id);
    });

    // All results should be identical
    for (let i = 1; i < results.length; i++) {
      expect(results[i]).toEqual(results[0]);
    }
  });
});
