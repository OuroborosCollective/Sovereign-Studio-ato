import { buildGitHubHeaders } from '../../github/githubAuthSession';
import { parseGithubRepoUrl } from '../../github/utils';
import {
  createSovereignDependencyLifecycleState,
  recordSovereignDependencyFailure,
  recordSovereignDependencySuccess,
  startSovereignDependencyCheck,
  type SovereignDependencyLifecycleState,
} from './sovereignDependencyLifecycle';

export type WorkflowWatchStatus = 'idle' | 'pending' | 'green' | 'red' | 'unknown';

export interface WorkflowWatchInput {
  repoUrl: string;
  token?: string;
  commitSha?: string;
  branch?: string;
  fetcher?: typeof fetch;
}

export interface WorkflowCheckItem {
  name: string;
  status: WorkflowWatchStatus;
  conclusion?: string;
  url?: string;
  source: 'commit-status' | 'check-run' | 'local';
  summary: string;
}

export interface WorkflowWatchReport {
  status: WorkflowWatchStatus;
  commitSha?: string;
  branch?: string;
  checkedAt: number;
  checks: WorkflowCheckItem[];
  errors: string[];
  warnings: string[];
  fixes: string[];
  summary: string;
  dependencyLifecycle?: SovereignDependencyLifecycleState;
}

export interface WorkflowWatchValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

interface GitHubCombinedStatusResponse {
  state?: string;
  statuses?: Array<{
    context?: string;
    state?: string;
    target_url?: string;
    description?: string;
  }>;
}

interface GitHubCheckRunsResponse {
  check_runs?: Array<{
    name?: string;
    status?: string;
    conclusion?: string | null;
    html_url?: string;
    output?: { title?: string | null; summary?: string | null };
  }>;
}

const WORKFLOW_STATUSES: WorkflowWatchStatus[] = ['idle', 'pending', 'green', 'red', 'unknown'];
const WORKFLOW_CHECK_SOURCES: WorkflowCheckItem['source'][] = ['commit-status', 'check-run', 'local'];

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

function hasSecret(value: string): boolean {
  return SECRET_PATTERNS.some((pattern) => {
    pattern.lastIndex = 0;
    return pattern.test(value);
  });
}

function createWorkflowDependency(): SovereignDependencyLifecycleState {
  return createSovereignDependencyLifecycleState(
    'github-workflow-watch',
    'workflow',
    'GitHub workflow checks have not been watched yet.',
  );
}

function mapStatus(value?: string | null): WorkflowWatchStatus {
  const normalized = (value ?? '').toLowerCase();
  if (normalized === 'success' || normalized === 'completed' || normalized === 'neutral' || normalized === 'skipped') return 'green';
  if (normalized === 'failure' || normalized === 'failed' || normalized === 'error' || normalized === 'cancelled' || normalized === 'timed_out' || normalized === 'action_required') return 'red';
  if (normalized === 'pending' || normalized === 'queued' || normalized === 'in_progress' || normalized === 'requested' || normalized === 'waiting') return 'pending';
  return 'unknown';
}

function summarizeStatus(checks: WorkflowCheckItem[], errors: string[], warnings: string[]): WorkflowWatchStatus {
  if (errors.length > 0) return 'red';
  if (checks.some((check) => check.status === 'red')) return 'red';
  if (checks.some((check) => check.status === 'pending')) return 'pending';
  if (checks.length > 0 && checks.every((check) => check.status === 'green')) return 'green';
  if (warnings.length > 0) return 'unknown';
  return checks.length ? 'unknown' : 'idle';
}

function buildFixes(status: WorkflowWatchStatus, checks: WorkflowCheckItem[], errors: string[]): string[] {
  const fixes: string[] = [];
  if (errors.length) fixes.push('Check GitHub token permissions and repository visibility.');
  if (checks.some((check) => check.status === 'red')) fixes.push('Open the failed check logs and generate a focused fix package from the failing step names.');
  if (checks.some((check) => check.status === 'pending')) fixes.push('Wait for pending checks before preparing a repair package.');
  if (!checks.length && status !== 'red') fixes.push('No GitHub checks were found for this commit yet. Re-run watch after Actions start.');
  return fixes;
}

