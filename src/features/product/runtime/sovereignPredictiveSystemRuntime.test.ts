import { describe, expect, it } from 'vitest';
import type { CapabilityDecision } from './sovereignCapabilityTypes';
import { appendSovereignActionEvent, createSovereignActionStreamState } from './sovereignActionStreamRuntime';
import { hasPredictiveSystemWork, runPredictiveSystemTick } from './sovereignPredictiveSystemRuntime';

const packageRequiredDecision: CapabilityDecision = {
  route: 'draft-pr-runtime',
  capability: 'draft_pr',
  allowed: false,
  reason: 'Draft PR Runtime blockiert: Patch-Paket/Diff muss zuerst erzeugt werden',
  blocker: 'package_required',
  nextAction: 'generate_patch_package',
};

describe('sovereignPredictiveSystemRuntime', () => {
  it('turns a router package gate into event, menu and inspector outputs', () => {
    const output = runPredictiveSystemTick({
      capabilityDecision: packageRequiredDecision,
      eventRoute: 'runtime',
    });

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

    expect(output.prediction?.signal).toBe('none');
    expect(output.actionEvent).toBeNull();
    expect(output.menuSuggestions).toEqual([]);
    expect(hasPredictiveSystemWork(output)).toBe(false);
  });
});
