#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

export const MATRIX_SCHEMA = 'sovereign.runtime-canary-matrix.v1';
export const EVIDENCE_SCHEMA = 'sovereign.runtime-canary-evidence.v1';
export const DEFAULT_MATRIX_PATH = 'config/architecture/SOVEREIGN_RUNTIME_CANARY_MATRIX.v1.json';
export const DEFAULT_REPORT_PATH = '.security-reports/runtime-canary-matrix-gate.json';
export const REQUIRED_EVIDENCE_FIELDS = ['revision', 'workflowRunId', 'status', 'evidenceSha256'];

const ALLOWED_FAMILIES = new Set(['backend', 'tool', 'storage', 'integration', 'release', 'client']);
const ALLOWED_RISKS = new Set(['critical', 'high', 'medium', 'low']);
const ALLOWED_LIVE_POLICIES = new Set(['required', 'excluded']);
const ALLOWED_RECEIPT_STATUSES = new Set(['passed', 'failed', 'blocked']);
const SHA40 = /^[0-9a-f]{40}$/;
const SHA256 = /^[0-9a-f]{64}$/;

export function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonicalize(value[key])]),
    );
  }
  return value;
}

export function canonicalSha256(value) {
  return crypto.createHash('sha256').update(JSON.stringify(canonicalize(value))).digest('hex');
}

