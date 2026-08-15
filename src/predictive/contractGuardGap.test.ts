/**
 * Predictive Contract Foundation - Guard Gap Regression Tests
 *
 * Issue #1168 step 1: Inventory and Guard-Gap Tests.
 *
 * These tests document and close the gaps in the hand-written guards in
 * `src/predictive/types.ts` (`isValidSignal`, `isValidPrediction`,
 * `isValidSynapse`). They are the regression contract for the Predictive
 * Runtime contract family before the Zod schemas of later PRs are introduced.
 *
 * Truth rule: structural validity is STRUCTURALLY_VALID only - never VERIFIED.
 */

import { describe, it, expect } from 'vitest';
import {
  isValidSignal,
  isValidPrediction,
  isValidSynapse,
  type Signal,
  type Prediction,
  type Synapse,
} from './types';

const BASE_SIGNAL: Signal = {
  id: 'sig-1',
  node: 'runtime.decision',
  value: 0.5,
  timestamp: 1_700_000_000_000,
  traceId: 'trace-1',
};

const BASE_PREDICTION: Prediction = {
  id: 'pred-1',
  predictedValue: 0.5,
  confidence: 0.5,
  node: 'runtime.decision',
  timestamp: 1_700_000_000_000,
  traceId: 'trace-1',
};

const BASE_SYNAPSE: Synapse = {
  id: 'syn-1',
  sourceNode: 'node-a',
  targetNode: 'node-b',
  weight: 0.5,
  lastUpdate: 1_700_000_000_000,
  activationCount: 1,
  weightDelta: 0.01,
};

describe('isValidSignal guard gaps', () => {
  it('accepts a fully valid signal', () => {
    expect(isValidSignal(BASE_SIGNAL)).toBe(true);
  });

  it('rejects missing id', () => {
    const { id: _omit, ...rest } = BASE_SIGNAL;
    expect(isValidSignal(rest)).toBe(false);
  });

  it('rejects missing node', () => {
    const { node: _omit, ...rest } = BASE_SIGNAL;
    expect(isValidSignal(rest)).toBe(false);
  });

  it('rejects missing value', () => {
    const { value: _omit, ...rest } = BASE_SIGNAL;
    expect(isValidSignal(rest)).toBe(false);
  });

  it('rejects missing timestamp', () => {
    const { timestamp: _omit, ...rest } = BASE_SIGNAL;
    expect(isValidSignal(rest)).toBe(false);
  });

  it('rejects missing traceId', () => {
    const { traceId: _omit, ...rest } = BASE_SIGNAL;
    expect(isValidSignal(rest)).toBe(false);
  });

  it('rejects NaN value', () => {
    expect(isValidSignal({ ...BASE_SIGNAL, value: NaN })).toBe(false);
  });

  it('rejects Infinity value', () => {
    expect(isValidSignal({ ...BASE_SIGNAL, value: Infinity })).toBe(false);
  });

  it('rejects -Infinity value', () => {
    expect(isValidSignal({ ...BASE_SIGNAL, value: -Infinity })).toBe(false);
  });

  it('rejects NaN timestamp', () => {
    expect(isValidSignal({ ...BASE_SIGNAL, timestamp: NaN })).toBe(false);
  });

  it('rejects Infinity timestamp', () => {
    expect(isValidSignal({ ...BASE_SIGNAL, timestamp: Infinity })).toBe(false);
  });

  it('rejects negative-zero timestamp as causal identity (not a real moment)', () => {
    expect(isValidSignal({ ...BASE_SIGNAL, timestamp: -0 })).toBe(false);
  });

  it('rejects unknown properties (strict contract)', () => {
    expect(isValidSignal({ ...BASE_SIGNAL, extra: 'should-reject' })).toBe(false);
  });

  it('rejects empty id', () => {
    expect(isValidSignal({ ...BASE_SIGNAL, id: '' })).toBe(false);
  });

  it('rejects empty node', () => {
    expect(isValidSignal({ ...BASE_SIGNAL, node: '' })).toBe(false);
  });

  it('rejects empty traceId', () => {
    expect(isValidSignal({ ...BASE_SIGNAL, traceId: '' })).toBe(false);
  });

  it('rejects metadata with non-object value', () => {
    expect(isValidSignal({ ...BASE_SIGNAL, metadata: 'not-an-object' })).toBe(false);
  });
});

