/**
 * Configuration Provenance - Receipts
 *
 * A public receipt is a redacted, serializable projection of a resolved
 * configuration. The same resolved configuration always produces the same
 * `receiptHash` (byte-identical). Receipts never contain secrets - only
 * redacted identities and hash/digest readback values.
 *
 * PatchMon reads back: revision, image digest, schema hash and the redacted
 * config hash from the same receipt.
 *
 * @module runtime/config/configReceipt
 */

import type { ConfigResolutionContract, SourceHashRecord } from './configSources';
import { canonicalJson, hashValue } from './configCanonicalize';

/**
 * Public configuration receipt. Safe to emit to RunEnvelope (#1116) and to
 * PatchMon readback. Contains no raw secret material.
 */
export interface ConfigReceipt {
  readonly receiptHash: string;
  readonly status: ConfigResolutionContract['status'];
  readonly sourceOrder: readonly string[];
  readonly sourceHashes: readonly SourceHashRecord[];
  readonly schemaHash: string;
  readonly resolvedHash: string;
  readonly resolved: Readonly<Record<string, unknown>>;
  readonly drift: ConfigResolutionContract['drift'];
  readonly errors: readonly string[];
  /** Bound revision read back by PatchMon. */
  readonly revision: string | null;
  /** Bound image digest read back by PatchMon (if present). */
  readonly imageDigest: string | null;
  /** ISO timestamp the receipt was materialized. */
  readonly materializedAt: string;
}

export interface ReceiptOptions {
  /**
   * The container/image revision to bind. PatchMon reads this back.
   */
  readonly revision?: string;
  /**
   * The immutable image digest to bind. PatchMon reads this back.
   */
  readonly imageDigest?: string;
  /**
   * Override the materialization timestamp. When omitted, a fixed epoch is
   * used so the receipt hash is deterministic and independent of wall-clock
   * time (same input -> same receiptHash).
   */
  readonly materializedAt?: string;
}

/**
 * Materialize a public receipt from a resolved contract.
 *
 * The `receiptHash` is sha256 of the canonical receipt body (excluding the
 * hash field itself), so identical resolved state yields identical receipts.
 * Timestamps default to a fixed epoch to preserve determinism unless
 * explicitly overridden.
 */
export async function materializeReceipt(
  contract: ConfigResolutionContract,
  options: ReceiptOptions = {},
): Promise<ConfigReceipt> {
  const materializedAt = options.materializedAt ?? DETERMINISTIC_EPOCH;
  const receiptWithoutHash: Omit<ConfigReceipt, 'receiptHash'> = {
    status: contract.status,
    sourceOrder: contract.sourceOrder,
    sourceHashes: contract.sourceHashes,
    schemaHash: contract.schemaHash,
    resolvedHash: contract.resolvedHash,
    resolved: contract.resolved,
    drift: contract.drift,
    errors: contract.errors,
    revision: options.revision ?? null,
    imageDigest: options.imageDigest ?? null,
    materializedAt,
  };
  const receiptHash = await computeReceiptHash(receiptWithoutHash);
  return { ...receiptWithoutHash, receiptHash };
}

/**
 * Compute the receipt hash from a receipt body (without the receiptHash
 * field). Deterministic: same body -> same hash.
 */
export async function computeReceiptHash(
  body: Omit<ConfigReceipt, 'receiptHash'>,
): Promise<string> {
  // The hash is computed over a canonical projection that intentionally
  // excludes the receiptHash field (which does not exist on `body`).
  return hashValue(canonicalReceiptBody(body));
}

/**
 * Canonical, redacted projection of a receipt body used for hashing.
 */
export function canonicalReceiptBody(body: Omit<ConfigReceipt, 'receiptHash'>): unknown {
  return JSON.parse(canonicalJson(body));
}

/**
 * Verify that a receipt's stated receiptHash matches a recomputation.
 * Used by PatchMon / readback consumers to confirm integrity.
 */
export async function verifyReceipt(receipt: ConfigReceipt): Promise<boolean> {
  const { receiptHash, ...body } = receipt;
  const recomputed = await computeReceiptHash(body);
  return recomputed === receiptHash;
}

/**
 * Fixed epoch used as the default materialization timestamp so that receipt
 * hashes are deterministic across runs for identical input. Callers that need
 * a real wall-clock timestamp must pass `materializedAt` explicitly (which
 * then becomes part of the bound identity).
 */
export const DETERMINISTIC_EPOCH = '1970-01-01T00:00:00Z';

// ---------------------------------------------------------------------------
// PatchMon readback (#1169)
//
// PatchMon independently reads back the configuration identity the running
// container actually loaded. A container is considered configured only when
// PatchMon's readback matches the resolved receipt exactly. Any mismatch, or a
// receipt that was never RESOLVED/bound, yields BLOCKED or CONTRADICTED -
// never a green state on a stale or unbound projection.
// ---------------------------------------------------------------------------

export const READBACK_VERIFIED = 'VERIFIED';
export const READBACK_CONTRADICTED = 'CONTRADICTED';
export const READBACK_BLOCKED = 'BLOCKED';

export type ReadbackVerdict =
  | typeof READBACK_VERIFIED
  | typeof READBACK_CONTRADICTED
  | typeof READBACK_BLOCKED;

/**
 * Independent PatchMon observation of the loaded configuration identity.
 * Every field is a redacted, hash/digest value - never raw config or secrets.
 */
export interface PatchMonReadback {
  readonly revision: string | null;
  readonly imageDigest: string | null;
  readonly schemaHash: string | null;
  readonly configHash: string | null;
}

