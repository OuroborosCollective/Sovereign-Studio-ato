'use strict';

const fs = require('node:fs');

const SHA40 = /^[0-9a-f]{40}$/;
const SAFE_REF = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$/;
const SUCCESS = new Set(['success', 'neutral', 'skipped']);
const RERUN_FAILED = new Set(['failure']);
const RERUN_ALL = new Set(['cancelled', 'timed_out', 'action_required', 'stale']);
const GOVERNANCE_MODES = new Set(['enforced', 'acceleration', 'reconciliation']);
const GOVERNANCE_SCHEMA_VERSION = 'sovereign.governance-mode.v1';
const CONTINUITY_WORKFLOW_NAME = 'Sovereign Continuity Gate';

const PR_WORKFLOWS = Object.freeze([
  { name: 'Release Verification', workflowId: 'release-verification.yml' },
  { name: 'Sovereign Agent Backend', workflowId: 'sovereign-agent-backend.yml' },
  { name: 'Sovereign Continuity Gate', workflowId: 'sovereign-continuity-gate.yml' },
]);

const MAIN_WORKFLOWS = Object.freeze([
  {
    name: 'Release Verification',
    workflowId: 'release-verification.yml',
    patterns: [
      'src/**', 'scripts/**', 'android/**', 'tests/**',
      'config/architecture/SOVEREIGN_RUNTIME_CANARY_MATRIX.v1.json',
      'docs/SOVEREIGN_ARCHITECTURE_MANIFEST.md',
      '.github/workflows/release-verification.yml',
      '.github/workflows/revision-guardian.yml',
      '.github/workflows/revision-guardian-sync-pr.yml',
      '.github/workflows/sovereign-continuity-gate.yml',
      '.github/workflows/supplemental-check-coordinator.yml',
      '.github/workflows/sovereign-agent-supplemental.yml',
      'package.json', 'pnpm-lock.yaml', 'vite.config.ts', 'capacitor.config.*',
    ],
  },
  {
    name: 'Sovereign Agent Backend',
    workflowId: 'sovereign-agent-backend.yml',
    patterns: [
      'backend/requirements-test.txt', 'backend/litellm_runtime.py',
      'scripts/check-backend-python-runtime.py', 'scripts/sovereign-backend/**',
      'scripts/sovereign-agent-internal-live-path.contract.mjs',
      '.github/actions/setup-backend-python/**',
      '.github/workflows/sovereign-agent-backend.yml',
    ],
  },
]);

const IMPACT_WORKFLOWS = Object.freeze([
  {
    name: 'Sovereign Toolchain',
    workflowId: 'sovereign-toolchain.yml',
    patterns: ['tools/sovereign-toolchain/**', 'tools/sovereign-legacy-mcp-common/github_app_auth.py', '.github/workflows/sovereign-toolchain.yml'],
  },
  {
    name: 'Sovereign ChatGPT MCP',
    workflowId: 'sovereign-chatgpt-mcp.yml',
    patterns: ['tools/sovereign-chatgpt-mcp/**', 'scripts/sovereign-backend/openrouter_provider_runtime.py', 'scripts/sovereign-backend/app.py', '.github/workflows/sovereign-chatgpt-mcp.yml'],
  },
  {
    name: 'Sovereign Backend Immutable Image',
    workflowId: 'sovereign-backend-image.yml',
    patterns: ['scripts/sovereign-backend/**', 'src/features/admin/**', 'src/SovereignAppWrapper.tsx', 'src/main.tsx', 'index.html', 'package.json', 'pnpm-lock.yaml', 'vite.config.ts', '.github/workflows/sovereign-backend-image.yml'],
  },
]);

function fullSha(value, label = 'revision') {
  const result = String(value || '').trim().toLowerCase();
  if (!SHA40.test(result)) throw new Error(`${label.toUpperCase()}_INVALID`);
  return result;
}

function safeRef(value, label = 'ref') {
  const result = String(value || '').trim();
  if (!SAFE_REF.test(result) || result.includes('..')) throw new Error(`${label.toUpperCase()}_INVALID`);
  return result;
}

function normalizeGovernanceMode(value = 'enforced') {
  const mode = String(value || 'enforced').trim().toLowerCase();
  if (!GOVERNANCE_MODES.has(mode)) throw new Error('GOVERNANCE_MODE_INVALID');
  return mode;
}

function loadGovernanceMode(filePath) {
  try {
    const payload = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    if (payload?.schemaVersion !== GOVERNANCE_SCHEMA_VERSION) throw new Error('GOVERNANCE_MODE_SCHEMA_INVALID');
    return normalizeGovernanceMode(payload?.mode);
  } catch (error) {
    if (error?.code === 'ENOENT') return 'enforced';
    throw error;
  }
}

function governanceIsAdvisory(value) {
  return normalizeGovernanceMode(value) !== 'enforced';
}

function requiresCurrentMainAncestor(value) {
  return !governanceIsAdvisory(value);
}

function shouldAutoSyncOpenPrs(value) {
  return !governanceIsAdvisory(value);
}

