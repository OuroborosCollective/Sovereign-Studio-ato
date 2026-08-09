/**
 * Tests for Tick Window
 *
 * @module predictive/pipeline/tickWindow.test
 */

import { describe, it, expect } from 'vitest';
import {
  validateTickWindowConfig,
  generateTickWindows,
  generateOverlappingTickWindows,
  createBackpressureMonitor,
  processSignalsToWindows,
  generateWindowReceipts,
  verifyConfigFingerprint,
} from './tickWindow';
import type { OrderedSignal } from './signalOrdering';
import type { Signal } from '../types';
import type { TickWindowConfig } from './deterministicIterables';

function createOrderedSignal(overrides: Partial<OrderedSignal> = {}): OrderedSignal {
  const { tick, sequence, node, value, metadata, ...rest } = overrides as Partial<OrderedSignal> & {
    tick?: number;
    sequence?: number;
  };
  return {
    id: 'sig-1',
    node: node ?? 'node-a',
    value: value ?? 1,
    timestamp: Date.now(),
    traceId: 'trace-1',
    metadata: {
      tick: tick ?? 0,
      sequence: sequence ?? 0,
      revision: 'rev-1',
      node: node ?? 'node-a',
      ...metadata,
    },
    ...rest,
  } as OrderedSignal;
}

function createSignals(count: number, startTick: number = 0): OrderedSignal[] {
  const signals: OrderedSignal[] = [];
  for (let i = 0; i < count; i++) {
    signals.push(
      createOrderedSignal({
        id: `sig-${i}`,
        tick: startTick + i,
        sequence: i,
        node: i % 2 === 0 ? 'node-a' : 'node-b',
        value: i + 1,
      }),
    );
  }
  return signals;
}

