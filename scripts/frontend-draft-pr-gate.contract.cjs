'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

function step(workflow, name) {
  const marker = `      - name: ${name}\n`;
  const start = workflow.indexOf(marker);
  assert.notEqual(start, -1, `Missing required step: ${name}`);
  const end = workflow.indexOf('\n      - ', start + marker.length);
  return workflow.slice(start, end === -1 ? undefined : end);
}

const frontendFiles = [
  'src/App.draftPrFlow.test.tsx',
  'src/features/release/PlayReleaseChat.resumeDraftPr.test.tsx',
  'src/features/product/runtime/sovereignAgentClient.draftPrEvidence.test.ts',
  'src/features/product/runtime/devChatDraftPrExecutionContract.test.ts',
  'src/features/product/runtime/githubAccessRuntime.test.ts',
  'src/features/product/runtime/githubAccessRuntime.statelessToken.test.ts',
  'src/features/product/components/GitHubAccessCard.test.tsx',
];
const backendFiles = [
  'backend/tests/test_agent_draft_pr_create_gate.py',
  'backend/tests/test_agent_draft_pr_create_routes.py',
  'backend/tests/test_github_installation_token_compatibility.py',
];

test('every Draft PR executes frontend regressions inside the existing required release runner', () => {
  const workflow = read('.github/workflows/release-verification.yml');
  const gate = step(workflow, 'Draft PR Frontend Regression Gate');
  assert.match(workflow, /\n  pull_request:\n/);
  assert.match(gate, /pnpm exec vitest run/);
  assert.doesNotMatch(gate, /\n\s+(?:if|continue-on-error):|\|\|\s*true|--passWithNoTests/);
  for (const file of frontendFiles) assert.ok(gate.includes(file), `Required frontend regression is missing: ${file}`);
  assert.match(workflow, /ref: \$\{\{ env\.SOVEREIGN_REVISION \}\}/);
  assert.ok(step(workflow, 'Required Gate Priority Contract Tests').includes('scripts/frontend-draft-pr-gate.contract.cjs'));
});

test('existing mandatory backend runner executes Draft PR and credential contracts on the exact PR head', () => {
  const workflow = read('.github/workflows/sovereign-agent-backend.yml');
  const gate = step(workflow, 'Run Agent Runtime Tests');
  assert.match(step(workflow, 'Checkout Repository'), /ref: \$\{\{ github\.event\.pull_request\.head\.sha \|\| github\.sha \}\}/);
  assert.ok(step(workflow, 'Verify exact source revision').includes('git rev-parse HEAD'));
  assert.doesNotMatch(gate, /\n\s+(?:if|continue-on-error):|\|\|\s*true/);
  assert.ok(gate.includes('test_status=${PIPESTATUS[0]}'));
  assert.ok(gate.includes('exit "${test_status}"'));
  for (const file of backendFiles) assert.ok(gate.includes(file), `Required backend regression is missing: ${file}`);
});

test('fast branch feedback does not allocate an additional direct PR runner or replace mandatory tests', () => {
  const workflow = read('.github/workflows/frontend-draft-pr-regression.yml');
  assert.doesNotMatch(workflow, /\n  pull_request(?:_target)?:/);
  assert.match(workflow, /\n  push:\n/);
  for (const file of frontendFiles) assert.ok(workflow.includes(file));
  for (const file of backendFiles) assert.ok(workflow.includes(file));
});
