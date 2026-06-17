import type { WorkflowWatchReport } from './workflowWatch';
import {
  buildScanFindingPublishGate,
  validateScanFindingRegistry,
  type ScanFindingPublishGate,
  type ScanFindingRegistry,
} from './scanFindingRegistry';
import { applyWorkflowWatchFindingsWithBookkeeping } from './scanFindingBookkeeping';

export interface WorkflowScanFindingBridgeResult {
  registry: ScanFindingRegistry;
  gate: ScanFindingPublishGate;
  summary: string;
}

export interface WorkflowScanFindingBridgeValidationReport {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary: string;
}

export function validateWorkflowScanFindingBridgeResult(
  result: WorkflowScanFindingBridgeResult,
): WorkflowScanFindingBridgeValidationReport {
  const errors: string[] = [];
  const warnings: string[] = [];
  const registryReport = validateScanFindingRegistry(result.registry);

  errors.push(...registryReport.errors.map((error) => `registry: ${error}`));
  warnings.push(...registryReport.warnings.map((warning) => `registry: ${warning}`));

  if (!result.summary.trim()) errors.push('Bridge summary is required.');
  if (result.gate.allowed !== (result.gate.blockers.length === 0)) {
    errors.push('Bridge publish gate mismatch between allowed and blockers.');
  }

  const expectedGate = buildScanFindingPublishGate(result.registry);
  if (expectedGate.allowed !== result.gate.allowed || expectedGate.blockers.length !== result.gate.blockers.length) {
    errors.push('Bridge publish gate does not match registry state.');
  }

  if (!result.registry.runs.length) warnings.push('Bridge result has no scan run history.');

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary: `${errors.length} error(s), ${warnings.length} warning(s) in workflow scan bridge result.`,
  };
}

export function assertWorkflowScanFindingBridgeResultValid(result: WorkflowScanFindingBridgeResult): void {
  const report = validateWorkflowScanFindingBridgeResult(result);
  if (!report.valid) {
    throw new Error(`Workflow scan bridge result is invalid: ${report.errors.join(' | ')}`);
  }
}

export function applyWorkflowScanAndBuildGate(
  registry: ScanFindingRegistry,
  report: WorkflowWatchReport | null,
  startedAt = Date.now(),
  completedAt = Date.now(),
): WorkflowScanFindingBridgeResult {
  const nextRegistry = applyWorkflowWatchFindingsWithBookkeeping(registry, report, startedAt, completedAt);
  const gate = buildScanFindingPublishGate(nextRegistry);
  const result = {
    registry: nextRegistry,
    gate,
    summary: `${nextRegistry.runs[0]?.summary ?? 'No workflow scan run recorded.'} ${gate.summary}`,
  } satisfies WorkflowScanFindingBridgeResult;
  assertWorkflowScanFindingBridgeResultValid(result);
  return result;
}
