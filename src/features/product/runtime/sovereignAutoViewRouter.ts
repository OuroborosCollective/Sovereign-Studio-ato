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
  hasDiffSources?: boolean;
  isPublishing: boolean;
  isWatchingWorkflow: boolean;
  workflowStatus?: WorkflowWatchStatus;
  hasActivePatterns?: boolean;
  hasActiveTelemetry?: boolean;
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

const ALL_KNOWN_TABS = new Set<SovereignAutoViewTab>([
  'repo',
  'readiness',
  'integrity',
  'findings',
  'builder',
  'files',
  'diff',
  'workflow',
  'repair',
  'health',
  'runtime',
  'coverage',
  'memory',
  'remote',
  'telemetry',
]);

export function validateSovereignAutoViewInput(input: SovereignAutoViewInput): string[] {
  const errors: string[] = [];

  if (!ALL_KNOWN_TABS.has(input.activeTab)) {
    errors.push(`Unknown active tab: ${input.activeTab}`);
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
    // Nach grünem Workflow: Diff laden wenn Package da
    if (input.hasDiffSources) {
      tab = 'diff';
      reason = 'Green workflow with diff sources loaded - show the diff.';
    } else {
      tab = 'files';
      reason = 'Green workflow with generated package - show files view.';
    }
  } else if (input.hasPackage && input.hasDiffSources && input.workflowStatus === 'idle') {
    // Package + Diff + kein Workflow = Diff anschauen
    tab = 'diff';
    reason = 'Package ready with diff sources - review the generated diff.';
  } else if (input.hasPackage && input.mode !== 'manual') {
    // Auto mode: Package bereit -> Files
    tab = 'files';
    reason = 'Auto mode generated package is ready for review.';
  } else if (input.hasPackage && input.workflowStatus === 'idle' && input.mode === 'manual') {
    // Manual mode: Package da, user darf selbst entscheiden wo sie sind
    // Nur zu workflow wechseln wenn sie auf Haupt-Tabs sind
    const userTabs = ['repo', 'builder', 'files', 'diff', 'workflow', 'repair'];
    if (userTabs.includes(input.activeTab)) {
      tab = 'workflow';
      reason = 'Package ready in manual mode - you can start workflow from here.';
    }
    // Wenn user auf side tab (memory, remote, telemetry, etc.), bleib dort
  } else if (input.hasActivePatterns && input.hasPackage) {
    // Patterns verfügbar + Package = Memory anschauen
    tab = 'memory';
    reason = 'Active patterns available with package - show learned patterns.';
  } else if (input.hasActiveTelemetry) {
    tab = 'telemetry';
    reason = 'Active telemetry events - show status.';
  }

  const target = tab ?? input.activeTab;
  return {
    shouldSwitch: target !== input.activeTab,
    tab: target,
    reason,
  };
}
