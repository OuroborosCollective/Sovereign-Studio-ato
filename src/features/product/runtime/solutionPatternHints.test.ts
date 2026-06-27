import { describe, expect, it } from 'vitest';
import type { SolutionPattern, SolutionPatternStore } from './solutionPatternMemory';
import { buildSolutionPatternHint, formatSolutionPatternHints } from './solutionPatternHints';

function pattern(overrides: Partial<SolutionPattern>): SolutionPattern {
  return {
    id: 'pattern-default',
    status: 'active',
    problemSignature: 'problem',
    contextFingerprint: 'context',
    fixFingerprint: 'fix',
    category: 'warning',
    filePathHint: 'src/App.tsx',
    fileExtension: '.tsx',
    problemSummary: 'Problem',
    beforeFingerprint: 'before',
    solutionSummary: 'Stabilisiere Runtime Checks',
    afterFingerprint: 'after',
    conditions: [],
    recommendedSteps: [],
    evidence: 'test',
    intakeNode: 'learning-memory',
    processingNode: 'action-builder',
    outputNodes: ['telemetry'],
    confidence: 'completed',
    tags: [],
    hits: 0,
    successfulUses: 0,
    rejectedUses: 0,
    createdAt: 0,
    updatedAt: 0,
    ...overrides,
  };
}

function store(patterns: SolutionPattern[]): SolutionPatternStore {
  return { version: 1, patterns, rejections: [], updatedAt: 0 };
}

describe('solutionPatternHints', () => {
  it('returns empty output for stores without active patterns', () => {
    const result = buildSolutionPatternHint(store([
      pattern({ id: 'rejected', status: 'rejected', successfulUses: 10 }),
    ]));

    expect(formatSolutionPatternHints(store([]))).toBe('');
    expect(result.visible).toBe(false);
    expect(result.activeCount).toBe(0);
    expect(result.selectedPatternIds).toEqual([]);
  });

  it('sorts active patterns by successful uses and update time', () => {
    const result = buildSolutionPatternHint(store([
      pattern({ id: 'older', successfulUses: 2, updatedAt: 10, solutionSummary: 'Older' }),
      pattern({ id: 'winner', successfulUses: 5, updatedAt: 1, solutionSummary: 'Winner' }),
      pattern({ id: 'newer', successfulUses: 2, updatedAt: 20, solutionSummary: 'Newer' }),
    ]), 2);

    expect(result.visible).toBe(true);
    expect(result.activeCount).toBe(3);
    expect(result.selectedPatternIds).toEqual(['winner', 'newer']);
    expect(result.detail).toContain('Winner');
    expect(result.detail).toContain('Newer');
    expect(result.detail).not.toContain('Older');
  });

  it('redacts sensitive text from pattern summaries', () => {
    const hint = formatSolutionPatternHints(store([
      pattern({
        id: 'secret-pattern',
        solutionSummary: 'Use token=abc123 and password=secret before deploy',
      }),
    ]));

    expect(hint).toContain('<redacted>');
    expect(hint).not.toContain('abc123');
    expect(hint).not.toContain('secret');
  });

  it('clamps limit to a safe range', () => {
    const patterns = Array.from({ length: 12 }, (_, index) => pattern({
      id: `p-${index}`,
      successfulUses: 12 - index,
      solutionSummary: `Pattern ${index}`,
    }));

    const hint = buildSolutionPatternHint(store(patterns), 99);

    expect(hint.selectedPatternIds).toHaveLength(10);
    expect(hint.detail.split('\n')).toHaveLength(11);
  });
});
