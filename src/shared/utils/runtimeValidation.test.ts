import { describe, it, expect, vi } from 'vitest';
import {
  validateRequired,
  validateNonEmpty,
  validateUrl,
  validateGitHubUrl,
  validateApiKey,
  validateNumberBounds,
  validateArrayNotEmpty,
  combineValidationResults,
  validateAppState,
  runtimeCheck,
  safeJsonParse,
  safeArrayAccess,
  safeGet,
} from './runtimeValidation';

describe('Runtime Validation System', () => {
  describe('validateRequired', () => {
    it('should pass for non-null values', () => {
      const result = validateRequired('hello', 'testField');
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('should fail for null', () => {
      const result = validateRequired(null, 'testField');
      expect(result.valid).toBe(false);
      expect(result.errors[0]).toContain('null or undefined');
    });

    it('should fail for undefined', () => {
      const result = validateRequired(undefined, 'testField');
      expect(result.valid).toBe(false);
      expect(result.errors[0]).toContain('null or undefined');
    });
  });

  describe('validateNonEmpty', () => {
    it('should pass for non-empty string', () => {
      const result = validateNonEmpty('hello', 'testField');
      expect(result.valid).toBe(true);
    });

    it('should fail for empty string', () => {
      const result = validateNonEmpty('', 'testField');
      expect(result.valid).toBe(false);
    });

    it('should fail for whitespace-only string', () => {
      const result = validateNonEmpty('   ', 'testField');
      expect(result.valid).toBe(false);
    });
  });

  describe('validateUrl', () => {
    it('should pass for valid URL', () => {
      const result = validateUrl('https://github.com/user/repo', 'url');
      expect(result.valid).toBe(true);
    });

    it('should fail for invalid URL', () => {
      const result = validateUrl('not-a-url', 'url');
      expect(result.valid).toBe(false);
    });
  });

  describe('validateGitHubUrl', () => {
    it('should pass for valid GitHub URL', () => {
      const result = validateGitHubUrl('https://github.com/OuroborosCollective/Sovereign-Studio-ato');
      expect(result.valid).toBe(true);
    });

    it('should fail for invalid GitHub URL', () => {
      const result = validateGitHubUrl('https://gitlab.com/user/repo');
      expect(result.valid).toBe(false);
    });

    it('should pass for GitHub URL without https', () => {
      const result = validateGitHubUrl('github.com/user/repo');
      expect(result.valid).toBe(true);
    });
  });

  describe('validateApiKey', () => {
    it('should pass for empty key (no key provided)', () => {
      const result = validateApiKey('', 'apiKey');
      expect(result.valid).toBe(true);
    });

    it('should pass for valid GitHub PAT', () => {
      const result = validateApiKey('ghp_1234567890abcdefghijklmnopqrstuvwxyz', 'accessKey');
      expect(result.valid).toBe(true);
    });

    it('should warn for short key', () => {
      const result = validateApiKey('ghp_short', 'accessKey');
      expect(result.warnings.length).toBeGreaterThan(0);
    });
  });

  describe('validateNumberBounds', () => {
    it('should pass for value within bounds', () => {
      const result = validateNumberBounds(5, 0, 10, 'test');
      expect(result.valid).toBe(true);
    });

    it('should fail for value below minimum', () => {
      const result = validateNumberBounds(-1, 0, 10, 'test');
      expect(result.valid).toBe(false);
    });

    it('should fail for value above maximum', () => {
      const result = validateNumberBounds(11, 0, 10, 'test');
      expect(result.valid).toBe(false);
    });
  });

  describe('validateArrayNotEmpty', () => {
    it('should pass for non-empty array', () => {
      const result = validateArrayNotEmpty([1, 2, 3], 'testArray');
      expect(result.valid).toBe(true);
    });

    it('should fail for empty array', () => {
      const result = validateArrayNotEmpty([], 'testArray');
      expect(result.valid).toBe(false);
    });

    it('should fail for undefined', () => {
      const result = validateArrayNotEmpty(undefined, 'testArray');
      expect(result.valid).toBe(false);
    });
  });

  describe('combineValidationResults', () => {
    it('should combine multiple results', () => {
      const result1 = validateRequired('hello', 'field1');
      const result2 = validateNonEmpty('', 'field2');
      const combined = combineValidationResults(result1, result2);
      
      expect(combined.valid).toBe(false);
      expect(combined.errors).toHaveLength(1);
    });
  });

  describe('validateAppState', () => {
    it('should pass for valid state', () => {
      const state = {
        repoUrl: 'https://github.com/user/repo',
        cards: [{ id: '1', title: 'Test' }],
        settings: {
          repoMode: 'monorepo',
          packageManager: 'npm',
        },
      };
      const result = validateAppState(state);
      expect(result.valid).toBe(true);
    });

    it('should fail for invalid repoMode', () => {
      const state = {
        settings: {
          repoMode: 'invalid',
        },
      };
      const result = validateAppState(state);
      expect(result.valid).toBe(false);
    });

    it('should fail for invalid packageManager', () => {
      const state = {
        settings: {
          packageManager: 'invalid',
        },
      };
      const result = validateAppState(state);
      expect(result.valid).toBe(false);
    });
  });

  describe('runtimeCheck', () => {
    it('should not throw for true condition', () => {
      expect(() => runtimeCheck(true, 'test')).not.toThrow();
    });

    it('should throw for false condition', () => {
      expect(() => runtimeCheck(false, 'test failed')).toThrow('RUNTIME_CHECK_FAILED');
    });
  });

  describe('safeJsonParse', () => {
    it('should parse valid JSON', () => {
      const result = safeJsonParse('{"key": "value"}', {});
      expect(result).toEqual({ key: 'value' });
    });

    it('should return fallback for invalid JSON', () => {
      const fallback = { default: true };
      const result = safeJsonParse('invalid json', fallback);
      expect(result).toEqual(fallback);
    });
  });

  describe('safeArrayAccess', () => {
    const arr = [1, 2, 3];

    it('should return element at valid index', () => {
      expect(safeArrayAccess(arr, 1, 0)).toBe(2);
    });

    it('should return fallback for out of bounds index', () => {
      expect(safeArrayAccess(arr, 10, 0)).toBe(0);
    });

    it('should return fallback for negative index', () => {
      expect(safeArrayAccess(arr, -1, 0)).toBe(0);
    });
  });

  describe('safeGet', () => {
    const obj = { key1: 'value1', key2: 'value2' };

    it('should return value for existing key', () => {
      expect(safeGet(obj, 'key1', 'default')).toBe('value1');
    });

    it('should return fallback for missing key', () => {
      expect(safeGet(obj, 'missing', 'default')).toBe('default');
    });

    it('should return fallback for null object', () => {
      expect(safeGet(null as any, 'key', 'default')).toBe('default');
    });
  });
});