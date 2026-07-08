import type { CapabilityDecision } from './sovereignCapabilityTypes';
import type {
  SovereignActionEventInput,
  SovereignActionStreamState,
  SovereignActionRoute,
} from './sovereignActionStreamRuntime';
import {
  createPredictiveActionState,
  derivePredictiveActionEvent,
  derivePredictiveInspectorSignals,
  derivePredictiveMenuSuggestions,
  learnFromActionStream,
  predictNextRuntimeAction,
  type PredictiveActionDecision,
  type PredictiveActionState,
  type PredictiveInspectorSignal,
  type PredictiveMenuSuggestion,
} from './sovereignPredictiveActionRuntime';
import {
  evaluatePredictiveRuntimePolicy,
  type PredictiveRuntimeContext,
  type PredictiveRuntimePolicyResult,
} from './sovereignPredictiveRuntimePolicy';

export interface PredictiveSystemInput {
  readonly state?: PredictiveActionState;
  readonly capabilityDecision?: CapabilityDecision | null;
  readonly actionStream?: SovereignActionStreamState | null;
  readonly eventRoute?: SovereignActionRoute;
  readonly runtime?: PredictiveRuntimeContext;
}

export interface PredictiveSystemOutput {
  readonly state: PredictiveActionState;
  readonly prediction: PredictiveActionDecision | null;
  readonly policy: PredictiveRuntimePolicyResult;
  readonly actionEvent: SovereignActionEventInput | null;
  readonly menuSuggestions: readonly PredictiveMenuSuggestion[];
  readonly inspectorSignals: readonly PredictiveInspectorSignal[];
}

function buildPolicyBlockedEvent(policy: PredictiveRuntimePolicyResult): SovereignActionEventInput {
  return {
    kind: 'blocked',
    route: 'runtime',
    label: 'Predictive Runtime Policy blockiert',
    detail: policy.violations.map((violation) => `${violation.code}: ${violation.message}`).join('\n'),
    state: 'blocked',
  };
}

/**
 * Central predictive runtime tick.
 *
 * This is the nervous-system bridge: Router decisions and Action Stream evidence
 * enter here; menus, inspector, action stream and future UI surfaces read the
 * resulting state instead of inventing their own truth.
 */
export function runPredictiveSystemTick(input: PredictiveSystemInput): PredictiveSystemOutput {
  const baseState = input.state ?? createPredictiveActionState();
  const learnedState = input.actionStream
    ? learnFromActionStream(baseState, input.actionStream)
    : baseState;

  const prediction = input.capabilityDecision
    ? predictNextRuntimeAction(input.capabilityDecision, learnedState)
    : null;

  const rawActionEvent = prediction
    ? derivePredictiveActionEvent(prediction, input.eventRoute ?? 'runtime')
    : null;
  const rawMenuSuggestions = prediction ? derivePredictiveMenuSuggestions(prediction) : [];
  const rawInspectorSignals = derivePredictiveInspectorSignals(learnedState, prediction);

  const policy = evaluatePredictiveRuntimePolicy({
    mode: 'suggestion',
    capabilityDecision: input.capabilityDecision ?? null,
    prediction,
    actionEvent: rawActionEvent,
    menuSuggestions: rawMenuSuggestions,
    inspectorSignals: rawInspectorSignals,
    runtime: input.runtime,
  });

  if (!policy.allowed) {
    return {
      state: learnedState,
      prediction,
      policy,
      actionEvent: buildPolicyBlockedEvent(policy),
      menuSuggestions: [],
      inspectorSignals: rawInspectorSignals,
    };
  }

  return {
    state: learnedState,
    prediction,
    policy,
    actionEvent: rawActionEvent,
    menuSuggestions: rawMenuSuggestions,
    inspectorSignals: rawInspectorSignals,
  };
}

export function hasPredictiveSystemWork(output: PredictiveSystemOutput): boolean {
  return Boolean(
    output.policy.allowed &&
    output.prediction?.signal &&
    output.prediction.signal !== 'none' &&
    (output.actionEvent || output.menuSuggestions.length > 0 || output.inspectorSignals.length > 0),
  );
}
