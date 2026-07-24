// @vitest-environment node
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { test } from 'vitest';

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

const COMPLETE_EVIDENCE_FIXTURE = Object.freeze({
  revision,
  workflowRunId: 'run-fixture',
  status: 'passed',
  evidenceSha256: 'a'.repeat(64),
  checkedOutHead: revision,
  artifactSha256: 'c'.repeat(64),
  mainPathStatus: 'passed',
  signerFingerprint: 'fixture-signer-fingerprint',
  negativeCases: 3,
  stateUnchanged: true,
  cleanupStatus: 'passed',
  usageId: 'usage-fixture',
  providerCostMicros: 0,
  chargedCostMicros: 0,
  creditDeltaMicros: 0,
  routeAlias: 'fixture-route',
  providerModel: 'fixture-model',
  quotaStatus: 'available',
  priceVerified: true,
  runId: 'run-fixture',
  taskId: 'task-fixture',
  controllerCorrelation: 'matched',
  workspaceId: 'workspace-fixture',
  prNumber: 1,
  prHeadSha: revision,
  routeRegistrationStatus: 'passed',
  installationReadbackStatus: 'passed',
  sourceFingerprint: 'fixture-source-fingerprint',
  chunkCount: 1,
  embeddingCount: 1,
  transportBlocker: 'none',
  sequence: 1,
  previousReceiptSha256: 'd'.repeat(64),
  receiptSha256: 'e'.repeat(64),
  migrationPath: 'migrations/fixture.sql',
  sourceSha256: 'f'.repeat(64),
  rollbackStatus: 'passed',
  collectionIdentityHash: '1'.repeat(64),
  queryStatus: 'passed',
  searchStatus: 'passed',
  pdfSha256: '2'.repeat(64),
  pdfBytes: 1024,
  tikaMarkerVerified: true,
  imageDigest: `sha256:${'3'.repeat(64)}`,
  adminProducer: 'enterprise-admin',
  overviewStatus: 'passed',
  integrationsStatus: 'passed',
  evidenceStatus: 'passed',
  containerHealthy: true,
  mcpProtocolReady: true,
  brokerRpcReady: true,
  pending: 0,
  oldestAgeSeconds: 0,
  deadLetters: 0,
  duplicateIdentities: 0,
  processedDelta: 1,
  backupDigest: '4'.repeat(64),
  restoredDigest: '4'.repeat(64),
  integrityChecks: 'passed',
  isolatedTarget: 'fixture-restore-target',
  ownerGateStatus: 'approved',
  budgetGateStatus: 'passed',
});

function completeReceipt(surface) {
  return {
    ...COMPLETE_EVIDENCE_FIXTURE,
    surface: surface.surface,
    workflowRunId: `run-${surface.surface}`,
    cleanupStatus: surface.liveCanary.mutates ? 'passed' : 'not-required',
    ownerGateStatus: surface.ownerGate ? 'approved' : 'not-required',
    budgetGateStatus: surface.liveCanary.externalCost ? 'passed' : 'not-required',
  };
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