function nonEmptyString(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function nonEmptyStringArray(value) {
  return Array.isArray(value) && value.length > 0 && value.every(nonEmptyString);
}

function pushError(errors, pathLabel, message) {
  errors.push({ path: pathLabel, message });
}

export function validateMatrix(matrix) {
  const errors = [];

  if (!matrix || typeof matrix !== 'object' || Array.isArray(matrix)) {
    return [{ path: '$', message: 'Matrix must be a JSON object.' }];
  }
  if (matrix.schemaVersion !== MATRIX_SCHEMA) {
    pushError(errors, '$.schemaVersion', `Expected ${MATRIX_SCHEMA}.`);
  }
  if (!nonEmptyString(matrix.matrixId)) pushError(errors, '$.matrixId', 'matrixId is required.');
  if (!matrix.revisionBinding || matrix.revisionBinding.mustMatchCheckout !== true) {
    pushError(errors, '$.revisionBinding', 'mustMatchCheckout must be true.');
  }
  if (matrix.revisionBinding?.format !== 'git-sha-40-lowercase') {
    pushError(errors, '$.revisionBinding.format', 'Revision format must be git-sha-40-lowercase.');
  }
  if (matrix.releasePolicy?.mode !== 'fail-closed') {
    pushError(errors, '$.releasePolicy.mode', 'Release policy must be fail-closed.');
  }
  if (matrix.releasePolicy?.receiptSchemaVersion !== EVIDENCE_SCHEMA) {
    pushError(errors, '$.releasePolicy.receiptSchemaVersion', `Expected ${EVIDENCE_SCHEMA}.`);
  }
  if (!nonEmptyStringArray(matrix.releasePolicy?.requiredEvidenceFields)) {
    pushError(errors, '$.releasePolicy.requiredEvidenceFields', 'Required evidence fields must be a non-empty string array.');
  } else {
    for (const field of REQUIRED_EVIDENCE_FIELDS) {
      if (!matrix.releasePolicy.requiredEvidenceFields.includes(field)) {
        pushError(errors, '$.releasePolicy.requiredEvidenceFields', `Missing mandatory field ${field}.`);
      }
    }
  }
  if (!Array.isArray(matrix.surfaces) || matrix.surfaces.length === 0) {
    pushError(errors, '$.surfaces', 'At least one surface is required.');
    return errors;
  }

  const seenSurfaces = new Set();
  for (const [index, surface] of matrix.surfaces.entries()) {
    const base = `$.surfaces[${index}]`;
    if (!surface || typeof surface !== 'object' || Array.isArray(surface)) {
      pushError(errors, base, 'Surface must be an object.');
      continue;
    }
    if (!nonEmptyString(surface.surface)) pushError(errors, `${base}.surface`, 'surface is required.');
    else if (seenSurfaces.has(surface.surface)) pushError(errors, `${base}.surface`, `Duplicate surface ${surface.surface}.`);
    else seenSurfaces.add(surface.surface);

    if (!ALLOWED_FAMILIES.has(surface.family)) pushError(errors, `${base}.family`, 'Unknown family.');
    if (!ALLOWED_RISKS.has(surface.riskClass)) pushError(errors, `${base}.riskClass`, 'Unknown riskClass.');
    if (surface.releaseCritical !== true) pushError(errors, `${base}.releaseCritical`, 'Every matrix entry must explicitly be releaseCritical.');
    if (!nonEmptyStringArray(surface.coverageSource)) pushError(errors, `${base}.coverageSource`, 'coverageSource must be non-empty.');
    if (!nonEmptyStringArray(surface.staticGate)) pushError(errors, `${base}.staticGate`, 'staticGate must be non-empty.');
    if (!nonEmptyStringArray(surface.ciCanary)) pushError(errors, `${base}.ciCanary`, 'ciCanary must be non-empty.');
    if (!nonEmptyStringArray(surface.evidenceFields)) pushError(errors, `${base}.evidenceFields`, 'evidenceFields must be non-empty.');
    else {
      for (const field of REQUIRED_EVIDENCE_FIELDS) {
        if (!surface.evidenceFields.includes(field)) pushError(errors, `${base}.evidenceFields`, `Missing mandatory evidence field ${field}.`);
      }
    }
    if (typeof surface.ownerGate !== 'boolean') pushError(errors, `${base}.ownerGate`, 'ownerGate must be boolean.');
    if (!nonEmptyString(surface.budgetGate)) pushError(errors, `${base}.budgetGate`, 'budgetGate is required.');

    const live = surface.liveCanary;
    if (!live || typeof live !== 'object' || Array.isArray(live)) {
      pushError(errors, `${base}.liveCanary`, 'liveCanary object is required.');
      continue;
    }
    if (!ALLOWED_LIVE_POLICIES.has(live.policy)) pushError(errors, `${base}.liveCanary.policy`, 'Policy must be required or excluded.');
    if (!nonEmptyString(live.producer)) pushError(errors, `${base}.liveCanary.producer`, 'producer is required.');
    if (!nonEmptyString(live.kind)) pushError(errors, `${base}.liveCanary.kind`, 'kind is required.');
    if (typeof live.mutates !== 'boolean') pushError(errors, `${base}.liveCanary.mutates`, 'mutates must be boolean.');
    if (typeof live.externalCost !== 'boolean') pushError(errors, `${base}.liveCanary.externalCost`, 'externalCost must be boolean.');
    if (!nonEmptyString(live.cleanup)) pushError(errors, `${base}.liveCanary.cleanup`, 'cleanup is required.');

    if (live.policy === 'required') {
      if (live.producer === 'none') pushError(errors, `${base}.liveCanary.producer`, 'Required canary cannot use producer none.');
      if (live.mutates === true && live.cleanup === 'none') {
        pushError(errors, `${base}.liveCanary.cleanup`, 'Mutating canaries require explicit cleanup.');
      }
      if (live.externalCost === true) {
        if (surface.ownerGate !== true) pushError(errors, `${base}.ownerGate`, 'External-cost canaries require ownerGate=true.');
        if (surface.budgetGate === 'none') pushError(errors, `${base}.budgetGate`, 'External-cost canaries require an explicit budget gate.');
      }
    }

    if (live.policy === 'excluded') {
      if (!live.exclusion || typeof live.exclusion !== 'object') {
        pushError(errors, `${base}.liveCanary.exclusion`, 'Excluded canaries require a documented exclusion.');
      } else {
        if (!nonEmptyString(live.exclusion.reason)) pushError(errors, `${base}.liveCanary.exclusion.reason`, 'Exclusion reason is required.');
        if (!nonEmptyString(live.exclusion.trackingIssue)) pushError(errors, `${base}.liveCanary.exclusion.trackingIssue`, 'trackingIssue is required, use none when not applicable.');
        if (live.exclusion.reviewRequired !== true) pushError(errors, `${base}.liveCanary.exclusion.reviewRequired`, 'Excluded canaries must remain reviewRequired.');
      }
    }
  }

  for (const family of ALLOWED_FAMILIES) {
    if (!matrix.surfaces.some((surface) => surface.family === family)) {
      pushError(errors, '$.surfaces', `Release-critical family ${family} has no matrix entry.`);
    }
  }

  return errors;
}

export function validateReleaseEvidence(matrix, evidence, revision, matrixSha256) {
  const errors = [];
  if (!SHA40.test(revision)) pushError(errors, '$.revision', 'Expected a full lowercase 40-character Git SHA.');
  if (!evidence || typeof evidence !== 'object' || Array.isArray(evidence)) {
    return [{ path: '$', message: 'Release evidence must be a JSON object.' }];
  }
  if (evidence.schemaVersion !== EVIDENCE_SCHEMA) pushError(errors, '$.schemaVersion', `Expected ${EVIDENCE_SCHEMA}.`);
  if (evidence.revision !== revision) pushError(errors, '$.revision', 'Evidence revision does not match authoritative revision.');
  if (evidence.matrixSha256 !== matrixSha256) pushError(errors, '$.matrixSha256', 'Evidence does not bind the canonical matrix hash.');
  if (!Array.isArray(evidence.receipts)) {
    pushError(errors, '$.receipts', 'receipts must be an array.');
    return errors;
  }

  const receiptBySurface = new Map();
  for (const [index, receipt] of evidence.receipts.entries()) {
    const base = `$.receipts[${index}]`;
    if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)) {
      pushError(errors, base, 'Receipt must be an object.');
      continue;
    }
    if (!nonEmptyString(receipt.surface)) {
      pushError(errors, `${base}.surface`, 'surface is required.');
      continue;
    }
    if (receiptBySurface.has(receipt.surface)) pushError(errors, `${base}.surface`, `Duplicate receipt for ${receipt.surface}.`);
    receiptBySurface.set(receipt.surface, receipt);
  }

  const knownSurfaces = new Set(matrix.surfaces.map((surface) => surface.surface));
  for (const surfaceName of receiptBySurface.keys()) {
    if (!knownSurfaces.has(surfaceName)) pushError(errors, '$.receipts', `Unknown surface receipt ${surfaceName}.`);
  }

  for (const surface of matrix.surfaces) {
    if (surface.liveCanary.policy === 'excluded') continue;
    const receipt = receiptBySurface.get(surface.surface);
    const base = `$.receipts[${surface.surface}]`;
    if (!receipt) {
      pushError(errors, base, 'Missing required live-canary receipt.');
      continue;
    }
    if (receipt.revision !== revision) pushError(errors, `${base}.revision`, 'Receipt revision mismatch.');
    if (!nonEmptyString(String(receipt.workflowRunId ?? ''))) pushError(errors, `${base}.workflowRunId`, 'workflowRunId is required.');
    if (!ALLOWED_RECEIPT_STATUSES.has(receipt.status)) pushError(errors, `${base}.status`, 'Unknown receipt status.');
    if (receipt.status !== 'passed') pushError(errors, `${base}.status`, 'Release mode requires passed status.');
    if (!SHA256.test(receipt.evidenceSha256 ?? '')) pushError(errors, `${base}.evidenceSha256`, 'evidenceSha256 must be 64 lowercase hex characters.');
    for (const field of surface.evidenceFields) {
      const present = Object.prototype.hasOwnProperty.call(receipt, field);
      const value = receipt[field];
      if (!present || value === null || value === undefined || (typeof value === 'string' && value.trim() === '')) {
        pushError(errors, `${base}.${field}`, `Missing declared evidence field ${field}.`);
      }
    }
    if (surface.liveCanary.mutates === true && receipt.cleanupStatus !== 'passed') {
      pushError(errors, `${base}.cleanupStatus`, 'Mutating canary cleanup must be passed.');
    }
    if (surface.ownerGate === true && receipt.ownerGateStatus !== 'approved') {
      pushError(errors, `${base}.ownerGateStatus`, 'Owner-gated canary requires approved ownerGateStatus.');
    }
    if (surface.liveCanary.externalCost === true && receipt.budgetGateStatus !== 'passed') {
      pushError(errors, `${base}.budgetGateStatus`, 'External-cost canary requires passed budgetGateStatus.');
    }
  }

  return errors;
}

