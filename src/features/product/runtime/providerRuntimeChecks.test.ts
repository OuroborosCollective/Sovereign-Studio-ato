import { describe, expect, it } from 'vitest';
import {
  checkProviderAvailable,
  getProviderRuntimeReport,
  getProviderStatus,
  getSafeRuntimeKeys,
} from './providerRuntimeChecks';

describe('providerRuntimeChecks', () => {
  it('reports the Sovereign Backend as the only online provider', () => {
    expect(getProviderStatus('optional-user-keys', {})).toMatchObject({
      status: 'free_available',
      isAvailable: true,
      priority: 1,
      label: 'Sovereign Backend · OpenRouter Paid + FreeLLM Free',
    });
    expect(getProviderStatus('pollinations', {})).toMatchObject({
      status: 'not_configured',
      isAvailable: false,
    });
  });

  it('ignores every browser provider key and keeps the fixed fallback chain', () => {
    const report = getProviderRuntimeReport({
      groq: 'legacy-value',
      pollinations: 'legacy-value',
    });

    expect(report.freeProviders).toEqual(['optional-user-keys']);
    expect(report.validUserKeyProviders).toEqual([]);
    expect(report.invalidUserKeyProviders).toEqual([]);
    expect(report.suggestedProvider).toBe('optional-user-keys');
    expect(report.fallbackChain).toEqual(['optional-user-keys', 'local-safe']);
  });

  it('returns no browser credentials to the runtime', () => {
    const result = getSafeRuntimeKeys({
      groq: 'legacy-value',
      gemini: 'legacy-value',
    });

    expect(result.keys).toEqual({});
    expect(result.isSecure).toBe(true);
    expect(result.report.fallbackChain).toEqual(['optional-user-keys', 'local-safe']);
  });

  it('blocks direct provider ids and points back to the backend chain', () => {
    const direct = checkProviderAvailable('groq', {});
    expect(direct.available).toBe(false);
    expect(direct.fallback).toEqual(['optional-user-keys', 'local-safe']);

    const backend = checkProviderAvailable('optional-user-keys', {});
    expect(backend.available).toBe(true);
    expect(backend.fallback).toEqual(['local-safe']);
  });
});
