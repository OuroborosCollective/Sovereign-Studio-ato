import { describe, expect, it, vi } from 'vitest';
import {
  assertWorkflowWatchReportValid,
  buildLocalWorkflowWatchReport,
  fetchWorkflowWatchReport,
  validateWorkflowCheckItem,
  validateWorkflowWatchReport,
  type WorkflowWatchReport,
} from './workflowWatch';

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'ERROR',
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

describe('workflowWatch', () => {
  it('summarizes and validates local checks', () => {
    const report = buildLocalWorkflowWatchReport({
      commitSha: 'abc',
      checks: [{ name: 'ci', status: 'green', source: 'local', summary: 'passed' }],
      checkedAt: 1,
    });
    expect(report.status).toBe('green');
    expect(report.summary).toContain('1 workflow');
    expect(report.evidenceLedger).toBeDefined();
    expect(report.evidenceLedger?.entries.length).toBeGreaterThan(0);
    expect(report.evidenceLedger?.entries.some((e) => e.status === 'success' && e.category === 'workflow-watch')).toBe(true);
    expect(validateWorkflowWatchReport(report).valid).toBe(true);
    expect(() => assertWorkflowWatchReportValid(report)).not.toThrow();
  });

  it('returns warning when commit sha is missing', async () => {
    const report = await fetchWorkflowWatchReport({ repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato' });
    expect(report.status).toBe('unknown');
    expect(report.warnings[0]).toContain('No commit SHA');
    expect(report.evidenceLedger).toBeDefined();
    expect(report.evidenceLedger?.entries.some((e) => e.status === 'unknown')).toBe(true);
    expect(validateWorkflowWatchReport(report).valid).toBe(true);
  });

  it('reads commit statuses and check runs from GitHub-compatible APIs', async () => {
    const fetcher = vi.fn(async (url: RequestInfo | URL) => {
      const textUrl = String(url);
      if (textUrl.endsWith('/status')) {
        return jsonResponse({ statuses: [{ context: 'ci/status', state: 'success', description: 'ok' }] });
      }
      if (textUrl.endsWith('/check-runs')) {
        return jsonResponse({ check_runs: [{ name: 'build', status: 'completed', conclusion: 'failure', output: { summary: 'failed' } }] });
      }
      return jsonResponse({}, false, 404);
    });

    const report = await fetchWorkflowWatchReport({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      commitSha: 'abc',
      fetcher: fetcher as unknown as typeof fetch,
    });

    expect(report.checks).toHaveLength(2);
    expect(report.status).toBe('red');
    expect(report.fixes.join(' ')).toContain('failed check logs');
    expect(report.dependencyLifecycle?.phase).toBe('ready');
    expect(report.dependencyLifecycle?.kind).toBe('workflow');
    expect(report.evidenceLedger).toBeDefined();
    expect(report.evidenceLedger?.entries.some((e) => e.status === 'failure' && e.category === 'workflow-watch')).toBe(true);
    expect(validateWorkflowWatchReport(report).valid).toBe(true);
  });

  it('marks workflow dependency degraded when GitHub endpoints fail', async () => {
    const fetcher = vi.fn(async () => jsonResponse({ message: 'server busy' }, false, 503));

    const report = await fetchWorkflowWatchReport({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      commitSha: 'abc',
      fetcher: fetcher as unknown as typeof fetch,
    });

    expect(report.status).toBe('unknown');
    expect(report.warnings.join(' ')).toContain('503');
    expect(report.dependencyLifecycle?.phase).toBe('degraded');
    expect(report.dependencyLifecycle?.lastFailureAt).toBeGreaterThan(0);
    expect(report.evidenceLedger).toBeDefined();
    expect(report.evidenceLedger?.entries.some((e) => e.status === 'unknown' || e.status === 'failure')).toBe(true);
    expect(validateWorkflowWatchReport(report).valid).toBe(true);
  });

  it('rejects impossible report status mismatches', () => {
    const broken: WorkflowWatchReport = {
      status: 'green',
      checkedAt: 1,
      checks: [{ name: 'ci', status: 'red', source: 'local', summary: 'failed' }],
      errors: [],
      warnings: [],
      fixes: ['fix it'],
      summary: 'wrong',
    };

    const report = validateWorkflowWatchReport(broken);
    expect(report.valid).toBe(false);
    expect(report.errors.join(' ')).toContain('status mismatch');
    expect(() => assertWorkflowWatchReportValid(broken)).toThrow('Workflow watch report is invalid');
  });

  it('rejects check items with secret-like content', () => {
    const validation = validateWorkflowCheckItem({
      name: 'ci',
      status: 'red',
      source: 'local',
      summary: 'failed with token=supersecret123456789',
    });
    expect(validation.valid).toBe(false);
    expect(validation.errors.join(' ')).toContain('secret-like');
  });

  it('returns idle instead of fake-green when no checks are available', async () => {
    const fetcher = vi.fn(async (url: RequestInfo | URL) => {
      const textUrl = String(url);
      if (textUrl.endsWith('/status')) {
        return jsonResponse({ statuses: [] });
      }
      if (textUrl.endsWith('/check-runs')) {
        return jsonResponse({ check_runs: [] });
      }
      return jsonResponse({}, false, 404);
    });

    const report = await fetchWorkflowWatchReport({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      commitSha: 'abc',
      fetcher: fetcher as unknown as typeof fetch,
    });

    expect(report.status).toBe('idle');
    expect(report.checks).toHaveLength(0);
    expect(validateWorkflowWatchReport(report).valid).toBe(true);
  });

  it('returns pending when at least one check is pending', async () => {
    const fetcher = vi.fn(async (url: RequestInfo | URL) => {
      const textUrl = String(url);
      if (textUrl.endsWith('/status')) {
        return jsonResponse({ statuses: [{ context: 'ci', state: 'pending', description: 'running' }] });
      }
      if (textUrl.endsWith('/check-runs')) {
        return jsonResponse({ check_runs: [] });
      }
      return jsonResponse({}, false, 404);
    });

    const report = await fetchWorkflowWatchReport({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      commitSha: 'abc',
      fetcher: fetcher as unknown as typeof fetch,
    });

    expect(report.status).toBe('pending');
    expect(report.checks[0].status).toBe('pending');
    expect(validateWorkflowWatchReport(report).valid).toBe(true);
  });

  it('does not fabricate green status from empty checks', async () => {
    const fetcher = vi.fn(async () => jsonResponse({}, false, 404));

    const report = await fetchWorkflowWatchReport({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      commitSha: 'abc',
      fetcher: fetcher as unknown as typeof fetch,
    });

    expect(report.status).not.toBe('green');
    expect(report.status).toBe('idle');
    expect(validateWorkflowWatchReport(report).valid).toBe(true);
  });
});
