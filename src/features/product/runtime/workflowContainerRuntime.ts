import type { WorkflowWatchReport } from './workflowWatch';
import type { WorkflowRepairPlan } from './workflowRepairPlan';

export type WorkflowContainerMode = 'watch' | 'repair';

export interface WorkflowContainerRuntimeInput {
  mode: WorkflowContainerMode;
  isWatching: boolean;
  runtimeBusy: boolean;
  hasDraftCommit: boolean;
  report: WorkflowWatchReport | null;
  repairPlan?: WorkflowRepairPlan | null;
}

export interface WorkflowContainerRuntimeState {
  canWatch: boolean;
  canUseRepairMission: boolean;
  status: 'idle' | 'ready' | 'watching' | 'blocked' | 'red' | 'green' | 'pending';
  message: string;
}

export function deriveWorkflowContainerState(input: WorkflowContainerRuntimeInput): WorkflowContainerRuntimeState {
  if (input.isWatching) {
    return { canWatch: false, canUseRepairMission: false, status: 'watching', message: 'Workflow watch is running.' };
  }
  if (input.runtimeBusy) {
    return { canWatch: false, canUseRepairMission: false, status: 'blocked', message: 'Sequential runtime is busy.' };
  }
  if (input.mode === 'watch' && !input.hasDraftCommit) {
    return { canWatch: false, canUseRepairMission: false, status: 'blocked', message: 'Create a Draft PR before watching workflow checks.' };
  }

  if (input.mode === 'repair') {
    const plan = input.repairPlan;
    if (!plan || plan.blocked) {
      return { canWatch: input.hasDraftCommit, canUseRepairMission: false, status: 'blocked', message: plan?.reason ?? 'No repair plan is available.' };
    }
    return { canWatch: input.hasDraftCommit, canUseRepairMission: true, status: 'ready', message: plan.summary };
  }

  if (!input.report) {
    return { canWatch: true, canUseRepairMission: false, status: 'idle', message: 'Workflow watch is ready.' };
  }

  if (input.report.status === 'green') return { canWatch: true, canUseRepairMission: false, status: 'green', message: input.report.summary };
  if (input.report.status === 'red') return { canWatch: true, canUseRepairMission: true, status: 'red', message: input.report.summary };
  return { canWatch: true, canUseRepairMission: false, status: 'pending', message: input.report.summary };
}

export function workflowModeLabel(mode: WorkflowContainerMode): string {
  return mode === 'repair' ? 'Workflow Repair' : 'Workflow Watch';
}
