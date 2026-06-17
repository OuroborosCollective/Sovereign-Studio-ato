import { describe, expect, it } from 'vitest';
import {
  buildSolutionPatternRuntimeSummary,
  createSolutionPatternStore,
  learnSolutionPattern,
  matchSolutionPatterns,
  validateSolutionPatternLearningInput,
  validateSolutionPatternMatches,
  validateSolutionPatternStore,
  type SolutionPatternLearningInput,
} from './solutionPatternMemory';

function baseInput(overrides: Partial<SolutionPatternLearningInput> = {}): SolutionPatternLearningInput {
  return {
    intakeNode: 'workflow-watch',
    processingNode: 'workflow-repair-plan',
    outputNodes: ['action-builder', 'learning-memory'],
    problem: {
      findingId: 'find-lint',
      category: 'ci-failure',
      severity: 'high',
      filePath: 'eslint.config.ts',
      lineNumber: 1,
      description: 'Lint workflow fails after adding generated runtime files.',
      beforeSnippet: 'rules: { noUnusedVars: off }',
      contextPaths: ['src/features/product/runtime', 'eslint.config.ts'],
      contextSignals: ['lint', 'generated-files', 'typescript'],
    },
    fix: {
      summary: 'Update lint config and generated runtime exports so lint sees valid TypeScript modules.',
      afterSnippet: 'rules: { noUnusedVars: warn }',
      changedFiles: ['eslint.config.ts', 'src/features/product/runtime/index.ts'],
      steps: ['Inspect failed lint check', 'Patch lint config', 'Re-run workflow watch'],
      completed: false,
    },
    confidence: 'reported',
    tags: ['lint', 'runtime'],
    now: 10,
    ...overrides,
  };
}

describe('solutionPatternMemory', () => {
  it('validates learning input and learns a reported problem solution pattern', () => {
    const input = baseInput();
    expect(validateSolutionPatternLearningInput(input).valid).toBe(true);

    const result = learnSolutionPattern(createSolutionPatternStore(1), input);

    expect(result.accepted).toBe(true);
    expect(result.store.patterns).toHaveLength(1);
    expect(result.pattern?.confidence).toBe('reported');
    expect(result.pattern?.successfulUses).toBe(0);
    expect(validateSolutionPatternStore(result.store).valid).toBe(true);
  });

  it('extends an existing pattern when a later completed fix proves the same solution', () => {
    const reported = learnSolutionPattern(createSolutionPatternStore(1), baseInput({ now: 10 }));
    const completed = learnSolutionPattern(reported.store, baseInput({
      confidence: 'completed',
      now: 20,
      fix: {
        ...baseInput().fix,
        completed: true,
        proof: 'Workflow Watch green after lint check passed.',
      },
    }));

    expect(completed.accepted).toBe(true);
    expect(completed.store.patterns).toHaveLength(1);
    expect(completed.store.patterns[0].hits).toBe(2);
    expect(completed.store.patterns[0].successfulUses).toBe(1);
    expect(completed.store.patterns[0].confidence).toBe('completed');
    expect(buildSolutionPatternRuntimeSummary(completed.store)).toContain('proof-backed success');
  });

  it('soft rejects invalid pattern intake without throwing or stopping the store', () => {
    const store = createSolutionPatternStore(1);
    const result = learnSolutionPattern(store, baseInput({
      problem: {
        ...baseInput().problem,
        filePath: '',
      },
      fix: {
        ...baseInput().fix,
        changedFiles: [],
      },
      now: 30,
    }));

    expect(result.accepted).toBe(false);
    expect(result.store.patterns).toHaveLength(0);
    expect(result.store.rejections).toHaveLength(1);
    expect(result.summary).toContain('rejected softly');
    expect(validateSolutionPatternStore(result.store).valid).toBe(true);
  });

  it('soft rejects sensitive-looking input instead of hard failing the runtime flow', () => {
    const result = learnSolutionPattern(createSolutionPatternStore(1), baseInput({
      problem: {
        ...baseInput().problem,
        description: 'Lint failed because password=abc123 was accidentally printed.',
      },
      now: 40,
    }));

    expect(result.accepted).toBe(false);
    expect(result.rejection?.errors.join(' ')).toContain('sensitive-looking');
    expect(result.store.rejections).toHaveLength(1);
  });

  it('matches later similar structural problems and emits aha logic', () => {
    const learned = learnSolutionPattern(createSolutionPatternStore(1), baseInput({
      confidence: 'completed',
      fix: {
        ...baseInput().fix,
        completed: true,
        proof: 'Workflow Watch green.',
      },
      now: 50,
    }));

    const matches = matchSolutionPatterns(learned.store, {
      category: 'ci-failure',
      filePath: 'eslint.config.ts',
      description: 'Lint workflow fails on generated TypeScript runtime module.',
      contextSignals: ['lint', 'typescript', 'runtime'],
      outputNode: 'action-builder',
      minSuccesses: 1,
    });

    expect(matches).toHaveLength(1);
    expect(matches[0].score).toBeGreaterThan(0);
    expect(matches[0].aha).toContain('Aha:');
    expect(matches[0].reasons).toContain('same category');
    expect(validateSolutionPatternMatches(matches).valid).toBe(true);
  });

  it('returns no match when output node is not allowed for the pattern', () => {
    const learned = learnSolutionPattern(createSolutionPatternStore(1), baseInput({
      confidence: 'completed',
      fix: {
        ...baseInput().fix,
        completed: true,
        proof: 'Workflow Watch green.',
      },
      now: 60,
    }));

    const matches = matchSolutionPatterns(learned.store, {
      category: 'ci-failure',
      filePath: 'eslint.config.ts',
      contextSignals: ['lint', 'typescript'],
      outputNode: 'draft-pr-publisher',
      minSuccesses: 1,
    });

    expect(matches).toHaveLength(0);
  });
});
