import type { WorkflowWatchReport } from './workflowWatch';
import {
  buildScanFindingPublishGate,
  type ScanFindingPublishGate,
  type ScanFindingRegistry,
} from './scanFindingRegistry';
import { applyWorkflowWatchFindingsWithBookkeeping } from './scanFindingBookkeeping';

export interface WorkflowScanFindingBridgeResult {
  registry: ScanFindingRegistry;
  gate: ScanFindingPublishGate;
  summary: string;
}

export function applyWorkflowScanAndBuildGate(
  registry: ScanFindingRegistry,
  report: WorkflowWatchReport | null,
  startedAt = Date.now(),
  completedAt = Date.now(),
): WorkflowScanFindingBridgeResult {
  const nextRegistry = applyWorkflowWatchFindingsWithBookkeeping(registry, report, startedAt, completedAt);
  const gate = buildScanFindingPublishGate(nextRegistry);
  return {
    registry: nextRegistry,
    gate,
    summary: `${nextRegistry.runs[0]?.summary ?? 'No workflow scan run recorded.'} ${gate.summary}`,
  };
}
