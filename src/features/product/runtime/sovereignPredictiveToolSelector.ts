/**
 * Sovereign Predictive Tool Selector
 *
 * Uses latent space patterns and learning history to suggest optimal tools.
 * Rule: Never claims guaranteed success. All suggestions are advisory.
 *
 * @module sovereignPredictiveToolSelector
 */

import type { ContainerDecisionLearningSignal, LearningOutcome } from './containerDecisionLearning';

/**
 * Tool performance record from learning history
 */
export interface ToolPerformance {
  readonly toolName: string;
  readonly route: string;
  readonly totalAttempts: number;
  readonly successCount: number;
  readonly failureCount: number;
  readonly successRate: number;
  readonly lastUsed: number;
}

/**
 * Tool suggestion with confidence indicator
 */
export interface ToolSuggestion {
  readonly toolName: string;
  readonly route: string;
  readonly reason: string;
  readonly confidence: 'high' | 'medium' | 'low';
  readonly basedOnAttempts: number;
}

/**
 * Analyzes learning history to extract tool performance
 */
export function analyzeToolPerformance(
  signals: readonly ContainerDecisionLearningSignal[],
): ToolPerformance[] {
  const toolStats = new Map<string, {
    toolName: string;
    route: string;
    successes: number;
    failures: number;
    lastUsed: number;
  }>();

  for (const signal of signals) {
    // Extract tool name from ruleId (format: "tool:toolname")
    if (!signal.ruleId.startsWith('tool:')) continue;

    const route = signal.learnTag;
    const existing = toolStats.get(route);

    if (existing) {
      if (signal.outcome === 'success') existing.successes++;
      else if (signal.outcome === 'failure') existing.failures++;
      existing.lastUsed = Math.max(existing.lastUsed, signal.timestamp);
    } else {
      toolStats.set(route, {
        toolName: route,
        route,
        successes: signal.outcome === 'success' ? 1 : 0,
        failures: signal.outcome === 'failure' ? 1 : 0,
        lastUsed: signal.timestamp,
      });
    }
  }

  return Array.from(toolStats.values())
    .map((stats) => ({
      toolName: stats.toolName,
      route: stats.route,
      totalAttempts: stats.successes + stats.failures,
      successCount: stats.successes,
      failureCount: stats.failures,
      successRate: (stats.successes + stats.failures) > 0
        ? stats.successes / (stats.successes + stats.failures)
        : 0,
      lastUsed: stats.lastUsed,
    }))
    .sort((a, b) => b.successRate - a.successRate);
}

/**
 * Gets the best performing tools from history
 */
export function getBestPerformingTools(
  performance: readonly ToolPerformance[],
  limit = 3,
): ToolPerformance[] {
  return performance
    .filter((t) => t.totalAttempts >= 2) // Only consider tools with enough data
    .slice(0, limit);
}

/**
 * Determines confidence level based on sample size
 */
function getConfidenceLevel(totalAttempts: number): 'high' | 'medium' | 'low' {
  if (totalAttempts >= 5) return 'high';
  if (totalAttempts >= 3) return 'medium';
  return 'low';
}

/**
 * Generates tool suggestions based on request context
 */
export function generateToolSuggestions(
  request: string,
  performance: readonly ToolPerformance[],
): readonly ToolSuggestion[] {
  const suggestions: ToolSuggestion[] = [];
  const requestLower = request.toLowerCase();

  // Find tools that have been successful for similar requests
  const bestTools = getBestPerformingTools(performance);

  for (const tool of bestTools) {
    if (tool.successRate < 0.5) continue; // Skip tools with poor track record

    let reason = '';
    const confidence = getConfidenceLevel(tool.totalAttempts);

    // Context-based reasoning
    if (requestLower.includes('github') || requestLower.includes('pr') || requestLower.includes('merge')) {
      if (tool.toolName.includes('github')) {
        reason = 'GitHub-Operation erkannt - سابقاً erfolgreich';
      }
    }

    if (requestLower.includes('patch') || requestLower.includes('diff') || requestLower.includes('code')) {
      if (tool.toolName.includes('patch') || tool.toolName.includes('direct')) {
        reason = 'Code-Änderung erkannt - سابقاً erfolgreich';
      }
    }

    if (requestLower.includes('repo') || requestLower.includes('repository') || requestLower.includes('codebase')) {
      if (tool.toolName.includes('repo')) {
        reason = 'Repository-Zugriff erkannt';
      }
    }

    if (!reason) {
      reason = `Historisch erfolgreich (${tool.successRate.toFixed(0)}% bei ${tool.totalAttempts} Versuchen)`;
    }

    suggestions.push({
      toolName: tool.toolName,
      route: tool.route,
      reason,
      confidence,
      basedOnAttempts: tool.totalAttempts,
    });
  }

  return suggestions;
}

/**
 * Suggests alternative strategy when current tool is stuck
 */
export function suggestAlternativeStrategy(
  stuckTool: string,
  performance: readonly ToolPerformance[],
): ToolSuggestion | null {
  // Find tools that worked when this tool failed
  const alternatives = performance.filter(
    (t) => t.toolName !== stuckTool && t.successRate > 0.5,
  );

  if (alternatives.length === 0) return null;

  // Suggest the best alternative
  const best = alternatives[0];
  return {
    toolName: best.toolName,
    route: best.route,
    reason: `Alternative nach ${stuckTool}-Blocker`,
    confidence: getConfidenceLevel(best.totalAttempts),
    basedOnAttempts: best.totalAttempts,
  };
}

/**
 * Checks if a tool has sufficient history to be confident
 */
export function hasSufficientHistory(
  toolName: string,
  performance: readonly ToolPerformance[],
  minAttempts = 3,
): boolean {
  const tool = performance.find((t) => t.toolName === toolName);
  return tool ? tool.totalAttempts >= minAttempts : false;
}

/**
 * Formats a suggestion for chat display
 */
export function formatSuggestionForChat(suggestion: ToolSuggestion): string {
  const confIcon = suggestion.confidence === 'high' ? '🟢' : suggestion.confidence === 'medium' ? '🟡' : '⚪';
  return `${confIcon} ${suggestion.toolName}: ${suggestion.reason}`;
}
