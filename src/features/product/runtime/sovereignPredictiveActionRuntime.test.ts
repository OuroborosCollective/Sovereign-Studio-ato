import { describe, expect, it } from 'vitest';
import type { CapabilityDecision } from './sovereignCapabilityTypes';
import {
  buildPredictiveActionSummary,
  createPredictiveActionState,
  derivePredictiveActionEvent,
  derivePredictiveInspectorSignals,
  derivePredictiveMenuSuggestions,
  learnFromActionStream,
  predictNextRuntimeAction,
  recordPredictiveActionOutcome,
} from './sovereignPredictiveActionRuntime';
import { appendSovereignActionEvent, createSovereignActionStreamState } from './sovereignActionStreamRuntime';

const packageRequiredDecision: CapabilityDecision = {
  route: 'draft-pr-runtime',
  capability: 'draft_pr',
  allowed: false,
  reason: 'Draft PR Runtime blockiert: Patch-Paket/Diff muss zuerst erzeugt werden',
  blocker: 'package_required',
  nextAction: 'generate_patch_package',
};

describe('sovereignPredictiveActionRuntime', () => {
  it('predicts patch package generation for package_required across active surfaces', () => {
    const state = createPredictiveActionState();
    const prediction = predictNextRuntimeAction(packageRequiredDecision, state);

    expect(prediction.action).toBe('generate_patch_package');
    expect(prediction.signal).toBe('runtime_contract');
    expect(prediction.confidence).toBe('high');
    expect(prediction.reason).toContain('Patch-Paket');
    expect(prediction.surfaces).toEqual(expect.arrayContaining([
      'router',
      'action_stream',
      'menu',
      'inspector',
      'draft_pr',
      'runtime',
    ]));
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
    expect(prediction.surfaces).toEqual(['router']);
  });

  it('learns from successful observations and activates the observed nerve surface without storing secrets', () => {
    const base = createPredictiveActionState();
    const learned = recordPredictiveActionOutcome(base, {
      blocker: 'github_access_missing',
      predictedAction: 'validate_github_access',
      actualAction: 'validate_github_access',
      succeeded: true,
      reason: 'User validated GitHub access successfully.',
      observedAt: 100,
      surface: 'github_access',
    });

    const prediction = predictNextRuntimeAction({
      route: 'sovereign-agent',
      capability: 'code_patch_plan',
      allowed: false,
      reason: 'Sovereign Agent Executor Route blockiert: GitHub-Zugang fehlt',
      blocker: 'github_access_missing',
      nextAction: 'validate_github_access',
    }, learned);

    const githubNerve = learned.nerve.find((node) => node.surface === 'github_access');

    expect(prediction.action).toBe('validate_github_access');
    expect(prediction.learnedFrom).toBeGreaterThanOrEqual(1);
    expect(githubNerve?.active).toBe(true);
    expect(githubNerve?.lastAction).toBe('validate_github_access');
    expect(JSON.stringify(learned)).not.toMatch(/gh[pousr]_[A-Za-z0-9_]{20,}/);
    expect(JSON.stringify(learned)).not.toMatch(/github_pat_[A-Za-z0-9_]{20,}/);
  });

  it('records misses when predicted action did not match the actual recovery action', () => {
    const base = createPredictiveActionState();
    const learned = recordPredictiveActionOutcome(base, {
      blocker: 'executor_unavailable',
      predictedAction: 'start_workspace',
      actualAction: 'start_agent',
      succeeded: true,
      reason: 'Sovereign Agent was connected instead of workspace.',
      observedAt: 200,
      surface: 'executor',
    });

    const pattern = learned.patterns.find(
      (entry) => entry.blocker === 'executor_unavailable' && entry.action === 'start_workspace',
    );

    expect(pattern?.hits).toBe(1); // one contract hit remains as baseline
    expect(pattern?.misses).toBe(1);
    expect(pattern?.surfaces).toContain('executor');
  });

  it('derives menu suggestions for every connected surface in the prediction', () => {
    const prediction = predictNextRuntimeAction(packageRequiredDecision, createPredictiveActionState());
    const suggestions = derivePredictiveMenuSuggestions(prediction);

    expect(suggestions.length).toBeGreaterThan(1);
    expect(suggestions.map((item) => item.surface)).toEqual(expect.arrayContaining(['menu', 'draft_pr', 'runtime']));
    expect(suggestions.every((item) => item.action === 'generate_patch_package')).toBe(true);
    expect(suggestions.some((item) => item.label === 'Patch/Diff erzeugen')).toBe(true);
  });

  it('derives inspector signals from active prediction and learned nerve nodes', () => {
    const base = createPredictiveActionState();
    const learned = recordPredictiveActionOutcome(base, {
      blocker: 'package_required',
      predictedAction: 'generate_patch_package',
      actualAction: 'generate_patch_package',
      succeeded: true,
      reason: 'Patch package was generated.',
      observedAt: 300,
      surface: 'draft_pr',
    });
    const prediction = predictNextRuntimeAction(packageRequiredDecision, learned);
    const signals = derivePredictiveInspectorSignals(learned, prediction);

    expect(signals.map((signal) => signal.id)).toContain('predictive-next-generate_patch_package');
    expect(signals.some((signal) => signal.id === 'predictive-nerve-active')).toBe(true);
    expect(signals.every((signal) => signal.prompt.length > 0)).toBe(true);
  });

  it('creates an action-stream event from a prediction instead of relying on UI-only hints', () => {
    const prediction = predictNextRuntimeAction(packageRequiredDecision, createPredictiveActionState());
    const event = derivePredictiveActionEvent(prediction, 'draft-pr-runtime' as never);

    expect(event).not.toBeNull();
    expect(event?.kind).toBe('blocked');
    expect(event?.state).toBe('blocked');
    expect(event?.detail).toContain('generate_patch_package');
  });

  it('learns from action stream blockers so the nerve can follow runtime events', () => {
    const stream = appendSovereignActionEvent(createSovereignActionStreamState(), {
      kind: 'patch_blocked',
      route: 'github-patch',
      label: 'Patch/Draft-PR Route wartet auf Ergebnis',
      detail: 'Patch-Paket muss zuerst erzeugt werden.',
      state: 'blocked',
      createdAt: 400,
    });

    const learned = learnFromActionStream(createPredictiveActionState(), stream);
    const prediction = predictNextRuntimeAction(packageRequiredDecision, learned);
    const actionStreamNerve = learned.nerve.find((node) => node.surface === 'action_stream');

    expect(prediction.action).toBe('generate_patch_package');
    expect(actionStreamNerve?.active).toBe(true);
    expect(actionStreamNerve?.lastBlocker).toBe('package_required');
  });

  it('knows agent surfaces without treating them as UI truth', () => {
    const state = createPredictiveActionState();

    expect(state.nerve.map((node) => node.surface)).toEqual(expect.arrayContaining([
      'agent_job',
      'agent_workspace',
      'agent_tool',
      'agent_evidence',
      'agent_pattern',
    ]));
  });

  it('activates agent evidence nerve from runtime action stream blockers', () => {
    const stream = appendSovereignActionEvent(createSovereignActionStreamState(), {
      kind: 'agent_result_blocked',
      route: 'agent-evidence',
      label: 'Agent Ergebnis blockiert',
      detail: 'Workspace benötigt echte Evidence bevor Draft PR vorbereitet wird.',
      state: 'blocked',
      createdAt: 500,
    });

    const learned = learnFromActionStream(createPredictiveActionState(), stream);
    const nerve = learned.nerve.find((node) => node.surface === 'agent_evidence');

    expect(nerve?.active).toBe(true);
    expect(nerve?.lastBlocker).toBe('workspace_required');
  });

  it('labels agent next actions for menu suggestions', () => {
    const decision = {
      action: 'run_agent_tool',
      signal: 'runtime_contract',
      confidence: 'high',
      reason: 'Agent Workspace ist bereit; nächster geprüfter Schritt ist Tool-Lauf.',
      learnedFrom: 1,
      surfaces: ['agent_tool'],
    } as const;

    const suggestions = derivePredictiveMenuSuggestions(decision);

    expect(suggestions[0]?.label).toBe('Agent Tool ausführen');
    expect(suggestions[0]?.surface).toBe('agent_tool');
  });

  it('builds user-visible summary from prediction', () => {
    const prediction = predictNextRuntimeAction(packageRequiredDecision, createPredictiveActionState());
    const summary = buildPredictiveActionSummary(prediction);

    expect(summary).toContain('Nächste Aktion: generate_patch_package');
    expect(summary).toContain('Sicherheit: high');
    expect(summary).toContain('Oberflächen:');
  });
});
