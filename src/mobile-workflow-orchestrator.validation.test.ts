import { describe, expect, it } from 'vitest';
import { validateMobileWorkflowDecision } from './mobile-workflow-orchestrator';
import { matchMobileWorkflowPatternDetailed } from './mobile-workflow-pattern-rules';

describe('mobile workflow decision validation', () => {
  it('accepts a complete safe decision', () => {
    const report = validateMobileWorkflowDecision({
      lamp: 'green',
      mode: 'review-log',
      title: 'Ready',
      summary: 'Ready to continue.',
      targetNav: 'Files',
      autoOpenTarget: true,
      lines: ['one', 'two'],
    });

    expect(report.valid).toBe(true);
    expect(report.errors).toEqual([]);
  });

  it('rejects auto-open without a target', () => {
    const report = validateMobileWorkflowDecision({
      lamp: 'yellow',
      mode: 'nocode-plan',
      title: 'Need input',
      summary: 'Need one next step.',
      targetNav: null,
      autoOpenTarget: true,
      lines: ['next'],
    });

    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('Auto-open requires a target');
  });

  it('correctly sorts candidate pattern rules deterministically without localeCompare', () => {
    const match = matchMobileWorkflowPatternDetailed('running test failed build failed');
    expect(match.rule.id).toBe('real-stopper');
    expect(match.candidates.length).toBeGreaterThan(0);
  });
});
