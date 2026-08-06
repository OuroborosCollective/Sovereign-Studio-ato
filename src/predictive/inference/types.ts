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

/** Validate a model receipt has required fields */
export function validateModelReceipt(receipt: unknown): ModelReceiptValidation {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (typeof receipt !== 'object' || receipt === null) {
    return { isValid: false, errors: ['Receipt is not an object'], warnings: [], bindingAgeMs: 0 };
  }

  const r = receipt as Partial<ModelReceipt>;

  // Required fields
  if (!r.schemaVersion) errors.push('Missing schemaVersion');
  if (!r.receiptId) errors.push('Missing receiptId');
  if (!r.channelType) errors.push('Missing channelType');
  if (!r.revisionBinding) errors.push('Missing revisionBinding');
  if (!r.inputWindowHash) errors.push('Missing inputWindowHash');
  if (!r.modelStateHash) errors.push('Missing modelStateHash');

  // Warnings for potentially weak receipts
  if (r.score === undefined) warnings.push('Missing score');
  if (!r.calibrationMetadata) warnings.push('No calibration metadata');
  if (r.knownLimitations && r.knownLimitations.length === 0) {
    warnings.push('No documented limitations');
  }

  const bindingAgeMs = r.createdAt ? Date.now() - r.createdAt : 0;

  return {
    isValid: errors.length === 0,
    errors,
    warnings,
    bindingAgeMs,
  };
}

/** Compute deterministic hash of a receipt for integrity */
export function computeReceiptHash(receipt: Omit<ModelReceipt, 'receiptHash'>): string {
  const normalized = JSON.stringify({
    schemaVersion: receipt.schemaVersion,
    receiptId: receipt.receiptId,
    channelType: receipt.channelType,
    modelClass: receipt.modelClass,
    revisionBinding: receipt.revisionBinding,
    featureSchemaHash: receipt.featureSchemaHash,
    inputWindowHash: receipt.inputWindowHash,
    modelStateHash: receipt.modelStateHash,
    score: receipt.score,
    createdAt: receipt.createdAt,
  });

  // Simple hash for demo - production should use crypto.subtle.digest
  let hash = 0;
  for (let i = 0; i < normalized.length; i++) {
    const char = normalized.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return `receipt_${Math.abs(hash).toString(16).padStart(8, '0')}`;
}

/** Check if channels have conflicting assessments */
export function detectChannelConflicts(receipts: ModelReceipt[]): boolean {
  if (receipts.length < 2) return false;

  const passedCount = receipts.filter(r => r.knownLimitations.length === 0 || r.abortReason === undefined).length;
  const passRate = passedCount / receipts.length;

  // Significant conflict if pass rate is between 20% and 80%
  return passRate > 0.2 && passRate < 0.8;
}
