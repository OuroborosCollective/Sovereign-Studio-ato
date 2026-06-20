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
import {
  buildSovereignPackageFromRepoFiles,
  summarizeSovereignPackage,
} from './sovereignPackageFromRepoFiles';
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

const concreteMission = 'Update README and launch readiness docs with current runtime setup';

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

    const auth = createGitHubAuthSession(' sample_value ');
    expect(auth.hasToken).toBe(true);
    expect(auth.redactedToken).not.toContain('sample_value');
    expect((buildGitHubHeaders({ token: auth.token }) as Record<string, string>).Authorization).toBe('Bearer sample_value');

    const signals = buildRepoSignalsFromFiles('https://github.com/OuroborosCollective/Sovereign-Studio-ato', repoFiles);
    const report = evaluateRepoReadiness(signals);
    const markdown = buildLaunchPackageMarkdown(signals, report, concreteMission);
    expect(markdown).toContain('Launch Readiness Package');

    const integrity = analyzeRepoFileIntegrityList(repoFiles);
    expect(summarizeFileIntegrity(integrity)).toContain('path-only');

    const pkg = buildSovereignPackageFromRepoFiles({
      mission: concreteMission,
      repoFiles,
    });
    expect(() => assertGeneratedPackageReady(pkg, repoFiles)).not.toThrow();
    expect(pkg.files.map((file) => file.path)).toContain('docs/LAUNCH_READINESS.md');

    const automationRunKey = buildAutomationRunKey({
      mode: 'full-auto-draft-pr',
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      repoBranch: 'main',
      githubTokenPresent: true,
      repoReady: snapshot.ready,
      mission: 'Bitte mobile UX verbessern und Logs direkt sichtbar machen.',
      repoFileCount: repoFiles.length,
      healthStatus: 'green',
    });
    const automation = decideSovereignAutomation({
      mode: 'full-auto-draft-pr',
      repoReady: snapshot.ready,
      hasMission: true,
      hasToken: true,
      isBusy: false,
      hasPackage: true,
      nextAutoRunKey: automationRunKey,
      healthAllowed: true,
      healthStatus: 'green',
    });
    expect(automation.shouldPublishDraftPr).toBe(true);

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
    expect(health.status).toBe('green');

    const coverage = buildRuntimeValidationCoverageReport();
    expect(coverage.covered).toBeGreaterThan(0);
    expect(coverage.healthy).toBe(true);
    expect(() => assertRuntimeValidationCoverageHealthy(coverage)).not.toThrow();

    const headers = buildGitHubHeaders({ token: auth.token }) as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer sample_value');

    const branch = buildSovereignBranchName(
      'sovereign/package',
      'runtime structure',
      pkg.files,
      'test',
    );
    expect(branch).toContain('sovereign/package');

    expect(validatePublishableFiles(pkg.files)).toHaveLength(pkg.files.length);

    const session = createSessionMemorySnapshot({
      repoUrl: 'https://github.com/OuroborosCollective/Sovereign-Studio-ato',
      repoBranch: 'main',
      repoStatus: 'loaded',
      repoFiles,
      mission: concreteMission,
      sovereignSummary: summarizeSovereignPackage(pkg, repoFiles),
      sovereignPreview: pkg.files.map((file) => `${file.path}\n${file.content}`).join('\n---\n'),
    });
    expect(parseSessionMemory(serializeSessionMemory(session))?.repoFiles).toHaveLength(repoFiles.length);
    expect(DEFAULT_TOOL_PROGRESS_RAIL.length).toBeGreaterThan(3);
  });
});
