/**
 * Predictive Guard
 *
 * Advisory safety guard backed by predictive runtime signals. It can warn or
 * block inside guard chains, but hard runtime checks remain authoritative.
 *
 * @module predictive/predictiveGuard
 */

import type { PredictiveLayerSnapshot } from './types';
import { PredictiveLayer } from './predictiveLayer';

export interface SafetyContext {
  action: string;
  nodeId: string;
  metadata?: Record<string, unknown>;
}

export interface SafetyCheckResult {
  safe: boolean;
  confidence: number;
  successProbability: number;
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
  reason: string;
  suggestedAction: 'proceed' | 'warn' | 'block' | 'review';
  similarPatterns: SimilarPattern[];
  recentErrors: number;
  traceId: string;
}

export interface SimilarPattern {
  description: string;
  outcome: 'success' | 'failure' | 'unknown';
  similarity: number;
  lastSeen: number;
}

export interface GuardThresholds {
  blockConfidence: number;
  warnConfidence: number;
  blockErrorRate: number;
  warnErrorRate: number;
  minSuccessProbability: number;
}

export interface PredictiveGuardConfig {
  blockingEnabled: boolean;
  warningsEnabled: boolean;
  thresholds: GuardThresholds;
  learnFromDecisions: boolean;
  maxSimilarPatterns: number;
}

export interface DecisionOutcome {
  action: string;
  predicted: 'success' | 'failure';
  actual: 'success' | 'failure';
  guardDecision: 'blocked' | 'warned' | 'proceeded';
  timestamp: number;
}

export const DEFAULT_GUARD_THRESHOLDS: GuardThresholds = {
  blockConfidence: 0.3,
  warnConfidence: 0.5,
  blockErrorRate: 0.2,
  warnErrorRate: 0.1,
  minSuccessProbability: 0.7,
};

export const DEFAULT_GUARD_CONFIG: PredictiveGuardConfig = {
  blockingEnabled: true,
  warningsEnabled: true,
  thresholds: DEFAULT_GUARD_THRESHOLDS,
  learnFromDecisions: true,
  maxSimilarPatterns: 5,
};

let guardTraceSequence = 0;

function generateGuardTraceId(): string {
  guardTraceSequence = (guardTraceSequence + 1) % Number.MAX_SAFE_INTEGER;
  return `guard-${guardTraceSequence.toString(36).padStart(8, '0')}`;
}

type ErrorRateCheck = {
  acceptable: boolean;
  rate: number;
  level: 'low' | 'medium' | 'high';
};

interface PatternInsight {
  action: string;
  successCount: number;
  failureCount: number;
  lastOutcome: 'success' | 'failure' | 'unknown';
}

function hasPredictiveEvidence(snapshot: PredictiveLayerSnapshot): boolean {
  return snapshot.active && (snapshot.nodeCount > 0 || snapshot.patternCount > 0 || snapshot.synapseCount > 0);
}

export class PredictiveGuard {
  private predictiveLayer: PredictiveLayer;
  private config: PredictiveGuardConfig;
  private decisionHistory: DecisionOutcome[] = [];
  private learnedPatterns: Map<string, PatternInsight> = new Map();
  private maxHistory = 1000;

  constructor(
    predictiveLayer: PredictiveLayer,
    config: Partial<PredictiveGuardConfig> = {},
  ) {
    this.predictiveLayer = predictiveLayer;
    this.config = {
      ...DEFAULT_GUARD_CONFIG,
      ...config,
      thresholds: {
        ...DEFAULT_GUARD_CONFIG.thresholds,
        ...(config.thresholds ?? {}),
      },
    };
  }