export function resolveRepositoryPath(filePath, cwd = process.cwd()) {
  if (!nonEmptyString(filePath)) throw new Error('Path must be a non-empty string.');
  const root = path.resolve(cwd);
  const resolved = path.resolve(root, filePath);
  const relative = path.relative(root, resolved);
  if (relative.startsWith('..') || path.isAbsolute(relative)) throw new Error(`Path escapes repository root: ${filePath}`);
  return resolved;
}

export function readJson(filePath, cwd = process.cwd()) {
  const resolved = resolveRepositoryPath(filePath, cwd);
  return JSON.parse(fs.readFileSync(resolved, 'utf8'));
}

function authoritativeRevision(explicitRevision) {
  const candidate = explicitRevision || process.env.SOVEREIGN_REVISION || execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  if (!SHA40.test(candidate)) throw new Error('Authoritative revision must be a full lowercase 40-character Git SHA.');
  return candidate;
}

function parseArgs(argv) {
  const args = {
    matrix: DEFAULT_MATRIX_PATH,
    report: DEFAULT_REPORT_PATH,
    mode: 'contract',
    evidence: '',
    revision: '',
  };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--matrix') args.matrix = argv[++index] ?? '';
    else if (token === '--report') args.report = argv[++index] ?? '';
    else if (token === '--mode') args.mode = argv[++index] ?? '';
    else if (token === '--evidence') args.evidence = argv[++index] ?? '';
    else if (token === '--revision') args.revision = argv[++index] ?? '';
    else throw new Error(`Unknown argument: ${token}`);
  }
  if (!['contract', 'release'].includes(args.mode)) throw new Error('Mode must be contract or release.');
  return args;
}

