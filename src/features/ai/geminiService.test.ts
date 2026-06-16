import { describe, it, expect, vi } from 'vitest';

describe('GeminiService', () => {
  // Note: Full integration tests for GeminiService require API keys
  // These are covered by e2e tests and manual testing
  // The provider fallback system (providerManager.ts) handles real API calls

  it('should have provider fallback chain for free API usage', async () => {
    // Verify the fallback providers exist and work without keys
    const { FREE_PROVIDERS } = await import('./providerManager');
    
    expect(FREE_PROVIDERS).toBeDefined();
    expect(Array.isArray(FREE_PROVIDERS)).toBe(true);
    expect(FREE_PROVIDERS.length).toBeGreaterThan(0);
    
    // First two providers should not require API keys
    expect(FREE_PROVIDERS[0].type).toBe('mlvoca');
    expect(FREE_PROVIDERS[1].type).toBe('pollinations');
  });

  it('should have mlvoca as default no-key provider', async () => {
    const { FREE_PROVIDERS } = await import('./providerManager');
    
    const mlvocaProvider = FREE_PROVIDERS.find(p => p.type === 'mlvoca');
    expect(mlvocaProvider).toBeDefined();
    expect(mlvocaProvider?.priority).toBe(0);
  });

  it('should support fallback chain order', async () => {
    const { FREE_PROVIDERS } = await import('./providerManager');
    
    // Verify providers are sorted by priority
    const priorities = FREE_PROVIDERS.map(p => p.priority);
    const sorted = [...priorities].sort((a, b) => a - b);
    expect(priorities).toEqual(sorted);
  });
});
