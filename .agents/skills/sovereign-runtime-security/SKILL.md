---
name: sovereign-runtime-security
description: This skill should be used when implementing security-hardened runtime defaults, API key handling, external route controls, or defensive parameter patterns in Sovereign Studio V3. Triggers include phrases like "default false", "security default", "hardened runtime", "safe by default", "parameter defaults", "block external routes", "no-key routes", "user key routes", "API key handling".
---

# Sovereign Runtime Security Patterns

## Purpose

Implement security-by-default patterns in runtime code. Ensure that potentially risky features are disabled by default and require explicit user opt-in.

## Core Principle

**Default to safest.** Runtime parameters that control external access, data exfiltration, or API usage should default to `false` unless explicitly enabled.

## Common Patterns

### 1. Safe Parameter Defaults

```typescript
// ❌ BAD: Default to true (risky)
interface RuntimeInput {
  allowExternalNoKey: boolean = true;
}

// ✅ GOOD: Default to false (safe)
interface RuntimeInput {
  allowExternalNoKey?: boolean;
}

// In implementation:
const effectiveValue = input.allowExternalNoKey ?? false;
```

### 2. Explicit Opt-In Flags

```typescript
interface RuntimeConfig {
  // Require explicit true
  allowExternalNoKey: boolean;
  allowUserKeyRoutes: boolean;
  allowThirdPartyIntegrations: boolean;
  allowDataExport: boolean;
}

// Validation
function validateConfig(config: RuntimeConfig): void {
  if (config.allowExternalNoKey !== true) {
    config.allowExternalNoKey = false; // Force safe default
  }
}
```

### 3. Runtime Guard Functions

```typescript
// Guard that checks all security flags before allowing operation
function assertSafeRuntime(input: RuntimeInput): void {
  // External routes need explicit consent
  if (input.allowExternalNoKey && !input.userConsented) {
    throw new SecurityError('External routes require explicit consent');
  }
  
  // User key routes need token present
  if (input.allowUserKeyRoutes && !hasValidApiKeys(input.userKeys)) {
    throw new SecurityError('User key routes require valid API keys');
  }
}
```

### 4. Parameter Hardening in Multiple Layers

```typescript
// Layer 1: Function parameter
export async function runSovereignLlmRuntime(
  input: SovereignLlmRuntimeInput
): Promise<SovereignLlmRuntimeResult> {
  // Layer 2: Nullish coalescing to false
  const allowExternal = input.allowExternalNoKey ?? false;
  
  // Layer 3: Runtime guard
  if (allowExternal) {
    assertConsentGiven();
  }
  
  // Use hardened value
  return executeRuntime({ allowExternalNoKey: allowExternal });
}

// In calling code:
await runSovereignLlmRuntime({
  ...input,
  allowExternalNoKey: false, // Explicit safe default
});
```

## External Route Control

### Route Classification

| Route Type | Requires | Default |
|------------|----------|---------|
| Local-only | Nothing | `true` (always allowed) |
| User-key routes | Valid API key | `false` (must opt-in) |
| External no-key routes | Explicit consent | `false` (must opt-in) |
| Third-party routes | Consent + verification | `false` (must opt-in) |

### Implementation

```typescript
interface RouteConfig {
  allowLocal: boolean;      // Default: true
  allowUserKey: boolean;    // Default: false
  allowExternalNoKey: boolean; // Default: false
}

const DEFAULT_ROUTE_CONFIG: RouteConfig = {
  allowLocal: true,
  allowUserKey: false,
  allowExternalNoKey: false,
};

function mergeRouteConfig(
  provided: Partial<RouteConfig> = {},
  defaults: RouteConfig = DEFAULT_ROUTE_CONFIG
): RouteConfig {
  return {
    allowLocal: provided.allowLocal ?? defaults.allowLocal,
    allowUserKey: provided.allowUserKey ?? defaults.allowUserKey,
    allowExternalNoKey: provided.allowExternalNoKey ?? defaults.allowExternalNoKey,
  };
}
```

## API Key Handling

### Never Log Secrets

```typescript
// ❌ BAD: Logging API keys
console.log(`Using API key: ${apiKey}`);

// ✅ GOOD: Never log secrets
console.log(`Using API key: [REDACTED]`);
```

### Mask Keys in Debug Output

```typescript
function maskKey(key: string): string {
  if (key.length <= 8) return '[SHORT]';
  return `${key.slice(0, 4)}...${key.slice(-4)}`;
}

// Usage
console.log(`API key: ${maskKey(userKeys.gemini)}`);
// Output: API key: sk_...7xYz
```

### Validate Key Format Before Use

```typescript
function isValidApiKeyFormat(key: string | undefined): boolean {
  if (!key) return false;
  // Check common key formats
  return (
    key.startsWith('sk-') ||      // OpenAI
    key.startsWith('AIza') ||      // Google
    key.startsWith('gsk_') ||      // Groq
    key.length >= 20               // Generic minimum
  );
}
```

## Testing Security Defaults

```typescript
describe('Security Default Tests', () => {
  it('defaults allowExternalNoKey to false', async () => {
    const result = await runWithDefaults({});
    expect(result.config.allowExternalNoKey).toBe(false);
  });
  
  it('explicit true is allowed', async () => {
    const result = await runWithDefaults({ allowExternalNoKey: true });
    expect(result.config.allowExternalNoKey).toBe(true);
  });
  
  it('cannot bypass with null', async () => {
    const result = await runWithDefaults({ 
      allowExternalNoKey: null as any 
    });
    expect(result.config.allowExternalNoKey).toBe(false);
  });
});
```

## Review Checklist

Before merging any runtime security changes:

- [ ] All risky flags default to `false`
- [ ] No secrets are logged (check console.log, debug output)
- [ ] API keys are masked in all output
- [ ] Consent gates are in place for external routes
- [ ] Tests verify default values
- [ ] Error messages don't leak sensitive info

## Additional Resources

For detailed patterns:
- **`references/api-key-handling.md`** - API key security patterns
- **`references/route-guards.md`** - Route protection patterns
- **`references/audit-logging.md`** - Security audit logging
