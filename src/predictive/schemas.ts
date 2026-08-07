/**
 * Predictive Coding Layer - Strict Schema Definitions
 *
 * Runtime-validated schemas for all predictive layer contracts.
 * These schemas enforce strict field validation at runtime, binding
 * every signal, prediction, and action to verifiable properties.
 *
 * Design constraints from Issue #1168:
 * - Each schema binds: schema version, source revision, hash chain
 * - Guards must check ALL required fields, not just partial
 * - No parallel interface plus diverging schema
 *
 * Schema versions:
 * - runtime-signal.v1: Micro-signal emitted when runtime state changes
 * - prediction-result.v1: Top-down prediction with confidence
 * - prediction-error.v1: Error computed as difference between actual/predicted
 * - runtime-action-receipt.v1: Receipt for an action taken
 * - bounded-action-plan.v1: Plan for bounded action execution
 *
 * @module predictive/schemas
 */

// ============================================================================
// Schema Version Constants
// ============================================================================

export const SCHEMA_VERSIONS = {
  RUNTIME_SIGNAL: 'runtime-signal.v1',
  PREDICTION_RESULT: 'prediction-result.v1',
  PREDICTION_ERROR: 'prediction-error.v1',
  RUNTIME_ACTION_RECEIPT: 'runtime-action-receipt.v1',
  BOUNDED_ACTION_PLAN: 'bounded-action-plan.v1',
  PREDICTIVE_SNAPSHOT: 'predictive-snapshot.v1',
  RUNTIME_READBACK: 'runtime-readback.v1',
  RISK_EVIDENCE_BUNDLE: 'risk-evidence-bundle.v1',
} as const;

export type SchemaVersion = typeof SCHEMA_VERSIONS[keyof typeof SCHEMA_VERSIONS];

// ============================================================================
// Validation Limits
// ============================================================================

const LIMITS = {
  MAX_ID_LENGTH: 128,
  MAX_NODE_LENGTH: 256,
  MAX_TRACE_LENGTH: 128,
  MAX_REASON_LENGTH: 1024,
  MIN_TIMESTAMP: 1_000_000_000_000, // After year 2001
  MAX_TIMESTAMP: 9_000_000_000_000, // Before year 2250
  MIN_CONFIDENCE: 0,
  MAX_CONFIDENCE: 1,
  MIN_WEIGHT: 0,
  MAX_WEIGHT: 1,
  MAX_HASH_LENGTH: 128,
  MAX_REVISION_LENGTH: 40,
  MAX_EMBEDDING_DIM: 16384,
} as const;

// ============================================================================
// Validation Helpers
// ============================================================================

/** Validates a string field is non-empty and within length bounds */
function validateString(
  value: unknown,
  fieldName: string,
  minLength = 1,
  maxLength?: number
): string {
  if (typeof value !== 'string') {
    throw new TypeError(`${fieldName} must be a string`);
  }
  if (value.length < minLength) {
    throw new RangeError(`${fieldName} must be at least ${minLength} characters`);
  }
  if (maxLength !== undefined && value.length > maxLength) {
    throw new RangeError(`${fieldName} must be at most ${maxLength} characters`);
  }
  return value;
}

/** Validates a number is finite and within bounds */
function validateNumber(
  value: unknown,
  fieldName: string,
  min?: number,
  max?: number
): number {
  if (typeof value !== 'number') {
    throw new TypeError(`${fieldName} must be a number`);
  }
  if (!Number.isFinite(value)) {
    throw new TypeError(`${fieldName} must be finite`);
  }
  if (min !== undefined && value < min) {
    throw new RangeError(`${fieldName} must be at least ${min}`);
  }
  if (max !== undefined && value > max) {
    throw new RangeError(`${fieldName} must be at most ${max}`);
  }
  return value;
}

/** Validates an array with element validation */
function validateArray<T>(
  value: unknown,
  fieldName: string,
  elementValidator: (item: unknown, index: number) => T,
  minLength = 0,
  maxLength?: number
): T[] {
  if (!Array.isArray(value)) {
    throw new TypeError(`${fieldName} must be an array`);
  }
  if (value.length < minLength) {
    throw new RangeError(`${fieldName} must have at least ${minLength} elements`);
  }
  if (maxLength !== undefined && value.length > maxLength) {
    throw new RangeError(`${fieldName} must have at most ${maxLength} elements`);
  }
  return value.map((item, index) => elementValidator(item, index));
}

