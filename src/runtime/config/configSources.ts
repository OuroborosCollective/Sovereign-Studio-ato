/**
 * Configuration Sources - Canonical source definitions for config resolution
 * 
 * Defines the contract for configuration sources with deterministic merge semantics.
 * Each source binds: ID, revision/digest, content hash, schema hash, priority.
 * 
 * @module runtime/config/configSources
 */

// ============================================================================
// Schema Identifiers
// ============================================================================

export const CONFIG_SOURCE_SCHEMA_ID = 'config-source.v1';
export const CONFIG_RESOLUTION_SCHEMA_ID = 'config-resolution.v1';

// ============================================================================
// Configuration Source Contract
// ============================================================================

export interface ConfigSourceContract {
  /** Schema identifier */
  schemaId: string;
  /** Schema version */
  schemaVersion: string;
  /** Unique source identifier */
  id: string;
  /** Source type */
  type: ConfigSourceType;
  /** Source priority (higher = later in merge) */
  priority: number;
  /** Content hash of the source */
  contentHash: string;
  /** Schema hash for the config structure */
  schemaHash: string;
  /** Revision or digest for immutable binding */
  revision?: string;
  /** Origin URL if remote */
  origin?: string;
  /** Digest for remote sources */
  digest?: string;
  /** Timestamp when source was loaded */
  timestamp: number;
  /** Whether this source contains secrets */
  hasSecrets: boolean;
}

export type ConfigSourceType = 
  | 'compiled-defaults'
  | 'image-manifest'
  | 'deployment-config'
  | 'environment-projection'
  | 'runtime-overlay'
  | 'user-override';

// ============================================================================
// Configuration Resolution Contract
// ============================================================================