export function validateWorkflowCheckItem(check: WorkflowCheckItem): WorkflowWatchValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!check.name.trim()) errors.push('Workflow check name is required.');
  if (!WORKFLOW_STATUSES.includes(check.status)) errors.push(`Unknown workflow check status: ${check.status}`);
  if (!WORKFLOW_CHECK_SOURCES.includes(check.source)) errors.push(`Unknown workflow check source: ${check.source}`);
  if (!check.summary.trim()) errors.push('Workflow check summary is required.');
  if (check.url && !/^https?:\/\//i.test(check.url)) warnings.push('Workflow check URL is not an HTTP URL.');
  if ([check.name, check.conclusion ?? '', check.url ?? '', check.summary].some(hasSecret)) {
    errors.push('Workflow check contains unredacted secret-like content.');
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in workflow check.`,
  };
}

export function validateWorkflowWatchReport(report: WorkflowWatchReport): WorkflowWatchValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!WORKFLOW_STATUSES.includes(report.status)) errors.push(`Unknown workflow report status: ${report.status}`);
  if (!Number.isFinite(report.checkedAt) || report.checkedAt <= 0) errors.push('Workflow report checkedAt must be a positive timestamp.');
  if (!Array.isArray(report.checks)) errors.push('Workflow report checks must be an array.');
  if (!Array.isArray(report.errors)) errors.push('Workflow report errors must be an array.');
  if (!Array.isArray(report.warnings)) errors.push('Workflow report warnings must be an array.');
  if (!Array.isArray(report.fixes)) errors.push('Workflow report fixes must be an array.');
  if (!report.summary.trim()) errors.push('Workflow report summary is required.');

  for (const check of report.checks ?? []) {
    const checkReport = validateWorkflowCheckItem(check);
    errors.push(...checkReport.errors.map((error) => `${check.name || 'check'}: ${error}`));
    warnings.push(...checkReport.warnings.map((warning) => `${check.name || 'check'}: ${warning}`));
  }

  if ([report.commitSha ?? '', report.branch ?? '', report.summary, ...report.errors, ...report.warnings, ...report.fixes, report.dependencyLifecycle?.message ?? ''].some(hasSecret)) {
    errors.push('Workflow report contains unredacted secret-like content.');
  }

  const expectedStatus = summarizeStatus(report.checks, report.errors, report.warnings);
  if (report.status !== expectedStatus) {
    errors.push(`Workflow report status mismatch: expected ${expectedStatus}, got ${report.status}.`);
  }

  if (report.status === 'red' && report.fixes.length === 0) warnings.push('Red workflow report should include at least one fix hint.');
  if (!report.checks.length && !report.errors.length && !report.warnings.length && report.status !== 'idle') {
    warnings.push('Workflow report has no checks, errors or warnings but is not idle.');
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in workflow report.`,
  };
}

export function assertWorkflowWatchReportValid(report: WorkflowWatchReport): void {
  const validation = validateWorkflowWatchReport(report);
  if (!validation.valid) {
    throw new Error(`Workflow watch report is invalid: ${validation.errors.join(' | ')}`);
  }
}

export function buildLocalWorkflowWatchReport(input: {
  commitSha?: string;
  branch?: string;
  checks?: WorkflowCheckItem[];
  errors?: string[];
  warnings?: string[];
  checkedAt?: number;
  dependencyLifecycle?: SovereignDependencyLifecycleState;
}): WorkflowWatchReport {
  const checks = input.checks ?? [];
  const errors = input.errors ?? [];
  const warnings = input.warnings ?? [];
  const status = summarizeStatus(checks, errors, warnings);
  const fixes = buildFixes(status, checks, errors);
  const report = {
    status,
    commitSha: input.commitSha,
    branch: input.branch,
    checkedAt: input.checkedAt ?? Date.now(),
    checks,
    errors,
    warnings,
    fixes,
    summary: `${checks.length} workflow check(s), ${errors.length} error(s), ${warnings.length} warning(s). Status: ${status}.`,
    dependencyLifecycle: input.dependencyLifecycle,
  } satisfies WorkflowWatchReport;

  assertWorkflowWatchReportValid(report);
  return report;
}

