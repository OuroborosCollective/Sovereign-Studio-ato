#!/usr/bin/env node
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

const repoRoot = path.resolve(new URL('..', import.meta.url).pathname, '..');
const gateScript = path.join(repoRoot, 'scripts/sovereign-agent-release-gate.mjs');

function runGate(cwd) {
  try {
    const stdout = execFileSync(process.execPath, [gateScript], {
      cwd,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return { status: 0, stdout, stderr: '' };
  } catch (error) {
    return {
      status: error.status ?? 1,
      stdout: error.stdout?.toString() ?? '',
      stderr: error.stderr?.toString() ?? '',
    };
  }
}

function copyFixtureFromRepo(targetDir) {
  const files = [
    'package.json',
    'scripts/sovereign-agent-release-gate.mjs',
    'scripts/sovereign-agent-release-gate.test.mjs',
    'backend/agent_runtime/contracts.py',
    'backend/agent_runtime/job_lifecycle.py',
    'backend/agent_runtime/job_store.py',
    'backend/agent_runtime/workspace.py',
    'backend/agent_runtime/workspace_policy.py',
    'backend/agent_runtime/tool_policy.py',
    'backend/agent_runtime/tool_runner.py',
    'backend/agent_runtime/tool_events.py',
    'backend/agent_runtime/evidence_gate.py',
    'backend/agent_runtime/draft_pr_gate.py',
    'backend/agent_runtime/draft_pr_create_gate.py',
    'backend/agent_runtime/pattern_gateway.py',
    'backend/agent_runtime/routes.py',
    'backend/agent_runtime/__init__.py',
    'scripts/sovereign-backend/migrations/003_sovereign_agent_jobs.sql',
    'scripts/sovereign-backend/migrations/004_sovereign_agent_draft_pr_preparation.sql',
    'scripts/sovereign-backend/migrations/005_sovereign_agent_schema_sync.sql',
    'scripts/sovereign-backend/migrations/006_sovereign_agent_pattern_learning.sql',
    'backend/tests/test_agent_job_contract.py',
    'backend/tests/test_agent_workspace_provisioner.py',
    'backend/tests/test_agent_tool_policy.py',
    'backend/tests/test_agent_internal_tools.py',
    'backend/tests/test_agent_tool_routes.py',
    'backend/tests/test_agent_evidence_gate.py',
    'backend/tests/test_agent_draft_pr_gate.py',
    'backend/tests/test_agent_draft_pr_routes.py',
    'backend/tests/test_agent_draft_pr_create_gate.py',
    'backend/tests/test_agent_draft_pr_create_routes.py',
    'backend/tests/test_agent_pattern_gateway.py',
    'backend/tests/test_agent_runtime_no_openhands_required.py',
    'backend/tests/test_agent_runtime_e2e.py',
    'src/features/product/runtime/sovereignAgentActionStreamBridge.ts',
    'src/features/product/runtime/sovereignAgentActionStreamBridge.test.ts',
    'src/features/product/runtime/sovereignAgentRuntimeE2E.test.ts',
    'src/features/product/runtime/sovereignActionStreamRuntime.ts',
    'src/features/product/runtime/sovereignPredictiveRuntimePolicy.ts',
    'src/features/product/runtime/sovereignPredictiveActionRuntime.ts',
  ];
  for (const file of files) {
    const src = path.join(repoRoot, file);
    const dest = path.join(targetDir, file);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(src, dest);
  }
}

test('release gate passes on the current repo checkout', () => {
  const result = runGate(repoRoot);

  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /SOVEREIGN_AGENT_RELEASE_GATE=PASS/);
});

test('release gate blocks when a required contract file is missing', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'sovereign-agent-release-gate-'));
  copyFixtureFromRepo(tempDir);
  fs.rmSync(path.join(tempDir, 'backend/agent_runtime/draft_pr_create_gate.py'));

  const result = runGate(tempDir);

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /SOVEREIGN_AGENT_RELEASE_GATE=BLOCKED/);
  assert.match(result.stderr, /missing file: backend\/agent_runtime\/draft_pr_create_gate\.py/);
});

test('release gate blocks when release scripts are missing', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'sovereign-agent-release-gate-'));
  copyFixtureFromRepo(tempDir);
  const packagePath = path.join(tempDir, 'package.json');
  const pkg = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
  delete pkg.scripts['release:agent-gate'];
  fs.writeFileSync(packagePath, JSON.stringify(pkg, null, 2));

  const result = runGate(tempDir);

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /missing package script: release:agent-gate/);
});

test('release gate blocks secret-like literals in checked runtime files', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'sovereign-agent-release-gate-'));
  copyFixtureFromRepo(tempDir);
  const target = path.join(tempDir, 'backend/agent_runtime/routes.py');
  fs.appendFileSync(target, '\nLEAK = "ghp_1234567890SECRETSECRETSECRET"\n');

  const result = runGate(tempDir);

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /secret-like literal: GitHub token literal in backend\/agent_runtime\/routes\.py/);
});
