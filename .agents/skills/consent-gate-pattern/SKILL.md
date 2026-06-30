---
name: sovereign-consent-gate
description: This skill should be used when implementing consent gates, user approval flows, security opt-ins, or runtime permission patterns in Sovereign Studio V3. Triggers include phrases like "add consent gate", "implement approval flow", "user must approve", "opt-in routes", "external routes consent", "security approval UI", "block until user confirms".
---

# Sovereign Consent Gate Pattern

## Purpose

Implement secure, user-facing consent gates that block runtime actions until explicit user approval. Used for enabling potentially risky features like external API routes, no-key fallback routes, or data exfiltration paths.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     CONSENT GATE FLOW                            │
├─────────────────────────────────────────────────────────────────┤
│  1. Runtime detects consent required                             │
│  2. Throw CONSENT_REQUIRED error with missionId                  │
│  3. UI catches error → shows consent gate component             │
│  4. User approves → grantConsentForMission(missionId)           │
│  5. User retries action → runtime checks missionId consent      │
│  6. Action proceeds with consent flag enabled                   │
│  7. Consent cleared after one successful use                     │
└─────────────────────────────────────────────────────────────────┘
```

## Core Implementation

### 1. Runtime Module (consentRegistry.ts)

Store consent state in a Map bound to mission identifiers:

```typescript
// Module-level consent registry
const consentRegistry = new Map<string, boolean>();

// Grant consent for a specific mission
export function grantConsentForMission(missionId: string): void {
  consentRegistry.set(missionId, true);
}

// Check if consent is granted
export function isConsentGrantedForMission(missionId: string): boolean {
  return consentRegistry.get(missionId) === true;
}

// Clear consent after use (one-time consent)
export function clearConsentForMission(missionId: string): void {
  consentRegistry.delete(missionId);
}
```

### 2. Error Type with Mission Binding

Throw structured errors that include mission identification:

```typescript
const CONSENT_REQUIRED_ERROR_CODE = 'CONSENT_REQUIRED';

function createConsentRequiredError(missionId: string, attempts: number): Error {
  const error = new Error(`CONSENT_REQUIRED_EXTERNAL_ROUTES: blocked`);
  (error as { code: string }).code = CONSENT_REQUIRED_ERROR_CODE;
  (error as { missionId: string }).missionId = missionId;
  (error as { attempts: number }).attempts = attempts;
  return error;
}
```

### 3. Runtime Function with Consent Check

```typescript
export async function runWithConsent(
  input: RuntimeInput,
  options: { onConsentRequired?: (missionId: string) => void } = {}
): Promise<RuntimeResult> {
  const missionId = input.missionId ?? generateMissionId();
  const hasConsent = isConsentGrantedForMission(missionId);
  
  // If consent required but not granted, throw
  if (requiresConsent && !hasConsent) {
    options.onConsentRequired?.(missionId);
    throw createConsentRequiredError(missionId, attemptCount);
  }
  
  try {
    const result = await executeRuntime({
      ...input,
      consentEnabled: hasConsent,
    });
    
    // Clear consent after successful use
    clearConsentForMission(missionId);
    return result;
  } catch (error) {
    // Re-throw consent errors with context
    if (isConsentError(error)) throw error;
    throw error;
  }
}
```

### 4. React Hook for UI State

```typescript
import { useState, useCallback } from 'react';
import { grantConsentForMission, denyConsentForMission } from './runtime';

export interface ConsentState {
  consentRequired: boolean;
  missionId: string | null;
  attempts: number;
}

export function useConsentGate() {
  const [state, setState] = useState<ConsentState>({
    consentRequired: false,
    missionId: null,
    attempts: 0,
  });

  const showConsentGate = useCallback((missionId: string, attempts: number) => {
    setState({ consentRequired: true, missionId, attempts });
  }, []);

  const approveConsent = useCallback(() => {
    if (state.missionId) {
      grantConsentForMission(state.missionId);
    }
    setState({ consentRequired: false, missionId: null, attempts: 0 });
    return state.missionId;
  }, [state.missionId]);

  const denyConsent = useCallback(() => {
    if (state.missionId) {
      denyConsentForMission(state.missionId);
    }
    setState({ consentRequired: false, missionId: null, attempts: 0 });
  }, [state.missionId]);

  return { state, showConsentGate, approveConsent, denyConsent };
}
```

### 5. Consent Gate UI Component

```typescript
interface ConsentGateProps {
  attempts: number;
  onApprove: () => void;
  onDeny: () => void;
}