  async checkSafety(context: SafetyContext): Promise<SafetyCheckResult> {
    const traceId = generateGuardTraceId();
    const snapshot = this.predictiveLayer.getSnapshot();

    if (!hasPredictiveEvidence(snapshot)) {
      return {
        safe: true,
        confidence: 0,
        successProbability: 0,
        riskLevel: 'medium',
        reason: 'Predictive guard has no runtime evidence yet. This is neutral advisory state, not proof of safety.',
        suggestedAction: 'review',
        similarPatterns: [],
        recentErrors: 0,
        traceId,
      };
    }

    const errorRateCheck = this.checkErrorRate(snapshot);
    const patterns = await this.findSimilarPatterns(context);
    const successProbability = this.calculateSuccessProbability(snapshot, patterns);
    const confidence = this.calculateConfidence(snapshot, patterns);
    const riskLevel = this.determineRiskLevel(confidence, successProbability, errorRateCheck);
    const decision = this.makeDecision(riskLevel, confidence, successProbability, errorRateCheck);

    return {
      safe: decision !== 'block',
      confidence,
      successProbability,
      riskLevel,
      reason: this.buildReason(decision, confidence, successProbability, errorRateCheck),
      suggestedAction: decision,
      similarPatterns: patterns.slice(0, this.config.maxSimilarPatterns),
      recentErrors: snapshot.errorRate > 0 ? Math.round(snapshot.errorRate * 100) : 0,
      traceId,
    };
  }

  private checkErrorRate(snapshot: PredictiveLayerSnapshot): ErrorRateCheck {
    const rate = Number.isFinite(snapshot.errorRate) ? snapshot.errorRate : 0;

    if (rate <= this.config.thresholds.warnErrorRate) return { acceptable: true, rate, level: 'low' };
    if (rate <= this.config.thresholds.blockErrorRate) return { acceptable: true, rate, level: 'medium' };
    return { acceptable: false, rate, level: 'high' };
  }

  private async findSimilarPatterns(context: SafetyContext): Promise<SimilarPattern[]> {
    const patterns: SimilarPattern[] = [];

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

    patterns.sort((a, b) => b.similarity - a.similarity);
    return patterns;
  }

  private calculateSimilarity(context: SafetyContext, decision: DecisionOutcome): number {
    let score = 0;
    let factors = 0;

    if (context.action === decision.action) score += 0.6;
    factors += 0.6;

    const ageHours = (Date.now() - decision.timestamp) / (1000 * 60 * 60);
    if (ageHours < 1) score += 0.2;
    else if (ageHours < 24) score += 0.1;
    factors += 0.2;

    return factors > 0 ? score / factors : 0;
  }

  private calculateSuccessProbability(snapshot: PredictiveLayerSnapshot, patterns: SimilarPattern[]): number {
    let probability = Math.max(0, Math.min(1, snapshot.avgConfidence));
    const successPatterns = patterns.filter((pattern) => pattern.outcome === 'success');
    const failurePatterns = patterns.filter((pattern) => pattern.outcome === 'failure');

    if (successPatterns.length > 0) {
      const successRate = successPatterns.length / patterns.length;
      probability = probability * 0.7 + successRate * 0.3;
    }

    if (failurePatterns.length > 0) {
      const failureRate = failurePatterns.length / patterns.length;
      probability = probability * 0.8 - failureRate * 0.2;
    }

    probability *= 1 - Math.max(0, Math.min(1, snapshot.errorRate));
    return Math.max(0, Math.min(1, probability));
  }

  private calculateConfidence(snapshot: PredictiveLayerSnapshot, patterns: SimilarPattern[]): number {
    let confidence = Math.max(0, Math.min(1, snapshot.avgConfidence));

    if (patterns.length > 0) {
      confidence = confidence * 0.6 + 0.4 * Math.min(1, patterns.length / 10);
    }

    if (snapshot.synapseCount > 50) {
      confidence = Math.min(1, confidence * 1.1);
    }

    return Math.max(0, Math.min(1, confidence));
  }

  private determineRiskLevel(
    confidence: number,
    successProbability: number,
    errorRateCheck: ErrorRateCheck,
  ): 'low' | 'medium' | 'high' | 'critical' {
    if (
      confidence < this.config.thresholds.blockConfidence ||
      successProbability < this.config.thresholds.minSuccessProbability ||
      errorRateCheck.level === 'high'
    ) {
      return 'critical';
    }

    if (confidence < this.config.thresholds.warnConfidence || errorRateCheck.level === 'medium') {
      return 'high';
    }

    if (confidence < 0.7) return 'medium';
    return 'low';
  }

