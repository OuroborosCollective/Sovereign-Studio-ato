import { beforeEach, describe, expect, it } from 'vitest';
import {
  buildSovereignHealthReport,
  clearLatestSovereignHealthReportForTests,
  getLatestSovereignHealthReport,
} from './sovereignHealth';
import { appendTelemetryEvent, createInitialTelemetryState, createTelemetryEvent } from './sovereignTelemetry';
import type { GeneratedFileReviewReport } from './generatedFileReview';

function highRiskGeneratedReview(): GeneratedFileReviewReport {
  return {
    files: [{
      path: 'dist/generated.js',
      reason: 'forbidden generated path',
      lineCount: 1,
      charCount: 1,
      risk: 'high',
      flags: ['forbidden-path'],
      preview: 'x',
    }],
    totalFiles: 1,
    totalLines: 1,
    totalChars: 1,
    highRiskCount: 1,
    mediumRiskCount: 0,
    planOnlyCount: 0,
    actionableFileCount: 0,
    selfReview: {
      accepted: false,
      rewriteRequired: true,
      reason: 'high-risk generated output',
      learningSignal: 'high-risk-output-rejected',
      rewritePlan: ['Remove forbidden paths.'],
    },
    summary: '1 high-risk generated file.',
  };
}

describe('sovereignHealth', () => {
  beforeEach(() => {
    clearLatestSovereignHealthReportForTests();
  });

  it('is idle without repo snapshot', () => {
    const report = buildSovereignHealthReport({ repoFiles: [] });
    expect(report.status).toBe('idle');
    expect(report.recommendations[0]).toContain('Load a real repository');
  });

  it('remembers the latest health report for runtime bridges', () => {
    const report = buildSovereignHealthReport({ repoFiles: [{ path: 'README.md', type: 'blob' }] });
    expect(getLatestSovereignHealthReport()).toBe(report);
    expect(getLatestSovereignHealthReport()?.status).toBe('green');
  });

  it('keeps high-risk existing repo paths as warnings instead of red blockers', () => {
    const report = buildSovereignHealthReport({
      repoFiles: [{ path: 'dist/generated.js', type: 'blob' }],
      telemetry: createInitialTelemetryState(),
    });
    expect(report.status).toBe('warning');
    expect(report.criticalRisks).toBe(0);
    expect(report.totalIssues).toBeGreaterThan(0);
    expect(report.branchDelta).toBe(0.5);
    expect(report.recommendations.join(' ')).toContain('do not block planning');
  });

  it('turns red for high-risk generated output', () => {
    const report = buildSovereignHealthReport({
      repoFiles: [{ path: 'README.md', type: 'blob' }],
      generatedFileReview: highRiskGeneratedReview(),
      telemetry: createInitialTelemetryState(),
    });
    expect(report.status).toBe('red');
    expect(report.criticalRisks).toBe(1);
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
