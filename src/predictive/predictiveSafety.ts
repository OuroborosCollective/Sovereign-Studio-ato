/**
 * Predictive Safety Check Functions
 *
 * Runtime safety helpers for predictive signals. Predictive output is advisory:
 * it may warn or block through guard chains, but it must never be treated as
 * proof that an action is safe.
 *
 * @module predictive/predictiveSafety
 */

import type { PredictiveLayerSnapshot } from './types';

export type SafetyLevel = 'safe' | 'warning' | 'danger' | 'critical';

export interface ActionSafetyCheck {
  action: string;
  nodeId: string;
  safety: SafetyLevel;
  confidence: number;
  reason: string;
  similarFailures: SimilarFailure[];
  recommendation: 'proceed' | 'caution' | 'block';
}

export interface SimilarFailure {
  pattern: string;
  frequency: number;
  lastOccurrence: number;
  errorMessage?: string;
}

export interface RuntimeSafetyContext {
  containerId?: string;
  operation: string;
  previousErrors?: number;
  userId?: string;
  sessionId?: string;
}

export const DEFAULT_SAFETY_THRESHOLDS = {
  warningConfidence: 0.5,
  dangerConfidence: 0.3,
  criticalConfidence: 0.15,
  warningErrorRate: 0.1,
  dangerErrorRate: 0.2,
  criticalErrorRate: 0.35,
  minPatternCountForConfidence: 5,
} as const;

function hasPredictiveEvidence(snapshot: PredictiveLayerSnapshot | null): snapshot is PredictiveLayerSnapshot {
  return Boolean(snapshot && snapshot.active && (snapshot.nodeCount > 0 || snapshot.patternCount > 0 || snapshot.synapseCount > 0));
}

export function checkActionSafety(
  snapshot: PredictiveLayerSnapshot | null,
  action: string,
  nodeId: string,
  thresholds = DEFAULT_SAFETY_THRESHOLDS,
): ActionSafetyCheck {
  if (!hasPredictiveEvidence(snapshot)) {
    return {
      action,
      nodeId,
      safety: 'warning',
      confidence: 0,
      reason: 'Predictive layer has no runtime evidence yet. This is a neutral advisory signal, not proof of safety.',
      similarFailures: [],
      recommendation: 'caution',
    };
  }

  const confidence = Number.isFinite(snapshot.avgConfidence) ? snapshot.avgConfidence : 0;
  const errorRate = Number.isFinite(snapshot.errorRate) ? snapshot.errorRate : 0;
  const similarFailures = findSimilarFailures(snapshot, action);

  let safety: SafetyLevel = 'safe';
  let recommendation: 'proceed' | 'caution' | 'block' = 'proceed';

  if (confidence < thresholds.criticalConfidence || errorRate > thresholds.criticalErrorRate) {
    safety = 'critical';
    recommendation = 'block';
  } else if (confidence < thresholds.dangerConfidence || errorRate > thresholds.dangerErrorRate) {
    safety = 'danger';
    recommendation = 'block';
  } else if (confidence < thresholds.warningConfidence || errorRate > thresholds.warningErrorRate) {
    safety = 'warning';
    recommendation = 'caution';
  }

  return {
    action,
    nodeId,
    safety,
    confidence,
    reason: buildSafetyReason(safety, confidence, errorRate, similarFailures, snapshot),
    similarFailures,
    recommendation,
  };
}

export function findSimilarFailures(
  snapshot: PredictiveLayerSnapshot,
  action: string,
  maxResults = 3,
): SimilarFailure[] {
  if (snapshot.errorRate <= 0) return [];

  return [{
    pattern: `${action}:runtime-error-rate`,
    frequency: Math.max(1, Math.round(snapshot.errorRate * Math.max(1, snapshot.nodeCount || snapshot.patternCount || 1) * 10)),
    lastOccurrence: snapshot.timestamp,
    errorMessage: `Predictive snapshot reports ${(snapshot.errorRate * 100).toFixed(1)}% error rate for current runtime state.`,
  }].slice(0, maxResults);
}

