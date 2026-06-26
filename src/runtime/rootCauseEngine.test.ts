import { describe, it, expect } from 'vitest';
import { createDependencyGraph, findRootCause } from './rootCauseEngine';

describe('rootCauseEngine', () => {
  it('finds upstream root node', () => {
    const g = createDependencyGraph([
      { from: 'A', to: 'B' },
      { from: 'B', to: 'C' },
    ]);
    const report = findRootCause(g, 'C');
    expect(report.cause).toBe('A');
    expect(report.path).toEqual(['A', 'B', 'C']);
  });
});
