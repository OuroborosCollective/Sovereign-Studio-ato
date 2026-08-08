/**
 * Predictive Inference Layer - Core Type Definitions
 *
 * Issue #1172: Predictive Inference and Wolfram Validation
 *
 * Architecture:
 * - Multiple inference channels (hard invariant, time series, anomaly, dependency graph)
 * - Each channel produces a Model Receipt with full revision/source binding
 * - Risk Evidence Bundle combines channel outputs
 * - Deterministic validation lane for fail-closed behavior
 *
 * Key contracts:
 * - No inference channel alone can grant permission or transition
 * - SUCCEEDED_UNVERIFIED until independent causal readback
 * - Stale revision/model triggers fail-closed behavior
 *
 * @module predictive/inference/types
 */

import { hashCanonical } from './hash';

const SHA256_PATTERN = /^[0-9a-f]{64}$/i;
const GIT_REVISION_PATTERN = /^[0-9a-f]{40}$/i;

// ============================================================================
// Revision and Hash Binding
// ============================================================================

/** Binding for runtime revision identification */
export interface RevisionBinding {
  /** Git commit SHA or equivalent */
  runtimeRevision: string;
  /** Config revision identifier */
  configRevision: string;
  /** Feature schema version */
  schemaVersion: string;
  /** Timestamp of binding */
  boundAt: number;
}

/** Hash of input data window for reproducibility */
export interface InputWindowHash {
  /** SHA-256 hash of the input window */
  hash: string;
  /** Number of signals in window */
  signalCount: number;
  /** Start timestamp of window */
  windowStart: number;
  /** End timestamp of window */
  windowEnd: number;
  /** Feature vector hash */
  featureHash: string;
}

/** Hash of model state for reproducibility */
export interface ModelStateHash {
  /** Full model parameters hash */
  parametersHash: string;
  /** Weights snapshot hash (mutable weights are versioned) */
  weightsHash: string;
  /** Configuration hash */
  configHash: string;
  /** Library/framework version */
  libraryVersion: string;
}

// ============================================================================
// Inference Channels
// ============================================================================

/** Classification of inference channel types */
export type InferenceChannelType =
  | 'hard_invariant'      // Deterministic bounds and limits
  | 'time_series'         // Resource/latency forecasting
  | 'anomaly_detection'    // Baseline deviation detection
  | 'predictive_coding'    // Top-down prediction + error
  | 'scann_matching'       // Similarity-based incident matching
  | 'dependency_graph';    // Graph propagation over runtime edges

/** Severity levels for inference signals */
export type InferenceSeverity = 'info' | 'warning' | 'critical';

/** Inference result without channel-specific details */
export interface BaseInferenceResult {
  /** Unique identifier */
  id: string;
  /** Channel that produced this result */
  channelType: InferenceChannelType;
  /** Severity level */
  severity: InferenceSeverity;
  /** Whether the inference passed its threshold */
  passed: boolean;
  /** Score or probability [0, 1] */
  score: number;
  /** Human-readable reason */
  reason: string;
  /** Timestamp of inference */
  timestamp: number;
  /** Trace context */
  traceId: string;
  /** Whether live revalidation is recommended */
  requiresLiveRevalidation: boolean;
}

// ============================================================================
// Model Receipt
// ============================================================================

/**
 * Complete binding for a single inference run.
 * Every inference channel must produce one of these.
 */
export interface ModelReceipt {
  /** Schema version for this receipt */
  schemaVersion: 'model-receipt.v1';
  /** Unique identifier for this inference run */
  receiptId: string;
  /** Inference channel that produced this */
  channelType: InferenceChannelType;
  /** Model class identifier */
  modelClass: string;
  /** Implementation/library version */
  implementationVersion: string;

  // Binding fields
  revisionBinding: RevisionBinding;
  featureSchemaHash: string;
  inputWindowHash: InputWindowHash;
  modelStateHash: ModelStateHash;

  // Inference parameters
  predictionHorizonMs?: number;
  score: number;
  calibrationMetadata?: {
    /** Calibration method used */
    method: string;
    /** Calibration score */
    score: number;
    /** Sample size used for calibration */
    sampleSize: number;
  };

  // Constraints and limits
  knownLimitations: string[];
  /** Why inference was aborted (if applicable) */
  abortReason?: string;

