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
import type { ConfigReceipt, ConfigReadbackObservation } from './configReceipt';
import { hashValue } from './configCanonicalize';
import { materializeReceipt, verifyReceipt, verifyConfigReadback } from './configReceipt';

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
 * Project only an advanceable receipt into the RunEnvelope fingerprint.
 * Unverified, non-RESOLVED, drifted, or error-bearing receipts fail closed
 * before a run binding can be created.
 *
 * When a PatchMon `readback` observation is supplied, the bound receipt must
 * additionally pass `verifyConfigReadback`: RunEnvelope and PatchMon must read
 * back the same redacted config fingerprint (#1169 DoD). A rejected readback
 * fails closed with the readback finding code rather than producing a binding.
 */
export async function bindConfigFingerprint(
  receipt: ConfigReceipt,
  options: { readback?: ConfigReadbackObservation } = {},
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
  if (options.readback !== undefined) {
    const audit = await verifyConfigReadback(receipt, options.readback);
    if (!audit.accepted) {
      throw new Error(`config readback rejected: ${audit.blocker}`);
    }
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
  options: { readback?: ConfigReadbackObservation } = {},
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

  if (options.readback !== undefined) {
    const advanceableReceipt = receipt ?? null;
    if (advanceableReceipt === null) {
      return { safe: false, reason: 'READBACK_NO_RECEIPT', status: contract.status, driftKind };
    }
    const audit = await verifyConfigReadback(advanceableReceipt, options.readback);
    if (!audit.accepted) {
      return { safe: false, reason: audit.blocker ?? 'READBACK_REJECTED', status: contract.status, driftKind };
    }
  }

  return { safe: true, reason: 'RESOLVED', status: contract.status, driftKind: null };
}

/**
 * Convenience: materialize a redacted receipt and bind its fingerprint.
 *
 * When a PatchMon `readback` observation is supplied, the bound receipt must
 * additionally pass `verifyConfigReadback` before the fingerprint is bound,
 * enforcing the #1169 readback contract at the live binding path.
 */
export async function materializeAndBind(
  contract: ConfigResolutionContract,
  options: { revision?: string; imageDigest?: string; materializedAt?: string; readback?: ConfigReadbackObservation } = {},
): Promise<{ receipt: ConfigReceipt; binding: ConfigFingerprintBinding }> {
  const { readback, ...receiptOptions } = options;
  const receipt = await materializeReceipt(contract, receiptOptions);
  const binding = await bindConfigFingerprint(receipt, { readback });
  return { receipt, binding };
}
