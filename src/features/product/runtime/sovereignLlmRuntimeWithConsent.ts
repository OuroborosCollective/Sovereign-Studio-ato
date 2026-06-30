/**
 * Sovereign LLM Runtime with Consent Gate
 *
 * Wraps runSovereignLlmRuntime with consent gate awareness.
 * When external no-key routes are blocked and consent is granted,
 * retries with allowExternalNoKey: true.
 */

import type { SovereignLlmRuntimeInput, SovereignLlmRuntimeResult } from './sovereignLlmRuntime';
import { runSovereignLlmRuntime } from './sovereignLlmRuntime';

export interface LlmRuntimeWithConsentResult extends SovereignLlmRuntimeResult {
  /** True if this result was obtained after user consent */
  afterConsentGrant?: boolean;
}

/**
 * Run LLM runtime with consent gate awareness.
 * 
 * Flow:
 * 1. Run with allowExternalNoKey: false (or undefined, defaults to false)
 * 2. If success, return result
 * 3. If consentRequired flag is set, the UI should show the consent gate
 * 4. After user approves, call runSovereignLlmRuntimeWithConsentGranted to retry
 * 
 * Note: This function now uses auto-detection via detectConsentForCurrentMission
 * in runSovereignLlmRuntime. The consent is automatically granted if the user
 * approved the same mission text previously.
 */
export async function runSovereignLlmRuntimeWithConsent(
  input: SovereignLlmRuntimeInput,
  options: {
    onConsentRequired?: (missionId: string, attempts: number) => void;
  } = {}
): Promise<LlmRuntimeWithConsentResult> {
  // runSovereignLlmRuntime now handles auto-detection of consent
  // If the user previously approved this mission, it will automatically use
  // allowExternalNoKey: true
  
  const result = await runSovereignLlmRuntime({
    ...input,
    // Don't override allowExternalNoKey - let the runtime auto-detect
    // allowExternalNoKey: undefined,
  });

  // If consent is required, notify the caller
  if (!result.ok && result.consentRequired && result.missionId) {
    options.onConsentRequired?.(result.missionId, result.attempts?.length ?? 0);
  }

  return result;
}

/**
 * Retry with consent after user has granted permission.
 * This should only be called after user explicitly approves the consent gate.
 * The grantConsentForMission must be called first to enable external routes.
 */
export async function runSovereignLlmRuntimeWithConsentGranted(
  input: SovereignLlmRuntimeInput
): Promise<LlmRuntimeWithConsentResult> {
  // Retry with external routes explicitly enabled
  const result = await runSovereignLlmRuntime({
    ...input,
    allowExternalNoKey: true, // Grant consent explicitly
  });

  return {
    ...result,
    afterConsentGrant: true,
  };
}