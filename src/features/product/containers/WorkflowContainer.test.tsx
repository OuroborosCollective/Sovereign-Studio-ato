import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WorkflowContainer } from './WorkflowContainer';
import type { WorkflowWatchReport } from '../runtime/workflowWatch';
import type { WorkflowRepairPlan } from '../runtime/workflowRepairPlan';

const report: WorkflowWatchReport = {
  status: 'green',
  summary: 'All checks passed.',
  commitSha: 'abc123',
  branch: 'main',
  checkedAt: Date.now(),
  errors: [],
  warnings: [],
  checks: [{ name: 'unit', status: 'green' as const, source: 'check-run' as const, summary: 'ok' }],
  fixes: [],
};

const repairPlan: WorkflowRepairPlan = {
  blocked: false,
  severity: 'medium',
  summary: 'Repair plan ready.',
  reason: 'Workflow has a failing check.',
  mission: 'Fix workflow check',
  actions: [],
};

describe('WorkflowContainer', () => {
  it('renders watch mode and triggers watch when allowed', () => {
    const onWatch = vi.fn();
    render(
      <WorkflowContainer
        mode="watch"
        report={report}
        repairPlan={repairPlan}
        isWatching={false}
        runtimeBusy={false}
        hasDraftCommit={true}
        onWatch={onWatch}
        onUseRepairMission={vi.fn()}
      />,
    );

    expect(screen.getByTestId('workflow-container')).toBeDefined();
    expect(screen.getByText(/All checks passed/i)).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /Watch Commit Checks/i }));
    expect(onWatch).toHaveBeenCalledOnce();
  });

  it('blocks watch mode until a draft commit exists', () => {
    render(
      <WorkflowContainer
        mode="watch"
        report={null}
        repairPlan={repairPlan}
        isWatching={false}
        runtimeBusy={false}
        hasDraftCommit={false}
        onWatch={vi.fn()}
        onUseRepairMission={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: /Watch Commit Checks/i })).toBeDisabled();
    expect(screen.getByText(/Create a Draft PR before watching/i)).toBeDefined();
  });

  it('renders repair mode and emits repair mission', () => {
    const onUseRepairMission = vi.fn();
    render(
      <WorkflowContainer
        mode="repair"
        report={report}
        repairPlan={repairPlan}
        isWatching={false}
        runtimeBusy={false}
        hasDraftCommit={true}
        onWatch={vi.fn()}
        onUseRepairMission={onUseRepairMission}
      />,
    );

    expect(screen.getByText(/Workflow Repair Planner/i)).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /Use Repair Mission/i }));
    expect(onUseRepairMission).toHaveBeenCalledWith('Fix workflow check');
  });
});
