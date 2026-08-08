/**
 * Configuration Merge Semantics
 *
 * Deterministic merge strategy for config values.
 * Handles Object, Array, Null, missing, and explicit null overrides.
 *
 * @module runtime/config/merge
 */

import type { ConfigSourcePriority } from './configSources';

/**
 * Merge strategy for config values.
 */
export type MergeStrategy = 'deep' | 'shallow' | 'replace';

/**
 * Merge result with attribution metadata.
 */
export interface MergeResult<T> {
  value: T;
  sources: {
    resolvedFrom: string;
    contentHash: string;
  }[];
}

/**
 * Sentinel value to explicitly delete a key.
 * Use `DELETE_KEY` as value to remove a property during merge.
 */
export const DELETE_KEY = Symbol('DELETE_KEY');

/**
 * Checks if a value is the delete sentinel.
 */
export function isDeleteKey(value: unknown): value is typeof DELETE_KEY {
  return value === DELETE_KEY;
}

/**
 * Merges two values according to merge semantics:
 * - Object: deep merge (recursive)
 * - Array: replace (not concatenate)
 * - Null: replaces previous value
 * - Explicit DELETE_KEY: removes key
 * - Primitive: replace
 */
export function mergeValue<T>(
  base: T,
  override: unknown,
  key: string,
): { value: T; changed: boolean } {
  // Handle DELETE_KEY: explicitly remove the key
  if (isDeleteKey(override)) {
    return { value: undefined as unknown as T, changed: true };
  }

  // If override is null, replace
  if (override === null) {
    return { value: null as unknown as T, changed: true };
  }

  // If base is null or undefined, replace
  if (base === null || base === undefined) {
    return { value: override as T, changed: true };
  }

  // If override is primitive, replace
  if (typeof override !== 'object') {
    return { value: override as T, changed: base !== override };
  }

  // If base is primitive, replace
  if (typeof base !== 'object') {
    return { value: override as T, changed: true };
  }

  // Handle Array: replace entirely (not concatenate)
  if (Array.isArray(override)) {
    return { value: override as T, changed: true };
  }

  // Handle Array base: replace with object
  if (Array.isArray(base)) {
    return { value: override as T, changed: true };
  }

  // Handle Object: deep merge
  const result = mergeObjects(base as object, override as object);
  return { value: result as T, changed: true };
}

/**
 * Deep merges two objects, recursively applying merge semantics.
 */
function mergeObjects(base: object, override: object): object {
  const result: Record<string, unknown> = { ...base };

  for (const key of Object.keys(override)) {
    const baseValue = result[key];
    const overrideValue = override[key as keyof typeof override];

    const { value } = mergeValue(baseValue, overrideValue, key);
    result[key] = value;
  }

  return result;
}

/**
 * Merges multiple config sources according to priority order.
 * Lower priority number = higher precedence.
 *
 * @param configs Array of { priority, content, sourceId, contentHash }
 * @returns Merged configuration
 */
export function mergeConfigs<T extends object>(
  configs: Array<{
    priority: ConfigSourcePriority;
    content: T;
    sourceId: string;
    contentHash: string;
  }>,
): MergeResult<T> {
  if (configs.length === 0) {
    return { value: {} as T, sources: [] };
  }

  if (configs.length === 1) {
    return {
      value: configs[0].content,
      sources: [{ resolvedFrom: configs[0].sourceId, contentHash: configs[0].contentHash }],
    };
  }

  // Sort by priority (lower = higher precedence)
  const sorted = [...configs].sort((a, b) => {
    const priorityOrder: Record<ConfigSourcePriority, number> = {
      compiled: 1,
      image: 2,
      deployment: 3,
      environment: 4,
      overlay: 5,
    };
    return priorityOrder[a.priority] - priorityOrder[b.priority];
  });

  // Start with highest precedence
  let merged: object = { ...sorted[0].content };
  const sources: MergeResult<T>['sources'] = [
    { resolvedFrom: sorted[0].sourceId, contentHash: sorted[0].contentHash },
  ];

  // Apply overrides in order
  for (let i = 1; i < sorted.length; i++) {
    const config = sorted[i];
    merged = mergeObjects(merged, config.content);
    sources.push({ resolvedFrom: config.sourceId, contentHash: config.contentHash });
  }

  return { value: merged as T, sources };
}

/**
 * Validates merge result against expected structure.
 * Returns array of validation errors (empty if valid).
 */
export function validateMergeResult<T extends object>(
  result: MergeResult<T>,
  expectedKeys?: string[],
): string[] {
  const errors: string[] = [];

  if (!result || typeof result !== 'object') {
    errors.push('Merge result must be an object');
    return errors;
  }

  if (!result.value || typeof result.value !== 'object') {
    errors.push('Merge result value must be an object');
  }

  if (!Array.isArray(result.sources)) {
    errors.push('Merge result sources must be an array');
  }

  if (expectedKeys) {
    const valueKeys = Object.keys(result.value as object);
    for (const key of expectedKeys) {
      if (!valueKeys.includes(key)) {
        errors.push(`Expected key "${key}" not found in merged config`);
      }
    }
  }

  return errors;
}
