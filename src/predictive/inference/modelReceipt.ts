/**
 * Model Receipt Creation and Validation
 *
 * Issue #1172: Model Receipt contract
 *
 * Every inference run must produce a Model Receipt with full revision binding.
 * The receipt attests to:
 * - Channel type and model class
 * - Implementation and library versions
 * - Source, runtime, and config revisions
 * - Feature schema and input window hashes
 * - Model state (versioned, mutable weights)
 * - Used seed/sampling rules
 *
 * Key rules:
 * - Same inputs + same model = reproducible outputs (within tolerance)
 * - Missing hashes block the channel
 * - Changed revision/config/weights invalidate old predictions
 *
 * @module predictive/inference/modelReceipt
 */

import type {
  ModelReceipt,
  RevisionBinding,
  InputWindowHash,
  ModelStateHash,
  InferenceChannelType,
  ModelReceiptValidation,
} from './types';
import { computeReceiptHash, validateModelReceipt as validateReceipt } from './types';

/** Input for creating a model receipt */
export interface CreateReceiptInput {
  channelType: InferenceChannelType;
  modelClass: string;
  implementationVersion: string;
  revisionBinding: RevisionBinding;
  featureSchemaHash: string;
  inputWindowHash: InputWindowHash;
  modelStateHash: ModelStateHash;
  score: number;
  predictionHorizonMs?: number;
  calibrationMetadata?: ModelReceipt['calibrationMetadata'];
  knownLimitations?: string[];
  abortReason?: string;
  scannInfo?: {
    manifestHash: string;
    candidateHashes: string[];
  };
  wolframInfo?: {
    version: string;
    kernelMode: string;
    expressionHash: string;
    resultHash: string;
  };
}

/**
 * Create a new Model Receipt with full binding.
 */
