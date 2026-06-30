import { useState, useCallback, useRef } from 'react';

export interface ExternalRouteConsentState {
  consentRequired: boolean;
  consentAttempts: number;
  isRetrying: boolean;
  pendingMission: string | null;
}

export interface UseExternalRouteConsentResult {
  state: ExternalRouteConsentState;
  /**
   * Trigger consent gate for a mission.
   * Call this when a LLM call fails and you want to show the consent UI.
   */
  triggerConsentGate: (mission: string, attempts: number) => void;
  /**
   * User approved - clears consent state and returns true for retry.
   */
  approveConsent: () => boolean;
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
 *   triggerConsentGate(mission, error.attempts);
 * }
 * 
 * // In render:
 * {state.consentRequired && (
 *   <ExternalRouteConsentGate
 *     attempts={state.consentAttempts}
 *     onApprove={() => {
 *       if (approveConsent()) {
 *         // Set state to retry with allowExternalNoKey: true
 *         setRetryWithConsent(true);
 *       }
 *     }}
 *     onDeny={denyConsent}
 *   />
 * )}
 * ```
 */
export function useExternalRouteConsent(): UseExternalRouteConsentResult {
  const [state, setState] = useState<ExternalRouteConsentState>({
    consentRequired: false,
    consentAttempts: 0,
    isRetrying: false,
    pendingMission: null,
  });

  const pendingMissionRef = useRef<string | null>(null);

  const triggerConsentGate = useCallback((mission: string, attempts: number) => {
    pendingMissionRef.current = mission;
    setState({
      consentRequired: true,
      consentAttempts: attempts,
      isRetrying: false,
      pendingMission: mission,
    });
  }, []);

  const approveConsent = useCallback(() => {
    const hadConsent = state.consentRequired;
    pendingMissionRef.current = null;
    setState({
      consentRequired: false,
      consentAttempts: 0,
      isRetrying: false,
      pendingMission: null,
    });
    return hadConsent;
  }, []);

  const denyConsent = useCallback(() => {
    pendingMissionRef.current = null;
    setState({
      consentRequired: false,
      consentAttempts: 0,
      isRetrying: false,
      pendingMission: null,
    });
  }, []);

  const reset = useCallback(() => {
    pendingMissionRef.current = null;
    setState({
      consentRequired: false,
      consentAttempts: 0,
      isRetrying: false,
      pendingMission: null,
    });
  }, []);

  return {
    state,
    triggerConsentGate,
    approveConsent,
    denyConsent,
    reset,
  };
}