/**
 * External Route Consent Store
 * 
 * Zustand store for managing consent gate state globally.
 * This store is the single source of truth for consent UI state.
 */

import { create } from 'zustand';
import { grantConsentForMission, denyConsentForMission } from '../runtime/externalRouteConsentGate';

export interface ConsentMission {
  missionId: string;
  mission: string;
  attempts: number;
  timestamp: number;
}

interface ExternalRouteConsentState {
  // Is consent gate currently shown?
  isConsentRequired: boolean;
  // Current pending mission requiring consent
  currentMission: ConsentMission | null;
  // Error that triggered the consent (for debugging)
  lastError: string | null;
}

interface ExternalRouteConsentActions {
  // Trigger consent gate - called when CONSENT_REQUIRED is detected
  requestConsent: (missionId: string, mission: string, attempts: number) => void;
  // User approved - grant consent and clear state
  approveConsent: () => string | null;
  // User denied - clear consent and state
  denyConsent: () => void;
  // Reset all state
  reset: () => void;
  // Clear after successful operation
  clearMission: () => void;
}

export type ExternalRouteConsentStore = ExternalRouteConsentState & ExternalRouteConsentActions;

const initialState: ExternalRouteConsentState = {
  isConsentRequired: false,
  currentMission: null,
  lastError: null,
};

export const useExternalRouteConsentStore = create<ExternalRouteConsentStore>((set, get) => ({
  ...initialState,

  requestConsent: (missionId: string, mission: string, attempts: number) => {
    set({
      isConsentRequired: true,
      currentMission: {
        missionId,
        mission,
        attempts,
        timestamp: Date.now(),
      },
      lastError: 'CONSENT_REQUIRED_EXTERNAL_ROUTES',
    });
  },

  approveConsent: () => {
    const { currentMission } = get();
    
    if (currentMission) {
      // Grant consent in the runtime registry
      grantConsentForMission(currentMission.missionId);
    }
    
    const missionId = currentMission?.missionId ?? null;
    
    set({
      isConsentRequired: false,
      currentMission: null,
    });
    
    return missionId;
  },

  denyConsent: () => {
    const { currentMission } = get();
    
    if (currentMission) {
      // Deny consent in the runtime registry
      denyConsentForMission(currentMission.missionId);
    }
    
    set({
      isConsentRequired: false,
      currentMission: null,
    });
  },

  reset: () => {
    set(initialState);
  },

  clearMission: () => {
    set({
      currentMission: null,
      isConsentRequired: false,
    });
  },
}));

// Selector hooks for optimized re-renders
export const useConsentRequired = () => useExternalRouteConsentStore((s) => s.isConsentRequired);
export const useCurrentConsentMission = () => useExternalRouteConsentStore((s) => s.currentMission);
