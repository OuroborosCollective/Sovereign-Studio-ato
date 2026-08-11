/**
 * Configuration Provenance - runtime binding & advance-gate tests.
 *
 * Mirrors `backend/tests/test_configuration_provenance_runtime_binding.py`.
 */
import { describe, it, expect } from 'vitest';

import {
  resolveConfigSources,
  materializeReceipt,
  materializeAndBind,
  bindConfigFingerprint,
  advanceDecision,
  verifyReceipt,
  isSafeToAdvance,
  defaultPriorityFor,
  type ConfigSourceContract,
} from './index';

function src(
  overrides: Partial<ConfigSourceContract> & Pick<ConfigSourceContract, 'id' | 'kind' | 'values'>,
): ConfigSourceContract {
  return {
    revision: overrides.revision ?? 'rev-1',
    contentHash: overrides.contentHash ?? 'ch-' + overrides.id,
    schemaHash: overrides.schemaHash ?? 'sch-default',
    priority: overrides.priority ?? defaultPriorityFor(overrides.kind),
    values: overrides.values,
    ...overrides,
  } as ConfigSourceContract;
}

const baseSources: ConfigSourceContract[] = [
  src({ id: 'defaults', kind: 'compiled-defaults', values: { a: 1, b: { x: 1 }, arr: [1, 2] } }),
  src({ id: 'deploy', kind: 'deployment-config', values: { b: { y: 2 }, c: 3 } }),
];

describe('runtimeBinding - bindConfigFingerprint', () => {
  it('is byte-identical for the same input', async () => {
    const res = await resolveConfigSources(baseSources);
    const { binding: a } = await materializeAndBind(res, { revision: 'rev-1', imageDigest: 'img-1' });
    const receipt = await materializeReceipt(res, { revision: 'rev-1', imageDigest: 'img-1' });
    const b = await bindConfigFingerprint(receipt);
    expect(a.fingerprintHash).toBe(b.fingerprintHash);
    expect(a.fingerprintHash).not.toBe('');
  });

  it('changes when bound revision or image digest change', async () => {
    const res = await resolveConfigSources(baseSources);
    const { binding: a } = await materializeAndBind(res, { revision: 'rev-1', imageDigest: 'img-1' });
    const { binding: b } = await materializeAndBind(res, { revision: 'rev-2', imageDigest: 'img-1' });
    const { binding: c } = await materializeAndBind(res, { revision: 'rev-1', imageDigest: 'img-2' });
    expect(a.fingerprintHash).not.toBe(b.fingerprintHash);
    expect(a.fingerprintHash).not.toBe(c.fingerprintHash);
  });

  it('exposes PatchMon readback fields', async () => {
    const res = await resolveConfigSources(baseSources);
    const { receipt, binding } = await materializeAndBind(res, {
      revision: 'rev-1',
      imageDigest: 'sha256:img-1',
    });
    expect(binding.version).not.toBe('');
    expect(binding.status).toBe('RESOLVED');
    expect(binding.verified).toBe(true);
    expect(binding.receiptHash).toBe(receipt.receiptHash);
    expect(binding.schemaHash).toBe(res.schemaHash);
    expect(binding.resolvedHash).toBe(res.resolvedHash);
    expect(binding.revision).toBe('rev-1');
    expect(binding.imageDigest).toBe('sha256:img-1');
    expect(binding.driftKind).toBeNull();
  });

  it('never carries raw secret material', async () => {
    const secret = 'super-secret-value-do-not-leak';
    const redactedId = 'a'.repeat(64); // synthetic, not derived from the secret
    const res = await resolveConfigSources([
      src({
        id: 'env',
        kind: 'environment-projection',
        values: { apiKey: { kind: 'secret', redactedId }, public: 'visible' },
      }),
    ]);
    expect(res.status).toBe('RESOLVED');
    const { binding } = await materializeAndBind(res, { revision: 'rev-1' });
    const serialized = JSON.stringify(binding);
    expect(serialized).not.toContain(secret);
    expect(serialized).not.toContain(redactedId);
  });

  it('fails closed on a tampered receipt', async () => {
    const res = await resolveConfigSources(baseSources);
    const receipt = await materializeReceipt(res, { revision: 'rev-1' });
    const tampered = { ...receipt, revision: 'rev-tampered' };
    const binding = await bindConfigFingerprint(tampered);
    expect(binding.verified).toBe(false);
  });
});

