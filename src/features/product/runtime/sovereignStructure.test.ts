import { describe, expect, it } from 'vitest';
import { buildGitHubHeaders, createGitHubAuthSession } from '../../github/githubAuthSession';
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
import {
  applyScanFindings,
  collectRepoPathFindings,
  createScanFindingRegistry,
  summarizeScanFindingRegistry,
} from './scanFindingRegistry';
import { applyWorkflowScanAndBuildGate } from './scanFindingWorkflowBridge';
import {
  createSequentialRuntimeState,
  finishSequentialStep,
  startSequentialStep,
} from './sequentialRuntimeGuard';
import {
  buildLearningMemoryRuntimeSummary,
  createLearningMemoryStore,
  intakeLearningMemory,
  queryLearningMemory,
} from './sovereignLearningMemory';
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
  it('connects repo snapshot, categorized findings, workflow finding bridge, auth, sequential runtime, learning memory, readiness, automation, diff, workflow, repair, health, coverage, file review, package guards and publisher validation', () => {
    const snapshot = getRepoSnapshotStatus(repoFiles);
    expect(snapshot.ready).toBe(true);

    const collectedFindings = collectRepoPathFindings(repoFiles, 1);
    const scanRegistry = applyScanFindings(createScanFindingRegistry(1), 'repo-path-scan', collectedFindings, 1, 2);
    expect(scanRegistry.runs[0].summary).toContain('abgeschlossen');
    expect(summarizeScanFindingRegistry(scanRegistry)).toContain('active finding');

    let sequential = createSequentialRuntimeState();
    sequential = startSequentialStep(sequential, 'repo-load', {}, 1);
    sequential = finishSequentialStep(sequential, 'repo-load', 'completed', 'loaded', 2);
    sequential = startSequentialStep(sequential, 'package-build', { repoReady: snapshot.ready }, 3);
    sequential = finishSequentialStep(sequential, 'package-build', 'completed', 'package built', 4);
    expect(sequential.steps['repo-load'].status).toBe('completed');
    expect(sequential.steps['package-build'].status).toBe('completed');

    const auth = createGitHubAuthSession(' ghp_demo_token ');
    expect(auth.hasToken).toBe(true);
    expect(auth.redactedToken).not.toContain('demo_token');
    expect((buildGitHubHeaders({ token: auth.token }) as Record<string, string>).Authorization).toBe('Bearer ghp_demo_token');

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
      mission: 'Bitte mobile UX verbessern und Logs direkt sichtbar machen.',
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
    const workflowBridge = applyWorkflowScanAndBuildGate(scanRegistry, failedWorkflow, 3, 4);
    expect(workflowBridge.registry.findings.some((finding) => finding.category === 'ci-failure')).toBe(true);
    expect(workflowBridge.gate.allowed).toBe(false);

    const repairPlan = buildWorkflowRepairPlan(failedWorkflow);
    expect(repairPlan.blocked).toBe(false);
    expect(repairPlan.mission).toContain('Workflow repair package');

    let learning = createLearningMemoryStore(1);
    learning = intakeLearningMemory(learning, {
      kind: 'workflow',
      sourceNode: 'workflow-watch',
      outputNodes: ['workflow-repair-plan', 'action-builder'],
      summary: 'Failed lint workflow maps to a focused repair mission.',
      evidence: repairPlan.summary,
      tags: ['lint', 'workflow'],
      confidence: 'observed',
      now: 2,
    });
    expect(queryLearningMemory(learning, { outputNode: 'action-builder' })).toHaveLength(1);
    expect(buildLearningMemoryRuntimeSummary(learning)).toContain('1 learning pattern');

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
