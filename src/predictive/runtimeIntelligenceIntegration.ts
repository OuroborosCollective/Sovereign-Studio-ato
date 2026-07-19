/**
 * Predictive Guard Integration for RuntimeIntelligence
 *
 * Phase 4.3: Integrate with RuntimeIntelligence guards.
 * Predictive guards emit advisory runtime signals and conform to the shared
 * RuntimeGuardResult contract.
 *
 * @module predictive/runtimeIntelligenceIntegration
 */

import type { RuntimeContext, RuntimeGuardResult, Guard } from '../runtime/RuntimeIntelligence';
import type { PredictiveLayerSnapshot } from './types';
import { checkActionSafety, getSystemSafetyStatus } from './predictiveSafety';

export type PredictiveGuardAction = 'build' | 'publish';

export interface PredictiveRuntimeGuardOptions {
  action: string;
  nodeId: string;
  minConfidence?: number;
  getSnapshot?: () => PredictiveLayerSnapshot | null;
  warnOnly?: boolean;
}

function resolveTraceId(ctx: RuntimeContext & Record<string, unknown>, fallback: string): string {
  return typeof ctx.traceId === 'string' && ctx.traceId.length > 0 ? ctx.traceId : fallback;
}

export function createPredictiveRuntimeGuard(options: PredictiveRuntimeGuardOptions): Guard {
  const {
    action,
    nodeId,
    minConfidence = 0.3,
    warnOnly = false,
    getSnapshot,
  } = options;

  return {
    name: `predictive_${action}_guard`,
    check: async (_ctx: RuntimeContext & Record<string, unknown>): Promise<RuntimeGuardResult> => {
      const startTime = performance.now();
      const guardName = `predictive_${action}_guard`;
      const traceId = resolveTraceId(_ctx, `${guardName}:no-trace`);

      try {
        const snapshot = getSnapshot?.() ?? null;
        const safetyCheck = checkActionSafety(snapshot, action, nodeId);
        // Missing predictive evidence is neutral advisory state. It is neither
        // proof of safety nor sufficient reason to block a hard runtime action.
        const pass = warnOnly || !safetyCheck.evidenceAvailable || safetyCheck.confidence >= minConfidence;
        const reason = `Predictive guard: ${safetyCheck.reason} | Action: ${action} | Confidence: ${(safetyCheck.confidence * 100).toFixed(0)}%`;
        const duration = performance.now() - startTime;

        return {
          pass,
          guardName,
          traceId,
          reason,
          durationMs: duration,
          riskReduction: pass ? 0.2 : 0.5,
          properties: {
            confidence: safetyCheck.confidence,
            evidenceAvailable: safetyCheck.evidenceAvailable,
            safety: safetyCheck.safety,
            similarFailures: safetyCheck.similarFailures.length,
            warnOnly,
            minConfidence,
          },
        };
      } catch (error) {
        const duration = performance.now() - startTime;
        return {
          // Advisory guards may continue while exposing the error. Hard guards
          // fail closed when their own safety evaluation cannot run.
          pass: warnOnly,
          guardName,
          traceId,
          reason: `Predictive guard error: ${error instanceof Error ? error.message : String(error)}`,
          durationMs: duration,
          riskReduction: 0,
          remediation: 'Check predictive layer initialization before relying on this advisory signal.',
          properties: {
            evidenceAvailable: false,
            warnOnly,
            guardError: true,
          },
        };
      }
    },
  };
}

export function createBuildPredictiveGuard(getSnapshot?: () => PredictiveLayerSnapshot | null): Guard {
  return createPredictiveRuntimeGuard({
    action: 'build',
    nodeId: 'runtime.container.build',
    minConfidence: 0.25,
    warnOnly: true,
    getSnapshot,
  });
}

export function createPublishPredictiveGuard(getSnapshot?: () => PredictiveLayerSnapshot | null): Guard {
  return createPredictiveRuntimeGuard({
    action: 'publish',
    nodeId: 'runtime.container.publish',
    minConfidence: 0.5,
    warnOnly: false,
    getSnapshot,
  });
}

export function createDecisionPredictiveGuard(
  decisionType: string,
  getSnapshot?: () => PredictiveLayerSnapshot | null,
): Guard {
  return createPredictiveRuntimeGuard({
    action: decisionType,
    nodeId: `runtime.decision.${decisionType}`,
    minConfidence: 0.3,
    warnOnly: true,
    getSnapshot,
  });
}

export function createSystemHealthPredictiveGuard(getSnapshot?: () => PredictiveLayerSnapshot | null): Guard {
  return {
    name: 'predictive_system_health_guard',
    check: async (_ctx: RuntimeContext & Record<string, unknown>): Promise<RuntimeGuardResult> => {
      const startTime = performance.now();
      const guardName = 'predictive_system_health_guard';
      const traceId = resolveTraceId(_ctx, `${guardName}:no-trace`);

      try {
        const snapshot = getSnapshot?.() ?? null;
        const healthStatus = getSystemSafetyStatus(snapshot);
        const duration = performance.now() - startTime;

        return {
          pass: healthStatus.isHealthy,
          guardName,
          traceId,
          reason: `System health: ${healthStatus.message} | Confidence: ${(healthStatus.confidence * 100).toFixed(0)}%`,
          durationMs: duration,
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
          guardName,
          traceId,
          reason: `System health check error: ${error instanceof Error ? error.message : String(error)}`,
          durationMs: duration,
          riskReduction: 0,
          remediation: 'Check predictive layer health',
        };
      }
    },
  };
}

export function createPredictiveGuardChainForAction(
  action: PredictiveGuardAction,
  getSnapshot?: () => PredictiveLayerSnapshot | null,
): {
  preFlight: Guard[];
  main: Guard[];
  postFlight: Guard[];
} {
  return {
    preFlight: [createSystemHealthPredictiveGuard(getSnapshot)],
    main: [
      action === 'build'
        ? createBuildPredictiveGuard(getSnapshot)
        : createPublishPredictiveGuard(getSnapshot),
    ],
    postFlight: [],
  };
}

/**
 * Legacy aggregate chain retained for compatibility and diagnostics. Product
 * action paths must use createPredictiveGuardChainForAction so build and publish
 * evidence cannot be mixed.
 */
export function createPredictiveGuardChain(getSnapshot?: () => PredictiveLayerSnapshot | null): {
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
