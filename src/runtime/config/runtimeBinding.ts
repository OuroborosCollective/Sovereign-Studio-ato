/**
 * Configuration Provenance - runtime binding & advance gate.
 *
 * Mirrors ``backend/agent_runtime/configuration/runtime_binding.py``.
 *
 * Integration seam between the read-only configuration provenance layer and
 * the runtime's advancement / RunEnvelope contracts:
 *
 * - `bindConfigFingerprint` projects a resolved, redacted receipt into the
 *   single canonical `ConfigFingerprintBinding` that the RunEnvelope (#1116)
 *   binds and PatchMon reads back. The same resolved configuration always
 *   produces the same `fingerprintHash` (byte-identical). Receipts that fail
 *   integrity verification bind as unverified and fail closed.
 *
 * - `advanceDecision` is the fail-closed drift gate for new mutations and
 *   active action plans. Only a `RESOLVED` contract with no drift, no errors
 *   and an integrity-verified receipt may advance. `CONTRADICTED` / `BLOCKED`
 *   / `DEGRADED` resolutions, or an unverifiable / mismatched receipt, block
 *   advancement with an explicit, machine-checkable reason.
 *
 * Mutation of configuration runs through #1119; this module performs
 * read-only projection and gating only - it never persists state or calls a
 * target system.
 *
 * @module runtime/config/runtimeBinding
 */

import type { ConfigResolutionContract } from './configSources';
import type { ConfigReceipt } from './configReceipt';
import { hashValue } from './configCanonicalize';
import { materializeReceipt, verifyReceipt } from './configReceipt';

const FINGERPRINT_VERSION = 'sovereign.config.fingerprint.v1';

/** Redacted config fingerprint bound into RunEnvelope and read by PatchMon. */
export interface ConfigFingerprintBinding {
  readonly fingerprintHash: string;
  readonly version: string;
  readonly status: ConfigResolutionContract['status'];
  readonly verified: boolean;
  readonly receiptHash: string;
  readonly schemaHash: string;
  readonly resolvedHash: string;
  readonly revision: string | null;
  readonly imageDigest: string | null;
  readonly driftKind: string | null;
}

/** Fail-closed advancement verdict for mutations and active action plans. */
export interface AdvanceDecision {
  readonly safe: boolean;
  readonly reason: string;
  readonly status: ConfigResolutionContract['status'];
  readonly driftKind: string | null;
}

interface BindingBody {
  readonly version: string;
  readonly status: ConfigResolutionContract['status'];
  readonly verified: boolean;
  readonly receiptHash: string;
  readonly schemaHash: string;
  readonly resolvedHash: string;
  readonly revision: string | null;
  readonly imageDigest: string | null;
  readonly driftKind: string | null;
}

async function bindingBody(receipt: ConfigReceipt): Promise<BindingBody> {
  return {
    version: FINGERPRINT_VERSION,
    status: receipt.status,
    verified: await verifyReceipt(receipt),
    receiptHash: receipt.receiptHash,
    schemaHash: receipt.schemaHash,
    resolvedHash: receipt.resolvedHash,
    revision: receipt.revision,
    imageDigest: receipt.imageDigest,
    driftKind: receipt.drift?.kind ?? null,
  };
}

/**
 * Project a redacted receipt into the RunEnvelope / PatchMon fingerprint.
 * Fail-closed: a receipt that fails integrity verification is bound as
 * unverified (its `fingerprintHash` still reflects the tampered body, so
 * tampering is detectable, but `verified` is false).
 */
export async function bindConfigFingerprint(
  receipt: ConfigReceipt,
): Promise<ConfigFingerprintBinding> {
  const body = await bindingBody(receipt);
  const fingerprintHash = await hashValue(body);
  return { fingerprintHash, ...body };
}

/**
 * Fail-closed drift gate for new mutations and active action plans.
 *
 * Returns `safe === true` only when the contract is `RESOLVED` with no drift
 * and no errors, AND the supplied receipt (if any) passes integrity
 * verification and matches the contract. Any drift, error, status downgrade
 * or receipt mismatch blocks advancement with an explicit reason.
 */
export async function advanceDecision(
  contract: ConfigResolutionContract,
  receipt?: ConfigReceipt | null,
): Promise<AdvanceDecision> {
  const driftKind = contract.drift?.kind ?? null;

  if (contract.status === 'CONTRADICTED') {
    return { safe: false, reason: `CONFIG_CONTRADICTED:${driftKind ?? 'content-drift'}`, status: contract.status, driftKind };
  }
  if (contract.status === 'BLOCKED') {
    return { safe: false, reason: `CONFIG_BLOCKED:${driftKind ?? 'resolution-error'}`, status: contract.status, driftKind };
  }
  if (contract.status === 'DEGRADED') {
    return { safe: false, reason: `CONFIG_DEGRADED:${driftKind ?? 'degraded'}`, status: contract.status, driftKind };
  }
  if (contract.errors.length > 0) {
    return { safe: false, reason: `CONFIG_ERRORS:${contract.errors.length}`, status: contract.status, driftKind };
  }
  if (contract.drift !== null) {
    return { safe: false, reason: `CONFIG_DRIFT:${driftKind ?? 'unknown'}`, status: contract.status, driftKind };
  }
  if (contract.status !== 'RESOLVED') {
    return { safe: false, reason: `CONFIG_NOT_RESOLVED:${contract.status}`, status: contract.status, driftKind };
  }

  if (receipt) {
    if (!(await verifyReceipt(receipt))) {
      return { safe: false, reason: 'RECEIPT_UNVERIFIED', status: contract.status, driftKind };
    }
    if (receipt.status !== 'RESOLVED') {
      return { safe: false, reason: `RECEIPT_STATUS:${receipt.status}`, status: contract.status, driftKind };
    }
    // A stale receipt materialized from a different contract must not
    // authorize advancement of this contract's mutations/action plans.
    if (receipt.resolvedHash !== contract.resolvedHash) {
      return { safe: false, reason: 'RECEIPT_MISMATCH', status: contract.status, driftKind };
    }
  }

  return { safe: true, reason: 'RESOLVED', status: contract.status, driftKind: null };
}

/**
 * Convenience: materialize a redacted receipt and bind its fingerprint.
 */
export async function materializeAndBind(
  contract: ConfigResolutionContract,
  options: { revision?: string; imageDigest?: string; materializedAt?: string } = {},
): Promise<{ receipt: ConfigReceipt; binding: ConfigFingerprintBinding }> {
  const receipt = await materializeReceipt(contract, options);
  const binding = await bindConfigFingerprint(receipt);
  return { receipt, binding };
}
