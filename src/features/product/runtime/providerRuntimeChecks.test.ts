import { describe, expect, it } from 'vitest';
import {
  checkProviderAvailable,
  classifyBackendRoute,
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
      label: 'Sovereign Backend · route-aware OpenRouter / FreeLLM',
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
    expect(report.resolvedTransportClass).toBe('UNRESOLVED');
    expect(report.pricingDisplay).toBe('Backend-Routenauflösung ausstehend');
  });

  it('keeps FreeLLM, OpenRouter-free and OpenRouter-paid pricing rules distinct', () => {
    expect(classifyBackendRoute({
      provider: 'freellm',
      billingCategory: 'free',
      fundingMode: 'provider_free_quota',
    })).toEqual({
      resolvedTransportClass: 'FREELLM_FREE',
      billingCategory: 'free',
      fundingMode: 'provider_free_quota',
      pricingDisplay: 'Free · Provider-Quota',
    });
    expect(classifyBackendRoute({
      provider: 'openrouter',
      billingCategory: 'free',
      fundingMode: 'provider_free_quota',
    })?.resolvedTransportClass).toBe('OPENROUTER_FREE');
    expect(classifyBackendRoute({
      provider: 'open-router',
      billingCategory: 'premium',
      fundingMode: 'provider_priced',
    })).toMatchObject({
      resolvedTransportClass: 'OPENROUTER_PAID',
      billingCategory: 'premium',
      pricingDisplay: 'Paid · OpenRouter · Premium',
    });
    expect(classifyBackendRoute({
      provider: 'freellm',
      billingCategory: 'standard',
      fundingMode: 'provider_priced',
    })).toBeNull();
  });

  it('projects an exact backend route classification into the runtime report', () => {
    const report = getProviderRuntimeReport({}, {
      provider: 'openrouter',
      billingCategory: 'standard',
      fundingMode: 'provider_priced',
    });
    expect(report.resolvedTransportClass).toBe('OPENROUTER_PAID');
    expect(report.billingCategory).toBe('standard');
    expect(report.fundingMode).toBe('provider_priced');
    expect(report.pricingDisplay).toBe('Paid · OpenRouter · Standard');
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
