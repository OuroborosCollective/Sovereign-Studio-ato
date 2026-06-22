import { beforeEach, describe, expect, it, vi } from 'vitest';
import { runSovereignLlmRuntime } from './sovereignLlmRuntime';

vi.mock('../llm/productLlmRevolver', () => ({
  resolveProductWithLlmRevolver: vi.fn(),
}));

import { resolveProductWithLlmRevolver } from '../llm/productLlmRevolver';

function mockBrain() {
  return {
    perception: { domain: 'test', intent: 'test', architecture: 'test', confidence: 0.9 },
    analysis: { severity: 'medium', issues: [], rootCause: 'test', systemicRisk: 'low' },
    plan: { strategy: 'test', phases: [], estimatedComplexity: 'low' },
    execution: { patches: [{ file: 'src/index.ts', type: 'replace', description: 'test patch', code: 'export const testRuntime = true;' }] },
    learning: { patterns: [], rules: [], architectureUpgrade: '' },
  };
}

describe('sovereignLlmRuntime', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls resolveProductWithLlmRevolver with memory and runtime context', async () => {
    vi.mocked(resolveProductWithLlmRevolver).mockResolvedValue({
      ok: true,
      result: {
        providerId: 'mlvoca',
        brain: mockBrain(),
        raw: '{}',
      },
      memory: { nextIndex: 0, shots: [] },
      attempts: [],
    });

    const result = await runSovereignLlmRuntime({
      mission: 'Test mission',
      repoPaths: ['src/index.ts'],
      selectedFilePath: 'src/index.ts',
      memoryContext: ['pattern: test'],
      runtimeEvents: ['event: test'],
    });

    expect(resolveProductWithLlmRevolver).toHaveBeenCalledWith(
      expect.objectContaining({
        mission: 'Test mission',
        repoPaths: ['src/index.ts'],
        selectedFilePath: 'src/index.ts',
        memoryContext: ['pattern: test'],
        runtimeEvents: ['event: test'],
        allowExternalNoKey: true,
      }),
      expect.any(Object),
    );

    expect(result.ok).toBe(true);
    expect(result.source).toBe('llm-revolver');
    expect(result.providerId).toBe('mlvoca');
  });

  it('returns local-safe failure state when all providers fail', async () => {
    vi.mocked(resolveProductWithLlmRevolver).mockResolvedValue({
      ok: false,
      failure: {
        providerId: 'mlvoca',
        code: 'network',
        message: 'Network error',
        retryable: true,
      },
      memory: { nextIndex: 0, shots: [] },
      attempts: [],
    });

    const result = await runSovereignLlmRuntime({
      mission: 'Test mission',
      repoPaths: ['src/index.ts'],
      selectedFilePath: 'src/index.ts',
      memoryContext: [],
      runtimeEvents: [],
    });

    expect(result.ok).toBe(false);
    expect(result.source).toBe('local-safe');
    expect(result.providerId).toBe('local-safe');
    expect(result.error).toBe('Network error');
  });

  it('passes user keys only when user-key routes are allowed', async () => {
    vi.mocked(resolveProductWithLlmRevolver).mockResolvedValue({
      ok: true,
      result: {
        providerId: 'groq',
        brain: mockBrain(),
        raw: '{}',
      },
      memory: { nextIndex: 0, shots: [] },
      attempts: [],
    });

    await runSovereignLlmRuntime({
      mission: 'Test mission',
      repoPaths: ['src/index.ts'],
      selectedFilePath: 'src/index.ts',
      memoryContext: [],
      runtimeEvents: [],
      allowUserKeyRoutes: true,
      userKeys: {
        groq: 'test-groq-key',
        gemini: 'test-gemini-key',
      },
    });

    expect(resolveProductWithLlmRevolver).toHaveBeenCalledWith(
      expect.objectContaining({
        groqApiKey: 'test-groq-key',
        geminiApiKey: 'test-gemini-key',
        allowExternalNoKey: true,
      }),
      expect.any(Object),
    );
  });

  it('tracks attempts from revolver events', async () => {
    vi.mocked(resolveProductWithLlmRevolver).mockImplementation(async (_input, options) => {
      options.onEvent?.({ type: 'provider:trying', providerId: 'mlvoca', message: 'Trying mlvoca', attempt: 1 });
      options.onEvent?.({ type: 'provider:success', providerId: 'mlvoca', message: 'Success', attempt: 1 });
      return {
        ok: true,
        result: {
          providerId: 'mlvoca',
          brain: mockBrain(),
          raw: '{}',
        },
        memory: { nextIndex: 1, shots: [] },
        attempts: [],
      };
    });

    const result = await runSovereignLlmRuntime({
      mission: 'Test mission',
      repoPaths: ['src/index.ts'],
      selectedFilePath: 'src/index.ts',
      memoryContext: [],
      runtimeEvents: [],
    });

    expect(result.attempts).toEqual([
      { providerId: 'mlvoca', status: 'success', message: 'Success' },
    ]);
  });
});
