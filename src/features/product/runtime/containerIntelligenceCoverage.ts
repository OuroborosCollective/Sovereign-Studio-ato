export type ContainerIntelligenceStatus = 'covered' | 'partial' | 'missing';

export type ContainerIntelligenceArea =
  | 'runtime-checks'
  | 'tests'
  | 'pattern-rules'
  | 'telemetry'
  | 'self-review'
  | 'ui-guidance';

export interface ContainerIntelligenceCoverageEntry {
  id: string;
  label: string;
  containerPath: string;
  runtimePath?: string;
  testPath?: string;
  status: ContainerIntelligenceStatus;
  coveredAreas: ContainerIntelligenceArea[];
  missingAreas: ContainerIntelligenceArea[];
  nextAction: string;
}

export interface ContainerIntelligenceCoverageReport {
  valid: boolean;
  errors: string[];
  entries: ContainerIntelligenceCoverageEntry[];
  coveredCount: number;
  partialCount: number;
  missingCount: number;
  summary: string;
}

const REQUIRED_AREAS: ContainerIntelligenceArea[] = [
  'runtime-checks',
  'tests',
  'pattern-rules',
  'telemetry',
  'self-review',
  'ui-guidance',
];

export const CONTAINER_INTELLIGENCE_COVERAGE: ContainerIntelligenceCoverageEntry[] = [
  {
    id: 'repo-snapshot',
    label: 'Repo Snapshot',
    containerPath: 'src/features/product/containers/RepoSnapshotContainer.tsx',
    status: 'partial',
    coveredAreas: ['runtime-checks', 'tests', 'ui-guidance'],
    missingAreas: ['pattern-rules', 'telemetry', 'self-review'],
    nextAction: 'Add repo-specific pattern rules for setup readiness, token guidance, load failures, and successful snapshot handoff.',
  },
  {
    id: 'builder',
    label: 'Builder',
    containerPath: 'src/features/product/containers/BuilderContainer.tsx',
    runtimePath: 'src/features/product/runtime/builderContainerRuntime.ts',
    status: 'partial',
    coveredAreas: ['runtime-checks', 'tests', 'ui-guidance'],
    missingAreas: ['pattern-rules', 'telemetry', 'self-review'],
    nextAction: 'Add intent-quality, placeholder-block, mission-readiness, and rewrite-request pattern rules.',
  },
  {
    id: 'generated-files',
    label: 'Generated Files Review',
    containerPath: 'src/features/product/components/GeneratedFileReviewPanel.tsx',
    runtimePath: 'src/features/product/runtime/generatedFileReview.ts',
    testPath: 'src/features/product/runtime/generatedFileReview.selfReview.test.ts',
    status: 'covered',
    coveredAreas: ['runtime-checks', 'tests', 'pattern-rules', 'telemetry', 'self-review', 'ui-guidance'],
    missingAreas: [],
    nextAction: 'Keep as reference pattern for other containers.',
  },
  {
    id: 'diff-preview',
    label: 'Generated Diff Preview',
    containerPath: 'src/features/product/components/GeneratedFileDiffPreviewPanel.tsx',
    runtimePath: 'src/features/product/runtime/generatedFileDiffPreview.ts',
    status: 'partial',
    coveredAreas: ['runtime-checks', 'tests', 'ui-guidance'],
    missingAreas: ['pattern-rules', 'telemetry', 'self-review'],
    nextAction: 'Add pattern rules for missing source files, diff readiness, unchanged output, and risky replacement signals.',
  },
  {
    id: 'workflow',
    label: 'Workflow',
    containerPath: 'src/features/product/containers/WorkflowContainer.tsx',
    runtimePath: 'src/features/product/runtime/workflowWatch.ts',
    status: 'partial',
    coveredAreas: ['runtime-checks', 'tests', 'telemetry', 'ui-guidance'],
    missingAreas: ['pattern-rules', 'self-review'],
    nextAction: 'Add workflow-state pattern rules for pending, green, red, stale, and repairable results.',
  },
  {
    id: 'remote-memory',
    label: 'Remote Memory',
    containerPath: 'src/features/product/containers/RemoteMemoryContainer.tsx',
    runtimePath: 'src/features/product/runtime/remoteMemoryContainerRuntime.ts',
    status: 'partial',
    coveredAreas: ['runtime-checks', 'tests', 'telemetry'],
    missingAreas: ['pattern-rules', 'self-review', 'ui-guidance'],
    nextAction: 'Add consent, gateway health, sync eligibility, delete safety, and pull-update pattern rules.',
  },
  {
    id: 'pattern-memory',
    label: 'Pattern Memory',
    containerPath: 'src/features/product/containers/PatternMemoryContainer.tsx',
    runtimePath: 'src/features/product/runtime/patternMemoryContainerRuntime.ts',
    testPath: 'src/features/product/containers/PatternMemoryContainer.test.tsx',
    status: 'partial',
    coveredAreas: ['runtime-checks', 'tests', 'telemetry'],
    missingAreas: ['pattern-rules', 'self-review', 'ui-guidance'],
    nextAction: 'Add learning-quality, stale-pattern, successful-use, rejected-pattern, and rewrite-memory rules.',
  },
  {
    id: 'telemetry',
    label: 'Telemetry',
    containerPath: 'src/features/product/containers/TelemetryContainer.tsx',
    runtimePath: 'src/features/product/runtime/sovereignTelemetry.ts',
    testPath: 'src/features/product/runtime/sovereignTelemetry.test.ts',
    status: 'partial',
    coveredAreas: ['runtime-checks', 'tests', 'telemetry'],
    missingAreas: ['pattern-rules', 'self-review', 'ui-guidance'],
    nextAction: 'Add event-quality, noisy-event, missing-stage, secret-risk, and user-guidance pattern rules.',
  },
  {
    id: 'health',
    label: 'Sovereign Health',
    containerPath: 'src/features/product/components/SovereignHealthPanel.tsx',
    runtimePath: 'src/features/product/runtime/sovereignHealth.ts',
    status: 'partial',
    coveredAreas: ['runtime-checks', 'tests', 'ui-guidance'],
    missingAreas: ['pattern-rules', 'telemetry', 'self-review'],
    nextAction: 'Add health-score pattern rules that convert mixed reports into green/yellow/red operator guidance.',
  },
  {
    id: 'runtime-coverage',
    label: 'Runtime Validation Coverage',
    containerPath: 'src/features/product/components/RuntimeValidationCoveragePanel.tsx',
    runtimePath: 'src/features/product/runtime/runtimeValidationCoverage.ts',
    status: 'partial',
    coveredAreas: ['runtime-checks', 'tests', 'ui-guidance'],
    missingAreas: ['pattern-rules', 'telemetry', 'self-review'],
    nextAction: 'Add coverage pattern rules for missing guards, weak coverage, and release-blocking validation gaps.',
  },
  {
    id: 'findings',
    label: 'Scan Findings',
    containerPath: 'src/features/product/components/ScanFindingRegistryPanel.tsx',
    runtimePath: 'src/features/product/runtime/scanFindingRegistry.ts',
    status: 'partial',
    coveredAreas: ['runtime-checks', 'tests', 'telemetry'],
    missingAreas: ['pattern-rules', 'self-review', 'ui-guidance'],
    nextAction: 'Add severity, duplicate, stale, resolved, and repair-priority pattern rules.',
  },
];

