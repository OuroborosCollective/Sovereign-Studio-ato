import { describe, expect, it } from 'vitest';
import { checkProviderAvailable, getProviderRuntimeReport, getProviderStatus, getSafeRuntimeKeys } from './providerRuntimeChecks';

describe('providerRuntimeChecks', () => {
  describe('getProviderStatus', () => {
    it('returns free_available for mlvoca without key', () => {
      const status = getProviderStatus('mlvoca', {});
      expect(status.status).toBe('free_available');
      expect(status.isAvailable).toBe(true);
      expect(status.priority).toBe(1);
    });

    it('returns free_available for pollinations without key', () => {
      const status = getProviderStatus('pollinations', {});
      expect(status.status).toBe('free_available');
      expect(status.isAvailable).toBe(true);
      expect(status.priority).toBe(2);
    });

    it('returns not_configured for groq without key', () => {
      const status = getProviderStatus('groq', {});
      expect(status.status).toBe('not_configured');
      expect(status.isAvailable).toBe(false);
    });

    it('returns user_key_available for valid groq key', () => {
      const status = getProviderStatus('groq', { groq: 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz' });
      expect(status.status).toBe('user_key_available');
      expect(status.isAvailable).toBe(true);
    });

    it('returns user_key_invalid for invalid key', () => {
      const status = getProviderStatus('groq', { groq: 'invalid' });
      expect(status.status).toBe('user_key_invalid');
      expect(status.isAvailable).toBe(false);
    });
  });

  describe('getProviderRuntimeReport', () => {
    it('keeps free no-key providers first when no keys are provided', () => {
      const report = getProviderRuntimeReport({});
      expect(report.freeProviders).toEqual(['mlvoca', 'pollinations']);
      expect(report.validUserKeyProviders).toHaveLength(0);
      expect(report.suggestedProvider).toBe('mlvoca');
      expect(report.fallbackChain).toEqual(['mlvoca', 'pollinations', 'local-safe']);
    });

    it('keeps valid user-key providers after free routes', () => {
      const report = getProviderRuntimeReport({
        groq: 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz',
        huggingface: 'hf_FakeTest1234567890abcdefghijk',
      });

      expect(report.validUserKeyProviders).toEqual(['groq', 'huggingface']);
      expect(report.fallbackChain.slice(0, 4)).toEqual(['mlvoca', 'pollinations', 'groq', 'huggingface']);
      expect(report.suggestedProvider).toBe('mlvoca');
    });

    it('excludes invalid providers from fallback chain', () => {
      const report = getProviderRuntimeReport({
        groq: 'invalid-key',
        huggingface: 'hf_FakeTest1234567890abcdefghijk',
      });

      expect(report.invalidUserKeyProviders).toContain('groq');
      expect(report.fallbackChain).not.toContain('groq');
      expect(report.fallbackChain).toContain('huggingface');
    });

    it('always includes local-safe as final fallback', () => {
      const report = getProviderRuntimeReport({});
      expect(report.fallbackChain[report.fallbackChain.length - 1]).toBe('local-safe');
    });
  });

  describe('getSafeRuntimeKeys', () => {
    it('returns only validated keys', () => {
      const { keys, isSecure } = getSafeRuntimeKeys({
        groq: 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz',
        huggingface: 'hf_FakeTest1234567890abcdefghijk',
        gemini: 'invalid',
      });

      expect(keys.groq).toBeDefined();
      expect(keys.huggingface).toBeDefined();
      expect(keys.gemini).toBeUndefined();
      expect(isSecure).toBe(false);
    });

    it('returns isSecure true when all keys valid', () => {
      const { isSecure } = getSafeRuntimeKeys({
        groq: 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz',
      });
      expect(isSecure).toBe(true);
    });

    it('returns empty keys when no keys provided', () => {
      const { keys, isSecure, report } = getSafeRuntimeKeys({});
      expect(Object.keys(keys)).toHaveLength(0);
      expect(isSecure).toBe(true);
      expect(report.freeProviders).toEqual(['mlvoca', 'pollinations']);
    });
  });

  describe('checkProviderAvailable', () => {
    it('returns available true for free provider', () => {
      const result = checkProviderAvailable('mlvoca', {});
      expect(result.available).toBe(true);
      expect(result.fallback).toContain('pollinations');
    });

    it('returns available true for valid user key provider', () => {
      const result = checkProviderAvailable('groq', {
        groq: 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz',
      });
      expect(result.available).toBe(true);
    });

    it('returns available false for invalid key', () => {
      const result = checkProviderAvailable('groq', { groq: 'invalid' });
      expect(result.available).toBe(false);
      expect(result.reason).toContain('user key invalid');
      expect(result.fallback.length).toBeGreaterThan(0);
    });

    it('returns fallback chain when provider is not available', () => {
      const result = checkProviderAvailable('gemini', {});
      expect(result.available).toBe(false);
      expect(result.fallback).toContain('mlvoca');
      expect(result.fallback).toContain('pollinations');
      expect(result.fallback).toContain('local-safe');
    });
  });
});