describe('tickWindow', () => {
  // ========== validateTickWindowConfig ==========
  describe('validateTickWindowConfig', () => {
    it('should accept valid config', () => {
      const config: TickWindowConfig = { windowSize: 10, overlap: 5 };
      expect(() => validateTickWindowConfig(config)).not.toThrow();
    });

    it('should throw for invalid windowSize', () => {
      const config: TickWindowConfig = { windowSize: 0, overlap: 0 };
      expect(() => validateTickWindowConfig(config)).toThrow('windowSize');
    });

    it('should throw for negative overlap', () => {
      const config: TickWindowConfig = { windowSize: 10, overlap: -1 };
      expect(() => validateTickWindowConfig(config)).toThrow('overlap');
    });

    it('should throw when overlap >= windowSize', () => {
      const config: TickWindowConfig = { windowSize: 5, overlap: 5 };
      expect(() => validateTickWindowConfig(config)).toThrow('less than windowSize');
    });
  });

  // ========== generateTickWindows ==========
  describe('generateTickWindows', () => {
    it('should generate windows with correct tick ranges', () => {
      const signals = createSignals(10, 0);
      const config: TickWindowConfig = { windowSize: 3, overlap: 0 };

      const windows = [...generateTickWindows(signals, config)];
      expect(windows).toHaveLength(4); // ticks 0-2, 3-5, 6-8, 9-10

      expect(windows[0]).toMatchObject({
        startTick: 0,
        endTick: 2,
        windowIndex: 0,
      });

      expect(windows[1]).toMatchObject({
        startTick: 3,
        endTick: 5,
        windowIndex: 1,
      });
    });

    it('should handle empty signals', () => {
      const config: TickWindowConfig = { windowSize: 3, overlap: 0 };
      const windows = [...generateTickWindows([], config)];
      expect(windows).toHaveLength(0);
    });

    it('should respect abort signal', () => {
      const signals = createSignals(10, 0);
      const config: TickWindowConfig = { windowSize: 3, overlap: 0 };
      const controller = new AbortController();
      controller.abort();

      const windows = [...generateTickWindows(signals, config, { abortSignal: controller.signal })];
      expect(windows).toHaveLength(0);
    });
  });

  // ========== generateOverlappingTickWindows ==========
  describe('generateOverlappingTickWindows', () => {
    it('should generate overlapping windows', () => {
      const signals = createSignals(10, 0);
      const config: TickWindowConfig = { windowSize: 3, overlap: 1 };

      const windows = [...generateOverlappingTickWindows(signals, config)];
      expect(windows).toHaveLength(5); // More windows due to overlap

      // First window
      expect(windows[0].startTick).toBe(0);
      expect(windows[0].endTick).toBe(2);

      // Second window (overlapping)
      expect(windows[1].startTick).toBe(2); // 3 - 1 = 2
      expect(windows[1].endTick).toBe(4);
    });

    it('should throw for invalid overlap', () => {
      const signals = createSignals(10, 0);
      const config: TickWindowConfig = { windowSize: 3, overlap: 3 };

      expect(() => [...generateOverlappingTickWindows(signals, config)]).toThrow();
    });
  });

  // ========== createBackpressureMonitor ==========
  describe('createBackpressureMonitor', () => {
    it('should not backpressure below threshold', () => {
      const monitor = createBackpressureMonitor(100);
      const state = monitor.update(50);
      expect(state.isBackpressured).toBe(false);
    });

    it('should backpressure at threshold', () => {
      const monitor = createBackpressureMonitor(100);
      const state = monitor.update(100);
      expect(state.isBackpressured).toBe(true);
    });

    it('should backpressure above threshold', () => {
      const monitor = createBackpressureMonitor(100);
      const state = monitor.update(150);
      expect(state.isBackpressured).toBe(true);
    });

    it('should report shouldBackpressure correctly', () => {
      const monitor = createBackpressureMonitor(100);
      expect(monitor.shouldBackpressure({ queueDepth: 50, isBackpressured: false, maxQueueDepth: 100 })).toBe(false);
      expect(monitor.shouldBackpressure({ queueDepth: 100, isBackpressured: true, maxQueueDepth: 100 })).toBe(true);
    });
  });

  // ========== processSignalsToWindows ==========
  describe('processSignalsToWindows', () => {
    it('should process signals into windows', () => {
      const signals = createSignals(10, 0);
      const config: TickWindowConfig = { windowSize: 3, overlap: 0 };

      const result = processSignalsToWindows(signals, config);

      expect(result.windows.length).toBeGreaterThan(0);
      expect(result.drops).toEqual([]);
      expect(result.aborted).toBe(false);
    });

    it('should respect maxItems', () => {
      const signals = createSignals(100, 0);
      const config: TickWindowConfig = { windowSize: 10, overlap: 0, maxItems: 5 };

      const result = processSignalsToWindows(signals, config);

      for (const drop of result.drops) {
        if (drop.reason === 'MAX_ITEMS_EXCEEDED') {
          expect(drop.signals.length).toBeLessThanOrEqual(95);
        }
      }
    });

    it('should handle abort signal', () => {
      const signals = createSignals(10, 0);
      const config: TickWindowConfig = { windowSize: 3, overlap: 0 };
      const controller = new AbortController();
      controller.abort();

      const result = processSignalsToWindows(signals, config, { abortSignal: controller.signal });

      expect(result.aborted).toBe(true);
    });

    it('should include backpressure in result', () => {
      const signals = createSignals(10, 0);
      const config: TickWindowConfig = { windowSize: 3, overlap: 0 };

      const result = processSignalsToWindows(signals, config);

      expect(result.backpressure).toBeDefined();
      expect(typeof result.backpressure.queueDepth).toBe('number');
    });
  });

  // ========== generateWindowReceipts ==========
  describe('generateWindowReceipts', () => {
    it('should generate receipts for windows', () => {
      const signals = createSignals(6, 0);
      const config: TickWindowConfig = { windowSize: 3, overlap: 0 };
      const windows = [...generateTickWindows(signals, config)];

      const receipts = generateWindowReceipts(windows);

      expect(receipts).toHaveLength(windows.length);
      for (const receipt of receipts) {
        expect(receipt.id).toBeDefined();
        expect(receipt.startTick).toBeDefined();
        expect(receipt.endTick).toBeDefined();
        expect(receipt.signalCount).toBeDefined();
      }
    });
  });

  // ========== verifyConfigFingerprint ==========
  describe('verifyConfigFingerprint', () => {
    it('should verify matching fingerprint', () => {
      const fp = 'ws=10|ov=5';
      expect(verifyConfigFingerprint(fp, 10, 5)).toBe(true);
    });

    it('should reject mismatched fingerprint', () => {
      const fp = 'ws=10|ov=5';
      expect(verifyConfigFingerprint(fp, 10, 3)).toBe(false);
    });

    it('should include maxItems in verification', () => {
      const fp = 'ws=10|ov=5|mi=100';
      expect(verifyConfigFingerprint(fp, 10, 5, 100)).toBe(true);
      expect(verifyConfigFingerprint(fp, 10, 5, 200)).toBe(false);
    });
  });
});