  private makeDecision(
    riskLevel: 'low' | 'medium' | 'high' | 'critical',
    _confidence: number,
    _successProbability: number,
    _errorRateCheck: ErrorRateCheck,
  ): 'proceed' | 'warn' | 'block' | 'review' {
    if (!this.config.blockingEnabled) return 'proceed';

    switch (riskLevel) {
      case 'critical':
        return 'block';
      case 'high':
        return this.config.warningsEnabled ? 'warn' : 'proceed';
      case 'medium':
        return 'review';
      case 'low':
      default:
        return 'proceed';
    }
  }

  private buildReason(
    decision: 'proceed' | 'warn' | 'block' | 'review',
    confidence: number,
    successProbability: number,
    errorRateCheck: ErrorRateCheck,
  ): string {
    const base = `confidence=${(confidence * 100).toFixed(0)}%, success=${(successProbability * 100).toFixed(0)}%, error=${(errorRateCheck.rate * 100).toFixed(1)}%`;

    switch (decision) {
      case 'block':
        return `Blocked by predictive advisory guard: ${base}. Hard runtime checks must confirm before retry.`;
      case 'warn':
        return `Predictive warning: ${base}. Continue only after runtime verification.`;
      case 'review':
        return `Predictive review recommended: ${base}. This is not a success signal.`;
      case 'proceed':
      default:
        return `Predictive signal has no blocking evidence: ${base}. Hard runtime guards remain authoritative.`;
    }
  }

  recordOutcome(outcome: DecisionOutcome): void {
    if (!this.config.learnFromDecisions) return;

    this.decisionHistory.push(outcome);
    if (this.decisionHistory.length > this.maxHistory) this.decisionHistory.shift();

    const patternKey = outcome.action;
    const insight = this.learnedPatterns.get(patternKey) ?? {
      action: outcome.action,
      successCount: 0,
      failureCount: 0,
      lastOutcome: 'unknown' as const,
    };

    if (outcome.actual === 'success') insight.successCount += 1;
    else insight.failureCount += 1;
    insight.lastOutcome = outcome.actual;

    this.learnedPatterns.set(patternKey, insight);
  }

  async reportDecisionOutcome(outcome: DecisionOutcome): Promise<void> {
    this.recordOutcome(outcome);
  }

  getStats(): {
    totalDecisions: number;
    blockedCount: number;
    warnedCount: number;
    proceededCount: number;
    accuracy: number;
    learnedActions: number;
  } {
    let blocked = 0;
    let warned = 0;
    let proceeded = 0;
    let correct = 0;

    for (const decision of this.decisionHistory) {
      switch (decision.guardDecision) {
        case 'blocked': blocked += 1; break;
        case 'warned': warned += 1; break;
        case 'proceeded': proceeded += 1; break;
      }

      if (decision.predicted === decision.actual) correct += 1;
    }

    return {
      totalDecisions: this.decisionHistory.length,
      blockedCount: blocked,
      warnedCount: warned,
      proceededCount: proceeded,
      accuracy: this.decisionHistory.length > 0 ? correct / this.decisionHistory.length : 0,
      learnedActions: this.learnedPatterns.size,
    };
  }

  updateConfig(config: Partial<PredictiveGuardConfig>): void {
    this.config = {
      ...this.config,
      ...config,
      thresholds: {
        ...this.config.thresholds,
        ...(config.thresholds ?? {}),
      },
    };
  }

  getConfig(): PredictiveGuardConfig {
    return {
      ...this.config,
      thresholds: { ...this.config.thresholds },
    };
  }

  reset(): void {
    this.decisionHistory = [];
    this.learnedPatterns.clear();
  }
}

export function createPredictiveGuard(
  predictiveLayer: PredictiveLayer,
  config?: Partial<PredictiveGuardConfig>,
): PredictiveGuard {
  return new PredictiveGuard(predictiveLayer, config);
}
