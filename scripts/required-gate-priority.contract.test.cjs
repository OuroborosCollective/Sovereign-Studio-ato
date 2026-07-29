'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

const ROOT = path.resolve(__dirname, '..');
const WORKFLOWS = path.join(ROOT, '.github', 'workflows');

function read(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), 'utf8');
}

function directPullRequestWorkflowFiles() {
  return fs.readdirSync(WORKFLOWS)
    .filter((name) => name.endsWith('.yml') || name.endsWith('.yaml'))
    .filter((name) => /^\s{2}pull_request:\s*$/m.test(fs.readFileSync(path.join(WORKFLOWS, name), 'utf8')))
    .sort();
}

function extractGithubScript(workflowText) {
  const marker = '          script: |\n';
  const start = workflowText.indexOf(marker);
  assert.notEqual(start, -1, 'actions/github-script script block must exist');
  const lines = workflowText.slice(start + marker.length).split('\n');
  const body = [];
  for (const line of lines) {
    if (line === '' || line.startsWith('            ')) {
      body.push(line.startsWith('            ') ? line.slice(12) : '');
      continue;
    }
    break;
  }
  return body.join('\n');
}

test('only required workflows receive direct pull_request runners', () => {
  assert.deepEqual(directPullRequestWorkflowFiles(), [
    'release-verification.yml',
    'sovereign-agent-backend.yml',
    'sovereign-continuity-gate.yml',
  ]);
  const releaseWorkflow = read('.github/workflows/release-verification.yml');
  const continuityWorkflow = read('.github/workflows/sovereign-continuity-gate.yml');
  assert.match(releaseWorkflow, /types: \[opened, synchronize, reopened\]/);
  assert.doesNotMatch(releaseWorkflow, /ready_for_review|converted_to_draft/);
  assert.match(continuityWorkflow, /name: continuity-ledger/);
  assert.match(continuityWorkflow, /ready_for_review/);
  assert.match(continuityWorkflow, /validate_continuity\.py/);
});

test('Agent Runtime Tests is the only direct backend PR job', () => {
  const requiredWorkflow = read('.github/workflows/sovereign-agent-backend.yml');
  const supplementalWorkflow = read('.github/workflows/sovereign-agent-supplemental.yml');
  assert.match(requiredWorkflow, /agent-tests:\n\s+name: Agent Runtime Tests\n/);
  assert.equal(requiredWorkflow.includes('name: Compile Check'), false);
  assert.equal(requiredWorkflow.includes('name: Queue-only Release Policy'), false);
  assert.equal(supplementalWorkflow.includes('  pull_request:'), false);
  assert.equal(supplementalWorkflow.includes('workflow_dispatch:'), true);
  assert.equal(supplementalWorkflow.includes('name: Compile Check'), true);
  assert.equal(supplementalWorkflow.includes('name: Queue-only Release Policy'), true);
  assert.equal(supplementalWorkflow.includes('needs: compile-check'), true);
});

test('supplemental coordinator script is syntactically valid and revision-bound', () => {
  const workflow = read('.github/workflows/supplemental-check-coordinator.yml');
  const script = extractGithubScript(workflow);
  assert.doesNotThrow(() => new AsyncFunction('github', 'context', 'core', script));
  assert.match(script, /head_sha: headSha/);
  assert.match(script, /event: 'pull_request'/);
  assert.match(script, /Supplemental Checks Dispatch/);
  assert.match(script, /workflow_id: 'sovereign-pr-review-evidence\.yml'/);
  assert.match(script, /workflow_id: 'sovereign-agent-supplemental\.yml'/);
  assert.match(script, /workflow_id: 'android\.yml'/);
  assert.match(script, /workflow_id: 'sovereign-backend-image\.yml'/);
  assert.match(script, /pr_validation: 'true'/);
});

test('backend image coordinated PR validation cannot publish', () => {
  const workflow = read('.github/workflows/sovereign-backend-image.yml');
  assert.match(workflow, /pr_validation:/);
  assert.match(workflow, /push: \$\{\{ env\.PR_VALIDATION != 'true' \}\}/);
  assert.match(workflow, /load: \$\{\{ env\.PR_VALIDATION == 'true' \}\}/);
  assert.match(workflow, /if: env\.PR_VALIDATION == 'true'/);
  assert.doesNotMatch(workflow, /github\.event_name != 'pull_request'/);
});

test('coordinator starts only after both required workflow families complete', () => {
  const workflow = read('.github/workflows/supplemental-check-coordinator.yml');
  assert.match(workflow, /workflows:\n\s+- Release Verification\n\s+- Sovereign Agent Backend\n/);
  assert.match(workflow, /types: \[completed\]/);
  assert.match(workflow, /requiredWorkflowNames = \[\n\s+'Release Verification',\n\s+'Sovereign Agent Backend',/);
});

test('revision guardian is trusted, exact-head bound and auto-synchronizes stale same-repository PRs', () => {
  const workflow = read('.github/workflows/revision-guardian.yml');
  const continuity = read('.github/workflows/sovereign-continuity-gate.yml');
  assert.match(workflow, /^\s{2}pull_request_target:\s*$/m);
  assert.doesNotMatch(workflow, /^\s{2}pull_request:\s*$/m);
  assert.match(workflow, /^\s{2}push:\n\s+branches: \[main\]/m);
  assert.match(workflow, /^\s{2}workflow_run:\s*$/m);
  assert.match(workflow, /^\s{2}deployment_status:\s*$/m);
  assert.match(workflow, /ref: main\n\s+fetch-depth: 1/);
  assert.match(workflow, /name: 'Revision Guardian'/);
  assert.match(workflow, /'Revision Guardian Reconcile'/);
  assert.match(workflow, /PR_HEAD_NOT_BASED_ON_CURRENT_MAIN/);
  assert.match(workflow, /workflowId: 'revision-guardian-sync-pr\.yml'/);
  assert.match(workflow, /expected_head_sha: target\.revision/);
  assert.match(workflow, /expected_base_sha: currentMain/);
  assert.match(workflow, /FORK_PR_REPAIR_FORBIDDEN/);
  assert.match(workflow, /waitFinal\('Waiting for exact-revision repair evidence'/);
  assert.match(workflow, /waitFinal\('Waiting for exact-revision workflow evidence'/);
  assert.doesNotMatch(workflow, /REVISION_REPAIR_DISPATCHED_WAIT_FOR_NEW_EVIDENCE/);
  assert.match(workflow, /X-GitHub-Api-Version': '2026-03-10'/);
  assert.doesNotMatch(workflow, /createWorkflowDispatch/);
  const guardianScript = extractGithubScript(workflow);
  assert.doesNotThrow(() => new AsyncFunction('github', 'context', 'core', 'require', guardianScript));
  assert.match(continuity, /^\s{2}workflow_dispatch:\s*$/m);
  assert.match(continuity, /expected_head_sha:/);
  assert.match(continuity, /PR_HEAD_IDENTITY_MISMATCH/);
  const syncWorkflow = read('.github/workflows/revision-guardian-sync-pr.yml');
  assert.match(syncWorkflow, /^\s{2}workflow_dispatch:\s*$/m);
  assert.match(syncWorkflow, /expected_head_sha:/);
  assert.match(syncWorkflow, /expected_base_sha:/);
  assert.match(syncWorkflow, /git merge --no-ff --no-edit "\$EXPECTED_BASE_SHA"/);
  assert.match(syncWorkflow, /git push origin "HEAD:\$\{TARGET_REF\}"/);
  assert.doesNotMatch(syncWorkflow, /git push[^\n]*(?:--force|-f\b)/);
});
