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

const VALID_WORKFLOW_STATUSES: WorkflowWatchStatus[] = ['idle', 'pending', 'green', 'red', 'unknown'];
const SIDE_TABS = new Set<SovereignAutoViewTab>([
  'memory',
  'remote',
  'telemetry',
  'readiness',
  'integrity',
  'findings',
  'health',
  'runtime',
  'coverage',
]);
const DEFAULT_AUTO_SWITCH_INACTIVITY_MS = 3_000;
const DEFAULT_CONFIDENCE_THRESHOLD = 0.8;

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function normalizeNowMs(input: SovereignAutoViewInput): number | null {
  return isFiniteNumber(input.nowMs) ? input.nowMs : null;
}

function hasCompletedTab(input: SovereignAutoViewInput, tab: SovereignAutoViewTab | undefined): boolean {
  return Boolean(tab && input.completedTabs?.includes(tab));
}

function deriveActiveSignals(input: SovereignAutoViewInput): Set<SovereignAutoViewSignal> {
  const signals = new Set<SovereignAutoViewSignal>(input.activeSignals ?? []);

  if (input.repoReady) signals.add('repo-ready');
  if (input.activeStep) signals.add('runtime-active');
  if (input.isPublishing) signals.add('publishing');
  if (input.isWatchingWorkflow) signals.add('workflow-watch');
  if (input.workflowStatus === 'red') signals.add('workflow-red');
  if (input.workflowStatus === 'pending' || input.workflowStatus === 'unknown') signals.add('workflow-pending');
  if (input.workflowStatus === 'green') signals.add('workflow-green');
  if (input.hasPackage) signals.add('package-ready');
  if (input.hasDiffSources) signals.add('diff-ready');
  if (input.hasActivePatterns) signals.add('patterns-active');
  if (input.hasActiveTelemetry) signals.add('telemetry-active');

  return signals;
}

export function isSovereignAutoViewManualOverrideActive(input: SovereignAutoViewInput): boolean {
  const nowMs = normalizeNowMs(input);
  if (nowMs === null || !isFiniteNumber(input.manualOverrideUntil)) return false;
  return input.manualOverrideUntil > nowMs;
}

export function isSovereignAutoViewUserInactive(
  input: SovereignAutoViewInput,
  thresholdMs = input.autoSwitchInactivityMs ?? DEFAULT_AUTO_SWITCH_INACTIVITY_MS,
): boolean {
  const nowMs = normalizeNowMs(input);
  // recentUserInteractionUntil takes precedence: if set and still in the future, user is considered active.
  if (nowMs !== null && isFiniteNumber(input.recentUserInteractionUntil) && input.recentUserInteractionUntil > nowMs) {
    return false;
  }
  if (nowMs === null || !isFiniteNumber(input.lastUserInteractionAt)) return true;
  return nowMs - input.lastUserInteractionAt >= thresholdMs;
}

export function isSovereignAutoViewConfidenceMatched(
  input: SovereignAutoViewInput,
  threshold = input.patternConfidenceThreshold ?? DEFAULT_CONFIDENCE_THRESHOLD,
): boolean {
  return isFiniteNumber(input.patternConfidence) && input.patternConfidence >= threshold;
}

export function evaluateSovereignAutoViewConditions(
  conditions: SovereignAutoViewCondition[],
  input: SovereignAutoViewInput,
): boolean {
  const activeSignals = deriveActiveSignals(input);

  return conditions.every((condition) => {
    switch (condition.type) {
      case 'SIGNAL_ACTIVE':
        return Boolean(condition.signal && activeSignals.has(condition.signal));
      case 'TAB_COMPLETED':
        return hasCompletedTab(input, condition.tab);
      case 'USER_INACTIVE':
        return isSovereignAutoViewUserInactive(input, condition.thresholdMs);
      case 'CONFIDENCE_MATCHED':
        return isSovereignAutoViewConfidenceMatched(input, condition.confidenceThreshold);
      case 'MANUAL_OVERRIDE_CLEAR':
        return !isSovereignAutoViewManualOverrideActive(input);
      default:
        return false;
    }
  });
}

