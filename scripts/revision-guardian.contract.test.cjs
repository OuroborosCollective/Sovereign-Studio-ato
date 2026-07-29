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

test('path impact selects immutable image workflows without replacing core gates', () => {
  const prSpecs = guardian.workflowSpecs('pr', ['tools/sovereign-chatgpt-mcp/server.py']);
  assert.deepEqual(prSpecs.map((item) => item.name), [
    'Release Verification',
    'Sovereign Agent Backend',
    'Sovereign Continuity Gate',
    'Sovereign ChatGPT MCP',
  ]);
  const mainSpecs = guardian.workflowSpecs('main', ['src/features/admin/api/adminApiClient.ts']);
  assert.deepEqual(mainSpecs.map((item) => item.name), [
    'Release Verification',
    'Sovereign Agent Backend',
    'Sovereign Backend Immutable Image',
  ]);
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

test('unsafe refs and non-full revisions fail closed', () => {
  assert.throws(() => guardian.fullSha('abc'), /REVISION_INVALID/);
  assert.throws(() => guardian.safeRef('../main'), /REF_INVALID/);
});
