/**
 * Prediction Generator Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { PredictionGenerator, createPredictionGenerator } from './predictionGenerator';
import { LatentSpaceNavigator } from './latentSpace';
import type { Signal, PatternEmbedding } from './types';

describe('PredictionGenerator', () => {
  let generator: PredictionGenerator;
  let latentSpace: LatentSpaceNavigator;

  beforeEach(() => {
    latentSpace = new LatentSpaceNavigator({
      dimension: 64,
      maxPatterns: 100,
      similarityThreshold: 0.7,
    });

    generator = new PredictionGenerator({
      latentSpace,
      defaultConfidence: 0.5,
      minSimilarityThreshold: 0.7,
    });
  });

  describe('generatePrediction', () => {
    it('should generate a prediction for a signal', async () => {
      const signal: Signal = {
        id: 'sig-1',
        node: 'runtime.decision',
        value: 0.8,
        timestamp: Date.now(),
        traceId: 'trace-1',
      };

      const prediction = await generator.generatePrediction(signal, 'trace-1');

      expect(prediction.id).toBeDefined();
      expect(prediction.predictedValue).toBeDefined();
      expect(prediction.confidence).toBeGreaterThanOrEqual(0);
      expect(prediction.confidence).toBeLessThanOrEqual(1);
      expect(prediction.node).toBe('runtime.decision');
      expect(prediction.traceId).toBe('trace-1');
    });

    it('should use latent space patterns when available', async () => {
      // Add a pattern to latent space
      const pattern: PatternEmbedding = {
        id: 'pattern-1',
        embedding: new Array(64).fill(0.8),
        norm: 1,
        signalValue: 0.8,
        node: 'runtime.decision',
        createdAt: Date.now(),
        matchCount: 0,
        avgConfidence: 0.9,
      };
      latentSpace.addPattern(pattern);

      const signal: Signal = {
        id: 'sig-1',
        node: 'runtime.decision',
        value: 0.8,
        timestamp: Date.now(),
        traceId: 'trace-1',
      };

      const prediction = await generator.generatePrediction(signal, 'trace-1');

      // Should have used pattern
      expect(prediction.patternId).toBe('pattern-1');
      expect(prediction.confidence).toBeGreaterThan(0.5);
    });

    it('should fall back to network prediction when no patterns', async () => {
      const signal: Signal = {
        id: 'sig-1',
        node: 'runtime.decision',
        value: 0.8,
        timestamp: Date.now(),
        traceId: 'trace-1',
      };

      const prediction = await generator.generatePrediction(signal, 'trace-1');

      // Should use default confidence
      expect(prediction.confidence).toBe(0.5);
    });

    it('should store prediction in history', async () => {
      const signal: Signal = {
        id: 'sig-1',
        node: 'runtime.decision',
        value: 0.8,
        timestamp: Date.now(),
        traceId: 'trace-1',
      };

      await generator.generatePrediction(signal, 'trace-1');

      const history = generator.getHistory('runtime.decision');
      expect(history.length).toBe(1);
    });

    it('should limit history size', async () => {
      // Generate more than 100 predictions
      for (let i = 0; i < 150; i++) {
        const signal: Signal = {
          id: `sig-${i}`,
          node: 'runtime.decision',
          value: 0.8,
          timestamp: Date.now(),
          traceId: `trace-${i}`,
        };
        await generator.generatePrediction(signal, `trace-${i}`);
      }

      const history = generator.getHistory('runtime.decision');
      expect(history.length).toBe(100);
    });
  });

  describe('generateBatchPredictions', () => {
    it('should generate predictions for multiple signals', async () => {
      const signals: Signal[] = [
        { id: 'sig-1', node: 'node-a', value: 0.5, timestamp: Date.now(), traceId: 't1' },
        { id: 'sig-2', node: 'node-b', value: 0.6, timestamp: Date.now(), traceId: 't2' },
        { id: 'sig-3', node: 'node-c', value: 0.7, timestamp: Date.now(), traceId: 't3' },
      ];

      const predictions = await generator.generateBatchPredictions(signals, 'trace-batch');

      expect(predictions.length).toBe(3);
      expect(predictions[0].node).toBe('node-a');
      expect(predictions[1].node).toBe('node-b');
      expect(predictions[2].node).toBe('node-c');
    });
  });

  describe('learn', () => {
    it('should add pattern to latent space', async () => {
      const signal: Signal = {
        id: 'sig-1',
        node: 'runtime.decision',
        value: 0.8,
        timestamp: Date.now(),
        traceId: 'trace-1',
      };

      const prediction = await generator.generatePrediction(signal, 'trace-1');

      generator.learn(signal, prediction, 0.85);

      const patternCount = latentSpace.getPatternCount();
      expect(patternCount).toBeGreaterThan(0);
    });
  });

  describe('getStats', () => {
    it('should return generator statistics', async () => {
      // Add some predictions
      for (let i = 0; i < 5; i++) {
        const signal: Signal = {
          id: `sig-${i}`,
          node: 'runtime.decision',
          value: 0.8,
          timestamp: Date.now(),
          traceId: `trace-${i}`,
        };
        await generator.generatePrediction(signal, `trace-${i}`);
      }

      const stats = generator.getStats();

      expect(stats.totalPredictions).toBe(5);
      expect(stats.patternCount).toBe(0); // No patterns added via learn
    });
  });

  describe('clearHistory', () => {
    it('should clear all prediction history', async () => {
      // Add some predictions
      for (let i = 0; i < 3; i++) {
        const signal: Signal = {
          id: `sig-${i}`,
          node: 'runtime.decision',
          value: 0.8,
          timestamp: Date.now(),
          traceId: `trace-${i}`,
        };
        await generator.generatePrediction(signal, `trace-${i}`);
      }

      expect(generator.getHistory('runtime.decision').length).toBe(3);

      generator.clearHistory();

      expect(generator.getHistory('runtime.decision').length).toBe(0);
    });
  });
});

describe('createPredictionGenerator factory', () => {
  it('should create generator with default config', () => {
    const generator = createPredictionGenerator();
    expect(generator).toBeDefined();
  });

  it('should create generator with custom config', () => {
    const generator = createPredictionGenerator({
      defaultConfidence: 0.7,
      minSimilarityThreshold: 0.8,
    });
    expect(generator).toBeDefined();
  });
});
