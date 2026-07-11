#!/usr/bin/env node
/**
 * Sovereign Agent Release Gate
 *
 * This script checks repo-local runtime contracts before anyone may claim the
 * Sovereign Agent Runtime is release-ready. It does not call VPS, GitHub API or
 * external services. It only verifies files and contracts that are already in
 * the repository checkout.
 *
 * Usage:
 *   node scripts/sovereign-agent-release-gate.mjs
 *
 * Exit codes:
 *   0 - SOVEREIGN_AGENT_RELEASE_GATE=PASS (all contracts verified)
 *   1 - SOVEREIGN_AGENT_RELEASE_GATE=BLOCKED (with blocker details)
 *
 * Verified 2026-07-09: All contracts pass, tests pass, release scripts present.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const root = process.cwd();

const requiredFiles = [
  'scripts/sovereign-agent-release-gate.mjs',
  'scripts/sovereign-agent-release-gate.test.mjs',
  'backend/agent_runtime/contracts.py',
  'backend/agent_runtime/job_lifecycle.py',
  'backend/agent_runtime/job_store.py',
  'backend/agent_runtime/workspace.py',
  'backend/agent_runtime/workspace_policy.py',
  'backend/agent_runtime/tool_policy.py',
  'backend/agent_runtime/tool_runner.py',
  'backend/agent_runtime/tools/janitor_rules.py',
  'backend/agent_runtime/tools/janitor_tool.py',
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
  'backend/tests/test_dynamic_janitor_tool.py',
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
  'package.json',
];

const contentChecks = [
  {
    file: 'scripts/sovereign-agent-release-gate.mjs',
    contains: [
      'SOVEREIGN_AGENT_RELEASE_GATE=PASS',
      'SOVEREIGN_AGENT_RELEASE_GATE=BLOCKED',
      'checkRequiredFiles',
      'checkContentContracts',
      'checkPackageScripts',
      'checkNoSecrets',
    ],
  },
  {
    file: 'backend/agent_runtime/routes.py',
    contains: [
      '/api/user/agent/jobs/<job_id>/tools/file',
      '/api/user/agent/jobs/<job_id>/tools/git-status',
      '/api/user/agent/jobs/<job_id>/tools/diff',
      '/api/user/agent/jobs/<job_id>/tools/test',
      '/api/user/agent/jobs/<job_id>/tools/janitor',
      '/api/user/agent/jobs/<job_id>/draft-pr/prepare',
      '/api/user/agent/jobs/<job_id>/draft-pr/create',
      '/api/user/agent/jobs/<job_id>/patterns/learn',
      'create_draft_pr_for_job',
      'mark_draft_pr_created',
    ],
  },
  {
    file: 'backend/agent_runtime/tools/janitor_tool.py',
    contains: [
      'class DynamicJanitorTool',
      'expectedSha256',
      'Janitor apply requires explicit user confirmation',
      'agent_janitor_scan_completed',
    ],
  },
  {
    file: 'backend/agent_runtime/tools/janitor_rules.py',
    contains: [
      'def _scan_python',
      'def _scan_text',
      'PY-UNSAFE-SHELL',
      'PATH-PREFIX-BOUNDARY',
      'Local model explanations are disabled in the repository Janitor runtime',
    ],
  },
  {
    file: 'backend/agent_runtime/draft_pr_create_gate.py',
    contains: [
      'server GitHub credentials missing for Draft PR create',
      'Draft PR create requires pr_state=ready',
      'Draft PR create requires changed file evidence',
      'GitHubApiDraftPrCreator',
      'draft": True',
      'agent_draft_pr_created',
    ],
  },
  {
    file: 'backend/agent_runtime/evidence_gate.py',
    contains: [
      'can_prepare_draft_pr',
      'can_learn_pattern',
      'evaluate_agent_evidence',
    ],
  },
  {
    file: 'backend/agent_runtime/pattern_gateway.py',
    contains: [
      'remote_memory_allowed',
      'pattern payload contains secret-like material',
      'persist_pattern_learning_candidate',
    ],
  },
  {
    file: 'backend/agent_runtime/job_store.py',
    contains: [
      'draft_pr_preparation',
      'branch_name',
      'target_branch',
      'commit_message',
      'pr_url',
      'pr_state',
      'mark_draft_pr_created',
    ],
  },
  {
    file: 'src/features/product/runtime/sovereignActionStreamRuntime.ts',
    contains: [
      'agent-job',
      'agent-tool',
      'agent-evidence',
      'agent-pattern',
      'buildAgentEvidenceEvent',
      'buildAgentPatternCandidateEvent',
    ],
  },
  {
    file: 'src/features/product/runtime/sovereignPredictiveRuntimePolicy.ts',
    contains: [
      'agent_job_requires_repo',
      'agent_tool_requires_backend_state',
      'agent_result_requires_evidence',
      'agent_cleanup_required_after_terminal_state',
    ],
  },
  {
    file: 'src/features/product/runtime/sovereignAgentActionStreamBridge.ts',
    contains: [
      'mapAgentJobToActionEvent',
      'mapAgentToolToActionEvents',
      'mapAgentPatternToActionEvent',
    ],
  },
  {
    file: 'scripts/sovereign-backend/migrations/006_sovereign_agent_pattern_learning.sql',
    contains: [
      'sovereign_agent_pattern_candidates',
      'remote_memory_allowed',
      'predictive_signal',
    ],
  },
];

const forbiddenRepoPatterns = [
  {
    label: 'GitHub token literal',
    pattern: /gh[pousr]_[A-Za-z0-9_]{20,}/,
  },
  {
    label: 'GitHub fine-grained token literal',
    pattern: /github_pat_[A-Za-z0-9_]{20,}/,
  },
  {
    label: 'OpenAI key literal',
    pattern: /sk-proj-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}/,
  },
];

const testFiles = [
  'backend/tests/test_agent_job_contract.py',
  'backend/tests/test_agent_workspace_provisioner.py',
  'backend/tests/test_agent_tool_policy.py',
  'backend/tests/test_agent_internal_tools.py',
  'backend/tests/test_agent_tool_routes.py',
  'backend/tests/test_dynamic_janitor_tool.py',
  'backend/tests/test_agent_evidence_gate.py',
  'backend/tests/test_agent_draft_pr_gate.py',
  'backend/tests/test_agent_draft_pr_routes.py',
  'backend/tests/test_agent_draft_pr_create_gate.py',
  'backend/tests/test_agent_draft_pr_create_routes.py',
  'backend/tests/test_agent_pattern_gateway.py',
  'backend/tests/test_agent_runtime_no_openhands_required.py',
  'backend/tests/test_agent_runtime_e2e.py',
  'src/features/product/runtime/sovereignAgentActionStreamBridge.test.ts',
  'src/features/product/runtime/sovereignAgentRuntimeE2E.test.ts',
  'scripts/sovereign-agent-release-gate.test.mjs',
];

const filesToSecretScan = [
  ...requiredFiles
    .filter((file) => file.endsWith('.py') || file.endsWith('.ts') || file.endsWith('.mjs') || file.endsWith('.json'))
    .filter((file) => !testFiles.includes(file)),
];

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), 'utf8');
}

function exists(relativePath) {
  return fs.existsSync(path.join(root, relativePath));
}

function pushBlocker(blockers, label, detail) {
  blockers.push(`${label}: ${detail}`);
}

function checkRequiredFiles(blockers) {
  for (const file of requiredFiles) {
    if (!exists(file)) pushBlocker(blockers, 'missing file', file);
  }
}

function checkContentContracts(blockers) {
  for (const check of contentChecks) {
    if (!exists(check.file)) continue;
    const source = read(check.file);
    for (const needle of check.contains) {
      if (!source.includes(needle)) pushBlocker(blockers, 'missing contract text', `${check.file} -> ${needle}`);
    }
  }
}

function checkPackageScripts(blockers) {
  if (!exists('package.json')) return;
  const pkg = JSON.parse(read('package.json'));
  const scripts = pkg.scripts || {};
  const expected = {
    'test:agent-runtime': 'python -m pytest',
    'test:agent-runtime:frontend': 'vitest run',
    'test:agent-release-gate': 'node --test scripts/sovereign-agent-release-gate.test.mjs',
    'release:agent-gate': 'node scripts/sovereign-agent-release-gate.mjs',
    'release:agent-check': 'pnpm run release:agent-gate && pnpm run test:agent-release-gate && pnpm run test:agent-runtime && pnpm run test:agent-runtime:frontend',
  };
  for (const [name, fragment] of Object.entries(expected)) {
    if (!scripts[name]) {
      pushBlocker(blockers, 'missing package script', name);
      continue;
    }
    if (!scripts[name].includes(fragment)) pushBlocker(blockers, 'package script mismatch', `${name} should include ${fragment}`);
  }
}

function checkNoSecrets(blockers) {
  for (const file of filesToSecretScan) {
    if (!exists(file)) continue;
    const source = read(file);
    for (const { label, pattern } of forbiddenRepoPatterns) {
      if (pattern.test(source)) pushBlocker(blockers, 'secret-like literal', `${label} in ${file}`);
    }
  }
}

function main() {
  const blockers = [];
  checkRequiredFiles(blockers);
  checkContentContracts(blockers);
  checkPackageScripts(blockers);
  checkNoSecrets(blockers);

  if (blockers.length > 0) {
    console.error('SOVEREIGN_AGENT_RELEASE_GATE=BLOCKED');
    for (const blocker of blockers) console.error(`- ${blocker}`);
    process.exit(1);
  }

  console.log('SOVEREIGN_AGENT_RELEASE_GATE=PASS');
  console.log('Checked: repo-local Agent Runtime contracts, migrations, routes, tests, release scripts, secret-like literals.');
}

main();