function writeReport(reportPath, report, cwd = process.cwd()) {
  const resolved = resolveRepositoryPath(reportPath, cwd);
  fs.mkdirSync(path.dirname(resolved), { recursive: true });
  fs.writeFileSync(resolved, `${JSON.stringify(report, null, 2)}\n`);
}

function appendSummary(report) {
  const summaryPath = process.env.GITHUB_STEP_SUMMARY;
  if (!summaryPath) return;
  const root = path.resolve(process.cwd());
  const resolved = path.resolve(summaryPath);
  const relative = path.relative(root, resolved);
  if (relative.startsWith('..') || path.isAbsolute(relative)) return;
  const lines = [
    '## Runtime Canary Matrix Gate',
    '',
    `- Mode: \`${report.mode}\``,
    `- Revision: \`${report.revision}\``,
    `- Matrix SHA-256: \`${report.matrixSha256}\``,
    `- Surfaces: **${report.surfaceCount}**`,
    `- Required live canaries: **${report.requiredLiveCanaryCount}**`,
    `- Documented exclusions: **${report.excludedLiveCanaryCount}**`,
    `- Status: **${report.status.toUpperCase()}**`,
    '',
  ];
  fs.appendFileSync(resolved, `${lines.join('\n')}\n`);
}

export function buildReport({ matrix, revision, mode, errors }) {
  const requiredLiveCanaryCount = matrix.surfaces.filter((surface) => surface.liveCanary.policy === 'required').length;
  const excludedLiveCanaryCount = matrix.surfaces.filter((surface) => surface.liveCanary.policy === 'excluded').length;
  return {
    schemaVersion: 'sovereign.runtime-canary-matrix-gate-report.v1',
    status: errors.length === 0 ? 'pass' : 'fail',
    mode,
    revision,
    matrixId: matrix.matrixId,
    matrixSha256: canonicalSha256(matrix),
    surfaceCount: matrix.surfaces.length,
    requiredLiveCanaryCount,
    excludedLiveCanaryCount,
    families: [...new Set(matrix.surfaces.map((surface) => surface.family))].sort(),
    errors,
  };
}

export function runGate({ matrix, evidence = null, revision, mode }) {
  const errors = validateMatrix(matrix);
  const matrixSha256 = canonicalSha256(matrix);
  if (mode === 'release' && errors.length === 0) {
    errors.push(...validateReleaseEvidence(matrix, evidence, revision, matrixSha256));
  }
  return buildReport({ matrix, revision, mode, errors });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const revision = authoritativeRevision(args.revision);
  const matrix = readJson(args.matrix);
  const evidence = args.mode === 'release' ? readJson(args.evidence) : null;
  const report = runGate({ matrix, evidence, revision, mode: args.mode });
  writeReport(args.report, report);
  appendSummary(report);
  console.log(JSON.stringify(report, null, 2));
  if (report.status !== 'pass') process.exitCode = 1;
}

const invokedAsScript = process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href;
if (invokedAsScript) {
  main().catch((error) => {
    const report = {
      schemaVersion: 'sovereign.runtime-canary-matrix-gate-report.v1',
      status: 'fail',
      mode: 'unknown',
      revision: '',
      matrixId: '',
      matrixSha256: '',
      surfaceCount: 0,
      requiredLiveCanaryCount: 0,
      excludedLiveCanaryCount: 0,
      families: [],
      errors: [{ path: '$', message: String(error) }],
    };
    try {
      writeReport(DEFAULT_REPORT_PATH, report);
    } catch {
      // Preserve the original fail-closed error without a second exception.
    }
    console.error(JSON.stringify(report, null, 2));
    process.exitCode = 1;
  });
}
