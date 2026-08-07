/**
 * Prediction Contracts - Runtime validation for predictive layer outputs
 * 
 * Schema definitions for:
 * - prediction-result.v1: Top-down predictions from the predictive layer
 * - prediction-error.v1: Computed prediction errors for error propagation
 * 
 * @module predictive/contracts/prediction
 */

// ============================================================================
// Schema Identifiers
// ============================================================================

export const PREDICTION_SCHEMA_ID = 'prediction-result.v1';
export const PREDICTION_ERROR_SCHEMA_ID = 'prediction-error.v1';

// ============================================================================
// Field Sets
// ============================================================================

/** Required fields for a valid prediction */
export const PREDICTION_REQUIRED_FIELDS = [
  'schemaId',
  'schemaVersion',
  'id',
  'predictedValue',
  'confidence',
  'node',
  'timestamp',
  'traceId',
] as const;

/** All allowed fields for a prediction */
export const PREDICTION_ALL_FIELDS = [
  ...PREDICTION_REQUIRED_FIELDS,
  'patternId',
  'embedding',
  'sourceRevision',
  'runtimeRevision',
  'tick',
  'sequence',
] as const;

/** Required fields for a valid prediction error */
export const PREDICTION_ERROR_REQUIRED_FIELDS = [
  'schemaId',
  'schemaVersion',
  'id',
  'actual',
  'predicted',
  'error',
  'absoluteError',
  'propagated',
  'node',
  'timestamp',
  'traceId',
] as const;

/** All allowed fields for a prediction error */
export const PREDICTION_ERROR_ALL_FIELDS = [
  ...PREDICTION_ERROR_REQUIRED_FIELDS,
  'weight',
  'sourceRevision',
  'runtimeRevision',
  'tick',
  'sequence',
] as const;

// ============================================================================
// Validation Result Types
// ============================================================================

export interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
  warnings: ValidationWarning[];
}

export interface ValidationError {
  field: string;
  code: string;
  message: string;
}

export interface ValidationWarning {
  field: string;
  message: string;
}

// ============================================================================
// Prediction Contract
// ============================================================================

export interface PredictionContract {
  /** Schema identifier */
  schemaId: string;
  /** Schema version */
  schemaVersion: string;
  /** Unique identifier for this prediction */
  id: string;
  /** The predicted value x̂(t) */
  predictedValue: number;
  /** Confidence score [0, 1] based on pattern match quality */
  confidence: number;
  /** The node this prediction is for */
  node: string;
  /** Timestamp when prediction was generated */
  timestamp: number;
  /** Trace context for debugging */
  traceId: string;
  /** Reference to the pattern used for prediction */
  patternId?: string;
  /** The latent space embedding used for this prediction */
  embedding?: number[];
  /** Source revision for deterministic replay */
  sourceRevision?: string;
  /** Runtime revision binding */
  runtimeRevision?: string;
  /** Causal tick (replaces wall-clock dependency) */
  tick?: number;
  /** Causal sequence number */
  sequence?: number;
}

/**
 * Validate a prediction contract.
 * Implements fail-closed validation - any unknown field or invalid value is rejected.
 */
