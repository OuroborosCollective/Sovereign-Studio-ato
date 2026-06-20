import { describe, expect, it } from 'vitest';
import { buildSovereignHealthReport } from './sovereignHealth';
import { appendTelemetryEvent, createInitialTelemetryState, createTelemetryEvent } from './sovereignTelemetry';

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

  it('turns red for blocked dependency telemetry', () => {
    const telemetry = appendTelemetryEvent(
      createInitialTelemetryState(),
      createTelemetryEvent('github', 'error', 'dependency:github:blocked', 'GitHub dependency unavailable.', {
        dependencyKey: 'github-repo-tree',
        dependencySource: 'github',
      }, 1_000),
    );

    const report = buildSovereignHealthReport({
      repoFiles: [{ path: 'README.md', type: 'blob' }],
      telemetry,
    });

    expect(report.status).toBe('red');
    expect(report.criticalRisks).toBe(1);
    expect(report.branchDelta).toBe(1);
    expect(report.recommendations.join(' ')).toContain('blocked dependency');
  });

  it('turns warning for degraded dependency telemetry', () => {
    const telemetry = appendTelemetryEvent(
      createInitialTelemetryState(),
      createTelemetryEvent('workflow', 'warning', 'dependency:workflow:degraded', 'Workflow dependency degraded.', {
        dependencyKey: 'github-workflow-watch',
        dependencySource: 'workflow',
      }, 1_000),
    );

    const report = buildSovereignHealthReport({
      repoFiles: [{ path: 'README.md', type: 'blob' }],
      telemetry,
    });

    expect(report.status).toBe('warning');
    expect(report.totalIssues).toBe(1);
    expect(report.branchDelta).toBe(0.5);
    expect(report.recommendations.join(' ')).toContain('degraded dependency');
  });

  it('turns warning for waiting dependency telemetry', () => {
    const telemetry = appendTelemetryEvent(
      createInitialTelemetryState(),
      createTelemetryEvent('memory', 'info', 'dependency:pattern-memory:idle', 'Pattern memory waiting.', {
        dependencyKey: 'pattern-memory-store',
        dependencySource: 'pattern-memory',
      }, 1_000),
    );

    const report = buildSovereignHealthReport({
      repoFiles: [{ path: 'README.md', type: 'blob' }],
      telemetry,
    });

    expect(report.status).toBe('warning');
    expect(report.totalIssues).toBe(1);
    expect(report.recommendations.join(' ')).toContain('waiting dependency');
  });
});
