import { useState, useEffect, useCallback, useMemo } from 'react';
import { getStoredUserKeys, type UserApiKeys } from '../components/UserKeyManager';
import { validateUserApiKeys, getValidatedKeys } from '../runtime/apiKeyValidation';
import { getProviderRuntimeReport, type ProviderRuntimeReport } from '../runtime/providerRuntimeChecks';

export interface UseUserApiKeysReturn {
  userKeys: UserApiKeys;
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
    // Load keys from localStorage on mount
    const stored = getStoredUserKeys();
    setUserKeysState(stored);
    setIsLoading(false);
  }, []);

  // Memoized validation
  const validationReport = useMemo(() => {
    return validateUserApiKeys(userKeys);
  }, [userKeys]);

  // Get only validated keys for safe runtime use
  const validatedKeys = useMemo(() => {
    return getValidatedKeys(userKeys);
  }, [userKeys]);

  // Provider runtime report
  const providerReport = useMemo(() => {
    return getProviderRuntimeReport(userKeys);
  }, [userKeys]);

  const setUserKeys = useCallback((keys: UserApiKeys) => {
    // Only save validated keys to localStorage
    const validated = getValidatedKeys(keys);
    setUserKeysState(keys);
    localStorage.setItem('sovereign-user-api-keys', JSON.stringify(validated));
  }, []);

  const hasKey = useCallback(
    (providerId: keyof UserApiKeys): boolean => {
      return !!userKeys[providerId];
    },
    [userKeys]
  );

  const hasAnyKey = Object.values(userKeys).some((key) => !!key);

  const hasInvalidKeys = validationReport.invalidCount > 0;

  const clearAllKeys = useCallback(() => {
    setUserKeysState({});
    localStorage.removeItem('sovereign-user-api-keys');
  }, []);

  return {
    userKeys,
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
