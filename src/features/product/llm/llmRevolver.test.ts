import { describe, expect, it } from 'vitest';
import type { LlmAdapter, LlmRevolverFailure } from './llmAdapter';
import { resolveWithLlmRevolver } from './llmRevolver';
import type { SovereignBrainResult } from '../brain/sovereignBrainContract';

function brain(file = 'README.md'): SovereignBrainResult {
  return {
    perception: { domain: 'repo automation', intent: 'README', architecture: 'React app', confidence: 0.8 },
    analysis: {
      severity: 'medium',
      issues: [{ type: 'architecture', location: 'generator', description: 'needs real files', impact: 'bad PR otherwise' }],
      rootCause: 'preview-only output',
      systemicRisk: 'irrelevant PRs',
    },
    plan: {
      strategy: 'produce real patches',
      phases: [{ phase: 1, name: 'plan', actions: ['patch'], rationale: 'requested docs' }],
      estimatedComplexity: 'medium',
    },
    execution: {
      patches: [{ file, type: 'replace', description: 'update docs', code: '# README\n' }],
      integrationNotes: 'push through PR',
      testStrategy: 'run checks',
    },
    learning: {
      patterns: ['brain gate'],
      rules: ['no patch no push'],
      architectureUpgrade: 'adapter revolver',
    },
  };
}

function adapter(id: LlmAdapter['id'], priority: number, run: LlmAdapter['run']): LlmAdapter {
  return { id, label: id, kind: 'existing', priority, enabled: true, run };
}

describe('llmRevolver', () => {
  it('rotates to the next adapter after rate limit', async () => {
    const first = adapter('mlvoca', 10, async () => {
      const err = new Error('rate limit');
      (err as Error & { status: number }).status = 429;
      throw err;
    });
    const second = adapter('pollinations', 20, async () => ({ providerId: 'pollinations', brain: brain(), raw: 'ok' }));

    const result = await resolveWithLlmRevolver([first, second], {
      mission: 'README + Update History',
      repoPaths: ['package.json'],
      selectedFilePath: 'README.md',
    });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.result.providerId).toBe('pollinations');
      expect(result.memory.nextIndex).toBe(0);
    }
  });

  it('rejects documentation requests without docs patches', async () => {
    const bad = adapter('mlvoca', 10, async () => ({ providerId: 'mlvoca', brain: brain('src/App.tsx'), raw: 'bad' }));

    const result = await resolveWithLlmRevolver([bad], {
      mission: 'README + Update History',
      repoPaths: ['package.json'],
      selectedFilePath: 'src/App.tsx',
    });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect((result as LlmRevolverFailure).failure.code).toBe('invalid_contract');
    }
  });

  it('skips external no-key adapters unless enabled', async () => {
    const noKey: LlmAdapter = {
      id: 'ovh-anonymous-code-chat',
      label: 'ovh',
      kind: 'no-key',
      priority: 10,
      enabled: true,
      async run() {
        return { providerId: 'ovh-anonymous-code-chat', brain: brain(), raw: 'ok' };
      },
    };

    const result = await resolveWithLlmRevolver([noKey], {
      mission: 'README',
      repoPaths: ['package.json'],
      selectedFilePath: 'README.md',
      allowExternalNoKey: false,
    });

    expect(result.ok).toBe(false);
    expect(result.attempts[0]?.type).toBe('provider:skipped');
  });
});
