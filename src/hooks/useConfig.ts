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
        const saved = await storageService.get<unknown>(CONFIG_STORAGE_KEY);
        // Behebe Spread-Fehler durch Prüfung auf Objekt-Typ
        if (saved !== null && typeof saved === 'object' && !Array.isArray(saved)) {
          setConfig((prev) => ({ ...prev, ...(saved as Partial<AppConfig>) }));
        }
      } catch (error) {
        console.error('Error loading config from storage:', error);
      } finally {
        setIsLoaded(true);
      }
    };

    void loadSavedConfig();
  }, []);

  const updateConfig = useCallback(async (newParams: Partial<AppConfig>) => {
    // Sicherstellen, dass ein gültiges Objekt übergeben wurde
    if (!newParams || typeof newParams !== 'object' || Array.isArray(newParams)) {
      return;
    }

    setConfig((prev) => {
      const updated: AppConfig = { ...prev, ...newParams };
      void storageService.set(CONFIG_STORAGE_KEY, updated).catch((err: unknown) => 
        console.error('Error saving config:', err)
      );
      return updated;
    });
  }, []);

  const resetToDefaults = useCallback(async () => {
    const freshConfig: AppConfig = { ...DEFAULT_CONFIG };
    setConfig(freshConfig);
    await storageService.set(CONFIG_STORAGE_KEY, freshConfig);
  }, []);

  return {
    config,
    updateConfig,
    resetToDefaults,
    isLoaded,
  };
};