function hasDuplicates(values: string[]): string[] {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const value of values) {
    if (seen.has(value)) duplicates.add(value);
    seen.add(value);
  }
  return [...duplicates];
}

function validateEntry(entry: ContainerIntelligenceCoverageEntry): string[] {
  const errors: string[] = [];
  if (!entry.id.trim()) errors.push('Container coverage id is required.');
  if (!entry.label.trim()) errors.push(`Container ${entry.id || 'unknown'} label is required.`);
  if (!entry.containerPath.trim()) errors.push(`Container ${entry.id || 'unknown'} path is required.`);
  if (!['covered', 'partial', 'missing'].includes(entry.status)) errors.push(`Container ${entry.id} has invalid status.`);
  if (!Array.isArray(entry.coveredAreas)) errors.push(`Container ${entry.id} coveredAreas must be an array.`);
  if (!Array.isArray(entry.missingAreas)) errors.push(`Container ${entry.id} missingAreas must be an array.`);
  if (!entry.nextAction.trim()) errors.push(`Container ${entry.id} nextAction is required.`);
  const unknownAreas = [...entry.coveredAreas, ...entry.missingAreas].filter((area) => !REQUIRED_AREAS.includes(area));
  if (unknownAreas.length) errors.push(`Container ${entry.id} has unknown area(s): ${unknownAreas.join(', ')}`);
  const overlap = entry.coveredAreas.filter((area) => entry.missingAreas.includes(area));
  if (overlap.length) errors.push(`Container ${entry.id} area(s) cannot be both covered and missing: ${overlap.join(', ')}`);
  if (entry.status === 'covered' && entry.missingAreas.length > 0) errors.push(`Container ${entry.id} is covered but still has missing areas.`);
  if (entry.status !== 'covered' && entry.missingAreas.length === 0) errors.push(`Container ${entry.id} is not covered but has no missing areas.`);
  return errors;
}

export function buildContainerIntelligenceCoverageReport(
  entries = CONTAINER_INTELLIGENCE_COVERAGE,
): ContainerIntelligenceCoverageReport {
  const errors: string[] = [];
  const ids = entries.map((entry) => entry.id);
  const paths = entries.map((entry) => entry.containerPath);
  const duplicateIds = hasDuplicates(ids);
  const duplicatePaths = hasDuplicates(paths);
  if (duplicateIds.length) errors.push(`Duplicate container coverage id(s): ${duplicateIds.join(', ')}`);
  if (duplicatePaths.length) errors.push(`Duplicate container path(s): ${duplicatePaths.join(', ')}`);
  for (const entry of entries) errors.push(...validateEntry(entry));
  const coveredCount = entries.filter((entry) => entry.status === 'covered').length;
  const partialCount = entries.filter((entry) => entry.status === 'partial').length;
  const missingCount = entries.filter((entry) => entry.status === 'missing').length;
  return {
    valid: errors.length === 0,
    errors,
    entries,
    coveredCount,
    partialCount,
    missingCount,
    summary: `${coveredCount} covered, ${partialCount} partial, ${missingCount} missing container intelligence module(s).`,
  };
}

export function assertContainerIntelligenceCoverageValid(entries = CONTAINER_INTELLIGENCE_COVERAGE): void {
  const report = buildContainerIntelligenceCoverageReport(entries);
  if (!report.valid) throw new Error(`Container intelligence coverage invalid: ${report.errors.join(' | ')}`);
}

export function listContainerIntelligenceGaps(entries = CONTAINER_INTELLIGENCE_COVERAGE): ContainerIntelligenceCoverageEntry[] {
  const report = buildContainerIntelligenceCoverageReport(entries);
  if (!report.valid) throw new Error(`Cannot list container intelligence gaps: ${report.errors.join(' | ')}`);
  return report.entries.filter((entry) => entry.status !== 'covered');
}
