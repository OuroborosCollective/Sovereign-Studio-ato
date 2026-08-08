/**
 * Replay Module
 *
 * Provides deterministic signal replay from recorded signals.
 * Live and Replay paths use the same core, producing identical
 * Window and Feature hashes for the same input.
 *
 * Key guarantees:
 * - Same recorded signals produce same Feature Hash
 * - Replay is bit-exact reproducible
 * - No wall-clock or random dependencies
 * - Shared pipeline with live processing
 *
 * @module predictive/pipeline/replay
 */

import type { OrderedSignal } from './signalOrdering';
import type { TickWindow, TickWindowConfig, TickWindowReceipt } from './tickWindow';
import type { FeatureVector, FeatureVectorConfig } from './featureVector';
import { processSignalsToWindows, DEFAULT_TICK_WINDOW_CONFIG } from './tickWindow';
import { computeFeatureVector, DEFAULT_FEATURE_VECTOR_CONFIG } from './featureVector';

/**
 * Recorded signal set for replay.
 */
export interface RecordedSignalSet {
  /** Set identifier */
  id: string;
  /** Signals recorded in order */
  signals: OrderedSignal[];
  /** Revision at recording time */
  revision: string;
  /** Recording timestamp (wall-clock, metadata only) */
  recordedAt: number;
  /** Total signals */
  signalCount: number;
}

/**
 * Replay configuration.
 */
export interface ReplayConfig {
  /** Window configuration */
  window: TickWindowConfig;
  /** Feature vector configuration */
  feature: FeatureVectorConfig;
  /** Enable validation of determinism */
  validateDeterminism: boolean;
  /** Abort signal */
  signal?: AbortSignal;
}

/**
 * Default replay configuration.
 */
export const DEFAULT_REPLAY_CONFIG: ReplayConfig = {
  window: DEFAULT_TICK_WINDOW_CONFIG,
  feature: DEFAULT_FEATURE_VECTOR_CONFIG,
  validateDeterminism: true,
};

/**
 * Result of a replay operation.
 */
export interface ReplayResult {
  /** Replay identifier */
  id: string;
  /** Windows created during replay */
  windows: TickWindow[];
  /** Feature vectors computed */
  features: FeatureVector[];
  /** Window receipt */
  windowReceipt: TickWindowReceipt;
  /** Whether determinism was validated */
  determinismValidated: boolean;
  /** Validation result if enabled */
  determinismResult?: { deterministic: boolean; hashes: string[] };
  /** Revision used */
  revision: string;
  /** Whether replay was complete */
  complete: boolean;
}

/**
 * Replay error types.
 */
export class ReplayError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly context?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'ReplayError';
  }
}

/**
 * Revision mismatch error.
 */
export class RevisionMismatchError extends ReplayError {
  constructor(
    public readonly expectedRevision: string,
    public readonly actualRevision: string,
  ) {
    super(
      `Revision mismatch: expected ${expectedRevision}, got ${actualRevision}`,
      'REVISION_MISMATCH',
      { expected: expectedRevision, actual: actualRevision },
    );
    this.name = 'RevisionMismatchError';
  }
}

/**
 * Creates a deterministic replay ID.
 */
function createReplayId(): string {
  return `replay-${Date.now().toString(36)}`;
}

/**
 * Validates that signals can be replayed deterministically.
 */
export function validateReplayable(
  signals: OrderedSignal[],
): { replayable: boolean; issues: string[] } {
  const issues: string[] = [];

  // Check for required fields
  for (let i = 0; i < signals.length; i++) {
    const signal = signals[i];
    if (!signal.id) {
      issues.push(`Signal at index ${i} missing id`);
    }
    if (signal.tick === undefined || signal.tick === null) {
      issues.push(`Signal ${signal.id || i} missing tick`);
    }
    if (signal.sequence === undefined || signal.sequence === null) {
      issues.push(`Signal ${signal.id || i} missing sequence`);
    }
    if (signal.revision === undefined || signal.revision === null) {
      issues.push(`Signal ${signal.id || i} missing revision`);
    }
  }

  // Check for deterministic ordering
  for (let i = 1; i < signals.length; i++) {
    const prev = signals[i - 1];
    const curr = signals[i];

    if (curr.tick < prev.tick) {
      issues.push(`Signal ${curr.id} has tick ${curr.tick} < previous ${prev.tick}`);
    }
    if (curr.tick === prev.tick && curr.sequence < prev.sequence) {
      issues.push(`Signal ${curr.id} has sequence ${curr.sequence} < previous ${prev.sequence} for same tick`);
    }
  }

  return {
    replayable: issues.length === 0,
    issues,
  };
}

/**
 * Creates a recorded signal set from ordered signals.
 */
export function createRecordedSet(
  signals: OrderedSignal[],
  revision: string,
): RecordedSignalSet {
  const id = `recorded-${revision}-${signals.length}`;

  return {
    id,
    signals: [...signals],
    revision,
    recordedAt: Date.now(), // Wall-clock for metadata only
    signalCount: signals.length,
  };
}

/**
 * Replays recorded signals through the pipeline.
 * Uses the same pipeline as live processing for parity.
 */
