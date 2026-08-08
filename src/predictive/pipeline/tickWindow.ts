/**
 * Tick Window Pipeline
 *
 * Deterministic tick windowing for signal grouping with fixed/overlapping windows.
 * Each window is bound to tick range and produces a deterministic receipt hash.
 *
 * @module predictive/pipeline/tickWindow
 */

import { chunkwiseOverlap } from './deterministicIterables';
import type { Signal } from '../types';

// ============================================================================
// Types
// ============================================================================

export interface TickWindow {
  id: string;
  startTick: number;
  endTick: number;
  signals: Signal[];
  receipt: TickWindowReceipt;
}

export interface TickWindowReceipt {
  windowId: string;
  startTick: number;
  endTick: number;
  signalCount: number;
  hash: string;
  timestamp: number;
}

export interface TickWindowConfig {
  windowSize: number;
  overlap: number;
  maxSignals?: number;
  includePartial?: boolean;
}

// ============================================================================
// Internal Hashing (deterministic, no crypto.random)
// ============================================================================

/**
 * Deterministic hash combining all signals in a window.
 * Uses simple string concatenation + polynomial rolling hash.
 * Same input always produces same output.
 */
function hashWindow(signals: Signal[], startTick: number, endTick: number): string {
  const parts: string[] = [`${startTick}`, `${endTick}`, `${signals.length}`];

  for (const signal of signals) {
    parts.push(
      signal.id,
      signal.node ?? '',
      `${signal.timestamp}`,
      `${signal.metadata?._tick ?? 0}`,
      `${signal.metadata?._seq ?? 0}`,
    );
  }

  return polynomialRollingHash(parts.join('|'));
}

/**
 * Polynomial rolling hash - deterministic, no random seed.
 * Uses prime multipliers and MOD for collision resistance.
 */
function polynomialRollingHash(str: string): string {
  const PRIME = 31;
  const MOD = 1_000_000_007;

  let hash = 0;
  let power = 1;

  for (let i = 0; i < str.length; i++) {
    const charCode = str.charCodeAt(i);
    hash = (hash + (charCode * power) % MOD) % MOD;
    power = (power * PRIME) % MOD;
  }

  // Convert to hex string for readability
  return hash.toString(16).padStart(8, '0');
}

// ============================================================================
// Tick Window Creation
// ============================================================================

/**
 * Creates a single tick window from signals within tick range.
 */
function createTickWindow(
  signals: Signal[],
  startTick: number,
  endTick: number,
  config: TickWindowConfig,
): TickWindow {
  const windowSignals = signals.filter((s) => {
    const tick = extractTick(s);
    return tick >= startTick && tick <= endTick;
  });

  // Apply max signals limit if configured
  const limitedSignals = config.maxSignals
    ? windowSignals.slice(-config.maxSignals)
    : windowSignals;

  const receipt: TickWindowReceipt = {
    windowId: `${startTick}-${endTick}`,
    startTick,
    endTick,
    signalCount: limitedSignals.length,
    hash: hashWindow(limitedSignals, startTick, endTick),
    timestamp: Date.now(), // Wall clock only for receipt metadata
  };

  return {
    id: receipt.windowId,
    startTick,
    endTick,
    signals: limitedSignals,
    receipt,
  };
}

/**
 * Extract tick from signal metadata.
 * Falls back to 0 if no tick metadata.
 */
export function extractTick(signal: Signal): number {
  const tick = signal.metadata?._tick;
  return typeof tick === 'number' ? tick : 0;
}

/**
 * Extract sequence from signal metadata.
 * Falls back to 0 if no sequence metadata.
 */
export function extractSequence(signal: Signal): number {
  const seq = signal.metadata?._seq;
  return typeof seq === 'number' ? seq : 0;
}

// ============================================================================
// Public API
// ============================================================================

/**
 * Creates fixed-size tick windows from signals.
 * Windows are non-overlapping and cover the signal range.
 *
 * @example
 * ```typescript
 * const signals = createTestSignals(50);
 * const windows = createFixedTickWindows(signals, { windowSize: 10, overlap: 0 });
 * // Returns windows with ticks: [0-9], [10-19], [20-29], ...
 * ```
 */
export function createFixedTickWindows(
  signals: Signal[],
  config: TickWindowConfig,
): TickWindow[] {
  if (signals.length === 0) return [];

  const sorted = [...signals].sort((a, b) => extractTick(a) - extractTick(b));
  const minTick = extractTick(sorted[0]);
  const maxTick = extractTick(sorted[sorted.length - 1]);

  const windows: TickWindow[] = [];
  const { windowSize, overlap = 0, includePartial = true } = config;

  if (windowSize <= 0) {
    throw new Error('windowSize must be positive');
  }

  const step = windowSize - overlap;
  if (step <= 0) {
    throw new Error('overlap must be less than windowSize');
  }

  for (let start = minTick; start <= maxTick; start += step) {
    const end = start + windowSize - 1;
    const windowSignals = sorted.filter((s) => {
      const tick = extractTick(s);
      return tick >= start && tick <= end;
    });

    // Skip empty windows unless configured to include partials
    if (windowSignals.length === 0 && !includePartial) {
      continue;
    }

    // Skip windows entirely outside signal range
    if (windowSignals.length === 0) {
      continue;
    }

    windows.push(createTickWindow(windowSignals, start, end, config));
  }

  return windows;
}

