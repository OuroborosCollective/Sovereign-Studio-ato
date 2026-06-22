import { useState, useEffect, useCallback } from 'react';
import { getStoredUserKeys, type UserApiKeys } from '../components/UserKeyManager';

export interface UseUserApiKeysReturn {
  userKeys: UserApiKeys;
  setUserKeys: (keys: UserApiKeys) => void;
  hasKey: (providerId: keyof UserApiKeys) => boolean;
  hasAnyKey: boolean;
  clearAllKeys: () => void;
  isLoading: boolean;
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

  const setUserKeys = useCallback((keys: UserApiKeys) => {
    setUserKeysState(keys);
    localStorage.setItem('sovereign-user-api-keys', JSON.stringify(keys));
  }, []);

  const hasKey = useCallback(
    (providerId: keyof UserApiKeys): boolean => {
      return !!userKeys[providerId];
    },
    [userKeys]
  );

  const hasAnyKey = Object.values(userKeys).some((key) => !!key);

  const clearAllKeys = useCallback(() => {
    setUserKeysState({});
    localStorage.removeItem('sovereign-user-api-keys');
  }, []);

  return {
    userKeys,
    setUserKeys,
    hasKey,
    hasAnyKey,
    clearAllKeys,
    isLoading,
  };
}
