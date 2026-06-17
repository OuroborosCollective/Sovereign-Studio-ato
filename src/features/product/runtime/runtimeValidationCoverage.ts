export type RuntimeCoverageStatus = 'covered' | 'partial' | 'missing';

export interface RuntimeValidationTarget {
  id: string;
  runtimePath: string;
  testPath: string;
  purpose: string;
  status: RuntimeCoverageStatus;
  integrationPoint: string;
}

export interface RuntimeValidationCoverageReport {
  targets: RuntimeValidationTarget[];
  covered: number;
  partial: number;
  missing: number;
  healthy: boolean;
  summary: string;
}

export const RUNTIME_VALIDATION_TARGETS: RuntimeValidationTarget[] = [
  {
    id: 'readiness-runtime',
    runtimePath: 'src/features/product/runtime/repoLaunchReadiness.ts',
    testPath: 'src/features/product/runtime/repoLaunchReadiness.test.ts',
    purpose: 'Launch readiness score, risk register and owner checklist.',
    status: 'covered',
    integrationPoint: 'RepoReadinessPanel',
  },
  {
    id: 'readiness-from-files',
    runtimePath: 'src/features/product/runtime/repoLaunchReadinessFromFiles.ts',
    testPath: 'src/features/product/runtime/repoLaunchReadinessFromFiles.test.ts',
    purpose: 'Maps GitHub tree entries into readiness signals.',
    status: 'covered',
    integrationPoint: 'RepoReadinessPanel',
  },
  {
    id: 'file-integrity',
    runtimePath: 'src/features/product/runtime/repoFileIntegrity.ts',
    testPath: 'src/features/product/runtime/repoFileIntegrity.test.ts',
    purpose: 'Honest path-only repository file risk matrix.',
    status: 'covered',
    integrationPoint: 'RepoFileIntegrityMatrix',
  },
  {
    id: 'github-auth-session',
    runtimePath: 'src/features/github/githubAuthSession.ts',
    testPath: 'src/features/github/githubAuthSession.test.ts',
    purpose: 'Centralizes session-only GitHub token headers, redaction and write-path token requirements.',
    status: 'covered',
    integrationPoint: 'Repo loader + Diff loader + Workflow Watch + Draft PR Publisher',
  },
  {
    id: 'functional-guards',
    runtimePath: 'src/features/product/runtime/sovereignFunctionalGuards.ts',
    testPath: 'src/features/product/runtime/sovereignFunctionalGuards.test.ts',
    purpose: 'Blocks empty snapshots, unsafe paths and incomplete docs packages.',
    status: 'covered',
    integrationPoint: 'buildSovereignPackageFromRepoFiles',
  },
  {
    id: 'package-builder',
    runtimePath: 'src/features/product/runtime/sovereignPackageFromRepoFiles.ts',
    testPath: 'src/features/product/runtime/sovereignPackageFromRepoFiles.test.ts',
    purpose: 'Builds brain-gated packages from loaded repo snapshots.',
    status: 'covered',
    integrationPoint: 'Sovereign Action Builder',
  },
  {
    id: 'generated-file-review',
    runtimePath: 'src/features/product/runtime/generatedFileReview.ts',
    testPath: 'src/features/product/runtime/generatedFileReview.test.ts',
    purpose: 'Reviews generated files before Draft PR publishing.',
    status: 'covered',
    integrationPoint: 'GeneratedFileReviewPanel + Draft PR flow',
  },
  {
    id: 'generated-file-diff-preview',
    runtimePath: 'src/features/product/runtime/generatedFileDiffPreview.ts',
    testPath: 'src/features/product/runtime/generatedFileDiffPreview.test.ts',
    purpose: 'Compares generated files with loaded source snapshots before publishing.',
    status: 'covered',
    integrationPoint: 'GeneratedFileDiffPreviewPanel + Draft PR body',
  },
  {
    id: 'automation-mode',
    runtimePath: 'src/features/product/runtime/sovereignAutomationMode.ts',
    testPath: 'src/features/product/runtime/sovereignAutomationMode.test.ts',
    purpose: 'Controls Manual, Auto Review and Full Auto Draft PR policy.',
    status: 'covered',
    integrationPoint: 'App automation effect',
  },
  {
    id: 'telemetry-runtime',
    runtimePath: 'src/features/product/runtime/sovereignTelemetry.ts',
    testPath: 'src/features/product/runtime/sovereignTelemetry.test.ts',
    purpose: 'Records visible lifecycle events.',
    status: 'covered',
    integrationPoint: 'SovereignTelemetryPanel',
  },
  {
    id: 'session-memory',
    runtimePath: 'src/features/product/runtime/sovereignSessionMemory.ts',
    testPath: 'src/features/product/runtime/sovereignSessionMemory.test.ts',
    purpose: 'Saves and restores local repo snapshot state without PATs.',
    status: 'covered',
    integrationPoint: 'Repo tab Save/Restore Session',
  },
  {
    id: 'workflow-watch',
    runtimePath: 'src/features/product/runtime/workflowWatch.ts',
    testPath: 'src/features/product/runtime/workflowWatch.test.ts',
    purpose: 'Reads commit status/check-runs and builds follow-up repair signals.',
    status: 'covered',
    integrationPoint: 'WorkflowWatchPanel',
  },
  {
    id: 'workflow-repair-plan',
    runtimePath: 'src/features/product/runtime/workflowRepairPlan.ts',
    testPath: 'src/features/product/runtime/workflowRepairPlan.test.ts',
    purpose: 'Turns failed workflow checks into a focused repair mission.',
    status: 'covered',
    integrationPoint: 'WorkflowRepairPanel + Sovereign Action Builder',
  },
  {
    id: 'health-runtime',
    runtimePath: 'src/features/product/runtime/sovereignHealth.ts',
    testPath: 'src/features/product/runtime/sovereignHealth.test.ts',
    purpose: 'Aggregates repo, file review, workflow and telemetry into health status.',
    status: 'covered',
    integrationPoint: 'SovereignHealthPanel',
  },
];

export function buildRuntimeValidationCoverageReport(
  targets: RuntimeValidationTarget[] = RUNTIME_VALIDATION_TARGETS,
): RuntimeValidationCoverageReport {
  const covered = targets.filter((target) => target.status === 'covered').length;
  const partial = targets.filter((target) => target.status === 'partial').length;
  const missing = targets.filter((target) => target.status === 'missing').length;
  const healthy = targets.length > 0 && missing === 0;
  return {
    targets,
    covered,
    partial,
    missing,
    healthy,
    summary: `${covered}/${targets.length} runtime validation target(s) covered, ${partial} partial, ${missing} missing.`,
  };
}

export function assertRuntimeValidationCoverageHealthy(report = buildRuntimeValidationCoverageReport()): void {
  if (!report.healthy) {
    throw new Error(`Runtime validation coverage is not healthy: ${report.summary}`);
  }
}
