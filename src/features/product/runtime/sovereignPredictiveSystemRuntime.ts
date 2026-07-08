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

export interface PredictiveSystemInput {
  readonly state?: PredictiveActionState;
  readonly capabilityDecision?: CapabilityDecision | null;
  readonly actionStream?: SovereignActionStreamState | null;
  readonly eventRoute?: SovereignActionRoute;
}

export interface PredictiveSystemOutput {
  readonly state: PredictiveActionState;
  readonly prediction: PredictiveActionDecision | null;
  readonly actionEvent: SovereignActionEventInput | null;
  readonly menuSuggestions: readonly PredictiveMenuSuggestion[];
  readonly inspectorSignals: readonly PredictiveInspectorSignal[];
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

  const actionEvent = prediction
    ? derivePredictiveActionEvent(prediction, input.eventRoute ?? 'runtime')
    : null;

  return {
    state: learnedState,
    prediction,
    actionEvent,
    menuSuggestions: prediction ? derivePredictiveMenuSuggestions(prediction) : [],
    inspectorSignals: derivePredictiveInspectorSignals(learnedState, prediction),
  };
}

export function hasPredictiveSystemWork(output: PredictiveSystemOutput): boolean {
  return Boolean(
    output.prediction?.signal &&
    output.prediction.signal !== 'none' &&
    (output.actionEvent || output.menuSuggestions.length > 0 || output.inspectorSignals.length > 0),
  );
}
