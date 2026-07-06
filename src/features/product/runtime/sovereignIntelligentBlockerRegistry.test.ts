import { describe, expect, it } from 'vitest';
import {
  createBlockerRegistryState,
  categorizeBlocker,
  trackBlocker,
  resolveBlocker,
  isBlockerStuck,
  getActiveBlockers,
  getStuckBlockers,
  getResolutionHint,
  analyzeBlockerPatterns,
} from './sovereignIntelligentBlockerRegistry';
import type { SovereignToolObservation } from './sovereignToolObservationRuntime';
import type { ContainerDecisionLearningSignal } from './containerDecisionLearning';

function createMockObservation(blocker: string, phase: 'blocked' | 'completed' | 'failed'): SovereignToolObservation {
  return {
    id: `obs-${Date.now()}`,
    toolName: 'test_tool',
    route: 'runtime',
    phase,
    blocker: phase === 'blocked' ? blocker : undefined,
    resultSummary: phase === 'completed' ? 'Success' : 'Failed',
    createdAt: Date.now(),
    event: {} as any,
  };
}

describe('sovereignIntelligentBlockerRegistry', () => {
  describe('createBlockerRegistryState', () => {
    it('creates empty state', () => {
      const state = createBlockerRegistryState();

      expect(state.blockers).toHaveLength(0);
      expect(state.totalBlockers).toBe(0);
      expect(state.activeBlockers).toBe(0);
      expect(state.resolvedBlockers).toBe(0);
    });
  });

  describe('categorizeBlocker', () => {
    it('categorizes github token blockers', () => {
      const category = categorizeBlocker('GitHub token missing');

      expect(category.category).toBe('auth');
      expect(category.severity).toBe('error');
      expect(category.resolutionHint).toContain('Token');
    });

    it('categorizes network blockers', () => {
      const category = categorizeBlocker('DNS resolution failed');

      expect(category.category).toBe('network');
      expect(category.severity).toBe('error');
    });

    it('categorizes rate limit blockers', () => {
      const category = categorizeBlocker('Rate limit exceeded (429)');

      expect(category.category).toBe('rate-limit');
      expect(category.severity).toBe('warning');
    });

    it('categorizes unknown blockers', () => {
      const category = categorizeBlocker('Some random blocker xyz');

      expect(category.category).toBe('unknown');
      expect(category.resolutionHint).toContain('analysieren');
    });
  });

  describe('trackBlocker', () => {
    it('tracks new blocker', () => {
      const state = createBlockerRegistryState();
      const observation = createMockObservation('missing_token', 'blocked');

      const newState = trackBlocker(state, observation);

      expect(newState.blockers).toHaveLength(1);
      expect(newState.blockers[0].blockerText).toBe('missing_token');
      expect(newState.blockers[0].occurrenceCount).toBe(1);
      expect(newState.activeBlockers).toBe(1);
    });

    it('increments occurrence count for repeated blocker', () => {
      let state = createBlockerRegistryState();
      const obs1 = createMockObservation('token_error', 'blocked');
      const obs2 = createMockObservation('token_error', 'blocked');

      state = trackBlocker(state, obs1);
      state = trackBlocker(state, obs2);

      expect(state.blockers).toHaveLength(1);
      expect(state.blockers[0].occurrenceCount).toBe(2);
      expect(state.activeBlockers).toBe(1);
    });

    it('ignores non-blocker observations', () => {
      const state = createBlockerRegistryState();
      const observation = createMockObservation('', 'completed');

      const newState = trackBlocker(state, observation);

      expect(newState.blockers).toHaveLength(0);
    });
  });

  describe('resolveBlocker', () => {
    it('resolves existing blocker', () => {
      let state = createBlockerRegistryState();
      const observation = createMockObservation('auth_failed', 'blocked');

      state = trackBlocker(state, observation);
      state = resolveBlocker(state, 'auth_failed');

      expect(state.resolvedBlockers).toBe(1);
      expect(getActiveBlockers(state)).toHaveLength(0);
    });

    it('ignores non-existing blocker', () => {
      const state = createBlockerRegistryState();
      const newState = resolveBlocker(state, 'unknown_blocker');

      expect(newState.resolvedBlockers).toBe(0);
    });
  });

  describe('isBlockerStuck', () => {
    it('detects stuck blocker', () => {
      const blocker = {
        blockerText: 'token_missing',
        kind: 'auth',
        severity: 'error' as const,
        category: 'auth',
        firstSeen: Date.now() - 10000,
        lastSeen: Date.now(),
        occurrenceCount: 5,
        resolutionHint: 'Provide token',
        resolvedCount: 0,
      };

      expect(isBlockerStuck(blocker, 3)).toBe(true);
      expect(isBlockerStuck(blocker, 6)).toBe(false);  // threshold 6 requires 6 active occurrences
    });

    it('does not count resolved occurrences', () => {
      const blocker = {
        blockerText: 'rate_limit',
        kind: 'rate-limit',
        severity: 'warning' as const,
        category: 'rate-limit',
        firstSeen: Date.now() - 10000,
        lastSeen: Date.now(),
        occurrenceCount: 4,
        resolutionHint: 'Wait',
        resolvedCount: 1,
      };

      // 4 occurrences - 1 resolved = 3 active = stuck at threshold 3
      expect(isBlockerStuck(blocker, 3)).toBe(true);
    });
  });

  describe('getActiveBlockers', () => {
    it('returns unresolved blockers sorted by severity', () => {
      let state = createBlockerRegistryState();

      state = trackBlocker(state, createMockObservation('minor_warning', 'blocked'));
      state = trackBlocker(state, createMockObservation('critical_error', 'blocked'));

      const active = getActiveBlockers(state);

      expect(active).toHaveLength(2);
      // Error severity should come first
      expect(active[0].blockerText).toBe('critical_error');
    });
  });

  describe('getStuckBlockers', () => {
    it('returns only stuck blockers', () => {
      let state = createBlockerRegistryState();

      // Add 4 occurrences of same blocker
      for (let i = 0; i < 4; i++) {
        state = trackBlocker(state, createMockObservation('repeated_blocker', 'blocked'));
      }

      // Add 1 occurrence of different blocker
      state = trackBlocker(state, createMockObservation('single_blocker', 'blocked'));

      const stuck = getStuckBlockers(state, 3);

      expect(stuck).toHaveLength(1);
      expect(stuck[0].blockerText).toBe('repeated_blocker');
    });
  });

  describe('getResolutionHint', () => {
    it('returns appropriate hint for github blockers', () => {
      const hint = getResolutionHint('GitHub token invalid');
      expect(hint).toContain('Token');
    });

    it('returns appropriate hint for network blockers', () => {
      const hint = getResolutionHint('Connection refused');
      expect(hint).toContain('Netzwerk');
    });
  });

  describe('analyzeBlockerPatterns', () => {
    it('extracts patterns from learning signals', () => {
      const signals: ContainerDecisionLearningSignal[] = [
        {
          containerId: 'session:1',
          ruleId: 'tool:github_access',
          learnTag: 'github_access',
          action: 'review',
          lamp: 'red',
          score: 0,
          outcome: 'failure',
          reason: 'GitHub token missing',
          timestamp: Date.now() - 1000,
        },
        {
          containerId: 'session:1',
          ruleId: 'tool:github_access',
          learnTag: 'github_access',
          action: 'review',
          lamp: 'red',
          score: 0,
          outcome: 'failure',
          reason: 'GitHub token missing',
          timestamp: Date.now(),
        },
        {
          containerId: 'session:1',
          ruleId: 'tool:repo_loader',
          learnTag: 'repo_loader',
          action: 'continue',
          lamp: 'green',
          score: 1,
          outcome: 'success',
          reason: 'Repo loaded',
          timestamp: Date.now(),
        },
      ];

      const patterns = analyzeBlockerPatterns(signals);

      expect(patterns.size).toBe(1);
      expect(patterns.get('GitHub token missing')?.count).toBe(2);
    });
  });
});
