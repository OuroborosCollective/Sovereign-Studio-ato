/**
 * Tick Window - Fixed and Overlapping Window Management
 *
 * Creates deterministic tick-based windows for signal processing.
 * Windows are bounded by tick range, not wall-clock time.
 *
 * @module predictive/pipeline/tickWindow
 */

import type { Signal } from '../types';
import type { OrderedSignal } from './signalOrdering';
import type { TickWindowConfig, BackpressureState } from './deterministicIterables';
import { chunkwise, chunkwiseOverlap, createConfigFingerprint } from './deterministicIterables';

// ============================================================================
// Window Types
// ============================================================================

/**
 * A tick window containing signals within a tick range.
 */
export interface TickWindow {
  /** Unique window identifier */
  id: string;
  /** Start tick (inclusive) */
  startTick: number;
  /** End tick (inclusive) */
  endTick: number;
  /** Signals in this window */
  signals: OrderedSignal[];
  /** Nodes covered by this window */
  nodes: string[];
  /** Window index from start of sequence */
  windowIndex: number;
  /** Config fingerprint */
  configFingerprint: string;
  /** Whether this window is complete (no partial coverage) */
  isComplete: boolean;
}

/**
 * Window drop event with reason code.
 */
export interface WindowDrop {
  /** Dropped signals */
  signals: Signal[];
  /** Reason code */
  reason: WindowDropReason;
  /** Additional details */
  details?: string;
}

/**
 * Reason codes for window drops.
 */
export type WindowDropReason =
  | 'MAX_ITEMS_EXCEEDED'
  | 'MAX_WINDOW_DURATION_EXCEEDED'
  | 'BACKPRESSURE_APPLIED'
  | 'ABORT_SIGNALLED'
  | 'INCOMPLETE_WINDOW';

/**
 * Window processing result.
 */
export interface WindowResult {
  /** Created windows */
  windows: TickWindow[];
  /** Dropped signals with reason codes */
  drops: WindowDrop[];
  /** Final backpressure state */
  backpressure: BackpressureState;
  /** Whether processing was aborted */
  aborted: boolean;
  /** Total ticks processed */
  ticksProcessed: number;
}

// ============================================================================
// Window Configuration Validation
// ============================================================================

/**
 * Validates tick window configuration.
 */
export function validateTickWindowConfig(config: TickWindowConfig): void {
  if (!Number.isInteger(config.windowSize) || config.windowSize <= 0) {
    throw new Error(`Invalid windowSize: must be positive integer, got ${config.windowSize}`);
  }
  if (!Number.isInteger(config.overlap) || config.overlap < 0) {
    throw new Error(`Invalid overlap: must be non-negative integer, got ${config.overlap}`);
  }
  if (config.overlap >= config.windowSize) {
    throw new Error(`Invalid overlap: must be less than windowSize (${config.windowSize}), got ${config.overlap}`);
  }
  if (config.maxItems !== undefined && (!Number.isInteger(config.maxItems) || config.maxItems <= 0)) {
    throw new Error(`Invalid maxItems: must be positive integer, got ${config.maxItems}`);
  }
  if (config.maxWindowDuration !== undefined && (!Number.isInteger(config.maxWindowDuration) || config.maxWindowDuration <= 0)) {
    throw new Error(`Invalid maxWindowDuration: must be positive integer, got ${config.maxWindowDuration}`);
  }
}

// ============================================================================
// Tick Window Generator
// ============================================================================

/**
 * Generates fixed-size tick windows from ordered signals.
 * Each window contains all signals whose tick falls within [startTick, endTick].
 */
