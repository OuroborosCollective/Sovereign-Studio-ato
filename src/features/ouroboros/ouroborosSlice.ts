import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface AREPayload {
  isActive?: boolean;
}

export interface OuroborosState {
  isAuthSequenceActive: boolean;
  activeAREPayload: AREPayload | null;
  errorState: string | null;
  isRootInitialized: boolean;
  telemetry: any;
  resonance: any;
}

const initialState: OuroborosState = {
  isAuthSequenceActive: false,
  activeAREPayload: null,
  errorState: null,
  isRootInitialized: false,
  telemetry: null,
  resonance: null,
};

export const ouroborosSlice = createSlice({
  name: 'ouroboros',
  initialState,
  reducers: {
    startAuthSequence: (state) => {
      state.isAuthSequenceActive = true;
    },
    stopAuthSequence: (state) => {
      state.isAuthSequenceActive = false;
    },
    setAREPayload: (state, action: PayloadAction<AREPayload | null>) => {
      state.activeAREPayload = action.payload;
    },
    initializeRoot: (state, action: PayloadAction<any>) => {
      state.isRootInitialized = true;
    },
    triggerError: (state, action: PayloadAction<string>) => {
      state.errorState = action.payload;
    },
    clearError: (state) => {
      state.errorState = null;
    },
  },
});

export const {
  startAuthSequence,
  stopAuthSequence,
  setAREPayload,
  initializeRoot,
  triggerError,
  clearError
} = ouroborosSlice.actions;

export default ouroborosSlice.reducer;
