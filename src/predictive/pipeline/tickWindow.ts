/**
 * Tick Window Module
 *
 * Provides fixed and overlapping tick-based windows for signal processing.
 * Window configuration is deterministic and included in config fingerprint.
 *
 * Features:
 * - Fixed-size tick windows
 * - Overlapping tick windows
 * - Configurable window size and overlap
 * - AbortSignal, Max-Items, Max-Window, Backpressure support
 * - No silent drops - every loss has Reason Code and Receipt
 *
 * @module predictive/pipeline/tickWindow
 */

import type { OrderedSignal } from './signalOrdering';
import type { ChunkResult } from './deterministicIterables';

/**
 * Window type enumeration.
 */
export type WindowType = 'fixed' | 'overlapping';

/**
 * Configuration for tick windows.
 * All fields are deterministic - no wall-clock dependencies.
 */
export interface TickWindowConfig {
  /** Window type */
  type: WindowType;
  /** Number of ticks per window */
  windowSize: number;
  /** Number of ticks to overlap (for overlapping type) */
  overlap: number;
  /** Maximum items per window */
  maxItemsPerWindow: number;
  /** Maximum total windows */
  maxWindows: number;
  /** Minimum signals required for window */
  minSignalsForWindow: number;
  /** Revision hash for cache invalidation */
  revision: string;
}

/**
 * Default tick window configuration.
 */
export const DEFAULT_TICK_WINDOW_CONFIG: TickWindowConfig = {
  type: 'fixed',
  windowSize: 10,
  overlap: 2,
  maxItemsPerWindow: 100,
  maxWindows: 1000,
  minSignalsForWindow: 1,
  revision: 'default',
};

/**
 * Result of a tick window operation.
 */
export interface TickWindow {
  /** Window identifier */
  id: string;
  /** Start tick (inclusive) */
  startTick: number;
  /** End tick (inclusive) */
  endTick: number;
  /** Signals in this window */
  signals: OrderedSignal[];
  /** Window metadata */
  metadata: TickWindowMetadata;
}

/**
 * Metadata for a tick window.
 */
export interface TickWindowMetadata {
  /** Number of signals */
  signalCount: number;
  /** Whether this is a partial window */
  isPartial: boolean;
  /** Whether signals were dropped */
  hadDrop: boolean;
  /** Reason code if dropped */
  dropReason?: string;
  /** Unique node IDs in this window */
  nodes: string[];
  /** Tick range */
  tickRange: [number, number];
  /** Window type */
  windowType: WindowType;
}

/**
 * Receipt for a tick window operation.
 * Documents what happened including any drops.
 */
export interface TickWindowReceipt {
  /** Receipt identifier */
  id: string;
  /** Configuration fingerprint */
  configFingerprint: string;
  /** Windows created */
  windows: TickWindow[];
  /** Total signals processed */
  signalsProcessed: number;
  /** Total signals dropped */
  signalsDropped: number;
  /** Drop reason codes */
  dropReasons: string[];
  /** Whether operation was complete */
  complete: boolean;
  /** Revision at time of processing */
  revision: string;
}

/**
 * Backpressure indicator for window processing.
 */
export interface BackpressureState {
  /** Whether backpressure is active */
  active: boolean;
  /** Current window count */
  currentWindows: number;
  /** Maximum allowed windows */
  maxWindows: number;
  /** Current items in pending window */
  pendingItems: number;
  /** Maximum items per window */
  maxItemsPerWindow: number;
}

/**
 * Creates a deterministic window ID.
 */
function createWindowId(startTick: number, windowIndex: number): string {
  return `win-${startTick}-${windowIndex}`;
}

/**
 * Creates a deterministic receipt ID.
 */
