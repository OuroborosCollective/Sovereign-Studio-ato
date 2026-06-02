/**
 * useProviderFallback Hook
 * Provides automatic fallback to free LLM providers when primary fails
 */

import { useState, useCallback, useEffect } from 'react';
import { providerManager, FREE_PROVIDERS, type ProviderType, type ProviderConfig, type ProviderResponse, type ProviderError } from '../providerManager';
import { geminiService } from '../geminiService';

// Re-export for convenience
export { providerManager, FREE_PROVIDERS, type ProviderType, type ProviderConfig, type ProviderResponse, type ProviderError };

export interface ProviderFallbackOptions {
  model?: string;
  temperature?: number;
  maxOutputTokens?: number;
  onFallback?: (from: ProviderType, to: ProviderType, error: string) => void;
  onProviderChanged?: (provider: ProviderType) => void;
}

export interface ProviderFallbackResult {
  generateContent: (prompt: string, apiKey: string) => Promise<string>;
  isLoading: boolean;
  error: string | null;
  currentProvider: ProviderType;
  setProviderApiKey: (provider: ProviderType, key: string) => void;
  configuredProviders: ProviderType[];
}

/**
 * Hook for generating content with automatic provider fallback
 */
export function useProviderFallback(options: ProviderFallbackOptions = {}): ProviderFallbackResult {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentProvider, setCurrentProvider] = useState<ProviderType>('gemini');

  // Set API keys from storage on mount
  useEffect(() => {
    // Load user-configured API keys
    const groqKey = localStorage.getItem('sovereign_groq_api_key');
    const hfKey = localStorage.getItem('sovereign_huggingface_api_key');
    const togetherKey = localStorage.getItem('sovereign_together_api_key');
    const openrouterKey = localStorage.getItem('sovereign_openrouter_api_key');

    if (groqKey) providerManager.setApiKey('groq', groqKey);
    if (hfKey) providerManager.setApiKey('huggingface', hfKey);
    if (togetherKey) providerManager.setApiKey('together', togetherKey);
    if (openrouterKey) providerManager.setApiKey('openrouter', openrouterKey);
  }, []);

  const handleFallback = useCallback((from: ProviderType, to: ProviderType, errorMsg: string) => {
    console.log(`🔄 Fallback: ${from} → ${to}: ${errorMsg}`);
    setCurrentProvider(to);
    options.onFallback?.(from, to, errorMsg);
  }, [options.onFallback]);

  const setProviderApiKey = useCallback((provider: ProviderType, key: string) => {
    providerManager.setApiKey(provider, key);
    // Persist to storage
    const storageKey = `sovereign_${provider}_api_key`;
    if (key.trim()) {
      localStorage.setItem(storageKey, key.trim());
    } else {
      localStorage.removeItem(storageKey);
    }
  }, []);

  const generateContent = useCallback(async (prompt: string, geminiApiKey?: string): Promise<string> => {
    setIsLoading(true);
    setError(null);

    try {
      // Try Gemini first if key is available
      if (geminiApiKey?.trim()) {
        try {
          const result = await geminiService.generateText(geminiApiKey, prompt, {
            model: options.model || 'gemini-1.5-flash',
            temperature: options.temperature,
            maxOutputTokens: options.maxOutputTokens,
          });
          setCurrentProvider('gemini');
          return result;
        } catch (err: any) {
          const errorMsg = err?.message || String(err);
          const isRetryable = 
            errorMsg.includes('429') || 
            errorMsg.includes('quota') || 
            errorMsg.includes('RESOURCE_EXHAUSTED') ||
            errorMsg.includes('authentication') ||
            errorMsg.includes('api key') ||
            err?.status === 401 || 
            err?.status === 403;

          if (!isRetryable) {
            throw err;
          }

          // Fall through to free providers
          handleFallback('gemini', 'groq', errorMsg);
        }
      }

      // Use provider manager for fallback chain
      const response = await providerManager.generateWithFallback(
        geminiApiKey || '',
        'gemini',
        prompt,
        {
          model: options.model || 'gemini-1.5-flash',
          temperature: options.temperature,
          maxOutputTokens: options.maxOutputTokens,
        },
        handleFallback
      );

      setCurrentProvider(response.provider);
      options.onProviderChanged?.(response.provider);
      return response.text;

    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      setError(errorMsg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [options, handleFallback]);

  return {
    generateContent,
    isLoading,
    error,
    currentProvider,
    setProviderApiKey,
    configuredProviders: providerManager.getConfiguredProviders(),
  };
}

/**
 * Provider status info for UI display
 */
export interface ProviderStatus {
  type: ProviderType;
  name: string;
  model: string;
  hasKey: boolean;
  isFree: boolean;
  description: string;
}

export const PROVIDER_INFO: ProviderStatus[] = [
  {
    type: 'gemini',
    name: 'Google Gemini',
    model: 'gemini-1.5-flash',
    hasKey: false,
    isFree: false,
    description: 'Primary provider. Requires Google AI API key.',
  },
  {
    type: 'pollinations',
    name: 'Pollinations AI',
    model: 'openai',
    hasKey: false,
    isFree: true,
    description: 'Free OpenAI-compatible API. No key needed! Fast, reliable fallback.',
  },
  {
    type: 'groq',
    name: 'Groq',
    model: 'llama-3.1-8b-instant',
    hasKey: false,
    isFree: true,
    description: 'Ultra-fast LPU inference. Free tier: 14,400 requests/day.',
  },
  {
    type: 'huggingface',
    name: 'HuggingFace',
    model: 'Llama-3.2-1B-Instruct',
    hasKey: false,
    isFree: true,
    description: 'Open source models. Some require API key.',
  },
  {
    type: 'together',
    name: 'Together AI',
    model: 'Llama-3.2-1B-Instruct',
    hasKey: false,
    isFree: true,
    description: 'Many open models. Free tier available.',
  },
  {
    type: 'openrouter',
    name: 'OpenRouter',
    model: 'llama-3.1-8b-instruct:free',
    hasKey: false,
    isFree: true,
    description: 'Aggregates many providers. Has free models.',
  },
];

export function getProviderStatus(): ProviderStatus[] {
  const configured = providerManager.getConfiguredProviders();
  return PROVIDER_INFO.map(p => ({
    ...p,
    hasKey: configured.includes(p.type),
  }));
}