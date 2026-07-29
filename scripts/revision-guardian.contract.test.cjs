'use strict';

const assert = require('node:assert/strict');
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

test('path impact keeps all PR gates but selects only matching main workflows', () => {
  const prSpecs = guardian.workflowSpecs('pr', ['tools/sovereign-chatgpt-mcp/server.py']);
  assert.deepEqual(prSpecs.map((item) => item.name), [
    'Release Verification',
    'Sovereign Agent Backend',
    'Sovereign Continuity Gate',
    'Sovereign ChatGPT MCP',
  ]);

  const frontendMainSpecs = guardian.workflowSpecs('main', ['src/features/admin/api/adminApiClient.ts']);
  assert.deepEqual(frontendMainSpecs.map((item) => item.name), [
    'Release Verification',
    'Sovereign Backend Immutable Image',
  ]);

  const backendMainSpecs = guardian.workflowSpecs('main', ['scripts/sovereign-backend/app.py']);
  assert.deepEqual(backendMainSpecs.map((item) => item.name), [
    'Release Verification',
    'Sovereign Agent Backend',
    'Sovereign ChatGPT MCP',
    'Sovereign Backend Immutable Image',
  ]);

  const docsOnlyMainSpecs = guardian.workflowSpecs('main', [
    'docs/architecture/SOVEREIGN_AI_ARCHITECTURE_CORPUS.md',
    'docs/sovereign-continuity/LEDGER.jsonl',
  ]);
  assert.deepEqual(docsOnlyMainSpecs, []);
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