/** Validates a SHA-256 hash (64 hex characters) */
function validateSha256(value: unknown, fieldName: string): string {
  const str = validateString(value, fieldName, 64, 64);
  if (!/^[0-9a-f]{64}$/.test(str)) {
    throw new RangeError(`${fieldName} must be a valid SHA-256 hex string`);
  }
  return str;
}

/** Validates a Git revision hash (40 hex characters) */
function validateGitSha(value: unknown, fieldName: string): string {
  const str = validateString(value, fieldName, 40, 40);
  if (!/^[0-9a-f]{40}$/.test(str)) {
    throw new RangeError(`${fieldName} must be a valid Git SHA-1 hex string`);
  }
  return str;
}

/** Validates an object with specific key requirements */
function validateObject(
  value: unknown,
  fieldName: string
): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new TypeError(`${fieldName} must be a non-null object`);
  }
  return value as Record<string, unknown>;
}

// ============================================================================
// Schema: Runtime Signal
// ============================================================================

export interface RuntimeSignalSchema {
  schemaVersion: typeof SCHEMA_VERSIONS.RUNTIME_SIGNAL;
  id: string;
  node: string;
  value: number;
  timestamp: number;
  traceId: string;
  sourceRevision?: string;
  signalHash?: string;
  metadata?: Record<string, unknown>;
}

/**
 * Validates and parses a runtime signal.
 * Throws on validation failure.
 * Note: schemaVersion is optional for backward compatibility.
 */
export function validateRuntimeSignal(data: unknown): RuntimeSignalSchema {
  const obj = validateObject(data, 'runtime-signal');

  const result: RuntimeSignalSchema = {
    schemaVersion: SCHEMA_VERSIONS.RUNTIME_SIGNAL,
    id: validateString(obj.id, 'id', 1, LIMITS.MAX_ID_LENGTH),
    node: validateString(obj.node, 'node', 1, LIMITS.MAX_NODE_LENGTH),
    value: validateNumber(obj.value, 'value'),
    timestamp: validateNumber(
      obj.timestamp,
      'timestamp',
      LIMITS.MIN_TIMESTAMP,
      LIMITS.MAX_TIMESTAMP
    ),
    traceId: validateString(obj.traceId, 'traceId', 1, LIMITS.MAX_TRACE_LENGTH),
  };

  if (obj.sourceRevision !== undefined) {
    result.sourceRevision = validateGitSha(obj.sourceRevision, 'sourceRevision');
  }

  if (obj.signalHash !== undefined) {
    result.signalHash = validateSha256(obj.signalHash, 'signalHash');
  }

  if (obj.metadata !== undefined) {
    result.metadata = validateObject(obj.metadata, 'metadata');
  }

  return result;
}

/**
 * Type guard for runtime signals.
 * Returns true if the object is a valid runtime signal.
 */
export function isValidRuntimeSignal(data: unknown): data is RuntimeSignalSchema {
  try {
    validateRuntimeSignal(data);
    return true;
  } catch {
    return false;
  }
}

// ============================================================================
// Schema: Prediction Result
// ============================================================================

export interface PredictionResultSchema {
  schemaVersion: typeof SCHEMA_VERSIONS.PREDICTION_RESULT;
  id: string;
  predictedValue: number;
  confidence: number;
  node: string;
  timestamp: number;
  traceId: string;
  sourceRevision?: string;
  predictionHash?: string;
  patternId?: string;
  embedding?: number[];
}

/**
 * Validates and parses a prediction result.
 * Note: schemaVersion is optional for backward compatibility.
 */
export function validatePredictionResult(data: unknown): PredictionResultSchema {
  const obj = validateObject(data, 'prediction-result');

  const result: PredictionResultSchema = {
    schemaVersion: SCHEMA_VERSIONS.PREDICTION_RESULT,
    id: validateString(obj.id, 'id', 1, LIMITS.MAX_ID_LENGTH),
    predictedValue: validateNumber(obj.predictedValue, 'predictedValue'),
    confidence: validateNumber(
      obj.confidence,
      'confidence',
      LIMITS.MIN_CONFIDENCE,
      LIMITS.MAX_CONFIDENCE
    ),
    node: validateString(obj.node, 'node', 1, LIMITS.MAX_NODE_LENGTH),
    timestamp: validateNumber(
      obj.timestamp,
      'timestamp',
      LIMITS.MIN_TIMESTAMP,
      LIMITS.MAX_TIMESTAMP
    ),
    traceId: validateString(obj.traceId, 'traceId', 1, LIMITS.MAX_TRACE_LENGTH),
  };

  if (obj.sourceRevision !== undefined) {
    result.sourceRevision = validateGitSha(obj.sourceRevision, 'sourceRevision');
  }

  if (obj.predictionHash !== undefined) {
    result.predictionHash = validateSha256(obj.predictionHash, 'predictionHash');
  }

  if (obj.patternId !== undefined) {
    result.patternId = validateString(obj.patternId, 'patternId');
  }

  if (obj.embedding !== undefined) {
    result.embedding = validateArray(
      obj.embedding,
      'embedding',
      (item) => validateNumber(item, 'embedding element'),
      1,
      LIMITS.MAX_EMBEDDING_DIM
    );
  }

  return result;
}

