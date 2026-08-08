/**
 * Tick Window Pipeline Tests
 *
 * Tests for deterministic tick windowing with fixed/overlapping windows.
 *
 * @module predictive/pipeline/tickWindow.test
 */

import { describe, it, expect } from 'vitest';
import {
  createFixedTickWindows,
  createOverlapTickWindows,
  createBoundedTickWindows,
  verifyWindowDeterminism,
  getUniqueTicks,
  groupByTick,
  computeTickWindowStats,
  extractTick,
  extractSequence,
} from './tickWindow';
import type { OrderedSignal } from './signalOrdering';

/**
 * Creates test signals deterministically for testing.
 */
function createTestSignals(count: number): OrderedSignal[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `test-signal-${i}`,
    node: i % 2 === 0 ? 'node-a' : 'node-b',
    value: i * 0.1,
    timestamp: 1000 + i * 100,
    traceId: `trace-${i}`,
    metadata: {
      _tick: i,
      _seq: i % 5,
    },
  }));
}

describe('extractTick', () => {
  it('should extract tick from signal metadata', () => {
    const signal = { id: 's1', node: 'a', timestamp: 1000, metadata: { _tick: 5, _seq: 2 } };
    expect(extractTick(signal as never)).toBe(5);
  });

  it('should default to 0 when no tick metadata', () => {
    const signal = { id: 's1', node: 'a', timestamp: 1000 };
    expect(extractTick(signal as never)).toBe(0);
  });
});

describe('extractSequence', () => {
  it('should extract sequence from signal metadata', () => {
    const signal = { id: 's1', node: 'a', timestamp: 1000, metadata: { _tick: 5, _seq: 2 } };
    expect(extractSequence(signal as never)).toBe(2);
  });

  it('should default to 0 when no sequence metadata', () => {
    const signal = { id: 's1', node: 'a', timestamp: 1000 };
    expect(extractSequence(signal as never)).toBe(0);
  });
});

describe('createFixedTickWindows', () => {
  it('should create non-overlapping windows', () => {
    const signals = createTestSignals(25);
    const windows = createFixedTickWindows(signals, { windowSize: 5, overlap: 0 });

    expect(windows.length).toBe(5);
    expect(windows[0].startTick).toBe(0);
    expect(windows[0].endTick).toBe(4);
    expect(windows[1].startTick).toBe(5);
    expect(windows[1].endTick).toBe(9);
  });

  it('should handle signals smaller than window size', () => {
    const signals = createTestSignals(3);
    const windows = createFixedTickWindows(signals, { windowSize: 10, overlap: 0 });

    expect(windows.length).toBe(1);
    expect(windows[0].startTick).toBe(0);
    expect(windows[0].endTick).toBe(9);
    expect(windows[0].signals.length).toBe(3);
  });

  it('should include receipt with deterministic hash', () => {
    const signals = createTestSignals(10);
    const windows = createFixedTickWindows(signals, { windowSize: 10, overlap: 0 });

    expect(windows[0].receipt).toBeDefined();
    expect(windows[0].receipt.hash).toBeTruthy();
    expect(windows[0].receipt.signalCount).toBe(10);
    expect(windows[0].receipt.startTick).toBe(0);
    expect(windows[0].receipt.endTick).toBe(9);
  });

  it('should be deterministic across runs', () => {
    const signals = createTestSignals(20);
    const windows1 = createFixedTickWindows(signals, { windowSize: 5, overlap: 0 });
    const windows2 = createFixedTickWindows(signals, { windowSize: 5, overlap: 0 });

    expect(windows1.length).toBe(windows2.length);
    for (let i = 0; i < windows1.length; i++) {
      expect(windows1[i].receipt.hash).toBe(windows2[i].receipt.hash);
    }
  });

  it('should throw on invalid window size', () => {
    const signals = createTestSignals(10);
    expect(() => createFixedTickWindows(signals, { windowSize: 0, overlap: 0 })).toThrow('windowSize must be positive');
    expect(() => createFixedTickWindows(signals, { windowSize: -1, overlap: 0 })).toThrow('windowSize must be positive');
  });

  it('should handle empty signals array', () => {
    const windows = createFixedTickWindows([], { windowSize: 5, overlap: 0 });
    expect(windows.length).toBe(0);
  });

  it('should apply maxSignals limit', () => {
    const signals = createTestSignals(20);
    const windows = createFixedTickWindows(signals, { windowSize: 10, overlap: 0, maxSignals: 3 });

    expect(windows.length).toBe(2);
    expect(windows[0].signals.length).toBeLessThanOrEqual(3);
  });
});

