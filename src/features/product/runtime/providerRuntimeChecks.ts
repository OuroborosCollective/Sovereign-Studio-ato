import type { UserApiKeys } from './userApiKeysContract';


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
  'optional-user-keys',
  'local-safe',
] as const;

const PROVIDER_PRIORITIES: Record<string, number> = {
  'optional-user-keys': 1,
  'local-safe': 999,
};

function byPriority(a: string, b: string): number {
  return (PROVIDER_PRIORITIES[a] ?? 100) - (PROVIDER_PRIORITIES[b] ?? 100);
}

export function getProviderStatus(providerId: string, _keys: UserApiKeys): ProviderStatus {
  const priority = PROVIDER_PRIORITIES[providerId] ?? 100;
  if (providerId === 'optional-user-keys') {
    return {
      providerId,
      status: 'free_available',
      label: 'Sovereign Backend · private LiteLLM',
      priority,
      isAvailable: true,
    };
  }
  if (providerId === 'local-safe') {
    return {
      providerId,
      status: 'free_available',
      label: 'local-safe (analysis only)',
      priority,
      isAvailable: true,
    };
  }
  return {
    providerId,
    status: 'not_configured',
    label: `${providerId} (server-managed only)`,
    priority,
    isAvailable: false,
  };
}

export function getProviderRuntimeReport(keys: UserApiKeys): ProviderRuntimeReport {
  const providers = PROVIDER_IDS.map((providerId) => getProviderStatus(providerId, keys));
  const freeProviders = providers
    .filter((provider) => provider.providerId === 'optional-user-keys')
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
  return {
    keys: {},
    report,
    isSecure: true,
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
