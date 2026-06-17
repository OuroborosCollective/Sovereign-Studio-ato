import { describe, expect, it } from 'vitest';
import { buildAutoHealFollowupPlan } from './autoHealFollowupPlan';
import type { WorkflowWatchReport } from './workflowWatch';

const report: WorkflowWatchReport = {
  status: 'red',
  summary: 'Needs follow-up.',
  commitSha: 'abc123',
  branch: 'main',
  checkedAt: 1000,
  errors: [],
  warnings: [],
  checks: [{ name: 'runtime', status: 'red', source: 'check-run', summary: 'needs follow-up' }],
  fixes: [],
};

describe('autoHealFollowupPlan', () => {
  it('blocks without report or without red status', () => {
    expect(buildAutoHealFollowupPlan(null).blocked).toBe(true);
    expect(buildAutoHealFollowupPlan({ ...report, status: 'green', summary: 'ok' }).enabled).toBe(false);
  });

  it('builds reviewed follow-up mission', () => {
    const plan = buildAutoHealFollowupPlan(report, []);

    expect(plan.enabled).toBe(true);
    expect(plan.blocked).toBe(false);
    expect(plan.mission).toContain('runtime');
    expect(plan.requiredGates.length).toBeGreaterThan(0);
  });
});
