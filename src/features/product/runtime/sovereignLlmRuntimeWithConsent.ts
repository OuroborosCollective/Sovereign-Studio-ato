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

export interface LlmRuntimeWithConsentOptions {
  /** Initial input - allowExternalNoKey defaults to false */
  initialInput: SovereignLlmRuntimeInput;
  /** Called when consent is required */
  onConsentRequired?: (attempts: number) => void;
  /** Called when consent is granted and we're retrying */
  onConsentGranted?: () => void;
}

const CONSENT_REQUIRED_ERROR_CODE = 'CONSENT_REQUIRED';

function isConsentRequiredError(error: unknown): error is Error & { code: string; attempts: number } {
  return error instanceof Error && 'code' in error && (error as { code: string }).code === CONSENT_REQUIRED_ERROR_CODE;
}

/**
 * Run LLM runtime with consent gate awareness.
 * 
 * Flow:
 * 1. Run with allowExternalNoKey: false (or undefined, defaults to false)
 * 2. If success, return result
 * 3. If CONSENT_REQUIRED error and retryWithConsent is true, retry with allowExternalNoKey: true
 * 4. Return final result
 */
export async function runSovereignLlmRuntimeWithConsent(
  input: SovereignLlmRuntimeInput,
  options: {
    onConsentRequired?: (attempts: number) => void;
    onConsentGranted?: () => void;
  } = {}
): Promise<LlmRuntimeWithConsentResult> {
  const { onConsentRequired, onConsentGranted } = options;

  // First attempt - no consent
  const firstResult = await runSovereignLlmRuntime({
    ...input,
    allowExternalNoKey: input.allowExternalNoKey ?? false,
  });

  if (firstResult.ok) {
    return firstResult;
  }

  // Check if consent is required
  if (firstResult.consentRequired) {
    onConsentRequired?.(firstResult.attempts?.length ?? 0);
    return firstResult;
  }

  // Regular error - return as-is
  return firstResult;
}

/**
 * Retry with consent after user has granted permission.
 * This should only be called after user explicitly approves the consent gate.
 */
export async function runSovereignLlmRuntimeWithConsentGranted(
  input: SovereignLlmRuntimeInput
): Promise<LlmRuntimeWithConsentResult> {
  // Retry with external routes explicitly enabled
  const result = await runSovereignLlmRuntime({
    ...input,
    allowExternalNoKey: true, // Grant consent
  });

  return {
    ...result,
    afterConsentGrant: true,
  };
}