export async function fetchWorkflowWatchReport(input: WorkflowWatchInput): Promise<WorkflowWatchReport> {
  const parsed = parseGithubRepoUrl(input.repoUrl);
  if (!parsed) {
    return buildLocalWorkflowWatchReport({
      commitSha: input.commitSha,
      branch: input.branch,
      errors: ['Invalid GitHub repository URL.'],
    });
  }
  if (!input.commitSha?.trim()) {
    return buildLocalWorkflowWatchReport({
      branch: input.branch,
      warnings: ['No commit SHA is available yet. Create a Draft PR first.'],
    });
  }

  const fetcher = input.fetcher ?? fetch;
  const apiBase = `https://api.github.com/repos/${parsed.owner}/${parsed.repo}`;
  const headers = buildGitHubHeaders({ token: input.token });
  const checks: WorkflowCheckItem[] = [];
  const errors: string[] = [];
  const warnings: string[] = [];
  let dependencyLifecycle = startSovereignDependencyCheck(createWorkflowDependency()).state;
  let dependencyFailed = false;

  try {
    const statusResponse = await fetcher(`${apiBase}/commits/${encodeURIComponent(input.commitSha)}/status`, { headers });
    if (statusResponse.ok) {
      const statusPayload = await statusResponse.json() as GitHubCombinedStatusResponse;
      for (const status of statusPayload.statuses ?? []) {
        const mapped = mapStatus(status.state);
        checks.push({
          name: status.context ?? 'commit-status',
          status: mapped,
          conclusion: status.state,
          url: status.target_url,
          source: 'commit-status',
          summary: status.description ?? `Commit status is ${status.state ?? 'unknown'}.`,
        });
      }
    } else if (statusResponse.status !== 404) {
      dependencyFailed = true;
      const message = `Commit status endpoint returned ${statusResponse.status}.`;
      warnings.push(message);
      dependencyLifecycle = recordSovereignDependencyFailure(dependencyLifecycle, {}, message).state;
    }
  } catch (error) {
    dependencyFailed = true;
    const message = error instanceof Error ? error.message : 'Commit status request failed.';
    warnings.push(message);
    dependencyLifecycle = recordSovereignDependencyFailure(dependencyLifecycle, {}, message).state;
  }

  try {
    const checksResponse = await fetcher(`${apiBase}/commits/${encodeURIComponent(input.commitSha)}/check-runs`, { headers });
    if (checksResponse.ok) {
      const checksPayload = await checksResponse.json() as GitHubCheckRunsResponse;
      for (const check of checksPayload.check_runs ?? []) {
        const mapped = mapStatus(check.conclusion ?? check.status);
        checks.push({
          name: check.name ?? 'check-run',
          status: mapped,
          conclusion: check.conclusion ?? check.status ?? undefined,
          url: check.html_url,
          source: 'check-run',
          summary: check.output?.summary ?? check.output?.title ?? `Check run is ${check.conclusion ?? check.status ?? 'unknown'}.`,
        });
      }
    } else if (checksResponse.status !== 404) {
      dependencyFailed = true;
      const message = `Check-runs endpoint returned ${checksResponse.status}.`;
      warnings.push(message);
      dependencyLifecycle = recordSovereignDependencyFailure(dependencyLifecycle, {}, message).state;
    }
  } catch (error) {
    dependencyFailed = true;
    const message = error instanceof Error ? error.message : 'Check-runs request failed.';
    warnings.push(message);
    dependencyLifecycle = recordSovereignDependencyFailure(dependencyLifecycle, {}, message).state;
  }

  if (!dependencyFailed) {
    dependencyLifecycle = recordSovereignDependencySuccess(dependencyLifecycle, 'GitHub workflow watch endpoints responded.').state;
  }

  return buildLocalWorkflowWatchReport({
    commitSha: input.commitSha,
    branch: input.branch,
    checks,
    errors,
    warnings,
    dependencyLifecycle,
  });
}
