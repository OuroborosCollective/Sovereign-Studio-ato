import type { JobPhase } from '../types/domain';

export interface JobState {
  currentPhase: JobPhase;
  jobId: string | null;
  objective: string | null;
  error: string | null;
}

export const INITIAL_FSM_STATE: JobState = {
  currentPhase: 'IDLE',
  jobId: null,
  objective: null,
  error: null,
};

export type FSMAction =
  | { type: 'START_TYPING' }
  | { type: 'CANCEL_TYPING' }
  | { type: 'SUBMIT_ORDER'; payload: { objective: string } }
  | { type: 'BACKEND_ACCEPTED'; payload: { jobId: string } }
  | { type: 'BACKEND_PHASE_UPDATE'; payload: { phase: JobPhase } }
  | { type: 'OWNER_INPUT_SUBMITTED' }
  | { type: 'EXECUTION_FAILED'; payload: { error: string } }
  | { type: 'RESET' };

export const jobStateReducer = (state: JobState, action: FSMAction): JobState => {
  switch (action.type) {
    case 'START_TYPING':
      return state.currentPhase === 'IDLE' ? { ...state, currentPhase: 'AWAKENING' } : state;
    case 'CANCEL_TYPING':
      return state.currentPhase === 'AWAKENING' ? { ...state, currentPhase: 'IDLE' } : state;
    case 'SUBMIT_ORDER':
      return { ...state, currentPhase: 'DISPATCHING', objective: action.payload.objective, error: null };
    case 'BACKEND_ACCEPTED':
      return { ...state, currentPhase: 'PROVISIONING', jobId: action.payload.jobId };
    case 'BACKEND_PHASE_UPDATE':
      return { ...state, currentPhase: action.payload.phase };
    case 'OWNER_INPUT_SUBMITTED':
      return { ...state, currentPhase: 'EXECUTING' };
    case 'EXECUTION_FAILED':
      return { ...state, currentPhase: 'FAILED', error: action.payload.error };
    case 'RESET':
      return INITIAL_FSM_STATE;
    default:
      return state;
  }
};

type FSMEvent =
  | { type: 'START_TYPING' }
  | { type: 'CANCEL_TYPING' }
  | { type: 'SUBMIT_ORDER' }
  | { type: 'DISPATCH_SUCCESS' }
  | { type: 'PROVISION_READY' }
  | { type: 'REQUIRE_INPUT' }
  | { type: 'INPUT_PROVIDED' }
  | { type: 'EXECUTION_FINISH' }
  | { type: 'READY_TO_PUBLISH' }
  | { type: 'VERIFIED_PR' }
  | { type: 'BLOCK' }
  | { type: 'FAIL' }
  | { type: 'CANCEL' };

export const transition = (currentState: JobPhase, event: FSMEvent): JobPhase => {
  switch (currentState) {
    case 'IDLE':
      if (event.type === 'START_TYPING') return 'AWAKENING';
      break;
    case 'AWAKENING':
      if (event.type === 'CANCEL_TYPING') return 'IDLE';
      if (event.type === 'SUBMIT_ORDER') return 'DISPATCHING';
      break;
    case 'DISPATCHING':
      if (event.type === 'DISPATCH_SUCCESS') return 'PROVISIONING';
      if (event.type === 'FAIL') return 'FAILED';
      break;
    case 'PROVISIONING':
      if (event.type === 'PROVISION_READY') return 'EXECUTING';
      if (event.type === 'FAIL') return 'FAILED';
      break;
    case 'EXECUTING':
      if (event.type === 'REQUIRE_INPUT') return 'AWAITING_OWNER_INPUT';
      if (event.type === 'EXECUTION_FINISH') return 'FINALIZING';
      if (event.type === 'BLOCK') return 'BLOCKED';
      if (event.type === 'FAIL') return 'FAILED';
      if (event.type === 'CANCEL') return 'CANCELLED';
      break;
    case 'AWAITING_OWNER_INPUT':
      if (event.type === 'INPUT_PROVIDED') return 'EXECUTING';
      if (event.type === 'CANCEL') return 'CANCELLED';
      break;
    case 'FINALIZING':
      if (event.type === 'READY_TO_PUBLISH') return 'READY_TO_PUBLISH';
      if (event.type === 'VERIFIED_PR') return 'COMPLETED';
      if (event.type === 'BLOCK') return 'BLOCKED';
      if (event.type === 'FAIL') return 'FAILED';
      break;
    case 'READY_TO_PUBLISH':
      if (event.type === 'VERIFIED_PR') return 'COMPLETED';
      if (event.type === 'BLOCK') return 'BLOCKED';
      break;
    case 'BLOCKED':
      if (event.type === 'INPUT_PROVIDED') return 'EXECUTING';
      if (event.type === 'CANCEL') return 'CANCELLED';
      break;
    case 'COMPLETED':
    case 'FAILED':
    case 'CANCELLED':
      break;
  }
  return currentState;
};
