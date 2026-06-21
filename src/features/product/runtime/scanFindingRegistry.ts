import type { RepoFile } from '../../github/types';
import type { WorkflowCheckItem, WorkflowWatchReport } from './workflowWatch';

export type ScanFindingCategory =
  | 'architecture'
  | 'type-error'
  | 'build-logic'
  | 'warning'
  | 'security-leak'
  | 'test-doubles'
  | 'build-artifact'
  | 'runtime-guard'
  | 'auth'
  | 'workflow'
  | 'ci-failure'
  | 'learning-memory'
  | 'diff-preview'
  | 'generated-file'
  | 'docs';

export type ScanFindingSeverity = 'low' | 'medium' | 'high' | 'critical';
export type ScanFindingStatus = 'active' | 'resolved';
export type ScanFindingConfidence = 'path-only' | 'content-scanned' | 'runtime-observed' | 'manual';

export interface ScanFinding {
  id: string;
  category: ScanFindingCategory;
  severity: ScanFindingSeverity;
  status: ScanFindingStatus;
  filePath: string;
  lineNumber?: number;
  title: string;
  description: string;
  fixTips: string;
  confidence: ScanFindingConfidence;
  source: string;
  hits: number;
  firstSeenAt: number;
  lastSeenAt: number;
}

export interface ScanFindingRun {
  id: string;
  source: string;
  startedAt: number;
  completedAt: number;
  totalFindings: number;
  byCategory: Record<ScanFindingCategory, number>;
  bySeverity: Record<ScanFindingSeverity, number>;
  summary: string;
}

export interface ScanFindingRegistry {
  version: 1;
  findings: ScanFinding[];
  runs: ScanFindingRun[];
  updatedAt: number;
}

export interface ScanFindingValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

export interface ScanFindingPublishGate {
  allowed: boolean;
  blockers: ScanFinding[];
  summary: string;
}

const MAX_FINDINGS = 500;
const MAX_RUNS = 80;
const MAX_TEXT = 1400;

export const SCAN_FINDING_CATEGORIES: ScanFindingCategory[] = [
  'architecture',
  'type-error',
  'build-logic',
  'warning',
  'security-leak',
  'test-doubles',
  'build-artifact',
  'runtime-guard',
  'auth',
  'workflow',
  'ci-failure',
  'learning-memory',
  'diff-preview',
  'generated-file',
  'docs',
];

export const SCAN_FINDING_SEVERITIES: ScanFindingSeverity[] = ['low', 'medium', 'high', 'critical'];

