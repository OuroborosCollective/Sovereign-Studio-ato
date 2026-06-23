/**
 * Predictive Guard
 *
 * Active safety guard that uses predictive layer insights to:
 * - Block actions when prediction confidence is too low
 * - Warn users when error rates are high
 * - Route to safety checks based on learned patterns
 *
 * This is Phase 4: Active integration where the predictive layer
 * can actively influence decisions.
 *
 * @module predictive/predictiveGuard
 */

import type {
  Signal,
  Prediction,
  PredictionError,
  PredictiveLayerSnapshot,
  NeuralNode,
} from './types';

import { PredictiveLayer } from './predictiveLayer';

// ============================================================================
// Types
// ============================================================================

export interface SafetyContext {
  /** The action being evaluated */
  action: string;
  /** Node ID in the predictive network */
  nodeId: string;
  /** Additional context data */
  metadata?: Record<string, unknown>;
}

export interface SafetyCheckResult {
  /** Whether the action is safe to proceed */
  safe: boolean;
  /** Confidence level [0, 1] */
  confidence: number;
  /** Probability of success [0, 1] */
  successProbability: number;
  /** Risk level classification */
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
  /** Reason for the decision */
  reason: string;
  /** Suggested next action */
  suggestedAction: 'proceed' | 'warn' | 'block' | 'review';
  /** Relevant past patterns */
  similarPatterns: SimilarPattern[];
  /** Error history count */
  recentErrors: number;
  /** Trace ID for debugging */
  traceId: string;
}

export interface SimilarPattern {
  /** Pattern description */
  description: string;
  /** Outcome of that pattern */
  outcome: 'success' | 'failure' | 'unknown';
  /** How similar this pattern is [0, 1] */
  similarity: number;
  /** When this pattern was last seen */
  lastSeen: number;
}

export interface GuardThresholds {
  /** Block if confidence below this */
  blockConfidence: number;
  /** Warn if confidence below this */
  warnConfidence: number;
  /** Block if error rate above this */
  blockErrorRate: number;
  /** Warn if error rate above this */
  warnErrorRate: number;
  /** Minimum success probability to proceed */
  minSuccessProbability: number;
}

export interface PredictiveGuardConfig {
  /** Enable active blocking */
  blockingEnabled: boolean;
  /** Enable warnings */
  warningsEnabled: boolean;
  /** Thresholds for decisions */
  thresholds: GuardThresholds;
  /** Enable learning from decisions */
  learnFromDecisions: boolean;
  /** Maximum similar patterns to return */
  maxSimilarPatterns: number;
}

export interface DecisionOutcome {
  /** The action that was taken */
  action: string;
  /** The predicted outcome */
  predicted: 'success' | 'failure';
  /** The actual outcome */
  actual: 'success' | 'failure';
  /** Whether we blocked/warned/proceeded */
  guardDecision: 'blocked' | 'warned' | 'proceeded';
  /** Timestamp */
  timestamp: number;
}

// ============================================================================
// Default Configuration
// ============================================================================

export const DEFAULT_GUARD_THRESHOLDS: GuardThresholds = {
  blockConfidence: 0.3,      // Block if < 30% confident
  warnConfidence: 0.5,       // Warn if < 50% confident
  blockErrorRate: 0.2,       // Block if > 20% error rate
  warnErrorRate: 0.1,        // Warn if > 10% error rate
  minSuccessProbability: 0.7,  // Need > 70% success chance
};

export const DEFAULT_GUARD_CONFIG: PredictiveGuardConfig = {
  blockingEnabled: true,
  warningsEnabled: true,
  thresholds: DEFAULT_GUARD_THRESHOLDS,
  learnFromDecisions: true,
  maxSimilarPatterns: 5,
};

// ============================================================================
// Predictive Guard
// ============================================================================

let guardTraceSequence = 0;

function generateGuardTraceId(): string {
  guardTraceSequence = (guardTraceSequence + 1) % Number.MAX_SAFE_INTEGER;
  return `guard-${guardTraceSequence.toString(36).padStart(8, '0')}`;
}

/**
 * Active safety guard using predictive layer insights.
 */
export class PredictiveGuard {
  private predictiveLayer: PredictiveLayer;
  private config: PredictiveGuardConfig;
  private decisionHistory: DecisionOutcome[] = [];
  private learnedPatterns: Map<string, PatternInsight> = new Map();
  private maxHistory: number = 1000;

  constructor(
    predictiveLayer: PredictiveLayer,
    config: Partial<PredictiveGuardConfig> = {},
  ) {
    this.predictiveLayer = predictiveLayer;
    this.config = { ...DEFAULT_GUARD_CONFIG, ...config };
  }

