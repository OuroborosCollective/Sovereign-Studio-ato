/**
 * Runtime Configuration - Registry
 *
 * @module runtime/config
 */

// Re-export config sources
export {
  validateConfigSource,
  validateConfigResolution,
  generateConfigSourceSchemaHash,
  generateConfigResolutionSchemaHash,
  CONFIG_SOURCE_SCHEMA_ID,
  CONFIG_RESOLUTION_SCHEMA_ID,
  type ConfigSourceContract,
  type ConfigResolutionContract,
  type ValidationResult,
  type ValidationError,
  type ValidationWarning,
} from './configSources';

// Re-export config resolver
export {
  resolveConfig,
  validateConfigConsistency,
  createConfigSource,
  deepMerge,
  arrayMerge,
  EXPLICIT_DELETE,
  MERGE_STRATEGIES,
  type ResolverOptions,
  type ResolutionResult,
} from './configResolver';
