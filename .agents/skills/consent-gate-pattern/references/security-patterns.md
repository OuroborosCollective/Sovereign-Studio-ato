# Security Patterns for Consent Gates

## Core Security Principles

### 1. Defense in Depth

Consent gates are one layer of defense, not the only one:
- **Runtime defaults** - Never enable risky features by default
- **Explicit consent** - User must actively approve
- **One-time use** - Consent is cleared after successful operation
- **Audit logging** - Track all consent events

### 2. Least Privilege

Only request the minimum consent needed:
- **Granular consent** - Don't bundle multiple permissions
- **Time-bounded** - Consent expires after a window
- **Operation-specific** - Scope consent to specific actions

### 3. User Control

User always has final say:
- **Easy deny** - No dark patterns to force approval
- **Transparent** - Clear explanation of consequences
- **Revocable** - User can change mind before execution

## Threat Model

### What Consent Gates Prevent

| Threat | Protection |
|--------|------------|
| Accidental external API calls | Explicit user approval required |
| Data exfiltration | Consent gate before external transmission |
| Resource exhaustion | Attempt tracking shows when limits near |
| Unauthorized third-party access | Per-operation consent |

### What Consent Gates Don't Prevent

| Threat | Requires |
|--------|----------|
| Malicious user intent | Other controls (rate limiting, monitoring) |
| Session hijacking | Session security measures |
| Credential theft | Credential protection, not consent gates |

## Implementation Security

### Input Validation

```typescript
// Always validate missionId format
function isValidMissionId(id: unknown): id is string {
  if (typeof id !== 'string') return false;
  // Mission IDs should be predictable format
  return /^consent:\d+:[a-zA-Z0-9]+$/.test(id);
}

// Validate consent before granting
function safeGrantConsent(missionId: string): boolean {
  if (!isValidMissionId(missionId)) {
    console.error('Invalid missionId format:', missionId);
    return false;
  }
  grantConsentForMission(missionId);
  return true;
}
```

### Consent Registry Security

```typescript
// Use a private WeakMap for additional encapsulation
const consentRegistry = new Map<string, {
  granted: boolean;
  timestamp: number;
  operationType: string;
}>();

export function grantConsentForMission(
  missionId: string,
  operationType: string = 'default'
): void {
  // Validate missionId
  if (!isValidMissionId(missionId)) {
    throw new Error('Invalid missionId');
  }
  
  // Set consent with metadata
  consentRegistry.set(missionId, {
    granted: true,
    timestamp: Date.now(),
    operationType,
  });
}

export function isConsentGrantedForMission(missionId: string): boolean {
  if (!isValidMissionId(missionId)) {
    return false;
  }
  
  const consent = consentRegistry.get(missionId);
  if (!consent || !consent.granted) {
    return false;
  }
  
  // Check expiration (10 minutes default)
  const EXPIRATION_MS = 10 * 60 * 1000;
  if (Date.now() - consent.timestamp > EXPIRATION_MS) {
    consentRegistry.delete(missionId);
    return false;
  }
  
  return true;
}
```

### Race Condition Prevention

```typescript
// Use a mutex-like pattern for consent operations
const pendingOperations = new Set<string>();

async function executeWithConsent(
  missionId: string,
  operation: () => Promise<void>
): Promise<void> {
  // Prevent double execution
  if (pendingOperations.has(missionId)) {
    throw new Error('Operation already in progress');
  }
  
  pendingOperations.add(missionId);
  
  try {
    // Check and clear consent atomically
    const hasConsent = consumeConsent(missionId);
    if (!hasConsent) {
      throw createConsentRequiredError(missionId);
    }
    
    await operation();
  } finally {
    pendingOperations.delete(missionId);
  }
}

function consumeConsent(missionId: string): boolean {
  const consent = consentRegistry.get(missionId);
  if (!consent || !consent.granted) {
    return false;
  }
  
  // Consume (delete) consent atomically
  consentRegistry.delete(missionId);
  return true;
}
```

## Logging and Auditing

### Consent Event Logging

```typescript
interface ConsentAuditLog {
  timestamp: string;
  event: 'requested' | 'granted' | 'denied' | 'used' | 'expired';
  missionId: string;
  operationType: string;
  userId?: string;
  ipAddress?: string;
  userAgent?: string;
}

function logConsentAudit(event: ConsentAuditLog): void {
  // In production, send to audit log service
  console.log(JSON.stringify({
    type: 'consent_audit',
    ...event,
  }));
  
  // Never log sensitive data
  // - Don't log full mission text
  // - Don't log user credentials
  // - Don't log API keys
}

// Usage with user context
async function grantConsentWithAudit(
  missionId: string,
  userContext: { userId?: string; ip?: string }
): Promise<void> {
  logConsentAudit({
    timestamp: new Date().toISOString(),
    event: 'granted',
    missionId,
    operationType: getOperationType(missionId),
    userId: userContext.userId,
    ipAddress: userContext.ip,
  });
  
  grantConsentForMission(missionId);
}
```

### Security Event Detection

