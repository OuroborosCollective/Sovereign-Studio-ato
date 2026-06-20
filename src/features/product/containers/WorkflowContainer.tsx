import React, { useEffect } from 'react';
import { WorkflowWatchPanel } from '../components/WorkflowWatchPanel';
import { WorkflowRepairPanel } from '../components/WorkflowRepairPanel';
import type { WorkflowWatchReport } from '../runtime/workflowWatch';
import type { WorkflowRepairPlan } from '../runtime/workflowRepairPlan';
import { publishSovereignDependencyCoachSignal } from '../runtime/sovereignDependencyCoachBridge';
import {
  deriveWorkflowContainerState,
  type WorkflowContainerMode,
} from '../runtime/workflowContainerRuntime';

export interface WorkflowContainerProps {
  mode: WorkflowContainerMode;
  report: WorkflowWatchReport | null;
  repairPlan: WorkflowRepairPlan;
  isWatching: boolean;
  runtimeBusy: boolean;
  hasDraftCommit: boolean;
  onWatch: () => void;
  onUseRepairMission: (mission: string) => void;
}

export function WorkflowContainer({
  mode,
  report,
  repairPlan,
  isWatching,
  runtimeBusy,
  hasDraftCommit,
  onWatch,
  onUseRepairMission,
}: WorkflowContainerProps) {
  const state = deriveWorkflowContainerState({
    mode,
    isWatching,
    runtimeBusy,
    hasDraftCommit,
    report,
    repairPlan,
  });

  useEffect(() => {
    const dependency = report?.dependencyLifecycle;
    if (!dependency) return;
    publishSovereignDependencyCoachSignal(dependency);
  }, [report?.dependencyLifecycle]);

  if (mode === 'repair') {
    return (
      <section data-testid="workflow-container" aria-label="Workflow Container">
        <p className="sr-only">{state.message}</p>
        <WorkflowRepairPanel plan={repairPlan} onUseMission={onUseRepairMission} />
      </section>
    );
  }

  return (
    <section data-testid="workflow-container" aria-label="Workflow Container">
      <p className="sr-only">{state.message}</p>
      <WorkflowWatchPanel
        report={report}
        isWatching={isWatching || runtimeBusy || !state.canWatch}
        onWatch={onWatch}
      />
    </section>
  );
}
