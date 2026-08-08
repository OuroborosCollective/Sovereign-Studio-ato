/**
 * Configuration Provenance - Source Contracts
 *
 * Revisions-, schema- and source-bound configuration resolution.
 * Each source binds ID, revision/digest, content-hash, schema-hash and priority.
 *
 * Resolution order (lowest priority first, later wins unless explicitly deleted):
 *
 *   compiled defaults
 *   -> immutable image manifest
 *   -> revision-bound deployment config
 *   -> environment projection
 *   -> explicitly approved runtime overlay
 *
 * Secrets are projected only as a redacted identity. This module never stores,
 * logs or reveals secret material - it only records that a secret-shaped value
 * was bound under a stable redacted id.
 *
 * @module runtime/config/configSources
 */

/** Stable identifier for a known/allowed configuration source origin. */
export type ConfigSourceKind =
  | 'compiled-defaults'
  | 'image-manifest'
  | 'deployment-config'
  | 'environment-projection'
  | 'approved-runtime-overlay';

/**
 * Monotonic priority. Higher priority overrides lower priority during merge
 * (subject to explicit-delete / null semantics). The order mirrors the
 * resolution order defined in the issue contract.
 */
export const SOURCE_PRIORITY: Readonly<Record<ConfigSourceKind, number>> = Object.freeze({
  'compiled-defaults': 0,
  'image-manifest': 10,
  'deployment-config': 20,
  'environment-projection': 30,
  'approved-runtime-overlay': 40,
});

/** Ordered source kinds, lowest priority first. */
export const SOURCE_ORDER: readonly ConfigSourceKind[] = Object.freeze(
  (Object.keys(SOURCE_PRIORITY) as ConfigSourceKind[]).sort(
    (a, b) => SOURCE_PRIORITY[a] - SOURCE_PRIORITY[b],
  ),
);

/**
 * A redacted secret identity. `redactedId` is a stable, non-reversible hash of
 * the secret material (used for drift detection) - never the secret itself.
 */
export interface RedactedSecret {
  readonly redactedId: string;
  readonly kind: 'secret';
}

/**
 * A remote-bound configuration origin. Remote config is only accepted when it
 * carries a pre-bound origin, digest and signature/hash. Unknown origins or
 * bare remote URLs fail closed.
 */
export interface RemoteBinding {
  readonly origin: string;
  /** Expected content digest (e.g. sha256 hex) of the remote payload. */
  readonly digest: string;
  /** Hash or signature bound to the digest; never a secret. */
  readonly signatureHash: string;
}

/**
 * A single configuration source contribution.
 *
 * `values` is the parsed, in-memory projection of this source. Values that are
 * secret-shaped MUST be wrapped in a `RedactedSecret` so the resolver and
 * receipt never touch raw material.
 */
export interface ConfigSourceContract {
  readonly id: string;
  readonly kind: ConfigSourceKind;
  /** Revision (git sha) or image digest this source is bound to. */
  readonly revision: string;
  /** sha256 hex of the canonicalized source content. */
  readonly contentHash: string;
  /** sha256 hex of the schema descriptor this source conforms to. */
  readonly schemaHash: string;
  /** Monotonic priority (derived from kind unless explicitly overridden). */
  readonly priority: number;
  /** Parsed values contributed by this source. */
  readonly values: Readonly<Record<string, unknown>>;
  /** Optional remote binding. When present, origin+digest+signatureHash are verified. */
  readonly remote?: RemoteBinding;
}

/**
 * Schema descriptor. `schemaHash` is sha256 of the canonical JSON of the field
 * list, so two schemas with identical shape produce identical hashes.
 */
export interface ConfigSchemaDescriptor {
  readonly id: string;
  readonly fields: ReadonlyArray<{ readonly name: string; readonly kind: string }>;
}

/** Outcome of a resolution attempt. */
export type ResolutionStatus =
  | 'RESOLVED'
  | 'BLOCKED'
  | 'CONTRADICTED'
  | 'DEGRADED';

/**
 * Per-source hash record exposed to RunEnvelope / PatchMon readback.
 * Never includes secret material.
 */
export interface SourceHashRecord {
  readonly id: string;
  readonly kind: ConfigSourceKind;
  readonly revision: string;
  readonly contentHash: string;
  readonly schemaHash: string;
  readonly priority: number;
  readonly remoteOrigin: string | null;
  readonly remoteDigest: string | null;
}

/**
 * Full resolution contract returned by the resolver. `resolvedHash` is the
 * byte-identical public receipt hash for the same input set.
 */
export interface ConfigResolutionContract {
  readonly status: ResolutionStatus;
  readonly sourceOrder: readonly ConfigSourceKind[];
  readonly sourceHashes: readonly SourceHashRecord[];
  readonly schemaHash: string;
  /** sha256 hex of the canonical resolved (redacted) projection. */
  readonly resolvedHash: string;
  /** The resolved, redacted projection (no raw secrets). */
  readonly resolved: Readonly<Record<string, unknown>>;
  readonly drift: ConfigDriftRecord | null;
  readonly errors: readonly string[];
}

/**
 * Drift record. When drift is detected, prior run/permission bindings are
 * invalidated and active action plans are blocked.
 */
export interface ConfigDriftRecord {
  readonly kind: 'schema-drift' | 'content-drift' | 'source-order-drift' | 'remote-binding-drift';
  readonly detail: string;
  /** The receipt hash the system expected (from a prior binding), if any. */
  readonly expectedHash: string | null;
  readonly actualHash: string;
}

/** Allowed source kinds for fast membership checks. */
export const ALLOWED_SOURCE_KINDS: ReadonlySet<ConfigSourceKind> = new Set(
  Object.keys(SOURCE_PRIORITY) as ConfigSourceKind[],
);

/**
 * Validate that a source kind is known. Unknown sources fail closed.
 */
export function isAllowedSourceKind(kind: string): kind is ConfigSourceKind {
  return ALLOWED_SOURCE_KINDS.has(kind as ConfigSourceKind);
}