function canRunSuggestionSwitch(input: SovereignAutoViewInput): boolean {
  if (isSovereignAutoViewManualOverrideActive(input)) return false;
  // planningConfirmed gates suggestion switching: user must confirm before auto-routing takes over.
  if (input.planningConfirmed === false) return false;
  if (isSovereignAutoViewUserInactive(input)) return true;
  return isSovereignAutoViewConfidenceMatched(input);
}

function keepCurrent(input: SovereignAutoViewInput, reason: string): SovereignAutoViewDecision {
  return { shouldSwitch: false, tab: input.activeTab, reason };
}

function switchTo(input: SovereignAutoViewInput, tab: SovereignAutoViewTab, reason: string): SovereignAutoViewDecision {
  return { shouldSwitch: tab !== input.activeTab, tab, reason };
}

export function validateSovereignAutoViewInput(input: SovereignAutoViewInput): string[] {
  const errors: string[] = [];

  if (!ALL_KNOWN_TABS.has(input.activeTab)) errors.push(`Unknown active tab: ${input.activeTab}`);
  if (input.workflowStatus && !VALID_WORKFLOW_STATUSES.includes(input.workflowStatus)) errors.push(`Unknown workflow status: ${input.workflowStatus}`);
  if (input.activeStep && !Object.prototype.hasOwnProperty.call(STEP_TABS, input.activeStep)) errors.push(`Unknown active step: ${input.activeStep}`);
  for (const tab of input.completedTabs ?? []) {
    if (!ALL_KNOWN_TABS.has(tab)) errors.push(`Unknown completed tab: ${tab}`);
  }
  if (input.nowMs !== undefined && !isFiniteNumber(input.nowMs)) errors.push('nowMs must be a finite number.');
  if (input.lastUserInteractionAt !== undefined && !isFiniteNumber(input.lastUserInteractionAt)) errors.push('lastUserInteractionAt must be a finite number.');
  if (input.manualOverrideUntil !== undefined && !isFiniteNumber(input.manualOverrideUntil)) errors.push('manualOverrideUntil must be a finite number.');
  if (input.recentUserInteractionUntil !== undefined && !isFiniteNumber(input.recentUserInteractionUntil)) errors.push('recentUserInteractionUntil must be a finite number.');
  if (input.patternConfidence !== undefined && !isFiniteNumber(input.patternConfidence)) errors.push('patternConfidence must be a finite number.');
  if (input.planningConfirmed !== undefined && typeof input.planningConfirmed !== 'boolean') errors.push('planningConfirmed must be a boolean.');

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

  if (input.activeStep) return switchTo(input, STEP_TABS[input.activeStep], `Active runtime step ${input.activeStep} owns the ${STEP_TABS[input.activeStep]} view.`);
  if (input.isPublishing) return switchTo(input, 'workflow', 'Draft PR publishing should show the workflow/log view.');
  if (input.isWatchingWorkflow) return switchTo(input, 'workflow', 'Workflow watch is running and should stay visible.');
  if (input.workflowStatus === 'red') return switchTo(input, 'repair', 'Red workflow status should surface the repair view.');
  if (input.workflowStatus === 'pending' || input.workflowStatus === 'unknown') return switchTo(input, 'workflow', 'Non-final workflow status should stay on workflow watch.');

  if (input.activeTab === 'builder') {
    return keepCurrent(input, 'Builder was selected by the user and remains the active planning workspace.');
  }

  if (SIDE_TABS.has(input.activeTab)) {
    return keepCurrent(input, 'Intentional side tabs stay visible when no runtime step owns the view.');
  }

  if (!canRunSuggestionSwitch(input)) {
    return keepCurrent(input, 'Manual override or recent user activity paused suggestion-only auto switching.');
  }

  if (input.workflowStatus === 'green' && input.hasPackage && input.activeTab === 'workflow') {
    return input.hasDiffSources
      ? switchTo(input, 'diff', 'Green workflow with diff sources loaded - show the diff.')
      : switchTo(input, 'files', 'Green workflow with generated package - show files view.');
  }

  if (input.hasPackage && input.hasDiffSources && input.workflowStatus === 'idle' && input.activeTab === 'files') {
    return switchTo(input, 'diff', 'Files were reviewed and diff sources are loaded - show the diff.');
  }

  return keepCurrent(input, 'No auto view change required without an active runtime step or explicit workflow state.');
}