const SECRET_PATTERNS = [
  /(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{8,}/g,
  /github_pat_[A-Za-z0-9_]+/g,
  /AIzaSy[A-Za-z0-9_-]{30,}/g,
  /sk-[A-Za-z0-9_-]{12,}/g,
  /gsk_[A-Za-z0-9_-]{12,}/g,
  /Bearer\s+[A-Za-z0-9._~+/=-]{10,}/gi,
  /password\s*[:=]\s*[^\s]+/gi,
  /token\s*[:=]\s*[^\s]+/gi,
];

function stableHash(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function sanitizeText(value: string): string {
  let output = value.trim().slice(0, MAX_TEXT);
  for (const pattern of SECRET_PATTERNS) {
    output = output.replace(pattern, '<redacted-secret>');
  }
  return output;
}

function hasSecret(value: string): boolean {
  return SECRET_PATTERNS.some((pattern) => {
    pattern.lastIndex = 0;
    return pattern.test(value);
  });
}

function makeFindingId(category: ScanFindingCategory, filePath: string, title: string, lineNumber?: number): string {
  return `find-${stableHash(`${category}|${filePath}|${lineNumber ?? 0}|${title}`)}`;
}

function createFinding(input: Omit<ScanFinding, 'id' | 'status' | 'hits' | 'firstSeenAt' | 'lastSeenAt'> & { now: number }): ScanFinding {
  const title = sanitizeText(input.title);
  return {
    id: makeFindingId(input.category, input.filePath, title, input.lineNumber),
    category: input.category,
    severity: input.severity,
    status: 'active',
    filePath: sanitizeText(input.filePath),
    lineNumber: input.lineNumber,
    title,
    description: sanitizeText(input.description),
    fixTips: sanitizeText(input.fixTips),
    confidence: input.confidence,
    source: sanitizeText(input.source),
    hits: 1,
    firstSeenAt: input.now,
    lastSeenAt: input.now,
  };
}

function emptyCategoryCounts(): Record<ScanFindingCategory, number> {
  return Object.fromEntries(SCAN_FINDING_CATEGORIES.map((category) => [category, 0])) as Record<ScanFindingCategory, number>;
}

function emptySeverityCounts(): Record<ScanFindingSeverity, number> {
  return Object.fromEntries(SCAN_FINDING_SEVERITIES.map((severity) => [severity, 0])) as Record<ScanFindingSeverity, number>;
}

function categoryCounts(findings: ScanFinding[]): Record<ScanFindingCategory, number> {
  const counts = emptyCategoryCounts();
  for (const finding of findings) counts[finding.category] += 1;
  return counts;
}

function severityCounts(findings: ScanFinding[]): Record<ScanFindingSeverity, number> {
  const counts = emptySeverityCounts();
  for (const finding of findings) counts[finding.severity] += 1;
  return counts;
}

function workflowText(check: WorkflowCheckItem): string {
  return `${check.name} ${check.conclusion ?? ''} ${check.summary}`.toLowerCase();
}

function inferWorkflowCategory(check: WorkflowCheckItem): ScanFindingCategory {
  const text = workflowText(check);
  if (/auth|permission|token|403|401/.test(text)) return 'auth';
  if (/typescript|tsc|typecheck|type-check|type error/.test(text)) return 'type-error';
  if (/build|vite|rollup|webpack|compile/.test(text)) return 'build-logic';
  if (/test|vitest|jest|playwright|e2e/.test(text)) return 'ci-failure';
  if (/lint|eslint|prettier/.test(text)) return 'ci-failure';
  if (/workflow|action|ci|yaml|yml/.test(text)) return 'workflow';
  return 'ci-failure';
}

function inferWorkflowFilePath(check: WorkflowCheckItem): string {
  const text = workflowText(check);
  if (/auth|permission|token|403|401/.test(text)) return 'GitHub Auth Session';
  if (/typescript|tsc|typecheck|type-check|type error/.test(text)) return 'tsconfig.json';
  if (/lint|eslint|prettier/.test(text)) return 'eslint.config.*';
  if (/test|vitest|jest/.test(text)) return 'src/**/*.test.ts';
  if (/playwright|e2e/.test(text)) return 'e2e/**/*';
  if (/build|vite|rollup|webpack|compile/.test(text)) return 'vite.config.*';
  if (/install|pnpm|npm|lockfile|dependency/.test(text)) return 'package.json';
  if (/workflow|action|ci|yaml|yml/.test(text)) return '.github/workflows/*';
  return '.github/workflows/*';
}

function severityForWorkflowCheck(check: WorkflowCheckItem): ScanFindingSeverity {
  if (check.status === 'red') return 'high';
  if (check.status === 'pending') return 'medium';
  return 'low';
}

export function createScanFindingRegistry(now = Date.now()): ScanFindingRegistry {
  return { version: 1, findings: [], runs: [], updatedAt: now };
}

export function collectWorkflowWatchFindings(
  report: WorkflowWatchReport | null,
  now = Date.now(),
  source = 'workflow-watch',
): ScanFinding[] {
  if (!report) return [];
  const findings: ScanFinding[] = [];

  for (const check of report.checks) {
    if (check.status !== 'red' && check.status !== 'pending') continue;
    const category = inferWorkflowCategory(check);
    const filePath = inferWorkflowFilePath(check);
    const blocked = check.status === 'red';
    findings.push(createFinding({
      category,
      severity: severityForWorkflowCheck(check),
      filePath,
      lineNumber: 1,
      title: blocked ? `CI check failed: ${check.name}` : `CI check pending: ${check.name}`,
      description: `${check.name} reported ${check.status}${check.conclusion ? ` (${check.conclusion})` : ''}. ${check.summary}`,
      fixTips: blocked
        ? 'Inspect the failed workflow job/step logs, repair the likely files, then run Workflow Watch again to prove the finding is resolved.'
        : 'Wait for this check to finish before publishing another repair package.',
      confidence: 'runtime-observed',
      source,
      now,
    }));
  }

  for (const error of report.errors) {
    findings.push(createFinding({
      category: /token|permission|403|401/i.test(error) ? 'auth' : 'workflow',
      severity: 'high',
      filePath: /token|permission|403|401/i.test(error) ? 'GitHub Auth Session' : '.github/workflows/*',
      lineNumber: 1,
      title: 'Workflow Watch runtime error',
      description: error,
      fixTips: 'Check GitHub token permissions, repository visibility, workflow availability and retry Workflow Watch.',
      confidence: 'runtime-observed',
      source,
      now,
    }));
  }

  return findings;
}

export function collectRepoPathFindings(files: RepoFile[], now = Date.now()): ScanFinding[] {
  const findings: ScanFinding[] = [];
  const paths = files.map((file) => file.path);
  const lowerPaths = paths.map((path) => path.toLowerCase());
  const hasWorkflow = lowerPaths.some((path) => path.startsWith('.github/workflows/') && (path.endsWith('.yml') || path.endsWith('.yaml')));
  const hasTests = lowerPaths.some((path) => /(?:\.test\.|\.spec\.|__tests__\/|\/test\/|\/tests\/)/.test(path));
  const hasReadme = lowerPaths.includes('readme.md');

  for (const file of files) {
    const path = file.path;
    const lower = path.toLowerCase();
    const size = file.size ?? 0;

    if (/^\.env(?:\.|$)|(^|\/)(secrets?|credentials?|private-key|id_rsa)(\.|\/|$)/.test(lower)) {
      findings.push(createFinding({
        category: 'security-leak',
        severity: lower === '.env' ? 'critical' : 'high',
        filePath: path,
        lineNumber: 1,
        title: 'Secret-looking repository path detected',
        description: 'A path suggests secrets, credentials, private keys, or environment variables may be committed.',
        fixTips: 'Remove secret files from version control, rotate exposed keys, and keep only safe examples such as .env.example.',
        confidence: 'path-only',
        source: 'repo-path-scan',
        now,
      }));
    }

    if (/(^|\/)(node_modules|dist|build|coverage)(\/|$)/.test(lower)) {
      findings.push(createFinding({
        category: 'build-artifact',
        severity: 'high',
        filePath: path,
        lineNumber: 1,
        title: 'Build artifact committed to repository tree',
        description: 'Generated dependency or build output folders should normally not be committed.',
        fixTips: 'Add this path to .gitignore and remove already committed artifacts from version control.',
        confidence: 'path-only',
        source: 'repo-path-scan',
        now,
      }));
    }

    if (/(mock|stub|fake|fixture|sample)/.test(lower)) {
      findings.push(createFinding({
        category: 'test-doubles',
        severity: 'medium',
        filePath: path,
        lineNumber: 1,
        title: 'Mock/stub/sample path detected',
        description: 'The path suggests test doubles or sample-only behavior. This may be fine in tests, but risky in production logic.',
        fixTips: 'Confirm this file is test-only or replace placeholder behavior with real runtime logic.',
        confidence: 'path-only',
        source: 'repo-path-scan',
        now,
      }));
    }

    if (/(todo|fixme|wip)/.test(lower)) {
      findings.push(createFinding({
        category: 'warning',
        severity: 'low',
        filePath: path,
        lineNumber: 1,
        title: 'Unfinished-work marker in path',
        description: 'The path name suggests unfinished, temporary, or work-in-progress code.',
        fixTips: 'Review whether this file should remain in the shipping tree or be renamed/documented.',
        confidence: 'path-only',
        source: 'repo-path-scan',
        now,
      }));
    }

    if (size > 750_000 && file.type === 'blob') {
      findings.push(createFinding({
        category: 'architecture',
        severity: 'medium',
        filePath: path,
        lineNumber: 1,
        title: 'Very large source file or asset detected',
        description: 'Large files can slow scans, reviews, diffs, and mobile usage.',
        fixTips: 'Consider splitting large source files or moving heavy assets into an asset pipeline.',
        confidence: 'path-only',
        source: 'repo-path-scan',
        now,
      }));
    }
  }

  if (!hasWorkflow) {
    findings.push(createFinding({
      category: 'workflow',
      severity: 'medium',
      filePath: '.github/workflows',
      lineNumber: 1,
      title: 'No GitHub Actions workflow detected',
      description: 'The repository tree does not show a GitHub Actions workflow file.',
      fixTips: 'Add a minimal CI workflow for type-check, lint, test and build before relying on Full Auto.',
      confidence: 'path-only',
      source: 'repo-path-scan',
      now,
    }));
  }

  if (!hasTests) {
    findings.push(createFinding({
      category: 'warning',
      severity: 'medium',
      filePath: 'tests',
      lineNumber: 1,
      title: 'No test files detected',
      description: 'The repository tree does not show obvious test files.',
      fixTips: 'Add tests for runtime modules and critical publish/guard paths.',
      confidence: 'path-only',
      source: 'repo-path-scan',
      now,
    }));
  }

  if (!hasReadme) {
    findings.push(createFinding({
      category: 'docs',
      severity: 'low',
      filePath: 'README.md',
      lineNumber: 1,
      title: 'README missing from repository root',
      description: 'No root README.md was detected in the repository tree.',
      fixTips: 'Add a concise README with purpose, setup, scripts, safety rules and contribution flow.',
      confidence: 'path-only',
      source: 'repo-path-scan',
      now,
    }));
  }

  return findings;
}

export function validateScanFinding(finding: ScanFinding): ScanFindingValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!finding.id.trim()) errors.push('Finding id is required.');
  if (!SCAN_FINDING_CATEGORIES.includes(finding.category)) errors.push(`Unknown finding category: ${finding.category}`);
  if (!SCAN_FINDING_SEVERITIES.includes(finding.severity)) errors.push(`Unknown finding severity: ${finding.severity}`);
  if (!['active', 'resolved'].includes(finding.status)) errors.push(`Unknown finding status: ${finding.status}`);
  if (!finding.filePath.trim()) errors.push('Finding filePath is required.');
  if (!finding.title.trim()) errors.push('Finding title is required.');
  if (!finding.description.trim()) errors.push('Finding description is required.');
  if (!finding.fixTips.trim()) errors.push('Finding fixTips are required.');
  if (finding.hits < 1 || !Number.isFinite(finding.hits)) errors.push('Finding hits must be positive.');
  if (finding.firstSeenAt > finding.lastSeenAt) errors.push('Finding firstSeenAt must not be newer than lastSeenAt.');
  if ([finding.filePath, finding.title, finding.description, finding.fixTips, finding.source].some(hasSecret)) {
    errors.push('Finding contains unredacted secret-like content.');
  }
  if (finding.confidence === 'path-only') warnings.push('Finding is path-only and should not be treated as content scan proof.');

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in scan finding.`,
  };
}

export function validateScanFindingRegistry(registry: ScanFindingRegistry): ScanFindingValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (registry.version !== 1) errors.push('Unsupported scan finding registry version.');
  if (registry.findings.length > MAX_FINDINGS) errors.push(`Too many findings: ${registry.findings.length}`);
  if (registry.runs.length > MAX_RUNS) errors.push(`Too many scan runs: ${registry.runs.length}`);

  const ids = new Set<string>();
  for (const finding of registry.findings) {
    if (ids.has(finding.id)) errors.push(`Duplicate finding id: ${finding.id}`);
    ids.add(finding.id);
    const report = validateScanFinding(finding);
    errors.push(...report.errors.map((error) => `${finding.id}: ${error}`));
    warnings.push(...report.warnings.map((warning) => `${finding.id}: ${warning}`));
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${registry.findings.length} finding(s), ${registry.runs.length} run(s), ${errors.length} error(s), ${warnings.length} warning(s).`,
  };
}