```typescript
interface SecurityAlert {
  type: 'rapid_consent_requests' | 'bulk_consent_grants' | 'consent_after_failure';
  missionId: string;
  timestamp: string;
  details: Record<string, unknown>;
}

// Track consent request patterns
const consentRequestHistory: Array<{
  missionId: string;
  timestamp: number;
}> = [];

function detectConsentAnomalies(missionId: string): SecurityAlert | null {
  const now = Date.now();
  const recentRequests = consentRequestHistory.filter(
    r => now - r.timestamp < 60000 // Last minute
  );
  
  // Alert: More than 5 consent requests in a minute
  if (recentRequests.length > 5) {
    return {
      type: 'rapid_consent_requests',
      missionId,
      timestamp: new Date().toISOString(),
      details: { count: recentRequests.length },
    };
  }
  
  return null;
}
```

## Edge Cases

### Network Failure During Consent

```typescript
async function handleConsentWithFallback(
  missionId: string,
  operation: () => Promise<void>
): Promise<void> {
  try {
    await executeWithConsent(missionId, operation);
  } catch (error) {
    if (isConsentError(error)) {
      // Show consent UI
      showConsentGate(missionId, error.attempts);
      
      // Wait for user response
      const response = await waitForConsentResponse(missionId);
      
      if (response === 'approved') {
        // Retry with consent
        await executeWithConsent(missionId, operation);
      } else {
        // User denied or timeout
        throw new Error('Consent denied or timeout');
      }
    } else {
      throw error;
    }
  }
}

async function waitForConsentResponse(
  missionId: string,
  timeoutMs: number = 300000 // 5 minutes
): Promise<'approved' | 'denied' | 'timeout'> {
  return new Promise((resolve) => {
    const timeout = setTimeout(() => resolve('timeout'), timeoutMs);
    
    // Listen for consent response
    const handler = (event: CustomEvent) => {
      if (event.detail.missionId === missionId) {
        clearTimeout(timeout);
        removeEventListener('consentResponse', handler);
        resolve(event.detail.response);
      }
    };
    
    addEventListener('consentResponse', handler);
  });
}
```

### Tab Synchronization

```typescript
// Sync consent state across tabs
class ConsentTabSync {
  private channel: BroadcastChannel;
  
  constructor() {
    this.channel = new BroadcastChannel('consent-sync');
    this.channel.onmessage = this.handleMessage.bind(this);
  }
  
  private handleMessage(event: MessageEvent): void {
    const { type, missionId } = event.data;
    
    switch (type) {
      case 'consent_granted':
        // Sync consent to this tab
        grantConsentForMission(missionId);
        break;
        
      case 'consent_denied':
        denyConsentForMission(missionId);
        break;
        
      case 'tab_closed':
        // Clean up if initiating tab closed
        this.cleanupMission(missionId);
        break;
    }
  }
  
  broadcastConsentGranted(missionId: string): void {
    this.channel.postMessage({
      type: 'consent_granted',
      missionId,
      sourceTab: getCurrentTabId(),
    });
  }
  
  broadcastConsentDenied(missionId: string): void {
    this.channel.postMessage({
      type: 'consent_denied',
      missionId,
      sourceTab: getCurrentTabId(),
    });
  }
}
```

### Session Expiration

```typescript
// Handle consent during session expiration
const SESSION_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes

function handleSessionExpiration(): void {
  // Clear all pending consents on session timeout
  clearAllConsents();
  
  logConsentAudit({
    timestamp: new Date().toISOString(),
    event: 'expired',
    missionId: '*',
    operationType: 'session',
    details: { reason: 'session_timeout' },
  });
}

// Set up session timeout listener
if (typeof window !== 'undefined') {
  let lastActivity = Date.now();
  
  ['click', 'keypress', 'scroll'].forEach(event => {
    window.addEventListener(event, () => {
      lastActivity = Date.now();
    });
  });
  
  setInterval(() => {
    if (Date.now() - lastActivity > SESSION_TIMEOUT_MS) {
      handleSessionExpiration();
    }
  }, 60000); // Check every minute
}
```

## Compliance Considerations

### GDPR (EU)

Consent gates help with GDPR compliance for:
- Processing personal data outside EU
- Third-party data sharing
- Profiling and automated decisions

Required elements:
- Clear explanation of what data is processed
- Purpose specification
- Easy withdrawal mechanism
- Record of consent

### CCPA (California)

Consent gates support CCPA requirements:
- Right to know what data is shared
- Right to opt-out of sale
- Non-discrimination for exercising rights

### Audit Trail Requirements

Maintain records of:
- When consent was requested
- What information was provided
- User response (granted/denied)
- Timestamp and context
- Any changes to consent

```typescript
interface ConsentRecord {
  id: string;
  missionId: string;
  requestedAt: string;
  respondedAt: string;
  response: 'granted' | 'denied' | 'expired';
  providedInformation: string[];
  operationType: string;
  metadata: Record<string, unknown>;
}

function createConsentRecord(
  missionId: string,
  information: string[]
): ConsentRecord {
  return {
    id: generateRecordId(),
    missionId,
    requestedAt: new Date().toISOString(),
    respondedAt: '', // Filled when responded
    response: 'expired',
    providedInformation: information,
    operationType: getOperationType(missionId),
    metadata: {},
  };
}
```
