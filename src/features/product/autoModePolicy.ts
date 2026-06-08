import type { FlowState } from './userFlow';
import { canPush, nextStep } from './userFlow';

export type AutoDecision = 'wait-for-user' | 'run-fix' | 'prepare-write';

export function decideAutoMode(state: FlowState): AutoDecision {
  if (nextStep(state) === 'fix') return 'run-fix';
  if (state.auto && canPush(state)) return 'prepare-write';
  return 'wait-for-user';
}
