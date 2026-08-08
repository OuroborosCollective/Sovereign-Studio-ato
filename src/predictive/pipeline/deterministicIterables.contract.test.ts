/**
 * Contract Test: Deterministic Iterables Allowlist
 *
 * This test verifies that only approved iterator functions are exported
 * and no blocked patterns (random, infinite) are present.
 *
 * @module predictive/pipeline/deterministicIterables.contract.test
 */

import { describe, it, expect } from 'vitest';
import * as deterministicIterables from './deterministicIterables';
import {
  DETERMINISTIC_ITERABLE_EXPORTS,
  BLOCKED_PATTERNS,
} from './deterministicIterables';

describe('Deterministic Iterables Contract', () => {
  describe('Export Allowlist', () => {
    const expectedExports = [
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
    ];

    it('should only export allowlisted functions', () => {
      const actualExports = Object.keys(deterministicIterables);

      for (const expected of expectedExports) {
        expect(actualExports).toContain(expected);
      }

      // Check no extra exports
      const extraExports = actualExports.filter(
        (e) => !expectedExports.includes(e) && !e.startsWith('_'),
      );
      expect(extraExports).toHaveLength(0);
    });

    it('should export DETERMINISTIC_ITERABLE_EXPORTS constant', () => {
      expect(DETERMINISTIC_ITERABLE_EXPORTS).toBeDefined();
      expect(Array.isArray(DETERMINISTIC_ITERABLE_EXPORTS)).toBe(true);
      expect(DETERMINISTIC_ITERABLE_EXPORTS).toContain('chunkwise');
      expect(DETERMINISTIC_ITERABLE_EXPORTS).toContain('zipEqual');
    });

    it('should export BLOCKED_PATTERNS constant', () => {
      expect(BLOCKED_PATTERNS).toBeDefined();
      expect(Array.isArray(BLOCKED_PATTERNS)).toBe(true);
      expect(BLOCKED_PATTERNS).toContain('random');
      expect(BLOCKED_PATTERNS).toContain('infinite');
    });
  });

  describe('Blocked Pattern Verification', () => {
    it('should not have blocked patterns in exports', () => {
      const actualExports = Object.keys(deterministicIterables);

      for (const blocked of BLOCKED_PATTERNS) {
        const matchingExports = actualExports.filter((e) =>
          e.toLowerCase().includes(blocked.toLowerCase()),
        );
        expect(matchingExports).toHaveLength(0);
      }
    });

    it('should not have Math.random in chunkwise', () => {
      const source = deterministicIterables.chunkwise.toString();
      expect(source).not.toContain('Math.random');
    });

    it('should not have Date.now in core iteration logic', () => {
      const functions = [
        'chunkwise',
        'chunkwiseOverlap',
        'pairwise',
        'zipEqual',
        'groupBy',
        'groupByNode',
        'runningDifference',
        'runningTotal',
        'toMinMax',
      ];

      for (const fnName of functions) {
        const fn = deterministicIterables[fnName as keyof typeof deterministicIterables];
        if (typeof fn === 'function') {
          const source = fn.toString();
          // Date.now is allowed in metadata/receipt IDs, but not in core iteration
          // We check for direct usage in a way that affects ordering
          expect(source).not.toMatch(/Date\.now\(\).*sort/i);
        }
      }
    });
  });

  describe('Function Signatures', () => {
    it('chunkwise should be a generator function', () => {
      const gen = deterministicIterables.chunkwise([1, 2, 3], 2);
      expect(gen[Symbol.iterator]).toBeDefined();
      expect(typeof gen.next).toBe('function');
    });

    it('pairwise should be a generator function', () => {
      const gen = deterministicIterables.pairwise([1, 2, 3]);
      expect(gen[Symbol.iterator]).toBeDefined();
    });

    it('zipEqual should throw on length mismatch', () => {
      expect(() => {
        const result: number[] = [];
        for (const pair of deterministicIterables.zipEqual([1, 2, 3], [1, 2])) {
          result.push(pair[0]);
        }
      }).toThrow();
    });

    it('zipEqual should work with equal lengths', () => {
      const result: [number, number][] = [];
      for (const pair of deterministicIterables.zipEqual([1, 2, 3], [4, 5, 6])) {
        result.push(pair);
      }
      expect(result).toEqual([
        [1, 4],
        [2, 5],
        [3, 6],
      ]);
    });

    it('groupBy should return Map', () => {
      const result = deterministicIterables.groupBy(
        [
          { id: '1', node: 'a' },
          { id: '2', node: 'b' },
          { id: '3', node: 'a' },
        ],
        (item) => item.node,
      );
      expect(result).toBeInstanceOf(Map);
      expect(result.get('a')).toHaveLength(2);
      expect(result.get('b')).toHaveLength(1);
    });
  });

  describe('Determinism Guarantees', () => {
    it('chunkwise should produce same chunks for same input order', () => {
      const input = [1, 2, 3, 4, 5, 6, 7];

      const result1: number[][] = [];
      for (const chunk of deterministicIterables.chunkwise(input, 3)) {
        result1.push(chunk.items);
      }

      const result2: number[][] = [];
      for (const chunk of deterministicIterables.chunkwise(input, 3)) {
        result2.push(chunk.items);
      }

      expect(result1).toEqual(result2);
    });

    it('pairwise should produce same pairs for same input order', () => {
      const input = [1, 2, 3, 4];

      const result1: number[][] = [];
      for (const { previous, current } of deterministicIterables.pairwise(input)) {
        result1.push([previous ?? 0, current]);
      }

      const result2: number[][] = [];
      for (const { previous, current } of deterministicIterables.pairwise(input)) {
        result2.push([previous ?? 0, current]);
      }

      expect(result1).toEqual(result2);
    });

    it('runningDifference should produce same deltas for same input', () => {
      const input = [10, 15, 21, 30];

      const result1: (number | undefined)[] = [];
      for (const { diff } of deterministicIterables.runningDifference(input)) {
        result1.push(diff);
      }

      const result2: (number | undefined)[] = [];
      for (const { diff } of deterministicIterables.runningDifference(input)) {
        result2.push(diff);
      }

      expect(result1).toEqual(result2);
      expect(result1).toEqual([undefined, 5, 6, 9]); // First is undefined
    });

    it('runningTotal should produce same cumulative sums', () => {
      const input = [1, 2, 3, 4];

      const result1: number[] = [];
      for (const { total } of deterministicIterables.runningTotal(input)) {
        result1.push(total);
      }

      const result2: number[] = [];
      for (const { total } of deterministicIterables.runningTotal(input)) {
        result2.push(total);
      }

      expect(result1).toEqual(result2);
      expect(result1).toEqual([1, 3, 6, 10]);
    });

    it('toMinMax should produce same min/max for same input', () => {
      const input = [3, 1, 4, 1, 5, 9, 2, 6];

      const result1: [number, number][] = [];
      for (const { minValue, maxValue } of deterministicIterables.toMinMax(input)) {
        result1.push([minValue, maxValue]);
      }

      const result2: [number, number][] = [];
      for (const { minValue, maxValue } of deterministicIterables.toMinMax(input)) {
        result2.push([minValue, maxValue]);
      }

      expect(result1).toEqual(result2);
    });
  });

  describe('Error Handling', () => {
    it('LengthMismatchError should have correct properties', () => {
      const error = new deterministicIterables.LengthMismatchError(3, 2, 'zipEqual');
      expect(error.leftLength).toBe(3);
      expect(error.rightLength).toBe(2);
      expect(error.operation).toBe('zipEqual');
      expect(error.message).toContain('Length mismatch');
    });

    it('chunkwise should throw on invalid size', () => {
      expect(() => {
        const result: number[][] = [];
        for (const chunk of deterministicIterables.chunkwise([1, 2, 3], 0)) {
          result.push(chunk.items);
        }
      }).toThrow('Chunk size must be positive');
    });

    it('chunkwiseOverlap should throw on invalid step', () => {
      expect(() => {
        const result: number[][] = [];
        for (const chunk of deterministicIterables.chunkwiseOverlap([1, 2, 3], 3, 5)) {
          result.push(chunk.items);
        }
      }).toThrow('Step cannot be greater than size');
    });
  });
});
