import { describe, expect, it } from 'vitest';
import {
  addLearningMemoryPattern,
  assertLearningMemoryPatternValid,
  assertLearningMemoryStoreValid,
  buildLearningMemoryPattern,
  buildLearningMemoryRuntimeSummary,
  createLearningMemoryStore,
  intakeLearningMemory,
  queryLearningMemory,
  validateLearningMemoryPattern,
  validateLearningMemoryStore,
  type LearningMemoryPattern,
} from './sovereignLearningMemory';

describe('sovereignLearningMemory', () => {
  it('builds sanitized patterns from intake nodes', () => {
    const pattern = buildLearningMemoryPattern({
      kind: 'workflow',
      sourceNode: 'workflow-watch',
      outputNodes: ['workflow-repair-plan', 'action-builder'],
      summary: 'CI failed because token=ghp_1234567890abcdef leaked in logs',
      evidence: 'workflow check failed after lint step',
      tags: ['CI Failed', ' lint '],
      confidence: 'observed',
      now: 10,
    });

    expect(pattern.summary).toContain('<redacted-secret>');
    expect(pattern.summary).not.toContain('ghp_1234567890abcdef');
    expect(pattern.tags).toEqual(['ci-failed', 'lint']);
    expect(validateLearningMemoryPattern(pattern).valid).toBe(true);
  });

  it('rejects unknown source and output nodes', () => {
    const pattern = {
      ...buildLearningMemoryPattern({
        kind: 'risk',
        sourceNode: 'file-integrity',
        outputNodes: ['health-report'],
        summary: 'Risk path found.',
        evidence: 'repo had .env path.',
        confidence: 'observed',
      }),
      sourceNode: 'fake-node',
      outputNodes: ['fake-output'],
    } as unknown as LearningMemoryPattern;

    const report = validateLearningMemoryPattern(pattern);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('Unknown source node');
    expect(report.errors.join(' ')).toContain('Unknown output node');
  });

  it('rejects manually forged unredacted secret-like content', () => {
    const pattern: LearningMemoryPattern = {
      id: 'learn-forged',
      kind: 'risk',
      sourceNode: 'telemetry',
      outputNodes: ['health-report'],
      summary: 'Bearer abcdefghijklmnopqrstuvwxyz',
      evidence: 'token: secret123456789',
      tags: [],
      confidence: 'manual',
      hits: 1,
      createdAt: 1,
      updatedAt: 1,
    };

    expect(validateLearningMemoryPattern(pattern).valid).toBe(false);
    expect(() => assertLearningMemoryPatternValid(pattern)).toThrow('unredacted secret-like');
  });

  it('adds patterns, deduplicates by id and increments hits', () => {
    const store = createLearningMemoryStore(1);
    const pattern = buildLearningMemoryPattern({
      kind: 'repair',
      sourceNode: 'workflow-repair-plan',
      outputNodes: ['action-builder'],
      summary: 'Lint failure should create focused repair mission.',
      evidence: 'workflow repair plan saw lint red.',
      confidence: 'observed',
      now: 1,
    });

    const first = addLearningMemoryPattern(store, pattern, 2);
    const second = addLearningMemoryPattern(first, pattern, 3);

    expect(second.patterns).toHaveLength(1);
    expect(second.patterns[0].hits).toBe(2);
    expect(second.patterns[0].updatedAt).toBe(3);
    expect(validateLearningMemoryStore(second).valid).toBe(true);
  });

  it('rejects duplicate ids in forged stores', () => {
    const pattern = buildLearningMemoryPattern({
      kind: 'guard',
      sourceNode: 'generated-file-review',
      outputNodes: ['draft-pr-publisher'],
      summary: 'High risk generated file should block publishing.',
      evidence: 'generated-file-review detected forbidden path.',
      confidence: 'observed',
      now: 1,
    });
    const store = { version: 1 as const, patterns: [pattern, pattern], updatedAt: 1 };

    expect(validateLearningMemoryStore(store).valid).toBe(false);
    expect(() => assertLearningMemoryStoreValid(store)).toThrow('Duplicate learning pattern id');
  });

  it('queries by output node, kind and tag', () => {
    let store = createLearningMemoryStore(1);
    store = intakeLearningMemory(store, {
      kind: 'workflow',
      sourceNode: 'workflow-watch',
      outputNodes: ['workflow-repair-plan'],
      summary: 'Failed lint check maps to repair plan.',
      evidence: 'workflow check lint failed.',
      tags: ['lint'],
      confidence: 'observed',
      now: 2,
    });
    store = intakeLearningMemory(store, {
      kind: 'docs',
      sourceNode: 'user-mission',
      outputNodes: ['action-builder'],
      summary: 'Docs request should generate docs package.',
      evidence: 'mission requested README and Update History.',
      tags: ['docs'],
      confidence: 'manual',
      now: 3,
    });

    expect(queryLearningMemory(store, { outputNode: 'workflow-repair-plan' })).toHaveLength(1);
    expect(queryLearningMemory(store, { kind: 'docs', tag: 'docs' })[0].summary).toContain('Docs request');
    expect(buildLearningMemoryRuntimeSummary(store)).toContain('2 learning pattern');
  });
});
