/**
 * Configuration Provenance - PatchMon Readback Verification
 *
 * PatchMon independently reads back the config projection that a running
 * container actually loaded (bound revision, image digest, schema hash and
 * redacted resolved hash). This module compares that independent observation
 * against a materialized {@link ConfigReceipt} and returns a deterministic
 * readback verdict. Mismatch routes the next action to BLOCKED / CONTRADICTED
 * so prior run/permission bindings are invalidated rather than silently
 * continuing - the runtime half of acceptance criterion #6 for #1169.
 *
 * This is read-only verification. It never mutates config (mutation flows
 * through #1119) and it never touches secret material: it only compares the
 * redacted hash/digest readback values that PatchMon observes.
 *
 * @module runtime/config/configReadback
 */

import type { ConfigReceipt } from './configReceipt';

/** Verdict PatchMon readback produces for a bound receipt. */
export type ReadbackVerdict = 'MATCHED' | 'MISMATCHED' | 'UNVERIFIABLE';

/**
 * The independent PatchMon observation of what the running container actually
 * loaded. Every field is a redacted hash/digest identity - never a secret.
 */
export interface PatchMonReadback {
  /** Bound revision the container reports (git sha), or null if not observed. */
  readonly revision: string | null;
  /** Immutable image digest the container reports, or null if not observed. */
  readonly imageDigest: string | null;
  /** Schema hash the container reports, or null if not observed. */
  readonly schemaHash: string | null;
  /** Redacted resolved config hash the container reports, or null if not observed. */
  readonly resolvedHash: string | null;
}

/** Result of comparing a receipt against a PatchMon observation. */
export interface ConfigReadbackResult {
  readonly verdict: ReadbackVerdict;
  /** True only when every bound field PatchMon observed matches the receipt. */
  readonly matched: boolean;
  /** Per-field comparison detail for readback/debug. Never contains secrets. */
  readonly fields: Readonly<Record<ReadbackField, ReadbackFieldState>>;
  /** Reason the verdict was not MATCHED (empty when MATCHED). */
  readonly reason: string;
}

/** The four readback fields PatchMon independently observes. */
export type ReadbackField = 'revision' | 'imageDigest' | 'schemaHash' | 'resolvedHash';

/** Per-field comparison state. */
export type ReadbackFieldState = 'matched' | 'mismatched' | 'unbound' | 'unobserved';

/**
 * Compare a materialized receipt against an independent PatchMon observation.
 *
 * A field is "bound" when the receipt carries a value for it (revision and
 * schemaHash are always present; imageDigest may be null when no image is
 * bound). A bound field that PatchMon did not observe (`null` in the readback)
 * yields UNVERIFIABLE, because PatchMon cannot confirm something it did not
 * read. A bound field whose observed value differs from the receipt yields
 * MISMATCHED. All bound fields matching yields MATCHED.
 *
 * Unbound optional fields (imageDigest absent on the receipt) are skipped:
 * PatchMon is not required to read back a digest that was never bound.
 */
export function verifyConfigReadback(
  receipt: ConfigReceipt,
  readback: PatchMonReadback,
): ConfigReadbackResult {
  // A tampered or broken receipt is never a match, regardless of observation.
  if (receipt.status !== 'RESOLVED') {
    return unverified('receipt is not RESOLVED', receipt);
  }

  const fields: Record<ReadbackField, ReadbackFieldState> = {
    revision: compareBound(receipt.revision, readback.revision),
    imageDigest: compareOptionalBound(receipt.imageDigest, readback.imageDigest),
    schemaHash: compareBound(receipt.schemaHash, readback.schemaHash),
    resolvedHash: compareBound(receipt.resolvedHash, readback.resolvedHash),
  };

  const mismatched = (Object.keys(fields) as ReadbackField[]).filter(
    f => fields[f] === 'mismatched',
  );
  const unobserved = (Object.keys(fields) as ReadbackField[]).filter(
    f => fields[f] === 'unobserved',
  );

  if (mismatched.length > 0) {
    const reason = `PatchMon readback mismatch: ${mismatched.join(', ')}`;
    return { verdict: 'MISMATCHED', matched: false, fields, reason };
  }
  if (unobserved.length > 0) {
    const reason = `PatchMon readback unverified: ${unobserved.join(', ')} not observed`;
    return { verdict: 'UNVERIFIABLE', matched: false, fields, reason };
  }
  return { verdict: 'MATCHED', matched: true, fields, reason: '' };
}

/** A bound (non-null) receipt field must be observed and equal. */
function compareBound(
  receiptValue: string | null,
  observed: string | null,
): ReadbackFieldState {
  if (receiptValue === null || receiptValue === '') return 'unbound';
  if (observed === null) return 'unobserved';
  return observed === receiptValue ? 'matched' : 'mismatched';
}

/**
 * An optional field (e.g. imageDigest) is only bound when the receipt carries a
 * non-null, non-empty value. When unbound, PatchMon is not required to observe
 * it, so it does not contribute to the verdict.
 */
function compareOptionalBound(
  receiptValue: string | null,
  observed: string | null,
): ReadbackFieldState {
  if (receiptValue === null || receiptValue === '') return 'unbound';
  if (observed === null) return 'unobserved';
  return observed === receiptValue ? 'matched' : 'mismatched';
}

function unverified(reason: string, receipt: ConfigReceipt): ConfigReadbackResult {
  const fields: Record<ReadbackField, ReadbackFieldState> = {
    revision: receipt.revision ? 'unobserved' : 'unbound',
    imageDigest: receipt.imageDigest ? 'unobserved' : 'unbound',
    schemaHash: receipt.schemaHash ? 'unobserved' : 'unbound',
    resolvedHash: receipt.resolvedHash ? 'unobserved' : 'unbound',
  };
  return { verdict: 'UNVERIFIABLE', matched: false, fields, reason };
}

/**
 * A container is considered configured only when PatchMon's independent readback
 * matches the resolved receipt. Convenience wrapper for the runtime gate.
 */
export function isConfigReadbackConfirmed(result: ConfigReadbackResult): boolean {
  return result.verdict === 'MATCHED' && result.matched;
}
