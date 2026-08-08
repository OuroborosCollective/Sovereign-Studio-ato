/**
 * Configuration Provenance Module
 *
 * Deterministic config resolution with source hashes and PatchMon readback.
 *
 * @module runtime/config
 */

// Sources
export {
  type ConfigSource,
  type ConfigSourcePriority,
  CONFIG_SOURCE_PRIORITIES,
  extractSourceMetadata,
  hashConfigContent,
  hashConfigContentAsync,
  validateRemoteSource,
} from './configSources';

// Merge
export {
  type MergeStrategy,
  type MergeResult,
  DELETE_KEY,
  isDeleteKey,
  mergeValue,
  mergeConfigs,
  validateMergeResult,
} from './configMerge';

// Resolver
export {
  type ResolvedConfig,
  type ResolveOptions,
  resolveConfig,
  verifyConfigDrift,
  getConfigFingerprint,
  getRedactedSources,
} from './configResolver';

// Receipt
export {
  type ConfigReceipt,
  createPublicReceiptHash,
  createConfigReceipt,
  verifyConfigReceipt,
  getPatchMonProjection,
  isReceiptBound,
} from './configReceipt';
