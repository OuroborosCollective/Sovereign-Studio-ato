/**
 * Replay - Signal Replay with Deterministic Parity
 *
 * Enables offline replay of recorded signals with exact reproduction
 * of windows, deltas, feature vectors, and hashes.
 *
 * @module predictive/pipeline/replay
 */

import type { Signal } from '../types';
import type { OrderedSignal } from './signalOrdering';
import type { TickWindow } from './tickWindow';
import type { FeatureVector, WindowReceipt } from './deterministicIterables';
import { TickWindowConfig } from './deterministicIterables';
import { orderSignals, generateOrderingReceipt, OrderingReceipt } from './signalOrdering';
import { processSignalsToWindows, generateWindowReceipts } from './tickWindow';
import { processWindowToFeatures, verifyFeatureParity } from './featureVector';

// ============================================================================
// Replay Types
// ============================================================================

/**
 * Recorded signal set for replay.
 */
export interface RecordedSignalSet {
  /** Signals in recording order */
  signals: Signal[];
  /** Revision at recording time */
  revision: string;
  /** Recording timestamp */
  recordedAt: number;
  /** Config fingerprint at recording time */
  configFingerprint: string;
  /** Original feature vectors (for parity verification) */
  featureVectors: FeatureVector[];
}

/**
 * Replay result comparing live and replay outputs.
 */
export interface ReplayResult {
  /** Original feature vectors */
  originalVectors: FeatureVector[];
  /** Replay feature vectors */
  replayVectors: FeatureVector[];
  /** Parity verification results */
  parityResults: Array<{ index: number; equal: boolean; diff?: string }>;
  /** All parity checks passed */
  parityVerified: boolean;
  /** Windows generated during replay */
  windows: ReturnType<typeof generateWindowReceipts>;
  /** Replay duration in ms */
  durationMs: number;
  /** Any errors during replay */
  errors: string[];
}

/**
 * Replay configuration.
 */
export interface ReplayConfig {
  /** Tick window configuration */
  windowConfig: TickWindowConfig;
  /** Abort signal for cancellation */
  abortSignal?: AbortSignal;
  /** Maximum replay duration in ms */
  maxDurationMs?: number;
}

// ============================================================================
// Signal Recording
// ============================================================================

/**
 * Records signals for later replay.
 */
export class SignalRecorder {
  private signals: Signal[] = [];
  private revision: string = '';
  private recordedAt: number = 0;
  private configFingerprint: string = '';

  /**
   * Starts a new recording session.
   */
  startRecording(revision: string, configFingerprint: string): void {
    this.signals = [];
    this.revision = revision;
    this.recordedAt = Date.now();
    this.configFingerprint = configFingerprint;
  }

  /**
   * Adds signals to the recording.
   */
  record(signals: Signal[]): void {
    this.signals.push(...signals);
  }

  /**
   * Finalizes and returns the recorded signal set.
   * ⚡ Bolt: .slice() replaces array spread iterator for faster array cloning.
   */
  finishRecording(originalFeatureVectors?: FeatureVector[]): RecordedSignalSet {
    const set: RecordedSignalSet = {
      signals: this.signals.slice(),
      revision: this.revision,
      recordedAt: this.recordedAt,
      configFingerprint: this.configFingerprint,
      featureVectors: originalFeatureVectors ?? [],
    };

    // Clear for potential reuse
    this.signals = [];
    this.recordedAt = 0;

    return set;
  }

  /**
   * Gets current recording count.
   */
  getCount(): number {
    return this.signals.length;
  }
}

// ============================================================================
// Signal Replay
// ============================================================================

/**
 * Replays a recorded signal set through the pipeline.
 * Returns parity verification results.
 */
export function replaySignals(
  recordedSet: RecordedSignalSet,
  config: ReplayConfig,
): ReplayResult {
  const startTime = performance.now();
  const errors: string[] = [];

  try {
    // Order signals canonically
    let orderedSignals: OrderedSignal[];
    try {
      orderedSignals = orderSignals(recordedSet.signals);
    } catch (e) {
      errors.push(`Signal ordering failed: ${e}`);
      return createEmptyReplayResult(recordedSet.featureVectors, startTime, errors);
    }

    // Generate windows
    let windowResult;
    try {
      windowResult = processSignalsToWindows(orderedSignals, config.windowConfig, {
        abortSignal: config.abortSignal,
      });
    } catch (e) {
      errors.push(`Window processing failed: ${e}`);
      return createEmptyReplayResult(recordedSet.featureVectors, startTime, errors);
    }

    // Extract features from replay windows
    // ⚡ Bolt: Preallocated array and indexed loop pass.
    const windows = windowResult.windows;
    const replayVectors: FeatureVector[] = new Array(windows.length);
    for (let i = 0; i < windows.length; i++) {
      const result = processWindowToFeatures(windows[i], true);
      replayVectors[i] = result.featureVector;
    }

    // Verify parity
    const parityResult = verifyParity(recordedSet.featureVectors, replayVectors);

    return {
      originalVectors: recordedSet.featureVectors,
      replayVectors,
      parityResults: parityResult.results,
      parityVerified: parityResult.parityVerified,
      windows: generateWindowReceipts(windowResult.windows),
      durationMs: performance.now() - startTime,
      errors,
    };
  } catch (e) {
    errors.push(`Replay failed: ${e}`);
    return createEmptyReplayResult(recordedSet.featureVectors, startTime, errors);
  }
}

