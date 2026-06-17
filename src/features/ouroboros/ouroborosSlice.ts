import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export type TelemetrySource = 'user' | 'system' | 'pattern';

export type TelemetryEventType =
  | 'auth_start'
  | 'auth_stop'
  | 'root_init'
  | 'pattern_match'
  | 'error_trigger'
  | 'consent_grant'
  | 'consent_revoke';

export interface OuroborosTelemetry {
  readonly eventType: TelemetryEventType;
  readonly timestamp: number;
  readonly sequenceId: string;
  readonly source: TelemetrySource;
  readonly metadata?: Readonly<Record<string, string | number | boolean>>;
}

export interface OuroborosResonance {
  readonly patternId: string;
  readonly strength: number;
  readonly lastReinforced: number;
  readonly consentGranted: boolean;
  readonly reinforcementCount: number;
}

export type ConsentLevel = 'none' | 'session' | 'persistent';

export interface ConsentAwarePatternRef {
  readonly patternId: string;
  readonly consentLevel: ConsentLevel;
  readonly grantedAt: number | null;
  readonly revokedAt: number | null;
}

export interface OuroborosGuardReport {
  readonly isValid: boolean;
  readonly violations: readonly string[];
  readonly checkedAt: number;
  readonly stateHash: string;
}

export interface AREPayload {
  readonly isActive?: boolean;
}

export interface RootInitPayload {
  readonly sessionId: string;
  readonly source: 'boot' | 'remote' | 'restore';
  readonly initialTelemetry?: OuroborosTelemetry;
}

export interface ResonanceUpdatePayload {
  readonly patternId: string;
  readonly strength: number;
  readonly lastReinforced: number;
  readonly consentGranted: boolean;
  readonly reinforcementCount: number;
}

export interface ConsentGrantPayload {
  readonly patternId: string;
  readonly consentLevel: Exclude<ConsentLevel, 'none'>;
  readonly grantedAt: number;
}

export interface ConsentRevokePayload {
  readonly patternId: string;
  readonly revokedAt: number;
}

export interface OuroborosState {
  readonly isAuthSequenceActive: boolean;
  readonly activeAREPayload: AREPayload | null;
  readonly errorState: string | null;
  readonly isRootInitialized: boolean;
  readonly telemetry: OuroborosTelemetry | null;
  readonly resonance: OuroborosResonance | null;
  readonly guardReport: OuroborosGuardReport | null;
  readonly activePattern: ConsentAwarePatternRef | null;
}

const initialState: OuroborosState = {
  isAuthSequenceActive: false,
  activeAREPayload: null,
  errorState: null,
  isRootInitialized: false,
  telemetry: null,
  resonance: null,
  guardReport: null,
  activePattern: null,
};

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
}

function clampNonNegativeInteger(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.trunc(value));
}

export const ouroborosSlice = createSlice({
  name: 'ouroboros',
  initialState,
  reducers: {
    startAuthSequence: (state) => {
      state.isAuthSequenceActive = true;
      state.telemetry = null;
      state.guardReport = null;
    },

    stopAuthSequence: (state) => {
      state.isAuthSequenceActive = false;
      state.activeAREPayload = null;
      state.guardReport = null;
    },

    setAREPayload: (state, action: PayloadAction<AREPayload | null>) => {
      state.activeAREPayload = action.payload;
      state.guardReport = null;
    },

    initializeRoot: (state, action: PayloadAction<RootInitPayload>) => {
      state.isRootInitialized = true;
      state.guardReport = null;
      if (action.payload.initialTelemetry !== undefined) {
        state.telemetry = action.payload.initialTelemetry;
      }
    },

    triggerError: (state, action: PayloadAction<string>) => {
      state.errorState = action.payload;
      state.guardReport = null;
    },

    clearError: (state) => {
      state.errorState = null;
      state.guardReport = null;
    },

    recordTelemetry: (state, action: PayloadAction<OuroborosTelemetry>) => {
      state.telemetry = action.payload;
      state.guardReport = null;
    },

    updateResonance: (state, action: PayloadAction<ResonanceUpdatePayload>) => {
      state.resonance = {
        patternId: action.payload.patternId,
        strength: clamp01(action.payload.strength),
        lastReinforced: action.payload.lastReinforced,
        consentGranted: action.payload.consentGranted,
        reinforcementCount: clampNonNegativeInteger(action.payload.reinforcementCount),
      };
      state.guardReport = null;
    },

    setGuardReport: (state, action: PayloadAction<OuroborosGuardReport>) => {
      state.guardReport = action.payload;
    },

    grantPatternConsent: (state, action: PayloadAction<ConsentGrantPayload>) => {
      state.activePattern = {
        patternId: action.payload.patternId,
        consentLevel: action.payload.consentLevel,
        grantedAt: action.payload.grantedAt,
        revokedAt: null,
      };
      state.guardReport = null;
    },

    revokePatternConsent: (state, action: PayloadAction<ConsentRevokePayload>) => {
      if (state.activePattern !== null && state.activePattern.patternId === action.payload.patternId) {
        state.activePattern.revokedAt = action.payload.revokedAt;
        state.guardReport = null;
      }
    },

    clearActivePattern: (state) => {
      state.activePattern = null;
      state.guardReport = null;
    },
  },
});

export const {
  startAuthSequence,
  stopAuthSequence,
  setAREPayload,
  initializeRoot,
  triggerError,
  clearError,
  recordTelemetry,
  updateResonance,
  setGuardReport,
  grantPatternConsent,
  revokePatternConsent,
  clearActivePattern,
} = ouroborosSlice.actions;

export default ouroborosSlice.reducer;
