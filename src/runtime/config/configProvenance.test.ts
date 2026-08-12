/**
 * Configuration Provenance - core contract tests
 *
 * Covers: deterministic merge semantics (object/array/null/missing/deleted),
 * fail-closed for unknown sources & bare remote URLs, remote-binding
 * enforcement, drift invalidation, byte-identical receipt hashing, secret
 * redaction, and PatchMon readback fields.
 */
import { describe, it, expect } from 'vitest';

import {
  resolveConfigSources,
  computeResolvedHash,
  materializeReceipt,
  verifyReceipt,
  defaultPriorityFor,
  canonicalSourceOrder,
  isSafeToAdvance,
  mergeValues,
  canonicalJson,
  hashValue,
  isRedactedSecret,
  schemaHashFromFields,
  advanceDecision,
  bindConfigFingerprint,
  materializeAndBind,
  type ConfigSourceContract,
  type ResolveOptions,
} from './index';

async function sha256(s: string): Promise<string> {
  return hashValue(s);
}

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

describe('configSources - source order & priority', () => {
  it('exposes the canonical resolution order ascending by priority', () => {
    expect(canonicalSourceOrder()).toEqual([
      'compiled-defaults',
      'image-manifest',
      'deployment-config',
      'environment-projection',
      'approved-runtime-overlay',
    ]);
  });

  it('derived priorities are monotonic per kind', () => {
    expect(defaultPriorityFor('compiled-defaults')).toBeLessThan(defaultPriorityFor('image-manifest'));
    expect(defaultPriorityFor('image-manifest')).toBeLessThan(defaultPriorityFor('deployment-config'));
    expect(defaultPriorityFor('deployment-config')).toBeLessThan(defaultPriorityFor('environment-projection'));
    expect(defaultPriorityFor('environment-projection')).toBeLessThan(defaultPriorityFor('approved-runtime-overlay'));
  });
});

describe('configCanonicalize - deterministic serialization & merge', () => {
  it('produces identical JSON regardless of key order', () => {
    expect(canonicalJson({ b: 2, a: 1 })).toBe(canonicalJson({ a: 1, b: 2 }));
  });

  it('omits undefined fields', () => {
    expect(canonicalJson({ a: 1, b: undefined })).toBe(canonicalJson({ a: 1 }));
  });

  it('deep-merges objects recursively', () => {
    expect(mergeValues({ b: { x: 1 } }, { b: { y: 2 } })).toEqual({ b: { x: 1, y: 2 } });
  });

  it('replaces arrays wholesale (no element merge)', () => {
    expect(mergeValues({ arr: [1, 2] }, { arr: [3] })).toEqual({ arr: [3] });
  });

  it('null explicitly deletes a key', () => {
    expect(mergeValues({ a: 1, b: 2 }, { a: null })).toEqual({ b: 2 });
    expect('a' in mergeValues({ a: 1 }, { a: null })).toBe(false);
  });

  it('undefined / missing does not touch resolved value', () => {
    expect(mergeValues({ a: 1 }, { a: undefined })).toEqual({ a: 1 });
    expect(mergeValues({ a: 1 }, {})).toEqual({ a: 1 });
  });

  it('redacted secrets are detected and carried through', () => {
    expect(isRedactedSecret({ kind: 'secret', redactedId: 'r-1' })).toBe(true);
    expect(isRedactedSecret({ kind: 'secret' })).toBe(false);
  });

  it('schema hash is order-independent for identical field sets', () => {
    const a = schemaHashFromFields([{ name: 'a', kind: 'num' }, { name: 'b', kind: 'str' }]);
    const b = schemaHashFromFields([{ name: 'b', kind: 'str' }, { name: 'a', kind: 'num' }]);
    expect(a).toBe(b);
  });
});

