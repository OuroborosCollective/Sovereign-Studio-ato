/**
 * Risk Evidence Bundle
 *
 * Issue #1172: Combines multiple inference channel receipts
 *
 * Architecture:
 * - Receives receipts from multiple inference channels
 * - Validates all receipts have proper revision binding
 * - Computes aggregate score and conflict detection
 * - Provides causal verdict interface for post-action readback
 *
 * Key rule: No channel alone grants permission or creates VERIFIED state.
 *
 * @module predictive/inference/riskEvidenceBundle
 */

import type {
  ModelReceipt,
  RiskEvidenceBundle,
  RiskBundleValidation,
  CausalVerdict,
  InferenceSeverity,
  InferenceChannelResult,
} from './types';
import { computeReceiptHash, detectChannelConflicts, validateModelReceipt } from './types';
import { hashCanonical } from './hash';

/** Input for creating a risk evidence bundle */
export interface CreateBundleInput {
  channelReceipts: ModelReceipt[];
  traceId: string;
  preActionWindow: {
    startTimestamp: number;
    endTimestamp: number;
    signalCount: number;
  };
  currentRevision: string;
  maxReceiptAgeMs?: number;
}

/** Post-action verification input */
export interface PostActionVerification {
  bundleId: string;
  startTimestamp: number;
  endTimestamp: number;
  observedEffects: {
    effect: string;
    observed: boolean;
    magnitude?: number;
  }[];
  externalChangesDetected: boolean;
}

function computeBundleHash(
  bundle: Omit<RiskEvidenceBundle, 'bundleHash'> | RiskEvidenceBundle,
): string {
  const { bundleHash: _bundleHash, ...payload } = bundle as RiskEvidenceBundle;
  return hashCanonical(payload);
}

/** Compute aggregate score from channel receipts */
function computeAggregateScore(receipts: ModelReceipt[]): number {
  if (receipts.length === 0) return 0;

  const sum = receipts.reduce((acc, r) => acc + r.score, 0);
  return sum / receipts.length;
}

/** Get worst severity from receipts */
function getWorstSeverity(receipts: ModelReceipt[]): InferenceSeverity {
  const severityOrder: InferenceSeverity[] = ['info', 'warning', 'critical'];
  let worst = 0; // info

  for (const receipt of receipts) {
    // Critical has score 0, so we check abort reasons
    if (receipt.abortReason) {
      worst = Math.max(worst, 2); // critical
    } else if (receipt.knownLimitations.length > 2) {
      worst = Math.max(worst, 1); // warning
    }
  }

  return severityOrder[worst];
}

/** Compute pass rate across channels */
function computeChannelPassRate(receipts: ModelReceipt[]): number {
  if (receipts.length === 0) return 0;

  const passed = receipts.filter(
    receipt => receipt.abortReason === undefined && Number.isFinite(receipt.score) && receipt.score >= 0.5,
  ).length;

  return passed / receipts.length;
}

/**
 * Create a new Risk Evidence Bundle from channel receipts.
 */
export function createRiskEvidenceBundle(input: CreateBundleInput): RiskEvidenceBundle {
  const { channelReceipts, traceId, preActionWindow } = input;

  if (channelReceipts.length === 0) {
    throw new TypeError('Risk evidence bundle requires at least one channel receipt');
  }
  if (!traceId.trim()) {
    throw new TypeError('Risk evidence bundle requires a traceId');
  }
  if (
    !Number.isFinite(preActionWindow.startTimestamp) ||
    !Number.isFinite(preActionWindow.endTimestamp) ||
    preActionWindow.startTimestamp >= preActionWindow.endTimestamp ||
    !Number.isInteger(preActionWindow.signalCount) ||
    preActionWindow.signalCount <= 0
  ) {
    throw new TypeError('Risk evidence bundle requires a non-empty, ordered pre-action window');
  }

  const maxAge = input.maxReceiptAgeMs ?? 5 * 60 * 1000;
  const invalidReceipts = channelReceipts.filter(receipt => {
    const ageMs = Date.now() - receipt.createdAt;
    return (
      !validateModelReceipt(receipt).isValid ||
      receipt.revisionBinding.runtimeRevision !== input.currentRevision ||
      ageMs < 0 ||
      ageMs > maxAge
    );
  });
  if (invalidReceipts.length > 0) {
    throw new TypeError(
      `Risk evidence bundle rejected ${invalidReceipts.length} invalid or stale receipt(s)`,
    );
  }

  const bundleId = `bundle_${traceId}_${Date.now()}`;

  const bundle: Omit<RiskEvidenceBundle, 'bundleHash'> = {
    schemaVersion: 'risk-evidence-bundle.v1',
    bundleId,
    traceId,
    channelReceipts,
    preActionEvidenceWindow: preActionWindow,
    aggregateScore: computeAggregateScore(channelReceipts),
    worstSeverity: getWorstSeverity(channelReceipts),
    channelPassRate: computeChannelPassRate(channelReceipts),
    hasConflicts: detectChannelConflicts(channelReceipts),
    createdAt: Date.now(),
  };

  return {
    ...bundle,
    bundleHash: computeBundleHash(bundle),
  };
}

/**
 * Validate a risk evidence bundle.
 */
