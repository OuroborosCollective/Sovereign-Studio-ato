import type { SequentialRuntimeStep } from './sequentialRuntimeGuard';
import type { WorkflowWatchStatus } from './workflowWatch';
import type { SovereignAutomationMode } from './sovereignAutomationMode';

export type SovereignAutoViewTab =
  | 'repo'
  | 'readiness'
  | 'integrity'
  | 'findings'
  | 'builder'
  | 'chat'
  | 'files'
  | 'diff'
  | 'workflow'
  | 'repair'
  | 'health'
  | 'runtime'
  | 'coverage'
  | 'memory'
  | 'remote'
  | 'telemetry'
  | 'monitor';

export type SovereignAutoViewSignal =
  | 'repo-ready'
  | 'runtime-active'
  | 'publishing'
  | 'workflow-watch'
  | 'workflow-red'
  | 'workflow-pending'
  | 'workflow-green'
  | 'package-ready'
  | 'diff-ready'
  | 'patterns-active'
  | 'telemetry-active';

export type SovereignAutoViewConditionType =
  | 'SIGNAL_ACTIVE'
  | 'TAB_COMPLETED'
  | 'USER_INACTIVE'
  | 'CONFIDENCE_MATCHED'
  | 'MANUAL_OVERRIDE_CLEAR';

export interface SovereignAutoViewCondition {
  type: SovereignAutoViewConditionType;
  signal?: SovereignAutoViewSignal;
  tab?: SovereignAutoViewTab;
  thresholdMs?: number;
  confidenceThreshold?: number;
}

export interface SovereignAutoViewInput {
  mode: SovereignAutomationMode;
  activeStep: SequentialRuntimeStep | null;
  activeTab: SovereignAutoViewTab;
  repoReady?: boolean;
  hasPackage: boolean;
  hasDiffSources?: boolean;
  isPublishing: boolean;
  isWatchingWorkflow: boolean;
  workflowStatus?: WorkflowWatchStatus;
  hasActivePatterns?: boolean;
  hasActiveTelemetry?: boolean;
  completedTabs?: SovereignAutoViewTab[];
  activeSignals?: SovereignAutoViewSignal[];
  nowMs?: number;
  lastUserInteractionAt?: number;
  manualOverrideUntil?: number;
  recentUserInteractionUntil?: number;
  patternConfidence?: number;
  autoSwitchInactivityMs?: number;
  patternConfidenceThreshold?: number;
  planningConfirmed?: boolean;
}

export interface SovereignAutoViewDecision {
  shouldSwitch: boolean;
  tab: SovereignAutoViewTab;
  reason: string;
}

const ALL_TABS: readonly SovereignAutoViewTab[] = [
  'repo',
  'readiness',
  'integrity',
  'findings',
  'builder',
  'chat',
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
  'monitor',
];

const SIDE_TABS: readonly SovereignAutoViewTab[] = [
  'memory',
  'remote',
  'telemetry',
  'monitor',
  'readiness',
  'integrity',
  'findings',
  'health',
  'runtime',
  'coverage',
  'chat',
];

const STEP_TABS: Record<SequentialRuntimeStep, SovereignAutoViewTab> = {
  'repo-load': 'repo',
  'package-build': 'builder',
  'diff-load': 'diff',
  'draft-pr-publish': 'workflow',
  'workflow-watch': 'workflow',
  'repair-plan': 'repair',
};

function activeSignalsFromInput(input: SovereignAutoViewInput): Set<SovereignAutoViewSignal> {
  const signals = new Set(input.activeSignals ?? []);
  if (input.repoReady) signals.add('repo-ready');
  if (input.activeStep) signals.add('runtime-active');
  if (input.isPublishing) signals.add('publishing');
  if (input.isWatchingWorkflow) signals.add('workflow-watch');
  if (input.workflowStatus === 'red') signals.add('workflow-red');
  if (input.workflowStatus === 'pending') signals.add('workflow-pending');
  if (input.workflowStatus === 'green') signals.add('workflow-green');
  if (input.hasPackage) signals.add('package-ready');
  if (input.hasDiffSources) signals.add('diff-ready');
  if (input.hasActivePatterns) signals.add('patterns-active');
  if (input.hasActiveTelemetry) signals.add('telemetry-active');
  return signals;
}

export function validateSovereignAutoViewInput(input: SovereignAutoViewInput): string[] {
  const errors: string[] = [];
  if (!ALL_TABS.includes(input.activeTab)) errors.push(`Unknown active tab: ${input.activeTab}`);
  if (input.completedTabs?.some((tab) => !ALL_TABS.includes(tab))) errors.push('completedTabs contains unknown tab.');
  if (input.activeStep && !(input.activeStep in STEP_TABS)) errors.push(`Unknown active step: ${input.activeStep}`);
  if (input.workflowStatus && !['idle', 'pending', 'green', 'red', 'unknown'].includes(input.workflowStatus)) errors.push(`Unknown workflow status: ${input.workflowStatus}`);
  return errors;
}

