import { describe, it, expect } from 'vitest';
import { validateProviderKey, validateUserApiKeys, getValidatedKeys, shouldUseProvider } from './apiKeyValidation';

describe('apiKeyValidation', () => {
  describe('validateProviderKey', () => {
    it('should validate empty key as empty (not invalid)', () => {
      const result = validateProviderKey('groq', '');
      expect(result.code).toBe('empty');
      expect(result.isValid).toBe(false);
      expect(result.message).toContain('No key provided');
    });

    it('should validate undefined key as empty', () => {
      const result = validateProviderKey('groq', undefined);
      expect(result.code).toBe('empty');
      expect(result.isValid).toBe(false);
    });

    it('should validate correct Groq key format', () => {
      // Fake key matching Groq format (gsk_ + alphanumeric)
      const result = validateProviderKey('groq', 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz');
      expect(result.code).toBe('valid');
      expect(result.isValid).toBe(true);
    });

    it('should reject Groq key with wrong prefix', () => {
      const result = validateProviderKey('groq', 'hf_wrongprefix123456789012345678901');
      expect(result.code).toBe('invalid_prefix');
      expect(result.isValid).toBe(false);
      expect(result.message).toContain('gsk_');
    });

    it('should validate correct HuggingFace key format', () => {
      // Fake key matching HuggingFace format (hf_ + alphanumeric)
      const result = validateProviderKey('huggingface', 'hf_FakeTest1234567890abcdefghijk');
      expect(result.code).toBe('valid');
      expect(result.isValid).toBe(true);
    });

    it('should reject HuggingFace key with wrong prefix', () => {
      const result = validateProviderKey('huggingface', 'gsk_wrongprefix');
      expect(result.code).toBe('invalid_prefix');
      expect(result.isValid).toBe(false);
    });

    it('should validate correct Together key format', () => {
      // Fake key matching Together format
      const result = validateProviderKey('together', 'together_FakeTest1234567890abcdefghijklmnop');
      expect(result.code).toBe('valid');
      expect(result.isValid).toBe(true);
    });

    it('should validate correct OpenRouter key format', () => {
      // Fake key matching OpenRouter format
      const result = validateProviderKey('openrouter', 'sk-or-v1-FakeTest1234567890abcdefghijklmnopqrstuvwxyz');
      expect(result.code).toBe('valid');
      expect(result.isValid).toBe(true);
    });

    it('should validate correct Gemini key format', () => {
      // Fake key matching Gemini format (AIza + alphanumeric)
      const result = validateProviderKey('gemini', 'AIzaFakeTest1234567890abcdefghijklmnopqrstuv');
      expect(result.code).toBe('valid');
      expect(result.isValid).toBe(true);
    });

    it('should reject Pollinations key with wrong prefix', () => {
      const result = validateProviderKey('pollinations', 'hf_wrongprefix');
      expect(result.code).toBe('invalid_prefix');
      expect(result.isValid).toBe(false);
    });
  });

  describe('validateUserApiKeys', () => {
    it('should validate empty keys report', () => {
      const report = validateUserApiKeys({});
      expect(report.allValid).toBe(true);
      expect(report.validCount).toBe(0);
      expect(report.invalidCount).toBe(0);
      expect(report.validProviders).toEqual([]);
    });

    it('should validate mixed valid and invalid keys', () => {
      const report = validateUserApiKeys({
        groq: 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz',
        huggingface: 'hf_FakeTest1234567890abcdefghijk',
        gemini: 'wrong-key',
      });
      expect(report.allValid).toBe(false);
      expect(report.validCount).toBe(2);
      expect(report.invalidCount).toBe(1);
      expect(report.validProviders).toContain('groq');
      expect(report.validProviders).toContain('huggingface');
      expect(report.invalidProviders).toContain('gemini');
    });

    it('should handle all empty keys', () => {
      const report = validateUserApiKeys({
        groq: '',
        huggingface: undefined,
        gemini: '   ',
      });
      expect(report.allValid).toBe(true);
      expect(report.validCount).toBe(0);
      expect(report.invalidCount).toBe(0);
    });
  });

  describe('getValidatedKeys', () => {
    it('should return only valid keys', () => {
      const keys = {
        groq: 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz',
        huggingface: 'hf_FakeTest1234567890abcdefghijk',
        gemini: 'invalid-key-too-short',
      };
      const validated = getValidatedKeys(keys);
      expect(validated.groq).toBe(keys.groq);
      expect(validated.huggingface).toBe(keys.huggingface);
      expect(validated.gemini).toBeUndefined();
    });

    it('should return empty object for all invalid keys', () => {
      const keys = {
        groq: 'invalid',
        gemini: 'wrong',
      };
      const validated = getValidatedKeys(keys);
      expect(Object.keys(validated)).toHaveLength(0);
    });
  });

  describe('shouldUseProvider', () => {
    it('should return true for valid key', () => {
      expect(shouldUseProvider('groq', { groq: 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz' })).toBe(true);
    });

    it('should return false for empty key', () => {
      expect(shouldUseProvider('groq', { groq: '' })).toBe(false);
    });

    it('should return false for invalid key', () => {
      expect(shouldUseProvider('groq', { groq: 'invalid' })).toBe(false);
    });

    it('should return false for undefined key', () => {
      expect(shouldUseProvider('groq', {})).toBe(false);
    });
  });
});
