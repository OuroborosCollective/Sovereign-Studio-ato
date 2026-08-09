/**
 * Tests for Deterministic Iterables
 *
 * @module predictive/pipeline/deterministicIterables.test
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  chunkwise,
  chunkwiseOverlap,
  pairwise,
  zipEqual,
  groupBy,
  runningDifference,
  runningTotal,
  toMinMax,
  bounded,
  canonicalSignalComparator,
  canonicalSort,
  createConfigFingerprint,
} from './deterministicIterables';
import type { Signal } from '../types';

describe('deterministicIterables', () => {
  // ========== chunkwise ==========
  describe('chunkwise', () => {
    it('should split array into chunks of specified size', () => {
      const input = [1, 2, 3, 4, 5];
      const result = [...chunkwise(input, 2)];
      expect(result).toEqual([[1, 2], [3, 4], [5]]);
    });

    it('should handle size equal to array length', () => {
      const input = [1, 2, 3];
      const result = [...chunkwise(input, 3)];
      expect(result).toEqual([[1, 2, 3]]);
    });

    it('should handle size greater than array length', () => {
      const input = [1, 2];
      const result = [...chunkwise(input, 5)];
      expect(result).toEqual([[1, 2]]);
    });

    it('should respect maxItems', () => {
      const input = [1, 2, 3, 4, 5, 6, 7];
      const result = [...chunkwise(input, 2, 4)];
      expect(result).toEqual([[1, 2], [3, 4]]);
    });

    it('should throw on invalid size', () => {
      expect(() => [...chunkwise([1, 2, 3], 0)]).toThrow('size must be positive');
      expect(() => [...chunkwise([1, 2, 3], -1)]).toThrow('size must be positive');
    });

    it('should handle empty input', () => {
      const result = [...chunkwise([], 2)];
      expect(result).toEqual([]);
    });
  });

  // ========== chunkwiseOverlap ==========
  describe('chunkwiseOverlap', () => {
    it('should create overlapping chunks', () => {
      const input = [1, 2, 3, 4, 5];
      const result = [...chunkwiseOverlap(input, 3, 1)];
      expect(result).toEqual([
        [1, 2, 3],
        [3, 4, 5],
      ]);
    });

    it('should throw when overlap >= size', () => {
      expect(() => [...chunkwiseOverlap([1, 2, 3], 2, 2)]).toThrow('overlap must be less than size');
      expect(() => [...chunkwiseOverlap([1, 2, 3], 2, 3)]).toThrow('overlap must be less than size');
    });

    it('should throw on negative overlap', () => {
      expect(() => [...chunkwiseOverlap([1, 2, 3], 2, -1)]).toThrow('overlap must be non-negative');
    });

    it('should respect maxItems', () => {
      const input = [1, 2, 3, 4, 5, 6];
      const result = [...chunkwiseOverlap(input, 2, 1, 3)];
      // maxItems caps consumed input items at 3: items 1,2,3 yield [1,2] then [2,3]
      expect(result).toEqual([
        [1, 2],
        [2, 3],
      ]);
    });
  });

  // ========== pairwise ==========
  describe('pairwise', () => {
    it('should yield consecutive pairs', () => {
      const input = [1, 2, 3, 4];
      const result = [...pairwise(input)];
      expect(result).toEqual([
        [1, 2],
        [2, 3],
        [3, 4],
      ]);
    });

    it('should return empty for single element', () => {
      const input = [1];
      const result = [...pairwise(input)];
      expect(result).toEqual([]);
    });

    it('should return empty for empty input', () => {
      const input: number[] = [];
      const result = [...pairwise(input)];
      expect(result).toEqual([]);
    });
  });

  // ========== zipEqual ==========
  describe('zipEqual', () => {
    it('should zip arrays of equal length', () => {
      const a = [1, 2, 3];
      const b = ['a', 'b', 'c'];
      const result = [...zipEqual(a, b)];
      expect(result).toEqual([[1, 'a'], [2, 'b'], [3, 'c']]);
    });

    it('should throw on mismatched lengths', () => {
      const a = [1, 2, 3];
      const b = ['a', 'b'];
      expect(() => [...zipEqual(a, b)]).toThrow('mismatched lengths');
    });

    it('should handle single array', () => {
      const a = [1, 2, 3];
      const result = [...zipEqual(a)];
      expect(result).toEqual([[1], [2], [3]]);
    });

    it('should handle empty arrays', () => {
      const result = [...zipEqual([], [])];
      expect(result).toEqual([]);
    });
  });

  // ========== groupBy ==========
  describe('groupBy', () => {
    it('should group by key', () => {
      const input = [
        { type: 'a', value: 1 },
        { type: 'a', value: 2 },
        { type: 'b', value: 3 },
      ];
      const result = [...groupBy(input, (item) => item.type)];
      expect(result).toEqual([
        ['a', [{ type: 'a', value: 1 }, { type: 'a', value: 2 }]],
        ['b', [{ type: 'b', value: 3 }]],
      ]);
    });

    it('should handle empty input', () => {
      const result = [...groupBy([], (x: number) => x)];
      expect(result).toEqual([]);
    });

    it('should group by numeric key', () => {
      // groupBy groups CONSECUTIVE elements sharing a key, so pre-group the input
      // so odd values (1,3) come first, then even values (2,4).
      const input = [1, 3, 2, 4];
      const result = [...groupBy(input, (n) => n % 2)];
      expect(result).toEqual([
        [1, [1, 3]],
        [0, [2, 4]],
      ]);
    });
  });

  // ========== runningDifference ==========
  describe('runningDifference', () => {
    it('should compute running differences', () => {
      const input = [10, 15, 12, 20];
      const result = [...runningDifference(input)];
      expect(result).toEqual([10, 5, -3, 8]);
    });

    it('should handle single element', () => {
      const input = [5];
      const result = [...runningDifference(input)];
      expect(result).toEqual([5]);
    });

    it('should handle empty input', () => {
      const input: number[] = [];
      const result = [...runningDifference(input)];
      expect(result).toEqual([]);
    });
  });

  // ========== runningTotal ==========
  describe('runningTotal', () => {
    it('should compute running totals', () => {
      const input = [1, 2, 3, 4];
      const result = [...runningTotal(input)];
      expect(result).toEqual([1, 3, 6, 10]);
    });

    it('should handle empty input', () => {
      const input: number[] = [];
      const result = [...runningTotal(input)];
      expect(result).toEqual([]);
    });
  });

  // ========== toMinMax ==========
  describe('toMinMax', () => {
    it('should return min and max', () => {
      const input = [3, 1, 4, 1, 5, 9, 2, 6];
      const result = toMinMax(input);
      expect(result).toEqual([1, 9]);
    });

    it('should handle single element', () => {
      const input = [42];
      const result = toMinMax(input);
      expect(result).toEqual([42, 42]);
    });

    it('should return undefined for empty input', () => {
      const input: number[] = [];
      const result = toMinMax(input);
      expect(result).toBeUndefined();
    });
  });

  // ========== bounded ==========
  describe('bounded', () => {
    it('should limit items', () => {
      const input = [1, 2, 3, 4, 5];
      const result = [...bounded(input, { maxItems: 3 })];
      expect(result).toEqual([1, 2, 3]);
    });

    it('should respect abort signal', () => {
      const input = [1, 2, 3, 4, 5];
      const controller = new AbortController();
      controller.abort();
      const result = [...bounded(input, { abortSignal: controller.signal })];
      expect(result).toEqual([]);
    });
  });

  // ========== canonicalSignalComparator ==========
  describe('canonicalSignalComparator', () => {
    function createSignal(overrides: Partial<Signal> = {}): Signal {
      return {
        id: 'sig-1',
        node: 'node-a',
        value: 1,
        timestamp: Date.now(),
        traceId: 'trace-1',
        metadata: {},
        ...overrides,
      };
    }

    it('should order by tick first', () => {
      const a = createSignal({ id: 'a', metadata: { tick: 1, sequence: 1 } });
      const b = createSignal({ id: 'b', metadata: { tick: 2, sequence: 0 } });
      const result = canonicalSignalComparator(a, b);
      expect(result).toBe(-1);
    });

    it('should order by node when tick is equal', () => {
      const a = createSignal({ id: 'a', node: 'node-a', metadata: { tick: 1, sequence: 1 } });
      const b = createSignal({ id: 'b', node: 'node-b', metadata: { tick: 1, sequence: 0 } });
      const result = canonicalSignalComparator(a, b);
      expect(result).toBe(-1);
    });

    it('should order by sequence when tick and node are equal', () => {
      const a = createSignal({ id: 'a', metadata: { tick: 1, sequence: 1 } });
      const b = createSignal({ id: 'b', metadata: { tick: 1, sequence: 2 } });
      const result = canonicalSignalComparator(a, b);
      expect(result).toBe(-1);
    });
  });

  // ========== canonicalSort ==========
  describe('canonicalSort', () => {
    it('should sort signals canonically', () => {
      const signals: Signal[] = [
        {
          id: '3',
          node: 'node-b',
          value: 3,
          timestamp: 0,
          traceId: 't',
          metadata: { tick: 1, sequence: 1 },
        },
        {
          id: '1',
          node: 'node-a',
          value: 1,
          timestamp: 0,
          traceId: 't',
          metadata: { tick: 1, sequence: 0 },
        },
        {
          id: '2',
          node: 'node-a',
          value: 2,
          timestamp: 0,
          traceId: 't',
          metadata: { tick: 0, sequence: 0 },
        },
      ];

      const result = canonicalSort(signals);
      expect(result.map((s) => s.id)).toEqual(['2', '1', '3']);
    });

    it('should return empty array for empty input', () => {
      const result = canonicalSort([]);
      expect(result).toEqual([]);
    });
  });

  // ========== createConfigFingerprint ==========
  describe('createConfigFingerprint', () => {
    it('should create fingerprint with window size and overlap', () => {
      const fp = createConfigFingerprint(10, 5);
      expect(fp).toBe('ws=10|ov=5');
    });

    it('should include maxItems in fingerprint', () => {
      const fp = createConfigFingerprint(10, 5, 100);
      expect(fp).toBe('ws=10|ov=5|mi=100');
    });
  });
});