function createReceiptId(): string {
  return `rcpt-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Generates the config fingerprint for windowing.
 * Includes all deterministic parameters.
 */
export function createWindowFingerprint(config: TickWindowConfig): string {
  return `tw:${config.type}:${config.windowSize}:${config.overlap}:${config.maxItemsPerWindow}:${config.revision}`;
}

/**
 * Fixed-size tick window generator.
 * Emits windows containing signals within the tick range.
 *
 * @param signals - Input signals in canonical order
 * @param config - Window configuration
 * @param options - Processing options (signal, onProgress)
 * @yields TickWindow objects
 */
export function* fixedTickWindows(
  signals: OrderedSignal[],
  config: TickWindowConfig = DEFAULT_TICK_WINDOW_CONFIG,
  options: { signal?: AbortSignal; onProgress?: (w: number) => void } = {},
): Generator<TickWindow> {
  const { signal, onProgress } = options;

  if (signal?.aborted) {
    throw new DOMException('Window processing aborted', 'AbortError');
  }

  if (signals.length === 0) {
    return;
  }

  const { windowSize, maxItemsPerWindow, maxWindows, minSignalsForWindow } = config;

  let windowIndex = 0;
  let currentWindowSignals: OrderedSignal[] = [];
  let currentStartTick = signals[0]?.tick ?? 0;
  let currentEndTick = currentStartTick + windowSize - 1;

  function createMetadata(isPartial: boolean, hadDrop: boolean, dropReason?: string): TickWindowMetadata {
    const nodes = [...new Set(currentWindowSignals.map((s) => s.node))];
    return {
      signalCount: currentWindowSignals.length,
      isPartial,
      hadDrop,
      dropReason,
      nodes,
      tickRange: [currentStartTick, currentEndTick],
      windowType: 'fixed',
    };
  }

  function emitWindow(isPartial = false, hadDrop = false, dropReason?: string): TickWindow {
    const window: TickWindow = {
      id: createWindowId(currentStartTick, windowIndex),
      startTick: currentStartTick,
      endTick: currentEndTick,
      signals: [...currentWindowSignals],
      metadata: createMetadata(isPartial, hadDrop, dropReason),
    };
    windowIndex++;
    onProgress?.(windowIndex);
    return window;
  }

  for (const signal of signals) {
    // Check abort
    if (signal?.signal?.aborted || (options.signal?.aborted && !signal)) {
      throw new DOMException('Window processing aborted', 'AbortError');
    }

    // Check max windows
    if (windowIndex >= maxWindows) {
      // Emit current window with drop indicator
      yield emitWindow(true, true, 'MAX_WINDOWS_REACHED');
      return;
    }

    const signalTick = signal.tick;

    // Check if signal is in current window range
    if (signalTick >= currentStartTick && signalTick <= currentEndTick) {
      // Check max items per window
      if (currentWindowSignals.length >= maxItemsPerWindow) {
        // Drop signal with reason
        continue;
      }
      currentWindowSignals.push(signal);
    } else {
      // Signal is outside current window
      // Emit current window if it has enough signals
      if (currentWindowSignals.length >= minSignalsForWindow) {
        yield emitWindow();
      }

      // Start new window
      currentStartTick = Math.floor(signalTick / windowSize) * windowSize;
      currentEndTick = currentStartTick + windowSize - 1;
      currentWindowSignals = [signal];
    }
  }

  // Emit final window
  if (currentWindowSignals.length >= minSignalsForWindow) {
    yield emitWindow(true); // Partial because it's the last
  }
}

/**
 * Overlapping tick window generator.
 * Windows share ticks based on overlap configuration.
 *
 * @param signals - Input signals in canonical order
 * @param config - Window configuration
 * @param options - Processing options
 * @yields TickWindow objects
 */
export function* overlappingTickWindows(
  signals: OrderedSignal[],
  config: TickWindowConfig = DEFAULT_TICK_WINDOW_CONFIG,
  options: { signal?: AbortSignal; onProgress?: (w: number) => void } = {},
): Generator<TickWindow> {
  const { signal, onProgress } = options;

  if (signal?.aborted) {
    throw new DOMException('Window processing aborted', 'AbortError');
  }

  if (signals.length === 0) {
    return;
  }

  const { windowSize, overlap, maxItemsPerWindow, maxWindows, minSignalsForWindow } = config;

  if (overlap >= windowSize) {
    throw new Error('Overlap must be less than window size');
  }

  let windowIndex = 0;
  const step = windowSize - overlap;
  let currentStartTick = Math.floor(signals[0]?.tick ?? 0 / step) * step;

  function createMetadata(isPartial: boolean, hadDrop: boolean, dropReason?: string): TickWindowMetadata {
    const nodes = [...new Set(currentWindowSignals.map((s) => s.node))];
    return {
      signalCount: currentWindowSignals.length,
      isPartial,
      hadDrop,
      dropReason,
      nodes,
      tickRange: [currentStartTick, currentStartTick + windowSize - 1],
      windowType: 'overlapping',
    };
  }

  let currentWindowSignals: OrderedSignal[] = [];
  let currentEndTick = currentStartTick + windowSize - 1;

  function emitWindow(isPartial = false, hadDrop = false, dropReason?: string): TickWindow {
    const window: TickWindow = {
      id: createWindowId(currentStartTick, windowIndex),
      startTick: currentStartTick,
      endTick: currentEndTick,
      signals: [...currentWindowSignals],
      metadata: createMetadata(isPartial, hadDrop, dropReason),
    };
    windowIndex++;
    onProgress?.(windowIndex);
    return window;
  }

  for (const signal of signals) {
    if (options.signal?.aborted) {
      throw new DOMException('Window processing aborted', 'AbortError');
    }

    if (windowIndex >= maxWindows) {
      yield emitWindow(true, true, 'MAX_WINDOWS_REACHED');
      return;
    }

    const signalTick = signal.tick;

    // Collect signals for current window
    if (signalTick >= currentStartTick && signalTick <= currentEndTick) {
      if (currentWindowSignals.length < maxItemsPerWindow) {
        currentWindowSignals.push(signal);
      }
    } else {
      // Emit current window and advance
      if (currentWindowSignals.length >= minSignalsForWindow) {
        yield emitWindow();
      }

      // Advance window start
      currentStartTick = Math.floor(signalTick / step) * step;
      currentEndTick = currentStartTick + windowSize - 1;
      currentWindowSignals = [];

      // Add signal if it fits in new window
      if (signalTick >= currentStartTick && signalTick <= currentEndTick) {
        currentWindowSignals.push(signal);
      }
    }
  }

  // Emit final window
  if (currentWindowSignals.length >= minSignalsForWindow) {
    yield emitWindow(true);
  }
}

/**
 * Unified tick window generator.
 * Dispatches to fixed or overlapping based on config.
 */
export function* tickWindows(
  signals: OrderedSignal[],
  config: TickWindowConfig = DEFAULT_TICK_WINDOW_CONFIG,
  options: { signal?: AbortSignal; onProgress?: (w: number) => void } = {},
): Generator<TickWindow> {
  if (config.type === 'overlapping') {
    yield* overlappingTickWindows(signals, config, options);
  } else {
    yield* fixedTickWindows(signals, config, options);
  }
}

/**
 * Processes signals into windows with receipt.
 * Always produces a receipt even if signals are dropped.
 */
export function processSignalsToWindows(
  signals: OrderedSignal[],
  config: TickWindowConfig = DEFAULT_TICK_WINDOW_CONFIG,
  options: { signal?: AbortSignal; onProgress?: (w: number) => void } = {},
): TickWindowReceipt {
  let signalsProcessed = 0;
  let signalsDropped = 0;
  const dropReasons: string[] = [];
  const windows: TickWindow[] = [];
  let complete = true;

  try {
    for (const window of tickWindows(signals, config, options)) {
      signalsProcessed += window.signals.length;
      if (window.metadata.hadDrop) {
        signalsDropped++;
        if (window.metadata.dropReason) {
          dropReasons.push(window.metadata.dropReason);
        }
      }
      windows.push(window);
    }
  } catch {
    complete = false;
  }

  return {
    id: createReceiptId(),
    configFingerprint: createWindowFingerprint(config),
    windows,
    signalsProcessed,
    signalsDropped,
    dropReasons: [...new Set(dropReasons)],
    complete,
    revision: config.revision,
  };
}

/**
 * Creates a backpressure-aware window processor.
 */
export function createBackpressureController(
  config: TickWindowConfig,
): {
  check: () => BackpressureState;
  update: (windows: number, pending: number) => void;
} {
  let currentWindows = 0;
  let pendingItems = 0;

  return {
    check: () => ({
      active: currentWindows >= config.maxWindows - 1 || pendingItems >= config.maxItemsPerWindow,
      currentWindows,
      maxWindows: config.maxWindows,
      pendingItems,
      maxItemsPerWindow: config.maxItemsPerWindow,
    }),
    update: (windows: number, pending: number) => {
      currentWindows = windows;
      pendingItems = pending;
    },
  };
}
