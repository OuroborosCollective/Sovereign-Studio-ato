import { describe, expect, it } from 'vitest';
import { buildSovereignBranchName, validatePublishableFiles } from '../../github/githubPackagePublisher';
import {
  buildAutomationRunKey,
  decideSovereignAutomation,
} from './sovereignAutomationMode';
import { buildGeneratedFileDiffReport } from './generatedFileDiffPreview';
import {
  assertGeneratedFileReviewSafe,
  reviewGeneratedFiles,
} from './generatedFileReview';
import {
  analyzeRepoFileIntegrityList,
  summarizeFileIntegrity,
} from './repoFileIntegrity';
import { buildRepoSignalsFromFiles } from './repoLaunchReadinessFromFiles';
import {
  DEFAULT_TOOL_PROGRESS_RAIL,
  buildLaunchPackageMarkdown,
  evaluateRepoReadiness,
} from './repoLaunchReadiness';
import {
  assertRuntimeValidationCoverageHealthy,
  buildRuntimeValidationCoverageReport,
} from './runtimeValidationCoverage';
import { buildSovereignHealthReport } from './sovereignHealth';
import {
  assertGeneratedPackageReady,
  getRepoSnapshotStatus,
} from './sovereignFunctionalGuards';
import { buildSovereignPackageFromRepoFiles } from './sovereignPackageFromRepoFiles';
import {
  createSessionMemorySnapshot,
  parseSessionMemory,
  serializeSessionMemory,
} from './sovereignSessionMemory';
import {
  appendTelemetryEvent,
  createInitialTelemetryState,
  createTelemetryEvent,
  summarizeTelemetry,
} from './sovereignTelemetry';
import { buildWorkflowRepairPlan } from './workflowRepairPlan';
import { buildLocalWorkflowWatchReport } from './workflowWatch';

const repoFiles = [
  { path: 'README.md', type: 'blob' as const },
  { path: 'package.json', type: 'blob' as const },
  { path: '.github/workflows/ci.yml', type: 'blob' as const },
  { path: 'src/features/product/runtime/sovereignRuntime.ts', type: 'blob' as const },
  { path: 'src/features/product/runtime/sovereignRuntime.test.ts', type: 'blob' as const },
];

describe('sovereign runtime structure', () => {
  it('connects repo snapshot, readiness, automation, diff, workflow, repair, health, coverage, file review, package guards and publisher validation', () => {
    const snapshot = getRepoSnapshotStatus(repoFiles);
    expect(snapshot.ready).toBe(true);

    const signals = buildRepoSignalsFromFiles('https://github.com/OuroborosCollective/Sovereign-Studio-ato', repoFiles);
    const report = evaluateRepoReadiness(signals);
    const markdown = buildLaunchPackageMarkdown(signals, report, 'README + Update History');
    expect(markdown).toContain('Launch Readiness Package');

    const integrity = analyzeRepoFileIntegrityList(repoFiles);
    expect(summarizeFileIntegrity(integrity)).toContain('path-only');

    const automationRunKey = buildAutomationRunKey({
      mode: 'full-auto-draft-pr',
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      repoBranch: 'main',
      mission: 'README + Update History',
      repoFileCount: repoFiles.length,
    });
    const automation = decideSovereignAutomation({
      mode: 'full-auto-draft-pr',
      repoReady: snapshot.ready,
      hasMission: true,
      hasToken: true,
      isBusy: false,
      hasPackage: false,
      nextAutoRunKey: automationRunKey,
    });
    expect(automation.shouldPublishDraftPr).toBe(true);

    const pkg = buildSovereignPackageFromRepoFiles({
      mission: 'README + Update History',
      repoFiles,
    });
    expect(() => assertGeneratedPackageReady(pkg, repoFiles)).not.toThrow();
    expect(pkg.files.map((file) => file.path)).toContain('docs/LAUNCH_READINESS.md');

    const fileReview = reviewGeneratedFiles(pkg.files);
    expect(fileReview.totalFiles).toBe(pkg.files.length);
    expect(() => assertGeneratedFileReviewSafe(fileReview)).not.toThrow();

    const diff = buildGeneratedFileDiffReport(pkg.files, pkg.files.map((file) => ({
      path: file.path,
      content: file.path === 'README.md' ? '# Old README' : null,
      found: file.path === 'README.md',
    })));
    expect(diff.files.length).toBe(pkg.files.length);
    expect(diff.summary).toContain('generated file');

    const workflow = buildLocalWorkflowWatchReport({
      commitSha: 'commit-sha',
      branch: 'sovereign/package/test',
      checks: [{ name: 'ci', status: 'green', source: 'local', summary: 'passed' }],
    });
    expect(workflow.status).toBe('green');

    const failedWorkflow = buildLocalWorkflowWatchReport({
      commitSha: 'commit-sha',
      branch: 'sovereign/package/test',
      checks: [{ name: 'lint', status: 'red', source: 'local', summary: 'eslint failed' }],
    });
    const repairPlan = buildWorkflowRepairPlan(failedWorkflow);
    expect(repairPlan.blocked).toBe(false);
    expect(repairPlan.mission).toContain('Workflow repair package');

    let telemetry = createInitialTelemetryState();
    telemetry = appendTelemetryEvent(telemetry, createTelemetryEvent('guards', 'success', 'guards:passed', 'Package ready.'));
    expect(summarizeTelemetry(telemetry)).toContain('guards:passed');

    const health = buildSovereignHealthReport({
      repoFiles,
      generatedFileReview: fileReview,
      workflowWatch: workflow,
      telemetry,
    });
    expect(health.status).not.toBe('idle');

    const coverage = buildRuntimeValidationCoverageReport();
    expect(() => assertRuntimeValidationCoverageHealthy(coverage)).not.toThrow();

    const memory = createSessionMemorySnapshot({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      repoBranch: 'main',
      repoStatus: 'loaded',
      repoFiles,
      mission: 'README + Update History',
      sovereignSummary: 'summary',
      sovereignPreview: 'preview',
    });
    expect(parseSessionMemory(serializeSessionMemory(memory))?.repoFiles).toHaveLength(repoFiles.length);

    const publishable = validatePublishableFiles(pkg.files);
    expect(publishable.length).toBe(pkg.files.length);
    expect(buildSovereignBranchName('sovereign/package', 'Sovereign Studio: docs', publishable)).toMatch(/^sovereign\/package\/[a-f0-9]{8}$/);
  });

  it('keeps the tool progress rail as the visible top-level workflow', () => {
    expect(DEFAULT_TOOL_PROGRESS_RAIL.map((stage) => stage.id)).toEqual([
      'safe_repo_inspection',
      'task_extraction',
      'readiness_eval',
      'checklist_generation',
      'copywriting',
      'workflow_watch',
    ]);
  });
});
