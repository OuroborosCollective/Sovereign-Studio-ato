/**
 * Configuration Resolver
 *
 * Deterministic config resolution with source tracking.
 * Provides SourceOrder, SourceHashes, SchemaHash, and ResolvedHash.
 *
 * @module runtime/config/resolver
 */

import type { ConfigSource, ConfigSourcePriority } from './configSources';
import { extractSourceMetadata, hashConfigContent, validateRemoteSource } from './configSources';
import { mergeConfigs, type MergeResult } from './configMerge';

/**
 * Resolved configuration with full provenance.
 */
export interface ResolvedConfig<T extends object = object> {
  /** Merged configuration value */
  value: T;
  /** Ordered list of sources (highest precedence first) */
  sourceOrder: ConfigSource[];
  /** Combined content hashes of all sources */
  sourceHashes: string[];
  /** Schema hash of merged config */
  schemaHash: string;
  /** Hash of resolved configuration */
  resolvedHash: string;
  /** Timestamp of resolution */
  resolvedAt: string;
}

/**
 * Config resolution options.
 */
export interface ResolveOptions {
  /** Fail on unknown sources */
  failOnUnknown?: boolean;
  /** Fail on remote URLs without pre-bound metadata */
  failOnUnboundRemote?: boolean;
  /** Additional validation schema */
  validationSchema?: Record<string, unknown>;
}

/**
 * Resolves configuration from multiple sources.
 * Applies deterministic merge semantics and tracks provenance.
 */
export function resolveConfig<T extends object>(
  sources: ConfigSource[],
  values: Map<string, unknown>,
  options: ResolveOptions = {},
): ResolvedConfig<T> {
  const validatedSources: ConfigSource[] = [];

  // Validate and filter sources
  for (const source of sources) {
    // Skip unknown sources if configured
    if (options.failOnUnknown && !isKnownSource(source)) {
      throw new Error(`Unknown config source: ${source.id}`);
    }

    // Validate remote sources have required bindings
    if (isRemoteSource(source) && options.failOnUnboundRemote) {
      if (!validateRemoteSource(source)) {
        throw new Error(`Remote source ${source.id} missing required bindings (origin/digest/hash)`);
      }
    }

    validatedSources.push(source);
  }

  // Sort by priority
  const sortedSources = [...validatedSources].sort((a, b) => {
    return getPriorityValue(a.priority) - getPriorityValue(b.priority);
  });

  // Build configs for merge
  const configs = sortedSources.map((source) => {
    const content = values.get(source.id) as T;
    const metadata = extractSourceMetadata(content);
    return {
      priority: source.priority,
      content: content ?? {},
      sourceId: source.id,
      contentHash: metadata?.contentHash ?? source.contentHash,
    };
  });

  // Merge configs
  const mergeResult = mergeConfigs(configs);

  // Calculate schema hash
  const schemaHash = calculateSchemaHash(mergeResult.value);

  // Calculate resolved hash
  const resolvedHash = hashConfigContent({
    sources: mergeResult.sources.map((s) => s.contentHash),
    schema: schemaHash,
    value: mergeResult.value,
  });

  return {
    value: mergeResult.value as T,
    sourceOrder: sortedSources,
    sourceHashes: mergeResult.sources.map((s) => s.contentHash),
    schemaHash,
    resolvedHash,
    resolvedAt: new Date().toISOString(),
  };
}

/**
 * Checks if a source is a known/recognized source.
 */
function isKnownSource(source: ConfigSource): boolean {
  const knownOrigins = [
    'compiled',
    'image-manifest',
    'deployment-config',
    'environment',
    'runtime-overlay',
  ];
  return knownOrigins.includes(source.origin) || source.id.startsWith('env:') || source.id.startsWith('file:');
}

/**
 * Checks if a source is remote (URL-based).
 */
function isRemoteSource(source: ConfigSource): boolean {
  return source.origin.startsWith('http://') || source.origin.startsWith('https://');
}

/**
 * Gets numeric priority value for sorting.
 */
function getPriorityValue(priority: ConfigSourcePriority): number {
  const priorityOrder: Record<ConfigSourcePriority, number> = {
    compiled: 1,
    image: 2,
    deployment: 3,
    environment: 4,
    overlay: 5,
  };
  return priorityOrder[priority];
}

/**
 * Calculates schema hash from config value keys.
 */
function calculateSchemaHash(value: object): string {
  const keys = Object.keys(value).sort();
  return hashConfigContent(keys);
}

/**
 * Verifies config drift between two resolved configs.
 * Returns true if configs are identical.
 */
export function verifyConfigDrift(
  before: ResolvedConfig,
  after: ResolvedConfig,
): { hasDrift: boolean; details: string[] } {
  const details: string[] = [];

  if (before.resolvedHash !== after.resolvedHash) {
    details.push('Resolved hash mismatch');

    // Check what changed
    if (before.schemaHash !== after.schemaHash) {
      details.push('Schema hash changed (keys differ)');
    }

    const beforeSources = new Set(before.sourceOrder.map((s) => s.id));
    const afterSources = new Set(after.sourceOrder.map((s) => s.id));

    const added = [...afterSources].filter((s) => !beforeSources.has(s));
    const removed = [...beforeSources].filter((s) => !afterSources.has(s));

    if (added.length > 0) details.push(`Added sources: ${added.join(', ')}`);
    if (removed.length > 0) details.push(`Removed sources: ${removed.join(', ')}`);
  }

  return {
    hasDrift: details.length > 0,
    details,
  };
}

/**
 * Extracts redacted config fingerprint for external display.
 * Does not expose secrets.
 */
export function getConfigFingerprint(config: ResolvedConfig): string {
  return config.resolvedHash.slice(0, 12) + '...';
}

/**
 * Extracts redacted source info (no secrets).
 */
export function getRedactedSources(config: ResolvedConfig): Array<{
  id: string;
  origin: string;
  hasSecrets: boolean;
  contentHash: string;
}> {
  return config.sourceOrder.map((source) => ({
    id: source.id,
    origin: source.origin,
    hasSecrets: source.hasSecrets,
    contentHash: source.contentHash,
  }));
}
