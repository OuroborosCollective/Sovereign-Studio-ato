/**
 * Signal Tick - Deterministic tick windows with replay parity
 * 
 * Defines the contract for causal tick ordering with bounded time windows.
 * Each tick binds: sequence, timestamp, content hash, causal parents.
 * 
 * @module predictive/signalPipeline/signalTick
 */

// ============================================================================
// Schema Identifiers
// ============================================================================

export const SIGNAL_TICK_SCHEMA_ID = 'signal-tick.v1';
export const SIGNAL_WINDOW_SCHEMA_ID = 'signal-window.v1';

// ============================================================================
// Signal Tick Contract
// ============================================================================

export interface SignalTickContract {
  /** Schema identifier */
  schemaId: string;
  /** Schema version */
  schemaVersion: string;
  /** Unique tick identifier */
  id: string;
  /** Causal sequence number */
  sequence: number;
  /** Causal tick (logical clock) */
  tick: number;
  /** Wall clock timestamp */
  timestamp: number;
  /** Content hash for this tick */
  contentHash: string;
  /** Schema hash for payload structure */
  schemaHash: string;
  /** Causal parent tick IDs */
  parents: string[];
  /** Tick window ID */
  windowId: string;
  /** Whether this tick is a checkpoint */
  isCheckpoint: boolean;
  /** Retry count for replay */
  retryCount: number;
}

export interface SignalWindowContract {
  /** Schema identifier */
  schemaId: string;
  /** Schema version */
  schemaVersion: string;
  /** Unique window identifier */
  id: string;
  /** Window start tick */
  startTick: number;
  /** Window end tick */
  endTick: number;
  /** Window start timestamp */
  startTime: number;
  /** Window duration in ms */
  windowDurationMs: number;
  /** Number of ticks in window */
  tickCount: number;
  /** Content hashes of all ticks */
  tickHashes: string[];
  /** Aggregated content hash */
  contentHash: string;
  /** Schema hash for window structure */
  schemaHash: string;
  /** Whether window was closed normally */
  closed: boolean;
  /** Reason for early close if applicable */
  closeReason?: string;
}

// ============================================================================
// Validation
// ============================================================================

export interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
  warnings: ValidationWarning[];
}

export interface ValidationError {
  field: string;
  code: string;
  message: string;
}

export interface ValidationWarning {
  field: string;
  message: string;
}

/**
 * Validate a signal tick contract.
 */
export function validateSignalTick(
  obj: unknown,
  options: { strict?: boolean; maxSequence?: number } = {}
): ValidationResult {
  const { strict = true, maxSequence = Infinity } = options;
  const errors: ValidationError[] = [];
  const warnings: ValidationWarning[] = [];

  if (typeof obj !== 'object' || obj === null) {
    return {
      valid: false,
      errors: [{
        field: 'root',
        code: 'INVALID_TYPE',
        message: 'SignalTick must be a non-null object',
      }],
      warnings: [],
    };
  }

  const t = obj as Record<string, unknown>;

  // Schema validation
  if (t.schemaId !== SIGNAL_TICK_SCHEMA_ID) {
    errors.push({
      field: 'schemaId',
      code: 'INVALID_SCHEMA',
      message: `Expected "${SIGNAL_TICK_SCHEMA_ID}"`,
    });
  }

  if (typeof t.schemaVersion !== 'string' || !t.schemaVersion.startsWith('v')) {
    errors.push({
      field: 'schemaVersion',
      code: 'INVALID_VERSION',
      message: 'schemaVersion must start with "v"',
    });
  }

  // Required numeric fields
  for (const field of ['sequence', 'tick', 'timestamp']) {
    if (typeof t[field] !== 'number' || t[field] < 0) {
      errors.push({
        field,
        code: 'INVALID_TYPE',
        message: `${field} must be a non-negative number`,
      });
    }
  }

  // Sequence monotonicity
  if (typeof t.sequence === 'number' && t.sequence > maxSequence + 1) {
    errors.push({
      field: 'sequence',
      code: 'SEQUENCE_GAP',
      message: `Sequence ${t.sequence} exceeds max expected ${maxSequence + 1}`,
    });
  }

  // Required string fields
  for (const field of ['id', 'contentHash', 'schemaHash', 'windowId']) {
    if (typeof t[field] !== 'string' || (t[field] as string).length === 0) {
      errors.push({
        field,
        code: 'MISSING_OR_EMPTY',
        message: `${field} must be a non-empty string`,
      });
    }
  }

  // Parents validation
  if (!Array.isArray(t.parents)) {
    errors.push({
      field: 'parents',
      code: 'INVALID_TYPE',
      message: 'parents must be an array',
    });
  }

  // Boolean fields
  for (const field of ['isCheckpoint']) {
    if (typeof t[field] !== 'boolean') {
      errors.push({
        field,
        code: 'INVALID_TYPE',
        message: `${field} must be a boolean`,
      });
    }
  }

  // Retry count
  if (typeof t.retryCount !== 'number' || t.retryCount < 0) {
    errors.push({
      field: 'retryCount',
      code: 'INVALID_TYPE',
      message: 'retryCount must be a non-negative number',
    });
  }

  // Strict mode
  if (strict) {
    const knownFields = new Set([
      'schemaId', 'schemaVersion', 'id', 'sequence', 'tick', 'timestamp',
      'contentHash', 'schemaHash', 'parents', 'windowId', 'isCheckpoint', 'retryCount',
    ]);
    for (const key of Object.keys(t)) {
      if (!knownFields.has(key)) {
        errors.push({
          field: key,
          code: 'UNKNOWN_FIELD',
          message: `Unknown field "${key}" in strict mode`,
        });
      }
    }
  }

  return { valid: errors.length === 0, errors, warnings };
}

