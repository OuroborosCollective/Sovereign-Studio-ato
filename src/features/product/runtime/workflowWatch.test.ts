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
    expect(validateWorkflowWatchReport(report).valid).toBe(true);
    expect(() => assertWorkflowWatchReportValid(report)).not.toThrow();
  });

  it('returns warning when commit sha is missing', async () => {
    const report = await fetchWorkflowWatchReport({ repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato' });
    expect(report.status).toBe('unknown');
    expect(report.warnings[0]).toContain('No commit SHA');
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
});
