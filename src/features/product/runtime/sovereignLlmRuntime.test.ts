import { describe, it, expect, vi, beforeEach } from 'vitest';
import { runSovereignLlmRuntime } from './sovereignLlmRuntime';
import { defaultSettings, starterCards } from '../../constants';

// Mock the productLlmRevolver module
vi.mock('../../llm/productLlmRevolver', () => ({
  resolveProductWithLlmRevolver: vi.fn(),
}));

import { resolveProductWithLlmRevolver } from '../../llm/productLlmRevolver';

describe('sovereignLlmRuntime', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should call resolveProductWithLlmRevolver with correct parameters', async () => {
    const mockResult = {
      ok: true,
      result: {
        providerId: 'mlvoca',
        brain: {
          perception: { domain: 'test', intent: 'test', architecture: 'test', confidence: 0.9 },
          analysis: { severity: 'medium', issues: [], rootCause: 'test', systemicRisk: 'low' },
          plan: { strategy: 'test', phases: [], estimatedComplexity: 'low' },
          execution: { patches: [] },
          learning: { patterns: [], rules: [], architectureUpgrade: '' },
        },
        raw: '{}',
      },
      memory: { nextIndex: 0, shots: [] },
      attempts: [],
    };

    (resolveProductWithLlmRevolver as any).mockResolvedValue(mockResult);

    const input = {
      mission: 'Test mission',
      repoPaths: ['src/index.ts'],
      selectedFilePath: 'src/index.ts',
      memoryContext: ['pattern: test'],
      runtimeEvents: ['event: test'],
    };

    const result = await runSovereignLlmRuntime(input);

    expect(resolveProductWithLlmRevolver).toHaveBeenCalledWith(
      expect.objectContaining({
        mission: 'Test mission',
        repoPaths: ['src/index.ts'],
        selectedFilePath: 'src/index.ts',
        memoryContext: ['pattern: test'],
        runtimeEvents: ['event: test'],
      }),
      expect.any(Object)
    );

    expect(result.ok).toBe(true);
    expect(result.source).toBe('llm-revolver');
    expect(result.providerId).toBe('mlvoca');
  });

  it('should return local-safe fallback when all providers fail', async () => {
    const mockResult = {
      ok: false,
      failure: {
        providerId: 'mlvoca',
        code: 'network' as const,
        message: 'Network error',
        retryable: true,
      },
      memory: { nextIndex: 0, shots: [] },
      attempts: [],
    };

    (resolveProductWithLlmRevolver as any).mockResolvedValue(mockResult);

    const input = {
      mission: 'Test mission',
      repoPaths: ['src/index.ts'],
      selectedFilePath: 'src/index.ts',
      memoryContext: [],
      runtimeEvents: [],
    };

    const result = await runSovereignLlmRuntime(input);

    expect(result.ok).toBe(false);
    expect(result.source).toBe('local-safe');
    expect(result.providerId).toBe('local-safe');
    expect(result.error).toBe('Network error');
  });

  it('should pass user keys to revolver when allowUserKeyRoutes is true', async () => {
    const mockResult = {
      ok: true,
      result: {
        providerId: 'groq',
        brain: {
          perception: { domain: 'test', intent: 'test', architecture: 'test', confidence: 0.9 },
          analysis: { severity: 'medium', issues: [], rootCause: 'test', systemicRisk: 'low' },
          plan: { strategy: 'test', phases: [], estimatedComplexity: 'low' },
          execution: { patches: [] },
          learning: { patterns: [], rules: [], architectureUpgrade: '' },
        },
        raw: '{}',
      },
      memory: { nextIndex: 0, shots: [] },
      attempts: [],
    };

    (resolveProductWithLlmRevolver as any).mockResolvedValue(mockResult);

    const input = {
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
    };

    await runSovereignLlmRuntime(input);

    expect(resolveProductWithLlmRevolver).toHaveBeenCalledWith(
      expect.objectContaining({
        groqApiKey: 'test-groq-key',
        geminiApiKey: 'test-gemini-key',
        allowExternalNoKey: true,
      }),
      expect.any(Object)
    );
  });

  it('should track attempts from revolver events', async () => {
    const mockResult = {
      ok: true,
      result: {
        providerId: 'pollinations',
        brain: {
          perception: { domain: 'test', intent: 'test', architecture: 'test', confidence: 0.9 },
          analysis: { severity: 'medium', issues: [], rootCause: 'test', systemicRisk: 'low' },
          plan: { strategy: 'test', phases: [], estimatedComplexity: 'low' },
          execution: { patches: [] },
          learning: { patterns: [], rules: [], architectureUpgrade: '' },
        },
        raw: '{}',
      },
      memory: { nextIndex: 0, shots: [] },
      attempts: [],
    };

    (resolveProductWithLlmRevolver as any).mockResolvedValue(mockResult);

    const input = {
      mission: 'Test mission',
      repoPaths: ['src/index.ts'],
      selectedFilePath: 'src/index.ts',
      memoryContext: [],
      runtimeEvents: [],
    };

    const result = await runSovereignLlmRuntime(input);

    expect(result.attempts).toBeDefined();
  });
});