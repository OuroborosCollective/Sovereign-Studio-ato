import { getDefaultPredictiveLayer } from '../../predictive/predictiveLayer';
import type { AreInferenceResult } from './areInferenceApi';

export type AreStateChangeKind =
  | 'initial'
  | 'prompt'
  | 'repository'
  | 'knowledge'
  | 'experience'
  | 'embedding_model'
  | 'capabilities'
  | 'connectivity';

export interface AreStateTransition {
  readonly previousStateHash: string | null;
  readonly currentStateHash: string;
  readonly changed: boolean;
  readonly changeKinds: readonly AreStateChangeKind[];
  readonly magnitude: number;
  readonly decision: AreInferenceResult['decision'];
  readonly adapter: string;
}

function sameStrings(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

export type ArePreviousState = Pick<AreInferenceResult, 'stateHash' | 'state'>;

export function compareAreState(
  previous: ArePreviousState | null,
  current: AreInferenceResult,
): AreStateTransition {
  const changes: AreStateChangeKind[] = [];
  if (!previous) {
    changes.push('initial');
  } else {
    if (previous.state.promptSha256 !== current.state.promptSha256) changes.push('prompt');
    if (JSON.stringify(previous.state.repository) !== JSON.stringify(current.state.repository)) changes.push('repository');
    if (previous.state.knowledgeRevision !== current.state.knowledgeRevision) changes.push('knowledge');
    if (previous.state.experienceRevision !== current.state.experienceRevision) changes.push('experience');
    if (previous.state.embeddingModelHash !== current.state.embeddingModelHash) changes.push('embedding_model');
    if (!sameStrings(previous.state.activeCapabilities, current.state.activeCapabilities)) changes.push('capabilities');
    if (previous.state.onlineAvailable !== current.state.onlineAvailable) changes.push('connectivity');
  }

  return {
    previousStateHash: previous?.stateHash ?? null,
    currentStateHash: current.stateHash,
    changed: changes.length > 0,
    changeKinds: changes,
    magnitude: Math.min(1, changes.length / 7),
    decision: current.decision,
    adapter: current.adapter,
  };
}

export function emitAreStateTransition(
  previous: ArePreviousState | null,
  current: AreInferenceResult,
): AreStateTransition {
  const transition = compareAreState(previous, current);
  if (!transition.changed) return transition;

  try {
    const layer = getDefaultPredictiveLayer();
    if (layer.isEnabled()) {
      layer.emitSignal('are.inference.state', transition.magnitude, {
        stateHash: transition.currentStateHash,
        changeKinds: transition.changeKinds,
        decision: transition.decision,
        adapter: transition.adapter,
        deterministic: true,
        authority: 'advisory-only',
      });
    }
  } catch {
    // Predictive observation is optional and must never block the truth path.
  }

  return transition;
}