export function* generateTickWindows(
  signals: OrderedSignal[],
  config: TickWindowConfig,
  options: {
    abortSignal?: AbortSignal;
    onBackpressure?: (state: BackpressureState) => void;
  } = {},
): Generator<TickWindow> {
  validateTickWindowConfig(config);

  if (signals.length === 0) return;

  const fingerprint = createConfigFingerprint(config.windowSize, config.overlap, config.maxItems);
  const tickRanges = computeTickRanges(signals, config.windowSize, config.overlap);

  let windowIndex = 0;
  for (const [startTick, endTick] of tickRanges) {
    // Check abort signal
    if (options.abortSignal?.aborted) return;

    const windowSignals: OrderedSignal[] = [];
    const uniqueTicks = new Set<number>();
    const uniqueNodes = new Set<string>();

    for (const s of signals) {
      if (s.metadata.tick >= startTick && s.metadata.tick <= endTick) {
        windowSignals.push(s);
        uniqueTicks.add(s.metadata.tick);
        uniqueNodes.add(s.metadata.node);
      }
    }

    const expectedTicks = endTick - startTick + 1;
    const isComplete = uniqueTicks.size === expectedTicks;
    const nodes = Array.from(uniqueNodes).sort();

    yield {
      id: `window-${startTick}-${endTick}-${windowIndex}`,
      startTick,
      endTick,
      signals: windowSignals,
      nodes,
      windowIndex,
      configFingerprint: fingerprint,
      isComplete,
    };

    windowIndex++;
  }
}

/**
 * Computes the tick ranges for windows given signals and config.
 */
function computeTickRanges(
  signals: OrderedSignal[],
  windowSize: number,
  overlap: number,
): Array<[number, number]> {
  if (signals.length === 0) return [];

  const ticks = [...new Set(signals.map((s) => s.metadata.tick))].sort();
  const ranges: Array<[number, number]> = [];

  let i = 0;
  while (i < ticks.length) {
    const startTick = ticks[i];
    const endTick = Math.min(startTick + windowSize - 1, ticks[ticks.length - 1]);
    ranges.push([startTick, endTick]);
    i += windowSize - overlap;
  }

  return ranges;
}

/**
 * Generates overlapping tick windows from ordered signals.
 */
export function* generateOverlappingTickWindows(
  signals: OrderedSignal[],
  config: TickWindowConfig,
  options: {
    abortSignal?: AbortSignal;
  } = {},
): Generator<TickWindow> {
  validateTickWindowConfig(config);

  if (signals.length === 0) return;

  const fingerprint = createConfigFingerprint(config.windowSize, config.overlap, config.maxItems);
  const ticks = [...new Set(signals.map((s) => s.metadata.tick))].sort();

  let windowIndex = 0;
  let startIdx = 0;

  while (startIdx < ticks.length) {
    if (options.abortSignal?.aborted) return;

    const startTick = ticks[startIdx];
    const endTickIdx = Math.min(startIdx + config.windowSize - 1, ticks.length - 1);
    const endTick = ticks[endTickIdx];

    const windowSignals: OrderedSignal[] = [];
    const uniqueNodes = new Set<string>();

    for (const s of signals) {
      if (s.metadata.tick >= startTick && s.metadata.tick <= endTick) {
        windowSignals.push(s);
        uniqueNodes.add(s.metadata.node);
      }
    }

    const nodes = Array.from(uniqueNodes).sort();
    const isComplete = windowSignals.length > 0 && endTickIdx - startIdx + 1 === config.windowSize;

    yield {
      id: `window-${startTick}-${endTick}-${windowIndex}`,
      startTick,
      endTick,
      signals: windowSignals,
      nodes,
      windowIndex,
      configFingerprint: fingerprint,
      isComplete,
    };

    windowIndex++;
    startIdx += config.windowSize - config.overlap;
  }
}

// ============================================================================
// Backpressure Management
// ============================================================================

/**
 * Creates a backpressure monitor for window processing.
 */
export function createBackpressureMonitor(maxQueueDepth: number = 100): {
  update: (queueDepth: number) => BackpressureState;
  shouldBackpressure: (state: BackpressureState) => boolean;
} {
  return {
    update(queueDepth: number): BackpressureState {
      return {
        queueDepth,
        isBackpressured: queueDepth >= maxQueueDepth,
        maxQueueDepth,
      };
    },
    shouldBackpressure(state: BackpressureState): boolean {
      return state.isBackpressured;
    },
  };
}