describe('isValidPrediction guard gaps', () => {
  it('accepts a fully valid prediction', () => {
    expect(isValidPrediction(BASE_PREDICTION)).toBe(true);
  });

  it('rejects missing id', () => {
    const { id: _omit, ...rest } = BASE_PREDICTION;
    expect(isValidPrediction(rest)).toBe(false);
  });

  it('rejects missing predictedValue', () => {
    const { predictedValue: _omit, ...rest } = BASE_PREDICTION;
    expect(isValidPrediction(rest)).toBe(false);
  });

  it('rejects missing confidence', () => {
    const { confidence: _omit, ...rest } = BASE_PREDICTION;
    expect(isValidPrediction(rest)).toBe(false);
  });

  it('rejects missing node', () => {
    const { node: _omit, ...rest } = BASE_PREDICTION;
    expect(isValidPrediction(rest)).toBe(false);
  });

  it('rejects missing timestamp', () => {
    const { timestamp: _omit, ...rest } = BASE_PREDICTION;
    expect(isValidPrediction(rest)).toBe(false);
  });

  it('rejects missing traceId', () => {
    const { traceId: _omit, ...rest } = BASE_PREDICTION;
    expect(isValidPrediction(rest)).toBe(false);
  });

  it('rejects NaN predictedValue', () => {
    expect(isValidPrediction({ ...BASE_PREDICTION, predictedValue: NaN })).toBe(false);
  });

  it('rejects Infinity predictedValue', () => {
    expect(isValidPrediction({ ...BASE_PREDICTION, predictedValue: Infinity })).toBe(false);
  });

  it('rejects NaN confidence', () => {
    expect(isValidPrediction({ ...BASE_PREDICTION, confidence: NaN })).toBe(false);
  });

  it('rejects confidence above 1', () => {
    expect(isValidPrediction({ ...BASE_PREDICTION, confidence: 1.0001 })).toBe(false);
  });

  it('rejects confidence below 0', () => {
    expect(isValidPrediction({ ...BASE_PREDICTION, confidence: -0.0001 })).toBe(false);
  });

  it('rejects NaN timestamp', () => {
    expect(isValidPrediction({ ...BASE_PREDICTION, timestamp: NaN })).toBe(false);
  });

  it('rejects non-positive timestamp', () => {
    expect(isValidPrediction({ ...BASE_PREDICTION, timestamp: 0 })).toBe(false);
  });

  it('rejects embedding with non-finite element', () => {
    expect(isValidPrediction({ ...BASE_PREDICTION, embedding: [0.1, NaN, 0.3] })).toBe(false);
  });

  it('rejects embedding with Infinity element', () => {
    expect(isValidPrediction({ ...BASE_PREDICTION, embedding: [Infinity] })).toBe(false);
  });

  it('rejects non-array embedding', () => {
    expect(isValidPrediction({ ...BASE_PREDICTION, embedding: 'not-an-array' as unknown })).toBe(false);
  });

  it('rejects unknown properties (strict contract)', () => {
    expect(isValidPrediction({ ...BASE_PREDICTION, extra: 'should-reject' })).toBe(false);
  });

  it('accepts prediction with finite embedding', () => {
    expect(isValidPrediction({ ...BASE_PREDICTION, embedding: [0.1, 0.2, 0.3] })).toBe(true);
  });

  it('accepts prediction with patternId', () => {
    expect(isValidPrediction({ ...BASE_PREDICTION, patternId: 'pattern-1' })).toBe(true);
  });
});

describe('isValidSynapse guard gaps', () => {
  it('accepts a fully valid synapse', () => {
    expect(isValidSynapse(BASE_SYNAPSE)).toBe(true);
  });

  it('rejects missing id', () => {
    const { id: _omit, ...rest } = BASE_SYNAPSE;
    expect(isValidSynapse(rest)).toBe(false);
  });

  it('rejects missing sourceNode', () => {
    const { sourceNode: _omit, ...rest } = BASE_SYNAPSE;
    expect(isValidSynapse(rest)).toBe(false);
  });

  it('rejects missing targetNode', () => {
    const { targetNode: _omit, ...rest } = BASE_SYNAPSE;
    expect(isValidSynapse(rest)).toBe(false);
  });

  it('rejects missing weight', () => {
    const { weight: _omit, ...rest } = BASE_SYNAPSE;
    expect(isValidSynapse(rest)).toBe(false);
  });

  it('rejects missing lastUpdate', () => {
    const { lastUpdate: _omit, ...rest } = BASE_SYNAPSE;
    expect(isValidSynapse(rest)).toBe(false);
  });

  it('rejects missing activationCount', () => {
    const { activationCount: _omit, ...rest } = BASE_SYNAPSE;
    expect(isValidSynapse(rest)).toBe(false);
  });

  it('rejects missing weightDelta', () => {
    const { weightDelta: _omit, ...rest } = BASE_SYNAPSE;
    expect(isValidSynapse(rest)).toBe(false);
  });

  it('rejects NaN weight', () => {
    expect(isValidSynapse({ ...BASE_SYNAPSE, weight: NaN })).toBe(false);
  });

  it('rejects Infinity weight', () => {
    expect(isValidSynapse({ ...BASE_SYNAPSE, weight: Infinity })).toBe(false);
  });

  it('rejects weight above 1', () => {
    expect(isValidSynapse({ ...BASE_SYNAPSE, weight: 1.0001 })).toBe(false);
  });

  it('rejects weight below 0', () => {
    expect(isValidSynapse({ ...BASE_SYNAPSE, weight: -0.0001 })).toBe(false);
  });

  it('rejects NaN lastUpdate', () => {
    expect(isValidSynapse({ ...BASE_SYNAPSE, lastUpdate: NaN })).toBe(false);
  });

  it('rejects non-integer activationCount', () => {
    expect(isValidSynapse({ ...BASE_SYNAPSE, activationCount: 1.5 })).toBe(false);
  });

  it('rejects negative activationCount', () => {
    expect(isValidSynapse({ ...BASE_SYNAPSE, activationCount: -1 })).toBe(false);
  });

  it('rejects NaN weightDelta', () => {
    expect(isValidSynapse({ ...BASE_SYNAPSE, weightDelta: NaN })).toBe(false);
  });

  it('rejects unknown properties (strict contract)', () => {
    expect(isValidSynapse({ ...BASE_SYNAPSE, extra: 'should-reject' })).toBe(false);
  });
});