  // ScaNN-specific if used
  scannManifestHash?: string;
  scannCandidateHashes?: string[];

  // Wolfram-specific if used
  wolframVersion?: string;
  wolframKernelMode?: string;
  wolframExpressionHash?: string;
  wolframResultHash?: string;

  // Provenance
  createdAt: number;
  /** Receipt hash for integrity */
  receiptHash: string;
}

/** Validation result for a model receipt */
export interface ModelReceiptValidation {
  isValid: boolean;
  errors: string[];
  warnings: string[];
  bindingAgeMs: number;
}

// ============================================================================
// Risk Evidence Bundle
// ============================================================================

/** Result of causal readback verification */
export type CausalVerdict =
  | 'EFFECT_VERIFIED'           // Expected effect confirmed
  | 'EFFECT_NOT_OBSERVED'        // Effect not seen
  | 'EFFECT_CONTRADICTED'        // Contradictory evidence
  | 'TARGET_CHANGED_EXTERNALLY'  // External change detected
  | 'INSUFFICIENT_POST_WINDOW'   // Not enough time for verification
  | 'ROLLBACK_REQUIRED';         // Compensation needed

/**
 * Risk Evidence Bundle combining multiple inference channels.
 * This is the canonical output for the deterministic validation lane.
 */
export interface RiskEvidenceBundle {
  /** Schema version */
  schemaVersion: 'risk-evidence-bundle.v1';
  /** Unique identifier */
  bundleId: string;
  /** Trace context for correlation */
  traceId: string;

  // Channel receipts
  channelReceipts: ModelReceipt[];

  // Pre-action evidence window
  preActionEvidenceWindow: {
    startTimestamp: number;
    endTimestamp: number;
    signalCount: number;
  };

  // Aggregate assessment
  aggregateScore: number;
  /** Worst-case severity across channels */
  worstSeverity: InferenceSeverity;
  /** Fraction of channels that passed [0, 1] */
  channelPassRate: number;
  /** Whether channels had conflicting assessments */
  hasConflicts: boolean;

  // Post-action verification (filled after causal readback)
  postActionWindow?: {
    startTimestamp: number;
    endTimestamp: number;
    verdict: CausalVerdict;
    verdictReason: string;
  };

  // Metadata
  createdAt: number;
  bundleHash: string;
}

/** Validation for a risk evidence bundle */
export interface RiskBundleValidation {
  isValid: boolean;
  errors: string[];
  warnings: string[];
  channelCount: number;
  hasConflictingChannels: boolean;
  staleReceipts: ModelReceipt[];
}

// ============================================================================
// Inference Channel Configuration
// ============================================================================

/** Configuration for an inference channel */
export interface InferenceChannelConfig {
  /** Channel type */
  channelType: InferenceChannelType;
  /** Whether channel is enabled */
  enabled: boolean;
  /** Minimum score to consider channel result */
  scoreThreshold: number;
  /** Maximum inference time in ms */
  timeoutMs: number;
  /** Whether to require live revalidation */
  requireRevalidation: boolean;
  /** Expected severity if threshold exceeded */
  severityOnThreshold: InferenceSeverity;
}

/** Result of running an inference channel */
export interface InferenceChannelResult extends BaseInferenceResult {
  /** Channel that produced this */
  channelType: InferenceChannelType;
  /** The model receipt for this channel */
  receipt: ModelReceipt;
  /** Any channel-specific details */
  channelDetails: Record<string, unknown>;
}

// ============================================================================
// Validation Helpers
// ============================================================================

/** Check if a receipt is stale based on revision */
export function isReceiptStale(
  receipt: ModelReceipt,
  currentRevision: string,
  maxAgeMs: number = 5 * 60 * 1000 // 5 minutes default
): boolean {
  const ageMs = Date.now() - receipt.createdAt;
  return (
    receipt.revisionBinding.runtimeRevision !== currentRevision ||
    ageMs > maxAgeMs
  );
}

