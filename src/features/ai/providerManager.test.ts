import { describe, it, expect, beforeEach } from 'vitest';
import { FREE_PROVIDERS, ProviderManager } from './providerManager';

describe('FREE_PROVIDERS constant', () => {
  it('should be an array of provider configurations', () => {
    expect(Array.isArray(FREE_PROVIDERS)).toBe(true);
    expect(FREE_PROVIDERS.length).toBe(6);
  });

  it('should have the correct providers in priority order', () => {
    const expectedTypes = ['mlvoca', 'pollinations', 'groq', 'huggingface', 'together', 'openrouter'];
    expect(FREE_PROVIDERS.map(p => p.type)).toEqual(expectedTypes);

    // Verify each has a unique priority that matches its index (as per current implementation)
    FREE_PROVIDERS.forEach((provider, index) => {
      expect(provider.priority).toBe(index);
    });
  });

  it('should have valid configurations for each provider', () => {
    FREE_PROVIDERS.forEach(provider => {
      expect(provider.type).toBeDefined();
      expect(provider.baseURL).toMatch(/^https?:\/\//);
      expect(provider.model).toBeDefined();
      expect(typeof provider.priority).toBe('number');
      if (provider.maxTokens) {
        expect(typeof provider.maxTokens).toBe('number');
      }
    });
  });

  it('should match the specific configuration for mlvoca', () => {
    const mlvoca = FREE_PROVIDERS.find(p => p.type === 'mlvoca');
    expect(mlvoca).toEqual({
      type: 'mlvoca',
      baseURL: 'https://mlvoca.com',
      model: 'deepseek-r1:1.5b',
      supportsStreaming: true,
      maxTokens: 2048,
      priority: 0,
    });
  });

  it('should match the specific configuration for pollinations', () => {
    const pollinations = FREE_PROVIDERS.find(p => p.type === 'pollinations');
    expect(pollinations).toEqual({
      type: 'pollinations',
      baseURL: 'https://gen.pollinations.ai',
      model: 'openai',
      supportsStreaming: true,
      maxTokens: 4096,
      priority: 1,
    });
  });

  it('should match the specific configuration for groq', () => {
    const groq = FREE_PROVIDERS.find(p => p.type === 'groq');
    expect(groq).toEqual({
      type: 'groq',
      baseURL: 'https://api.groq.com/openai/v1',
      model: 'llama-3.1-8b-instant',
      supportsStreaming: true,
      maxTokens: 8192,
      priority: 2,
    });
  });

  it('should match the specific configuration for huggingface', () => {
    const huggingface = FREE_PROVIDERS.find(p => p.type === 'huggingface');
    expect(huggingface).toEqual({
      type: 'huggingface',
      baseURL: 'https://api-inference.huggingface.co/models',
      model: 'meta-llama/Llama-3.2-1B-Instruct',
      supportsStreaming: false,
      maxTokens: 2048,
      priority: 3,
    });
  });

  it('should match the specific configuration for together', () => {
    const together = FREE_PROVIDERS.find(p => p.type === 'together');
    expect(together).toEqual({
      type: 'together',
      baseURL: 'https://api.together.xyz/v1',
      model: 'meta-llama/Llama-3.2-1B-Instruct-Turbo',
      supportsStreaming: true,
      maxTokens: 4096,
      priority: 4,
    });
  });

  it('should match the specific configuration for openrouter', () => {
    const openrouter = FREE_PROVIDERS.find(p => p.type === 'openrouter');
    expect(openrouter).toEqual({
      type: 'openrouter',
      baseURL: 'https://openrouter.ai/api/v1',
      model: 'meta-llama/llama-3.1-8b-instruct:free',
      supportsStreaming: true,
      maxTokens: 8192,
      priority: 5,
    });
  });
});

describe('ProviderManager', () => {
  let manager: ProviderManager;

  beforeEach(() => {
    manager = new ProviderManager();
  });

  it('should initialize with no configured providers', () => {
    expect(manager.getConfiguredProviders()).toEqual([]);
  });

  it('should allow setting and retrieving API keys', () => {
    manager.setApiKey('groq', 'test-key');
    expect(manager.getConfiguredProviders()).toEqual(['groq']);
    expect(manager.getConfiguredProviders()).not.toContain('huggingface');
  });

  it('should return available providers sorted by priority', () => {
    const providers = manager.getAvailableProviders();
    expect(providers.length).toBe(FREE_PROVIDERS.length);
    for (let i = 0; i < providers.length - 1; i++) {
      expect(providers[i].priority).toBeLessThan(providers[i + 1].priority);
    }
  });

  it('should reset failed providers', () => {
    // Testing the public reset method
    expect(() => manager.resetFailedProviders()).not.toThrow();
  });
});
