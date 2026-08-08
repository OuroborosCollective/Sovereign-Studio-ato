/**
 * Deterministic Tick Windows.
 *
 * Issue #1170: windows are bounded by causal tick ranges and a fixed
 * (config-fingerprinted) size/overlap. Window identity and hashes are derived
 * purely from tick indices and content hashes - never from wall-clock - so that
 * replay of the same recorded signals reproduces identical windows and hashes.
 *
 * @module predictive/pipeline/tickWindow
 */

import { hashCanonical } from '../inference/hash';
import { canonicalOrder, type PipelineSignal } from './signalOrdering';
import { chunkwise, chunkwiseOverlap, pairwise, runningDifference } from './deterministicIterables';

/** Configuration fingerprinted into every window receipt. */
export interface TickWindowConfig {
  /** Number of ticks per window. */
  windowSize: number;
  /** Overlap in ticks between consecutive windows (0 = disjoint). */
  overlap: number;
  /** Maximum number of windows emitted (backpressure bound). */
  maxWindows: number;
  /** Maximum ticks consumed (backpressure bound). */
  maxTicks: number;
}

export const DEFAULT_TICK_WINDOW_CONFIG: TickWindowConfig = {
  windowSize: 8,
  overlap: 0,
  maxWindows: 1024,
  maxTicks: 1_000_000,
};

/** Reason codes for non-silent signal loss. */
export type DropReasonCode =
  | 'SEQUENCE_NON_MONOTONIC'
  | 'DUPLICATE_KEY'
  | 'WINDOW_LIMIT_REACHED'
  | 'TICK_LIMIT_REACHED'
  | 'ABORTED';

export interface SignalDrop {
  reason: DropReasonCode;
  node: string;
  sequence: number;
  tick: number;
  detail: string;
}

/** A bounded, deterministic tick window with a content hash. */
export interface TickWindow {
  /** Window index in emission order (0-based). */
  index: number;
  /** Inclusive start tick. */
  startTick: number;
  /** Inclusive end tick. */
  endTick: number;
  /** Tick count in this window. */
  tickCount: number;
  /** Per-tick content hashes (causal order). */
  tickHashes: string[];
  /** Aggregated content hash over the window. */
  contentHash: string;
  /** SHA-256 over the window config + structural fields (tamper-evident). */
  windowHash: string;
  /** True when closed by source exhaustion (not by a limit). */
  closedNaturally: boolean;
}

/** A window paired with its accepted signal slice (causal order). */
export interface TickWindowSlice extends TickWindow {
  signals: PipelineSignal[];
}

/** Deterministic hash of a single signal's causal payload (no timestamp). */
export function signalTickHash(signal: PipelineSignal): string {
  return hashCanonical({
    node: signal.node,
    sequence: signal.sequence,
    tick: signal.tick,
    value: signal.value,
  });
}

/** Hash of the window config (bound into receipts). */
export function tickWindowConfigHash(config: TickWindowConfig): string {
  return hashCanonical({
    windowSize: config.windowSize,
    overlap: config.overlap,
    maxWindows: config.maxWindows,
    maxTicks: config.maxTicks,
  });
}

function buildWindow(
  index: number,
  signals: PipelineSignal[],
  config: TickWindowConfig,
  closedNaturally: boolean,
): TickWindowSlice {
  const tickHashes = signals.map(signalTickHash);
  const startTick = signals.length > 0 ? signals[0].tick : 0;
  const endTick = signals.length > 0 ? signals[signals.length - 1].tick : 0;
  const contentHash = hashCanonical(tickHashes);
  const windowHash = hashCanonical({
    index,
    startTick,
    endTick,
    tickCount: signals.length,
    contentHash,
    configHash: tickWindowConfigHash(config),
    closedNaturally,
  });
  return {
    index,
    startTick,
    endTick,
    tickCount: signals.length,
    tickHashes,
    contentHash,
    windowHash,
    closedNaturally,
    signals,
  };
}

export interface WindowingResult {
  config: TickWindowConfig;
  configHash: string;
  windows: TickWindowSlice[];
  /** Pairwise deltas between consecutive window content hashes. */
  windowDeltas: string[];
  drops: SignalDrop[];
  /** Accepted signals in canonical order (post-drop), sliced into windows. */
  accepted: PipelineSignal[];
  /** Total ticks consumed (excluding dropped). */
  consumedTicks: number;
}

/**
 * Build deterministic tick windows from validated signals.
 *
 * Signals are canonically ordered first. Out-of-order or duplicate causal keys
 * are recorded as drops with reason codes (never silently dropped). Windows are
 * sliced by the configured size/overlap. Emission stops at maxWindows/maxTicks.
 */