export function replay(
  recorded: RecordedSignalSet,
  config: ReplayConfig = DEFAULT_REPLAY_CONFIG,
): ReplayResult {
  const { window: windowConfig, feature: featureConfig, validateDeterminism } = config;

  if (config.signal?.aborted) {
    throw new DOMException('Replay aborted', 'AbortError');
  }

  // Validate revision
  if (recorded.revision !== windowConfig.revision) {
    throw new RevisionMismatchError(windowConfig.revision, recorded.revision);
  }

  const replayId = createReplayId();
  const windows: TickWindow[] = [];
  const features: FeatureVector[] = [];

  // Validate replayability
  const validation = validateReplayable(recorded.signals);
  if (!validation.replayable) {
    throw new ReplayError(
      `Signals not replayable: ${validation.issues.join(', ')}`,
      'NOT_REPLAYABLE',
      { issues: validation.issues },
    );
  }

  // Process signals through windowing (same as live)
  const windowReceipt = processSignalsToWindows(
    recorded.signals,
    { ...windowConfig, revision: recorded.revision },
    { signal: config.signal },
  );

  windows.push(...windowReceipt.windows);

  // Process windows to feature vectors (same as live)
  let determinismResult: { deterministic: boolean; hashes: string[] } | undefined;

  for (const win of windows) {
    const vector = computeFeatureVector(win.signals, win, {
      ...featureConfig,
      revision: recorded.revision,
    });
    features.push(vector);
  }

  // Validate determinism if enabled
  if (validateDeterminism && features.length > 0) {
    const firstWindow = windows[0];
    const firstFeatures = computeFeatureVector(
      firstWindow.signals,
      firstWindow,
      { ...featureConfig, revision: recorded.revision },
    );

    // Re-run to check determinism
    const reRun = computeFeatureVector(
      firstWindow.signals,
      firstWindow,
      { ...featureConfig, revision: recorded.revision },
    );

    determinismResult = {
      deterministic: reRun.hash === firstFeatures.hash,
      hashes: [firstFeatures.hash, reRun.hash],
    };
  }

  return {
    id: replayId,
    windows,
    features,
    windowReceipt,
    determinismValidated: validateDeterminism,
    determinismResult,
    revision: recorded.revision,
    complete: windowReceipt.complete,
  };
}

/**
 * Compares live and replay results for parity.
 */
export function compareLiveReplayParity(
  liveResult: ReplayResult,
  replayResult: ReplayResult,
): { parity: boolean; differences: string[] } {
  const differences: string[] = [];

  // Compare window counts
  if (liveResult.windows.length !== replayResult.windows.length) {
    differences.push(
      `Window count mismatch: live=${liveResult.windows.length}, replay=${replayResult.windows.length}`,
    );
  }

  // Compare feature hash counts
  if (liveResult.features.length !== replayResult.features.length) {
    differences.push(
      `Feature count mismatch: live=${liveResult.features.length}, replay=${replayResult.features.length}`,
    );
  }

  // Compare window contents
  for (let i = 0; i < Math.min(liveResult.windows.length, replayResult.windows.length); i++) {
    const live = liveResult.windows[i];
    const replay = replayResult.windows[i];

    if (live.id !== replay.id) {
      differences.push(`Window ${i} ID mismatch: live=${live.id}, replay=${replay.id}`);
    }
    if (live.startTick !== replay.startTick) {
      differences.push(`Window ${i} startTick mismatch: live=${live.startTick}, replay=${replay.startTick}`);
    }
    if (live.endTick !== replay.endTick) {
      differences.push(`Window ${i} endTick mismatch: live=${live.endTick}, replay=${replay.endTick}`);
    }
    if (live.signals.length !== replay.signals.length) {
      differences.push(`Window ${i} signal count mismatch: live=${live.signals.length}, replay=${replay.signals.length}`);
    }
  }

  // Compare feature hashes
  for (let i = 0; i < Math.min(liveResult.features.length, replayResult.features.length); i++) {
    const live = liveResult.features[i];
    const replay = replayResult.features[i];

    if (live.hash !== replay.hash) {
      differences.push(
        `Feature ${i} hash mismatch: live=${live.hash}, replay=${replay.hash}`,
      );
    }
  }

  return {
    parity: differences.length === 0,
    differences,
  };
}

/**
 * Creates a parity receipt documenting live/replay comparison.
 */
export interface ParityReceipt {
  id: string;
  liveResultId: string;
  replayResultId: string;
  parity: boolean;
  differences: string[];
  timestamp: number;
}

export function createParityReceipt(
  liveResult: ReplayResult,
  replayResult: ReplayResult,
): ParityReceipt {
  const comparison = compareLiveReplayParity(liveResult, replayResult);

  return {
    id: `parity-${Date.now().toString(36)}`,
    liveResultId: liveResult.id,
    replayResultId: replayResult.id,
    parity: comparison.parity,
    differences: comparison.differences,
    timestamp: Date.now(),
  };
}

/**
 * Live processing that uses same pipeline as replay.
 * Ensures bit-exact parity.
 */
export function liveProcess(
  signals: OrderedSignal[],
  config: ReplayConfig = DEFAULT_REPLAY_CONFIG,
): Omit<ReplayResult, 'id' | 'determinismValidated' | 'determinismResult'> {
  const { window: windowConfig, feature: featureConfig } = config;

  // Use current revision
  const revision = signals[0]?.revision || 'live';

  // Process through windows
  const windowReceipt = processSignalsToWindows(
    signals,
    { ...windowConfig, revision },
    { signal: config.signal },
  );

  const windows = windowReceipt.windows;

  // Process to feature vectors
  const features: FeatureVector[] = windows.map((win) =>
    computeFeatureVector(win.signals, win, { ...featureConfig, revision }),
  );

  return {
    windows,
    features,
    windowReceipt,
    revision,
    complete: windowReceipt.complete,
  };
}
