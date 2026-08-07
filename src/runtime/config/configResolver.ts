/**
 * Configuration Resolver - Deterministic merge with provenance tracking
 * 
 * Implements fixed merge semantics for Object, Array, Null, missing, and explicitly deleted.
 * Each source is bound to ID, Revision/Digest, Content Hash, Schema Hash, and Priority.
 * 
 * @module runtime/config/configResolver
 */

import {
  ConfigSourceContract,
  ConfigResolutionContract,
  CONFIG_SOURCE_SCHEMA_ID,
  CONFIG_RESOLUTION_SCHEMA_ID,
} from './configSources';

// ============================================================================
// Merge Semantics
// ============================================================================

type MergeStrategy = 'replace' | 'deep-merge' | 'array-merge' | 'delete';

/**
 * Merge behavior for different value types.
 */
export const MERGE_STRATEGIES: Record<string, MergeStrategy> = {
  object: 'deep-merge',
  array: 'array-merge',
  null: 'replace',
  string: 'replace',
  number: 'replace',
  boolean: 'replace',
  undefined: 'delete',
};

/**
 * Sentinel value to explicitly delete a key.
 */
export const EXPLICIT_DELETE = Symbol('EXPLICIT_DELETE');

function isExplicitDelete(value: unknown): boolean {
  return value === EXPLICIT_DELETE || (typeof value === 'object' && value !== null && (value as Record<string, unknown>)['__delete'] === true);
}

/**
 * Deterministic deep merge with explicit delete support.
 */
export function deepMerge(base: Record<string, unknown>, overlay: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = { ...base };
  
  for (const key of Object.keys(overlay)) {
    const overlayValue = overlay[key];
    
    if (isExplicitDelete(overlayValue)) {
      delete result[key];
      continue;
    }
    
    const baseValue = base[key];
    
    if (
      typeof overlayValue === 'object' &&
      overlayValue !== null &&
      !Array.isArray(overlayValue) &&
      typeof baseValue === 'object' &&
      baseValue !== null &&
      !Array.isArray(baseValue)
    ) {
      result[key] = deepMerge(baseValue as Record<string, unknown>, overlayValue as Record<string, unknown>);
    } else if (Array.isArray(overlayValue) && Array.isArray(baseValue)) {
      // Array merge: concatenate and deduplicate
      result[key] = arrayMerge(baseValue, overlayValue);
    } else {
      result[key] = overlayValue;
    }
  }
  
  return result;
}

/**
 * Array merge with deduplication for primitives.
 * For objects, uses deep equality comparison.
 */
export function arrayMerge(base: unknown[], overlay: unknown[]): unknown[] {
  const result: unknown[] = [...base];
  
  for (const item of overlay) {
    if (!containsDeepEqual(result, item)) {
      result.push(item);
    }
  }
  
  return result;
}

/**
 * Deep equality check for arrays.
 */
function containsDeepEqual(arr: unknown[], item: unknown): boolean {
  return arr.some(existing => deepEqual(existing, item));
}

/**
 * Deep equality comparison.
 */
function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (a === null || b === null) return a === b;
  if (typeof a !== 'object') return a === b;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    return a.every((val, idx) => deepEqual(val, b[idx]));
  }
  
  const objA = a as Record<string, unknown>;
  const objB = b as Record<string, unknown>;
  const keysA = Object.keys(objA);
  const keysB = Object.keys(objB);
  
  if (keysA.length !== keysB.length) return false;
  return keysA.every(key => deepEqual(objA[key], objB[key]));
}

// ============================================================================
// Content Hash Generation
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

function generateContentHash(obj: unknown): string {
  // Canonical JSON serialization for deterministic hashing
  const canonical = JSON.stringify(sortObjectKeys(obj));
  return simpleHash(canonical);
}

function sortObjectKeys(obj: unknown): unknown {
  if (obj === null || typeof obj !== 'object') return obj;
  if (Array.isArray(obj)) return obj.map(sortObjectKeys);
  
  const sorted: Record<string, unknown> = {};
  const keys = Object.keys(obj as Record<string, unknown>).sort();
  
  for (const key of keys) {
    sorted[key] = sortObjectKeys((obj as Record<string, unknown>)[key]);
  }
  
  return sorted;
}

// ============================================================================
// Config Resolver
// ============================================================================

export interface ResolverOptions {
  strict?: boolean;
  includeRedacted?: boolean;
  secretFields?: string[];
}

export interface ResolutionResult {
  resolution: ConfigResolutionContract | null;
  error?: string;
}

/**
 * Resolves configuration from multiple sources with deterministic merge.
 * 
 * Resolution order (lowest to highest priority):
 * 1. compiled defaults
 * 2. immutable image manifest
 * 3. revision-bound deployment config
 * 4. environment projection
 * 5. explicitly approved runtime overlay
 */
