import { describe, expect, it } from 'vitest';
import { buildSovereignHealthReport } from './sovereignHealth';
import { createInitialTelemetryState } from './sovereignTelemetry';

describe('sovereignHealth', () => {
  it('is idle without repo snapshot', () => {
    const report = buildSovereignHealthReport({ repoFiles: [] });
    expect(report.status).toBe('idle');
    expect(report.recommendations[0]).toContain('Load a real repository');
  });

  it('turns red for high-risk repo paths', () => {
    const report = buildSovereignHealthReport({
      repoFiles: [{ path: '.env', type: 'blob' }],
      telemetry: createInitialTelemetryState(),
    });
    expect(report.status).toBe('red');
    expect(report.criticalRisks).toBeGreaterThan(0);
  });

  it('turns warning for pending workflow checks', () => {
    const report = buildSovereignHealthReport({
      repoFiles: [{ path: 'README.md', type: 'blob' }],
      workflowWatch: {
        status: 'pending',
        checkedAt: 1,
        checks: [{ name: 'ci', status: 'pending', source: 'local', summary: 'running' }],
        errors: [],
        warnings: [],
        fixes: [],
        summary: 'pending',
      },
    });
    expect(report.status).toBe('warning');
    expect(report.branchDelta).toBe(0.5);
  });
});
