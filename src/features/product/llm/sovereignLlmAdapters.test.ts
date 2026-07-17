import { describe, expect, it } from 'vitest';
import { defaultSettings, starterCards } from '../constants';
import { buildSovereignLlmAdapters } from './sovereignLlmAdapters';

describe('sovereignLlmAdapters', () => {
  it('exposes exactly one online backend route plus local analysis fallback', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });

    expect(adapters.map((adapter) => adapter.id)).toEqual([
      'optional-user-keys',
      'local-safe',
    ]);
    expect(adapters[0]).toMatchObject({
      label: 'Sovereign Backend · private LiteLLM',
      kind: 'existing',
      priority: -10,
      enabled: true,
    });
    expect(adapters[1]).toMatchObject({
      id: 'local-safe',
      kind: 'local-safe',
      priority: 999,
    });
  });

  it('never rebuilds direct browser providers even when legacy keys are supplied', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
      pollinationsApiKey: 'legacy-pollinations',
      groqApiKey: 'legacy-groq',
      huggingfaceApiKey: 'legacy-hf',
      togetherApiKey: 'legacy-together',
      openrouterApiKey: 'legacy-openrouter',
      geminiApiKey: 'legacy-gemini',
    });

    expect(adapters.map((adapter) => adapter.id)).toEqual([
      'optional-user-keys',
      'local-safe',
    ]);
  });

  it('keeps runtime context support on the backend adapter', () => {
    const adapters = buildSovereignLlmAdapters({
      cards: starterCards(),
      settings: defaultSettings,
    });
    const backendAdapter = adapters[0];
    const context = {
      mission: 'Test mission',
      repoPaths: ['src/index.ts'],
      selectedFilePath: 'src/index.ts',
      memoryContext: ['pattern: test-pattern'],
      runtimeEvents: ['event: test-event'],
    };

    expect(context.memoryContext).toEqual(['pattern: test-pattern']);
    expect(context.runtimeEvents).toEqual(['event: test-event']);
    expect(backendAdapter.run).toBeDefined();
  });
});
