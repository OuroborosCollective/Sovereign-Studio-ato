import { describe, expect, it } from 'vitest';
import type { CapabilityDecision } from './sovereignCapabilityTypes';
import { appendSovereignActionEvent, createSovereignActionStreamState } from './sovereignActionStreamRuntime';
import { hasPredictiveSystemWork, runPredictiveSystemTick } from './sovereignPredictiveSystemRuntime';
import { recordPredictiveActionOutcome, createPredictiveActionState } from './sovereignPredictiveActionRuntime';

const packageRequiredDecision: CapabilityDecision = {
  route: 'draft-pr-runtime',
  capability: 'draft_pr',
  allowed: false,
  reason: 'Draft PR Runtime blockiert: Patch-Paket/Diff muss zuerst erzeugt werden',
  blocker: 'package_required',
  nextAction: 'generate_patch_package',
};

describe('sovereignPredictiveSystemRuntime', () => {
  it('turns a router package gate into policy-allowed event, menu and inspector outputs', () => {
    const output = runPredictiveSystemTick({
      capabilityDecision: packageRequiredDecision,
      eventRoute: 'runtime',
      runtime: {
        repoReady: true,
        githubAccessState: 'ready',
        githubWriteAllowed: true,
        hasPackage: false,
      },
    });

    expect(output.policy.allowed).toBe(true);
    expect(output.prediction?.action).toBe('generate_patch_package');
    expect(output.actionEvent?.detail).toContain('generate_patch_package');
    expect(output.menuSuggestions.some((item) => item.label === 'Patch/Diff erzeugen')).toBe(true);
    expect(output.inspectorSignals.some((item) => item.id === 'predictive-next-generate_patch_package')).toBe(true);
    expect(hasPredictiveSystemWork(output)).toBe(true);
  });

  it('learns from action-stream blockers before predicting the next router action', () => {
    const stream = appendSovereignActionEvent(createSovereignActionStreamState(), {
      kind: 'patch_blocked',
      route: 'github-patch',
      label: 'Patch/Draft-PR Route wartet auf Ergebnis',
      detail: 'Patch-Paket muss zuerst erzeugt werden.',
      state: 'blocked',
      createdAt: 100,
    });

    const output = runPredictiveSystemTick({
      actionStream: stream,
      capabilityDecision: packageRequiredDecision,
      eventRoute: 'runtime',
    });

    const actionStreamNerve = output.state.nerve.find((node) => node.surface === 'action_stream');

    expect(actionStreamNerve?.active).toBe(true);
    expect(actionStreamNerve?.lastBlocker).toBe('package_required');
    expect(output.prediction?.action).toBe('generate_patch_package');
    expect(output.policy.allowed).toBe(true);
  });

  it('blocks policy-unsafe predictive output before it reaches menus', () => {
    const unsafeState = recordPredictiveActionOutcome(createPredictiveActionState(), {
      blocker: 'package_required',
      predictedAction: 'create_draft_pr',
      actualAction: 'create_draft_pr',
      succeeded: true,
      reason: 'Unsafe learned shortcut that skips patch package.',
      observedAt: 200,
      surface: 'draft_pr',
    });

    const output = runPredictiveSystemTick({
      state: unsafeState,
      capabilityDecision: {
        ...packageRequiredDecision,
        nextAction: 'create_draft_pr',
      },
      runtime: {
        githubAccessState: 'ready',
        hasPackage: false,
      },
    });

    expect(output.policy.allowed).toBe(false);
    expect(output.policy.violations.map((violation) => violation.code)).toContain('draft_pr_requires_patch_package');
    expect(output.actionEvent?.label).toBe('Predictive Runtime Policy blockiert');
    expect(output.menuSuggestions).toEqual([]);
    expect(hasPredictiveSystemWork(output)).toBe(false);
  });

  it('stays quiet when there is no blocker and no predictive work', () => {
    const output = runPredictiveSystemTick({
      capabilityDecision: {
        route: 'worker-chat',
        capability: 'free_chat',
        allowed: true,
        reason: 'Route gewählt: Worker-Chat Route',
        nextAction: 'run_worker',
      },
    });

    expect(output.policy.allowed).toBe(true);
    expect(output.prediction?.signal).toBe('none');
    expect(output.actionEvent).toBeNull();
    expect(output.menuSuggestions).toEqual([]);
    expect(hasPredictiveSystemWork(output)).toBe(false);
  });
});