export function validatePrediction(
  obj: unknown,
  options: { strict?: boolean } = {}
): ValidationResult {
  const { strict = true } = options;
  const errors: ValidationError[] = [];
  const warnings: ValidationWarning[] = [];

  if (typeof obj !== 'object' || obj === null) {
    return {
      valid: false,
      errors: [{
        field: 'root',
        code: 'INVALID_TYPE',
        message: 'Prediction must be a non-null object',
      }],
      warnings: [],
    };
  }

  const p = obj as Record<string, unknown>;

  // Validate schema binding
  if (p.schemaId !== PREDICTION_SCHEMA_ID) {
    errors.push({
      field: 'schemaId',
      code: 'INVALID_SCHEMA',
      message: `Expected schemaId "${PREDICTION_SCHEMA_ID}", got "${p.schemaId}"`,
    });
  }

  if (typeof p.schemaVersion !== 'string' || !p.schemaVersion.startsWith('v')) {
    errors.push({
      field: 'schemaVersion',
      code: 'INVALID_VERSION',
      message: 'schemaVersion must be a string starting with "v"',
    });
  }

  // Validate required string fields
  for (const field of ['id', 'node', 'traceId']) {
    if (typeof p[field] !== 'string' || (p[field] as string).length === 0) {
      errors.push({
        field,
        code: 'MISSING_OR_EMPTY',
        message: `${field} must be a non-empty string`,
      });
    }
  }

  // Validate numeric fields
  const numericFields: Array<{ name: string; min?: number; max?: number }> = [
    { name: 'predictedValue' },
    { name: 'confidence', min: 0, max: 1 },
    { name: 'timestamp', min: 0 },
    { name: 'tick', min: 0 },
    { name: 'sequence', min: 0 },
  ];

  for (const { name, min, max } of numericFields) {
    if (p[name] !== undefined) {
      const value = p[name];
      if (typeof value !== 'number') {
        errors.push({
          field: name,
          code: 'INVALID_TYPE',
          message: `${name} must be a number`,
        });
      } else if (!Number.isFinite(value)) {
        errors.push({
          field: name,
          code: 'INVALID_NUMBER',
          message: `${name} must be finite (not NaN or Infinity)`,
        });
      } else if (Number.isNaN(value)) {
        errors.push({
          field: name,
          code: 'INVALID_NUMBER',
          message: `${name} must not be NaN`,
        });
      } else if (min !== undefined && value < min) {
        errors.push({
          field: name,
          code: 'OUT_OF_RANGE',
          message: `${name} must be >= ${min}`,
        });
      } else if (max !== undefined && value > max) {
        errors.push({
          field: name,
          code: 'OUT_OF_RANGE',
          message: `${name} must be <= ${max}`,
        });
      }
    }
  }

  // Validate embedding array if present
  if (p.embedding !== undefined) {
    if (!Array.isArray(p.embedding)) {
      errors.push({
        field: 'embedding',
        code: 'INVALID_TYPE',
        message: 'embedding must be an array',
      });
    } else {
      for (let i = 0; i < p.embedding.length; i++) {
        const val = p.embedding[i];
        if (typeof val !== 'number') {
          errors.push({
            field: `embedding[${i}]`,
            code: 'INVALID_TYPE',
            message: `embedding[${i}] must be a number`,
          });
        } else if (!Number.isFinite(val)) {
          errors.push({
            field: `embedding[${i}]`,
            code: 'INVALID_NUMBER',
            message: `embedding[${i}] must be finite`,
          });
        }
      }
      // Check for negative zero
      if (p.embedding.some((v: number) => Object.is(v, -0))) {
        errors.push({
          field: 'embedding',
          code: 'AMBIGUOUS_VALUE',
          message: 'embedding must not contain negative zero',
        });
      }
    }
  }

  // Strict mode: reject unknown fields
  if (strict) {
    const knownFields = new Set(PREDICTION_ALL_FIELDS.map(f => f as string));
    for (const key of Object.keys(p)) {
      if (!knownFields.has(key)) {
        errors.push({
          field: key,
          code: 'UNKNOWN_FIELD',
          message: `Unknown field "${key}" in strict mode`,
        });
      }
    }
  }

  // Payload size check for embeddings
  if (p.embedding && Array.isArray(p.embedding) && p.embedding.length > 10000) {
    warnings.push({
      field: 'embedding',
      message: `embedding has ${p.embedding.length} dimensions, which may cause memory issues`,
    });
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  };
}

// ============================================================================
// Prediction Error Contract
// ============================================================================

export interface PredictionErrorContract {
  /** Schema identifier */
  schemaId: string;
  /** Schema version */
  schemaVersion: string;
  /** Unique identifier for this error */
  id: string;
  /** Actual value x(t) */
  actual: number;
  /** Predicted value x̂(t) */
  predicted: number;
  /** Error value ε(t) = actual - predicted */
  error: number;
  /** Absolute error magnitude */
  absoluteError: number;
  /** Whether this error exceeds the propagation threshold */
  propagated: boolean;
  /** The node this error occurred on */
  node: string;
  /** Timestamp */
  timestamp: number;
  /** Trace context */
  traceId: string;
  /** Weight of this error for learning */
  weight?: number;
  /** Source revision for deterministic replay */
  sourceRevision?: string;
  /** Runtime revision binding */
  runtimeRevision?: string;
  /** Causal tick */
  tick?: number;
  /** Causal sequence number */
  sequence?: number;
}

/**
 * Validate a prediction error contract.
 */