export interface ReadbackResult {
  readonly verdict: ReadbackVerdict;
  readonly matchedFields: readonly string[];
  readonly mismatchedFields: readonly string[];
  readonly missingFields: readonly string[];
  readonly detail: string;
}

type ReadbackField = {
  readonly observedKey: keyof PatchMonReadback;
  readonly receiptKey: keyof ConfigReceipt;
  readonly label: string;
};

const READBACK_FIELDS: readonly ReadbackField[] = [
  { observedKey: 'revision', receiptKey: 'revision', label: 'revision' },
  { observedKey: 'imageDigest', receiptKey: 'imageDigest', label: 'imageDigest' },
  { observedKey: 'schemaHash', receiptKey: 'schemaHash', label: 'schemaHash' },
  {
    observedKey: 'configHash',
    receiptKey: 'resolvedHash',
    label: 'resolvedHash (config)',
  },
];

/**
 * Compare a bound receipt against an independent PatchMon readback (#1169).
 *
 * Returns a ReadbackResult whose verdict is:
 *   - VERIFIED      only when the receipt is RESOLVED and every bound field
 *                   PatchMon must confirm matches exactly;
 *   - CONTRADICTED  when a field PatchMon observed does not match the bound
 *                   receipt (loaded projection diverges from resolved);
 *   - BLOCKED       when the receipt was not RESOLVED, or a required field is
 *                   missing on either side (unknown truth, not green).
 *
 * PatchMon readback never promotes a non-RESOLVED or tampered receipt to
 * VERIFIED.
 */
export function comparePatchMonReadback(
  receipt: ConfigReceipt,
  observed: PatchMonReadback,
): ReadbackResult {
  const matched: string[] = [];
  const mismatched: string[] = [];
  const missing: string[] = [];

  if (receipt.status !== 'RESOLVED') {
    return {
      verdict: READBACK_BLOCKED,
      matchedFields: [],
      mismatchedFields: [],
      missingFields: [],
      detail: `receipt not RESOLVED (status=${receipt.status})`,
    };
  }

  for (const field of READBACK_FIELDS) {
    const bound = receipt[field.receiptKey] as string | null;
    const seen = observed[field.observedKey] as string | null;
    if (!bound || !seen) {
      missing.push(field.label);
      continue;
    }
    if (bound === seen) {
      matched.push(field.label);
    } else {
      mismatched.push(field.label);
    }
  }

  if (mismatched.length > 0) {
    return {
      verdict: READBACK_CONTRADICTED,
      matchedFields: matched,
      mismatchedFields: mismatched,
      missingFields: missing,
      detail: `PatchMon readback contradicts receipt: ${mismatched.join(', ')}`,
    };
  }
  if (missing.length > 0) {
    return {
      verdict: READBACK_BLOCKED,
      matchedFields: matched,
      mismatchedFields: [],
      missingFields: missing,
      detail: `PatchMon readback incomplete: ${missing.join(', ')}`,
    };
  }
  return {
    verdict: READBACK_VERIFIED,
    matchedFields: matched,
    mismatchedFields: [],
    missingFields: [],
    detail: 'PatchMon readback matches resolved receipt',
  };
}

// ---------------------------------------------------------------------------
// RunEnvelope config binding (#1116 / #1169)
//
// Binds a redacted config fingerprint to a run envelope hash so the run
// carries a deterministic, tamper-evident reference to the exact
// configuration projection it started under. The binding is read-only
// provenance: it never mutates config and never carries raw secret material
// (only hashes).
// ---------------------------------------------------------------------------

/**
 * A run envelope <-> resolved config binding. `bindingHash` is sha256 of the
 * canonical binding body (excluding the hash itself), so identical
 * (runEnvelopeHash, receiptHash) pairs always produce identical bindings.
 */
export interface ConfigRunBinding {
  readonly runEnvelopeHash: string;
  readonly configReceiptHash: string;
  readonly configFingerprint: string;
  readonly schemaHash: string;
  readonly revision: string | null;
  readonly imageDigest: string | null;
  readonly bindingHash: string;
}

/**
 * Bind a resolved config receipt to a run envelope hash (#1116).
 *
 * Produces a deterministic `ConfigRunBinding` whose `configFingerprint` is the
 * redacted public config hash (the receipt's resolvedHash) and whose
 * `bindingHash` ties the run envelope to that fingerprint. A non-RESOLVED or
 * tampered receipt still produces a binding, but callers MUST gate advancement
 * on `isSafeToAdvance` (resolver) / receipt.status === 'RESOLVED' before
 * trusting the binding - the fingerprint alone does not prove the config was
 * safely resolved.
 */
export async function bindConfigToRun(
  runEnvelopeHash: string,
  receipt: ConfigReceipt,
): Promise<ConfigRunBinding> {
  if (!runEnvelopeHash) {
    throw new Error('runEnvelopeHash is required');
  }
  if (!receipt.receiptHash) {
    throw new Error('receipt must carry a receiptHash');
  }
  const body = {
    runEnvelopeHash,
    configReceiptHash: receipt.receiptHash,
    configFingerprint: receipt.resolvedHash,
    schemaHash: receipt.schemaHash,
    revision: receipt.revision,
    imageDigest: receipt.imageDigest,
  };
  const bindingHash = await hashValue(JSON.parse(canonicalJson(body)));
  return {
    runEnvelopeHash,
    configReceiptHash: receipt.receiptHash,
    configFingerprint: receipt.resolvedHash,
    schemaHash: receipt.schemaHash,
    revision: receipt.revision,
    imageDigest: receipt.imageDigest,
    bindingHash,
  };
}
