/**
 * Cross-language PatchMon readback parity - golden vector (issue #1169).
 *
 * Acceptance criterion #6: "PatchMon bestätigt die wirklich geladene
 * Config-Projektion; TS und Python müssen byteidentische Fail-Closed-
 * Readback-Entscheidungen treffen." The existing parity tests lock the
 * assembled receipt hash; this module guards the **readback audit** that
 * consumes that receipt.
 *
 * It loads a single shared golden fixture
 * (`backend/tests/fixtures/config_provenance_readback_parity.v1.json`), runs
 * the full `resolveConfigSources -> materializeReceipt` live path to build a
 * real `ConfigReceipt`, asserts the materialized receipt hash equals the
 * frozen golden (cross-language lock, same value as the receipt-hash parity
 * fixture), then feeds each frozen PatchMon observation to
 * `verifyConfigReadback` and asserts the frozen audit outcome
 * (`accepted` / `blocker` / `contradicted`).
 *
 * The same fixture is consumed by the Python test
 * `test_configuration_readback_parity.py`, so any divergence in the readback
 * audit reason codes between TypeScript and Python breaks the gate on the
 * offending side. No production logic is copied here; the live
 * `verifyConfigReadback` implementation is exercised directly.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve as resolvePath } from 'node:path';

import {
  resolveConfigSources,
  materializeReceipt,
  type ConfigSourceContract,
  type ConfigReceipt,
  type ConfigReadbackObservation,
  type ConfigReadbackAudit,
} from './index';
import { verifyConfigReadback } from './configReceipt';

const FIXTURE_PATH = resolvePath(
  __dirname,
  '../../../backend/tests/fixtures/config_provenance_readback_parity.v1.json',
);

interface ReadbackFixture {
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
  };
  scenarios: Array<{
    name: string;
    description: string;
    observation: ConfigReadbackObservation;
    expected: {
      accepted: boolean;
      blocker: string | null;
      contradicted: boolean;
    };
  }>;
}

function loadFixture(): ReadbackFixture {
  return JSON.parse(readFileSync(FIXTURE_PATH, 'utf-8')) as ReadbackFixture;
}

function buildSources(fixture: ReadbackFixture): ConfigSourceContract[] {
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

async function materializeGoldenReceipt(
  fixture: ReadbackFixture,
): Promise<ConfigReceipt> {
  const contract = await resolveConfigSources(
    buildSources(fixture),
    { schemaFields: fixture.options.schemaFields },
  );
  return materializeReceipt(contract, {
    revision: fixture.options.revision,
    imageDigest: fixture.options.imageDigest,
  });
}

describe('cross-language PatchMon readback parity - golden vector (#1169)', () => {
  it('materializes the golden resolved/receipt hash before readback', async () => {
    const fixture = loadFixture();
    const receipt = await materializeGoldenReceipt(fixture);
    expect(receipt.status).toBe(fixture.expected.status);
    expect(receipt.resolvedHash).toBe(fixture.expected.resolved_hash);
    expect(receipt.receiptHash).toBe(fixture.expected.receipt_hash);
  });

  for (const scenario of loadFixture().scenarios) {
    it(`readback audit: ${scenario.name} -> accepted=${scenario.expected.accepted} blocker=${scenario.expected.blocker ?? 'null'}`, async () => {
      const fixture = loadFixture();
      const receipt = await materializeGoldenReceipt(fixture);
      // Cross-language lock: the audit must run against the frozen receipt.
      expect(receipt.receiptHash).toBe(fixture.expected.receipt_hash);

      const audit: ConfigReadbackAudit = await verifyConfigReadback(
        receipt,
        scenario.observation,
      );
      expect(audit.accepted).toBe(scenario.expected.accepted);
      expect(audit.blocker).toBe(scenario.expected.blocker);
      expect(audit.contradicted).toBe(scenario.expected.contradicted);
    });
  }
});