  /**
   * Check if an action is safe to proceed.
   * This is the main entry point for active guard evaluation.
   */
  async checkSafety(context: SafetyContext): Promise<SafetyCheckResult> {
    const traceId = generateGuardTraceId();
    const startTime = performance.now();

    // 1. Get current layer state
    const snapshot = this.predictiveLayer.getSnapshot();

    // 2. Check error rate
    const errorRateCheck = this.checkErrorRate(snapshot);

    // 3. Find similar patterns
    const patterns = await this.findSimilarPatterns(context);

    // 4. Calculate success probability
    const successProbability = this.calculateSuccessProbability(
      context,
      snapshot,
      patterns,
    );

    // 5. Determine confidence
    const confidence = this.calculateConfidence(snapshot, patterns);

    // 6. Determine risk level
    const riskLevel = this.determineRiskLevel(
      confidence,
      successProbability,
      errorRateCheck,
    );

    // 7. Make decision
    const decision = this.makeDecision(
      riskLevel,
      confidence,
      successProbability,
      errorRateCheck,
    );

    // 8. Create result
    const result: SafetyCheckResult = {
      safe: decision !== 'block',
      confidence,
      successProbability,
      riskLevel,
      reason: this.buildReason(decision, context, confidence, successProbability),
      suggestedAction: decision,
      similarPatterns: patterns.slice(0, this.config.maxSimilarPatterns),
      recentErrors: snapshot.errorRate > 0 ? Math.round(snapshot.errorRate * 100) : 0,
      traceId,
    };

    return result;
  }

  /**
   * Check if error rate is within acceptable bounds.
   */
  private checkErrorRate(snapshot: PredictiveLayerSnapshot): {
    acceptable: boolean;
    rate: number;
    level: 'low' | 'medium' | 'high';
  } {
    const rate = snapshot.errorRate;

    if (rate <= this.config.thresholds.warnErrorRate) {
      return { acceptable: true, rate, level: 'low' };
    } else if (rate <= this.config.thresholds.blockErrorRate) {
      return { acceptable: true, rate, level: 'medium' };
    } else {
      return { acceptable: false, rate, level: 'high' };
    }
  }

  /**
   * Find similar patterns from history.
   */
  private async findSimilarPatterns(context: SafetyContext): Promise<SimilarPattern[]> {
    const patterns: SimilarPattern[] = [];

    // Look through decision history
    for (const decision of this.decisionHistory.slice(-100)) {
      if (decision.action === context.action) {
        patterns.push({
          description: `Previous ${decision.action}`,
          outcome: decision.actual,
          similarity: this.calculateSimilarity(context, decision),
          lastSeen: decision.timestamp,
        });
      }
    }

    // Sort by similarity descending
    patterns.sort((a, b) => b.similarity - a.similarity);

    return patterns;
  }

  /**
   * Calculate similarity between context and decision.
   */
  private calculateSimilarity(context: SafetyContext, decision: DecisionOutcome): number {
    let score = 0;
    let factors = 0;

    // Action match
    if (context.action === decision.action) {
      score += 0.6;
    }
    factors += 0.6;

    // Outcome recency
    const ageHours = (Date.now() - decision.timestamp) / (1000 * 60 * 60);
    if (ageHours < 1) score += 0.2;
    else if (ageHours < 24) score += 0.1;
    factors += 0.2;

    // Normalize
    return factors > 0 ? score / factors : 0;
  }

  /**
   * Calculate success probability based on patterns.
   */
  private calculateSuccessProbability(
    context: SafetyContext,
    snapshot: PredictiveLayerSnapshot,
    patterns: SimilarPattern[],
  ): number {
    // Base probability from prediction confidence
    let probability = snapshot.avgConfidence;

    // Adjust based on similar patterns
    const successPatterns = patterns.filter(p => p.outcome === 'success');
    const failurePatterns = patterns.filter(p => p.outcome === 'failure');

    if (successPatterns.length > 0) {
      const successRate = successPatterns.length / patterns.length;
      probability = probability * 0.7 + successRate * 0.3;
    }

    if (failurePatterns.length > 0) {
      const failureRate = failurePatterns.length / patterns.length;
      probability = probability * 0.8 - failureRate * 0.2;
    }

    // Adjust based on error rate
    probability = probability * (1 - snapshot.errorRate);

    return Math.max(0, Math.min(1, probability));
  }

  /**
   * Calculate overall confidence.
   */
  private calculateConfidence(
    snapshot: PredictiveLayerSnapshot,
    patterns: SimilarPattern[],
  ): number {
    // Start with layer confidence
    let confidence = snapshot.avgConfidence;

    // Boost for patterns
    if (patterns.length > 0) {
      confidence = confidence * 0.6 + 0.4 * (patterns.length / 10);
    }

    // Boost for established network
    if (snapshot.synapseCount > 50) {
      confidence = Math.min(1, confidence * 1.1);
    }

    return Math.max(0, Math.min(1, confidence));
  }