// ---------------------------------------------------------------------------
// Cross-language float canonicalization parity.
//
// The Python mirror must produce byte-identical canonical JSON and sha256 for
// these floats. The expected values below are the JS- canonical output
// (Number.prototype.toString per ECMA-262 6.1.6.1.20). The mirror parity test
// re-checks the same values against the Python implementation. If JS float
// serialization ever changes, regenerate both sides together.
// ---------------------------------------------------------------------------
const JS_FLOAT_REFERENCE: ReadonlyArray<[number, string, string]> = [
  [1.0, '1', '6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b'],
  [-0.0, '0', '5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9'],
  [0.1, '0.1', '14be4b45f18e0d8c67b4f719b5144eee88497e413709d11d85b096d8e2346310'],
  [-0.1, '-0.1', 'ffe616e28103a848cc8a18531f5ba096e153b50c6d597297ad5cb69e39496f6a'],
  [100.25, '100.25', '276e984dd04dbd73c7d99e14cf02cff9fe8d1b467a04929a3770f8c7c7f0ace2'],
  [1e16, '10000000000000000', '139eb393675707818651f879828a526159209ca3ad3b2f94f9f8ec8c4fb5e610'],
  [1e20, '100000000000000000000', 'c344e9487bfbd5c4e03c9fb90d62a5dde5e00b54d55c46e9f4a803aea162b80c'],
  [1e21, '1e+21', '241c4643fa70b1dcde1205b71be4e3bebb17e9f880c8e1a33d0ead6c27271d3c'],
  [1e-7, '1e-7', '5b33e02f2c5103a05d32f6ba9cb058294452bfbf393967f68bb30c1bdcbbab22'],
  [5e-7, '5e-7', '1dbb0eeaf281e991374e0969e04ccffc84d2c820f69c056f105256cf4cc2bba0'],
  [5e-324, '5e-324', 'c46e7ca1be4c8734f373a56530787288fa2058d73d07855e9247e949f811a42a'],
  [1.7976931348623157e308, '1.7976931348623157e+308', 'c2784e1abd6317452708f3fbf9641c16b959561bc621a1d408c23a20aa2cb585'],
  [1234567.89, '1234567.89', '3b1ff895d2562d2fd5af9c6868370fb954997d8d863abd0e28bdd981b3ba6cd2'],
  [1234567890123456.0, '1234567890123456', '7a51d064a1a216a692f753fcdab276e4ff201a01d8b66f56d50d4d719fd0dc87'],
];

describe('configCanonicalize - cross-language float parity', () => {
  it.each(JS_FLOAT_REFERENCE)('serializes %f to JS-canonical string and hash', async (value, expectedStr, expectedHash) => {
    expect(canonicalJson(value)).toBe(expectedStr);
    expect(await hashValue(value)).toBe(expectedHash);
  });

  it('serializes nested float structures to JS-canonical output', async () => {
    const value = { a: 1.0, b: [1e20, 2.5, 3], c: { d: 0.1, e: 1e-7 } };
    const expected = '{"a":1,"b":[100000000000000000000,2.5,3],"c":{"d":0.1,"e":1e-7}}';
    expect(canonicalJson(value)).toBe(expected);
  });
});

describe('resolveConfigSources - success path', () => {
  it('merges sources low->high and resolves', async () => {
    const res = await resolveConfigSources(baseSources);
    expect(res.status).toBe('RESOLVED');
    expect(res.resolved).toEqual({ a: 1, b: { x: 1, y: 2 }, arr: [1, 2], c: 3 });
    expect(res.sourceHashes).toHaveLength(2);
    expect(res.errors).toEqual([]);
  });

  it('reports sourceOrder of present kinds ascending', async () => {
    const res = await resolveConfigSources(baseSources);
    expect(res.sourceOrder).toEqual(['compiled-defaults', 'deployment-config']);
  });

  it('returns schemaHash, resolvedHash and per-source hashes', async () => {
    const res = await resolveConfigSources(baseSources);
    expect(typeof res.schemaHash).toBe('string');
    expect(res.schemaHash).toBe('sch-default');
    expect(res.resolvedHash).toMatch(/^[0-9a-f]{64}$/);
    expect(res.sourceHashes[0]).toMatchObject({
      id: 'defaults',
      kind: 'compiled-defaults',
      revision: 'rev-1',
      contentHash: 'ch-defaults',
      schemaHash: 'sch-default',
      remoteOrigin: null,
      remoteDigest: null,
    });
  });
});

describe('resolveConfigSources - determinism', () => {
  it('identical input produces byte-identical resolvedHash', async () => {
    const r1 = await resolveConfigSources([...baseSources].reverse());
    const r2 = await resolveConfigSources(baseSources);
    expect(r1.resolvedHash).toBe(r2.resolvedHash);
    // resolved content equal even though input order differed
    expect(canonicalJson(r1.resolved)).toBe(canonicalJson(r2.resolved));
  });

  it('computeResolvedHash matches resolver resolvedHash for same input', async () => {
    const res = await resolveConfigSources(baseSources);
    const direct = await computeResolvedHash(baseSources);
    expect(direct).toBe(res.resolvedHash);
  });
});

