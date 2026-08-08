import { describe, it, expect } from 'vitest';
import {
  mergeValue,
  mergeConfigs,
  DELETE_KEY,
  isDeleteKey,
  validateMergeResult,
  type MergeResult,
} from './configMerge';
import type { ConfigSourcePriority } from './configSources';

describe('configMerge', () => {
  describe('mergeValue', () => {
    it('should replace primitive values', () => {
      const { value, changed } = mergeValue(1, 2, 'key');
      expect(value).toBe(2);
      expect(changed).toBe(true);
    });

    it('should handle null override', () => {
      const { value, changed } = mergeValue({ key: 'a' }, null, 'key');
      expect(value).toBeNull();
      expect(changed).toBe(true);
    });

    it('should handle DELETE_KEY to remove values', () => {
      const { value, changed } = mergeValue({ key: 'a' }, DELETE_KEY, 'key');
      expect(value).toBeUndefined();
      expect(changed).toBe(true);
    });

    it('should deep merge objects', () => {
      const base = { a: 1, b: { c: 2 } };
      const override = { b: { d: 3 }, e: 4 };
      const { value } = mergeValue(base, override, 'root');
      expect(value).toEqual({ a: 1, b: { c: 2, d: 3 }, e: 4 });
    });

    it('should replace arrays (not concatenate)', () => {
      const { value } = mergeValue([1, 2], [3, 4], 'key');
      expect(value).toEqual([3, 4]);
    });

    it('should replace object with array', () => {
      const { value } = mergeValue({ key: 'a' }, [1, 2], 'key');
      expect(value).toEqual([1, 2]);
    });

    it('should handle missing base value', () => {
      const { value, changed } = mergeValue(undefined as unknown as object, { a: 1 }, 'key');
      expect(value).toEqual({ a: 1 });
      expect(changed).toBe(true);
    });

    it('should detect unchanged primitives', () => {
      const { value, changed } = mergeValue('same', 'same', 'key');
      expect(value).toBe('same');
      expect(changed).toBe(false);
    });
  });

  describe('isDeleteKey', () => {
    it('should return true for DELETE_KEY', () => {
      expect(isDeleteKey(DELETE_KEY)).toBe(true);
    });

    it('should return false for other values', () => {
      expect(isDeleteKey(null)).toBe(false);
      expect(isDeleteKey(undefined)).toBe(false);
      expect(isDeleteKey('delete')).toBe(false);
      expect(isDeleteKey({})).toBe(false);
    });
  });

  describe('mergeConfigs', () => {
    it('should merge configs by priority', () => {
      const configs = [
        {
          priority: 'compiled' as ConfigSourcePriority,
          content: { a: 1, b: 2 },
          sourceId: 'compiled',
          contentHash: 'hash1',
        },
        {
          priority: 'overlay' as ConfigSourcePriority,
          content: { b: 3, c: 4 },
          sourceId: 'overlay',
          contentHash: 'hash2',
        },
      ];

      const result = mergeConfigs(configs);

      // Overlay has highest precedence, so it overrides compiled values
      expect(result.value).toEqual({ a: 1, b: 3, c: 4 });
      expect(result.sources).toHaveLength(2);
    });

    it('should handle single config', () => {
      const configs = [
        {
          priority: 'compiled' as ConfigSourcePriority,
          content: { a: 1 },
          sourceId: 'compiled',
          contentHash: 'hash1',
        },
      ];

      const result = mergeConfigs(configs);
      expect(result.value).toEqual({ a: 1 });
      expect(result.sources).toHaveLength(1);
    });

    it('should handle empty configs', () => {
      const result = mergeConfigs([]);
      expect(result.value).toEqual({});
      expect(result.sources).toHaveLength(0);
    });

    it('should apply delete keys', () => {
      const configs = [
        {
          priority: 'compiled' as ConfigSourcePriority,
          content: { a: 1, b: 2 },
          sourceId: 'compiled',
          contentHash: 'hash1',
        },
        {
          priority: 'overlay' as ConfigSourcePriority,
          content: { b: DELETE_KEY } as Record<string, unknown>,
          sourceId: 'overlay',
          contentHash: 'hash2',
        },
      ];

      const result = mergeConfigs(configs);
      expect(result.value).toEqual({ a: 1 });
    });

    it('should track source attribution', () => {
      const configs = [
        {
          priority: 'compiled' as ConfigSourcePriority,
          content: { a: 1 },
          sourceId: 'compiled',
          contentHash: 'hash1',
        },
        {
          priority: 'overlay' as ConfigSourcePriority,
          content: { b: 2 },
          sourceId: 'overlay',
          contentHash: 'hash2',
        },
      ];

      const result = mergeConfigs(configs);
      expect(result.sources[0]).toEqual({ resolvedFrom: 'compiled', contentHash: 'hash1' });
      expect(result.sources[1]).toEqual({ resolvedFrom: 'overlay', contentHash: 'hash2' });
    });
  });

  describe('validateMergeResult', () => {
    it('should pass for valid result', () => {
      const result: MergeResult<object> = {
        value: { a: 1 },
        sources: [{ resolvedFrom: 'test', contentHash: 'hash' }],
      };
      const errors = validateMergeResult(result);
      expect(errors).toHaveLength(0);
    });

    it('should fail for invalid result structure', () => {
      const errors = validateMergeResult(null);
      expect(errors).toContain('Merge result must be an object');
    });

    it('should fail for missing value', () => {
      const result = { value: null, sources: [] } as unknown as MergeResult<object>;
      const errors = validateMergeResult(result);
      expect(errors).toContain('Merge result value must be an object');
    });

    it('should fail for missing sources', () => {
      const result = { value: { a: 1 }, sources: null } as unknown as MergeResult<object>;
      const errors = validateMergeResult(result);
      expect(errors).toContain('Merge result sources must be an array');
    });

    it('should validate expected keys', () => {
      const result: MergeResult<object> = {
        value: { a: 1 },
        sources: [],
      };
      const errors = validateMergeResult(result, ['a', 'b']);
      expect(errors).toContain('Expected key "b" not found in merged config');
    });
  });
});