function buildSafetyReason(
  safety: SafetyLevel,
  confidence: number,
  errorRate: number,
  similarFailures: SimilarFailure[],
  snapshot: PredictiveLayerSnapshot,
): string {
  const parts: string[] = [];

  switch (safety) {
    case 'critical':
      parts.push('Critical: predictive runtime signal indicates very low confidence or high error rate');
      break;
    case 'danger':
      parts.push('Danger: predictive runtime signal indicates low confidence or elevated error rate');
      break;
    case 'warning':
      parts.push('Warning: predictive runtime signal is below preferred confidence');
      break;
    case 'safe':
      parts.push('Advisory clear: predictive signal has no blocking evidence; hard runtime guards still decide');
      break;
  }

  parts.push(`Confidence: ${(confidence * 100).toFixed(0)}%`);
  parts.push(`Error rate: ${(errorRate * 100).toFixed(1)}%`);
  parts.push(`Evidence: nodes=${snapshot.nodeCount}, patterns=${snapshot.patternCount}, synapses=${snapshot.synapseCount}`);

  if (similarFailures.length > 0) {
    parts.push(`Found ${similarFailures.length} similar failure signal(s)`);
  }

  return parts.join(' | ');
}

export function checkBuildSafety(
  snapshot: PredictiveLayerSnapshot | null,
  context?: RuntimeSafetyContext,
): ActionSafetyCheck {
  return checkActionSafety(snapshot, context?.operation ?? 'build', 'runtime.container.build', DEFAULT_SAFETY_THRESHOLDS);
}

export function checkPublishSafety(
  snapshot: PredictiveLayerSnapshot | null,
  context?: RuntimeSafetyContext,
): ActionSafetyCheck {
  const check = checkActionSafety(snapshot, context?.operation ?? 'publish', 'runtime.container.publish', DEFAULT_SAFETY_THRESHOLDS);

  if (check.confidence < 0.6) {
    check.recommendation = check.recommendation === 'proceed' ? 'caution' : check.recommendation;
    if (check.confidence < 0.4) check.recommendation = 'block';
  }

  return check;
}

export function checkDecisionSafety(
  snapshot: PredictiveLayerSnapshot | null,
  decisionType: string,
  context?: RuntimeSafetyContext,
): ActionSafetyCheck {
  return checkActionSafety(snapshot, context?.operation ?? decisionType, `runtime.decision.${decisionType}`, DEFAULT_SAFETY_THRESHOLDS);
}

export function getSystemSafetyStatus(
  snapshot: PredictiveLayerSnapshot | null,
): {
  status: SafetyLevel;
  confidence: number;
  errorRate: number;
  isHealthy: boolean;
  message: string;
} {
  if (!hasPredictiveEvidence(snapshot)) {
    return {
      status: 'warning',
      confidence: 0,
      errorRate: 0,
      isHealthy: true,
      message: 'Predictive layer has no runtime evidence yet; treating it as neutral advisory, not safety proof.',
    };
  }

  const confidence = snapshot.avgConfidence;
  const errorRate = snapshot.errorRate;
  const thresholds = DEFAULT_SAFETY_THRESHOLDS;

  let status: SafetyLevel = 'safe';
  let isHealthy = true;

  if (confidence < thresholds.criticalConfidence || errorRate > thresholds.criticalErrorRate) {
    status = 'critical';
    isHealthy = false;
  } else if (confidence < thresholds.dangerConfidence || errorRate > thresholds.dangerErrorRate) {
    status = 'danger';
    isHealthy = false;
  } else if (confidence < thresholds.warningConfidence || errorRate > thresholds.warningErrorRate) {
    status = 'warning';
  }

  const message = status === 'critical'
    ? 'Critical predictive signal - hard runtime guard review required'
    : status === 'danger'
      ? 'Danger predictive signal - proceed only if hard runtime guards pass'
      : status === 'warning'
        ? 'Predictive warning - monitoring recommended'
        : 'Predictive signal has no blocking evidence; hard runtime guards remain authoritative';

  return { status, confidence, errorRate, isHealthy, message };
}

export function safetyCheckToGuardResult(
  check: ActionSafetyCheck,
): {
  pass: boolean;
  reason: string;
  remediation?: string;
} {
  return {
    pass: check.recommendation !== 'block',
    reason: check.reason,
    remediation: check.recommendation === 'block'
      ? `Action blocked by predictive advisory guard. Safety=${check.safety}, confidence=${(check.confidence * 100).toFixed(0)}%. Verify hard runtime checks and recent telemetry.`
      : undefined,
  };
}

export async function predictiveGuardPreFlight(
  snapshot: PredictiveLayerSnapshot | null,
  _context: RuntimeSafetyContext,
): Promise<{ pass: boolean; reason: string; remediation?: string }> {
  const check = getSystemSafetyStatus(snapshot);

  if (!check.isHealthy) {
    return {
      pass: false,
      reason: check.message,
      remediation: `System safety: ${check.status}. Confidence: ${(check.confidence * 100).toFixed(0)}%. Error rate: ${(check.errorRate * 100).toFixed(1)}%`,
    };
  }

  return {
    pass: true,
    reason: check.message,
  };
}
