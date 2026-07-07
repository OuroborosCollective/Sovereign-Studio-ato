import { describe, expect, it } from 'vitest';
import { createSolutionPatternStore } from './solutionPatternMemory';
import { buildPresetActionMemoryHint, recordPresetActionOutcome } from './presetActionOutcomeMemory';

describe('presetActionOutcomeMemory', () => {
  it('records proof-backed preset success through the existing SolutionPatternMemory store', () => {
    const result = recordPresetActionOutcome(createSolutionPatternStore(100), {
      actionId: 'runtime_hardening',
      status: 'success',
      repoFullName: 'OuroborosCollective/Sovereign-Studio-ato',
      branch: 'main',
      targetPaths: ['src/features/product/runtime/runtimeGuard.ts'],
      summary: 'Runtime guard was hardened with tests.',
      proof: 'type-check and targeted tests passed',
      route: 'runtime-review',
      now: 200,
    });

    expect(result.accepted).toBe(true);
    expect(result.learned).toBe(true);
    expect(result.store.patterns).toHaveLength(1);
    expect(result.store.patterns[0]).toMatchObject({
      intakeNode: 'action-builder',
      processingNode: 'learning-memory',
      category: 'learning-memory',
      successfulUses: 1,
    });
    expect(buildPresetActionMemoryHint(result.store, 'runtime_hardening')).toContain('Runtime guard');
  });

  it('rejects blocked preset outcomes so they never count as successful learning', () => {
    const result = recordPresetActionOutcome(createSolutionPatternStore(100), {
      actionId: 'open_pr_review',
      status: 'blocked',
      targetPaths: ['README.md'],
      summary: 'Draft PR unavailable.',
      blocker: 'GitHub access missing.',
      route: 'github-access',
      now: 200,
    });

    expect(result.accepted).toBe(false);
    expect(result.rejected).toBe(true);
    expect(result.store.patterns).toHaveLength(0);
    expect(result.store.rejections).toHaveLength(1);
    expect(result.store.rejections[0].reason).toContain('blocked');
  });

  it('redacts sensitive looking tokens before they reach memory summaries', () => {
    const result = recordPresetActionOutcome(createSolutionPatternStore(100), {
      actionId: 'tests_gate_repair',
      status: 'failed',
      targetPaths: ['package.json'],
      summary: 'Failed with ghp_abcdefghijklmnopqrstuvwxyz1234567890 token visible.',
      blocker: 'password=secret-value',
      route: 'runtime',
      now: 200,
    });

    expect(JSON.stringify(result.store)).not.toContain('ghp_abcdefghijklmnopqrstuvwxyz');
    expect(JSON.stringify(result.store)).not.toContain('secret-value');
  });
});