  /**
   * Determine risk level.
   */
  private determineRiskLevel(
    confidence: number,
    successProbability: number,
    errorRateCheck: ReturnType<PredictiveGuard['checkErrorRate']>,
  ): 'low' | 'medium' | 'high' | 'critical' {
    if (confidence < this.config.thresholds.blockConfidence ||
        successProbability < this.config.thresholds.minSuccessProbability ||
        errorRateCheck.level === 'high') {
      return 'critical';
    }

    if (confidence < this.config.thresholds.warnConfidence ||
        errorRateCheck.level === 'medium') {
      return 'high';
    }

    if (confidence < 0.7 || errorRateCheck.level === 'low') {
      return 'medium';
    }

    return 'low';
  }

  /**
   * Make guard decision based on risk level.
   */
  private makeDecision(
    riskLevel: 'low' | 'medium' | 'high' | 'critical',
    confidence: number,
    successProbability: number,
    errorRateCheck: ReturnType<PredictiveGuard['checkSafety'] extends Promise<infer R> ? never : never>,
  ): 'proceed' | 'warn' | 'block' | 'review' {
    if (!this.config.blockingEnabled) {
      return 'proceed';
    }

    switch (riskLevel) {
      case 'critical':
        return 'block';

      case 'high':
        if (!this.config.warningsEnabled) {
          return 'proceed';
        }
        return 'warn';

      case 'medium':
        return 'review';

      case 'low':
      default:
        return 'proceed';
    }
  }

  /**
   * Build human-readable reason for the decision.
   */
  private buildReason(
    decision: 'proceed' | 'warn' | 'block' | 'review',
    context: SafetyContext,
    confidence: number,
    successProbability: number,
  ): string {
    switch (decision) {
      case 'block':
        return `Blocked: Confidence (${(confidence * 100).toFixed(0)}%) below threshold. Success probability: ${(successProbability * 100).toFixed(0)}%`;

      case 'warn':
        return `Warning: Lower confidence (${(confidence * 100).toFixed(0)}%). Success probability: ${(successProbability * 100).toFixed(0)}%`;

      case 'review':
        return `Review recommended: Moderate confidence (${(confidence * 100).toFixed(0)}%). Consider verifying inputs.`;

      case 'proceed':
      default:
        return `Proceed: High confidence (${(confidence * 100).toFixed(0)}%). Success probability: ${(successProbability * 100).toFixed(0)}%`;
    }
  }

  /**
   * Record the outcome of a decision for learning.
   */
  recordOutcome(outcome: DecisionOutcome): void {
    if (!this.config.learnFromDecisions) return;

    this.decisionHistory.push(outcome);

    // Keep history bounded
    if (this.decisionHistory.length > this.maxHistory) {
      this.decisionHistory.shift();
    }

    // Update learned patterns
    const patternKey = `${outcome.action}`;
    const insight = this.learnedPatterns.get(patternKey) ?? {
      action: outcome.action,
      successCount: 0,
      failureCount: 0,
      lastOutcome: 'unknown',
    };

    if (outcome.actual === 'success') {
      insight.successCount++;
    } else {
      insight.failureCount++;
    }
    insight.lastOutcome = outcome.actual;

    this.learnedPatterns.set(patternKey, insight);
  }

  /**
   * Get statistics about guard decisions.
   */
  getStats(): {
    totalDecisions: number;
    blockedCount: number;
    warnedCount: number;
    proceededCount: number;
    accuracy: number;
    learnedActions: number;
  } {
    let blocked = 0, warned = 0, proceeded = 0;
    let correct = 0;

    for (const decision of this.decisionHistory) {
      switch (decision.guardDecision) {
        case 'blocked': blocked++; break;
        case 'warned': warned++; break;
        case 'proceeded': proceeded++; break;
      }

      if (decision.predicted === decision.actual) {
        correct++;
      }
    }

    return {
      totalDecisions: this.decisionHistory.length,
      blockedCount: blocked,
      warnedCount: warned,
      proceededCount: proceeded,
      accuracy: this.decisionHistory.length > 0
        ? correct / this.decisionHistory.length
        : 0,
      learnedActions: this.learnedPatterns.size,
    };
  }

  /**
   * Update guard configuration.
   */
  updateConfig(config: Partial<PredictiveGuardConfig>): void {
    this.config = { ...this.config, ...config };
  }

  /**
   * Get current configuration.
   */
  getConfig(): PredictiveGuardConfig {
    return { ...this.config };
  }

  /**
   * Reset guard state.
   */
  reset(): void {
    this.decisionHistory = [];
    this.learnedPatterns.clear();
  }
}

// ============================================================================
// Pattern Insight
// ============================================================================

interface PatternInsight {
  action: string;
  successCount: number;
  failureCount: number;
  lastOutcome: 'success' | 'failure' | 'unknown';
}

// ============================================================================
// Factory
// ============================================================================

/**
 * Create a predictive guard attached to a predictive layer.
 */
export function createPredictiveGuard(
  predictiveLayer: PredictiveLayer,
  config?: Partial<PredictiveGuardConfig>,
): PredictiveGuard {
  return new PredictiveGuard(predictiveLayer, config);
}
