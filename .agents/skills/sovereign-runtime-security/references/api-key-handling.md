# API Key Handling Patterns

## Golden Rules

1. **Never log raw API keys**
2. **Never store keys in version control**
3. **Never expose keys in error messages**
4. **Mask keys in all output**
5. **Validate format before use**

## Key Masking Utilities

```typescript
// Basic masking
function maskApiKey(key: string | undefined): string {
  if (!key) return '[not set]';
  if (key.length <= 8) return '[too short]';
  return `${key.slice(0, 4)}...${key.slice(-4)}`;
}

// Extended masking with key type detection
function maskApiKeyExtended(key: string | undefined): string {
  if (!key) return '[not set]';
  
  const patterns = [
    { prefix: 'sk-', name: 'OpenAI' },
    { prefix: 'AIza', name: 'Google' },
    { prefix: 'gsk_', name: 'Groq' },
    { prefix: 'hf_', name: 'HuggingFace' },
    { prefix: 'sk-or-', name: 'OpenRouter' },
  ];
  
  const matched = patterns.find(p => key.startsWith(p.prefix));
  const masked = key.length > 8 
    ? `${key.slice(0, 4)}...${key.slice(-4)}` 
    : '[***]';
  
  return matched ? `${matched.name}:${masked}` : masked;
}

// Token validation
function isValidApiKey(key: string | undefined): key is string {
  if (!key) return false;
  return (
    key.length >= 20 &&
    !key.includes('\n') &&
    !key.includes(' ')
  );
}
```

## Secure Key Storage

```typescript
// Use environment variables (Vite pattern)
const API_KEYS = {
  gemini: import.meta.env.VITE_GEMINI_API_KEY,
  groq: import.meta.env.VITE_GROQ_API_KEY,
} as const;

// In-memory only storage (never persist)
interface SecureKeyStore {
  keys: Map<string, string>;
  set: (name: string, key: string) => void;
  get: (name: string) => string | undefined;
  clear: () => void;
}

const secureKeyStore: SecureKeyStore = {
  keys: new Map(),
  
  set(name: string, key: string) {
    // Validate before storing
    if (!isValidApiKey(key)) {
      throw new Error(`Invalid API key format for ${name}`);
    }
    this.keys.set(name, key);
  },
  
  get(name: string) {
    return this.keys.get(name);
  },
  
  clear() {
    this.keys.clear();
  },
};
```

## Error Message Sanitization

```typescript
// Wrap API errors to prevent key leakage
function sanitizeApiError(error: unknown): string {
  if (error instanceof Error) {
    let message = error.message;
    
    // Remove any potential key patterns
    message = message.replace(/sk-[a-zA-Z0-9]{20,}/g, '[API_KEY]');
    message = message.replace(/AIza[a-zA-Z0-9_-]{35,}/g, '[API_KEY]');
    message = message.replace(/gsk_[a-zA-Z0-9]{40,}/g, '[API_KEY]');
    
    return message;
  }
  
  return 'Unknown API error';
}

// Usage
try {
  await callApi();
} catch (error) {
  console.error('API Error:', sanitizeApiError(error));
  // Safe to show user
  showError(sanitizeApiError(error));
}
```

## Provider Key Configuration

```typescript
interface ProviderKeyConfig {
  name: string;
  key: string | undefined;
  masked: string;
  configured: boolean;
}

function getProviderKeyConfig(
  provider: string,
  keys: UserApiKeys
): ProviderKeyConfig {
  const keyMap: Record<string, keyof UserApiKeys | undefined> = {
    gemini: keys.gemini,
    groq: keys.groq,
    huggingface: keys.huggingface,
    openrouter: keys.openrouter,
    together: keys.together,
  };
  
  const key = keyMap[provider];
  
  return {
    name: provider,
    key,
    masked: maskApiKey(key),
    configured: isValidApiKey(key),
  };
}

// Usage in UI
function ProviderStatus({ provider, keys }: Props) {
  const config = getProviderKeyConfig(provider, keys);
  
  return (
    <div>
      <span>{config.name}</span>
      <span>{config.masked}</span>
      <Badge type={config.configured ? 'success' : 'warning'}>
        {config.configured ? 'Configured' : 'Not set'}
      </Badge>
    </div>
  );
}
```

## Key Rotation Support

```typescript
interface KeyRotation {
  rotate: (name: string, newKey: string) => Promise<void>;
  validate: (name: string, key: string) => Promise<boolean>;
}

const keyRotation: KeyRotation = {
  async rotate(name: string, newKey: string) {
    // Validate new key
    if (!isValidApiKey(newKey)) {
      throw new Error(`Invalid key format for ${name}`);
    }
    
    // Test key before rotating
    const valid = await this.validate(name, newKey);
    if (!valid) {
      throw new Error(`Key validation failed for ${name}`);
    }
    
    // Update in secure store
    secureKeyStore.set(name, newKey);
    
    // Log rotation (no key data)
    console.log(`API key rotated for ${name}`);
  },
  
  async validate(name: string, key: string): Promise<boolean> {
    try {
      const result = await testApiKey(name, key);
      return result.valid;
    } catch {
      return false;
    }
  },
};
```
