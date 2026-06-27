import { describe, expect, it } from 'vitest';
import type { SolutionPattern, SolutionPatternStore } from './solutionPatternMemory';
import { buildWorkspaceInspectorRuntime } from './workspaceInspectorRuntime';

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

function store(patterns: SolutionPattern[] = []): SolutionPatternStore {
  return { version: 1, patterns, rejections: [], updatedAt: 0 };
}

describe('workspaceInspectorRuntime', () => {
  it('keeps a no-repo state quiet except for PAL guidance', () => {
    const result = buildWorkspaceInspectorRuntime({
      repoName: 'Empty',
      branch: 'main',
      repoFiles: [],
      mission: 'Erklär mir den Ablauf',
      repoReady: false,
      solutionPatternStore: store(),
      now: 10,
    });

    expect(result.policy.hasVisibleSignals).toBe(true);
    expect(result.policy.signals).toHaveLength(1);
    expect(result.policy.signals[0].id).toBe('pal');
    expect(result.policy.signals[0].lamp).toBe('green');
    expect(result.palBlocked).toBe(false);
  });

  it('prioritizes real PAL blockers before other hints', () => {
    const result = buildWorkspaceInspectorRuntime({
      repoName: 'Blocked Repo',
      branch: 'main',
      repoFiles: ['package.json', 'src/App.tsx', 'src/main.tsx'],
      mission: 'Fix die roten Gates',
      repoReady: true,
      blockers: ['Health Blocker zuerst lösen'],
      solutionPatternStore: store([
        pattern({ id: 'aha', successfulUses: 3, solutionSummary: 'Nutze bekannte Gates-Reparatur' }),
      ]),
      now: 20,
    });

    expect(result.palBlocked).toBe(true);
    expect(result.activePatternCount).toBe(1);
    expect(result.policy.topLamp).toBe('red');
    // Brownfield and PAL both have 'red' lamp in this test state.
    // Alphabetical ID sorting in quietInspectorHintPolicy.ts puts 'brownfield' before 'pal'.
    expect(result.policy.signals[0].id).toBe('brownfield');
    expect(result.policy.summary).toContain('Blocker');
  });

  it('composes Brownfield, PAL and memory into a capped inspector policy', () => {
    const result = buildWorkspaceInspectorRuntime({
      repoName: 'Composed Repo',
      branch: 'main',
      repoFiles: [
        'package.json',
        'pnpm-lock.yaml',
        'src/legacy/OldFeature.tsx',
        'src/App.tsx',
        'src/App.test.tsx',
      ],
      mission: 'Implementiere den neuen Runtime Hook',
      repoReady: true,
      solutionPatternStore: store([
        pattern({ id: 'aha-a', successfulUses: 2, updatedAt: 2, solutionSummary: 'Hook Pattern wiederverwenden' }),
      ]),
      now: 30,
    });

    expect(result.policy.hasVisibleSignals).toBe(true);
    expect(result.policy.signals.map((signal) => signal.id)).toContain('brownfield');
    expect(result.policy.signals.map((signal) => signal.id)).toContain('pal');
    expect(result.policy.signals.map((signal) => signal.id)).toContain('remote-memory');
    expect(result.brownfieldScore).toBeGreaterThanOrEqual(0);
    expect(result.activePatternCount).toBe(1);
  });
});
