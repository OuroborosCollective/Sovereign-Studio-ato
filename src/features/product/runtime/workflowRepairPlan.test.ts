import { describe, expect, it } from 'vitest';
import {
  assertWorkflowRepairPlanReady,
  buildWorkflowRepairPlan,
} from './workflowRepairPlan';
import type { WorkflowWatchReport } from './workflowWatch';

function report(overrides: Partial<WorkflowWatchReport>): WorkflowWatchReport {
  return {
    status: 'idle',
    checkedAt: 1,
    checks: [],
    errors: [],
    warnings: [],
    fixes: [],
    summary: 'test',
    ...overrides,
  };
}

describe('workflowRepairPlan', () => {
  it('blocks when no workflow report exists', () => {
    const plan = buildWorkflowRepairPlan({ report: null });
    expect(plan.blocked).toBe(true);
    expect(() => assertWorkflowRepairPlanReady(plan)).toThrow('Workflow Watch');
    expect(plan.evidenceLedger?.entries.length).toBeGreaterThan(0);
  });

  it('blocks green workflows because no repair is needed', () => {
    const plan = buildWorkflowRepairPlan({ report: report({
      status: 'green',
      checks: [{ name: 'ci', status: 'green', source: 'local', summary: 'passed' }],
    })});
    expect(plan.blocked).toBe(true);
    expect(plan.severity).toBe('none');
    expect(plan.evidenceLedger?.entries.some((e) => e.status === 'success')).toBe(true);
  });

  it('builds a targeted repair mission from failed checks', () => {
    const plan = buildWorkflowRepairPlan({ report: report({
      status: 'red',
      checks: [
        { name: 'lint', status: 'red', source: 'local', summary: 'eslint failed' },
        { name: 'build', status: 'red', source: 'local', summary: 'tsc failed' },
      ],
    })});

    expect(plan.blocked).toBe(false);
    expect(plan.severity).toBe('high');
    expect(plan.mission).toContain('lint, build');
    expect(plan.actions.flatMap((action) => action.suggestedFiles)).toContain('package.json');
    expect(plan.evidenceLedger?.entries.some((e) => e.status === 'success' && e.category === 'repair')).toBe(true);
    expect(() => assertWorkflowRepairPlanReady(plan)).not.toThrow();
  });

  it('waits when checks are only pending', () => {
    const plan = buildWorkflowRepairPlan({ report: report({
      status: 'pending',
      checks: [{ name: 'ci', status: 'pending', source: 'local', summary: 'running' }],
    })});
    expect(plan.blocked).toBe(true);
    expect(plan.reason).toContain('pending');
    expect(plan.evidenceLedger?.entries.some((e) => e.status === 'pending')).toBe(true);
  });

  it('records access errors with evidence', () => {
    const plan = buildWorkflowRepairPlan({ report: report({
      status: 'unknown',
      errors: ['Token expired'],
    })});
    expect(plan.blocked).toBe(false);
    expect(plan.evidenceLedger?.entries.some((e) => e.status === 'failure' && e.reason.includes('Token expired'))).toBe(true);
  });
});
