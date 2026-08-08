/**
 * Predictive Layer Types Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  isValidSignal,
  isValidPrediction,
  isValidSynapse,
  isValidPredictionError,
  DEFAULT_HEBBIAN_CONFIG,
  DEFAULT_PREDICTIVE_CONFIG,
  type Signal,
  type Prediction,
  type Synapse,
  type PredictionError,
} from './types';

describe('Type Validation', () => {
  describe('isValidSignal', () => {
    it('should return true for valid signal', () => {
      const signal: Signal = {
        id: 'sig-123',
        node: 'runtime.decision',
        value: 0.85,
        timestamp: Date.now(),
        traceId: 'trace-456',
      };
      expect(isValidSignal(signal)).toBe(true);
    });

    it('should return false for null', () => {
      expect(isValidSignal(null)).toBe(false);
    });

    it('should return false for non-object', () => {
      expect(isValidSignal('not an object')).toBe(false);
    });

    it('should return false for signal with invalid id', () => {
      const signal = {
        id: 123, // should be string
        node: 'runtime.decision',
        value: 0.85,
        timestamp: Date.now(),
        traceId: 'trace-456',
      };
      expect(isValidSignal(signal)).toBe(false);
    });

    it('should return false for signal with NaN value', () => {
      const signal = {
        id: 'sig-123',
        node: 'runtime.decision',
        value: NaN,
        timestamp: Date.now(),
        traceId: 'trace-456',
      };
      expect(isValidSignal(signal)).toBe(false);
    });

    it('should return false for signal with negative timestamp', () => {
      const signal = {
        id: 'sig-123',
        node: 'runtime.decision',
        value: 0.85,
        timestamp: -1,
        traceId: 'trace-456',
      };
      expect(isValidSignal(signal)).toBe(false);
    });

    it('should return true for signal with optional metadata', () => {
      const signal: Signal = {
        id: 'sig-123',
        node: 'runtime.decision',
        value: 0.85,
        timestamp: Date.now(),
        traceId: 'trace-456',
        metadata: { type: 'container_decision' },
      };
      expect(isValidSignal(signal)).toBe(true);
    });
  });

  describe('isValidPrediction', () => {
    it('should return true for valid prediction', () => {
      const prediction: Prediction = {
        id: 'pred-123',
        predictedValue: 0.75,
        confidence: 0.85,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
      };
      expect(isValidPrediction(prediction)).toBe(true);
    });

    it('should return false for prediction with confidence > 1', () => {
      const prediction = {
        id: 'pred-123',
        predictedValue: 0.75,
        confidence: 1.5,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
      };
      expect(isValidPrediction(prediction)).toBe(false);
    });

    it('should return false for prediction with negative confidence', () => {
      const prediction = {
        id: 'pred-123',
        predictedValue: 0.75,
        confidence: -0.1,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
      };
      expect(isValidPrediction(prediction)).toBe(false);
    });

    it('should return true for prediction with optional fields', () => {
      const prediction: Prediction = {
        id: 'pred-123',
        predictedValue: 0.75,
        confidence: 0.85,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        patternId: 'pattern-789',
        embedding: [0.1, 0.2, 0.3],
      };
      expect(isValidPrediction(prediction)).toBe(true);
    });
  });

  describe('isValidSynapse', () => {
    it('should return true for valid synapse', () => {
      const synapse: Synapse = {
        id: 'syn-123',
        sourceNode: 'node-a',
        targetNode: 'node-b',
        weight: 0.5,
        lastUpdate: Date.now(),
        activationCount: 10,
        weightDelta: 0.01,
      };
      expect(isValidSynapse(synapse)).toBe(true);
    });

    it('should return false for synapse with weight > 1', () => {
      const synapse = {
        id: 'syn-123',
        sourceNode: 'node-a',
        targetNode: 'node-b',
        weight: 1.5,
        lastUpdate: Date.now(),
        activationCount: 10,
        weightDelta: 0.01,
      };
      expect(isValidSynapse(synapse)).toBe(false);
    });

    it('should return false for synapse with negative weight', () => {
      const synapse = {
        id: 'syn-123',
        sourceNode: 'node-a',
        targetNode: 'node-b',
        weight: -0.1,
        lastUpdate: Date.now(),
        activationCount: 10,
        weightDelta: 0.01,
      };
      expect(isValidSynapse(synapse)).toBe(false);
    });
  });

  describe('isValidPredictionError', () => {
    it('should return true for valid prediction error', () => {
      const error: PredictionError = {
        id: 'err-123',
        actual: 0.85,
        predicted: 0.75,
        error: 0.10,
        absoluteError: 0.10,
        propagated: true,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        weight: 0.5,
      };
      expect(isValidPredictionError(error)).toBe(true);
    });

    it('should return false for null', () => {
      expect(isValidPredictionError(null)).toBe(false);
    });

    it('should return false for non-object', () => {
      expect(isValidPredictionError('not an object')).toBe(false);
    });

    it('should return false for missing required fields', () => {
      const error = {
        id: 'err-123',
        actual: 0.85,
        // missing predicted, error, absoluteError, propagated, node, timestamp, traceId, weight
      };
      expect(isValidPredictionError(error)).toBe(false);
    });

    it('should return false for unknown fields (strict mode)', () => {
      const error = {
        id: 'err-123',
        actual: 0.85,
        predicted: 0.75,
        error: 0.10,
        absoluteError: 0.10,
        propagated: true,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        weight: 0.5,
        unknownField: 'should reject',
      };
      expect(isValidPredictionError(error)).toBe(false);
    });

    it('should return false for NaN actual value', () => {
      const error = {
        id: 'err-123',
        actual: NaN,
        predicted: 0.75,
        error: 0.10,
        absoluteError: 0.10,
        propagated: true,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        weight: 0.5,
      };
      expect(isValidPredictionError(error)).toBe(false);
    });

    it('should return false for Infinity actual value', () => {
      const error = {
        id: 'err-123',
        actual: Infinity,
        predicted: 0.75,
        error: 0.10,
        absoluteError: 0.10,
        propagated: true,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        weight: 0.5,
      };
      expect(isValidPredictionError(error)).toBe(false);
    });

    it('should return false for -Infinity predicted value', () => {
      const error = {
        id: 'err-123',
        actual: 0.85,
        predicted: -Infinity,
        error: 0.10,
        absoluteError: 0.10,
        propagated: true,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        weight: 0.5,
      };
      expect(isValidPredictionError(error)).toBe(false);
    });

    it('should return false for negative zero actual value', () => {
      const error = {
        id: 'err-123',
        actual: -0, // negative zero
        predicted: 0.75,
        error: 0.10,
        absoluteError: 0.10,
        propagated: true,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        weight: 0.5,
      };
      expect(isValidPredictionError(error)).toBe(false);
    });

    it('should return false for negative zero error value', () => {
      const error = {
        id: 'err-123',
        actual: 0.85,
        predicted: 0.75,
        error: -0, // negative zero
        absoluteError: 0.10,
        propagated: true,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        weight: 0.5,
      };
      expect(isValidPredictionError(error)).toBe(false);
    });

    it('should return false for weight > 1', () => {
      const error = {
        id: 'err-123',
        actual: 0.85,
        predicted: 0.75,
        error: 0.10,
        absoluteError: 0.10,
        propagated: true,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        weight: 1.5,
      };
      expect(isValidPredictionError(error)).toBe(false);
    });

    it('should return false for negative weight', () => {
      const error = {
        id: 'err-123',
        actual: 0.85,
        predicted: 0.75,
        error: 0.10,
        absoluteError: 0.10,
        propagated: true,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        weight: -0.1,
      };
      expect(isValidPredictionError(error)).toBe(false);
    });

    it('should return false for non-positive timestamp', () => {
      const error = {
        id: 'err-123',
        actual: 0.85,
        predicted: 0.75,
        error: 0.10,
        absoluteError: 0.10,
        propagated: true,
        node: 'runtime.decision',
        timestamp: 0,
        traceId: 'trace-456',
        weight: 0.5,
      };
      expect(isValidPredictionError(error)).toBe(false);
    });

    it('should return false for negative timestamp', () => {
      const error = {
        id: 'err-123',
        actual: 0.85,
        predicted: 0.75,
        error: 0.10,
        absoluteError: 0.10,
        propagated: true,
        node: 'runtime.decision',
        timestamp: -1,
        traceId: 'trace-456',
        weight: 0.5,
      };
      expect(isValidPredictionError(error)).toBe(false);
    });

    it('should return false for propagated not being boolean', () => {
      const error = {
        id: 'err-123',
        actual: 0.85,
        predicted: 0.75,
        error: 0.10,
        absoluteError: 0.10,
        propagated: 'true', // should be boolean
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        weight: 0.5,
      };
      expect(isValidPredictionError(error)).toBe(false);
    });

    it('should accept zero for actual/predicted/error (non-negative zero)', () => {
      const error: PredictionError = {
        id: 'err-123',
        actual: 0, // positive zero is OK
        predicted: 0,
        error: 0,
        absoluteError: 0,
        propagated: false,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        weight: 0,
      };
      expect(isValidPredictionError(error)).toBe(true);
    });

    it('should accept weight of exactly 0 and 1', () => {
      const errorMin: PredictionError = {
        id: 'err-123',
        actual: 0.5,
        predicted: 0.5,
        error: 0,
        absoluteError: 0,
        propagated: false,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        weight: 0,
      };
      expect(isValidPredictionError(errorMin)).toBe(true);

      const errorMax: PredictionError = {
        id: 'err-456',
        actual: 1,
        predicted: 1,
        error: 0,
        absoluteError: 0,
        propagated: true,
        node: 'runtime.decision',
        timestamp: Date.now(),
        traceId: 'trace-456',
        weight: 1,
      };
      expect(isValidPredictionError(errorMax)).toBe(true);
    });
  });
});

describe('Default Configurations', () => {
  describe('DEFAULT_HEBBIAN_CONFIG', () => {
    it('should have valid learning rate', () => {
      expect(DEFAULT_HEBBIAN_CONFIG.learningRate).toBeGreaterThan(0);
      expect(DEFAULT_HEBBIAN_CONFIG.learningRate).toBeLessThanOrEqual(1);
    });

    it('should have valid weight bounds', () => {
      expect(DEFAULT_HEBBIAN_CONFIG.weightBounds.min).toBe(0);
      expect(DEFAULT_HEBBIAN_CONFIG.weightBounds.max).toBe(1);
      expect(DEFAULT_HEBBIAN_CONFIG.weightBounds.min).toBeLessThan(DEFAULT_HEBBIAN_CONFIG.weightBounds.max);
    });

    it('should have valid decay factor', () => {
      expect(DEFAULT_HEBBIAN_CONFIG.decayFactor).toBeGreaterThan(0);
      expect(DEFAULT_HEBBIAN_CONFIG.decayFactor).toBeLessThanOrEqual(1);
    });

    it('should have valid min weight for pruning', () => {
      expect(DEFAULT_HEBBIAN_CONFIG.minWeight).toBeGreaterThanOrEqual(0);
      expect(DEFAULT_HEBBIAN_CONFIG.minWeight).toBeLessThan(1);
    });
  });

  describe('DEFAULT_PREDICTIVE_CONFIG', () => {
    it('should be enabled by default', () => {
      expect(DEFAULT_PREDICTIVE_CONFIG.enabled).toBe(true);
    });

    it('should have valid signal config', () => {
      expect(DEFAULT_PREDICTIVE_CONFIG.signal.batchSize).toBeGreaterThan(0);
      expect(DEFAULT_PREDICTIVE_CONFIG.signal.flushIntervalMs).toBeGreaterThanOrEqual(0);
      expect(DEFAULT_PREDICTIVE_CONFIG.signal.maxBufferSize).toBeGreaterThan(0);
    });

    it('should have valid latent space config', () => {
      expect(DEFAULT_PREDICTIVE_CONFIG.latentSpace.dimension).toBeGreaterThan(0);
      expect(DEFAULT_PREDICTIVE_CONFIG.latentSpace.maxPatterns).toBeGreaterThan(0);
      expect(DEFAULT_PREDICTIVE_CONFIG.latentSpace.similarityThreshold).toBeGreaterThan(0);
      expect(DEFAULT_PREDICTIVE_CONFIG.latentSpace.similarityThreshold).toBeLessThanOrEqual(1);
    });

    it('should have valid error threshold', () => {
      expect(DEFAULT_PREDICTIVE_CONFIG.error.threshold).toBeGreaterThanOrEqual(0);
      expect(DEFAULT_PREDICTIVE_CONFIG.error.threshold).toBeLessThan(1);
    });

    it('should have valid network config', () => {
      expect(DEFAULT_PREDICTIVE_CONFIG.network.maxConnectionsPerNode).toBeGreaterThan(0);
      expect(DEFAULT_PREDICTIVE_CONFIG.network.correlationThreshold).toBeGreaterThan(0);
      expect(DEFAULT_PREDICTIVE_CONFIG.network.correlationThreshold).toBeLessThanOrEqual(1);
    });
  });
});