/**
 * Type guard for prediction results.
 */
export function isValidPredictionResult(data: unknown): data is PredictionResultSchema {
  try {
    validatePredictionResult(data);
    return true;
  } catch {
    return false;
  }
}

// ============================================================================
// Schema: Prediction Error
// ============================================================================

export interface PredictionErrorSchema {
  schemaVersion: typeof SCHEMA_VERSIONS.PREDICTION_ERROR;
  id: string;
  actual: number;
  predicted: number;
  error: number;
  absoluteError: number;
  propagated: boolean;
  node: string;
  timestamp: number;
  traceId: string;
  sourceRevision?: string;
  weight: number;
}

/**
 * Validates and parses a prediction error.
 * Note: schemaVersion is optional for backward compatibility.
 */
export function validatePredictionError(data: unknown): PredictionErrorSchema {
  const obj = validateObject(data, 'prediction-error');

  const result: PredictionErrorSchema = {
    schemaVersion: SCHEMA_VERSIONS.PREDICTION_ERROR,
    id: validateString(obj.id, 'id', 1, LIMITS.MAX_ID_LENGTH),
    actual: validateNumber(obj.actual, 'actual'),
    predicted: validateNumber(obj.predicted, 'predicted'),
    error: validateNumber(obj.error, 'error'),
    absoluteError: validateNumber(obj.absoluteError, 'absoluteError', 0),
    propagated: typeof obj.propagated === 'boolean' ? obj.propagated : false,
    node: validateString(obj.node, 'node', 1, LIMITS.MAX_NODE_LENGTH),
    timestamp: validateNumber(
      obj.timestamp,
      'timestamp',
      LIMITS.MIN_TIMESTAMP,
      LIMITS.MAX_TIMESTAMP
    ),
    traceId: validateString(obj.traceId, 'traceId', 1, LIMITS.MAX_TRACE_LENGTH),
    weight: validateNumber(
      obj.weight,
      'weight',
      LIMITS.MIN_WEIGHT,
      LIMITS.MAX_WEIGHT
    ),
  };

  if (obj.sourceRevision !== undefined) {
    result.sourceRevision = validateGitSha(obj.sourceRevision, 'sourceRevision');
  }

  return result;
}

/**
 * Type guard for prediction errors.
 */
export function isValidPredictionError(data: unknown): data is PredictionErrorSchema {
  try {
    validatePredictionError(data);
    return true;
  } catch {
    return false;
  }
}

// ============================================================================
// Schema: Bounded Action Plan
// ============================================================================

export interface ActionStep {
  stepId: string;
  action: string;
  parameters: Record<string, unknown>;
  preconditionHash?: string;
  rollbackPlan?: string;
}

export interface BoundedActionPlanSchema {
  schemaVersion: typeof SCHEMA_VERSIONS.BOUNDED_ACTION_PLAN;
  planId: string;
  planHash: string;
  traceId: string;
  sourceRevision: string;
  createdAt: number;
  steps: ActionStep[];
  maxDurationMs: number;
  riskLevel: 'low' | 'medium' | 'high';
  boundedResources?: string[];
}

/**
 * Validates and parses a bounded action plan.
 * Note: schemaVersion is optional for backward compatibility.
 */