/**
 * Verifies parity between original and replay feature vectors.
 * ⚡ Bolt: Populates result objects directly without object spread allocations
 * and accumulates `parityVerified` in a single loop pass.
 */
function verifyParity(
  original: FeatureVector[],
  replay: FeatureVector[],
): {
  results: Array<{ index: number; equal: boolean; diff?: string }>;
  parityVerified: boolean;
} {
  const origLen = original.length;
  const repLen = replay.length;
  let parityVerified = true;

  if (origLen !== repLen) {
    const maxLen = origLen > repLen ? origLen : repLen;
    const results: Array<{ index: number; equal: boolean; diff?: string }> = new Array(maxLen);
    for (let i = 0; i < maxLen; i++) {
      if (i < origLen && i < repLen) {
        const parity = verifyFeatureParity(original[i], replay[i]);
        if (!parity.equal) parityVerified = false;
        results[i] = { index: i, equal: parity.equal, diff: parity.diff };
      } else {
        parityVerified = false;
        results[i] = {
          index: i,
          equal: false,
          diff: `Length mismatch at index ${i}: original has ${origLen}, replay has ${repLen}`,
        };
      }
    }
    return { results, parityVerified: false };
  }

  const results: Array<{ index: number; equal: boolean; diff?: string }> = new Array(origLen);
  for (let i = 0; i < origLen; i++) {
    const parity = verifyFeatureParity(original[i], replay[i]);
    if (!parity.equal) parityVerified = false;
    results[i] = { index: i, equal: parity.equal, diff: parity.diff };
  }

  return { results, parityVerified };
}

/**
 * Creates an empty replay result for error cases.
 * ⚡ Bolt: Single-pass pre-allocated indexed loop replaces .map() callback allocations.
 */
function createEmptyReplayResult(
  originalVectors: FeatureVector[],
  startTime: number,
  errors: string[],
): ReplayResult {
  const len = originalVectors.length;
  const parityResults: Array<{ index: number; equal: boolean; diff?: string }> = new Array(len);
  for (let i = 0; i < len; i++) {
    parityResults[i] = {
      index: i,
      equal: false,
      diff: 'Replay failed before vector generation',
    };
  }

  return {
    originalVectors,
    replayVectors: [],
    parityResults,
    parityVerified: false,
    windows: [],
    durationMs: performance.now() - startTime,
    errors,
  };
}

// ============================================================================
// Live vs Replay Comparison
// ============================================================================

/**
 * Result of comparing live and replay outputs.
 */
export interface LiveReplayComparison {
  /** Live outputs */
  live: {
    vectors: FeatureVector[];
    windowCount: number;
    totalSignals: number;
  };
  /** Replay outputs */
  replay: {
    vectors: FeatureVector[];
    windowCount: number;
    totalSignals: number;
  };
  /** Semantically identical */
  semanticallyIdentical: boolean;
  /** Differences found */
  differences: string[];
}

/**
 * Compares live and replay outputs for semantic identity.
 * ⚡ Bolt: Single Map lookup pass using direct Map queries and deletion tracking
 * replaces secondary Map allocations (`replayMap`) and separate key iteration loops.
 */
export function compareLiveReplay(
  liveResult: { vectors: FeatureVector[]; windows: unknown[]; signals: Signal[] },
  replayResult: { vectors: FeatureVector[]; windows: unknown[]; signals: Signal[] },
): LiveReplayComparison {
  const differences: string[] = [];

  // Compare window counts
  if (liveResult.windows.length !== replayResult.windows.length) {
    differences.push(
      `Window count mismatch: live=${liveResult.windows.length}, replay=${replayResult.windows.length}`,
    );
  }

  // Compare signal counts
  if (liveResult.signals.length !== replayResult.signals.length) {
    differences.push(
      `Signal count mismatch: live=${liveResult.signals.length}, replay=${replayResult.signals.length}`,
    );
  }

  // Populate liveMap with live feature vectors by tick range key
  const liveMap = new Map<string, FeatureVector>();
  const liveVecs = liveResult.vectors;
  for (let i = 0; i < liveVecs.length; i++) {
    const v = liveVecs[i];
    liveMap.set(`${v.tickRange[0]}-${v.tickRange[1]}`, v);
  }

  // Check replay vectors directly against liveMap without building replayMap
  const replayVecs = replayResult.vectors;
  for (let i = 0; i < replayVecs.length; i++) {
    const replayVec = replayVecs[i];
    const key = `${replayVec.tickRange[0]}-${replayVec.tickRange[1]}`;
    const liveVec = liveMap.get(key);
    if (!liveVec) {
      differences.push(`Live missing vector for tick range ${key}`);
    } else {
      const parity = verifyFeatureParity(liveVec, replayVec);
      if (!parity.equal) {
        differences.push(`Parity mismatch at ${key}: ${parity.diff}`);
      }
      liveMap.delete(key);
    }
  }

  // Any remaining keys in liveMap were missing from replay
  for (const [key] of liveMap) {
    differences.push(`Replay missing vector for tick range ${key}`);
  }

  return {
    live: {
      vectors: liveResult.vectors,
      windowCount: liveResult.windows.length,
      totalSignals: liveResult.signals.length,
    },
    replay: {
      vectors: replayResult.vectors,
      windowCount: replayResult.windows.length,
      totalSignals: replayResult.signals.length,
    },
    semanticallyIdentical: differences.length === 0,
    differences,
  };
}

