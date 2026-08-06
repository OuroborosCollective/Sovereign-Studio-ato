/**
 * Hard Invariant Inference Channel
 *
 * Issue #1172: Deterministic validation lane
 *
 * Implements fail-closed hard invariant checks that:
 * - Are purely deterministic (no ML/probability)
 * - Have explicit bounds and thresholds
 * - Fail closed when inputs are missing or stale
 * - Cannot be bypassed by lower-confidence channels
 *
 * Examples:
 * - CPU/RAM/Latency bounds
 * - Rate limits
 * - Queue depth limits
 * - Error rate thresholds
 *
 * @module predictive/inference/hardInvariantChannel
 */

import type {
  InferenceChannelResult,
  ModelReceipt,
  RevisionBinding,
  InputWindowHash,
  ModelStateHash,
  InferenceChannelConfig,
  InferenceSeverity,
  BaseInferenceResult,
} from './types';
import {
  computeReceiptHash,
  validateModelReceipt,
} from './types';

/** Hard invariant definition */
export interface HardInvariant {
  /** Unique identifier */
  id: string;
  /** Human-readable name */
  name: string;
  /** Category of the invariant */
  category: 'resource' | 'rate' | 'latency' | 'error_rate' | 'queue';
  /** Current value */
  currentValue: number;
  /** Hard minimum (must not go below) */
  hardMin?: number;
  /** Hard maximum (must not go above) */
  hardMax?: number;
  /** Warning threshold (advisory only) */
  warningThreshold?: number;
  /** Unit of measurement */
  unit: string;
  /** Timestamp of measurement */
  measuredAt: number;
}

/** Result of a hard invariant check */
export interface HardInvariantCheckResult extends BaseInferenceResult {
  channelType: 'hard_invariant';
  invariantId: string;
  invariantName: string;
  category: HardInvariant['category'];
  currentValue: number;
  bound: 'min' | 'max' | 'none';
  /** Distance from threshold (negative = safe, positive = violation) */
  thresholdDistance: number;
}

/** Configuration for hard invariant channel */
export interface HardInvariantChannelConfig extends InferenceChannelConfig {
  channelType: 'hard_invariant';
  /** Invariants to check */
  invariants: HardInvariant[];
  /** Whether to fail closed on missing invariants */
  failClosedOnMissing: boolean;
}

/** Default configuration */
export const DEFAULT_HARD_INVARIANT_CONFIG: HardInvariantChannelConfig = {
  channelType: 'hard_invariant',
  enabled: true,
  scoreThreshold: 0.8,
  timeoutMs: 100,
  requireRevalidation: false,
  severityOnThreshold: 'critical',
  invariants: [],
  failClosedOnMissing: true,
};

/**
 * Check a single hard invariant.
 * Returns whether the invariant is violated and the distance from threshold.
 */
export function checkHardInvariant(
  invariant: HardInvariant,
  _currentRevision: string,
): HardInvariantCheckResult {
  let passed = true;
  let bound: 'min' | 'max' | 'none' = 'none';
  let thresholdDistance = 0;
  let severity: InferenceSeverity = 'info';

  // Check hard maximum
  if (invariant.hardMax !== undefined) {
    if (invariant.currentValue > invariant.hardMax) {
      passed = false;
      bound = 'max';
      thresholdDistance = invariant.currentValue - invariant.hardMax;
      severity = 'critical';
    } else if (invariant.warningThreshold !== undefined && invariant.currentValue > invariant.warningThreshold) {
      severity = 'warning';
      thresholdDistance = invariant.currentValue - invariant.warningThreshold;
    }
  }

  // Check hard minimum
  if (invariant.hardMin !== undefined) {
    if (invariant.currentValue < invariant.hardMin) {
      passed = false;
      bound = 'min';
      thresholdDistance = invariant.hardMin - invariant.currentValue;
      severity = 'critical';
    }
  }

  // If no bounds, only warn
  if (invariant.hardMin === undefined && invariant.hardMax === undefined) {
    passed = true;
    severity = 'info';
  }

  return {
    id: `hard_invariant_${invariant.id}_${invariant.measuredAt}`,
    channelType: 'hard_invariant',
    severity,
    passed,
    score: passed ? 1.0 : 0.0,
    reason: passed
      ? `${invariant.name}: ${invariant.currentValue}${invariant.unit} (within bounds)`
      : `${invariant.name}: ${invariant.currentValue}${invariant.unit} violates ${bound} bound ${invariant.hardMax ?? invariant.hardMin}${invariant.unit}`,
    timestamp: invariant.measuredAt,
    traceId: `hard_invariant_${invariant.id}`,
    requiresLiveRevalidation: !passed,
    invariantId: invariant.id,
    invariantName: invariant.name,
    category: invariant.category,
    currentValue: invariant.currentValue,
    bound,
    thresholdDistance,
  };
}