describe('resolveConfigSources - fail closed', () => {
  it('rejects unknown source kinds', async () => {
    const res = await resolveConfigSources([
      src({ id: 'bad', kind: 'unknown-origin' as never, values: {} }),
    ]);
    expect(res.status).toBe('BLOCKED');
    expect(res.errors[0]).toContain('unknown source kind');
    expect(res.resolved).toEqual({});
    expect(res.resolvedHash).toBe('');
  });

  it('rejects sources missing revision/contentHash/schemaHash', async () => {
    const res = await resolveConfigSources([
      src({ id: 'x', kind: 'compiled-defaults', values: {}, revision: '' }),
    ]);
    expect(res.status).toBe('BLOCKED');
    expect(res.errors.join('|')).toContain('missing revision');
  });

  it('rejects remote sources whose origin is not pre-bound', async () => {
    const res = await resolveConfigSources([
      src({
        id: 'remote',
        kind: 'approved-runtime-overlay',
        values: { a: 9 },
        remote: { origin: 'https://untrusted.example/cfg', digest: 'd-1', signatureHash: 's-1' },
      }),
    ]);
    expect(res.status).toBe('BLOCKED');
    expect(res.errors.join('|')).toContain('remote origin not pre-bound/allowed');
  });

  it('rejects remote sources missing digest or signatureHash', async () => {
    const opts: ResolveOptions = {
      allowedRemoteOrigins: new Set(['https://trusted.example/cfg']),
    };
    const res = await resolveConfigSources(
      [
        src({
          id: 'remote',
          kind: 'approved-runtime-overlay',
          values: { a: 9 },
          remote: { origin: 'https://trusted.example/cfg', digest: '', signatureHash: 's-1' },
        }),
      ],
      opts,
    );
    expect(res.status).toBe('BLOCKED');
    expect(res.errors.join('|')).toContain('without digest');
  });

  it('accepts remote sources when origin is pre-bound and binding is complete', async () => {
    const opts: ResolveOptions = {
      allowedRemoteOrigins: new Set(['https://trusted.example/cfg']),
    };
    const res = await resolveConfigSources(
      [
        src({ id: 'defaults', kind: 'compiled-defaults', values: { a: 1 } }),
        src({
          id: 'remote',
          kind: 'approved-runtime-overlay',
          values: { a: 9 },
          remote: { origin: 'https://trusted.example/cfg', digest: 'd-1', signatureHash: 's-1' },
        }),
      ],
      opts,
    );
    expect(res.status).toBe('RESOLVED');
    expect(res.resolved).toEqual({ a: 9 });
    expect(res.sourceHashes[1]?.remoteOrigin).toBe('https://trusted.example/cfg');
    expect(res.sourceHashes[1]?.remoteDigest).toBe('d-1');
  });
});

describe('resolveConfigSources - drift invalidation', () => {
  it('content drift against expected hash yields CONTRADICTED and empty resolved', async () => {
    const res = await resolveConfigSources(baseSources, {
      expectedReceiptHash: 'deadbeef',
    });
    expect(res.status).toBe('CONTRADICTED');
    expect(res.drift?.kind).toBe('content-drift');
    expect(res.drift?.expectedHash).toBe('deadbeef');
    expect(res.drift?.actualHash).toBe(res.resolvedHash);
    expect(res.resolved).toEqual({});
    expect(isSafeToAdvance(res)).toBe(false);
  });

  it('no drift when expected hash matches resolved hash', async () => {
    const baseline = await resolveConfigSources(baseSources);
    const res = await resolveConfigSources(baseSources, {
      expectedReceiptHash: baseline.resolvedHash,
    });
    expect(res.status).toBe('RESOLVED');
    expect(res.drift).toBeNull();
    expect(isSafeToAdvance(res)).toBe(true);
  });

  it('schema disagreement across sources yields schema-drift and BLOCKED', async () => {
    const res = await resolveConfigSources([
      src({ id: 'a', kind: 'compiled-defaults', values: { a: 1 }, schemaHash: 'sch-1' }),
      src({ id: 'b', kind: 'deployment-config', values: { b: 2 }, schemaHash: 'sch-2' }),
    ]);
    expect(res.status).toBe('BLOCKED');
    expect(res.drift?.kind).toBe('schema-drift');
    expect(res.errors.join('|')).toContain('schemaHash');
  });

  it('expected schema fields mismatch yields schema-drift', async () => {
    const res = await resolveConfigSources(
      [src({ id: 'a', kind: 'compiled-defaults', values: { a: 1 }, schemaHash: 'sch-default' })],
      { schemaFields: [{ name: 'zzz', kind: 'num' }] },
    );
    expect(res.status).toBe('BLOCKED');
    expect(res.drift?.kind).toBe('schema-drift');
  });
});

