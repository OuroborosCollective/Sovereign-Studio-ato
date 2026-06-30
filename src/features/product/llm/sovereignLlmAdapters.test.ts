import { describe, expect, it } from 'vitest';
import { defaultSettings, starterCards } from '../constants';
import { buildSovereignLlmAdapters } from './sovereignLlmAdapters';

describe('sovereignLlmAdapters', () => {
  it('creates the hosted primary bridge first by default', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    expect(adapters[0].id).toBe('optional-user-keys');
    expect(adapters[0].kind).toBe('user-key');
    expect(adapters[0].priority).toBe(-10);
    expect(adapters[0].enabled).toBe(true);
  });

  it('keeps mlvoca as the first no-key fallback by default', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    const mlvocaAdapter = adapters.find((adapter) => adapter.id === 'mlvoca');
    expect(mlvocaAdapter).toBeDefined();
    expect(mlvocaAdapter?.kind).toBe('no-key');
    expect(mlvocaAdapter?.priority).toBe(0);
    expect(mlvocaAdapter?.enabled).toBe(true);
  });

  it('creates pollinations adapter after mlvoca by default', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    const pollinationsAdapter = adapters.find((adapter) => adapter.id === 'pollinations');
    expect(pollinationsAdapter).toBeDefined();
    expect(pollinationsAdapter?.kind).toBe('no-key');
    expect(pollinationsAdapter?.priority).toBe(1);
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
      'optional-user-keys',
      'mlvoca',
      'pollinations',
      'groq',
      'huggingface',
      'together',
      'openrouter',
      'gemini',
      'ovh-anonymous-code-chat',
      'ovh-anonymous-fixed-model',
      'hf-curated-public-space',
      'puter-js-opt-in',
      'local-safe',
    ]);
  });

  it('includes emergency keyless fallbacks even without any API keys', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    const ids = adapters.map((adapter) => adapter.id);
    expect(ids).toContain('ovh-anonymous-code-chat');
    expect(ids).toContain('ovh-anonymous-fixed-model');
    expect(ids).toContain('hf-curated-public-space');
    expect(ids).toContain('puter-js-opt-in');
  });

  it('emergency keyless adapters have correct kinds and priorities', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    const ovhCodeChat = adapters.find((a) => a.id === 'ovh-anonymous-code-chat');
    const ovhFixed = adapters.find((a) => a.id === 'ovh-anonymous-fixed-model');
    const hfPublic = adapters.find((a) => a.id === 'hf-curated-public-space');
    const puter = adapters.find((a) => a.id === 'puter-js-opt-in');

    expect(ovhCodeChat?.kind).toBe('no-key');
    expect(ovhCodeChat?.priority).toBe(7);
    expect(ovhFixed?.kind).toBe('no-key');
    expect(ovhFixed?.priority).toBe(8);
    expect(hfPublic?.kind).toBe('no-key');
    expect(hfPublic?.priority).toBe(9);
    expect(puter?.kind).toBe('opt-in');
    expect(puter?.priority).toBe(10);
  });

  it('maintains priority ordering', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
      groqApiKey: 'test-key',
    });

    const sortedAdapters = [...adapters].sort((a, b) => a.priority - b.priority);

    expect(sortedAdapters[0].id).toBe('optional-user-keys');
    expect(sortedAdapters[1].id).toBe('mlvoca');
    expect(sortedAdapters[2].id).toBe('pollinations');
    expect(sortedAdapters[3].id).toBe('groq');
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