// ============================================================================
// Full Pipeline Integration
// ============================================================================

/**
 * Full signal pipeline that can run in both live and replay modes.
 */
export class DeterministicSignalPipeline {
  private recorder: SignalRecorder;
  private windowConfig: TickWindowConfig;
  private abortSignal?: AbortSignal;

  constructor(windowConfig: TickWindowConfig, abortSignal?: AbortSignal) {
    this.recorder = new SignalRecorder();
    this.windowConfig = windowConfig;
    this.abortSignal = abortSignal;
  }

  /**
   * Processes signals through the pipeline (live mode).
   */
  processSignals(signals: Signal[], revision: string): {
    windows: ReturnType<typeof generateWindowReceipts>;
    receipts: WindowReceipt[];
    featureVectors: FeatureVector[];
  } {
    // Order signals
    const orderedSignals = orderSignals(signals);

    // Generate windows
    const windowResult = processSignalsToWindows(orderedSignals, this.windowConfig, {
      abortSignal: this.abortSignal,
    });

    // Extract features
    // ⚡ Bolt: Preallocated arrays and indexed loop pass.
    const windows = windowResult.windows;
    const receipts: WindowReceipt[] = new Array(windows.length);
    const featureVectors: FeatureVector[] = new Array(windows.length);

    for (let i = 0; i < windows.length; i++) {
      const result = processWindowToFeatures(windows[i], false);
      receipts[i] = result.receipt;
      featureVectors[i] = result.featureVector;
    }

    return {
      windows: generateWindowReceipts(windowResult.windows),
      receipts,
      featureVectors,
    };
  }

  /**
   * Starts recording for replay.
   */
  startRecording(revision: string): void {
    const fingerprint = `${this.windowConfig.windowSize}|${this.windowConfig.overlap}`;
    this.recorder.startRecording(revision, fingerprint);
  }

  /**
   * Records signals for later replay.
   */
  recordSignals(signals: Signal[]): void {
    this.recorder.record(signals);
  }

  /**
   * Finalizes recording and returns a replayable signal set.
   */
  finishRecording(featureVectors?: FeatureVector[]): RecordedSignalSet {
    return this.recorder.finishRecording(featureVectors);
  }

  /**
   * Replays a recorded signal set through the pipeline.
   */
  replayRecorded(recordedSet: RecordedSignalSet): ReplayResult {
    return replaySignals(recordedSet, {
      windowConfig: this.windowConfig,
      abortSignal: this.abortSignal,
    });
  }

  /**
   * Updates window configuration.
   */
  updateConfig(windowConfig: TickWindowConfig): void {
    this.windowConfig = windowConfig;
  }
}

// ============================================================================
// Receipt and Verification
// ============================================================================

/**
 * Complete processing receipt with all pipeline outputs.
 */
export interface PipelineReceipt {
  /** Pipeline version */
  version: string;
  /** Revision bound */
  revision: string;
  /** Window receipts */
  windowReceipts: ReturnType<typeof generateWindowReceipts>;
  /** Feature receipts */
  featureReceipts: WindowReceipt[];
  /** Feature vectors */
  featureVectors: FeatureVector[];
  /** Signal count */
  signalCount: number;
  /** Drop count */
  dropCount: number;
  /** Processing timestamp */
  timestamp: number;
  /** Whether from live or replay */
  isReplay: boolean;
}

/**
 * Verifies that a receipt matches expected values.
 */
export function verifyPipelineReceipt(
  receipt: PipelineReceipt,
  expectedRevision: string,
  expectedSignalCount?: number,
): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (receipt.revision !== expectedRevision) {
    errors.push(`Revision mismatch: expected ${expectedRevision}, got ${receipt.revision}`);
  }

  if (expectedSignalCount !== undefined && receipt.signalCount !== expectedSignalCount) {
    errors.push(
      `Signal count mismatch: expected ${expectedSignalCount}, got ${receipt.signalCount}`,
    );
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
