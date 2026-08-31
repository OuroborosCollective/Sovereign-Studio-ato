import { describe, expect, it } from 'vitest';
import { derivePatternMemoryContainerState, canClearPatternMemory } from './patternMemoryContainerRuntime';
import type { SolutionPatternStore } from './solutionPatternMemory';

describe('patternMemoryContainerRuntime', () => {
  it('correctly derives state from store in a single pass', () => {
    const mockStore: SolutionPatternStore = {
      version: 1,
      updatedAt: 1000,
      patterns: [
        {
          id: 'p1',
          status: 'active',
          problemSignature: 'sig1',
          contextFingerprint: 'ctx1',
          fixFingerprint: 'fix1',
          category: 'scan-finding-registry',
          filePathHint: 'src/file1.ts',
          fileExtension: '.ts',
          problemSummary: 'Problem 1',
          beforeFingerprint: 'before1',
          solutionSummary: 'Solution 1',
          afterFingerprint: 'after1',
          conditions: ['cond1'],
          recommendedSteps: ['step1'],
          evidence: 'proof1',
          intakeNode: 'scan-finding-registry',
          processingNode: 'learning-memory',
          outputNodes: ['action-builder'],
          confidence: 'completed',
          tags: ['a'],
          hits: 5,
          successfulUses: 1,
          rejectedUses: 0,
          createdAt: 1000,
          updatedAt: 1000,
        },
        {
          id: 'p2',
          status: 'active',
          problemSignature: 'sig2',
          contextFingerprint: 'ctx2',
          fixFingerprint: 'fix2',
          category: 'workflow-watch',
          filePathHint: 'src/file2.ts',
          fileExtension: '.ts',
          problemSummary: 'Problem 2',
          beforeFingerprint: 'before2',
          solutionSummary: 'Solution 2',
          afterFingerprint: 'after2',
          conditions: ['cond2'],
          recommendedSteps: ['step2'],
          evidence: 'proof2',
          intakeNode: 'workflow-watch',
          processingNode: 'learning-memory',
          outputNodes: ['action-builder'],
          confidence: 'reported',
          tags: ['b'],
          hits: 3,
          successfulUses: 0,
          rejectedUses: 0,
          createdAt: 1000,
          updatedAt: 1000,
        },
        {
          id: 'p3',
          status: 'rejected',
          problemSignature: 'sig3',
          contextFingerprint: 'ctx3',
          fixFingerprint: 'fix3',
          category: 'telemetry',
          filePathHint: 'src/file3.ts',
          fileExtension: '.ts',
          problemSummary: 'Problem 3',
          beforeFingerprint: 'before3',
          solutionSummary: 'Solution 3',
          afterFingerprint: 'after3',
          conditions: ['cond3'],
          recommendedSteps: ['step3'],
          evidence: 'proof3',
          intakeNode: 'telemetry',
          processingNode: 'learning-memory',
          outputNodes: ['action-builder'],
          confidence: 'completed',
          tags: ['c'],
          hits: 10,
          successfulUses: 1,
          rejectedUses: 0,
          createdAt: 1000,
          updatedAt: 1000,
        },
        {
          id: 'p4',
          status: 'active',
          problemSignature: 'sig4',
          contextFingerprint: 'ctx4',
          fixFingerprint: 'fix4',
          category: 'action-builder',
          filePathHint: 'src/file4.ts',
          fileExtension: '.ts',
          problemSummary: 'Problem 4',
          beforeFingerprint: 'before4',
          solutionSummary: 'Solution 4',
          afterFingerprint: 'after4',
          conditions: ['cond4'],
          recommendedSteps: ['step4'],
          evidence: 'proof4',
          intakeNode: 'action-builder',
          processingNode: 'learning-memory',
          outputNodes: ['action-builder'],
          confidence: 'manual',
          tags: ['d'],
          hits: 2,
          successfulUses: 0,
          rejectedUses: 0,
          createdAt: 1000,
          updatedAt: 1000,
        },
      ],
      rejections: [
        {
          id: 'r1',
          reason: 'rejected',
          errors: [],
          warnings: [],
          at: 1000,
        },
      ],
    };

    const derived = derivePatternMemoryContainerState(mockStore);

    expect(derived.valid).toBe(true);
    expect(derived.activePatterns).toBe(3);
    expect(derived.completedPatterns).toBe(1);
    expect(derived.reportedPatterns).toBe(1);
    expect(derived.totalHits).toBe(10); // 5 + 3 + 2 (p3 has status: 'rejected' so ignored)
    expect(derived.rejectedItems).toBe(1);
    expect(canClearPatternMemory(mockStore)).toBe(true);
  });

  it('handles empty pattern store', () => {
    const emptyStore: SolutionPatternStore = {
      version: 1,
      patterns: [],
      rejections: [],
      updatedAt: 0,
    };

    const derived = derivePatternMemoryContainerState(emptyStore);

    expect(derived.valid).toBe(true);
    expect(derived.activePatterns).toBe(0);
    expect(derived.completedPatterns).toBe(0);
    expect(derived.reportedPatterns).toBe(0);
    expect(derived.totalHits).toBe(0);
    expect(derived.rejectedItems).toBe(0);
    expect(canClearPatternMemory(emptyStore)).toBe(false);
  });
});
