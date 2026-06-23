/**
 * Predictive Guard Integration for RuntimeIntelligence
 *
 * Phase 4.3: Integrate with RuntimeIntelligence guards
 * Provides Guard-compatible functions that use the predictive layer.
 *
 * @module predictive/runtimeIntelligenceIntegration
 */

import type { RuntimeContext, RuntimeGuardResult, Guard } from '../runtime/RuntimeIntelligence';
import type { PredictiveLayerSnapshot } from './types';
import { checkActionSafety, checkBuildSafety, checkPublishSafety, getSystemSafetyStatus } from './predictiveSafety';

// ============================================================================
// Predictive Guard Factory
// ============================================================================

export interface PredictiveRuntimeGuardOptions {
  /** Action type to guard */
  action: string;
  /** Node ID in the predictive network */
  nodeId: string;
  /** Minimum confidence to pass (0-1) */
  minConfidence?: number;
  /** Custom snapshot provider */
  getSnapshot?: () => PredictiveLayerSnapshot | null;
  /** Enable warning instead of blocking for low confidence */
  warnOnly?: boolean;
}

/**
 * Create a Guard-compatible function that uses the predictive layer.
 */
export function createPredictiveRuntimeGuard(
  options: PredictiveRuntimeGuardOptions
): Guard {
  const {
    action,
    nodeId,
    minConfidence = 0.3,
    warnOnly = false,
    getSnapshot,
  } = options;

  return {
    name: `predictive_${action}_guard`,
    check: async (ctx: RuntimeContext & Record<string, unknown>): Promise<RuntimeGuardResult> => {
      const startTime = performance.now();

      try {
        // Get snapshot from predictive layer or use provided function
        const snapshot = getSnapshot?.() ?? null;

        // Perform safety check
        const safetyCheck = checkActionSafety(snapshot, action, nodeId);

        // Determine pass/fail based on confidence and warnOnly setting
        const pass = warnOnly || safetyCheck.confidence >= minConfidence;

        // Build reason
        const reason = `Predictive guard: ${safetyCheck.reason} | Action: ${action} | Confidence: ${(safetyCheck.confidence * 100).toFixed(0)}%`;

        const duration = performance.now() - startTime;

        return {
          pass,
          guardName: `predictive_${action}_guard`,
          reason,
          duration,
          riskReduction: pass ? 0.2 : 0.5,
          properties: {
            confidence: safetyCheck.confidence,
            safety: safetyCheck.safety,
            similarFailures: safetyCheck.similarFailures.length,
            warnOnly,
            minConfidence,
          },
        };
      } catch (error) {
        const duration = performance.now() - startTime;
        return {
          pass: !warnOnly, // Fail closed if error unless warnOnly
          guardName: `predictive_${action}_guard`,
          reason: `Predictive guard error: ${error instanceof Error ? error.message : String(error)}`,
          duration,
          riskReduction: 0,
          remediation: 'Check predictive layer initialization',
        };
      }
    },
  };
}

// ============================================================================
// Pre-built Guard Functions
// ============================================================================

/**
 * Guard for build operations.
 */
export function createBuildPredictiveGuard(
  getSnapshot?: () => PredictiveLayerSnapshot | null
): Guard {
  return createPredictiveRuntimeGuard({
    action: 'build',
    nodeId: 'runtime.container.build',
    minConfidence: 0.25,
    warnOnly: true,
    getSnapshot,
  });
}

/**
 * Guard for publish operations (higher safety requirements).
 */
export function createPublishPredictiveGuard(
  getSnapshot?: () => PredictiveLayerSnapshot | null
): Guard {
  return createPredictiveRuntimeGuard({
    action: 'publish',
    nodeId: 'runtime.container.publish',
    minConfidence: 0.5,
    warnOnly: false, // Block on low confidence for publish
    getSnapshot,
  });
}

/**
 * Guard for decision operations.
 */
export function createDecisionPredictiveGuard(
  decisionType: string,
  getSnapshot?: () => PredictiveLayerSnapshot | null
): Guard {
  return createPredictiveRuntimeGuard({
    action: decisionType,
    nodeId: `runtime.decision.${decisionType}`,
    minConfidence: 0.3,
    warnOnly: true,
    getSnapshot,
  });
}

// ============================================================================
// System Health Guard
// ============================================================================

/**
 * Guard that checks overall system health via predictive layer.
 */
export function createSystemHealthPredictiveGuard(
  getSnapshot?: () => PredictiveLayerSnapshot | null
): Guard {
  return {
    name: 'predictive_system_health_guard',
    check: async (ctx: RuntimeContext & Record<string, unknown>): Promise<RuntimeGuardResult> => {
      const startTime = performance.now();

      try {
        const snapshot = getSnapshot?.() ?? null;
        const healthStatus = getSystemSafetyStatus(snapshot);

        const duration = performance.now() - startTime;

        return {
          pass: healthStatus.isHealthy,
          guardName: 'predictive_system_health_guard',
          reason: `System health: ${healthStatus.message} | Confidence: ${(healthStatus.confidence * 100).toFixed(0)}%`,
          duration,
          riskReduction: healthStatus.isHealthy ? 0.1 : 0.4,
          properties: {
            healthStatus: healthStatus.status,
            confidence: healthStatus.confidence,
            errorRate: healthStatus.errorRate,
          },
        };
      } catch (error) {
        const duration = performance.now() - startTime;
        return {
          pass: false,
          guardName: 'predictive_system_health_guard',
          reason: `System health check error: ${error instanceof Error ? error.message : String(error)}`,
          duration,
          riskReduction: 0,
          remediation: 'Check predictive layer health',
        };
      }
    },
  };
}

// ============================================================================
// Guard Chain Helpers
// ============================================================================

/**
 * Create a full predictive guard chain.
 */
export function createPredictiveGuardChain(
  getSnapshot?: () => PredictiveLayerSnapshot | null
): {
  preFlight: Guard[];
  main: Guard[];
  postFlight: Guard[];
} {
  return {
    preFlight: [createSystemHealthPredictiveGuard(getSnapshot)],
    main: [
      createBuildPredictiveGuard(getSnapshot),
      createPublishPredictiveGuard(getSnapshot),
    ],
    postFlight: [],
  };
}
