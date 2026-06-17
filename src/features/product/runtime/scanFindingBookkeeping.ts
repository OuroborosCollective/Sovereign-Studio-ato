import type { WorkflowWatchReport } from './workflowWatch';
import {
  assertScanFindingRegistryValid,
  collectWorkflowWatchFindings,
  createScanFindingRun,
  validateScanFinding,
  type ScanFinding,
  type ScanFindingRegistry,
} from './scanFindingRegistry';

const MAX_BOOKKEEPING_FINDINGS = 500;
const MAX_BOOKKEEPING_RUNS = 80;

export function applyScanFindingsWithBookkeeping(
  registry: ScanFindingRegistry,
  source: string,
  findings: ScanFinding[],
  startedAt = Date.now(),
  completedAt = Date.now(),
): ScanFindingRegistry {
  assertScanFindingRegistryValid(registry);
  for (const finding of findings) {
    const report = validateScanFinding(finding);
    if (!report.valid) throw new Error(`Invalid scan finding ${finding.id}: ${report.errors.join(' | ')}`);
  }

  const existingById = new Map(registry.findings.map((finding) => [finding.id, finding]));
  const incomingById = new Map(findings.map((finding) => [finding.id, finding]));

  const mergedExisting = registry.findings.map((existing) => {
    const incoming = incomingById.get(existing.id);
    if (incoming) {
      return {
        ...incoming,
        firstSeenAt: existing.firstSeenAt,
        hits: existing.hits + 1,
        status: 'active' as const,
        lastSeenAt: completedAt,
      };
    }
    if (existing.source === source && existing.status === 'active') {
      return {
        ...existing,
        status: 'resolved' as const,
        lastSeenAt: completedAt,
      };
    }
    return existing;
  });

  const newFindings = findings.filter((finding) => !existingById.has(finding.id));
  const nextFindings = [...newFindings, ...mergedExisting]
    .slice(0, MAX_BOOKKEEPING_FINDINGS);
  const run = createScanFindingRun(source, findings, startedAt, completedAt);
  const nextRegistry = {
    version: 1 as const,
    findings: nextFindings,
    runs: [run, ...registry.runs].slice(0, MAX_BOOKKEEPING_RUNS),
    updatedAt: completedAt,
  };

  assertScanFindingRegistryValid(nextRegistry);
  return nextRegistry;
}

export function applyWorkflowWatchFindingsWithBookkeeping(
  registry: ScanFindingRegistry,
  report: WorkflowWatchReport | null,
  startedAt = Date.now(),
  completedAt = Date.now(),
): ScanFindingRegistry {
  const findings = collectWorkflowWatchFindings(report, startedAt, 'workflow-watch');
  return applyScanFindingsWithBookkeeping(registry, 'workflow-watch', findings, startedAt, completedAt);
}

export function markSourceResolvedByCleanScan(
  registry: ScanFindingRegistry,
  source: string,
  startedAt = Date.now(),
  completedAt = Date.now(),
): ScanFindingRegistry {
  return applyScanFindingsWithBookkeeping(registry, source, [], startedAt, completedAt);
}
