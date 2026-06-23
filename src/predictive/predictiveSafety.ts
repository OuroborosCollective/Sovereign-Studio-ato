/**
 * Predictive Safety Check Functions
 *
 * Standalone safety check functions for use outside of React components.
 * These can be used in guard chains, runtime decisions, and non-UI contexts.
 *
 * @module predictive/predictiveSafety
 */

import type { Signal, Prediction, PredictionError, PredictiveLayerSnapshot } from './types';
import { LatentSpaceNavigator } from './latentSpace';
import { ErrorComputer } from './errorComputer';
import { HebbianAdaptor } from './hebbianAdaptor';
import { createPredictionGenerator } from './predictionGenerator';

// ============================================================================
// Safety Check Types
// ============================================================================

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

// ============================================================================
// Safety Thresholds
// ============================================================================

export const DEFAULT_SAFETY_THRESHOLDS = {
  /** Confidence below this is warning */
  warningConfidence: 0.5,
  /** Confidence below this is danger */
  dangerConfidence: 0.3,
  /** Confidence below this is critical */
  criticalConfidence: 0.15,
  /** Error rate above this is warning */
  warningErrorRate: 0.1,
  /** Error rate above this is danger */
  dangerErrorRate: 0.2,
  /** Error rate above this is critical */
  criticalErrorRate: 0.35,
  /** Block if less than this many similar patterns exist */
  minPatternCountForConfidence: 5,
} as const;

// ============================================================================
// Safety Check Functions
// ============================================================================

/**
 * Check if an action is safe to proceed based on predictive layer state.
 */
export function checkActionSafety(
  snapshot: PredictiveLayerSnapshot | null,
  action: string,
  nodeId: string,
  thresholds = DEFAULT_SAFETY_THRESHOLDS
): ActionSafetyCheck {
  // Default to safe if no snapshot
  if (!snapshot || snapshot.nodes.length === 0) {
    return {
      action,
      nodeId,
      safety: 'safe',
      confidence: 0.5,
      reason: 'No predictive data available - defaulting to safe',
      similarFailures: [],
      recommendation: 'proceed',
    };
  }

  // Find the relevant node
  const node = snapshot.nodes.find((n) => n.nodeId === nodeId);
  const confidence = node?.confidence ?? snapshot.avgConfidence ?? 0.5;
  const errorRate = snapshot.errorRate ?? 0;

  // Check similar failures
  const similarFailures = findSimilarFailures(snapshot, action);

  // Determine safety level
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

  // Build reason
  const reason = buildSafetyReason(safety, confidence, errorRate, similarFailures);

  return {
    action,
    nodeId,
    safety,
    confidence,
    reason,
    similarFailures,
    recommendation,
  };
}

/**
 * Find patterns of similar failures in the predictive layer.
 */
export function findSimilarFailures(
  snapshot: PredictiveLayerSnapshot,
  action: string,
  maxResults = 3
): SimilarFailure[] {
  const failures: SimilarFailure[] = [];

  // Look through recent errors for patterns
  for (const node of snapshot.nodes) {
    if (node.type === 'error' && node.metadata?.action === action) {
      failures.push({
        pattern: node.nodeId,
        frequency: node.signalCount,
        lastOccurrence: node.lastSignalTime,
        errorMessage: node.metadata?.error as string | undefined,
      });
    }
  }

  return failures.slice(0, maxResults);
}

/**
 * Build a human-readable safety reason.
 */
function buildSafetyReason(
  safety: SafetyLevel,
  confidence: number,
  errorRate: number,
  similarFailures: SimilarFailure[]
): string {
  const parts: string[] = [];

  switch (safety) {
    case 'critical':
      parts.push('Critical: Very low prediction confidence');
      break;
    case 'danger':
      parts.push('Danger: Low prediction confidence');
      break;
    case 'warning':
      parts.push('Warning: Below optimal confidence');
      break;
    case 'safe':
      parts.push('Safe: Predictions are reliable');
      break;
  }

  parts.push(`Confidence: ${(confidence * 100).toFixed(0)}%`);
  parts.push(`Error rate: ${(errorRate * 100).toFixed(1)}%`);

  if (similarFailures.length > 0) {
    parts.push(`Found ${similarFailures.length} similar failure patterns`);
  }

  return parts.join(' | ');
}

/**
 * Check if a build action is safe.
 */
export function checkBuildSafety(
  snapshot: PredictiveLayerSnapshot | null,
  context?: RuntimeSafetyContext
): ActionSafetyCheck {
  return checkActionSafety(
    snapshot,
    context?.operation ?? 'build',
    'runtime.container.build',
    DEFAULT_SAFETY_THRESHOLDS
  );
}

/**
 * Check if a publish action is safe.
 */
export function checkPublishSafety(
  snapshot: PredictiveLayerSnapshot | null,
  context?: RuntimeSafetyContext
): ActionSafetyCheck {
  const check = checkActionSafety(
    snapshot,
    context?.operation ?? 'publish',
    'runtime.container.publish',
    DEFAULT_SAFETY_THRESHOLDS
  );

  // Publish has higher safety requirements
  if (check.confidence < 0.6) {
    check.recommendation = check.recommendation === 'proceed' ? 'caution' : check.recommendation;
    if (check.recommendation === 'caution' && check.confidence < 0.4) {
      check.recommendation = 'block';
    }
  }

  return check;
}

/**
 * Check if a runtime decision is safe.
 */
export function checkDecisionSafety(
  snapshot: PredictiveLayerSnapshot | null,
  decisionType: string,
  context?: RuntimeSafetyContext
): ActionSafetyCheck {
  return checkActionSafety(
    snapshot,
    decisionType,
    `runtime.decision.${decisionType}`,
    DEFAULT_SAFETY_THRESHOLDS
  );
}

/**
 * Get overall system safety status.
 */
export function getSystemSafetyStatus(
  snapshot: PredictiveLayerSnapshot | null
): {
  status: SafetyLevel;
  confidence: number;
  errorRate: number;
  isHealthy: boolean;
  message: string;
} {
  if (!snapshot || snapshot.nodes.length === 0) {
    return {
      status: 'safe',
      confidence: 0.5,
      errorRate: 0,
      isHealthy: true,
      message: 'Predictive layer not initialized - assuming safe',
    };
  }

  const confidence = snapshot.avgConfidence ?? 0.5;
  const errorRate = snapshot.errorRate ?? 0;
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
    isHealthy = true;
  }

  let message = 'System operating normally';
  if (status === 'critical') {
    message = 'Critical safety concerns - immediate attention required';
  } else if (status === 'danger') {
    message = 'Safety warnings detected - proceed with caution';
  } else if (status === 'warning') {
    message = 'Minor concerns - monitoring recommended';
  }

  return {
    status,
    confidence,
    errorRate,
    isHealthy,
    message,
  };
}

// ============================================================================
// Guard Integration Helpers
// ============================================================================

/**
 * Create a runtime guard result from a safety check.
 */
export function safetyCheckToGuardResult(
  check: ActionSafetyCheck
): {
  pass: boolean;
  reason: string;
  remediation?: string;
} {
  return {
    pass: check.recommendation !== 'block',
    reason: check.reason,
    remediation:
      check.recommendation === 'block'
        ? `Action blocked due to ${check.safety} safety level. Confidence: ${(check.confidence * 100).toFixed(0)}%`
        : undefined,
  };
}

/**
 * Pre-flight safety check for guard chains.
 */
export async function predictiveGuardPreFlight(
  snapshot: PredictiveLayerSnapshot | null,
  context: RuntimeSafetyContext
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
