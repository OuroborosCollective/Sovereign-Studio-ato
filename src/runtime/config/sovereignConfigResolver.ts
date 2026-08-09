/**
 * Configuration Provenance - Deterministic Resolver
 *
 * Resolves an ordered set of ConfigSourceContract contributions into a single
 * redacted projection with a byte-identical receipt hash. Unknown sources and
 * bare remote URLs fail closed. Remote config requires pre-bound origin,
 * digest and signature/hash. Drift against an expected binding invalidates the
 * resolution (status BLOCKED/CONTRADICTED) so prior run/permission bindings
 * and active action plans are blocked rather than silently continuing.
 *
 * @module runtime/config/sovereignConfigResolver
 */

import {
  SOURCE_ORDER,
  SOURCE_PRIORITY,
  isAllowedSourceKind,
  type ConfigSourceContract,
  type ConfigSourceKind,
  type ConfigResolutionContract,
  type ConfigDriftRecord,
  type SourceHashRecord,
} from './configSources';
import { canonicalJson, hashValue, mergeValues, schemaHashFromFields } from './configCanonicalize';

/**
 * Options for resolving a configuration source set.
 */
export interface ResolveOptions {
  /**
   * Previously bound receipt hash. When provided, a mismatch produces a
   * content-drift record and BLOCKED status, invalidating prior bindings.
   */
  readonly expectedReceiptHash?: string;
  /**
   * Allowed remote origins. Remote sources whose origin is not in this set
   * fail closed. Defaults to an empty set (all remote rejected).
   */
  readonly allowedRemoteOrigins?: ReadonlySet<string>;
  /**
   * Schema fields the resolved projection is expected to conform to. When
   * provided, a schema-hash mismatch against the sources produces schema drift.
   */
  readonly schemaFields?: ReadonlyArray<{ readonly name: string; readonly kind: string }>;
}

/**
 * Resolve a set of configuration sources deterministically.
 *
 * Returns a ConfigResolutionContract. The same input set always produces the
 * same `resolvedHash`. On any fail-closed condition the status is BLOCKED (or
 * CONTRADICTED for drift) and `resolved` is empty.
 */
export async function resolveConfigSources(
  sources: readonly ConfigSourceContract[],
  options: ResolveOptions = {},
): Promise<ConfigResolutionContract> {
  const errors: string[] = [];
  const allowedOrigins = options.allowedRemoteOrigins ?? new Set<string>();

  // 1. Validate each source: known kind, present hashes, remote binding.
  const validated: ConfigSourceContract[] = [];
  for (const source of sources) {
    if (!isAllowedSourceKind(source.kind)) {
      errors.push(`unknown source kind: ${source.kind} (id=${source.id})`);
      continue;
    }
    if (!source.revision) {
      errors.push(`missing revision (id=${source.id})`);
      continue;
    }
    if (!source.contentHash) {
      errors.push(`missing contentHash (id=${source.id})`);
      continue;
    }
    if (!source.schemaHash) {
      errors.push(`missing schemaHash (id=${source.id})`);
      continue;
    }
    if (source.remote) {
      if (!source.remote.origin) {
        errors.push(`remote source without origin (id=${source.id})`);
        continue;
      }
      if (!source.remote.digest) {
        errors.push(`remote source without digest (id=${source.id})`);
        continue;
      }
      if (!source.remote.signatureHash) {
        errors.push(`remote source without signatureHash (id=${source.id})`);
        continue;
      }
      if (!allowedOrigins.has(source.remote.origin)) {
        errors.push(`remote origin not pre-bound/allowed: ${source.remote.origin} (id=${source.id})`);
        continue;
      }
    }
    validated.push(source);
  }

  if (errors.length > 0) {
    return blockedResolution(errors, [], null);
  }

  // 2. Stable sort by priority ascending (lowest first), then by id for tie-break.
  const ordered = [...validated].sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });

  // 3. Derive the effective source order (kinds present, ascending).
  const presentKinds = uniqueKindsInOrder(ordered);

  // 4. Merge values low->high.
  let merged: Record<string, unknown> = {};
  for (const source of ordered) {
    merged = mergeValues(merged, source.values);
  }

  // 5. Compute resolved hash over the canonical, redacted projection.
  const resolvedHash = await hashValue(merged);

  // 6. Build per-source hash records for readback.
  const sourceHashes: SourceHashRecord[] = ordered.map(s => ({
    id: s.id,
    kind: s.kind,
    revision: s.revision,
    contentHash: s.contentHash,
    schemaHash: s.schemaHash,
    priority: s.priority,
    remoteOrigin: s.remote?.origin ?? null,
    remoteDigest: s.remote?.digest ?? null,
  }));

  // 7. Schema-hash coherence: all sources must agree on schemaHash.
  const schemaHashes = new Set(ordered.map(s => s.schemaHash));
  if (schemaHashes.size > 1) {
    const drift: ConfigDriftRecord = {
      kind: 'schema-drift',
      detail: `sources disagree on schemaHash: ${[...schemaHashes].join(', ')}`,
      expectedHash: null,
      actualHash: resolvedHash,
    };
    return blockedResolution([drift.detail], sourceHashes, drift);
  }
  const schemaHash = ordered[0]?.schemaHash ?? '';

  // 8. Optional expected-schema coherence check.
  if (options.schemaFields) {
    const expectedSchemaHash = schemaHashFromFields(options.schemaFields);
    if (schemaHash && schemaHash !== expectedSchemaHash) {
      const drift: ConfigDriftRecord = {
        kind: 'schema-drift',
        detail: `schemaHash mismatch: expected ${expectedSchemaHash}, got ${schemaHash}`,
        expectedHash: null,
        actualHash: resolvedHash,
      };
      return blockedResolution([drift.detail], sourceHashes, drift);
    }
  }

  // 9. Drift against prior binding.
  if (options.expectedReceiptHash && options.expectedReceiptHash !== resolvedHash) {
    const drift: ConfigDriftRecord = {
      kind: 'content-drift',
      detail: `resolved hash ${resolvedHash} != expected ${options.expectedReceiptHash}`,
      expectedHash: options.expectedReceiptHash,
      actualHash: resolvedHash,
    };
    return {
      status: 'CONTRADICTED',
      sourceOrder: presentKinds,
      sourceHashes,
      schemaHash,
      resolvedHash,
      resolved: {},
      drift,
      errors: [drift.detail],
    };
  }

  return {
    status: 'RESOLVED',
    sourceOrder: presentKinds,
    sourceHashes,
    schemaHash,
    resolvedHash,
    resolved: merged,
    drift: null,
    errors: [],
  };
}