describe('createOverlapTickWindows', () => {
  it('should create overlapping windows', () => {
    const signals = createTestSignals(20);
    const windows = createOverlapTickWindows(signals, { windowSize: 5, overlap: 2 });

    // With size 5 and overlap 2, step is 3
    // ticks: 0, 3, 6, 9, 12, 15, 18 -> 7 windows
    expect(windows.length).toBe(7);
    expect(windows[0].startTick).toBe(0);
    expect(windows[0].endTick).toBe(4);
    expect(windows[1].startTick).toBe(3);
    expect(windows[1].endTick).toBe(7);
  });

  it('should use half-size overlap by default', () => {
    const signals = createTestSignals(20);
    const windows = createOverlapTickWindows(signals, { windowSize: 4 });

    // Default overlap is size/2 = 2, step is 2
    // Signal ticks range from 0-19, with window size 4
    // Windows at start ticks: 0, 2, 4, 6, 8, 10, 12, 14, 16, 18
    // Each window spans 4 ticks, so [0-3], [2-5], [4-7], ... [18-21]
    // For 20 signals (0-19), some windows may be partial or empty at edges
    expect(windows.length).toBeGreaterThanOrEqual(5);
  });

  it('should be deterministic', () => {
    const signals = createTestSignals(15);
    const windows1 = createOverlapTickWindows(signals, { windowSize: 5, overlap: 2 });
    const windows2 = createOverlapTickWindows(signals, { windowSize: 5, overlap: 2 });

    expect(windows1.length).toBe(windows2.length);
    for (let i = 0; i < windows1.length; i++) {
      expect(windows1[i].receipt.hash).toBe(windows2[i].receipt.hash);
    }
  });

  it('should throw on invalid overlap', () => {
    const signals = createTestSignals(10);
    expect(() => createOverlapTickWindows(signals, { windowSize: 5, overlap: 5 })).toThrow('overlap must be in range [0, windowSize)');
    expect(() => createOverlapTickWindows(signals, { windowSize: 5, overlap: -1 })).toThrow('overlap must be in range [0, windowSize)');
  });
});

describe('createBoundedTickWindows', () => {
  it('should create windows with given tick boundaries', () => {
    const signals = createTestSignals(20);
    const boundaries = [0, 5, 10, 15, 20];
    const windows = createBoundedTickWindows(signals, boundaries, { windowSize: 5, overlap: 0 });

    expect(windows.length).toBe(4);
    expect(windows[0].startTick).toBe(0);
    expect(windows[0].endTick).toBe(4);
    expect(windows[1].startTick).toBe(5);
    expect(windows[1].endTick).toBe(9);
  });

  it('should throw with insufficient boundaries', () => {
    const signals = createTestSignals(10);
    expect(() => createBoundedTickWindows(signals, [0], { windowSize: 5, overlap: 0 })).toThrow('tickBoundaries must have at least 2 elements');
    expect(() => createBoundedTickWindows(signals, [], { windowSize: 5, overlap: 0 })).toThrow('tickBoundaries must have at least 2 elements');
  });
});

describe('verifyWindowDeterminism', () => {
  it('should verify deterministic window hash', () => {
    const signals = createTestSignals(10);
    const windows = createFixedTickWindows(signals, { windowSize: 10, overlap: 0 });

    expect(verifyWindowDeterminism(windows[0])).toBe(true);
  });

  it('should detect different signal sets via hash', () => {
    // Create a window with known signals
    const signals = createTestSignals(10);
    const windows = createFixedTickWindows(signals, { windowSize: 10, overlap: 0 });

    // Verify initial state is deterministic
    expect(verifyWindowDeterminism(windows[0])).toBe(true);

    // Create another window from the same signals - should have same hash
    const windows2 = createFixedTickWindows(signals, { windowSize: 10, overlap: 0 });
    expect(windows2[0].receipt.hash).toBe(windows[0].receipt.hash);

    // Create window from different signals (different tick range)
    // Signals with tick starting at 100 should produce different hash
    const differentSignals = Array.from({ length: 10 }, (_, i) => ({
      id: `test-signal-${i}`,
      node: 'node-a',
      value: i * 0.1,
      timestamp: 1000 + i * 100,
      traceId: `trace-${i}`,
      metadata: {
        _tick: 100 + i, // different tick range
        _seq: i % 5,
      },
    }));
    const windows3 = createFixedTickWindows(differentSignals, { windowSize: 10, overlap: 0 });
    expect(windows3[0].receipt.hash).not.toBe(windows[0].receipt.hash);
  });
});

describe('getUniqueTicks', () => {
  it('should return sorted unique ticks', () => {
    const signals = createTestSignals(15);
    const ticks = getUniqueTicks(signals);

    expect(ticks).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]);
    expect(ticks.length).toBe(15);
  });

  it('should return empty for no signals', () => {
    expect(getUniqueTicks([])).toEqual([]);
  });
});

describe('groupByTick', () => {
  it('should group signals by tick', () => {
    const signals = createTestSignals(10);
    const groups = groupByTick(signals);

    expect(groups.size).toBe(10);
    for (const [tick, signals2] of groups) {
      expect(signals2.length).toBe(1);
      expect(extractTick(signals2[0])).toBe(tick);
    }
  });

  it('should return empty map for no signals', () => {
    expect(groupByTick([]).size).toBe(0);
  });
});

describe('computeTickWindowStats', () => {
  it('should compute correct statistics', () => {
    const signals = createTestSignals(20);
    const windows = createFixedTickWindows(signals, { windowSize: 5, overlap: 0 });

    const stats = computeTickWindowStats(windows);

    expect(stats.totalWindows).toBe(4);
    expect(stats.totalSignals).toBe(20);
    expect(stats.avgSignalsPerWindow).toBe(5);
    expect(stats.minSignalsInWindow).toBe(5);
    expect(stats.maxSignalsInWindow).toBe(5);
    expect(stats.windowCoverage).toBeGreaterThan(0);
  });

  it('should handle empty windows', () => {
    const stats = computeTickWindowStats([]);

    expect(stats.totalWindows).toBe(0);
    expect(stats.totalSignals).toBe(0);
    expect(stats.avgSignalsPerWindow).toBe(0);
    expect(stats.windowCoverage).toBe(0);
  });
});
