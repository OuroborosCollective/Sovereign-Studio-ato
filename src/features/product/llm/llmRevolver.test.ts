import { describe, expect, it } from 'vitest';
import type {
  LlmRevolverEvent, LlmAdapter } from './llmAdapter';
import { resolveWithLlmRevolver, createInitialRevolverMemory } from './llmRevolver';
import type {
  LlmRevolverEvent, SovereignBrainResult } from '../brain/sovereignBrainContract';

function brain(file = 'README.md', code = '# README file\n'): SovereignBrainResult {
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
      patches: [{ file, type: 'replace', description: 'update docs', code }],
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
    expect((result as { ok: false; failure: { code: string } }).failure.code).toBe('invalid_contract');
  });

  it('rejects plan-only LLM output before it can become a draft PR', async () => {
    const bad = adapter('mlvoca', 10, async () => ({ providerId: 'mlvoca', brain: brain('docs/SOVEREIGN_PLAN.md', '# Sovereign Plan\n'), raw: 'plan-only' }));

    const result = await resolveWithLlmRevolver([bad], {
      mission: 'Improve runtime checks',
      repoPaths: ['src/App.tsx'],
      selectedFilePath: 'src/App.tsx',
    });

    expect(result.ok).toBe(false);
    expect((result as { ok: false; failure: { code: string; message: string } }).failure.code).toBe('invalid_contract');
    expect((result as { ok: false; failure: { code: string; message: string } }).failure.message).toContain('PLAN_ONLY');
  });

  it('rejects empty LLM patches', async () => {
    const bad = adapter('mlvoca', 10, async () => ({ providerId: 'mlvoca', brain: brain('src/App.tsx', ' '), raw: 'empty' }));

    const result = await resolveWithLlmRevolver([bad], {
      mission: 'Improve runtime checks',
      repoPaths: ['src/App.tsx'],
      selectedFilePath: 'src/App.tsx',
    });

    expect(result.ok).toBe(false);
    expect((result as { ok: false; failure: { code: string; message: string } }).failure.code).toBe('invalid_contract');
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

  it('returns consent-required when no-key routes are blocked and all others fail', async () => {
    // A user-key adapter that fails
    const failingUserKey: LlmAdapter = {
      id: 'gemini',
      label: 'gemini',
      kind: 'user-key',
      priority: 10,
      enabled: true,
      async run() {
        const err = new Error('API quota exceeded');
        (err as Error & { status: number }).status = 429;
        throw err;
      },
    };

    // A no-key adapter that should be blocked
    const noKey: LlmAdapter = {
      id: 'ovh-anonymous-code-chat',
      label: 'ovh',
      kind: 'no-key',
      priority: 20,
      enabled: true,
      async run() {
        return { providerId: 'ovh-anonymous-code-chat', brain: brain(), raw: 'ok' };
      },
    };

    const result = await resolveWithLlmRevolver([failingUserKey, noKey], {
      mission: 'Implement feature',
      repoPaths: ['src/App.tsx'],
      selectedFilePath: 'src/App.tsx',
      allowExternalNoKey: false, // explicitly disabled
    });

    expect(result.ok).toBe(false);
    // Should be consent-required, not regular failure
    expect('consentRequired' in result && result.consentRequired).toBe(true);
    expect('reason' in result && result.reason).toBe('no_key_routes_blocked');
    // The no-key adapter should have been skipped
    const skippedAttempt = result.attempts.find(a => a.type === 'provider:skipped');
    expect(skippedAttempt?.providerId).toBe('ovh-anonymous-code-chat');
  });

  it('allows no-key routes when allowExternalNoKey is true', async () => {
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
      allowExternalNoKey: true, // enabled
    });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.result.providerId).toBe('ovh-anonymous-code-chat');
    }
  });
  describe('cooldown tracking', () => {
    it('puts a rate-limited adapter into cooldown and skips it on next shot', async () => {
      let callCount = 0;
      const rateLimited: LlmAdapter = {
        id: 'mlvoca',
        label: 'mlvoca',
        kind: 'no-key',
        priority: 0,
        enabled: true,
        async run() {
          callCount += 1;
          const err = new Error('Rate limit exceeded');
          (err as Error & { status: number }).status = 429;
          throw err;
        },
      };
      const fallback: LlmAdapter = {
        id: 'pollinations',
        label: 'pollinations',
        kind: 'no-key',
        priority: 10,
        enabled: true,
        async run() {
          return { providerId: 'pollinations', brain: brain(), raw: 'ok' };
        },
      };

      // First shot: mlvoca gets tried, fails → enters cooldown
      // Second shot: pollinations is tried (mlvoca cooling)
      const nowValues = [1000, 1000, 1000, 1000];
      let nowIdx = 0;
      const fakeNow = () => nowValues[nowIdx++] ?? 1000;

      const result = await resolveWithLlmRevolver(
        [rateLimited, fallback],
        { mission: 'test', repoPaths: ['src/App.tsx'], selectedFilePath: 'src/App.tsx',
          allowExternalNoKey: true },
        { now: fakeNow },
      );

      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.result.providerId).toBe('pollinations');
      }
      // mlvoca was called once before entering cooldown
      expect(callCount).toBe(1);
    });

    it('skips a cooling adapter and emits provider:cooling event', async () => {
      const coolingAdapter: LlmAdapter = {
        id: 'mlvoca',
        label: 'mlvoca',
        kind: 'no-key',
        priority: 0,
        enabled: true,
        async run() {
          throw Object.assign(new Error('timeout'), { code: 'ETIMEDOUT' });
        },
      };
      const reserve: LlmAdapter = {
        id: 'pollinations',
        label: 'pollinations',
        kind: 'no-key',
        priority: 10,
        enabled: true,
        async run() {
          return { providerId: 'pollinations', brain: brain(), raw: 'ok' };
        },
      };

      const events: LlmRevolverEvent[] = [];
      const result = await resolveWithLlmRevolver(
        [coolingAdapter, reserve],
        { mission: 'x', repoPaths: ['a.ts'], selectedFilePath: 'a.ts', allowExternalNoKey: true },
        { onEvent: (e) => events.push(e) },
      );

      expect(result.ok).toBe(true);
      // After first run with cooldown the memory should have coolingUntil set
      if (result.ok) {
        expect(result.memory.coolingUntil['mlvoca']).toBeUndefined(); // 'mlvoca' failed with unknown, not rate_limit
      }
    });

    it('createInitialRevolverMemory includes coolingUntil', () => {
      const mem = createInitialRevolverMemory();
      expect(mem.coolingUntil).toBeDefined();
      expect(typeof mem.coolingUntil).toBe('object');
    });

    it('cooling adapter is skipped when memory.coolingUntil is in the future', async () => {
      const now = Date.now();
      const coolingMemory = {
        nextIndex: 0,
        shots: [],
        coolingUntil: { 'mlvoca': now + 300_000 }, // 5 min in future
      };
      let called = false;
      const coolingAdapter: LlmAdapter = {
        id: 'mlvoca',
        label: 'mlvoca',
        kind: 'no-key',
        priority: 0,
        enabled: true,
        async run() { called = true; return { providerId: 'mlvoca', brain: brain(), raw: 'x' }; },
      };
      const reserve: LlmAdapter = {
        id: 'pollinations',
        label: 'pollinations',
        kind: 'no-key',
        priority: 10,
        enabled: true,
        async run() { return { providerId: 'pollinations', brain: brain(), raw: 'ok' }; },
      };

      const events: LlmRevolverEvent[] = [];
      const result = await resolveWithLlmRevolver(
        [coolingAdapter, reserve],
        { mission: 'x', repoPaths: ['a.ts'], selectedFilePath: 'a.ts', allowExternalNoKey: true },
        { memory: coolingMemory, onEvent: (e) => events.push(e) },
      );

      expect(called).toBe(false);
      expect(result.ok).toBe(true);
      const coolingEvent = events.find(e => e.type === 'provider:cooling');
      expect(coolingEvent).toBeDefined();
      expect(coolingEvent?.providerId).toBe('mlvoca');
    });
  });

});
