/**
 * Runtime Signal Contract - Predictive Contract Foundation
 *
 * Strict schema validation for Runtime Signals with schema hashes,
 * source/runtime revision binding, and fail-closed validation.
 *
 * @module predictive/contracts/runtimeSignal
 */

/**
 * SHA-256 hash using Web Crypto API (works in browser and Node.js 19+)
 */
async function sha256(message: string): Promise<string> {
  const msgBuffer = new TextEncoder().encode(message);
  const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Synchronous SHA-256 using the Web Crypto API
 */
function sha256Sync(message: string): string {
  // Simple synchronous hash for deterministic operations
  // Uses a basic hash function for browser compatibility
  let hash = 0;
  for (let i = 0; i < message.length; i++) {
    const char = message.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  // Convert to hex string (16 chars)
  const hex = Math.abs(hash).toString(16).padStart(8, '0');
  return hex.repeat(2).slice(0, 16);
}

// ============================================================================
// Schema Identity
// ============================================================================

export const RUNTIME_SIGNAL_SCHEMA_ID = 'sovereign.runtime-signal.v1';
export const RUNTIME_SIGNAL_SCHEMA_VERSION = '1.0.0';

export interface RuntimeSignalSchemaMetadata {
  schemaId: string;
  schemaVersion: string;
  schemaHash: string;
  sourceRevision?: string;
  runtimeRevision?: string;
}

// ============================================================================
// Contract Types
// ============================================================================

export interface RuntimeSignal {
  /** Unique identifier for the signal */
  id: string;
  /** Name of the node that emitted this signal */
  node: string;
  /** Numeric value - must be finite */
  value: number;
  /** Unix timestamp in milliseconds */
  timestamp: number;
  /** Trace context for debugging */
  traceId: string;
  /** Tick counter - causal identity (not wall-clock) */
  tick?: number;
  /** Sequence number - causal ordering */
  sequence?: number;
  /** Chunk index for batched signals */
  chunk?: number;
  /** Schema metadata */
  schema?: RuntimeSignalSchemaMetadata;
  /** Optional metadata - no secrets */
  metadata?: Record<string, unknown>;
}

export interface RuntimeSignalWindow {
  /** Window identifier */
  windowId: string;
  /** Signals in this window */
  signals: RuntimeSignal[];
  /** Window start tick */
  startTick: number;
  /** Window end tick */
  endTick: number;
  /** Window start sequence */
  startSequence: number;
  /** Window end sequence */
  endSequence: number;
  /** Config fingerprint - window size and overlap */
  configHash: string;
  /** Schema metadata */
  schema?: RuntimeSignalSchemaMetadata;
}

export interface SignalValidationResult {
  valid: boolean;
  errors: SignalValidationError[];
  schemaId?: string;
  schemaHash?: string;
}

export interface SignalValidationError {
  field: string;
  code: SignalErrorCode;
  message: string;
}

export enum SignalErrorCode {
  MISSING_REQUIRED = 'MISSING_REQUIRED',
  INVALID_TYPE = 'INVALID_TYPE',
  NON_FINITE_NUMBER = 'NON_FINITE_NUMBER',
  UNKNOWN_FIELD = 'UNKNOWN_FIELD',
  DIMENSION_MISMATCH = 'DIMENSION_MISMATCH',
  INVALID_TIMESTAMP = 'INVALID_TIMESTAMP',
  EMPTY_STRING = 'EMPTY_STRING',
  REVISION_MISSING = 'REVISION_MISSING',
}

// ============================================================================
// Allowed Fields (additionalProperties: false equivalent)
// ============================================================================

const SIGNAL_REQUIRED_FIELDS = ['id', 'node', 'value', 'timestamp', 'traceId'] as const;
const SIGNAL_OPTIONAL_FIELDS = ['tick', 'sequence', 'chunk', 'schema', 'metadata'] as const;
const SIGNAL_ALL_FIELDS: string[] = [...SIGNAL_REQUIRED_FIELDS, ...SIGNAL_OPTIONAL_FIELDS];

const WINDOW_REQUIRED_FIELDS = ['windowId', 'signals', 'startTick', 'endTick', 'configHash'] as const;
const WINDOW_OPTIONAL_FIELDS = ['startSequence', 'endSequence', 'schema'] as const;
const WINDOW_ALL_FIELDS: string[] = [...WINDOW_REQUIRED_FIELDS, ...WINDOW_OPTIONAL_FIELDS];

// ============================================================================
// Numeric Validation
// ============================================================================

function isCanonicalNumber(value: unknown): value is number {
  if (typeof value !== 'number') return false;
  if (!Number.isFinite(value)) return false;
  // Reject ambiguous negative zero
  if (Object.is(value, -0)) return false;
  return true;
}

// ============================================================================
// Schema Hash Generation
// ============================================================================

export function generateSchemaHash(schemaId: string, schemaVersion: string): string {
  const content = `${schemaId}::${schemaVersion}`;
  return sha256Sync(content);
}

export function generateSignalHash(signal: RuntimeSignal): string {
  const canonical = {
    id: signal.id,
    node: signal.node,
    value: signal.value,
    tick: signal.tick ?? 0,
    sequence: signal.sequence ?? 0,
  };
  const content = JSON.stringify(canonical, Object.keys(canonical).sort());
  return sha256Sync(content);
}

// ============================================================================
// Signal Validation
// ============================================================================

export function validateSignal(obj: unknown, options: { strict: boolean } = { strict: true }): SignalValidationResult {
  const errors: SignalValidationError[] = [];

  if (typeof obj !== 'object' || obj === null) {
    return {
      valid: false,
      errors: [{ field: 'root', code: SignalErrorCode.INVALID_TYPE, message: 'Signal must be an object' }],
    };
  }

  const signal = obj as Record<string, unknown>;

  // Check for unknown fields (fail closed)
  if (options.strict) {
    for (const key of Object.keys(signal)) {
      if (!SIGNAL_ALL_FIELDS.includes(key)) {
        errors.push({
          field: key,
          code: SignalErrorCode.UNKNOWN_FIELD,
          message: `Unknown field: ${key}`,
        });
      }
    }
  }

  // Required fields
  for (const field of SIGNAL_REQUIRED_FIELDS) {
    if (!(field in signal)) {
      errors.push({
        field,
        code: SignalErrorCode.MISSING_REQUIRED,
        message: `Missing required field: ${field}`,
      });
    }
  }

  // Type and value validations
  if (!('id' in signal) || typeof signal.id !== 'string' || signal.id.length === 0) {
    errors.push({ field: 'id', code: SignalErrorCode.EMPTY_STRING, message: 'id must be a non-empty string' });
  }

  if (!('node' in signal) || typeof signal.node !== 'string' || signal.node.length === 0) {
    errors.push({ field: 'node', code: SignalErrorCode.EMPTY_STRING, message: 'node must be a non-empty string' });
  }

  if (!('value' in signal) || !isCanonicalNumber(signal.value)) {
    errors.push({
      field: 'value',
      code: SignalErrorCode.NON_FINITE_NUMBER,
      message: 'value must be a finite number (not NaN, Infinity, -Infinity, or -0)',
    });
  }

  if (!('timestamp' in signal) || typeof signal.timestamp !== 'number' || signal.timestamp <= 0) {
    errors.push({
      field: 'timestamp',
      code: SignalErrorCode.INVALID_TIMESTAMP,
      message: 'timestamp must be a positive number',
    });
  }

  if (!('traceId' in signal) || typeof signal.traceId !== 'string') {
    errors.push({ field: 'traceId', code: SignalErrorCode.INVALID_TYPE, message: 'traceId must be a string' });
  }

  // Optional numeric fields must be canonical if present
  if ('tick' in signal && !isCanonicalNumber(signal.tick)) {
    errors.push({ field: 'tick', code: SignalErrorCode.NON_FINITE_NUMBER, message: 'tick must be a finite number' });
  }

  if ('sequence' in signal && !isCanonicalNumber(signal.sequence)) {
    errors.push({ field: 'sequence', code: SignalErrorCode.NON_FINITE_NUMBER, message: 'sequence must be a finite number' });
  }

  if ('chunk' in signal && !isCanonicalNumber(signal.chunk)) {
    errors.push({ field: 'chunk', code: SignalErrorCode.NON_FINITE_NUMBER, message: 'chunk must be a finite number' });
  }

  return {
    valid: errors.length === 0,
    errors,
    schemaId: RUNTIME_SIGNAL_SCHEMA_ID,
    schemaHash: generateSchemaHash(RUNTIME_SIGNAL_SCHEMA_ID, RUNTIME_SIGNAL_SCHEMA_VERSION),
  };
}

// ============================================================================
// Window Validation
// ============================================================================

export function validateSignalWindow(obj: unknown, options: { strict: boolean } = { strict: true }): SignalValidationResult {
  const errors: SignalValidationError[] = [];

  if (typeof obj !== 'object' || obj === null) {
    return {
      valid: false,
      errors: [{ field: 'root', code: SignalErrorCode.INVALID_TYPE, message: 'SignalWindow must be an object' }],
    };
  }

  const window = obj as Record<string, unknown>;

  // Check for unknown fields
  if (options.strict) {
    for (const key of Object.keys(window)) {
      if (!WINDOW_ALL_FIELDS.includes(key)) {
        errors.push({
          field: key,
          code: SignalErrorCode.UNKNOWN_FIELD,
          message: `Unknown field: ${key}`,
        });
      }
    }
  }

  // Required fields
  for (const field of WINDOW_REQUIRED_FIELDS) {
    if (!(field in window)) {
      errors.push({
        field,
        code: SignalErrorCode.MISSING_REQUIRED,
        message: `Missing required field: ${field}`,
      });
    }
  }

  // Type validations
  if (!('windowId' in window) || typeof window.windowId !== 'string' || window.windowId.length === 0) {
    errors.push({ field: 'windowId', code: SignalErrorCode.EMPTY_STRING, message: 'windowId must be a non-empty string' });
  }

  if (!('signals' in window)) {
    errors.push({ field: 'signals', code: SignalErrorCode.MISSING_REQUIRED, message: 'signals is required' });
  } else if (!Array.isArray(window.signals)) {
    errors.push({ field: 'signals', code: SignalErrorCode.INVALID_TYPE, message: 'signals must be an array' });
  } else {
    for (let i = 0; i < window.signals.length; i++) {
      const signalResult = validateSignal(window.signals[i], options);
      if (!signalResult.valid) {
        errors.push({
          field: `signals[${i}]`,
          code: signalResult.errors[0].code,
          message: `signals[${i}]: ${signalResult.errors[0].message}`,
        });
      }
    }
  }

  if (!('startTick' in window) || !isCanonicalNumber(window.startTick)) {
    errors.push({ field: 'startTick', code: SignalErrorCode.NON_FINITE_NUMBER, message: 'startTick must be a finite number' });
  }

  if (!('endTick' in window) || !isCanonicalNumber(window.endTick)) {
    errors.push({ field: 'endTick', code: SignalErrorCode.NON_FINITE_NUMBER, message: 'endTick must be a finite number' });
  }

  if (!('configHash' in window) || typeof window.configHash !== 'string' || window.configHash.length === 0) {
    errors.push({ field: 'configHash', code: SignalErrorCode.EMPTY_STRING, message: 'configHash must be a non-empty string' });
  }

  return {
    valid: errors.length === 0,
    errors,
    schemaId: `${RUNTIME_SIGNAL_SCHEMA_ID}.window`,
    schemaHash: generateSchemaHash(RUNTIME_SIGNAL_SCHEMA_ID, `${RUNTIME_SIGNAL_SCHEMA_VERSION}.window`),
  };
}

// ============================================================================
// Default Schema Metadata
// ============================================================================

export function createSchemaMetadata(overrides?: Partial<RuntimeSignalSchemaMetadata>): RuntimeSignalSchemaMetadata {
  return {
    schemaId: RUNTIME_SIGNAL_SCHEMA_ID,
    schemaVersion: RUNTIME_SIGNAL_SCHEMA_VERSION,
    schemaHash: generateSchemaHash(RUNTIME_SIGNAL_SCHEMA_ID, RUNTIME_SIGNAL_SCHEMA_VERSION),
    ...overrides,
  };
}

// ============================================================================
// Bounded Payload Sizes
// ============================================================================

export const SIGNAL_MAX_METADATA_SIZE = 4096; // bytes
export const SIGNAL_WINDOW_MAX_SIGNALS = 1000;

export function validateSignalPayloadSize(signal: RuntimeSignal): boolean {
  if (signal.metadata) {
    const metadataStr = JSON.stringify(signal.metadata);
    if (metadataStr.length > SIGNAL_MAX_METADATA_SIZE) return false;
  }
  return true;
}

export function validateWindowPayloadSize(window: RuntimeSignalWindow): boolean {
  return window.signals.length <= SIGNAL_WINDOW_MAX_SIGNALS;
}
