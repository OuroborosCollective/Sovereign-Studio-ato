import { describe, expect, it } from 'vitest';
import {
  runSignalPipeline,
  runSignalPipelineAsync,
  assertReplayParity,
  buildTickWindows,
  buildFeatureReceipt,
  verifyFeatureReceipt,
  canonicalOrder,
  findDuplicateKeys,
  type PipelineSignal,
  type PipelineConfig,
} from '../index';

function sig(node: string, sequence: number, tick: number, value: number): PipelineSignal {
  // timestamp is wall-clock metadata only; never used for ordering/hashing.
  return { node, sequence, tick, timestamp: 0, value };
}

function monoSignals(n: number): PipelineSignal[] {
  return Array.from({ length: n }, (_, i) => sig('nodeA', i + 1, i, i * 2));
}

const config: PipelineConfig = {
  windowSize: 3,
  overlap: 0,
  maxTicks: 100,
  maxWindows: 50,
  featureDescriptor: 'sum',
};

describe('deterministic signal pipeline - replay parity', () => {
  it('produces byte-identical window hashes, feature hashes and pipeline hash on replay', () => {
    const signals = monoSignals(9);
    const parity = assertReplayParity(signals, config);
    expect(parity.parity).toBe(true);
    expect(parity.windowHashes[0]).toEqual(parity.windowHashes[1]);
    expect(parity.featureHashes[0]).toEqual(parity.featureHashes[1]);
    expect(parity.pipelineHashes[0]).toBe(parity.pipelineHashes[1]);
  });

  it('replay parity holds across multiple feature descriptors', () => {
    const signals = monoSignals(6);
    for (const descriptor of ['sum', 'mean', 'min', 'max', 'range'] as const) {
      const c: PipelineConfig = { ...config, featureDescriptor: descriptor };
      const a = runSignalPipeline(signals, c);
      const b = runSignalPipeline(signals, c);
      expect(a.featureReceipts.map(r => r.featureHash)).toEqual(b.featureReceipts.map(r => r.featureHash));
      expect(a.pipelineHash).toBe(b.pipelineHash);
    }
  });

  it('replay parity holds when input order is shuffled (canonical ordering)', () => {
    const ordered = monoSignals(9);
    const shuffled = [...ordered].reverse();
    const a = runSignalPipeline(ordered, config);
    const b = runSignalPipeline(shuffled, config);
    expect(a.windows.map(w => w.windowHash)).toEqual(b.windows.map(w => w.windowHash));
    expect(a.featureReceipts.map(r => r.featureHash)).toEqual(b.featureReceipts.map(r => r.featureHash));
    expect(a.pipelineHash).toBe(b.pipelineHash);
  });
});

describe('deterministic signal pipeline - canonical ordering', () => {
  it('orders by node, then sequence, then tick', () => {
    const signals = [
      sig('nodeB', 1, 5, 1),
      sig('nodeA', 2, 1, 2),
      sig('nodeA', 1, 0, 3),
    ];
    const ordered = canonicalOrder(signals);
    expect(ordered.map(s => `${s.node}:${s.sequence}`)).toEqual(['nodeA:1', 'nodeA:2', 'nodeB:1']);
  });

  it('detects duplicate causal keys', () => {
    const signals = [sig('nodeA', 1, 0, 1), sig('nodeA', 1, 1, 2)];
    expect(findDuplicateKeys(signals)).toContain('nodeA:1');
  });

  it('detects duplicate causal keys and drops them with DUPLICATE_KEY', () => {
    const signals = [sig('nodeA', 1, 0, 1), sig('nodeA', 1, 1, 2), sig('nodeA', 2, 2, 3)];
    const result = runSignalPipeline(signals, config);
    const dupDrops = result.drops.filter(d => d.reason === 'DUPLICATE_KEY');
    expect(dupDrops.length).toBe(2); // both copies of seq 1 are ambiguous -> dropped
    expect(dupDrops.every(d => d.node === 'nodeA' && d.sequence === 1)).toBe(true);
    expect(result.consumedTicks).toBe(1); // only seq 2 accepted
  });

  it('canonicalizes out-of-order sequences instead of dropping them (no SEQUENCE_NON_MONOTONIC)', () => {
    // Unique (node, sequence) keys arriving out of order. These are reordered by
    // canonicalOrder, not lost — that is what keeps replay parity for shuffled
    // input. A drop here would be a silent, order-dependent loss.
    const shuffled = [
      sig('nodeA', 4, 3, 4),
      sig('nodeA', 1, 0, 1),
      sig('nodeA', 3, 2, 3),
      sig('nodeA', 2, 1, 2),
    ];
    const ordered = [sig('nodeA', 1, 0, 1), sig('nodeA', 2, 1, 2), sig('nodeA', 3, 2, 3), sig('nodeA', 4, 3, 4)];
    const a = runSignalPipeline(shuffled, config);
    const b = runSignalPipeline(ordered, config);
    expect(a.consumedTicks).toBe(4); // none dropped
    expect(b.consumedTicks).toBe(4);
    expect(a.drops.some(d => (d.reason as string) === 'SEQUENCE_NON_MONOTONIC')).toBe(false);
    expect(a.pipelineHash).toBe(b.pipelineHash); // order-independent
  });
});