function resolveTarget(eventName, payload, inputs = {}) {
  if (eventName === 'pull_request_target' || eventName === 'pull_request') {
    const pull = payload.pull_request || {};
    if (payload.action === 'closed' && pull.merged === true) {
      return { mode: 'main', revision: fullSha(pull.merge_commit_sha, 'merge_revision'), ref: safeRef(pull.base?.ref || 'main'), prNumber: Number(pull.number || 0) };
    }
    return { mode: 'pr', revision: fullSha(pull.head?.sha, 'pr_head'), ref: safeRef(pull.head?.ref, 'pr_ref'), prNumber: Number(pull.number || 0) };
  }
  if (eventName === 'push') {
    return { mode: 'main', revision: fullSha(payload.after, 'push_revision'), before: String(payload.before || '').toLowerCase(), ref: safeRef(String(payload.ref || '').replace(/^refs\/heads\//, '')), prNumber: 0 };
  }
  if (eventName === 'workflow_run') {
    const run = payload.workflow_run || {};
    return { mode: run.pull_requests?.length ? 'pr' : 'main', revision: fullSha(run.head_sha, 'workflow_revision'), ref: safeRef(run.head_branch || 'main'), prNumber: Number(run.pull_requests?.[0]?.number || 0) };
  }
  if (eventName === 'deployment_status') {
    const deployment = payload.deployment || {};
    return { mode: 'main', revision: fullSha(deployment.sha, 'deployment_revision'), ref: safeRef(deployment.ref || 'main'), prNumber: 0 };
  }
  if (eventName === 'workflow_dispatch') {
    return { mode: Number(inputs.pr_number || 0) > 0 ? 'pr' : 'main', revision: fullSha(inputs.expected_revision, 'dispatch_revision'), ref: safeRef(inputs.target_ref || 'main'), prNumber: Number(inputs.pr_number || 0) };
  }
  throw new Error(`EVENT_NOT_SUPPORTED:${eventName}`);
}

function globToRegExp(pattern) {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*\*/g, '__DOUBLE_STAR__').replace(/\*/g, '[^/]*');
  return new RegExp(`^${escaped.replace(/__DOUBLE_STAR__/g, '.*')}$`);
}

function workflowSpecs(mode, changedFiles = [], governanceMode = 'enforced') {
  const selectedGovernanceMode = normalizeGovernanceMode(governanceMode);
  const specs = mode === 'pr'
    ? PR_WORKFLOWS.filter((spec) => (
      !governanceIsAdvisory(selectedGovernanceMode) || spec.name !== CONTINUITY_WORKFLOW_NAME
    ))
    : MAIN_WORKFLOWS.filter((spec) => (
      changedFiles.some((file) => spec.patterns.some((pattern) => globToRegExp(pattern).test(file)))
    ));
  for (const spec of IMPACT_WORKFLOWS) {
    if (
      changedFiles.some((file) => spec.patterns.some((pattern) => globToRegExp(pattern).test(file)))
      && !specs.some((selected) => selected.name === spec.name)
    ) specs.push(spec);
  }
  return specs;
}

function latestRunsByName(runs = []) {
  const grouped = new Map();
  for (const run of runs) {
    const name = String(run?.name || '');
    const id = Number(run?.id || 0);
    if (!name || id < 1) continue;
    if (!grouped.has(name)) grouped.set(name, []);
    grouped.get(name).push(run);
  }

  const latest = new Map();
  for (const [name, candidates] of grouped.entries()) {
    candidates.sort((left, right) => Number(right?.id || 0) - Number(left?.id || 0));
    const newest = candidates[0];
    const newestRevision = String(newest?.head_sha || '').toLowerCase();
    if (
      newest?.status === 'completed'
      && String(newest?.conclusion || '') === 'cancelled'
      && newestRevision
    ) {
      const priorSuccess = candidates.find((candidate) => (
        String(candidate?.head_sha || '').toLowerCase() === newestRevision
        && candidate?.status === 'completed'
        && SUCCESS.has(String(candidate?.conclusion || ''))
      ));
      if (priorSuccess) {
        latest.set(name, priorSuccess);
        continue;
      }
    }
    latest.set(name, newest);
  }
  return latest;
}

function classifyRun(run, revision) {
  if (!run) return 'missing';
  if (String(run.head_sha || '').toLowerCase() !== revision) return 'stale';
  if (run.status !== 'completed') return 'pending';
  const conclusion = String(run.conclusion || '');
  if (SUCCESS.has(conclusion)) return 'success';
  if (RERUN_FAILED.has(conclusion)) return 'rerun-failed';
  if (RERUN_ALL.has(conclusion)) return 'rerun-all';
  return 'failed';
}

module.exports = {
  SHA40,
  PR_WORKFLOWS,
  MAIN_WORKFLOWS,
  IMPACT_WORKFLOWS,
  GOVERNANCE_MODES,
  GOVERNANCE_SCHEMA_VERSION,
  CONTINUITY_WORKFLOW_NAME,
  fullSha,
  safeRef,
  normalizeGovernanceMode,
  loadGovernanceMode,
  governanceIsAdvisory,
  requiresCurrentMainAncestor,
  shouldAutoSyncOpenPrs,
  resolveTarget,
  globToRegExp,
  workflowSpecs,
  latestRunsByName,
  classifyRun,
};