/** Validate a model receipt and its revision/integrity bindings. */
export function validateModelReceipt(receipt: unknown): ModelReceiptValidation {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (typeof receipt !== 'object' || receipt === null || Array.isArray(receipt)) {
    return { isValid: false, errors: ['Receipt is not an object'], warnings: [], bindingAgeMs: 0 };
  }

  const r = receipt as Partial<ModelReceipt>;

  if (r.schemaVersion !== 'model-receipt.v1') errors.push('Invalid schemaVersion');
  if (!r.receiptId) errors.push('Missing receiptId');
  if (!r.channelType) errors.push('Missing channelType');
  if (!r.modelClass) errors.push('Missing modelClass');
  if (!r.implementationVersion) errors.push('Missing implementationVersion');

  if (!r.revisionBinding) {
    errors.push('Missing revisionBinding');
  } else {
    if (!GIT_REVISION_PATTERN.test(r.revisionBinding.runtimeRevision)) {
      errors.push('runtimeRevision must be a full Git SHA');
    }
    if (!r.revisionBinding.configRevision) errors.push('Missing configRevision');
    if (!r.revisionBinding.schemaVersion) errors.push('Missing revision schemaVersion');
    if (!Number.isFinite(r.revisionBinding.boundAt)) errors.push('Invalid revision boundAt');
  }

  if (!SHA256_PATTERN.test(r.featureSchemaHash ?? '')) {
    errors.push('featureSchemaHash must be SHA-256');
  }

  if (!r.inputWindowHash) {
    errors.push('Missing inputWindowHash');
  } else {
    if (!SHA256_PATTERN.test(r.inputWindowHash.hash)) {
      errors.push('inputWindowHash.hash must be SHA-256');
    }
    if (!SHA256_PATTERN.test(r.inputWindowHash.featureHash)) {
      errors.push('inputWindowHash.featureHash must be SHA-256');
    }
    if (!Number.isInteger(r.inputWindowHash.signalCount) || r.inputWindowHash.signalCount < 0) {
      errors.push('Invalid inputWindowHash.signalCount');
    }
    if (
      !Number.isFinite(r.inputWindowHash.windowStart) ||
      !Number.isFinite(r.inputWindowHash.windowEnd) ||
      r.inputWindowHash.windowStart > r.inputWindowHash.windowEnd
    ) {
      errors.push('Invalid input window timestamps');
    }
  }

  if (!r.modelStateHash) {
    errors.push('Missing modelStateHash');
  } else {
    for (const [label, value] of Object.entries({
      parametersHash: r.modelStateHash.parametersHash,
      weightsHash: r.modelStateHash.weightsHash,
      configHash: r.modelStateHash.configHash,
    })) {
      if (!SHA256_PATTERN.test(value)) errors.push(`${label} must be SHA-256`);
    }
    if (!r.modelStateHash.libraryVersion) errors.push('Missing model libraryVersion');
  }

  if (!Number.isFinite(r.score) || (r.score ?? -1) < 0 || (r.score ?? 2) > 1) {
    errors.push('score must be finite and within [0, 1]');
  }
  if (!Array.isArray(r.knownLimitations)) errors.push('Missing knownLimitations');
  if (!r.calibrationMetadata) warnings.push('No calibration metadata');

  if (!Number.isFinite(r.createdAt) || (r.createdAt ?? 0) <= 0) {
    errors.push('Invalid createdAt');
  }

  if (!SHA256_PATTERN.test(r.receiptHash ?? '')) {
    errors.push('receiptHash must be SHA-256');
  } else {
    try {
      if (computeReceiptHash(r as ModelReceipt) !== r.receiptHash) {
        errors.push('Receipt hash mismatch');
      }
    } catch (error) {
      errors.push(`Receipt hashing failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  const bindingAgeMs = Number.isFinite(r.createdAt) ? Date.now() - (r.createdAt as number) : 0;

  return {
    isValid: errors.length === 0,
    errors,
    warnings,
    bindingAgeMs,
  };
}

/** Compute canonical SHA-256 over every receipt field except the digest itself. */
export function computeReceiptHash(
  receipt: Omit<ModelReceipt, 'receiptHash'> | ModelReceipt,
): string {
  const { receiptHash: _receiptHash, ...payload } = receipt as ModelReceipt;
  return hashCanonical(payload);
}

/** Check whether receipt pass/fail outcomes materially disagree. */
export function detectChannelConflicts(receipts: ModelReceipt[]): boolean {
  if (receipts.length < 2) return false;

  const passedCount = receipts.filter(
    receipt => receipt.abortReason === undefined && Number.isFinite(receipt.score) && receipt.score >= 0.5,
  ).length;
  const passRate = passedCount / receipts.length;

  return passRate > 0.2 && passRate < 0.8;
}
