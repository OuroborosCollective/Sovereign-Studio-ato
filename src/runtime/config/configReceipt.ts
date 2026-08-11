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
 * Independent PatchMon readback of the actually-loaded config projection.
 * PatchMon observes the running container and reports the identity fields it
 * read back. These are compared against the materialized `ConfigReceipt` that
 * RunEnvelope carries. Every bound (non-null) field must match exactly.
 */
export interface ConfigReadbackObservation {
  readonly revision: string | null;
  readonly imageDigest: string | null;
  readonly schemaHash: string | null;
  readonly resolvedHash: string | null;
  /** Redacted config fingerprint both sides must agree on (#1169). */
  readonly receiptHash: string | null;
}

/** Finding code explaining why a config readback was rejected. */
export type ConfigReadbackBlocker =
  | 'config_receipt_self_verification_failed'
  | 'config_receipt_not_resolved'
  | 'config_receipt_not_advanceable'
  | 'config_readback_missing_bound_field'
  | 'config_readback_contradicts_receipt';

export interface ConfigReadbackAudit {
  readonly accepted: boolean;
  readonly blocker: ConfigReadbackBlocker | null;
  /** A contradiction is a harder failure than missing evidence. */
  readonly contradicted: boolean;
}

/**
 * Confirm a PatchMon readback matches a bound config receipt.
 *
 * Fails closed: the receipt must self-verify (no tampering), then every bound
 * field on the observation must equal the receipt's bound field. A mismatch on
 * a populated field is a *contradiction* (the wrong config is loaded); a
 * missing field (null on the observation while the receipt binds it) is a
 * *blocker* (readback incomplete). Either blocks RUNTIME advancement per the
 * #1169 DoD: RunEnvelope and PatchMon must read back the same redacted config
 * fingerprint.
 */
export async function verifyConfigReadback(
  receipt: ConfigReceipt,
  observation: ConfigReadbackObservation,
): Promise<ConfigReadbackAudit> {
  if (!(await verifyReceipt(receipt))) {
    return { accepted: false, blocker: 'config_receipt_self_verification_failed', contradicted: false };
  }
  if (receipt.status !== 'RESOLVED') {
    return { accepted: false, blocker: 'config_receipt_not_resolved', contradicted: false };
  }
  if (receipt.drift !== null || receipt.errors.length > 0) {
    return { accepted: false, blocker: 'config_receipt_not_advanceable', contradicted: false };
  }

  const pairs: ReadonlyArray<readonly [string, string | null, string | null]> = [
    ['revision', receipt.revision, observation.revision],
    ['imageDigest', receipt.imageDigest, observation.imageDigest],
    ['schemaHash', receipt.schemaHash, observation.schemaHash],
    ['resolvedHash', receipt.resolvedHash, observation.resolvedHash],
  ];

  for (const [_field, expected, actual] of pairs) {
    const expectedNorm = (expected ?? '').trim().toLowerCase();
    const actualNorm = (actual ?? '').trim().toLowerCase();
    if (!expectedNorm) continue; // receipt does not bind this field
    if (!actualNorm) {
      return { accepted: false, blocker: 'config_readback_missing_bound_field', contradicted: false };
    }
    if (actualNorm !== expectedNorm) {
      return { accepted: false, blocker: 'config_readback_contradicts_receipt', contradicted: true };
    }
  }

  const reportedHash = (observation.receiptHash ?? '').trim().toLowerCase();
  if (reportedHash) {
    if (reportedHash !== (receipt.receiptHash ?? '').trim().toLowerCase()) {
      return { accepted: false, blocker: 'config_readback_contradicts_receipt', contradicted: true };
    }
  } else {
    return { accepted: false, blocker: 'config_readback_missing_bound_field', contradicted: false };
  }

  return { accepted: true, blocker: null, contradicted: false };
}

/**
 * Fixed epoch used as the default materialization timestamp so that receipt
 * hashes are deterministic across runs for identical input. Callers that need
 * a real wall-clock timestamp must pass `materializedAt` explicitly (which
 * then becomes part of the bound identity).
 */
export const DETERMINISTIC_EPOCH = '1970-01-01T00:00:00Z';
