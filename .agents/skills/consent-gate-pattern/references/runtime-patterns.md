# Runtime Patterns for Consent Gates

## Error Handling Patterns

### Structured Error Creation

Always create typed errors with consistent structure:

```typescript
interface ConsentError extends Error {
  code: string;
  missionId: string;
  attempts: number;
  retryable: boolean;
}

function createConsentError(
  message: string,
  missionId: string,
  attempts: number,
  options: { retryable?: boolean } = {}
): ConsentError {
  const error = new Error(message) as ConsentError;
  error.code = 'CONSENT_REQUIRED';
  error.missionId = missionId;
  error.attempts = attempts;
  error.retryable = options.retryable ?? true;
  return error;
}
```

### Error Detection Helper

```typescript
function isConsentError(error: unknown): error is ConsentError {
  return (
    error instanceof Error &&
    'code' in error &&
    (error as { code: string }).code === 'CONSENT_REQUIRED'
  );
}
```

## Mission ID Generation

Generate unique, deterministic mission IDs:

```typescript
function generateMissionId(): string {
  return `mission:${Date.now()}:${Math.random().toString(36).slice(2, 9)}`;
}

function generateMissionIdFromContext(
  mission: string,
  repoId?: string,
  userId?: string
): string {
  const timestamp = Date.now();
  const missionHash = mission.slice(0, 32).replace(/[^a-zA-Z0-9]/g, '');
  const parts = [timestamp, missionHash];
  if (repoId) parts.push(repoId);
  if (userId) parts.push(userId);
  return `consent:${parts.join(':')}`;
}
```

## Retry Logic Patterns

### Consent-Aware Retry Loop

```typescript
async function executeWithConsent<T>(
  operation: (consent: boolean) => Promise<T>,
  options: {
    maxAttempts?: number;
    onConsentRequired?: (missionId: string, attempts: number) => void;
    onError?: (error: Error, attempt: number) => void;
  } = {}
): Promise<{ result: T; consentGranted: boolean }> {
  const maxAttempts = options.maxAttempts ?? 3;
  let attempts = 0;
  
  while (attempts < maxAttempts) {
    attempts++;
    const consentGranted = isConsentGrantedForMission(currentMissionId);
    
    try {
      const result = await operation(consentGranted);
      clearConsentForMission(currentMissionId);
      return { result, consentGranted };
    } catch (error) {
      if (isConsentError(error)) {
        options.onConsentRequired?.(error.missionId, error.attempts);
        throw error; // Let UI handle consent flow
      }
      
      options.onError?.(error as Error, attempts);
      
      if (attempts >= maxAttempts) {
        throw error;
      }
      
      // Exponential backoff
      await sleep(Math.pow(2, attempts) * 100);
    }
  }
  
  throw new Error('Max attempts exceeded');
}
```

## State Management Patterns

### Zustand Store Integration

```typescript
import { create } from 'zustand';

interface ConsentStore {
  pendingConsents: Map<string, { missionId: string; attempts: number; timestamp: number }>;
  grantConsent: (missionId: string) => void;
  denyConsent: (missionId: string) => void;
  clearExpiredConsents: () => void;
}

export const useConsentStore = create<ConsentStore>((set, get) => ({
  pendingConsents: new Map(),
  
  grantConsent: (missionId) => {
    set((state) => {
      const newMap = new Map(state.pendingConsents);
      newMap.delete(missionId);
      return { pendingConsents: newMap };
    });
    grantConsentForMission(missionId);
  },
  
  denyConsent: (missionId) => {
    set((state) => {
      const newMap = new Map(state.pendingConsents);
      newMap.delete(missionId);
      return { pendingConsents: newMap };
    });
    denyConsentForMission(missionId);
  },
  
  clearExpiredConsents: () => {
    const now = Date.now();
    const expirationMs = 5 * 60 * 1000; // 5 minutes
    
    set((state) => {
      const newMap = new Map(state.pendingConsents);
      for (const [id, consent] of newMap) {
        if (now - consent.timestamp > expirationMs) {
          newMap.delete(id);
          denyConsentForMission(id);
        }
      }
      return { pendingConsents: newMap };
    });
  },
}));
```

## TypeScript Patterns

### Discriminated Union for Results

```typescript
type ConsentResult<T> =
  | { ok: true; data: T; missionId: string }
  | { ok: false; consentRequired: true; missionId: string; attempts: number }
  | { ok: false; consentRequired: false; error: string };

// Usage
async function processWithConsent(input: Input): Promise<ConsentResult<Output>> {
  const missionId = generateMissionId();
  
  if (requiresConsent && !isConsentGrantedForMission(missionId)) {
    return {
      ok: false,
      consentRequired: true,
      missionId,
      attempts: currentAttempts,
    };
  }
  
  try {
    const data = await process(input);
    return { ok: true, data, missionId };
  } catch (error) {
    return {
      ok: false,
      consentRequired: false,
      error: (error as Error).message,
    };
  }
}
```

## Logging Patterns

```typescript
function logConsentEvent(
  event: 'requested' | 'granted' | 'denied' | 'expired' | 'used',
  missionId: string,
  context?: Record<string, unknown>
): void {
  console.log(JSON.stringify({
    type: 'consent_event',
    event,
    missionId,
    timestamp: new Date().toISOString(),
    ...context,
  }));
}

// Usage
logConsentEvent('requested', missionId, { attempts, operation: 'external_api' });
logConsentEvent('granted', missionId, { userId: currentUser });
logConsentEvent('used', missionId, { duration: Date.now() - startTime });
```

## Cleanup Patterns

### Periodic Cleanup

```typescript
// In app initialization
setInterval(() => {
  const now = Date.now();
  const expirationMs = 10 * 60 * 1000; // 10 minutes
  
  for (const [missionId, data] of consentRegistry) {
    if (now - data.timestamp > expirationMs) {
      consentRegistry.delete(missionId);
      logConsentEvent('expired', missionId);
    }
  }
}, 60 * 1000); // Every minute
```

### Cleanup on Navigation

```typescript
// In React router or navigation handler
function handleNavigation() {
  // Clear all pending consents on significant navigation
  if (isSignificantNavigation()) {
    clearAllConsents();
    logConsentEvent('expired', '*', { reason: 'navigation' });
  }
}
```
