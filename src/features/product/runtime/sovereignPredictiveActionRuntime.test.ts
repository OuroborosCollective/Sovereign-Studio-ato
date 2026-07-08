import { describe, expect, it } from 'vitest';
import type { CapabilityDecision } from './sovereignCapabilityTypes';
import {
  buildPredictiveActionSummary,
  createPredictiveActionState,
  predictNextRuntimeAction,
  recordPredictiveActionOutcome,
} from './sovereignPredictiveActionRuntime';

const packageRequiredDecision: CapabilityDecision = {
  route: 'draft-pr-runtime',
  capability: 'draft_pr',
  allowed: false,
  reason: 'Draft PR Runtime blockiert: Patch-Paket/Diff muss zuerst erzeugt werden',
  blocker: 'package_required',
  nextAction: 'generate_patch_package',
};

describe('sovereignPredictiveActionRuntime', () => {
  it('predicts patch package generation for package_required as runtime contract', () => {
    const state = createPredictiveActionState();
    const prediction = predictNextRuntimeAction(packageRequiredDecision, state);

    expect(prediction.action).toBe('generate_patch_package');
    expect(prediction.signal).toBe('runtime_contract');
    expect(prediction.confidence).toBe('high');
    expect(prediction.reason).toContain('Patch-Paket');
  });

  it('does not invent actions when no blocker exists', () => {
    const decision: CapabilityDecision = {
      route: 'worker-chat',
      capability: 'free_chat',
      allowed: true,
      reason: 'Route gewählt: Worker-Chat Route',
      nextAction: 'run_worker',
    };

    const prediction = predictNextRuntimeAction(decision, createPredictiveActionState());

    expect(prediction.action).toBe('run_worker');
    expect(prediction.signal).toBe('none');
    expect(prediction.confidence).toBe('none');
  });

  it('learns from successful observations without storing secrets', () => {
    const base = createPredictiveActionState();
    const learned = recordPredictiveActionOutcome(base, {
      blocker: 'github_access_missing',
      predictedAction: 'validate_github_access',
      actualAction: 'validate_github_access',
      succeeded: true,
      reason: 'User validated GitHub access successfully.',
      observedAt: 100,
    });

    const prediction = predictNextRuntimeAction({
      route: 'openhands',
      capability: 'code_patch_plan',
      allowed: false,
      reason: 'OpenHands Executor Route blockiert: GitHub-Zugang fehlt',
      blocker: 'github_access_missing',
      nextAction: 'validate_github_access',
    }, learned);

    expect(prediction.action).toBe('validate_github_access');
    expect(prediction.learnedFrom).toBe(1);
    expect(JSON.stringify(learned)).not.toMatch(/gh[pousr]_[A-Za-z0-9_]{20,}/);
    expect(JSON.stringify(learned)).not.toMatch(/github_pat_[A-Za-z0-9_]{20,}/);
  });

  it('records misses when predicted action did not match the actual recovery action', () => {
    const base = createPredictiveActionState();
    const learned = recordPredictiveActionOutcome(base, {
      blocker: 'executor_unavailable',
      predictedAction: 'start_workspace',
      actualAction: 'start_openhands',
      succeeded: true,
      reason: 'OpenHands was connected instead of workspace.',
      observedAt: 200,
    });

    const pattern = learned.patterns.find(
      (entry) => entry.blocker === 'executor_unavailable' && entry.action === 'start_workspace',
    );

    expect(pattern?.hits).toBe(0);
    expect(pattern?.misses).toBe(1);
  });

  it('builds user-visible summary from prediction', () => {
    const prediction = predictNextRuntimeAction(packageRequiredDecision, createPredictiveActionState());
    const summary = buildPredictiveActionSummary(prediction);

    expect(summary).toContain('Nächste Aktion: generate_patch_package');
    expect(summary).toContain('Sicherheit: high');
  });
});
