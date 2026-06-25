import { describe, expect, it } from 'vitest';
import { defaultSettings, starterCards } from '../constants';
import { buildSovereignLlmAdapters } from './sovereignLlmAdapters';

describe('sovereignLlmAdapters', () => {
  it('creates mlvoca adapter first by default', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    expect(adapters[0].id).toBe('mlvoca');
    expect(adapters[0].kind).toBe('no-key');
    expect(adapters[0].priority).toBe(0);
    expect(adapters[0].enabled).toBe(true);
  });

  it('creates pollinations adapter second by default', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    expect(adapters[1].id).toBe('pollinations');
    expect(adapters[1].kind).toBe('no-key');
    expect(adapters[1].priority).toBe(1);
  });

  it('creates groq adapter only when API key is provided', () => {
    const adaptersWithoutKey = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    expect(adaptersWithoutKey.find((adapter) => adapter.id === 'groq')).toBeUndefined();

    const adaptersWithKey = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
      groqApiKey: 'test-api-key',
    });

    const groqWithKey = adaptersWithKey.find((adapter) => adapter.id === 'groq');
    expect(groqWithKey).toBeDefined();
    expect(groqWithKey?.enabled).toBe(true);
  });

  it('creates local-safe as the final fallback adapter', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    const localSafeAdapter = adapters[adapters.length - 1];
    expect(localSafeAdapter.id).toBe('local-safe');
    expect(localSafeAdapter.kind).toBe('local-safe');
    expect(localSafeAdapter.priority).toBe(999);
  });

  it('includes all adapters when all keys are provided', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
      groqApiKey: 'test-groq-key',
      huggingfaceApiKey: 'test-hf-key',
      togetherApiKey: 'test-together-key',
      openrouterApiKey: 'test-or-key',
      geminiApiKey: 'test-gemini-key',
    });

    expect(adapters.map((adapter) => adapter.id)).toEqual([
      'mlvoca',
      'pollinations',
      'groq',
      'huggingface',
      'together',
      'openrouter',
      'gemini',
      'local-safe',
    ]);
  });

  it('maintains priority ordering', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
      groqApiKey: 'test-key',
    });

    const sortedAdapters = [...adapters].sort((a, b) => a.priority - b.priority);

    expect(sortedAdapters[0].id).toBe('mlvoca');
    expect(sortedAdapters[1].id).toBe('pollinations');
    expect(sortedAdapters[2].id).toBe('groq');
    expect(sortedAdapters[sortedAdapters.length - 1].id).toBe('local-safe');
  });
});

describe('LlmAdapterContext extension', () => {
  it('accepts memoryContext and runtimeEvents in adapter context', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    const mlvocaAdapter = adapters.find((adapter) => adapter.id === 'mlvoca');
    expect(mlvocaAdapter).toBeDefined();

    const context = {
      mission: 'Test mission',
      repoPaths: ['src/index.ts'],
      selectedFilePath: 'src/index.ts',
      memoryContext: ['pattern: test-pattern'],
      runtimeEvents: ['event: test-event'],
    };

    expect(context.memoryContext).toEqual(['pattern: test-pattern']);
    expect(context.runtimeEvents).toEqual(['event: test-event']);
    expect(mlvocaAdapter?.run).toBeDefined();
  });
});
