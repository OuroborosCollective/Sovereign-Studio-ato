/**
 * Tests for Feature Vector
 *
 * @module predictive/pipeline/featureVector.test
 */

import { describe, it, expect } from 'vitest';
import {
  computeSignalHash,
  computeMean,
  computeStdDev,
  extractFeatures,
  featuresToVector,
  createFeatureVector,
  createFeatureReceipt,
  processWindowToFeatures,
  computeNodeDeltaFeatures,
  verifyFeatureParity,
} from './featureVector';
import type { OrderedSignal } from './signalOrdering';
import type { TickWindow } from './tickWindow';

function createOrderedSignal(overrides: Partial<OrderedSignal> & { tick: number; sequence: number; revision: string; node: string }): OrderedSignal {
  return {
    id: 'sig-1',
    node: 'node-a',
    value: 1,
    timestamp: Date.now(),
    traceId: 'trace-1',
    metadata: {
      tick: 0,
      sequence: 0,
      revision: 'rev-1',
      node: 'node-a',
    },
    ...overrides,
  } as OrderedSignal;
}

function createTickWindow(signals: OrderedSignal[], overrides: Partial<TickWindow> = {}): TickWindow {
  const ticks = signals.map((s) => s.metadata.tick);
  return {
    id: 'window-1',
    startTick: Math.min(...ticks),
    endTick: Math.max(...ticks),
    signals,
    nodes: [...new Set(signals.map((s) => s.metadata.node))],
    windowIndex: 0,
    configFingerprint: 'ws=3|ov=0',
    isComplete: true,
    ...overrides,
  };
}