export function createModelReceipt(input: CreateReceiptInput): ModelReceipt {
  const receiptId = `receipt_${input.channelType}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

  const receipt: Omit<ModelReceipt, 'receiptHash'> = {
    schemaVersion: 'model-receipt.v1',
    receiptId,
    channelType: input.channelType,
    modelClass: input.modelClass,
    implementationVersion: input.implementationVersion,

    revisionBinding: input.revisionBinding,
    featureSchemaHash: input.featureSchemaHash,
    inputWindowHash: input.inputWindowHash,
    modelStateHash: input.modelStateHash,

    predictionHorizonMs: input.predictionHorizonMs,
    score: input.score,
    calibrationMetadata: input.calibrationMetadata,

    knownLimitations: input.knownLimitations ?? [],
    abortReason: input.abortReason,

    scannManifestHash: input.scannInfo?.manifestHash,
    scannCandidateHashes: input.scannInfo?.candidateHashes,

    wolframVersion: input.wolframInfo?.version,
    wolframKernelMode: input.wolframInfo?.kernelMode,
    wolframExpressionHash: input.wolframInfo?.expressionHash,
    wolframResultHash: input.wolframInfo?.resultHash,

    createdAt: Date.now(),
  };

  return {
    ...receipt,
    receiptHash: computeReceiptHash(receipt),
  };
}

/**
 * Validate a model receipt and check for staleness.
 */
export function validateModelReceipt(
  receipt: ModelReceipt,
  currentRevision: string,
  maxAgeMs: number = 5 * 60 * 1000,
): ModelReceiptValidation {
  // Base validation
  const baseValidation = validateReceipt(receipt);

  const errors = [...baseValidation.errors];
  const warnings = [...baseValidation.warnings];

  // Check revision binding
  if (receipt.revisionBinding.runtimeRevision !== currentRevision) {
    errors.push(
      `Revision mismatch: receipt has ${receipt.revisionBinding.runtimeRevision}, current is ${currentRevision}`
    );
  }

  // Check for stale receipt
  const ageMs = Date.now() - receipt.createdAt;
  if (ageMs > maxAgeMs) {
    warnings.push(`Receipt is stale: ${ageMs}ms old (max ${maxAgeMs}ms)`);
  }

  // Check for missing critical hashes
  if (!receipt.featureSchemaHash || receipt.featureSchemaHash === 'n/a') {
    errors.push('Missing feature schema hash');
  }

  if (!receipt.inputWindowHash.hash || receipt.inputWindowHash.hash === 'n/a') {
    errors.push('Missing input window hash');
  }

  // Validate model state hash
  if (!receipt.modelStateHash.parametersHash) {
    errors.push('Missing model parameters hash');
  }

  // Wolfram-specific validation
  if (receipt.wolframVersion) {
    if (!receipt.wolframResultHash) {
      warnings.push('Wolfram run without result hash');
    }
    if (!receipt.wolframKernelMode) {
      warnings.push('Wolfram run without kernel mode specification');
    }
  }

  // ScaNN-specific validation
  if (receipt.scannManifestHash) {
    if (!receipt.scannCandidateHashes || receipt.scannCandidateHashes.length === 0) {
      warnings.push('ScaNN manifest without candidate hashes');
    }
  }

  return {
    isValid: errors.length === 0,
    errors,
    warnings,
    bindingAgeMs: ageMs,
  };
}

/**
 * Check if two receipts are for the same inference run.
 */
export function isSameInferenceRun(a: ModelReceipt, b: ModelReceipt): boolean {
  return (
    a.channelType === b.channelType &&
    a.revisionBinding.runtimeRevision === b.revisionBinding.runtimeRevision &&
    a.inputWindowHash.hash === b.inputWindowHash.hash &&
    a.modelStateHash.weightsHash === b.modelStateHash.weightsHash
  );
}

/**
 * Verify receipt integrity (hash check).
 */
export function verifyReceiptIntegrity(receipt: ModelReceipt): boolean {
  const computed = computeReceiptHash(receipt);
  return computed === receipt.receiptHash;
}

/**
 * Create a receipt summary for logging/debugging.
 */
export function formatReceiptSummary(receipt: ModelReceipt): string {
  return [
    `ModelReceipt[${receipt.receiptId}]`,
    `  Channel: ${receipt.channelType}`,
    `  Model: ${receipt.modelClass}@${receipt.implementationVersion}`,
    `  Revision: ${receipt.revisionBinding.runtimeRevision.slice(0, 8)}`,
    `  Score: ${(receipt.score * 100).toFixed(1)}%`,
    receipt.abortReason ? `  ABORTED: ${receipt.abortReason}` : '',
    receipt.knownLimitations.length > 0
      ? `  Limitations: ${receipt.knownLimitations.length}`
      : '',
    receipt.wolframVersion ? `  Wolfram: ${receipt.wolframVersion}` : '',
    receipt.scannManifestHash ? `  ScaNN: ${receipt.scannManifestHash.slice(0, 8)}` : '',
  ]
    .filter(Boolean)
    .join('\n');
}

/**
 * Extract key identifiers from a receipt for correlation.
 */
export interface ReceiptIdentifiers {
  receiptId: string;
  channelType: InferenceChannelType;
  runtimeRevision: string;
  configRevision: string;
  inputWindowHash: string;
  weightsHash: string;
}

export function extractReceiptIdentifiers(receipt: ModelReceipt): ReceiptIdentifiers {
  return {
    receiptId: receipt.receiptId,
    channelType: receipt.channelType,
    runtimeRevision: receipt.revisionBinding.runtimeRevision,
    configRevision: receipt.revisionBinding.configRevision,
    inputWindowHash: receipt.inputWindowHash.hash,
    weightsHash: receipt.modelStateHash.weightsHash,
  };
}

/**
 * Create a revision binding from current environment.
 */
export function createRevisionBinding(
  runtimeRevision: string,
  configRevision: string,
): RevisionBinding {
  return {
    runtimeRevision,
    configRevision,
    schemaVersion: '1.0',
    boundAt: Date.now(),
  };
}

/**
 * Create an input window hash from signal data.
 */
export function createInputWindowHash(
  signals: { timestamp: number; value: number }[],
  windowStart: number,
  windowEnd: number,
): InputWindowHash {
  // Simple hash from signal values
  const featureString = signals.map(s => `${s.timestamp}:${s.value}`).join('|');
  let hash = 0;
  for (let i = 0; i < featureString.length; i++) {
    hash = ((hash << 5) - hash) + featureString.charCodeAt(i);
    hash = hash & hash;
  }

  return {
    hash: `window_${Math.abs(hash).toString(16)}`,
    signalCount: signals.length,
    windowStart,
    windowEnd,
    featureHash: `feat_${Math.abs(hash).toString(16).slice(0, 8)}`,
  };
}

/**
 * Create a model state hash from parameters.
 */
export function createModelStateHash(
  parameters: unknown,
  weights: unknown,
  config: unknown,
  libraryVersion: string,
): ModelStateHash {
  const hashObj = (obj: unknown): string => {
    const str = JSON.stringify(obj);
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash = hash & hash;
    }
    return Math.abs(hash).toString(16);
  };

  return {
    parametersHash: hashObj(parameters),
    weightsHash: hashObj(weights),
    configHash: hashObj(config),
    libraryVersion,
  };
}