export interface ConfigResolutionContract {
  /** Schema identifier */
  schemaId: string;
  /** Schema version */
  schemaVersion: string;
  /** Unique resolution identifier */
  id: string;
  /** Resolved configuration */
  config: Record<string, unknown>;
  /** Sources in resolution order */
  sources: ConfigSourceContract[];
  /** Merged content hash */
  contentHash: string;
  /** Schema hash of final config */
  schemaHash: string;
  /** Redacted fingerprint for PatchMon */
  redactedFingerprint: string;
  /** Resolution timestamp */
  timestamp: number;
  /** Source revision binding */
  revision?: string;
  /** Runtime revision */
  runtimeRevision?: string;
  /** Causal tick */
  tick?: number;
  /** Causal sequence */
  sequence?: number;
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
 * Validate a configuration source contract.
 */
export function validateConfigSource(
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
        message: 'ConfigSource must be a non-null object',
      }],
      warnings: [],
    };
  }

  const s = obj as Record<string, unknown>;

  // Schema validation
  if (s.schemaId !== CONFIG_SOURCE_SCHEMA_ID) {
    errors.push({
      field: 'schemaId',
      code: 'INVALID_SCHEMA',
      message: `Expected "${CONFIG_SOURCE_SCHEMA_ID}"`,
    });
  }

  if (typeof s.schemaVersion !== 'string' || !s.schemaVersion.startsWith('v')) {
    errors.push({
      field: 'schemaVersion',
      code: 'INVALID_VERSION',
      message: 'schemaVersion must start with "v"',
    });
  }

  // Required fields
  for (const field of ['id', 'type', 'priority', 'contentHash', 'schemaHash', 'timestamp']) {
    if (field === 'priority') {
      if (typeof s[field] !== 'number' || s[field] < 0) {
        errors.push({
          field,
          code: 'INVALID_TYPE',
          message: `${field} must be a non-negative number`,
        });
      }
    } else if (field === 'timestamp') {
      if (typeof s[field] !== 'number' || s[field] < 0) {
        errors.push({
          field,
          code: 'INVALID_TYPE',
          message: `${field} must be a non-negative number`,
        });
      }
    } else {
      if (typeof s[field] !== 'string' || (s[field] as string).length === 0) {
        errors.push({
          field,
          code: 'MISSING_OR_EMPTY',
          message: `${field} must be a non-empty string`,
        });
      }
    }
  }

  // Valid source type
  const validTypes: ConfigSourceType[] = [
    'compiled-defaults', 'image-manifest', 'deployment-config',
    'environment-projection', 'runtime-overlay', 'user-override',
  ];
  if (!validTypes.includes(s.type as ConfigSourceType)) {
    errors.push({
      field: 'type',
      code: 'INVALID_VALUE',
      message: `type must be one of: ${validTypes.join(', ')}`,
    });
  }

  // Remote source validation
  if (s.type === 'image-manifest' || s.type === 'deployment-config') {
    if (s.origin && !s.digest) {
      warnings.push({
        field: 'digest',
        message: 'Remote source should have a digest for immutable binding',
      });
    }
    if (s.origin && !s.revision) {
      warnings.push({
        field: 'revision',
        message: 'Remote source should have a revision for traceability',
      });
    }
  }

  // Secret flag
  if (typeof s.hasSecrets !== 'boolean') {
    errors.push({
      field: 'hasSecrets',
      code: 'INVALID_TYPE',
      message: 'hasSecrets must be a boolean',
    });
  }

  // Strict mode
  if (strict) {
    const knownFields = new Set([
      'schemaId', 'schemaVersion', 'id', 'type', 'priority',
      'contentHash', 'schemaHash', 'revision', 'origin', 'digest',
      'timestamp', 'hasSecrets',
    ]);
    for (const key of Object.keys(s)) {
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
 * Validate a configuration resolution contract.
 */
export function validateConfigResolution(
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
        message: 'ConfigResolution must be a non-null object',
      }],
      warnings: [],
    };
  }

  const r = obj as Record<string, unknown>;

  // Schema validation
  if (r.schemaId !== CONFIG_RESOLUTION_SCHEMA_ID) {
    errors.push({
      field: 'schemaId',
      code: 'INVALID_SCHEMA',
      message: `Expected "${CONFIG_RESOLUTION_SCHEMA_ID}"`,
    });
  }

  if (typeof r.schemaVersion !== 'string' || !r.schemaVersion.startsWith('v')) {
    errors.push({
      field: 'schemaVersion',
      code: 'INVALID_VERSION',
      message: 'schemaVersion must start with "v"',
    });
  }

  // Required fields
  for (const field of ['id', 'config', 'sources', 'contentHash', 'schemaHash', 'timestamp']) {
    if (field === 'config') {
      if (typeof r[field] !== 'object' || r[field] === null || Array.isArray(r[field])) {
        errors.push({
          field,
          code: 'INVALID_TYPE',
          message: `${field} must be a non-null object`,
        });
      }
    } else if (field === 'sources') {
      if (!Array.isArray(r[field])) {
        errors.push({
          field,
          code: 'INVALID_TYPE',
          message: `${field} must be an array`,
        });
      } else {
        for (let i = 0; i < r[field].length; i++) {
          const sourceResult = validateConfigSource((r[field] as unknown[])[i], { strict: false });
          if (!sourceResult.valid) {
            errors.push({
              field: `sources[${i}]`,
              code: 'INVALID_SOURCE',
              message: `sources[${i}] failed validation: ${sourceResult.errors.map(e => e.message).join(', ')}`,
            });
          }
        }
      }
    } else if (field === 'timestamp') {
      if (typeof r[field] !== 'number' || r[field] < 0) {
        errors.push({
          field,
          code: 'INVALID_TYPE',
          message: `${field} must be a non-negative number`,
        });
      }
    } else {
      if (typeof r[field] !== 'string' || (r[field] as string).length === 0) {
        errors.push({
          field,
          code: 'MISSING_OR_EMPTY',
          message: `${field} must be a non-empty string`,
        });
      }
    }
  }

  // Redacted fingerprint format (should be hex string)
  if (typeof r.redactedFingerprint === 'string') {
    if (!/^[a-f0-9]+$/i.test(r.redactedFingerprint as string)) {
      warnings.push({
        field: 'redactedFingerprint',
        message: 'redactedFingerprint should be a hex string',
      });
    }
  }

  // Strict mode
  if (strict) {
    const knownFields = new Set([
      'schemaId', 'schemaVersion', 'id', 'config', 'sources',
      'contentHash', 'schemaHash', 'redactedFingerprint', 'timestamp',
      'revision', 'runtimeRevision', 'tick', 'sequence',
    ]);
    for (const key of Object.keys(r)) {
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

export function generateConfigSourceSchemaHash(): string {
  return simpleHash(JSON.stringify({
    schemaId: CONFIG_SOURCE_SCHEMA_ID,
    version: 'v1',
    fields: ['id', 'type', 'priority', 'contentHash', 'schemaHash', 'timestamp', 'hasSecrets'],
  }));
}

export function generateConfigResolutionSchemaHash(): string {
  return simpleHash(JSON.stringify({
    schemaId: CONFIG_RESOLUTION_SCHEMA_ID,
    version: 'v1',
    fields: ['id', 'sources', 'contentHash', 'schemaHash', 'redactedFingerprint', 'timestamp'],
  }));
}
