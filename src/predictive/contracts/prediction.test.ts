/**
 * Prediction Contract Tests
 */

import {
  validatePrediction,
  validatePredictionError,
  PREDICTION_SCHEMA_ID,
  PREDICTION_ERROR_SCHEMA_ID,
  generatePredictionSchemaHash,
  generatePredictionErrorSchemaHash,
} from './prediction';

describe('Prediction Contract', () => {
  const validPrediction = {
    schemaId: 'prediction-result.v1',
    schemaVersion: 'v1',
    id: 'pred-001',
    predictedValue: 42.5,
    confidence: 0.85,
    node: 'sensor-1',
    timestamp: 1234567890,
    traceId: 'trace-abc',
  };

  describe('validatePrediction', () => {
    it('accepts valid prediction', () => {
      const result = validatePrediction(validPrediction);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('rejects non-object input', () => {
      const result = validatePrediction(null);
      expect(result.valid).toBe(false);
      expect(result.errors[0].code).toBe('INVALID_TYPE');
    });

    it('rejects wrong schemaId', () => {
      const result = validatePrediction({ ...validPrediction, schemaId: 'wrong-schema' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'schemaId')).toBe(true);
    });

    it('rejects invalid schemaVersion', () => {
      const result = validatePrediction({ ...validPrediction, schemaVersion: '1.0' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'schemaVersion')).toBe(true);
    });

    it('rejects missing required string fields', () => {
      const result = validatePrediction({ ...validPrediction, id: '' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'id')).toBe(true);
    });

    it('rejects NaN in numeric fields', () => {
      const result = validatePrediction({ ...validPrediction, predictedValue: NaN });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'predictedValue')).toBe(true);
    });

    it('rejects Infinity in numeric fields', () => {
      const result = validatePrediction({ ...validPrediction, predictedValue: Infinity });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'predictedValue')).toBe(true);
    });

    it('rejects confidence out of range', () => {
      const result = validatePrediction({ ...validPrediction, confidence: 1.5 });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'confidence')).toBe(true);
    });

    it('rejects negative confidence', () => {
      const result = validatePrediction({ ...validPrediction, confidence: -0.1 });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'confidence')).toBe(true);
    });

    it('accepts valid embedding', () => {
      const result = validatePrediction({
        ...validPrediction,
        embedding: [0.1, 0.2, 0.3, 0.4],
      });
      expect(result.valid).toBe(true);
    });

    it('rejects embedding with NaN', () => {
      const result = validatePrediction({
        ...validPrediction,
        embedding: [0.1, NaN, 0.3],
      });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field.startsWith('embedding'))).toBe(true);
    });

    it('rejects unknown fields in strict mode', () => {
      const result = validatePrediction({ ...validPrediction, unknownField: 'value' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === 'UNKNOWN_FIELD')).toBe(true);
    });

    it('accepts unknown fields in non-strict mode', () => {
      const result = validatePrediction({ ...validPrediction, unknownField: 'value' }, { strict: false });
      expect(result.valid).toBe(true);
    });

    it('warns about large embeddings', () => {
      const largeEmbedding = new Array(10001).fill(0.1);
      const result = validatePrediction({ ...validPrediction, embedding: largeEmbedding });
      expect(result.valid).toBe(true); // Still valid, but warns
      expect(result.warnings.length).toBeGreaterThan(0);
    });

    it('accepts optional causal fields', () => {
      const result = validatePrediction({
        ...validPrediction,
        tick: 100,
        sequence: 5,
        sourceRevision: 'abc123',
        runtimeRevision: 'def456',
      });
      expect(result.valid).toBe(true);
    });
  });
});

describe('PredictionError Contract', () => {
  const validError = {
    schemaId: 'prediction-error.v1',
    schemaVersion: 'v1',
    id: 'err-001',
    actual: 10,
    predicted: 8,
    error: 2,
    absoluteError: 2,
    propagated: true,
    node: 'sensor-1',
    timestamp: 1234567890,
    traceId: 'trace-abc',
  };

  describe('validatePredictionError', () => {
    it('accepts valid prediction error', () => {
      const result = validatePredictionError(validError);
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('rejects non-object input', () => {
      const result = validatePredictionError(null);
      expect(result.valid).toBe(false);
      expect(result.errors[0].code).toBe('INVALID_TYPE');
    });

    it('rejects wrong schemaId', () => {
      const result = validatePredictionError({ ...validError, schemaId: 'wrong' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'schemaId')).toBe(true);
    });

    it('rejects non-boolean propagated', () => {
      const result = validatePredictionError({ ...validError, propagated: 'true' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'propagated')).toBe(true);
    });

    it('rejects negative absoluteError', () => {
      const result = validatePredictionError({ ...validError, absoluteError: -1 });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'absoluteError')).toBe(true);
    });

    it('warns about inconsistent absoluteError', () => {
      const result = validatePredictionError({ ...validError, absoluteError: 100 });
      expect(result.valid).toBe(true);
      expect(result.warnings.some(w => w.field === 'absoluteError')).toBe(true);
    });

    it('accepts optional weight', () => {
      const result = validatePredictionError({ ...validError, weight: 0.5 });
      expect(result.valid).toBe(true);
    });

    it('rejects weight out of range', () => {
      const result = validatePredictionError({ ...validError, weight: 2 });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.field === 'weight')).toBe(true);
    });

    it('rejects unknown fields in strict mode', () => {
      const result = validatePredictionError({ ...validError, extra: 'data' });
      expect(result.valid).toBe(false);
      expect(result.errors.some(e => e.code === 'UNKNOWN_FIELD')).toBe(true);
    });
  });
});

describe('Schema Hash Generation', () => {
  it('generates consistent prediction schema hash', () => {
    const hash1 = generatePredictionSchemaHash();
    const hash2 = generatePredictionSchemaHash();
    expect(hash1).toBe(hash2);
    expect(hash1).toMatch(/^s[0-9a-f]{8}$/);
  });

  it('generates consistent prediction error schema hash', () => {
    const hash1 = generatePredictionErrorSchemaHash();
    const hash2 = generatePredictionErrorSchemaHash();
    expect(hash1).toBe(hash2);
    expect(hash1).toMatch(/^s[0-9a-f]{8}$/);
  });

  it('generates different hashes for prediction and error', () => {
    const predHash = generatePredictionSchemaHash();
    const errHash = generatePredictionErrorSchemaHash();
    expect(predHash).not.toBe(errHash);
  });
});