export function validateBoundedActionPlan(data: unknown): BoundedActionPlanSchema {
  const obj = validateObject(data, 'bounded-action-plan');

  const steps = validateArray(
    obj.steps,
    'steps',
    (step): ActionStep => {
      const s = validateObject(step, 'step');
      return {
        stepId: validateString(s.stepId, 'stepId'),
        action: validateString(s.action, 'action'),
        parameters: validateObject(s.parameters, 'parameters'),
        preconditionHash: s.preconditionHash
          ? validateSha256(s.preconditionHash, 'preconditionHash')
          : undefined,
        rollbackPlan: s.rollbackPlan
          ? validateString(s.rollbackPlan, 'rollbackPlan')
          : undefined,
      };
    },
    1
  );

  const riskLevel = obj.riskLevel;
  if (riskLevel !== 'low' && riskLevel !== 'medium' && riskLevel !== 'high') {
    throw new RangeError('riskLevel must be low, medium, or high');
  }

  const result: BoundedActionPlanSchema = {
    schemaVersion: SCHEMA_VERSIONS.BOUNDED_ACTION_PLAN,
    planId: validateString(obj.planId, 'planId'),
    planHash: validateSha256(obj.planHash, 'planHash'),
    traceId: validateString(obj.traceId, 'traceId'),
    sourceRevision: validateGitSha(obj.sourceRevision, 'sourceRevision'),
    createdAt: validateNumber(obj.createdAt, 'createdAt', LIMITS.MIN_TIMESTAMP),
    steps,
    maxDurationMs: validateNumber(obj.maxDurationMs, 'maxDurationMs', 1),
    riskLevel,
  };

  if (obj.boundedResources !== undefined) {
    result.boundedResources = validateArray(
      obj.boundedResources,
      'boundedResources',
      (item) => validateString(item, 'boundedResource'),
      0
    );
  }

  return result;
}

/**
 * Type guard for bounded action plans.
 */
export function isValidBoundedActionPlan(data: unknown): data is BoundedActionPlanSchema {
  try {
    validateBoundedActionPlan(data);
    return true;
  } catch {
    return false;
  }
}

// ============================================================================
// Schema: Runtime Action Receipt
// ============================================================================

export type ActionOutcome = 'succeeded' | 'failed' | 'blocked' | 'rolled_back';

export interface RuntimeActionReceiptSchema {
  schemaVersion: typeof SCHEMA_VERSIONS.RUNTIME_ACTION_RECEIPT;
  receiptId: string;
  actionHash: string;
  traceId: string;
  sourceRevision: string;
  executedAt: number;
  durationMs: number;
  outcome: ActionOutcome;
  targetResource?: string;
  errorMessage?: string;
  evidenceHashes?: string[];
}

/**
 * Validates and parses a runtime action receipt.
 * Note: schemaVersion is optional for backward compatibility.
 */
export function validateRuntimeActionReceipt(data: unknown): RuntimeActionReceiptSchema {
  const obj = validateObject(data, 'runtime-action-receipt');

  const outcome = obj.outcome;
  const validOutcomes: ActionOutcome[] = ['succeeded', 'failed', 'blocked', 'rolled_back'];
  if (!validOutcomes.includes(outcome as ActionOutcome)) {
    throw new RangeError(`outcome must be one of: ${validOutcomes.join(', ')}`);
  }

  const result: RuntimeActionReceiptSchema = {
    schemaVersion: SCHEMA_VERSIONS.RUNTIME_ACTION_RECEIPT,
    receiptId: validateString(obj.receiptId, 'receiptId'),
    actionHash: validateSha256(obj.actionHash, 'actionHash'),
    traceId: validateString(obj.traceId, 'traceId'),
    sourceRevision: validateGitSha(obj.sourceRevision, 'sourceRevision'),
    executedAt: validateNumber(obj.executedAt, 'executedAt', LIMITS.MIN_TIMESTAMP),
    durationMs: validateNumber(obj.durationMs, 'durationMs', 0),
    outcome: outcome as ActionOutcome,
  };

  if (obj.targetResource !== undefined) {
    result.targetResource = validateString(obj.targetResource, 'targetResource');
  }

  if (obj.errorMessage !== undefined) {
    result.errorMessage = validateString(obj.errorMessage, 'errorMessage', 0, LIMITS.MAX_REASON_LENGTH);
  }

  if (obj.evidenceHashes !== undefined) {
    result.evidenceHashes = validateArray(
      obj.evidenceHashes,
      'evidenceHashes',
      (item) => validateSha256(item, 'evidenceHash'),
      0
    );
  }

  return result;
}

/**
 * Type guard for runtime action receipts.
 */
export function isValidRuntimeActionReceipt(data: unknown): data is RuntimeActionReceiptSchema {
  try {
    validateRuntimeActionReceipt(data);
    return true;
  } catch {
    return false;
  }
}

// ============================================================================
// Schema: Predictive Snapshot
// ============================================================================