// ============================================================================
// Window Processing with Backpressure
// ============================================================================

/**
 * Processes signals into windows with backpressure control.
 */
export function processSignalsToWindows(
  signals: OrderedSignal[],
  config: TickWindowConfig,
  options: {
    abortSignal?: AbortSignal;
    maxQueueDepth?: number;
    backpressureCallback?: (state: BackpressureState) => void;
  } = {},
): WindowResult {
  const maxQueueDepth = options.maxQueueDepth ?? 100;
  const backpressureMonitor = createBackpressureMonitor(maxQueueDepth);

  const windows: TickWindow[] = [];
  const drops: WindowDrop[] = [];
  let aborted = false;
  let ticksProcessed = 0;

  // Pre-flight abort check: if already aborted, no windows are produced.
  if (options.abortSignal?.aborted) {
    aborted = true;
  }

  // Track queue depth (number of pending signals)
  let queueDepth = 0;

  const generator = config.overlap > 0
    ? generateOverlappingTickWindows(signals, config, { abortSignal: options.abortSignal })
    : generateTickWindows(signals, config, { abortSignal: options.abortSignal });

  for (const window of generator) {
    // Check abort
    if (options.abortSignal?.aborted) {
      aborted = true;
      break;
    }

    // Update queue depth
    queueDepth = window.signals.length;
    const bpState = backpressureMonitor.update(queueDepth);

    // Check backpressure
    if (backpressureMonitor.shouldBackpressure(bpState)) {
      options.backpressureCallback?.(bpState);
      drops.push({
        signals: window.signals,
        reason: 'BACKPRESSURE_APPLIED',
        details: `Queue depth ${queueDepth} exceeded max ${maxQueueDepth}`,
      });
      continue;
    }

    // Check maxItems
    if (config.maxItems !== undefined && window.signals.length > config.maxItems) {
      drops.push({
        signals: window.signals.slice(config.maxItems),
        reason: 'MAX_ITEMS_EXCEEDED',
        details: `Window has ${window.signals.length} signals, max is ${config.maxItems}`,
      });
      window.signals = window.signals.slice(0, config.maxItems);
    }

    windows.push(window);
    ticksProcessed = Math.max(ticksProcessed, window.endTick + 1);
  }

  const finalBackpressure = backpressureMonitor.update(queueDepth);

  return {
    windows,
    drops,
    backpressure: finalBackpressure,
    aborted,
    ticksProcessed,
  };
}

// ============================================================================
// Fixed-Window Receipt
// ============================================================================

/**
 * Receipt for a processed tick window.
 */
export interface TickWindowReceipt {
  /** Window ID */
  id: string;
  /** Start tick */
  startTick: number;
  /** End tick */
  endTick: number;
  /** Signal count */
  signalCount: number;
  /** Node count */
  nodeCount: number;
  /** Config fingerprint */
  configFingerprint: string;
  /** Whether complete */
  isComplete: boolean;
  /** Processing timestamp */
  timestamp: number;
}

/**
 * Generates receipts for processed windows.
 */
export function generateWindowReceipts(windows: TickWindow[]): TickWindowReceipt[] {
  return windows.map((w) => ({
    id: w.id,
    startTick: w.startTick,
    endTick: w.endTick,
    signalCount: w.signals.length,
    nodeCount: w.nodes.length,
    configFingerprint: w.configFingerprint,
    isComplete: w.isComplete,
    timestamp: Date.now(),
  }));
}

// ============================================================================
// Config Fingerprint Verification
// ============================================================================

/**
 * Verifies that a config fingerprint matches expected values.
 */
export function verifyConfigFingerprint(
  fingerprint: string,
  expectedWindowSize: number,
  expectedOverlap: number,
  expectedMaxItems?: number,
): boolean {
  const actual = createConfigFingerprint(expectedWindowSize, expectedOverlap, expectedMaxItems);
  return fingerprint === actual;
}