/**
 * Compute the receipt hash for a source set without requiring full validation
 * (used to pre-bind an expected hash). Performs the same merge + hash as the
 * resolver but skips fail-closed gates.
 */
export async function computeReceiptHash(
  sources: readonly ConfigSourceContract[],
): Promise<string> {
  const ordered = [...sources].sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });
  let merged: Record<string, unknown> = {};
  for (const source of ordered) {
    merged = mergeValues(merged, source.values);
  }
  return hashValue(merged);
}

/**
 * Derive the default priority for a source kind. Exposed so callers building
 * ConfigSourceContract can rely on the canonical order.
 */
export function defaultPriorityFor(kind: ConfigSourceKind): number {
  return SOURCE_PRIORITY[kind];
}

/** The canonical source order (all kinds, ascending priority). */
export function canonicalSourceOrder(): readonly ConfigSourceKind[] {
  return SOURCE_ORDER;
}

function uniqueKindsInOrder(ordered: readonly ConfigSourceContract[]): ConfigSourceKind[] {
  const seen = new Set<ConfigSourceKind>();
  const out: ConfigSourceKind[] = [];
  for (const s of ordered) {
    if (!seen.has(s.kind)) {
      seen.add(s.kind);
      out.push(s.kind);
    }
  }
  return out;
}

function blockedResolution(
  errors: string[],
  sourceHashes: SourceHashRecord[],
  drift: ConfigDriftRecord | null,
): ConfigResolutionContract {
  return {
    status: 'BLOCKED',
    sourceOrder: [],
    sourceHashes,
    schemaHash: '',
    resolvedHash: '',
    resolved: {},
    drift,
    errors,
  };
}

/**
 * Inspect whether a resolved contract is safe to start a container / advance
 * an action plan with. Only RESOLVED (no drift, no errors) is safe.
 */
export function isSafeToAdvance(contract: ConfigResolutionContract): boolean {
  return contract.status === 'RESOLVED' && contract.errors.length === 0 && contract.drift === null;
}

/**
 * Canonical JSON of the resolved projection (exposed for readback/debug).
 */
export function resolvedCanonicalJson(contract: ConfigResolutionContract): string {
  return canonicalJson(contract.resolved);
}
