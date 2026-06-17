import { describe, expect, it } from 'vitest';
import {
  applyScanFindings,
  buildScanFindingPublishGate,
  collectRepoPathFindings,
  collectWorkflowWatchFindings,
  createScanFindingRegistry,
  groupScanFindingsByCategory,
  summarizeScanFindingRegistry,
  validateScanFinding,
  validateScanFindingRegistry,
  type ScanFinding,
} from './scanFindingRegistry';
import {
  applyScanFindingsWithBookkeeping,
  applyWorkflowWatchFindingsWithBookkeeping,
  markSourceResolvedByCleanScan,
} from './scanFindingBookkeeping';
import { applyWorkflowScanAndBuildGate } from './scanFindingWorkflowBridge';
import type { WorkflowWatchReport } from './workflowWatch';

describe('scanFindingRegistry', () => {
  it('collects categorized findings with direct paths and details', () => {
    const findings = collectRepoPathFindings([
      { path: '.env', type: 'blob', size: 20 },
      { path: 'node_modules/pkg/index.js', type: 'blob', size: 10 },
      { path: 'src/test/FakeService.test.ts', type: 'blob', size: 100 },
      { path: 'src/TODO-runtime.ts', type: 'blob', size: 100 },
      { path: 'README.md', type: 'blob', size: 100 },
    ], 1);

    expect(findings.map((finding) => finding.category)).toContain('security-leak');
    expect(findings.map((finding) => finding.category)).toContain('build-artifact');
    expect(findings.map((finding) => finding.category)).toContain('test-doubles');
    expect(findings.map((finding) => finding.category)).toContain('warning');
    expect(findings[0]).toMatchObject({ filePath: '.env', lineNumber: 1 });
    expect(findings.every((finding) => finding.description.length > 0 && finding.fixTips.length > 0)).toBe(true);
  });

  it('creates scan runs with category and severity summaries', () => {
    const startedAt = 10;
    const completedAt = 20;
    const findings = collectRepoPathFindings([
      { path: '.env', type: 'blob', size: 20 },
      { path: 'README.md', type: 'blob', size: 100 },
      { path: '.github/workflows/ci.yml', type: 'blob', size: 100 },
      { path: 'src/app.test.ts', type: 'blob', size: 100 },
    ], startedAt);

    const registry = applyScanFindings(createScanFindingRegistry(1), 'repo-path-scan', findings, startedAt, completedAt);
    expect(registry.runs).toHaveLength(1);
    expect(registry.runs[0].summary).toContain('abgeschlossen');
    expect(registry.runs[0].byCategory['security-leak']).toBe(1);
    expect(registry.runs[0].bySeverity.critical).toBe(1);
    expect(validateScanFindingRegistry(registry).valid).toBe(true);
  });

  it('increments repeated findings and keeps resolved findings in bookkeeping history', () => {
    const firstFindings = collectRepoPathFindings([
      { path: '.env', type: 'blob', size: 20 },
      { path: 'README.md', type: 'blob', size: 100 },
    ], 1);
    const first = applyScanFindingsWithBookkeeping(createScanFindingRegistry(1), 'repo-path-scan', firstFindings, 1, 2);

    const secondFindings = collectRepoPathFindings([
      { path: 'README.md', type: 'blob', size: 100 },
      { path: '.github/workflows/ci.yml', type: 'blob', size: 100 },
      { path: 'src/app.test.ts', type: 'blob', size: 100 },
    ], 3);
    const second = applyScanFindingsWithBookkeeping(first, 'repo-path-scan', secondFindings, 3, 4);

    const envFinding = second.findings.find((finding) => finding.filePath === '.env');
    expect(envFinding?.status).toBe('resolved');
    expect(second.runs).toHaveLength(2);
  });

  it('groups active findings by category', () => {
    const findings = collectRepoPathFindings([
      { path: '.env', type: 'blob', size: 20 },
      { path: 'node_modules/pkg/index.js', type: 'blob', size: 10 },
    ], 1);
    const grouped = groupScanFindingsByCategory(findings);
    expect(grouped['security-leak']).toHaveLength(1);
    expect(grouped['build-artifact']).toHaveLength(1);
  });

  it('collects CI workflow findings with likely paths and runtime-observed confidence', () => {
    const report: WorkflowWatchReport = {
      status: 'red',
      commitSha: 'abc',
      branch: 'main',
      checkedAt: 1,
      checks: [
        { name: 'lint', status: 'red', conclusion: 'failure', source: 'check-run', summary: 'eslint failed' },
        { name: 'typecheck', status: 'red', conclusion: 'failure', source: 'check-run', summary: 'tsc failed' },
      ],
      errors: [],
      warnings: [],
      fixes: [],
      summary: 'red',
    };

    const findings = collectWorkflowWatchFindings(report, 1);
    expect(findings).toHaveLength(2);
    expect(findings[0]).toMatchObject({ category: 'ci-failure', filePath: 'eslint.config.*', confidence: 'runtime-observed' });
    expect(findings[1]).toMatchObject({ category: 'type-error', filePath: 'tsconfig.json' });
  });

  it('keeps CI findings active until a clean workflow scan proves resolution', () => {
    const failing: WorkflowWatchReport = {
      status: 'red',
      commitSha: 'abc',
      branch: 'main',
      checkedAt: 1,
      checks: [{ name: 'lint', status: 'red', conclusion: 'failure', source: 'check-run', summary: 'eslint failed' }],
      errors: [],
      warnings: [],
      fixes: [],
      summary: 'red',
    };

    const first = applyWorkflowWatchFindingsWithBookkeeping(createScanFindingRegistry(1), failing, 1, 2);
    expect(first.findings.find((finding) => finding.category === 'ci-failure')?.status).toBe('active');
    expect(buildScanFindingPublishGate(first).allowed).toBe(false);

    const clean = markSourceResolvedByCleanScan(first, 'workflow-watch', 3, 4);
    const ciFinding = clean.findings.find((finding) => finding.category === 'ci-failure');
    expect(ciFinding?.status).toBe('resolved');
    expect(buildScanFindingPublishGate(clean).allowed).toBe(true);
  });

  it('bridges workflow scans into registry plus publish gate', () => {
    const failing: WorkflowWatchReport = {
      status: 'red',
      checkedAt: 1,
      checks: [{ name: 'build', status: 'red', conclusion: 'failure', source: 'check-run', summary: 'vite build failed' }],
      errors: [],
      warnings: [],
      fixes: [],
      summary: 'red',
    };

    const result = applyWorkflowScanAndBuildGate(createScanFindingRegistry(1), failing, 1, 2);
    expect(result.registry.findings[0]).toMatchObject({ category: 'build-logic', filePath: 'vite.config.*' });
    expect(result.gate.allowed).toBe(true);
    expect(result.summary).toContain('Scan workflow-watch abgeschlossen');
  });

  it('rejects forged findings with unredacted secrets', () => {
    const finding: ScanFinding = {
      id: 'find-forged',
      category: 'auth',
      severity: 'critical',
      status: 'active',
      filePath: 'src/auth.ts',
      lineNumber: 1,
      title: 'Leaked token',
      description: 'token=supersecret123456789',
      fixTips: 'Rotate it',
      confidence: 'manual',
      source: 'test',
      hits: 1,
      firstSeenAt: 1,
      lastSeenAt: 1,
    };
    expect(validateScanFinding(finding).valid).toBe(false);
  });

  it('summarizes active registry severity counts', () => {
    const findings = collectRepoPathFindings([
      { path: '.env', type: 'blob', size: 20 },
      { path: 'README.md', type: 'blob', size: 100 },
    ], 1);
    const registry = applyScanFindings(createScanFindingRegistry(1), 'repo-path-scan', findings, 1, 2);
    expect(summarizeScanFindingRegistry(registry)).toContain('active finding');
  });
});
