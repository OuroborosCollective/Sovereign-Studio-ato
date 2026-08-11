/**
 * Cross-language configuration provenance parity - end-to-end golden vector
 * (issue #1169).
 *
 * Acceptance criterion: "gleicher Input erzeugt bytegleichen
 * Public-Receipt-Hash". The existing parity tests in `configProvenance.test.ts`
 * lock the primitive serializers (`canonicalJson` / `hashValue`) against
 * Python reference values. This module guards the **assembled** contract: it
 * loads a single shared golden fixture
 * (`backend/tests/fixtures/config_provenance_parity.v1.json`), runs the full
 * `resolveConfigSources -> materializeReceipt` pipeline against it, and asserts
 * that the TypeScript implementation produces the byte-identical
 * `resolvedHash` and `receiptHash` frozen in that fixture.
 *
 * The same fixture is consumed by the Python test
 * `test_configuration_provenance_parity.py`, so any serialization divergence
 * on either side breaks both gates. The fixture is the single source of truth;
 * both language tests read the same inputs and the same expected hashes.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve as resolvePath } from 'node:path';

import {
  resolveConfigSources,
  materializeReceipt,
  type ConfigSourceContract,
  type ResolveOptions,
} from './index';

const FIXTURE_PATH = resolvePath(
  __dirname,
  '../../../backend/tests/fixtures/config_provenance_parity.v1.json',
);

interface ParityFixture {
  sources: Array<{
    id: string;
    kind: string;
    revision: string;
    content_hash: string;
    schema_hash: string;
    priority: number;
    values: unknown;
  }>;
  options: {
    schemaFields: Array<{ name: string; kind: string }>;
    revision: string;
    imageDigest: string;
  };
  expected: {
    status: string;
    resolved_hash: string;
    receipt_hash: string;
    resolved: unknown;
  };
  parity_verified: {
    python_resolved_hash: string;
    typescript_resolved_hash: string;
    python_receipt_hash: string;
    typescript_receipt_hash: string;
    identical: boolean;
  };
}

function loadFixture(): ParityFixture {
  return JSON.parse(readFileSync(FIXTURE_PATH, 'utf-8')) as ParityFixture;
}

function buildSources(fixture: ParityFixture): ConfigSourceContract[] {
  return fixture.sources.map((s) => ({
    id: s.id,
    kind: s.kind as ConfigSourceContract['kind'],
    revision: s.revision,
    contentHash: s.content_hash,
    schemaHash: s.schema_hash,
    priority: s.priority,
    values: s.values as Record<string, unknown>,
  }));
}

function resolveOptions(fixture: ParityFixture): ResolveOptions {
  return { schemaFields: fixture.options.schemaFields };
}

describe('cross-language config provenance parity - golden vector (#1169)', () => {
  it('produces the golden resolvedHash', async () => {
    const fixture = loadFixture();
    const contract = await resolveConfigSources(buildSources(fixture), resolveOptions(fixture));
    expect(contract.status).toBe(fixture.expected.status);
    expect(contract.resolvedHash).toBe(fixture.expected.resolved_hash);
  });

  it('produces the golden receiptHash', async () => {
    const fixture = loadFixture();
    const contract = await resolveConfigSources(buildSources(fixture), resolveOptions(fixture));
    const receipt = await materializeReceipt(contract, {
      revision: fixture.options.revision,
      imageDigest: fixture.options.imageDigest,
    });
    expect(receipt.receiptHash).toBe(fixture.expected.receipt_hash);
  });

  it('produces the golden resolved values', async () => {
    const fixture = loadFixture();
    const contract = await resolveConfigSources(buildSources(fixture), resolveOptions(fixture));
    expect(contract.resolved).toEqual(fixture.expected.resolved);
  });

  it('fixture self-documents verified parity', () => {
    const fixture = loadFixture();
    const proof = fixture.parity_verified;
    expect(proof.identical).toBe(true);
    expect(proof.python_resolved_hash).toBe(proof.typescript_resolved_hash);
    expect(proof.python_receipt_hash).toBe(proof.typescript_receipt_hash);
    expect(proof.python_resolved_hash).toBe(fixture.expected.resolved_hash);
    expect(proof.python_receipt_hash).toBe(fixture.expected.receipt_hash);
  });
});
