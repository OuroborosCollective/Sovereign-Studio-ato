'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const guardian = require('./revision-guardian.cjs');

const HEAD = '1'.repeat(40);
const BASE = '2'.repeat(40);
const MERGE = '3'.repeat(40);

test('pull request target binds the immutable source head, not a synthetic merge SHA', () => {
  const target = guardian.resolveTarget('pull_request_target', {
    action: 'synchronize',
    pull_request: {
      number: 1081,
      head: { sha: HEAD, ref: 'sovereign/revision-guardian' },
      base: { ref: 'main' },
    },
  });
  assert.deepEqual(target, {
    mode: 'pr',
    revision: HEAD,
    ref: 'sovereign/revision-guardian',
    prNumber: 1081,
  });
});

test('merged pull request binds the actual merge commit on main', () => {
  const target = guardian.resolveTarget('pull_request_target', {
    action: 'closed',
    pull_request: {
      number: 1081,
      merged: true,
      merge_commit_sha: MERGE,
      head: { sha: HEAD, ref: 'feature' },
      base: { ref: 'main', sha: BASE },
    },
  });
  assert.equal(target.mode, 'main');
  assert.equal(target.revision, MERGE);
  assert.equal(target.ref, 'main');
});

test('push binds the event after SHA', () => {
  const target = guardian.resolveTarget('push', {
    before: BASE,
    after: MERGE,
    ref: 'refs/heads/main',
  });
  assert.equal(target.revision, MERGE);
  assert.equal(target.before, BASE);
  assert.equal(target.ref, 'main');
});

test('workflow runs are classified only against the exact authoritative revision', () => {
  assert.equal(guardian.classifyRun(undefined, HEAD), 'missing');
  assert.equal(guardian.classifyRun({ head_sha: BASE }, HEAD), 'stale');
  assert.equal(guardian.classifyRun({ head_sha: HEAD, status: 'in_progress' }, HEAD), 'pending');
  assert.equal(guardian.classifyRun({ head_sha: HEAD, status: 'completed', conclusion: 'success' }, HEAD), 'success');
  assert.equal(guardian.classifyRun({ head_sha: HEAD, status: 'completed', conclusion: 'failure' }, HEAD), 'rerun-failed');
  assert.equal(guardian.classifyRun({ head_sha: HEAD, status: 'completed', conclusion: 'cancelled' }, HEAD), 'rerun-all');
});

test('path impact preserves blocking product gates while acceleration makes only continuity advisory', () => {
  const enforcedPrSpecs = guardian.workflowSpecs('pr', ['tools/sovereign-chatgpt-mcp/server.py'], 'enforced');
  assert.deepEqual(enforcedPrSpecs.map((item) => item.name), [
    'Release Verification',
    'Sovereign Agent Backend',
    'Sovereign Continuity Gate',
    'Sovereign ChatGPT MCP',
  ]);

  const toolchainPrSpecs = guardian.workflowSpecs('pr', ['tools/sovereign-toolchain/src/sovereign_toolchain/core.py'], 'enforced');
  assert.deepEqual(toolchainPrSpecs.map((item) => item.name), [
    'Release Verification',
    'Sovereign Agent Backend',
    'Sovereign Continuity Gate',
    'Sovereign Toolchain',
  ]);

  const accelerationPrSpecs = guardian.workflowSpecs('pr', ['tools/sovereign-chatgpt-mcp/server.py'], 'acceleration');
  assert.deepEqual(accelerationPrSpecs.map((item) => item.name), [
    'Release Verification',
    'Sovereign Agent Backend',
    'Sovereign ChatGPT MCP',
  ]);

  const reconciliationPrSpecs = guardian.workflowSpecs('pr', ['tools/sovereign-chatgpt-mcp/server.py'], 'reconciliation');
  assert.deepEqual(reconciliationPrSpecs.map((item) => item.name), accelerationPrSpecs.map((item) => item.name));

  const frontendMainSpecs = guardian.workflowSpecs('main', ['src/features/admin/api/adminApiClient.ts'], 'acceleration');
  assert.deepEqual(frontendMainSpecs.map((item) => item.name), [
    'Release Verification',
    'Sovereign Backend Immutable Image',
  ]);

  const backendMainSpecs = guardian.workflowSpecs('main', ['scripts/sovereign-backend/app.py'], 'acceleration');
  assert.deepEqual(backendMainSpecs.map((item) => item.name), [
    'Release Verification',
    'Sovereign Agent Backend',
    'Sovereign ChatGPT MCP',
    'Sovereign Backend Immutable Image',
  ]);

  const docsOnlyMainSpecs = guardian.workflowSpecs('main', [
    'docs/architecture/SOVEREIGN_AI_ARCHITECTURE_CORPUS.md',
    'docs/sovereign-continuity/LEDGER.jsonl',
  ], 'acceleration');
  assert.deepEqual(docsOnlyMainSpecs, []);
});