export function assertScanFindingRegistryValid(registry: ScanFindingRegistry): void {
  const report = validateScanFindingRegistry(registry);
  if (!report.valid) throw new Error(`Scan finding registry is invalid: ${report.errors.join(' | ')}`);
}

export function createScanFindingRun(source: string, findings: ScanFinding[], startedAt: number, completedAt: number): ScanFindingRun {
  const byCategory = categoryCounts(findings);
  const bySeverity = severityCounts(findings);
  const high = bySeverity.high + bySeverity.critical;
  return {
    id: `scan-${stableHash(`${source}|${startedAt}|${completedAt}|${findings.map((finding) => finding.id).join(',')}`)}`,
    source: sanitizeText(source),
    startedAt,
    completedAt,
    totalFindings: findings.length,
    byCategory,
    bySeverity,
    summary: `Scan ${source} abgeschlossen: ${findings.length} finding(s), ${high} high/critical.`,
  };
}

export function applyScanFindings(
  registry: ScanFindingRegistry,
  source: string,
  findings: ScanFinding[],
  startedAt = Date.now(),
  completedAt = Date.now(),
): ScanFindingRegistry {
  assertScanFindingRegistryValid(registry);
  for (const finding of findings) {
    const report = validateScanFinding(finding);
    if (!report.valid) throw new Error(`Invalid scan finding ${finding.id}: ${report.errors.join(' | ')}`);
  }

  const mergedExisting = registry.findings.map((existing) => {
    const incoming = findings.find((finding) => finding.id === existing.id);
    if (incoming) {
      return {
        ...incoming,
        firstSeenAt: existing.firstSeenAt,
        hits: existing.hits + 1,
        lastSeenAt: completedAt,
        status: 'active' as const,
      };
    }
    if (existing.source === source && existing.status === 'active') {
      return { ...existing, status: 'resolved' as const, lastSeenAt: completedAt };
    }
    return existing;
  });

  const existingIds = new Set(registry.findings.map((finding) => finding.id));
  const newFindings = findings.filter((finding) => !existingIds.has(finding.id));
  const nextFindings = [...newFindings, ...mergedExisting].slice(0, MAX_FINDINGS);
  const run = createScanFindingRun(source, findings, startedAt, completedAt);
  const nextRegistry = {
    version: 1 as const,
    findings: nextFindings,
    runs: [run, ...registry.runs].slice(0, MAX_RUNS),
    updatedAt: completedAt,
  };
  assertScanFindingRegistryValid(nextRegistry);
  return nextRegistry;
}

