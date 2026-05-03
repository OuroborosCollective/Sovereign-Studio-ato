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
    const loadSavedConfig = async () => {
      try {
        const saved = await storageService.get<AppConfig>(CONFIG_STORAGE_KEY);
        if (saved) {
          setConfig({ ...DEFAULT_CONFIG, ...saved });
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
      const updated = { ...prev, ...newParams };
      storageService.set(CONFIG_STORAGE_KEY, updated).catch((err) => 
        console.error('Error saving config:', err)
      );
      return updated;
    });
  }, []);

  const resetToDefaults = useCallback(async () => {
    setConfig(DEFAULT_CONFIG);
    await storageService.set(CONFIG_STORAGE_KEY, DEFAULT_CONFIG);
  }, []);

  return {
    config,
    updateConfig,
    resetToDefaults,
    isLoaded,
  };
};