export interface PredictiveSnapshotSchema {
  schemaVersion: typeof SCHEMA_VERSIONS.PREDICTIVE_SNAPSHOT;
  snapshotId: string;
  sourceRevision: string;
  capturedAt: number;
  nodeCount: number;
  synapseCount: number;
  patternCount: number;
  avgConfidence: number;
  errorRate: number;
  phase: 'idle' | 'predicting' | 'error-computing' | 'learning';
}

/**
 * Validates and parses a predictive snapshot.
 * Note: schemaVersion is optional for backward compatibility.
 */
export function validatePredictiveSnapshot(data: unknown): PredictiveSnapshotSchema {
  const obj = validateObject(data, 'predictive-snapshot');

  const phase = obj.phase;
  const validPhases = ['idle', 'predicting', 'error-computing', 'learning'] as const;
  if (!validPhases.includes(phase as typeof validPhases[number])) {
    throw new RangeError(`phase must be one of: ${validPhases.join(', ')}`);
  }

  return {
    schemaVersion: SCHEMA_VERSIONS.PREDICTIVE_SNAPSHOT,
    snapshotId: validateString(obj.snapshotId, 'snapshotId'),
    sourceRevision: validateGitSha(obj.sourceRevision, 'sourceRevision'),
    capturedAt: validateNumber(obj.capturedAt, 'capturedAt', LIMITS.MIN_TIMESTAMP),
    nodeCount: validateNumber(obj.nodeCount, 'nodeCount', 0),
    synapseCount: validateNumber(obj.synapseCount, 'synapseCount', 0),
    patternCount: validateNumber(obj.patternCount, 'patternCount', 0),
    avgConfidence: validateNumber(
      obj.avgConfidence,
      'avgConfidence',
      LIMITS.MIN_CONFIDENCE,
      LIMITS.MAX_CONFIDENCE
    ),
    errorRate: validateNumber(obj.errorRate, 'errorRate', 0, 1),
    phase: phase as 'idle' | 'predicting' | 'error-computing' | 'learning',
  };
}

/**
 * Type guard for predictive snapshots.
 */
export function isValidPredictiveSnapshot(data: unknown): data is PredictiveSnapshotSchema {
  try {
    validatePredictiveSnapshot(data);
    return true;
  } catch {
    return false;
  }
}

// ============================================================================
// Schema: Runtime Readback
// ============================================================================

export type ReadbackStatus = 'verified' | 'mismatch' | 'unavailable' | 'timeout';

export interface RuntimeReadbackSchema {
  schemaVersion: typeof SCHEMA_VERSIONS.RUNTIME_READBACK;
  readbackId: string;
  sourceRevision: string;
  targetResource: string;
  expectedHash: string;
  actualHash?: string;
  status: ReadbackStatus;
  readbackAt: number;
  latencyMs?: number;
  errorMessage?: string;
}

/**
 * Validates and parses a runtime readback.
 * Note: schemaVersion is optional for backward compatibility.
 */
export function validateRuntimeReadback(data: unknown): RuntimeReadbackSchema {
  const obj = validateObject(data, 'runtime-readback');

  const status = obj.status;
  const validStatuses: ReadbackStatus[] = ['verified', 'mismatch', 'unavailable', 'timeout'];
  if (!validStatuses.includes(status as ReadbackStatus)) {
    throw new RangeError(`status must be one of: ${validStatuses.join(', ')}`);
  }

  const result: RuntimeReadbackSchema = {
    schemaVersion: SCHEMA_VERSIONS.RUNTIME_READBACK,
    readbackId: validateString(obj.readbackId, 'readbackId'),
    sourceRevision: validateGitSha(obj.sourceRevision, 'sourceRevision'),
    targetResource: validateString(obj.targetResource, 'targetResource'),
    expectedHash: validateSha256(obj.expectedHash, 'expectedHash'),
    status: status as ReadbackStatus,
    readbackAt: validateNumber(obj.readbackAt, 'readbackAt', LIMITS.MIN_TIMESTAMP),
  };

  if (obj.actualHash !== undefined) {
    result.actualHash = validateSha256(obj.actualHash, 'actualHash');
  }

  if (obj.latencyMs !== undefined) {
    result.latencyMs = validateNumber(obj.latencyMs, 'latencyMs', 0);
  }

  if (obj.errorMessage !== undefined) {
    result.errorMessage = validateString(obj.errorMessage, 'errorMessage', 0, LIMITS.MAX_REASON_LENGTH);
  }

  return result;
}

/**
 * Type guard for runtime readbacks.
 */
