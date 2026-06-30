import { useState, useCallback } from 'react';
import { grantConsentForMission, denyConsentForMission } from '../runtime/externalRouteConsentGate';

export interface ExternalRouteConsentState {
  consentRequired: boolean;
  missionId: string | null;
  consentAttempts: number;
  pendingMission: string | null;
}

export interface UseExternalRouteConsentResult {
  state: ExternalRouteConsentState;
  /**
   * Trigger consent gate for a mission.
   * Call this when a LLM call fails and you want to show the consent UI.
   */
  triggerConsentGate: (mission: string, missionId: string, attempts: number) => void;
  /**
   * User approved - grants consent for mission and clears UI state.
   * Returns the missionId so caller can retry.
   */
  approveConsent: () => string | null;
  /**
   * User denied - clears the consent state.
   */
  denyConsent: () => void;
  /**
   * Reset all consent state.
   */
  reset: () => void;
}

/**
 * Hook that handles the external route consent gate workflow.
 * 
 * Usage in component:
 * 
 * ```tsx
 * const { state, triggerConsentGate, approveConsent, denyConsent } = useExternalRouteConsent();
 * 
 * // When LLM fails with consent required:
 * if (error.code === 'CONSENT_REQUIRED') {
 *   triggerConsentGate(mission, error.missionId, error.attempts);
 * }
 * 
 * // In render:
 * {state.consentRequired && (
 *   <ExternalRouteConsentGate
 *     attempts={state.consentAttempts}
 *     onApprove={() => {
 *       const missionId = approveConsent();
 *       if (missionId) retryWithConsent(missionId);
 *     }}
 *     onDeny={denyConsent}
 *   />
 * )}
 * ```
 */
export function useExternalRouteConsent(): UseExternalRouteConsentResult {
  const [state, setState] = useState<ExternalRouteConsentState>({
    consentRequired: false,
    missionId: null,
    consentAttempts: 0,
    pendingMission: null,
  });

  const triggerConsentGate = useCallback((mission: string, missionId: string, attempts: number) => {
    setState({
      consentRequired: true,
      missionId,
      consentAttempts: attempts,
      pendingMission: mission,
    });
  }, []);

  const approveConsent = useCallback(() => {
    const { missionId, pendingMission } = state;
    
    if (missionId) {
      // Grant consent in the registry
      grantConsentForMission(missionId);
    }
    
    setState({
      consentRequired: false,
      missionId: null,
      consentAttempts: 0,
      pendingMission: null,
    });
    
    // Return missionId so caller can retry with the same ID
    return missionId;
  }, [state]);

  const denyConsent = useCallback(() => {
    const { missionId } = state;
    
    if (missionId) {
      denyConsentForMission(missionId);
    }
    
    setState({
      consentRequired: false,
      missionId: null,
      consentAttempts: 0,
      pendingMission: null,
    });
  }, [state]);

  const reset = useCallback(() => {
    const { missionId } = state;
    
    if (missionId) {
      denyConsentForMission(missionId);
    }
    
    setState({
      consentRequired: false,
      missionId: null,
      consentAttempts: 0,
      pendingMission: null,
    });
  }, [state]);

  return {
    state,
    triggerConsentGate,
    approveConsent,
    denyConsent,
    reset,
  };
}