describe('deterministic signal pipeline - backpressure and bounds', () => {
  it('respects maxTicks backpressure bound (finite batch)', () => {
    const bounded: PipelineConfig = { ...config, maxTicks: 4 };
    const result = runSignalPipeline(monoSignals(20), bounded);
    expect(result.consumedTicks).toBe(4);
    const tickLimitDrops = result.drops.filter(d => d.reason === 'TICK_LIMIT_REACHED');
    expect(tickLimitDrops.length).toBeGreaterThan(0);
  });

  it('respects maxWindows bound', () => {
    const bounded: PipelineConfig = { ...config, maxWindows: 1 };
    const result = runSignalPipeline(monoSignals(9), bounded);
    expect(result.windows.length).toBe(1);
    expect(result.drops.some(d => d.reason === 'WINDOW_LIMIT_REACHED')).toBe(true);
  });

  it('async variant stops at maxTicks and rejects unbounded growth', async () => {
    const bounded: PipelineConfig = { ...config, maxTicks: 3 };
    async function* infinite(): AsyncIterable<PipelineSignal> {
      let i = 0;
      while (true) {
        yield sig('nodeA', i + 1, i, i);
        i += 1;
      }
    }
    const result = await runSignalPipelineAsync(infinite(), bounded);
    expect(result.consumedTicks).toBe(3);
    expect(result.windows.length).toBeGreaterThanOrEqual(1);
  });
});

describe('deterministic signal pipeline - abort', () => {
  it('records an ABORTED drop when the abort signal is set', () => {
    const result = runSignalPipeline(monoSignals(9), config, { aborted: true });
    expect(result.aborted).toBe(true);
    expect(result.drops.some(d => d.reason === 'ABORTED')).toBe(true);
  });

  it('without abort signal the result is not aborted', () => {
    const result = runSignalPipeline(monoSignals(9), config);
    expect(result.aborted).toBe(false);
    expect(result.drops.some(d => d.reason === 'ABORTED')).toBe(false);
  });
});

describe('deterministic signal pipeline - feature receipts', () => {
  it('feature receipts are source-bound and verifiable', () => {
    const result = runSignalPipeline(monoSignals(6), { ...config, windowSize: 3 });
    expect(result.featureReceipts.length).toBe(result.windows.length);
    for (let i = 0; i < result.windows.length; i++) {
      const window = result.windows[i];
      const values = window.signals.map(s => s.value);
      const validation = verifyFeatureReceipt(result.featureReceipts[i], window, values);
      expect(validation.ok).toBe(true);
      expect(validation.sourceMatch).toBe(true);
    }
  });

  it('tampering with a feature vector invalidates the receipt', () => {
    const result = runSignalPipeline(monoSignals(6), { ...config, windowSize: 3 });
    const window = result.windows[0];
    const values = window.signals.map(s => s.value);
    const tampered = { ...result.featureReceipts[0], featureHash: 'deadbeef' };
    const validation = verifyFeatureReceipt(tampered, window, values);
    expect(validation.ok).toBe(false);
  });

  it('descriptor produces correct numeric projection', () => {
    const window = {
      index: 0,
      startTick: 0,
      endTick: 2,
      tickCount: 3,
      tickHashes: [],
      contentHash: 'c',
      windowHash: 'w',
      closedNaturally: true,
      signals: [] as PipelineSignal[],
    };
    expect(buildFeatureReceipt(window, [1, 2, 3], 'sum').vector).toEqual([6]);
    expect(buildFeatureReceipt(window, [1, 2, 3], 'mean').vector).toEqual([2]);
    expect(buildFeatureReceipt(window, [1, 2, 3], 'min').vector).toEqual([1]);
    expect(buildFeatureReceipt(window, [1, 2, 3], 'max').vector).toEqual([3]);
    expect(buildFeatureReceipt(window, [1, 2, 3], 'range').vector).toEqual([2]);
  });
});

describe('deterministic signal pipeline - overlapping windows', () => {
  it('overlap produces shared signals across windows with consistent hashes', () => {
    const overlapConfig: PipelineConfig = { ...config, windowSize: 3, overlap: 1 };
    const result = runSignalPipeline(monoSignals(6), overlapConfig);
    expect(result.windows.length).toBeGreaterThanOrEqual(2);
    // Replay parity with overlap
    const replay = runSignalPipeline(monoSignals(6), overlapConfig);
    expect(result.windows.map(w => w.windowHash)).toEqual(replay.windows.map(w => w.windowHash));
  });
});

describe('deterministic signal pipeline - invalid config', () => {
  it('rejects non-positive windowSize', () => {
    expect(() => buildTickWindows(monoSignals(3), { ...config, windowSize: 0 })).toThrow(RangeError);
  });

  it('rejects overlap >= windowSize', () => {
    expect(() => buildTickWindows(monoSignals(3), { ...config, windowSize: 3, overlap: 3 })).toThrow(RangeError);
  });
});
