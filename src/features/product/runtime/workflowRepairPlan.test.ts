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
    const plan = buildWorkflowRepairPlan(null);
    expect(plan.blocked).toBe(true);
    expect(() => assertWorkflowRepairPlanReady(plan)).toThrow('Workflow Watch');
  });

  it('blocks green workflows because no repair is needed', () => {
    const plan = buildWorkflowRepairPlan(report({
      status: 'green',
      checks: [{ name: 'ci', status: 'green', source: 'local', summary: 'passed' }],
    }));
    expect(plan.blocked).toBe(true);
    expect(plan.severity).toBe('none');
  });

  it('builds a targeted repair mission from failed checks', () => {
    const plan = buildWorkflowRepairPlan(report({
      status: 'red',
      checks: [
        { name: 'lint', status: 'red', source: 'local', summary: 'eslint failed' },
        { name: 'build', status: 'red', source: 'local', summary: 'tsc failed' },
      ],
    }));

    expect(plan.blocked).toBe(false);
    expect(plan.severity).toBe('high');
    expect(plan.mission).toContain('lint, build');
    expect(plan.actions.flatMap((action) => action.suggestedFiles)).toContain('package.json');
    expect(() => assertWorkflowRepairPlanReady(plan)).not.toThrow();
  });

  it('waits when checks are only pending', () => {
    const plan = buildWorkflowRepairPlan(report({
      status: 'pending',
      checks: [{ name: 'ci', status: 'pending', source: 'local', summary: 'running' }],
    }));
    expect(plan.blocked).toBe(true);
    expect(plan.reason).toContain('pending');
  });

  it('does not fabricate repair mission from unknown status', () => {
    const plan = buildWorkflowRepairPlan(report({
      status: 'unknown',
      checks: [],
    }));
    expect(plan.blocked).toBe(true);
    expect(plan.severity).toBe('low');
    expect(plan.actions).toHaveLength(0);
  });

  it('blocks when errors exist but no failed checks', () => {
    const plan = buildWorkflowRepairPlan(report({
      status: 'unknown',
      checks: [],
      errors: ['GitHub API rate limited'],
    }));
    expect(plan.blocked).toBe(false);
    expect(plan.severity).toBe('medium');
    expect(plan.actions).toHaveLength(1);
  });

  it('maps lint check failure to correct suggested files', () => {
    const plan = buildWorkflowRepairPlan(report({
      status: 'red',
      checks: [{ name: 'lint', status: 'red', source: 'check-run', summary: 'ESLint found 5 errors' }],
    }));
    expect(plan.blocked).toBe(false);
    expect(plan.actions[0].suggestedFiles).toContain('src/**/*');
    expect(plan.actions[0].suggestedFiles).toContain('eslint.config.*');
  });

  it('maps test check failure to correct suggested files', () => {
    const plan = buildWorkflowRepairPlan(report({
      status: 'red',
      checks: [{ name: 'test', status: 'red', source: 'check-run', summary: 'Vitest failed' }],
    }));
    expect(plan.blocked).toBe(false);
    expect(plan.actions[0].suggestedFiles).toContain('src/**/*.test.ts');
    expect(plan.actions[0].suggestedFiles).toContain('src/**/*.test.tsx');
  });

  it('maps build check failure to correct suggested files', () => {
    const plan = buildWorkflowRepairPlan(report({
      status: 'red',
      checks: [{ name: 'build', status: 'red', source: 'check-run', summary: 'Vite build failed' }],
    }));
    expect(plan.blocked).toBe(false);
    expect(plan.actions[0].suggestedFiles).toContain('tsconfig.json');
    expect(plan.actions[0].suggestedFiles).toContain('vite.config.*');
  });

  it('derives severity from number of failed checks', () => {
    const single = buildWorkflowRepairPlan(report({
      status: 'red',
      checks: [{ name: 'lint', status: 'red', source: 'local', summary: 'failed' }],
    }));
    expect(single.severity).toBe('medium');

    const multi = buildWorkflowRepairPlan(report({
      status: 'red',
      checks: [
        { name: 'lint', status: 'red', source: 'local', summary: 'failed' },
        { name: 'test', status: 'red', source: 'local', summary: 'failed' },
      ],
    }));
    expect(multi.severity).toBe('high');
  });
});