test('governance mode is fail-closed by default and reversible', () => {
  assert.equal(guardian.normalizeGovernanceMode('enforced'), 'enforced');
  assert.equal(guardian.normalizeGovernanceMode('acceleration'), 'acceleration');
  assert.equal(guardian.normalizeGovernanceMode('reconciliation'), 'reconciliation');
  assert.equal(guardian.requiresCurrentMainAncestor('enforced'), true);
  assert.equal(guardian.shouldAutoSyncOpenPrs('enforced'), true);
  assert.equal(guardian.requiresCurrentMainAncestor('acceleration'), false);
  assert.equal(guardian.shouldAutoSyncOpenPrs('reconciliation'), false);
  assert.throws(() => guardian.normalizeGovernanceMode('disabled'), /GOVERNANCE_MODE_INVALID/);

  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'sovereign-governance-'));
  try {
    const missing = path.join(root, 'missing.json');
    assert.equal(guardian.loadGovernanceMode(missing), 'enforced');
    const config = path.join(root, 'mode.json');
    fs.writeFileSync(config, JSON.stringify({ schemaVersion: 'sovereign.governance-mode.v1', mode: 'acceleration' }));
    assert.equal(guardian.loadGovernanceMode(config), 'acceleration');
    fs.writeFileSync(config, JSON.stringify({ schemaVersion: 'wrong', mode: 'acceleration' }));
    assert.throws(() => guardian.loadGovernanceMode(config), /GOVERNANCE_MODE_SCHEMA_INVALID/);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('latest workflow selection is deterministic by run id', () => {
  const selected = guardian.latestRunsByName([
    { id: 2, name: 'Release Verification' },
    { id: 5, name: 'Release Verification' },
    { id: 4, name: 'Sovereign Agent Backend' },
  ]);
  assert.equal(selected.get('Release Verification').id, 5);
  assert.equal(selected.get('Sovereign Agent Backend').id, 4);
});

test('cancelled duplicate runs do not invalidate successful evidence for the same revision', () => {
  const selected = guardian.latestRunsByName([
    { id: 10, name: 'Sovereign ChatGPT MCP', head_sha: HEAD, status: 'completed', conclusion: 'success' },
    { id: 11, name: 'Sovereign ChatGPT MCP', head_sha: HEAD, status: 'completed', conclusion: 'cancelled' },
    { id: 20, name: 'Release Verification', head_sha: HEAD, status: 'completed', conclusion: 'success' },
    { id: 21, name: 'Release Verification', head_sha: HEAD, status: 'completed', conclusion: 'failure' },
    { id: 30, name: 'Sovereign Agent Backend', head_sha: HEAD, status: 'completed', conclusion: 'success' },
    { id: 31, name: 'Sovereign Agent Backend', head_sha: HEAD, status: 'in_progress', conclusion: null },
    { id: 40, name: 'Sovereign Continuity Gate', head_sha: HEAD, status: 'completed', conclusion: 'success' },
    { id: 41, name: 'Sovereign Continuity Gate', head_sha: BASE, status: 'completed', conclusion: 'cancelled' },
  ]);

  assert.equal(selected.get('Sovereign ChatGPT MCP').id, 10);
  assert.equal(selected.get('Release Verification').id, 21);
  assert.equal(selected.get('Sovereign Agent Backend').id, 31);
  assert.equal(selected.get('Sovereign Continuity Gate').id, 41);
});

test('unsafe refs and non-full revisions fail closed', () => {
  assert.throws(() => guardian.fullSha('abc'), /REVISION_INVALID/);
  assert.throws(() => guardian.safeRef('../main'), /REF_INVALID/);
});
