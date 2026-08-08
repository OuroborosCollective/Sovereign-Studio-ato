/**
 * Configuration Receipt
 *
 * Immutable config receipt generation and verification.
 * Provides cryptographic evidence of config state.
 *
 * @module runtime/config/receipt
 */

import type { ResolvedConfig } from './configResolver';
import { hashConfigContent } from './configSources';

/**
 * Config receipt with cryptographic evidence.
 */
export interface ConfigReceipt {
  /** Unique receipt identifier */
  id: string;
  /** Resolved config fingerprint */
  configFingerprint: string;
  /** Schema hash */
  schemaHash: string;
  /** Source hashes in order */
  sourceHashes: string[];
  /** Public receipt hash (deterministic) */
  publicReceiptHash: string;
  /** Redacted sources (no secrets) */
  sources: Array<{
    id: string;
    origin: string;
    hasSecrets: boolean;
  }>;
  /** Image digest if bound */
  imageDigest?: string;
  /** Revision if bound */
  revision?: string;
  /** Timestamp */
  createdAt: string;
}

/**
 * Creates a deterministic public receipt hash.
 * Same input always produces byte-identical output.
 */
export function createPublicReceiptHash(
  configFingerprint: string,
  schemaHash: string,
  sourceHashes: string[],
): string {
  const payload = {
    fingerprint: configFingerprint,
    schema: schemaHash,
    sources: sourceHashes.slice().sort(), // Sort for determinism
  };
  return hashConfigContent(payload);
}

/**
 * Generates a config receipt from resolved config.
 */
export function createConfigReceipt(
  resolved: ResolvedConfig,
  options: {
    imageDigest?: string;
    revision?: string;
  } = {},
): ConfigReceipt {
  const sources = resolved.sourceOrder.map((source) => ({
    id: source.id,
    origin: source.origin,
    hasSecrets: source.hasSecrets,
  }));

  const publicReceiptHash = createPublicReceiptHash(
    resolved.resolvedHash,
    resolved.schemaHash,
    resolved.sourceHashes,
  );

  return {
    id: generateReceiptId(publicReceiptHash),
    configFingerprint: resolved.resolvedHash,
    schemaHash: resolved.schemaHash,
    sourceHashes: resolved.sourceHashes,
    publicReceiptHash,
    sources,
    imageDigest: options.imageDigest,
    revision: options.revision,
    createdAt: new Date().toISOString(),
  };
}

/**
 * Generates a unique receipt ID from hash.
 */
function generateReceiptId(hash: string): string {
  return `cfg_rcpt_${hash.slice(0, 16)}`;
}

/**
 * Verifies receipt integrity.
 * Returns true if receipt is valid and matches config.
 */
export function verifyConfigReceipt(
  receipt: ConfigReceipt,
  resolved: ResolvedConfig,
): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  // Verify fingerprint matches
  if (receipt.configFingerprint !== resolved.resolvedHash) {
    errors.push('Config fingerprint mismatch');
  }

  // Verify schema hash matches
  if (receipt.schemaHash !== resolved.schemaHash) {
    errors.push('Schema hash mismatch');
  }

  // Verify source hashes match
  if (JSON.stringify(receipt.sourceHashes.sort()) !== JSON.stringify(resolved.sourceHashes.sort())) {
    errors.push('Source hashes mismatch');
  }

  // Recalculate public receipt hash
  const expectedHash = createPublicReceiptHash(
    resolved.resolvedHash,
    resolved.schemaHash,
    resolved.sourceHashes,
  );

  if (receipt.publicReceiptHash !== expectedHash) {
    errors.push('Public receipt hash mismatch');
  }

  // Verify source count matches
  if (receipt.sources.length !== resolved.sourceOrder.length) {
    errors.push(`Source count mismatch: expected ${resolved.sourceOrder.length}, got ${receipt.sources.length}`);
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

/**
 * Extracts PatchMon-compatible config projection.
 */
export function getPatchMonProjection(receipt: ConfigReceipt): {
  revision: string | undefined;
  imageDigest: string | undefined;
  schemaHash: string;
  configHash: string;
  sourceCount: number;
} {
  return {
    revision: receipt.revision,
    imageDigest: receipt.imageDigest,
    schemaHash: receipt.schemaHash,
    configHash: receipt.configFingerprint,
    sourceCount: receipt.sources.length,
  };
}

/**
 * Checks if a receipt is bound to specific revision/digest.
 */
export function isReceiptBound(receipt: ConfigReceipt): boolean {
  return !!(receipt.revision || receipt.imageDigest);
}
