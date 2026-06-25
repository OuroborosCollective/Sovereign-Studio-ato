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
  'draft-pr-publish': 'files',
  'workflow-watch': 'workflow',
  'repair-plan': 'repair',
};

const AUTO_VIEW_RULES: ReadonlyArray<{
  readonly tab: SovereignAutoViewTab;
  readonly reason: string;
  readonly when: (input: Required<Pick<SovereignAutoViewInput, 'hasPackage' | 'isPublishing' | 'isWatchingWorkflow'>> & SovereignAutoViewInput) => boolean;
}> = [
  {
    tab: 'files',
    reason: 'Draft PR publishing is active, so generated files stay visible.',
    when: (input) => input.isPublishing,
  },
  {
    tab: 'workflow',
    reason: 'Workflow watch is active, so workflow state stays visible.',
    when: (input) => input.isWatchingWorkflow,
  },
  {
    tab: 'repair',
    reason: 'Workflow is red, so repair guidance is the next safe surface.',
    when: (input) => input.workflowStatus === 'red',
  },
  {
    tab: 'workflow',
    reason: 'Workflow is pending, so checks remain visible.',
    when: (input) => input.workflowStatus === 'yellow',
  },
  {
    tab: 'diff',
    reason: 'Diff sources are loaded, so review the diff before publishing.',
    when: (input) => Boolean(input.hasDiffSources),
  },
  {
    tab: 'files',
    reason: 'A package exists, so generated files are ready for review.',
    when: (input) => input.hasPackage,
  },
  {
    tab: 'builder',
    reason: 'Repo is ready and no result exists yet, so chat/builder remains the planning surface.',
    when: (input) => Boolean(input.repoReady),
  },
  {
    tab: 'repo',
    reason: 'Repo is not ready, so setup remains the safe surface.',
    when: (input) => !input.repoReady,
  },
];

function protectManualSideTab(input: SovereignAutoViewInput): SovereignAutoViewDecision | null {
  const sideTabs: SovereignAutoViewTab[] = ['memory', 'remote', 'telemetry', 'monitor', 'readiness', 'integrity', 'findings', 'health', 'runtime', 'coverage'];
  const recentUserInteractionUntil = input.recentUserInteractionUntil ?? input.manualOverrideUntil;
  const now = input.nowMs ?? Date.now();
  if (sideTabs.includes(input.activeTab) && recentUserInteractionUntil && now < recentUserInteractionUntil) {
    return {
      shouldSwitch: false,
      tab: input.activeTab,
      reason: `Manual side tab ${input.activeTab} is still protected by recent user interaction.`,
    };
  }
  return null;
}

export function decideSovereignAutoView(input: SovereignAutoViewInput): SovereignAutoViewDecision {
  const manualProtection = protectManualSideTab(input);
  if (manualProtection) return manualProtection;

  if (input.activeStep) {
    const tab = STEP_TABS[input.activeStep];
    return {
      shouldSwitch: input.activeTab !== tab,
      tab,
      reason: `Sequential runtime step ${input.activeStep} is active.`,
    };
  }

  for (const rule of AUTO_VIEW_RULES) {
    if (rule.when(input as Required<Pick<SovereignAutoViewInput, 'hasPackage' | 'isPublishing' | 'isWatchingWorkflow'>> & SovereignAutoViewInput)) {
      return {
        shouldSwitch: input.activeTab !== rule.tab,
        tab: rule.tab,
        reason: rule.reason,
      };
    }
  }

  return {
    shouldSwitch: false,
    tab: input.activeTab,
    reason: 'No auto-view rule matched.',
  };
}
