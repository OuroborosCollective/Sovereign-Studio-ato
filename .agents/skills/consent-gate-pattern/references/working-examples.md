# Working Examples from Sovereign Studio

This file contains concrete examples from the actual implementation of the consent gate in Sovereign Studio V3.

## File Locations

| File | Purpose |
|------|---------|
| `src/features/product/runtime/externalRouteConsentGate.ts` | Core runtime module |
| `src/features/product/runtime/externalRouteConsentGate.test.ts` | Unit tests |
| `src/features/product/hooks/useExternalRouteConsent.ts` | React hook |
| `src/features/product/components/ExternalRouteConsentGate.tsx` | UI component |
| `src/features/product/containers/BuilderContainer.tsx` | Container integration |

## externalRouteConsentGate.ts (Full Implementation)

```typescript
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
import { buildSovereignPackageFromRepoFilesWithLlm } from './sovereignPackageFromRepoFiles';
import { defaultSettings, starterCards } from '../constants';

// Consent registry: missionId -> boolean
const consentRegistry = new Map<string, boolean>();

export function generateMissionConsentToken(mission: string): string {
  return `consent:${Date.now()}:${mission.slice(0, 32)}`;
}

export function grantConsentForMission(missionId: string): void {
  consentRegistry.set(missionId, true);
}

export function denyConsentForMission(missionId: string): void {
  consentRegistry.delete(missionId);
}

export function isConsentGrantedForMission(missionId: string): boolean {
  return consentRegistry.get(missionId) === true;
}

export function clearAllConsents(): void {
  consentRegistry.clear();
}

export interface ExternalRouteConsentGateInput {
  mission: string;
  missionId?: string;
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
  | { ok: true; package: SovereignImplementationPackage }
  | { ok: false; consentRequired: true; missionId: string; attempts: number }
  | { ok: false; consentRequired: false; error: string };

const CONSENT_REQUIRED_ERROR_CODE = 'CONSENT_REQUIRED';

function isConsentRequiredError(error: unknown): error is Error & { code: string; attempts: number; missionId?: string } {
  return error instanceof Error && 'code' in error && (error as { code: string }).code === CONSENT_REQUIRED_ERROR_CODE;
}

export async function buildSovereignPackageWithConsentGate(
  input: ExternalRouteConsentGateInput,
  callbacks: {
    onConsentRequired?: (missionId: string, attempts: number) => void;
  } = {}
): Promise<ExternalRouteConsentGateResult> {
  const missionId = input.missionId ?? generateMissionConsentToken(input.mission);
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
      allowExternalNoKey: hasConsent ? true : (input.allowExternalNoKey ?? false),
      userKeys: input.userKeys,
    });

    // Clear consent after successful use (one-time consent per mission)
    consentRegistry.delete(missionId);

    return { ok: true, package: pkg };
  } catch (error) {
    if (isConsentRequiredError(error)) {
      const attempts = error.attempts ?? 0;
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

export async function buildSovereignPackageWithConsentGranted(
  input: ExternalRouteConsentGateInput
): Promise<ExternalRouteConsentGateResult> {
  const missionId = input.missionId ?? generateMissionConsentToken(input.mission);
  grantConsentForMission(missionId);
  
  return buildSovereignPackageWithConsentGate({
    ...input,
    missionId,
    allowExternalNoKey: true,
  });
}
```

## useExternalRouteConsent.ts (React Hook)

```typescript
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
  triggerConsentGate: (mission: string, missionId: string, attempts: number) => void;
  approveConsent: () => string | null;
  denyConsent: () => void;
  reset: () => void;
}

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
    const { missionId } = state;
    
    if (missionId) {
      grantConsentForMission(missionId);
    }
    
    setState({
      consentRequired: false,
      missionId: null,
      consentAttempts: 0,
      pendingMission: null,
    });
    
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
```

## Container Integration (BuilderContainer.tsx)

```typescript
// State declarations
const [externalRouteConsentRequired, setExternalRouteConsentRequired] = useState(false);
const [externalRouteConsentAttempts, setExternalRouteConsentAttempts] = useState(0);
const [pendingMissionForConsent, setPendingMissionForConsent] = useState<string | null>(null);
const [pendingMissionId, setPendingMissionId] = useState<string | null>(null);

// Consent Gate UI rendering
{externalRouteConsentRequired && (
  <ExternalRouteConsentGate
    attempts={externalRouteConsentAttempts}
    onApprove={() => {
      if (pendingMissionId) {
        import('../runtime/externalRouteConsentGate').then(module => {
          module.grantConsentForMission(pendingMissionId);
        });
        appendChatLine({
          role: 'assistant',
          text: 'Free-Routen für diese Anfrage aktiviert. Bitte Mission erneut senden.'
        });
      }
      setExternalRouteConsentRequired(false);
      setPendingMissionForConsent(null);
      setPendingMissionId(null);
    }}
    onDeny={() => {
      if (pendingMissionId) {
        import('../runtime/externalRouteConsentGate').then(module => {
          module.denyConsentForMission(pendingMissionId);
        });
      }
      setExternalRouteConsentRequired(false);
      setPendingMissionForConsent(null);
      setPendingMissionId(null);
      appendChatLine({
        role: 'assistant',
        text: 'Free-Routen abgelehnt. Arbeit wird lokal fortgesetzt.'
      });
    }}
  />
)}
```

## Test Example (externalRouteConsentGate.test.ts)

```typescript
describe('Consent Retry Flow', () => {
  it('full flow: CONSENT_REQUIRED → grant consent → retry with allowExternalNoKey: true', async () => {
    const missionId = 'test-full-flow-mission';
    
    // First call: fails with CONSENT_REQUIRED
    const consentError = new Error('CONSENT_REQUIRED_EXTERNAL_ROUTES: blocked');
    (consentError as { code: string }).code = 'CONSENT_REQUIRED';
    (consentError as { attempts: number }).attempts = 2;

    (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(consentError);

    const firstResult = await buildSovereignPackageWithConsentGate({
      ...baseInput,
      missionId,
    });

    expect(firstResult.ok).toBe(false);
    expect(firstResult.consentRequired).toBe(true);

    // User approves: grant consent
    grantConsentForMission(missionId);

    // Second call: succeeds with consent
    const mockPackage = { /* ... */ };

    (buildSovereignPackageFromRepoFilesWithLlm as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(mockPackage);

    const secondResult = await buildSovereignPackageWithConsentGate({
      ...baseInput,
      missionId,
    });

    expect(secondResult.ok).toBe(true);
    expect(buildSovereignPackageFromRepoFilesWithLlm).toHaveBeenLastCalledWith(
      expect.objectContaining({
        allowExternalNoKey: true,
        missionId,
      })
    );
  });
});
```

## Key Takeaways

1. **Mission Binding**: Consent is tied to a unique missionId, not just a global flag
2. **One-Time Use**: Consent is cleared after successful execution
3. **Explicit Flow**: User must manually retry after granting consent
4. **No DOM Manipulation**: Consent is granted through runtime functions, not UI clicks
5. **Tested Flow**: Full flow from consent required → grant → retry is tested
