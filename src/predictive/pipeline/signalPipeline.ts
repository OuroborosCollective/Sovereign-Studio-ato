/**
 * Deterministic Signal Pipeline - public orchestrator.
 *
 * Issue #1170: a single deterministic transform from validated signals to
 * feature receipts. The pipeline is a pure function of its inputs + config, so
 * replaying the same recorded signals reproduces byte-identical window hashes
 * and feature hashes.
 *
 * Truth chain:
 *   validated signals
 *   -> canonical order (node, sequence, tick)
 *   -> deterministic tick windows (causal bounds + SHA-256)
 *   -> feature vectors (pure numeric projections)
 *   -> feature receipts (source-bound, recomputable)
 *
 * Wall-clock timestamps are metadata only. Loss is never silent: every dropped
 * signal carries a reason code and is surfaced in the result.
 *
 * @module predictive/pipeline/signalPipeline
 */

import { type PipelineSignal } from './signalOrdering';
import {
  buildTickWindows,
  DEFAULT_TICK_WINDOW_CONFIG,
  type TickWindow,
  type TickWindowConfig,
  type WindowingResult,
} from './tickWindow';
import {
  buildFeatureReceipt,
  type FeatureReceipt,
  type FeatureDescriptorName,
} from './featureExtraction';
import { hashCanonical } from '../inference/hash';

export interface PipelineConfig extends TickWindowConfig {
  /** Feature descriptor applied to each window. */
  featureDescriptor: FeatureDescriptorName;
}

export const DEFAULT_PIPELINE_CONFIG: PipelineConfig = {
  ...DEFAULT_TICK_WINDOW_CONFIG,
  featureDescriptor: 'sum',
};

export interface SignalPipelineResult {
  config: PipelineConfig;
  /** Canonical-order signals actually consumed. */
  consumed: PipelineSignal[];
  /** Bounded deterministic windows. */
  windows: TickWindow[];
  /** Per-window feature receipts (same length as windows). */
  featureReceipts: FeatureReceipt[];
  /** Content-hash deltas between consecutive windows. */
  windowDeltas: string[];
  /** Non-silent drops with reason codes. */
  drops: WindowingResult['drops'];
  /** Aggregate hash over all window hashes (causal digest of the run). */
  pipelineHash: string;
  /** Total ticks consumed. */
  consumedTicks: number;
  /** Abort signal state at completion. */
  aborted: boolean;
}

/**
 * Run the deterministic signal pipeline over a batch of validated signals.
 *
 * This is the synchronous (batch) entry point: it consumes a finite array. For
 * the async/streaming variant use `runSignalPipelineAsync` with an async source.
 *
 * @param signals validated signals (any order; canonicalized internally)
 * @param config  pipeline configuration
 * @param abort   optional abort signal (stops after current window)
 */
export function runSignalPipeline(
  signals: readonly PipelineSignal[],
  config: PipelineConfig = DEFAULT_PIPELINE_CONFIG,
  abort?: { aborted: boolean },
): SignalPipelineResult {
  const aborted = abort?.aborted === true;

  const windowing = buildTickWindows(signals, config);

  const featureReceipts: FeatureReceipt[] = [];
  for (const window of windowing.windows) {
    const sliceValues = window.signals.map(s => s.value);
    featureReceipts.push(buildFeatureReceipt(window, sliceValues, config.featureDescriptor));
  }

  const pipelineHash = hashCanonical(windowing.windows.map(w => w.windowHash));

  return {
    config,
    consumed: windowing.accepted,
    windows: windowing.windows,
    featureReceipts,
    windowDeltas: windowing.windowDeltas,
    drops: aborted
      ? [...windowing.drops, { reason: 'ABORTED', node: '', sequence: 0, tick: 0, detail: 'abort signal set' }]
      : windowing.drops,
    pipelineHash,
    consumedTicks: windowing.consumedTicks,
    aborted,
  };
}

/**
 * Replay-parity check: run the pipeline on the same signals twice and assert
 * that window hashes, feature hashes and the pipeline hash are byte-identical.
 *
 * Returns the comparison; does not throw, so callers can surface drift.
 */
export function assertReplayParity(
  signals: readonly PipelineSignal[],
  config: PipelineConfig = DEFAULT_PIPELINE_CONFIG,
): {
  parity: boolean;
  windowHashes: [string[], string[]];
  featureHashes: [string[], string[]];
  pipelineHashes: [string, string];
} {
  const a = runSignalPipeline(signals, config);
  const b = runSignalPipeline(signals, config);
  const windowHashes: [string[], string[]] = [a.windows.map(w => w.windowHash), b.windows.map(w => w.windowHash)];
  const featureHashes: [string[], string[]] = [
    a.featureReceipts.map(r => r.featureHash),
    b.featureReceipts.map(r => r.featureHash),
  ];
  const pipelineHashes: [string, string] = [a.pipelineHash, b.pipelineHash];
  const parity =
    JSON.stringify(windowHashes[0]) === JSON.stringify(windowHashes[1]) &&
    JSON.stringify(featureHashes[0]) === JSON.stringify(featureHashes[1]) &&
    pipelineHashes[0] === pipelineHashes[1];
  return { parity, windowHashes, featureHashes, pipelineHashes };
}

/**
 * Async/streaming variant. Consumes a finite async iterable of signals and
 * accumulates them into a batch, applying the same deterministic transform.
 * The async source MUST be finite; infinite sources are rejected after
 * maxTicks to preserve the backpressure bound.
 */
export async function runSignalPipelineAsync(
  source: AsyncIterable<PipelineSignal>,
  config: PipelineConfig = DEFAULT_PIPELINE_CONFIG,
  abort?: { aborted: boolean },
): Promise<SignalPipelineResult> {
  const collected: PipelineSignal[] = [];
  for await (const signal of source) {
    if (abort?.aborted === true) {
      break;
    }
    if (collected.length >= config.maxTicks) {
      // Backpressure bound: stop consuming rather than growing unbounded.
      break;
    }
    collected.push(signal);
  }
  return runSignalPipeline(collected, config, abort);
}
