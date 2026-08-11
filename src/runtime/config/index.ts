/**
 * Configuration Provenance - public surface
 *
 * Deterministic, revisions/schema/source-bound configuration resolution with
 * redacted receipts and PatchMon readback. Clean-room core (no external
 * dependency such as zod) - see docs/architecture/CONFIGURATION_PROVENANCE.md
 * for the clean-room rationale and Zod-4 pilot assessment.
 *
 * @module runtime/config
 */

export {
  SOURCE_PRIORITY,
  SOURCE_ORDER,
  ALLOWED_SOURCE_KINDS,
  isAllowedSourceKind,
} from './configSources';

export type {
  ConfigSourceKind,
  RedactedSecret,
  RemoteBinding,
  ConfigSourceContract,
  ConfigSchemaDescriptor,
  ResolutionStatus,
  SourceHashRecord,
  ConfigResolutionContract,
  ConfigDriftRecord,
} from './configSources';

export {
  canonicalJson,
  hashValue,
  hashString,
  mergeValues,
  isRedactedSecret,
  schemaHashFromFields,
} from './configCanonicalize';

export {
  resolveConfigSources,
  computeReceiptHash as computeResolvedHash,
  defaultPriorityFor,
  canonicalSourceOrder,
  isSafeToAdvance,
  resolvedCanonicalJson,
} from './sovereignConfigResolver';

export type { ResolveOptions } from './sovereignConfigResolver';

export {
  materializeReceipt,
  computeReceiptHash,
  verifyReceipt,
  canonicalReceiptBody,
  DETERMINISTIC_EPOCH,
} from './configReceipt';

export type { ConfigReceipt, ReceiptOptions } from './configReceipt';

export {
  bindConfigFingerprint,
  advanceDecision,
  materializeAndBind,
} from './runtimeBinding';

export type {
  ConfigFingerprintBinding,
  AdvanceDecision,
} from './runtimeBinding';
