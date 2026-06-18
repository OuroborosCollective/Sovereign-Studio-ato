import { describe, expect, it } from 'vitest';
import {
  assertMobileWorkflowPatternRulesValid,
  matchMobileWorkflowPattern,
  validateMobileWorkflowPatternRule,
  MOBILE_WORKFLOW_PATTERN_RULES,
} from './mobile-workflow-pattern-rules';

describe('mobile workflow pattern rules', () => {
  it('keeps the bundled pattern rules valid', () => {
    expect(() => assertMobileWorkflowPatternRulesValid()).not.toThrow();
    expect(MOBILE_WORKFLOW_PATTERN_RULES.some((rule) => rule.id === 'awaiting-intent')).toBe(true);
  });

  it('selects active work over the default pattern', () => {
    const match = matchMobileWorkflowPattern('package-build package build running');
    expect(match.rule.id).toBe('active-work');
    expect(match.rule.mode).toBe('matrix-work');
  });

  it('selects review when generated output was accepted', () => {
    const match = matchMobileWorkflowPattern('SELF REVIEW: ACCEPTED generated-output-accepted');
    expect(match.rule.id).toBe('result-review');
    expect(match.rule.targetNav).toBe('Files');
  });

  it('does not select a stopper when harmless zero-failed text is present', () => {
    const match = matchMobileWorkflowPattern('0 failed step runtime ready');
    expect(match.rule.id).not.toBe('real-stopper');
  });

  it('rejects a malformed rule', () => {
    const report = validateMobileWorkflowPatternRule({
      id: 'awaiting-intent',
      priority: Number.NaN,
      lamp: 'yellow',
      mode: 'nocode-plan',
      targetNav: null,
      autoOpenTarget: true,
      title: '',
      summary: '',
      positiveSignals: [],
      minScore: -1,
      lines: [],
    });

    expect(report.valid).toBe(false);
    expect(report.errors.length).toBeGreaterThan(0);
  });
});