export function buildTickWindows(
  signals: readonly PipelineSignal[],
  config: TickWindowConfig = DEFAULT_TICK_WINDOW_CONFIG,
): WindowingResult {
  if (!Number.isInteger(config.windowSize) || config.windowSize <= 0) {
    throw new RangeError('windowSize must be a positive integer');
  }
  if (!Number.isInteger(config.overlap) || config.overlap < 0 || config.overlap >= config.windowSize) {
    throw new RangeError('overlap must be a non-negative integer less than windowSize');
  }

  const configHash = tickWindowConfigHash(config);
  const drops: SignalDrop[] = [];
  const accepted: PipelineSignal[] = [];

  const duplicates = new Set(findDuplicateKeyStrings(signals));
  let lastSeqPerNode = new Map<string, number>();

  for (const s of canonicalOrder(signals)) {
    const key = `${s.node}:${s.sequence}`;
    if (duplicates.has(key)) {
      drops.push({
        reason: 'DUPLICATE_KEY',
        node: s.node,
        sequence: s.sequence,
        tick: s.tick,
        detail: `duplicate causal key ${key}`,
      });
      continue;
    }
    const last = lastSeqPerNode.get(s.node);
    if (last !== undefined && s.sequence <= last) {
      drops.push({
        reason: 'SEQUENCE_NON_MONOTONIC',
        node: s.node,
        sequence: s.sequence,
        tick: s.tick,
        detail: `sequence ${s.sequence} <= last ${last} for node ${s.node}`,
      });
      continue;
    }
    if (accepted.length >= config.maxTicks) {
      drops.push({
        reason: 'TICK_LIMIT_REACHED',
        node: s.node,
        sequence: s.sequence,
        tick: s.tick,
        detail: `maxTicks ${config.maxTicks} reached`,
      });
      break;
    }
    lastSeqPerNode.set(s.node, s.sequence);
    accepted.push(s);
  }

  // Slice into windows using the allowlisted primitives.
  const step = config.windowSize - config.overlap;
  const slicer = config.overlap > 0
    ? chunkwiseOverlap(accepted, config.windowSize, step)
    : chunkwise(accepted, config.windowSize);

  const windows: TickWindowSlice[] = [];
  let windowIndex = 0;
  for (const slice of slicer) {
    if (windows.length >= config.maxWindows) {
      drops.push({
        reason: 'WINDOW_LIMIT_REACHED',
        node: slice[0]?.node ?? '',
        sequence: slice[0]?.sequence ?? 0,
        tick: slice[0]?.tick ?? 0,
        detail: `maxWindows ${config.maxWindows} reached`,
      });
      break;
    }
    const closedNaturally = slice.length === config.windowSize;
    windows.push(buildWindow(windowIndex, slice, config, closedNaturally));
    windowIndex += 1;
  }

  // Mark the final window as naturally closed when source exhaustion occurred
  // before any configured limit (no drops caused by limits).
  if (windows.length > 0) {
    const limitDrop = drops.some(d => d.reason === 'WINDOW_LIMIT_REACHED' || d.reason === 'TICK_LIMIT_REACHED');
    windows[windows.length - 1].closedNaturally = !limitDrop;
  }

  const windowDeltas = computeWindowDeltas(windows);

  return {
    config,
    configHash,
    windows,
    windowDeltas,
    drops,
    accepted,
    consumedTicks: accepted.length,
  };
}

/** Deterministic content-hash deltas between consecutive windows. */
export function computeWindowDeltas(windows: readonly TickWindow[]): string[] {
  return [...runningDifference(windowHashIntegers(windows))].map(n => n.toString(16).padStart(8, '0'));
}

function* windowHashIntegers(windows: readonly TickWindow[]): Generator<number> {
  for (const w of windows) {
    // Use the first 8 hex chars (32-bit) of each window hash as a deterministic
    // numeric proxy for delta computation. This is a projection, not a truth hash.
    yield parseInt(w.windowHash.slice(0, 8), 16);
  }
}

/** Pairwise (prev, curr) window hashes - exported for parity tests. */
export function pairwiseWindowHashes(windows: readonly TickWindow[]): [string, string][] {
  return [...pairwise(windows.map(w => w.windowHash))];
}

function findDuplicateKeyStrings(signals: readonly PipelineSignal[]): string[] {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const s of signals) {
    const key = `${s.node}:${s.sequence}`;
    if (seen.has(key)) {
      duplicates.add(key);
    } else {
      seen.add(key);
    }
  }
  return [...duplicates].sort();
}