describe('featureVector', () => {
  // ========== computeMean ==========
  describe('computeMean', () => {
    it('should compute mean correctly', () => {
      expect(computeMean([1, 2, 3, 4, 5])).toBe(3);
      expect(computeMean([10, 20, 30])).toBe(20);
    });

    it('should return 0 for empty array', () => {
      expect(computeMean([])).toBe(0);
    });
  });

  // ========== computeStdDev ==========
  describe('computeStdDev', () => {
    it('should compute standard deviation correctly', () => {
      // Values: [2, 4, 4, 4, 5, 5, 7, 9] - mean is 5
      // Variance = [(2-5)² + (4-5)² + ...] / (n-1) = 36 / 7 ≈ 5.14
      // StdDev ≈ 2.27
      const result = computeStdDev([2, 4, 4, 4, 5, 5, 7, 9]);
      expect(result).toBeCloseTo(2.27, 1);
    });

    it('should return 0 for single element', () => {
      expect(computeStdDev([5])).toBe(0);
    });

    it('should return 0 for empty array', () => {
      expect(computeStdDev([])).toBe(0);
    });
  });

  // ========== computeSignalHash ==========
  describe('computeSignalHash', () => {
    it('should produce same hash for same signals', () => {
      const signals = [
        createOrderedSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'node-a', value: 1 }),
        createOrderedSignal({ id: '2', tick: 1, sequence: 0, revision: 'rev-1', node: 'node-a', value: 2 }),
      ];

      const hash1 = computeSignalHash(signals);
      const hash2 = computeSignalHash(signals);
      expect(hash1).toBe(hash2);
    });

    it('should produce different hash for different signals', () => {
      const signals1 = [
        createOrderedSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'node-a', value: 1 }),
      ];
      const signals2 = [
        createOrderedSignal({ id: '2', tick: 0, sequence: 0, revision: 'rev-1', node: 'node-a', value: 2 }),
      ];

      const hash1 = computeSignalHash(signals1);
      const hash2 = computeSignalHash(signals2);
      expect(hash1).not.toBe(hash2);
    });

    it('should return "empty" for empty array', () => {
      expect(computeSignalHash([])).toBe('empty');
    });

    it('should be deterministic across calls', () => {
      const signals = [
        createOrderedSignal({ id: '1', tick: 5, sequence: 3, revision: 'rev-abc', node: 'node-x', value: 42 }),
      ];

      const hashes = [computeSignalHash(signals), computeSignalHash(signals), computeSignalHash(signals)];
      expect(new Set(hashes).size).toBe(1);
    });
  });

  // ========== extractFeatures ==========
  describe('extractFeatures', () => {
    it('should extract features from window', () => {
      const signals = [
        createOrderedSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'node-a', value: 10 }),
        createOrderedSignal({ id: '2', tick: 1, sequence: 0, revision: 'rev-1', node: 'node-a', value: 20 }),
        createOrderedSignal({ id: '3', tick: 2, sequence: 0, revision: 'rev-1', node: 'node-a', value: 30 }),
      ];
      const window = createTickWindow(signals);

      const features = extractFeatures(window);

      expect(features.mean).toBe(20);
      expect(features.min).toBe(10);
      expect(features.max).toBe(30);
      expect(features.range).toBe(20);
      expect(features.sum).toBe(60);
      expect(features.deltas).toEqual([10, 10]); // Running difference
      expect(features.cumulativeSum).toEqual([10, 30, 60]); // Running total
    });

    it('should handle empty window', () => {
      const window = createTickWindow([]);
      const features = extractFeatures(window);

      expect(features.mean).toBe(0);
      expect(features.signalHash).toBe('empty');
    });

    it('should compute per-node statistics', () => {
      const signals = [
        createOrderedSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'node-a', value: 10 }),
        createOrderedSignal({ id: '2', tick: 0, sequence: 1, revision: 'rev-1', node: 'node-b', value: 20 }),
        createOrderedSignal({ id: '3', tick: 1, sequence: 0, revision: 'rev-1', node: 'node-a', value: 15 }),
        createOrderedSignal({ id: '4', tick: 1, sequence: 1, revision: 'rev-1', node: 'node-b', value: 25 }),
      ];
      const window = createTickWindow(signals);

      const features = extractFeatures(window);

      expect(features.nodeStats.get('node-a')).toEqual({
        mean: 12.5,
        stdDev: 2.5,
        count: 2,
      });
      expect(features.nodeStats.get('node-b')).toEqual({
        mean: 22.5,
        stdDev: 2.5,
        count: 2,
      });
    });
  });

  // ========== featuresToVector ==========
  describe('featuresToVector', () => {
    it('should convert features to flat vector', () => {
      const signals = [
        createOrderedSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'node-a', value: 10 }),
        createOrderedSignal({ id: '2', tick: 1, sequence: 0, revision: 'rev-1', node: 'node-a', value: 20 }),
      ];
      const window = createTickWindow(signals);
      const features = extractFeatures(window);

      const vector = featuresToVector(features, {
        includeStats: true,
        includeDeltas: true,
        includeTemporal: true,
        histogramBins: 0,
      });

      expect(vector.length).toBeGreaterThan(0);
      expect(vector[0]).toBe(features.mean);
    });
  });

  // ========== processWindowToFeatures ==========
  describe('processWindowToFeatures', () => {
    it('should process window and generate all outputs', () => {
      const signals = [
        createOrderedSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'node-a', value: 5 }),
      ];
      const window = createTickWindow(signals);

      const result = processWindowToFeatures(window, false);

      expect(result.features).toBeDefined();
      expect(result.featureVector).toBeDefined();
      expect(result.receipt).toBeDefined();
      expect(result.receipt.isReplay).toBe(false);
    });

    it('should set isReplay flag correctly', () => {
      const signals = [
        createOrderedSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'node-a', value: 5 }),
      ];
      const window = createTickWindow(signals);

      const liveResult = processWindowToFeatures(window, false);
      const replayResult = processWindowToFeatures(window, true);

      expect(liveResult.receipt.isReplay).toBe(false);
      expect(replayResult.receipt.isReplay).toBe(true);
    });
  });

  // ========== verifyFeatureParity ==========
  describe('verifyFeatureParity', () => {
    it('should verify identical vectors as equal', () => {
      const vec1 = {
        values: [1, 2, 3],
        signalHash: 'abc123',
        tickRange: [0, 5] as [number, number],
        sequenceRange: [0, 10] as [number, number],
        revision: 'rev-1',
        configFingerprint: 'ws=3|ov=0',
      };

      const vec2 = {
        values: [1, 2, 3],
        signalHash: 'abc123',
        tickRange: [0, 5] as [number, number],
        sequenceRange: [0, 10] as [number, number],
        revision: 'rev-1',
        configFingerprint: 'ws=3|ov=0',
      };

      const result = verifyFeatureParity(vec1, vec2);
      expect(result.equal).toBe(true);
    });

    it('should detect signal hash mismatch', () => {
      const vec1 = {
        values: [1, 2, 3],
        signalHash: 'abc123',
        tickRange: [0, 5] as [number, number],
        sequenceRange: [0, 10] as [number, number],
        revision: 'rev-1',
        configFingerprint: 'ws=3|ov=0',
      };

      const vec2 = {
        values: [1, 2, 3],
        signalHash: 'xyz789',
        tickRange: [0, 5] as [number, number],
        sequenceRange: [0, 10] as [number, number],
        revision: 'rev-1',
        configFingerprint: 'ws=3|ov=0',
      };

      const result = verifyFeatureParity(vec1, vec2);
      expect(result.equal).toBe(false);
      expect(result.diff).toContain('Signal hash mismatch');
    });

    it('should detect tick range mismatch', () => {
      const vec1 = {
        values: [1, 2, 3],
        signalHash: 'abc123',
        tickRange: [0, 5] as [number, number],
        sequenceRange: [0, 10] as [number, number],
        revision: 'rev-1',
        configFingerprint: 'ws=3|ov=0',
      };

      const vec2 = {
        values: [1, 2, 3],
        signalHash: 'abc123',
        tickRange: [0, 10] as [number, number],
        sequenceRange: [0, 10] as [number, number],
        revision: 'rev-1',
        configFingerprint: 'ws=3|ov=0',
      };

      const result = verifyFeatureParity(vec1, vec2);
      expect(result.equal).toBe(false);
      expect(result.diff).toContain('Tick range mismatch');
    });

    it('should detect revision mismatch', () => {
      const vec1 = {
        values: [1, 2, 3],
        signalHash: 'abc123',
        tickRange: [0, 5] as [number, number],
        sequenceRange: [0, 10] as [number, number],
        revision: 'rev-1',
        configFingerprint: 'ws=3|ov=0',
      };

      const vec2 = {
        values: [1, 2, 3],
        signalHash: 'abc123',
        tickRange: [0, 5] as [number, number],
        sequenceRange: [0, 10] as [number, number],
        revision: 'rev-2',
        configFingerprint: 'ws=3|ov=0',
      };

      const result = verifyFeatureParity(vec1, vec2);
      expect(result.equal).toBe(false);
      expect(result.diff).toContain('Revision mismatch');
    });
  });
});
