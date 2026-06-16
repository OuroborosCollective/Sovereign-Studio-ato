import { describe, expect, it } from 'vitest';
import {
  assertSovereignBrainResult,
  parseSovereignBrainJson,
  toImplementationFiles,
  type SovereignBrainResult,
} from './sovereignBrainContract';

const validBrain: SovereignBrainResult = {
  perception: {
    domain: 'repo automation',
    intent: 'update README',
    architecture: 'React Vite app',
    confidence: 0.9,
  },
  analysis: {
    severity: 'medium',
    issues: [
      {
        type: 'architecture',
        location: 'generator',
        description: 'Preview-only output is not enough.',
        impact: 'README request would not update README.',
      },
    ],
    rootCause: 'No hard brain contract before push.',
    systemicRisk: 'Bad PRs with irrelevant files.',
  },
  plan: {
    strategy: 'Generate real target files.',
    phases: [
      { phase: 1, name: 'Plan', actions: ['select files'], rationale: 'Need real patches.' },
    ],
    estimatedComplexity: 'medium',
  },
  execution: {
    patches: [
      {
        file: 'README.md',
        type: 'replace',
        description: 'Update README.',
        code: '# README\n',
      },
    ],
    integrationNotes: 'Push through PR flow.',
    testStrategy: 'Run type-check and tests.',
  },
  learning: {
    patterns: ['Brain-gated output'],
    rules: ['No patch, no push'],
    architectureUpgrade: 'Use brain contract before GitHub push.',
  },
};

describe('sovereignBrainContract', () => {
  it('accepts a complete five-layer brain result', () => {
    expect(() => assertSovereignBrainResult(validBrain)).not.toThrow();
    expect(toImplementationFiles(validBrain)).toEqual([
      { path: 'README.md', content: '# README\n', reason: 'Update README.' },
    ]);
  });

  it('rejects provider output with no real patches', () => {
    const invalid = {
      ...validBrain,
      execution: {
        ...validBrain.execution,
        patches: [],
      },
    };

    expect(() => assertSovereignBrainResult(invalid)).not.toThrow();
    expect(toImplementationFiles(invalid)).toEqual([]);
  });

  it('parses fenced JSON responses', () => {
    const parsed = parseSovereignBrainJson(`\`\`\`json\n${JSON.stringify(validBrain)}\n\`\`\``);
    assertSovereignBrainResult(parsed);
    expect(parsed.perception.intent).toBe('update README');
  });

  it('rejects malformed execution patches', () => {
    const malformed = {
      ...validBrain,
      execution: {
        ...validBrain.execution,
        patches: [{ file: '', type: 'create', description: 'bad', code: '' }],
      },
    };

    expect(() => assertSovereignBrainResult(malformed)).toThrow();
  });
});
