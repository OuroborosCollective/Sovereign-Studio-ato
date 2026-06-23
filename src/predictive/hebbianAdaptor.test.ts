/**
 * Hebbian Adaptor Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  HebbianAdaptor,
  createHebbianAdaptor,
  Synaptogenesis,
} from './hebbianAdaptor';
import type { Synapse, PredictionError, NeuralNode } from './types';

describe('HebbianAdaptor', () => {
  let adaptor: HebbianAdaptor;

  beforeEach(() => {
    adaptor = createHebbianAdaptor({
      learningRate: 0.1,
      decayFactor: 0.99,
      maxWeight: 1.0,
      minWeight: 0.05,
      dampingFactor: 0.9,
    });
  });

  describe('registerSynapse', () => {
    it('should register a synapse', () => {
      const synapse: Synapse = {
        id: 'syn-1',
        sourceNode: 'node-a',
        targetNode: 'node-b',
        weight: 0.5,
        lastUpdate: Date.now(),
        activationCount: 0,
        weightDelta: 0,
      };

      adaptor.registerSynapse(synapse);

      const retrieved = adaptor.getSynapse('syn-1');
      expect(retrieved).toBeDefined();
      expect(retrieved!.weight).toBe(0.5);
    });
  });

  describe('registerNode', () => {
    it('should register a neural node', () => {
      const node: NeuralNode = {
        id: 'node-1',
        name: 'Test Node',
        activation: 0.5,
        previousActivation: 0.4,
        outgoingSynapses: [],
        incomingSynapses: [],
        signalHistory: [],
        predictionHistory: [],
        errorHistory: [],
        nodeType: 'sensor',
        lastActivity: Date.now(),
      };

      adaptor.registerNode(node);

      const synapses = adaptor.getIncomingSynapses('node-1');
      expect(synapses).toBeDefined();
    });
  });

  describe('updateWeight', () => {
    it('should update weight based on error', () => {
      const synapse: Synapse = {
        id: 'syn-1',
        sourceNode: 'node-a',
        targetNode: 'node-b',
        weight: 0.5,
        lastUpdate: Date.now(),
        activationCount: 0,
        weightDelta: 0,
      };
      adaptor.registerSynapse(synapse);

      const error: PredictionError = {
        id: 'err-1',
        actual: 0.8,
        predicted: 0.5,
        error: 0.3,
        absoluteError: 0.3,
        propagated: true,
        node: 'node-b',
        timestamp: Date.now(),
        traceId: 'trace-1',
        weight: 0.5,
      };

      const result = adaptor.updateWeight('syn-1', error, 0.6);

      expect(result).not.toBeNull();
      expect(result!.previousWeight).toBe(0.5);
      expect(result!.newWeight).not.toBe(0.5);
      expect(adaptor.getSynapse('syn-1')!.activationCount).toBe(1);
    });

    it('should clamp weight to bounds', () => {
      const synapse: Synapse = {
        id: 'syn-1',
        sourceNode: 'node-a',
        targetNode: 'node-b',
        weight: 0.99,
        lastUpdate: Date.now(),
        activationCount: 0,
        weightDelta: 0,
      };
      adaptor.registerSynapse(synapse);

      const error: PredictionError = {
        id: 'err-1',
        actual: 1.0,
        predicted: 0.0,
        error: 1.0,
        absoluteError: 1.0,
        propagated: true,
        node: 'node-b',
        timestamp: Date.now(),
        traceId: 'trace-1',
        weight: 1.0,
      };

      // Update many times to try to exceed bounds
      for (let i = 0; i < 100; i++) {
        adaptor.updateWeight('syn-1', error, 1.0);
      }

      const weight = adaptor.getSynapse('syn-1')!.weight;
      expect(weight).toBeLessThanOrEqual(1.0);
      expect(weight).toBeGreaterThanOrEqual(0.0);
    });

    it('should return null for unknown synapse', () => {
      const error: PredictionError = {
        id: 'err-1',
        actual: 0.8,
        predicted: 0.5,
        error: 0.3,
        absoluteError: 0.3,
        propagated: true,
        node: 'node-b',
        timestamp: Date.now(),
        traceId: 'trace-1',
        weight: 0.5,
      };

      const result = adaptor.updateWeight('unknown-synapse', error, 0.6);
      expect(result).toBeNull();
    });

    it('should apply decay factor', () => {
      const synapse: Synapse = {
        id: 'syn-1',
        sourceNode: 'node-a',
        targetNode: 'node-b',
        weight: 0.8,
        lastUpdate: Date.now(),
        activationCount: 0,
        weightDelta: 0,
      };
      adaptor.registerSynapse(synapse);

      const error: PredictionError = {
        id: 'err-1',
        actual: 0.0,
        predicted: 0.0,
        error: 0.0,
        absoluteError: 0.0,
        propagated: false,
        node: 'node-b',
        timestamp: Date.now(),
        traceId: 'trace-1',
        weight: 0.0,
      };

      const result = adaptor.updateWeight('syn-1', error, 0.0);

      // Weight should decay
      expect(result!.newWeight).toBeLessThan(0.8);
      // But not go below 0 due to decay
      expect(result!.newWeight).toBeGreaterThan(0);
    });
  });

  describe('updateWeights (batch)', () => {
    it('should update multiple synapses', () => {
      const synapse1: Synapse = {
        id: 'syn-1',
        sourceNode: 'node-a',
        targetNode: 'node-b',
        weight: 0.5,
        lastUpdate: Date.now(),
        activationCount: 0,
        weightDelta: 0,
      };
      const synapse2: Synapse = {
        id: 'syn-2',
        sourceNode: 'node-c',
        targetNode: 'node-b',
        weight: 0.5,
        lastUpdate: Date.now(),
        activationCount: 0,
        weightDelta: 0,
      };
      adaptor.registerSynapse(synapse1);
      adaptor.registerSynapse(synapse2);

      const error: PredictionError = {
        id: 'err-1',
        actual: 0.8,
        predicted: 0.5,
        error: 0.3,
        absoluteError: 0.3,
        propagated: true,
        node: 'node-b',
        timestamp: Date.now(),
        traceId: 'trace-1',
        weight: 0.5,
      };

      const results = adaptor.updateWeights([
        { synapseId: 'syn-1', error, previousActivation: 0.6 },
        { synapseId: 'syn-2', error, previousActivation: 0.4 },
      ]);

      expect(results.length).toBe(2);
    });
  });

  describe('applyHebbianLearning', () => {
    it('should strengthen connection for co-activated nodes', () => {
      const initialWeight = 0.3;

      const result = adaptor.applyHebbianLearning('node-a', 'node-b', 0.8);

      expect(result).not.toBeNull();
      expect(result!.newWeight).toBeGreaterThan(initialWeight);
    });

    it('should return null when max connections reached', () => {
      // Create adaptor with low max connections
      const limitedAdaptor = createHebbianAdaptor({
        maxConnections: 2,
      });

      // Create existing connections
      limitedAdaptor.applyHebbianLearning('node-a', 'node-b', 0.5);
      limitedAdaptor.applyHebbianLearning('node-c', 'node-b', 0.5);
      // Now at max

      // This should fail as target already has 2 connections
      const result = limitedAdaptor.applyHebbianLearning('node-d', 'node-b', 0.5);
      expect(result).toBeNull();
    });
  });

  describe('pruneWeights', () => {
    it('should prune weak synapses', () => {
      const synapse1: Synapse = {
        id: 'syn-strong',
        sourceNode: 'node-a',
        targetNode: 'node-b',
        weight: 0.8,
        lastUpdate: Date.now(),
        activationCount: 10,
        weightDelta: 0,
      };
      const synapse2: Synapse = {
        id: 'syn-weak',
        sourceNode: 'node-c',
        targetNode: 'node-b',
        weight: 0.02, // Below pruning threshold
        lastUpdate: Date.now(),
        activationCount: 1,
        weightDelta: 0,
      };
      adaptor.registerSynapse(synapse1);
      adaptor.registerSynapse(synapse2);

      const prunedCount = adaptor.pruneWeights(0.05);

      expect(prunedCount).toBe(1);
      expect(adaptor.getSynapse('syn-strong')).toBeDefined();
      expect(adaptor.getSynapse('syn-weak')).toBeUndefined();
    });
  });

  describe('getStats', () => {
    it('should track statistics', () => {
      const synapse: Synapse = {
        id: 'syn-1',
        sourceNode: 'node-a',
        targetNode: 'node-b',
        weight: 0.5,
        lastUpdate: Date.now(),
        activationCount: 0,
        weightDelta: 0,
      };
      adaptor.registerSynapse(synapse);

      const error: PredictionError = {
        id: 'err-1',
        actual: 0.8,
        predicted: 0.5,
        error: 0.3,
        absoluteError: 0.3,
        propagated: true,
        node: 'node-b',
        timestamp: Date.now(),
        traceId: 'trace-1',
        weight: 0.5,
      };

      adaptor.updateWeight('syn-1', error, 0.6);

      const stats = adaptor.getStats();

      expect(stats.totalUpdates).toBe(1);
      expect(stats.synapseCount).toBe(1);
      expect(stats.averageWeight).toBeGreaterThan(0);
    });
  });

  describe('exportSynapses / importSynapses', () => {
    it('should export and import synapses', () => {
      const synapse: Synapse = {
        id: 'syn-1',
        sourceNode: 'node-a',
        targetNode: 'node-b',
        weight: 0.7,
        lastUpdate: Date.now(),
        activationCount: 5,
        weightDelta: 0.1,
      };
      adaptor.registerSynapse(synapse);

      const exported = adaptor.exportSynapses();
      expect(exported.length).toBe(1);

      // Clear and import
      adaptor.clear();
      expect(adaptor.getSynapse('syn-1')).toBeUndefined();

      const imported = adaptor.importSynapses(exported);
      expect(imported).toBe(1);
      expect(adaptor.getSynapse('syn-1')).toBeDefined();
    });
  });

  describe('learning rate', () => {
    it('should allow setting learning rate', () => {
      adaptor.setLearningRate(0.5);
      expect(adaptor.getLearningRate()).toBe(0.5);
    });

    it('should clamp learning rate', () => {
      adaptor.setLearningRate(1.5);
      expect(adaptor.getLearningRate()).toBe(1);

      adaptor.setLearningRate(-0.1);
      expect(adaptor.getLearningRate()).toBe(0);
    });
  });
});

describe('Synaptogenesis', () => {
  let synaptogenesis: Synaptogenesis;

  beforeEach(() => {
    synaptogenesis = new Synaptogenesis({
      correlationThreshold: 0.7,
      minSamples: 10,
      maxConnectionsPerNode: 3,
    });
  });

  describe('recordCoActivation', () => {
    it('should record co-activation between nodes', () => {
      synaptogenesis.recordCoActivation('node-a', 'node-b', 0.8, 0.7);
      synaptogenesis.recordCoActivation('node-a', 'node-b', 0.6, 0.5);
      synaptogenesis.recordCoActivation('node-a', 'node-b', 0.9, 0.8);

      // Should not throw
      const correlation = synaptogenesis.detectCorrelation('node-a', 'node-b');
      expect(typeof correlation).toBe('number');
    });

    it('should ignore self-activation', () => {
      // Should not throw
      synaptogenesis.recordCoActivation('node-a', 'node-a', 0.8, 0.7);
    });
  });

  describe('detectCorrelation', () => {
    it('should return 0 for insufficient samples', () => {
      synaptogenesis.recordCoActivation('node-a', 'node-b', 0.8, 0.7);
      synaptogenesis.recordCoActivation('node-a', 'node-b', 0.6, 0.5);

      // Only 2 samples, need 10
      const correlation = synaptogenesis.detectCorrelation('node-a', 'node-b');
      expect(correlation).toBe(0);
    });

    it('should return correlation for sufficient samples', () => {
      // Record enough samples
      for (let i = 0; i < 20; i++) {
        synaptogenesis.recordCoActivation('node-a', 'node-b', 0.8, 0.7);
      }

      const correlation = synaptogenesis.detectCorrelation('node-a', 'node-b');
      // Should return a valid correlation value
      expect(correlation).toBeGreaterThanOrEqual(-1);
      expect(correlation).toBeLessThanOrEqual(1);
    });
  });

  describe('findCandidates', () => {
    it('should return candidate nodes above threshold', () => {
      // Add some correlated nodes
      for (let i = 0; i < 20; i++) {
        synaptogenesis.recordCoActivation('node-a', 'node-b', 0.8, 0.7);
        synaptogenesis.recordCoActivation('node-a', 'node-c', 0.3, 0.2);
      }

      const candidates = synaptogenesis.findCandidates('node-a');

      // Should find node-b as candidate (correlated)
      expect(candidates.length).toBeGreaterThan(0);
    });

    it('should return empty for no candidates', () => {
      const candidates = synaptogenesis.findCandidates('node-unknown');
      expect(candidates.length).toBe(0);
    });
  });

  describe('clear', () => {
    it('should clear correlation data', () => {
      for (let i = 0; i < 20; i++) {
        synaptogenesis.recordCoActivation('node-a', 'node-b', 0.8, 0.7);
      }

      synaptogenesis.clear();

      const correlation = synaptogenesis.detectCorrelation('node-a', 'node-b');
      expect(correlation).toBe(0);
    });
  });
});

describe('createHebbianAdaptor factory', () => {
  it('should create adaptor with default config', () => {
    const adaptor = createHebbianAdaptor();
    expect(adaptor.getStats().totalUpdates).toBe(0);
  });

  it('should create adaptor with custom config', () => {
    const adaptor = createHebbianAdaptor({
      learningRate: 0.2,
      maxConnections: 5,
    });
    expect(adaptor.getLearningRate()).toBe(0.2);
  });
});
