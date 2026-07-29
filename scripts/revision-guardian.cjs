'use strict';

const SHA40 = /^[0-9a-f]{40}$/;
const SAFE_REF = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$/;
const SUCCESS = new Set(['success', 'neutral', 'skipped']);
const RERUN_FAILED = new Set(['failure']);
const RERUN_ALL = new Set(['cancelled', 'timed_out', 'action_required', 'stale']);

const PR_WORKFLOWS = Object.freeze([
  { name: 'Release Verification', workflowId: 'release-verification.yml' },
  { name: 'Sovereign Agent Backend', workflowId: 'sovereign-agent-backend.yml' },
  { name: 'Sovereign Continuity Gate', workflowId: 'sovereign-continuity-gate.yml' },
]);

const IMPACT_WORKFLOWS = Object.freeze([
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

function workflowSpecs(mode, changedFiles = []) {
  const specs = mode === 'pr' ? [...PR_WORKFLOWS] : PR_WORKFLOWS.slice(0, 2);
  for (const spec of IMPACT_WORKFLOWS) {
    if (changedFiles.some((file) => spec.patterns.some((pattern) => globToRegExp(pattern).test(file)))) specs.push(spec);
  }
  return specs;
}

function latestRunsByName(runs = []) {
  const latest = new Map();
  for (const run of runs) {
    const name = String(run?.name || '');
    const id = Number(run?.id || 0);
    if (!name || id < 1) continue;
    if (!latest.has(name) || id > Number(latest.get(name).id || 0)) latest.set(name, run);
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

module.exports = { SHA40, PR_WORKFLOWS, IMPACT_WORKFLOWS, fullSha, safeRef, resolveTarget, globToRegExp, workflowSpecs, latestRunsByName, classifyRun };
