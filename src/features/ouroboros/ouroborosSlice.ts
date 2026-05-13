import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface OuroborosState {
  telemetry: {
    sysLoad: number;
    resSync: number;
    latency: number;
    uplinkStatus: 'ACTIVE' | 'OFFLINE' | 'SYNCING';
  };
  resonance: number;
  isRootInitialized: boolean;
  kappaPosHash: string;
  errorState: boolean;
}

const initialState: OuroborosState = {
  telemetry: {
    sysLoad: 14,
    resSync: 10.00,
    latency: 12,
    uplinkStatus: 'ACTIVE',
  },
  resonance: 0.842,
  isRootInitialized: false,
  kappaPosHash: '',
  errorState: false,
};

const ouroborosSlice = createSlice({
  name: 'ouroboros',
  initialState,
  reducers: {
    setTelemetry: (state, action: PayloadAction<Partial<OuroborosState['telemetry']>>) => {
      state.telemetry = { ...state.telemetry, ...action.payload };
    },
    setResonance: (state, action: PayloadAction<number>) => {
      state.resonance = action.payload;
    },
    initializeRoot: (state, action: PayloadAction<string>) => {
      state.kappaPosHash = action.payload;
      state.isRootInitialized = true;
      state.errorState = false;
    },
    triggerError: (state) => {
      state.errorState = true;
    },
    clearError: (state) => {
      state.errorState = false;
    },
  },
});

export const { setTelemetry, setResonance, initializeRoot, triggerError, clearError } = ouroborosSlice.actions;
export default ouroborosSlice.reducer;
