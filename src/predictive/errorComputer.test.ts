/**
 * Error Computer Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  ErrorComputer,
  createErrorComputer,
  calculateAccuracy,
  calculateMSE,
  calculateRMSE,
} from './errorComputer';
import type { Signal, Prediction, PredictionError } from './types';

describe('ErrorComputer', () => {
  let errorComputer: ErrorComputer;

  const createSignal = (value: number, node = 'test.node'): Signal => ({
    id: `sig-${Math.random().toString(36).substr(2, 9)}`,
    node,
    value,
    timestamp: Date.now(),
    traceId: `trace-${Math.random().toString(36).substr(2, 9)}`,
  });

  const createPrediction = (
    predictedValue: number,
    confidence = 0.8,
    node = 'test.node',
  ): Prediction => ({
    id: `pred-${Math.random().toString(36).substr(2, 9)}`,
    predictedValue,
    confidence,
    node,
    timestamp: Date.now(),
    traceId: `trace-${Math.random().toString(36).substr(2, 9)}`,
  });

  beforeEach(() => {
    errorComputer = new ErrorComputer({
      threshold: 0.1,
      propagationWeight: 1.0,
      temporalSmoothing: false,
    });
  });

  describe('computeError', () => {
    it('should compute zero error for perfect prediction', () => {
      const signal = createSignal(0.8);
      const prediction = createPrediction(0.8);

      const error = errorComputer.computeError(signal, prediction, 'trace-1');

      expect(error.error).toBeCloseTo(0, 5);
      expect(error.absoluteError).toBeCloseTo(0, 5);
      expect(error.propagated).toBe(false);
    });

    it('should compute positive error when actual > predicted', () => {
      const signal = createSignal(0.9);
      const prediction = createPrediction(0.7);

      const error = errorComputer.computeError(signal, prediction, 'trace-1');

      expect(error.error).toBeCloseTo(0.2, 5);
      expect(error.absoluteError).toBeCloseTo(0.2, 5);
    });

    it('should compute negative error when actual < predicted', () => {
      const signal = createSignal(0.5);
      const prediction = createPrediction(0.8);

      const error = errorComputer.computeError(signal, prediction, 'trace-1');

      expect(error.error).toBeCloseTo(-0.3, 5);
      expect(error.absoluteError).toBeCloseTo(0.3, 5);
    });

    it('should mark error as propagated when above threshold', () => {
      const signal = createSignal(0.9);
      const prediction = createPrediction(0.5);

      const error = errorComputer.computeError(signal, prediction, 'trace-1');

      expect(error.absoluteError).toBe(0.4);
      expect(error.propagated).toBe(true);
    });

    it('should mark error as not propagated when below threshold', () => {
      const signal = createSignal(0.81);
      const prediction = createPrediction(0.8);

      const error = errorComputer.computeError(signal, prediction, 'trace-1');

      expect(error.absoluteError).toBeCloseTo(0.01, 5);
      expect(error.propagated).toBe(false);
    });

    it('should calculate error weight based on magnitude', () => {
      const signal = createSignal(1.0);
      const prediction = createPrediction(0.0);

      const error = errorComputer.computeError(signal, prediction, 'trace-1');

      expect(error.weight).toBeGreaterThan(0);
      expect(error.weight).toBeLessThanOrEqual(1);
    });

    it('should track error in history', () => {
      const signal = createSignal(0.8);
      const prediction = createPrediction(0.6);

      errorComputer.computeError(signal, prediction, 'trace-1');

      const history = errorComputer.getHistory(signal.node);
      expect(history.length).toBe(1);
    });

    it('should limit history size per node', () => {
      // Add 150 errors (history limit is 100)
      for (let i = 0; i < 150; i++) {
        const signal = createSignal(0.8 + i * 0.001);
        const prediction = createPrediction(0.6);
        errorComputer.computeError(signal, prediction, 'trace-1');
      }

      const history = errorComputer.getHistory('test.node');
      expect(history.length).toBe(100);
    });
  });

  describe('getStats', () => {
    it('should track total errors', () => {
      for (let i = 0; i < 5; i++) {
        const signal = createSignal(0.8);
        const prediction = createPrediction(0.6);
        errorComputer.computeError(signal, prediction, `trace-${i}`);
      }

      const stats = errorComputer.getStats();
      expect(stats.totalErrors).toBe(5);
    });

    it('should track propagated vs suppressed errors', () => {
      // 3 propagated (error > 0.1), 2 suppressed (error < 0.1)
      for (let i = 0; i < 3; i++) {
        const signal = createSignal(0.9);
        const prediction = createPrediction(0.5);
        errorComputer.computeError(signal, prediction, `trace-${i}`);
      }

      for (let i = 0; i < 2; i++) {
        const signal = createSignal(0.81);
        const prediction = createPrediction(0.8);
        errorComputer.computeError(signal, prediction, `trace-3-${i}`);
      }

      const stats = errorComputer.getStats();
      expect(stats.propagatedErrors).toBe(3);
      expect(stats.suppressedErrors).toBe(2);
    });

    it('should calculate average error', () => {
      const signals = [createSignal(0.9), createSignal(0.7)];
      const predictions = [createPrediction(0.8), createPrediction(0.6)];

      for (let i = 0; i < signals.length; i++) {
        errorComputer.computeError(signals[i], predictions[i], `trace-${i}`);
      }

      const stats = errorComputer.getStats();
      expect(stats.averageError).toBeCloseTo(0.1, 5); // (0.1 + 0.1) / 2 = 0.1
    });

    it('should track min and max error', () => {
      const signals = [createSignal(0.9), createSignal(0.5), createSignal(0.7)];
      const predictions = [createPrediction(0.8), createPrediction(0.6), createPrediction(0.7)];

      for (let i = 0; i < signals.length; i++) {
        errorComputer.computeError(signals[i], predictions[i], `trace-${i}`);
      }

      const stats = errorComputer.getStats();
      expect(stats.maxError).toBeCloseTo(0.4, 5); // 0.9 - 0.5 = 0.4 (largest negative)
      expect(stats.minError).toBeCloseTo(-0.1, 5); // 0.7 - 0.8 = -0.1 (largest negative)
    });
  });

  describe('getErrorRate', () => {
    it('should calculate error rate', () => {
      for (let i = 0; i < 10; i++) {
        const signal = createSignal(0.9);
        const prediction = createPrediction(i < 7 ? 0.5 : 0.85);
        errorComputer.computeError(signal, prediction, `trace-${i}`);
      }

      expect(errorComputer.getErrorRate()).toBeCloseTo(0.7, 5);
    });

    it('should return 0 for no errors', () => {
      expect(errorComputer.getErrorRate()).toBe(0);
    });
  });

  describe('getSuppressionRate', () => {
    it('should calculate suppression rate', () => {
      for (let i = 0; i < 10; i++) {
        const signal = createSignal(0.9);
        const prediction = createPrediction(i < 3 ? 0.5 : 0.85);
        errorComputer.computeError(signal, prediction, `trace-${i}`);
      }

      expect(errorComputer.getSuppressionRate()).toBeCloseTo(0.3, 5);
    });
  });

  describe('reset', () => {
    it('should clear all history and stats', () => {
      for (let i = 0; i < 5; i++) {
        const signal = createSignal(0.8);
        const prediction = createPrediction(0.6);
        errorComputer.computeError(signal, prediction, `trace-${i}`);
      }

      errorComputer.reset();

      const stats = errorComputer.getStats();
      expect(stats.totalErrors).toBe(0);
      expect(stats.propagatedErrors).toBe(0);
      expect(errorComputer.getErrorRate()).toBe(0);
    });
  });

  describe('setThreshold', () => {
    it('should allow setting new threshold', () => {
      errorComputer.setThreshold(0.2);

      expect(errorComputer.getThreshold()).toBe(0.2);
    });

    it('should enforce minimum threshold of 0', () => {
      errorComputer.setThreshold(-0.5);
      expect(errorComputer.getThreshold()).toBe(0);
    });
  });

  describe('batch processing', () => {
    it('should compute batch errors', () => {
      const pairs = [
        { signal: createSignal(0.9), prediction: createPrediction(0.5) },
        { signal: createSignal(0.81), prediction: createPrediction(0.8) },
        { signal: createSignal(0.7), prediction: createPrediction(0.6) },
      ];

      const errors = errorComputer.computeBatchErrors(pairs, 'trace-batch');

      expect(errors.length).toBe(3);
      expect(errors[0].propagated).toBe(true); // 0.4 > 0.1
      expect(errors[1].propagated).toBe(false); // 0.01 < 0.1
      expect(errors[2].propagated).toBe(true); // 0.1 == 0.1 (boundary case)
    });
  });

  describe('filtering', () => {
    it('should filter propagated errors', () => {
      const errors: PredictionError[] = [
        { id: '1', actual: 0.9, predicted: 0.5, error: 0.4, absoluteError: 0.4, propagated: true, node: 'n', timestamp: 1, traceId: 't', weight: 1 },
        { id: '2', actual: 0.81, predicted: 0.8, error: 0.01, absoluteError: 0.01, propagated: false, node: 'n', timestamp: 1, traceId: 't', weight: 0 },
        { id: '3', actual: 0.7, predicted: 0.5, error: 0.2, absoluteError: 0.2, propagated: true, node: 'n', timestamp: 1, traceId: 't', weight: 0.5 },
      ];

      const propagated = errorComputer.getPropagatedErrors(errors);
      expect(propagated.length).toBe(2);
    });

    it('should get errors above specific threshold', () => {
      const errors: PredictionError[] = [
        { id: '1', actual: 0.9, predicted: 0.5, error: 0.4, absoluteError: 0.4, propagated: true, node: 'n', timestamp: 1, traceId: 't', weight: 1 },
        { id: '2', actual: 0.85, predicted: 0.8, error: 0.05, absoluteError: 0.05, propagated: false, node: 'n', timestamp: 1, traceId: 't', weight: 0 },
        { id: '3', actual: 0.7, predicted: 0.5, error: 0.2, absoluteError: 0.2, propagated: true, node: 'n', timestamp: 1, traceId: 't', weight: 0.5 },
      ];

      const aboveThreshold = errorComputer.getErrorsAboveThreshold(errors, 0.3);
      expect(aboveThreshold.length).toBe(1);
      expect(aboveThreshold[0].id).toBe('1');
    });

    it('should get top errors', () => {
      for (let i = 0; i < 10; i++) {
        const signal = createSignal(0.9 - i * 0.05);
        const prediction = createPrediction(0.5);
        errorComputer.computeError(signal, prediction, `trace-${i}`);
      }

      const topErrors = errorComputer.getTopErrors('test.node', 3);
      expect(topErrors.length).toBe(3);
      // First should have highest absolute error
      expect(topErrors[0].absoluteError).toBeGreaterThanOrEqual(topErrors[1].absoluteError);
    });
  });
});

describe('Utility Functions', () => {
  const createError = (
    error: number,
    absoluteError: number,
  ): PredictionError => ({
    id: `err-${Math.random().toString(36).substr(2, 9)}`,
    actual: 0.8,
    predicted: 0.8 - error,
    error,
    absoluteError,
    propagated: absoluteError > 0.1,
    node: 'test.node',
    timestamp: Date.now(),
    traceId: 'trace-1',
    weight: 0.5,
  });

  describe('calculateAccuracy', () => {
    it('should calculate accuracy for errors within threshold', () => {
      const errors = [
        createError(0.05, 0.05), // accurate
        createError(0.08, 0.08), // accurate
        createError(0.15, 0.15), // inaccurate
        createError(0.02, 0.02), // accurate
      ];

      expect(calculateAccuracy(errors, 0.1)).toBeCloseTo(0.75, 5);
    });

    it('should return 0 for empty errors', () => {
      expect(calculateAccuracy([], 0.1)).toBe(0);
    });
  });

  describe('calculateMSE', () => {
    it('should calculate mean squared error', () => {
      const errors = [
        createError(0.1, 0.1),
        createError(-0.2, 0.2),
        createError(0.3, 0.3),
      ];

      const mse = calculateMSE(errors);
      // (0.01 + 0.04 + 0.09) / 3 = 0.0467
      expect(mse).toBeCloseTo(0.0467, 3);
    });

    it('should return 0 for empty errors', () => {
      expect(calculateMSE([])).toBe(0);
    });
  });

  describe('calculateRMSE', () => {
    it('should calculate root mean squared error', () => {
      const errors = [
        createError(0.1, 0.1),
        createError(0.1, 0.1),
      ];

      const rmse = calculateRMSE(errors);
      // sqrt(0.01) = 0.1
      expect(rmse).toBeCloseTo(0.1, 5);
    });
  });
});

describe('createErrorComputer factory', () => {
  it('should create with custom config', () => {
    const ec = createErrorComputer({
      threshold: 0.05,
      propagationWeight: 0.8,
    });

    expect(ec.getThreshold()).toBe(0.05);
  });
});
