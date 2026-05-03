import { useState, useEffect, useCallback } from 'react';
import { storageService } from '../shared/api/storageService';

export interface AppConfig {
  apiKey: string;
  baseUrl: string;
  model: string;
  temperature: number;
  maxTokens: number;
  topP: number;
}

const DEFAULT_CONFIG: AppConfig = {
  apiKey: '',
  baseUrl: 'https://api.openai.com/v1',
  model: 'gpt-4-turbo',
  temperature: 0.7,
  maxTokens: 2000,
  topP: 1,
};

const CONFIG_STORAGE_KEY = 'app_settings_v1';

export const useConfig = () => {
  const [config, setConfig] = useState<AppConfig>(DEFAULT_CONFIG);
  const [isLoaded, setIsLoaded] = useState<boolean>(false);

  useEffect(() => {
    const loadSavedConfig = async () => {
      try {
        const saved = await storageService.get(CONFIG_STORAGE_KEY);
        if (saved) {
          const parsed = typeof saved === 'string' ? JSON.parse(saved) : saved;
          setConfig((prev) => ({ ...prev, ...parsed }));
        }
      } catch (error) {
        console.error('Error loading config from storage:', error);
      } finally {
        setIsLoaded(true);
      }
    };

    loadSavedConfig();
  }, []);

  const updateConfig = useCallback(async (newParams: Partial<AppConfig>) => {
    setConfig((prev) => {
      const updated: AppConfig = { ...prev, ...newParams };
      storageService.set(CONFIG_STORAGE_KEY, JSON.stringify(updated)).catch((err: unknown) => 
        console.error('Error saving config:', err)
      );
      return updated;
    });
  }, []);

  const resetToDefaults = useCallback(async () => {
    const freshConfig: AppConfig = { ...DEFAULT_CONFIG };
    setConfig(freshConfig);
    await storageService.set(CONFIG_STORAGE_KEY, JSON.stringify(freshConfig));
  }, []);

  return {
    config,
    updateConfig,
    resetToDefaults,
    isLoaded,
  };
};