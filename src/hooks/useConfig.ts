import { useState, useEffect, useCallback } from 'react';
import { storageService } from '../shared/api/storageService';
import type { AppConfig } from '../features/config/types';

const DEFAULT_CONFIG: AppConfig = {
  canvas: {
    resolutionScale: 1,
    fpsLimit: 60,
    showStats: false,
    bloomEnabled: true,
  },
  gemini: {
    temperature: 0.7,
    topP: 1,
    maxTokens: 2000,
    model: 'gemini-2.0-flash',
  },
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

  const updateConfig = useCallback((newParams: Partial<AppConfig>) => {
    setConfig((prev) => {
      const updated: AppConfig = { ...prev, ...newParams };
      try {
        storageService.set(CONFIG_STORAGE_KEY, JSON.stringify(updated));
      } catch (err: unknown) {
        console.error('Error saving config:', err);
      }
      return updated;
    });
  }, []);

  const resetToDefaults = useCallback(() => {
    const freshConfig: AppConfig = { ...DEFAULT_CONFIG };
    setConfig(freshConfig);
    try {
      storageService.set(CONFIG_STORAGE_KEY, JSON.stringify(freshConfig));
    } catch (err: unknown) {
      console.error('Error resetting config:', err);
    }
  }, []);

  return {
    config,
    updateConfig,
    resetToDefaults,
    isLoaded,
  };
};