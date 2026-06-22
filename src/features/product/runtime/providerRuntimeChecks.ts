import type { UserApiKeys } from '../components/UserKeyManager';
import { validateUserApiKeys, getValidatedKeys, shouldUseProvider } from './apiKeyValidation';

export type LlmProviderStatus = 
  | 'free_available'
  | 'user_key_available'
  | 'user_key_invalid'
  | 'not_configured';

export interface ProviderStatus {
  providerId: string;
  status: LlmProviderStatus;
  label: string;
  priority: number;
  isAvailable: boolean;
}

export interface ProviderRuntimeReport {
  providers: ProviderStatus[];
  freeProviders: string[];
  validUserKeyProviders: string[];
  invalidUserKeyProviders: string[];
  suggestedProvider: string;
  fallbackChain: string[];
}

// Provider priority order (lower = higher priority)
const PROVIDER_PRIORITIES: Record<string, number> = {
  pollinations: 1,
  mlvoca: 2,
  groq: 3,
  huggingface: 4,
  together: 5,
  openrouter: 6,
  gemini: 7,
  'local-safe': 999,
};

/**
 * Get provider status with runtime checks
 */
export function getProviderStatus(providerId: string, keys: UserApiKeys): ProviderStatus {
  const key = keys[providerId as keyof UserApiKeys];
  const priority = PROVIDER_PRIORITIES[providerId] ?? 100;

  // Check if key is provided
  if (!key || key.trim() === '') {
    // Check if this is a free provider
    if (providerId === 'mlvoca' || providerId === 'pollinations') {
      return {
        providerId,
        status: 'free_available',
        label: `${providerId} (Free)`,
        priority,
        isAvailable: true,
      };
    }
    return {
      providerId,
      status: 'not_configured',
      label: `${providerId} (No key)`,
      priority,
      isAvailable: false,
    };
  }

  // Key provided, validate it
  const validation = validateUserApiKeys({ ...keys, [providerId]: key });
  const providerValidation = validation.validations.find(v => v.providerId === providerId);

  if (providerValidation?.isValid) {
    return {
      providerId,
      status: 'user_key_available',
      label: `${providerId} (User Key)`,
      priority,
      isAvailable: true,
    };
  }

  return {
    providerId,
    status: 'user_key_invalid',
    label: `${providerId} (Invalid Key)`,
    priority,
    isAvailable: false,
  };
}

/**
 * Get runtime report for all providers
 */
export function getProviderRuntimeReport(keys: UserApiKeys): ProviderRuntimeReport {
  const providerIds = [
    'pollinations',
    'mlvoca',
    'groq',
    'huggingface',
    'together',
    'openrouter',
    'gemini',
    'local-safe',
  ];

  const providers: ProviderStatus[] = [];
  const freeProviders: string[] = [];
  const validUserKeyProviders: string[] = [];
  const invalidUserKeyProviders: string[] = [];

  for (const providerId of providerIds) {
    const status = getProviderStatus(providerId, keys);
    providers.push(status);

    if (status.status === 'free_available') {
      freeProviders.push(providerId);
    } else if (status.status === 'user_key_available') {
      validUserKeyProviders.push(providerId);
    } else if (status.status === 'user_key_invalid') {
      invalidUserKeyProviders.push(providerId);
    }
  }

  // Build fallback chain
  const fallbackChain = [
    ...validUserKeyProviders,
    ...freeProviders,
    'local-safe',
  ];

  // Suggest best available provider
  const suggestedProvider = fallbackChain[0] || 'local-safe';

  return {
    providers,
    freeProviders,
    validUserKeyProviders,
    invalidUserKeyProviders,
    suggestedProvider,
    fallbackChain,
  };
}

/**
 * Runtime check: Get validated keys for safe runtime use
 */
export function getSafeRuntimeKeys(keys: UserApiKeys): {
  keys: UserApiKeys;
  report: ProviderRuntimeReport;
  isSecure: boolean;
} {
  const report = getProviderRuntimeReport(keys);
  
  // Only include keys that are validated
  const safeKeys = getValidatedKeys(keys);
  
  // Check if any invalid keys were provided
  const hasInvalidKeys = report.invalidUserKeyProviders.length > 0;
  
  return {
    keys: safeKeys,
    report,
    isSecure: !hasInvalidKeys,
  };
}

/**
 * Runtime check: Verify provider availability before attempting
 */
export function checkProviderAvailable(providerId: string, keys: UserApiKeys): {
  available: boolean;
  reason: string;
  fallback: string[];
} {
  const report = getProviderRuntimeReport(keys);
  const status = report.providers.find(p => p.providerId === providerId);

  if (!status) {
    return {
      available: false,
      reason: `Unknown provider: ${providerId}`,
      fallback: report.fallbackChain,
    };
  }

  if (!status.isAvailable) {
    return {
      available: false,
      reason: `${providerId}: ${status.status.replace(/_/g, ' ')}`,
      fallback: report.fallbackChain.filter(p => p !== providerId),
    };
  }

  return {
    available: true,
    reason: `${providerId}: Ready`,
    fallback: report.fallbackChain.filter(p => p !== providerId),
  };
}