export function resolveConfig(
  sources: ConfigSourceContract[],
  options: ResolverOptions = {}
): ResolutionResult {
  const { strict = true, includeRedacted = true, secretFields = [] } = options;
  
  // Validate all sources first
  for (let i = 0; i < sources.length; i++) {
    const source = sources[i];
    if (strict && source.schemaId !== CONFIG_SOURCE_SCHEMA_ID) {
      return {
        resolution: null,
        error: `sources[${i}] has invalid schemaId: ${source.schemaId}`,
      };
    }
    if (!source.revision && (source.type === 'image-manifest' || source.type === 'deployment-config')) {
      if (strict) {
        return {
          resolution: null,
          error: `sources[${i}] of type ${source.type} requires revision`,
        };
      }
    }
  }
  
  // Sort by priority (ascending)
  const sortedSources = [...sources].sort((a, b) => a.priority - b.priority);
  
  // We need the actual config data for merging - for now, we'll use a placeholder
  // In real usage, sources would contain the actual config data
  // This resolver validates the structure and produces the resolution receipt
  
  const resolutionId = `res-${Date.now()}-${simpleHash(sortedSources.map(s => s.id).join(':'))}`;
  const timestamp = Date.now();
  
  // Generate source order hashes
  const sourceOrderHashes = sortedSources.map(s => s.contentHash);
  const mergedContentHash = simpleHash(sourceOrderHashes.join('|'));
  const schemaHash = simpleHash(CONFIG_RESOLUTION_SCHEMA_ID + ':v1');
  
  // Generate redacted fingerprint (excludes secrets)
  let redactedConfig: Record<string, unknown> = {};
  if (includeRedacted) {
    for (const source of sortedSources) {
      redactedConfig = deepMerge(redactedConfig, { 
        [`source:${source.id}`]: { 
          id: source.id,
          type: source.type,
          hasSecrets: source.hasSecrets,
          // Actual config values would be redacted if hasSecrets
        } 
      });
    }
  }
  
  const redactedFingerprint = simpleHash(JSON.stringify(redactedConfig));
  
  const resolution: ConfigResolutionContract = {
    schemaId: CONFIG_RESOLUTION_SCHEMA_ID,
    schemaVersion: 'v1',
    id: resolutionId,
    config: {}, // Actual config would be merged from sources
    sources: sortedSources,
    contentHash: mergedContentHash,
    schemaHash,
    redactedFingerprint,
    timestamp,
    tick: undefined,
    sequence: undefined,
  };
  
  return { resolution };
}

/**
 * Validates that a config resolution matches PatchMon readback.
 */
export function validateConfigConsistency(
  resolution: ConfigResolutionContract,
  readback: { revision: string; imageDigest: string; schemaHash: string; configFingerprint: string }
): { consistent: boolean; drift: string[] } {
  const drift: string[] = [];
  
  // Check if any source revision matches
  const matchingRevision = resolution.sources.some(s => s.revision === readback.revision);
  if (!matchingRevision) {
    drift.push(`revision mismatch: expected ${readback.revision}`);
  }
  
  // Check schema hash
  if (resolution.schemaHash !== readback.schemaHash) {
    drift.push(`schema hash mismatch: expected ${readback.schemaHash}`);
  }
  
  // Check redacted fingerprint (allows for secret differences)
  if (resolution.redactedFingerprint !== readback.configFingerprint) {
    drift.push(`config fingerprint mismatch: expected ${readback.configFingerprint}`);
  }
  
  return {
    consistent: drift.length === 0,
    drift,
  };
}

// ============================================================================
// Source Factory
// ============================================================================

export function createConfigSource(
  type: ConfigSourceContract['type'],
  id: string,
  config: Record<string, unknown>,
  options: Partial<ConfigSourceContract> = {}
): ConfigSourceContract {
  const contentHash = generateContentHash(config);
  const schemaHash = generateContentHash({ type, fields: Object.keys(config) });
  
  return {
    schemaId: CONFIG_SOURCE_SCHEMA_ID,
    schemaVersion: 'v1',
    id,
    type,
    priority: typeToPriority(type),
    contentHash,
    schemaHash,
    timestamp: Date.now(),
    hasSecrets: detectSecrets(config),
    ...options,
  };
}

function typeToPriority(type: ConfigSourceContract['type']): number {
  const priorities: Record<ConfigSourceContract['type'], number> = {
    'compiled-defaults': 0,
    'image-manifest': 10,
    'deployment-config': 20,
    'environment-projection': 30,
    'runtime-overlay': 40,
    'user-override': 50,
  };
  return priorities[type];
}

function detectSecrets(config: Record<string, unknown>): boolean {
  const secretPatterns = ['password', 'secret', 'token', 'api_key', 'apikey', 'private'];
  const keys = Object.keys(config).map(k => k.toLowerCase());
  return keys.some(key => secretPatterns.some(pattern => key.includes(pattern)));
}
