/**
 * Predictive Contracts - JSON Schema Exports
 *
 * Exports JSON schemas for runtime signal contracts.
 * These schemas define the canonical structure for predictive layer signals
 * and can be used for cross-language validation.
 *
 * @module predictive/contracts
 */

export const CONTRACTS = {
  RUNTIME_SIGNAL: 'runtime-signal.v1',
  PREDICTION_RESULT: 'prediction-result.v1',
  PREDICTION_ERROR: 'prediction-error.v1',
} as const;

// Lazy-loaded schema imports for tree-shaking
let _runtimeSignalSchema: object | null = null;
let _predictionResultSchema: object | null = null;
let _predictionErrorSchema: object | null = null;

export function getRuntimeSignalSchema(): object {
  if (!_runtimeSignalSchema) {
    _runtimeSignalSchema = require('./runtime-signal.v1.schema.json');
  }
  return _runtimeSignalSchema;
}

export function getPredictionResultSchema(): object {
  if (!_predictionResultSchema) {
    _predictionResultSchema = require('./prediction-result.v1.schema.json');
  }
  return _predictionResultSchema;
}

export function getPredictionErrorSchema(): object {
  if (!_predictionErrorSchema) {
    _predictionErrorSchema = require('./prediction-error.v1.schema.json');
  }
  return _predictionErrorSchema;
}
