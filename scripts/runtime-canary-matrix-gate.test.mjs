import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

import {
  DEFAULT_MATRIX_PATH,
  EVIDENCE_SCHEMA,
  canonicalSha256,
  resolveRepositoryPath,
  runGate,
  validateMatrix,
} from './runtime-canary-matrix-gate.mjs';

const matrix = JSON.parse(fs.readFileSync(DEFAULT_MATRIX_PATH, 'utf8'));
const revision = 'b'.repeat(40);

function completeReceipt(surface) {
  const receipt = {
    surface: surface.surface,
    revision,
    workflowRunId: `run-${surface.surface}`,
    status: 'passed',
    evidenceSha256: 'a'.repeat(64),
  };
  for (const field of surface.evidenceFields) {
    if (!(field in receipt)) receipt[field] = `verified-${field}`;
  }
  if (surface.liveCanary.mutates) receipt.cleanupStatus = 'passed';
  if (surface.ownerGate) receipt.ownerGateStatus = 'approved';
  if (surface.liveCanary.externalCost) receipt.budgetGateStatus = 'passed';
  return receipt;
}

test('canonical matrix passes the contract gate', () => {
  assert.deepEqual(validateMatrix(matrix), []);
  const report = runGate({ matrix, revision, mode: 'contract' });
  assert.equal(report.status, 'pass');
  assert.equal(report.surfaceCount, 18);
  assert.equal(report.requiredLiveCanaryCount, 16);
  assert.equal(report.excludedLiveCanaryCount, 2);
  assert.deepEqual(report.families, ['backend', 'client', 'integration', 'release', 'storage', 'tool']);
});

test('duplicate surfaces and missing cleanup fail closed', () => {
  const broken = structuredClone(matrix);
  broken.surfaces[1].surface = broken.surfaces[0].surface;
  broken.surfaces[3].liveCanary.cleanup = 'none';
  const errors = validateMatrix(broken);
  assert.ok(errors.some((error) => error.message.includes('Duplicate surface')));
  assert.ok(errors.some((error) => error.message.includes('explicit cleanup')));
});

test('release mode rejects missing live evidence', () => {
  const evidence = {
    schemaVersion: EVIDENCE_SCHEMA,
    revision,
    matrixSha256: canonicalSha256(matrix),
    receipts: [],
  };
  const report = runGate({ matrix, evidence, revision, mode: 'release' });
  assert.equal(report.status, 'fail');
  assert.ok(report.errors.some((error) => error.message === 'Missing required live-canary receipt.'));
});

test('release mode accepts one complete passed receipt per required surface', () => {
  const evidence = {
    schemaVersion: EVIDENCE_SCHEMA,
    revision,
    matrixSha256: canonicalSha256(matrix),
    receipts: matrix.surfaces
      .filter((surface) => surface.liveCanary.policy === 'required')
      .map(completeReceipt),
  };
  const report = runGate({ matrix, evidence, revision, mode: 'release' });
  assert.equal(report.status, 'pass');
  assert.deepEqual(report.errors, []);
});

test('repository paths cannot escape the checkout root', () => {
  assert.throws(() => resolveRepositoryPath('../outside.json'), /escapes repository root/);
});
