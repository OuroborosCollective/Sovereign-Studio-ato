import { describe, expect, it } from 'vitest';
import type { ExternalMemorySyncItem } from './externalMemorySync';
import { createSolutionPatternStore, matchSolutionPatterns } from './solutionPatternMemory';
import {
  buildLearningInputFromRemoteUpdate,
  intakeRemoteMemoryUpdates,
  validateRemoteMemoryUpdateItem,
} from './remoteMemoryUpdateIntake';

function remoteSolution(overrides: Partial<ExternalMemorySyncItem> = {}): ExternalMemorySyncItem {
  return {
    id: 'remote-solve-1',
    kind: 'solution-pattern',
    title: 'Workflow check fails after runtime guard update',
    text: 'Re-run the workflow watch, inspect the failing check name, then patch the generated runtime guard exports.',
    tags: ['workflow', 'runtime-guard', 'typescript'],
    metadata: {
      contributionScope: 'shared-derived-pattern',
      category: 'ci-failure',
      fileExtension: '.ts',
      successfulUses: 3,
    },
    ...overrides,
  };
}

describe('remoteMemoryUpdateIntake', () => {
  it('validates shared solution-pattern updates', () => {
    const item = remoteSolution();
    const report = validateRemoteMemoryUpdateItem(item);
    expect(report.valid).toBe(true);
  });

  it('rejects user-submitted remote items so contributor erasure remains isolated', () => {
    const item = remoteSolution({ metadata: { contributionScope: 'user-submitted-summary', category: 'ci-failure' } });
    const report = validateRemoteMemoryUpdateItem(item);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('shared-derived-pattern');
  });

  it('rejects non-solution remote items for local solution memory intake', () => {
    const item = remoteSolution({ kind: 'scan-finding' });
    const report = validateRemoteMemoryUpdateItem(item);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('Only solution-pattern');
  });

  it('builds a safe local learning input from a shared remote update', () => {
    const input = buildLearningInputFromRemoteUpdate(remoteSolution(), 10);
    expect(input.intakeNode).toBe('learning-memory');
    expect(input.problem.category).toBe('ci-failure');
    expect(input.problem.filePath).toContain('.ts');
    expect(input.confidence).toBe('reported');
    expect(input.fix.completed).toBe(false);
    expect(input.tags).toContain('shared-derived-pattern');
  });

  it('intakes shared remote solution updates into local solution memory', () => {
    const result = intakeRemoteMemoryUpdates(createSolutionPatternStore(1), [remoteSolution()], 10);
    expect(result.accepted).toBe(1);
    expect(result.rejected).toBe(0);
    expect(result.store.patterns).toHaveLength(1);
    expect(result.store.patterns[0].tags).toContain('remote-update');

    const matches = matchSolutionPatterns(result.store, {
      category: 'ci-failure',
      filePath: 'server/runtime.ts',
      contextSignals: ['workflow', 'runtime-guard'],
      outputNode: 'action-builder',
    });
    expect(matches.length).toBeGreaterThan(0);
    expect(matches[0].aha).toContain('Aha:');
  });

  it('soft rejects invalid remote updates and keeps processing valid ones', () => {
    const invalid = remoteSolution({
      id: 'bad',
      kind: 'learning-pattern',
      metadata: { contributionScope: 'user-submitted-summary' },
    });
    const valid = remoteSolution({ id: 'good' });
    const result = intakeRemoteMemoryUpdates(createSolutionPatternStore(1), [invalid, valid], 10);
    expect(result.accepted).toBe(1);
    expect(result.rejected).toBe(1);
    expect(result.store.patterns).toHaveLength(1);
    expect(result.rejections.join(' ')).toContain('Only solution-pattern');
  });
});