describe('runtimeBinding - advanceDecision (fail-closed drift gate)', () => {
  it('advances a RESOLVED contract', async () => {
    const res = await resolveConfigSources(baseSources);
    const decision = await advanceDecision(res);
    expect(decision.safe).toBe(true);
    expect(decision.reason).toBe('RESOLVED');
  });

  it('blocks CONTRADICTED with drift kind', async () => {
    const res = await resolveConfigSources(baseSources, { expectedReceiptHash: 'deadbeef' });
    expect(res.status).toBe('CONTRADICTED');
    const decision = await advanceDecision(res);
    expect(decision.safe).toBe(false);
    expect(decision.reason.startsWith('CONFIG_CONTRADICTED:')).toBe(true);
    expect(decision.driftKind).toBe('content-drift');
  });

  it('blocks BLOCKED schema drift', async () => {
    const res = await resolveConfigSources([
      src({ id: 'a', kind: 'compiled-defaults', values: { a: 1 }, schemaHash: 'sch-1' }),
      src({ id: 'b', kind: 'deployment-config', values: { b: 2 }, schemaHash: 'sch-2' }),
    ]);
    expect(res.status).toBe('BLOCKED');
    const decision = await advanceDecision(res);
    expect(decision.safe).toBe(false);
    expect(decision.reason.startsWith('CONFIG_BLOCKED:')).toBe(true);
    expect(decision.driftKind).toBe('schema-drift');
  });

  it('blocks an unverifiable receipt', async () => {
    const res = await resolveConfigSources(baseSources);
    const receipt = await materializeReceipt(res, { revision: 'rev-1' });
    const tampered = { ...receipt, revision: 'rev-tampered' };
    const decision = await advanceDecision(res, tampered);
    expect(decision.safe).toBe(false);
    expect(decision.reason).toBe('RECEIPT_UNVERIFIED');
  });

  it('blocks a stale receipt mismatch', async () => {
    const baseline = await resolveConfigSources(baseSources);
    const receipt = await materializeReceipt(baseline, { revision: 'rev-1' });
    const other = await resolveConfigSources([
      src({ id: 'defaults', kind: 'compiled-defaults', values: { a: 999 } }),
    ]);
    expect(other.resolvedHash).not.toBe(baseline.resolvedHash);
    expect(other.status).toBe('RESOLVED');
    const decision = await advanceDecision(other, receipt);
    expect(decision.safe).toBe(false);
    expect(decision.reason).toBe('RECEIPT_MISMATCH');
  });

  it('is safe with a matching receipt', async () => {
    const res = await resolveConfigSources(baseSources);
    const receipt = await materializeReceipt(res, { revision: 'rev-1' });
    expect(await verifyReceipt(receipt)).toBe(true);
    const decision = await advanceDecision(res, receipt);
    expect(decision.safe).toBe(true);
    expect(decision.reason).toBe('RESOLVED');
  });

  it('agrees with isSafeToAdvance on the status axis', async () => {
    const res = await resolveConfigSources(baseSources);
    expect((await advanceDecision(res)).safe).toBe(isSafeToAdvance(res));
    const blocked = await resolveConfigSources([
      src({ id: 'a', kind: 'compiled-defaults', values: { a: 1 }, schemaHash: 'sch-1' }),
      src({ id: 'b', kind: 'deployment-config', values: { b: 2 }, schemaHash: 'sch-2' }),
    ]);
    expect((await advanceDecision(blocked)).safe).toBe(isSafeToAdvance(blocked));
  });

  it('blocks when a bound receipt status is not RESOLVED', async () => {
    const blocked = await resolveConfigSources([
      src({ id: 'a', kind: 'compiled-defaults', values: { a: 1 }, schemaHash: 'sch-1' }),
      src({ id: 'b', kind: 'deployment-config', values: { b: 2 }, schemaHash: 'sch-2' }),
    ]);
    expect(blocked.status).toBe('BLOCKED');
    const blockedReceipt = await materializeReceipt(blocked, { revision: 'rev-1' });
    expect(await verifyReceipt(blockedReceipt)).toBe(true);
    const resolved = await resolveConfigSources(baseSources);
    expect(resolved.status).toBe('RESOLVED');
    const decision = await advanceDecision(resolved, blockedReceipt);
    expect(decision.safe).toBe(false);
    expect(decision.reason).toBe('RECEIPT_STATUS:BLOCKED');
  });
});