export function validatePredictionError(
  obj: unknown,
  options: { strict?: boolean } = {}
): ValidationResult {
  const { strict = true } = options;
  const errors: ValidationError[] = [];
  const warnings: ValidationWarning[] = [];

  if (typeof obj !== 'object' || obj === null) {
    return {
      valid: false,
      errors: [{
        field: 'root',
        code: 'INVALID_TYPE',
        message: 'PredictionError must be a non-null object',
      }],
      warnings: [],
    };
  }

  const p = obj as Record<string, unknown>;

  // Validate schema binding
  if (p.schemaId !== PREDICTION_ERROR_SCHEMA_ID) {
    errors.push({
      field: 'schemaId',
      code: 'INVALID_SCHEMA',
      message: `Expected schemaId "${PREDICTION_ERROR_SCHEMA_ID}", got "${p.schemaId}"`,
    });
  }

  if (typeof p.schemaVersion !== 'string' || !p.schemaVersion.startsWith('v')) {
    errors.push({
      field: 'schemaVersion',
      code: 'INVALID_VERSION',
      message: 'schemaVersion must be a string starting with "v"',
    });
  }

  // Validate required fields
  for (const field of ['id', 'node', 'traceId']) {
    if (typeof p[field] !== 'string' || (p[field] as string).length === 0) {
      errors.push({
        field,
        code: 'MISSING_OR_EMPTY',
        message: `${field} must be a non-empty string`,
      });
    }
  }

  // Validate boolean field
  if (typeof p.propagated !== 'boolean') {
    errors.push({
      field: 'propagated',
      code: 'INVALID_TYPE',
      message: 'propagated must be a boolean',
    });
  }

  // Validate numeric fields
  const numericFields: Array<{ name: string; min?: number; max?: number }> = [
    { name: 'actual' },
    { name: 'predicted' },
    { name: 'error' },
    { name: 'absoluteError', min: 0 },
    { name: 'timestamp', min: 0 },
    { name: 'weight', min: 0, max: 1 },
    { name: 'tick', min: 0 },
    { name: 'sequence', min: 0 },
  ];

  for (const { name, min, max } of numericFields) {
    if (p[name] !== undefined) {
      const value = p[name];
      if (typeof value !== 'number') {
        errors.push({
          field: name,
          code: 'INVALID_TYPE',
          message: `${name} must be a number`,
        });
      } else if (!Number.isFinite(value)) {
        errors.push({
          field: name,
          code: 'INVALID_NUMBER',
          message: `${name} must be finite (not NaN or Infinity)`,
        });
      } else if (min !== undefined && value < min) {
        errors.push({
          field: name,
          code: 'OUT_OF_RANGE',
          message: `${name} must be >= ${min}`,
        });
      } else if (max !== undefined && value > max) {
        errors.push({
          field: name,
          code: 'OUT_OF_RANGE',
          message: `${name} must be <= ${max}`,
        });
      }
    }
  }

  // Validate absoluteError consistency with error
  if (
    typeof p.absoluteError === 'number' &&
    typeof p.error === 'number' &&
    Number.isFinite(p.absoluteError) &&
    Number.isFinite(p.error)
  ) {
    const expectedAbs = Math.abs(p.error);
    if (Math.abs(p.absoluteError - expectedAbs) > 1e-10) {
      warnings.push({
        field: 'absoluteError',
        message: `absoluteError (${p.absoluteError}) should equal Math.abs(error) (${expectedAbs})`,
      });
    }
  }

  // Strict mode: reject unknown fields
  if (strict) {
    const knownFields = new Set(PREDICTION_ERROR_ALL_FIELDS.map(f => f as string));
    for (const key of Object.keys(p)) {
      if (!knownFields.has(key)) {
        errors.push({
          field: key,
          code: 'UNKNOWN_FIELD',
          message: `Unknown field "${key}" in strict mode`,
        });
      }
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  };
}

// ============================================================================
// Schema Hash Generation
// ============================================================================

/**
 * Simple synchronous hash function for deterministic schema identity.
 * Uses a simple but deterministic algorithm for browser compatibility.
 */
function simpleHash(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  // Convert to hex and pad
  const hex = Math.abs(hash).toString(16).padStart(8, '0');
  return `s${hex}`;
}

/**
 * Generate a deterministic schema hash for a prediction contract.
 * The hash only includes structural fields, not values.
 */
export function generatePredictionSchemaHash(): string {
  const schema = {
    schemaId: PREDICTION_SCHEMA_ID,
    schemaVersion: 'v1',
    fields: PREDICTION_ALL_FIELDS,
  };
  return simpleHash(JSON.stringify(schema));
}

/**
 * Generate a deterministic schema hash for a prediction error contract.
 */
export function generatePredictionErrorSchemaHash(): string {
  const schema = {
    schemaId: PREDICTION_ERROR_SCHEMA_ID,
    schemaVersion: 'v1',
    fields: PREDICTION_ERROR_ALL_FIELDS,
  };
  return simpleHash(JSON.stringify(schema));
}