export function isValidRuntimeReadback(data: unknown): data is RuntimeReadbackSchema {
  try {
    validateRuntimeReadback(data);
    return true;
  } catch {
    return false;
  }
}

// ============================================================================
// Schema: Risk Evidence Bundle
// ============================================================================

export type RiskLevel = 'negligible' | 'low' | 'medium' | 'high' | 'critical';
export type RiskCategory = 'security' | 'operational' | 'compliance' | 'performance' | 'reliability';

export interface RiskEvidence {
  evidenceId: string;
  evidenceHash: string;
  sourceType: 'log' | 'metric' | 'config' | 'runtime' | 'external';
  sourceTimestamp: number;
  description: string;
}

export interface RiskEvidenceBundleSchema {
  schemaVersion: typeof SCHEMA_VERSIONS.RISK_EVIDENCE_BUNDLE;
  bundleId: string;
  bundleHash: string;
  sourceRevision: string;
  riskLevel: RiskLevel;
  riskCategory: RiskCategory;
  description: string;
  evidence: RiskEvidence[];
  detectedAt: number;
  ownerReviewRequired: boolean;
  mitigationPlan?: string;
}

/**
 * Validates and parses a risk evidence bundle.
 * Note: schemaVersion is optional for backward compatibility.
 */
export function validateRiskEvidenceBundle(data: unknown): RiskEvidenceBundleSchema {
  const obj = validateObject(data, 'risk-evidence-bundle');

  const riskLevel = obj.riskLevel;
  const validRiskLevels: RiskLevel[] = ['negligible', 'low', 'medium', 'high', 'critical'];
  if (!validRiskLevels.includes(riskLevel as RiskLevel)) {
    throw new RangeError(`riskLevel must be one of: ${validRiskLevels.join(', ')}`);
  }

  const riskCategory = obj.riskCategory;
  const validCategories: RiskCategory[] = ['security', 'operational', 'compliance', 'performance', 'reliability'];
  if (!validCategories.includes(riskCategory as RiskCategory)) {
    throw new RangeError(`riskCategory must be one of: ${validCategories.join(', ')}`);
  }

  const evidence = validateArray(
    obj.evidence,
    'evidence',
    (item): RiskEvidence => {
      const e = validateObject(item, 'evidence');
      const sourceType = e.sourceType;
      const validSourceTypes = ['log', 'metric', 'config', 'runtime', 'external'];
      if (!validSourceTypes.includes(sourceType as string)) {
        throw new RangeError(`evidence.sourceType must be one of: ${validSourceTypes.join(', ')}`);
      }
      return {
        evidenceId: validateString(e.evidenceId, 'evidenceId'),
        evidenceHash: validateSha256(e.evidenceHash, 'evidenceHash'),
        sourceType: sourceType as 'log' | 'metric' | 'config' | 'runtime' | 'external',
        sourceTimestamp: validateNumber(e.sourceTimestamp, 'sourceTimestamp', LIMITS.MIN_TIMESTAMP),
        description: validateString(e.description, 'description', 1, LIMITS.MAX_REASON_LENGTH),
      };
    },
    1
  );

  const result: RiskEvidenceBundleSchema = {
    schemaVersion: SCHEMA_VERSIONS.RISK_EVIDENCE_BUNDLE,
    bundleId: validateString(obj.bundleId, 'bundleId'),
    bundleHash: validateSha256(obj.bundleHash, 'bundleHash'),
    sourceRevision: validateGitSha(obj.sourceRevision, 'sourceRevision'),
    riskLevel: riskLevel as RiskLevel,
    riskCategory: riskCategory as RiskCategory,
    description: validateString(obj.description, 'description', 1, LIMITS.MAX_REASON_LENGTH),
    evidence,
    detectedAt: validateNumber(obj.detectedAt, 'detectedAt', LIMITS.MIN_TIMESTAMP),
    ownerReviewRequired: typeof obj.ownerReviewRequired === 'boolean' ? obj.ownerReviewRequired : false,
  };

  if (obj.mitigationPlan !== undefined) {
    result.mitigationPlan = validateString(obj.mitigationPlan, 'mitigationPlan', 0, LIMITS.MAX_REASON_LENGTH);
  }

  return result;
}

/**
 * Type guard for risk evidence bundles.
 */
export function isValidRiskEvidenceBundle(data: unknown): data is RiskEvidenceBundleSchema {
  try {
    validateRiskEvidenceBundle(data);
    return true;
  } catch {
    return false;
  }
}

// ============================================================================
// Exports
// ============================================================================

export * from './types';