describe('configReceipt - redacted, byte-identical receipts', () => {
  it('materializes a receipt with a deterministic hash for identical input', async () => {
    const res = await resolveConfigSources(baseSources);
    const r1 = await materializeReceipt(res, { revision: 'rev-1', imageDigest: 'img-1' });
    const r2 = await materializeReceipt(res, { revision: 'rev-1', imageDigest: 'img-1' });
    expect(r1.receiptHash).toBe(r2.receiptHash);
    expect(r1.receiptHash).toMatch(/^[0-9a-f]{64}$/);
  });

  it('receipts differ when bound revision/digest differ', async () => {
    const res = await resolveConfigSources(baseSources);
    const r1 = await materializeReceipt(res, { revision: 'rev-1', imageDigest: 'img-1' });
    const r2 = await materializeReceipt(res, { revision: 'rev-2', imageDigest: 'img-1' });
    expect(r1.receiptHash).not.toBe(r2.receiptHash);
  });

  it('verifyReceipt confirms integrity', async () => {
    const res = await resolveConfigSources(baseSources);
    const receipt = await materializeReceipt(res, { revision: 'rev-1' });
    expect(await verifyReceipt(receipt)).toBe(true);
  });

  it('tampered receipt fails verification', async () => {
    const res = await resolveConfigSources(baseSources);
    const receipt = await materializeReceipt(res, { revision: 'rev-1' });
    const tampered = { ...receipt, revision: 'rev-tampered' };
    expect(await verifyReceipt(tampered)).toBe(false);
  });

  it('PatchMon readback fields are present', async () => {
    const res = await resolveConfigSources(baseSources);
    const receipt = await materializeReceipt(res, {
      revision: 'rev-1',
      imageDigest: 'sha256:img-1',
    });
    expect(receipt.revision).toBe('rev-1');
    expect(receipt.imageDigest).toBe('sha256:img-1');
    expect(receipt.schemaHash).toBe(res.schemaHash);
    expect(receipt.resolvedHash).toBe(res.resolvedHash);
    expect(receipt.sourceHashes).toBe(res.sourceHashes);
  });
});

describe('configReceipt - secret redaction (negative tests)', () => {
  it('raw secret material never appears in resolved projection or receipt', async () => {
    const SECRET = 'super-secret-value-do-not-leak';
    const redactedId = await sha256(SECRET);
    const sources: ConfigSourceContract[] = [
      src({
        id: 'env',
        kind: 'environment-projection',
        values: {
          apiKey: { kind: 'secret', redactedId },
          publicSetting: 'visible',
        },
      }),
    ];
    const res = await resolveConfigSources(sources);
    expect(res.status).toBe('RESOLVED');
    const json = canonicalJson(res.resolved);
    expect(json).not.toContain(SECRET);
    expect(json).toContain('redactedId');

    const receipt = await materializeReceipt(res, { revision: 'rev-1' });
    const receiptJson = canonicalJson(receipt);
    expect(receiptJson).not.toContain(SECRET);
  });

  it('two sources with the same redacted secret identity are stable', async () => {
    const redactedId = 'r-fixed';
    const sources: ConfigSourceContract[] = [
      src({
        id: 'env',
        kind: 'environment-projection',
        values: { apiKey: { kind: 'secret', redactedId } },
      }),
      src({
        id: 'overlay',
        kind: 'approved-runtime-overlay',
        values: { apiKey: { kind: 'secret', redactedId } },
      }),
    ];
    const res = await resolveConfigSources(sources);
    expect((res.resolved as { apiKey: { redactedId: string } }).apiKey.redactedId).toBe('r-fixed');
  });
});

