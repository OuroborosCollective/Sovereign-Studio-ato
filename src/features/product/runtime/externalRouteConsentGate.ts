/**
 * External Route Consent Gate Runtime
 *
 * Handles the flow when external no-key routes are blocked and all other
 * routes have failed. Provides a consent-required state that the UI can
 * use to prompt the user for permission to enable external routes.
 */

import type { RepoFile } from '../../github/types';
import type { Card, ProjectSettings } from '../types';
import type { PalAutomationMode } from './palRouter';
import type { SovereignBrainResult } from '../brain/sovereignBrainContract';
import { buildSovereignPackageFromRepoFilesWithLlm } from './sovereignPackageFromRepoFiles';
import { defaultSettings, starterCards } from '../constants';

export interface ExternalRouteConsentGateInput {
  mission: string;
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
  | { ok: false; consentRequired: true; attempts: number }
  | { ok: false; consentRequired: false; error: string };

const CONSENT_REQUIRED_ERROR_CODE = 'CONSENT_REQUIRED';

function isConsentRequiredError(error: unknown): error is Error & { code: string; attempts: number } {
  return error instanceof Error && 'code' in error && (error as { code: string }).code === CONSENT_REQUIRED_ERROR_CODE;
}

/**
 * Attempts to build a sovereign package with LLM, handling the consent gate flow.
 * 
 * Returns:
 * - { ok: true, package } on success
 * - { ok: false, consentRequired: true, attempts } when external routes are blocked
 * - { ok: false, consentRequired: false, error } on other failures
 */
export async function buildSovereignPackageWithConsentGate(
  input: ExternalRouteConsentGateInput
): Promise<ExternalRouteConsentGateResult> {
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
      allowExternalNoKey: input.allowExternalNoKey ?? false,
      userKeys: input.userKeys,
    });

    return { ok: true, package: pkg };
  } catch (error) {
    if (isConsentRequiredError(error)) {
      return {
        ok: false,
        consentRequired: true,
        attempts: error.attempts ?? 0,
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
 * Retry the package build with external routes enabled (after user consent).
 */
export async function buildSovereignPackageWithConsentGranted(
  input: ExternalRouteConsentGateInput
): Promise<ExternalRouteConsentGateResult> {
  return buildSovereignPackageWithConsentGate({
    ...input,
    allowExternalNoKey: true, // Grant consent
  });
}