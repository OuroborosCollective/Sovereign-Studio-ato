import { describe, it, expect } from 'vitest';
import reducer, {
  startAuthSequence,
  stopAuthSequence,
  setAREPayload,
  initializeRoot,
  triggerError,
  clearError,
  OuroborosState,
  AREPayload
} from './ouroborosSlice';

describe('ouroborosSlice reducers', () => {
  const initialState: OuroborosState = {
    isAuthSequenceActive: false,
    activeAREPayload: null,
    errorState: null,
    isRootInitialized: false,
    telemetry: null,
    resonance: null,
  };

  it('should handle startAuthSequence', () => {
    const nextState = reducer(initialState, startAuthSequence());
    expect(nextState.isAuthSequenceActive).toBe(true);
  });

  it('should handle stopAuthSequence', () => {
    const stateWithAuth = { ...initialState, isAuthSequenceActive: true };
    const nextState = reducer(stateWithAuth, stopAuthSequence());
    expect(nextState.isAuthSequenceActive).toBe(false);
  });

  it('should handle setAREPayload', () => {
    const payload: AREPayload = { isActive: true };
    const nextState = reducer(initialState, setAREPayload(payload));
    expect(nextState.activeAREPayload).toEqual(payload);
  });

  it('should handle setAREPayload with null', () => {
    const stateWithPayload = { ...initialState, activeAREPayload: { isActive: true } };
    const nextState = reducer(stateWithPayload, setAREPayload(null));
    expect(nextState.activeAREPayload).toBeNull();
  });

  it('should handle initializeRoot', () => {
    const nextState = reducer(initialState, initializeRoot({}));
    expect(nextState.isRootInitialized).toBe(true);
  });

  it('should handle triggerError', () => {
    const errorMessage = 'An error occurred';
    const nextState = reducer(initialState, triggerError(errorMessage));
    expect(nextState.errorState).toBe(errorMessage);
  });

  it('should handle clearError', () => {
    const stateWithError = { ...initialState, errorState: 'Some error' };
    const nextState = reducer(stateWithError, clearError());
    expect(nextState.errorState).toBeNull();
  });
});
