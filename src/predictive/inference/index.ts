/**
 * Predictive Inference Layer - Public Exports
 *
 * Issue #1172: Predictive Inference and Wolfram Validation
 *
 * This module implements the deterministic validation lane with:
 * - Multiple independent inference channels
 * - Model receipts with full revision binding
 * - Risk evidence bundles combining channel outputs
 * - Fail-closed behavior for stale/missing data
 *
 * @module predictive/inference
 */

// Types
export {
  type RevisionBinding,
  type InputWindowHash,
  type ModelStateHash,
  type InferenceChannelType,
  type InferenceSeverity,
  type BaseInferenceResult,
  type ModelReceipt,
  type ModelReceiptValidation,
  type RiskEvidenceBundle,
  type RiskBundleValidation,
  type CausalVerdict,
  type InferenceChannelConfig,
  type InferenceChannelResult,
  // Helpers
  isReceiptStale,
  validateModelReceipt,
  computeReceiptHash,
  detectChannelConflicts,
} from './types';

// Hard Invariant Channel
export {
  type HardInvariant,
  type HardInvariantCheckResult,
  type HardInvariantChannelConfig,
  DEFAULT_HARD_INVARIANT_CONFIG,
  checkHardInvariant,
  createHardInvariantReceipt,
  runHardInvariantChannel,
  createDefaultRuntimeInvariantConfig,
} from './hardInvariantChannel';

// Risk Evidence Bundle
export {
  type CreateBundleInput,
  type PostActionVerification,
  createRiskEvidenceBundle,
  validateRiskBundle,
  determineCausalVerdict,
  applyCausalVerdict,
  receiptsToChannelResults,
} from './riskEvidenceBundle';

// Model Receipt
export {
  type CreateReceiptInput,
  type ReceiptIdentifiers,
  createModelReceipt,
  validateModelReceipt as validateReceipt,
  isSameInferenceRun,
  verifyReceiptIntegrity,
  formatReceiptSummary,
  extractReceiptIdentifiers,
  createRevisionBinding,
  createInputWindowHash,
  createModelStateHash,
} from './modelReceipt';
