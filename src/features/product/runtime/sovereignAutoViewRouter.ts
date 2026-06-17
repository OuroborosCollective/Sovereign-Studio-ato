import type { SequentialRuntimeStep } from './sequentialRuntimeGuard';
import type { WorkflowWatchStatus } from './workflowWatch';
import type { SovereignAutomationMode } from './sovereignAutomationMode';

export type SovereignAutoViewTab =
  | 'repo'
  | 'readiness'
  | 'integrity'
  | 'findings'
  | 'builder'
  | 'files'
  | 'diff'
  | 'workflow'
  | 'repair'
  | 'health'
  | 'runtime'
  | 'coverage'
  | 'memory'
  | 'remote'
  | 'telemetry';

export interface SovereignAutoViewInput {
  mode: SovereignAutomationMode;
  activeStep: SequentialRuntimeStep | null;
  activeTab: SovereignAutoViewTab;
  hasPackage: boolean;
  isPublishing: boolean;
  isWatchingWorkflow: boolean;
  workflowStatus?: WorkflowWatchStatus;
}

export interface SovereignAutoViewDecision {
  shouldSwitch: boolean;
  tab: SovereignAutoViewTab;
  reason: string;
}

const STEP_TABS: Record<SequentialRuntimeStep, SovereignAutoViewTab> = {
  'repo-load': 'repo',
  'package-build': 'builder',
  'diff-load': 'diff',
  'draft-pr-publish': 'workflow',
  'workflow-watch': 'workflow',
  'repair-plan': 'repair',
};

const AUTO_VISIBLE_TABS = new Set<SovereignAutoViewTab>([
  'repo',
  'readiness',
  'builder',
  'files',
  'diff',
  'workflow',
  'repair',
  'telemetry',
]);

export function validateSovereignAutoViewInput(input: SovereignAutoViewInput): string[] {
  const errors: string[] = [];

  if (!AUTO_VISIBLE_TABS.has(input.activeTab) && input.mode !== 'manual') {
    errors.push(`Auto mode is on an unsupported active tab: ${input.activeTab}`);
  }

  if (input.workflowStatus && !['idle', 'pending', 'green', 'red', 'unknown'].includes(input.workflowStatus)) {
    errors.push(`Unknown workflow status: ${input.workflowStatus}`);
  }

  if (input.activeStep && !Object.prototype.hasOwnProperty.call(STEP_TABS, input.activeStep)) {
    errors.push(`Unknown active step: ${input.activeStep}`);
  }

  return errors;
}

export function decideSovereignAutoView(input: SovereignAutoViewInput): SovereignAutoViewDecision {
  const validationErrors = validateSovereignAutoViewInput(input);
  if (validationErrors.length) {
    return {
      shouldSwitch: input.activeTab !== 'telemetry',
      tab: 'telemetry',
      reason: `Auto view validation failed: ${validationErrors.join(' | ')}`,
    };
  }

  let tab: SovereignAutoViewTab | null = null;
  let reason = 'No auto view change required.';

  if (input.activeStep) {
    tab = STEP_TABS[input.activeStep];
    reason = `Active runtime step ${input.activeStep} owns the ${tab} view.`;
  } else if (input.isPublishing) {
    tab = 'workflow';
    reason = 'Draft PR publishing should show the workflow/log view.';
  } else if (input.isWatchingWorkflow) {
    tab = 'workflow';
    reason = 'Workflow watch is running and should stay visible.';
  } else if (input.workflowStatus === 'red') {
    tab = 'repair';
    reason = 'Red workflow status should surface the repair view.';
  } else if (input.workflowStatus === 'pending' || input.workflowStatus === 'unknown') {
    tab = 'workflow';
    reason = 'Non-final workflow status should stay on workflow watch.';
  } else if (input.workflowStatus === 'green' && input.hasPackage) {
    tab = 'files';
    reason = 'Green workflow with a generated package should return to the ready files view.';
  } else if (input.hasPackage && input.mode !== 'manual') {
    tab = 'files';
    reason = 'Auto mode generated package is ready for review.';
  } else if (input.mode !== 'manual') {
    tab = 'builder';
    reason = 'Auto mode starts in the Auftrag/Builder view.';
  }

  const target = tab ?? input.activeTab;
  return {
    shouldSwitch: target !== input.activeTab,
    tab: target,
    reason,
  };
}
