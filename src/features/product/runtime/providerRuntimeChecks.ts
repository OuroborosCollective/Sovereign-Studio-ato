import type { UserApiKeys } from './userApiKeysContract';
import { validateUserApiKeys, getValidatedKeys } from './apiKeyValidation';

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

const PROVIDER_IDS = [
  'mlvoca',
  'pollinations',
  'groq',
  'huggingface',
  'together',
  'openrouter',
  'gemini',
  'local-safe',
] as const;

const PROVIDER_PRIORITIES: Record<string, number> = {
  mlvoca: 1,
  pollinations: 2,
  groq: 3,
  huggingface: 4,
  together: 5,
  openrouter: 6,
  gemini: 7,
  'local-safe': 999,
};

function byPriority(a: string, b: string): number {
  return (PROVIDER_PRIORITIES[a] ?? 100) - (PROVIDER_PRIORITIES[b] ?? 100);
}

export function getProviderStatus(providerId: string, keys: UserApiKeys): ProviderStatus {
  const key = keys[providerId as keyof UserApiKeys];
  const priority = PROVIDER_PRIORITIES[providerId] ?? 100;

  if (providerId === 'local-safe') {
    return {
      providerId,
      status: 'free_available',
      label: 'local-safe (Fallback)',
      priority,
      isAvailable: true,
    };
  }

  if (!key || key.trim() === '') {
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

  const validation = validateUserApiKeys({ ...keys, [providerId]: key });
  const providerValidation = validation.validations.find((item) => item.providerId === providerId);

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

export function getProviderRuntimeReport(keys: UserApiKeys): ProviderRuntimeReport {
  const providers = PROVIDER_IDS.map((providerId) => getProviderStatus(providerId, keys));
  const freeProviders = providers
    .filter((provider) => provider.status === 'free_available' && provider.providerId !== 'local-safe')
    .map((provider) => provider.providerId)
    .sort(byPriority);
  const validUserKeyProviders = providers
    .filter((provider) => provider.status === 'user_key_available')
    .map((provider) => provider.providerId)
    .sort(byPriority);
  const invalidUserKeyProviders = providers
    .filter((provider) => provider.status === 'user_key_invalid')
    .map((provider) => provider.providerId)
    .sort(byPriority);

  const fallbackChain = [
    ...freeProviders,
    ...validUserKeyProviders,
    'local-safe',
  ];

  return {
    providers,
    freeProviders,
    validUserKeyProviders,
    invalidUserKeyProviders,
    suggestedProvider: fallbackChain[0] || 'local-safe',
    fallbackChain,
  };
}

export function getSafeRuntimeKeys(keys: UserApiKeys): {
  keys: UserApiKeys;
  report: ProviderRuntimeReport;
  isSecure: boolean;
} {
  const report = getProviderRuntimeReport(keys);
  const safeKeys = getValidatedKeys(keys);
  const hasInvalidKeys = report.invalidUserKeyProviders.length > 0;

  return {
    keys: safeKeys,
    report,
    isSecure: !hasInvalidKeys,
  };
}

export function checkProviderAvailable(providerId: string, keys: UserApiKeys): {
  available: boolean;
  reason: string;
  fallback: string[];
} {
  const report = getProviderRuntimeReport(keys);
  const status = report.providers.find((provider) => provider.providerId === providerId);

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
      fallback: report.fallbackChain.filter((provider) => provider !== providerId),
    };
  }

  return {
    available: true,
    reason: `${providerId}: Ready`,
    fallback: report.fallbackChain.filter((provider) => provider !== providerId),
  };
}
