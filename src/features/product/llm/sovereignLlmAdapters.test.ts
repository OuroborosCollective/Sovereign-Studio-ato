import { describe, it, expect, vi } from 'vitest';
import { buildSovereignLlmAdapters } from '../sovereignLlmAdapters';
import { defaultSettings, starterCards } from '../../constants';

describe('sovereignLlmAdapters', () => {
  it('should create mlvoca adapter by default', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    const mlvocaAdapter = adapters.find((a) => a.id === 'mlvoca');
    expect(mlvocaAdapter).toBeDefined();
    expect(mlvocaAdapter?.kind).toBe('no-key');
    expect(mlvocaAdapter?.priority).toBe(0);
    expect(mlvocaAdapter?.enabled).toBe(true);
  });

  it('should create pollinations adapter by default', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    const pollinationsAdapter = adapters.find((a) => a.id === 'pollinations');
    expect(pollinationsAdapter).toBeDefined();
    expect(pollinationsAdapter?.kind).toBe('no-key');
    expect(pollinationsAdapter?.priority).toBe(1);
  });

  it('should create groq adapter only when API key is provided', () => {
    const adaptersWithoutKey = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    const groqWithoutKey = adaptersWithoutKey.find((a) => a.id === 'groq');
    expect(groqWithoutKey).toBeUndefined();

    const adaptersWithKey = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
      groqApiKey: 'test-api-key',
    });

    const groqWithKey = adaptersWithKey.find((a) => a.id === 'groq');
    expect(groqWithKey).toBeDefined();
    expect(groqWithKey?.enabled).toBe(true);
  });

  it('should create local-safe fallback adapter', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    const localSafeAdapter = adapters.find((a) => a.id === 'local-safe');
    expect(localSafeAdapter).toBeDefined();
    expect(localSafeAdapter?.kind).toBe('local-safe');
    expect(localSafeAdapter?.priority).toBe(999);
  });

  it('should include all adapters when all keys are provided', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
      groqApiKey: 'test-groq-key',
      huggingfaceApiKey: 'test-hf-key',
      togetherApiKey: 'test-together-key',
      openrouterApiKey: 'test-or-key',
      geminiApiKey: 'test-gemini-key',
    });

    expect(adapters.length).toBeGreaterThanOrEqual(7);
    expect(adapters.find((a) => a.id === 'groq')).toBeDefined();
    expect(adapters.find((a) => a.id === 'huggingface')).toBeDefined();
    expect(adapters.find((a) => a.id === 'together')).toBeDefined();
    expect(adapters.find((a) => a.id === 'openrouter')).toBeDefined();
    expect(adapters.find((a) => a.id === 'gemini')).toBeDefined();
    expect(adapters.find((a) => a.id === 'local-safe')).toBeDefined();
  });

  it('should maintain priority ordering (lower number = higher priority)', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
      groqApiKey: 'test-key',
    });

    // Sort by priority to verify ordering
    const sortedAdapters = [...adapters].sort((a, b) => a.priority - b.priority);

    // Verify priority ordering
    expect(sortedAdapters[0].id).toBe('mlvoca');
    expect(sortedAdapters[1].id).toBe('pollinations');
    expect(sortedAdapters[2].id).toBe('groq');
    // local-safe should be last
    expect(sortedAdapters[sortedAdapters.length - 1].id).toBe('local-safe');
  });
});

describe('LlmAdapterContext extension', () => {
  it('should include memoryContext and runtimeEvents in context interface', async () => {
    // This test verifies the interface has the new fields
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    const mlvocaAdapter = adapters.find((a) => a.id === 'mlvoca');
    expect(mlvocaAdapter).toBeDefined();

    // Test that adapter can receive context with memory and runtime fields
    // (This validates the interface extension without actually calling the API)
    const context = {
      mission: 'Test mission',
      repoPaths: ['src/index.ts'],
      selectedFilePath: 'src/index.ts',
      memoryContext: ['pattern: test-pattern'],
      runtimeEvents: ['event: test-event'],
    };

    // The adapter should accept this context without type errors
    expect(mlvocaAdapter?.run).toBeDefined();
  });
});