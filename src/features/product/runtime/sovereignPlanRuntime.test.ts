import { describe, expect, it } from 'vitest';
import {
  blockSovereignPlanStep,
  completeSovereignPlanStep,
  createSovereignPlan,
  createSovereignPlanFromRequest,
  deriveSovereignPlanNextAction,
  getSovereignPlanNextStep,
  markSovereignPlanStepInProgress,
  summarizeSovereignPlan,
} from './sovereignPlanRuntime';

describe('sovereignPlanRuntime', () => {
  it('creates a compact plan without percentage progress', () => {
    const plan = createSovereignPlan({
      title: 'Runtime Auftrag',
      steps: ['Repo prüfen', 'Patch planen'],
      now: 1700000000000,
    });

    const summary = summarizeSovereignPlan(plan);
    expect(plan.steps).toHaveLength(2);
    expect(summary.notStarted).toBe(2);
    expect(summary.nextAllowedAction).toBe('start_step');
    expect(summary.text).not.toContain('%');
  });

  it('moves the next step through in_progress and completed', () => {
    let plan = createSovereignPlan({
      title: 'Runtime Auftrag',
      steps: ['Repo prüfen', 'Patch planen'],
      now: 1700000000000,
    });

    const first = getSovereignPlanNextStep(plan);
    if (!first) throw new Error('expected first step');

    plan = markSovereignPlanStepInProgress(plan, first.id, 'started', 1700000000001);
    expect(plan.steps[0].status).toBe('in_progress');
    expect(deriveSovereignPlanNextAction(plan)).toBe('continue_step');

    plan = completeSovereignPlanStep(plan, first.id, 'done', 'repo://snapshot', 1700000000002);
    expect(plan.steps[0].status).toBe('completed');
    expect(plan.steps[0].artifacts).toContain('repo://snapshot');
    expect(getSovereignPlanNextStep(plan)?.id).toBe(plan.steps[1].id);
  });

  it('blocks a step and requires blocker resolution', () => {
    let plan = createSovereignPlan({
      title: 'Runtime Auftrag',
      steps: ['GitHub Write prüfen'],
      now: 1700000000000,
    });

    plan = blockSovereignPlanStep(plan, plan.steps[0].id, 'github_access_missing', 'needs access');
    const summary = summarizeSovereignPlan(plan);

    expect(plan.steps[0].status).toBe('blocked');
    expect(summary.blocked).toBe(1);
    expect(summary.nextAllowedAction).toBe('resolve_blocker');
    expect(summary.text).toContain('github_access_missing');
  });

  it('finishes when all steps are completed', () => {
    let plan = createSovereignPlan({
      title: 'Runtime Auftrag',
      steps: ['A', 'B'],
      now: 1700000000000,
    });

    plan = completeSovereignPlanStep(plan, plan.steps[0].id);
    plan = completeSovereignPlanStep(plan, plan.steps[1].id);

    expect(deriveSovereignPlanNextAction(plan)).toBe('finish_plan');
    expect(summarizeSovereignPlan(plan).completed).toBe(2);
  });

  it('creates a standard Sovereign request plan', () => {
    const plan = createSovereignPlanFromRequest('Bitte Patch sauber planen', 1700000000000);

    expect(plan.title).toBe('Bitte Patch sauber planen');
    expect(plan.steps.map((step) => step.title)).toContain('Runtime-Gates prüfen');
    expect(summarizeSovereignPlan(plan).text).not.toContain('%');
  });
});