export const ConsentGate: React.FC<ConsentGateProps> = ({
  attempts,
  onApprove,
  onDeny,
}) => (
  <div className="consent-gate">
    <div className="warning-icon">⚠️</div>
    <h3>Limits erreicht – Notfall Free-Routen aktivieren?</h3>
    <p>
      Kostenlose externe Notfall-Routen können Auftrag und Repo-Kontext 
      außerhalb der lokalen Runtime verarbeiten.
    </p>
    <div className="attempts-badge">Versuche: {attempts}</div>
    <div className="actions">
      <button onClick={onApprove}>JA, einmalig aktivieren</button>
      <button onClick={onDeny}>NEIN, lokal weiter</button>
    </div>
  </div>
);
```

### 6. Container Integration

```typescript
function MyContainer() {
  const { state, showConsentGate, approveConsent, denyConsent } = useConsentGate();
  
  const runAction = async (mission: string) => {
    const missionId = generateMissionId();
    
    try {
      const result = await runWithConsent({ mission, missionId });
      return result;
    } catch (error) {
      if (isConsentError(error)) {
        showConsentGate(error.missionId, error.attempts);
        return null;
      }
      throw error;
    }
  };

  return (
    <>
      {/* Main content */}
      <ActionButton onClick={() => runAction(userMission)} />
      
      {/* Consent Gate UI */}
      {state.consentRequired && (
        <ConsentGate
          attempts={state.attempts}
          onApprove={() => {
            approveConsent();
            // User re-triggers action manually or via state
          }}
          onDeny={denyConsent}
        />
      )}
    </>
  );
}
```

## Key Design Principles

### One-Time Consent Per Mission

Consent is bound to a mission ID and automatically cleared after one successful use. This prevents:
- Accidental re-use of consent
- Consent lingering across different operations
- Security bypass through cached consent

### No DOM Manipulation

Never use `document.querySelector` or DOM clicks to trigger retries. Instead:
- Store pending mission in state
- Let user manually re-trigger
- Use React patterns for state updates

### Explicit User Action Required

```
DON'T: Auto-retry without visible consent
DON'T: Use timeouts to bypass consent
DON'T: Cache consent across sessions

DO: Show clear consent gate UI
DO: Bind consent to specific mission ID
DO: Clear consent after one use
```

## Testing Pattern

```typescript
describe('Consent Gate Flow', () => {
  beforeEach(() => clearAllConsents());
  
  it('full flow: consent required → grant → retry succeeds', async () => {
    const missionId = 'test-mission';
    
    // First call fails with consent required
    mockRuntime.mockRejectedValue(createConsentError());
    const result1 = await runWithConsent({ missionId });
    expect(result1.consentRequired).toBe(true);
    
    // User grants consent
    grantConsentForMission(missionId);
    
    // Second call succeeds
    mockRuntime.mockResolvedValue({ ok: true, data: 'result' });
    const result2 = await runWithConsent({ missionId });
    expect(result2.ok).toBe(true);
    expect(mockRuntime).toHaveBeenLastCalledWith(
      expect.objectContaining({ consentEnabled: true })
    );
    
    // Consent is cleared
    expect(isConsentGrantedForMission(missionId)).toBe(false);
  });
});
```

## Common Use Cases

### 1. External API Routes (No-Key Fallback)

When all paid/keyed routes fail and external no-key routes are available:

```typescript
if (paidRoutesExhausted && noKeyRoutesAvailable && !allowExternalNoKey) {
  throw createConsentRequiredError(missionId, attemptCount);
}
```

### 2. Data Export

When user requests data export outside the app:

```typescript
if (operationType === 'export' && targetExternal) {
  throw createConsentRequiredError(missionId, 0);
}
```

### 3. Third-Party Integrations

When connecting to third-party services:

```typescript
if (requiresThirdPartyAccess && !userApprovedThirdParty) {
  throw createConsentRequiredError(missionId, 0);
}
```

## Error Codes

| Code | Description |
|------|-------------|
| `CONSENT_REQUIRED` | Action requires user consent |
| `CONSENT_DENIED` | User explicitly denied consent |
| `CONSENT_EXPIRED` | Consent window has timed out |

## Additional Resources

For detailed implementation patterns, see:
- **`references/runtime-patterns.md`** - Runtime error handling patterns
- **`references/ui-patterns.md`** - Consent UI component patterns
- **`references/security-patterns.md`** - Security considerations and edge cases