/**
 * Validate a signal window contract.
 */
export function validateSignalWindow(
  obj: unknown,
  options: { strict?: boolean } = {}
): ValidationResult {
  const { strict = true } = options;
  const errors: ValidationError[] = [];
  const warnings: ValidationWarning[] = [];

  if (typeof obj !== 'object' || obj === null) {
    return {
      valid: false,
      errors: [{
        field: 'root',
        code: 'INVALID_TYPE',
        message: 'SignalWindow must be a non-null object',
      }],
      warnings: [],
    };
  }

  const w = obj as Record<string, unknown>;

  // Schema validation
  if (w.schemaId !== SIGNAL_WINDOW_SCHEMA_ID) {
    errors.push({
      field: 'schemaId',
      code: 'INVALID_SCHEMA',
      message: `Expected "${SIGNAL_WINDOW_SCHEMA_ID}"`,
    });
  }

  if (typeof w.schemaVersion !== 'string' || !w.schemaVersion.startsWith('v')) {
    errors.push({
      field: 'schemaVersion',
      code: 'INVALID_VERSION',
      message: 'schemaVersion must start with "v"',
    });
  }

  // Window boundaries
  for (const field of ['startTick', 'endTick', 'startTime', 'windowDurationMs', 'tickCount']) {
    if (typeof w[field] !== 'number' || w[field] < 0) {
      errors.push({
        field,
        code: 'INVALID_TYPE',
        message: `${field} must be a non-negative number`,
      });
    }
  }

  if (typeof w.startTick === 'number' && typeof w.endTick === 'number') {
    if (w.endTick < w.startTick) {
      errors.push({
        field: 'endTick',
        code: 'INVALID_RANGE',
        message: 'endTick must be >= startTick',
      });
    }
  }

  // Required string fields
  for (const field of ['id', 'contentHash', 'schemaHash']) {
    if (typeof w[field] !== 'string' || (w[field] as string).length === 0) {
      errors.push({
        field,
        code: 'MISSING_OR_EMPTY',
        message: `${field} must be a non-empty string`,
      });
    }
  }

  // tickHashes validation
  if (!Array.isArray(w.tickHashes)) {
    errors.push({
      field: 'tickHashes',
      code: 'INVALID_TYPE',
      message: 'tickHashes must be an array',
    });
  }

  // Closed flag
  if (typeof w.closed !== 'boolean') {
    errors.push({
      field: 'closed',
      code: 'INVALID_TYPE',
      message: 'closed must be a boolean',
    });
  }

  // Strict mode
  if (strict) {
    const knownFields = new Set([
      'schemaId', 'schemaVersion', 'id', 'startTick', 'endTick',
      'startTime', 'windowDurationMs', 'tickCount', 'tickHashes',
      'contentHash', 'schemaHash', 'closed', 'closeReason',
    ]);
    for (const key of Object.keys(w)) {
      if (!knownFields.has(key)) {
        errors.push({
          field: key,
          code: 'UNKNOWN_FIELD',
          message: `Unknown field "${key}" in strict mode`,
        });
      }
    }
  }

  return { valid: errors.length === 0, errors, warnings };
}

// ============================================================================
// Schema Hash Generation
// ============================================================================

function simpleHash(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash).toString(16).padStart(8, '0');
}

export function generateSignalTickSchemaHash(): string {
  return simpleHash(JSON.stringify({
    schemaId: SIGNAL_TICK_SCHEMA_ID,
    version: 'v1',
    fields: ['id', 'sequence', 'tick', 'timestamp', 'contentHash', 'schemaHash', 'parents', 'windowId', 'isCheckpoint', 'retryCount'],
  }));
}

export function generateSignalWindowSchemaHash(): string {
  return simpleHash(JSON.stringify({
    schemaId: SIGNAL_WINDOW_SCHEMA_ID,
    version: 'v1',
    fields: ['id', 'startTick', 'endTick', 'startTime', 'windowDurationMs', 'tickCount', 'tickHashes', 'contentHash', 'schemaHash', 'closed'],
  }));
}
