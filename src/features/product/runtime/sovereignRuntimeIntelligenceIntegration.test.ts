import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  detectBlockerPatterns,
  getSessionHealth,
  formatIntelligenceStatsCompact,
  type SovereignIntelligenceStats,
} from './sovereignRuntimeIntelligenceIntegration';
import type { SovereignToolObservation } from './sovereignToolObservationRuntime';
import type { SovereignExecutionSession } from './sovereignExecutionSessionRuntime';

// Mock all dependencies
vi.mock('./sovereignSessionIntelligenceBridge', () => ({
  emitSovereignSessionSignal: vi.fn().mockResolvedValue(undefined),
  emitSovereignToolSignal: vi.fn().mockResolvedValue(undefined),
  applySovereignToolLearning: vi.fn(),
  applySovereignStuckLearning: vi.fn(),
  applySovereignStrategyChangeLearning: vi.fn(),
}));

vi.mock('./containerDecisionLearning', () => ({
  getContainerDecisionLearningStats: vi.fn().mockReturnValue({
    total: 10,
    success: 7,
    failure: 3,
    accepted: 0,
    rejected: 0,
    rewrite: 0,
    repair: 0,
  }),
}));

vi.mock('../../../predictive/predictiveLayer', () => ({
  getDefaultPredictiveLayer: vi.fn().mockReturnValue({
    getSnapshot: () => ({
      active: true,
      nodeCount: 5,
      patternCount: 3,
      avgConfidence: 0.75,
    }),
  }),
}));

// Helper to create mock session
function createMockSession(overrides: Partial<SovereignExecutionSession> = {}): SovereignExecutionSession {
  return {
    id: 'test-session',
    request: 'Test request',
    status: 'running',
    plan: {
      id: 'plan-1',
      title: 'Test Plan',
      steps: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    },
    observations: [],
    currentStepId: 'step-1',
    createdAt: Date.now(),
    updatedAt: Date.now(),
    ...overrides,
  };
}

// Helper to create mock observation
function createMockObservation(overrides: Partial<SovereignToolObservation> = {}): SovereignToolObservation {
  return {
    id: 'obs-1',
    toolName: 'github_access',
    route: 'github-access',
    phase: 'completed',
    createdAt: Date.now(),
    event: {} as any,
    ...overrides,
  };
}

describe('sovereignRuntimeIntelligenceIntegration', () => {
  describe('detectBlockerPatterns', () => {
    it('detects repeated blocker patterns', () => {
      const observations: SovereignToolObservation[] = [
        createMockObservation({ id: '1', blocker: 'missing_token', createdAt: 1000 }),
        createMockObservation({ id: '2', blocker: 'missing_token', createdAt: 2000 }),
        createMockObservation({ id: '3', blocker: 'missing_token', createdAt: 3000 }),
        createMockObservation({ id: '4', blocker: undefined, createdAt: 4000 }),
        createMockObservation({ id: '5', phase: 'completed', createdAt: 5000 }),
      ];

      const patterns = detectBlockerPatterns(observations);

      expect(patterns).toHaveLength(1);
      expect(patterns[0].blockerText).toBe('missing_token');
      expect(patterns[0].occurrenceCount).toBe(3);
    });

    it('sorts patterns by occurrence count', () => {
      const observations: SovereignToolObservation[] = [
        createMockObservation({ id: '1', blocker: 'minor_issue', createdAt: 1000 }),
        createMockObservation({ id: '2', blocker: 'major_blocker', createdAt: 2000 }),
        createMockObservation({ id: '3', blocker: 'major_blocker', createdAt: 3000 }),
        createMockObservation({ id: '4', blocker: 'major_blocker', createdAt: 4000 }),
        createMockObservation({ id: '5', blocker: 'minor_issue', createdAt: 5000 }),
      ];

      const patterns = detectBlockerPatterns(observations);

      expect(patterns[0].blockerText).toBe('major_blocker');
      expect(patterns[0].occurrenceCount).toBe(3);
      expect(patterns[1].blockerText).toBe('minor_issue');
      expect(patterns[1].occurrenceCount).toBe(2);
    });

    it('limits to recent count', () => {
      const observations: SovereignToolObservation[] = [
        createMockObservation({ id: '1', blocker: 'old_blocker', createdAt: 1000 }),
        createMockObservation({ id: '2', blocker: 'old_blocker', createdAt: 2000 }),
        createMockObservation({ id: '3', blocker: 'new_blocker', createdAt: 3000 }),
      ];

      // recentCount=1 means only look at last observation
      const patterns = detectBlockerPatterns(observations, 1);

      expect(patterns).toHaveLength(1);
      expect(patterns[0].blockerText).toBe('new_blocker');
    });
  });

  describe('getSessionHealth', () => {
    it('returns healthy for running session', () => {
      const session = createMockSession({ status: 'running' });
      const report = getSessionHealth(session);

      expect(report.health).toBe('healthy');
      expect(report.reason).toBe('Session läuft normal.');
      expect(report.recommendations).toHaveLength(0);
    });

    it('returns warning for blocked session', () => {
      const session = createMockSession({
        status: 'blocked',
        blocker: 'missing_token',
      });
      const report = getSessionHealth(session);

      expect(report.health).toBe('warning');
      expect(report.reason).toBe('missing_token');
      expect(report.recommendations).toContain('Strategie überprüfen');
    });

    it('returns critical for error session', () => {
      const session = createMockSession({
        status: 'error',
        error: 'runtime_error',
      });
      const report = getSessionHealth(session);

      expect(report.health).toBe('critical');
      expect(report.reason).toBe('runtime_error');
      expect(report.recommendations).toContain('Fehler analysieren');
    });

    it('warns on repeated blockers', () => {
      const observations: SovereignToolObservation[] = [
        createMockObservation({ id: '1', blocker: 'token_issue' }),
        createMockObservation({ id: '2', blocker: 'token_issue' }),
        createMockObservation({ id: '3', blocker: 'token_issue' }),
        createMockObservation({ id: '4', blocker: 'token_issue' }),
      ];

      const session = createMockSession({ status: 'running', observations });
      const report = getSessionHealth(session);

      expect(report.health).toBe('warning');
      expect(report.recommendations).toContain('Strategie wechseln');
    });
  });

  describe('formatIntelligenceStatsCompact', () => {
    it('formats active predictive layer', () => {
      const stats: SovereignIntelligenceStats = {
        predictive: {
          active: true,
          nodeCount: 10,
          patternCount: 5,
          avgConfidence: 0.78,
        },
        learning: {
          totalSignals: 100,
          successCount: 75,
          failureCount: 25,
          successRate: 75,
        },
      };

      const formatted = formatIntelligenceStatsCompact(stats);

      expect(formatted).toContain('🧠');
      expect(formatted).toContain('10 Nodes');
      expect(formatted).toContain('5 Patterns');
      expect(formatted).toContain('78% Conf');
      expect(formatted).toContain('100 Signals');
      expect(formatted).toContain('75% Success');
    });

    it('returns empty string when no stats', () => {
      const stats: SovereignIntelligenceStats = {
        predictive: {
          active: false,
          nodeCount: 0,
          patternCount: 0,
          avgConfidence: 0,
        },
        learning: {
          totalSignals: 0,
          successCount: 0,
          failureCount: 0,
          successRate: 0,
        },
      };

      const formatted = formatIntelligenceStatsCompact(stats);

      expect(formatted).toBe('');
    });
  });
});