/**
 * Creates overlapping tick windows from signals.
 * Windows share signals at boundaries based on overlap ratio.
 *
 * @example
 * ```typescript
 * const signals = createTestSignals(50);
 * const windows = createOverlapTickWindows(signals, { windowSize: 10, overlap: 5 });
 * // Returns overlapping windows with 5-signal overlap at boundaries
 * ```
 */
export function createOverlapTickWindows(
  signals: Signal[],
  config: TickWindowConfig,
): TickWindow[] {
  if (signals.length === 0) return [];

  const sorted = [...signals].sort((a, b) => extractTick(a) - extractTick(b));
  const ticks = sorted.map(extractTick);
  const minTick = Math.min(...ticks);
  const maxTick = Math.max(...ticks);

  const { windowSize, overlap = 0, includePartial = true } = config;

  if (windowSize <= 0) {
    throw new Error('windowSize must be positive');
  }

  if (overlap < 0 || overlap >= windowSize) {
    throw new Error('overlap must be in range [0, windowSize)');
  }

  // Create windows using tick-based chunking
  const windows: TickWindow[] = [];
  const step = windowSize - overlap;

  for (let start = minTick; start <= maxTick; start += step) {
    const end = start + windowSize - 1;
    const windowSignals = sorted.filter((s) => {
      const tick = extractTick(s);
      return tick >= start && tick <= end;
    });

    if (windowSignals.length === 0 && !includePartial) {
      continue;
    }

    if (windowSignals.length === 0) {
      continue;
    }

    windows.push(createTickWindow(windowSignals, start, end, config));
  }

  return windows;
}

/**
 * Creates tick windows with fixed tick boundaries.
 * Useful when you need windows aligned to specific tick boundaries.
 */
export function createBoundedTickWindows(
  signals: Signal[],
  tickBoundaries: number[],
  config: TickWindowConfig,
): TickWindow[] {
  if (signals.length === 0) return [];
  if (tickBoundaries.length < 2) {
    throw new Error('tickBoundaries must have at least 2 elements');
  }

  const sortedBoundaries = [...tickBoundaries].sort((a, b) => a - b);
  const windows: TickWindow[] = [];

  for (let i = 0; i < sortedBoundaries.length - 1; i++) {
    const start = sortedBoundaries[i];
    const end = sortedBoundaries[i + 1] - 1;
    const windowSignals = signals.filter((s) => {
      const tick = extractTick(s);
      return tick >= start && tick <= end;
    });

    if (windowSignals.length > 0 || config.includePartial) {
      windows.push(createTickWindow(windowSignals, start, end, config));
    }
  }

  return windows;
}

/**
 * Verifies window receipts are deterministic.
 * Re-hashing should produce identical receipts.
 */
export function verifyWindowDeterminism(window: TickWindow): boolean {
  const rehash = hashWindow(window.signals, window.startTick, window.endTick);
  return rehash === window.receipt.hash;
}

/**
 * Gets all unique tick values from signals.
 */
export function getUniqueTicks(signals: Signal[]): number[] {
  const ticks = new Set(signals.map(extractTick));
  return Array.from(ticks).sort((a, b) => a - b);
}

/**
 * Groups signals by tick value.
 */
export function groupByTick(signals: Signal[]): Map<number, Signal[]> {
  const groups = new Map<number, Signal[]>();

  for (const signal of signals) {
    const tick = extractTick(signal);
    if (!groups.has(tick)) {
      groups.set(tick, []);
    }
    groups.get(tick)!.push(signal);
  }

  return groups;
}

/**
 * Computes tick window statistics.
 */
export interface TickWindowStats {
  totalWindows: number;
  totalSignals: number;
  avgSignalsPerWindow: number;
  minSignalsInWindow: number;
  maxSignalsInWindow: number;
  windowCoverage: number; // Percentage of tick range covered
}

export function computeTickWindowStats(windows: TickWindow[]): TickWindowStats {
  if (windows.length === 0) {
    return {
      totalWindows: 0,
      totalSignals: 0,
      avgSignalsPerWindow: 0,
      minSignalsInWindow: 0,
      maxSignalsInWindow: 0,
      windowCoverage: 0,
    };
  }

  const signalCounts = windows.map((w) => w.signals.length);
  const totalSignals = signalCounts.reduce((a, b) => a + b, 0);

  const minTick = Math.min(...windows.map((w) => w.startTick));
  const maxTick = Math.max(...windows.map((w) => w.endTick));
  const tickRange = maxTick - minTick + 1;

  // Calculate coverage (sum of window spans / total tick range)
  const coveredTicks = new Set<number>();
  for (const window of windows) {
    for (let tick = window.startTick; tick <= window.endTick; tick++) {
      coveredTicks.add(tick);
    }
  }
  const windowCoverage = tickRange > 0 ? (coveredTicks.size / tickRange) * 100 : 0;

  return {
    totalWindows: windows.length,
    totalSignals,
    avgSignalsPerWindow: totalSignals / windows.length,
    minSignalsInWindow: Math.min(...signalCounts),
    maxSignalsInWindow: Math.max(...signalCounts),
    windowCoverage,
  };
}

// ============================================================================
// Re-export deterministic primitives
// ============================================================================

export { chunkwiseOverlap } from './deterministicIterables';
