import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RepoFile } from '../../github/types';
import type { SovereignBrainResult } from '../brain/sovereignBrainContract';
import { defaultSettings, starterCards } from '../constants';
import { buildSovereignPackageFromRepoFilesWithLlm } from './sovereignPackageFromRepoFiles';
import { runSovereignLlmRuntime } from './sovereignLlmRuntime';

vi.mock('./sovereignLlmRuntime', () => ({
  runSovereignLlmRuntime: vi.fn(),
}));

function createRepoFile(path: string): RepoFile {
  return { path, type: 'blob' };
}

function validBrain(): SovereignBrainResult {
  return {
    perception: {
      domain: 'repository automation',
      intent: 'Implement LLM package builder',
      architecture: 'React Vite repository automation runtime',
      confidence: 0.9,
    },
    analysis: {
      severity: 'medium',
      issues: [{ type: 'runtime', location: 'src/App.tsx', description: 'LLM path needs runtime wiring.', impact: 'NoCode flow would use fallback only.' }],
      rootCause: 'LLM result was not connected to package build.',
      systemicRisk: 'User words are not transformed into guarded patches.',
    },
    plan: {
      strategy: 'Wire the LLM runtime through the package builder and preserve guards.',
      phases: [{ phase: 1, name: 'Runtime wiring', actions: ['update package builder'], rationale: 'LLM output must become package input.' }],
      estimatedComplexity: 'medium',
    },
    execution: {
      patches: [{ file: 'src/App.tsx', type: 'replace', description: 'Use LLM-aware package builder.', code: 'export const appRuntime = true;\n' }],
      integrationNotes: 'Package builder uses validated LLM output.',
      testStrategy: 'Run type-check and package builder tests.',
    },
    learning: {
      patterns: ['llm-package-builder'],
      rules: ['LLM output needs patch guards.'],
      architectureUpgrade: 'LLM runtime becomes the primary package input.',
    },
  };
}

describe('sovereignPackageFromRepoFilesWithLlm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('builds package from a valid LLM brain result before local fallback', async () => {
    vi.mocked(runSovereignLlmRuntime).mockResolvedValue({
      ok: true,
      source: 'llm-revolver',
      providerId: 'mlvoca',
      brain: validBrain(),
      raw: JSON.stringify(validBrain()),
      attempts: [{ providerId: 'mlvoca', status: 'success', message: 'valid brain result' }],
    });

    const pkg = await buildSovereignPackageFromRepoFilesWithLlm({
      mission: 'Implementiere LLM Package Builder Runtime mit Tests',
      repoFiles: [createRepoFile('src/App.tsx'), createRepoFile('src/features/product/runtime/sovereignPackageFromRepoFiles.ts')],
      cards: starterCards(),
      settings: defaultSettings,
      memoryContext: ['REMOTE PATTERN: use guarded patches'],
      runtimeEvents: ['package:info:package:build-start'],
      allowUserKeyRoutes: true,
      userKeys: { groq: 'gsk_fake_key_for_test_only' },
    });

    expect(runSovereignLlmRuntime).toHaveBeenCalledWith(expect.objectContaining({
      mission: expect.stringContaining('Implementiere'),
      memoryContext: ['REMOTE PATTERN: use guarded patches'],
      allowExternalNoKey: true,
      allowUserKeyRoutes: true,
      userKeys: { groq: 'gsk_fake_key_for_test_only' },
    }));
    expect(pkg.brain.perception.intent).toContain('LLM package builder');
    expect(pkg.files.map((file) => file.path)).toContain('src/App.tsx');
    expect(pkg.files.map((file) => file.path)).toContain('generated/sovereign-product/workflow.ts');
    expect(pkg.suggestions.join('\n')).toContain('LLM source: llm-revolver via mlvoca');
  });

  it('falls back to local-safe docs package only for documentation requests when LLM runtime fails', async () => {
    vi.mocked(runSovereignLlmRuntime).mockResolvedValue({
      ok: false,
      source: 'local-safe',
      providerId: 'local-safe',
      attempts: [{ providerId: 'mlvoca', status: 'failed', message: 'network failed' }],
      error: 'All providers failed.',
    });

    const pkg = await buildSovereignPackageFromRepoFilesWithLlm({
      mission: 'Update README documentation for the launch flow',
      repoFiles: [createRepoFile('src/index.ts')],
      cards: starterCards(),
      settings: defaultSettings,
    });

    expect(pkg).toBeDefined();
    expect(pkg.files.length).toBeGreaterThan(0);
    expect(runSovereignLlmRuntime).toHaveBeenCalledTimes(1);
  });



  it('rejects local-safe fallback for env and security implementation requests', async () => {
    vi.mocked(runSovereignLlmRuntime).mockResolvedValue({
      ok: false,
      source: 'local-safe',
      providerId: 'local-safe',
      attempts: [{ providerId: 'mlvoca', status: 'failed', message: 'network failed' }],
      error: 'All providers failed.',
    });

    await expect(buildSovereignPackageFromRepoFilesWithLlm({
      mission: 'Behebe Env Datei und Sicherheitsrisiken mit echten Code-Änderungen',
      repoFiles: [createRepoFile('src/index.ts'), createRepoFile('.github/workflows/ci.yml'), createRepoFile('.env.example')],
      cards: starterCards(),
      settings: defaultSettings,
    })).rejects.toThrow('VALIDATION_FAILED_LLM_REQUIRED');
  });

  it('rejects placeholder missions before firing LLM runtime', async () => {
    await expect(
      buildSovereignPackageFromRepoFilesWithLlm({
        mission: 'placeholder mission',
        repoFiles: [createRepoFile('src/index.ts')],
      }),
    ).rejects.toThrow('Concrete user mission is required');

    expect(runSovereignLlmRuntime).not.toHaveBeenCalled();
  });
});
