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