describe('cross-environment safety (negative tests)', () => {
  it('environment projection cannot be silently promoted by omitting higher sources', async () => {
    // Only env present: it resolves, but sourceOrder reflects it (no silent promotion claim).
    const res = await resolveConfigSources([
      src({ id: 'env', kind: 'environment-projection', values: { a: 1 } }),
    ]);
    expect(res.status).toBe('RESOLVED');
    expect(res.sourceOrder).toEqual(['environment-projection']);
  });

  it('a lower-priority value overridden by a higher-priority null is deleted', async () => {
    const res = await resolveConfigSources([
      src({ id: 'defaults', kind: 'compiled-defaults', values: { secret: 'x' } }),
      src({ id: 'overlay', kind: 'approved-runtime-overlay', values: { secret: null } }),
    ]);
    expect(res.status).toBe('RESOLVED');
    expect('secret' in res.resolved).toBe(false);
  });

  it('bare remote URL in values does not create a remote truth path', async () => {
    // A string value that looks like a URL is just data; remote binding is required for remote config.
    const res = await resolveConfigSources([
      src({ id: 'defaults', kind: 'compiled-defaults', values: { url: 'https://evil.example/cfg' } }),
    ]);
    expect(res.status).toBe('RESOLVED');
    expect((res.resolved as { url: string }).url).toBe('https://evil.example/cfg');
    // No remote readback recorded because it was not a bound remote source.
    expect(res.sourceHashes[0]?.remoteOrigin).toBeNull();
  });
});