export function groupScanFindingsByCategory(findings: ScanFinding[]): Record<ScanFindingCategory, ScanFinding[]> {
  const grouped = Object.fromEntries(SCAN_FINDING_CATEGORIES.map((category) => [category, []])) as Record<ScanFindingCategory, ScanFinding[]>;
  for (const finding of findings) grouped[finding.category].push(finding);
  return grouped;
}

export function getBlockingScanFindings(registry: ScanFindingRegistry): ScanFinding[] {
  assertScanFindingRegistryValid(registry);
  return registry.findings.filter((finding) => finding.status === 'active' && (
    finding.severity === 'critical'
    || finding.category === 'security-leak'
    || finding.category === 'auth'
    || finding.category === 'ci-failure'
  ));
}

export function buildScanFindingPublishGate(registry: ScanFindingRegistry): ScanFindingPublishGate {
  const blockers = getBlockingScanFindings(registry);
  return {
    allowed: blockers.length === 0,
    blockers,
    summary: blockers.length
      ? `Publish blocked by ${blockers.length} active scan finding(s). Re-scan after fixing to prove resolution.`
      : 'Publish gate clear: no active blocking scan findings.',
  };
}

export function assertNoBlockingScanFindingsBeforePublish(registry: ScanFindingRegistry): void {
  const gate = buildScanFindingPublishGate(registry);
  if (!gate.allowed) throw new Error(gate.summary);
}

export function summarizeScanFindingRegistry(registry: ScanFindingRegistry): string {
  const active = registry.findings.filter((finding) => finding.status === 'active');
  const counts = severityCounts(active);
  return `${active.length} active finding(s): ${counts.critical} critical, ${counts.high} high, ${counts.medium} medium, ${counts.low} low.`;
}
