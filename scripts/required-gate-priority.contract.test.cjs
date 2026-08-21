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
    'boundary-ledger-drift.yml',
    'integration-plan-lane-gate.yml',
    'release-verification.yml',
    'sovereign-agent-backend.yml',
    'sovereign-continuity-gate.yml',
  ]);
  const releaseWorkflow = read('.github/workflows/release-verification.yml');
  const boundaryWorkflow = read('.github/workflows/boundary-ledger-drift.yml');
  const continuityWorkflow = read('.github/workflows/sovereign-continuity-gate.yml');
  assert.match(releaseWorkflow, /types: \[opened, synchronize, reopened\]/);
  assert.doesNotMatch(releaseWorkflow, /ready_for_review|converted_to_draft/);
  assert.match(continuityWorkflow, /name: continuity-ledger/);
  assert.match(continuityWorkflow, /ready_for_review/);
  assert.match(continuityWorkflow, /validate_continuity\.py/);
  assert.match(boundaryWorkflow, /Fail closed before the MCP full suite/);
  assert.match(boundaryWorkflow, /Upload bounded drift evidence/);
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
  assert.match(script, /String\(run\?\.head_sha \|\| ''\)\.toLowerCase\(\) !== headSha/,
    'the coordinator must locally recheck the exact workflow head instead of trusting a paginated API projection');
  assert.match(script, /run\.event !== 'pull_request'/,
    'the coordinator must ignore non-PR workflow runs even when an API filter returns them');
  assert.match(script, /Supplemental Checks Dispatch/);
  assert.match(
    script,
    /existingChecks\.some\(\(check\) => \(\s*check\s*&& check\.status === 'completed'/,
    'check projections may be absent and must not crash the coordinator',
  );
  assert.match(script, /workflow_id: 'sovereign-pr-review-evidence\.yml'/);
  assert.match(script, /workflow_id: 'sovereign-agent-supplemental\.yml'/);
  assert.match(script, /workflow_id: 'sovereign-toolchain\.yml'/);
  assert.match(script, /expected_head_sha: headSha/);
  assert.match(script, /workflow_id: 'android\.yml'/);
  assert.match(script, /workflow_id: 'sovereign-backend-image\.yml'/);
  assert.match(script, /pr_validation: 'true'/);
  assert.doesNotMatch(script, /pyrewrinterwurst|workflow_id: 'pyre[^']*'/i);
  assert.equal(
    fs.existsSync(path.join(WORKFLOWS, 'pyrewrinterwurst.yml')),
    false,
    'unused Pyre workflow must stay retired',
  );
});