// Runtime binding & advance gate (#1169 criteria #5 and #6). Mirrors the
// Python `backend/tests/test_configuration_runtime_integration.py` coverage
// (`test_runtime_binding_rejects_tampered_and_non_resolved_receipts` and
// `test_run_preparation_identity_is_bound_to_verified_config_fingerprint`):
// the redacted config fingerprint bound into a RunEnvelope must be byte-
// identical for the same resolved config, and config drift / a tampered or
// non-RESOLVED receipt must block advancement (fail closed) instead of
// silently continuing.
describe('runtimeBinding - redacted fingerprint & fail-closed advance gate (#1169)', () => {
  it('binds a RESOLVED receipt to a deterministic, byte-identical fingerprint', async () => {
    const res = await resolveConfigSources(baseSources);
    const r1 = await materializeReceipt(res, { revision: 'rev-1', imageDigest: 'sha256:img-1' });
    const r2 = await materializeReceipt(res, { revision: 'rev-1', imageDigest: 'sha256:img-1' });
    const b1 = await bindConfigFingerprint(r1);
    const b2 = await bindConfigFingerprint(r2);
    expect(b1.fingerprintHash).toBe(b2.fingerprintHash);
    expect(b1.fingerprintHash).toMatch(/^[0-9a-f]{64}$/);
    expect(b1.verified).toBe(true);
    expect(b1.status).toBe('RESOLVED');
    expect(b1.receiptHash).toBe(r1.receiptHash);
    expect(b1.schemaHash).toBe(res.schemaHash);
    expect(b1.resolvedHash).toBe(res.resolvedHash);
    expect(b1.driftKind).toBeNull();
  });

  it('a fingerprint bound from different resolved/digest inputs differs', async () => {
    const res = await resolveConfigSources(baseSources);
    const a = await bindConfigFingerprint(
      await materializeReceipt(res, { revision: 'rev-1', imageDigest: 'sha256:img-1' }),
    );
    const b = await bindConfigFingerprint(
      await materializeReceipt(res, { revision: 'rev-2', imageDigest: 'sha256:img-1' }),
    );
    expect(a.fingerprintHash).not.toBe(b.fingerprintHash);
  });

  it('materializeAndBind yields a self-verifying receipt and matching binding', async () => {
    const res = await resolveConfigSources(baseSources);
    const { receipt, binding } = await materializeAndBind(res, {
      revision: 'rev-1',
      imageDigest: 'sha256:img-1',
    });
    expect(await verifyReceipt(receipt)).toBe(true);
    expect(binding.verified).toBe(true);
    expect(binding.receiptHash).toBe(receipt.receiptHash);
    expect(binding.resolvedHash).toBe(res.resolvedHash);
  });

  it('bindConfigFingerprint rejects a tampered (non-self-verifying) receipt', async () => {
    const res = await resolveConfigSources(baseSources);
    const receipt = await materializeReceipt(res, { revision: 'rev-1' });
    const tampered = { ...receipt, revision: 'rev-tampered' };
    await expect(bindConfigFingerprint(tampered)).rejects.toThrow(/integrity verification/);
  });

  it('bindConfigFingerprint rejects a CONTRADICTED (drifted) receipt', async () => {
    const contradicted = await resolveConfigSources(baseSources, {
      expectedReceiptHash: '0'.repeat(64),
    });
    expect(contradicted.status).toBe('CONTRADICTED');
    const receipt = await materializeReceipt(contradicted, { revision: 'rev-1' });
    await expect(bindConfigFingerprint(receipt)).rejects.toThrow(/not RESOLVED|not advanceable/);
  });

  it('advanceDecision allows advancement only for a RESOLVED, drift-free contract', async () => {
    const res = await resolveConfigSources(baseSources);
    expect(res.status).toBe('RESOLVED');
    const decision = await advanceDecision(res);
    expect(decision.safe).toBe(true);
    expect(decision.reason).toBe('RESOLVED');
    expect(decision.driftKind).toBeNull();
  });

  it('advanceDecision blocks (fail closed) on a CONTRADICTED contract', async () => {
    const contradicted = await resolveConfigSources(baseSources, {
      expectedReceiptHash: 'deadbeef',
    });
    expect(contradicted.status).toBe('CONTRADICTED');
    const receipt = await materializeReceipt(contradicted, { revision: 'rev-1' });
    const decision = await advanceDecision(contradicted, receipt);
    expect(decision.safe).toBe(false);
    expect(decision.reason).toContain('CONFIG_CONTRADICTED');
    expect(decision.driftKind).toBe('content-drift');
  });

  it('advanceDecision blocks on a BLOCKED (schema-drift) contract', async () => {
    const blocked = await resolveConfigSources([
      src({ id: 'a', kind: 'compiled-defaults', values: { a: 1 }, schemaHash: 'sch-1' }),
      src({ id: 'b', kind: 'deployment-config', values: { b: 2 }, schemaHash: 'sch-2' }),
    ]);
    expect(blocked.status).toBe('BLOCKED');
    const decision = await advanceDecision(blocked);
    expect(decision.safe).toBe(false);
    expect(decision.reason).toContain('CONFIG_BLOCKED');
    expect(decision.driftKind).toBe('schema-drift');
  });

  it('advanceDecision blocks when a stale receipt does not match the contract', async () => {
    const res = await resolveConfigSources(baseSources);
    const otherSources = [src({ id: 'other', kind: 'compiled-defaults', values: { z: 9 } })];
    const stale = await materializeReceipt(await resolveConfigSources(otherSources), {
      revision: 'rev-stale',
    });
    const decision = await advanceDecision(res, stale);
    expect(decision.safe).toBe(false);
    expect(decision.reason).toBe('RECEIPT_MISMATCH');
  });

  it('advanceDecision blocks when the supplied receipt fails integrity verification', async () => {
    const res = await resolveConfigSources(baseSources);
    const receipt = await materializeReceipt(res, { revision: 'rev-1' });
    const tampered = { ...receipt, revision: 'rev-tampered' };
    const decision = await advanceDecision(res, tampered);
    expect(decision.safe).toBe(false);
    expect(decision.reason).toBe('RECEIPT_UNVERIFIED');
  });

  it('bindConfigFingerprint + advanceDecision agree: an advanceable config binds and advances', async () => {
    const res = await resolveConfigSources(baseSources);
    const binding = await bindConfigFingerprint(
      await materializeReceipt(res, { revision: 'rev-1', imageDigest: 'sha256:img-1' }),
    );
    const decision = await advanceDecision(res);
    expect(binding.verified).toBe(true);
    expect(decision.safe).toBe(true);
    // The fingerprint carries the same redacted resolved hash the gate advanced on.
    expect(binding.resolvedHash).toBe(res.resolvedHash);
  });
});

// Cross-language parity: identical input must produce byte-identical canonical
// JSON and sha256 hash in both the TypeScript and Python implementations.
// Python reference values were produced from the canonical backend package
// (backend/agent_runtime/configuration/config_canonicalize.py) using the exact
// same input shape. If either side changes serialization, this test fails and
// provenance parity is broken.
describe('cross-language hash parity (TS vs Python)', () => {
  const parityInput = {
    a: 1,
    b: { x: 1, y: 2 },
    arr: [1, 2],
    c: 3,
    apiKey: { kind: 'secret', redactedId: 'r-1' },
  };

  it('produces the Python-reference canonical JSON byte-for-byte', () => {
    const expected =
      '{"a":1,"apiKey":{"kind":"secret","redactedId":"r-1"},"arr":[1,2],"b":{"x":1,"y":2},"c":3}';
    expect(canonicalJson(parityInput)).toBe(expected);
  });

  it('produces the Python-reference sha256 hash', async () => {
    // sha256 of the canonical JSON above, hex lowercase.
    const expected = '490e12734026df474ee4de8ce1d5d891cf1e702b14f038ca4174ddd64ed6731c';
    expect(await hashValue(parityInput)).toBe(expected);
  });
});
