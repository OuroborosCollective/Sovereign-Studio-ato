import { describe, expect, it } from 'vitest';
import { deriveWorkflowContainerState, workflowModeLabel } from './workflowContainerRuntime';
import type { WorkflowWatchReport } from './workflowWatch';
import type { WorkflowRepairPlan } from './workflowRepairPlan';

const greenReport: WorkflowWatchReport = {
  status: 'green',
  summary: 'All checks passed.',
  commitSha: 'abc123',
  branch: 'main',
  checks: [],
  fixes: [],
};

const repairPlan: WorkflowRepairPlan = {
  blocked: false,
  severity: 'medium',
  summary: 'Repair available.',
  reason: 'Workflow is red.',
  mission: 'Fix workflow failure',
  actions: [],
};

describe('workflowContainerRuntime', () => {
  it('blocks watch without draft commit', () => {
    const state = deriveWorkflowContainerState({ mode: 'watch', isWatching: false, runtimeBusy: false, hasDraftCommit: false, report: null });
    expect(state.canWatch).toBe(false);
    expect(state.status).toBe('blocked');
    expect(state.message).toContain('Draft PR');
  });

  it('allows watch when draft commit exists', () => {
    const state = deriveWorkflowContainerState({ mode: 'watch', isWatching: false, runtimeBusy: false, hasDraftCommit: true, report: null });
    expect(state.canWatch).toBe(true);
    expect(state.status).toBe('idle');
  });

  it('reflects green reports', () => {
    const state = deriveWorkflowContainerState({ mode: 'watch', isWatching: false, runtimeBusy: false, hasDraftCommit: true, report: greenReport });
    expect(state.status).toBe('green');
    expect(state.message).toBe('All checks passed.');
  });

  it('allows repair mission when repair plan is unblocked', () => {
    const state = deriveWorkflowContainerState({ mode: 'repair', isWatching: false, runtimeBusy: false, hasDraftCommit: true, report: greenReport, repairPlan });
    expect(state.canUseRepairMission).toBe(true);
    expect(state.status).toBe('ready');
  });

  it('blocks while watching or runtime busy', () => {
    expect(deriveWorkflowContainerState({ mode: 'watch', isWatching: true, runtimeBusy: false, hasDraftCommit: true, report: null }).status).toBe('watching');
    expect(deriveWorkflowContainerState({ mode: 'watch', isWatching: false, runtimeBusy: true, hasDraftCommit: true, report: null }).status).toBe('blocked');
  });

  it('labels modes', () => {
    expect(workflowModeLabel('watch')).toBe('Workflow Watch');
    expect(workflowModeLabel('repair')).toBe('Workflow Repair');
  });
});
