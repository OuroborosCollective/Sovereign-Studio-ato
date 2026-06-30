import { useState, useCallback, useRef } from 'react';
import type { SovereignLlmRuntimeInput } from '../runtime/sovereignLlmRuntime';
import { runSovereignLlmRuntime } from '../runtime/sovereignLlmRuntime';
import type { SovereignBrainResult } from '../brain/sovereignBrainContract';

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
   * User approved - returns the mission to retry with consent enabled.
   */
  approveConsent: () => string | null;
  /**
   * User denied - clears the consent state.
   */
  denyConsent: () => void;
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
 *       const mission = approveConsent();
 *       if (mission) retryWithConsent(mission);
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
    const mission = pendingMissionRef.current;
    pendingMissionRef.current = null;
    setState({
      consentRequired: false,
      consentAttempts: 0,
      isRetrying: false,
      pendingMission: null,
    });
    return mission;
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

  return {
    state,
    triggerConsentGate,
    approveConsent,
    denyConsent,
  };
}