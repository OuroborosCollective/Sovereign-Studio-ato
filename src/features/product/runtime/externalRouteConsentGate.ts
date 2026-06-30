/**
 * External Route Consent Gate Runtime
 *
 * Handles the flow when external no-key routes are blocked and all other
 * routes have failed. Provides a consent-required state that the UI can
 * use to prompt the user for permission to enable external routes.
 * 
 * Architecture:
 * - Consent is bound to a mission ID / trace ID
 * - One-time consent per mission attempt
 * - Runtime throws CONSENT_REQUIRED error when external routes are blocked
 * - UI catches this and shows the consent gate
 * - User approves → next call with same mission and consent=true retries
 * 
 * Usage:
 * 1. Call runWithConsent(input, callbacks)
 * 2. If consentRequired callback fires → show UI
 * 3. User clicks JA → call grantConsentForMission(missionId)
 * 4. Call runWithConsent again with same missionId → allowExternalNoKey: true
 */

import type { RepoFile } from '../../github/types';
import type { Card, ProjectSettings } from '../types';
import type { PalAutomationMode } from './palRouter';
import { buildSovereignPackageFromRepoFilesWithLlm } from './sovereignPackageFromRepoFiles';
import { defaultSettings, starterCards } from '../constants';

// Consent registry: missionId -> boolean
const consentRegistry = new Map<string, boolean>();

/**
 * Generate a consent token for a mission.
 * This binds the consent to a specific mission attempt.
 */
export function generateMissionConsentToken(mission: string): string {
  return `consent:${Date.now()}:${mission.slice(0, 32)}`;
}

/**
 * Grant consent for a specific mission.
 * Call this when user approves the consent gate.
 */
export function grantConsentForMission(missionId: string): void {
  consentRegistry.set(missionId, true);
}

/**
 * Deny consent for a specific mission.
 * Call this when user denies the consent gate.
 */
export function denyConsentForMission(missionId: string): void {
  consentRegistry.delete(missionId);
}

/**
 * Check if consent is granted for a mission.
 */
export function isConsentGrantedForMission(missionId: string): boolean {
  return consentRegistry.get(missionId) === true;
}

/**
 * Clear all pending consents.
 */
export function clearAllConsents(): void {
  consentRegistry.clear();
}

export interface ExternalRouteConsentGateInput {
  mission: string;
  missionId?: string; // Optional binding for consent
  repoFiles: RepoFile[];
  selectedFilePath?: string;
  cards?: Card[];
  settings?: ProjectSettings;
  previousPreview?: string;
  memoryContext?: string[];
  runtimeEvents?: string[];
  palBlockers?: string[];
  automationMode?: PalAutomationMode;
  allowUserKeyRoutes?: boolean;
  allowExternalNoKey?: boolean;
  userKeys?: {
    gemini?: string;
    groq?: string;
    huggingface?: string;
    together?: string;
    openrouter?: string;
    pollinations?: string;
  };
}

export type ExternalRouteConsentGateResult =
  | { ok: true; package: import('./sovereignRuntime').SovereignImplementationPackage }
  | { ok: false; consentRequired: true; missionId: string; attempts: number }
  | { ok: false; consentRequired: false; error: string };

const CONSENT_REQUIRED_ERROR_CODE = 'CONSENT_REQUIRED';

function isConsentRequiredError(error: unknown): error is Error & { code: string; attempts: number; missionId?: string } {
  return error instanceof Error && 'code' in error && (error as { code: string }).code === CONSENT_REQUIRED_ERROR_CODE;
}

/**
 * Run the sovereign package build with consent awareness.
 * 
 * Flow:
 * 1. First call with allowExternalNoKey: false (default)
 * 2. If CONSENT_REQUIRED error → call onConsentRequired(missionId, attempts)
 * 3. User approves → grantConsentForMission(missionId)
 * 4. Call again with same mission → will use allowExternalNoKey: true
 * 5. Consent is cleared after one successful use
 */
export async function buildSovereignPackageWithConsentGate(
  input: ExternalRouteConsentGateInput,
  callbacks: {
    onConsentRequired?: (missionId: string, attempts: number) => void;
  } = {}
): Promise<ExternalRouteConsentGateResult> {
  // Generate mission ID if not provided
  const missionId = input.missionId ?? generateMissionConsentToken(input.mission);
  
  // Check if consent is granted for this mission
  const hasConsent = isConsentGrantedForMission(missionId);
  
  try {
    const pkg = await buildSovereignPackageFromRepoFilesWithLlm({
      mission: input.mission,
      repoFiles: input.repoFiles,
      selectedFilePath: input.selectedFilePath,
      cards: input.cards ?? starterCards(),
      settings: input.settings ?? defaultSettings,
      previousPreview: input.previousPreview,
      memoryContext: input.memoryContext ?? [],
      runtimeEvents: input.runtimeEvents ?? [],
      palBlockers: input.palBlockers,
      automationMode: input.automationMode,
      allowUserKeyRoutes: input.allowUserKeyRoutes ?? false,
      // Use granted consent OR input value (defaults to false)
      allowExternalNoKey: hasConsent ? true : (input.allowExternalNoKey ?? false),
      userKeys: input.userKeys,
    });

    // Clear consent after successful use (one-time consent per mission)
    consentRegistry.delete(missionId);

    return { ok: true, package: pkg };
  } catch (error) {
    if (isConsentRequiredError(error)) {
      const attempts = error.attempts ?? 0;
      
      // Notify via callback
      callbacks.onConsentRequired?.(missionId, attempts);
      
      return {
        ok: false,
        consentRequired: true,
        missionId,
        attempts,
      };
    }

    const message = error instanceof Error ? error.message : 'Unknown error';
    return {
      ok: false,
      consentRequired: false,
      error: message,
    };
  }
}

/**
 * Retry a mission with consent granted.
 * Call this after user approves the consent gate.
 */
export async function buildSovereignPackageWithConsentGranted(
  input: ExternalRouteConsentGateInput
): Promise<ExternalRouteConsentGateResult> {
  const missionId = input.missionId ?? generateMissionConsentToken(input.mission);
  
  // Grant consent for this mission
  grantConsentForMission(missionId);
  
  // Retry with consent
  return buildSovereignPackageWithConsentGate({
    ...input,
    missionId,
    allowExternalNoKey: true,
  });
}