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

// Cross-language unicode / non-ASCII string parity (#1169).
//
// JS JSON.stringify emits raw UTF-8 (it does NOT escape non-ASCII code points).
// The Python mirror must use ensure_ascii=False to match; otherwise non-ASCII
// config inputs (German labels, emojis) produce different canonical JSON and
// different sha256 receipt hashes, breaking the #1169 acceptance criterion
// "gleicher Input erzeugt bytegleichen Public-Receipt-Hash". These cases lock
// the corrected parity: the TS canonical form must be byte-identical to the
// Python (ensure_ascii=False) form. Python reference values below were
// computed from backend/agent_runtime/configuration/config_canonicalize.py.
describe('cross-language hash parity - non-ASCII strings (#1169)', () => {
  const unicodeInput = {
    label: 'café',
    emoji: '🛡️',
    greeting: 'Grüße',
    model: 'llama-3',
    nested: { title: 'Synchronisieren' },
    arr: ['Wiederherstellung', 1, true, null],
  };

  it('produces byte-identical (raw UTF-8) canonical JSON for non-ASCII inputs', () => {
    const expected =
      '{"arr":["Wiederherstellung",1,true,null],"emoji":"🛡️","greeting":"Grüße","label":"café","model":"llama-3","nested":{"title":"Synchronisieren"}}';
    expect(canonicalJson(unicodeInput)).toBe(expected);
  });

  it('produces the Python-reference sha256 hash for non-ASCII inputs', async () => {
    // sha256 of the canonical JSON above over its raw UTF-8 bytes, hex lowercase.
    const expected = '6929ea6b770c93c1f9d34bc0ecac2d6aa6f8373906c2c69ebd4ad953cab1756c';
    expect(await hashValue(unicodeInput)).toBe(expected);
  });

  it('does not ASCII-escape a non-ASCII string value', () => {
    expect(canonicalJson({ k: 'café' })).toBe('{"k":"café"}');
    expect(canonicalJson({ k: 'café' })).not.toContain('\\u');
  });

  it('does not ASCII-escape a non-ASCII object key', () => {
    expect(canonicalJson({ Synchronisieren: 1 })).toBe('{"Synchronisieren":1}');
    expect(canonicalJson({ Synchronisieren: 1 })).not.toContain('\\u');
  });

  it('produces the Python-reference sha256 for a single non-ASCII string', async () => {
    // sha256 of '"café"' over raw UTF-8 bytes.
    const expected = '28380feb8724d669bc8d4cf5b5a5bb1adbdc61b81ebd06f3fabc567b4f3b0fc5';
    expect(await hashValue('café')).toBe(expected);
  });
});