test('locked Google auth plugin cannot restore JCenter resolution', () => {
  const packageJson = JSON.parse(read('package.json'));
  const patchPath = 'patches/@codetrix-studio__capacitor-google-auth@3.3.6.patch';
  assert.equal(
    packageJson.pnpm?.patchedDependencies?.['@codetrix-studio/capacitor-google-auth@3.3.6'],
    patchPath,
  );
  const packagePatch = read(patchPath);
  assert.equal((packagePatch.match(/^-\s*jcenter\(\)$/gm) || []).length, 2);
  assert.doesNotMatch(packagePatch, /^\+\s*jcenter\(\)$/m);
  assert.match(packagePatch, /^\+\s*mavenCentral\(\)$/m);

  const lockfile = read('pnpm-lock.yaml');
  assert.match(lockfile, /@codetrix-studio\/capacitor-google-auth@3\.3\.6/);
  assert.match(lockfile, /patch_hash=3gjc3ddxdsf7zh24aorpnjbxp4/);
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
  const syncWorkflow = read('.github/workflows/revision-guardian-sync-pr.yml');

  const guardianScript = extractGithubScript(workflow);
  assert.doesNotThrow(() => new AsyncFunction('github', 'context', 'core', guardianScript));

  const requiredMarkers = [
    [workflow, '  pull_request_target:\n', 'trusted pull_request_target trigger'],
    [workflow, '  push:\n    branches: [main]\n', 'main push trigger'],
    [workflow, '  workflow_run:\n', 'workflow completion trigger'],
    [workflow, '  deployment_status:\n', 'deployment trigger'],
    [workflow, 'ref: main', 'trusted main checkout'],
    [workflow, 'fetch-depth: 1', 'bounded trusted checkout'],
    [workflow, '    name: Revision Guardian\n', 'native required check job'],
    [workflow, "name: 'Revision Guardian Evidence'", 'supplemental evidence check projection'],
    [workflow, 'PR_HEAD_NOT_BASED_ON_CURRENT_MAIN', 'main ancestor enforcement'],
    [workflow, "workflow_id: 'revision-guardian-sync-pr.yml'", 'bounded sync dispatch'],
    [workflow, 'expected_head_sha: target.revision', 'exact PR head binding'],
    [workflow, 'expected_base_sha: currentMain', 'exact main binding'],
    [workflow, 'FORK_PR_REPAIR_FORBIDDEN', 'fork repair prohibition'],
    [workflow, "core.notice('REVISION_REPAIR_DISPATCHED_WAIT_FOR_NEW_EVIDENCE')", 'repair dispatch leaves the orchestrator job green while the projected check remains fail-closed'],
    [workflow, "core.notice('PR_HEAD_SYNC_DISPATCHED_WAIT_FOR_NEW_EVIDENCE')", 'PR synchronization dispatch leaves no stale failed workflow job'],
    [workflow, "['workflow_run', 'workflow_dispatch'].includes(context.eventName) ? 10000 : 0", 'workflow-run and manual-audit settle delay'],
    [workflow, 'per_page: 100', 'bounded recent workflow run query'],
    [workflow, 'const recentRuns = Array.isArray(runsResponse.data?.workflow_runs)', 'bounded response normalization'],
    [workflow, "String(run?.head_sha || '').toLowerCase() === target.revision", 'local exact-revision run filter'],
    [workflow, 'queriedRunCount: recentRuns.length', 'raw query count evidence'],
    [workflow, 'const recentRunSample = recentRuns.slice(0, 20)', 'bounded raw run sample evidence'],
    [workflow, "const evidencePath = path.join(process.env.GITHUB_WORKSPACE, 'revision-guardian-evidence.json')", 'bounded visible evidence path'],
    [workflow, "schemaVersion: 'sovereign.revision-guardian-evidence.v1'", 'versioned evidence schema'],
    [workflow, 'candidateRuns,', 'candidate run evidence'],
    [workflow, 'writeEvidence({', 'evidence persistence before outcome'],
    [workflow, 'if (repairRequested)', 'single repair mutation guard'],
    [workflow, '- name: Upload revision guardian evidence', 'always-uploaded guardian evidence'],
    [workflow, 'if: always()', 'failure evidence upload'],
    [workflow, 'revision-guardian-evidence-${{ github.run_id }}', 'run-bound evidence artifact'],
    [workflow, 'path: revision-guardian-evidence.json', 'visible evidence upload path'],
    [continuity, '  workflow_dispatch:\n', 'continuity repair dispatch'],
    [continuity, 'expected_head_sha:', 'continuity exact-head input'],
    [continuity, 'PR_HEAD_IDENTITY_MISMATCH', 'continuity identity enforcement'],
    [syncWorkflow, '  workflow_dispatch:\n', 'sync dispatch trigger'],
    [syncWorkflow, 'expected_head_sha:', 'sync exact-head input'],
    [syncWorkflow, 'expected_base_sha:', 'sync exact-base input'],
    [syncWorkflow, 'pull-requests: write', 'bounded PR write permission'],
    [syncWorkflow, 'git merge --no-ff --no-edit "$EXPECTED_BASE_SHA"', 'preferred exact-main merge'],
    [syncWorkflow, 'git push origin "HEAD:${TARGET_REF}"', 'non-force source branch update'],
    [syncWorkflow, 'git checkout --detach "$EXPECTED_BASE_SHA"', 'recovery starts at exact main'],
    [syncWorkflow, 'git rev-list --reverse --no-merges', 'deterministic source commit order'],
    [syncWorkflow, 'test "${#COMMITS[@]}" -le 200', 'bounded replay size'],
    [syncWorkflow, 'git cherry-pick --abort || true', 'fail-closed replay conflict'],
    [syncWorkflow, 'draft: true', 'replacement remains draft'],
    [syncWorkflow, 'SOURCE_PR_CHANGED_DURING_RECOVERY', 'source identity recheck'],
    [syncWorkflow, 'The original PR remains open until the replacement evidence is reviewed', 'auditable replacement handoff'],
  ];

  for (const [surface, marker, label] of requiredMarkers) {
    assert.equal(surface.includes(marker), true, `missing revision guardian contract: ${label}`);
  }
  assert.equal(workflow.includes('\n  pull_request:\n'), false, 'guardian must not execute untrusted PR workflow code');
  assert.equal(
    workflow.includes("core.setFailed('REVISION_REPAIR_DISPATCHED_WAIT_FOR_NEW_EVIDENCE')"),
    false,
    'a successful repair dispatch must not leave a permanent failed workflow job',
  );
  assert.doesNotMatch(workflow, /listWorkflowRunsForRepo,[\s\S]{0,300}(?:head_sha:\s*target\.revision|branch:\s*target\.ref)/);
  assert.doesNotMatch(workflow, /github\.paginate\([\s\S]{0,180}listWorkflowRunsForRepo/);
  assert.doesNotMatch(syncWorkflow, /git push[^\n]*(?:--force|-f\b)/);
});
