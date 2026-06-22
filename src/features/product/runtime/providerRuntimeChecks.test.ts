import { describe, it, expect } from 'vitest';
import { getProviderStatus, getProviderRuntimeReport, getSafeRuntimeKeys, checkProviderAvailable } from './providerRuntimeChecks';

describe('providerRuntimeChecks', () => {
  describe('getProviderStatus', () => {
    it('should return free_available for mlvoca without key', () => {
      const status = getProviderStatus('mlvoca', {});
      expect(status.status).toBe('free_available');
      expect(status.isAvailable).toBe(true);
      expect(status.priority).toBe(2);
    });

    it('should return free_available for pollinations without key', () => {
      const status = getProviderStatus('pollinations', {});
      expect(status.status).toBe('free_available');
      expect(status.isAvailable).toBe(true);
      expect(status.priority).toBe(1);
    });

    it('should return not_configured for groq without key', () => {
      const status = getProviderStatus('groq', {});
      expect(status.status).toBe('not_configured');
      expect(status.isAvailable).toBe(false);
    });

    it('should return user_key_available for valid groq key', () => {
      const status = getProviderStatus('groq', { groq: 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz' });
      expect(status.status).toBe('user_key_available');
      expect(status.isAvailable).toBe(true);
    });

    it('should return user_key_invalid for invalid key', () => {
      const status = getProviderStatus('groq', { groq: 'invalid' });
      expect(status.status).toBe('user_key_invalid');
      expect(status.isAvailable).toBe(false);
    });
  });

  describe('getProviderRuntimeReport', () => {
    it('should report free providers when no keys provided', () => {
      const report = getProviderRuntimeReport({});
      expect(report.freeProviders).toContain('mlvoca');
      expect(report.freeProviders).toContain('pollinations');
      expect(report.validUserKeyProviders).toHaveLength(0);
      expect(report.suggestedProvider).toBe('pollinations'); // Highest priority free provider
    });

    it('should include valid user key providers in fallback chain', () => {
      const report = getProviderRuntimeReport({
        groq: 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz',
        huggingface: 'hf_FakeTest1234567890abcdefghijk',
      });
      expect(report.validUserKeyProviders).toContain('groq');
      expect(report.validUserKeyProviders).toContain('huggingface');
      expect(report.suggestedProvider).toBe('groq'); // Highest priority with valid key
    });

    it('should exclude invalid providers from fallback chain', () => {
      const report = getProviderRuntimeReport({
        groq: 'invalid-key',
        huggingface: 'hf_FakeTest1234567890abcdefghijk',
      });
      expect(report.invalidUserKeyProviders).toContain('groq');
      expect(report.fallbackChain).not.toContain('groq');
      expect(report.fallbackChain).toContain('huggingface');
    });

    it('should always include local-safe as final fallback', () => {
      const report = getProviderRuntimeReport({});
      expect(report.fallbackChain[report.fallbackChain.length - 1]).toBe('local-safe');
    });
  });

  describe('getSafeRuntimeKeys', () => {
    it('should return only validated keys', () => {
      const { keys, isSecure } = getSafeRuntimeKeys({
        groq: 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz',
        huggingface: 'hf_FakeTest1234567890abcdefghijk',
        gemini: 'invalid',
      });
      expect(keys.groq).toBeDefined();
      expect(keys.huggingface).toBeDefined();
      expect(keys.gemini).toBeUndefined();
      expect(isSecure).toBe(false); // Because gemini was invalid
    });

    it('should return isSecure true when all keys valid', () => {
      const { isSecure } = getSafeRuntimeKeys({
        groq: 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz',
      });
      expect(isSecure).toBe(true);
    });

    it('should return empty keys when no keys provided', () => {
      const { keys, isSecure, report } = getSafeRuntimeKeys({});
      expect(Object.keys(keys)).toHaveLength(0);
      expect(isSecure).toBe(true);
      expect(report.freeProviders).toContain('mlvoca');
      expect(report.freeProviders).toContain('pollinations');
    });
  });

  describe('checkProviderAvailable', () => {
    it('should return available true for free provider', () => {
      const result = checkProviderAvailable('mlvoca', {});
      expect(result.available).toBe(true);
      expect(result.fallback).toContain('pollinations');
    });

    it('should return available true for valid user key provider', () => {
      const result = checkProviderAvailable('groq', {
        groq: 'gsk_FakeTest1234567890abcdefghijklmnopqrstuvwxyz',
      });
      expect(result.available).toBe(true);
    });

    it('should return available false for invalid key', () => {
      const result = checkProviderAvailable('groq', { groq: 'invalid' });
      expect(result.available).toBe(false);
      expect(result.reason).toContain('user_key_invalid');
      expect(result.fallback.length).toBeGreaterThan(0);
    });

    it('should return fallback chain when provider not available', () => {
      const result = checkProviderAvailable('gemini', {});
      expect(result.available).toBe(false);
      expect(result.fallback).toContain('mlvoca');
      expect(result.fallback).toContain('pollinations');
      expect(result.fallback).toContain('local-safe');
    });
  });
});
