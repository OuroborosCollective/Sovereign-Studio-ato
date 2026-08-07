/**
 * Predictive Contract Foundation - Registry
 *
 * @module predictive/contracts
 */

// Re-export Runtime Signal contracts
export {
  validateSignal,
  validateSignalWindow,
  generateSchemaHash,
  generateSignalHash,
  createSchemaMetadata,
  validateSignalPayloadSize,
  validateWindowPayloadSize,
  SIGNAL_MAX_METADATA_SIZE,
  SIGNAL_WINDOW_MAX_SIGNALS,
  RUNTIME_SIGNAL_SCHEMA_ID,
  RUNTIME_SIGNAL_SCHEMA_VERSION,
  SignalErrorCode,
  type RuntimeSignal,
  type RuntimeSignalWindow,
  type RuntimeSignalSchemaMetadata,
  type SignalValidationResult,
  type SignalValidationError,
} from './runtimeSignal';

// Re-export Prediction contracts
export {
  validatePrediction,
  validatePredictionError,
  PREDICTION_SCHEMA_ID,
  PREDICTION_ERROR_SCHEMA_ID,
  generatePredictionSchemaHash,
  generatePredictionErrorSchemaHash,
  type PredictionContract,
  type PredictionErrorContract,
  type ValidationResult,
  type ValidationError,
  type ValidationWarning,
} from './prediction';

// Re-export Risk Evidence contracts
export {
  validateRiskEvidenceBundle,
  validateBoundedActionPlan,
  generateRiskEvidenceBundleSchemaHash,
  generateBoundedActionPlanSchemaHash,
  RISK_EVIDENCE_BUNDLE_SCHEMA_ID,
  BOUNDED_ACTION_PLAN_SCHEMA_ID,
  type RiskEvidenceBundleContract,
  type RiskEvidenceItem,
  type BoundedActionPlanContract,
  type BoundedAction,
  type PreCondition,
  type PostCondition,
  type ActionScope,
} from './riskEvidence';
