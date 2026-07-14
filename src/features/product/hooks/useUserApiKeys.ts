import { useState, useEffect, useCallback, useMemo } from 'react';
import type { UserApiKeys } from '../runtime/userApiKeysContract';
import { validateUserApiKeys, getValidatedKeys } from '../runtime/apiKeyValidation';
import { getProviderRuntimeReport, type ProviderRuntimeReport } from '../runtime/providerRuntimeChecks';

export interface UseUserApiKeysReturn {
  userKeys: UserApiKeys;
  userApiKeys: UserApiKeys;
  validatedKeys: UserApiKeys;
  setUserKeys: (keys: UserApiKeys) => void;
  hasKey: (providerId: keyof UserApiKeys) => boolean;
  hasAnyKey: boolean;
  clearAllKeys: () => void;
  isLoading: boolean;
  validationReport: ReturnType<typeof validateUserApiKeys>;
  providerReport: ProviderRuntimeReport;
  suggestedProvider: string;
  fallbackChain: string[];
  hasInvalidKeys: boolean;
}

export function useUserApiKeys(): UseUserApiKeysReturn {
  const [userKeys, setUserKeysState] = useState<UserApiKeys>({});
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setUserKeysState({});
    setIsLoading(false);
  }, []);

  const validationReport = useMemo(() => validateUserApiKeys(userKeys), [userKeys]);

  const validatedKeys = useMemo(() => getValidatedKeys(userKeys), [userKeys]);

  const providerReport = useMemo(() => getProviderRuntimeReport(userKeys), [userKeys]);

  const setUserKeys = useCallback((_keys: UserApiKeys) => {
    setUserKeysState({});
  }, []);

  const hasKey = useCallback((_providerId: keyof UserApiKeys): boolean => false, []);

  const hasAnyKey = false;
  const hasInvalidKeys = validationReport.invalidCount > 0;

  const clearAllKeys = useCallback(() => {
    setUserKeysState({});
  }, []);

  return {
    userKeys,
    userApiKeys: userKeys,
    validatedKeys,
    setUserKeys,
    hasKey,
    hasAnyKey,
    clearAllKeys,
    isLoading,
    validationReport,
    providerReport,
    suggestedProvider: providerReport.suggestedProvider,
    fallbackChain: providerReport.fallbackChain,
    hasInvalidKeys,
  };
}
