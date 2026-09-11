import { describe, expect, it } from 'vitest';
import { canClearPatternMemory, derivePatternMemoryContainerState } from './patternMemoryContainerRuntime';
import type { SolutionPattern, SolutionPatternStore } from './solutionPatternMemory';

function pattern(id: string, status: SolutionPattern['status'], confidence: SolutionPattern['confidence'], hits: number): SolutionPattern {
  return {
    id,
    status,
    problemSignature: `sig-${id}`,
    contextFingerprint: `ctx-${id}`,
    fixFingerprint: `fix-${id}`,
    category: 'logic',
    filePathHint: `src/${id}.ts`,
    fileExtension: '.ts',
    problemSummary: `Problem ${id}`,
    beforeFingerprint: `before-${id}`,
    solutionSummary: `Solution ${id}`,
    afterFingerprint: `after-${id}`,
    conditions: ['condition'],
    recommendedSteps: ['step'],
    evidence: `proof-${id}`,
    intakeNode: 'action-builder',
    processingNode: 'learning-memory',
    outputNodes: ['action-builder'],
    confidence,
    tags: [id],
    hits,
    successfulUses: 0,
    rejectedUses: 0,
    createdAt: 1000,
    updatedAt: 1000,
  };
}

describe('patternMemoryContainerRuntime', () => {
  it('derives active counters and hits without counting rejected patterns', () => {
    const store: SolutionPatternStore = {
      version: 1,
      updatedAt: 1000,
      patterns: [
        pattern('p1', 'active', 'completed', 5),
        pattern('p2', 'active', 'reported', 3),
        pattern('p3', 'rejected', 'completed', 10),
        pattern('p4', 'active', 'manual', 2),
      ],
      rejections: [{ id: 'r1', reason: 'rejected', errors: [], warnings: [], at: 1000 }],
    };
    const derived = derivePatternMemoryContainerState(store);
    expect(derived.activePatterns).toBe(3);
    expect(derived.completedPatterns).toBe(1);
    expect(derived.reportedPatterns).toBe(1);
    expect(derived.totalHits).toBe(10);
    expect(derived.rejectedItems).toBe(1);
    expect(canClearPatternMemory(store)).toBe(true);
  });

  it('handles an empty store', () => {
    const store: SolutionPatternStore = { version: 1, patterns: [], rejections: [], updatedAt: 0 };
    expect(derivePatternMemoryContainerState(store)).toMatchObject({
      activePatterns: 0,
      completedPatterns: 0,
      reportedPatterns: 0,
      totalHits: 0,
      rejectedItems: 0,
    });
    expect(canClearPatternMemory(store)).toBe(false);
  });
});