export function validateRiskBundle(
  bundle: RiskEvidenceBundle,
  currentRevision: string,
  maxReceiptAgeMs: number = 5 * 60 * 1000,
): RiskBundleValidation {
  const errors: string[] = [];
  const warnings: string[] = [];
  const staleReceipts: ModelReceipt[] = [];

  // Schema validation
  if (bundle.schemaVersion !== 'risk-evidence-bundle.v1') {
    errors.push(`Invalid schema version: ${bundle.schemaVersion}`);
  }

  if (!bundle.bundleId) {
    errors.push('Missing bundleId');
  }

  if (!bundle.traceId) {
    errors.push('Missing traceId');
  }

  // Channel receipt validation
  if (bundle.channelReceipts.length === 0) {
    errors.push('No channel receipts in bundle');
  }

  for (const receipt of bundle.channelReceipts) {
    const ageMs = Date.now() - receipt.createdAt;
    if (
      receipt.revisionBinding.runtimeRevision !== currentRevision ||
      ageMs < 0 ||
      ageMs > maxReceiptAgeMs
    ) {
      staleReceipts.push(receipt);
      errors.push(`Receipt ${receipt.receiptId} is stale or revision-mismatched`);
    }

    const receiptValidation = validateModelReceipt(receipt);
    if (!receiptValidation.isValid || computeReceiptHash(receipt) !== receipt.receiptHash) {
      errors.push(`Receipt ${receipt.receiptId} failed integrity validation`);
    }
  }

  try {
    if (computeBundleHash(bundle) !== bundle.bundleHash) {
      errors.push('Bundle hash mismatch');
    }
  } catch (error) {
    errors.push(`Bundle hashing failed: ${error instanceof Error ? error.message : String(error)}`);
  }

  // Pre-action window validation
  if (bundle.preActionEvidenceWindow.startTimestamp >= bundle.preActionEvidenceWindow.endTimestamp) {
    errors.push('Invalid pre-action window: start >= end');
  }

  if (bundle.preActionEvidenceWindow.signalCount === 0) {
    warnings.push('No signals in pre-action window');
  }

  return {
    isValid: errors.length === 0,
    errors,
    warnings,
    channelCount: bundle.channelReceipts.length,
    hasConflictingChannels: bundle.hasConflicts,
    staleReceipts,
  };
}

/**
 * Determine causal verdict from post-action verification.
 */
export function determineCausalVerdict(
  verification: PostActionVerification,
  bundle: RiskEvidenceBundle,
): { verdict: CausalVerdict; reason: string } {
  const { observedEffects, externalChangesDetected, startTimestamp, endTimestamp } = verification;

  if (verification.bundleId !== bundle.bundleId) {
    return {
      verdict: 'EFFECT_CONTRADICTED',
      reason: 'Post-action verification does not match the evidence bundle',
    };
  }

  // Check if we have enough post-window time
  const postWindowDuration = endTimestamp - startTimestamp;
  const preWindowDuration =
    bundle.preActionEvidenceWindow.endTimestamp -
    bundle.preActionEvidenceWindow.startTimestamp;

  if (postWindowDuration < preWindowDuration * 0.5) {
    return {
      verdict: 'INSUFFICIENT_POST_WINDOW',
      reason: `Post-action window (${postWindowDuration}ms) shorter than minimum expected (${preWindowDuration * 0.5}ms)`,
    };
  }

  // Check for external changes
  if (externalChangesDetected) {
    return {
      verdict: 'TARGET_CHANGED_EXTERNALLY',
      reason: 'External changes detected during post-action window; causality unclear',
    };
  }

  // Count observed vs expected effects
  const observedCount = observedEffects.filter(e => e.observed).length;
  const totalCount = observedEffects.length;

  if (totalCount === 0) {
    return {
      verdict: 'EFFECT_NOT_OBSERVED',
      reason: 'No effects were monitored in post-action window',
    };
  }

  const observationRate = observedCount / totalCount;

  // Determine verdict based on observation rate
  if (observationRate >= 0.8) {
    return {
      verdict: 'EFFECT_VERIFIED',
      reason: `${observedCount}/${totalCount} expected effects observed`,
    };
  } else if (observationRate >= 0.5) {
    return {
      verdict: 'EFFECT_NOT_OBSERVED',
      reason: `Only ${observedCount}/${totalCount} expected effects observed`,
    };
  } else {
    return {
      verdict: 'EFFECT_CONTRADICTED',
      reason: `Expected effects not observed: ${observedCount}/${totalCount}`,
    };
  }
}

/**
 * Update bundle with post-action verdict.
 * Returns a new bundle (immutable update).
 */
export function applyCausalVerdict(
  bundle: RiskEvidenceBundle,
  verification: PostActionVerification,
): RiskEvidenceBundle {
  const { verdict, reason } = determineCausalVerdict(verification, bundle);

  const updated: Omit<RiskEvidenceBundle, 'bundleHash'> = {
    ...bundle,
    postActionWindow: {
      startTimestamp: verification.startTimestamp,
      endTimestamp: verification.endTimestamp,
      verdict,
      verdictReason: reason,
    },
  };
  const { bundleHash: _previousHash, ...payload } = updated as RiskEvidenceBundle;
  return {
    ...payload,
    bundleHash: computeBundleHash(payload),
  };
}

/**
 * Create inference results from channel receipts.
 * Used to convert stored receipts back to runtime results.
 */
export function receiptsToChannelResults(
  receipts: ModelReceipt[],
): InferenceChannelResult[] {
  return receipts.map(receipt => ({
    id: receipt.receiptId,
    channelType: receipt.channelType,
    severity: receipt.abortReason ? 'critical' :
      receipt.score < 0.5 ? 'warning' : 'info',
    passed: !receipt.abortReason && receipt.score >= 0.5,
    score: receipt.score,
    reason: receipt.abortReason ?? `Channel ${receipt.channelType} passed`,
    timestamp: receipt.createdAt,
    traceId: receipt.revisionBinding.runtimeRevision,
    requiresLiveRevalidation: receipt.abortReason !== undefined,
    receipt,
    channelDetails: {
      modelClass: receipt.modelClass,
      implementationVersion: receipt.implementationVersion,
    },
  }));
}
