import { describe, expect, it } from 'vitest';
import {
  analyzeToolPerformance,
  getBestPerformingTools,
  generateToolSuggestions,
  suggestAlternativeStrategy,
  hasSufficientHistory,
  formatSuggestionForChat,
} from './sovereignPredictiveToolSelector';
import type { ContainerDecisionLearningSignal } from './containerDecisionLearning';

// Helper to create mock signals
function createMockSignal(
  toolName: string,
  outcome: 'success' | 'failure',
  timestamp = Date.now(),
): ContainerDecisionLearningSignal {
  return {
    containerId: 'session:test',
    ruleId: `tool:${toolName}`,
    learnTag: toolName,
    action: outcome === 'success' ? 'continue' : 'review',
    lamp: outcome === 'success' ? 'green' : 'red',
    score: outcome === 'success' ? 1.0 : 0.0,
    outcome,
    reason: `Tool ${toolName} ${outcome}`,
    timestamp,
  };
}

describe('sovereignPredictiveToolSelector', () => {
  describe('analyzeToolPerformance', () => {
    it('calculates performance for single tool', () => {
      const signals: ContainerDecisionLearningSignal[] = [
        createMockSignal('github_access', 'success'),
        createMockSignal('github_access', 'success'),
        createMockSignal('github_access', 'failure'),
      ];

      const performance = analyzeToolPerformance(signals);

      expect(performance).toHaveLength(1);
      expect(performance[0].toolName).toBe('github_access');
      expect(performance[0].totalAttempts).toBe(3);
      expect(performance[0].successCount).toBe(2);
      expect(performance[0].failureCount).toBe(1);
      expect(performance[0].successRate).toBeCloseTo(0.667, 2);
    });

    it('handles multiple tools', () => {
      const signals: ContainerDecisionLearningSignal[] = [
        createMockSignal('openhands', 'success'),
        createMockSignal('openhands', 'success'),
        createMockSignal('repo_loader', 'success'),
        createMockSignal('repo_loader', 'failure'),
      ];

      const performance = analyzeToolPerformance(signals);

      expect(performance).toHaveLength(2);
      // openhands has 100% success, should be first
      expect(performance[0].toolName).toBe('openhands');
      expect(performance[1].toolName).toBe('repo_loader');
    });

    it('ignores non-tool signals', () => {
      const signals: ContainerDecisionLearningSignal[] = [
        createMockSignal('github_access', 'success'),
        {
          containerId: 'session:test',
          ruleId: 'strategy:stuck-detection',
          learnTag: 'change_strategy',
          action: 'ask-user',
          lamp: 'yellow',
          score: 0.0,
          outcome: 'failure' as const,
          reason: 'Session stuck',
          timestamp: Date.now(),
        },
      ];

      const performance = analyzeToolPerformance(signals);

      expect(performance).toHaveLength(1);
    });
  });

  describe('getBestPerformingTools', () => {
    it('returns top performing tools', () => {
      const performance = [
        { toolName: 'tool-a', route: 'route-a', totalAttempts: 5, successCount: 3, failureCount: 2, successRate: 0.6, lastUsed: Date.now() },
        { toolName: 'tool-b', route: 'route-b', totalAttempts: 10, successCount: 8, failureCount: 2, successRate: 0.8, lastUsed: Date.now() },
        { toolName: 'tool-c', route: 'route-c', totalAttempts: 1, successCount: 1, failureCount: 0, successRate: 1.0, lastUsed: Date.now() },
      ];

      const best = getBestPerformingTools(performance, 2);

      // Should filter out tool-c (only 1 attempt) and return top 2
      expect(best).toHaveLength(2);
      expect(best[0].toolName).toBe('tool-a');
      expect(best[1].toolName).toBe('tool-b');
    });
  });

  describe('generateToolSuggestions', () => {
    it('suggests github tool for github-related requests', () => {
      const performance = [
        { toolName: 'github_access', route: 'github-access', totalAttempts: 5, successCount: 4, failureCount: 1, successRate: 0.8, lastUsed: Date.now() },
      ];

      const suggestions = generateToolSuggestions('Create a GitHub PR', performance);

      expect(suggestions.length).toBeGreaterThan(0);
      expect(suggestions[0].toolName).toBe('github_access');
    });

    it('returns empty for no performance data', () => {
      const suggestions = generateToolSuggestions('Do something', []);
      expect(suggestions).toHaveLength(0);
    });

    it('skips tools with low success rate', () => {
      const performance = [
        { toolName: 'failing_tool', route: 'fail-route', totalAttempts: 5, successCount: 1, failureCount: 4, successRate: 0.2, lastUsed: Date.now() },
      ];

      const suggestions = generateToolSuggestions('Do something', performance);
      expect(suggestions).toHaveLength(0);
    });
  });

  describe('suggestAlternativeStrategy', () => {
    it('suggests alternative when tool is stuck', () => {
      const performance = [
        { toolName: 'openhands', route: 'openhands', totalAttempts: 5, successCount: 1, failureCount: 4, successRate: 0.2, lastUsed: Date.now() },
        { toolName: 'direct-patch', route: 'direct-patch', totalAttempts: 5, successCount: 4, failureCount: 1, successRate: 0.8, lastUsed: Date.now() },
      ];

      const suggestion = suggestAlternativeStrategy('openhands', performance);

      expect(suggestion).not.toBeNull();
      expect(suggestion!.toolName).toBe('direct-patch');
      expect(suggestion!.confidence).toBe('high');
    });

    it('returns null when no good alternatives exist', () => {
      const performance = [
        { toolName: 'tool-a', route: 'route-a', totalAttempts: 2, successCount: 0, failureCount: 2, successRate: 0, lastUsed: Date.now() },
      ];

      const suggestion = suggestAlternativeStrategy('tool-a', performance);
      expect(suggestion).toBeNull();
    });
  });

  describe('hasSufficientHistory', () => {
    it('returns true for tools with enough data', () => {
      const performance = [
        { toolName: 'tool-a', route: 'route-a', totalAttempts: 5, successCount: 3, failureCount: 2, successRate: 0.6, lastUsed: Date.now() },
      ];

      expect(hasSufficientHistory('tool-a', performance, 3)).toBe(true);
      expect(hasSufficientHistory('tool-a', performance, 4)).toBe(true);
      expect(hasSufficientHistory('tool-a', performance, 6)).toBe(false);
    });

    it('returns false for unknown tools', () => {
      expect(hasSufficientHistory('unknown', [])).toBe(false);
    });
  });

  describe('formatSuggestionForChat', () => {
    it('formats high confidence suggestion', () => {
      const suggestion = {
        toolName: 'github_access',
        route: 'github-access',
        reason: 'GitHub operation detected',
        confidence: 'high' as const,
        basedOnAttempts: 5,
      };

      const formatted = formatSuggestionForChat(suggestion);
      expect(formatted).toContain('🟢');
      expect(formatted).toContain('github_access');
    });

    it('formats medium confidence suggestion', () => {
      const suggestion = {
        toolName: 'repo_loader',
        route: 'repo',
        reason: 'Repository access',
        confidence: 'medium' as const,
        basedOnAttempts: 3,
      };

      const formatted = formatSuggestionForChat(suggestion);
      expect(formatted).toContain('🟡');
    });
  });
});
