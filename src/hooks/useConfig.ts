import { useState, useEffect, useCallback } from 'react';
import { storageService } from '../services/storageService';

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
    const loadSavedConfig = async (): Promise<void> => {
      try {
        const saved = await storageService.getItem<AppConfig>(CONFIG_STORAGE_KEY);
        if (saved && typeof saved === 'object') {
          setConfig((prev: AppConfig) => ({ ...prev, ...saved }));
        }
      } catch (error) {
        console.error('Error loading config from storage:', error);
      } finally {
        setIsLoaded(true);
      }
    };

    void loadSavedConfig();
  }, []);

  const updateConfig = useCallback(async (newParams: Partial<AppConfig>): Promise<void> => {
    setConfig((prev: AppConfig) => {
      const updated: AppConfig = { ...prev, ...(newParams && typeof newParams === 'object' ? newParams : {}) };
      storageService.setItem<AppConfig>(CONFIG_STORAGE_KEY, updated).catch((err: unknown) => 
        console.error('Error saving config:', err)
      );
      return updated;
    });
  }, []);

  const resetToDefaults = useCallback(async (): Promise<void> => {
    setConfig(DEFAULT_CONFIG);
    await storageService.setItem<AppConfig>(CONFIG_STORAGE_KEY, DEFAULT_CONFIG);
  }, []);

  return {
    config,
    updateConfig,
    resetToDefaults,
    isLoaded,
  };
};