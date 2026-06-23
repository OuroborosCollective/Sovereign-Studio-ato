/**
 * Predictive Layer Types Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  isValidSignal,
  isValidPrediction,
  isValidSynapse,
  DEFAULT_HEBBIAN_CONFIG,
  DEFAULT_PREDICTIVE_CONFIG,
  type Signal,
  type Prediction,
  type Synapse,
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
