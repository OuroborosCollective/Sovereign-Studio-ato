import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  createContainerDecisionLearningSignal,
  validateContainerDecisionLearningSignal,
  applyContainerDecisionOutcome,
  summarizeContainerDecisionLearning,
  resetContainerDecisionLearningHistory,
  getContainerDecisionLearningHistory,
  getContainerDecisionLearningStats,
} from './containerDecisionLearning';

describe('containerDecisionLearning', () => {
  beforeEach(() => {
    resetContainerDecisionLearningHistory();
  });

  afterEach(() => {
    resetContainerDecisionLearningHistory();
  });

  describe('validateContainerDecisionLearningSignal', () => {
    it('accepts a valid learning signal', () => {
      const signal = {
        containerId: 'repo-snapshot',
        ruleId: 'repo-snapshot:ready',
        learnTag: 'repo-snapshot.ready',
        action: 'continue',
        lamp: 'green',
        score: 1,
        outcome: 'success' as const,
        reason: 'Rule matched and workflow continued',
        timestamp: Date.now(),
      };
      const report = validateContainerDecisionLearningSignal(signal);
      expect(report.valid).toBe(true);
      expect(report.errors).toHaveLength(0);
    });

    it('rejects empty containerId', () => {
      const signal = {
        containerId: '',
        ruleId: 'repo-snapshot:ready',
        learnTag: 'repo-snapshot.ready',
        action: 'continue',
        lamp: 'green',
        score: 1,
        outcome: 'success' as const,
        reason: 'Test',
        timestamp: Date.now(),
      };
      const report = validateContainerDecisionLearningSignal(signal);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('containerId required');
    });

    it('rejects invalid outcome', () => {
      const signal = {
        containerId: 'repo-snapshot',
        ruleId: 'repo-snapshot:ready',
        learnTag: 'repo-snapshot.ready',
        action: 'continue',
        lamp: 'green',
        score: 1,
        outcome: 'invalid-outcome' as 'accepted' | 'rejected' | 'rewrite' | 'repair' | 'success' | 'failure',
        reason: 'Test',
        timestamp: Date.now(),
      };
      const report = validateContainerDecisionLearningSignal(signal);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('outcome');
    });

    it('rejects secret-like reason', () => {
      const signal = {
        containerId: 'repo-snapshot',
        ruleId: 'repo-snapshot:ready',
        learnTag: 'repo-snapshot.ready',
        action: 'continue',
        lamp: 'green',
        score: 1,
        outcome: 'success' as const,
        reason: 'Token: ghp_abcdefghijklmnopqrstuvwxyz1234567890',
        timestamp: Date.now(),
      };
      const report = validateContainerDecisionLearningSignal(signal);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('secrets');
    });

    it('rejects negative score', () => {
      const signal = {
        containerId: 'repo-snapshot',
        ruleId: 'repo-snapshot:ready',
        learnTag: 'repo-snapshot.ready',
        action: 'continue',
        lamp: 'green',
        score: -1,
        outcome: 'success' as const,
        reason: 'Test',
        timestamp: Date.now(),
      };
      const report = validateContainerDecisionLearningSignal(signal);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('score');
    });

    it('rejects future timestamp beyond 1 minute', () => {
      const signal = {
        containerId: 'repo-snapshot',
        ruleId: 'repo-snapshot:ready',
        learnTag: 'repo-snapshot.ready',
        action: 'continue',
        lamp: 'green',
        score: 1,
        outcome: 'success' as const,
        reason: 'Test',
        timestamp: Date.now() + 120000,
      };
      const report = validateContainerDecisionLearningSignal(signal);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('future');
    });

    it('rejects invalid lamp', () => {
      const signal = {
        containerId: 'repo-snapshot',
        ruleId: 'repo-snapshot:ready',
        learnTag: 'repo-snapshot.ready',
        action: 'continue',
        lamp: 'purple',
        score: 1,
        outcome: 'success' as const,
        reason: 'Test',
        timestamp: Date.now(),
      };
      const report = validateContainerDecisionLearningSignal(signal);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('lamp');
    });

    it('rejects invalid action', () => {
      const signal = {
        containerId: 'repo-snapshot',
        ruleId: 'repo-snapshot:ready',
        learnTag: 'repo-snapshot.ready',
        action: 'invalid-action',
        lamp: 'green',
        score: 1,
        outcome: 'success' as const,
        reason: 'Test',
        timestamp: Date.now(),
      };
      const report = validateContainerDecisionLearningSignal(signal);
      expect(report.valid).toBe(false);
      expect(report.errors.join(' ')).toContain('action');
    });
  });

  describe('createContainerDecisionLearningSignal', () => {
    it('creates a valid learning signal', () => {
      const signal = createContainerDecisionLearningSignal(
        'repo-snapshot',
        'repo-snapshot:ready',
        'repo-snapshot.ready',
        'continue',
        'green',
        1,
        'success',
        'Rule matched correctly',
      );
      expect(signal.containerId).toBe('repo-snapshot');
      expect(signal.ruleId).toBe('repo-snapshot:ready');
      expect(signal.outcome).toBe('success');
      expect(signal.timestamp).toBeGreaterThan(0);
    });

    it('throws for invalid signal', () => {
      expect(() =>
        createContainerDecisionLearningSignal(
          '',
          'rule',
          'tag',
          'continue',
          'green',
          1,
          'success',
          'reason',
        ),
      ).toThrow();
    });

    it('includes optional fields when provided', () => {
      const signal = createContainerDecisionLearningSignal(
        'repo-snapshot',
        'repo-snapshot:ready',
        'repo-snapshot.ready',
        'continue',
        'green',
        1,
        'success',
        'Rule matched',
        'telemetry-123',
        'pattern-456',
      );
      expect(signal.relatedTelemetryId).toBe('telemetry-123');
      expect(signal.relatedPatternId).toBe('pattern-456');
    });
  });

  describe('applyContainerDecisionOutcome', () => {
    it('applies valid signal to history', () => {
      const signal = createContainerDecisionLearningSignal(
        'repo-snapshot',
        'repo-snapshot:ready',
        'repo-snapshot.ready',
        'continue',
        'green',
        1,
        'success',
        'Rule worked',
      );
      applyContainerDecisionOutcome(signal);
      const history = getContainerDecisionLearningHistory();
      expect(history).toHaveLength(1);
      expect(history[0].outcome).toBe('success');
    });

    it('throws for invalid signal', () => {
      const signal = {
        containerId: '',
        ruleId: 'test',
        learnTag: 'test',
        action: 'continue',
        lamp: 'green',
        score: 0,
        outcome: 'success' as const,
        reason: 'Test',
        timestamp: Date.now(),
      };
      expect(() => applyContainerDecisionOutcome(signal)).toThrow();
    });

    it('limits history to 500 entries when exceeding 1000', () => {
      for (let i = 0; i < 1005; i++) {
        const signal = createContainerDecisionLearningSignal(
          'repo-snapshot',
          'repo-snapshot:ready',
          'repo-snapshot.ready',
          'continue',
          'green',
          1,
          'success',
          `Test ${i}`,
        );
        applyContainerDecisionOutcome(signal);
      }
      const history = getContainerDecisionLearningHistory();
      expect(history.length).toBeLessThanOrEqual(500);
    });
  });

  describe('summarizeContainerDecisionLearning', () => {
    it('returns message for empty history', () => {
      const summary = summarizeContainerDecisionLearning();
      expect(summary).toContain('No learning signals');
    });

    it('returns message for specific container with no signals', () => {
      const summary = summarizeContainerDecisionLearning('non-existent');
      expect(summary).toContain('No learning signals');
      expect(summary).toContain('non-existent');
    });

    it('summarizes history correctly', () => {
      for (let i = 0; i < 3; i++) {
        applyContainerDecisionOutcome(
          createContainerDecisionLearningSignal(
            'repo-snapshot',
            'repo-snapshot:ready',
            'repo-snapshot.ready',
            'continue',
            'green',
            1,
            'success',
            'Success reason',
          ),
        );
      }
      applyContainerDecisionOutcome(
        createContainerDecisionLearningSignal(
          'repo-snapshot',
          'repo-snapshot:review',
          'repo-snapshot.review',
          'review',
          'yellow',
          1,
          'failure',
          'Failure reason',
        ),
      );
      const summary = summarizeContainerDecisionLearning();
      expect(summary).toContain('signal(s) processed');
      expect(summary).toContain('repo-snapshot');
    });

    it('summarizes for specific container', () => {
      applyContainerDecisionOutcome(
        createContainerDecisionLearningSignal(
          'builder',
          'builder:ready',
          'builder.ready',
          'continue',
          'green',
          1,
          'success',
          'Builder worked',
        ),
      );
      const summary = summarizeContainerDecisionLearning('builder');
      expect(summary).toContain('builder');
    });
  });

  describe('getContainerDecisionLearningStats', () => {
    it('returns zeros for empty history', () => {
      const stats = getContainerDecisionLearningStats();
      expect(stats.total).toBe(0);
      expect(stats.success).toBe(0);
      expect(stats.failure).toBe(0);
    });

    it('counts outcomes correctly', () => {
      applyContainerDecisionOutcome(
        createContainerDecisionLearningSignal(
          'repo-snapshot',
          'repo-snapshot:ready',
          'repo-snapshot.ready',
          'continue',
          'green',
          1,
          'success',
          'Success',
        ),
      );
      applyContainerDecisionOutcome(
        createContainerDecisionLearningSignal(
          'repo-snapshot',
          'repo-snapshot:ready',
          'repo-snapshot.ready',
          'continue',
          'green',
          1,
          'accepted',
          'Accepted',
        ),
      );
      applyContainerDecisionOutcome(
        createContainerDecisionLearningSignal(
          'repo-snapshot',
          'repo-snapshot:review',
          'repo-snapshot.review',
          'review',
          'yellow',
          1,
          'failure',
          'Failure',
        ),
      );
      const stats = getContainerDecisionLearningStats();
      expect(stats.total).toBe(3);
      expect(stats.success).toBe(1);
      expect(stats.accepted).toBe(1);
      expect(stats.failure).toBe(1);
    });

    it('filters by container', () => {
      applyContainerDecisionOutcome(
        createContainerDecisionLearningSignal(
          'repo-snapshot',
          'repo-snapshot:ready',
          'repo-snapshot.ready',
          'continue',
          'green',
          1,
          'success',
          'Repo success',
        ),
      );
      applyContainerDecisionOutcome(
        createContainerDecisionLearningSignal(
          'builder',
          'builder:ready',
          'builder.ready',
          'continue',
          'green',
          1,
          'success',
          'Builder success',
        ),
      );
      const repoStats = getContainerDecisionLearningStats('repo-snapshot');
      expect(repoStats.total).toBe(1);
      expect(repoStats.success).toBe(1);
    });
  });

  describe('deterministic behavior', () => {
    it('same input produces same output', () => {
      const signal1 = createContainerDecisionLearningSignal(
        'repo-snapshot',
        'repo-snapshot:ready',
        'repo-snapshot.ready',
        'continue',
        'green',
        1,
        'success',
        'Deterministic test',
      );
      const signal2 = createContainerDecisionLearningSignal(
        'repo-snapshot',
        'repo-snapshot:ready',
        'repo-snapshot.ready',
        'continue',
        'green',
        1,
        'success',
        'Deterministic test',
      );
      expect(signal1.containerId).toBe(signal2.containerId);
      expect(signal1.ruleId).toBe(signal2.ruleId);
      expect(signal1.outcome).toBe(signal2.outcome);
      expect(signal1.learnTag).toBe(signal2.learnTag);
    });
  });
});