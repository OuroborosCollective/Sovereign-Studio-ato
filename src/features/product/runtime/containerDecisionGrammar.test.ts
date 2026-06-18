import { describe, expect, it } from 'vitest';
import {
  decideContainerAction,
  validateContainerDecisionRule,
  KNOWN_CONTAINER_IDS,
  assertContainerDecisionRulesValid,
} from './containerDecisionGrammar';

describe('containerDecisionGrammar', () => {
  describe('validateContainerDecisionRule', () => {
    it('accepts a valid rule', () => {
      const rule = {
        id: 'test:ready',
        containerId: 'repo-snapshot',
        priority: 50,
        lamp: 'green' as const,
        action: 'continue' as const,
        signals: ['repo ready'],
        minScore: 1,
        learnTag: 'test.ready',
        nextAction: 'continue',
      };
      const report = validateContainerDecisionRule(rule);
      expect(report.valid).toBe(true);
      expect(report.errors).toHaveLength(0);
    });

    it('rejects empty id', () => {
      const rule = {
        id: '',
        containerId: 'repo-snapshot',
        priority: 50,
        lamp: 'green' as const,
        action: 'continue' as const,
        signals: ['repo ready'],
        minScore: 1,
        learnTag: 'test.ready',
        nextAction: 'continue',
      };
      const report = validateContainerDecisionRule(rule);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('id required');
    });

    it('rejects unknown containerId', () => {
      const rule = {
        id: 'test:ready',
        containerId: 'unknown-container',
        priority: 50,
        lamp: 'green' as const,
        action: 'continue' as const,
        signals: ['test'],
        minScore: 1,
        learnTag: 'test.ready',
        nextAction: 'continue',
      };
      const report = validateContainerDecisionRule(rule);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('unknown');
    });

    it('rejects minScore exceeding signal count', () => {
      const rule = {
        id: 'test:ready',
        containerId: 'repo-snapshot',
        priority: 50,
        lamp: 'green' as const,
        action: 'continue' as const,
        signals: ['single signal'],
        minScore: 3,
        learnTag: 'test.ready',
        nextAction: 'continue',
      };
      const report = validateContainerDecisionRule(rule);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('cannot exceed signal count');
    });

    it('rejects signal and blocker overlap', () => {
      const rule = {
        id: 'test:ready',
        containerId: 'repo-snapshot',
        priority: 50,
        lamp: 'green' as const,
        action: 'continue' as const,
        signals: ['overlap signal'],
        blockers: ['overlap signal', 'other blocker'],
        minScore: 1,
        learnTag: 'test.ready',
        nextAction: 'continue',
      };
      const report = validateContainerDecisionRule(rule);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('cannot overlap');
    });

    it('rejects invalid lamp', () => {
      const rule = {
        id: 'test:ready',
        containerId: 'repo-snapshot',
        priority: 50,
        lamp: 'purple' as 'green' | 'yellow' | 'red',
        action: 'continue' as const,
        signals: ['test'],
        minScore: 1,
        learnTag: 'test.ready',
        nextAction: 'continue',
      };
      const report = validateContainerDecisionRule(rule);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('lamp invalid');
    });

    it('rejects invalid action', () => {
      const rule = {
        id: 'test:ready',
        containerId: 'repo-snapshot',
        priority: 50,
        lamp: 'green' as const,
        action: 'invalid-action' as 'continue' | 'ask-user' | 'review' | 'repair' | 'learn',
        signals: ['test'],
        minScore: 1,
        learnTag: 'test.ready',
        nextAction: 'continue',
      };
      const report = validateContainerDecisionRule(rule);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('action invalid');
    });
  });

  describe('assertContainerDecisionRulesValid', () => {
    it('accepts valid rules', () => {
      const rules = [
        {
          id: 'repo-snapshot:ready',
          containerId: 'repo-snapshot',
          priority: 50,
          lamp: 'green' as const,
          action: 'continue' as const,
          signals: ['repo ready'],
          minScore: 1,
          learnTag: 'repo-snapshot.ready',
          nextAction: 'continue',
        },
      ];
      expect(() => assertContainerDecisionRulesValid(rules)).not.toThrow();
    });

    it('rejects duplicate rule ids', () => {
      const rules = [
        {
          id: 'duplicate-id',
          containerId: 'repo-snapshot',
          priority: 50,
          lamp: 'green' as const,
          action: 'continue' as const,
          signals: ['repo ready'],
          minScore: 1,
          learnTag: 'repo-snapshot.ready',
          nextAction: 'continue',
        },
        {
          id: 'duplicate-id',
          containerId: 'builder',
          priority: 50,
          lamp: 'green' as const,
          action: 'continue' as const,
          signals: ['builder ready'],
          minScore: 1,
          learnTag: 'builder.ready',
          nextAction: 'continue',
        },
      ];
      expect(() => assertContainerDecisionRulesValid(rules)).toThrow('duplicate id');
    });
  });

  describe('decideContainerAction', () => {
    const rules = [
      {
        id: 'repo-snapshot:ready',
        containerId: 'repo-snapshot',
        priority: 80,
        lamp: 'green' as const,
        action: 'continue' as const,
        signals: ['repo ready', 'snapshot loaded', 'repository loaded'],
        minScore: 1,
        learnTag: 'repo-snapshot.ready',
        nextAction: 'continue guided flow',
      },
      {
        id: 'repo-snapshot:review',
        containerId: 'repo-snapshot',
        priority: 70,
        lamp: 'yellow' as const,
        action: 'review' as const,
        signals: ['repo needs attention', 'snapshot warning'],
        minScore: 1,
        learnTag: 'repo-snapshot.review',
        nextAction: 'review snapshot status',
      },
      {
        id: 'repo-snapshot:repair',
        containerId: 'repo-snapshot',
        priority: 90,
        lamp: 'red' as const,
        action: 'repair' as const,
        signals: ['repo load failed', 'snapshot error'],
        blockers: ['repo ready'],
        minScore: 1,
        learnTag: 'repo-snapshot.repair',
        nextAction: 'fix repo load error',
      },
    ];

    it('selects green continue when ready signal matches', () => {
      const decision = decideContainerAction('repo-snapshot', 'repo ready and working', rules);
      expect(decision.lamp).toBe('green');
      expect(decision.action).toBe('continue');
      expect(decision.ruleId).toBe('repo-snapshot:ready');
    });

    it('selects yellow review when review signal matches', () => {
      const decision = decideContainerAction('repo-snapshot', 'repo needs attention', rules);
      expect(decision.lamp).toBe('yellow');
      expect(decision.action).toBe('review');
      expect(decision.ruleId).toBe('repo-snapshot:review');
    });

    it('selects red repair when repair signal matches and no blocker', () => {
      const decision = decideContainerAction('repo-snapshot', 'repo load failed with error', rules);
      expect(decision.lamp).toBe('red');
      expect(decision.action).toBe('repair');
      expect(decision.ruleId).toBe('repo-snapshot:repair');
    });

    it('blocks match when blocker signal is present', () => {
      // Text contains "repo load failed" which matches repair rule, but "repo ready" is a blocker
      const decision = decideContainerAction('repo-snapshot', 'repo load failed and repo ready', rules);
      expect(decision.lamp).not.toBe('red');
      // Since repair is blocked, and ready rule has lower priority than repair, 
      // but repair is blocked so ready should win
      expect(decision.ruleId).toBe('repo-snapshot:ready');
    });

    it('returns fallback for unknown state', () => {
      const decision = decideContainerAction('repo-snapshot', 'some unknown text', rules);
      expect(decision.ruleId).toBe('fallback');
      expect(decision.lamp).toBe('yellow');
    });

    it('resolves priority correctly when multiple rules match', () => {
      const decision = decideContainerAction('repo-snapshot', 'repo ready and repo needs attention', rules);
      expect(decision.ruleId).toBe('repo-snapshot:ready');
      expect(decision.priority).toBe(80);
    });

    it('includes matchedSignals in decision', () => {
      const decision = decideContainerAction('repo-snapshot', 'repo ready', rules);
      expect(decision.matchedSignals).toContain('repo ready');
    });

    it('computes confidence correctly', () => {
      const decision = decideContainerAction('repo-snapshot', 'repo ready', rules);
      expect(decision.confidence).toBeGreaterThan(0);
      expect(decision.confidence).toBeLessThanOrEqual(1);
    });

    it('returns zero confidence for fallback', () => {
      const decision = decideContainerAction('repo-snapshot', 'unknown text', rules);
      expect(decision.confidence).toBe(0);
      expect(decision.matchedSignals).toHaveLength(0);
    });
  });

  describe('KNOWN_CONTAINER_IDS', () => {
    it('includes all required container IDs', () => {
      expect(KNOWN_CONTAINER_IDS).toContain('repo-snapshot');
      expect(KNOWN_CONTAINER_IDS).toContain('builder');
      expect(KNOWN_CONTAINER_IDS).toContain('generated-files');
      expect(KNOWN_CONTAINER_IDS).toContain('diff-preview');
      expect(KNOWN_CONTAINER_IDS).toContain('workflow');
      expect(KNOWN_CONTAINER_IDS).toContain('remote-memory');
      expect(KNOWN_CONTAINER_IDS).toContain('pattern-memory');
      expect(KNOWN_CONTAINER_IDS).toContain('telemetry');
      expect(KNOWN_CONTAINER_IDS).toContain('health');
      expect(KNOWN_CONTAINER_IDS).toContain('runtime-coverage');
      expect(KNOWN_CONTAINER_IDS).toContain('findings');
      expect(KNOWN_CONTAINER_IDS).toContain('sequential-runtime');
      expect(KNOWN_CONTAINER_IDS).toContain('mobile-workbench');
      expect(KNOWN_CONTAINER_IDS).toContain('mobile-coach');
    });

    it('has at least 14 container IDs', () => {
      expect(KNOWN_CONTAINER_IDS.length).toBeGreaterThanOrEqual(14);
    });
  });
});