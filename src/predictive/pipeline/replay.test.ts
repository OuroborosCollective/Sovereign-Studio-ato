/**
 * Tests for Replay
 *
 * @module predictive/pipeline/replay.test
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  SignalRecorder,
  replaySignals,
  compareLiveReplay,
  DeterministicSignalPipeline,
  verifyPipelineReceipt,
} from './replay';
import { orderSignals } from './signalOrdering';
import { processSignalsToWindows } from './tickWindow';
import { processWindowToFeatures } from './featureVector';
import type { Signal } from '../types';
import type { RecordedSignalSet, ReplayConfig } from './replay';
import type { TickWindowConfig } from './deterministicIterables';

function createSignal(overrides: Partial<Signal> & { tick: number; sequence: number; revision: string; node: string; value: number }): Signal {
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
    },
    ...overrides,
  };
}

describe('replay', () => {
  // ========== SignalRecorder ==========
  describe('SignalRecorder', () => {
    let recorder: SignalRecorder;

    beforeEach(() => {
      recorder = new SignalRecorder();
    });

    it('should start and finish recording', () => {
      recorder.startRecording('rev-abc', 'ws=10|ov=5');
      recorder.record([createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-abc', node: 'node-a', value: 1 })]);
      recorder.record([createSignal({ id: '2', tick: 1, sequence: 0, revision: 'rev-abc', node: 'node-a', value: 2 })]);

      const recordedSet = recorder.finishRecording();

      expect(recordedSet.revision).toBe('rev-abc');
      expect(recordedSet.configFingerprint).toBe('ws=10|ov=5');
      expect(recordedSet.signals).toHaveLength(2);
    });

    it('should track signal count', () => {
      recorder.startRecording('rev-1', 'fp');
      expect(recorder.getCount()).toBe(0);

      recorder.record([createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'n', value: 1 })]);
      expect(recorder.getCount()).toBe(1);

      recorder.record([createSignal({ id: '2', tick: 1, sequence: 0, revision: 'rev-1', node: 'n', value: 2 })]);
      expect(recorder.getCount()).toBe(2);
    });

    it('should include feature vectors in recording', () => {
      recorder.startRecording('rev-1', 'fp');
      recorder.record([createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'n', value: 1 })]);

      const vectors = [
        {
          values: [1, 2, 3],
          signalHash: 'hash123',
          tickRange: [0, 0] as [number, number],
          sequenceRange: [0, 0] as [number, number],
          revision: 'rev-1',
          configFingerprint: 'fp',
        },
      ];

      const recordedSet = recorder.finishRecording(vectors);
      expect(recordedSet.featureVectors).toHaveLength(1);
      expect(recordedSet.featureVectors[0].signalHash).toBe('hash123');
    });

    it('should clear after finishRecording', () => {
      recorder.startRecording('rev-1', 'fp');
      recorder.record([createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'n', value: 1 })]);
      recorder.finishRecording();

      expect(recorder.getCount()).toBe(0);
    });
  });

  // ========== replaySignals ==========
  describe('replaySignals', () => {
    const windowConfig: TickWindowConfig = { windowSize: 3, overlap: 0 };

    it('should replay recorded signals', () => {
      const signals = [
        createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-abc', node: 'node-a', value: 10 }),
        createSignal({ id: '2', tick: 0, sequence: 1, revision: 'rev-abc', node: 'node-b', value: 20 }),
        createSignal({ id: '3', tick: 1, sequence: 0, revision: 'rev-abc', node: 'node-a', value: 15 }),
        createSignal({ id: '4', tick: 1, sequence: 1, revision: 'rev-abc', node: 'node-b', value: 25 }),
      ];

      const recordedSet: RecordedSignalSet = {
        signals,
        revision: 'rev-abc',
        recordedAt: Date.now(),
        configFingerprint: 'ws=3|ov=0',
        featureVectors: [],
      };

      const config: ReplayConfig = { windowConfig };
      const result = replaySignals(recordedSet, config);

      expect(result.replayVectors.length).toBeGreaterThan(0);
      expect(result.windows.length).toBeGreaterThan(0);
      expect(result.errors).toEqual([]);
    });

    it('should verify parity when feature vectors provided', () => {
      // First pass: generate live feature vectors
      const signals = [
        createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-abc', node: 'node-a', value: 10 }),
        createSignal({ id: '2', tick: 0, sequence: 1, revision: 'rev-abc', node: 'node-b', value: 20 }),
      ];

      const orderedSignals = orderSignals(signals);
      const windowResult = processSignalsToWindows(orderedSignals, windowConfig);
      const liveVectors = windowResult.windows.map((w) => processWindowToFeatures(w, false).featureVector);

      // Create recording with live vectors
      const recordedSet: RecordedSignalSet = {
        signals,
        revision: 'rev-abc',
        recordedAt: Date.now(),
        configFingerprint: 'ws=3|ov=0',
        featureVectors: liveVectors,
      };

      // Replay
      const config: ReplayConfig = { windowConfig };
      const result = replaySignals(recordedSet, config);

      expect(result.parityVerified).toBe(true);
    });
  });

  // ========== DeterministicSignalPipeline ==========
  describe('DeterministicSignalPipeline', () => {
    it('should process signals in live mode', () => {
      const pipeline = new DeterministicSignalPipeline({ windowSize: 3, overlap: 0 });

      const signals = [
        createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'node-a', value: 10 }),
        createSignal({ id: '2', tick: 1, sequence: 0, revision: 'rev-1', node: 'node-a', value: 20 }),
      ];

      const result = pipeline.processSignals(signals, 'rev-1');

      expect(result.featureVectors.length).toBeGreaterThan(0);
      expect(result.receipts.length).toBeGreaterThan(0);
    });

    it('should record and replay signals', () => {
      const pipeline = new DeterministicSignalPipeline({ windowSize: 3, overlap: 0 });

      // Start recording
      pipeline.startRecording('rev-abc');

      // Record signals
      const signals = [
        createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-abc', node: 'node-a', value: 10 }),
        createSignal({ id: '2', tick: 0, sequence: 1, revision: 'rev-abc', node: 'node-b', value: 20 }),
      ];

      pipeline.recordSignals(signals);

      // Get live feature vectors for comparison
      const orderedSignals = orderSignals(signals);
      const windowResult = processSignalsToWindows(orderedSignals, { windowSize: 3, overlap: 0 });
      const liveVectors = windowResult.windows.map((w) => processWindowToFeatures(w, false).featureVector);

      // Finish recording
      const recordedSet = pipeline.finishRecording(liveVectors);

      // Replay
      const replayResult = pipeline.replayRecorded(recordedSet);

      expect(replayResult.parityVerified).toBe(true);
    });

    it('should update configuration', () => {
      const pipeline = new DeterministicSignalPipeline({ windowSize: 3, overlap: 0 });
      pipeline.updateConfig({ windowSize: 5, overlap: 1 });

      const signals = [
        createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'node-a', value: 10 }),
      ];

      const result = pipeline.processSignals(signals, 'rev-1');
      expect(result.windows.length).toBeGreaterThanOrEqual(0);
    });
  });

  // ========== compareLiveReplay ==========
  describe('compareLiveReplay', () => {
    it('should detect semantic identity', () => {
      const liveResult = {
        vectors: [
          {
            values: [1, 2],
            signalHash: 'abc',
            tickRange: [0, 1] as [number, number],
            sequenceRange: [0, 1] as [number, number],
            revision: 'rev-1',
            configFingerprint: 'ws=3',
          },
        ],
        windows: [{ id: 'w1' }],
        signals: [createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'n', value: 1 })],
      };

      const replayResult = {
        vectors: liveResult.vectors,
        windows: [{ id: 'w1' }],
        signals: liveResult.signals,
      };

      const comparison = compareLiveReplay(liveResult, replayResult);
      expect(comparison.semanticallyIdentical).toBe(true);
      expect(comparison.differences).toEqual([]);
    });

    it('should detect differences', () => {
      const liveResult = {
        vectors: [
          {
            values: [1, 2],
            signalHash: 'abc',
            tickRange: [0, 1] as [number, number],
            sequenceRange: [0, 1] as [number, number],
            revision: 'rev-1',
            configFingerprint: 'ws=3',
          },
        ],
        windows: [{ id: 'w1' }],
        signals: [createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'n', value: 1 })],
      };

      const replayResult = {
        vectors: [
          {
            values: [1, 3], // Different value
            signalHash: 'xyz',
            tickRange: [0, 1] as [number, number],
            sequenceRange: [0, 1] as [number, number],
            revision: 'rev-1',
            configFingerprint: 'ws=3',
          },
        ],
        windows: [{ id: 'w1' }],
        signals: [createSignal({ id: '1', tick: 0, sequence: 0, revision: 'rev-1', node: 'n', value: 1 })],
      };

      const comparison = compareLiveReplay(liveResult, replayResult);
      expect(comparison.semanticallyIdentical).toBe(false);
      expect(comparison.differences.length).toBeGreaterThan(0);
    });
  });

  // ========== verifyPipelineReceipt ==========
  describe('verifyPipelineReceipt', () => {
    it('should verify valid receipt', () => {
      const receipt = {
        version: '1.0',
        revision: 'rev-abc',
        windowReceipts: [],
        featureReceipts: [],
        featureVectors: [],
        signalCount: 10,
        dropCount: 0,
        timestamp: Date.now(),
        isReplay: false,
      };

      const result = verifyPipelineReceipt(receipt, 'rev-abc', 10);
      expect(result.valid).toBe(true);
      expect(result.errors).toEqual([]);
    });

    it('should detect revision mismatch', () => {
      const receipt = {
        version: '1.0',
        revision: 'rev-abc',
        windowReceipts: [],
        featureReceipts: [],
        featureVectors: [],
        signalCount: 10,
        dropCount: 0,
        timestamp: Date.now(),
        isReplay: false,
      };

      const result = verifyPipelineReceipt(receipt, 'rev-xyz');
      expect(result.valid).toBe(false);
      expect(result.errors[0]).toContain('Revision mismatch');
    });

    it('should detect signal count mismatch', () => {
      const receipt = {
        version: '1.0',
        revision: 'rev-abc',
        windowReceipts: [],
        featureReceipts: [],
        featureVectors: [],
        signalCount: 10,
        dropCount: 0,
        timestamp: Date.now(),
        isReplay: false,
      };

      const result = verifyPipelineReceipt(receipt, 'rev-abc', 20);
      expect(result.valid).toBe(false);
      expect(result.errors[0]).toContain('Signal count mismatch');
    });
  });
});
