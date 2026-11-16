/**
 * Autopoiesis Engine Tests
 */

import assert from 'node:assert';
import {
  AutopoiesisEngine,
  integrateAutopoiesis,
} from './autopoiesis';
import type { Synapse, NeuralNode, Signal, PredictionError } from './types';

function runTests() {
  // Test recordCoActivation & calculateCorrelation
  {
    const engine = new AutopoiesisEngine({
      minCorrelationSamples: 5,
      correlationThreshold: 0.7,
      minWeight: 0.05,
      maxConnectionsPerNode: 2,
      pruneInterval: 2,
    });

    const sigA: Signal = { id: '1', node: 'nodeA', value: 1.0, timestamp: Date.now(), traceId: 't1' };
    const sigB: Signal = { id: '2', node: 'nodeB', value: 1.0, timestamp: Date.now(), traceId: 't1' };

    engine.recordCoActivation(sigA, sigB);
    assert.strictEqual(engine.calculateCorrelation('nodeA', 'nodeB'), 0);

    engine.recordCoActivation(sigA);
    engine.recordCoActivation(sigA, sigA);
    assert.strictEqual(engine.getStats().totalCorrelationsTracked, 1);

    for (let i = 0; i < 10; i++) {
      const val = i * 0.1;
      engine.recordCoActivation(
        { id: `${i}-a`, node: 'nodeA', value: val, timestamp: Date.now(), traceId: 't1' },
        { id: `${i}-b`, node: 'nodeB', value: val, timestamp: Date.now(), traceId: 't1' },
      );
    }

    const corr = engine.calculateCorrelation('nodeA', 'nodeB');
    assert.ok(corr > 0.99, 'Expected correlation to be > 0.99');

    const err: PredictionError = {
      id: 'e1',
      actual: 0.8,
      predicted: 0.2,
      error: 0.6,
      absoluteError: 0.6,
      propagated: false,
      node: 'nodeA',
      timestamp: Date.now(),
      traceId: 't1',
      weight: 0.5,
    };
    const relSig: Signal = { id: 's1', node: 'nodeB', value: 0.5, timestamp: Date.now(), traceId: 't1' };

    engine.recordErrorCorrelation(err, relSig);
    assert.ok(engine.getStats().totalCorrelationsTracked > 10);
  }

  // Test findSynaptogenesisCandidates
  {
    const engine = new AutopoiesisEngine({
      minCorrelationSamples: 5,
      correlationThreshold: 0.7,
      maxConnectionsPerNode: 2,
    });

    engine.updateConfig({ synaptogenesisEnabled: false });
    assert.deepStrictEqual(engine.findSynaptogenesisCandidates([]), []);

    engine.updateConfig({ synaptogenesisEnabled: true });

    for (let i = 0; i < 10; i++) {
      const val = i * 0.1;
      engine.recordCoActivation(
        { id: `${i}-a`, node: 'nodeA', value: val, timestamp: Date.now(), traceId: 't1' },
        { id: `${i}-b`, node: 'nodeB', value: val, timestamp: Date.now(), traceId: 't1' },
      );
    }

    const candidates = engine.findSynaptogenesisCandidates([]);
    assert.strictEqual(candidates.length, 1);
    assert.strictEqual(candidates[0].sourceNode, 'nodeA');
    assert.strictEqual(candidates[0].targetNode, 'nodeB');
    assert.ok(candidates[0].correlation > 0.9);

    const existingSynapses: Synapse[] = [
      {
        id: 'syn-1',
        sourceNode: 'nodeA',
        targetNode: 'nodeB',
        weight: 0.5,
        lastUpdate: Date.now(),
        activationCount: 1,
        weightDelta: 0,
      },
    ];

    const candidatesWithExisting = engine.findSynaptogenesisCandidates(existingSynapses);
    assert.deepStrictEqual(candidatesWithExisting, []);

    const limitedSynapses: Synapse[] = [
      { id: 's1', sourceNode: 'x1', targetNode: 'nodeB', weight: 0.5, lastUpdate: Date.now(), activationCount: 1, weightDelta: 0 },
      { id: 's2', sourceNode: 'x2', targetNode: 'nodeB', weight: 0.5, lastUpdate: Date.now(), activationCount: 1, weightDelta: 0 },
    ];
    const maxedCandidates = engine.findSynaptogenesisCandidates(limitedSynapses);
    assert.deepStrictEqual(maxedCandidates, []);
  }

  // Test findPruningCandidates & runPruningPass
  {
    const engine = new AutopoiesisEngine({ minWeight: 0.05, pruneInterval: 2 });
    const synapses: Synapse[] = [
      { id: 'syn-strong', sourceNode: 'nodeA', targetNode: 'nodeB', weight: 0.8, lastUpdate: Date.now(), activationCount: 10, weightDelta: 0 },
      { id: 'syn-weak', sourceNode: 'nodeC', targetNode: 'nodeB', weight: 0.02, lastUpdate: Date.now(), activationCount: 1, weightDelta: 0 },
    ];

    assert.deepStrictEqual(engine.findPruningCandidates(synapses), ['syn-weak']);

    engine.updateConfig({ pruningEnabled: false });
    assert.deepStrictEqual(engine.findPruningCandidates(synapses), []);
    engine.updateConfig({ pruningEnabled: true });

    const prune1 = engine.runPruningPass(synapses);
    assert.deepStrictEqual(prune1, []);

    const prune2 = engine.runPruningPass(synapses);
    assert.deepStrictEqual(prune2, ['syn-weak']);
    assert.strictEqual(engine.getStats().prunedConnections, 1);
  }

  // Test exportCorrelationMatrix & reset
  {
    const engine = new AutopoiesisEngine({ minCorrelationSamples: 5 });
    for (let i = 0; i < 10; i++) {
      const val = i * 0.1;
      engine.recordCoActivation(
        { id: `${i}-a`, node: 'nodeA', value: val, timestamp: Date.now(), traceId: 't1' },
        { id: `${i}-b`, node: 'nodeB', value: val, timestamp: Date.now(), traceId: 't1' },
      );
    }

    const exported = engine.exportCorrelationMatrix();
    assert.ok(exported.correlations);
    assert.strictEqual(exported.correlations.length, 1);
    assert.strictEqual(exported.correlations[0].nodeA, 'nodeA');
    assert.strictEqual(exported.correlations[0].nodeB, 'nodeB');

    engine.reset();
    assert.strictEqual(engine.getStats().totalCorrelationsTracked, 0);
    assert.strictEqual(engine.calculateCorrelation('nodeA', 'nodeB'), 0);
  }

  // Test integrateAutopoiesis
  {
    const engine = new AutopoiesisEngine();
    const nodes: NeuralNode[] = [];
    const synapses: Synapse[] = [];

    const result = integrateAutopoiesis(engine, synapses, nodes);
    assert.ok(Array.isArray(result.newSynapses));
    assert.ok(Array.isArray(result.pruneIds));
  }

  console.log('All AutopoiesisEngine unit tests passed successfully!');
}

runTests();