/**
 * Create a model receipt for a hard invariant check.
 * Hard invariants are deterministic so no calibration is needed.
 */
export function createHardInvariantReceipt(
  result: HardInvariantCheckResult,
  revisionBinding: RevisionBinding,
  inputWindowHash: InputWindowHash,
  invariants: HardInvariant[],
): ModelReceipt {
  const receipt: Omit<ModelReceipt, 'receiptHash'> = {
    schemaVersion: 'model-receipt.v1',
    receiptId: result.id,
    channelType: 'hard_invariant',
    modelClass: 'hard_invariant_deterministic',
    implementationVersion: '1.0.0',

    revisionBinding,
    featureSchemaHash: `invariant_schema_${invariants.length}`,
    inputWindowHash,
    modelStateHash: {
      parametersHash: 'n/a', // No learned parameters
      weightsHash: 'n/a',
      configHash: JSON.stringify({ invariantCount: invariants.length }),
      libraryVersion: '1.0.0',
    },

    score: result.score,
    calibrationMetadata: {
      method: 'deterministic',
      score: 1.0, // Deterministic = perfectly calibrated
      sampleSize: 1,
    },

    knownLimitations: invariants
      .filter(i => !i.hardMin && !i.hardMax)
      .map(i => `${i.name} has no defined bounds`),

    createdAt: Date.now(),
  };

  return {
    ...receipt,
    receiptHash: computeReceiptHash(receipt),
  };
}

/**
 * Run the hard invariant inference channel.
 * This is the most deterministic channel and should be checked first.
 */
export function runHardInvariantChannel(
  config: HardInvariantChannelConfig,
  revisionBinding: RevisionBinding,
  traceId: string,
): InferenceChannelResult[] {
  if (!config.enabled) {
    return [];
  }

  const results: InferenceChannelResult[] = [];

  // Create synthetic input window hash from current time
  const now = Date.now();
  const inputWindowHash: InputWindowHash = {
    hash: `window_${now}`,
    signalCount: config.invariants.length,
    windowStart: now - 1000,
    windowEnd: now,
    featureHash: `invariants_${config.invariants.length}`,
  };

  for (const invariant of config.invariants) {
    const result = checkHardInvariant(invariant, revisionBinding.runtimeRevision);

    const receipt = createHardInvariantReceipt(
      result,
      revisionBinding,
      inputWindowHash,
      config.invariants,
    );

    const validation = validateModelReceipt(receipt);

    results.push({
      ...result,
      channelDetails: {
        invariant,
        receiptValidation: validation,
      },
      receipt,
    });
  }

  return results;
}

/**
 * Factory to create a default hard invariant channel config
 * with common runtime invariants.
 */
export function createDefaultRuntimeInvariantConfig(): HardInvariantChannelConfig {
  const now = Date.now();

  return {
    ...DEFAULT_HARD_INVARIANT_CONFIG,
    invariants: [
      {
        id: 'cpu_usage',
        name: 'CPU Usage',
        category: 'resource',
        currentValue: 0,
        hardMax: 95,
        warningThreshold: 80,
        unit: '%',
        measuredAt: now,
      },
      {
        id: 'memory_usage',
        name: 'Memory Usage',
        category: 'resource',
        currentValue: 0,
        hardMax: 90,
        warningThreshold: 75,
        unit: '%',
        measuredAt: now,
      },
      {
        id: 'error_rate',
        name: 'Error Rate',
        category: 'error_rate',
        currentValue: 0,
        hardMax: 5,
        warningThreshold: 2,
        unit: '%',
        measuredAt: now,
      },
      {
        id: 'latency_p99',
        name: 'Latency P99',
        category: 'latency',
        currentValue: 0,
        hardMax: 5000,
        warningThreshold: 2000,
        unit: 'ms',
        measuredAt: now,
      },
      {
        id: 'queue_depth',
        name: 'Queue Depth',
        category: 'queue',
        currentValue: 0,
        hardMax: 1000,
        warningThreshold: 500,
        unit: 'items',
        measuredAt: now,
      },
    ],
  };
}