export function isSovereignAutoViewManualOverrideActive(input: SovereignAutoViewInput): boolean {
  const now = input.nowMs ?? Date.now();
  return Boolean(input.manualOverrideUntil && now < input.manualOverrideUntil);
}

export function evaluateSovereignAutoViewConditions(
  conditions: SovereignAutoViewCondition[],
  input: SovereignAutoViewInput,
): boolean {
  const signals = activeSignalsFromInput(input);
  const now = input.nowMs ?? Date.now();
  const completedTabs = new Set(input.completedTabs ?? []);

  return conditions.every((condition) => {
    if (condition.type === 'SIGNAL_ACTIVE') return Boolean(condition.signal && signals.has(condition.signal));
    if (condition.type === 'TAB_COMPLETED') return Boolean(condition.tab && completedTabs.has(condition.tab));
    if (condition.type === 'USER_INACTIVE') {
      const threshold = condition.thresholdMs ?? input.autoSwitchInactivityMs ?? 0;
      if (!input.lastUserInteractionAt || threshold <= 0) return false;
      return now - input.lastUserInteractionAt >= threshold;
    }
    if (condition.type === 'CONFIDENCE_MATCHED') {
      const threshold = condition.confidenceThreshold ?? input.patternConfidenceThreshold ?? 0;
      return (input.patternConfidence ?? 0) >= threshold;
    }
    if (condition.type === 'MANUAL_OVERRIDE_CLEAR') return !isSovereignAutoViewManualOverrideActive(input);
    return false;
  });
}

export function decideSovereignAutoView(input: SovereignAutoViewInput): SovereignAutoViewDecision {
  const validationErrors = validateSovereignAutoViewInput(input);
  if (validationErrors.length > 0) {
    return {
      shouldSwitch: false,
      tab: input.activeTab,
      reason: `Invalid auto view input: ${validationErrors.join(' | ')}`,
    };
  }

  if (isSovereignAutoViewManualOverrideActive(input)) {
    return {
      shouldSwitch: false,
      tab: input.activeTab,
      reason: 'Auto view switch paused by manual override window.',
    };
  }

  if (input.mode === 'manual') {
    if (input.activeStep) {
      const stepTab = STEP_TABS[input.activeStep];
      return {
        shouldSwitch: input.activeTab !== stepTab,
        tab: stepTab,
        reason: `Sequential runtime step ${input.activeStep} is active.`,
      };
    }

    if (input.workflowStatus === 'red') {
      return {
        shouldSwitch: input.activeTab !== 'repair',
        tab: 'repair',
        reason: 'Workflow red stopper routes into repair even in manual mode.',
      };
    }

    if (input.activeTab === 'diff' && input.hasPackage && input.hasDiffSources) {
      return {
        shouldSwitch: true,
        tab: 'workflow',
        reason: 'Source snapshots exist; diff is internal and workflow is the safe review surface.',
      };
    }

    if (input.activeTab === 'builder') {
      return {
        shouldSwitch: false,
        tab: 'builder',
        reason: 'Manual mode keeps user navigation free in the Builder planning workspace.',
      };
    }

    return {
      shouldSwitch: false,
      tab: input.activeTab,
      reason: 'Manual mode keeps user navigation free.',
    };
  }

  if (input.activeStep) {
    const stepTab = STEP_TABS[input.activeStep];
    return {
      shouldSwitch: input.activeTab !== stepTab,
      tab: stepTab,
      reason: `Sequential runtime step ${input.activeStep} is active.`,
    };
  }

  if (SIDE_TABS.includes(input.activeTab)) {
    return {
      shouldSwitch: false,
      tab: input.activeTab,
      reason: `User-selected side tab ${input.activeTab} stays visible until runtime work requires a switch.`,
    };
  }

  if (input.isPublishing || input.isWatchingWorkflow || input.workflowStatus === 'pending' || input.workflowStatus === 'green') {
    return {
      shouldSwitch: input.activeTab !== 'workflow',
      tab: 'workflow',
      reason: 'Workflow state is active or recently completed, so workflow remains visible.',
    };
  }

  if (input.workflowStatus === 'red') {
    return {
      shouldSwitch: input.activeTab !== 'repair',
      tab: 'repair',
      reason: 'Workflow is red, so repair guidance is the next safe surface.',
    };
  }

  if (input.hasPackage && (input.hasDiffSources || input.mode === 'auto-review' || input.mode === 'full-auto-draft-pr')) {
    return {
      shouldSwitch: input.activeTab !== 'workflow',
      tab: 'workflow',
      reason: input.hasDiffSources
        ? 'Package source snapshots exist; diff is internal and workflow is the safe review surface.'
        : 'Package exists; diff is internal until source snapshots are loaded, so workflow is the safe review surface.',
    };
  }

  return {
    shouldSwitch: false,
    tab: input.activeTab,
    reason: 'No auto view change matched.',
  };
}
