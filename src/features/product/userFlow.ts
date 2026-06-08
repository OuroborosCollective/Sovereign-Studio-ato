export type FlowStep = 'idea' | 'plan' | 'work' | 'check' | 'fix' | 'ready';

export interface FlowState {
  step: FlowStep;
  auto: boolean;
  hasError: boolean;
  green: boolean;
}

export function nextStep(state: FlowState): FlowStep {
  if (state.hasError) return 'fix';
  if (state.green) return 'ready';
  if (state.step === 'idea') return 'plan';
  if (state.step === 'plan') return 'work';
  if (state.step === 'work') return 'check';
  return state.step;
}

export function canPush(state: FlowState): boolean {
  return nextStep(state) === 'ready';
}
