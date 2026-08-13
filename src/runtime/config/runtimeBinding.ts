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

/**
 * Verdict on whether a previously-bound run/permission binding remains valid
 * against the current resolution contract. Drift, status downgrade, errors or
 * an identity mismatch mean the binding no longer reflects live runtime
 * configuration and must be treated as invalidated (#1169 criterion #5).
 */
export interface BindingLivenessDecision {
  readonly valid: boolean;
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
 * Project only an advanceable receipt into the RunEnvelope fingerprint.
 * Unverified, non-RESOLVED, drifted, or error-bearing receipts fail closed
 * before a run binding can be created.
 */
export async function bindConfigFingerprint(
  receipt: ConfigReceipt,
): Promise<ConfigFingerprintBinding> {
  if (!(await verifyReceipt(receipt))) {
    throw new Error('config receipt failed integrity verification');
  }
  if (receipt.status !== 'RESOLVED') {
    throw new Error(`config receipt is not RESOLVED: ${receipt.status}`);
  }
  if (receipt.drift !== null || receipt.errors.length > 0) {
    throw new Error('config receipt is not advanceable');
  }
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
 * Fail-closed liveness gate for a previously-bound run/permission binding.
 *
 * A binding created from an earlier resolution remains valid only while the
 * live contract is still `RESOLVED` with no drift, no errors, and the same
 * resolved/schema identity the binding was minted from. Any drift, status
 * downgrade, error, or identity mismatch invalidates the binding so the stale
 * run/permission grant is no longer authoritative (#1169 criterion #5).
 *
 * The verdict mirrors `advanceDecision` for the drift/status/error cases so a
 * binding can never stay valid for a contract that would not be allowed to
 * advance in the first place.
 */
export async function bindingLiveness(
  binding: ConfigFingerprintBinding,
  contract: ConfigResolutionContract,
): Promise<BindingLivenessDecision> {
  const driftKind = contract.drift?.kind ?? null;

  if (contract.status === 'CONTRADICTED') {
    return { valid: false, reason: `BINDING_CONTRADICTED:${driftKind ?? 'content-drift'}`, status: contract.status, driftKind };
  }
  if (contract.status === 'BLOCKED') {
    return { valid: false, reason: `BINDING_BLOCKED:${driftKind ?? 'resolution-error'}`, status: contract.status, driftKind };
  }
  if (contract.status === 'DEGRADED') {
    return { valid: false, reason: `BINDING_DEGRADED:${driftKind ?? 'degraded'}`, status: contract.status, driftKind };
  }
  if (contract.errors.length > 0) {
    return { valid: false, reason: `BINDING_ERRORS:${contract.errors.length}`, status: contract.status, driftKind };
  }
  if (contract.drift !== null) {
    return { valid: false, reason: `BINDING_DRIFT:${driftKind ?? 'unknown'}`, status: contract.status, driftKind };
  }
  if (contract.status !== 'RESOLVED') {
    return { valid: false, reason: `BINDING_NOT_RESOLVED:${contract.status}`, status: contract.status, driftKind };
  }

  if (binding.resolvedHash !== contract.resolvedHash) {
    return { valid: false, reason: 'BINDING_RESOLVED_HASH_MISMATCH', status: contract.status, driftKind };
  }
  if (binding.schemaHash !== contract.schemaHash) {
    return { valid: false, reason: 'BINDING_SCHEMA_HASH_MISMATCH', status: contract.status, driftKind };
  }

  return { valid: true, reason: 'RESOLVED', status: contract.status, driftKind: null };
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
