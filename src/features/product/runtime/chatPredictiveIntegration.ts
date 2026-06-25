/**
 * Chat Predictive Integration
 * 
 * Connects the chat interface with the predictive layer for intelligent
 * suggestions based on learned patterns and runtime intelligence.
 */

import type { PredictiveLayerSnapshot } from '../../predictive/types';
import type { SolutionPatternStore } from './solutionPatternMemory';
import type { Suggestion } from '../types';
import { latentSpaceSearch, createLatentSpace } from '../../predictive/latentSpace';

/**
 * Configuration for chat predictive integration
 */
export interface ChatPredictiveConfig {
  /** Minimum similarity score (0-1) for pattern matches */
  minSimilarity?: number;
  /** Maximum number of suggestions to return */
  maxSuggestions?: number;
  /** Include pattern-based suggestions */
  includePatterns?: boolean;
  /** Include predictive safety suggestions */
  includeSafety?: boolean;
}

const DEFAULT_CONFIG: Required<ChatPredictiveConfig> = {
  minSimilarity: 0.3,
  maxSuggestions: 4,
  includePatterns: true,
  includeSafety: true,
};

/**
 * Derive predictive suggestions from chat input
 */
export function derivePredictiveSuggestions(
  input: string,
  predictiveSnapshot: PredictiveLayerSnapshot | null,
  patternStore: SolutionPatternStore | null,
  config: ChatPredictiveConfig = {}
): Suggestion[] {
  const opts = { ...DEFAULT_CONFIG, ...config };
  const suggestions: Suggestion[] = [];

  if (!input.trim()) return suggestions;

  // Pattern-based suggestions from learned patterns
  if (opts.includePatterns && patternStore && patternStore.patterns.length > 0) {
    const latentSpace = createLatentSpace(64);
    
    // Index existing patterns
    for (const pattern of patternStore.patterns) {
      latentSpace.addPattern({
        id: pattern.id,
        pattern: pattern.name,
        embedding: pattern.embedding || generateSimpleEmbedding(pattern.name),
        metadata: pattern,
      });
    }

    // Search for similar patterns
    const queryEmbedding = generateSimpleEmbedding(input);
    const results = latentSpace.search(queryEmbedding, opts.maxSuggestions);

    for (const result of results) {
      if (result.score >= opts.minSimilarity) {
        const pattern = result.pattern.metadata;
        suggestions.push({
          id: `pattern-${pattern.id}`,
          type: 'improvement',
          title: pattern.name || 'Learned Pattern',
          description: `Based on: ${pattern.action || pattern.name}`,
          priority: result.score > 0.7 ? 'high' : result.score > 0.5 ? 'medium' : 'low',
        });
      }
    }
  }

  // Predictive safety suggestions
  if (opts.includeSafety && predictiveSnapshot) {
    const systemHealth = predictiveSnapshot.systemHealth;
    
    if (systemHealth.status === 'degraded') {
      suggestions.push({
        id: 'safety-degraded',
        type: 'error',
        title: 'System verlangsamt',
        description: 'Einige Systeme reagieren verzögert. Geduld empfohlen.',
        priority: 'medium',
      });
    }
    
    if (systemHealth.status === 'error') {
      suggestions.push({
        id: 'safety-error',
        type: 'error',
        title: 'Systemprobleme erkannt',
        description: 'Warte auf Stabilisierung oder prüfe die Logs.',
        priority: 'high',
      });
    }

    // Recent failures
    if (predictiveSnapshot.recentFailures.length > 0) {
      const lastFailure = predictiveSnapshot.recentFailures[0];
      suggestions.push({
        id: 'safety-failure-hint',
        type: 'error',
        title: 'Letzte Fehlerquelle',
        description: `Ähnliche Fehler vermeiden: ${lastFailure.action}`,
        priority: 'medium',
      });
    }
  }

  // Action-specific suggestions based on input
  const inputLower = input.toLowerCase();
  
  if (inputLower.includes('build') || inputLower.includes('bauen') || inputLower.includes('feature')) {
    suggestions.push({
      id: 'action-build',
      type: 'feature',
      title: 'Feature mit Tests',
      description: 'Baue mit passenden Unit-Tests und Validierung.',
      priority: 'medium',
    });
  }

  if (inputLower.includes('fix') || inputLower.includes('bug') || inputLower.includes('fehler')) {
    suggestions.push({
      id: 'action-fix',
      type: 'error',
      title: 'Fehler reproduzieren',
      description: 'Prüfe zuerst den Fehler und erstelle einen minimalen Fix.',
      priority: 'high',
    });
  }

  if (inputLower.includes('pr') || inputLower.includes('pull') || inputLower.includes('publish')) {
    suggestions.push({
      id: 'action-pr',
      type: 'improvement',
      title: 'Draft PR erstellen',
      description: 'Nur als Draft PR publishen, niemals direkt auf main.',
      priority: 'high',
    });
  }

  if (inputLower.includes('test') || inputLower.includes('prüfen')) {
    suggestions.push({
      id: 'action-test',
      type: 'improvement',
      title: 'Tests zuerst',
      description: 'Validiere mit echten Tests, keine Mocks im Live-Pfad.',
      priority: 'medium',
    });
  }

  // Deduplicate by title and limit
  const seen = new Set<string>();
  const deduplicated = suggestions.filter(s => {
    const key = s.title.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  return deduplicated.slice(0, opts.maxSuggestions);
}

/**
 * Generate a simple embedding from text
 * Uses a deterministic hash-based approach
 */
function generateSimpleEmbedding(text: string, dimension: number = 64): number[] {
  const embedding: number[] = [];
  for (let i = 0; i < dimension; i++) {
    // Simple hash-based value
    const char = text.charCodeAt(i % text.length);
    const offset = Math.sin(char * (i + 1)) * 0.5 + 0.5;
    embedding.push(offset);
  }
  return embedding;
}

/**
 * Get chat context for predictive analysis
 */
export interface ChatPredictiveContext {
  hasRepo: boolean;
  hasOpenHands: boolean;
  hasPatterns: boolean;
  isBusy: boolean;
  recentErrors: number;
}

export function deriveChatPredictiveContext(
  predictiveSnapshot: PredictiveLayerSnapshot | null,
  patternStore: SolutionPatternStore | null,
  runtimeState: { repoReady: boolean; openhandsReady: boolean; runtimeBusy: boolean }
): ChatPredictiveContext {
  return {
    hasRepo: runtimeState.repoReady,
    hasOpenHands: runtimeState.openhandsReady,
    hasPatterns: Boolean(patternStore && patternStore.patterns.length > 0),
    isBusy: runtimeState.runtimeBusy,
    recentErrors: predictiveSnapshot?.recentFailures.length || 0,
  };
}
